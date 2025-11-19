from .models import DebtPlan
from .serializers import DebtPlanSerializer, UpdateDebtPlanSerializer
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from django.utils import timezone
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser
from Loan.models import Loan
from rest_framework.validators import ValidationError
from Loan.utils.services import(
    generate_payment_schedule,
    record_payment,
    get_current_month_plan,
    calculate_progress,
    recalculate_all_payoff_orders,
    check_if_plan_completed,
    calculate_minimum_payment,
)


@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def list_debt_plans(request):
    user = request.user
    debt_plans = DebtPlan.objects.filter(user=user)
    serializer = DebtPlanSerializer(debt_plans, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

@swagger_auto_schema(methods=['POST'], request_body=DebtPlanSerializer)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['POST'])
def create_debt_plan(request):
    user = request.user
    serialzer = DebtPlanSerializer(data=request.data)
    if not serialzer.is_valid():
        return Response(serialzer.errors)
    validated_data = serialzer.validated_data
    strategy = validated_data['strategy']
    name = validated_data['name']
    monthly_payment_budget = validated_data['monthly_payment_budget']
    if monthly_payment_budget <= 0:
        return Response(
            {'error': 'Monthly payment budget must be positive'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    DebtPlan.objects.create(
        strategy = strategy,
        user = user,
        name = name,
        monthly_payment_budget = monthly_payment_budget,
        projected_payoff_date = None,
        total_interest_saved = None,
        is_active = False
    )
    return Response(serialzer.data, status=status.HTTP_201_CREATED)
    



@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def get_debt_plan(request, plan_id):
    user = request.user
    try:
        debt_plan = DebtPlan.objects.get(user=user, id=plan_id)
    except DebtPlan.DoesNotExist:
        return Response(
            {'message': 'DebtPlan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except ValidationError:
        return Response(
            {'message': 'Invalid plan ID'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = DebtPlanSerializer(debt_plan, many=False)
    return Response(serializer.data, status=status.HTTP_200_OK)

@swagger_auto_schema(methods=['PATCH'], request_body=UpdateDebtPlanSerializer)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['PATCH'])
def update_debt_plan(request, plan_id):
    user = request.user
    try: 
        debt_plan = DebtPlan.objects.get(id=plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'message': 'DebtPlan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except ValidationError:
        return Response(
            {'message': 'Invalid plan ID'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = UpdateDebtPlanSerializer(debt_plan, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors)
    serializer.save()
    loans = Loan.objects.filter(debt_plan=debt_plan, user=user)
    if loans:
        generate_payment_schedule(debt_plan)
    else:
        pass

    return Response(serializer.data, status=status.HTTP_200_OK)