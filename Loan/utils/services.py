from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction
from ..models import DebtPlan
from Loan.models import Loan
from PaymentSchedule.models import PaymentSchedule, LoanPaymentSchedule
from Payment.models import Payment


def calculate_minimum_payment(principal, interest_rate, months=None):
    """
    Calculate minimum monthly payment for a loan
    If months not specified, use 2% of principal as baseline
    """
    if months:
        monthly_rate = (interest_rate / 100) / 12
        if monthly_rate == 0:
            return principal / months
        payment = principal * (monthly_rate * (1 + monthly_rate)**months) / \
                  ((1 + monthly_rate)**months - 1)
        return round(payment, 2)
    else:
        # Default to 2% of principal or $25, whichever is higher
        return max(principal * Decimal('0.02'), Decimal('25.00'))


def recalculate_all_payoff_orders(debt_plan):
    """
    Recalculate payoff orders for all loans in a debt plan
    """
    loans = Loan.objects.filter(debt_plan=debt_plan)
    
    if debt_plan.strategy == 'snowball':
        sorted_loans = sorted(loans, key=lambda x: x.remaining_balance)
    else:  # avalanche
        sorted_loans = sorted(loans, key=lambda x: x.interest_rate, reverse=True)
    
    for order, loan in enumerate(sorted_loans, start=1):
        loan.payoff_order = order
        loan.save()
    
    return len(sorted_loans)


@transaction.atomic
def generate_payment_schedule(debt_plan):
    """
    Generate complete payment schedule for a debt plan
    This is the core algorithm for both snowball and avalanche methods
    """
    # Clear existing schedule
    PaymentSchedule.objects.filter(debt_plan=debt_plan).delete()
    
    # Get all loans ordered by payoff strategy
    loans = list(Loan.objects.filter(debt_plan=debt_plan).order_by('payoff_order'))
    
    if not loans:
        return None
    
    # Calculate total minimum payments
    total_minimum = sum(loan.minimum_payment or Decimal('0') for loan in loans)
    
    if debt_plan.monthly_payment_budget < total_minimum:
        raise ValueError("Monthly budget is less than total minimum payments required")
    
    # Extra money to apply after minimums
    extra_payment = debt_plan.monthly_payment_budget - total_minimum
    
    # Create working copy of loan balances
    loan_balances = {loan.id: loan.remaining_balance for loan in loans}
    
    month_number = 1
    total_interest_paid = Decimal('0')
    
    while any(balance > 0 for balance in loan_balances.values()):
        if month_number > 600:  # Safety check (50 years)
            raise ValueError("Payment schedule exceeds 50 years")
        
        # Create month's payment schedule
        payment_schedule = PaymentSchedule.objects.create(
            debt_plan=debt_plan,
            month_number=month_number,
            total_payment=Decimal('0'),
            total_interest=Decimal('0'),
            total_principal=Decimal('0')
        )
        
        month_total_payment = Decimal('0')
        month_total_interest = Decimal('0')
        month_total_principal = Decimal('0')
        
        # Find focus loan (first unpaid loan in order)
        focus_loan = None
        for loan in loans:
            if loan_balances[loan.id] > 0:
                focus_loan = loan
                break
        
        # Process each loan
        for loan in loans:
            if loan_balances[loan.id] <= 0:
                continue
            
            current_balance = loan_balances[loan.id]
            monthly_interest_rate = (loan.interest_rate / 100) / 12
            interest_charge = current_balance * monthly_interest_rate
            
            # Determine payment amount
            is_focus = (loan.id == focus_loan.id) if focus_loan else False
            
            if is_focus:
                # Focus loan gets minimum + extra
                payment = loan.minimum_payment + extra_payment
            else:
                # Other loans get minimum only
                payment = loan.minimum_payment
            
            # Don't overpay
            max_payment = current_balance + interest_charge
            payment = min(payment, max_payment)
            
            principal_payment = payment - interest_charge
            new_balance = max(current_balance - principal_payment, Decimal('0'))
            
            # Create loan breakdown
            LoanPaymentSchedule.objects.create(
                payment_schedule=payment_schedule,
                loan=loan,
                payment_amount=payment,
                interest_amount=interest_charge,
                principal_amount=principal_payment,
                remaining_balance=new_balance,
                is_focus_loan=is_focus
            )
            
            loan_balances[loan.id] = new_balance
            month_total_payment += payment
            month_total_interest += interest_charge
            month_total_principal += principal_payment
            total_interest_paid += interest_charge
        
        # Update payment schedule totals
        payment_schedule.total_payment = month_total_payment
        payment_schedule.total_interest = month_total_interest
        payment_schedule.total_principal = month_total_principal
        payment_schedule.focus_loan = focus_loan
        payment_schedule.save()
        
        month_number += 1
    
    # Update debt plan
    projected_date = date.today() + relativedelta(months=month_number - 1)
    debt_plan.projected_payoff_date = projected_date
    debt_plan.total_interest_saved = total_interest_paid
    debt_plan.save()
    
    return month_number - 1


@transaction.atomic
def record_payment(debt_plan, loan, amount, payment_date):
    """
    Record a payment and determine if schedule needs recalculation
    """
    # Get current month's schedule
    months_since_start = (payment_date.year - debt_plan.created_at.year) * 12 + \
                         (payment_date.month - debt_plan.created_at.month) + 1
    
    try:
        current_schedule = PaymentSchedule.objects.get(
            debt_plan=debt_plan,
            month_number=months_since_start
        )
        loan_schedule = LoanPaymentSchedule.objects.get(
            payment_schedule=current_schedule,
            loan=loan
        )
        expected_payment = loan_schedule.payment_amount
    except (PaymentSchedule.DoesNotExist, LoanPaymentSchedule.DoesNotExist):
        expected_payment = loan.minimum_payment
    
    # Determine payment type
    is_extra = amount > expected_payment
    is_below = amount < loan.minimum_payment
    
    # Create payment record
    payment = Payment.objects.create(
        user=debt_plan.user,
        loan=loan,
        debt_plan=debt_plan,
        amount=amount,
        payment_date=payment_date,
        is_extra_payment=is_extra,
        is_below_minimum=is_below
    )
    
    # Update loan balance
    monthly_interest = loan.remaining_balance * (loan.interest_rate / 100) / 12
    principal_paid = amount - monthly_interest
    loan.remaining_balance = max(loan.remaining_balance - principal_paid, Decimal('0'))
    loan.save()
    
    # Recalculate if payment deviates significantly
    should_recalculate = is_below or is_extra or \
                        abs(amount - expected_payment) > Decimal('10.00')
    
    if should_recalculate:
        recalculate_all_payoff_orders(debt_plan)
        generate_payment_schedule(debt_plan)
    
    return payment, should_recalculate


def get_current_month_plan(debt_plan):
    """
    Get the payment plan for the current month
    """
    months_since_start = (date.today().year - debt_plan.created_at.year) * 12 + \
                         (date.today().month - debt_plan.created_at.month) + 1
    
    try:
        schedule = PaymentSchedule.objects.prefetch_related(
            'loan_breakdowns__loan'
        ).get(
            debt_plan=debt_plan,
            month_number=months_since_start
        )
        return schedule
    except PaymentSchedule.DoesNotExist:
        return None


def calculate_progress(debt_plan):
    """
    Calculate overall progress on debt plan
    """
    loans = Loan.objects.filter(debt_plan=debt_plan)
    
    total_original = sum(loan.principal_balance for loan in loans)
    total_remaining = sum(loan.remaining_balance for loan in loans)
    total_paid = total_original - total_remaining
    
    progress_percentage = (total_paid / total_original * 100) if total_original > 0 else 0
    
    # Get actual payments made
    payments = Payment.objects.filter(debt_plan=debt_plan)
    total_payments_made = sum(p.amount for p in payments)
    
    return {
        'total_original': total_original,
        'total_remaining': total_remaining,
        'total_paid': total_paid,
        'progress_percentage': round(progress_percentage, 2),
        'total_payments_made': total_payments_made,
        'number_of_payments': payments.count(),
        'loans_paid_off': loans.filter(remaining_balance=0).count(),
        'total_loans': loans.count()
    }


def check_if_plan_completed(debt_plan):
    """
    Check if debt plan is completed
    """
    loans = Loan.objects.filter(debt_plan=debt_plan)
    all_paid = all(loan.remaining_balance == 0 for loan in loans)
    
    if all_paid and debt_plan.is_active:
        debt_plan.is_active = False
        debt_plan.save()
        return True
    
    return False