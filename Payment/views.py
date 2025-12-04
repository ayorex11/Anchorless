from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from drf_yasg.utils import swagger_auto_schema
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Payment
from .serializers import PaymentSerializer, PaymentFilterSerializer, PaymentSummaryFilterSerializer
from Loan.models import Loan
from DebtPlan.models import DebtPlan
from Loan.utils.services import record_payment
from django.db.models import Sum, Count

@swagger_auto_schema(methods=['POST'],request_body=PaymentSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@transaction.atomic
def create_payment(request):
    user = request.user
    
    # Validate input data
    serializer = PaymentSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(
            serializer.errors, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    validated_data = serializer.validated_data
    loan_id = validated_data['loan'].id
    debt_plan_id = validated_data['debt_plan'].id
    amount = validated_data['amount']
    payment_date = validated_data['payment_date']
    payment_method = validated_data.get('payment_method', 'bank_transfer')
    notes = validated_data.get('notes', '')
    confirmation_number = validated_data.get('confirmation_number', '')
    month_number = validated_data.get('month_number', None)
    
    try:
        # Use select_for_update to lock the records
        loan = Loan.objects.select_for_update().get(id=loan_id, user=user)
        debt_plan = DebtPlan.objects.select_for_update().get(id=debt_plan_id, user=user)
    except Loan.DoesNotExist:
        return Response(
            {'error': 'Loan not found or does not belong to you'},
            status=status.HTTP_404_NOT_FOUND
        )
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found or does not belong to you'},
            status=status.HTTP_404_NOT_FOUND
        )
    

    if loan.debt_plan_id != debt_plan.id:
        return Response(
            {'error': 'Loan does not belong to the specified debt plan'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        payment, was_recalculated = record_payment(
            debt_plan=debt_plan,
            loan=loan,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            notes=notes,
            confirmation_number=confirmation_number,
            month_number=month_number
        )
        
        # Serialize the response
        response_serializer = PaymentSerializer(payment)
        response_data = response_serializer.data
        
        # Add metadata about what happened
        response_data['schedule_recalculated'] = was_recalculated
        response_data['message'] = (
            'Payment recorded successfully. Schedule was recalculated.' 
            if was_recalculated 
            else 'Payment recorded successfully.'
        )
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except DjangoValidationError as e:
        # Business logic validation errors
        error_message = str(e)
        
        # Handle ValidationError dict format
        if hasattr(e, 'error_dict'):
            error_message = '; '.join([
                f"{field}: {', '.join(errors)}" 
                for field, errors in e.error_dict.items()
            ])
        
        return Response(
            {'error': error_message},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    except Exception as e:
        # Unexpected errors
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error recording payment: {str(e)}", exc_info=True)
        
        return Response(
            {'error': f'Failed to record payment: An unexpected error occurred. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



@swagger_auto_schema(methods=['GET'], query_serializer=PaymentFilterSerializer)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def list_payments(request):
    """List all payments for the authenticated user with optional filtering"""
    user = request.user
    

    loan_id = request.query_params.get('loan')
    debt_plan_id = request.query_params.get('debt_plan')
    payment_method = request.query_params.get('payment_method')
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    payments = Payment.objects.filter(loan__user=user)
    
    if loan_id:
        payments = payments.filter(loan_id=loan_id)
    
    if debt_plan_id:
        payments = payments.filter(debt_plan_id=debt_plan_id)
    
    if payment_method:
        payments = payments.filter(payment_method=payment_method)
    
    if start_date:
        payments = payments.filter(payment_date__gte=start_date)
    
    if end_date:
        payments = payments.filter(payment_date__lte=end_date)
    
    
    payments = payments.order_by('-payment_date', '-created_at')
    
    serializer = PaymentSerializer(payments, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['GET'], query_serializer=PaymentSummaryFilterSerializer)
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@api_view(['GET'])
def payment_summary_by_method(request):
    """Get summary of payments grouped by payment method"""
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    payments = Payment.objects.filter(loan__user=user)
    
    if debt_plan_id:
        payments = payments.filter(debt_plan_id=debt_plan_id)
    
    summary = payments.values('payment_method').annotate(
        total_amount=Sum('amount'),
        payment_count=Count('id')
    ).order_by('-total_amount')
    
    for item in summary:
        item['payment_method_display'] = dict(Payment.PAYMENT_METHOD_CHOICES).get(
            item['payment_method'], 
            item['payment_method']
        )
    
    return Response(summary, status=status.HTTP_200_OK)