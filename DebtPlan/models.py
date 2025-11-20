from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
import uuid

from Account.models import CustomUser


class DebtPlan(models.Model):
    STRATEGY_CHOICES = [
        ('snowball', 'Snowball Method'),
        ('avalanche', 'Avalanche Method'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='debt_plans'
    )
    name = models.CharField(max_length=255, default="My Debt Freedom Plan")
    strategy = models.CharField(max_length=20, choices=STRATEGY_CHOICES)
    monthly_payment_budget = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    projected_payoff_date = models.DateField(null=True, blank=True)
    total_interest_saved = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Validate debt plan data"""
        errors = {}
        
        if self.monthly_payment_budget <= 0:
            errors['monthly_payment_budget'] = "Monthly payment budget must be positive"
        
        
        # Check for multiple active plans
        if self.is_active:
            existing_active = DebtPlan.objects.filter(
                user=self.user, 
                is_active=True
            ).exclude(id=self.id)
            
            if existing_active.exists():
                errors['is_active'] = "User can only have one active debt plan at a time"
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.clean()
        super().save(*args, **kwargs)