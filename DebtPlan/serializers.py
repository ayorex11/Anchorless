from rest_framework import serializers
from .models import DebtPlan


class DebtPlanSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    monthly_payment_budget = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        min_value=0.01
    )
    
    class Meta:
        model = DebtPlan
        fields = [
            'id', 'user', 'name', 'strategy', 'monthly_payment_budget',
            'projected_payoff_date', 'total_interest_saved', 
            'created_at', 'updated_at', 'is_active'
        ]
        read_only_fields = [
            'id', 'user', 'projected_payoff_date', 'total_interest_saved', 
            'created_at', 'updated_at', 'is_active'
        ]
    
    def validate_monthly_payment_budget(self, value):
        """Validate monthly payment budget is positive"""
        if value <= 0:
            raise serializers.ValidationError(
                "Monthly payment budget must be positive"
            )
        return value
    
    def validate_strategy(self, value):
        """Validate strategy is valid"""
        valid_strategies = ['snowball', 'avalanche']
        if value not in valid_strategies:
            raise serializers.ValidationError(
                f"Strategy must be one of: {', '.join(valid_strategies)}"
            )
        return value


class UpdateDebtPlanSerializer(serializers.ModelSerializer):
    """Serializer for updating debt plan - allows only specific fields"""
    
    monthly_payment_budget = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        min_value=0.01,
        required=False
    )
    
    class Meta:
        model = DebtPlan
        fields = ['name', 'monthly_payment_budget']
    
    def validate_monthly_payment_budget(self, value):
        """Validate monthly payment budget is positive"""
        if value <= 0:
            raise serializers.ValidationError(
                "Monthly payment budget must be positive"
            )
        return value
    
    def validate(self, attrs):
        """Additional validation when updating"""
        instance = self.instance
        
        # If changing budget, validate against existing loans
        if 'monthly_payment_budget' in attrs:
            from Loan.models import Loan
            loans = Loan.objects.filter(debt_plan=instance, remaining_balance__gt=0)
            
            if loans.exists():
                total_minimum = sum(loan.minimum_payment or 0 for loan in loans)
                if attrs['monthly_payment_budget'] < total_minimum:
                    raise serializers.ValidationError({
                        'monthly_payment_budget': f'Monthly budget must be at least ${total_minimum} to cover minimum payments'
                    })
        
        return attrs