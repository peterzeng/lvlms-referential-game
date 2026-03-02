"""
Create cleaner, round-oriented CSVs from oTree's all_apps_wide export.

Usage (round-level only):
    python scripts/export_round_level_csv.py data/all_apps_wide-2025-11-17.csv data/round_level_export.csv

Usage (round-level + pair-level):
    python scripts/export_round_level_csv.py data/all_apps_wide-2025-11-17.csv data/round_level_export.csv data/pair_round_level_export.csv

This script:
    - Flattens the wide export into one row per participant per round
    - Uses explicit "round" naming instead of implicit task indices
    - Adds stable identifiers:
        * session_code
        * participant_code
        * pair_id (if available via participant.pair_id)
        * group_id_in_subsession (per-round)
        * group_id_db / participant.group_id_db (if exported via PARTICIPANT_FIELDS)
    - Carries over key analysis fields from referential_task:
        * role (director / matcher)
        * sequence_accuracy
        * task_completed
        * attention_round_q + derived attention_round_correct
        * chat_transcript
        * prolific_participant_id
        * experiment_start_time / experiment_end_time

If a third output path is provided, it also creates a pair-level CSV with
one row per pair per round, combining director and matcher data into a
single wide row for easier reading when there are multiple groups.
"""

import csv
import os
import sys
from collections import defaultdict
from typing import Dict, Any, List, Tuple


REFERENTIAL_APP_NAME = "referential_task"
# Known number of rounds in this app (can be adjusted if session.config.num_rounds differs)
MAX_ROUNDS = 4


# Columns for the pair-level (one row per pair per round) export
PAIR_FIELDNAMES: List[str] = [
    "session_code",
    "pair_id",
    "round",
    "group_id_in_subsession",
    "group_id_db",
    # Participant identifiers
    "director_participant_code",
    "matcher_participant_code",
    "director_id_in_group",
    "matcher_id_in_group",
    "director_prolific_participant_id",
    "matcher_prolific_participant_id",
    # Performance metrics
    "director_sequence_accuracy",
    "matcher_sequence_accuracy",
    "director_task_completed",
    "matcher_task_completed",
    # Attention checks
    "director_attention_round_q",
    "director_attention_round_correct",
    "matcher_attention_round_q",
    "matcher_attention_round_correct",
    # Chat transcripts
    "director_chat_transcript",
    "matcher_chat_transcript",
    # Timing
    "director_experiment_start_time",
    "director_experiment_end_time",
    "matcher_experiment_start_time",
    "matcher_experiment_end_time",
]


def derive_attention_correct(round_number: int, selected: str) -> str:
    """
    Given a round number and the selected attention response (A/B/C/D),
    return "1" if correct, "0" if incorrect, or "" if not applicable.
    Mirrors the logic in RoundAttentionCheck.
    """
    if not selected:
        return ""
    # Correct answers defined in RoundAttentionCheck.before_next_page
    correct_answers = {1: "A", 2: "C", 3: "B"}
    correct = correct_answers.get(round_number)
    if not correct:
        return ""
    return "1" if selected.strip() == correct else "0"


def extract_round_rows(wide_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Expand a single all_apps_wide row into 0..MAX_ROUNDS rows, one per
    referential_task round where the player actually has data.
    """
    session_code = wide_row.get("session.code", "")
    participant_code = wide_row.get("participant.code", "")

    # Stable identifiers exported via PARTICIPANT_FIELDS (if configured)
    pair_id = wide_row.get("participant.pair_id", "")
    participant_group_db = wide_row.get("participant.group_id_db", "")
    participant_group_in_sub = wide_row.get("participant.group_id_in_subsession", "")
    participant_id_in_group = wide_row.get("participant.id_in_group", "")

    prolific_id = wide_row.get("onboarding.1.player.prolific_participant_id", "") or wide_row.get(
        f"{REFERENTIAL_APP_NAME}.1.player.prolific_participant_id", ""
    )

    rows: List[Dict[str, Any]] = []

    for r in range(1, MAX_ROUNDS + 1):
        base_player = f"{REFERENTIAL_APP_NAME}.{r}.player."
        base_group = f"{REFERENTIAL_APP_NAME}.{r}.group."
        base_subsession = f"{REFERENTIAL_APP_NAME}.{r}.subsession."

        # Determine if this round actually exists for this participant
        role = (
            wide_row.get(base_player + "player_role")
            or wide_row.get(base_player + "role")
            or ""
        )
        if not role:
            # No role means this participant did not play this round
            continue

        group_id_in_subsession = (
            wide_row.get(base_group + "id_in_subsession") or participant_group_in_sub
        )
        group_id_db = participant_group_db  # DB id only available via participant field
        round_number = wide_row.get(base_subsession + "round_number") or r

        sequence_accuracy = wide_row.get(base_player + "sequence_accuracy", "")
        task_completed = wide_row.get(base_player + "task_completed", "")
        attention_round_q = wide_row.get(base_player + "attention_round_q", "")
        attention_round_correct = derive_attention_correct(r, attention_round_q)
        chat_transcript = wide_row.get(base_player + "chat_transcript", "")

        experiment_start_time = wide_row.get(base_player + "experiment_start_time", "")
        experiment_end_time = wide_row.get(base_player + "experiment_end_time", "")

        row_out: Dict[str, Any] = {
            "session_code": session_code,
            "participant_code": participant_code,
            "pair_id": pair_id,
            "round": round_number,
            "role": role,
            "group_id_in_subsession": group_id_in_subsession,
            "group_id_db": group_id_db,
            "participant_id_in_group": participant_id_in_group,
            "prolific_participant_id": prolific_id,
            "sequence_accuracy": sequence_accuracy,
            "task_completed": task_completed,
            "attention_round_q": attention_round_q,
            "attention_round_correct": attention_round_correct,
            "chat_transcript": chat_transcript,
            "experiment_start_time": experiment_start_time,
            "experiment_end_time": experiment_end_time,
        }

        rows.append(row_out)

    return rows


def build_pair_round_rows(all_round_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Collapse per-participant round rows into one row per pair per round.

    Each output row has separate columns for director and matcher fields,
    which makes the data much easier to read when there are many groups.
    """
    pairs: Dict[Tuple[str, str, Any, Any], Dict[str, Any]] = {}

    for row in all_round_rows:
        session_code = row.get("session_code", "")
        pair_id = row.get("pair_id", "")
        group_id_in_subsession = row.get("group_id_in_subsession", "")
        group_id_db = row.get("group_id_db", "")
        round_number = row.get("round")

        key = (session_code, pair_id, group_id_in_subsession, round_number)
        if key not in pairs:
            base: Dict[str, Any] = {
                "session_code": session_code,
                "pair_id": pair_id,
                "round": round_number,
                "group_id_in_subsession": group_id_in_subsession,
                "group_id_db": group_id_db,
            }
            # Initialize remaining fields as empty strings
            for field in PAIR_FIELDNAMES:
                if field not in base:
                    base[field] = ""
            pairs[key] = base

        out = pairs[key]
        role = row.get("role", "")
        if role == "director":
            prefix = "director"
        elif role == "matcher":
            prefix = "matcher"
        else:
            # Unknown role; skip
            continue

        out[f"{prefix}_participant_code"] = row.get("participant_code", "")
        out[f"{prefix}_id_in_group"] = row.get("participant_id_in_group", "")
        out[f"{prefix}_prolific_participant_id"] = row.get("prolific_participant_id", "")
        out[f"{prefix}_sequence_accuracy"] = row.get("sequence_accuracy", "")
        out[f"{prefix}_task_completed"] = row.get("task_completed", "")
        out[f"{prefix}_attention_round_q"] = row.get("attention_round_q", "")
        out[f"{prefix}_attention_round_correct"] = row.get("attention_round_correct", "")
        out[f"{prefix}_chat_transcript"] = row.get("chat_transcript", "")
        out[f"{prefix}_experiment_start_time"] = row.get("experiment_start_time", "")
        out[f"{prefix}_experiment_end_time"] = row.get("experiment_end_time", "")

    return list(pairs.values())


def process_wide_csv(input_csv: str, output_csv: str, pair_output_csv: str | None = None) -> None:
    """
    Read an all_apps_wide CSV and write a cleaner, round-level CSV.
    Optionally also write a pair-level CSV (one row per pair per round).
    """
    with open(input_csv, "r", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        all_rows = list(reader)

    if not all_rows:
        print(f"No data found in input CSV: {input_csv}")
        return

    # Build fieldnames from a sample row so we don't forget anything we add later.
    sample_round_rows = extract_round_rows(all_rows[0])
    if sample_round_rows:
        fieldnames = list(sample_round_rows[0].keys())
    else:
        # Fallback in case first row has no referential_task data
        fieldnames = [
            "session_code",
            "participant_code",
            "pair_id",
            "round",
            "role",
            "group_id_in_subsession",
            "group_id_db",
            "participant_id_in_group",
            "prolific_participant_id",
            "sequence_accuracy",
            "task_completed",
            "attention_round_q",
            "attention_round_correct",
            "chat_transcript",
            "experiment_start_time",
            "experiment_end_time",
        ]

    all_round_rows: List[Dict[str, Any]] = []

    with open(output_csv, "w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        total_rows = 0
        for wide_row in all_rows:
            round_rows = extract_round_rows(wide_row)
            for rr in round_rows:
                writer.writerow(rr)
                all_round_rows.append(rr)
                total_rows += 1

    print(f"Created round-level export: {output_csv} ({total_rows} rows)")

    if pair_output_csv:
        pair_rows = build_pair_round_rows(all_round_rows)
        with open(pair_output_csv, "w", encoding="utf-8", newline="") as f_pair:
            writer = csv.DictWriter(f_pair, fieldnames=PAIR_FIELDNAMES)
            writer.writeheader()
            for row in pair_rows:
                writer.writerow(row)
        print(f"Created pair-level export: {pair_output_csv} ({len(pair_rows)} rows)")


def main(argv=None) -> None:
    argv = argv or sys.argv
    if len(argv) < 3:
        print(__doc__)
        print("\nExample:")
        print(
            "  python scripts/export_round_level_csv.py "
            "data/all_apps_wide-2025-11-17.csv data/round_level_export.csv"
        )
        print(
            "  python scripts/export_round_level_csv.py "
            "data/all_apps_wide-2025-11-17.csv data/round_level_export.csv data/pair_round_level_export.csv"
        )
        sys.exit(1)

    input_csv = argv[1]
    output_csv = argv[2]
    pair_output_csv = argv[3] if len(argv) >= 4 else None

    if not os.path.exists(input_csv):
        print(f"Error: Input file '{input_csv}' not found")
        sys.exit(1)

    process_wide_csv(input_csv, output_csv, pair_output_csv)


if __name__ == "__main__":
    main()


