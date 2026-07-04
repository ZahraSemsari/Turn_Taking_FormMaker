from __future__ import annotations

from typing import Optional

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

TEST_PASSWORD = "Str0ngPass!123"
FAST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def create_user(
    *,
    username: str = "testuser",
    email: Optional[str] = None,
    mobile: Optional[str] = "09120000000",
    password: str = TEST_PASSWORD,
    is_active: bool = True,
    verified_email: bool = False,
    has_set_password: bool = True,
):
    """Create a user compatible with the custom accounts.User model."""
    User = get_user_model()
    user = User.objects.create_user(
        username=username,
        email=email,
        mobile=mobile,
        password=password,
    )
    fields_to_update = []

    if user.is_active != is_active:
        user.is_active = is_active
        fields_to_update.append("is_active")

    if getattr(user, "has_set_password", None) != has_set_password:
        user.has_set_password = has_set_password
        fields_to_update.append("has_set_password")

    if fields_to_update:
        user.save(update_fields=fields_to_update)

    if email:
        EmailAddress.objects.create(
            user=user,
            email=email,
            primary=True,
            verified=verified_email,
        )

    return user


def jwt_client_for(user) -> APIClient:
    """Return an APIClient authenticated with a real JWT access token."""
    refresh = RefreshToken.for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client
