from django.urls import path
from . import views

urlpatterns = [
    path('create_plan/', views.create_debt_plan, name='debt_plan_create'),
    path('update_plan/<uuid:plan_id>/', views.update_debt_plan, name='debt_plan_update'),
]