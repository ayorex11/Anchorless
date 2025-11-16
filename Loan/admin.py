from django.contrib import admin
from .models import Loan
@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'principal_balance', 'interest_rate', 'minimum_payment', 'due_date', 'remaining_balance', 'payoff_order', 'created_at')
    list_filter = ('user',)
    search_fields = ('name', 'user__email')
