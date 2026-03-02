"""
Format chat transcript from single-line to multi-line format.

Usage:
    python scripts/format_chat_transcript.py input.txt output.txt
    
Or process all chat columns from a CSV:
    python scripts/format_chat_transcript.py data.csv output_folder/
"""

import re
import sys
import os
import csv
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta


def extract_timestamps_from_transcript(raw_text):
    """
    Extract all timestamps from a chat transcript.
    Returns list of (HH, MM, SS) tuples.
    """
    if not raw_text or not raw_text.strip():
        return []
    
    # Pattern to match timestamps like [HH:MM:SS] or [HH:MM:SS.mmm]
    pattern = r'\[(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?\]'
    matches = re.findall(pattern, raw_text)
    
    timestamps = []
    for match in matches:
        try:
            h, m, s = int(match[0]), int(match[1]), int(match[2])
            timestamps.append((h, m, s))
        except (ValueError, IndexError):
            continue
    
    return timestamps


def calculate_round_duration(raw_text):
    """
    Calculate duration of a round from chat transcript timestamps.
    Returns duration in seconds, or None if unable to calculate.
    """
    timestamps = extract_timestamps_from_transcript(raw_text)
    
    if len(timestamps) < 2:
        return None
    
    # Get first and last timestamps
    first = timestamps[0]
    last = timestamps[-1]
    
    # Create datetime objects (using a dummy date, we only care about time difference)
    # Handle case where time wraps around midnight
    base_date = datetime(2000, 1, 1)
    first_dt = base_date.replace(hour=first[0], minute=first[1], second=first[2])
    last_dt = base_date.replace(hour=last[0], minute=last[1], second=last[2])
    
    # If last time is earlier than first, assume it's the next day
    if last_dt < first_dt:
        last_dt += timedelta(days=1)
    
    duration = (last_dt - first_dt).total_seconds()
    return duration


def format_duration(seconds):
    """
    Format duration in seconds to a human-readable string.
    Returns format like "5m 30s" or "1h 15m 30s"
    """
    if seconds is None:
        return "N/A"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or len(parts) == 0:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


def format_chat_transcript(raw_text):
    """
    Convert single-line chat transcript to multi-line format.
    
    Input:  "[15:59:54] matcher: I am peter  [15:59:57] director: i am groot"
    Output: "[15:59:54] matcher: I am peter\n[15:59:57] director: i am groot"
    """
    if not raw_text or not raw_text.strip():
        return ""
    
    # Pattern to match timestamps like [HH:MM:SS] or [HH:MM:SS.mmm]
    # This splits before each timestamp
    pattern = r'(\[\d{2}:\d{2}:\d{2}(?:\.\d+)?\])'
    
    # Split by the pattern but keep the delimiters (timestamps)
    parts = re.split(pattern, raw_text)
    
    # Reconstruct with newlines
    lines = []
    i = 1  # Start at 1 to skip the first empty string
    while i < len(parts):
        if i + 1 < len(parts):
            # Combine timestamp with its message
            timestamp = parts[i]
            message = parts[i + 1].strip()
            if message:
                lines.append(f"{timestamp} {message}")
            i += 2
        else:
            i += 1
    
    return '\n'.join(lines)


def process_single_file(input_path, output_path):
    """Process a single text file with chat transcript."""
    print(f"Reading from: {input_path}")
    
    with open(input_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    
    formatted = format_chat_transcript(raw_text)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(formatted)
    
    print(f"Formatted transcript saved to: {output_path}")
    print(f"Lines: {len(formatted.splitlines())}")


def process_csv_file(input_csv, output_folder):
    """
    Process CSV to extract transcripts for each pair/group in the basket matching game.
    Combines all rounds into one transcript per pair.
    """
    # Determine output folder and, if possible, nest by date parsed from the
    # input CSV filename (e.g., all_apps_wide-2025-11-21 (1).csv ->
    # <output_folder>/2025-11-21/).
    base_output_folder = Path(output_folder)

    # Try to extract a YYYY-MM-DD date from the input filename.
    csv_name = Path(input_csv).name
    date_match = re.search(r'\d{4}-\d{2}-\d{2}', csv_name)
    if date_match:
        date_str = date_match.group(0)
        base_output_folder = base_output_folder / date_str

    # Ensure the (possibly nested) output directory exists.
    base_output_folder.mkdir(parents=True, exist_ok=True)
    
    print(f"Reading CSV: {input_csv}")
    print(f"Writing transcripts to folder: {base_output_folder}")
    
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    if not rows:
        print("No data found in CSV")
        return
    
    # First pass: collect all participant data
    # Structure: participant_data[session_code][participant_code] = {rounds: {...}, prolific_id: ...}
    participant_data = defaultdict(lambda: defaultdict(lambda: {'rounds': {}, 'prolific_id': ''}))
    
    print(f"Processing {len(rows)} rows...")
    
    for row in rows:
        session_code = row.get('session.code', '')
        if not session_code:
            continue
        
        participant_code = row.get('participant.code', '')
        if not participant_code:
            continue
        
        # Get the prolific participant ID from the onboarding section
        prolific_id = row.get('onboarding.1.player.prolific_participant_id', '')
        participant_data[session_code][participant_code]['prolific_id'] = prolific_id
        
        # Process each round (referential_task.1 through referential_task.4)
        for round_num in range(1, 5):
            # Get the group ID for this round
            group_key = f'referential_task.{round_num}.group.id_in_subsession'
            group_id = row.get(group_key, '')
            
            # Get the chat transcript for this round
            chat_key = f'referential_task.{round_num}.player.chat_transcript'
            chat_transcript = row.get(chat_key, '')
            
            # Get the role for this round
            role_key = f'referential_task.{round_num}.player.player_role'
            role = row.get(role_key, '')
            
            # Get attention check results
            attention_q1 = row.get(f'referential_task.{round_num}.player.attention_q1', '')
            attention_q2 = row.get(f'referential_task.{round_num}.player.attention_q2', '')
            attention_q3 = row.get(f'referential_task.{round_num}.player.attention_q3', '')
            attention_round_q = row.get(f'referential_task.{round_num}.player.attention_round_q', '')
            
            # Get payoff (score)
            payoff = row.get(f'referential_task.{round_num}.player.payoff', '')
            
            # Store round data even if empty
            participant_data[session_code][participant_code]['rounds'][round_num] = {
                'group_id': group_id,
                'transcript': chat_transcript,
                'role': role,
                'task_completed': row.get(f'referential_task.{round_num}.player.task_completed', ''),
                'sequence_accuracy': row.get(f'referential_task.{round_num}.player.sequence_accuracy', ''),
                'payoff': payoff,
                'attention_q1': attention_q1,
                'attention_q2': attention_q2,
                'attention_q3': attention_q3,
                'attention_round_q': attention_round_q,
            }
    
    # Second pass: group participants into pairs based on who played together
    # Structure: pairs[pair_key] = {participants: {...}, rounds: {...}}
    pairs = {}
    processed_participants = set()
    
    for session_code, participants in participant_data.items():
        for participant_code, pdata in participants.items():
            if (session_code, participant_code) in processed_participants:
                continue
            
            # Find this participant's partner for each round
            partners_by_round = {}
            for round_num, round_data in pdata['rounds'].items():
                if not round_data['group_id'] or not round_data['role']:
                    continue
                
                # Find partner in same group for this round
                for other_code, other_data in participants.items():
                    if other_code == participant_code:
                        continue
                    
                    other_round = other_data['rounds'].get(round_num, {})
                    if (other_round.get('group_id') == round_data['group_id'] and
                        other_round.get('role') and
                        other_round['role'] != round_data['role']):
                        partners_by_round[round_num] = other_code
                        break
            
            # If we found any partners, this is a valid pair
            if partners_by_round:
                # Use the most common partner as the pair partner
                partner_code = max(set(partners_by_round.values()), 
                                 key=list(partners_by_round.values()).count)
                
                # Create unique pair key (sorted to avoid duplicates)
                pair_key = f"{session_code}_" + "_".join(sorted([participant_code, partner_code]))
                
                if pair_key not in pairs:
                    pairs[pair_key] = {
                        'session_code': session_code,
                        'participants': {},
                        'rounds': {}
                    }
                    
                    # Store both participants' info
                    for pcode in [participant_code, partner_code]:
                        pinfo = participants[pcode]
                        for round_num, round_data in pinfo['rounds'].items():
                            if round_data['role']:
                                role = round_data['role']
                                pairs[pair_key]['participants'][role] = pcode
                                pairs[pair_key]['participants'][f'{role}_prolific'] = pinfo['prolific_id']
                                
                                # Store round data (use first available transcript, but collect per-player data)
                                if round_num not in pairs[pair_key]['rounds']:
                                    pairs[pair_key]['rounds'][round_num] = {
                                        'group_id': round_data['group_id'],
                                        'transcript': round_data['transcript'],
                                        'task_completed': round_data['task_completed'],
                                        'sequence_accuracy': round_data['sequence_accuracy'],
                                        'player_data': {}  # Store per-player metrics
                                    }
                                
                                # Store per-player data (attention checks, payoff, sequence_accuracy)
                                pairs[pair_key]['rounds'][round_num]['player_data'][role] = {
                                    'payoff': round_data['payoff'],
                                    'sequence_accuracy': round_data['sequence_accuracy'],
                                    'attention_q1': round_data['attention_q1'],
                                    'attention_q2': round_data['attention_q2'],
                                    'attention_q3': round_data['attention_q3'],
                                    'attention_round_q': round_data['attention_round_q'],
                                }
                    
                    processed_participants.add((session_code, participant_code))
                    processed_participants.add((session_code, partner_code))
    
    # Now process each pair and create output files
    file_count = 0
    for pair_key, pair_data in pairs.items():
        session_code = pair_data['session_code']
        rounds = pair_data['rounds']
        participants = pair_data['participants']
        
        # Build combined transcript
        combined_lines = []
        
        # Extract prolific IDs for filename
        director_prolific = participants.get('director_prolific', '')
        matcher_prolific = participants.get('matcher_prolific', '')
        
        # Create metadata header
        participant_info = []
        for role in ['director', 'matcher']:
            if role in participants:
                info = f"{role}: {participants[role]}"
                if f'{role}_prolific' in participants:
                    info += f" (prolific: {participants[f'{role}_prolific']})"
                participant_info.append(info)
        
        # Get group IDs from rounds (they may change per round in legacy data).
        # For analysis and filenames we prefer a single, canonical identifier:
        # - canonical_group_id: first non-empty group_id observed across rounds
        # - group_id_display: all unique raw group_ids (for debugging/backward-compat)
        raw_group_ids = [r.get('group_id', '') for r in rounds.values() if r.get('group_id')]
        unique_group_ids = sorted(set(raw_group_ids)) if raw_group_ids else []
        canonical_group_id = unique_group_ids[0] if unique_group_ids else 'N/A'
        group_id_display = ', '.join(unique_group_ids) if unique_group_ids else 'N/A'
        
        # Calculate timing for each round and total
        round_durations = {}
        total_duration_seconds = 0
        
        for round_num in range(1, 5):
            round_data = rounds.get(round_num, {})
            transcript = round_data.get('transcript', '')
            if transcript and transcript.strip():
                duration = calculate_round_duration(transcript)
                if duration is not None:
                    round_durations[round_num] = duration
                    total_duration_seconds += duration
        
        # Build timing info string
        timing_lines = []
        if round_durations:
            timing_lines.append("Timing:")
            for round_num in range(1, 5):
                if round_num in round_durations:
                    timing_lines.append(f"  Round {round_num}: {format_duration(round_durations[round_num])}")
                else:
                    timing_lines.append(f"  Round {round_num}: No data")
            timing_lines.append(f"  Total: {format_duration(total_duration_seconds)}")
        else:
            timing_lines.append("Timing: No timing data available")
        
        header = f"Session: {session_code}\n"
        header += f"Group ID (canonical): {canonical_group_id}\n"
        if len(unique_group_ids) > 1:
            header += f"Raw group IDs (by round): {group_id_display}\n"
        header += f"Participants: {', '.join(participant_info)}\n"
        header += f"Total Rounds: 4\n"
        header += "\n".join(timing_lines) + "\n"
        header += "=" * 70 + "\n\n"
        
        combined_lines.append(header)
        
        # Add all 4 rounds (show empty if no data)
        for round_num in range(1, 5):
            round_data = rounds.get(round_num, {})
            
            # Round header
            round_header = f"{'='*70}\n"
            round_header += f"ROUND {round_num}"
            if round_data.get('group_id'):
                round_header += f" (Group {round_data['group_id']})"
            round_header += f"\n{'='*70}\n"
            combined_lines.append(round_header)
            
            # Add performance metrics section
            if round_data:
                metrics_lines = []
                player_data = round_data.get('player_data', {})
                
                # Display metrics for both players
                for role in ['director', 'matcher']:
                    if role in player_data:
                        pdata = player_data[role]
                        metrics_lines.append(f"\n{role.upper()} METRICS:")
                        
                        # Sequence accuracy (percentage score)
                        sequence_accuracy = pdata.get('sequence_accuracy', '')
                        if sequence_accuracy and sequence_accuracy != '':
                            try:
                                accuracy_val = float(sequence_accuracy)
                                metrics_lines.append(f"  Score (Accuracy): {accuracy_val:.2f}%")
                            except (ValueError, TypeError):
                                if sequence_accuracy:
                                    metrics_lines.append(f"  Score (Accuracy): {sequence_accuracy}%")
                        
                        # Payoff (if different from accuracy and non-zero)
                        payoff = pdata.get('payoff', '')
                        if payoff:
                            try:
                                payoff_val = float(payoff)
                                # Only show payoff if it's non-zero and different from accuracy
                                if payoff_val != 0:
                                    try:
                                        accuracy_val = float(sequence_accuracy) if sequence_accuracy else None
                                        if accuracy_val is None or payoff_val != accuracy_val:
                                            metrics_lines.append(f"  Payoff: {payoff_val}")
                                    except (ValueError, TypeError):
                                        metrics_lines.append(f"  Payoff: {payoff_val}")
                            except (ValueError, TypeError):
                                pass
                        
                        # Attention checks
                        attention_checks = []
                        for q_num in ['q1', 'q2', 'q3', 'round_q']:
                            val = pdata.get(f'attention_{q_num}', '')
                            if val:
                                q_label = q_num.replace('_', ' ').title()
                                attention_checks.append(f"{q_label}={val}")
                        
                        if attention_checks:
                            metrics_lines.append(f"  Attention Checks: {', '.join(attention_checks)}")
                
                if metrics_lines:
                    combined_lines.append('\n'.join(metrics_lines))
                    combined_lines.append("")
            
            # Format and add transcript
            transcript = round_data.get('transcript', '')
            if transcript and transcript.strip():
                combined_lines.append("CHAT TRANSCRIPT:")
                formatted = format_chat_transcript(transcript)
                if formatted:
                    combined_lines.append(formatted)
                else:
                    combined_lines.append("(No messages)")
            else:
                combined_lines.append("(No data for this round)")
            
            combined_lines.append("\n")
        
        # Create filename with prolific IDs
        prolific_part = ""
        if director_prolific and matcher_prolific:
            prolific_part = f"_{director_prolific[:8]}_{matcher_prolific[:8]}"
        elif director_prolific or matcher_prolific:
            prolific_part = f"_{director_prolific[:8] or matcher_prolific[:8]}"
        
        # Use canonical group ID for filename so it is stable across rounds
        filename_group_id = canonical_group_id if canonical_group_id != 'N/A' else 'unknown'
        filename = f"pair_session{session_code}_group{filename_group_id}{prolific_part}.txt"
        output_path = base_output_folder / filename
        
        full_content = '\n'.join(combined_lines)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        # Count total messages across all rounds
        total_messages = sum(len(format_chat_transcript(rounds[r].get('transcript', '')).splitlines()) 
                           for r in rounds if rounds[r].get('transcript'))
        rounds_with_data = sum(1 for r in rounds.values() if r.get('transcript', '').strip())
        
        file_count += 1
        print(f"  Saved: {filename} ({rounds_with_data}/4 rounds with data, {total_messages} messages)")
    
    print(f"\nTotal pair transcripts created: {file_count}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nExample:")
        print("  python scripts/format_chat_transcript.py chat.json formatted_chat.txt")
        print("  python scripts/format_chat_transcript.py data.csv output_chats/")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' not found")
        sys.exit(1)
    
    # Check if input is CSV
    if input_path.endswith('.csv'):
        process_csv_file(input_path, output_path)
    else:
        process_single_file(input_path, output_path)


if __name__ == '__main__':
    main()

