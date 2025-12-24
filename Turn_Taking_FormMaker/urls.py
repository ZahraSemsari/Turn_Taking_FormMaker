"""
URL configuration for Turn_Taking_FormMaker project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from allauth.account.views import ConfirmEmailView
from django.contrib import admin
from django.urls import path
from django.urls import path, include
from accounts.views import PasswordResetConfirmEchoView



urlpatterns = [
    path('admin/', admin.site.urls),
    path('account/', include('accounts.urls')),
    path(
        "accounts/confirm-email/<str:key>/",
        ConfirmEmailView.as_view(),
        name="account_confirm_email",
    ),
    path("auth/registration/account-confirm-email/<str:key>/",
         ConfirmEmailView.as_view(),
         name="dj_rest_auth_account_confirm_email"),
    path("auth/", include("dj_rest_auth.urls")),
    path("auth/registration/", include("dj_rest_auth.registration.urls")),
    path("api/" , include("FormAPI.urls")),
    path(
        "accounts/reset/<uidb64>/<token>/",
        PasswordResetConfirmEchoView.as_view(),
        name="password_reset_confirm",
    ),
]

