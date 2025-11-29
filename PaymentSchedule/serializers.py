from rest_framework import serializers
from .models import PaymentSchedule, LoanPaymentSchedule


class DebtPlanQuerySerializer(serializers.Serializer):
    """Query params: just debt_plan UUID"""
    debt_plan = serializers.UUIDField(
        required=True,
        help_text="Debt plan UUID"
    )


class PaymentScheduleDetailQuerySerializer(serializers.Serializer):
    """Query params: debt_plan + month_number"""
    debt_plan = serializers.UUIDField(
        required=True,
        help_text="Debt plan UUID"
    )
    month_number = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="Month number (1, 2, 3...)"
    )


# Response serializers
class LoanPaymentScheduleSerializer(serializers.ModelSerializer):
    """Breakdown for one loan in one month"""
    loan_id = serializers.UUIDField(source='loan.id', read_only=True)
    loan_name = serializers.CharField(source='loan.name', read_only=True)
    loan_payoff_order = serializers.IntegerField(source='loan.payoff_order', read_only=True)
    has_payment = serializers.BooleanField(read_only=True)
    actual_payment_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = LoanPaymentSchedule
        fields = [
            'id',
            'loan_id',
            'loan_name',
            'loan_payoff_order',
            'payment_amount',
            'interest_amount',
            'principal_amount',
            'remaining_balance',
            'is_focus_loan',
            'has_payment',
            'actual_payment_amount'
        ]


class PaymentScheduleSummarySerializer(serializers.ModelSerializer):
    """Simple list view with payment status"""
    focus_loan_name = serializers.CharField(source='focus_loan.name', read_only=True)
    
    has_payments = serializers.BooleanField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)
    payment_deficit = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    completion_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    
    is_current_month = serializers.SerializerMethodField()
    is_past_month = serializers.SerializerMethodField()
    is_future_month = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentSchedule
        fields = [
            'id',
            'month_number',
            'focus_loan_name',
            'total_payment',
            'total_interest',
            'total_principal',
            'has_payments',
            'total_paid',
            'is_fully_paid',
            'payment_deficit',
            'completion_percentage',
            'is_current_month',
            'is_past_month',
            'is_future_month',
            'created_at'
        ]
    
    def _get_current_month_number(self, debt_plan):
        """Helper to calculate current month number (cached per request)"""
        if not hasattr(self, '_current_month_cache'):
            from datetime import datetime
            created_date = debt_plan.created_at
            current_date = datetime.now()
            self._current_month_cache = (
                (current_date.year - created_date.year) * 12 + 
                (current_date.month - created_date.month) + 1
            )
        return self._current_month_cache
    
    def get_is_current_month(self, obj):
        """Check if this is the current payment month"""
        current_month = self._get_current_month_number(obj.debt_plan)
        return obj.month_number == current_month
    
    def get_is_past_month(self, obj):
        """Check if this month has passed"""
        current_month = self._get_current_month_number(obj.debt_plan)
        return obj.month_number < current_month
    
    def get_is_future_month(self, obj):
        """Check if this month is in the future"""
        current_month = self._get_current_month_number(obj.debt_plan)
        return obj.month_number > current_month


class PaymentScheduleSerializer(serializers.ModelSerializer):
    """Detailed view with loan-by-loan breakdown"""
    loan_breakdowns = LoanPaymentScheduleSerializer(many=True, read_only=True)
    focus_loan_id = serializers.UUIDField(source='focus_loan.id', read_only=True)
    focus_loan_name = serializers.CharField(source='focus_loan.name', read_only=True)
    debt_plan_name = serializers.CharField(source='debt_plan.name', read_only=True)
    
    class Meta:
        model = PaymentSchedule
        fields = [
            'id',
            'debt_plan_name',
            'month_number',
            'focus_loan_id',
            'focus_loan_name',
            'total_payment',
            'total_interest',
            'total_principal',
            'loan_breakdowns',
            'created_at'
        ]


class PaymentScheduleWithProgressSerializer(serializers.ModelSerializer):
    """Timeline view with completion tracking"""
    focus_loan_name = serializers.CharField(source='focus_loan.name', read_only=True)
    
    # Progress properties
    has_payments = serializers.BooleanField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)
    payment_deficit = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    payment_surplus = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    completion_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    latest_payment_date = serializers.DateField(read_only=True)
    payment_count = serializers.SerializerMethodField()
    
    def get_payment_count(self, obj):
        return obj.actual_payments.count()
    
    class Meta:
        model = PaymentSchedule
        fields = [
            'id',
            'month_number',
            'focus_loan_name',
            'total_payment',
            'total_interest',
            'total_principal',
            # Progress tracking
            'has_payments',
            'total_paid',
            'is_fully_paid',
            'payment_deficit',
            'payment_surplus',
            'completion_percentage',
            'latest_payment_date',
            'payment_count',
            'created_at'
        ]


class ProgressSerializer(serializers.Serializer):
    """Master progress dashboard data"""
    # Overall metrics
    total_months = serializers.IntegerField()
    completed_months = serializers.IntegerField()
    months_remaining = serializers.IntegerField()
    current_month_number = serializers.IntegerField()
    progress_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    
    # Debt totals
    total_debt_original = serializers.CharField()  # String to avoid precision issues
    total_debt_remaining = serializers.CharField()
    total_debt_paid = serializers.CharField()
    
    # Plan details
    projected_payoff_date = serializers.DateField()
    total_interest_to_pay = serializers.CharField()
    strategy = serializers.CharField()
    monthly_payment_budget = serializers.CharField()
    
    # Per-loan breakdown (ordered by payoff_order)
    loans = serializers.ListField(child=serializers.DictField())