from rest_framework import serializers
from .models import Loan

class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = '__all__'
        read_only_fields = ('id','user', 'created_at', 'updated_at', 'payoff_order', 'remaining_balance')

