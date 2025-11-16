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

@swagger_auto_schema(methods=['POST'], request_body=DebtPlanSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
def create_debt_plan(request):
    user = request.user
    serializer = DebtPlanSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    validated_data = serializer.validated_data
    debt_plan = DebtPlan.objects.create(
        user=user,
        name=validated_data['name'],
        strategy=validated_data['strategy'],
        monthly_payment_budget=validated_data['monthly_payment_budget'],
        projected_payoff_date=None,
        total_interest_saved=0,
        is_active=False
    )
    debt_plan.save()
    response_serializer = DebtPlanSerializer(debt_plan)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)

@swagger_auto_schema(methods=['PATCH'], request_body=UpdateDebtPlanSerializer)
@api_view(['PATCH'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])

def update_debt_plan(request, plan_id):
    user = request.user
    try:
        debt_plan = DebtPlan.objects.get(id=plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response({'detail': 'Debt plan not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    serializer = UpdateDebtPlanSerializer(debt_plan, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # recalculation logic here

    serializer.save()
    response_serializer = DebtPlanSerializer(debt_plan)
    return Response(response_serializer.data, status=status.HTTP_200_OK)