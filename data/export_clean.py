"""
Combined export script: extracts key columns from all_apps_wide CSV.
- Per-round accuracy (r1-r4)
- Partner perception questions (round 4 only)
- AI experience questions
- Participant info

Usage: python export_clean.py input.csv [output.xlsx]
"""
import pandas as pd
import sys

def export_clean(input_file, output_file=None):
    """
    Extract key columns from all_apps_wide export into a clean Excel file.
    """
    if output_file is None:
        base = input_file.rsplit('.', 1)[0]
        output_file = f"{base}_clean.xlsx"
    
    print(f"Reading {input_file}...")
    df = pd.read_csv(input_file)
    print(f"Original: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Define columns to extract (in order)
    column_spec = [
        # Participant info
        ('participant.code', 'participant_code'),
        ('onboarding.1.player.prolific_participant_id', 'prolific_id'),
        ('participant.time_started_utc', 'time_started'),
        ('session.code', 'session_code'),
        
        # Role
        ('referential_task.1.player.player_role', 'role'),
        
        # Per-round accuracy
        ('referential_task.1.player.sequence_accuracy', 'r1_accuracy'),
        ('referential_task.2.player.sequence_accuracy', 'r2_accuracy'),
        ('referential_task.3.player.sequence_accuracy', 'r3_accuracy'),
        ('referential_task.4.player.sequence_accuracy', 'r4_accuracy'),
        
        # Per-round completion time
        ('referential_task.1.player.completion_time', 'r1_completion_time'),
        ('referential_task.2.player.completion_time', 'r2_completion_time'),
        ('referential_task.3.player.completion_time', 'r3_completion_time'),
        ('referential_task.4.player.completion_time', 'r4_completion_time'),
        
        # Per-round chat transcripts
        ('referential_task.1.player.chat_transcript', 'r1_transcript'),
        ('referential_task.2.player.chat_transcript', 'r2_transcript'),
        ('referential_task.3.player.chat_transcript', 'r3_transcript'),
        ('referential_task.4.player.chat_transcript', 'r4_transcript'),
        
        # Partner perception (round 4 only - that's when collected)
        ('referential_task.4.player.partner_capable', 'partner_capable'),
        ('referential_task.4.player.partner_helpful', 'partner_helpful'),
        ('referential_task.4.player.partner_understood', 'partner_understood'),
        ('referential_task.4.player.partner_adapted', 'partner_adapted'),
        ('referential_task.4.player.collaboration_improved', 'collaboration_improved'),
        ('referential_task.4.player.partner_comment', 'partner_comment'),
        ('referential_task.4.player.partner_human_vs_ai', 'partner_human_vs_ai'),
        ('referential_task.4.player.partner_human_vs_ai_why', 'partner_human_vs_ai_why'),
        
        # AI experience (round 4)
        ('referential_task.4.player.ai_familiarity', 'ai_familiarity'),
        ('referential_task.4.player.ai_usage_frequency', 'ai_usage_frequency'),
        ('referential_task.4.player.ai_used_for_task', 'ai_used_for_task'),
        
        # AI's perception of human (round 4, group level)
        ('referential_task.4.group.ai_partner_capable', 'ai_partner_capable'),
        ('referential_task.4.group.ai_partner_helpful', 'ai_partner_helpful'),
        ('referential_task.4.group.ai_partner_understood', 'ai_partner_understood'),
        ('referential_task.4.group.ai_partner_adapted', 'ai_partner_adapted'),
        ('referential_task.4.group.ai_collaboration_improved', 'ai_collaboration_improved'),
        ('referential_task.4.group.ai_partner_comment', 'ai_partner_comment'),
    ]
    
    # Build output dataframe
    output_data = {}
    found_cols = []
    missing_cols = []
    
    for orig_col, new_name in column_spec:
        if orig_col in df.columns:
            output_data[new_name] = df[orig_col]
            found_cols.append(new_name)
        else:
            missing_cols.append(orig_col)
    
    df_output = pd.DataFrame(output_data)
    
    print(f"\nOutput: {df_output.shape[0]} rows, {df_output.shape[1]} columns")
    
    if missing_cols:
        print(f"\nNote: {len(missing_cols)} columns not in source data")
    
    # Show fill rates
    print("\nColumn fill rates:")
    for col in df_output.columns:
        non_empty = df_output[col].notna().sum()
        pct = non_empty / len(df_output) * 100
        if pct > 0:
            print(f"  {col}: {non_empty}/{len(df_output)} ({pct:.0f}%)")
    
    # Save
    print(f"\nSaving to {output_file}...")
    df_output.to_excel(output_file, index=False, engine='openpyxl')
    
    print("Done!")
    return df_output

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "human-ai-batch-1.csv"
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    export_clean(input_file, output_file)

