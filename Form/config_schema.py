from django.core.exceptions import ValidationError

FIELD_CONFIG_SCHEMAS = {
    "text": {"allowed": {"min_length", "max_length", "regex", "placeholder", "default"}, "required": set()},
    "slider": {"allowed": {"min", "max", "step", "default"}, "required": {"min", "max"}},
    "dropdown": {"allowed": {"choices", "default"}, "required": {"choices"}},
    "radio": {"allowed": {"choices", "default"}, "required": {"choices"}},
    "checkbox": {"allowed": {"choices", "min_select", "max_select", "default"}, "required": {"choices"}},
    "file": {"allowed": {"allowed_mime_types", "allowed_extensions", "max_size_mb"}, "required": {"allowed_mime_types"}}

}

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
    return dict(DEFAULT_CONFIG.get(field_type, {}))

def validate_config_for_field(field_type, config):
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
