from django.contrib import admin
from .models import PaymentSchedule, LoanPaymentSchedule

@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'total_payment', 'total_interest', 'total_principal', 'created_at')
    search_fields = ('id', 'debt_plan__user__email')
    ordering = ('-created_at',)

admin.site.register(LoanPaymentSchedule)
