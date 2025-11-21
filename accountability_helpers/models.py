from django.db import models
from django.core.validators import FileExtensionValidator
import uuid
from Account.models import CustomUser
from DebtPlan.models import DebtPlan


class PaymentPlanPDF(models.Model):
    """Generated PDF payment plan for a debt plan"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    debt_plan = models.OneToOneField(
        DebtPlan, 
        on_delete=models.CASCADE, 
        related_name='payment_plan_pdf'
    )
    user = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='payment_plan_pdfs'
    )
    pdf_file = models.FileField(
        upload_to='payment_plans/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        blank=True,
        null=True
    )
    generated_at = models.DateTimeField(auto_now=True)
    file_size = models.IntegerField(default=0, help_text="File size in bytes")
    
    class Meta:
        verbose_name = "Payment Plan PDF"
        verbose_name_plural = "Payment Plan PDFs"
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"PDF for {self.debt_plan.name} - {self.user.email}"
    
    def delete_file(self):
        """Delete the physical PDF file"""
        if self.pdf_file:
            try:
                self.pdf_file.delete(save=False)
            except Exception:
                pass


class LetterToSelf(models.Model):
    """Motivational letter to be sent when debt is paid off"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='letters_to_self'
    )
    debt_plan = models.OneToOneField(
        DebtPlan,
        on_delete=models.CASCADE,
        related_name='completion_letter',
        help_text="The debt plan this letter is for"
    )
    subject = models.CharField(max_length=250)
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    is_sent = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Letter to Self"
        verbose_name_plural = "Letters to Self"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.subject}"