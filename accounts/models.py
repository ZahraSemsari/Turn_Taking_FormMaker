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
# models.py

from django.db import models
from django.utils import timezone
from datetime import timedelta
import random

from django.contrib.auth.hashers import make_password, check_password


class PhoneOTP(models.Model):
    class Purpose(models.TextChoices):
        RESET_PASSWORD = "reset_password", "Reset password"
        SIGNUP = "signup", "Signup"

    mobile = models.CharField(max_length=11, db_index=True)
    purpose = models.CharField(max_length=32, choices=Purpose.choices, db_index=True)

    code_hash = models.CharField(max_length=128)  # hashed OTP
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    is_used = models.BooleanField(default=False, db_index=True)

    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["mobile", "purpose", "-created_at"]),
        ]

    @staticmethod
    def generate_code() -> str:
        return f"{random.randint(0, 999999):06d}"

    @staticmethod
    def _now():
        return timezone.now()

    @classmethod
    def _active_qs(cls, mobile: str, purpose: str):
        now = cls._now()
        return cls.objects.filter(
            mobile=mobile,
            purpose=purpose,
            is_used=False,
            expires_at__gt=now,
        )

    @classmethod
    def request_otp(
        cls,
        *,
        mobile: str,
        purpose: str,
        minutes: int = 5,
        cooldown_seconds: int = 60,
        max_attempts: int = 5,
        lock_minutes: int = 10,
    ) -> str:
        """
        Creates a new OTP and returns the raw code (ONLY to send via SMS).
        Stores only a hash in DB.
        Enforces:
        - lockout window
        - cooldown/rate limit
        - invalidates previous active OTPs
        """
        now = cls._now()

        latest = cls.objects.filter(mobile=mobile, purpose=purpose).order_by("-created_at").first()
        if latest and latest.locked_until and latest.locked_until > now:
            remaining = int((latest.locked_until - now).total_seconds())
            raise ValueError(f"locked:{remaining}")

        # rate limit: 1 per cooldown_seconds
        if latest and (now - latest.created_at).total_seconds() < cooldown_seconds:
            remaining = int(cooldown_seconds - (now - latest.created_at).total_seconds())
            raise ValueError(f"cooldown:{remaining}")

        # invalidate previous active OTPs (so only 1 valid at a time)
        cls._active_qs(mobile, purpose).update(is_used=True)

        code = cls.generate_code()
        cls.objects.create(
            mobile=mobile,
            purpose=purpose,
            code_hash=make_password(code),
            expires_at=now + timedelta(minutes=minutes),
            is_used=False,
            failed_attempts=0,
            locked_until=None,
        )
        return code

    @classmethod
    def verify_otp(
        cls,
        *,
        mobile: str,
        purpose: str,
        code: str,
        max_attempts: int = 5,
        lock_minutes: int = 10,
    ) -> bool:
        """
        Verifies the latest active OTP.
        On failure increments attempts; on reaching max_attempts locks for lock_minutes.
        """
        now = cls._now()

        otp = cls._active_qs(mobile, purpose).order_by("-created_at").first()
        if not otp:
            return False

        if otp.locked_until and otp.locked_until > now:
            return False

        if check_password(code, otp.code_hash):
            otp.is_used = True
            otp.save(update_fields=["is_used"])
            return True

        # wrong code
        otp.failed_attempts += 1
        updates = ["failed_attempts"]

        if otp.failed_attempts >= max_attempts:
            otp.locked_until = now + timedelta(minutes=lock_minutes)
            otp.is_used = True  # invalidate this OTP
            updates += ["locked_until", "is_used"]

        otp.save(update_fields=updates)
        return False