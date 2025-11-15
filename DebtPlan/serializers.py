from rest_framework import serializers
from .models import DebtPlan

class DebtPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtPlan
        fields = '__all__'
        read_only_fields = ('id', 'user', 'created_at', 'projected_payoff_date', 'total_interest_saved', 'is_active', 'created_at')