"""
Clean an oTree all_apps_wide CSV by removing unused (all-blank) columns.

Usage:
    python scripts/clean_all_apps_wide.py data/all_apps_wide-2025-11-18.csv data/all_apps_wide-2025-11-18.cleaned.csv

What this does:
    - Reads the raw oTree "All apps (wide)" CSV export.
    - Detects columns that are completely empty across all rows
      (e.g., deprecated fields, round-specific fields that are never used).
    - Writes a new CSV that keeps only columns with at least one non-empty value.

This does NOT modify the original CSV or change any values; it only drops
truly unused columns to make the file narrower and more readable.
"""

import csv
import os
import sys
from typing import List


def detect_used_columns(rows: List[dict], fieldnames: List[str]) -> List[str]:
    """
    Return the subset of fieldnames that have at least one non-empty value
    across all rows.
    """
    used = []
    for field in fieldnames:
        has_value = any((row.get(field, "") or "").strip() != "" for row in rows)
        if has_value:
            used.append(field)
    return used


def clean_all_apps_wide(input_csv: str, output_csv: str) -> None:
    with open(input_csv, "r", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        rows = list(reader)

    if not rows:
        print(f"No data found in input CSV: {input_csv}")
        return

    original_fields = reader.fieldnames or []
    used_fields = detect_used_columns(rows, original_fields)

    removed_count = len(original_fields) - len(used_fields)

    with open(output_csv, "w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=used_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in used_fields})

    print(
        f"Cleaned all_apps_wide CSV written to: {output_csv} "
        f"(dropped {removed_count} all-blank columns, kept {len(used_fields)})"
    )


def main(argv=None) -> None:
    argv = argv or sys.argv
    if len(argv) < 3:
        print(__doc__)
        print("\nExample:")
        print(
            "  python scripts/clean_all_apps_wide.py "
            "data/all_apps_wide-2025-11-18.csv data/all_apps_wide-2025-11-18.cleaned.csv"
        )
        sys.exit(1)

    input_csv = argv[1]
    output_csv = argv[2]

    if not os.path.exists(input_csv):
        print(f"Error: Input file '{input_csv}' not found")
        sys.exit(1)

    clean_all_apps_wide(input_csv, output_csv)


if __name__ == "__main__":
    main()


