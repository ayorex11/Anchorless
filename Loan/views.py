from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser
from drf_yasg.utils import swagger_auto_schema

from .models import Loan
from .serializers import LoanSerializer, LoanUpdateSerializer
from DebtPlan.models import DebtPlan
from Loan.utils.services import(
    generate_payment_schedule,
    recalculate_all_payoff_orders,
    calculate_minimum_payment,
)


def validate_minimum_payment_settings(manually_set, minimum_payment):
    """
    Validate minimum payment configuration
    Returns tuple: (is_valid, error_message)
    """
    if manually_set:
        if minimum_payment is None or minimum_payment <= 0:
            return False, 'When manually setting minimum payment, value must be positive'
    else:
        if minimum_payment is not None and minimum_payment > 0:
            return False, 'Cannot provide minimum_payment when manually_set_minimum_payment is False'
    
    return True, None


@swagger_auto_schema(methods=['POST'], request_body=LoanSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@parser_classes([FormParser, MultiPartParser])
@transaction.atomic
def create_loan(request):
    """
    Create a new loan and add it to a debt plan
    """
    user = request.user
    serializer = LoanSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    
    # Extract and validate data
    debt_plan_id = validated_data.get('debt_plan')
    name = validated_data['name']
    principal_balance = validated_data['principal_balance']
    interest_rate = validated_data['interest_rate']
    manually_set_minimum_payment = validated_data.get('manually_set_minimum_payment', False)
    minimum_payment = validated_data.get('minimum_payment')
    due_date = validated_data.get('due_date', 1)
    
    # Validate principal balance
    if principal_balance <= 0:
        return Response(
            {'principal_balance': 'Principal balance must be positive'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate interest rate
    if interest_rate < 0:
        return Response(
            {'interest_rate': 'Interest rate cannot be negative'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate minimum payment settings
    is_valid, error_msg = validate_minimum_payment_settings(
        manually_set_minimum_payment, 
        minimum_payment
    )
    if not is_valid:
        return Response(
            {'minimum_payment': error_msg}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Calculate minimum payment if not manually set
    if not manually_set_minimum_payment:
        try:
            minimum_payment = calculate_minimum_payment(principal_balance, interest_rate)
        except DjangoValidationError as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # Verify debt plan exists and belongs to user
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'debt_plan': 'Debt plan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'debt_plan': 'Invalid debt plan ID'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create the loan
    try:
        loan = Loan.objects.create(
            user=user,
            debt_plan=debt_plan,
            name=name,
            principal_balance=principal_balance,
            interest_rate=interest_rate,
            minimum_payment=minimum_payment,
            due_date=due_date,
            remaining_balance=principal_balance,
            manually_set_minimum_payment=manually_set_minimum_payment,
        )
        
        recalculate_all_payoff_orders(debt_plan)
        generate_payment_schedule(debt_plan)
        
        # Activate the debt plan
        if not debt_plan.is_active:
            debt_plan.is_active = True
            debt_plan.save(update_fields=['is_active'])
        
        # Return the created loan data
        response_serializer = LoanSerializer(loan)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
    except DjangoValidationError as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': f'Failed to create loan: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def list_loans(request):
    """List all loans for the authenticated user"""
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if debt_plan_id:
        # Filter by specific debt plan
        try:
            debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
            loans = Loan.objects.filter(debt_plan=debt_plan).order_by('payoff_order')
        except DebtPlan.DoesNotExist:
            return Response(
                {'error': 'Debt plan not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Get all user's loans
        loans = Loan.objects.filter(user=user).order_by('-created_at')
    
    serializer = LoanSerializer(loans, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def get_loan(request, loan_id):
    """Get a specific loan"""
    user = request.user
    
    try:
        loan = Loan.objects.get(id=loan_id, user=user)
    except Loan.DoesNotExist:
        return Response(
            {'error': 'Loan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid loan ID format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = LoanSerializer(loan)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema( methods=['PATCH'], request_body=LoanUpdateSerializer)
@api_view(['PATCH'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@parser_classes([FormParser, MultiPartParser])
@transaction.atomic
def update_loan(request, loan_id):
    """Update a loan"""
    user = request.user
    
    try:
        loan = Loan.objects.get(id=loan_id, user=user)
    except Loan.DoesNotExist:
        return Response(
            {'error': 'Loan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid loan ID format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = LoanUpdateSerializer(
        loan, 
        data=request.data, 
        partial=True,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    updated_loan = serializer.save()
    
    # Regenerate schedule if loan has a debt plan
    if updated_loan.debt_plan:
        try:
            recalculate_all_payoff_orders(updated_loan.debt_plan)
            generate_payment_schedule(updated_loan.debt_plan)
        except DjangoValidationError as e:
            return Response(
                {'error': f'Failed to regenerate schedule: {str(e)}'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    response_serializer = LoanSerializer(updated_loan)
    return Response(response_serializer.data, status=status.HTTP_200_OK)


@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['DELETE'])
@transaction.atomic
def delete_loan(request, loan_id):
    """Delete a loan"""
    user = request.user
    
    try:
        loan = Loan.objects.get(id=loan_id, user=user)
    except Loan.DoesNotExist:
        return Response(
            {'error': 'Loan not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid loan ID format'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    debt_plan = loan.debt_plan
    loan_name = loan.name
    
    # Delete the loan
    loan.delete()
    
    # Regenerate schedule if loan was part of a debt plan
    if debt_plan:
        remaining_loans = Loan.objects.filter(debt_plan=debt_plan, remaining_balance__gt=0)
        
        if remaining_loans.exists():
            try:
                recalculate_all_payoff_orders(debt_plan)
                generate_payment_schedule(debt_plan)
            except DjangoValidationError as e:
                return Response(
                    {'error': f'Failed to regenerate schedule: {str(e)}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # No loans left, deactivate plan
            debt_plan.is_active = False
            debt_plan.save(update_fields=['is_active'])
    
    return Response(
        {'message': f'Loan "{loan_name}" deleted successfully'}, 
        status=status.HTTP_200_OK
    )