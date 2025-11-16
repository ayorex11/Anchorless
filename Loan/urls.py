from django.urls import path
from . import views
urlpatterns = [
    path('create_loan/', views.create_loan, name='debt_plan_create'),  
]