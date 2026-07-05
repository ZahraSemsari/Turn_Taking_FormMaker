import itertools

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from Form.models import FormModel, FieldModel


@pytest.fixture(autouse=True)
def test_media_root(settings, tmp_path):
    """Keep uploaded files from tests out of the real MEDIA_ROOT."""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_factory(db):
    counter = itertools.count(1)
    User = get_user_model()

    def make_user(**kwargs):
        i = next(counter)
        password = kwargs.pop("password", "StrongPass123!")
        defaults = {
            "username": f"user_{i}",
            "email": f"user_{i}@example.com",
            "mobile": f"09123{i:06d}",
        }
        defaults.update(kwargs)
        return User.objects.create_user(password=password, **defaults)

    return make_user


@pytest.fixture
def user(user_factory):
    return user_factory(
        username="owner",
        email="owner@example.com",
        mobile="09111111111",
    )


@pytest.fixture
def other_user(user_factory):
    return user_factory(
        username="other_owner",
        email="other@example.com",
        mobile="09222222222",
    )


@pytest.fixture
def authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def other_authed_client(other_user):
    client = APIClient()
    client.force_authenticate(user=other_user)
    return client


@pytest.fixture
def form_factory(db, user):
    counter = itertools.count(1)

    def make_form(created_by=None, **kwargs):
        i = next(counter)
        defaults = {
            "title": f"test-form-{i}",
            "description": f"description-{i}",
            "is_public": True,
        }
        defaults.update(kwargs)
        return FormModel.objects.create(created_by=created_by or user, **defaults)

    return make_form


@pytest.fixture
def form(form_factory):
    return form_factory()


@pytest.fixture
def private_form(form_factory):
    return form_factory(is_public=False)


@pytest.fixture
def field_factory(db, form):
    counter = itertools.count(1)

    def make_field(form=form, **kwargs):
        i = next(counter)
        defaults = {
            "field_type": "text",
            "config": {},
            "name": f"field_{i}",
            "label": f"Field {i}",
            "order_index": i,
            "is_required": False,
            "description": "",
        }
        defaults.update(kwargs)
        return FieldModel.objects.create(form=form, **defaults)

    return make_field
