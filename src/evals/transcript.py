import re
import pandas as pd
from .time import extract_hms, add_duration_columns_to_transcript_df


# x_to_y where x is director and y is matcher
PAIRING_CONDITIONS = [
    "Human-Human",  "AI-AI", "AI-Human", "Human-AI"
]


def _clean_transcript(transcript: str) -> str:
    # Replace multiple whitespace with single space
    trainscript_refined = re.sub(r"\s+", " ", transcript)
    # Insert double newlines before timestamps
    trainscript_refined = re.sub(
        r"(\[(\d{2}:\d{2}:\d{2})\]\s)", r"\n\n\1", trainscript_refined
    ).strip()
    return trainscript_refined


def get_human_to_human_transcript(df: pd.DataFrame, 
                                  condition="human_to_human", 
                                  drop_incomplete_rounds=True) -> pd.DataFrame:
    
    human_to_human_transcripts = []

    for _, row in df.iterrows():
        pair_id = row['pair_id']
        
        if pd.isna(pair_id):
            continue
        
        four_round_transcripts = []
        accuracy_nums = [row[f'round{round_ix}_matcher_sequence_accuracy'] for round_ix in range(1, 5)]
        for round_num in range(1, 5):
            director_col = f'round{round_num}_director_chat_transcript'
            matcher_col = f'round{round_num}_matcher_chat_transcript'

            transcript = row.get(director_col, '')
            if pd.isnull(transcript) or (isinstance(transcript, str) and len(transcript.strip().split()) <= 20):
                transcript = row.get(matcher_col, '')

            if pd.isnull(transcript):
                continue
            
            four_round_transcripts.append(
                {
                    "pair_id": pair_id,
                    "condition": condition,
                    "round_ix": round_num,
                    "accuracy": accuracy_nums[round_num - 1],
                    "transcript": _clean_transcript(transcript)
                }
            )
        
        if drop_incomplete_rounds and len(four_round_transcripts) < 4:
            continue

        human_to_human_transcripts.extend(four_round_transcripts)
    
    human_to_human_transcripts_df = pd.DataFrame(human_to_human_transcripts)
    return human_to_human_transcripts_df


def get_ai_to_ai_transcript(df: pd.DataFrame, 
                            condition="ai_to_ai", 
                            drop_incomplete_rounds=True) -> pd.DataFrame:
    ai_to_ai_transcripts = []

    for _, row in df.iterrows():
        pair_id = row['pair_id']

        four_round_transcripts = []

        accuracy_nums = [row[f'round{round_ix}_matcher_sequence_accuracy'] for round_ix in range(1, 5)]
        for round_ix in range(1, 5):
            col_name = f"round{round_ix}_ai_messages"

            if pd.isna(row[col_name]):
                continue

            messages = eval(row[col_name])

            if len(messages) == 0:
                continue

            transcript = "\n\n".join([f'[{extract_hms(msg["timestamp"])}] {msg["sender_role"]}: {msg["text"]}' for msg in messages])
            four_round_transcripts.append(
                {
                    "pair_id": pair_id,
                    "condition": condition,
                    "round_ix": round_ix,
                    "accuracy": accuracy_nums[round_ix - 1],
                    "transcript": transcript
                }
            )

        if drop_incomplete_rounds and len(four_round_transcripts) < 4:
            continue

        ai_to_ai_transcripts.extend(four_round_transcripts)
    
    ai_to_ai_transcripts_df = pd.DataFrame(ai_to_ai_transcripts)
    return ai_to_ai_transcripts_df


# to rewrite: the methods need to vary for each pairing condition
def get_clean_transcript(df: pd.DataFrame, 
                         condition, drop_incomplete_rounds=True, 
                         add_duration_columns=True) -> pd.DataFrame | None:

    assert condition in PAIRING_CONDITIONS, f"Condition {condition} not recognized."

    if condition in ["Human-Human",  "AI-Human", "Human-AI"]:
        df = get_human_to_human_transcript(df, condition=condition, drop_incomplete_rounds=drop_incomplete_rounds)
    
    if condition in ["AI-AI"]:
        df = get_ai_to_ai_transcript(df, condition=condition, drop_incomplete_rounds=drop_incomplete_rounds)

    if add_duration_columns:
        add_duration_columns_to_transcript_df(df)
    
    return df