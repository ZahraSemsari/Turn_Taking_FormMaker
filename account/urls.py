from . import views
from django.urls import path
from .views import MyTokenObtainPairView

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('', views.Home),
    path('api/token/',MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/',TokenRefreshView.as_view(), name='token_refresh'),
    path('my-protected-endpoint/', views.MyProtectedRoute),
#   #معمولاً با توکن JWT کار می‌کنه و اطلاعات همان کاربری که توکن متعلق به اوست را برمی‌گرداند.
    path('me/', views.GetUserInfo),
]