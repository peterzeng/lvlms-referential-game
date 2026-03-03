#!/usr/bin/env python3
"""
Consolidate all_apps_wide CSV files and merge director/matcher rows into single pair rows.

This script:
1. Loads all all_apps_wide-*.csv files from the data directory
2. Groups rows by pair_id (participant.pair_id)
3. Merges director and matcher rows into a single row per pair
4. Handles the 4 rounds of referential_task data

The output has:
- Pair-level identifiers (pair_id, session, etc.)
- Session/group-level data (shared between participants)
- Director-specific columns with 'director_' prefix
- Matcher-specific columns with 'matcher_' prefix
- Round data for each round (1-4)

Survey questions (partner_capable, partner_human_vs_ai, etc.) are only collected in round 4.
"""

import csv
import glob
import os
from collections import defaultdict
from datetime import datetime


def get_all_csv_files(data_dir):
    """Get all all_apps_wide CSV files sorted by date."""
    pattern = os.path.join(data_dir, 'all_apps_wide*.csv')
    files = glob.glob(pattern)
    return sorted(files)


def determine_role(row):
    """
    Determine if a row is director or matcher based on player_role.
    We use referential_task.1.player.player_role as the primary indicator.
    """
    # Check round 1 player_role first
    role = row.get('referential_task.1.player.player_role', '')
    if role:
        return role.lower()
    
    # Fallback: check partner_role (if partner is matcher, this person is director)
    partner_role = row.get('participant.partner_role', '')
    if partner_role == 'matcher':
        return 'director'
    elif partner_role == 'director':
        return 'matcher'
    
    return None


def get_column_categories(columns):
    """Categorize columns into different types."""
    categories = {
        'participant': [],
        'session': [],
        'onboarding': [],
        'round_player': {1: [], 2: [], 3: [], 4: []},
        'round_group': {1: [], 2: [], 3: [], 4: []},
    }
    
    for col in columns:
        if col.startswith('participant.'):
            categories['participant'].append(col)
        elif col.startswith('session.'):
            categories['session'].append(col)
        elif col.startswith('onboarding.'):
            categories['onboarding'].append(col)
        else:
            for r in [1, 2, 3, 4]:
                if col.startswith(f'referential_task.{r}.'):
                    if '.player.' in col:
                        categories['round_player'][r].append(col)
                    elif '.group.' in col or '.subsession.' in col:
                        categories['round_group'][r].append(col)
    
    return categories


def merge_pair_rows(director_row, matcher_row, all_columns):
    """Merge director and matcher rows into a single pair row."""
    merged = {}
    categories = get_column_categories(all_columns)
    
    # Use director row as base for pair-level info
    base_row = director_row if director_row else matcher_row
    
    # === PAIR IDENTIFIERS ===
    merged['pair_id'] = base_row.get('participant.pair_id', '')
    merged['session_code'] = base_row.get('session.code', '')
    merged['session_config_name'] = base_row.get('session.config.name', '')
    merged['session_config_basket_set'] = base_row.get('session.config.basket_set', '')
    merged['session_config_director_view'] = base_row.get('session.config.director_view', '')
    
    # === DIRECTOR INFO ===
    if director_row:
        merged['director_participant_code'] = director_row.get('participant.code', '')
        merged['director_time_started_utc'] = director_row.get('participant.time_started_utc', '')
        merged['director_prolific_id'] = director_row.get('onboarding.1.player.prolific_participant_id', '')
        merged['director_experiment_start_time'] = director_row.get('onboarding.1.player.experiment_start_time', '')
        merged['director_device_type'] = director_row.get('onboarding.1.player.device_type', '')
        merged['director_user_agent'] = director_row.get('onboarding.1.player.user_agent', '')
        merged['director_screen_width'] = director_row.get('onboarding.1.player.screen_width', '')
        merged['director_screen_height'] = director_row.get('onboarding.1.player.screen_height', '')
        merged['director_is_mobile_detected'] = director_row.get('onboarding.1.player.is_mobile_detected', '')
        merged['director_comprehension_check'] = director_row.get('onboarding.1.player.comprehension_check', '')
    else:
        for key in ['director_participant_code', 'director_time_started_utc', 'director_prolific_id',
                    'director_experiment_start_time', 'director_device_type', 'director_user_agent',
                    'director_screen_width', 'director_screen_height', 'director_is_mobile_detected',
                    'director_comprehension_check']:
            merged[key] = ''
    
    # === MATCHER INFO ===
    if matcher_row:
        merged['matcher_participant_code'] = matcher_row.get('participant.code', '')
        merged['matcher_time_started_utc'] = matcher_row.get('participant.time_started_utc', '')
        merged['matcher_prolific_id'] = matcher_row.get('onboarding.1.player.prolific_participant_id', '')
        merged['matcher_experiment_start_time'] = matcher_row.get('onboarding.1.player.experiment_start_time', '')
        merged['matcher_device_type'] = matcher_row.get('onboarding.1.player.device_type', '')
        merged['matcher_user_agent'] = matcher_row.get('onboarding.1.player.user_agent', '')
        merged['matcher_screen_width'] = matcher_row.get('onboarding.1.player.screen_width', '')
        merged['matcher_screen_height'] = matcher_row.get('onboarding.1.player.screen_height', '')
        merged['matcher_is_mobile_detected'] = matcher_row.get('onboarding.1.player.is_mobile_detected', '')
        merged['matcher_comprehension_check'] = matcher_row.get('onboarding.1.player.comprehension_check', '')
    else:
        for key in ['matcher_participant_code', 'matcher_time_started_utc', 'matcher_prolific_id',
                    'matcher_experiment_start_time', 'matcher_device_type', 'matcher_user_agent',
                    'matcher_screen_width', 'matcher_screen_height', 'matcher_is_mobile_detected',
                    'matcher_comprehension_check']:
            merged[key] = ''
    
    # === ROUND DATA (1-4) ===
    for round_num in [1, 2, 3, 4]:
        prefix = f'round{round_num}'
        task_prefix = f'referential_task.{round_num}'
        
        # Group-level data (shared - use director or matcher row)
        merged[f'{prefix}_shared_grid'] = base_row.get(f'{task_prefix}.group.shared_grid', '')
        merged[f'{prefix}_target_baskets'] = base_row.get(f'{task_prefix}.group.target_baskets', '')
        merged[f'{prefix}_matcher_sequence'] = base_row.get(f'{task_prefix}.group.matcher_sequence', '')
        merged[f'{prefix}_group_id'] = base_row.get(f'{task_prefix}.group.id_in_subsession', '')
        
        # Director-specific round data
        if director_row:
            merged[f'{prefix}_director_player_role'] = director_row.get(f'{task_prefix}.player.player_role', '')
            merged[f'{prefix}_director_grid_messages'] = director_row.get(f'{task_prefix}.player.grid_messages', '')
            merged[f'{prefix}_director_chat_transcript'] = director_row.get(f'{task_prefix}.player.chat_transcript', '')
            merged[f'{prefix}_director_task_completed'] = director_row.get(f'{task_prefix}.player.task_completed', '')
            merged[f'{prefix}_director_completion_time'] = director_row.get(f'{task_prefix}.player.completion_time', '')
            merged[f'{prefix}_director_experiment_end_time'] = director_row.get(f'{task_prefix}.player.experiment_end_time', '')
        else:
            for key in ['player_role', 'grid_messages', 'chat_transcript', 'task_completed', 
                       'completion_time', 'experiment_end_time']:
                merged[f'{prefix}_director_{key}'] = ''
        
        # Matcher-specific round data
        if matcher_row:
            merged[f'{prefix}_matcher_player_role'] = matcher_row.get(f'{task_prefix}.player.player_role', '')
            merged[f'{prefix}_matcher_grid_messages'] = matcher_row.get(f'{task_prefix}.player.grid_messages', '')
            merged[f'{prefix}_matcher_chat_transcript'] = matcher_row.get(f'{task_prefix}.player.chat_transcript', '')
            merged[f'{prefix}_matcher_selected_sequence'] = matcher_row.get(f'{task_prefix}.player.selected_sequence', '')
            merged[f'{prefix}_matcher_task_completed'] = matcher_row.get(f'{task_prefix}.player.task_completed', '')
            merged[f'{prefix}_matcher_sequence_accuracy'] = matcher_row.get(f'{task_prefix}.player.sequence_accuracy', '')
            merged[f'{prefix}_matcher_completion_time'] = matcher_row.get(f'{task_prefix}.player.completion_time', '')
            merged[f'{prefix}_matcher_experiment_end_time'] = matcher_row.get(f'{task_prefix}.player.experiment_end_time', '')
        else:
            for key in ['player_role', 'grid_messages', 'chat_transcript', 'selected_sequence',
                       'task_completed', 'sequence_accuracy', 'completion_time', 'experiment_end_time']:
                merged[f'{prefix}_matcher_{key}'] = ''
    
    # === SURVEY DATA (Round 4 only) ===
    # Director's survey responses about matcher
    if director_row:
        merged['director_partner_capable'] = director_row.get('referential_task.4.player.partner_capable', '') or director_row.get('participant.partner_capable', '')
        merged['director_partner_helpful'] = director_row.get('referential_task.4.player.partner_helpful', '') or director_row.get('participant.partner_helpful', '')
        merged['director_partner_understood'] = director_row.get('referential_task.4.player.partner_understood', '') or director_row.get('participant.partner_understood', '')
        merged['director_partner_adapted'] = director_row.get('referential_task.4.player.partner_adapted', '') or director_row.get('participant.partner_adapted', '')
        merged['director_collaboration_improved'] = director_row.get('referential_task.4.player.collaboration_improved', '') or director_row.get('participant.collaboration_improved', '')
        merged['director_partner_comment'] = director_row.get('referential_task.4.player.partner_comment', '') or director_row.get('participant.partner_comment', '')
        merged['director_partner_human_vs_ai'] = director_row.get('referential_task.4.player.partner_human_vs_ai', '') or director_row.get('participant.partner_human_vs_ai', '')
        merged['director_partner_human_vs_ai_why'] = director_row.get('referential_task.4.player.partner_human_vs_ai_why', '') or director_row.get('participant.partner_human_vs_ai_why', '')
        merged['director_ai_familiarity'] = director_row.get('referential_task.4.player.ai_familiarity', '') or director_row.get('participant.ai_familiarity', '')
        merged['director_ai_usage_frequency'] = director_row.get('referential_task.4.player.ai_usage_frequency', '') or director_row.get('participant.ai_usage_frequency', '')
        merged['director_ai_used_for_task'] = director_row.get('referential_task.4.player.ai_used_for_task', '') or director_row.get('participant.ai_used_for_task', '')
    else:
        for key in ['partner_capable', 'partner_helpful', 'partner_understood', 'partner_adapted',
                   'collaboration_improved', 'partner_comment', 'partner_human_vs_ai',
                   'partner_human_vs_ai_why', 'ai_familiarity', 'ai_usage_frequency', 'ai_used_for_task']:
            merged[f'director_{key}'] = ''
    
    # Matcher's survey responses about director
    if matcher_row:
        merged['matcher_partner_capable'] = matcher_row.get('referential_task.4.player.partner_capable', '') or matcher_row.get('participant.partner_capable', '')
        merged['matcher_partner_helpful'] = matcher_row.get('referential_task.4.player.partner_helpful', '') or matcher_row.get('participant.partner_helpful', '')
        merged['matcher_partner_understood'] = matcher_row.get('referential_task.4.player.partner_understood', '') or matcher_row.get('participant.partner_understood', '')
        merged['matcher_partner_adapted'] = matcher_row.get('referential_task.4.player.partner_adapted', '') or matcher_row.get('participant.partner_adapted', '')
        merged['matcher_collaboration_improved'] = matcher_row.get('referential_task.4.player.collaboration_improved', '') or matcher_row.get('participant.collaboration_improved', '')
        merged['matcher_partner_comment'] = matcher_row.get('referential_task.4.player.partner_comment', '') or matcher_row.get('participant.partner_comment', '')
        merged['matcher_partner_human_vs_ai'] = matcher_row.get('referential_task.4.player.partner_human_vs_ai', '') or matcher_row.get('participant.partner_human_vs_ai', '')
        merged['matcher_partner_human_vs_ai_why'] = matcher_row.get('referential_task.4.player.partner_human_vs_ai_why', '') or matcher_row.get('participant.partner_human_vs_ai_why', '')
        merged['matcher_ai_familiarity'] = matcher_row.get('referential_task.4.player.ai_familiarity', '') or matcher_row.get('participant.ai_familiarity', '')
        merged['matcher_ai_usage_frequency'] = matcher_row.get('referential_task.4.player.ai_usage_frequency', '') or matcher_row.get('participant.ai_usage_frequency', '')
        merged['matcher_ai_used_for_task'] = matcher_row.get('referential_task.4.player.ai_used_for_task', '') or matcher_row.get('participant.ai_used_for_task', '')
    else:
        for key in ['partner_capable', 'partner_helpful', 'partner_understood', 'partner_adapted',
                   'collaboration_improved', 'partner_comment', 'partner_human_vs_ai',
                   'partner_human_vs_ai_why', 'ai_familiarity', 'ai_usage_frequency', 'ai_used_for_task']:
            merged[f'matcher_{key}'] = ''
    
    return merged


def process_files(data_dir, output_file=None, deduplicate=True):
    """
    Process all CSV files and consolidate pairs.
    
    Args:
        data_dir: Directory containing the all_apps_wide CSV files
        output_file: Output CSV file path (default: consolidated_pairs.csv in data_dir)
        deduplicate: If True, keep only the most recent version of each pair
    
    Returns:
        List of merged pair dictionaries
    """
    files = get_all_csv_files(data_dir)
    print(f"Found {len(files)} CSV files to process")
    
    all_pairs = {}  # pair_id -> {'director': row, 'matcher': row, 'source_file': str}
    all_columns = set()
    
    for filepath in files:
        filename = os.path.basename(filepath)
        print(f"\nProcessing: {filename}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            all_columns.update(columns)
            
            rows = list(reader)
            print(f"  Rows: {len(rows)}")
            
            # Group by pair_id
            file_pairs = defaultdict(list)
            for row in rows:
                pair_id = row.get('participant.pair_id', '')
                if pair_id:
                    file_pairs[pair_id].append(row)
            
            print(f"  Pairs with pair_id: {len(file_pairs)}")
            
            # Process each pair
            for pair_id, members in file_pairs.items():
                director_row = None
                matcher_row = None
                
                for member in members:
                    role = determine_role(member)
                    if role == 'director':
                        director_row = member
                    elif role == 'matcher':
                        matcher_row = member
                
                # Store or update pair (later files override earlier ones if deduplicating)
                if deduplicate:
                    all_pairs[pair_id] = {
                        'director': director_row,
                        'matcher': matcher_row,
                        'source_file': filename
                    }
                else:
                    # Create unique key for non-deduplicated mode
                    unique_key = f"{pair_id}_{filename}"
                    all_pairs[unique_key] = {
                        'director': director_row,
                        'matcher': matcher_row,
                        'source_file': filename
                    }
    
    print(f"\n{'='*60}")
    print(f"Total unique pairs: {len(all_pairs)}")
    
    # Merge pairs
    merged_pairs = []
    all_columns = sorted(list(all_columns))
    
    for pair_key, pair_data in all_pairs.items():
        merged = merge_pair_rows(
            pair_data['director'],
            pair_data['matcher'],
            all_columns
        )
        merged['source_file'] = pair_data['source_file']
        merged_pairs.append(merged)
    
    # Sort by pair_id
    merged_pairs.sort(key=lambda x: x.get('pair_id', ''))
    
    # Write output
    if output_file is None:
        output_file = os.path.join(data_dir, 'consolidated_pairs.csv')
    
    if merged_pairs:
        # Get column order
        output_columns = list(merged_pairs[0].keys())
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=output_columns)
            writer.writeheader()
            writer.writerows(merged_pairs)
        
        print(f"\nOutput written to: {output_file}")
        print(f"Total pairs: {len(merged_pairs)}")
        print(f"Columns: {len(output_columns)}")
    
    return merged_pairs


def print_summary(merged_pairs):
    """Print a summary of the consolidated data."""
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    # Count pairs with complete data
    complete_pairs = sum(1 for p in merged_pairs 
                        if p.get('director_participant_code') and p.get('matcher_participant_code'))
    director_only = sum(1 for p in merged_pairs 
                       if p.get('director_participant_code') and not p.get('matcher_participant_code'))
    matcher_only = sum(1 for p in merged_pairs 
                      if not p.get('director_participant_code') and p.get('matcher_participant_code'))
    
    print(f"Complete pairs (both roles): {complete_pairs}")
    print(f"Director only: {director_only}")
    print(f"Matcher only: {matcher_only}")
    
    # Count by session config
    configs = defaultdict(int)
    for p in merged_pairs:
        config = p.get('session_config_name', 'unknown')
        configs[config] += 1
    
    print(f"\nPairs by session config:")
    for config, count in sorted(configs.items()):
        print(f"  {config}: {count}")
    
    # Count completed tasks
    completed_round4 = sum(1 for p in merged_pairs 
                          if p.get('round4_matcher_task_completed') == '1')
    print(f"\nPairs that completed round 4: {completed_round4}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Consolidate all_apps_wide CSV files into pair-level data')
    parser.add_argument('--data-dir', '-d', default='.', 
                       help='Directory containing the CSV files (default: current directory)')
    parser.add_argument('--output', '-o', default=None,
                       help='Output file path (default: consolidated_pairs.csv in data dir)')
    parser.add_argument('--no-dedupe', action='store_true',
                       help='Keep all versions of pairs (default: keep only most recent)')
    parser.add_argument('--summary', '-s', action='store_true',
                       help='Print summary statistics')
    
    args = parser.parse_args()
    
    # Resolve data directory
    data_dir = os.path.abspath(args.data_dir)
    if not os.path.exists(data_dir):
        print(f"Error: Directory not found: {data_dir}")
        exit(1)
    
    merged_pairs = process_files(
        data_dir,
        output_file=args.output,
        deduplicate=not args.no_dedupe
    )
    
    if args.summary:
        print_summary(merged_pairs)

