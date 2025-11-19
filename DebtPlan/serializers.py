from rest_framework import serializers
from .models import DebtPlan

class DebtPlanSerializer(serializers.ModelSerializer):
    monthly_payment_budget = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        min_value=0.01
    )

    def validate_monthly_payment_budget(self, value):
        if value <= 0:
            raise serializers.ValidationError("Monthly payment budget must be positive")
        return value

    class Meta:
        model = DebtPlan
        fields = '__all__'
        read_only_fields = ['id', 'user', 'projected_payoff_date', 'total_interest_saved', 'created_at', 'is_active']


class UpdateDebtPlanSerializer(serializers.ModelSerializer):

    class Meta:
        model = DebtPlan
        fields = ['name', 'monthly_payment_budget']