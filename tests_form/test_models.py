import pytest
from django.core.exceptions import ValidationError

from Form.models import AllResponse, FieldResponse, FieldModel, FormModel
from Form.utils import decode_form_token


pytestmark = pytest.mark.django_db


def test_form_save_generates_slug_and_signed_share_link(form):
    form.refresh_from_db()

    assert form.slug == form.title
    assert form.share_link.startswith("/f/")
    assert form.share_link.endswith("/")

    token = form.share_link.strip("/").split("/", 1)[1]
    decoded = decode_form_token(token)
    assert decoded == {"u": form.created_by_id, "f": form.id}


def test_form_save_preserves_existing_share_link(form_factory):
    form = form_factory(share_link="/custom/share/")

    assert form.share_link == "/custom/share/"


def test_form_string_representation_returns_title(form):
    # This catches the common typo `def str(self)` instead of `def __str__(self)`.
    assert str(form) == form.title


def test_field_save_fills_default_config_when_config_is_empty(field_factory):
    field = field_factory(field_type="slider", config={})

    assert field.config == {"min": 0, "max": 100, "step": 1}


def test_field_save_rejects_invalid_config(field_factory):
    with pytest.raises(ValidationError):
        field_factory(field_type="slider", config={"min": 10, "max": 1})


def test_field_name_must_be_unique_inside_one_form(field_factory):
    field_factory(name="email", field_type="email")

    with pytest.raises(ValidationError):
        field_factory(name="email", field_type="text")


def test_same_field_name_is_allowed_in_different_forms(form_factory, field_factory):
    other_form = form_factory()
    first = field_factory(name="email")
    second = field_factory(form=other_form, name="email")

    assert first.name == second.name == "email"
    assert first.form_id != second.form_id


def test_field_response_clean_accepts_field_from_same_form(form, field_factory):
    field = field_factory(form=form)
    response = AllResponse.objects.create(form=form)
    field_response = FieldResponse(response=response, response_fields=field, value="ok")

    field_response.clean()


def test_field_response_clean_rejects_field_from_another_form(form, form_factory, field_factory):
    other_form = form_factory()
    field_from_other_form = field_factory(form=other_form)
    response = AllResponse.objects.create(form=form)
    field_response = FieldResponse(
        response=response,
        response_fields=field_from_other_form,
        value="bad",
    )

    with pytest.raises(ValidationError, match="not related"):
        field_response.clean()
