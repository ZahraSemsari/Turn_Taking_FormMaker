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

User = get_user_model()

@api_view(['GET'])
def Home(request):
    return Response("Hello world")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def MyProtectedRoute(request):
    return Response("You have been granted access to my protected route")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def GetUserInfo(request):
    user = request.user
    user_serializer = UserSerializer(user)
    return Response(user_serializer.data)

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailOrUsernameOrMobileTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except TokenError as e:
            raise InvalidToken(e.args[0])

#-----------------------------------------------------
#make view for sign up

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):

    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        # اگر ورودی‌ها اشتباه باشن (یا ایمیل/موبایل تکراری باشه) خطای 400 برمی‌گردونیم
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    tokens = get_tokens_for_user(user)

    user_data = UserSerializer(user).data

    return Response(
        {
            "user": user_data,
            "access": tokens["access"],
            "refresh": tokens["refresh"],
        },
        status=status.HTTP_201_CREATED,
    )


#---------------------------------login with google!!!----------------------------------------------

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.conf import settings

class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    callback_url = "http://localhost:8000/"



