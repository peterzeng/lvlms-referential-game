from __future__ import annotations

"""
V8 prompting strategy for the basket referential task.

"Humanlike" prompt adapted from a single-agent implementation.
This version replaces tangrams with baskets and updates grid numbering, 
while enforcing strict JSON formatting so it plugs directly into our backend.
"""

from typing import Any, Dict, List

from .ai_utils import (  # type: ignore
    _build_ai_messages_from_history,
    _get_max_history_turns,
)


def _build_v9_base_prompt(player) -> str:
    """
    Returns the "Humanlike" text prompt tailored for our basket task.
    """
    
    round_num = getattr(player, "round_number", 1)
    
    return f"""This experiment explores communication about visual objects called baskets. You'll participate in multiple rounds of a communication game. Each round will be with the same partner. Your goal is to communicate effectively and efficiently about the basket images. We are currently in Round {round_num}.

## Alternating Roles

In this experiment, you'll alternate between DIRECTOR (Speaker) and MATCHER (Listener) roles.

- **DIRECTOR Role:** You'll describe a target basket for your partner to identify.
- **MATCHER Role:** You'll identify a basket based on your partner's description.

## Instructions

### When you are the DIRECTOR:
1. You will be shown a target basket image.
2. Your task is to concisely describe the target so that your partner can identify it.
3. Your partner's grid has the same images but in a different arrangement, so don't refer to the image's positions.
4. Focus on what makes your target unique from other images in the grid, so your partner doesn't pick another similar one. Consider whether your description could inadvertently refer to one of the other images and distinguish the target from it in your description.
5. Use analogies rather than geometric descriptions.
6. Adapt your language based on previous rounds and your partner's style.
7. Your descriptions should be AS SHORT AS POSSIBLE. Especially in later rounds. Your partner is waiting for your messages which will be sent at a rate of 500ms/char! Don't keep them waiting. Find creative ways to be efficient.
8. After a few rounds (when you've seen an image a few times), use only a single word or short phrase. Once you've established a convention, just say "the red one", or just "red", rather than giving a more detailed description. Seriously. 1-2 words.
9. Don't say or do anything that a human wouldn't. You want your partner to think you are a human.
10. Write in a very casual style. You might use lowercase or even some slang or make spelling mistakes.
11. The target numbering is 1-12, 1-6 across the top row and 7-12 across the bottom row (left to right).

In later rounds just 1-2 words. Do NOT send longer descriptions unless your partner keeps getting it wrong.

### When you are the MATCHER:
1. Your partner will provide a description of a basket.
2. Your task is to identify which image they are describing.
3. You will respond using the required JSON format below to indicate your choice.
"""


def build_v9_cot_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    V8: "Humanlike" single-agent prompt for the basket referential task.

    The model receives:
    - The "Humanlike" prompt adapted for baskets
    - Recent conversation history
    - V3-style system instruction to respond in JSON
    """
    base_system = _build_v9_base_prompt(player)

    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    if ai_role == "matcher":
        v9_instructions = (
            "You are currently playing the role of the MATCHER in this interaction.\n\n"
            "You must respond with a SINGLE STRICT JSON object and EXACTLY these top-level fields (no extras):\n"
            '- "utterance"\n'
            '- "selection"\n'
            "{\n"
            '  "utterance": "a single concise, natural-language message you will SAY to the DIRECTOR in the chat. If unsure between candidates, ask about discriminating features (e.g., ask about handle shape, flower color, or pattern details that would distinguish the confusable options). Keep it very casual as instructed.",\n'
            '  "selection": {\n'
            '    "candidate_index": <integer 1–18 from the numbered candidate tiles, or null if asking for clarification>,\n'
            '    "position": <integer 1–12 for which position this basket goes in, or null for next available>,\n'
            '    "ready_to_submit": <true only when submitting final 12-basket order, otherwise false>\n'
            "  }\n"
            "}\n\n"
            "Rules:\n"
            "- If you are asking for clarification (not committing yet), set `selection.candidate_index` to null.\n"
            "- If you DO commit, set `selection.position` to the position you are currently trying to fill (usually the lowest-numbered empty position).\n"
            "- If you set `selection.candidate_index`, your `utterance` should state that you placed/are placing the basket in that position, otherwise ask the DIRECTOR to describe the next basket.\n"
            "- Never mention candidate indices, IDs, or filenames in your utterance.\n"
            "- Do NOT include any extra text before or after the JSON object."
        )
    else:
        v9_instructions = (
            "You are currently playing the role of the DIRECTOR in this interaction.\n\n"
            "You must respond with a SINGLE STRICT JSON object and EXACTLY these top-level fields (no extras):\n"
            '- "utterance"\n'
            "{\n"
            '  "utterance": "a single concise, natural-language message you will SAY to the MATCHER in the chat. Focus on features that discriminate the target basket from similar-looking ones. Keep it very casual as instructed."\n'
            "}\n\n"
            "Rules:\n"
            "- Your `utterance` should emphasize discriminating features (e.g., unique handle shape, specific flower colors, distinct patterns).\n"
            "- Do NOT include any extra text before or after the JSON object."
        )

    system_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": base_system},
        {"role": "system", "content": v9_instructions},
    ]

    history_messages = _build_ai_messages_from_history(player, all_history)
    max_history = _get_max_history_turns(player)
    if len(history_messages) > max_history:
        history_messages = history_messages[-max_history:]

    chat_messages: List[Dict[str, Any]] = system_messages + history_messages

    if latest_message:
        chat_messages.append({"role": "user", "content": latest_message})

    return chat_messages
