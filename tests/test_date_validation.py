"""Tests for date parameter validation in /api/v1/liquidaciones."""
import pytest
from app.api.v1.endpoints.liquidaciones import validate_and_parse_dates
from app.core.exceptions import DateRangeExceededError, DateRangeInvalidError, InvalidParametersError


def test_valid_date_range():
    """Valid date range within 31 days must pass without error."""
    validate_and_parse_dates("2026-01-01", "2026-01-31")
    validate_and_parse_dates("2026-05-10", "2026-05-10")  # single day


def test_invalid_start_date_format():
    """Invalid start date format raises InvalidParametersError (HTTP 400)."""
    with pytest.raises(InvalidParametersError) as exc_info:
        validate_and_parse_dates("01-01-2026", "2026-01-31")
    assert "no tiene un formato válido" in str(exc_info.value.message)
    assert exc_info.value.status_code == 400


def test_invalid_end_date_format():
    """Invalid end date format raises InvalidParametersError (HTTP 400)."""
    with pytest.raises(InvalidParametersError) as exc_info:
        validate_and_parse_dates("2026-01-01", "2026/01/31")
    assert "no tiene un formato válido" in str(exc_info.value.message)


def test_start_date_after_end_date():
    """When fecha_inicio > fecha_fin, raises DateRangeInvalidError (HTTP 400)."""
    with pytest.raises(DateRangeInvalidError) as exc_info:
        validate_and_parse_dates("2026-02-15", "2026-02-01")
    assert exc_info.value.code == "DATE_RANGE_INVALID"
    assert exc_info.value.status_code == 400


def test_date_range_exceeds_maximum_days():
    """When range exceeds MAX_DATE_RANGE_DAYS (31), raises DateRangeExceededError."""
    with pytest.raises(DateRangeExceededError) as exc_info:
        validate_and_parse_dates("2026-01-01", "2026-02-15")  # 46 days
    assert exc_info.value.code == "DATE_RANGE_EXCEEDED"
    assert exc_info.value.status_code == 400
    assert "31 días" in exc_info.value.message
