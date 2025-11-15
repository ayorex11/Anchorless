from .models import DebtPlan
from .serializers import DebtPlanSerializer
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from django.utils import timezone
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser

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
