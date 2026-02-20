"""
Calculate time taken per round using timestamps from chat messages.

This script reads the Excel files with chat transcripts and calculates the duration
of each round based on the timestamps of the first and last messages.

Outputs a new Excel file with 4 additional columns:
- round_1_time, round_2_time, round_3_time, round_4_time (in hh:mm:ss format)

Usage:
    python scripts/calculate_round_times.py
"""

import pandas as pd
import re
from datetime import datetime, timedelta
from pathlib import Path


def extract_timestamps(chat_text):
    """
    Extract all timestamps from a chat transcript.
    
    Args:
        chat_text: String containing chat messages with timestamps like [HH:MM:SS]
        
    Returns:
        List of datetime.time objects
    """
    if not chat_text or pd.isna(chat_text) or str(chat_text).strip() == '':
        return []
    
    chat_text = str(chat_text)
    
    # Pattern to match timestamps like [HH:MM:SS] or [HH:MM:SS.mmm]
    pattern = r'\[(\d{2}:\d{2}:\d{2})(?:\.\d+)?\]'
    matches = re.findall(pattern, chat_text)
    
    timestamps = []
    for match in matches:
        try:
            t = datetime.strptime(match, '%H:%M:%S').time()
            timestamps.append(t)
        except ValueError:
            continue
    
    return timestamps


def calculate_duration(timestamps):
    """
    Calculate duration between first and last timestamp.
    
    Args:
        timestamps: List of datetime.time objects
        
    Returns:
        timedelta object representing the duration, or None if not enough timestamps
    """
    if len(timestamps) < 2:
        return None
    
    first = timestamps[0]
    last = timestamps[-1]
    
    # Convert time to datetime for calculation (using a dummy date)
    base_date = datetime(2000, 1, 1)
    first_dt = datetime.combine(base_date, first)
    last_dt = datetime.combine(base_date, last)
    
    # Handle case where round might span midnight (unlikely but safe)
    if last_dt < first_dt:
        last_dt += timedelta(days=1)
    
    return last_dt - first_dt


def format_duration(td):
    """
    Format a timedelta as hh:mm:ss.
    
    Args:
        td: timedelta object
        
    Returns:
        String in format hh:mm:ss
    """
    if td is None:
        return ''
    
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


def find_chat_columns(df):
    """
    Find chat transcript columns in the dataframe.
    
    Returns:
        Dictionary mapping round number to list of column names
        (each round may have multiple chat sources like director, matcher, ai_messages)
    """
    chat_cols = {}
    
    for col in df.columns:
        col_lower = col.lower()
        
        # Pattern 1: round1_director_chat_transcript, round2_matcher_chat_transcript, etc.
        match = re.search(r'round(\d+)[_\.]?(director|matcher)?[_\.]?(chat[_\.]?transcript|grid[_\.]?messages|ai[_\.]?messages)', col_lower)
        if match:
            round_num = int(match.group(1))
            if round_num not in chat_cols:
                chat_cols[round_num] = []
            chat_cols[round_num].append(col)
            continue
        
        # Pattern 2: r1_chat_transcript, r2_chat_transcript, etc.
        match = re.search(r'r(\d+)[_\.]?chat[_\.]?transcript', col_lower)
        if match:
            round_num = int(match.group(1))
            if round_num not in chat_cols:
                chat_cols[round_num] = []
            chat_cols[round_num].append(col)
            continue
        
        # Pattern 3: r1_ai_messages, r2_ai_messages, etc.
        match = re.search(r'r(\d+)[_\.]?ai[_\.]?messages', col_lower)
        if match:
            round_num = int(match.group(1))
            if round_num not in chat_cols:
                chat_cols[round_num] = []
            chat_cols[round_num].append(col)
    
    return chat_cols


def process_file(input_path, output_path=None):
    """
    Process an Excel file and add round time columns.
    
    Args:
        input_path: Path to input Excel file
        output_path: Path to output Excel file (defaults to input with _with_times suffix)
    """
    input_path = Path(input_path)
    
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_with_times{input_path.suffix}"
    else:
        output_path = Path(output_path)
    
    print(f"Reading {input_path}...")
    df = pd.read_excel(input_path, engine='openpyxl')
    print(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")
    
    # Find chat transcript columns
    chat_cols = find_chat_columns(df)
    
    if not chat_cols:
        print("\nNo chat transcript columns found with pattern r#_chat_transcript")
        print("Available columns:")
        for col in sorted(df.columns):
            if 'chat' in col.lower() or 'message' in col.lower() or 'transcript' in col.lower():
                print(f"  - {col}")
        return
    
    print(f"\nFound chat columns for rounds: {sorted(chat_cols.keys())}")
    for round_num, cols in sorted(chat_cols.items()):
        print(f"  Round {round_num}: {', '.join(cols)}")
    
    # Calculate round times
    print("\nCalculating round times...")
    
    for round_num in range(1, 5):
        col_name = f'round_{round_num}_time'
        
        if round_num in chat_cols:
            round_cols = chat_cols[round_num]
            
            durations = []
            for idx, row in df.iterrows():
                # Collect all timestamps from all chat columns for this round
                all_timestamps = []
                for chat_col in round_cols:
                    chat_text = row[chat_col]
                    timestamps = extract_timestamps(chat_text)
                    all_timestamps.extend(timestamps)
                
                # Sort all timestamps to get correct first and last
                all_timestamps.sort()
                
                duration = calculate_duration(all_timestamps)
                formatted = format_duration(duration)
                durations.append(formatted)
            
            df[col_name] = durations
            
            # Calculate stats for this round
            valid_durations = [d for d in durations if d]
            print(f"  Round {round_num}: {len(valid_durations)} valid durations calculated")
        else:
            # No data for this round
            df[col_name] = ''
            print(f"  Round {round_num}: No chat transcript column found")
    
    # Save output
    print(f"\nSaving to {output_path}...")
    df.to_excel(output_path, index=False, engine='openpyxl')
    print(f"Done! Added columns: round_1_time, round_2_time, round_3_time, round_4_time")
    
    # Show sample of results
    print("\nSample of round times (first 10 rows):")
    time_cols = [f'round_{i}_time' for i in range(1, 5)]
    print(df[time_cols].head(10).to_string())
    
    return df


def main():
    """Process both Excel files."""
    data_dir = Path(__file__).parent.parent / 'data'
    
    files = [
        'human-matcher-ai-director.xlsx',
        'human-director-ai-matcher.xlsx'
    ]
    
    for filename in files:
        input_path = data_dir / filename
        
        if not input_path.exists():
            print(f"Warning: {input_path} not found, skipping")
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing: {filename}")
        print('='*60)
        
        process_file(input_path)


if __name__ == '__main__':
    main()
