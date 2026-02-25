from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views
from .views import (
    GoogleLogin,
    MyTokenObtainPairView,
    PasswordResetOTPConfirmView,
    PasswordResetRequestView,
    SignupOTPRequestView,
    complete_profile,
)


urlpatterns = [
    # Health / debug endpoints
    path("", views.Home, name="accounts-home"),
    path("my-protected-endpoint/", views.MyProtectedRoute, name="auth-protected-debug"),

    # Auth: signup/login/social
    path("signup/", views.register, name="auth-signup"),
    path("signup/otp/request/", SignupOTPRequestView.as_view(), name="auth-signup-otp-request"),

    path("login/", MyTokenObtainPairView.as_view(), name="auth-login"),

    path("login/google/", GoogleLogin.as_view(), name="auth-login-google"),

    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),

    # Auth: password reset
    path("password/reset/request/", PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("password/reset/otp/confirm/", PasswordResetOTPConfirmView.as_view(), name="auth-password-reset-otp-confirm"),

    # User profile
    path("me/", views.GetUserInfo, name="users-me"),
    path("profile/complete/", complete_profile, name="users-profile-complete"),
]
