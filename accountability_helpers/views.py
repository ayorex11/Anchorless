from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.parsers import FormParser, MultiPartParser
from drf_yasg.utils import swagger_auto_schema

from .models import PaymentPlanPDF, LetterToSelf
from .serializers import (
    PaymentPlanPDFSerializer, 
    LetterToSelfSerializer,
    DebtPlanQuerySerializer
)
from DebtPlan.models import DebtPlan
from .utils.pdf_generator import save_payment_plan_pdf


@swagger_auto_schema(
    methods=['POST'],
    query_serializer=DebtPlanQuerySerializer,
    operation_description="Generate a PDF payment plan for a debt plan"
)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@transaction.atomic
def generate_pdf(request):
    """Generate/regenerate PDF payment plan"""
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if not debt_plan_id:
        return Response(
            {'error': 'debt_plan parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        return Response(
            {'error': 'Invalid debt plan ID'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        pdf_plan = save_payment_plan_pdf(debt_plan)
        serializer = PaymentPlanPDFSerializer(pdf_plan, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response(
            {'error': f'Failed to generate PDF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@swagger_auto_schema(
    methods=['GET'],
    query_serializer=DebtPlanQuerySerializer,
    operation_description="Get PDF payment plan info for a debt plan"
)
@api_view(['GET'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
def get_pdf_info(request):
    """Get PDF payment plan information"""
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if not debt_plan_id:
        return Response(
            {'error': 'debt_plan parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
        pdf_plan = PaymentPlanPDF.objects.get(debt_plan=debt_plan)
        serializer = PaymentPlanPDFSerializer(pdf_plan, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except PaymentPlanPDF.DoesNotExist:
        return Response(
            {'error': 'PDF not generated yet. Use POST /generate/ to create one.'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
def download_pdf(request, pdf_id):
    """Download PDF file"""
    user = request.user
    
    try:
        pdf_plan = PaymentPlanPDF.objects.get(id=pdf_id, user=user)
        
        if not pdf_plan.pdf_file:
            raise Http404("PDF file not found")
        
        response = FileResponse(
            pdf_plan.pdf_file.open('rb'),
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="{pdf_plan.pdf_file.name.split("/")[-1]}"'
        return response
        
    except PaymentPlanPDF.DoesNotExist:
        raise Http404("PDF not found")



@swagger_auto_schema(
    methods=['POST'],
    request_body=LetterToSelfSerializer,
    operation_description="Create a letter to yourself to be sent when debt is paid off"
)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@parser_classes([FormParser, MultiPartParser])
@transaction.atomic
def create_letter(request):
    """Create letter to self"""
    user = request.user
    serializer = LetterToSelfSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    debt_plan = validated_data['debt_plan']
    
    # Check if letter already exists for this debt plan
    if LetterToSelf.objects.filter(debt_plan=debt_plan).exists():
        return Response(
            {'error': 'A letter already exists for this debt plan. Update it instead.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    letter = LetterToSelf.objects.create(
        user=user,
        debt_plan=debt_plan,
        subject=validated_data['subject'],
        body=validated_data['body']
    )
    
    response_serializer = LetterToSelfSerializer(letter, context={'request': request})
    return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@swagger_auto_schema(
    methods=['GET'],
    query_serializer=DebtPlanQuerySerializer,
)
@api_view(['GET'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
def get_letter(request):
    """Get letter to self for a debt plan"""
    user = request.user
    debt_plan_id = request.query_params.get('debt_plan')
    
    if not debt_plan_id:
        return Response(
            {'error': 'debt_plan parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        debt_plan = DebtPlan.objects.get(id=debt_plan_id, user=user)
        letter = LetterToSelf.objects.get(debt_plan=debt_plan)
        serializer = LetterToSelfSerializer(letter, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except DebtPlan.DoesNotExist:
        return Response(
            {'error': 'Debt plan not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except LetterToSelf.DoesNotExist:
        return Response(
            {'error': 'No letter found for this debt plan'},
            status=status.HTTP_404_NOT_FOUND
        )


@swagger_auto_schema(
    methods=['PATCH'],
    request_body=LetterToSelfSerializer,
)
@api_view(['PATCH'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@parser_classes([FormParser, MultiPartParser])
@transaction.atomic
def update_letter(request, letter_id):
    """Update letter to self"""
    user = request.user
    
    try:
        letter = LetterToSelf.objects.get(id=letter_id, user=user)
    except LetterToSelf.DoesNotExist:
        return Response(
            {'error': 'Letter not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if letter.is_sent:
        return Response(
            {'error': 'Cannot update a letter that has already been sent'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = LetterToSelfSerializer(
        letter,
        data=request.data,
        partial=True,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    updated_letter = serializer.save()
    response_serializer = LetterToSelfSerializer(updated_letter, context={'request': request})
    return Response(response_serializer.data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([IsAuthenticated])
@transaction.atomic
def delete_letter(request, letter_id):
    """Delete letter to self"""
    user = request.user
    
    try:
        letter = LetterToSelf.objects.get(id=letter_id, user=user)
    except LetterToSelf.DoesNotExist:
        return Response(
            {'error': 'Letter not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if letter.is_sent:
        return Response(
            {'error': 'Cannot delete a letter that has already been sent'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    letter.delete()
    return Response(
        {'message': 'Letter deleted successfully'},
        status=status.HTTP_200_OK
    )