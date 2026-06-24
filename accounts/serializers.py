from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from allauth.account.models import EmailAddress
from .models import PhoneOTP
from django.db import transaction, IntegrityError
import re

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "mobile", "first_name", "last_name"]


class EmailOrUsernameOrMobileTokenObtainPairSerializer(TokenObtainPairSerializer):

    identifier = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False

    def validate(self, attrs):

        identifier = (
            attrs.get("identifier")
            or attrs.get(self.username_field)
            or attrs.get("email")
            or attrs.get("mobile")
        )
        password = attrs.get("password")

        if not identifier or not password:
            raise serializers.ValidationError(
                "identifier/email/username/mobile , password must be set"
            )

        identifier = str(identifier).strip()
        username_value = identifier

        try:

            if "@" in identifier:
                user = User.objects.get(email__iexact=identifier)

            elif identifier.isdigit() and len(identifier) == 11:
                user = User.objects.get(mobile=identifier)

            else:
                user = User.objects.get(username__iexact=identifier)

            username_value = user.username

        except User.DoesNotExist:
            pass


        attrs[self.username_field] = username_value
        data = super().validate(attrs)
        user = self.user

        #-----------------compelete-profile------------------------
        data["profile_incomplete"] = (
                not user.username
                or not user.mobile
                or not user.has_usable_password()
        )

        if user and user.email :
            email_qs = EmailAddress.objects.filter(
                user=user,
                email__iexact=user.email,
                verified=True,
            )
            if not email_qs.exists():
                raise serializers.ValidationError(
                    "Email address is not verified ; please check your email and click the confirmation link"
                )

        data["user"] = UserSerializer(self.user).data
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = getattr(user, "username")
        token["email"] = getattr(user, "email", None)
        token["mobile"] = getattr(user, "mobile")
        return token


class RegisterSerializer(serializers.ModelSerializer):
    """
    Mobile signup requires OTP verification.
    Client flow:
      1) POST /signup/otp/request   { mobile }
      2) POST /register            { username, mobile, password, otp_code, email(optional) }
    """

    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)

    mobile = serializers.CharField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="This mobile number is already in use.",
            )
        ],
    )

    username = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        max_length=150,
    )


    password = serializers.CharField(write_only=True, min_length=8)
    otp_code = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "mobile", "password", "otp_code")
        extra_kwargs = {
            "username": {"required": True, "allow_blank": False},
            "mobile": {"required": True},
            "email": {"required": False, "allow_null": True, "allow_blank": True},
        }

    def validate_username(self, value):
        value = (value or "").strip()

        if not value:
            raise serializers.ValidationError("Username is required.")

        if len(value) > 150:
            raise serializers.ValidationError("Username must be less than 150 characters.")

        if not re.match(r'^[\w.+-]+$', value):
            raise serializers.ValidationError(
                "Username may contain only letters, numbers, and ./+/-/_ characters."
            )

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with that username already exists.")

        return value

    def validate_email(self, value):
        raw_email = self.initial_data.get("email", None)

        if isinstance(raw_email, str) and raw_email != "" and raw_email.strip() == "":
            raise serializers.ValidationError({
                "email": "Email cannot be whitespace only."
            })
        if value is not None:
            value = str(value).strip()
            if value == "":
                return None
        return value

    def validate_mobile(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Mobile number is required.")
        if not value.isdigit() or len(value) != 11:
            raise serializers.ValidationError("Mobile must be exactly 11 digits.")
        if not value.startswith("09"):
            raise serializers.ValidationError("Mobile number must start with '09'.")
        return value

    def validate_otp_code(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("OTP code is required.")
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError("OTP code must be exactly 6 digits.")
        return value

    def validate(self, attrs):
        raw_username = self.initial_data.get("username", None)

        if not isinstance(raw_username, str):
            raise serializers.ValidationError({
                "username": "Username must be a string."
            })

        """
        Verify OTP before allowing user creation.
        OTP is consumed (marked used) only if it is valid.
        """

        mobile = attrs.get("mobile")
        otp_code = attrs.get("otp_code")

        try:
            is_valid = PhoneOTP.verify_otp(
                mobile=mobile,
                purpose=PhoneOTP.Purpose.SIGNUP,
                code=otp_code,
                max_attempts=5,
                lock_minutes=10,
            )
        except Exception:
            raise serializers.ValidationError({
                "otp_code": "Unable to verify OTP."
            })

        if not is_valid:
            raise serializers.ValidationError(
                {"otp_code": "Invalid or expired verification code."}
            )

        return attrs

    def create(self, validated_data):
        """
        Create the user after OTP is verified.
        Note: otp_code is not stored in user model.
        """
        validated_data.pop("otp_code", None)
        email = validated_data.pop("email", None)
        if email == "":
            email = None

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=validated_data["username"],
                    email=email,
                    mobile=validated_data["mobile"],
                    password=validated_data["password"],
                )
        except IntegrityError:
            raise serializers.ValidationError({
                "detail": "Username or mobile already exists."
            })
        
        return user