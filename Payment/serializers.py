from rest_framework import serializers
from .models import Payment
from Loan.models import Loan
from DebtPlan.models import DebtPlan


class PaymentSerializer(serializers.ModelSerializer):
    loan_name = serializers.CharField(source='loan.name', read_only=True)
    debt_name = serializers.CharField(source='debt_plan.name', read_only=True)  
    user = serializers.SerializerMethodField()
    principal_paid = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True
    )
    interest_paid = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True
    )
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', 
        read_only=True
    )
    month_number = serializers.IntegerField(
        required=True,
        min_value=1,
        write_only=False,
        help_text="Month number in the debt plan this payment is for (optional)"
    )
    
    class Meta:
        model = Payment
        fields = [
            'id', 'loan', 'loan_name', 'debt_plan', 'debt_name', 'amount', 
            'payment_date', 'payment_method', 'payment_method_display',
            'is_extra_payment', 'is_below_minimum',
            'month_number', 'notes', 'confirmation_number',
            'principal_paid', 'interest_paid',
            'user', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'is_extra_payment', 'is_below_minimum', 
            'created_at', 'updated_at'
        ]
    
    def get_user(self, obj):
        return obj.user.email if obj.user else None
    
    def validate_loan(self, value):
        """Ensure user can only add payments to their own loans"""
        request = self.context.get('request')
        if request and value.user != request.user:
            raise serializers.ValidationError(
                "Cannot add payment to another user's loan"
            )
        return value
    
    def validate_debt_plan(self, value):
        """Ensure user can only add payments to their own debt plans"""
        request = self.context.get('request')
        if request and value.user != request.user:
            raise serializers.ValidationError(
                "Cannot add payment to another user's debt plan"
            )
        return value
    
    def validate_payment_method(self, value):
        """Validate payment method is valid"""
        valid_methods = [choice[0] for choice in Payment.PAYMENT_METHOD_CHOICES]
        if value not in valid_methods:
            raise serializers.ValidationError(
                f"Invalid payment method. Choose from: {', '.join(valid_methods)}"
            )
        return value
    
    def validate(self, attrs):
        """Cross-field validation"""
        loan = attrs.get('loan')
        debt_plan = attrs.get('debt_plan')
        
        # Ensure loan belongs to debt plan
        if loan and debt_plan:
            if loan.debt_plan_id != debt_plan.id:
                raise serializers.ValidationError({
                    'loan': 'This loan does not belong to the specified debt plan'
                })
        
        return attrs
    
    def validate_month_number(self, value):
        """Validate month number is positive"""
        if value and value < 1:
            raise serializers.ValidationError("Month number must be a positive integer")
        request = self.context.get('request')
        debt_plan_id = self.initial_data.get('debt_plan')
        if debt_plan_id and request:
            from PaymentSchedule.models import PaymentSchedule
            from DebtPlan.models import DebtPlan

            try:
                plan = DebtPlan.objects.get(id=debt_plan_id, user=request.user)
                if not PaymentSchedule.objects.filter(
                    debt_plan= plan,
                    month_number = value
                ).exists():
                    raise serializers.ValidationError(
                        f"Month {value } does not exist in payment schedule"
                    )
            except DebtPlan.DoesNotExist:
                pass 
        return value
    
class PaymentFilterSerializer(serializers.Serializer):
    """Serializer for filtering payments in list view"""
    loan = serializers.UUIDField(
        required=False,
        help_text="Filter by loan UUID"
    )
    debt_plan = serializers.UUIDField(
        required=False,
        help_text="Filter by debt plan UUID"
    )
    payment_method = serializers.ChoiceField(
        choices=Payment.PAYMENT_METHOD_CHOICES,
        required=False,
        help_text="Filter by payment method"
    )
    start_date = serializers.DateField(
        required=False,
        help_text="Filter payments from this date (YYYY-MM-DD)"
    )
    end_date = serializers.DateField(
        required=False,
        help_text="Filter payments until this date (YYYY-MM-DD)"
    )


class PaymentSummaryFilterSerializer(serializers.Serializer):
    """Serializer for filtering payment summary"""
    debt_plan = serializers.UUIDField(
        required=False,
        help_text="Filter summary by debt plan UUID"
    )