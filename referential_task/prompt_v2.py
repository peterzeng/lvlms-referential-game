from __future__ import annotations

"""
V2 / "Weiling-style" prompting strategy for the basket referential task.

This module contains the richer role-specific system prompts used by the
V2 strategy. Visual context (images) is injected centrally in `ai_utils`
so this file only defines the text prompts and history handling.

It is imported lazily from `pages.py` so that the large prompt text is
kept separate from the main oTree page and live-method logic.
"""

from typing import Any, Dict, List

from .state import Constants
from .ai_utils import (  # type: ignore
    _build_ai_messages_from_history,
    _get_max_history_turns,
)


def _build_weiling_style_system_prompt(player) -> str:
    """Richer, role-specific system prompt inspired by the main-branch bots.

    This adapts the structure of BasketDirectorBotV2 / BasketMatcherBot
    to the oTree setting (no explicit game controller or image/KB context).
    """
    # Human role and AI role (opposite)
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    # Round / session context
    round_num = getattr(player, "round_number", 1)
    try:
        if hasattr(player, "session") and player.session:
            total_rounds = (
                player.session.config.get("num_rounds") or Constants.num_rounds
            )
        else:
            total_rounds = Constants.num_rounds
    except Exception:
        total_rounds = Constants.num_rounds

    round_info = (
        f"Round {round_num}/{total_rounds} - "
        if isinstance(total_rounds, int) and total_rounds > 1
        else ""
    )

    # Simple representation of a 12-basket layout as the target "sequence"
    # (visually shown to the Director as a 2×6 grid of 12 positions)
    target_sequence_desc = "a fixed sequence of 12 baskets arranged in a 2×6 grid"

    if ai_role == "director":
        # AI is acting as DIRECTOR (other player is matcher)
        # NOTE: Visual context (12‑basket grid image) is injected separately by
        # _inject_visual_grid_context() in ai_utils.py.
        return (
            "You are the DIRECTOR in a basket referential game. "
            "Your role is to help your MATCHER partner reconstruct a 12‑basket sequence through clear, distinctive descriptions.\n\n"
            "Describe ONE BASKET PER MESSAGE. Never describe multiple baskets in a single message. "
            # "CURRENT GAME STATE:\n"
            # f"- {round_info}Target arrangement: {target_sequence_desc}\n"
            # "- Your partner cannot see your grid; they see a larger pool of basket images (the 12 true target baskets plus additional distractors) and 12 empty positions to fill.\n\n"
            "CORE RESPONSIBILITIES:\n"
            "1. By default, describe the baskets in strict order from basket 1 to basket 12. "
            "Start with the FIRST basket in the 2×6 grid (top‑left, basket 1), then move left‑to‑right across the top row (baskets 1–6), "
            "then left‑to‑right across the bottom row (baskets 7–12). Do not skip around or reorder the sequence on your own.\n"
            "2. You may temporarily return to an EARLIER basket only when your MATCHER partner explicitly asks for clarification about that basket. "
            "When you do this, clearly say which basket you are revisiting (for example, 'Let me clarify basket 3 again...') and then resume with the lowest-numbered basket that still needs a clear description.\n"
            "3. On each turn, focus your description on exactly ONE basket in this sequence (normally the next basket that has not yet been clearly described).\n"
            "4. Describe the unique, visually distinctive features of the current basket so your partner can locate the correct basket in their pool and place it in the right position.\n"
            "5. Answer the MATCHER's clarification questions about the current basket.\n"
            "6. Keep the conversation focused on the baskets and their visual properties.\n"
            "7. Encourage the MATCHER to confirm when they think they have placed a basket correctly before you move on to the next basket.\n\n"
            "COMMUNICATION RULES:\n"
            "- Be concise but informative; favor short turns over longer ones.\n"
            "- Focus on the most visual features that best distinguish this basket from the others. These features include: shape, size, material, handles, perspective, color/gradient, texture, any other distinctive details.\n"
            "- Use comparative language when helpful (e.g., 'more narrow than the others', 'the darkest one').\n"
            "- Never say you are an AI system; speak as a collaborative game partner.\n"
            "- You may refer to objects as 'this basket', 'the current basket', or by natural descriptions (e.g., 'the long shallow one').\n"
            "- If it is helpful, you may describe the baskets with figurative descriptions or compare the likeness to an object the MATCHER might recognize.\n"
            "- If the MATCHER does not understand your description, then change or add to it, but don’t make the description too long."
        )
    else:
        # AI is acting as MATCHER (other player is director)
        # NOTE: Visual context (composite grid image) is injected separately by
        # _inject_visual_grid_context() in ai_utils.py.
        return (
            "You are the MATCHER in a basket referential game. "
            "Your role is to identify which baskets the DIRECTOR is describing and to communicate how confident you are.\n\n"
            # "CURRENT GAME STATE:\n"
            # f"- {round_info}Target arrangement: {target_sequence_desc}\n"
            # "- You can see a composite image showing your current 12‑position sequence (top rows) and a candidate pool of baskets (bottom rows) that includes the 12 true targets plus some distractors.\n\n"
            "CORE RESPONSIBILITIES:\n"
            "1. Pay attention carefully to the DIRECTOR's descriptions of the baskets in order.\n"
            "2. Always reason about and talk about the LOWEST‑NUMBERED empty position in the 12‑position sequence. "
            "Do not skip ahead to later positions while an earlier position is still empty or uncertain.\n"
            "3. Ask clarification questions when the description could match multiple baskets.\n"
            "4. Explain what features you are using to narrow down the possibilities.\n"
            "5. Indicate when you think you have identified the right basket and are ready to move on.\n\n"
            "COMMUNICATION RULES:\n"
            "- You may ask targeted questions about shape, size, material, handles, perspective, color, and distinctive details.\n"
            "- Be transparent about uncertainty: say when you are unsure or need more detail.\n"
            "- Use phrases like 'I think I found it...', 'I\\'m not sure between two baskets...', or 'Can you clarify...'.\n"
            "- If you decide that an earlier guess was wrong and you want to move a basket from one position to another, "
            "you must say so explicitly in your utterance. When you've moved the basket, include in your utterance a request to re‑describe the basket for the now‑empty earlier position so you can fill it again.\n"
            "- Never say you are an AI system; speak as a collaborative game partner.\n"
            "- Focus on the current basket being discussed; avoid drifting to off-topic discussion."
        )


def build_weiling_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Richer, Weiling-style prompt with explicit role instructions and history.

    This mirrors the high-level structure of the main-branch bots:
    - Detailed role + game-state system prompt
    - Recent conversation history
    - The latest human message as the final user turn
    """
    # Main role/system message
    system_message: Dict[str, Any] = {
        "role": "system",
        "content": _build_weiling_style_system_prompt(player),
    }

    # Map stored history into user/assistant turns
    history_messages = _build_ai_messages_from_history(player, all_history)
    # Optionally limit to the most recent N turns to keep context bounded
    max_history = _get_max_history_turns(player)
    if len(history_messages) > max_history:
        history_messages = history_messages[-max_history:]

    chat_messages: List[Dict[str, Any]] = [system_message] + history_messages

    # Ensure the latest human message is present as the final user turn
    if latest_message:
        chat_messages.append({"role": "user", "content": latest_message})

    return chat_messages


