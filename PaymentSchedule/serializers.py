from rest_framework import serializers
from .models import PaymentSchedule, LoanPaymentSchedule

class LoanPaymentScheduleSerializer(serializers.ModelSerializer):
    loan_name = serializers.CharField(source='loan.name', read_only=True)
    loan_id = serializers.UUIDField(source='loan.id', read_only=True)
    
    class Meta:
        model = LoanPaymentSchedule
        fields = [
            'id', 'loan_id', 'loan_name', 'payment_amount',
            'interest_amount', 'principal_amount', 'remaining_balance',
            'is_focus_loan'
        ]

class PaymentScheduleSerializer(serializers.ModelSerializer):
    loan_breakdowns = LoanPaymentScheduleSerializer(many=True, read_only=True)
    focus_loan_name = serializers.CharField(
        source='focus_loan.name',
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = PaymentSchedule
        fields = [
            'id', 'debt_plan', 'month_number', 'focus_loan',
            'focus_loan_name', 'total_payment', 'total_interest',
            'total_principal', 'loan_breakdowns'
        ]