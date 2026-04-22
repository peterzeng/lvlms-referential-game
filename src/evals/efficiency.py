import re
import math
import pandas as pd
from .time import seconds_to_hhmmss, get_duration_seconds

import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import statsmodels.api as sm


def parse_transcript(transcript_text):
    """
    Parse a chat transcript and extract language units with timestamps.
    Returns: {
        'turns': list of turns (each turn is a list of (timestamp, message) tuples),
        'utterances': list of all (timestamp, message) tuples,
        'words': list of word counts per utterance
    }
    A turn is all contributions from one DP without interruption by the other DP.
    An utterance is a single message (up to carriage return).
    """
    if pd.isnull(transcript_text) or not isinstance(transcript_text, str) or not transcript_text.strip():
        return {'turns': [], 'utterances': [], 'words': []}
    
    # Pattern to match: [HH:MM:SS] speaker: message
    # Messages can span multiple lines until the next timestamp
    pattern = r'\[(\d{2}:\d{2}:\d{2})\]\s*(director|matcher):\s*(.*?)(?=\[\d{2}:\d{2}:\d{2}\]|$)'
    
    matches = re.findall(pattern, transcript_text, re.DOTALL)
    
    turns = []
    utterances = []
    words = []
    
    current_turn = []
    current_speaker = None
    
    for timestamp, speaker, message in matches:
        message = message.strip()
        if not message:
            continue
        
        # Check if this is a new turn (different speaker)
        if current_speaker is not None and speaker != current_speaker:
            # End the current turn
            if current_turn:
                turns.append(current_turn)
            current_turn = []
        
        # Add this utterance with timestamp
        current_turn.append((timestamp, message))
        utterances.append((timestamp, message))
        
        # Count words in this utterance
        words_in_utterance = len(re.findall(r'\b\w+\b', message))
        words.extend([words_in_utterance])  # Store word count per utterance for easier calculation
        
        current_speaker = speaker
    
    # Don't forget the last turn
    if current_turn:
        turns.append(current_turn)
    
    return {
        'turns': turns,
        'utterances': utterances,
        'words': words  # This is word counts per utterance
    }


def calculate_efficiency_metrics_for_round(transcript_text: str):
    """Calculate all language unit metrics for a single round, including time metrics."""
    parsed = parse_transcript(transcript_text)
    
    turns = parsed['turns']
    utterances = parsed['utterances']
    word_counts = parsed['words']  # List of word counts per utterance
    
    total_words = sum(word_counts)
    num_turns = len(turns)
    num_utterances = len(utterances)
    
    # Calculate round duration (from first to last timestamp)
    round_duration_seconds = None
    if utterances:
        first_ts = utterances[0][0]
        last_ts = utterances[-1][0]
        round_duration_seconds = get_duration_seconds(first_ts, last_ts)
    
    # Calculate turn durations
    turn_durations = []
    for turn in turns:
        if len(turn) > 0:
            turn_start_ts = turn[0][0]
            turn_end_ts = turn[-1][0]
            turn_duration = get_duration_seconds(turn_start_ts, turn_end_ts)
            if turn_duration is not None:
                turn_durations.append(turn_duration)
    
    # Calculate utterance durations (inter-utterance intervals)
    # This measures the time between consecutive utterances across the entire round
    # Note: This includes intervals both WITHIN turns and BETWEEN turns (when speakers switch)
    utterance_durations = []
    for i, (ts, msg) in enumerate(utterances):
        if i < len(utterances) - 1:
            # Duration from this utterance to the next
            next_ts = utterances[i + 1][0]
            duration = get_duration_seconds(ts, next_ts)
            if duration is not None:
                utterance_durations.append(duration)
    # Note: We don't include the last utterance as it has no "next" utterance
    
    # Calculate average time metrics
    avg_turn_duration = sum(turn_durations) / len(turn_durations) if turn_durations else None
    avg_utterance_duration = sum(utterance_durations) / len(utterance_durations) if utterance_durations else None
    
    # IMPORTANT NOTE: avg_turn_duration vs avg_utterance_duration
    # - avg_turn_duration: Time span WITHIN a turn (from first to last utterance in that turn)
    #   If a turn has only 1 utterance, duration = 0 seconds
    # - avg_utterance_duration: Time BETWEEN consecutive utterances (inter-utterance interval)
    #   This includes gaps both within turns AND between turns (when speakers switch)
    #   So avg_utterance_duration can be longer than avg_turn_duration if:
    #   - Most turns have only 1 utterance (making turn durations short)
    #   - There are long gaps between turns (when the other speaker responds)
    
    # Calculate metrics
    metrics = {
        '# words': total_words,
        '# turns': num_turns,
        '# utterances': num_utterances,
        # 'words_per_round': total_words,
        'words_per_turn': total_words / num_turns if num_turns > 0 else 0,
        'words_per_utterance': total_words / num_utterances if num_utterances > 0 else 0,
        'utterances_per_turn': num_utterances / num_turns if num_turns > 0 else 0,
        # 'utterances_per_round': num_utterances,
        # 'turns_per_round': num_turns,
        'round_duration_seconds': round_duration_seconds,
        'avg_turn_duration_seconds': avg_turn_duration,
        'avg_utterance_duration_seconds': avg_utterance_duration,
        # Formatted time strings
        'round_duration': seconds_to_hhmmss(round_duration_seconds),
        'avg_turn_duration': seconds_to_hhmmss(avg_turn_duration),
        'avg_utterance_duration': seconds_to_hhmmss(avg_utterance_duration)
    }
    
    return metrics