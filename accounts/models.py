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
            raise ValueError("Username is required")
        # if not mobile:
        #     raise ValueError("Mobile is required")


        email = self.normalize_email(email) if email else None
        if mobile:
            mobile = str(mobile).strip().replace(" ", "")

        user = self.model(
            username=username,
            email=email,
            mobile=mobile,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, mobile=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, mobile, password, **extra_fields)

    def create_superuser(self, username, email=None, mobile=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if mobile is None:
            raise ValueError("Users must have mobile number")

        return self._create_user(username, email, mobile, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile = models.CharField(
        max_length=11,
        unique=True,
        validators=[mobile_validator],
        null=True,
        blank=True,

    )
    
    #-----------------------profile-check------------------------------

    is_profile_completed = models.BooleanField(default=False)
    has_set_password = models.BooleanField(default=False)

    
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["mobile"]

    objects = UserManager()

    def __str__(self):
        return self.username or self.email or self.mobile


#---------------------------------------OTP model-------------------------------------------------------------

from django.db import models
from django.utils import timezone
from datetime import timedelta
import random


class PhoneResetOTP(models.Model):
    mobile = models.CharField(max_length=11, db_index=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    @staticmethod
    def generate_code():
        return f"{random.randint(0, 999999):06d}"

    @classmethod
    def create_otp(cls, mobile, minutes=2):
        return cls.objects.create(
            mobile=mobile,
            code=cls.generate_code(),
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    def is_expired(self):
        return timezone.now() > self.expires_at
