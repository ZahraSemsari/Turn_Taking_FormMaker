# Form/utils.py
from django.core import signing

# Salt used for signing public form links.
# It separates form share-link tokens from other signed values in the project.
FORM_LINK_SALT = "form-share-link"

def encode_form_token(user_id: int, form_id: int) -> str:
    """
    Create a signed public token for a form.

    The token contains:
    - u: owner user id
    - f: form id

    Because the token is signed, users cannot safely change its content manually.
    """
    data = {"u": user_id, "f": form_id}
    return signing.dumps(data, salt=FORM_LINK_SALT)

def decode_form_token(token: str) -> dict:
    """
    Decode and verify a signed public form token.

    Returns a dictionary with user id and form id.
    Raises BadSignature if the token is invalid or tampered with.
    """
    return signing.loads(token, salt=FORM_LINK_SALT)
