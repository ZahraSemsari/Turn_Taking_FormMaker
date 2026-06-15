# tests/test_user_model.py

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

User = get_user_model()


@pytest.mark.django_db
def test_create_user_success():
    user = User.objects.create_user(
        username="fatemeh",
        email="fatemeh@test.com",
        mobile="09111111111",
        password="StrongPass123!"
    )

    assert user.username == "fatemeh"
    assert user.email == "fatemeh@test.com"
    assert user.mobile == "09111111111"


@pytest.mark.django_db
def test_password_is_hashed():
    user = User.objects.create_user(
        username="u1",
        password="MySecret123!"
    )

    assert user.password != "MySecret123!"
    assert user.check_password("MySecret123!")


@pytest.mark.django_db
def test_create_user_without_username():
    with pytest.raises(ValueError):
        User.objects.create_user(
            username="",
            password="StrongPass123!"
        )


@pytest.mark.django_db
def test_multiple_null_emails_allowed():
    user1 = User.objects.create_user(
        username="u1",
        email=None,
        password="StrongPass123!"
    )

    user2 = User.objects.create_user(
        username="u2",
        email=None,
        password="StrongPass123!"
    )

    assert user1.id != user2.id


@pytest.mark.django_db
def test_duplicate_email_raises_error():
    User.objects.create_user(
        username="u1",
        email="dup@test.com",
        password="StrongPass123!"
    )

    with pytest.raises(IntegrityError):
        User.objects.create_user(
            username="u2",
            email="dup@test.com",
            password="StrongPass123!"
        )


@pytest.mark.django_db
def test_mobile_validation_invalid_short():
    user = User(
        username="u1",
        mobile="09123"
    )

    with pytest.raises(ValidationError):
        user.full_clean()


@pytest.mark.django_db
def test_mobile_validation_non_digit():
    user = User(
        username="u1",
        mobile="09123abc789"
    )

    with pytest.raises(ValidationError):
        user.full_clean()


@pytest.mark.django_db
@pytest.mark.django_db
def test_mobile_validation_valid():
    user = User(
        username="u1", 
        mobile="09123456789"
    )
    try:
        user.clean_fields(exclude=['password'])
    except ValidationError as e:
        assert 'mobile' not in e.message_dict


@pytest.mark.django_db
def test_unicode_username():
    user = User.objects.create_user(
        username="فاطمه",
        password="StrongPass123!"
    )

    assert user.username == "فاطمه"


@pytest.mark.django_db
def test_very_long_username():
    username = "a" * 300
    user = User(username=username, password="testpass123")
    
    # این روش در همه دیتابیس‌ها کار می‌کند
    with pytest.raises(ValidationError):
        user.full_clean()


@pytest.mark.django_db
def test_email_normalization():
    user = User.objects.create_user(
        username="u1",
        email="TEST@EXAMPLE.COM",
        password="StrongPass123!"
    )

    assert user.email == "TEST@example.com"


@pytest.mark.django_db
def test_superuser_creation():
    admin = User.objects.create_superuser(
        username="admin",
        email="admin@test.com",
        mobile="09111111111",
        password="AdminPass123!"
    )

    assert admin.is_staff
    assert admin.is_superuser


@pytest.mark.django_db
def test_superuser_requires_mobile():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            username="admin",
            password="AdminPass123!"
        )


@pytest.mark.django_db
def test_mobile_whitespace_removed():
    user = User.objects.create_user(
        username="u1",
        mobile="0912 3456789",
        password="StrongPass123!"
    )

    assert user.mobile == "09123456789"


@pytest.mark.django_db
def test_user_str_returns_username():
    user = User.objects.create_user(
        username="fatemeh",
        password="StrongPass123!"
    )

    assert str(user) == "fatemeh"