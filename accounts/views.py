# from django.shortcuts import render
# from rest_framework.response import Response
# from rest_framework.decorators import api_view , permission_classes
# from rest_framework.permissions import IsAuthenticated
#
# from django.contrib.auth import get_user_model
# from .serializers import UserSerializer
# from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
# from rest_framework_simplejwt.views import TokenObtainPairView
#
# @api_view(['GET'])
# def Home(request):
#     return Response("Welcome back!")
# # Create your views here.
# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def MyProtectedRoute(request):
#     return Response("Welcome back!")

#--------------------------------------------------

from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from .serializers import UserSerializer, EmailOrUsernameOrMobileTokenObtainPairSerializer, RegisterSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

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

    # def post(self, request, *args, **kwargs):
    #     try:
    #         return super().post(request, *args, **kwargs)
    #     except TokenError as e:
    #         raise InvalidToken(e.args[0])

#-----------------------------------------------------
#make view for sign up
#
# def get_tokens_for_user(user):
#     refresh = RefreshToken.for_user(user)
#     return {
#         "refresh": str(refresh),
#         "access": str(refresh.access_token),
#     }

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):

    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        if user.email:
            email_address, created = EmailAddress.objects.get_or_create(
                user=user,
                email=user.email,
                defaults={"primary": True},
            )
            if not email_address.verified:
                email_address.send_confirmation(request , signup=False)
        
        #--------------compelete-profile---------------------------
        user_data = UserSerializer(user).data
        user_data["profile_incomplete"] = (
            not user.mobile or not user.has_usable_password()
        )

        return Response(user_data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # tokens = get_tokens_for_user(user)
        #
        # user_data = UserSerializer(user).data
        #
        # return Response(
        #     {
        #         "user": user_data,
        #         "access": tokens["access"],
        #         "refresh": tokens["refresh"],
        #     },
        #     status=status.HTTP_201_CREATED,
        # )

#---------------------------------login with google!!!----------------------------------------------

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.conf import settings

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
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

class PasswordResetConfirmEchoView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, uidb64, token, *args, **kwargs):
        return Response(
            {"uid": uidb64, "token": token},
            status=status.HTTP_200_OK
        )

#-----------------------password reset with mobile and switch-------------------------------------------------------
def send_sms(mobile, text):
    print(f"[SMS to {mobile}] {text}")

from dj_rest_auth.serializers import PasswordResetSerializer
from django.utils import timezone
from .models import PhoneResetOTP


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
                ser = PasswordResetSerializer(data={"email": user.email}, context={"request": request})
                ser.is_valid(raise_exception=True)
                ser.save()
            return Response(email_response, status=status.HTTP_200_OK)


        if id_type == "mobile":
            user = User.objects.filter(mobile=identifier).first()
            if not user:
                return Response(sms_response, status=status.HTTP_200_OK)

            if user.email:
                ser = PasswordResetSerializer(data={"email": user.email}, context={"request": request})
                ser.is_valid(raise_exception=True)
                ser.save()
                return Response(email_response, status=status.HTTP_200_OK)


            otp = PhoneResetOTP.create_otp(mobile=user.mobile, minutes=5)
            send_sms(user.mobile, f"code: {otp.code} (credit value up to 2 minutes)")
            return Response(sms_response, status=status.HTTP_200_OK)

        user = User.objects.filter(username__iexact=identifier).first()
        if not user:
            return Response(email_response, status=status.HTTP_200_OK)

        if user.email:
            ser = PasswordResetSerializer(data={"email": user.email}, context={"request": request})
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(email_response, status=status.HTTP_200_OK)

        if getattr(user, "mobile", None):
            otp = PhoneResetOTP.create_otp(mobile=user.mobile, minutes=5)
            send_sms(user.mobile, f"code: {otp.code} (credit value up to 2 minutes)")
            return Response(sms_response, status=status.HTTP_200_OK)

        return Response(email_response, status=status.HTTP_200_OK)

class PasswordResetOTPConfirmView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        mobile = (request.data.get("mobile") or "").strip()
        code = (request.data.get("code") or "").strip()
        new_password = request.data.get("new_password")

        if not mobile or not code or not new_password:
            return Response({"detail": "mobile, code, new_password are required"},
                            status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(mobile=mobile).first()
        if not user:
            return Response({"detail": "invalid code"}, status=status.HTTP_400_BAD_REQUEST)

        otp = PhoneResetOTP.objects.filter(
            mobile=mobile,
            code=code,
            is_used=False,
            expires_at__gt=timezone.now()
        ).order_by("-created_at").first()

        if not otp:
            return Response({"detail": "invalid code"}, status=status.HTTP_400_BAD_REQUEST)

        otp.is_used = True
        otp.save(update_fields=["is_used"])

        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response({"detail": "password changed"}, status=status.HTTP_200_OK)


#---------------------compelete-profile-------------------------------
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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
