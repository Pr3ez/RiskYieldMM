"""Ed25519 adapter for V3 governance-ledger checkpoints.

Key persistence is intentionally outside this module.  Callers provide a
private key object or in-memory raw bytes from their own secret manager; the
ledger receives only the structural signer interface and stores no secret.
"""

from __future__ import annotations

from typing import Any

from .canonical import CanonicalizationError, canonical_hash, sha256_digest

ED25519_ALGORITHM = "ED25519"
_ED25519_FIELD_MODULUS = 2**255 - 19
_ED25519_SUBGROUP_ORDER = 2**252 + 27742317777372353535851937790883648493
_ED25519_D = (
    -121665 * pow(121666, -1, _ED25519_FIELD_MODULUS)
) % _ED25519_FIELD_MODULUS
_ED25519_SQRT_MINUS_ONE = pow(
    2,
    (_ED25519_FIELD_MODULUS - 1) // 4,
    _ED25519_FIELD_MODULUS,
)


def _ed25519_add(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Add two Edwards25519 points in extended projective coordinates."""

    modulus = _ED25519_FIELD_MODULUS
    x1, y1, z1, t1 = left
    x2, y2, z2, t2 = right
    a = ((y1 - x1) * (y2 - x2)) % modulus
    b = ((y1 + x1) * (y2 + x2)) % modulus
    c = (2 * _ED25519_D * t1 * t2) % modulus
    d = (2 * z1 * z2) % modulus
    e = (b - a) % modulus
    f = (d - c) % modulus
    g = (d + c) % modulus
    h = (b + a) % modulus
    return (
        (e * f) % modulus,
        (g * h) % modulus,
        (f * g) % modulus,
        (e * h) % modulus,
    )


def _ed25519_scalar_multiply(
    point: tuple[int, int, int, int],
    scalar: int,
) -> tuple[int, int, int, int]:
    result = (0, 1, 1, 0)
    addend = point
    value = scalar
    while value:
        if value & 1:
            result = _ed25519_add(result, addend)
        addend = _ed25519_add(addend, addend)
        value >>= 1
    return result


def _ed25519_is_identity(point: tuple[int, int, int, int]) -> bool:
    x, y, z, _ = point
    modulus = _ED25519_FIELD_MODULUS
    return x % modulus == 0 and (y - z) % modulus == 0


def _decode_ed25519_point(encoded: bytes) -> tuple[int, int, int, int] | None:
    if not isinstance(encoded, bytes) or len(encoded) != 32:
        return None
    modulus = _ED25519_FIELD_MODULUS
    value = int.from_bytes(encoded, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    if y >= modulus:
        return None
    y_squared = (y * y) % modulus
    denominator = (_ED25519_D * y_squared + 1) % modulus
    if denominator == 0:
        return None
    x_squared = ((y_squared - 1) * pow(denominator, -1, modulus)) % modulus
    x = pow(x_squared, (modulus + 3) // 8, modulus)
    if (x * x - x_squared) % modulus != 0:
        x = (x * _ED25519_SQRT_MINUS_ONE) % modulus
    if (x * x - x_squared) % modulus != 0:
        return None
    if x == 0 and sign == 1:
        return None
    if x & 1 != sign:
        x = (-x) % modulus
    return (x, y, 1, (x * y) % modulus)


def ed25519_public_key_is_valid(public_key_bytes: bytes) -> bool:
    """Return whether an encoding is canonical, nonzero, and in the main subgroup.

    Some Ed25519 providers accept low-order encodings for selected messages.
    Checkpoint keys therefore use the stricter point-validity rule also exposed by
    mature Ed25519 APIs: the encoding must decode canonically to a non-identity
    point in the prime-order subgroup.
    """

    point = _decode_ed25519_point(public_key_bytes)
    if point is None or _ed25519_is_identity(point):
        return False
    return _ed25519_is_identity(
        _ed25519_scalar_multiply(point, _ED25519_SUBGROUP_ORDER)
    )


def _validate_ed25519_signature_encoding(signature: bytes) -> None:
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise CanonicalizationError("Ed25519 signature must contain exactly 64 bytes")
    if not ed25519_public_key_is_valid(signature[:32]):
        raise CanonicalizationError(
            "Ed25519 signature R encoding is not a valid main-subgroup point"
        )
    if int.from_bytes(signature[32:], "little") >= _ED25519_SUBGROUP_ORDER:
        raise CanonicalizationError("Ed25519 signature scalar is not canonical")


def _ed25519_types() -> tuple[type[Any], type[Any]]:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Ed25519 checkpoint signing requires riskyieldmm[governance]"
        ) from exc
    return Ed25519PrivateKey, Ed25519PublicKey


def _public_bytes(public_key: Any) -> bytes:
    try:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Ed25519 checkpoint signing requires riskyieldmm[governance]"
        ) from exc
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def derive_ed25519_key_id(public_key_bytes: bytes) -> str:
    """Derive the stable checkpoint key ID from exactly 32 public-key bytes."""

    if not isinstance(public_key_bytes, bytes) or len(public_key_bytes) != 32:
        raise CanonicalizationError("Ed25519 public key must contain exactly 32 bytes")
    return sha256_digest(
        {
            "algorithm": ED25519_ALGORITHM,
            "domain": "RiskYieldMMCheckpointPublicKeyV1",
            "public_key_hex": public_key_bytes.hex(),
        }
    )


class Ed25519CheckpointVerifier:
    """Trusted public-key verifier for an externally anchored checkpoint."""

    algorithm = ED25519_ALGORITHM

    def __init__(self, public_key: Any, *, key_id: str | None = None) -> None:
        _, public_type = _ed25519_types()
        if not isinstance(public_key, public_type):
            raise TypeError("public_key must be an Ed25519PublicKey")
        public_bytes = _public_bytes(public_key)
        if not ed25519_public_key_is_valid(public_bytes):
            raise CanonicalizationError(
                "Ed25519 public key is not a valid main-subgroup point"
            )
        derived = derive_ed25519_key_id(public_bytes)
        if key_id is not None and canonical_hash(key_id, field="key_id") != derived:
            raise CanonicalizationError("key_id differs from the supplied public key")
        self._public_key = public_key
        self.key_id = derived
        self.public_key_bytes = public_bytes

    @classmethod
    def from_public_bytes(
        cls,
        public_key_bytes: bytes,
        *,
        key_id: str | None = None,
    ) -> Ed25519CheckpointVerifier:
        if not isinstance(public_key_bytes, bytes) or len(public_key_bytes) != 32:
            raise CanonicalizationError(
                "Ed25519 public key must contain exactly 32 bytes"
            )
        _, public_type = _ed25519_types()
        return cls(public_type.from_public_bytes(public_key_bytes), key_id=key_id)

    def verify(self, payload: bytes, signature: bytes) -> None:
        if not isinstance(payload, bytes):
            raise TypeError("checkpoint payload must be bytes")
        _validate_ed25519_signature_encoding(signature)
        self._public_key.verify(signature, payload)


class Ed25519CheckpointSigner:
    """In-memory Ed25519 signer; private-key storage remains caller-owned."""

    algorithm = ED25519_ALGORITHM

    def __init__(self, private_key: Any, *, key_id: str | None = None) -> None:
        private_type, _ = _ed25519_types()
        if not isinstance(private_key, private_type):
            raise TypeError("private_key must be an Ed25519PrivateKey")
        self._private_key = private_key
        public_bytes = _public_bytes(private_key.public_key())
        derived = derive_ed25519_key_id(public_bytes)
        if key_id is not None and canonical_hash(key_id, field="key_id") != derived:
            raise CanonicalizationError("key_id differs from the private key")
        self.key_id = derived
        self.public_key_bytes = public_bytes

    @classmethod
    def generate(cls) -> Ed25519CheckpointSigner:
        private_type, _ = _ed25519_types()
        return cls(private_type.generate())

    @classmethod
    def from_private_bytes(
        cls,
        private_key_bytes: bytes,
        *,
        key_id: str | None = None,
    ) -> Ed25519CheckpointSigner:
        if not isinstance(private_key_bytes, bytes) or len(private_key_bytes) != 32:
            raise CanonicalizationError(
                "Ed25519 private key seed must contain exactly 32 bytes"
            )
        private_type, _ = _ed25519_types()
        return cls(private_type.from_private_bytes(private_key_bytes), key_id=key_id)

    def sign(self, payload: bytes) -> bytes:
        if not isinstance(payload, bytes):
            raise TypeError("checkpoint payload must be bytes")
        return self._private_key.sign(payload)

    def verify(self, payload: bytes, signature: bytes) -> None:
        """Self-check a signature without exposing the private key."""

        self.verifier().verify(payload, signature)

    def verifier(self) -> Ed25519CheckpointVerifier:
        return Ed25519CheckpointVerifier(
            self._private_key.public_key(),
            key_id=self.key_id,
        )


__all__ = [
    "ED25519_ALGORITHM",
    "Ed25519CheckpointSigner",
    "Ed25519CheckpointVerifier",
    "derive_ed25519_key_id",
    "ed25519_public_key_is_valid",
]
