"""
Process oTree export to create a cleaner, more readable format.
- Filters to only completed rounds (with actual task data)
- Extracts key columns
- Optionally pivots to wide format (one row per participant)
"""
import pandas as pd
import sys
import json

def process_export(input_file, output_file=None, format='long'):
    """
    Process oTree export file.
    
    Args:
        input_file: Path to CSV export
        output_file: Output path (defaults to input_cleaned.xlsx)
        format: 'long' (one row per round) or 'wide' (one row per participant)
    """
    if output_file is None:
        base = input_file.rsplit('.', 1)[0]
        output_file = f"{base}_processed.xlsx"
    
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    print(f"Original shape: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Key columns to extract
    key_cols = [
        'participant.code',
        'player.prolific_participant_id',
        'player.player_role',
        'subsession.round_number',
        'session.code',
        # Task data
        'player.chat_transcript',
        'player.sequence_accuracy',
        'player.completion_time',
        'player.task_completed',
        # Grid/sequence data
        'group.shared_grid',
        'group.matcher_sequence',
        'group.ai_messages',
        # Post-task survey (only filled in round 4)
        'player.partner_capable',
        'player.partner_helpful',
        'player.partner_understood',
        'player.partner_adapted',
        'player.collaboration_improved',
        'player.partner_comment',
        'player.partner_human_vs_ai',
        'player.partner_human_vs_ai_why',
        'player.ai_familiarity',
        'player.ai_usage_frequency',
        'player.ai_used_for_task',
    ]
    
    # Filter to columns that exist
    existing_cols = [c for c in key_cols if c in df.columns]
    missing_cols = [c for c in key_cols if c not in df.columns]
    if missing_cols:
        print(f"Note: {len(missing_cols)} columns not found in data")
    
    df_filtered = df[existing_cols].copy()
    
    # Rename columns to be cleaner
    rename_map = {c: c.split('.')[-1] for c in existing_cols}
    # Handle duplicates in rename (e.g., both player.code and participant.code)
    rename_map['participant.code'] = 'participant_code'
    rename_map['session.code'] = 'session_code'
    rename_map['subsession.round_number'] = 'round_number'
    df_filtered = df_filtered.rename(columns=rename_map)
    
    # Filter to rows with actual task data (non-empty chat or sequence)
    has_data_mask = (
        df_filtered['chat_transcript'].notna() & 
        (df_filtered['chat_transcript'] != '') & 
        (df_filtered['chat_transcript'] != '[]')
    ) | (
        df_filtered['sequence_accuracy'].notna()
    )
    
    df_with_data = df_filtered[has_data_mask].copy()
    print(f"Rows with actual task data: {len(df_with_data)}")
    
    if format == 'wide':
        # Pivot to one row per participant
        print("Pivoting to wide format (one row per participant)...")
        
        # Separate per-round and final-round-only columns
        per_round_cols = ['chat_transcript', 'sequence_accuracy', 'completion_time', 
                         'task_completed', 'shared_grid', 'matcher_sequence', 'ai_messages']
        final_round_cols = ['partner_capable', 'partner_helpful', 'partner_understood',
                           'partner_adapted', 'collaboration_improved', 'partner_comment',
                           'partner_human_vs_ai', 'partner_human_vs_ai_why',
                           'ai_familiarity', 'ai_usage_frequency', 'ai_used_for_task']
        
        # For each participant, get their data across rounds
        participants = df_with_data['participant_code'].unique()
        wide_rows = []
        
        for pcode in participants:
            pdata = df_with_data[df_with_data['participant_code'] == pcode]
            row = {
                'participant_code': pcode,
                'session_code': pdata['session_code'].iloc[0] if 'session_code' in pdata.columns else None,
                'prolific_participant_id': pdata['prolific_participant_id'].iloc[0] if 'prolific_participant_id' in pdata.columns else None,
                'player_role': pdata['player_role'].iloc[0] if 'player_role' in pdata.columns else None,
            }
            
            # Add per-round data
            for round_num in [1, 2, 3, 4]:
                round_data = pdata[pdata['round_number'] == round_num]
                if len(round_data) > 0:
                    for col in per_round_cols:
                        if col in round_data.columns:
                            row[f'r{round_num}_{col}'] = round_data[col].iloc[0]
            
            # Add final round survey data (no round prefix)
            final_data = pdata[pdata['round_number'] == 4]
            if len(final_data) > 0:
                for col in final_round_cols:
                    if col in final_data.columns:
                        row[col] = final_data[col].iloc[0]
            
            wide_rows.append(row)
        
        df_output = pd.DataFrame(wide_rows)
    else:
        df_output = df_with_data
    
    print(f"Output shape: {df_output.shape[0]} rows, {df_output.shape[1]} columns")
    
    # Save
    print(f"Saving to {output_file}...")
    if output_file.endswith('.xlsx'):
        df_output.to_excel(output_file, index=False, engine='openpyxl')
    else:
        df_output.to_csv(output_file, index=False)
    
    print("Done!")
    return df_output

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "custom_export.csv"
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    format_type = sys.argv[3] if len(sys.argv) > 3 else 'long'
    
    process_export(input_file, output_file, format_type)

