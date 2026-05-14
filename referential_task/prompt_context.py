from __future__ import annotations

import json
import os
import re as _re
from typing import Any

from .state import Constants, Player


# ---------------------------------------------------------------------------
# Shared task background (mirrors what human participants see at game start)
# ---------------------------------------------------------------------------
TASK_BACKGROUND = """
TASK BACKGROUND (shared with both partners):
You are on a team with a partner. Your goal is to work together to match the correct order of a set of baskets. The game consists of 5 rounds, and in each round, your team must correctly order 12 baskets.

There are two distinct roles: the Director and the Matcher. Both partners see the same 12 target baskets, but the Matcher sees additional distractor baskets mixed in.

Director: Sees the correct target sequence for the 12 baskets and describes each basket one by one (in order starting with the upper-left basket) to the Matcher via live chat.

Matcher: Sees these 12 target baskets plus some additional baskets. As the Director describes each basket, the Matcher interprets the description, asks clarifying questions if needed, and selects the correct target basket.

You can communicate back and forth as much as needed. If you discover an error, it is fine to make corrections within a round. When the round is finished, the Matcher submits the sequence, and both players see the score.
""".strip()


def _is_instruction_message(message: dict[str, Any]) -> bool:
    """Return True for high-priority application instruction messages."""
    return message.get("role") in ("developer", "system")


def _inject_task_background(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepend the shared task background as a developer instruction.

    This ensures the AI has the same high-level context that human participants
    receive at the start of the game, regardless of which prompt strategy is used.
    """
    if not messages:
        return messages

    background_message = {
        "role": "developer",
        "content": TASK_BACKGROUND,
    }
    return [background_message] + messages

def _should_log_acl_reasoning(player: Player) -> bool:
    """Return True if we should persist ACL_prompt reasoning JSON for this session.

    Controlled by (in order of precedence):
    - session.config['log_acl_reasoning'] (truthy)
    - LOG_ACL_REASONING environment variable
    """
    try:
        if hasattr(player, "session") and player.session:
            if bool(player.session.config.get("log_acl_reasoning", False)):
                return True
    except Exception:
        pass

    flag = os.environ.get("LOG_ACL_REASONING", "").strip().lower()
    return flag in ("1", "true", "yes")

def _ai_debug_enabled(player: Player | None) -> bool:
    """Return True when we should surface explicit AI‑offline messages in chat.

    This is intended only for local testing / debugging so that silent failures
    (missing API key, import issues, etc.) are obvious to the experimenter.

    Controlled by:
    - session.config['ai_debug_enabled'] (preferred)
    - or, as a fallback, session.config['testing_debug_enabled']
    """
    try:
        if not player or not hasattr(player, "session") or not player.session:
            return False
        cfg = player.session.config or {}
        if cfg.get("ai_debug_enabled") is not None:
            return bool(cfg.get("ai_debug_enabled"))
        # Back‑compat: reuse existing testing flag if present.
        return bool(cfg.get("testing_debug_enabled", False))
    except Exception:
        return False


import re as _re


def _build_director_conversation_state(player: Player) -> dict[str, Any]:
    """Build the Director's game-progress state from conversation history ONLY.

    Unlike _build_matcher_current_sequence_state_for_prompt (which reads the
    Matcher's actual selections), this function derives the Director's notion
    of "completed positions" solely from the chat transcript.  A position is
    considered completed when:
      1. The Director sent a message starting with "Basket <N>" (describing it).
      2. The Matcher subsequently sent a confirmation (contains "Placed",
         "Done", "Confirmed", "Got it", or "Placing") BEFORE the Director
         moved on to a different basket number.

    This preserves the information asymmetry required by the experiment: the
    Director never learns which candidate the Matcher actually selected.
    """
    import logging

    # Gather current-round messages
    group = getattr(player, "group", None)
    if group is None:
        return {"completed_positions": [], "next_target": 1}

    try:
        msgs = json.loads(getattr(group, "ai_messages", "") or "[]")
    except Exception:
        msgs = []

    # Confirmation phrases the Matcher uses to signal placement.
    _CONFIRM_PATTERNS = (
        "placed", "done", "confirmed", "got it", "placing",
        "go to basket", "round complete",
    )

    # Walk through messages in order and track which basket the Director is
    # currently describing, and whether the Matcher confirmed it.
    completed: set[int] = set()
    current_director_basket: int | None = None

    for msg in msgs:
        if not isinstance(msg, dict):
            continue
        sender = (msg.get("sender_role") or "").lower()
        text = (msg.get("text") or "").strip()
        if not text:
            continue

        if sender == "director":
            # Check if the Director is introducing a new basket number.
            # Patterns: "Basket 7: ...", "Basket 7 = ...", "Basket 7 —"
            m = _re.match(r"Basket\s+(\d+)\b", text, _re.IGNORECASE)
            if m:
                basket_num = int(m.group(1))
                if 1 <= basket_num <= 12:
                    current_director_basket = basket_num
            # If the Director answers a clarification question (no new
            # basket number), current_director_basket stays the same.

        elif sender == "matcher":
            text_lower = text.lower()
            if current_director_basket is not None:
                # Check if this message is a confirmation.
                if any(pat in text_lower for pat in _CONFIRM_PATTERNS):
                    completed.add(current_director_basket)
                    current_director_basket = None  # reset for next basket
                # Otherwise it's a clarification question — don't mark as done.

        elif sender == "system":
            # Check for notices about vacated positions (from Matcher moving a basket)
            if "is now EMPTY" in text:
                m_v = _re.search(r"position (\d+) is now EMPTY", text)
                if m_v:
                    vacated_num = int(m_v.group(1))
                    if vacated_num in completed:
                        completed.remove(vacated_num)

    completed_sorted = sorted(completed)

    # Next target = lowest position in 1..12 not yet confirmed.
    next_target = None
    for i in range(1, 13):
        if i not in completed:
            next_target = i
            break

    logging.debug(
        "[DIRECTOR_CONV_STATE] completed=%s next_target=%s",
        completed_sorted, next_target,
    )

    return {
        "completed_positions": completed_sorted,
        "next_target": next_target,
    }


def _build_matcher_current_sequence_state_for_prompt(player: Player) -> dict[str, Any]:
    """Build an explicit 12-slot state for the AI matcher prompt.

    We store the incremental state as `group.ai_partial_sequence` (by position,
    with image paths). The matcher chooses by `candidate_index` (1–18), so for
    prompting we also map each placed image path back to its pool index using
    the same deterministic pool ordering used in the composite image.
    """
    state: dict[str, Any] = {
        "sequence_candidate_indices": [None] * 12,
        "sequence_slots": [
            {
                "position": pos,
                "candidate_index": None,
                "image": None,
                "originalPosition": None,
            }
            for pos in range(1, 13)
        ],
    }

    group = getattr(player, "group", None)
    if group is None:
        return state

    # Load current partial sequence (list of {position, image, originalPosition}).
    try:
        partial = json.loads(getattr(group, "ai_partial_sequence", "") or "[]")
    except Exception:
        partial = []

    pos_to_item: dict[int, dict[str, Any]] = {}
    if isinstance(partial, list):
        for item in partial:
            if not isinstance(item, dict):
                continue
            img = (item.get("image") or "").strip()
            if not img:
                continue
            try:
                pos_int = int(item.get("position"))
            except Exception:
                continue
            if 1 <= pos_int <= 12:
                pos_to_item[pos_int] = item

    # Map image path -> candidate_index based on the pool ordering used by the UI/composite.
    image_to_candidate_index: dict[str, int] = {}
    try:
        from .visual_context import _load_matcher_pool_image_urls
        pool_items = _load_matcher_pool_image_urls(player) or []
    except Exception:
        pool_items = []
    pool_images: list[str] = []
    for it in pool_items:
        slot = (it or {}).get("slot") or {}
        img = (slot.get("image") or "").strip()
        if img:
            pool_images.append(img)
    pool_images = pool_images[:18]
    for idx, img in enumerate(pool_images, start=1):
        image_to_candidate_index.setdefault(img, idx)

    for pos in range(1, 13):
        item = pos_to_item.get(pos)
        if not item:
            continue
        img = (item.get("image") or "").strip() or None
        orig = item.get("originalPosition")
        cand_idx = image_to_candidate_index.get(img) if img else None
        state["sequence_candidate_indices"][pos - 1] = cand_idx
        state["sequence_slots"][pos - 1] = {
            "position": pos,
            "candidate_index": cand_idx,
            "image": img,
            "originalPosition": orig,
        }

    return state


def _get_pending_refill_positions(player: Player) -> list[int]:
    """Return completed-in-dialogue positions that are currently empty on the board.

    These are vacancies caused by the matcher reusing/moving a basket. They
    should be surfaced only as hidden matcher prompt context, not as visible
    chat messages.
    """
    try:
        conv_state = _build_director_conversation_state(player)
        completed_positions = {
            int(pos) for pos in conv_state.get("completed_positions", []) if pos is not None
        }
    except Exception:
        completed_positions = set()

    try:
        seq_state = _build_matcher_current_sequence_state_for_prompt(player)
        filled_positions = {
            int(slot.get("position"))
            for slot in seq_state.get("sequence_slots", [])
            if isinstance(slot, dict) and slot.get("image") and slot.get("position") is not None
        }
    except Exception:
        filled_positions = set()

    return sorted(pos for pos in completed_positions if pos not in filled_positions)


def _build_ai_messages_from_history(
    player: Player, history, ai_role: str | None = None
):
    """Convert stored chat history into OpenAI chat messages.

    - Messages from the partner perspective are mapped to role='user'
    - Messages from the generated role are mapped to role='assistant'
    - Feedback/system messages are mapped to role='user' (shared context info)
    - Round boundary markers are inserted when the round changes (for cross-round history)
    """
    messages: list[dict[str, Any]] = []
    if ai_role not in ("director", "matcher"):
        human_role = (
            player.field_maybe_none("player_role") or player.participant.vars.get("role")
        )
        ai_role = "matcher" if human_role == "director" else "director"
    
    # Get current round to distinguish past rounds from current round
    current_round = getattr(player, "round_number", 1) or 1
    
    # Track the last round we saw to insert boundary markers
    last_seen_round = None

    for msg in history:
        msg_round = msg.get("round_number")
        sender = msg.get("sender_role")
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        
        # Insert a round boundary marker when entering a new round's messages
        # This helps the model understand that basket arrangements differ per round
        if msg_round is not None and msg_round != last_seen_round:
            if last_seen_round is not None or msg_round < current_round:
                # Insert marker for previous round history
                if msg_round < current_round:
                    boundary_text = (
                        f"═══ ROUND {msg_round} HISTORY (PAST - DIFFERENT BASKETS) ═══\n"
                        f"The following messages are from Round {msg_round}, which had a DIFFERENT basket arrangement. "
                        f"Learn from the communication strategies and terminology that worked, but do NOT reuse "
                        f"descriptions literally - the baskets are in different positions now."
                    )
                    messages.append({"role": "user", "content": boundary_text})
                elif msg_round == current_round and last_seen_round is not None:
                    # Entering current round after seeing past history
                    boundary_text = (
                        f"═══ ROUND {msg_round} (CURRENT ROUND - ACTIVE) ═══\n"
                        f"The following messages are from the CURRENT round. "
                        f"Use the image labeled 'ROUND {msg_round}' to see the actual basket arrangement."
                    )
                    messages.append({"role": "user", "content": boundary_text})
            last_seen_round = msg_round
        
        if sender == ai_role:
            role = "assistant"
        elif sender == "system" or msg.get("is_feedback"):
            # Feedback messages are shared context (both players see round results)
            # Treat as user message to maintain conversation flow
            role = "user"
        else:
            role = "user"

        # NOTE: We intentionally DO NOT include feedback images in the prompt.
        # Including feedback images (with green/red borders from previous rounds)
        # confuses the model - it describes baskets from feedback images instead of
        # the current round's target grid. The text description of results is sufficient.
        messages.append({"role": role, "content": text})
    return messages


def _compute_round_correct_count(player: Player) -> int | None:
    """Compute how many baskets were correctly placed in a given round.

    This mirrors the logic from RoundFeedback.vars_for_template.
    Returns None if the round data is incomplete or unavailable.
    """
    try:
        shared_grid = json.loads(player.group.shared_grid or "[]")
        matcher_sequence = json.loads(player.group.matcher_sequence or "[]")
    except Exception:
        return None

    if not shared_grid or not matcher_sequence:
        return None

    # Build correct sequence (target order)
    correct_sequence = [slot.get("image") for slot in shared_grid]

    # Build matcher's submissions by position
    matcher_by_pos = {}
    for item in matcher_sequence:
        if not isinstance(item, dict):
            continue
        pos = item.get("position")
        try:
            pos_int = int(pos)
        except (TypeError, ValueError):
            continue
        if 1 <= pos_int <= 12 and pos_int not in matcher_by_pos:
            matcher_by_pos[pos_int] = item

    # Count correct placements
    correct_count = 0
    for i in range(12):
        correct_img = correct_sequence[i] if i < len(correct_sequence) else None
        submitted_entry = matcher_by_pos.get(i + 1)
        submitted_img = submitted_entry.get("image") if submitted_entry else None
        if (
            submitted_img is not None
            and correct_img is not None
            and submitted_img == correct_img
        ):
            correct_count += 1

    return correct_count


def _get_prompt_strategy_name(player: Player) -> str:
    """Return the configured prompt strategy name.

    Strategy can be set per-session via `session.config['prompt_strategy']`
    or globally via PROMPT_STRATEGY env var. Defaults to ACL_prompt.
    """
    # Session-level override (preferred)
    try:
        if hasattr(player, "session") and player.session:
            cfg_name = player.session.config.get("prompt_strategy")
            if isinstance(cfg_name, str) and cfg_name.strip():
                return cfg_name.strip().lower()
    except Exception:
        pass

    # Environment-level default
    env_name = os.environ.get("PROMPT_STRATEGY", "").strip().lower()
    if env_name:
        return env_name

    return "acl_prompt"


def _is_acl_prompt_strategy(strategy_name: str) -> bool:
    """Return True for ACL_prompt strategy aliases."""
    return strategy_name in ("acl_prompt", "acl-prompt", "acl")


def _normalize_prompt_strategy(strategy_name: str) -> str:
    """Map removed or legacy strategy names onto currently available strategies."""
    if strategy_name in (
        "director_visual",
        "visual_director",
        "matcher_visual",
        "visual_matcher",
        "simple",
        "v1",
        "weiling",
        "v2",
        "v4",
        "v4_cg",
        "v5",
        "v6",
        "v9",
    ):
        return "acl_prompt"
    return strategy_name
