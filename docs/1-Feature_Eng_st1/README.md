# Feature Engineering - Stage 1

## Overview

This folder contains the modular documentation for feature engineering.
Each part is a separate file for easier navigation and maintenance.

## Document Structure

| File | Description | Status |
|------|-------------|--------|
| [Part_0_Convention.md](Part_0_Convention.md) | Naming conventions, process, design philosophy | ✅ Reference |
| [Part_1_Groups.md](Part_1_Groups.md) | Group/Category definitions and Form Suffixes | ✅ Reference |
| [Part_2_Raw.md](Part_2_Raw.md) | Raw features from API sources (24 features) | ✅ Reference |
| [Part_3_Approved.md](Part_3_Approved.md) | Approved engineered features (67 features) | ✅ Complete |
| [Part_3_Approved2.md](Part_3_Approved2.md) | Approved features Part 2 — Sentiment (3 features) | ✅ Complete |
| [Part_4_Suggestions.md](Part_4_Suggestions.md) | Features under consideration (0 pending) | ✅ All Decided |
| [Part_4_Analysis.md](Part_4_Analysis.md) | Autonomous feature review (all decided) | ✅ Complete |
| [Part_5_Disapproved.md](Part_5_Disapproved.md) | Features not approved (16 rejected, 1 reconsidered) | 📋 Archive |

### Common Structure (All Parts)

Each Part file follows a consistent structure:

1. **Navigation bar** — Links to all Parts for easy navigation
2. **Intro paragraph** — Brief description of what this Part contains
3. **Normalization note** — `_N` = Normalized, `_NN` = Not Normalized
4. **Main content** — Tables, definitions, or feature entries
5. **Cross-References** — Links to related Parts

## Quick Links

**Need to understand naming?** → [Part_0_Convention.md](Part_0_Convention.md)

**Need to check what groups exist?** → [Part_1_Groups.md](Part_1_Groups.md)

**Need to see available raw data?** → [Part_2_Raw.md](Part_2_Raw.md)

**Need to see approved features?** → [Part_3_Approved.md](Part_3_Approved.md) | [Part_3_Approved2.md](Part_3_Approved2.md)

**Need to review/add suggestions?** → [Part_4_Suggestions.md](Part_4_Suggestions.md)

**Need to see why features were rejected?** → [Part_5_Disapproved.md](Part_5_Disapproved.md)

## Workflow

```
New idea → Part_4 (Suggestions) → Discussion → Part_3 (Approved)
                                      ↓
                              Not approved? → Part_5 (Disapproved with reasoning)
```

## Data Context

- **Instrument:** Bybit BTCUSDT Perpetual
- **Timeframe:** 8h bars (3 per day, aligned with funding cycle)
- **Data sources:** Klines, Funding, OI, Mark Price, Index Price, Premium Index, Long/Short Ratio
- **History:** 2021-01-01 to present (L/S Ratio from 2021-05-28)

---

*Last updated: 2025-12-22*
