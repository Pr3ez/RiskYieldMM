# Metadata And Lineage

## Purpose

Define metadata required to reproduce regression feature artifacts.

## Current Status

Manifests and feature catalogs are written by
`regression_feature_engineering.materialize_features` for generated
`regression_path_features_v1` roots. Current implementation support covers
Phase 1-9 families. Validation summaries are written by
`regression_feature_engineering.validate_features`.

## Scope

Applies to current and future `regression_path_features_v1` feature roots and
reports.

## Source Of Truth

- Manifest contract: `regression_feature_engineering/core/metadata.py`
- Feature registry contract: `regression_feature_engineering/core/registry.py`
- Feature implementation status: `feature_implementation_todo.md`

## What This Does Not Decide

This document does not introduce an external feature store or catalog.

## Required Manifest Fields

Each feature root must record:

- feature set;
- target variant;
- asset;
- root ID;
- row count;
- duplicate count;
- null feature count;
- schema hash;
- source fingerprint;
- generated timestamp;
- code/config version;
- feature catalog path.

## Required Feature Catalog Fields

Every promoted feature must record:

- feature name;
- family;
- target intent;
- source timeframes;
- source columns;
- availability rule;
- normalization;
- temporal safety notes.

The catalog is the bridge between formula implementation and model review.

## Validation Artifacts

Feature validation writes report-only artifacts under `test_output/`, including:

- per-root `summary.md`;
- per-root `summary.json`;
- per-root feature/target correlation tables;
- per-root feature quality tables;
- asset or all-core `validation_index.csv`.

Generated validation artifacts are ignored by git. Durable conclusions should be
copied into the tracked docs after review.
