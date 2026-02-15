from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from allauth.account.models import EmailAddress


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
                not user.mobile or not user.has_usable_password()
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
    email = serializers.EmailField(
        required=False,
        allow_null=True,
        allow_blank=True
    )
    mobile = serializers.CharField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="This Mobile is already in use.",
            )
        ],
    )
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "mobile", "password")
        extra_kwargs = {
            "mobile": {"required": True},
            "email": {"required": False, "allow_null": True, "allow_blank": True},
        }


    def validate_mobile(self, value):
        if not value:
            raise serializers.ValidationError("Mobile number is required")
        if not value.isdigit() or len(value) != 11:
            raise serializers.ValidationError("Mobile must be 11 digit.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email"),
            mobile=validated_data["mobile"],
            password=validated_data["password"],
        )
        return user

