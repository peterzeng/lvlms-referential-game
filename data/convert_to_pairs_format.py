"""
Convert all_apps_wide CSV to consolidated_pairs format (matching consolidated_ai_pairs.csv structure).
For human-AI sessions: human takes one role, AI takes the other.
"""
import pandas as pd
import sys
import os
from datetime import datetime

def convert_to_pairs(input_file, output_file=None):
    """
    Convert all_apps_wide format to consolidated_pairs format.
    """
    if output_file is None:
        # Create dated output directory
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_dir = f"exports_{date_str}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Get just the filename without path
        input_basename = os.path.basename(input_file).rsplit('.', 1)[0]
        output_file = os.path.join(output_dir, f"{input_basename}_pairs.xlsx")
    
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    print(f"Original: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Filter to participants who actually did the task (have a role assigned)
    df = df[df['referential_task.1.player.player_role'].notna()].copy()
    print(f"Participants with task data: {len(df)}")
    
    if len(df) == 0:
        print("No participants with task data found!")
        return None
    
    rows = []
    for idx, p in df.iterrows():
        human_role = p.get('referential_task.1.player.player_role', '')
        ai_role = 'matcher' if human_role == 'director' else 'director'
        
        # Use Prolific ID as pair_id for easy searching, fall back to participant code or index
        prolific_id = p.get('onboarding.1.player.prolific_participant_id', '')
        if pd.isna(prolific_id) or prolific_id == '':
            prolific_id = p.get('participant.code', f'participant_{idx}')
        
        row = {
            'pair_id': prolific_id,
            'session_code': p.get('session.code', ''),
            'session_config_name': p.get('session.config.name', ''),
            'session_config_basket_set': p.get('session.config.basket_set', ''),
            'session_config_director_view': p.get('session.config.director_view', ''),
            'prompt_version': p.get('session.config.prompt_version', ''),
            'reasoning_level': p.get('session.config.reasoning_level', ''),
            
            # Human takes one role, AI takes the other
            # We'll put human info in director columns if human is director, else in matcher columns
        }
        
        # Determine which columns to populate based on human's role
        if human_role == 'director':
            # Human is director
            row['director_participant_code'] = p.get('participant.code', '')
            row['director_time_started_utc'] = p.get('participant.time_started_utc', '')
            row['director_prolific_id'] = p.get('onboarding.1.player.prolific_participant_id', '')
            row['director_experiment_start_time'] = p.get('onboarding.1.player.experiment_start_time', '')
            row['director_device_type'] = p.get('onboarding.1.player.device_type', '')
            row['director_user_agent'] = p.get('onboarding.1.player.user_agent', '')
            row['director_screen_width'] = p.get('onboarding.1.player.screen_width', '')
            row['director_screen_height'] = p.get('onboarding.1.player.screen_height', '')
            row['director_is_mobile_detected'] = p.get('onboarding.1.player.is_mobile_detected', '')
            row['director_comprehension_check'] = p.get('referential_task.1.player.comprehension_check', '')
            
            # AI is matcher
            row['matcher_participant_code'] = 'AI'
            row['matcher_time_started_utc'] = ''
            row['matcher_prolific_id'] = ''
            row['matcher_experiment_start_time'] = ''
            row['matcher_device_type'] = ''
            row['matcher_user_agent'] = ''
            row['matcher_screen_width'] = ''
            row['matcher_screen_height'] = ''
            row['matcher_is_mobile_detected'] = ''
            row['matcher_comprehension_check'] = ''
        else:
            # Human is matcher
            row['matcher_participant_code'] = p.get('participant.code', '')
            row['matcher_time_started_utc'] = p.get('participant.time_started_utc', '')
            row['matcher_prolific_id'] = p.get('onboarding.1.player.prolific_participant_id', '')
            row['matcher_experiment_start_time'] = p.get('onboarding.1.player.experiment_start_time', '')
            row['matcher_device_type'] = p.get('onboarding.1.player.device_type', '')
            row['matcher_user_agent'] = p.get('onboarding.1.player.user_agent', '')
            row['matcher_screen_width'] = p.get('onboarding.1.player.screen_width', '')
            row['matcher_screen_height'] = p.get('onboarding.1.player.screen_height', '')
            row['matcher_is_mobile_detected'] = p.get('onboarding.1.player.is_mobile_detected', '')
            row['matcher_comprehension_check'] = p.get('referential_task.1.player.comprehension_check', '')
            
            # AI is director
            row['director_participant_code'] = 'AI'
            row['director_time_started_utc'] = ''
            row['director_prolific_id'] = ''
            row['director_experiment_start_time'] = ''
            row['director_device_type'] = ''
            row['director_user_agent'] = ''
            row['director_screen_width'] = ''
            row['director_screen_height'] = ''
            row['director_is_mobile_detected'] = ''
            row['director_comprehension_check'] = ''
        
        # Per-round data
        for round_num in [1, 2, 3, 4]:
            prefix = f'referential_task.{round_num}'
            round_prefix = f'round{round_num}'
            
            # Group-level data (same for both roles)
            row[f'{round_prefix}_shared_grid'] = p.get(f'{prefix}.group.shared_grid', '')
            row[f'{round_prefix}_target_baskets'] = p.get(f'{prefix}.group.target_baskets', '')
            row[f'{round_prefix}_matcher_sequence'] = p.get(f'{prefix}.group.matcher_sequence', '')
            row[f'{round_prefix}_group_id'] = p.get(f'{prefix}.group.id_in_subsession', '')
            
            # AI-specific group data
            row[f'{round_prefix}_ai_partial_sequence'] = p.get(f'{prefix}.group.ai_partial_sequence', '')
            row[f'{round_prefix}_ai_messages'] = p.get(f'{prefix}.group.ai_messages', '')
            row[f'{round_prefix}_ai_reasoning_log'] = p.get(f'{prefix}.group.ai_reasoning_log', '')
            
            if human_role == 'director':
                # Human is director - their data goes in director columns
                row[f'{round_prefix}_director_player_role'] = 'director'
                row[f'{round_prefix}_director_grid_messages'] = p.get(f'{prefix}.player.grid_messages', '')
                row[f'{round_prefix}_director_chat_transcript'] = p.get(f'{prefix}.player.chat_transcript', '')
                row[f'{round_prefix}_director_task_completed'] = p.get(f'{prefix}.player.task_completed', '')
                row[f'{round_prefix}_director_completion_time'] = p.get(f'{prefix}.player.completion_time', '')
                row[f'{round_prefix}_director_experiment_end_time'] = p.get(f'{prefix}.player.experiment_end_time', '')
                
                # AI is matcher
                row[f'{round_prefix}_matcher_player_role'] = 'matcher'
                row[f'{round_prefix}_matcher_grid_messages'] = p.get(f'{prefix}.group.ai_messages', '')  # AI messages
                row[f'{round_prefix}_matcher_chat_transcript'] = ''  # Same as director's transcript
                row[f'{round_prefix}_matcher_selected_sequence'] = p.get(f'{prefix}.player.selected_sequence', '')
                row[f'{round_prefix}_matcher_task_completed'] = p.get(f'{prefix}.player.task_completed', '')
                row[f'{round_prefix}_matcher_sequence_accuracy'] = p.get(f'{prefix}.player.sequence_accuracy', '')
                row[f'{round_prefix}_matcher_completion_time'] = ''
                row[f'{round_prefix}_matcher_experiment_end_time'] = ''
            else:
                # Human is matcher - their data goes in matcher columns
                row[f'{round_prefix}_matcher_player_role'] = 'matcher'
                row[f'{round_prefix}_matcher_grid_messages'] = p.get(f'{prefix}.player.grid_messages', '')
                row[f'{round_prefix}_matcher_chat_transcript'] = p.get(f'{prefix}.player.chat_transcript', '')
                row[f'{round_prefix}_matcher_selected_sequence'] = p.get(f'{prefix}.player.selected_sequence', '')
                row[f'{round_prefix}_matcher_task_completed'] = p.get(f'{prefix}.player.task_completed', '')
                row[f'{round_prefix}_matcher_sequence_accuracy'] = p.get(f'{prefix}.player.sequence_accuracy', '')
                row[f'{round_prefix}_matcher_completion_time'] = p.get(f'{prefix}.player.completion_time', '')
                row[f'{round_prefix}_matcher_experiment_end_time'] = p.get(f'{prefix}.player.experiment_end_time', '')
                
                # AI is director
                row[f'{round_prefix}_director_player_role'] = 'director'
                row[f'{round_prefix}_director_grid_messages'] = p.get(f'{prefix}.group.ai_messages', '')  # AI messages
                row[f'{round_prefix}_director_chat_transcript'] = ''  # Same as matcher's transcript
                row[f'{round_prefix}_director_task_completed'] = ''
                row[f'{round_prefix}_director_completion_time'] = ''
                row[f'{round_prefix}_director_experiment_end_time'] = ''
        
        # Partner perception (from round 4, human only)
        if human_role == 'director':
            row['director_partner_capable'] = p.get('referential_task.4.player.partner_capable', '')
            row['director_partner_helpful'] = p.get('referential_task.4.player.partner_helpful', '')
            row['director_partner_understood'] = p.get('referential_task.4.player.partner_understood', '')
            row['director_partner_adapted'] = p.get('referential_task.4.player.partner_adapted', '')
            row['director_collaboration_improved'] = p.get('referential_task.4.player.collaboration_improved', '')
            row['director_partner_comment'] = p.get('referential_task.4.player.partner_comment', '')
            row['director_perceptions_raw'] = ''
            row['director_partner_human_vs_ai'] = p.get('referential_task.4.player.partner_human_vs_ai', '')
            row['director_partner_human_vs_ai_why'] = p.get('referential_task.4.player.partner_human_vs_ai_why', '')
            row['director_ai_familiarity'] = p.get('referential_task.4.player.ai_familiarity', '')
            row['director_ai_usage_frequency'] = p.get('referential_task.4.player.ai_usage_frequency', '')
            row['director_ai_used_for_task'] = p.get('referential_task.4.player.ai_used_for_task', '')
            
            # AI matcher perceptions (from group level)
            row['matcher_partner_capable'] = p.get('referential_task.4.group.ai_partner_capable', '')
            row['matcher_partner_helpful'] = p.get('referential_task.4.group.ai_partner_helpful', '')
            row['matcher_partner_understood'] = p.get('referential_task.4.group.ai_partner_understood', '')
            row['matcher_partner_adapted'] = p.get('referential_task.4.group.ai_partner_adapted', '')
            row['matcher_collaboration_improved'] = p.get('referential_task.4.group.ai_collaboration_improved', '')
            row['matcher_partner_comment'] = p.get('referential_task.4.group.ai_partner_comment', '')
            row['matcher_perceptions_raw'] = p.get('referential_task.4.group.ai_partner_perceptions_raw', '')
            row['matcher_partner_human_vs_ai'] = ''
            row['matcher_partner_human_vs_ai_why'] = ''
            row['matcher_ai_familiarity'] = ''
            row['matcher_ai_usage_frequency'] = ''
            row['matcher_ai_used_for_task'] = ''
        else:
            row['matcher_partner_capable'] = p.get('referential_task.4.player.partner_capable', '')
            row['matcher_partner_helpful'] = p.get('referential_task.4.player.partner_helpful', '')
            row['matcher_partner_understood'] = p.get('referential_task.4.player.partner_understood', '')
            row['matcher_partner_adapted'] = p.get('referential_task.4.player.partner_adapted', '')
            row['matcher_collaboration_improved'] = p.get('referential_task.4.player.collaboration_improved', '')
            row['matcher_partner_comment'] = p.get('referential_task.4.player.partner_comment', '')
            row['matcher_perceptions_raw'] = ''
            row['matcher_partner_human_vs_ai'] = p.get('referential_task.4.player.partner_human_vs_ai', '')
            row['matcher_partner_human_vs_ai_why'] = p.get('referential_task.4.player.partner_human_vs_ai_why', '')
            row['matcher_ai_familiarity'] = p.get('referential_task.4.player.ai_familiarity', '')
            row['matcher_ai_usage_frequency'] = p.get('referential_task.4.player.ai_usage_frequency', '')
            row['matcher_ai_used_for_task'] = p.get('referential_task.4.player.ai_used_for_task', '')
            
            # AI director perceptions (from group level)
            row['director_partner_capable'] = p.get('referential_task.4.group.ai_partner_capable', '')
            row['director_partner_helpful'] = p.get('referential_task.4.group.ai_partner_helpful', '')
            row['director_partner_understood'] = p.get('referential_task.4.group.ai_partner_understood', '')
            row['director_partner_adapted'] = p.get('referential_task.4.group.ai_partner_adapted', '')
            row['director_collaboration_improved'] = p.get('referential_task.4.group.ai_collaboration_improved', '')
            row['director_partner_comment'] = p.get('referential_task.4.group.ai_partner_comment', '')
            row['director_perceptions_raw'] = p.get('referential_task.4.group.ai_partner_perceptions_raw', '')
            row['director_partner_human_vs_ai'] = ''
            row['director_partner_human_vs_ai_why'] = ''
            row['director_ai_familiarity'] = ''
            row['director_ai_usage_frequency'] = ''
            row['director_ai_used_for_task'] = ''
        
        row['source_file'] = input_file
        rows.append(row)
    
    # Create dataframe with columns in the same order as consolidated_ai_pairs.csv
    column_order = [
        'pair_id', 'session_code', 'session_config_name', 'session_config_basket_set', 
        'session_config_director_view', 'prompt_version', 'reasoning_level',
        'director_participant_code', 'director_time_started_utc', 'director_prolific_id',
        'director_experiment_start_time', 'director_device_type', 'director_user_agent',
        'director_screen_width', 'director_screen_height', 'director_is_mobile_detected',
        'director_comprehension_check',
        'matcher_participant_code', 'matcher_time_started_utc', 'matcher_prolific_id',
        'matcher_experiment_start_time', 'matcher_device_type', 'matcher_user_agent',
        'matcher_screen_width', 'matcher_screen_height', 'matcher_is_mobile_detected',
        'matcher_comprehension_check',
    ]
    
    # Add per-round columns
    for round_num in [1, 2, 3, 4]:
        rp = f'round{round_num}'
        column_order.extend([
            f'{rp}_shared_grid', f'{rp}_target_baskets', f'{rp}_matcher_sequence', f'{rp}_group_id',
            f'{rp}_director_player_role', f'{rp}_director_grid_messages', f'{rp}_director_chat_transcript',
            f'{rp}_director_task_completed', f'{rp}_director_completion_time', f'{rp}_director_experiment_end_time',
            f'{rp}_matcher_player_role', f'{rp}_matcher_grid_messages', f'{rp}_matcher_chat_transcript',
            f'{rp}_matcher_selected_sequence', f'{rp}_matcher_task_completed', f'{rp}_matcher_sequence_accuracy',
            f'{rp}_matcher_completion_time', f'{rp}_matcher_experiment_end_time',
            f'{rp}_ai_partial_sequence', f'{rp}_ai_messages', f'{rp}_ai_reasoning_log',
        ])
    
    # Add perception columns
    column_order.extend([
        'director_partner_capable', 'director_partner_helpful', 'director_partner_understood',
        'director_partner_adapted', 'director_collaboration_improved', 'director_partner_comment',
        'director_perceptions_raw', 'director_partner_human_vs_ai', 'director_partner_human_vs_ai_why',
        'director_ai_familiarity', 'director_ai_usage_frequency', 'director_ai_used_for_task',
        'matcher_partner_capable', 'matcher_partner_helpful', 'matcher_partner_understood',
        'matcher_partner_adapted', 'matcher_collaboration_improved', 'matcher_partner_comment',
        'matcher_perceptions_raw', 'matcher_partner_human_vs_ai', 'matcher_partner_human_vs_ai_why',
        'matcher_ai_familiarity', 'matcher_ai_usage_frequency', 'matcher_ai_used_for_task',
        'source_file',
    ])
    
    df_output = pd.DataFrame(rows)
    
    # Reorder columns (only include columns that exist)
    existing_cols = [c for c in column_order if c in df_output.columns]
    df_output = df_output[existing_cols]
    
    print(f"\nOutput: {df_output.shape[0]} rows, {df_output.shape[1]} columns")
    
    # Save
    print(f"Saving to {output_file}...")
    if output_file.endswith('.xlsx'):
        df_output.to_excel(output_file, index=False, engine='openpyxl')
    else:
        df_output.to_csv(output_file, index=False)
    
    print("Done!")
    return df_output

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "all_apps_wide-2025-12-29 (3).csv"
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    convert_to_pairs(input_file, output_file)

