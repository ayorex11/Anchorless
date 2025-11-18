from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from django.utils import timezone
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser
from .models import Loan
from DebtPlan.models import DebtPlan
from .serializers import LoanSerializer
from .utils.services import recalculate_all_payoff_orders

@swagger_auto_schema(methods=['POST'], request_body=LoanSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
def create_loan(request):
    user = request.user
    serializer = LoanSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    debt_plan = validated_data.get('debt_plan')
    
    # Create the loan without payoff_order first
    loan = Loan.objects.create(
        user=user,
        debt_plan=debt_plan,
        name=validated_data['name'],
        principal_balance=validated_data['principal_balance'],
        interest_rate=validated_data['interest_rate'],
        minimum_payment=validated_data.get('minimum_payment'),
        due_date=validated_data.get('due_date', 1),
        remaining_balance=validated_data['principal_balance'],
        manually_set_minimum_payment=validated_data.get('manually_set_minimum_payment', False),
        payoff_order=None 
    )
    
    if debt_plan:
        recalculate_all_payoff_orders(debt_plan)
    
    response_serializer = LoanSerializer(loan)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)
