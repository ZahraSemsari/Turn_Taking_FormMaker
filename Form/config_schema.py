from django.core.exceptions import ValidationError


# Defines valid config schema for each configurable field type.
# `allowed` contains keys the frontend is allowed to send.
# `required` contains keys that must exist for that field type.
FIELD_CONFIG_SCHEMAS = {
    "text": {"allowed": {"min_length", "max_length", "regex", "placeholder", "default"}, "required": set()},
    "slider": {"allowed": {"min", "max", "step", "default"}, "required": {"min", "max"}},
    "dropdown": {"allowed": {"choices", "default"}, "required": {"choices"}},
    "radio": {"allowed": {"choices", "default"}, "required": {"choices"}},
    "checkbox": {"allowed": {"choices", "min_select", "max_select", "default"}, "required": {"choices"}},
    "file": {"allowed": {"allowed_mime_types", "allowed_extensions", "max_size_mb"}, "required": {"allowed_mime_types"}}

}

# Default config used when frontend does not provide config for a field.
DEFAULT_CONFIG = {
    "text": {"min_length": 0, "max_length": 255},
    "slider": {"min": 0, "max": 100, "step": 1},
    "dropdown": {"choices": []},
    "radio": {"choices": []},
    "checkbox": {"choices": []},
    "file": {
            "allowed_mime_types": ["image/png"],
            "allowed_extensions": [".png"],
            "max_size_mb": 10
        }
}

def default_config_for(field_type):
    """
    Return a copy of default config for the given field type.

    A copy is returned to avoid accidental mutation of DEFAULT_CONFIG.
    """
    return dict(DEFAULT_CONFIG.get(field_type, {}))

def validate_config_for_field(field_type, config):
    """
    Validate the config object of a form field.

    Checks:
    - config must be a dictionary/object
    - unsupported keys are rejected
    - required keys must be present
    - slider min must be less than or equal to max

    Unknown field types are ignored here because not every field type
    currently needs custom config validation.
    """
    if not isinstance(config, dict):
        raise ValidationError("config must be an object.")
    schema = FIELD_CONFIG_SCHEMAS.get(field_type)
    if not schema:
        return
    extra = set(config.keys()) - schema["allowed"]
    missing = schema["required"] - set(config.keys())
    if extra:
        raise ValidationError(f"Unsupported keys for {field_type}: {sorted(extra)}")
    if missing:
        raise ValidationError(f"Missing keys for {field_type}: {sorted(missing)}")
    if field_type == "slider" and config["min"] > config["max"]:
        raise ValidationError("slider: min must be <= max")
