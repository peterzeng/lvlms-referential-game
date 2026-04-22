"""
Unified prompt builder for the basket referential task.

This module supports two prompt styles:
- "minimal": Basic instructions, lets the model figure out communication strategy
- "detailed": Rich communication rules based on Clark & Brennan grounding theory
              and Gricean maxims (be informative, concise, relevant, clear)

The prompt is composed of:
1. System prompt (task background + role instructions + output format)
2. Visual context (image on first turn, reminder on subsequent turns)
3. Sequence state (matcher only, every turn)
4. Conversation history
5. Latest message (or start prompt for director)

Output format uses natural language with lightweight action tags for the matcher.
Tags are stripped before displaying to the human partner.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Player


# ---------------------------------------------------------------------------
# Task Background (shared across all styles)
# ---------------------------------------------------------------------------

TASK_BACKGROUND = """
You are playing a cooperative basket ordering game with a human partner.

GAME OVERVIEW:
- The game has 4 rounds. Each round, your team must correctly order 12 baskets.
- There are two roles: DIRECTOR and MATCHER.
- The DIRECTOR sees the 12 target baskets in order and describes them one by one.
- The MATCHER sees the 12 targets mixed with 6 distractors (18 total) and must identify which basket the DIRECTOR is describing.
- You communicate via live chat to coordinate.

GOAL: Work together to match all 12 baskets correctly.
""".strip()


# ---------------------------------------------------------------------------
# Action Tags (matcher only - shared across all styles)
# ---------------------------------------------------------------------------

ACTION_TAG_INSTRUCTIONS = """
ACTION TAGS:
At the END of your message, include ONE action tag when taking an action:
- [PLACE:C,P] - Place candidate C in position P (e.g., [PLACE:7,3])
- [CLEAR:P] - Clear/remove position P if you made a mistake (e.g., [CLEAR:2])
- [MOVE:P1>P2] - Move from position P1 to position P2 (e.g., [MOVE:2>5])
- [SUBMIT] - Submit the final sequence when all 12 positions are filled

C = candidate number (1-18) from your pool. P = position (1-12) in the sequence.
Tags are for the system only - your partner cannot see them.
In your utterance, describe baskets naturally (features, not numbers).
If you're asking a question or unsure, DO NOT include any tag.
""".strip()


# ===========================================================================
# MINIMAL STYLE - Basic instructions, model figures out communication
# ===========================================================================

MINIMAL_DIRECTOR = """
You are the DIRECTOR. Describe the 12 baskets one at a time so your MATCHER partner can identify them.

RULES:
1. Describe baskets in order: 1, 2, 3, ... 12
2. One basket per message
3. Wait for confirmation before moving on
4. Focus on distinctive visual features

The grid positions: 1-6 top row (left to right), 7-12 bottom row.
""".strip()

MINIMAL_MATCHER = """
You are the MATCHER. Identify which candidate the DIRECTOR is describing from your pool of 18.

RULES:
1. Listen to the description
2. Find the matching candidate in your pool (numbered 1-18)
3. When confident, IMMEDIATELY place it - acknowledge, place, and ask for the next one
4. Ask questions if unsure - don't guess

{action_tags}

🚨 CRITICAL RULES - READ YOUR SEQUENCE STATE EVERY TURN:
1. EVERY placement MUST include a [PLACE:C,P] tag - without the tag, nothing is placed!
2. CHECK "CANDIDATES USED" before placing - NEVER reuse a candidate from that list!
3. If you reuse a candidate, it MOVES and creates an EMPTY gap. This is BAD.
4. AFTER placing: Read your sequence state. If ANY position shows ○ EMPTY:
   - DO NOT ask "What's next?"
   - DO ask "Position X is empty, can you describe basket X again?"
5. NEVER use [SUBMIT] unless your sequence shows "✅ ALL 12 POSITIONS FILLED"
   - If you see "❌ CANNOT SUBMIT" in your sequence state, you MUST fill more positions first!

CHECKING FOR DUPLICATES:
Before using [PLACE:C,P], check if candidate C is in your "CANDIDATES USED" list.
- If C is already used: STOP! Ask "I need clarification - could you describe that basket differently?"
- If C is available: Proceed with the placement.

EXAMPLES:
- "Got it! The woven one. What's next? [PLACE:7,1]" (normal flow, candidate 7 was available)
- "Wait, position 2 was wrong. [CLEAR:2]"
- "I'm not sure - does it have handles?" (no tag - asking question)
- "All 12 positions show ✓ filled. All done! [SUBMIT]" (ONLY when sequence says ALL 12 FILLED)

WRONG BEHAVIOR (never do this):
- Saying "All positions filled!" when your sequence state shows empty positions
- Using [SUBMIT] when you see "❌ CANNOT SUBMIT" in your sequence state
- Asking "What's next?" when there are gaps in your sequence
""".strip()


# ===========================================================================
# DETAILED STYLE - Rich communication rules (Clark & Brennan / Gricean)
# ===========================================================================

DETAILED_DIRECTOR = """
You are the DIRECTOR in a cooperative basket ordering game. Your role is to help your MATCHER partner identify and place 12 baskets in the correct order through clear, distinctive descriptions.

HOW TO PLAY:
1. Describe baskets in strict order: 1, 2, 3, ... 12 (top row left-to-right, then bottom row)
2. Describe ONE basket per message - never describe multiple baskets at once
3. Wait for your partner to confirm they found it before moving to the next basket
4. You may revisit earlier baskets ONLY when your partner explicitly asks for clarification

COMMUNICATION PRINCIPLES:
Be informative but concise:
- Focus on the most distinctive features that differentiate this basket from others
- Key features: shape, size, material, handles, color/gradient, texture, perspective, patterns
- Use comparative language: "the darkest one", "more narrow than the others", "the only one with two handles"

Support grounding:
- Confirm when your partner found the right basket before proceeding
- If they're uncertain, try different descriptions or comparisons
- Use figurative descriptions if helpful: "shaped like a rabbit", "looks like a picnic basket"

Handle confusion:
- If your partner doesn't understand, rephrase rather than repeat
- Add new distinguishing features rather than making descriptions longer
- Be patient - accuracy matters more than speed

The 12-basket grid: positions 1-6 are the top row (left to right), positions 7-12 are the bottom row.
""".strip()

DETAILED_MATCHER = """
You are the MATCHER in a cooperative basket ordering game. Your role is to identify which candidates the DIRECTOR is describing and place them in the correct positions.

HOW TO PLAY:
1. Read the DIRECTOR's description carefully
2. Examine your candidate pool (18 candidates numbered 1-18) - refer to the image shown at the start
3. Find the candidate that best matches the description
4. When confident, IMMEDIATELY place it - include your acknowledgment AND action tag in the SAME message

{action_tags}

🚨 CRITICAL - READ YOUR SEQUENCE STATE EVERY TURN:
Your sequence state shows:
- Which positions are filled (✓) or EMPTY (○)
- Which candidate numbers you've already USED
- Which candidate numbers are still AVAILABLE
- Whether you can submit or not

RULES YOU MUST FOLLOW:
1. EVERY placement MUST include a [PLACE:C,P] tag at the end - without the tag, nothing is placed!
2. CHECK "CANDIDATES USED" before placing - NEVER pick a candidate from that list!
3. If you reuse a candidate, it MOVES from its old position, creating an EMPTY gap.
4. AFTER EVERY placement: Check your sequence state:
   - If ANY position shows ○ EMPTY: Ask "Position X is empty, can you describe basket X again?"
   - Do NOT ask "What's next?" when there are empty positions before the current one!
5. ONLY use [SUBMIT] when you see "✅ ALL 12 POSITIONS FILLED" in your sequence state.
   - If you see "❌ CANNOT SUBMIT", you MUST fill more positions first!

PREVENTING DUPLICATES:
Before writing [PLACE:C,P], check your "CANDIDATES USED" list:
- If candidate C is in USED: STOP! Ask "Could you describe that basket differently? I want to make sure I pick the right one."
- If candidate C is in AVAILABLE: Proceed with placement.

When you find the basket, place it right away in ONE message. Do NOT:
- First say "I see it!" and then wait to place in a separate message
- Say "I've placed it" without including the [PLACE:C,P] tag

COMMUNICATION PRINCIPLES:
Express your understanding WITH placement, then ask for next:
- "I see it! The tall woven one. What's next? [PLACE:7,3]" (acknowledge + place + ask for next)
- "Got it - the bunny-shaped basket! Ready for the next one. [PLACE:9,1]" (acknowledge + place + prompt)

When uncertain (NO tag):
- "I see two similar ones - one has flowers, one doesn't. Which one?"
- "Can you describe it differently? I'm not sure which one you mean."

Ask targeted questions (NO tag):
- Focus on distinguishing features: "Does it have handles?", "Is it the darker one or lighter one?"
- NEVER mention candidate numbers in your utterance - your partner can't see them!

Support grounding:
- If you realize a mistake, say so explicitly and use [CLEAR:X] to fix it
- Request re-description for cleared positions

CRITICAL - Do not guess:
- If you cannot confidently identify the candidate, DO NOT include an action tag
- Ask for clarification instead - wrong placements hurt your team's score
- It's always better to ask than to guess incorrectly

EXAMPLES OF CORRECT BEHAVIOR:
- Director: "First basket looks like a bunny" → "Got it! The bunny-shaped one. What's basket 2? [PLACE:9,1]"
- Director: "Basket 2 is tall and narrow" → "I see it - the tall narrow one! Next? [PLACE:12,2]"
- "Wait, I think position 2 was wrong. Can you describe that one again? [CLEAR:2]"
- "I see two similar ones. One has a pattern, one is plain. Which one?" (no tag - asking for clarification)
- After checking sequence shows all ✓: "All 12 positions filled! [SUBMIT]"

WRONG BEHAVIOR (NEVER DO THIS):
- Saying "All done!" when your sequence state shows ○ EMPTY positions
- Using [SUBMIT] when you see "❌ CANNOT SUBMIT" in your sequence state
- Asking "What's next?" when positions 1-5 have gaps
- Placing candidate #7 when "CANDIDATES USED" already includes 7

HANDLING GAPS:
After placing, read your sequence state. If there's a gap (empty position BEFORE a filled one):
- BAD: "Got it! What's next? [PLACE:7,5]" (ignores gap at position 3)
- GOOD: "Placed it! But I see position 3 is empty. Can you re-describe basket 3? [PLACE:7,5]"

Fill positions in order (1, 2, 3...) unless correcting an earlier mistake.
""".strip()


# ===========================================================================
# Output Format Examples (shared structure, varies by style)
# ===========================================================================

DIRECTOR_OUTPUT_FORMAT = """
RESPONSE FORMAT:
Reply naturally in conversation. Describe one basket at a time.

Examples:
- "Basket 1 is a dark woven basket with two curved handles on the sides."
- "This one is shallow and oval-shaped, more like a tray."
- "Yes, it has a decorative pattern around the rim. Does that help?"
- "Great! Moving to basket 2 - this one is tall and narrow..."
""".strip()

MATCHER_OUTPUT_FORMAT = """
RESPONSE FORMAT:
Reply naturally. Put your action tag at the END of your message when taking an action.
If asking a question or uncertain, do NOT include any tag.
""".strip()


# ---------------------------------------------------------------------------
# Prompt Style Registry
# ---------------------------------------------------------------------------

# Two prompt styles:
# - "minimal": Basic task instructions, lets model figure out communication strategy
# - "grounded": Rich communication rules based on Clark & Brennan grounding theory
#               and Gricean maxims (be informative, concise, relevant, clear)

PROMPT_STYLES = {
    "minimal": {
        "director": MINIMAL_DIRECTOR,
        "matcher": MINIMAL_MATCHER,
    },
    "grounded": {
        "director": DETAILED_DIRECTOR,
        "matcher": DETAILED_MATCHER,
    },
    # Backwards compatibility aliases
    "detailed": {
        "director": DETAILED_DIRECTOR,
        "matcher": DETAILED_MATCHER,
    },
}

DEFAULT_STYLE = "grounded"


# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

def get_prompt_style(player: "Player") -> str:
    """Get the prompt style from session config.
    
    Checks for 'prompt_style' first, then 'prompt_strategy' for backwards compat.
    Maps old strategy names: v1 -> minimal, v2/v3 -> grounded
    
    Returns 'grounded' by default.
    """
    try:
        # Check new config key first
        style = player.session.config.get("prompt_style")
        if style in PROMPT_STYLES:
            return style
        
        # Backwards compat: map old prompt_strategy values
        strategy = player.session.config.get("prompt_strategy", "")
        if strategy == "v1":
            return "minimal"
        elif strategy in ("v2", "v3"):
            return "grounded"
    except Exception:
        pass
    return DEFAULT_STYLE


def build_system_prompt(ai_role: str, style: str = DEFAULT_STYLE) -> str:
    """Build the complete system prompt for the given AI role and style."""
    style_prompts = PROMPT_STYLES.get(style, PROMPT_STYLES[DEFAULT_STYLE])
    role_prompt = style_prompts.get(ai_role, "")
    
    # For matcher, inject action tag instructions
    if ai_role == "matcher":
        role_prompt = role_prompt.format(action_tags=ACTION_TAG_INSTRUCTIONS)
    
    # Build complete prompt
    if ai_role == "director":
        return f"{TASK_BACKGROUND}\n\n{role_prompt}\n\n{DIRECTOR_OUTPUT_FORMAT}"
    else:
        return f"{TASK_BACKGROUND}\n\n{role_prompt}\n\n{MATCHER_OUTPUT_FORMAT}"


def build_sequence_state_text(player: "Player") -> str | None:
    """Build a human-readable sequence state for the matcher.
    
    Returns None if not applicable (e.g., for director role).
    Includes both position status AND which candidates have been used.
    """
    from .ai_context import _load_matcher_pool_image_urls
    
    group = getattr(player, "group", None)
    if group is None:
        return None
    
    try:
        partial = json.loads(getattr(group, "ai_partial_sequence", "") or "[]")
    except Exception:
        partial = []
    
    # Load the candidate pool to map images back to candidate numbers
    try:
        pool_items = _load_matcher_pool_image_urls(player)
        # Build image -> candidate number mapping
        image_to_candidate: dict[str, int] = {}
        for idx, item in enumerate(pool_items):
            slot = (item or {}).get("slot") or {}
            img = slot.get("image")
            if img:
                image_to_candidate[img] = idx + 1  # 1-based candidate numbers
    except Exception:
        pool_items = []
        image_to_candidate = {}
    
    # Build position -> image mapping and track used candidates
    # A position is filled if it has a non-null, non-empty image
    filled_positions: dict[int, str | None] = {}
    used_candidates: set[int] = set()
    position_to_candidate: dict[int, int] = {}
    
    if isinstance(partial, list):
        for item in partial:
            if not isinstance(item, dict):
                continue
            pos = item.get("position")
            try:
                pos_int = int(pos)
            except Exception:
                continue
            if 1 <= pos_int <= 12:
                # Check 'image' field - position is filled only if image is non-null/non-empty
                img = item.get("image")
                if img:
                    filled_positions[pos_int] = img
                    # Track which candidate number this corresponds to
                    cand_num = image_to_candidate.get(img)
                    if cand_num:
                        used_candidates.add(cand_num)
                        position_to_candidate[pos_int] = cand_num
                else:
                    filled_positions[pos_int] = None
    
    # Build readable state
    lines = ["YOUR CURRENT SEQUENCE:"]
    empty_positions = []
    for pos in range(1, 13):
        if pos in filled_positions and filled_positions[pos] is not None:
            cand = position_to_candidate.get(pos)
            if cand:
                lines.append(f"  Position {pos}: ✓ filled (candidate #{cand})")
            else:
                lines.append(f"  Position {pos}: ✓ filled")
        else:
            lines.append(f"  Position {pos}: ○ EMPTY")
            empty_positions.append(pos)
    
    filled_count = 12 - len(empty_positions)
    lines.insert(1, f"  ({filled_count}/12 positions filled)")
    
    # Add candidate usage summary
    if used_candidates:
        used_list = sorted(used_candidates)
        available = [c for c in range(1, 19) if c not in used_candidates]
        lines.append(f"\nCANDIDATES USED: {used_list}")
        lines.append(f"CANDIDATES AVAILABLE: {available}")
        lines.append("⚠️ DO NOT reuse a candidate number from the USED list - it will create a gap!")
    
    if empty_positions:
        # Find the highest filled position
        highest_filled = 0
        for pos in range(1, 13):
            if pos in filled_positions and filled_positions[pos] is not None:
                highest_filled = pos
        
        # A "gap" is an empty position that's LOWER than the highest filled position
        # e.g., if positions 1,3,4 are filled but 2 is empty, position 2 is a gap
        gaps = [p for p in empty_positions if p < highest_filled]
        
        if gaps:
            # Real gaps exist - a basket must have moved
            lines.append(f"\n🚨 GAP DETECTED! Position(s) {gaps} are EMPTY but position {highest_filled} is filled.")
            lines.append(f"You MUST ask for re-description: \"Position {gaps[0]} is empty. Can you describe basket {gaps[0]} again?\"")
            lines.append("DO NOT ask \"What's next?\" - you have gaps to fill first!")
        else:
            # No gaps - just normal unfilled positions at the end
            next_pos = empty_positions[0]
            lines.append(f"\nNEXT: Fill position {next_pos}")
        
        # Strong warning about empty positions
        lines.append(f"\n❌ CANNOT SUBMIT: {len(empty_positions)} positions are still empty: {empty_positions}")
    else:
        lines.append("\n✅ ALL 12 POSITIONS FILLED - You may use [SUBMIT] if confident.")
    
    return "\n".join(lines)


def build_conversation_history(player: "Player", all_history: list[dict]) -> list[dict[str, Any]]:
    """Convert stored chat history into OpenAI message format.
    
    - Human messages -> role='user'
    - AI messages -> role='assistant'
    - Feedback messages -> role='user' (system info presented as context)
    """
    messages: list[dict[str, Any]] = []
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"
    
    for msg in all_history:
        sender = msg.get("sender_role")
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        
        if sender == ai_role:
            role = "assistant"
        else:
            role = "user"
        
        # Handle multimodal feedback messages with images
        image_url = msg.get("image_url")
        if image_url and msg.get("is_feedback"):
            content = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
            messages.append({"role": role, "content": content})
        else:
            messages.append({"role": role, "content": text})
    
    return messages


def build_prompt_messages(
    player: "Player",
    latest_message: str | None,
    all_history: list[dict],
    visual_context_message: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Build the complete prompt message list for the AI.
    
    Args:
        player: The oTree Player object
        latest_message: The most recent message from the human (or None for director start)
        all_history: Full conversation history
        visual_context_message: Pre-built visual context message (image or reminder)
    
    Returns:
        List of messages ready for the OpenAI API.
    """
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"
    current_round = getattr(player, "round_number", 1) or 1
    
    # Get prompt style from session config
    style = get_prompt_style(player)
    
    messages: list[dict[str, Any]] = []
    
    # 1. System prompt (task + role + output format)
    system_prompt = build_system_prompt(ai_role, style)
    messages.append({"role": "system", "content": system_prompt})
    
    # 2. Visual context (provided by caller - image or reminder)
    if visual_context_message:
        messages.append(visual_context_message)
    
    # 3. Sequence state (matcher only)
    if ai_role == "matcher":
        seq_state = build_sequence_state_text(player)
        if seq_state:
            messages.append({"role": "system", "content": seq_state})
    
    # 4. Conversation history (full history, no truncation)
    history_messages = build_conversation_history(player, all_history)
    messages.extend(history_messages)
    
    # 5. Latest message or start prompt
    if latest_message:
        # Check if latest message is already in history
        if history_messages:
            last = history_messages[-1]
            last_content = last.get("content")
            if isinstance(last_content, str) and last_content.strip() == latest_message.strip():
                # Already included, don't duplicate
                pass
            else:
                messages.append({"role": "user", "content": latest_message})
        else:
            messages.append({"role": "user", "content": latest_message})
    elif ai_role == "director":
        # Director needs a start prompt on first turn
        start_prompt = (
            f"Round {current_round} is starting. Please describe Basket 1 "
            f"(top-left in your grid). Remember: one basket per message, "
            f"wait for my confirmation before moving to basket 2."
        )
        messages.append({"role": "user", "content": start_prompt})
    
    return messages


# ---------------------------------------------------------------------------
# Response Parsing (shared across all styles)
# ---------------------------------------------------------------------------

# Tag patterns for action extraction
# [PLACE:C,P] - candidate C (1-18) in position P (1-12)
# [CLEAR:P] - clear position P
# [MOVE:P1>P2] - move from position P1 to P2
# [SUBMIT] - submit final sequence
TAG_PATTERNS = {
    "place": r"\[PLACE:(\d{1,2}),(\d{1,2})\]",
    "clear": r"\[CLEAR:(\d{1,2})\]",
    "move": r"\[MOVE:(\d{1,2})>(\d{1,2})\]",
    "submit": r"\[SUBMIT\]",
}


def strip_action_tags(text: str) -> str:
    """Remove all action tags from text, returning clean utterance for display."""
    import re
    
    # Remove all known tag patterns
    cleaned = text
    cleaned = re.sub(r"\[PLACE:\d{1,2},\d{1,2}\]", "", cleaned)
    cleaned = re.sub(r"\[CLEAR:\d{1,2}\]", "", cleaned)
    cleaned = re.sub(r"\[MOVE:\d{1,2}>\d{1,2}\]", "", cleaned)
    cleaned = re.sub(r"\[SUBMIT\]", "", cleaned)
    
    # Clean up extra whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    return cleaned


def parse_matcher_response(text: str) -> dict[str, Any]:
    """
    Parse the matcher's response to extract action tags and clean utterance.
    
    Action tags are lightweight markers at the end of natural language:
    - [PLACE:C,P] - Place candidate C (1-18) in position P (1-12)
    - [CLEAR:P] - Clear/remove position P
    - [MOVE:P1>P2] - Move basket from position P1 to position P2
    - [SUBMIT] - Submit the final sequence
    
    Returns:
        {
            "utterance": str,  # Clean text with tags stripped (for display)
            "raw_text": str,   # Original text including tags
            "action": str | None,  # "place", "clear", "move", "submit", or None
            "candidate_index": int | None,  # Candidate 1-18 for place action
            "position": int | None,  # Target position for place/clear
            "from_position": int | None,  # Source position for move
            "to_position": int | None,  # Destination position for move
            "ready_to_submit": bool,  # True if submit action
        }
    """
    import re
    
    result = {
        "utterance": strip_action_tags(text),
        "raw_text": text.strip(),
        "action": None,
        "candidate_index": None,
        "position": None,
        "from_position": None,
        "to_position": None,
        "ready_to_submit": False,
    }
    
    if not text:
        return result
    
    # Check for [PLACE:C,P] tag (candidate, position)
    place_match = re.search(TAG_PATTERNS["place"], text)
    if place_match:
        candidate = int(place_match.group(1))
        pos = int(place_match.group(2))
        if 1 <= candidate <= 18 and 1 <= pos <= 12:
            result["action"] = "place"
            result["candidate_index"] = candidate
            result["position"] = pos
            return result
    
    # Check for [CLEAR:P] tag
    clear_match = re.search(TAG_PATTERNS["clear"], text)
    if clear_match:
        pos = int(clear_match.group(1))
        if 1 <= pos <= 12:
            result["action"] = "clear"
            result["position"] = pos
            return result
    
    # Check for [MOVE:P1>P2] tag
    move_match = re.search(TAG_PATTERNS["move"], text)
    if move_match:
        from_pos = int(move_match.group(1))
        to_pos = int(move_match.group(2))
        if 1 <= from_pos <= 12 and 1 <= to_pos <= 12:
            result["action"] = "move"
            result["from_position"] = from_pos
            result["to_position"] = to_pos
            result["position"] = to_pos  # For backward compat
            return result
    
    # Check for [SUBMIT] tag
    submit_match = re.search(TAG_PATTERNS["submit"], text)
    if submit_match:
        result["action"] = "submit"
        result["ready_to_submit"] = True
        return result
    
    # FALLBACK: No tags found - try natural language parsing as backup
    # This handles cases where the AI forgets to use tags
    text_lower = text.lower()
    
    # Check for natural language submit indicators
    submit_patterns = [
        r"ready to submit",
        r"all done.*submit",
        r"let'?s submit",
    ]
    for pattern in submit_patterns:
        if re.search(pattern, text_lower):
            result["action"] = "submit"
            result["ready_to_submit"] = True
            logging.debug("[PARSE] Fallback: detected submit from natural language")
            return result
    
    # No action detected - this is fine, might just be a question
    return result