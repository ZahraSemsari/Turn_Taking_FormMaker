import pytest
from django.core.exceptions import ValidationError

from Form.config_schema import default_config_for, validate_config_for_field


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "field_type, expected",
    [
        ("text", {"min_length": 0, "max_length": 255}),
        ("slider", {"min": 0, "max": 100, "step": 1}),
        ("dropdown", {"choices": []}),
        ("radio", {"choices": []}),
        ("checkbox", {"choices": []}),
        (
            "file",
            {
                "allowed_mime_types": ["image/png"],
                "allowed_extensions": [".png"],
                "max_size_mb": 10,
            },
        ),
        ("number", {}),
    ],
)
def test_default_config_for_known_and_unknown_field_types(field_type, expected):
    assert default_config_for(field_type) == expected


def test_default_config_returns_a_copy_not_shared_state():
    first = default_config_for("text")
    first["max_length"] = 1

    assert default_config_for("text")["max_length"] == 255


@pytest.mark.parametrize(
    "field_type, config",
    [
        ("text", {"min_length": 2, "max_length": 20, "regex": r"^[A-Z]+$"}),
        ("slider", {"min": 1, "max": 10, "step": 1}),
        ("dropdown", {"choices": ["a", "b"]}),
        ("radio", {"choices": [{"value": "yes"}, {"value": "no"}]}),
        ("checkbox", {"choices": ["x", "y"], "min_select": 1, "max_select": 2}),
        (
            "file",
            {
                "allowed_mime_types": ["image/png"],
                "allowed_extensions": [".png"],
                "max_size_mb": 1,
            },
        ),
        ("number", {"any": "thing"}),  # unknown schema is intentionally ignored
    ],
)
def test_validate_config_for_field_accepts_valid_configs(field_type, config):
    validate_config_for_field(field_type, config)


def test_validate_config_rejects_non_object_config():
    with pytest.raises(ValidationError, match="config must be an object"):
        validate_config_for_field("text", [])


@pytest.mark.parametrize(
    "field_type, config, expected_message",
    [
        ("text", {"max_length": 10, "bad_key": True}, "Unsupported keys"),
        ("slider", {"min": 1}, "Missing keys"),
        ("dropdown", {}, "Missing keys"),
        ("radio", {}, "Missing keys"),
        ("checkbox", {}, "Missing keys"),
        ("file", {"allowed_extensions": [".png"]}, "Missing keys"),
        ("slider", {"min": 10, "max": 1}, "min must be <= max"),
    ],
)
def test_validate_config_for_field_rejects_invalid_configs(field_type, config, expected_message):
    with pytest.raises(ValidationError, match=expected_message):
        validate_config_for_field(field_type, config)
