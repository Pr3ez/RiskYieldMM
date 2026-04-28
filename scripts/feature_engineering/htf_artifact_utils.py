from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import polars as pl

PathSerializer = Callable[[Path], str]
LoggerFn = Callable[[str], None]


def _identity_path(path: Path) -> str:
    return str(path)


def load_json_safe(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except Exception:
        return None


def fingerprint_paths(
    paths: Sequence[Path],
    *,
    path_serializer: PathSerializer | None = None,
    include_paths: bool = False,
    include_summary_stats: bool = False,
) -> dict[str, Any]:
    serializer = path_serializer or _identity_path
    entries: list[tuple[str, int, int]] = []
    for path in sorted({Path(p) for p in paths}, key=lambda p: str(p)):
        if not path.exists():
            continue
        stat = path.stat()
        entries.append((serializer(path), int(stat.st_mtime_ns), int(stat.st_size)))

    digest = hashlib.sha256()
    for item in entries:
        digest.update(f"{item[0]}|{item[1]}|{item[2]}\n".encode("utf-8"))

    payload: dict[str, Any] = {
        "count": int(len(entries)),
        "digest": digest.hexdigest(),
    }
    if include_paths:
        payload["paths"] = [item[0] for item in entries]
    if include_summary_stats:
        payload["latest_mtime_ns"] = int(max((entry[1] for entry in entries), default=0))
        payload["total_size_bytes"] = int(sum(entry[2] for entry in entries))
    return payload


def fingerprint_batch_dir(
    directory: Path,
    *,
    path_serializer: PathSerializer | None = None,
    include_paths: bool = False,
    include_summary_stats: bool = False,
) -> dict[str, Any]:
    return fingerprint_paths(
        sorted(directory.glob("batch_*.parquet")),
        path_serializer=path_serializer,
        include_paths=include_paths,
        include_summary_stats=include_summary_stats,
    )


def schema_columns_for_batch_dir(directory: Path) -> list[str]:
    files = sorted(directory.glob("batch_*.parquet"))
    if not files:
        return []
    return pl.scan_parquet(str(files[0])).collect_schema().names()


def find_batch_missing_required_columns(
    directory: Path,
    required_cols: set[str],
    *,
    path_serializer: PathSerializer | None = None,
) -> dict[str, Any] | None:
    serializer = path_serializer or _identity_path
    for batch_path in sorted(directory.glob("batch_*.parquet")):
        cols = set(pl.scan_parquet(str(batch_path)).collect_schema().names())
        missing = sorted(required_cols - cols)
        if missing:
            return {"path": serializer(batch_path), "missing": missing}
    return None


def clear_artifact_target(
    path: Path,
    *,
    path_serializer: PathSerializer | None = None,
) -> list[str]:
    serializer = path_serializer or _identity_path
    removed: list[str] = []
    if not path.exists():
        return removed

    if path.is_dir():
        for child in sorted(path.iterdir(), key=lambda p: p.name):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed.append(serializer(child))
        return removed

    path.unlink()
    removed.append(serializer(path))
    return removed


def artifact_rebuild_reasons(
    *,
    meta_path: Path,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict[str, Any],
    schema_columns: list[str] | None = None,
) -> list[str]:
    meta = load_json_safe(meta_path)
    if meta is None:
        return ["missing_meta"]

    reasons: list[str] = []
    if meta.get("artifact_version") != artifact_version:
        reasons.append("artifact_version")
    if meta.get("family") != family:
        reasons.append("family")
    if meta.get("timeframe") != timeframe:
        reasons.append("timeframe")
    if meta.get("source_fingerprint") != source_fingerprint:
        reasons.append("source_fingerprint")
    if schema_columns is not None and sorted(meta.get("schema_columns", [])) != sorted(
        schema_columns
    ):
        reasons.append("schema_columns")
    return reasons


def artifact_meta_payload(
    *,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict[str, Any],
    schema_columns: list[str],
    rebuild_mode: str,
    extra: dict[str, Any] | None = None,
    updated_at_mode: str = "offset",
) -> dict[str, Any]:
    if updated_at_mode == "z":
        updated_at = f"{datetime.utcnow().isoformat()}Z"
    else:
        updated_at = datetime.now(timezone.utc).isoformat()

    payload: dict[str, Any] = {
        "artifact_version": artifact_version,
        "family": family,
        "timeframe": timeframe,
        "source_fingerprint": source_fingerprint,
        "schema_columns": schema_columns,
        "rebuild_mode": rebuild_mode,
        "updated_at": updated_at,
    }
    if extra:
        payload.update(extra)
    return payload


def prepare_stage_rebuild(
    *,
    stage_name: str,
    meta_path: Path,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict[str, Any],
    schema_columns: list[str],
    output_targets: list[Path],
    inspect_batch_dir: Path | None = None,
    required_batch_columns: set[str] | None = None,
    full_rebuild_reasons: set[str] | None = None,
    path_serializer: PathSerializer | None = None,
    log: LoggerFn | None = None,
) -> tuple[list[str], str]:
    reasons = artifact_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=artifact_version,
        family=family,
        timeframe=timeframe,
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
    )

    legacy_schema = None
    if inspect_batch_dir is not None and required_batch_columns:
        if inspect_batch_dir.exists() and list(inspect_batch_dir.glob("batch_*.parquet")):
            legacy_schema = find_batch_missing_required_columns(
                inspect_batch_dir,
                required_batch_columns,
                path_serializer=path_serializer,
            )
            if legacy_schema is not None:
                reasons.append(
                    "legacy_schema:"
                    f"{legacy_schema['path']} missing={','.join(legacy_schema['missing'])}"
                )

    def _reason_key(reason: str) -> str:
        return "legacy_schema" if reason.startswith("legacy_schema:") else reason

    destructive_reason_keys = (
        {_reason_key(reason) for reason in reasons}
        if full_rebuild_reasons is None
        else set(full_rebuild_reasons)
    )
    should_full_rebuild = any(
        _reason_key(reason) in destructive_reason_keys for reason in reasons
    )

    rebuild_mode = "full" if should_full_rebuild else "incremental_tail"
    if should_full_rebuild:
        for target in output_targets:
            clear_artifact_target(target, path_serializer=path_serializer)

    if log is not None:
        if should_full_rebuild:
            log(f"  {stage_name} rebuild mode: full ({', '.join(reasons)})")
        elif reasons:
            log(f"  {stage_name} rebuild mode: incremental_tail ({', '.join(reasons)})")
        else:
            log(f"  {stage_name} rebuild mode: incremental_tail")

    return reasons, rebuild_mode
