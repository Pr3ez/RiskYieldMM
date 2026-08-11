#!/usr/bin/env python3
"""Validate the frozen Unicode 15.0.0 sources and normalization oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Final

UNICODE_VERSION: Final = "15.0.0"
COMPONENT_STATUS: Final = "UNICODE_15_0_0_SOURCE_AND_NORMALIZATION_CONFORMANCE"
MAXIMUM_SOURCE_DIRECTORY_BYTES: Final = 8 * 1024 * 1024
EXPECTED_NORMALIZATION_PART_ROW_COUNTS: Final = {
    "@Part0": 25,
    "@Part1": 17_029,
    "@Part2": 1_844,
    "@Part3": 176,
}
EXPECTED_NORMALIZATION_ROW_COUNT: Final = 19_074
EXPECTED_NORMALIZATION_ASSERTION_COUNT: Final = 381_480
SOURCE_SPECS: Final = (
    (
        "CompositionExclusions.txt",
        8_911,
        "3b019c0a33c3140cbc920c078f4f9af2680ba4f71869c8d4de5190667c70b6a3",
    ),
    (
        "DerivedNormalizationProps.txt",
        837_688,
        "d5687a48c95c7d6e1ec59cb29c0f2e8b052018eb069a4371b7368d0561e12a29",
    ),
    (
        "NormalizationTest.txt",
        2_625_136,
        "fb9ac8cc154a80cad6caac9897af55a4e75176af6f4e2bb6edc2bf8b1d57f326",
    ),
    (
        "PropList.txt",
        132_360,
        "e05c0a2811d113dae4abd832884199a3ea8d187ee1b872d8240a788a96540bfd",
    ),
    (
        "ReadMe.txt",
        635,
        "53672c0d0b5185e3cf04c8e970d544c3af81ae7c8eeba0b9cf6d355aa954ae1f",
    ),
    (
        "UnicodeData.txt",
        1_913_704,
        "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73",
    ),
)
_CODE_POINT_RE: Final = re.compile(r"[0-9A-F]{4,6}")
_PART_RE: Final = re.compile(r"@Part[0-9]+")


class UnicodeConformanceError(ValueError):
    """Raised when frozen Unicode evidence or conformance differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UnicodeConformanceError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_exact_regular_file(path: Path, *, expected_bytes: int) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    try:
        metadata_before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(metadata_before.st_mode),
            f"Unicode source {path.name} is not a direct regular file",
        )
        _require(
            metadata_before.st_size == expected_bytes,
            f"Unicode source {path.name} byte count differs",
        )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(expected_bytes + 1)
        metadata_after = os.fstat(descriptor)
        _require(
            (
                metadata_after.st_dev,
                metadata_after.st_ino,
                metadata_after.st_mode,
                metadata_after.st_size,
                metadata_after.st_mtime_ns,
                metadata_after.st_ctime_ns,
            )
            == (
                metadata_before.st_dev,
                metadata_before.st_ino,
                metadata_before.st_mode,
                metadata_before.st_size,
                metadata_before.st_mtime_ns,
                metadata_before.st_ctime_ns,
            ),
            f"Unicode source {path.name} changed while it was read",
        )
        _require(
            len(raw) == expected_bytes,
            f"Unicode source {path.name} changed while it was read",
        )
        return raw
    finally:
        os.close(descriptor)


def _read_frozen_sources(source_directory: Path) -> dict[str, bytes]:
    directory = source_directory.resolve(strict=True)
    _require(directory.is_dir(), "Unicode source path is not a directory")
    expected_names = {item[0] for item in SOURCE_SPECS}
    actual_entries = tuple(directory.iterdir())
    actual_names = {entry.name for entry in actual_entries}
    _require(
        actual_names == expected_names,
        "Unicode source directory has missing or extra entries",
    )
    sources: dict[str, bytes] = {}
    total_bytes = 0
    for source_name, expected_bytes, expected_sha256 in SOURCE_SPECS:
        path = directory / source_name
        total_bytes += expected_bytes
        _require(
            total_bytes <= MAXIMUM_SOURCE_DIRECTORY_BYTES,
            "Unicode source directory exceeds its reviewed byte ceiling",
        )
        raw = _read_exact_regular_file(path, expected_bytes=expected_bytes)
        _require(
            _sha256(raw) == expected_sha256,
            f"Unicode source {source_name} SHA-256 differs",
        )
        sources[source_name] = raw
    return sources


def _decode_code_point_field(value: str, *, line_number: int) -> str:
    tokens = value.split()
    _require(tokens, f"normalization row {line_number} has an empty column")
    code_points: list[int] = []
    for token in tokens:
        _require(
            _CODE_POINT_RE.fullmatch(token) is not None,
            f"normalization row {line_number} has noncanonical code-point text",
        )
        code_point = int(token, 16)
        _require(
            code_point <= 0x10FFFF and not 0xD800 <= code_point <= 0xDFFF,
            f"normalization row {line_number} has a non-scalar code point",
        )
        code_points.append(code_point)
    return "".join(chr(code_point) for code_point in code_points)


def _parse_normalization_rows(
    raw: bytes,
) -> list[tuple[int, str, tuple[str, str, str, str, str]]]:
    text = raw.decode("utf-8")
    _require(
        text.startswith("# NormalizationTest-15.0.0.txt\n"),
        "normalization oracle header differs",
    )
    current_part: str | None = None
    rows: list[tuple[int, str, tuple[str, str, str, str, str]]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        content = line.split("#", 1)[0].strip()
        if not content:
            continue
        if content.startswith("@"):
            _require(
                _PART_RE.fullmatch(content) is not None,
                f"normalization part marker at line {line_number} is invalid",
            )
            current_part = content
            continue
        _require(
            current_part is not None,
            f"normalization row {line_number} precedes a part marker",
        )
        columns = [value.strip() for value in content.split(";")]
        if columns and columns[-1] == "":
            columns.pop()
        _require(
            len(columns) == 5,
            f"normalization row {line_number} does not have five columns",
        )
        decoded = tuple(
            _decode_code_point_field(value, line_number=line_number)
            for value in columns
        )
        rows.append((line_number, current_part, decoded))
    _require(rows, "normalization oracle has no conformance rows")
    return rows


def _validate_normalization_rows(
    rows: list[tuple[int, str, tuple[str, str, str, str, str]]],
) -> int:
    assertion_count = 0
    for line_number, _part, columns in rows:
        c1, c2, c3, c4, c5 = columns
        cases = (
            ("NFC", c1, c2),
            ("NFC", c2, c2),
            ("NFC", c3, c2),
            ("NFC", c4, c4),
            ("NFC", c5, c4),
            ("NFD", c1, c3),
            ("NFD", c2, c3),
            ("NFD", c3, c3),
            ("NFD", c4, c5),
            ("NFD", c5, c5),
            ("NFKC", c1, c4),
            ("NFKC", c2, c4),
            ("NFKC", c3, c4),
            ("NFKC", c4, c4),
            ("NFKC", c5, c4),
            ("NFKD", c1, c5),
            ("NFKD", c2, c5),
            ("NFKD", c3, c5),
            ("NFKD", c4, c5),
            ("NFKD", c5, c5),
        )
        for normalization_form, source, expected in cases:
            _require(
                unicodedata.normalize(normalization_form, source) == expected,
                (
                    f"Unicode {UNICODE_VERSION} {normalization_form} "
                    f"conformance differs at line {line_number}"
                ),
            )
            assertion_count += 1
    return assertion_count


def _build_report(source_directory: Path) -> dict[str, Any]:
    _require(
        unicodedata.unidata_version == UNICODE_VERSION,
        (
            "runtime Unicode database differs: "
            f"expected {UNICODE_VERSION}, got {unicodedata.unidata_version}"
        ),
    )
    sources = _read_frozen_sources(source_directory)
    rows = _parse_normalization_rows(sources["NormalizationTest.txt"])
    part_counts = Counter(part for _line_number, part, _columns in rows)
    _require(
        len(rows) == EXPECTED_NORMALIZATION_ROW_COUNT,
        "normalization oracle row count differs",
    )
    _require(
        dict(part_counts) == EXPECTED_NORMALIZATION_PART_ROW_COUNTS,
        "normalization oracle part counts differ",
    )
    assertion_count = _validate_normalization_rows(rows)
    _require(
        assertion_count == EXPECTED_NORMALIZATION_ASSERTION_COUNT,
        "normalization assertion count differs",
    )
    report = {
        "component_status": COMPONENT_STATUS,
        "normalization_assertion_count": assertion_count,
        "normalization_part_row_counts": dict(sorted(part_counts.items())),
        "normalization_row_count": len(rows),
        "runtime_unicode_version": unicodedata.unidata_version,
        "source_byte_count_by_name": {
            name: len(sources[name]) for name, _size, _digest in SOURCE_SPECS
        },
        "source_count": len(sources),
        "source_sha256_by_name": {
            name: _sha256(sources[name]) for name, _size, _digest in SOURCE_SPECS
        },
        "unicode_version": UNICODE_VERSION,
    }
    report["component_sha256"] = _sha256(_canonical_bytes(report))
    return report


def _parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", required=True, type=Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    namespace = _parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        report = _build_report(namespace.source_directory)
        print(_canonical_bytes(report).decode("utf-8"))
        return 0
    except (OSError, RecursionError, UnicodeError, UnicodeConformanceError) as exc:
        print(f"Unicode 15.0.0 conformance error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
