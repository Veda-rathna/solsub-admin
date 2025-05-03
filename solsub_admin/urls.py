# solsub_admin/urls.py
from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('users/', views.users, name='users'),
    path('payments/', views.payments, name='payments'),
    path('match-ids/', views.match_ids, name='match_ids'),
    path('clusters/', views.clusters, name='clusters'),
    path('reports/', views.reports, name='reports'),
    path('api/analytics/', views.analytics_data, name='analytics_data'),
    path('api/clusters/', views.cluster_data, name='cluster_data'),
    path('api/users/<str:user_id>/', views.user_detail, name='user_detail'),
]