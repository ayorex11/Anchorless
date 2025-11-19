from rest_framework import serializers
from .models import Payment

class PaymentSerializer(serializers.ModelSerializer):
    loan_name = serializers.CharField(source='loan.name', read_only=True)
    debt_plan_name = serializers.CharField(source='debt_plan.name', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'loan', 'loan_name', 'debt_plan', 'debt_plan_name',
            'amount', 'payment_date', 'is_extra_payment', 'is_below_minimum',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'is_extra_payment', 'is_below_minimum']

