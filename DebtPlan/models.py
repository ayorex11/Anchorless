from django.db import models
import uuid
from Account.models import CustomUser
class DebtPlan(models.Model):
    STRATEGY_CHOICES = [
        ('snowball', 'Snowball Method'),
        ('avalanche', 'Avalanche Method'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='debt_plans')
    name = models.CharField(max_length=255, default="My Debt Freedom Plan")
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
    monthly_payment_budget = models.DecimalField(max_digits=10, decimal_places=2)  # Total user can pay monthly
    projected_payoff_date = models.DateField(null=True, blank=True)
    total_interest_saved = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.email}'s {self.strategy} Plan"