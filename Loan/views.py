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
from .serializers import LoanSerializer, LoanUpdateSerializer, LoanFilterSerializer, GetLoanSerializer
from DebtPlan.models import DebtPlan
from Loan.utils.services import(
    generate_payment_schedule,
    recalculate_all_payoff_orders,
    calculate_minimum_payment,
)
from DebtPlan.models import DebtPlan


@swagger_auto_schema(methods=['POST'], request_body=LoanSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
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
    
    try:
        debt_plan = DebtPlan.objects.select_for_update().get(pk=validated_data['debt_plan'].pk)
    except DebtPlan.DoesNotExist:
        return Response({'error': 'Debt plan not found'}, status=status.HTTP_404_NOT_FOUND)

    name = validated_data['name']
    principal_balance = validated_data['principal_balance']
    interest_rate = validated_data['interest_rate']
    manually_set_minimum_payment = validated_data.get('manually_set_minimum_payment', False)
    minimum_payment = validated_data.get('minimum_payment')
    due_date = validated_data.get('due_date', 1)
    
    if not manually_set_minimum_payment or minimum_payment is None:
        try:
            minimum_payment = calculate_minimum_payment(principal_balance, interest_rate)
        except DjangoValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        current_loans = Loan.objects.filter(debt_plan=debt_plan, remaining_balance__gt=0)
        current_total_minimum = sum(loan.minimum_payment for loan in current_loans)
        new_total_minimum = current_total_minimum + minimum_payment
        

        if debt_plan.monthly_payment_budget < new_total_minimum:
            wiggle_space = debt_plan.monthly_payment_budget - current_total_minimum
            if wiggle_space > 0:
                suggestion = f"Increase your monthly budget or manually set the minimum payment for this loan to ${wiggle_space} or lower."
            else :
                suggestion = "Your budget is already fully utilized by existing loans. You must increase your monthly budget to add new debts."
            return Response({
                'error': f'Cannot add this loan. Total minimum payments (${new_total_minimum}) would exceed your monthly budget (${debt_plan.monthly_payment_budget}). {suggestion}',
                'current_minimum': str(current_total_minimum),
                'new_loan_minimum': str(minimum_payment),
                'total_needed': str(new_total_minimum),
                'current_budget': str(debt_plan.monthly_payment_budget),
                'suggestion': suggestion,
            }, status=status.HTTP_400_BAD_REQUEST)    

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
        
        if not debt_plan.is_active:
            debt_plan.is_active = True
            debt_plan.save(update_fields=['is_active'])
        
        response_serializer = LoanSerializer(loan, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
    except DjangoValidationError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response(
            {'error': f'Failed to create loan: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@swagger_auto_schema(methods=['GET'], query_serializer=LoanFilterSerializer)
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
        except Exception:
            return Response(
                {'error': 'Invalid debt plan ID format'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        # Get all user's loans
        loans = Loan.objects.filter(user=user).order_by('-created_at')
    
    serializer = GetLoanSerializer(loans, many=True, context={'request': request})
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
    
    serializer = LoanSerializer(loan, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['PATCH'], request_body=LoanUpdateSerializer)
@api_view(['PATCH'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
#_classes([FormParser, MultiPartParser])
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
    
    validated_data = serializer.validated_data
    manually_set_minimum_payment = validated_data.get('manually_set_minimum_payment', False)
    minimum_payment = validated_data.get('minimum_payment')
    principal_balance = loan.principal_balance
    interest_rate = loan.interest_rate



    if not manually_set_minimum_payment or minimum_payment is None:
        try:
            minimum_payment = calculate_minimum_payment(principal_balance, interest_rate)
        except DjangoValidationError as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
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
    
    response_serializer = LoanSerializer(updated_loan, context={'request': request})
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
            debt_plan.projected_payoff_date = None
            debt_plan.total_interest_saved = 0
            debt_plan.save(update_fields=['is_active'])
            
    
    return Response(
        {'message': f'Loan "{loan_name}" deleted successfully'}, 
        status=status.HTTP_200_OK
    )