from django.db import models
import uuid
from Account.models import CustomUser
from Loan.models import Loan
from DebtPlan.models import DebtPlan


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payments')
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payments')
    debt_plan = models.ForeignKey(DebtPlan, on_delete=models.CASCADE, related_name='payments')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    is_extra_payment = models.BooleanField(default=False)  # Payment beyond minimum
    is_below_minimum = models.BooleanField(default=False)  # Payment below minimum required
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"${self.amount} to {self.loan.name}"