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
from rest_framework.permissions import IsAuthenticated

from django.contrib.auth import get_user_model
from .serializers import UserSerializer, EmailOrUsernameTokenObtainPairSerializer

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

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
    serializer_class = EmailOrUsernameTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except TokenError as e:
            raise InvalidToken(e.args[0])

