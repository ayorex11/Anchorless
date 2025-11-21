from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from drf_yasg.utils import swagger_auto_schema
from decimal import Decimal
from datetime import date

from .models import PaymentSchedule, LoanPaymentSchedule
from .serializers import (
    PaymentScheduleSerializer,
    PaymentScheduleSummarySerializer,
    PaymentScheduleWithProgressSerializer,
    PaymentScheduleDetailQuerySerializer,
    DebtPlanQuerySerializer,
    ProgressSerializer
)
from DebtPlan.models import DebtPlan
from Loan.models import Loan
from Payment.models import Payment
from Loan.utils.services import get_month_number


@swagger_auto_schema(
    methods=['GET'],
    query_serializer=DebtPlanQuerySerializer,
    operation_description="List all payment schedules for a debt plan, ordered by month"
)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def list_payment_schedules(request):
    """
    Get all scheduled payment months for a debt plan (simple list)
    Use this to see the entire payment timeline
    """
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if not debt_plan_id:
        return Response(
            {'error': 'debt_plan parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid debt plan ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    schedules = PaymentSchedule.objects.filter(
        debt_plan=debt_plan
    ).select_related('focus_loan', 'debt_plan').order_by('month_number')
    
    serializer = PaymentScheduleSummarySerializer(schedules, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    methods=['GET'],
    query_serializer=PaymentScheduleDetailQuerySerializer,
    operation_description="Get detailed payment schedule for a specific month with loan-by-loan breakdown (ordered by payoff priority)"
)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def get_payment_schedule_detail(request):
    """
    Get detailed breakdown for a specific month showing:
    - How much to pay each loan
    - Which loan is the focus
    - Interest vs principal split
    - Expected remaining balance after payment
    """
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    month_number = request.query_params.get('month_number')
    
    if not debt_plan_id or not month_number:
        return Response(
            {'error': 'debt_plan and month_number parameters are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        month_number = int(month_number)
    except ValueError:
        return Response(
            {'error': 'month_number must be an integer'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid debt plan ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        schedule = PaymentSchedule.objects.prefetch_related(
            'loan_breakdowns__loan'
        ).select_related('focus_loan', 'debt_plan').get(
            debt_plan=debt_plan,
            month_number=month_number
        )
    except PaymentSchedule.DoesNotExist:
        return Response(
            {'error': f'No payment schedule found for month {month_number}'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = PaymentScheduleSerializer(schedule)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    methods=['GET'],
    query_serializer=DebtPlanQuerySerializer,
    operation_description="Get current month's payment schedule based on today's date"
)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def get_current_month_schedule(request):
    """
    Get what you should pay THIS month
    Automatically calculates which month you're in based on when the plan started
    """
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if not debt_plan_id:
        return Response(
            {'error': 'debt_plan parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid debt plan ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        current_month = get_month_number(debt_plan.created_at.date(), date.today())
    except DjangoValidationError:
        return Response(
            {'error': 'Unable to determine current month - plan may not have started yet'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        schedule = PaymentSchedule.objects.prefetch_related(
            'loan_breakdowns__loan'
        ).select_related('focus_loan', 'debt_plan').get(
            debt_plan=debt_plan,
            month_number=current_month
        )
    except PaymentSchedule.DoesNotExist:
        return Response(
            {'error': f'No payment schedule found for current month ({current_month})'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    serializer = PaymentScheduleSerializer(schedule)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    methods=['GET'],
    query_serializer=DebtPlanQuerySerializer,
    operation_description="Get all payment schedules with completion status - shows which months are paid, current, or upcoming"
)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def get_schedules_with_progress(request):
    """
    Get payment timeline showing which months are:
    - Completed (paid in full)
    - Partially paid
    - Current month
    - Upcoming months
    
    Perfect for creating a visual timeline or progress tracker
    """
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if not debt_plan_id:
        return Response(
            {'error': 'debt_plan parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid debt plan ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get current month for context
    try:
        current_month = get_month_number(debt_plan.created_at.date(), date.today())
    except DjangoValidationError:
        current_month = 1
    
    schedules = PaymentSchedule.objects.filter(
        debt_plan=debt_plan
    ).prefetch_related('actual_payments').select_related(
        'focus_loan', 'debt_plan'
    ).order_by('month_number')
    
    serializer = PaymentScheduleWithProgressSerializer(schedules, many=True)
    
    # Add current month indicator to response
    response_data = serializer.data
    for schedule_data in response_data:
        schedule_data['is_current_month'] = schedule_data['month_number'] == current_month
        schedule_data['is_past_month'] = schedule_data['month_number'] < current_month
        schedule_data['is_future_month'] = schedule_data['month_number'] > current_month
    
    return Response(response_data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    methods=['GET'],
    query_serializer=DebtPlanQuerySerializer,
    operation_description="Get comprehensive debt payoff progress including overall stats and per-loan breakdown (ordered by payoff priority)"
)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def get_debt_progress(request):
    """
    MASTER PROGRESS VIEW - Get everything you need for progress bars and dashboards:
    
    Overall Progress:
    - Total debt (original vs remaining)
    - Percentage paid off
    - Months completed vs remaining
    - Current month number
    - Projected completion date
    
    Per-Loan Progress (in payoff order):
    - Each loan's progress percentage
    - Which loans are paid off
    - Which loan is currently being focused on
    - Remaining balances
    """
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if not debt_plan_id:
        return Response(
            {'error': 'debt_plan parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid debt plan ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get all loans ordered by payoff priority
    loans = Loan.objects.filter(debt_plan=debt_plan).order_by('payoff_order')
    
    if not loans.exists():
        return Response(
            {'error': 'No loans found for this debt plan'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Calculate overall debt metrics
    total_original = sum(loan.principal_balance for loan in loans)
    total_remaining = sum(loan.remaining_balance for loan in loans)
    total_paid = total_original - total_remaining
    
    # Get schedule information
    schedules = PaymentSchedule.objects.filter(debt_plan=debt_plan).prefetch_related('actual_payments')
    total_months = schedules.count()
    
    # Calculate current month
    try:
        current_month = get_month_number(debt_plan.created_at.date(), date.today())
    except DjangoValidationError:
        current_month = 1
    
    # Calculate how many months are fully completed
    completed_months = sum(1 for schedule in schedules if schedule.is_fully_paid)
    months_remaining = total_months - completed_months
    
    # Overall progress percentage
    progress_percentage = (total_paid / total_original * 100) if total_original > 0 else Decimal('0')
    
    # Determine which loan is currently being focused on
    current_focus_loan = None
    try:
        current_schedule = PaymentSchedule.objects.get(
            debt_plan=debt_plan,
            month_number=current_month
        )
        current_focus_loan = current_schedule.focus_loan
    except PaymentSchedule.DoesNotExist:
        pass
    
    # Build per-loan breakdown
    loan_data = []
    for loan in loans:
        loan_paid = loan.principal_balance - loan.remaining_balance
        loan_progress = (loan_paid / loan.principal_balance * 100) if loan.principal_balance > 0 else Decimal('0')
        
        loan_data.append({
            'id': str(loan.id),
            'name': loan.name,
            'payoff_order': loan.payoff_order,
            'original_balance': str(loan.principal_balance),
            'remaining_balance': str(loan.remaining_balance),
            'paid_amount': str(loan_paid),
            'progress_percentage': str(loan_progress.quantize(Decimal('0.01'))),
            'interest_rate': str(loan.interest_rate),
            'minimum_payment': str(loan.minimum_payment),
            'is_paid_off': loan.remaining_balance == 0,
            'is_current_focus': current_focus_loan and loan.id == current_focus_loan.id
        })
    
    progress_data = {
        'total_months': total_months,
        'completed_months': completed_months,
        'months_remaining': months_remaining,
        'current_month_number': current_month,
        'progress_percentage': progress_percentage.quantize(Decimal('0.01')),
        'total_debt_original': str(total_original),
        'total_debt_remaining': str(total_remaining),
        'total_debt_paid': str(total_paid),
        'projected_payoff_date': debt_plan.projected_payoff_date,
        'total_interest_to_pay': str(debt_plan.total_interest_saved or Decimal('0')),
        'loans': loan_data,
        'strategy': debt_plan.strategy,
        'monthly_payment_budget': str(debt_plan.monthly_payment_budget)
    }
    
    serializer = ProgressSerializer(progress_data)
    return Response(serializer.data, status=status.HTTP_200_OK)