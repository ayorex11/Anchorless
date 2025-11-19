from rest_framework.decorators import api_view, throttle_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from Loan.utils.services import(
    generate_payment_schedule,
    record_payment,
    get_current_month_plan,
    calculate_progress,
    recalculate_all_payoff_orders,
    check_if_plan_completed,
    calculate_minimum_payment,
)
from rest_framework.parsers import FormParser, MultiPartParser
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from DebtPlan.models import DebtPlan
from .models import PaymentSchedule, LoanPaymentSchedule
@api_view(['GET'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])

def get_schedule(request, debt_plan_id):
    user = request.user
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response({'detail': 'Debt plan not found.'}, status=status.HTTP_404_NOT_FOUND)
    schedule = PaymentSchedule.objects.filter(debt_plan=debt_plan).prefetch_related('loan_payment_schedules__loan')
    serializer = PaymentScheduleSerializer(schedule, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
