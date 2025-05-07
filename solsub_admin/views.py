from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from .mongo_models import UserProfile, MatchId, Payment, ClusterDetails
from .models import Cluster
from datetime import datetime, timedelta
import json
import calendar
import logging
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    # Get counts for dashboard stats
    user_count = UserProfile.objects.count()
    
    # Count active match IDs (Trial Active or Paid Active)
    now = datetime.now()
    active_match_ids = 0
    for match_id in MatchId.objects:
        is_active = match_id.valid_till and now <= match_id.valid_till
        if is_active:  # Includes both Trial Active and Paid Active
            active_match_ids += 1
    
    # Get clusters with at least one active match ID
    active_clusters = set()
    for match_id in MatchId.objects(valid_till__gt=now):
        active_clusters.add(match_id.cluster_name)
    
    # Calculate total revenue
    total_revenue = 0
    for payment in Payment.objects(status='Completed'):
        total_revenue += float(payment.amount)
    
    # Calculate trial conversion rate
    trial_match_ids = MatchId.objects(is_trial=True).count()
    converted_trials = 0
    for match_id in MatchId.objects(is_trial=True):
        if match_id.last_paid_on and match_id.last_paid_on > match_id.created_on:
            converted_trials += 1
    
    trial_conversion_rate = 0
    if trial_match_ids > 0:
        trial_conversion_rate = (converted_trials / trial_match_ids) * 100
    
    context = {
        'user_count': user_count,
        'active_match_ids': active_match_ids,
        'cluster_count': len(active_clusters),  # Only clusters with active match IDs
        'total_revenue': total_revenue,
        'trial_conversion_rate': trial_conversion_rate,
    }
    
    return render(request, 'dashboard/index.html', context)

@login_required
def users(request):
    # Get all users
    all_users = []
    
    for user in UserProfile.objects:
        all_users.append({
            'id': user.user_id,
            'username': user.username,
            'email': user.email,
            'created_at': user.created_at.strftime('%Y-%m-%d') if user.created_at else '-',
            'cluster_count': len(user.clusters),
            'has_bank_details': user.bank_details is not None,
        })
    
    return render(request, 'dashboard/users.html', {'users': all_users})

@login_required
def payments(request):
    # Get all payments
    all_payments = []
    
    for payment in Payment.objects:
        # Get cluster_name from api_key
        cluster_name = payment.cluster_name
        
        all_payments.append({
            'id': payment.payment_id,
            'match_id': payment.match_id,
            'cluster_name': cluster_name,
            'amount': float(payment.amount),
            'status': payment.status,
            'date': payment.payment_date.strftime('%Y-%m-%d'),
            'user_email': payment.user_email if payment.user_email else '-',
        })
    
    return render(request, 'dashboard/payments.html', {'payments': all_payments})

@login_required
def match_ids(request):
    # Get all match IDs
    all_match_ids = []
    now = datetime.now()
    
    for match_id in MatchId.objects:
        is_active = match_id.valid_till and now <= match_id.valid_till
        
        if match_id.is_trial and is_active:
            status = "Trial Active"
        elif is_active:
            status = "Paid Active"
        else:
            status = "Inactive"
        
        all_match_ids.append({
            'id': match_id.match_id,
            'cluster_name': match_id.cluster_name,
            'created_on': match_id.created_on.strftime('%Y-%m-%d'),
            'last_paid_on': match_id.last_paid_on.strftime('%Y-%m-%d') if match_id.last_paid_on else '-',
            'valid_till': match_id.valid_till.strftime('%Y-%m-%d') if match_id.valid_till else '-',
            'is_trial': match_id.is_trial,
            'status': status,
        })
    
    return render(request, 'dashboard/match_ids.html', {'match_ids': all_match_ids})

@login_required
def clusters(request):
    # Get all unique clusters
    all_clusters = []
    for user in UserProfile.objects:
        for cluster in user.clusters:
            # Count active match IDs for this cluster
            active_count = MatchId.objects(
                cluster_name=cluster.cluster_name,
                valid_till__gt=datetime.now()
            ).count()
            
            all_clusters.append({
                'name': cluster.cluster_name,
                'price': float(cluster.cluster_price),
                'timeline_days': cluster.timeline_days,
                'trial_period': cluster.trial_period,
                'match_id_type': cluster.match_id_type,
                'active_subscriptions': active_count,
                'api_key': cluster.api_key,
            })
    
    # Remove duplicates based on cluster name
    unique_clusters = []
    cluster_names = set()
    for cluster in all_clusters:
        if cluster['name'] not in cluster_names:
            cluster_names.add(cluster['name'])
            unique_clusters.append(cluster)
    
    return render(request, 'dashboard/clusters.html', {'clusters': unique_clusters})

@login_required
def reports(request):
    # Get data for reports
    now = datetime.now()
    
    # Monthly revenue data
    monthly_revenue = {}
    for payment in Payment.objects(status='Completed'):
        if payment.payment_date:  # Check if payment_date is not None
            month_year = payment.payment_date.strftime('%Y-%m')
            if month_year not in monthly_revenue:
                monthly_revenue[month_year] = 0
            monthly_revenue[month_year] += float(payment.amount)
    
    # Cluster performance data
    cluster_performance = {}
    for payment in Payment.objects(status='Completed'):
        cluster_name = payment.cluster_name
        if cluster_name:
            if cluster_name not in cluster_performance:
                cluster_performance[cluster_name] = {
                    'revenue': 0,
                    'count': 0
                }
            cluster_performance[cluster_name]['revenue'] += float(payment.amount)
            cluster_performance[cluster_name]['count'] += 1
    
    # User growth data (safe, since created_at is required)
    user_growth = {}
    for user in UserProfile.objects:
        if user.created_at:  # Check if created_at is not None
            month_year = user.created_at.strftime('%Y-%m')
            if month_year not in user_growth:
                user_growth[month_year] = 0
            user_growth[month_year] += 1
    
    # Get all cluster names for the dropdown
    cluster_names = []
    for user in UserProfile.objects:
        for cluster in user.clusters:
            if cluster.cluster_name not in cluster_names:
                cluster_names.append(cluster.cluster_name)
    
    context = {
        'monthly_revenue': monthly_revenue,
        'cluster_performance': cluster_performance,
        'user_growth': user_growth,
        'cluster_names': cluster_names,
    }
    
    return render(request, 'dashboard/reports.html', context)

@login_required
def cluster_owner_payment_report(request):
    # Get the selected cluster name from the request
    cluster_name = request.GET.get('cluster_name', '')
    
    # Get the current month and year
    now = datetime.now()
    current_month = now.month
    current_year = now.year
    
    # Calculate the first and last day of the current month
    first_day = datetime(current_year, current_month, 1)
    if current_month == 12:
        last_day = datetime(current_year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(current_year, current_month + 1, 1) - timedelta(days=1)
    
    # Get all payments for the selected cluster in the current month
    payments_data = []
    total_amount = 0
    
    # Get api_key for the selected cluster
    api_key = None
    if cluster_name:
        for user in UserProfile.objects:
            for cluster in user.clusters:
                if cluster.cluster_name == cluster_name:
                    api_key = cluster.api_key
                    break
            if api_key:
                break
    
    # Filter query based on whether a cluster was selected
    if api_key:
        payments = Payment.objects(
            api_key=api_key,
            payment_date__gte=first_day,
            payment_date__lte=last_day,
            status='Completed'
        )
    else:
        payments = Payment.objects(
            payment_date__gte=first_day,
            payment_date__lte=last_day,
            status='Completed'
        )
    
    # Process payments
    for payment in payments:
        payment_cluster_name = payment.cluster_name
        payments_data.append({
            'id': payment.payment_id,
            'match_id': payment.match_id,
            'cluster_name': payment_cluster_name,
            'amount': float(payment.amount),
            'date': payment.payment_date.strftime('%Y-%m-%d'),
            'user_email': payment.user_email if payment.user_email else '-',
        })
        total_amount += float(payment.amount)
    
    # Get all cluster names for the dropdown
    cluster_names = []
    for user in UserProfile.objects:
        for cluster in user.clusters:
            if cluster.cluster_name not in cluster_names:
                cluster_names.append(cluster.cluster_name)
    
    # Get cluster owner information if a cluster is selected
    owner_info = None
    if cluster_name:
        for user in UserProfile.objects:
            for cluster in user.clusters:
                if cluster.cluster_name == cluster_name:
                    owner_info = {
                        'username': user.username,
                        'email': user.email,
                        'has_bank_details': user.bank_details is not None,
                    }
                    if user.bank_details:
                        owner_info['bank_details'] = {
                            'bank_name': user.bank_details.bank_name,
                            'account_number': user.bank_details.account_number,
                            'ifsc_code': user.bank_details.ifsc_code,
                            'branch_name': user.bank_details.branch_name,
                        }
                    break
            if owner_info:
                break
    
    context = {
        'cluster_name': cluster_name,
        'month_name': now.strftime('%B'),
        'year': current_year,
        'payments': payments_data,
        'total_amount': total_amount,
        'cluster_names': cluster_names,
        'owner_info': owner_info,
    }
    
    # Check if PDF download was requested
    if request.GET.get('format') == 'pdf':
        return generate_payment_report_pdf(context)
    
    return render(request, 'dashboard/cluster_owner_payment_report.html', context)

def generate_payment_report_pdf(context):
    """Generate a PDF report for cluster owner payments"""
    # Create a file-like buffer to receive PDF data
    buffer = io.BytesIO()
    
    # Create the PDF object, using the buffer as its "file"
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    subtitle_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Add title
    if context['cluster_name']:
        title = f"Payment Report for {context['cluster_name']}"
    else:
        title = "Payment Report for All Clusters"
    
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add period
    period = f"{context['month_name']} {context['year']}"
    elements.append(Paragraph(f"Period: {period}", subtitle_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add owner info if available
    if context['owner_info']:
        owner = context['owner_info']
        elements.append(Paragraph("Cluster Owner Information", subtitle_style))
        elements.append(Paragraph(f"Name: {owner['username']}", normal_style))
        elements.append(Paragraph(f"Email: {owner['email']}", normal_style))
        
        if 'bank_details' in owner:
            elements.append(Spacer(1, 0.1*inch))
            elements.append(Paragraph("Bank Details", subtitle_style))
            bank = owner['bank_details']
            elements.append(Paragraph(f"Bank: {bank['bank_name']}", normal_style))
            elements.append(Paragraph(f"Account: {bank['account_number']}", normal_style))
            elements.append(Paragraph(f"IFSC: {bank['ifsc_code']}", normal_style))
            elements.append(Paragraph(f"Branch: {bank['branch_name']}", normal_style))
        
        elements.append(Spacer(1, 0.25*inch))
    
    # Add summary
    elements.append(Paragraph("Summary", subtitle_style))
    elements.append(Paragraph(f"Total Revenue: ₹{context['total_amount']:.2f}", normal_style))
    elements.append(Paragraph(f"Total Payments: {len(context['payments'])}", normal_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add payments table
    elements.append(Paragraph("Payment Details", subtitle_style))
    
    # Define table data
    if context['cluster_name']:
        # If specific cluster, don't include cluster name column
        data = [['Payment ID', 'Match ID', 'Amount (₹)', 'Date', 'User Email']]
        for payment in context['payments']:
            data.append([
                payment['id'],
                payment['match_id'],
                f"₹{payment['amount']:.2f}",
                payment['date'],
                payment['user_email']
            ])
        # Add total row
        data.append(['Total', '', f"₹{context['total_amount']:.2f}", '', ''])
    else:
        # If all clusters, include cluster name column
        data = [['Payment ID', 'Match ID', 'Cluster', 'Amount (₹)', 'Date', 'User Email']]
        for payment in context['payments']:
            data.append([
                payment['id'],
                payment['match_id'],
                payment['cluster_name'],
                f"₹{payment['amount']:.2f}",
                payment['date'],
                payment['user_email']
            ])
        # Add total row
        data.append(['Total', '', '', f"₹{context['total_amount']:.2f}", '', ''])
    
    # Create table
    table = Table(data)
    
    # Add style to table
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.beige),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (3, 1), (3, -1), 'RIGHT'),  # Align amount column to right
    ])
    table.setStyle(style)
    
    # Add table to elements
    elements.append(table)
    
    # Add footer with date
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create the HTTP response with PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f"payment_report_{context['month_name']}_{context['year']}"
    if context['cluster_name']:
        filename += f"_{context['cluster_name'].replace(' ', '_')}"
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    
    # Write the PDF to the response
    response.write(pdf)
    return response

@login_required
def generate_report_pdf(request):
    """Generate a PDF for the custom report"""
    # Get report parameters
    report_type = request.GET.get('report_type', 'summary')
    date_range = request.GET.get('date_range', 'last30days')
    
    # Create a file-like buffer to receive PDF data
    buffer = io.BytesIO()
    
    # Create the PDF object, using the buffer as its "file"
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    subtitle_style = styles['Heading2']
    normal_style = styles['Normal']
    
    # Add title
    title = f"SolSub Admin {report_type.capitalize()} Report"
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add date range
    date_range_text = "Last 30 Days"
    if date_range == 'last90days':
        date_range_text = "Last 90 Days"
    elif date_range == 'lastYear':
        date_range_text = "Last Year"
    elif date_range == 'custom':
        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')
        if start_date and end_date:
            date_range_text = f"From {start_date} to {end_date}"
    
    elements.append(Paragraph(f"Period: {date_range_text}", subtitle_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add summary statistics
    now = datetime.now()
    
    # Calculate total revenue
    total_revenue = 0
    for payment in Payment.objects(status='Completed'):
        total_revenue += float(payment.amount)
    
    # Count active match IDs
    active_match_ids = 0
    for match_id in MatchId.objects:
        is_active = match_id.valid_till and now <= match_id.valid_till
        if is_active:
            active_match_ids += 1
    
    # Calculate trial conversion rate
    trial_match_ids = MatchId.objects(is_trial=True).count()
    converted_trials = 0
    for match_id in MatchId.objects(is_trial=True):
        if match_id.last_paid_on and match_id.last_paid_on > match_id.created_on:
            converted_trials += 1
    
    trial_conversion_rate = 0
    if trial_match_ids > 0:
        trial_conversion_rate = (converted_trials / trial_match_ids) * 100
    
    elements.append(Paragraph("Summary", subtitle_style))
    elements.append(Paragraph(f"Total Revenue: ₹{total_revenue:.2f}", normal_style))
    elements.append(Paragraph(f"Active Subscriptions: {active_match_ids}", normal_style))
    elements.append(Paragraph(f"Trial Conversion Rate: {trial_conversion_rate:.1f}%", normal_style))
    elements.append(Spacer(1, 0.25*inch))
    
    # Add monthly revenue breakdown
    elements.append(Paragraph("Monthly Revenue Breakdown", subtitle_style))
    
    # Get monthly revenue data
    monthly_revenue = {}
    for payment in Payment.objects(status='Completed'):
        if payment.payment_date:
            month_year = payment.payment_date.strftime('%Y-%m')
            if month_year not in monthly_revenue:
                monthly_revenue[month_year] = 0
            monthly_revenue[month_year] += float(payment.amount)
    
    # Create table data
    data = [['Month', 'Revenue (₹)']]
    for month, revenue in monthly_revenue.items():
        # Format month as "Month Year"
        month_date = datetime.strptime(month, '%Y-%m')
        formatted_month = month_date.strftime('%B %Y')
        data.append([formatted_month, f"₹{revenue:.2f}"])
    
    # Create table
    if len(data) > 1:  # Only create table if there's data
        table = Table(data)
        
        # Add style to table
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),  # Align amount column to right
        ])
        table.setStyle(style)
        
        # Add table to elements
        elements.append(table)
    else:
        elements.append(Paragraph("No revenue data available", normal_style))
    
    # Add cluster performance if detailed report
    if report_type in ['detailed', 'financial']:
        elements.append(Spacer(1, 0.25*inch))
        elements.append(Paragraph("Cluster Performance", subtitle_style))
        
        # Get cluster performance data
        cluster_performance = {}
        for payment in Payment.objects(status='Completed'):
            cluster_name = payment.cluster_name
            if cluster_name:
                if cluster_name not in cluster_performance:
                    cluster_performance[cluster_name] = {
                        'revenue': 0,
                        'count': 0
                    }
                cluster_performance[cluster_name]['revenue'] += float(payment.amount)
                cluster_performance[cluster_name]['count'] += 1
        
        # Create table data
        data = [['Cluster', 'Revenue (₹)', 'Number of Payments']]
        for cluster, stats in cluster_performance.items():
            data.append([cluster, f"₹{stats['revenue']:.2f}", stats['count']])
        
        # Create table
        if len(data) > 1:  # Only create table if there's data
            table = Table(data)
            
            # Add style to table
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),  # Align amount column to right
            ])
            table.setStyle(style)
            
            # Add table to elements
            elements.append(table)
        else:
            elements.append(Paragraph("No cluster performance data available", normal_style))
    
    # Add footer with date
    elements.append(Spacer(1, 0.5*inch))
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create the HTTP response with PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f"solsub_report_{report_type}_{datetime.now().strftime('%Y%m%d')}"
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    
    # Write the PDF to the response
    response.write(pdf)
    return response

# API endpoints for dashboard data
def analytics_data(request):
    # Get monthly payment data for the chart
    now = datetime.now()
    start_date = now - timedelta(days=180)  # Last 6 months
    
    # Initialize monthly data
    monthly_data = {}
    for i in range(6):
        month_date = now - timedelta(days=30 * i)
        month_name = month_date.strftime('%b')
        monthly_data[month_name] = {
            'revenue': 0,
            'payments': 0,
            'subscriptions': 0,
            'clusters': {}
        }
    
    # Populate with payment data
    for payment in Payment.objects(payment_date__gte=start_date, status='Completed'):
        month_name = payment.payment_date.strftime('%b')
        if month_name in monthly_data:
            monthly_data[month_name]['revenue'] += float(payment.amount)
            monthly_data[month_name]['payments'] += 1
            
            # Get cluster_name from api_key
            cluster_name = payment.cluster_name
            if cluster_name:
                # Track by cluster
                if cluster_name not in monthly_data[month_name]['clusters']:
                    monthly_data[month_name]['clusters'][cluster_name] = 0
                monthly_data[month_name]['clusters'][cluster_name] += float(payment.amount)
    
    # Count active subscriptions by month
    for match_id in MatchId.objects:
        if match_id.valid_till:
            month_name = match_id.valid_till.strftime('%b')
            if month_name in monthly_data:
                monthly_data[month_name]['subscriptions'] += 1
    
    # Format for chart
    chart_data = []
    for month, data in monthly_data.items():
        chart_item = {
            'month': month,
            'revenue': data['revenue'],
            'payments': data['payments'],
            'subscriptions': data['subscriptions']
        }
        # Add cluster data
        for cluster_name, amount in data['clusters'].items():
            chart_item[cluster_name] = amount
        
        chart_data.append(chart_item)
    
    # Sort by month chronologically
    month_order = {month: i for i, month in enumerate(calendar.month_abbr[1:])}
    chart_data.sort(key=lambda x: month_order[x['month']])
    
    return JsonResponse({'data': chart_data})

def cluster_data(request):
    # Similar to the clusters view but returns JSON
    all_clusters = []
    for user in UserProfile.objects:
        for cluster in user.clusters:
            active_count = MatchId.objects(
                cluster_name=cluster.cluster_name,
                valid_till__gt=datetime.now()
            ).count()
            
            all_clusters.append({
                'name': cluster.cluster_name,
                'price': float(cluster.cluster_price),
                'timeline_days': cluster.timeline_days,
                'trial_period': cluster.trial_period,
                'match_id_type': cluster.match_id_type,
                'active_subscriptions': active_count,
                'api_key': cluster.api_key,
            })
    
    # Remove duplicates
    unique_clusters = []
    cluster_names = set()
    for cluster in all_clusters:
        if cluster['name'] not in cluster_names:
            cluster_names.add(cluster['name'])
            unique_clusters.append(cluster)
    
    return JsonResponse({'clusters': unique_clusters})

def user_detail(request, user_id):
    # Get detailed information for a specific user
    user = UserProfile.objects(user_id=user_id).first()
    
    if not user:
        return JsonResponse({'success': False, 'error': 'User not found'})
    
    # Format user data
    user_data = {
        'id': user.user_id,
        'username': user.username,
        'email': user.email,
        'created_at': user.created_at.strftime('%Y-%m-%d'),
        'clusters': [],
    }
    
    # Add bank details if available
    if user.bank_details:
        user_data['bank_details'] = {
            'bank_name': user.bank_details.bank_name,
            'account_number': user.bank_details.account_number,
            'ifsc_code': user.bank_details.ifsc_code,
            'branch_name': user.bank_details.branch_name,
        }
    
    # Add clusters
    for cluster in user.clusters:
        user_data['clusters'].append({
            'cluster_name': cluster.cluster_name,
            'cluster_price': float(cluster.cluster_price),
            'timeline_days': cluster.timeline_days,
            'trial_period': cluster.trial_period,
            'match_id_type': cluster.match_id_type,
            'api_key': cluster.api_key,
        })
    
    return JsonResponse({'success': True, 'user': user_data})
