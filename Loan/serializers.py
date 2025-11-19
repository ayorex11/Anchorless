from rest_framework import serializers
from .models import Loan

class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = [
            'id', 'user', 'debt_plan', 'name', 'principal_balance',
            'interest_rate', 'minimum_payment', 'due_date',
            'remaining_balance', 'manually_set_minimum_payment',
            'payoff_order', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'payoff_order']
    
    def validate(self, data):
        # Ensure remaining_balance is set to principal if not provided
        if 'remaining_balance' not in data and 'principal_balance' in data:
            data['remaining_balance'] = data['principal_balance']
        
        return data

