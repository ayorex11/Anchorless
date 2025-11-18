from django.contrib import admin
from .models import Payment
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'loan', 'debt_plan', 'amount', 'payment_date', 'is_extra_payment', 'created_at')
    list_filter = ('is_extra_payment', 'payment_date', 'created_at')
    search_fields = ('user__username', 'loan__name', 'debt_plan__name')
    ordering = ('-created_at',)