# solsub_admin/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .mongo_models import UserProfile, MatchId, Payment, ClusterDetails
from .models import Cluster
from datetime import datetime, timedelta
import json
import calendar
import logging

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    # Get counts for dashboard stats
    user_count = UserProfile.objects.count()
    
    # Count active match IDs
    now = datetime.now()
    active_match_ids = MatchId.objects(valid_till__gt=now).count()
    
    # Get total clusters
    clusters = set()
    for user in UserProfile.objects:
        for cluster in user.clusters:
            clusters.add(cluster.cluster_name)
    
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
        'cluster_count': len(clusters),
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
        all_payments.append({
            'id': payment.payment_id,
            'match_id': payment.match_id,
            'cluster_name': payment.cluster_name,
            'amount': float(payment.amount),
            'status': payment.status,
            'date': payment.payment_date.strftime('%Y-%m-%d'),
            'user_email': payment.user_email,
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
        if payment.cluster_name not in cluster_performance:
            cluster_performance[payment.cluster_name] = {
                'revenue': 0,
                'count': 0
            }
        cluster_performance[payment.cluster_name]['revenue'] += float(payment.amount)
        cluster_performance[payment.cluster_name]['count'] += 1
    
    # User growth data (safe, since created_at is required)
    user_growth = {}
    for user in UserProfile.objects:
        if user.created_at:  # Check if created_at is not None
            month_year = user.created_at.strftime('%Y-%m')
            if month_year not in user_growth:
                user_growth[month_year] = 0
            user_growth[month_year] += 1
    
    context = {
        'monthly_revenue': monthly_revenue,
        'cluster_performance': cluster_performance,
        'user_growth': user_growth,
    }
    
    return render(request, 'dashboard/reports.html', context)

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
            
            # Track by cluster
            if payment.cluster_name not in monthly_data[month_name]['clusters']:
                monthly_data[month_name]['clusters'][payment.cluster_name] = 0
            monthly_data[month_name]['clusters'][payment.cluster_name] += float(payment.amount)
    
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