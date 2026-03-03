#!/usr/bin/env python3
"""
Consolidate AI-AI experiment CSV files into a format matching consolidated_pairs.csv.

This script:
1. Loads all 5.2-*.csv files (AI-AI data) from the data directory
2. Transforms them to match the consolidated_pairs.csv column structure
3. Adds prompt_version and reasoning_level columns

Files processed:
- 5.2-simple-prompt.csv -> prompt_version=v1, reasoning_level=none
- 5.2-none-reasoning.csv -> prompt_version=v3, reasoning_level=none
- 5.2-low-reasoning.csv -> prompt_version=v3, reasoning_level=low
- 5.2-medium-reasoning.csv -> prompt_version=v3, reasoning_level=medium
- 5.2-high-reasoning.csv -> prompt_version=v3, reasoning_level=high
"""

import csv
import os
from pathlib import Path


# Map file names to prompt version and reasoning level
FILE_CONFIG = {
    '5.2-simple-prompt.csv': {'prompt_version': 'v1', 'reasoning_level': 'none'},
    '5.2-none-reasoning.csv': {'prompt_version': 'v3', 'reasoning_level': 'none'},
    '5.2-low-reasoning.csv': {'prompt_version': 'v3', 'reasoning_level': 'low'},
    '5.2-medium-reasoning.csv': {'prompt_version': 'v3', 'reasoning_level': 'medium'},
    '5.2-high-reasoning.csv': {'prompt_version': 'v3', 'reasoning_level': 'high'},
}


def transform_row(row, prompt_version, reasoning_level, source_file):
    """Transform an AI-AI row to match consolidated_pairs.csv format."""
    
    transformed = {}
    
    # === IDENTIFIERS ===
    # Use session.code as pair_id equivalent for AI-AI
    transformed['pair_id'] = row.get('session.code', '')
    transformed['session_code'] = row.get('session.code', '')
    transformed['session_config_name'] = row.get('session.config.name', '')
    transformed['session_config_basket_set'] = row.get('session.config.basket_set', '')
    transformed['session_config_director_view'] = row.get('session.config.director_view', '')
    
    # === AI-AI SPECIFIC ===
    transformed['prompt_version'] = prompt_version
    transformed['reasoning_level'] = reasoning_level
    
    # === PARTICIPANT INFO (AI doesn't have separate director/matcher participants) ===
    # Use the single participant row data
    transformed['director_participant_code'] = row.get('participant.code', '')
    transformed['director_time_started_utc'] = row.get('participant.time_started_utc', '')
    transformed['director_prolific_id'] = ''  # AI doesn't have prolific IDs
    transformed['director_experiment_start_time'] = ''
    transformed['director_device_type'] = ''
    transformed['director_user_agent'] = ''
    transformed['director_screen_width'] = ''
    transformed['director_screen_height'] = ''
    transformed['director_is_mobile_detected'] = ''
    transformed['director_comprehension_check'] = ''
    
    # Matcher info same as director for AI-AI (same session)
    transformed['matcher_participant_code'] = row.get('participant.code', '')
    transformed['matcher_time_started_utc'] = row.get('participant.time_started_utc', '')
    transformed['matcher_prolific_id'] = ''
    transformed['matcher_experiment_start_time'] = ''
    transformed['matcher_device_type'] = ''
    transformed['matcher_user_agent'] = ''
    transformed['matcher_screen_width'] = ''
    transformed['matcher_screen_height'] = ''
    transformed['matcher_is_mobile_detected'] = ''
    transformed['matcher_comprehension_check'] = ''
    
    # === ROUND DATA (1-4) ===
    for round_num in [1, 2, 3, 4]:
        prefix = f'round{round_num}'
        task_prefix = f'referential_task.{round_num}'
        
        # Group-level data (shared)
        transformed[f'{prefix}_shared_grid'] = row.get(f'{task_prefix}.group.shared_grid', '')
        transformed[f'{prefix}_target_baskets'] = row.get(f'{task_prefix}.group.target_baskets', '')
        transformed[f'{prefix}_matcher_sequence'] = row.get(f'{task_prefix}.group.matcher_sequence', '')
        transformed[f'{prefix}_group_id'] = row.get(f'{task_prefix}.group.id_in_subsession', '')
        
        # Director-specific round data (from player data)
        transformed[f'{prefix}_director_player_role'] = 'director'  # AI plays director role
        transformed[f'{prefix}_director_grid_messages'] = row.get(f'{task_prefix}.player.grid_messages', '')
        transformed[f'{prefix}_director_chat_transcript'] = row.get(f'{task_prefix}.player.chat_transcript', '')
        transformed[f'{prefix}_director_task_completed'] = row.get(f'{task_prefix}.player.task_completed', '')
        transformed[f'{prefix}_director_completion_time'] = row.get(f'{task_prefix}.player.completion_time', '')
        transformed[f'{prefix}_director_experiment_end_time'] = row.get(f'{task_prefix}.player.experiment_end_time', '')
        
        # Matcher-specific round data
        transformed[f'{prefix}_matcher_player_role'] = 'matcher'  # AI plays matcher role
        transformed[f'{prefix}_matcher_grid_messages'] = row.get(f'{task_prefix}.player.grid_messages', '')
        transformed[f'{prefix}_matcher_chat_transcript'] = row.get(f'{task_prefix}.player.chat_transcript', '')
        transformed[f'{prefix}_matcher_selected_sequence'] = row.get(f'{task_prefix}.player.selected_sequence', '')
        transformed[f'{prefix}_matcher_task_completed'] = row.get(f'{task_prefix}.player.task_completed', '')
        transformed[f'{prefix}_matcher_sequence_accuracy'] = row.get(f'{task_prefix}.player.sequence_accuracy', '')
        transformed[f'{prefix}_matcher_completion_time'] = row.get(f'{task_prefix}.player.completion_time', '')
        transformed[f'{prefix}_matcher_experiment_end_time'] = row.get(f'{task_prefix}.player.experiment_end_time', '')
        
        # AI-specific data for this round
        transformed[f'{prefix}_ai_partial_sequence'] = row.get(f'{task_prefix}.group.ai_partial_sequence', '')
        transformed[f'{prefix}_ai_messages'] = row.get(f'{task_prefix}.group.ai_messages', '')
        transformed[f'{prefix}_ai_reasoning_log'] = row.get(f'{task_prefix}.group.ai_reasoning_log', '')
    
    # === SURVEY DATA (Round 4 - AI perceptions) ===
    # Director's perception of matcher (from AI director)
    transformed['director_partner_capable'] = row.get('referential_task.4.group.ai_director_partner_capable', '')
    transformed['director_partner_helpful'] = row.get('referential_task.4.group.ai_director_partner_helpful', '')
    transformed['director_partner_understood'] = row.get('referential_task.4.group.ai_director_partner_understood', '')
    transformed['director_partner_adapted'] = row.get('referential_task.4.group.ai_director_partner_adapted', '')
    transformed['director_collaboration_improved'] = row.get('referential_task.4.group.ai_director_collaboration_improved', '')
    transformed['director_partner_comment'] = row.get('referential_task.4.group.ai_director_partner_comment', '')
    transformed['director_perceptions_raw'] = row.get('referential_task.4.group.ai_director_perceptions_raw', '')
    
    # These fields don't apply to AI-AI
    transformed['director_partner_human_vs_ai'] = ''
    transformed['director_partner_human_vs_ai_why'] = ''
    transformed['director_ai_familiarity'] = ''
    transformed['director_ai_usage_frequency'] = ''
    transformed['director_ai_used_for_task'] = ''
    
    # Matcher's perception of director (from AI matcher)
    transformed['matcher_partner_capable'] = row.get('referential_task.4.group.ai_matcher_partner_capable', '')
    transformed['matcher_partner_helpful'] = row.get('referential_task.4.group.ai_matcher_partner_helpful', '')
    transformed['matcher_partner_understood'] = row.get('referential_task.4.group.ai_matcher_partner_understood', '')
    transformed['matcher_partner_adapted'] = row.get('referential_task.4.group.ai_matcher_partner_adapted', '')
    transformed['matcher_collaboration_improved'] = row.get('referential_task.4.group.ai_matcher_collaboration_improved', '')
    transformed['matcher_partner_comment'] = row.get('referential_task.4.group.ai_matcher_partner_comment', '')
    transformed['matcher_perceptions_raw'] = row.get('referential_task.4.group.ai_matcher_perceptions_raw', '')
    
    # These fields don't apply to AI-AI
    transformed['matcher_partner_human_vs_ai'] = ''
    transformed['matcher_partner_human_vs_ai_why'] = ''
    transformed['matcher_ai_familiarity'] = ''
    transformed['matcher_ai_usage_frequency'] = ''
    transformed['matcher_ai_used_for_task'] = ''
    
    # Source file
    transformed['source_file'] = source_file
    
    return transformed


def process_files(data_dir, output_file=None):
    """
    Process all AI-AI CSV files and consolidate them.
    
    Args:
        data_dir: Directory containing the AI-AI CSV files
        output_file: Output CSV file path (default: consolidated_ai_pairs.csv in data_dir)
    
    Returns:
        List of transformed row dictionaries
    """
    all_rows = []
    
    for filename, config in FILE_CONFIG.items():
        filepath = os.path.join(data_dir, filename)
        
        if not os.path.exists(filepath):
            print(f"Warning: File not found: {filepath}")
            continue
        
        print(f"\nProcessing: {filename}")
        print(f"  Prompt version: {config['prompt_version']}")
        print(f"  Reasoning level: {config['reasoning_level']}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            print(f"  Rows: {len(rows)}")
            
            for row in rows:
                transformed = transform_row(
                    row,
                    config['prompt_version'],
                    config['reasoning_level'],
                    filename
                )
                all_rows.append(transformed)
    
    print(f"\n{'='*60}")
    print(f"Total AI-AI pairs: {len(all_rows)}")
    
    # Write output
    if output_file is None:
        output_file = os.path.join(data_dir, 'consolidated_ai_pairs.csv')
    
    if all_rows:
        # Get column order from first row
        output_columns = list(all_rows[0].keys())
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=output_columns)
            writer.writeheader()
            writer.writerows(all_rows)
        
        print(f"\nOutput written to: {output_file}")
        print(f"Total rows: {len(all_rows)}")
        print(f"Columns: {len(output_columns)}")
    
    return all_rows


def print_summary(rows):
    """Print a summary of the consolidated data."""
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    # Count by prompt version and reasoning level
    from collections import defaultdict
    by_version = defaultdict(int)
    by_reasoning = defaultdict(int)
    by_combo = defaultdict(int)
    
    for row in rows:
        v = row.get('prompt_version', 'unknown')
        r = row.get('reasoning_level', 'unknown')
        by_version[v] += 1
        by_reasoning[r] += 1
        by_combo[f"{v}_{r}"] += 1
    
    print(f"\nBy prompt version:")
    for v, count in sorted(by_version.items()):
        print(f"  {v}: {count}")
    
    print(f"\nBy reasoning level:")
    for r, count in sorted(by_reasoning.items()):
        print(f"  {r}: {count}")
    
    print(f"\nBy combination:")
    for combo, count in sorted(by_combo.items()):
        print(f"  {combo}: {count}")
    
    # Count completed round 4
    completed = sum(1 for r in rows if r.get('round4_matcher_task_completed') == '1')
    print(f"\nCompleted round 4: {completed}")
    
    # Average accuracy per reasoning level
    print(f"\nAverage round 4 accuracy by reasoning level:")
    for r_level in ['none', 'low', 'medium', 'high']:
        accuracies = []
        for row in rows:
            if row.get('reasoning_level') == r_level:
                acc = row.get('round4_matcher_sequence_accuracy', '')
                if acc:
                    try:
                        accuracies.append(float(acc))
                    except ValueError:
                        pass
        if accuracies:
            avg = sum(accuracies) / len(accuracies)
            print(f"  {r_level}: {avg:.2f}% (n={len(accuracies)})")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Consolidate AI-AI CSV files')
    parser.add_argument('--data-dir', '-d', default='.',
                       help='Directory containing the CSV files (default: current directory)')
    parser.add_argument('--output', '-o', default=None,
                       help='Output file path (default: consolidated_ai_pairs.csv in data dir)')
    parser.add_argument('--summary', '-s', action='store_true',
                       help='Print summary statistics')
    
    args = parser.parse_args()
    
    # Resolve data directory
    data_dir = os.path.abspath(args.data_dir)
    if not os.path.exists(data_dir):
        print(f"Error: Directory not found: {data_dir}")
        exit(1)
    
    rows = process_files(data_dir, output_file=args.output)
    
    if args.summary:
        print_summary(rows)


