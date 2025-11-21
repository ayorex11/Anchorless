from django.db import models
import uuid
from DebtPlan.models import DebtPlan
from Loan.models import Loan
from decimal import Decimal
from django.core.validators import MinValueValidator


class PaymentSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    debt_plan = models.ForeignKey(DebtPlan, on_delete=models.CASCADE, related_name='payment_schedules')
    month_number = models.IntegerField(validators=[MinValueValidator(1)])
    
    focus_loan = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True, related_name='focused_schedules')
    
    total_payment = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    total_interest = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    total_principal = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['month_number']
        unique_together = ['debt_plan', 'month_number']
        indexes = [
            models.Index(fields=['debt_plan', 'month_number']),
        ]
    
    def __str__(self):
        return f"Month {self.month_number}: ${self.total_payment}"
    
    # Calculated properties based on actual Payment records
    @property
    def has_payments(self):
        """Check if any payments have been made for this schedule"""
        return self.actual_payments.exists()
    
    @property
    def total_paid(self):
        """Total amount paid for this schedule"""
        from django.db.models import Sum
        result = self.actual_payments.aggregate(total=Sum('amount'))['total']
        return result if result is not None else Decimal('0.00')
    
    @property
    def is_fully_paid(self):
        """Check if total payment meets or exceeds scheduled amount"""
        return self.total_paid >= self.total_payment
    
    @property
    def payment_deficit(self):
        """How much short of scheduled payment"""
        return max(self.total_payment - self.total_paid, Decimal('0.00'))
    
    @property
    def payment_surplus(self):
        """How much over scheduled payment (if any)"""
        return max(self.total_paid - self.total_payment, Decimal('0.00'))
    
    @property
    def completion_percentage(self):
        """Percentage of scheduled payment that's been paid"""
        if self.total_payment == 0:
            return Decimal('100.00')
        return min((self.total_paid / self.total_payment * 100).quantize(Decimal('0.01')), Decimal('100.00'))
    
    @property
    def latest_payment_date(self):
        """Date of the most recent payment for this schedule"""
        payment = self.actual_payments.order_by('-payment_date').first()
        return payment.payment_date if payment else None


class LoanPaymentSchedule(models.Model):
    """Detailed breakdown per loan per month"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_schedule = models.ForeignKey(
        PaymentSchedule, 
        on_delete=models.CASCADE, 
        related_name='loan_breakdowns'
    )
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payment_breakdowns')
    
    payment_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    interest_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    principal_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    remaining_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    is_focus_loan = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['loan__payoff_order']
        indexes = [
            models.Index(fields=['payment_schedule', 'loan']),
        ]
    
    def __str__(self):
        return f"{self.loan.name}: ${self.payment_amount}"
    
    @property
    def has_payment(self):
        """Check if this specific loan has a payment for this month"""
        return self.payment_schedule.actual_payments.filter(loan=self.loan).exists()
    
    @property
    def actual_payment_amount(self):
        """Get the actual amount paid for this loan in this schedule"""
        from django.db.models import Sum
        result = self.payment_schedule.actual_payments.filter(
            loan=self.loan
        ).aggregate(total=Sum('amount'))['total']
        return result if result is not None else Decimal('0.00')