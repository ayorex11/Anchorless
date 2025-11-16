from django.db import models
import uuid
from Account.models import CustomUser
from DebtPlan.models import DebtPlan
class Loan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='loans')
    debt_plan = models.ForeignKey(DebtPlan, on_delete=models.CASCADE, related_name='loans', null=True, blank=True)
    
    name = models.CharField(max_length=255)  # e.g., "Chase Credit Card", "Car Loan"
    principal_balance = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)  # Annual percentage
    minimum_payment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    due_date = models.IntegerField(choices=[(i, f'Day {i}') for i in range(1, 29)], default=1) 
    remaining_balance = models.DecimalField(max_digits=10, decimal_places=2)
    manually_set_minimum_payment = models.BooleanField(default=False)
    
    # Plan-specific ordering
    payoff_order = models.IntegerField(null=True, blank=True)  # Order in which this loan will be paid off
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['payoff_order']
    
    def __str__(self):
        return f"{self.name} - ${self.principal_balance}"