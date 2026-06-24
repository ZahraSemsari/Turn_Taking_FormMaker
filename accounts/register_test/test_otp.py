# tests/test_otp.py

import pytest
from freezegun import freeze_time
from datetime import timedelta
from django.utils import timezone
from concurrent.futures import ThreadPoolExecutor

from accounts.models import PhoneOTP


@pytest.mark.django_db
def test_generate_otp_format():
    code = PhoneOTP.generate_code()

    assert len(code) == 6
    assert code.isdigit()


@pytest.mark.django_db
def test_request_otp_creates_record():
    code = PhoneOTP.request_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    otp = PhoneOTP.objects.first()

    assert otp is not None
    assert otp.code_hash != code


@pytest.mark.django_db
def test_verify_otp_success():
    code = PhoneOTP.request_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    result = PhoneOTP.verify_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP,
        code=code
    )

    assert result is True


@pytest.mark.django_db
def test_verify_otp_wrong_code():
    PhoneOTP.request_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    result = PhoneOTP.verify_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP,
        code="000000"
    )

    assert result is False


@pytest.mark.django_db
def test_otp_replay_prevention():
    code = PhoneOTP.request_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    assert PhoneOTP.verify_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP,
        code=code
    )

    assert not PhoneOTP.verify_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP,
        code=code
    )


@pytest.mark.django_db
@freeze_time("2025-01-01 10:00:00")
def test_otp_expiration():
    code = PhoneOTP.request_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=1
    )

    with freeze_time("2025-01-01 10:02:00"):
        result = PhoneOTP.verify_otp(
            mobile="09111111111",
            purpose=PhoneOTP.Purpose.SIGNUP,
            code=code
        )

    assert result is False



@pytest.mark.django_db
def test_cooldown_enforced():
    PhoneOTP.request_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    with pytest.raises(ValueError):
        PhoneOTP.request_otp(
            mobile="09111111111",
            purpose=PhoneOTP.Purpose.SIGNUP
        )


@pytest.mark.django_db
@freeze_time("2025-01-01 10:00:00")
def test_cooldown_expires():
    PhoneOTP.request_otp(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    with freeze_time("2025-01-01 10:02:00"):
        code = PhoneOTP.request_otp(
            mobile="09111111111",
            purpose=PhoneOTP.Purpose.SIGNUP
        )

    assert code is not None



@pytest.mark.django_db(transaction=True)
def test_concurrent_otp_requests():
    """تست درخواست‌های همزمان OTP"""
    from concurrent.futures import ThreadPoolExecutor
    
    def request_otp():
        try:
            # دستکاری زمان برای هر درخواست
            otp = PhoneOTP.objects.filter(mobile="09111111111").first()
            if otp:
                otp.created_at = timezone.now() - timedelta(seconds=61)
                otp.save()
            
            return PhoneOTP.request_otp(
                mobile="09111111111",
                purpose=PhoneOTP.Purpose.SIGNUP
            )
        except ValueError:
            return None
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(request_otp) for _ in range(5)]
        results = [f.result() for f in futures]
    
    active_otps = PhoneOTP.objects.filter(
        mobile="09111111111",
        purpose=PhoneOTP.Purpose.SIGNUP,
        is_used=False
    ).count()
    
    assert active_otps <= 1