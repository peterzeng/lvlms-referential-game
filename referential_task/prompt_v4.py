from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .ai_utils import (  # type: ignore
    _build_ai_messages_from_history,
    _get_ai_client,
)
from .prompt_v2 import _build_weiling_style_system_prompt

def _extract_common_ground(player: Any, history_messages: List[Dict[str, Any]]) -> str:
    """
    Agent 1 (Common Ground Extractor).
    Uses a fast/cheap model to summarize the history into established lexical terms
    and current intent.
    """
    client = _get_ai_client()
    if not client or not history_messages:
        return "No history available yet."

    # Format the history into a single text block for the extraction agent
    history_text = ""
    for msg in history_messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            # Skip images for the fast text summary extraction
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            content = " ".join(text_parts)
        history_text += f"{role}: {content}\n"

    system_prompt = (
        "You are a Common Ground Extraction Agent observing a dialogue "
        "between a DIRECTOR and a MATCHER in a referential matching game.\n"
        "Your job is to summarize the dialogue history into established "
        "common ground (agreed-upon lexical terms for basket positions 1-12) "
        "and identify the current immediate focus/dispute.\n\n"
        "Respond strictly in JSON with this schema:\n"
        "{\n"
        '  "agreed_terms_per_position": {"1": ["tall handle", "dark wood"], ...},\n'
        '  "current_target_position": <integer or null>,\n'
        '  "current_intent": "<short description of what the most recent turn is trying to achieve>"\n'
        "}"
    )

    try:
        # Fallback to gpt-4o-mini which is widely available for proof-of-concept
        # Alternatively, reading from player.session.config.get("ai_model") could work
        extractor_model = os.environ.get("AI_EXTRACTOR_MODEL", "gpt-4o-mini")
        
        response = client.chat.completions.create(
            model=extractor_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Dialogue History:\n{history_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        summary = response.choices[0].message.content
        if not summary:
            return "Failed to extract common ground."
        
        parsed = json.loads(summary)
        formatted_summary = json.dumps(parsed, indent=2)
        
        import logging
        logging.info(f"[V4_CG_AGENT] Extractor Output:\n{formatted_summary}")
        
        return formatted_summary
    except Exception as e:
        import logging
        logging.error(f"[V4_CG_AGENT] Extraction failed: {e}")
        return "Common ground extraction failed."

def build_v4_cg_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    V4: Common Ground Multi-Agent strategy.
    
    1. Extracts established terms from the full history using gpt-5.2-mini.
    2. Constructs a prompt for the primary Reasoning Agent containing:
       - The System Prompt
       - The extracted Common Ground summary
       - Only the last 2 messages (to prevent context saturation/glitching)
       - The V3/CoT JSON instructions
    """
    base_system = _build_weiling_style_system_prompt(player)

    # Convert all raw history to standardized chat messages
    full_history_messages = _build_ai_messages_from_history(player, all_history)

    # 1. Agent 1 extracts the common ground (if there is history)
    if full_history_messages:
        common_ground_summary = _extract_common_ground(player, full_history_messages)
    else:
        common_ground_summary = "No history available yet."

    # 2. Agent 2 setup
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    # Define the JSON CoT instructions (borrowed from v3)
    if ai_role == "matcher":
        v4_instructions = (
            "You must respond with a SINGLE STRICT JSON object and EXACTLY these top-level fields (no extras):\n"
            '- "reasoning"\n'
            '- "utterance"\n'
            '- "selection"\n'
            "{\n"
            '  "reasoning": {\n'
            '    "target_position": <integer 1-12>,\n'
            '    "shared_features": ["features many baskets share"],\n'
            '    "distinctive_features": ["features that uniquely identify the basket"],\n'
            '    "best_guess_candidate_index": <integer 1-18 or null>,\n'
            '    "likely_confusions": <array of integers 1-18>,\n'
            '    "discriminative_question": "a short question to disambiguate"\n'
            "  },\n"
            '  "utterance": "a single concise natural-language message you will SAY to the DIRECTOR. Do NOT reveal you are an AI.",\n'
            '  "selection": {\n'
            '    "candidate_index": <integer 1–18 or null>,\n'
            '    "position": <integer 1–12 or null>,\n'
            '    "ready_to_submit": <true/false>\n'
            "  }\n"
            "}\n\n"
            "Rules:\n"
            "- Rely on the 'Common Ground Summary' block to understand past agreed terms. Do not contradict established terms.\n"
            "- Write step-by-step thinking in `reasoning`. The DIRECTOR only sees `utterance`.\n"
            "- Never mention candidate indices or filenames in your utterance.\n"
            "- CRITICAL RULE: When you confidently lock in a basket (i.e., your `selection` has a valid `candidate_index` and `position`), your `utterance` MUST explicitly command the Director to move to the next empty basket. Example: 'I have locked in Basket 1. Please describe Basket 2 now'. This is mandatory so the Director can track progress.\n"
            "- Do NOT include extra text outside the JSON."
        )
    else:
        v4_instructions = (
            "You must respond with a SINGLE STRICT JSON object and EXACTLY these top-level fields (no extras):\n"
            '- "reasoning"\n'
            '- "utterance"\n'
            "{\n"
            '  "reasoning": {\n'
            '    "target_position": <integer 1-12>,\n'
            '    "shared_features": ["features this basket shares with others"],\n'
            '    "distinctive_features": ["features that uniquely identify THIS basket"],\n'
            '    "likely_confusions": <array of integers 1-12>,\n'
            '    "discriminative_strategy": "features to emphasize"\n'
            "  },\n"
            '  "utterance": "a single concise natural-language message you will SAY to the MATCHER. Do NOT reveal you are an AI."\n'
            "}\n\n"
            "Rules:\n"
            "- CRITICAL RULE: You MUST strictly obey the `GLOBAL GAME STATE` context message. It tells you exactly which baskets are already completed. NEVER describe a basket that is in the `Completed Positions` list.\n"
            "- ALWAY focus your description squarely on the `Next Target Position to Describe`.\n"
            "- Rely on the 'Common Ground Summary' block to use terms the MATCHER already understands.\n"
            "- Write step-by-step thinking in `reasoning`. The MATCHER only sees `utterance`.\n"
            "- Do NOT include extra text outside the JSON."
        )

    # Inject the common ground summary into the system messages
    cg_system_block = (
        "======== COMMON GROUND SUMMARY ========\n"
        "The Context Extraction Agent has summarized previous interactions into agreed terms:\n"
        f"{common_ground_summary}\n"
        "=======================================\n"
    )

    system_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": base_system},
        {"role": "system", "content": cg_system_block},
        {"role": "system", "content": v4_instructions},
    ]

    # Constrain the RAW history to ONLY the last 2 turns to prevent context saturation/glitching
    max_history_raw_turns = 2
    recent_history = full_history_messages[-max_history_raw_turns:] if full_history_messages else []

    chat_messages: List[Dict[str, Any]] = system_messages + recent_history

    if latest_message:
        chat_messages.append({"role": "user", "content": latest_message})

    return chat_messages
