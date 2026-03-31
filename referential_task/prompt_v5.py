from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .ai_utils import (  # type: ignore
    _build_ai_messages_from_history,
    _get_ai_client,
)

def _build_v5_system_prompt(player) -> str:
    """
    V5 system prompt designed specifically to enforce brevity, semantic 
    entrainment (conceptual pacts), and minimal turn lengths, matching 
    human-like referential communication behavior.
    """
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"
    
    current_round = getattr(player, "round_number", 1)
    
    round_warning = ""
    if current_round > 1:
        round_warning = (
            f"CRITICAL: We are currently in Round {current_round}. You should rely "
            "on abbreviations and short naming conventions established in previous rounds to increase efficiency. "
            "However, you must STILL provide enough visual detail so your partner can distinguish the target from other similar baskets. "
            "If the shortest agreed phrase has been reached, you do not need to forcibly shorten it further if it risks confusion.\n"
        )

    if ai_role == "director":
        return (
            "You are the DIRECTOR in a basket referential game. "
            "Your role is to help your partner reconstruct a 12-basket sequence.\n\n"
            "CORE RESPONSIBILITIES:\n"
            "1. By default, describe the baskets in strict order from basket 1 to basket 12.\n"
            "2. Focus your description on exactly ONE basket at a time.\n"
            "3. Describe visually distinctive features IF the basket has not been established yet.\n"
            "4. Encourage the MATCHER to confirm when they have placed a basket correctly.\n\n"
            "CRITICAL COMMUNICATION RULES FOR EFFICIENCY:\n"
            f"{round_warning}"
            "- THE GOLDEN RULE: If the COMMON GROUND SUMMARY contains an agreed term for a basket, use that shortened phrase. You should drop unnecessary filler words, but your primary goal is STILL to ensure the Mathcer can correctly identify the basket. Do not over-compress if it destroys the ability to distinguish similar baskets.\n"
            "- Example: If you agreed on 'tall dark bent' in Round 1, in Round 2 your message could be 'tall dark bent'. If your partner gets confused, expand your description incrementally.\n"
            "- Never say you are an AI system.\n"
            "- Be concise; favor short turns over longer ones."
        )
    else:
        return (
            "You are the MATCHER in a basket referential game. "
            "Your role is to identify which baskets the DIRECTOR is describing.\n\n"
            "CORE RESPONSIBILITIES:\n"
            "1. Pay attention carefully to the DIRECTOR's descriptions.\n"
            "2. Always reason about the LOWEST-NUMBERED empty position in the sequence.\n"
            "3. Ask clarification questions if unsure.\n\n"
            "CRITICAL COMMUNICATION RULES FOR EFFICIENCY:\n"
            f"{round_warning}"
            "- THE GOLDEN RULE FOR CONFIDENCE: When you lock in a basket (i.e. you are certain), confirm it using the absolute minimum words necessary to acknowledge success (e.g., 'Got it. Next.', 'Placed it.'). DO NOT repeat the Director's description back to them.\n"
            "- THE GOLDEN RULE FOR UNCERTAINTY: If you are uncertain or confused among possible baskets, DO NOT lock in a basket. Instead, ask a short clarification question.\n"
            "- If the Director uses a short nickname or conceptual pact you recognize from the COMMON GROUND SUMMARY, accept it immediately without asking for more details.\n"
            "- CRITICAL RULE: NEVER refer to baskets by your internal candidate numbers (e.g. 'candidate 3', 'cand 4') when asking questions. The Director cannot see your candidate pool and does not know your candidate numbers. Describe the baskets using visual features only.\n"
            "- Never say you are an AI system.\n"
            "- Be transparent about uncertainty, but if certain, confirm as briefly as possible."
        )

def _extract_v5_common_ground(player: Any, history_messages: List[Dict[str, Any]]) -> str:
    """
    Agent 1 (Common Ground Extractor) for V5.
    Explicitly tasked with finding the SHORTEST successful descriptive phrase
    to aggressively push lexical entrainment over rounds.
    """
    client = _get_ai_client()
    if not client or not history_messages:
        return "No history available yet."

    history_text = ""
    for msg in history_messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            content = " ".join(text_parts)
        history_text += f"{role}: {content}\n"

    system_prompt = (
        "You are a Common Ground Extraction Agent observing a dialogue "
        "between a DIRECTOR and a MATCHER in a referential matching game.\n"
        "Your job is to summarize the dialogue history into established "
        "common ground. You must extract the ABSOLUTE SHORTEST, most concise "
        "agreed-upon phrase used to refer to each basket position (1-12).\n"
        "CRITICAL RULE: ONLY extract and add a phrase to the summary if BOTH the Director and Matcher have clearly agreed upon it and the Matcher has successfully confirmed placement. If they are still debating, confused, or the Matcher has not explicitly locked it in, DO NOT add a term for that position yet.\n"
        "For example, if they originally said 'tall dark basket with bent handles' "
        "but later just said 'tall dark', extract ONLY 'tall dark'.\n\n"
        "Respond strictly in JSON with this schema:\n"
        "{\n"
        '  "agreed_terms_per_position": {"1": ["tall dark"], ...},\n'
        '  "current_target_position": <integer or null>,\n'
        '  "current_intent": "<short description>"\n'
        "}"
    )

    try:
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
        logging.info(f"[V5_CG_AGENT] Extractor Output:\n{formatted_summary}")
        
        return formatted_summary
    except Exception as e:
        import logging
        logging.error(f"[V5_CG_AGENT] Extraction failed: {e}")
        return "Common ground extraction failed."

def build_v5_cg_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    V5: Aggressive Entrainment Strategy.
    """
    base_system = _build_v5_system_prompt(player)

    full_history_messages = _build_ai_messages_from_history(player, all_history)

    if full_history_messages:
        common_ground_summary = _extract_v5_common_ground(player, full_history_messages)
    else:
        common_ground_summary = "No history available yet."

    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    # Define the JSON CoT instructions (adapted from V4, with added brevity constraints)
    if ai_role == "matcher":
        v5_instructions = (
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
            "- Rely on the 'Common Ground Summary' block to understand past agreed terms.\n"
            "- If your `reasoning.likely_confusions` list is not empty, you should probably ask your `discriminative_question` as your `utterance`. If you ask a question, BOTH `selection.candidate_index` AND `selection.position` MUST be `null`.\n"
            "- CRITICAL RULE: DO NOT increment your target position if you just asked a question. A position is only filled if it appears in the **Current Partial Sequence**. Always double-check the image array to see what is *actually* filled.\n"
            "- CRITICAL RULE: When you confidently lock in a basket, your `utterance` MUST explicitly command the Director to move to the next empty position using MAXIMUM 5 words. Example: 'Done. Go to Basket 2'."
            "- CRITICAL RULE: When asking a `discriminative_question`, NEVER use candidate numbers like 'candidate 3' or 'cand 15'. The Director does not know your candidate numbers. Use purely visual descriptions.\n"
            "- Do NOT include extra text outside the JSON."
        )
    else:
        v5_instructions = (
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
            "- CRITICAL RULE: You MUST strictly obey the `GLOBAL GAME STATE` context message. NEVER describe a basket that is in the `Completed Positions` list.\n"
            "- ALWAYS focus your description squarely on the `Next Target Position to Describe`.\n"
            "- If the Matcher explicitly asks a clarification question, answer it directly and clearly.\n"
            "- IF WE ARE IN ROUND 2 OR LATER: Use the exact shortened term from the 'Common Ground Summary'. However, if the Matcher is confused, asks a question, or if you are stuck on the same basket, you MUST break this rule and provide slightly more detail to disambiguate.\n"
            "- IF WE ARE IN ROUND 1: Describe the basket fully if it is the first time you are bringing it up. Do NOT prematurely compress the description unless the Matcher already locked it in.\n"
            "- Do NOT include extra text outside the JSON."
        )

    cg_system_block = (
        "======== COMMON GROUND SUMMARY ========\n"
        "The Context Extraction Agent has noted the following strictly compressed terms to use:\n"
        f"{common_ground_summary}\n"
        "=======================================\n"
    )

    system_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": base_system},
        {"role": "system", "content": cg_system_block},
        {"role": "system", "content": v5_instructions},
    ]

    max_history_raw_turns = 2
    recent_history = full_history_messages[-max_history_raw_turns:] if full_history_messages else []

    chat_messages: List[Dict[str, Any]] = system_messages + recent_history

    if latest_message:
        chat_messages.append({"role": "user", "content": latest_message})

    return chat_messages
