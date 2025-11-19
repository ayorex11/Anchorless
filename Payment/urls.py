from django.urls import path
from . import views

urlpatterns = [
    path('create_payment/', views.create_payment),
    path('list_payments/', views.list_payments),
    path('payment_summary_by_method/', views.payment_summary_by_method),
]