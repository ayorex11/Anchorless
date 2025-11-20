from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
import uuid

from Account.models import CustomUser
from DebtPlan.models import DebtPlan


class Loan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='loans')
    debt_plan = models.ForeignKey(
        DebtPlan, 
        on_delete=models.CASCADE, 
        related_name='loans', 
        null=True, 
        blank=True
    )
    
    name = models.CharField(max_length=255)
    principal_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    interest_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))]
    )
    minimum_payment = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    due_date = models.IntegerField(
        choices=[(i, f'Day {i}') for i in range(1, 29)], 
        default=1
    )
    remaining_balance = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    manually_set_minimum_payment = models.BooleanField(default=False)
    
    # Plan-specific ordering
    payoff_order = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['payoff_order', 'created_at']
        indexes = [
            models.Index(fields=['user', 'debt_plan']),
            models.Index(fields=['payoff_order']),
        ]
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Validate loan data"""
        errors = {}
        
        if self.remaining_balance > self.principal_balance:
            errors['remaining_balance'] = "Remaining balance cannot exceed principal balance"
        
        if self.minimum_payment and self.minimum_payment <= 0:
            errors['minimum_payment'] = "Minimum payment must be positive"
        
        if self.interest_rate < 0:
            errors['interest_rate'] = "Interest rate cannot be negative"
        
        if self.remaining_balance < 0:
            errors['remaining_balance'] = "Remaining balance cannot be negative"
        
        if self.manually_set_minimum_payment and not self.minimum_payment:
            errors['minimum_payment'] = "Minimum payment required when manually_set_minimum_payment is True"
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.clean()
        super().save(*args, **kwargs)