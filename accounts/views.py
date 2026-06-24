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
import logging
from time import sleep
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
import re

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
            try:
                email_address.send_confirmation(request, signup=False)
            except Exception as e:
                logger.error("Email confirmation failed for user %s: %s", user.id, str(e))

    # Profile completeness hint
    user_data = UserSerializer(user).data
    user_data["profile_incomplete"] = (
            not user.username
            or not user.mobile
            or not user.has_usable_password()
    )

    return Response(user_data, status=status.HTTP_201_CREATED)

#---------------------------------login with google!!!----------------------------------------------


class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter

    def get_response(self):
        response = super().get_response()

        user = self.user

        #--------------compelete-profile---------------------------
        response.data["profile_incomplete"] = (
                not user.username
                or not user.mobile
                or not user.has_usable_password()
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

            send_sms(user.mobile, code)
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

            send_sms(user.mobile, code)
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
    username = request.data.get("username", None)

    if username is None:
        if not user.username:
            return Response({"username": "Username is required"}, status=400)
    else:
        if not isinstance(username, str):
            return Response({"username": "Username must be a string."}, status=400)

        username = username.strip()

        if not username:
            return Response({"username": "Username is required"}, status=400)

        if len(username) > 150:
            return Response({"username": "Username must be less than 150 characters"}, status=400)

        if not re.match(r'^[\w.+-]+$', username):
            return Response(
                {"username": "Username may contain only letters, numbers, and ./+/-/_ characters."},
                status=400
            )

        if User.objects.exclude(id=user.id).filter(username__iexact=username).exists():
            return Response({"username": "Username already exists"}, status=400)

        user.username = username

    # موبایل (اجباری)
    mobile = request.data.get("mobile")
    if not mobile and not user.mobile:
        return Response({"mobile": "Mobile is required"}, status=400)
    if mobile:
        if not mobile.isdigit() or len(mobile) != 11:
            return Response({"mobile": "Mobile must be 11 digits"}, status=400)
        if User.objects.exclude(id=user.id).filter(mobile=mobile).exists():
            return Response(
                {"mobile": "Mobile already in use"},
                status=400
            )
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
            "profile_incomplete": (
                not user.username
                or not user.mobile
                or not user.has_usable_password()
            )
        }
    })




logger = logging.getLogger(__name__)


def format_mobile_e164(mobile: str) -> str:
    """
    Convert Iranian mobile to E.164 format.
    09123456789 -> +989123456789
    """
    mobile = mobile.strip()

    if mobile.startswith("09"):
        return "+98" + mobile[1:]

    if mobile.startswith("989"):
        return "+" + mobile

    if mobile.startswith("+989"):
        return mobile

    raise ValueError("Invalid mobile format")

def send_sms(mobile: str, otp_code: str, retries: int = 2):
    import requests
    import logging
    from time import sleep
    from django.conf import settings

    logger = logging.getLogger(__name__)

    api_key = settings.SMS_API_KEY
    base_url = "https://edge.ippanel.com/v1/api/send"
    sender = settings.SMS_SENDER
    pattern_code = settings.SMS_PATTERN_OTP

    clean_mobile = mobile.replace("+98", "0") if mobile.startswith("+98") else mobile
    clean_mobile = "+98" + clean_mobile.lstrip("0")

    payload = {
        "sending_type": "pattern",
        "from_number": sender,
        "code": pattern_code,
        "recipients": [clean_mobile],
        "params": {
            "code": otp_code
        }
    }

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    for _ in range(retries):
        try:
            response = requests.post(
                base_url,
                json=payload,
                headers=headers,
                timeout=10
            )
        except requests.RequestException as e:
            logger.error("SMS sending failed: %s", str(e))
            sleep(1)
            continue

        print(f"IPPanel Response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            return True

        if response.status_code == 422:
            logger.error("Invalid pattern or params: %s", response.text)
            break

        sleep(1)

    return False




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

        try:
            sms_status = send_sms(mobile, code)
        except Exception as e:
            logger.error("SMS sending crashed: %s", str(e))
            return Response(
                {"detail": "Failed to send SMS. Please check server logs."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if sms_status:
            return Response({"detail": "Verification code sent."}, status=status.HTTP_200_OK)
        else:
            return Response(
                {"detail": "Failed to send SMS. Please check server logs."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

#-----------------------logout-------------------------

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response(
                {"refresh": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {"detail": "Logout successful."},
            status=status.HTTP_200_OK
        )
