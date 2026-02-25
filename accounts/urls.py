from . import views
from django.urls import path
from .views import MyTokenObtainPairView, SignupOTPRequestView
from .views import GoogleLogin, PasswordResetRequestView, PasswordResetOTPConfirmView , complete_profile


from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    path('', views.Home),
    path("signup/", views.register, name="signup"),
    path("google-login/", GoogleLogin.as_view(), name="google_login"),
    path('signin/',MyTokenObtainPairView.as_view(), name='signin'),
    path("password/reset/request/", PasswordResetRequestView.as_view()),
    path("password/reset/otp/confirm/", PasswordResetOTPConfirmView.as_view()),
    path('api/token/refresh/',TokenRefreshView.as_view(), name='token_refresh'),
    path('my-protected-endpoint/', views.MyProtectedRoute),
    path('profile/complete/', complete_profile, name='complete_profile'),
#   #معمولاً با توکن JWT کار می‌کنه و اطلاعات همان کاربری که توکن متعلق به اوست را برمی‌گرداند.
    path('me/', views.GetUserInfo),
    path("signup/otp/request/", SignupOTPRequestView.as_view(), name='signup-otp-request'),

]