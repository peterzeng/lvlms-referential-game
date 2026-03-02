"""
Export key columns from all_apps_wide CSV.
Always keeps accuracy and partner perception columns, regardless of fill rate.
"""
import pandas as pd
import sys

def export_key_columns(input_file, output_file=None):
    """
    Extract key columns from all_apps_wide export.
    Always includes per-round accuracy and round-4 partner perception.
    """
    if output_file is None:
        base = input_file.rsplit('.', 1)[0]
        output_file = f"{base}_key_columns.xlsx"
    
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    print(f"Original shape: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Define columns to always keep
    key_patterns = [
        # Participant info
        'participant.code',
        'participant.time_started_utc',
        
        # Per-round accuracy (all 4 rounds)
        'referential_task.1.player.sequence_accuracy',
        'referential_task.2.player.sequence_accuracy',
        'referential_task.3.player.sequence_accuracy',
        'referential_task.4.player.sequence_accuracy',
        
        # Per-round completion time
        'referential_task.1.player.completion_time',
        'referential_task.2.player.completion_time',
        'referential_task.3.player.completion_time',
        'referential_task.4.player.completion_time',
        
        # Role (should be same across rounds, just grab round 1)
        'referential_task.1.player.player_role',
        
        # Prolific ID
        'onboarding.1.player.prolific_participant_id',
        
        # Partner perception (ONLY round 4 - that's when they're collected)
        'referential_task.4.player.partner_capable',
        'referential_task.4.player.partner_helpful',
        'referential_task.4.player.partner_understood',
        'referential_task.4.player.partner_adapted',
        'referential_task.4.player.collaboration_improved',
        'referential_task.4.player.partner_comment',
        'referential_task.4.player.partner_human_vs_ai',
        'referential_task.4.player.partner_human_vs_ai_why',
        
        # AI experience questions (round 4)
        'referential_task.4.player.ai_familiarity',
        'referential_task.4.player.ai_usage_frequency',
        'referential_task.4.player.ai_used_for_task',
        
        # AI's perception of human (round 4, group level)
        'referential_task.4.group.ai_partner_capable',
        'referential_task.4.group.ai_partner_helpful',
        'referential_task.4.group.ai_partner_understood',
        'referential_task.4.group.ai_partner_adapted',
        'referential_task.4.group.ai_collaboration_improved',
        'referential_task.4.group.ai_partner_comment',
        
        # Session info
        'session.code',
    ]
    
    # Find columns that exist
    cols_to_keep = [c for c in key_patterns if c in df.columns]
    missing = [c for c in key_patterns if c not in df.columns]
    
    print(f"\nKeeping {len(cols_to_keep)} key columns")
    if missing:
        print(f"Note: {len(missing)} columns not found in data:")
        for m in missing[:5]:
            print(f"  - {m}")
        if len(missing) > 5:
            print(f"  ... and {len(missing) - 5} more")
    
    df_output = df[cols_to_keep].copy()
    
    # Rename columns to be cleaner
    rename_map = {}
    for col in cols_to_keep:
        # Extract meaningful parts
        parts = col.split('.')
        if 'referential_task' in col:
            # Format: referential_task.1.player.field or referential_task.1.group.field
            round_num = parts[1]  # The number after referential_task
            field = parts[-1]
            new_name = f"r{round_num}_{field}"
        elif 'onboarding' in col:
            new_name = parts[-1]
        elif col == 'participant.code':
            new_name = 'participant_code'
        elif col == 'participant.time_started_utc':
            new_name = 'time_started'
        elif col == 'session.code':
            new_name = 'session_code'
        else:
            new_name = parts[-1]
        rename_map[col] = new_name
    
    df_output = df_output.rename(columns=rename_map)
    
    print(f"\nOutput columns:")
    for col in df_output.columns:
        non_empty = df_output[col].notna().sum()
        print(f"  {col}: {non_empty}/{len(df_output)} non-empty")
    
    print(f"\nSaving to {output_file}...")
    if output_file.endswith('.xlsx'):
        df_output.to_excel(output_file, index=False, engine='openpyxl')
    else:
        df_output.to_csv(output_file, index=False)
    
    print("Done!")
    return df_output

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "human-ai-batch-1.csv"
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    export_key_columns(input_file, output_file)

