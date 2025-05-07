from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('users/', views.users, name='users'),
    path('payments/', views.payments, name='payments'),
    path('match-ids/', views.match_ids, name='match_ids'),
    path('clusters/', views.clusters, name='clusters'),
    path('reports/', views.reports, name='reports'),
    path('reports/cluster-owner-payment/', views.cluster_owner_payment_report, name='cluster_owner_payment_report'),
    path('reports/generate-pdf/', views.generate_report_pdf, name='generate_report_pdf'),
    path('api/analytics/', views.analytics_data, name='analytics_data'),
    path('api/clusters/', views.cluster_data, name='cluster_data'),
    path('api/users/<str:user_id>/', views.user_detail, name='user_detail'),
]
