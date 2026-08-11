"""Versioned canonical primitives for identity-bearing trading records.

The protocol deliberately uses a smaller JSON domain than general JSON:

* mappings have string keys;
* numbers are booleans or I-JSON-safe integers;
* exact financial values are canonical decimal *strings*;
* binary floats are prohibited in identity payloads;
* duplicate keys and non-finite constants are rejected on input.

This is a RiskYieldMM protocol inspired by RFC 8785.  It is not advertised as
full JCS because Python's standard JSON float formatting is not ECMAScript
number serialization.  Prohibiting floats removes that ambiguity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

CANONICALIZATION_VERSION = "riskyieldmm_canonical_json_v1"
MAX_IJSON_INTEGER = (1 << 53) - 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,6}))?"
    r"(?P<offset>Z|[+-]\d{2}:\d{2})$"
)


class CanonicalizationError(ValueError):
    """Raised when a value cannot enter an identity-bearing payload."""


def utc_datetime(value: datetime | str, *, field: str = "timestamp") -> datetime:
    """Parse an offset-aware timestamp and normalize it to UTC."""

    parsed: datetime
    if type(value) is datetime:
        parsed = value
    elif isinstance(value, datetime):
        raise CanonicalizationError(
            f"{field} must be an exact datetime, not a datetime subclass"
        )
    elif isinstance(value, str):
        text = value
        if not text or text != text.strip():
            raise CanonicalizationError(f"{field} must be a trimmed RFC 3339 timestamp")
        match = RFC3339_RE.fullmatch(text)
        if match is None:
            raise CanonicalizationError(
                f"{field} must use strict RFC 3339 syntax with at most 6 fractional digits"
            )
        if match.group("offset") == "Z":
            text = f"{text[:-1]}+00:00"
        elif match.group("offset") == "-00:00":
            raise CanonicalizationError(
                f"{field} must not use RFC 3339's unknown -00:00 offset"
            )
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise CanonicalizationError(
                f"{field} must be an RFC 3339 timestamp"
            ) from exc
    else:
        raise CanonicalizationError(f"{field} must be a datetime or RFC 3339 string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalizationError(f"{field} must include an explicit UTC offset")
    offset_seconds = parsed.utcoffset().total_seconds()
    if offset_seconds % 60:
        raise CanonicalizationError(f"{field} UTC offset must use whole minutes")
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise CanonicalizationError(
            f"{field} is outside the supported UTC range"
        ) from exc


def utc_iso(value: datetime | str, *, field: str = "timestamp") -> str:
    """Return the one canonical UTC representation used in persisted hashes."""

    parsed = utc_datetime(value, field=field)
    timespec = "microseconds" if parsed.microsecond else "seconds"
    return parsed.isoformat(timespec=timespec).replace("+00:00", "Z")


def canonical_decimal(
    value: Decimal | int | float | str,
    *,
    field: str,
    minimum: Decimal | int | str | None = None,
    strictly_positive: bool = False,
    max_precision: int = 38,
    max_scale: int = 18,
) -> str:
    """Normalize an exact financial value into a non-exponent decimal string.

    Floats are accepted only at the in-process construction boundary and are
    converted from their shortest round-trippable ``repr``.  Persisted parsers
    require the resulting string, so binary floats never enter canonical JSON.
    """

    if isinstance(value, bool):
        raise CanonicalizationError(f"{field} must be numeric, not boolean")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"{field} must be finite")
        if value == 0.0 and math.copysign(1.0, value) < 0:
            raise CanonicalizationError(f"{field} must not be negative zero")
        raw = repr(value)
    elif isinstance(value, (Decimal, int)):
        raw = str(value)
    elif isinstance(value, str):
        if not value or value != value.strip():
            raise CanonicalizationError(f"{field} must be a trimmed decimal string")
        raw = value
    else:
        raise CanonicalizationError(f"{field} must be Decimal, int, float, or string")

    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise CanonicalizationError(f"{field} must be a valid decimal") from exc
    if not number.is_finite():
        raise CanonicalizationError(f"{field} must be finite")
    if number.is_zero() and number.is_signed():
        raise CanonicalizationError(f"{field} must not be negative zero")
    if strictly_positive and number <= 0:
        raise CanonicalizationError(f"{field} must be strictly positive")
    if minimum is not None and number < Decimal(str(minimum)):
        raise CanonicalizationError(f"{field} must be at least {minimum}")
    if number.is_zero():
        return "0"
    if not number.is_zero() and number.adjusted() >= max_precision:
        raise CanonicalizationError(
            f"{field} exceeds maximum decimal precision {max_precision}"
        )
    decimal_tuple = number.as_tuple()
    trailing_zeros = 0
    for digit in reversed(decimal_tuple.digits):
        if digit != 0:
            break
        trailing_zeros += 1
    effective_exponent = decimal_tuple.exponent + trailing_zeros
    if not number.is_zero() and effective_exponent < -max_scale:
        raise CanonicalizationError(
            f"{field} exceeds maximum decimal scale {max_scale}"
        )
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        text = "0"
    unsigned = text.lstrip("-")
    integer_part, _, fractional_part = unsigned.partition(".")
    precision = len((integer_part.lstrip("0") + fractional_part).lstrip("0")) or 1
    if precision > max_precision:
        raise CanonicalizationError(
            f"{field} exceeds maximum decimal precision {max_precision}"
        )
    if len(fractional_part) > max_scale:
        raise CanonicalizationError(
            f"{field} exceeds maximum decimal scale {max_scale}"
        )
    return text


def canonical_identifier(value: Any, *, field: str, maximum: int = 256) -> str:
    """Validate an identity string without silently rewriting it."""

    if not isinstance(value, str):
        raise CanonicalizationError(f"{field} must be a string")
    if not value or value != value.strip():
        raise CanonicalizationError(f"{field} must be non-empty and trimmed")
    if len(value) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CanonicalizationError(f"{field} contains a control character")
    if not unicodedata.is_normalized("NFC", value):
        raise CanonicalizationError(f"{field} must use NFC-normalized Unicode")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CanonicalizationError(f"{field} contains invalid Unicode") from exc
    return value


def canonical_hash(value: Any, *, field: str) -> str:
    """Validate a lowercase SHA-256 hexadecimal identity."""

    text = canonical_identifier(value, field=field, maximum=64)
    if SHA256_RE.fullmatch(text) is None:
        raise CanonicalizationError(f"{field} must be a lowercase SHA-256 digest")
    return text


def canonical_reason_codes(values: Sequence[str], *, field: str) -> tuple[str, ...]:
    """Return a deterministic, unique tuple for a semantic set of reasons."""

    if isinstance(values, (str, bytes)):
        raise CanonicalizationError(f"{field} must be a sequence of strings")
    normalized = tuple(canonical_identifier(value, field=field) for value in values)
    if len(set(normalized)) != len(normalized):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return tuple(sorted(normalized))


def canonical_safe_int(
    value: Any,
    *,
    field: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Validate an integer that round-trips through the I-JSON domain."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise CanonicalizationError(f"{field} must be an integer")
    if abs(value) > MAX_IJSON_INTEGER:
        raise CanonicalizationError(f"{field} exceeds the I-JSON safe integer range")
    if minimum is not None and value < minimum:
        raise CanonicalizationError(f"{field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise CanonicalizationError(f"{field} must be at most {maximum}")
    return value


def require_exact_keys(
    payload: Mapping[str, Any],
    *,
    expected: set[str] | frozenset[str],
    context: str,
) -> None:
    """Reject missing and unknown persisted fields."""

    if not isinstance(payload, Mapping):
        raise CanonicalizationError(f"{context} must be a mapping")
    if not all(isinstance(key, str) for key in payload):
        raise CanonicalizationError(f"{context} keys must all be strings")
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise CanonicalizationError(
            f"{context} keys do not match schema; missing={missing}, unknown={unknown}"
        )


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize the supported JSON subset to stable UTF-8 bytes."""

    _validate_json_value(value, path="$", seen=set())
    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CanonicalizationError("value cannot be serialized canonically") from exc


def canonical_json_text(value: Any) -> str:
    """Return canonical UTF-8 JSON as text."""

    return canonical_json_bytes(value).decode("utf-8")


def sha256_digest(value: Any) -> str:
    """Hash a canonical JSON value with SHA-256."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def strict_json_loads(value: str | bytes | bytearray) -> Any:
    """Load strict identity JSON, rejecting duplicates, floats, and constants."""

    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except CanonicalizationError:
        raise
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalizationError("invalid canonical JSON") from exc
    _validate_json_value(parsed, path="$", seen=set())
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalizationError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_float(value: str) -> None:
    raise CanonicalizationError(
        f"JSON floating-point value {value!r} is prohibited; use a decimal string"
    )


def _reject_json_constant(value: str) -> None:
    raise CanonicalizationError(f"non-finite JSON constant {value!r} is prohibited")


def _validate_json_value(value: Any, *, path: str, seen: set[int]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        canonical_safe_int(value, field=path)
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise CanonicalizationError(f"{path} contains invalid Unicode") from exc
        return
    if isinstance(value, float):
        raise CanonicalizationError(
            f"{path} contains a floating-point number; use a decimal string"
        )
    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in seen:
            raise CanonicalizationError(f"{path} contains a reference cycle")
        seen.add(object_id)
        try:
            for key, child in value.items():
                if not isinstance(key, str):
                    raise CanonicalizationError(f"{path} has a non-string key")
                _validate_json_value(child, path=f"{path}.{key}", seen=seen)
        finally:
            seen.remove(object_id)
        return
    if isinstance(value, (list, tuple)):
        object_id = id(value)
        if object_id in seen:
            raise CanonicalizationError(f"{path} contains a reference cycle")
        seen.add(object_id)
        try:
            for index, child in enumerate(value):
                _validate_json_value(child, path=f"{path}[{index}]", seen=seen)
        finally:
            seen.remove(object_id)
        return
    raise CanonicalizationError(
        f"{path} contains unsupported type {type(value).__name__}"
    )


__all__ = [
    "CANONICALIZATION_VERSION",
    "MAX_IJSON_INTEGER",
    "CanonicalizationError",
    "canonical_decimal",
    "canonical_hash",
    "canonical_identifier",
    "canonical_json_bytes",
    "canonical_json_text",
    "canonical_reason_codes",
    "canonical_safe_int",
    "require_exact_keys",
    "sha256_digest",
    "strict_json_loads",
    "utc_datetime",
    "utc_iso",
]
