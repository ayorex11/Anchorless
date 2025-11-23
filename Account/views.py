from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, throttle_classes 
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from .models import CustomUser, VerificationToken, PasswordResetToken
from .serializers import (
    UserRegistrationSerializer, 
    UserLoginSerializer, 
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    LogoutSerializer,
    EmailResendSerializer
)
from django.core.mail import send_mail
from django.conf import settings
from drf_yasg.utils import swagger_auto_schema
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

@swagger_auto_schema(methods=['POST'], request_body=UserRegistrationSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.AllowAny])
def register(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        
        expires_at = timezone.now() + timedelta(hours=24)
        verification_token = VerificationToken.objects.create(
            user=user,
            expires_at=expires_at
        )
        
        # Send verification email
        verification_url = f"http://localhost:5173/verify-email/{verification_token.token}/"
        send_mail(
            'Verify Your Account',
            f"""
            Hello {user.email},
            Welcome to Anchorless! Please verify your email address to complete your registration.
            Click the link to verify your account: {verification_url}
            Thank you for joining us!
            """,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        
        return Response({
            "message": "User registered successfully. Please check your email for verification.",
            "user": {
                "email": user.email,
                "first_name": user.first_name
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(methods=['POST'], request_body=UserLoginSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.AllowAny])
def login(request):
    serializer = UserLoginSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        user = authenticate(request, email=email, password=password)
        
        if user is not None:
            if not user.is_verified:
                return Response(
                    {"error": "Please verify your email before logging in."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            refresh = RefreshToken.for_user(user)
            
            return Response({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "access_expires": refresh.access_token.payload['exp'],
                "refresh_expires": refresh.payload['exp'],
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(methods=['POST'], request_body=LogoutSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    serializer = LogoutSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    validated_data = serializer.validated_data
    try:
        refresh_token = validated_data['refresh']
        token = RefreshToken(refresh_token)
        token.blacklist()
        
        return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.AllowAny])
def verify_email(request, token):
    try:
        verification_token = VerificationToken.objects.get(token=token)
        
        if verification_token.is_expired():
            return Response(
                {"error": "Verification token has expired"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = verification_token.user
        user.is_verified = True
        user.save()
        
        # Delete the used token
        verification_token.delete()
        
        return Response({"message": "Email verified successfully"}, status=status.HTTP_200_OK)
    
    except VerificationToken.DoesNotExist:
        return Response(
            {"error": "Invalid verification token"},
            status=status.HTTP_400_BAD_REQUEST
        )


@swagger_auto_schema(methods=['POST'], request_body=ForgotPasswordSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.AllowAny])
def forgot_password(request):
    serializer = ForgotPasswordSerializer(data=request.data)
    if serializer.is_valid():
        email = serializer.validated_data['email']
        
        try:
            user = CustomUser.objects.get(email=email)
            expires_at = timezone.now() + timedelta(hours=1)
            
            # Delete any existing reset tokens for this user
            PasswordResetToken.objects.filter(user=user).delete()
            
            # Create new reset token
            reset_token = PasswordResetToken.objects.create(
                user=user,
                expires_at=expires_at
            )
            
            # Send reset email
            reset_url = f"http://localhost:5173/reset-password/{reset_token.token}/"
            send_mail(
                'Reset Your Password',
                f"""
                Hello {user.email},
                We received a request to reset your password.
                If you did not make this request, please ignore this email.
                Click the link to reset your password: {reset_url}
                Thank you.
                """,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            
            return Response({
                "message": "Password reset email sent successfully"
            }, status=status.HTTP_200_OK)
        
        except CustomUser.DoesNotExist:
            # Don't reveal whether email exists or not
            return Response({
                "message": "If the email exists, a reset link has been sent"
            }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(methods=['POST'], request_body=ResetPasswordSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.AllowAny])
def reset_password(request):
    serializer = ResetPasswordSerializer(data=request.data)
    if serializer.is_valid():
        token = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']
        
        try:
            reset_token = PasswordResetToken.objects.get(token=token)
            
            if reset_token.is_expired():
                return Response(
                    {"error": "Password reset token has expired"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user = reset_token.user
            user.set_password(new_password)
            user.save()
            
            # Delete the used token
            reset_token.delete()
            
            # Blacklist all existing tokens for this user
            tokens = OutstandingToken.objects.filter(user=user)
            for token in tokens:
                BlacklistedToken.objects.get_or_create(token=token)
            
            return Response({
                "message": "Password reset successfully"
            }, status=status.HTTP_200_OK)
        
        except PasswordResetToken.DoesNotExist:
            return Response(
                {"error": "Invalid reset token"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@swagger_auto_schema(methods=['POST'], request_body=ChangePasswordSerializer)
@api_view(['POST'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    if serializer.is_valid():
        user = request.user
        
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {"error": "Current password is incorrect"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Blacklist all existing tokens
        tokens = OutstandingToken.objects.filter(user=user)
        for token in tokens:
            BlacklistedToken.objects.get_or_create(token=token)
        
        # Generate new tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            "message": "Password changed successfully",
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@throttle_classes([UserRateThrottle, AnonRateThrottle])
@permission_classes([permissions.IsAuthenticated])
def profile(request):
    user = request.user
    return Response({
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_verified": user.is_verified,
        "created_at": user.created_at,
        "updated_at": user.updated_at
    }, status=status.HTTP_200_OK)


@swagger_auto_schema(methods=['POST'], request_body=EmailResendSerializer)
@api_view(['POST'])
@throttle_classes([AnonRateThrottle]) 
@permission_classes([permissions.AllowAny])
def resend_verification_email(request):
    """
    Resend verification email to unverified users
    """
    serializer = EmailResendSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors)
    validated_data = serializer.validated_data
    email = validated_data['email']
    
    if not email:
        return Response(
            {"error": "Email is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        user = CustomUser.objects.get(email=email)
        
        # Check if user is already verified
        if user.is_verified:
            return Response(
                {"error": "Email is already verified"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check for existing non-expired token
        existing_token = VerificationToken.objects.filter(user=user).first()
        
        if existing_token:
            # Check if the existing token was created recently (within last 5 minutes)
            time_since_creation = timezone.now() - existing_token.created_at
            if time_since_creation < timedelta(minutes=5):
                remaining_seconds = (timedelta(minutes=5) - time_since_creation).seconds
                return Response(
                    {
                        "error": f"Please wait {remaining_seconds} seconds before requesting another verification email"
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            
            # Delete old token if it exists
            existing_token.delete()
        
        # Create new verification token
        expires_at = timezone.now() + timedelta(hours=24)
        verification_token = VerificationToken.objects.create(
            user=user,
            expires_at=expires_at
        )
        
        # Send verification email
        verification_url = f"http://localhost:5173/verify-email/{verification_token.token}/"
        
        try:
            send_mail(
                'Verify Your Account - Anchorless',
                f"""
Hello {user.first_name or user.email},

Thank you for registering with Anchorless!

Please verify your email address to complete your registration and start managing your debt freedom journey.

Click the link below to verify your account:
{verification_url}

This link will expire in 24 hours.

If you didn't create an account with Anchorless, please ignore this email.

Best regards,
The Anchorless Team
                """,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            
            return Response({
                "message": "Verification email sent successfully. Please check your inbox."
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            # Log the error but don't expose details to user
            print(f"Email sending failed: {str(e)}")
            return Response(
                {"error": "Failed to send verification email. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    except CustomUser.DoesNotExist:
        # Don't reveal whether email exists or not for security
        return Response({
            "message": "If an unverified account exists with this email, a verification link has been sent."
        }, status=status.HTTP_200_OK)