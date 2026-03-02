from __future__ import annotations

"""
V3 / CoT prompting strategy for the basket referential task.

This module reuses the Weiling-style system prompt from `prompt_v2` but
adds explicit JSON / chain-of-thought instructions. It is imported lazily
from `pages.py` so that the long prompt text is factored out.
"""

from typing import Any, Dict, List

from .pages import (  # type: ignore
    _build_ai_messages_from_history,
    _get_max_history_turns,
)
from .prompt_v2 import _build_weiling_style_system_prompt


def build_v3_cot_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    V3: Explicit chain-of-thought prompting for the basket referential task.

    The model receives:
    - A detailed role/game-state system prompt (same as V2/Weiling)
    - Recent conversation history
    - A V3-specific system instruction to respond in JSON with:
        {
          "reasoning": { ... step-by-step discriminative analysis ... },
          "utterance": "single natural-language message to show the human",
          "selection": { ... basket choice metadata ... }
        }
    We will log/use the full JSON server-side but only show `utterance` to the user.
    """
    base_system = _build_weiling_style_system_prompt(player)

    # Determine the AI role so that JSON instructions can be role-specific.
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    if ai_role == "matcher":
        v3_instructions = (
            "You must respond with a SINGLE STRICT JSON object and EXACTLY these top-level fields (no extras):\n"
            '- "reasoning"\n'
            '- "utterance"\n'
            '- "selection"\n'
            "{\n"
            '  "reasoning": {\n'
            '    "target_position": <integer 1-12 for which position in the 12-slot sequence you are currently trying to fill (usually the lowest-numbered empty position unless the DIRECTOR explicitly revisits a specific basket number)>,\n'
            '    "shared_features": ["features many baskets share"],\n'
            '    "distinctive_features": ["features that uniquely or strongly identify the basket from the description"],\n'
            '    "best_guess_candidate_index": <integer 1-18 for your current best guess, or null if you truly have no best guess yet>,\n'
            '    "likely_confusions": <array of integers 1-18 for OTHER plausible candidates you might confuse with your best guess; MUST NOT include `best_guess_candidate_index` (and MUST NOT include `selection.candidate_index` if you set one)>,\n'
            '    "discriminative_question": "a short question to either (a) disambiguate your best guess vs `likely_confusions`, or (b) if `likely_confusions` is empty, to confirm a key distinctive feature of your best guess"\n'
            "  },\n"
            '  "utterance": "a single concise, natural-language message you will SAY to the DIRECTOR in the chat. If unsure between candidates, ask about discriminating features (e.g., ask about handle shape, flower color, or pattern details that would distinguish the confusable options). Do NOT reveal you are an AI.",\n'
            '  "selection": {\n'
            '    "candidate_index": <integer 1–18 from the numbered candidate tiles, or null if asking for clarification>,\n'
            '    "position": <integer 1–12 for which position this basket goes in, or null for next available>,\n'
            '    "ready_to_submit": <true only when submitting final 12-basket order, otherwise false>\n'
            "  }\n"
            "}\n\n"
            "Rules:\n"
            "- Set `reasoning.target_position` to the position you are trying to fill (default: lowest-numbered empty position unless the DIRECTOR explicitly revisits a specific basket number).\n"
            "- If you are asking for clarification (not committing yet), set `selection.candidate_index` to null and do NOT advance `reasoning.target_position`.\n"
            "- If you DO commit, set `selection.position` to `reasoning.target_position`.\n"
            "- Always maintain a single `best_guess_candidate_index` when possible; if you set `selection.candidate_index`, set `best_guess_candidate_index` to the same value.\n"
            "- Put ONLY the competing alternatives in `likely_confusions` (do not include the best guess).\n"
            "- If you are NOT committing yet (`selection.candidate_index` is null), you can still set `best_guess_candidate_index` and ask a discriminative question to confirm it.\n"
            "- It is OK for `likely_confusions` to be empty if you see only one plausible match; in that case, use `discriminative_question` as a confirmation question about a key distinctive feature.\n"
            "- If you set `selection.candidate_index`, your `utterance` should (1) state that you placed/are placing the basket in position `reasoning.target_position`, and (2) ask the discriminative/confirmation question if needed; otherwise ask the DIRECTOR to describe the next basket.\n"
            "- Write all of your step-by-step thinking only inside `reasoning`. The DIRECTOR will only see `utterance`, not your reasoning.\n"
            "- Never mention candidate indices, IDs, or filenames in your utterance.\n"
            "- Do NOT include any extra text before or after the JSON object."
        )
    else:
        # Director: still use the same JSON envelope, but never choose a basket directly.
        v3_instructions = (
            "You must respond with a SINGLE STRICT JSON object and EXACTLY these top-level fields (no extras):\n"
            '- "reasoning"\n'
            '- "utterance"\n'
            "{\n"
            '  "reasoning": {\n'
            '    "target_position": <integer 1-12 for which basket position you are describing>,\n'
            '    "shared_features": ["features this basket shares with others in the grid"],\n'
            '    "distinctive_features": ["features that uniquely identify THIS basket from similar ones"],\n'
            '    "likely_confusions": <array of integers 1-12 for OTHER positions in YOUR grid that the MATCHER might confuse with the target; MUST NOT include target_position>,\n'
            '    "discriminative_strategy":   "which specific features you will emphasize to distinguish the target from the likely confusions"\n'
            "  },\n"
            '  "utterance": "a single concise, natural-language message you will SAY to the MATCHER in the chat. Focus on features that discriminate the target basket from similar-looking ones. Do NOT reveal you are an AI."\n'
            "}\n\n"
            "Rules:\n"
            "- Before describing, identify which other baskets (by position 1-12) look similar to your target.\n"
            "- List those similar position indices in `likely_confusions` and plan which features discriminate your target from them.\n"
            "- Your `utterance` should emphasize discriminating features (e.g., unique handle shape, specific flower colors, distinct patterns).\n"
            "- Write all of your step-by-step thinking only inside `reasoning`. The MATCHER will only see `utterance`, not your reasoning.\n"
            "- Do NOT include any extra text before or after the JSON object."
        )

    system_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": base_system},
        {"role": "system", "content": v3_instructions},
    ]

    # Map stored history into user/assistant turns
    history_messages = _build_ai_messages_from_history(player, all_history)
    max_history = _get_max_history_turns(player)
    if len(history_messages) > max_history:
        history_messages = history_messages[-max_history:]

    chat_messages: List[Dict[str, Any]] = system_messages + history_messages
    # NOTE: latest_message is already included in all_history (appended to
    # grid_messages before _generate_ai_reply is called), so we do NOT
    # append it again here to avoid duplicate messages in the API call.

    return chat_messages


