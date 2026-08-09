from __future__ import annotations

import hashlib
import os
import ssl
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.operational_artifact_loading_v4 import (
    OperationalArtifactChangedV4Error,
    OperationalArtifactV4Error,
)
from riskyieldmm.trading.operational_manifests_v4 import (
    TLS_TRUST_STORE_FORMAT,
    TLS_VERIFY_PURPOSE,
    TlsTrustStoreManifestV4,
)
from riskyieldmm.trading.tls_trust_store_v49 import (
    PinnedTlsTrustStoreV49,
    TlsTrustStoreV49Error,
    derive_tls_ca_der_set_root_v49,
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _test_ca(common_name: str, serial_number: int) -> tuple[bytes, bytes]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(serial_number)
        .not_valid_before(datetime(2025, 1, 1, tzinfo=timezone.utc))
        .not_valid_after(datetime(2035, 1, 1, tzinfo=timezone.utc))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key, hashes.SHA256())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM),
        certificate.public_bytes(serialization.Encoding.DER),
    )


def _write_bundle(tmp_path: Path, payload: bytes, name: str = "ca-bundle.pem") -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    path.chmod(0o644)
    return path


def _manifest(
    payload: bytes,
    certificates_der: tuple[bytes, ...],
) -> TlsTrustStoreManifestV4:
    return TlsTrustStoreManifestV4(
        bundle_format=TLS_TRUST_STORE_FORMAT,
        ca_bundle_sha256=_digest(payload),
        ca_bundle_size_bytes=len(payload),
        ca_certificate_count=len(certificates_der),
        ca_der_set_root_sha256=derive_tls_ca_der_set_root_v49(certificates_der),
        openssl_verify_purpose=TLS_VERIFY_PURPOSE,
    )


def _open(
    path: Path,
    manifest: TlsTrustStoreManifestV4,
) -> PinnedTlsTrustStoreV49:
    return PinnedTlsTrustStoreV49.open_verified(
        manifest=manifest,
        ca_bundle_path=path,
    )


def test_der_set_root_is_domain_separated_order_independent_and_unique() -> None:
    first = b"first DER certificate"
    second = b"second DER certificate"

    root = derive_tls_ca_der_set_root_v49((first, second))

    assert root == sha256_digest(
        {
            "certificate_der_sha256": sorted((_digest(first), _digest(second))),
            "domain": "RiskYieldMMTlsCaDerDigestSetV49",
        }
    )
    assert root == derive_tls_ca_der_set_root_v49((second, first))
    assert root != _digest(first + second)
    assert root != derive_tls_ca_der_set_root_v49((first, b"changed certificate"))
    with pytest.raises(CanonicalizationError, match="duplicate DER"):
        derive_tls_ca_der_set_root_v49((first, first))
    with pytest.raises(CanonicalizationError, match="non-empty tuple"):
        derive_tls_ca_der_set_root_v49(())


def test_exact_bundle_builds_fresh_tls13_contexts_with_only_signed_roots(
    tmp_path: Path,
) -> None:
    first_pem, first_der = _test_ca("RiskYieldMM test root one", 1)
    second_pem, second_der = _test_ca("RiskYieldMM test root two", 2)
    payload = b"\n\t" + first_pem + b"\r\n  " + second_pem + b"\n"
    manifest = _manifest(payload, (first_der, second_der))
    path = _write_bundle(tmp_path, payload)
    store = _open(path, manifest)

    try:
        first_context = store.build_context()
        second_context = store.build_context()

        assert store.manifest is manifest
        assert first_context is not second_context
        assert first_context.protocol == ssl.PROTOCOL_TLS_CLIENT
        assert first_context.minimum_version == ssl.TLSVersion.TLSv1_3
        assert first_context.maximum_version == ssl.TLSVersion.TLSv1_3
        assert first_context.verify_mode == ssl.CERT_REQUIRED
        assert first_context.check_hostname is True
        assert first_context.cert_store_stats() == {
            "x509": 2,
            "crl": 0,
            "x509_ca": 2,
        }
        assert set(first_context.get_ca_certs(binary_form=True)) == {
            first_der,
            second_der,
        }
        if hasattr(ssl, "OP_NO_COMPRESSION"):
            assert first_context.options & ssl.OP_NO_COMPRESSION
        if hasattr(ssl, "OP_NO_TICKET"):
            assert first_context.options & ssl.OP_NO_TICKET
        assert first_context.keylog_filename is None
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            assert not first_context.verify_flags & ssl.VERIFY_X509_STRICT
        assert not hasattr(store, "context")
        assert not hasattr(store, "bundle_bytes")
        store.assert_current()
    finally:
        store.close()


def test_bundle_digest_must_match_signed_manifest(tmp_path: Path) -> None:
    pem, der = _test_ca("RiskYieldMM digest root", 10)
    path = _write_bundle(tmp_path, pem)
    manifest = replace(
        _manifest(pem, (der,)), ca_bundle_sha256=_digest(b"x" * len(pem))
    )

    with pytest.raises(
        OperationalArtifactV4Error,
        match="digest differs from signed policy",
    ):
        _open(path, manifest)


def test_bundle_size_must_equal_signed_manifest(tmp_path: Path) -> None:
    pem, der = _test_ca("RiskYieldMM size root", 11)
    path = _write_bundle(tmp_path, pem)
    manifest = replace(_manifest(pem, (der,)), ca_bundle_size_bytes=len(pem) + 1)

    with pytest.raises(TlsTrustStoreV49Error, match="size differs"):
        _open(path, manifest)


def test_certificate_count_must_match_signed_manifest(tmp_path: Path) -> None:
    pem, der = _test_ca("RiskYieldMM count root", 12)
    path = _write_bundle(tmp_path, pem)
    manifest = replace(_manifest(pem, (der,)), ca_certificate_count=2)

    with pytest.raises(TlsTrustStoreV49Error, match="count differs"):
        _open(path, manifest)


def test_der_set_root_must_match_signed_manifest(tmp_path: Path) -> None:
    pem, der = _test_ca("RiskYieldMM root mismatch", 13)
    path = _write_bundle(tmp_path, pem)
    manifest = replace(
        _manifest(pem, (der,)),
        ca_der_set_root_sha256=_digest(b"different DER set"),
    )

    with pytest.raises(TlsTrustStoreV49Error, match="DER set root differs"):
        _open(path, manifest)


@pytest.mark.parametrize(
    "decorate",
    [
        lambda pem: b"# comments are not authority\n" + pem,
        lambda pem: (
            pem + b"-----BEGIN PRIVATE KEY-----\nAA==\n-----END PRIVATE KEY-----\n"
        ),
        lambda pem: pem + b"not whitespace\n",
    ],
    ids=("comment", "other-pem-block", "trailing-text"),
)
def test_bundle_rejects_non_certificate_content(
    tmp_path: Path,
    decorate,
) -> None:
    pem, der = _test_ca("RiskYieldMM strict PEM root", 14)
    payload = decorate(pem)
    path = _write_bundle(tmp_path, payload)
    manifest = _manifest(payload, (der,))

    with pytest.raises(TlsTrustStoreV49Error, match="non-certificate content"):
        _open(path, manifest)


def test_bundle_rejects_malformed_certificate_block(tmp_path: Path) -> None:
    _, der = _test_ca("RiskYieldMM malformed placeholder", 15)
    payload = (
        b"-----BEGIN CERTIFICATE-----\n"
        b"this-is-not-base64-DER\n"
        b"-----END CERTIFICATE-----\n"
    )
    path = _write_bundle(tmp_path, payload)
    manifest = _manifest(payload, (der,))

    with pytest.raises(TlsTrustStoreV49Error, match="malformed certificate"):
        _open(path, manifest)


def test_bundle_rejects_duplicate_certificate_der(tmp_path: Path) -> None:
    pem, der = _test_ca("RiskYieldMM duplicate root", 16)
    payload = pem + pem
    path = _write_bundle(tmp_path, payload)
    manifest = TlsTrustStoreManifestV4(
        bundle_format=TLS_TRUST_STORE_FORMAT,
        ca_bundle_sha256=_digest(payload),
        ca_bundle_size_bytes=len(payload),
        ca_certificate_count=2,
        ca_der_set_root_sha256=derive_tls_ca_der_set_root_v49((der,)),
        openssl_verify_purpose=TLS_VERIFY_PURPOSE,
    )

    with pytest.raises(TlsTrustStoreV49Error, match="duplicate certificate DER"):
        _open(path, manifest)


def test_path_replacement_invalidates_retained_trust_store(tmp_path: Path) -> None:
    pem, der = _test_ca("RiskYieldMM retained root", 17)
    path = _write_bundle(tmp_path, pem)
    store = _open(path, _manifest(pem, (der,)))
    replacement = _write_bundle(tmp_path, pem, name="replacement.pem")
    os.replace(replacement, path)

    try:
        with pytest.raises(OperationalArtifactChangedV4Error):
            store.assert_current()
        with pytest.raises(OperationalArtifactChangedV4Error):
            store.build_context()
    finally:
        store.close()


def test_close_is_idempotent_and_fails_closed(tmp_path: Path) -> None:
    pem, der = _test_ca("RiskYieldMM closed root", 18)
    path = _write_bundle(tmp_path, pem)
    store = _open(path, _manifest(pem, (der,)))

    store.close()
    store.close()

    with pytest.raises(OperationalArtifactChangedV4Error, match="not live"):
        store.assert_current()
    with pytest.raises(OperationalArtifactChangedV4Error, match="not live"):
        store.build_context()
