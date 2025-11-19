from rest_framework import serializers
from .models import Loan
from DebtPlan.models import DebtPlan


class LoanSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    debt_plan = serializers.PrimaryKeyRelatedField(
        queryset=DebtPlan.objects.all(),
        required=True
    )
    
    class Meta:
        model = Loan
        fields = [
            'id', 'user', 'debt_plan', 'name', 'principal_balance', 
            'interest_rate', 'minimum_payment', 'due_date', 
            'remaining_balance', 'manually_set_minimum_payment', 
            'payoff_order', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'remaining_balance', 'payoff_order', 
            'created_at', 'updated_at'
        ]
    
    def validate_debt_plan(self, value):
        """Ensure user can only add loans to their own debt plans"""
        request = self.context.get('request')
        if request and value.user != request.user:
            raise serializers.ValidationError(
                "Cannot add loan to another user's debt plan"
            )
        return value
    
    def validate_principal_balance(self, value):
        """Validate principal balance is positive"""
        if value <= 0:
            raise serializers.ValidationError(
                "Principal balance must be positive"
            )
        return value
    
    def validate_interest_rate(self, value):
        """Validate interest rate is non-negative"""
        if value < 0:
            raise serializers.ValidationError(
                "Interest rate cannot be negative"
            )
        if value > 100:
            raise serializers.ValidationError(
                "Interest rate cannot exceed 100%"
            )
        return value
    
    def validate_minimum_payment(self, value):
        """Validate minimum payment if provided"""
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "Minimum payment must be positive"
            )
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        manually_set = attrs.get('manually_set_minimum_payment', False)
        minimum_payment = attrs.get('minimum_payment')
        
        if manually_set and (minimum_payment is None or minimum_payment <= 0):
            raise serializers.ValidationError({
                'minimum_payment': 'Minimum payment is required and must be positive when manually_set_minimum_payment is True'
            })
        
        return attrs


class LoanUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating loan details"""
    
    class Meta:
        model = Loan
        fields = [
            'name', 'minimum_payment', 'due_date', 
            'manually_set_minimum_payment'
        ]
    
    def validate_minimum_payment(self, value):
        """Validate minimum payment if provided"""
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "Minimum payment must be positive"
            )
        return value
    
    def validate(self, attrs):
        """Cross-field validation for updates"""
        instance = self.instance
        manually_set = attrs.get('manually_set_minimum_payment', instance.manually_set_minimum_payment)
        minimum_payment = attrs.get('minimum_payment', instance.minimum_payment)
        
        if manually_set and (minimum_payment is None or minimum_payment <= 0):
            raise serializers.ValidationError({
                'minimum_payment': 'Minimum payment is required and must be positive when manually_set_minimum_payment is True'
            })
        
        return attrs