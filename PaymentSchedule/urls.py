from django.urls import path
from . import views

urlpatterns = [
    path('list/', views.list_payment_schedules, name='list'),
    path('detail/', views.get_payment_schedule_detail, name='detail'),
    path('current/', views.get_current_month_schedule, name='current'),
    path('timeline/', views.get_schedules_with_progress, name='timeline'),
    path('progress/', views.get_debt_progress, name='progress'),
]