from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .ai_utils import (  # type: ignore
    _build_ai_messages_from_history,
    _get_ai_client,
)


def _build_v6_system_prompt(player) -> str:
    """
    V6 system prompt: Natural Entrainment via Definite Determiners + Nickname-First.

    Key changes from V5:
    - Round 1: Full descriptions with indefinite determiners ("a dark basket with...").
    - Round 2+: Nickname-first approach using definite determiners ("the duck basket").
      Start with the shortest agreed nickname. Only expand if the Matcher asks.
    - The Matcher is explicitly told to accept recognized nicknames immediately.
    """
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    current_round = getattr(player, "round_number", 1)

    # Round-specific compression guidance
    if current_round == 1:
        round_guidance = (
            "ROUND 1 STRATEGY: This is the first time describing these baskets. "
            "Use indefinite determiners ('a', 'an') since these are new to your partner. "
            "Give a natural description highlighting with enough visual detail so your partner can distinguish the target from other similar baskets."
            "Aim to establish a short, memorable nickname for each basket.\n"
            "Do NOT explicitly suggest this nickname during your description — just describe it naturally.\n"
        )
    elif current_round == 2:    
        round_guidance = (
            f"ROUND {current_round} STRATEGY — NICKNAME-FIRST: "
            "Your partner has seen these baskets before. Start with ONLY the agreed nickname "
            "from the COMMON GROUND SUMMARY, using a DEFINITE determiner ('the', 'that'). "
            "Example: 'the duck basket' or 'the dark two-tone one'. "
            "If your partner confirms immediately, you used the right amount of detail. "
            "If they ask a question, add ONE distinguishing detail to disambiguate.\n"
        )
    else:
        round_guidance = (
            f"ROUND {current_round} STRATEGY — MINIMAL NICKNAMES: "
            "By now, your partner knows these baskets well. Use the SHORTEST agreed nickname "
            "with a definite determiner. Example: 'the duck', 'the dark one', 'orange tote'. "
            "Only add detail if your partner explicitly asks for clarification. "
            "Trust the shared vocabulary you have built together.\n"
        )

    if ai_role == "director":
        return (
            "You are the DIRECTOR in a basket referential game. "
            "Your role is to help your partner reconstruct a 12-basket sequence.\n\n"
            "CORE RESPONSIBILITIES:\n"
            "1. By default, describe the baskets in strict order from basket 1 to basket 12.\n"
            "2. Focus your description on exactly ONE basket at a time.\n"
            # "3. Encourage the MATCHER to confirm when they have placed a basket correctly.\n\n"
            "COMMUNICATION STRATEGY:\n"
            f"{round_guidance}"
            "- FORMAT RULE: When introducing a new target basket, ALWAYS begin your utterance with `Basket N:` where N is the current target position. "
            "Examples: `Basket 1: a duck-shaped wicker basket...` or `Basket 5: the duck basket.` "
            "This label is required so game state stays synchronized.\n"
            # "- THE GOLDEN RULE: Start with the SHORTEST phrase that could uniquely identify the basket. "
            # "If the COMMON GROUND SUMMARY has a nickname, lead with that nickname and a definite determiner. "
            # "Only add more detail if the Matcher asks a clarification question.\n"
            "- DETERMINER RULE: In Round 1, use 'a/an' (new to partner). "
            "In Round 2+, use 'the/that' (if your partner already knows it). "
            "This signals shared knowledge and is how humans naturally shorten descriptions.\n"
            "- EXPANSION RULE: If the Matcher asks a question, add ONE extra distinguishing feature. "
            "Do NOT re-describe the basket from scratch.\n"
            "- VACANCY RESPONSE: If the Matcher asks you to re-describe a previous basket (because they moved one), provide a very brief 1-sentence reminder and still begin with `Basket N:` for that re-described basket.\n"
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
            "COMMUNICATION STRATEGY:\n"
            f"{round_guidance}"
            "- THE GOLDEN RULE FOR CONFIDENCE: When you lock in a basket (i.e. you are certain), "
            "confirm it using the absolute minimum words necessary (e.g., 'Got it.', 'Placed it.'). "
            "DO NOT repeat the Director's description back to them.\n"
            "- THE GOLDEN RULE FOR UNCERTAINTY: If you are uncertain or confused among possible baskets, "
            "DO NOT lock in a basket. Instead, ask a short clarification question.\n"
            "- NICKNAME ACCEPTANCE: If the Director uses a short nickname or definite reference "
            "(e.g. 'the duck basket') that you recognize from the COMMON GROUND SUMMARY, "
            "accept it IMMEDIATELY without asking for more details. Trust the shared vocabulary.\n"
            "- VACANCY RULE: If your hidden prompt context says a previously completed position is now empty because you moved a basket, you MUST prioritize asking the Director to re-describe that missing basket once you finish the current target. Ask naturally in dialogue. Example: 'Before we move on, can you remind me of Basket 5?'\n"
            "- CRITICAL RULE: NEVER refer to baskets by your internal candidate numbers "
            "(e.g. 'candidate 3', 'cand 4') when asking questions. The Director cannot see your "
            "candidate pool and does not know your candidate numbers. Describe using visual features only.\n"
            "- Never say you are an AI system.\n"
            "- Be transparent about uncertainty, but if certain, confirm as briefly as possible."
        )


def _extract_v6_common_ground(player: Any, history_messages: List[Dict[str, Any]]) -> str:
    """
    V6 Common Ground Extractor.

    Key change from V5: Explicitly instructs the extractor to produce
    2-4 word NICKNAMES (not full descriptions). The nickname must be the
    shortest phrase that was sufficient for the Matcher to confirm placement
    without confusion.
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
        "between a DIRECTOR and a MATCHER in a referential matching game.\n\n"
        "Your job: extract the SHORTEST NICKNAME (2-4 words) that each basket "
        "was successfully identified by. This nickname will be used in future "
        "rounds as a shorthand.\n\n"
        "RULES:\n"
        "1. ONLY extract a nickname if the Matcher CONFIRMED placement (said 'Placed', "
        "'Done', 'Got it', etc.). Do NOT extract terms for baskets still being debated.\n"
        "2. The nickname should be the MINIMUM DISCRIMINATING phrase — the fewest words "
        "that distinguish this basket from ALL OTHERS in the set. Drop generic words like "
        "'basket', 'wicker', 'brown' unless they are the primary distinguishing feature.\n"
        "3. UNIQUENESS RULE (critical): Every basket must have a nickname that is UNIQUE "
        "and cannot be confused with any other basket's nickname. If a naive short form would "
        "collide (e.g. both basket 5 and basket 9 could be called 'dark rectangular'), you "
        "MUST include one extra differentiating word (e.g. 'dark gray-brown rounded' vs. "
        "'dark green rectangular'). The nickname must be unambiguous across the whole set.\n"
        "4. GOOD nicknames: 'duck basket', 'dark gray-brown rounded', 'green rectangle', "
        "'cat basket', 'picnic lid open', 'oval red-ties'\n"
        "5. BAD nicknames: 'dark two-tone' when two baskets could match that description; "
        "'warm orange-tan wicker tote with chunky rounded oval body and slightly flared rim' (too long).\n"
        "6. If a basket was described multiple times across rounds, use only the SHORTEST "
        "version that the Matcher accepted without confusion — but never so short it collides.\n\n"
        "Respond strictly in JSON with this schema:\n"
        "{\n"
        '  "agreed_terms_per_position": {"1": ["duck basket"], "2": ["dark gray-brown rounded"], ...},\n'
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
        logging.info(f"[V6_CG_AGENT] Extractor Output:\n{formatted_summary}")

        return formatted_summary
    except Exception as e:
        import logging
        logging.error(f"[V6_CG_AGENT] Extraction failed: {e}")
        return "Common ground extraction failed."


def build_v6_cg_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    V6: Natural Entrainment via Definite Determiners + Nickname-First.
    """
    base_system = _build_v6_system_prompt(player)

    full_history_messages = _build_ai_messages_from_history(player, all_history)

    if full_history_messages:
        common_ground_summary = _extract_v6_common_ground(player, full_history_messages)
    else:
        common_ground_summary = "No history available yet."

    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    current_round = getattr(player, "round_number", 1)

    # Define the JSON CoT instructions
    if ai_role == "matcher":
        v6_instructions = (
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
            "- If your `reasoning.likely_confusions` list is not empty, you MUST ask your `discriminative_question` as your `utterance`. If you ask a question, BOTH `selection.candidate_index` AND `selection.position` MUST be `null`.\n"
            "- CRITICAL RULE: DO NOT increment your target position if you just asked a question. A position is only filled if it appears in the **Current Partial Sequence**. Always double-check the image array to see what is *actually* filled.\n"
            "- CRITICAL RULE: When you confidently lock in a basket and there is NO pending refill request, your `utterance` MUST explicitly command the Director to move to the next empty position using MAXIMUM 5 words. Example: 'Done. Go to Basket 2'.\n"
            "- EXCEPTION: If hidden refill context says a previously completed position is now empty, you should finish the current placement and then ask for that basket to be re-described in the SAME utterance. Example: 'Placed it. Before we move on, can you remind me of Basket 5?' In that case, do NOT tell the Director to move to a new basket yet.\n"
            "- REMINDER TURN RULE: If the Director's message is a RE-DESCRIPTION of a previously placed basket (i.e., the Director says 'Basket N: ...' for a basket you already placed), treat it as a reminder, NOT a new placement. Do NOT say 'Placed it' again for the same basket. Instead, confirm the re-description with 'Re-confirmed Basket N.' and then ask for the next missing basket or command the Director to move on.\n"
            "- OUTPUT FORM RULE: Your `utterance` must be a complete conversational sentence. Never output a bare nickname fragment or partial echo like `the cat-face lidded` or `the shallow spiral-handled`.\n"
            "- OUTPUT FORM RULE: If `selection.candidate_index` is not null, your `utterance` must be a confirmation such as `Placed it. Go to Basket 8.` or `Done. Ready to submit.` It must NOT restate the Director's description.\n"
            "- OUTPUT FORM RULE: If `selection.candidate_index` is null, your `utterance` must be a full question ending with `?`.\n"
            "- CRITICAL RULE: When asking a `discriminative_question`, NEVER use candidate numbers like 'candidate 3' or 'cand 15'. The Director does not know your candidate numbers. Use purely visual descriptions.\n"
            "- RE-FILL VACANCIES: If hidden refill context says a position is now empty (e.g. Basket 5), you MUST ask the Director to re-describe it once the current basket is done. Do NOT mention system notices or hidden state. Do NOT submit the round until all 12 positions are filled.\n"
            "- Do NOT include extra text outside the JSON."
        )
    else:
        v6_instructions = (
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
            "- FORMAT RULE: When describing a target basket or re-describing a requested earlier basket, your `utterance` MUST begin with `Basket N:` using the correct basket number.\n"
            "- If the Matcher explicitly asks a clarification question, answer it directly and clearly. Add ONE distinguishing detail; do NOT re-describe from scratch.\n"
            + (
                "- ROUND 1: Use indefinite determiners ('a', 'an'). Give a focused description with the 1-2 most distinctive features. Aim to establish a nickname. Example: `Basket 1: a duck-shaped wicker basket...`\n"
                if current_round == 1
                else
                "- ROUND 2+: Lead with the agreed nickname from the 'Common Ground Summary' using a definite determiner ('the', 'that'). "
                "Example: 'Basket 5: the duck basket.' Do NOT add extra description unless the Matcher asks.\n"
                "- NICKNAME COLLISION RULE (critical): Before using a nickname, verify it cannot be confused with another basket's nickname already used in this conversation. "
                "If two baskets share similar short labels (e.g. both might be called 'dark rectangular'), "
                "add the one extra word that distinguishes them (e.g. 'the dark GREEN rectangular' vs. 'the dark GRAY-BROWN rounded'). "
                "Never assign the same or near-identical nickname to two different baskets.\n"
            )
            + "- RE-DESCRIPTION REQUESTS: If the Matcher asks you to re-describe Basket N, your ENTIRE response must be about Basket N ONLY. "
            "Use `Basket N:` as the label, give the agreed nickname (or a brief 1-sentence reminder), and STOP. "
            "Do NOT introduce a new basket in that same turn. Do NOT answer about Basket N+1 or any other basket. "
            "Wait for the Matcher to confirm the re-fill before continuing to the next basket.\n"
            + "- Do NOT include extra text outside the JSON."
        )

    cg_system_block = (
        "======== COMMON GROUND SUMMARY ========\n"
        "The following SHORT NICKNAMES have been agreed upon in previous rounds.\n"
        "Use these exact nicknames with a definite determiner ('the').\n"
        f"{common_ground_summary}\n"
        "=======================================\n"
    )

    system_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": base_system},
        {"role": "system", "content": cg_system_block},
        {"role": "system", "content": v6_instructions},
    ]

    max_history_raw_turns = 2
    recent_history = full_history_messages[-max_history_raw_turns:] if full_history_messages else []

    chat_messages: List[Dict[str, Any]] = system_messages + recent_history

    if latest_message:
        chat_messages.append({"role": "user", "content": latest_message})

    return chat_messages
