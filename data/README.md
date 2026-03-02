# Data Processing Pipeline

This directory contains scripts and data for processing oTree experiment exports from Human-VLM referential task sessions.

## Quick Start

```bash
# Step 1: Export data from oTree Admin → Data → "All apps - wide format" (CSV)

# Step 2: Convert to pairs format
python convert_to_pairs_format.py all_apps_wide-YYYY-MM-DD.csv

# Step 3: Generate visual reports
python generate_pair_report.py -i exports_YYYY-MM-DD/all_apps_wide-YYYY-MM-DD_pairs.xlsx
```

## Pipeline Overview

```
┌─────────────────────────────────┐
│  oTree Admin Export             │
│  (all_apps_wide.csv)            │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│  convert_to_pairs_format.py     │  Converts wide format → pairs format
│  Output: exports_*/..._pairs.xlsx │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│  generate_pair_report.py        │  Creates visual reports
│  Output: pair_reports/          │
└─────────────────────────────────┘
```

---

## Scripts

### `convert_to_pairs_format.py`

Converts oTree's "all_apps_wide" CSV export into a standardized pairs format suitable for analysis.

**What it does:**
- Restructures data so each row represents one human-AI pair session
- Extracts per-round data (grids, sequences, transcripts, accuracy)
- Separates director vs matcher role data into labeled columns
- Handles both AI-as-director and AI-as-matcher configurations

**Usage:**
```bash
# Basic usage (creates dated output folder)
python convert_to_pairs_format.py all_apps_wide-2025-12-30.csv

# Specify custom output file
python convert_to_pairs_format.py all_apps_wide-2025-12-30.csv output.xlsx
```

**Input:** oTree CSV export (`all_apps_wide-*.csv`)

**Output:** Excel file in `exports_YYYY-MM-DD/` folder:
- `<input_filename>_pairs.xlsx`

**Output columns include:**
| Category | Example Columns |
|----------|-----------------|
| Session | `session_code`, `session_config_name`, `prompt_version`, `reasoning_level` |
| Director | `director_participant_code`, `director_prolific_id`, `director_device_type` |
| Matcher | `matcher_participant_code`, `matcher_prolific_id`, `matcher_device_type` |
| Per-Round | `round1_shared_grid`, `round1_target_baskets`, `round1_matcher_sequence`, `round1_matcher_sequence_accuracy` |
| AI Data | `round1_ai_messages`, `round1_ai_reasoning_log`, `round1_ai_partial_sequence` |
| Perceptions | `director_partner_capable`, `matcher_partner_human_vs_ai`, etc. |

---

### `generate_pair_report.py`

Generates visual reports for each human-AI pair session, making it easy to review task performance and dialogue.

**What it does:**
- Creates side-by-side grid comparisons (Director's target vs Matcher's sequence)
- Highlights correct/incorrect basket placements in green/red
- Generates formatted transcript files with all rounds

**Usage:**
```bash
# Process all pairs in a file
python generate_pair_report.py -i exports_2025-12-30/all_apps_wide-2025-12-30_pairs.xlsx

# Process a specific participant by Prolific ID
python generate_pair_report.py -i input.xlsx --pair-id 5f8a2b3c4d5e6f7g

# Specify custom output directory
python generate_pair_report.py -i input.xlsx -o my_reports/
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `-i, --input` | Path to pairs Excel file (required) |
| `-o, --output` | Output directory (default: `data/pair_reports/<filename>_<date>/`) |
| `-p, --pair-id` | Process only a specific pair ID |
| `-r, --rounds` | Number of rounds to process (default: 4) |
| `--images-dir` | Path to basket images (default: auto-detect) |

**Output structure:**
```
pair_reports/
└── all_apps_wide-2025-12-30_pairs_2025-12-30/
    ├── 5f8a2b3c4d5e6f7g/          # Prolific participant ID
    │   ├── round_1_comparison.png
    │   ├── round_2_comparison.png
    │   ├── round_3_comparison.png
    │   ├── round_4_comparison.png
    │   └── transcript.txt
    ├── 6g7h8i9j0k1l2m3n/
    │   └── ...
    └── ...
```

**Sample output:**
- `round_X_comparison.png` - Side-by-side grids showing Director's target sequence and Matcher's submitted sequence with accuracy highlighting
- `transcript.txt` - Full dialogue transcript with timestamps, accuracy scores, and session metadata

> **Note:** Directories are named by the human participant's Prolific ID for easy searching. Falls back to oTree participant code if Prolific ID is unavailable.

---

### `clean_wide_export.py` (Optional)

Utility script to clean up the raw oTree export by removing mostly-empty columns.

**Usage:**
```bash
python clean_wide_export.py all_apps_wide.csv
python clean_wide_export.py all_apps_wide.csv cleaned_output.xlsx
```

**Options:**
- Default threshold: removes columns that are >90% empty
- Useful for exploratory analysis of the raw data

---

## Directory Structure

```
data/
├── README.md                          # This file
├── convert_to_pairs_format.py         # Step 2: Convert to pairs
├── generate_pair_report.py            # Step 3: Generate reports
├── clean_wide_export.py               # Optional: Clean raw export
│
├── all_apps_wide-*.csv                # Raw oTree exports
├── exports_YYYY-MM-DD/                # Converted pairs files
│   └── *_pairs.xlsx
│
├── pair_reports/                      # Generated visual reports
│   └── <filename>_<date>/
│       └── human_ai_X/
│           ├── round_*_comparison.png
│           └── transcript.txt
│
├── chat_transcripts/                  # Individual chat transcript files
└── analyze_human_ai_data.ipynb        # Jupyter notebook for analysis
```

---

## Complete Example Workflow

```bash
# 1. Download export from oTree Admin
#    Go to: Data → All apps - wide format → Download CSV
#    Save as: data/all_apps_wide-2025-12-30.csv

# 2. Navigate to data directory
cd data

# 3. Convert to pairs format
python convert_to_pairs_format.py all_apps_wide-2025-12-30.csv
# Output: exports_2025-12-30/all_apps_wide-2025-12-30_pairs.xlsx

# 4. Generate visual reports for all pairs
python generate_pair_report.py -i exports_2025-12-30/all_apps_wide-2025-12-30_pairs.xlsx
# Output: pair_reports/all_apps_wide-2025-12-30_pairs_2025-12-30/

# 5. Review reports (directories named by Prolific ID)
open pair_reports/all_apps_wide-2025-12-30_pairs_2025-12-30/<prolific_id>/transcript.txt
open pair_reports/all_apps_wide-2025-12-30_pairs_2025-12-30/<prolific_id>/round_1_comparison.png
```

---

## Requirements

```
pandas
openpyxl
Pillow
```

Install with:
```bash
pip install pandas openpyxl Pillow
```

---

## Notes

- The scripts assume basket images are located in `../_static/images/` relative to the data directory
- Pairs are labeled by their **Prolific participant ID** for easy searching (falls back to oTree participant code if unavailable)
- Both AI-as-director and AI-as-matcher configurations are supported
- Accuracy is calculated per-round and displayed in the visual comparison images

