from rest_framework.permissions import AllowAny
from .serializers import UserSerializer, EmailOrUsernameOrMobileTokenObtainPairSerializer, RegisterSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from dj_rest_auth.serializers import PasswordResetSerializer
from .models import PhoneOTP
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import requests
from django.conf import settings
from django.utils import timezone

User = get_user_model()

@api_view(['GET'])
def Home(request):
    return Response("Hello world")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def MyProtectedRoute(request):
    return Response(
        {"detail" : "You are logged in", "user" : UserSerializer(request.user).data},
    )
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def GetUserInfo(request):
    user = request.user
    user_serializer = UserSerializer(user)
    return Response(user_serializer.data)

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailOrUsernameOrMobileTokenObtainPairSerializer

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """
    Register a user AFTER successful OTP verification.
    Expected body:
      {
        "username": "...",
        "mobile": "09xxxxxxxxx",
        "password": "...",
        "otp_code": "123456",
        "email": "optional@mail.com"
      }
    """

    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()

    # If email provided, create EmailAddress and send confirmation (if not verified)
    if user.email:
        email_address, created = EmailAddress.objects.get_or_create(
            user=user,
            email=user.email,
            defaults={"primary": True},
        )
        if not email_address.verified:
            email_address.send_confirmation(request, signup=False)

    # Profile completeness hint
    user_data = UserSerializer(user).data
    user_data["profile_incomplete"] = (not user.mobile or not user.has_usable_password())

    return Response(user_data, status=status.HTTP_201_CREATED)

#---------------------------------login with google!!!----------------------------------------------


class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter

    def get_response(self):
        response = super().get_response()

        user = self.user

        #--------------compelete-profile---------------------------
        response.data["profile_incomplete"] = (
            not user.mobile or not user.has_usable_password()
        )

        return response
    
    # client_class = OAuth2Client
    # callback_url = "http://localhost:8000/"


def detect_identifier_type(identifier: str) -> str:
    identifier = (identifier or "").strip()
    if "@" in identifier:
        return "email"
    if identifier.isdigit() and len(identifier) == 11 and identifier.startswith("09"):
        return "mobile"
    return "username"

#-------------------------------just with email password reset--------------------------------------------------------


class PasswordResetConfirmEchoView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, uidb64, token, *args, **kwargs):
        return Response(
            {"uid": uidb64, "token": token},
            status=status.HTTP_200_OK
        )

#------------------------------------------reset password-----------------------------------------------------
class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        identifier = (request.data.get("identifier") or "").strip()
        if not identifier:
            return Response({"identifier": "required"}, status=status.HTTP_400_BAD_REQUEST)

        id_type = detect_identifier_type(identifier)

        email_response = {"method": "email", "detail": "if there is account , email has sent"}
        sms_response = {"method": "sms", "detail": "if there is account , code has sent"}

        if id_type == "email":
            user = User.objects.filter(email__iexact=identifier).first()
            if user:
                ser = PasswordResetSerializer(
                    data={"email": user.email},
                    context={"request": request}
                )
                ser.is_valid(raise_exception=True)
                ser.save()
            return Response(email_response, status=status.HTTP_200_OK)

        if id_type == "mobile":
            user = User.objects.filter(mobile=identifier).first()
            if not user:
                return Response(sms_response, status=status.HTTP_200_OK)

            try:
                code = PhoneOTP.request_otp(
                    mobile=user.mobile,
                    purpose=PhoneOTP.Purpose.RESET_PASSWORD,
                    minutes=2,
                    cooldown_seconds=60,
                    max_attempts=5,
                    lock_minutes=10,
                )
            except ValueError as e:
                msg = str(e)


                if msg.startswith("locked:"):
                    seconds = int(msg.split(":")[1])
                    return Response(
                        {"detail": f"too many attempts, try again in {seconds}s"},
                        status=429
                    )

                if msg.startswith("cooldown:"):
                    seconds = int(msg.split(":")[1])
                    return Response(
                        {"detail": f"please wait {seconds}s before requesting again"},
                        status=429
                    )

                return Response({"detail": "cannot send code"}, status=400)

            send_sms(user.mobile, f"code : {code}")
            return Response(sms_response, status=status.HTTP_200_OK)

        user = User.objects.filter(username__iexact=identifier).first()
        if not user:
            return Response(email_response, status=status.HTTP_200_OK)

        if user.email:
            ser = PasswordResetSerializer(
                data={"email": user.email},
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(email_response, status=status.HTTP_200_OK)

        if getattr(user, "mobile", None):
            try:
                code = PhoneOTP.request_otp(
                    mobile=user.mobile,
                    purpose=PhoneOTP.Purpose.RESET_PASSWORD,
                    minutes=5,
                    cooldown_seconds=60,
                    max_attempts=5,
                    lock_minutes=10,
                )
            except ValueError as e:
                msg = str(e)
                if msg.startswith("locked:"):
                    seconds = int(msg.split(":")[1])
                    return Response(
                        {"detail": f"too many attempts, try again in {seconds}s"},
                        status=429
                    )
                if msg.startswith("cooldown:"):
                    seconds = int(msg.split(":")[1])
                    return Response(
                        {"detail": f"please wait {seconds}s before requesting again"},
                        status=429
                    )
                return Response({"detail": "cannot send code"}, status=400)

            send_sms(user.mobile, f"code : {code}")
            return Response(sms_response, status=status.HTTP_200_OK)

        return Response(email_response, status=status.HTTP_200_OK)

class PasswordResetOTPConfirmView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # Extract required fields from request body
        mobile = (request.data.get("mobile") or "").strip()
        code = (request.data.get("code") or "").strip()
        new_password = request.data.get("new_password")

        # Validate required fields
        if not mobile or not code or not new_password:
            return Response(
                {"detail": "mobile, code and new_password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user exists (avoid revealing user existence explicitly)
        user = User.objects.filter(mobile=mobile).first()
        if not user:
            return Response(
                {"detail": "Invalid or expired verification code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify OTP (hashed comparison + expiration + attempts + lockout handled inside model)
        is_valid = PhoneOTP.verify_otp(
            mobile=mobile,
            purpose=PhoneOTP.Purpose.RESET_PASSWORD,
            code=code,
            max_attempts=5,
            lock_minutes=10,
        )

        if not is_valid:
            return Response(
                {"detail": "Invalid or expired verification code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update user's password
        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response(
            {"detail": "Password has been successfully updated."},
            status=status.HTTP_200_OK,
        )


#---------------------compelete-profile-------------------------------


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def complete_profile(request):
    user = request.user

    # موبایل (اجباری)
    mobile = request.data.get("mobile")
    if not mobile and not user.mobile:
        return Response({"mobile": "Mobile is required"}, status=400)
    if mobile:
        if not mobile.isdigit() or len(mobile) != 11:
            return Response({"mobile": "Mobile must be 11 digits"}, status=400)
        user.mobile = mobile

    # رمز (اجباری اگر قبلاً رمز نداشته)
    password = request.data.get("password")
    if not password and not user.has_usable_password():
        return Response({"password": "Password is required"}, status=400)
    if password:
        if len(password) < 8:
            return Response({"password": "Password must be at least 8 chars"}, status=400)
        user.set_password(password)

    # نام و نام خانوادگی (اختیاری)
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")
    if first_name:
        user.first_name = first_name
    if last_name:
        user.last_name = last_name

    user.save()

    return Response({
        "detail": "Profile updated successfully",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "mobile": user.mobile,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "profile_incomplete": (not user.mobile or not user.has_usable_password())
        }
    })




def send_sms(mobile: str, text: str):
    """
    If SMS_API_KEY not set, fallback to print (dev).
    Replace request details once panel docs are available.
    """
    api_key = getattr(settings, "SMS_API_KEY", "")
    base = getattr(settings, "SMS_API_BASE_URL", "")
    if not api_key or not base:
        print(f"[SMS to {mobile}] {text}")
        return

    # TODO: Replace with real provider endpoint/payload:
    url = f"{base}/api/send"
    payload = {
        "to": mobile,
        "message": text,
        "sender": getattr(settings, "SMS_SENDER", ""),
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()


class SignupOTPRequestView(APIView):
    """
    Request an OTP for signup (mobile verification).
    Body:
      { "mobile": "09xxxxxxxxx" }
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        mobile = (request.data.get("mobile") or "").strip()

        # Basic mobile validation
        if not mobile:
            return Response({"detail": "mobile is required."}, status=status.HTTP_400_BAD_REQUEST)
        if (not mobile.isdigit()) or len(mobile) != 11 or (not mobile.startswith("09")):
            return Response({"detail": "mobile must be 11 digits and start with '09'."}, status=status.HTTP_400_BAD_REQUEST)

        # If a user already exists with this mobile, do NOT send OTP (avoid wasting SMS)
        if User.objects.filter(mobile=mobile).exists():
            return Response({"detail": "This mobile number is already registered."}, status=status.HTTP_400_BAD_REQUEST)

        # Create OTP with rate limit + lockout rules inside model
        try:
            code = PhoneOTP.request_otp(
                mobile=mobile,
                purpose=PhoneOTP.Purpose.SIGNUP,
                minutes=5,
                cooldown_seconds=60,
                max_attempts=5,
                lock_minutes=10,
            )
        except ValueError as e:
            msg = str(e)

            # Locked due to too many failed attempts
            if msg.startswith("locked:"):
                seconds = int(msg.split(":")[1])
                return Response(
                    {"detail": f"Too many attempts. Try again in {seconds} seconds."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            # Cooldown rate limit
            if msg.startswith("cooldown:"):
                seconds = int(msg.split(":")[1])
                return Response(
                    {"detail": f"Please wait {seconds} seconds before requesting a new code."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            return Response({"detail": "Unable to send verification code."}, status=status.HTTP_400_BAD_REQUEST)

        # Send SMS (your send_sms supports fallback to print)
        send_sms(mobile, f"Your verification code is: {code}")

        return Response({"detail": "Verification code sent."}, status=status.HTTP_200_OK)