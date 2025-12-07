from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from ..models import DebtPlan
from Loan.models import Loan
from PaymentSchedule.models import PaymentSchedule, LoanPaymentSchedule
from Payment.models import Payment
from django.db import models


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
    
    Key improvements:
    - Two-pass algorithm for proper extra payment redistribution
    - Handles overpayment scenarios correctly
    - Prevents loss of extra payments when focus loan is paid off early
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
        
        # Process each loan with minimum payment (focus gets minimum + extra)
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
            
            # If focus loan is overpaid, capture the unused extra for redistribution
            if is_focus and actual_payment < payment:
                remaining_extra = payment - actual_payment
            elif is_focus:
                # Focus loan accepted all the extra
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
            
            # Update working balance
            loan_balances[loan.id] = new_balance
            month_total_payment += actual_payment
            month_total_interest += interest_charge
            month_total_principal += principal_payment
            total_interest_paid += interest_charge
        
        # If focus loan couldn't accept all extra, redistribute to other loans
        if remaining_extra > 0:
            for schedule_data in loan_schedules_data:
                # Skip focus loan and fully paid loans
                if schedule_data['is_focus_loan']:
                    continue
                
                loan_id = schedule_data['loan'].id
                if loan_balances[loan_id] <= 0:
                    continue
                
                current_balance = loan_balances[loan_id]
                
                # Calculate how much more this loan can accept
                # (current balance minus what we're already paying toward principal)
                max_additional = current_balance - schedule_data['principal_amount']
                max_additional = max(max_additional, Decimal('0'))  # Can't be negative
                
                # Apply as much extra as possible to this loan
                additional_payment = min(remaining_extra, max_additional)
                
                if additional_payment > 0:
                    # Update schedule data
                    schedule_data['payment_amount'] += additional_payment
                    schedule_data['principal_amount'] += additional_payment
                    schedule_data['remaining_balance'] -= additional_payment
                    
                    # Update tracking
                    loan_balances[loan_id] -= additional_payment
                    month_total_payment += additional_payment
                    month_total_principal += additional_payment
                    remaining_extra -= additional_payment
                
                # If we've redistributed all extra, we're done
                if remaining_extra <= 0:
                    break
        
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
    
    # Update debt plan with final projections
    projected_date = date.today() + relativedelta(months=month_number - 1)
    debt_plan.projected_payoff_date = projected_date
    debt_plan.total_interest_saved = total_interest_paid
    debt_plan.save(update_fields=['projected_payoff_date', 'total_interest_saved'])

    # Generate PDF (optional, log errors but don't fail)
    try:
        from accountability_helpers.utils.pdf_generator import save_payment_plan_pdf
        save_payment_plan_pdf(debt_plan)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to generate PDF for debt plan {debt_plan.id}: {str(e)}")
    
    return month_number - 1


def validate_schedule_integrity(debt_plan):
    """
    Validate that the generated schedule is mathematically correct
    Use this in testing to verify the algorithm works properly
    """
    schedules = PaymentSchedule.objects.filter(debt_plan=debt_plan).order_by('month_number')
    
    total_paid = Decimal('0')
    for schedule in schedules:
        # Each month's payment should equal budget (except possibly last month)
        if schedule.month_number < schedules.count():
            assert schedule.total_payment == debt_plan.monthly_payment_budget, \
                f"Month {schedule.month_number}: Payment mismatch"
        
        # Interest + Principal should equal Total Payment
        assert schedule.total_interest + schedule.total_principal == schedule.total_payment, \
            f"Month {schedule.month_number}: Components don't sum to total"
        
        total_paid += schedule.total_payment
    
    # Total paid should approximately equal original debt + interest
    loans = Loan.objects.filter(debt_plan=debt_plan)
    total_original = sum(loan.principal_balance for loan in loans)
    
    print(f"✓ Schedule validation passed")
    print(f"  Total months: {schedules.count()}")
    print(f"  Total paid: ${total_paid}")
    print(f"  Original debt: ${total_original}")
    print(f"  Total interest: ${debt_plan.total_interest_saved}")
    
    return True

@transaction.atomic
def regenerate_schedule_from_month(debt_plan, start_month):
    """
    Regenerate payment schedule starting from a specific month
    Preserves all schedules before start_month
    
    Args:
        debt_plan: DebtPlan instance
        start_month: int, month number to start regeneration from
    """
    from dateutil.relativedelta import relativedelta
    
    # Delete only FUTURE schedules (starting from start_month)
    PaymentSchedule.objects.filter(
        debt_plan=debt_plan,
        month_number__gte=start_month
    ).delete()
    
    # Get all loans with remaining balance
    loans = list(
        Loan.objects.filter(
            debt_plan=debt_plan,
            remaining_balance__gt=0
        ).order_by('payoff_order')
    )
    
    if not loans:
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
    
    extra_payment = debt_plan.monthly_payment_budget - total_minimum
    
    # Use CURRENT balances as starting point (not original balances)
    loan_balances = {loan.id: loan.remaining_balance for loan in loans}
    
    month_number = start_month
    total_interest_paid = Decimal('0')
    
    # Add interest from PREVIOUS months (before start_month)
    previous_schedules = PaymentSchedule.objects.filter(
        debt_plan=debt_plan,
        month_number__lt=start_month
    )
    total_interest_paid = sum(
        schedule.total_interest for schedule in previous_schedules
    )
    
    # Same generation logic as generate_payment_schedule()
    while any(balance > 0 for balance in loan_balances.values()):
        if month_number > 600:
            raise DjangoValidationError("Payment schedule exceeds 50 years")
        
        month_total_payment = Decimal('0')
        month_total_interest = Decimal('0')
        month_total_principal = Decimal('0')
        
        # Find focus loan
        focus_loan = None
        for loan in loans:
            if loan_balances[loan.id] > 0:
                focus_loan = loan
                break
        
        remaining_extra = extra_payment
        loan_schedules_data = []
        
        # Process each loan (same logic as before)
        for loan in loans:
            if loan_balances[loan.id] <= 0:
                continue
            
            current_balance = loan_balances[loan.id]
            monthly_interest_rate = (loan.interest_rate / Decimal('100')) / Decimal('12')
            interest_charge = (current_balance * monthly_interest_rate).quantize(Decimal('0.01'))
            
            is_focus = (loan.id == focus_loan.id) if focus_loan else False
            
            if is_focus:
                payment = loan.minimum_payment + remaining_extra
            else:
                payment = loan.minimum_payment
            
            max_payment = current_balance + interest_charge
            actual_payment = min(payment, max_payment)
            
            if is_focus and actual_payment < payment:
                remaining_extra = payment - actual_payment
            elif is_focus:
                remaining_extra = Decimal('0')
            
            principal_payment = actual_payment - interest_charge
            new_balance = (current_balance - principal_payment).quantize(Decimal('0.01'))
            new_balance = max(new_balance, Decimal('0'))
            
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
        
        # Redistribute remaining extra (same logic as before)
        if remaining_extra > 0:
            for schedule_data in loan_schedules_data:
                if schedule_data['is_focus_loan']:
                    continue
                
                loan_id = schedule_data['loan'].id
                if loan_balances[loan_id] <= 0:
                    continue
                
                current_balance = loan_balances[loan_id]
                max_additional = current_balance - schedule_data['principal_amount']
                max_additional = max(max_additional, Decimal('0'))
                
                additional_payment = min(remaining_extra, max_additional)
                
                if additional_payment > 0:
                    schedule_data['payment_amount'] += additional_payment
                    schedule_data['principal_amount'] += additional_payment
                    schedule_data['remaining_balance'] -= additional_payment
                    
                    loan_balances[loan_id] -= additional_payment
                    month_total_payment += additional_payment
                    month_total_principal += additional_payment
                    remaining_extra -= additional_payment
                
                if remaining_extra <= 0:
                    break
        
        # Create payment schedule
        payment_schedule = PaymentSchedule.objects.create(
            debt_plan=debt_plan,
            month_number=month_number,
            total_payment=month_total_payment,
            total_interest=month_total_interest,
            total_principal=month_total_principal,
            focus_loan=focus_loan
        )
        
        # Create loan schedules
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
    
    # Update debt plan projections
    projected_date = debt_plan.created_at.date() + relativedelta(months=month_number - 1)
    debt_plan.projected_payoff_date = projected_date
    debt_plan.total_interest_saved = total_interest_paid
    debt_plan.save(update_fields=['projected_payoff_date', 'total_interest_saved'])
    
    # Regenerate PDF
    try:
        from accountability_helpers.utils.pdf_generator import save_payment_plan_pdf
        save_payment_plan_pdf(debt_plan)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to generate PDF: {str(e)}")
    
    return month_number - start_month


def get_month_number(plan_start_date, payment_date):
    """
    Calculate which month number a payment falls into
    Month 1 is the first month of the plan
    """
    if payment_date < plan_start_date:
        raise DjangoValidationError("Payment date cannot be before plan start date")
    
    plan_month_start = plan_start_date.replace(day=1)
    payment_month_start = payment_date.replace(day=1)

    delta = relativedelta(payment_month_start, plan_month_start)
    return delta.years * 12 + delta.months + 1


def determine_payment_timing(payment, debt_plan):
    """Determine if payment is early, on-time, or late"""
    from datetime import timedelta
    
    current_month = get_month_number(debt_plan.created_at.date(), date.today())
    
    if payment.month_number > current_month:
        return 'early'
    elif payment.month_number < current_month:
        return 'late'
    else:
        # Same month - check against loan due date
        expected_date = debt_plan.created_at.date().replace(day=min(payment.loan.due_date, 28))
        if payment.payment_date < expected_date - timedelta(days=3):
            return 'early'
        elif payment.payment_date > expected_date + timedelta(days=3):
            return 'late'
        else:
            return 'on_time'


@transaction.atomic
def record_payment(debt_plan, loan, amount, payment_date, payment_method='bank_transfer', 
                   notes='', confirmation_number='', month_number=None, skip_recalculation=False):
    """
    FIXED: Record a payment with proper interest calculation
    """
    # Lock the loan to prevent race conditions
    loan = Loan.objects.select_for_update().get(id=loan.id)
    debt_plan = DebtPlan.objects.select_for_update().get(id=debt_plan.id)
    
    # Validate basic requirements
    if amount <= 0:
        raise DjangoValidationError("Payment amount must be positive")
    
    if loan.debt_plan_id != debt_plan.id:
        raise DjangoValidationError("Loan does not belong to this debt plan")
    
    # Determine month number if not provided
    if not month_number:
        try:
            month_number = get_month_number(debt_plan.created_at.date(), payment_date)
        except DjangoValidationError as e:
            raise DjangoValidationError(f"Cannot record payment: {str(e)}")
    
    # Validate month exists
    max_month = PaymentSchedule.objects.filter(
        debt_plan=debt_plan
    ).aggregate(models.Max('month_number'))['month_number__max'] or 0
    
    if month_number > max_month:
        raise DjangoValidationError(
            f"Cannot make payments for month {month_number}. "
            f"Schedule only goes up to month {max_month}."
        )
    
    # Get expected payment
    expected_payment = loan.minimum_payment
    payment_schedule = None
    
    try:
        payment_schedule = PaymentSchedule.objects.get(
            debt_plan=debt_plan,
            month_number=month_number
        )
        loan_schedule = LoanPaymentSchedule.objects.get(
            payment_schedule=payment_schedule,
            loan=loan
        )
        expected_payment = loan_schedule.payment_amount
    except (PaymentSchedule.DoesNotExist, LoanPaymentSchedule.DoesNotExist):
        pass
    
    # *** CRITICAL FIX: Store balance BEFORE payment ***
    balance_before_payment = loan.remaining_balance
    
    # Calculate interest on balance BEFORE payment (not current balance!)
    monthly_interest_rate = (loan.interest_rate / Decimal('100')) / Decimal('12')
    interest_charge = (balance_before_payment * monthly_interest_rate).quantize(Decimal('0.01'))
    
    # Validate payment covers interest
    if amount < interest_charge:
        raise DjangoValidationError(
            f"Payment of ${amount} is less than interest charge of ${interest_charge}. "
            f"Minimum payment needed: ${interest_charge}."
        )
    
    # Calculate principal
    principal_paid = amount - interest_charge
    
    # Validate not overpaying
    max_allowed = balance_before_payment + interest_charge
    if amount > max_allowed:
        raise DjangoValidationError(
            f"Payment of ${amount} exceeds remaining balance plus interest (${max_allowed})."
        )
    
    # Determine classification
    is_extra = amount > expected_payment if expected_payment else amount > loan.minimum_payment
    is_below = amount < loan.minimum_payment
    
    # *** CREATE PAYMENT WITH STORED VALUES ***
    payment = Payment.objects.create(
        loan=loan,
        debt_plan=debt_plan,
        payment_schedule=payment_schedule,
        amount=amount,
        payment_date=payment_date,
        payment_method=payment_method,
        interest_paid=interest_charge,  # STORED AT PAYMENT TIME
        principal_paid=principal_paid,   # STORED AT PAYMENT TIME
        balance_before_payment=balance_before_payment,  # STORED
        is_extra_payment=is_extra,
        is_below_minimum=is_below,
        month_number=month_number,
        notes=notes,
        confirmation_number=confirmation_number
    )
    
    # Set payment timing
    payment.payment_timing = determine_payment_timing(payment, debt_plan)
    payment.save(update_fields=['payment_timing'])
    
    # Update loan balance
    new_balance = balance_before_payment - principal_paid
    loan.remaining_balance = max(new_balance, Decimal('0')).quantize(Decimal('0.01'))
    loan.save(update_fields=['remaining_balance', 'updated_at'])
    
    # Determine if recalculation needed
    should_recalculate = False
    if not skip_recalculation:
        deviation = abs(amount - expected_payment) if expected_payment else Decimal('0')
        should_recalculate = (
            deviation > Decimal('10.00') or
            loan.remaining_balance == 0 or
            is_below or
            is_extra
        )
    
    if should_recalculate:
        recalculate_all_payoff_orders(debt_plan)
        regenerate_schedule_from_month(debt_plan, month_number)
        
        # Relink payment to new schedule
        try:
            new_schedule = PaymentSchedule.objects.get(
                debt_plan=debt_plan,
                month_number=month_number
            )
            if LoanPaymentSchedule.objects.filter(
                payment_schedule=new_schedule, loan=loan
            ).exists():
                payment.payment_schedule = new_schedule
            else:
                payment.payment_schedule = None
            payment.save(update_fields=['payment_schedule'])
        except PaymentSchedule.DoesNotExist:
            payment.payment_schedule = None
            payment.save(update_fields=['payment_schedule'])
        
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
    FIXED: Calculate progress using loan balances (source of truth)
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
    
    # *** USE LOAN BALANCES AS SOURCE OF TRUTH ***
    total_original = sum(loan.principal_balance for loan in loans)
    total_remaining = sum(loan.remaining_balance for loan in loans)
    total_paid = total_original - total_remaining  # THIS IS THE TRUE AMOUNT PAID
    
    # Get sum of all payment amounts (for reference/debugging)
    payments = Payment.objects.filter(debt_plan=debt_plan)
    total_payment_amounts = sum(p.amount for p in payments) if payments.exists() else Decimal('0')
    
    # Calculate percentage
    progress_percentage = (
        (total_paid / total_original * 100) if total_original > 0 else Decimal('0')
    )
    
    return {
        'total_original': total_original,
        'total_remaining': total_remaining,
        'total_paid': total_paid, 
        'progress_percentage': round(progress_percentage, 2),
        'total_payments_made': total_payment_amounts,
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

        try:
            from accountability_helpers.models import LetterToSelf
            from accountability_helpers.tasks import send_completion_letter
            
            letter = LetterToSelf.objects.get(debt_plan=debt_plan, is_sent=False)
            # Queue the email to be sent
            send_completion_letter.delay(letter.id)
        except LetterToSelf.DoesNotExist:
            # No letter exists, that's fine
            pass
        except Exception as e:
            # Log error but don't fail
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send completion letter: {str(e)}")
        return True
    
    return False


def get_accurate_months_remaining(debt_plan):
    """
    FIXED: Calculate months remaining based on current schedule
    """
    
    try:
        current_month = get_month_number(debt_plan.created_at.date(), date.today())
    except:
        current_month = 1
    
    # Get schedules from current month onwards
    remaining_schedules = PaymentSchedule.objects.filter(
        debt_plan=debt_plan,
        month_number__gte=current_month
    ).order_by('month_number')
    
    if not remaining_schedules.exists():
        return 0
    
    # Count months that still have unpaid balances
    months_remaining = 0
    for schedule in remaining_schedules:
        # Check if any loan in this schedule still has balance
        has_balance = schedule.loan_breakdowns.filter(
            remaining_balance__gt=0
        ).exists()
        
        if has_balance:
            months_remaining += 1
    
    return months_remaining