from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser
from drf_yasg.utils import swagger_auto_schema

from .models import DebtPlan
from .serializers import DebtPlanSerializer, UpdateDebtPlanSerializer
from Loan.models import Loan
from Loan.utils.services import generate_payment_schedule


@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def list_debt_plans(request):
    """List all debt plans for the authenticated user"""
    user = request.user
    debt_plans = DebtPlan.objects.filter(user=user).order_by('-created_at')
    serializer = DebtPlanSerializer(debt_plans, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['POST'], request_body=DebtPlanSerializer)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['POST'])
@transaction.atomic
def create_debt_plan(request):
    """Create a new debt plan"""
    user = request.user
    
    # Check for existing active plan
    if DebtPlan.objects.filter(user=user, is_active=True).exists():
        return Response(
            {'error': 'You can only have one active debt plan at a time. Please complete or deactivate your current plan first.'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = DebtPlanSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    strategy = validated_data['strategy']
    name = validated_data.get('name', 'My Debt Freedom Plan')
    monthly_payment_budget = validated_data['monthly_payment_budget']
    
    # Additional validation
    if monthly_payment_budget <= 0:
        return Response(
            {'monthly_payment_budget': 'Monthly payment budget must be positive'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create debt plan
    debt_plan = DebtPlan.objects.create(
        strategy=strategy,
        user=user,
        name=name,
        monthly_payment_budget=monthly_payment_budget,
        projected_payoff_date=None,
        total_interest_saved=None,
        is_active=False  # Will be activated when first loan is added
    )
    
    response_serializer = DebtPlanSerializer(debt_plan)
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def get_debt_plan(request, plan_id):
    """Get a specific debt plan"""
    user = request.user
    
    try:
        debt_plan = DebtPlan.objects.get(user=user, id=plan_id)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid plan ID format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = DebtPlanSerializer(debt_plan)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['PATCH'], request_body=UpdateDebtPlanSerializer)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@parser_classes([FormParser, MultiPartParser])
@permission_classes([IsAuthenticated])
@api_view(['PATCH'])
@transaction.atomic
def update_debt_plan(request, plan_id):
    """Update an existing debt plan"""
    user = request.user
    
    try: 
        debt_plan = DebtPlan.objects.get(id=plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid plan ID format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = UpdateDebtPlanSerializer(
        debt_plan, 
        data=request.data, 
        partial=True,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Save the updated plan
    updated_plan = serializer.save()
    
    # Regenerate schedule if plan has loans
    loans = Loan.objects.filter(debt_plan=debt_plan, user=user)
    if loans.exists():
        try:
            generate_payment_schedule(debt_plan)
        except DjangoValidationError as e:
            return Response(
                {'error': f'Failed to regenerate schedule: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    response_serializer = DebtPlanSerializer(updated_plan)
    return Response(response_serializer.data, status=status.HTTP_200_OK)