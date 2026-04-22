import re
import pandas as pd
from datetime import datetime


def extract_hms(timestamp: str) -> str:
    """
    Extract HH:MM:SS from an ISO-8601 timestamp string.

    Example:
        '2025-12-29T12:11:20.433631' -> '12:11:20'
    """
    dt = datetime.fromisoformat(timestamp)
    return dt.strftime("%H:%M:%S")


def get_first_and_last_timestamps(chat_transcript):
    if pd.isnull(chat_transcript) or not isinstance(chat_transcript, str):
        return None, None
    # Expected timestamp format: [HH:MM:SS]
    timestamps = re.findall(r'\[(\d{2}:\d{2}:\d{2})\]', chat_transcript)
    if not timestamps:
        return None, None
    return timestamps[0], timestamps[-1]


def get_duration_seconds(start_ts, end_ts):
    if not start_ts or not end_ts:
        return None
    fmt = "%H:%M:%S"
    try:
        t1 = datetime.strptime(start_ts, fmt)
        t2 = datetime.strptime(end_ts, fmt)
        delta = (t2 - t1).total_seconds()
        
        # handle possible day wraparound
        if delta < 0:
            delta += 24 * 60 * 60
        return delta
    except Exception:
        return None


def seconds_to_hhmmss(seconds):
    """Convert seconds to HH:MM:SS format"""
    if seconds is None or pd.isnull(seconds):
        return None
    try:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except Exception:
        return None



def timestamp_to_seconds(ts_str):
    """Convert HH:MM:SS timestamp to seconds since start of day."""
    try:
        parts = ts_str.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except:
        return None


def add_duration_columns_to_transcript_df(transcript_df: pd.DataFrame) -> None:
    for ix, row in transcript_df.iterrows():
        transcript = row["transcript"]
        
        # Extract timestamps and calculate duration
        first_ts, last_ts = get_first_and_last_timestamps(transcript)
        duration_seconds = get_duration_seconds(first_ts, last_ts)
        duration_hhmmss = seconds_to_hhmmss(duration_seconds)
        transcript_df.at[ix, "duration_seconds"] = duration_seconds
        transcript_df.at[ix, "duration_hhmmss"] = duration_hhmmss