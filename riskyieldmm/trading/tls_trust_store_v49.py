"""Hash-pinned, certificate-exact TLS trust stores for transport V4.9.

The signed :class:`~riskyieldmm.trading.operational_manifests_v4.TlsTrustStoreManifestV4`
deliberately contains no deployment pathname.  Operations supplies that path at
admission time; this module pins the exact regular file behind it and refuses to
turn the bundle into TLS authority unless both its byte identity and its parsed
certificate set match the signed manifest.

Each call to :meth:`PinnedTlsTrustStoreV49.build_context` returns a fresh client
context.  The retained object never stores a context or exposes bundle bytes,
and the context is populated only from the admitted bundle (never from ambient
platform roots).
"""

from __future__ import annotations

import hashlib
import os
import ssl
import threading
from typing import Final

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from .canonical import CanonicalizationError, sha256_digest
from .operational_artifact_loading_v4 import (
    PinnedRuntimeArtifactV4,
    RuntimeArtifactSpecV4,
)
from .operational_manifests_v4 import TlsTrustStoreManifestV4

_TLS_CA_DER_DIGEST_SET_DOMAIN: Final = "RiskYieldMMTlsCaDerDigestSetV49"
_PEM_CERTIFICATE_BEGIN: Final = b"-----BEGIN CERTIFICATE-----"
_PEM_CERTIFICATE_END: Final = b"-----END CERTIFICATE-----"
_OUTSIDE_PEM_WHITESPACE: Final = frozenset(b" \t\r\n\f\v")


class TlsTrustStoreV49Error(RuntimeError):
    """The pinned bundle cannot be used as the signed TLS trust store."""


def derive_tls_ca_der_set_root_v49(certificates_der: tuple[bytes, ...]) -> str:
    """Return the domain-separated root of a non-empty unique DER set.

    Member ordering is intentionally irrelevant.  The committed members are
    sorted SHA-256 digests, making the representation canonical without
    retaining certificate order from a presentation-only PEM bundle.
    """

    if type(certificates_der) is not tuple or not certificates_der:
        raise CanonicalizationError("TLS CA DER closure must be a non-empty tuple")
    if any(type(item) is not bytes or not item for item in certificates_der):
        raise CanonicalizationError(
            "TLS CA DER closure contains an unsupported certificate"
        )
    if len(set(certificates_der)) != len(certificates_der):
        raise CanonicalizationError("TLS CA DER closure contains duplicate DER")

    digests = tuple(
        sorted(hashlib.sha256(item).hexdigest() for item in certificates_der)
    )
    if len(set(digests)) != len(digests):  # Defensive collision fail-closed.
        raise CanonicalizationError(
            "TLS CA DER closure contains duplicate certificate digests"
        )
    return sha256_digest(
        {
            "certificate_der_sha256": list(digests),
            "domain": _TLS_CA_DER_DIGEST_SET_DOMAIN,
        }
    )


def _skip_outside_whitespace(payload: bytes, offset: int) -> int:
    while offset < len(payload) and payload[offset] in _OUTSIDE_PEM_WHITESPACE:
        offset += 1
    return offset


def _parse_strict_certificate_bundle(
    payload: bytes,
) -> tuple[tuple[bytes, ...], tuple[bytes, ...]]:
    """Parse only PEM CERTIFICATE blocks separated by ASCII whitespace."""

    certificates_der: list[bytes] = []
    certificate_pem_blocks: list[bytes] = []
    offset = 0
    while True:
        offset = _skip_outside_whitespace(payload, offset)
        if offset == len(payload):
            break
        if not payload.startswith(_PEM_CERTIFICATE_BEGIN, offset):
            raise TlsTrustStoreV49Error(
                "TLS trust-store bundle contains non-certificate content"
            )
        footer = payload.find(
            _PEM_CERTIFICATE_END,
            offset + len(_PEM_CERTIFICATE_BEGIN),
        )
        if footer < 0:
            raise TlsTrustStoreV49Error(
                "TLS trust-store bundle contains an unterminated certificate"
            )
        block_end = footer + len(_PEM_CERTIFICATE_END)
        block = payload[offset:block_end]
        try:
            certificate = x509.load_pem_x509_certificate(block)
        except ValueError as exc:
            raise TlsTrustStoreV49Error(
                "TLS trust-store bundle contains a malformed certificate"
            ) from exc
        certificates_der.append(certificate.public_bytes(serialization.Encoding.DER))
        certificate_pem_blocks.append(block)
        offset = block_end

    if not certificates_der:
        raise TlsTrustStoreV49Error("TLS trust-store bundle contains no certificates")
    result = tuple(certificates_der)
    if len(set(result)) != len(result):
        raise TlsTrustStoreV49Error(
            "TLS trust-store bundle contains duplicate certificate DER"
        )
    return result, tuple(certificate_pem_blocks)


def _validate_manifest_bundle(
    *,
    manifest: TlsTrustStoreManifestV4,
    payload: bytes,
) -> tuple[tuple[bytes, ...], tuple[bytes, ...]]:
    if len(payload) != manifest.ca_bundle_size_bytes:
        raise TlsTrustStoreV49Error(
            "TLS trust-store bundle size differs from signed manifest"
        )
    certificates_der, certificate_pem_blocks = _parse_strict_certificate_bundle(payload)
    if len(certificates_der) != manifest.ca_certificate_count:
        raise TlsTrustStoreV49Error(
            "TLS trust-store certificate count differs from signed manifest"
        )
    if (
        derive_tls_ca_der_set_root_v49(certificates_der)
        != manifest.ca_der_set_root_sha256
    ):
        raise TlsTrustStoreV49Error(
            "TLS trust-store DER set root differs from signed manifest"
        )
    return certificates_der, certificate_pem_blocks


def _new_exact_client_context(
    *,
    manifest: TlsTrustStoreManifestV4,
    certificates_der: tuple[bytes, ...],
    certificate_pem_blocks: tuple[bytes, ...],
) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if any(context.cert_store_stats().values()):
        raise TlsTrustStoreV49Error(
            "fresh TLS client context unexpectedly contains ambient trust roots"
        )

    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    no_compression = getattr(ssl, "OP_NO_COMPRESSION", 0)
    no_ticket = getattr(ssl, "OP_NO_TICKET", 0)
    context.options |= no_compression | no_ticket
    if hasattr(context, "keylog_filename"):
        context.keylog_filename = None

    try:
        # Whitespace between blocks is presentation-only and OpenSSL doesn't
        # accept every ASCII whitespace sequence that the PEM grammar permits.
        # Load each exact admitted CERTIFICATE block, and nothing else.
        for block in certificate_pem_blocks:
            context.load_verify_locations(cadata=block.decode("ascii"))
    except (UnicodeDecodeError, ssl.SSLError) as exc:
        raise TlsTrustStoreV49Error(
            "OpenSSL rejected the exact TLS trust-store bundle"
        ) from exc

    loaded_der = tuple(context.get_ca_certs(binary_form=True))
    loaded_set = set(loaded_der)
    expected_set = set(certificates_der)
    if (
        len(loaded_der) != len(loaded_set)
        or len(loaded_set) != manifest.ca_certificate_count
        or loaded_set != expected_set
        or derive_tls_ca_der_set_root_v49(tuple(loaded_set))
        != manifest.ca_der_set_root_sha256
    ):
        raise TlsTrustStoreV49Error(
            "OpenSSL TLS trust-store differs from the signed DER closure"
        )
    return context


class PinnedTlsTrustStoreV49:
    """Retained bundle authority with no context or byte-export surface."""

    __slots__ = ("_artifact", "_lock", "_manifest")

    def __init__(
        self,
        *,
        manifest: TlsTrustStoreManifestV4,
        artifact: PinnedRuntimeArtifactV4,
    ) -> None:
        if type(manifest) is not TlsTrustStoreManifestV4:
            raise TypeError("manifest must be an exact TlsTrustStoreManifestV4")
        if type(artifact) is not PinnedRuntimeArtifactV4:
            raise TypeError("artifact must be an exact PinnedRuntimeArtifactV4")
        if (
            artifact.spec.sha256 != manifest.ca_bundle_sha256
            or artifact.spec.max_bytes != manifest.ca_bundle_size_bytes
            or artifact.spec.require_executable
        ):
            raise TlsTrustStoreV49Error(
                "pinned TLS trust-store artifact differs from signed manifest"
            )
        artifact.assert_unchanged()
        self._manifest = manifest
        self._artifact = artifact
        self._lock = threading.RLock()

    @classmethod
    def open_verified(
        cls,
        *,
        manifest: TlsTrustStoreManifestV4,
        ca_bundle_path: str | os.PathLike[str],
    ) -> PinnedTlsTrustStoreV49:
        if cls is not PinnedTlsTrustStoreV49:
            raise TypeError("TLS trust-store subclasses are not supported")
        if type(manifest) is not TlsTrustStoreManifestV4:
            raise TypeError("manifest must be an exact TlsTrustStoreManifestV4")
        try:
            path = os.fspath(ca_bundle_path)
        except TypeError as exc:
            raise TypeError("ca_bundle_path must be text or path-like") from exc
        if type(path) is not str:
            raise TypeError("ca_bundle_path must resolve to text")

        artifact: PinnedRuntimeArtifactV4 | None = None
        try:
            artifact = PinnedRuntimeArtifactV4.open_verified(
                RuntimeArtifactSpecV4(
                    path=path,
                    sha256=manifest.ca_bundle_sha256,
                    max_bytes=manifest.ca_bundle_size_bytes,
                )
            )
            payload = artifact.read_bytes()
            certificates_der, certificate_pem_blocks = _validate_manifest_bundle(
                manifest=manifest,
                payload=payload,
            )
            # Admission includes OpenSSL's effective view, not merely a parser
            # check.  The temporary context is deliberately not retained.
            _new_exact_client_context(
                manifest=manifest,
                certificates_der=certificates_der,
                certificate_pem_blocks=certificate_pem_blocks,
            )
            return cls(manifest=manifest, artifact=artifact)
        except BaseException:
            if artifact is not None:
                artifact.close()
            raise

    @property
    def manifest(self) -> TlsTrustStoreManifestV4:
        return self._manifest

    def build_context(self) -> ssl.SSLContext:
        """Build a fresh TLS 1.3 client context from the still-pinned bundle."""

        with self._lock:
            payload = self._artifact.read_bytes()
            certificates_der, certificate_pem_blocks = _validate_manifest_bundle(
                manifest=self._manifest,
                payload=payload,
            )
            return _new_exact_client_context(
                manifest=self._manifest,
                certificates_der=certificates_der,
                certificate_pem_blocks=certificate_pem_blocks,
            )

    def assert_current(self) -> None:
        """Revalidate the path, bytes, certificate closure, and OpenSSL view."""

        with self._lock:
            payload = self._artifact.read_bytes()
            certificates_der, certificate_pem_blocks = _validate_manifest_bundle(
                manifest=self._manifest,
                payload=payload,
            )
            _new_exact_client_context(
                manifest=self._manifest,
                certificates_der=certificates_der,
                certificate_pem_blocks=certificate_pem_blocks,
            )

    def close(self) -> None:
        with self._lock:
            self._artifact.close()


__all__ = [
    "PinnedTlsTrustStoreV49",
    "TlsTrustStoreV49Error",
    "derive_tls_ca_der_set_root_v49",
]
