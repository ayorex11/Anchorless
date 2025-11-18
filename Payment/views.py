from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from django.utils import timezone
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser
from .models import Payment
from .serializers import PaymentSerializer
from Loan.models import Loan
from DebtPlan.models import DebtPlan

@swagger_auto_schema(methods=['POST'], request_body=PaymentSerializer)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])

def log_payment(request):
    """
    Log a payment made by the authenticated user.
    """
    user = request.user

    serializer = PaymentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    validated_data = serializer.validated_data
    loan = validated_data.get('loan')
    debt_plan = validated_data.get('debt_plan')
    amount = validated_data.get('amount')
    payment_date = validated_data.get('payment_date', timezone.now().date())

    debt_plan_check = DebtPlan.objects.get(user=user, id=debt_plan.id)
    if not debt_plan_check:
        return Response({"detail": "Debt plan does not belong to the user."}, status=status.HTTP_400_BAD_REQUEST)
    loan_check = Loan.objects.get(user=user, debt_plan=debt_plan, id=loan.id)
    if not loan_check:
        return Response({"detail": "Loan does not belong to the user or is not part of the specified debt plan."}, status=status.HTTP_400_BAD_REQUEST)
    minimum_payment = loan_check.minimum_payment
    if amount > minimum_payment:
        

    
