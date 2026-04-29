# Security Policy

## Supported Scope

Security reports are accepted for the current `main` branch of RiskYieldMM.
Historical archives, generated artifacts, local experiment outputs, and old
notebook snapshots are reviewed on a best-effort basis.

This project is research software. It is not a hosted service, trading bot, or
financial-advice product.

## What To Report

Please report:

- exposed credentials, API keys, tokens, or secrets
- unsafe handling of exchange credentials or local configuration
- code paths that could overwrite unexpected files outside the project root
- dependency or native-extension vulnerabilities with a plausible impact
- data-ingestion behavior that could execute untrusted content
- security-relevant issues in GitHub Actions or release tooling, if added later

Do not report model-performance concerns, trading losses, market-risk outcomes,
or ordinary prediction errors as security vulnerabilities.

## How To Report

Prefer GitHub private vulnerability reporting if it is enabled for this
repository.

If private reporting is not enabled, open a minimal public issue that says you
have a security report and asks for a private contact channel. Do not include
exploit details, secrets, tokens, or sensitive file paths in a public issue.

Include:

- affected file, command, or workflow
- impact and realistic attack or misuse scenario
- reproduction steps using synthetic/minimal data where possible
- suggested fix, if known

## Response Expectations

The maintainer will review reports as time allows. Valid reports will be triaged
by impact and reproducibility. Fixes may be released as normal commits unless a
coordinated disclosure process is needed.

## Secret Handling

If a real credential was committed or exposed, rotate it immediately. Removing it
from the latest commit is not enough if it exists in Git history.
