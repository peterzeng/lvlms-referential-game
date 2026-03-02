from __future__ import annotations

"""
V1 / "simple" prompting strategy for the basket referential task.

This module is imported lazily from `pages.py` so that the large prompt
definitions live in a separate file, making the main oTree page logic
easier to read and present.
"""

from typing import Any, List, Dict

# Internal helper imported from the main pages module. We import from
# `.pages` rather than duplicating logic so that history handling stays
# centralised in one place.
from .ai_utils import _build_ai_messages_from_history  # type: ignore


def build_simple_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Original lightweight prompt: single system message + mapped history.
    """
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    # NOTE: Visual context (images of the basket grid) is injected separately by
    # _inject_visual_grid_context() in ai_utils.py — no need to mention images here.

    if ai_role == "matcher":
        # AI is the MATCHER (other player is Director)
        system_content = (
            "You are the MATCHER in a basket referential game. "
            "Your role is to identify which baskets the DIRECTOR is describing and to communicate how confident you are.\n\n"
            "CORE RESPONSIBILITIES:\n"
            "1. Pay attention carefully to the DIRECTOR's descriptions of the baskets in order.\n"
            "2. Always reason about and talk about the LOWEST‑NUMBERED empty position in the 12‑position sequence. "
            "Do not skip ahead to later positions while an earlier position is still empty or uncertain.\n"
            "3. Ask clarification questions when the description could match multiple baskets.\n"
            "4. Explain what features you are using to narrow down the possibilities.\n"
            "5. Indicate when you think you have identified the right basket and are ready to move on."
        )
    else:
        # AI is the DIRECTOR (other player is Matcher)
        system_content = (
            "You are the DIRECTOR in a basket referential game. "
            "Your role is to help your MATCHER partner reconstruct a 12‑basket sequence through clear, distinctive descriptions.\n\n"
            "Describe ONE BASKET PER MESSAGE. Never describe multiple baskets in a single message. "
            "Wait for your partner to respond before moving to the next basket.\n\n"
            "CORE RESPONSIBILITIES:\n"
            "1. Describe baskets in strict order from basket 1 to basket 12. "
            "Start with basket 1 (top‑left), then move left‑to‑right across the top row (baskets 1–6), "
            "then left‑to‑right across the bottom row (baskets 7–12).\n"
            "2. Each message should describe ONLY ONE basket. Do not list or describe multiple baskets at once.\n"
            "3. Wait for your MATCHER to confirm they found the basket before moving to the next one.\n"
            "4. You may revisit an earlier basket only if your MATCHER explicitly asks for clarification.\n"
            "5. Describe unique, visually distinctive features: shape, color, texture, handles, special features.\n"
            "6. Answer clarification questions about the current basket.\n"
            "7. Keep responses focused and concise - describe one basket, then wait."
        )

    system_message: Dict[str, Any] = {
        "role": "system",
        "content": system_content,
    }

    history_messages = _build_ai_messages_from_history(player, all_history)
    # Ensure the latest human message is present at the end
    if latest_message:
        history_messages.append({"role": "user", "content": latest_message})

    return [system_message] + history_messages


