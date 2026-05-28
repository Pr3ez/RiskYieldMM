# Metadata And Lineage

## Purpose

Define metadata required to reproduce regression feature artifacts.

## Current Status

Contract scaffold only.

## Scope

Applies to future `regression_path_features_v1` feature roots and reports.

## Source Of Truth

- Manifest contract: `regression_feature_engineering/core/metadata.py`
- Feature registry contract: `regression_feature_engineering/core/registry.py`
- Feature implementation status: `feature_implementation_todo.md`

## What This Does Not Decide

This document does not introduce an external feature store or catalog.

## Required Manifest Fields

Each future feature root must record:

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
