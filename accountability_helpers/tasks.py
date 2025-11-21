from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import LetterToSelf
from DebtPlan.models import DebtPlan
from Loan.models import Loan


@shared_task(bind=True, max_retries=3)
def send_completion_letter(self, letter_id):
    """
    Send letter to self when debt is paid off
    """
    try:
        letter = LetterToSelf.objects.get(id=letter_id, is_sent=False)
        
        # Send email
        send_mail(
            subject=letter.subject,
            message=letter.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[letter.user.email],
            fail_silently=False,
        )
        
        # Mark as sent
        letter.is_sent = True
        letter.sent_at = timezone.now()
        letter.save(update_fields=['is_sent', 'sent_at'])
        
        return f"Letter sent to {letter.user.email}"
        
    except LetterToSelf.DoesNotExist:
        return "Letter not found or already sent"
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_biweekly_motivation_emails():
    """
    Send motivational emails to all users with active debt plans
    Runs every 2 weeks via Celery Beat
    """
    from Loan.utils.services import calculate_progress
    
    # Get all active debt plans
    active_plans = DebtPlan.objects.filter(is_active=True).select_related('user')
    sent_count = 0
    failed_count = 0
    
    for debt_plan in active_plans:
        try:
            # Calculate progress
            progress = calculate_progress(debt_plan)
            
            # Get loan info
            loans = Loan.objects.filter(debt_plan=debt_plan).order_by('payoff_order')
            total_loans = loans.count()
            paid_off_loans = loans.filter(remaining_balance=0).count()
            
            # Determine current focus loan
            focus_loan = None
            for loan in loans:
                if loan.remaining_balance > 0:
                    focus_loan = loan
                    break
            
            # Craft personalized message
            subject = f"💪 Keep Going! You're {progress['progress_percentage']}% There!"
            
            message = f"""
Hi {debt_plan.user.first_name or debt_plan.user.email}!

This is your bi-weekly reminder that you're making amazing progress on your debt-free journey!

📊 Your Progress:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Paid Off: ${progress['total_paid']:,.2f} of ${progress['total_original']:,.2f}
📈 Progress: {progress['progress_percentage']}%
🎯 Loans Completed: {paid_off_loans} of {total_loans}
💵 Remaining Debt: ${progress['total_remaining']:,.2f}

{f"🔥 Current Focus: {focus_loan.name}" if focus_loan else "🎉 All loans paid off!"}

{f"Projected Payoff: {debt_plan.projected_payoff_date.strftime('%B %Y')}" if debt_plan.projected_payoff_date else ""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Remember:
"Every payment brings you closer to financial freedom. Stay consistent, stay focused, and remember why you started!"

{f"You've made {progress['number_of_payments']} payments so far. Each one is a victory!" if progress['number_of_payments'] > 0 else "Start making payments to see your progress!"}

Keep up the great work! 🚀

Best regards,
Anchorless.

            """
            
            # Send email
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[debt_plan.user.email],
                fail_silently=False,
            )
            
            sent_count += 1
            
        except Exception as e:
            failed_count += 1
            # Log error but continue processing other users
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send motivation email to {debt_plan.user.email}: {str(e)}")
    
    return f"Sent {sent_count} emails, {failed_count} failed"


@shared_task
def send_monthly_progress_report():
    """
    Send detailed monthly progress report to all users
    Runs monthly via Celery Beat
    """
    from Loan.utils.services import calculate_progress
    from PaymentSchedule.models import PaymentSchedule
    from Payment.models import Payment
    from datetime import date
    from dateutil.relativedelta import relativedelta
    
    # Get all active debt plans
    active_plans = DebtPlan.objects.filter(is_active=True).select_related('user')
    
    sent_count = 0
    
    for debt_plan in active_plans:
        try:
            # Calculate progress
            progress = calculate_progress(debt_plan)
            
            # Get this month's payments
            last_month = date.today() - relativedelta(months=1)
            monthly_payments = Payment.objects.filter(
                debt_plan=debt_plan,
                payment_date__year=last_month.year,
                payment_date__month=last_month.month
            )
            
            total_paid_last_month = sum(p.amount for p in monthly_payments)
            payment_count_last_month = monthly_payments.count()
            
            # Get schedule completion
            schedules = PaymentSchedule.objects.filter(
                debt_plan=debt_plan
            ).prefetch_related('actual_payments')
            
            completed_months = sum(1 for s in schedules if s.is_fully_paid)
            
            subject = f"📊 Your Monthly Debt Freedom Report - {last_month.strftime('%B %Y')}"
            
            message = f"""
Hi {debt_plan.user.first_name or debt_plan.user.email}!

Here's your monthly progress report for {last_month.strftime('%B %Y')}:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 OVERALL PROGRESS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Debt Eliminated: ${progress['total_paid']:,.2f}
Remaining Debt: ${progress['total_remaining']:,.2f}
Overall Progress: {progress['progress_percentage']}%
Loans Paid Off: {progress['loans_paid_off']} of {progress['total_loans']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 LAST MONTH'S ACTIVITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Payments Made: {payment_count_last_month}
Amount Paid: ${total_paid_last_month:,.2f}
Months Completed: {completed_months} of {schedules.count()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 WHAT'S NEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monthly Budget: ${debt_plan.monthly_payment_budget:,.2f}
Strategy: {debt_plan.get_strategy_display()}
{f"Projected Debt-Free Date: {debt_plan.projected_payoff_date.strftime('%B %d, %Y')}" if debt_plan.projected_payoff_date else ""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🌟 Keep pushing forward! Every payment is a step closer to freedom!


Best regards,
Anchorless
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[debt_plan.user.email],
                fail_silently=False,
            )
            
            sent_count += 1
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send monthly report to {debt_plan.user.email}: {str(e)}")
    
    return f"Sent {sent_count} monthly reports"


@shared_task
def send_payment_reminder():
    """
    Send payment reminders to users who haven't made a payment this month
    Runs weekly via Celery Beat
    """
    from Payment.models import Payment
    from datetime import date
    
    active_plans = DebtPlan.objects.filter(is_active=True).select_related('user')
    
    sent_count = 0
    
    for debt_plan in active_plans:
        try:
            # Check if payment made this month
            payments_this_month = Payment.objects.filter(
                debt_plan=debt_plan,
                payment_date__year=date.today().year,
                payment_date__month=date.today().month
            )
            
            # Only send reminder if no payment this month
            if not payments_this_month.exists():
                subject = "⏰ Friendly Reminder: Monthly Payment Due"
                
                message = f"""
Hi {debt_plan.user.first_name or debt_plan.user.email}!

This is a friendly reminder that we haven't recorded a payment for {date.today().strftime('%B %Y')} yet.

Your monthly budget: ${debt_plan.monthly_payment_budget:,.2f}

Staying consistent with your payments is key to reaching your debt-free goals! 

💡 Quick Tips:
- Set up automatic payments to never miss a due date
- Make payments early in the month when possible
- Even partial payments are better than no payment


You've got this! 💪

Best regards,
Anchorless
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[debt_plan.user.email],
                    fail_silently=False,
                )
                
                sent_count += 1
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send payment reminder to {debt_plan.user.email}: {str(e)}")
    
    return f"Sent {sent_count} payment reminders"