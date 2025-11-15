from django.contrib import admin
from .models import DebtPlan
@admin.register(DebtPlan)
class DebtPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'strategy', 'monthly_payment_budget', 'projected_payoff_date', 'total_interest_saved', 'created_at', 'is_active')
    list_filter = ('strategy', 'is_active', 'created_at')
    search_fields = ('user__email', 'name')
    ordering = ('-created_at',)