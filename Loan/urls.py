from django.urls import path
from . import views


urlpatterns = [
    path('list_loan/', views.list_loans, name='list_loans'),
    path('create/', views.create_loan, name='create_loan'),
    path('get_loan/<uuid:loan_id>/', views.get_loan, name='get_loan'),
    path('update/<uuid:loan_id>/', views.update_loan, name='update_loan'),
    path('delete/<uuid:loan_id>/', views.delete_loan, name='delete_loan'),
]