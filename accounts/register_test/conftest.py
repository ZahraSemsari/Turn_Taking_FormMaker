# tests/conftest.py

import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_user():
    def make_user(**kwargs):
        defaults = {
            "username": "testuser",
            "email": "test@example.com",
            "mobile": "09123456789",
            "password": "StrongPass123!"
        }
        defaults.update(kwargs)

        password = defaults.pop("password")

        user = User.objects.create_user(**defaults)
        user.set_password(password)
        user.save()

        return user

    return make_user
