from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator


mobile_validator = RegexValidator(
    regex=r"^\d{11}$",
    message="phone number must be entered in the format: 09123456789",
)


class UserManager(BaseUserManager):
    use_in_migrations = True


    def _create_user(self, username, email, mobile, password, **extra_fields):
        if not username:
            raise ValueError("username is required")
        if not email:
            raise ValueError("Email is required")
        if not mobile:
            raise ValueError("Mobile is required")

        email = self.normalize_email(email)
        mobile = str(mobile).strip().replace(" ", "")

        user = self.model(
            username=username,
            email=email,
            mobile=mobile,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email, mobile, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, mobile, password, **extra_fields)

    def create_superuser(self, username, email, mobile, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(username, email, mobile, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile = models.CharField(
        max_length=11,
        unique=True,
        validators=[mobile_validator],

    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["mobile"]

    objects = UserManager()

    def __str__(self):
        return self.username or self.email or self.mobile
