from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from ..models import DebtPlan
from Loan.models import Loan
from PaymentSchedule.models import PaymentSchedule, LoanPaymentSchedule
from Payment.models import Payment


def calculate_minimum_payment(principal, interest_rate, months=None):
    """
    Calculate minimum monthly payment for a loan
    If months not specified, use 2% of principal as baseline
    """
    if principal <= 0:
        raise DjangoValidationError("Principal must be positive")
    
    if interest_rate < 0:
        raise DjangoValidationError("Interest rate cannot be negative")
    
    if months is not None and months <= 0:
        raise DjangoValidationError("Months must be positive")

    if months:
        monthly_rate = (Decimal(str(interest_rate)) / Decimal('100')) / Decimal('12')
        principal = Decimal(str(principal))
        
        if monthly_rate == 0:
            payment = principal / Decimal(str(months))
        else:
            numerator = monthly_rate * ((1 + monthly_rate) ** months)
            denominator = ((1 + monthly_rate) ** months) - 1
            payment = principal * (numerator / denominator)
        
        return payment.quantize(Decimal('0.01'))
    else:
        # Default to 2% of principal or $25, whichever is higher
        principal = Decimal(str(principal))
        return max(principal * Decimal('0.02'), Decimal('25.00'))


def recalculate_all_payoff_orders(debt_plan):
    """
    Recalculate payoff orders for all loans in a debt plan
    Only considers loans with remaining balance > 0
    """
    loans = Loan.objects.filter(debt_plan=debt_plan, remaining_balance__gt=0)
    
    if debt_plan.strategy == 'snowball':
        sorted_loans = sorted(loans, key=lambda x: x.remaining_balance)
    else:  # avalanche
        sorted_loans = sorted(loans, key=lambda x: x.interest_rate, reverse=True)
    
    # Update only active loans
    for order, loan in enumerate(sorted_loans, start=1):
        loan.payoff_order = order
        loan.save(update_fields=['payoff_order'])
    
    # Set payoff_order to None for paid-off loans
    Loan.objects.filter(debt_plan=debt_plan, remaining_balance=0).update(payoff_order=None)
    
    return len(sorted_loans)


@transaction.atomic
def generate_payment_schedule(debt_plan):
    """
    Generate complete payment schedule for a debt plan
    This is the core algorithm for both snowball and avalanche methods
    """
    # Clear existing schedule
    PaymentSchedule.objects.filter(debt_plan=debt_plan).delete()
    
    # Get all loans with balance remaining, ordered by payoff strategy
    loans = list(
        Loan.objects.filter(
            debt_plan=debt_plan, 
            remaining_balance__gt=0
        ).order_by('payoff_order')
    )
    
    if not loans:
        # No loans with balance - mark plan as completed
        debt_plan.is_active = False
        debt_plan.save(update_fields=['is_active'])
        return 0
    
    # Validate all loans
    for loan in loans:
        if loan.interest_rate < 0:
            raise DjangoValidationError(f"Loan {loan.name} has negative interest rate")
        if not loan.minimum_payment or loan.minimum_payment <= 0:
            raise DjangoValidationError(f"Loan {loan.name} has invalid minimum payment")
    
    # Calculate total minimum payments
    total_minimum = sum(loan.minimum_payment for loan in loans)
    
    if debt_plan.monthly_payment_budget < total_minimum:
        raise DjangoValidationError(
            f"Monthly budget ${debt_plan.monthly_payment_budget} is less than "
            f"total minimum payments ${total_minimum}"
        )
    
    # Extra money to apply after minimums
    extra_payment = debt_plan.monthly_payment_budget - total_minimum
    
    # Create working copy of loan balances
    loan_balances = {loan.id: loan.remaining_balance for loan in loans}
    
    month_number = 1
    total_interest_paid = Decimal('0')
    
    while any(balance > 0 for balance in loan_balances.values()):
        if month_number > 600:  # Safety check (50 years)
            raise DjangoValidationError("Payment schedule exceeds 50 years - check your inputs")
        
        month_total_payment = Decimal('0')
        month_total_interest = Decimal('0')
        month_total_principal = Decimal('0')
        
        # Find focus loan (first unpaid loan in order)
        focus_loan = None
        for loan in loans:
            if loan_balances[loan.id] > 0:
                focus_loan = loan
                break
        
        remaining_extra = extra_payment
        loan_schedules_data = []
        
        # Process each loan
        for loan in loans:
            if loan_balances[loan.id] <= 0:
                continue
            
            current_balance = loan_balances[loan.id]
            monthly_interest_rate = (loan.interest_rate / Decimal('100')) / Decimal('12')
            interest_charge = (current_balance * monthly_interest_rate).quantize(Decimal('0.01'))
            
            # Determine payment amount
            is_focus = (loan.id == focus_loan.id) if focus_loan else False
            
            if is_focus:
                # Focus loan gets minimum + all remaining extra
                payment = loan.minimum_payment + remaining_extra
            else:
                # Other loans get minimum only
                payment = loan.minimum_payment
            
            # Don't overpay - cap at balance + interest
            max_payment = current_balance + interest_charge
            actual_payment = min(payment, max_payment)
            
            # If focus loan is overpaid, capture the unused extra
            if is_focus and actual_payment < payment:
                unused_extra = payment - actual_payment
                remaining_extra = unused_extra
            else:
                remaining_extra = Decimal('0')
            
            principal_payment = actual_payment - interest_charge
            new_balance = (current_balance - principal_payment).quantize(Decimal('0.01'))
            new_balance = max(new_balance, Decimal('0'))
            
            # Store loan schedule data (without payment_schedule FK yet)
            loan_schedules_data.append({
                'loan': loan,
                'payment_amount': actual_payment,
                'interest_amount': interest_charge,
                'principal_amount': principal_payment,
                'remaining_balance': new_balance,
                'is_focus_loan': is_focus
            })
            
            loan_balances[loan.id] = new_balance
            month_total_payment += actual_payment
            month_total_interest += interest_charge
            month_total_principal += principal_payment
            total_interest_paid += interest_charge
        
        # Create and SAVE the payment schedule for this month
        payment_schedule = PaymentSchedule.objects.create(
            debt_plan=debt_plan,
            month_number=month_number,
            total_payment=month_total_payment,
            total_interest=month_total_interest,
            total_principal=month_total_principal,
            focus_loan=focus_loan
        )
        
        # NOW create loan schedules with the saved payment_schedule
        loan_schedule_objects = [
            LoanPaymentSchedule(
                payment_schedule=payment_schedule, 
                loan=data['loan'],
                payment_amount=data['payment_amount'],
                interest_amount=data['interest_amount'],
                principal_amount=data['principal_amount'],
                remaining_balance=data['remaining_balance'],
                is_focus_loan=data['is_focus_loan']
            )
            for data in loan_schedules_data
        ]
        
        LoanPaymentSchedule.objects.bulk_create(loan_schedule_objects)
        
        month_number += 1
    
    # Update debt plan
    projected_date = date.today() + relativedelta(months=month_number - 1)
    debt_plan.projected_payoff_date = projected_date
    debt_plan.total_interest_saved = total_interest_paid
    debt_plan.save(update_fields=['projected_payoff_date', 'total_interest_saved'])
    
    return month_number - 1


def get_month_number(plan_start_date, payment_date):
    """
    Calculate which month number a payment falls into
    Month 1 is the first month of the plan
    """
    if payment_date < plan_start_date:
        raise DjangoValidationError("Payment date cannot be before plan start date")
    
    delta = relativedelta(payment_date, plan_start_date)
    return delta.years * 12 + delta.months + 1


@transaction.atomic
def record_payment(debt_plan, loan, amount, payment_date, payment_method='bank_transfer', 
                   notes='', confirmation_number=''):
    """
    Record a payment and determine if schedule needs recalculation
    
    Args:
        debt_plan: DebtPlan instance
        loan: Loan instance
        amount: Decimal, payment amount
        payment_date: date object
        payment_method: str, one of Payment.PAYMENT_METHOD_CHOICES
        notes: str, optional notes about the payment
        confirmation_number: str, bank confirmation or reference number
    
    Returns:
        tuple: (Payment instance, bool indicating if schedule was recalculated)
    """
    # Lock the loan to prevent race conditions
    loan = Loan.objects.select_for_update().get(id=loan.id)
    
    # Validate payment amount
    if amount <= 0:
        raise DjangoValidationError("Payment amount must be positive")
    
    # Validate loan belongs to debt plan
    if loan.debt_plan_id != debt_plan.id:
        raise DjangoValidationError("Loan does not belong to this debt plan")
    
    # Validate payment method
    valid_methods = [choice[0] for choice in Payment.PAYMENT_METHOD_CHOICES]
    if payment_method not in valid_methods:
        raise DjangoValidationError(
            f"Invalid payment method. Choose from: {', '.join(valid_methods)}"
        )
    
    # Get current month's schedule and month number
    try:
        month_number = get_month_number(
            debt_plan.created_at.date(), 
            payment_date
        )
    except DjangoValidationError:
        month_number = None
    
    # Get expected payment for this month
    expected_payment = loan.minimum_payment  # Default
    
    if month_number:
        try:
            current_schedule = PaymentSchedule.objects.get(
                debt_plan=debt_plan,
                month_number=month_number
            )
            loan_schedule = LoanPaymentSchedule.objects.get(
                payment_schedule=current_schedule,
                loan=loan
            )
            expected_payment = loan_schedule.payment_amount
        except (PaymentSchedule.DoesNotExist, LoanPaymentSchedule.DoesNotExist):
            pass  # Use default minimum_payment
    
    # Calculate interest and principal
    monthly_interest_rate = (loan.interest_rate / Decimal('100')) / Decimal('12')
    monthly_interest = (loan.remaining_balance * monthly_interest_rate).quantize(Decimal('0.01'))
    
    # Validate payment covers interest (prevents negative amortization)
    if amount < monthly_interest:
        raise DjangoValidationError(
            f"Payment of ${amount} is less than interest charge of ${monthly_interest}. "
            f"Minimum payment needed: ${monthly_interest}"
        )
    
    principal_paid = amount - monthly_interest
    
    # Determine payment classification
    is_extra = amount > expected_payment
    is_below = amount < loan.minimum_payment
    
    # Create payment record
    payment = Payment.objects.create(
        loan=loan,
        debt_plan=debt_plan,
        amount=amount,
        payment_date=payment_date,
        payment_method=payment_method,
        is_extra_payment=is_extra,
        is_below_minimum=is_below,
        month_number=month_number,
        notes=notes,
        confirmation_number=confirmation_number
    )
    
    # Update loan balance
    new_balance = loan.remaining_balance - principal_paid
    loan.remaining_balance = max(new_balance, Decimal('0')).quantize(Decimal('0.01'))
    loan.save(update_fields=['remaining_balance', 'updated_at'])
    
    # Determine if schedule needs recalculation
    should_recalculate = (
        is_below or  # Payment below minimum changes the plan
        is_extra or  # Extra payment accelerates payoff
        loan.remaining_balance == 0 or  # Loan paid off
        abs(amount - expected_payment) > Decimal('10.00')  # Significant deviation
    )
    
    if should_recalculate:
        recalculate_all_payoff_orders(debt_plan)
        generate_payment_schedule(debt_plan)
        check_if_plan_completed(debt_plan)
    
    return payment, should_recalculate


def get_current_month_plan(debt_plan):
    """
    Get the payment plan for the current month
    """
    try:
        months_since_start = get_month_number(
            debt_plan.created_at.date(),
            date.today()
        )
    except DjangoValidationError:
        return None
    
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
    
    if not loans.exists():
        return {
            'total_original': Decimal('0'),
            'total_remaining': Decimal('0'),
            'total_paid': Decimal('0'),
            'progress_percentage': Decimal('0'),
            'total_payments_made': Decimal('0'),
            'number_of_payments': 0,
            'loans_paid_off': 0,
            'total_loans': 0
        }
    
    total_original = sum(loan.principal_balance for loan in loans)
    total_remaining = sum(loan.remaining_balance for loan in loans)
    total_paid = total_original - total_remaining
    
    progress_percentage = (
        (total_paid / total_original * 100) if total_original > 0 else Decimal('0')
    )
    
    # Get actual payments made
    payments = Payment.objects.filter(debt_plan=debt_plan)
    total_payments_made = sum(p.amount for p in payments) if payments.exists() else Decimal('0')
    
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
    Check if debt plan is completed and update status
    """
    loans = Loan.objects.filter(debt_plan=debt_plan)
    
    if not loans.exists():
        return False
    
    all_paid = all(loan.remaining_balance == 0 for loan in loans)
    
    if all_paid and debt_plan.is_active:
        debt_plan.is_active = False
        debt_plan.save(update_fields=['is_active'])
        return True
    
    return False