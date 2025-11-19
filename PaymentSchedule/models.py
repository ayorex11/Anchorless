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