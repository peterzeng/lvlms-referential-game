"""
Core AI reply generation logic for the basket referential task.

This module handles:
- Computing round correct counts (for feedback)
- Generating AI replies via OpenAI API
- Coordinating with the unified prompt builder

This is the main entry point for AI reply generation, used by page_views.py.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import Player


# ---------------------------------------------------------------------------
# Round Feedback Computation
# ---------------------------------------------------------------------------


def _compute_round_correct_count(player: "Player") -> int | None:
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


# ---------------------------------------------------------------------------
# History Loading
# ---------------------------------------------------------------------------


def _load_conversation_history(player: "Player") -> list[dict[str, Any]]:
    """Load and merge conversation history from human and AI messages.
    
    Supports optional cross-round history for learning across rounds.
    Returns a sorted list of message dicts.
    """
    use_cross_round_history = False
    try:
        if hasattr(player, "session") and player.session:
            use_cross_round_history = bool(
                player.session.config.get("cross_round_history", False)
            )
    except Exception:
        use_cross_round_history = False

    human_msgs = []
    ai_msgs = []
    feedback_msgs = []

    if use_cross_round_history:
        try:
            all_round_players = player.in_all_rounds()
        except Exception:
            all_round_players = [player]
        
        current_round = getattr(player, "round_number", 1)
        
        for p_round in all_round_players:
            round_num = getattr(p_round, "round_number", None)
            
            # Human messages from this round
            try:
                msgs = json.loads(p_round.grid_messages or "[]")
            except Exception:
                msgs = []
            for m in msgs:
                if isinstance(m, dict):
                    if round_num is not None and "round_number" not in m:
                        m = dict(m)
                        m["round_number"] = round_num
                    human_msgs.append(m)
            
            # AI messages from this round's group
            try:
                ai_round_msgs = json.loads(p_round.group.ai_messages or "[]")
            except Exception:
                ai_round_msgs = []
            for m in ai_round_msgs:
                if isinstance(m, dict):
                    if round_num is not None and "round_number" not in m:
                        m = dict(m)
                        m["round_number"] = round_num
                    ai_msgs.append(m)

            # For completed rounds, inject feedback summary (text only - no images)
            # NOTE: We intentionally do NOT include feedback images because they
            # confuse the model - it describes baskets from feedback images instead
            # of the current round's target grid.
            if round_num is not None and round_num < current_round:
                correct_count = _compute_round_correct_count(p_round)
                if correct_count is not None:
                    feedback_msgs.append({
                        "text": (
                            f"[ROUND {round_num} COMPLETE: {correct_count}/12 correct. "
                            f"NOTE: The baskets have been RESHUFFLED for the next round - "
                            f"position numbers no longer correspond to the same baskets. "
                            f"Learn from communication strategies, but describe baskets fresh from the new image.]"
                        ),
                        "sender_role": "system",
                        "round_number": round_num,
                        "is_feedback": True,
                    })
    else:
        # Single-round history
        try:
            msgs = json.loads(player.grid_messages or "[]")
        except Exception:
            msgs = []
        for m in msgs:
            if isinstance(m, dict):
                human_msgs.append(m)
        try:
            ai_msgs = json.loads(player.group.ai_messages or "[]")
        except Exception:
            ai_msgs = []

    # Merge and sort by (round_number, timestamp)
    all_history = []
    for m in human_msgs + ai_msgs + feedback_msgs:
        if isinstance(m, dict):
            all_history.append(m)
    
    all_history.sort(
        key=lambda m: (
            m.get("round_number") or 0,
            1 if m.get("is_feedback") else 0,
            m.get("server_ts") or "",
            m.get("timestamp") or "",
        )
    )
    
    return all_history


# ---------------------------------------------------------------------------
# Main Reply Generation
# ---------------------------------------------------------------------------


def _generate_ai_reply(player: "Player", latest_message: str | None):
    """Generate a GPT-4o reply for the AI partner.

    Returns a dict of the form:
        {
            "text": "<utterance to show in chat>" or None,
            "selection": {
                "candidate_index": int | None,
                "position": int | None,
                "ready_to_submit": bool,
            } | None,
        }

    For non-matcher roles (AI as DIRECTOR) the ``selection`` field is always None.
    """
    from .ai_utils import (
        _ai_debug_enabled,
        _get_ai_client,
        _get_ai_model,
        _is_gpt_5_2_model,
        _build_api_call_kwargs,
    )
    from .ai_context import _inject_visual_grid_context
    from .prompt import (
        build_prompt_messages,
        get_prompt_style,
        parse_matcher_response,
        parse_natural_language_response,
    )

    client = _get_ai_client()
    if client is None:
        if _ai_debug_enabled(player):
            human_role = (
                player.field_maybe_none("player_role")
                or player.participant.vars.get("role")
            )
            ai_role = "matcher" if human_role == "director" else "director"
            return {
                "text": (
                    f"[DEBUG] AI partner not configured (missing OPENAI_API_KEY). "
                    f"The {ai_role.upper()} will not respond automatically."
                ),
                "selection": None,
            }
        return None

    try:
        human_role = (
            player.field_maybe_none("player_role")
            or player.participant.vars.get("role")
        )
        ai_role = "matcher" if human_role == "director" else "director"

        # Load conversation history
        all_history = _load_conversation_history(player)

        # Build prompt messages using unified prompt builder
        chat_messages = build_prompt_messages(
            player=player,
            latest_message=latest_message,
            all_history=all_history,
            visual_context_message=None,  # Will be injected below
        )

        # Inject visual context (image on first turn, reminder otherwise)
        chat_messages = _inject_visual_grid_context(player, chat_messages)

        # Log message structure for debugging
        for i, msg in enumerate(chat_messages):
            role = msg.get("role", "?")
            content = msg.get("content")
            if isinstance(content, list):
                parts_desc = []
                for part in content:
                    if isinstance(part, dict):
                        ptype = part.get("type", "?")
                        if ptype == "image_url":
                            url = (part.get("image_url") or {}).get("url", "")
                            parts_desc.append(f"image({len(url)} chars)")
                        elif ptype == "text":
                            text_preview = (part.get("text") or "")[:40]
                            parts_desc.append(f"text({text_preview}...)")
                logging.debug("[PROMPT %d] role=%s, multimodal: %s", i, role, ", ".join(parts_desc))
            else:
                content_preview = str(content)[:60] if content else "(empty)"
                logging.debug("[PROMPT %d] role=%s: %s...", i, role, content_preview)

        # Get model configuration and build API call parameters
        model = _get_ai_model(player)
        api_params = _build_api_call_kwargs(
            model=model,
            messages=chat_messages,
            player=player,
        )
        
        logging.info(
            "[AI_REPLY] Using model: %s (is_gpt_5_2=%s)",
            model, _is_gpt_5_2_model(model)
        )
        
        # Make API call
        completion = client.chat.completions.create(**api_params)

        reply = completion.choices[0].message.content
        if isinstance(reply, list):
            reply = "".join(
                (part.get("text", "") if isinstance(part, dict) else str(getattr(part, 'text', '')))
                for part in reply
            )
        text = (reply or "").strip()
        
        logging.info("[AI_REPLY] %s raw response: %s", ai_role.upper(), text[:100] if text else "(empty)")

        # Parse response based on role and style
        if ai_role == "matcher":
            # Choose parser based on prompt style
            style = get_prompt_style(player)
            if style == "natural":
                parsed = parse_natural_language_response(text)
                display_text = text  # Natural style - show the full response as-is
            else:
                parsed = parse_matcher_response(text)
                # Use cleaned utterance (tags stripped) for display to human
                display_text = parsed.get("utterance", text)
            
            # Build selection dict if an action was detected
            selection = None
            action = parsed.get("action")
            
            if action:
                selection = {
                    "action": action,
                    "position": parsed.get("position"),
                    "from_position": parsed.get("from_position"),
                    "to_position": parsed.get("to_position"),
                    "candidate_index": parsed.get("candidate_index"),
                    "ready_to_submit": parsed.get("ready_to_submit", False),
                }
                logging.info(
                    "[AI_REPLY] Matcher action: %s, selection: %s",
                    action, selection
                )
            
            return {"text": display_text, "selection": selection}
        else:
            # Director - no selection parsing needed
            return {"text": text, "selection": None}

    except Exception as e:
        import traceback
        logging.error(
            "[AI_REPLY] Error: %s: %s\n%s",
            type(e).__name__, e, traceback.format_exc()
        )

        if _ai_debug_enabled(player):
            return {
                "text": f"[DEBUG] AI error: {type(e).__name__}. Human can continue without AI.",
                "selection": None,
            }
        return None


# ---------------------------------------------------------------------------
# Backward Compatibility Exports
# ---------------------------------------------------------------------------

# These are kept for any code that might import them directly
def _build_ai_messages_from_history(player: "Player", history):
    """Deprecated: Use prompt.build_conversation_history instead."""
    from .prompt import build_conversation_history
    return build_conversation_history(player, history)
