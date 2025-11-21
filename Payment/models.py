from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid

from Account.models import CustomUser
from Loan.models import Loan
from DebtPlan.models import DebtPlan
from PaymentSchedule.models import PaymentSchedule


class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('check', 'Check'),
        ('cash', 'Cash'),
        ('auto_pay', 'Automatic Payment'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Foreign Keys
    loan = models.ForeignKey(
        Loan, 
        on_delete=models.CASCADE, 
        related_name='payments'
    )
    debt_plan = models.ForeignKey(
        DebtPlan, 
        on_delete=models.CASCADE, 
        related_name='payments'
    )

    payment_schedule = models.ForeignKey(
        PaymentSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actual_payments',
        help_text="The scheduled month this payment fulfills"
    )
    
    # Payment Details
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_date = models.DateField()
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='bank_transfer'
    )
    
    # Payment Classification
    is_extra_payment = models.BooleanField(default=False)  # Payment beyond scheduled
    is_below_minimum = models.BooleanField(default=False)  # Payment below minimum required
    
    # Tracking & Context
    month_number = models.IntegerField(null=True, blank=True)  # Which month of the plan
    notes = models.TextField(blank=True, default='')
    confirmation_number = models.CharField(max_length=100, blank=True, default='')  # Bank confirmation/reference
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['loan', 'payment_date']),
            models.Index(fields=['debt_plan', 'payment_date']),
            models.Index(fields=['payment_schedule']),
            models.Index(fields=['payment_method']),
            models.Index(fields=['-payment_date']),
        ]
    
    def __str__(self):
        return f"${self.amount} to {self.loan.name} on {self.payment_date}"
    
    def clean(self):
        """Validate payment data"""
        errors = {}
        
        # Validate amount
        if self.amount <= 0:
            errors['amount'] = "Payment amount must be positive"
        
        # Validate payment date isn't too far in future (allow up to 7 days)
        max_future_date = timezone.now().date() + timezone.timedelta(days=7)
        if self.payment_date > max_future_date:
            errors['payment_date'] = "Payment date cannot be more than 7 days in the future"
        
        # Validate payment date isn't before loan creation
        if self.loan_id and hasattr(self.loan, 'created_at'):
            if self.payment_date < self.loan.created_at.date():
                errors['payment_date'] = "Payment date cannot be before loan was created"
        
        # Validate loan belongs to debt plan
        if self.loan_id and self.debt_plan_id:
            if self.loan.debt_plan_id != self.debt_plan_id:
                errors['loan'] = "Loan does not belong to the specified debt plan"
        
        # Validate both flags aren't true simultaneously
        if self.is_extra_payment and self.is_below_minimum:
            errors['is_extra_payment'] = "Payment cannot be both extra and below minimum"
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save to run validation"""
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def user(self):
        """Helper property to get user from loan"""
        return self.loan.user if self.loan else None
    
    @property
    def principal_paid(self):
        """Calculate how much of this payment went to principal"""
        if not self.loan:
            return Decimal('0')
        
        monthly_interest_rate = (self.loan.interest_rate / Decimal('100')) / Decimal('12')
        interest = (self.loan.remaining_balance * monthly_interest_rate).quantize(Decimal('0.01'))
        return max(self.amount - interest, Decimal('0'))
    
    @property
    def interest_paid(self):
        """Calculate how much of this payment went to interest"""
        return self.amount - self.principal_paid
    
    def get_payment_method_display_name(self):
        """Get human-readable payment method name"""
        return dict(self.PAYMENT_METHOD_CHOICES).get(self.payment_method, self.payment_method)