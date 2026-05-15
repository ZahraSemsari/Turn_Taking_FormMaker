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
from django.conf import settings
from django.conf.urls.static import static
from FormAPI.views import PublicFormView 


urlpatterns = [
    path('admin/', admin.site.urls),
    path('account/', include('accounts.urls')),
    path('accounts/', include('allauth.urls')),
    # path("auth/social/", include("dj_rest_auth.socialaccount.urls")),
    path("auth/", include("dj_rest_auth.urls")),
    path(
        "accounts/confirm-email/<str:key>/",
        ConfirmEmailView.as_view(),
        name="account_confirm_email",
    ),

    path("api/" , include("FormAPI.urls")),
    path('f/<str:token>/', PublicFormView.as_view(), name="public-form"),
    
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

