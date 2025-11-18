from django.db import models
import uuid
from DebtPlan.models import DebtPlan
from Loan.models import Loan

class PaymentSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    debt_plan = models.ForeignKey(DebtPlan, on_delete=models.CASCADE, related_name='payment_schedule')
    month_number = models.IntegerField()  # Month 1, 2, 3, etc.
    
    focus_loan = models.ForeignKey(Loan, on_delete=models.CASCADE, null=True, blank=True)
    
    # Total payment for this month across all loans
    total_payment = models.DecimalField(max_digits=10, decimal_places=2)
    total_interest = models.DecimalField(max_digits=10, decimal_places=2)
    total_principal = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        ordering = ['month_number']
        unique_together = ['debt_plan', 'month_number']
    
    def __str__(self):
        return f"Month {self.month_number}: {self.total_payment}"

class LoanPaymentSchedule(models.Model):
    """Detailed breakdown per loan per month"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_schedule = models.ForeignKey(PaymentSchedule, on_delete=models.CASCADE, related_name='loan_breakdowns')
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_amount = models.DecimalField(max_digits=10, decimal_places=2)
    principal_amount = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_balance = models.DecimalField(max_digits=10, decimal_places=2)
    is_focus_loan = models.BooleanField(default=False)  # Is this the loan getting extra payments?
    
    class Meta:
        ordering = ['loan__payoff_order']
    
    def __str__(self):
        return f"{self.loan.name}: ${self.payment_amount}"