from __future__ import annotations

"""
V8 Prompt Strategy: Bare Minimum CoT

"Humanlike" prompt adapted from a single-agent implementation.
This version replaces tangrams with baskets and updates grid numbering, 
while enforcing strict JSON formatting (CoT reasoning) but providing minimal other instructions.
It acts as a baseline for single-agent evaluation.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from .ai_utils import (  # type: ignore
    _build_ai_messages_from_history,
    _get_max_history_turns,
)

class Selection(BaseModel):
    model_config = {"extra": "forbid"}
    candidate_index: Optional[int]
    position: Optional[int]
    ready_to_submit: bool

class MatcherResponse(BaseModel):
    model_config = {"extra": "forbid"}
    utterance: Optional[str]
    reasoning: Optional[str]
    selection: Optional[Selection]

class DirectorResponse(BaseModel):
    model_config = {"extra": "forbid"}
    utterance: Optional[str]
    reasoning: Optional[str]


def _build_cameron_base_prompt(player, role: str) -> str:
    """
    Returns the "Humanlike" text prompt tailored for our basket task.
    """
    
    round_num = getattr(player, "round_number", 1)
    
    base = f"""We are currently in Round {round_num}.

## Role

"""
    if role == "director":
        base += """You are the DIRECTOR (Speaker). 

## Instructions

- You will be shown a target basket image.
- Your task is to concisely describe the target so that your partner can identify it.
- Your partner's grid has the same images but in a different arrangement, so don't refer to the image's positions.
- Focus on what makes your target unique from other images in the grid, so your partner doesn't pick another similar one. 
    Consider whether your description could inadvertently refer to one of the other images and distinguish the target from it in your description.
- Adapt your language based on previous rounds and your partner's style.
- Your descriptions should be AS SHORT AS POSSIBLE. Especially in later rounds. Your partner is waiting for your messages which will be sent at a rate of 500ms/char! Don't keep them waiting. Find creative ways to be efficient.
- After a few rounds (when you've seen an image a few times), use only a single word or short phrase.
    Once you've established a convention, just say "the red one", or just "red", rather than giving a more detailed description. Seriously. 1-2 words.
- Don't say or do anything that a human wouldn't. You want your partner to think you are a human.
- Write in a very casual style. You might use lowercase or even some slang or make spelling mistakes.
- The target numbering is 1-12, 1-6 across the top row and 7-12 across the bottom row (left to right).

SERIOUSLY—in later rounds just 1-2 words. Do NOT send longer descriptions unless your partner keeps getting it wrong.
"""
    else:
        base += """You are the MATCHER (Listener). You'll identify a basket based on your partner's description.

## Instructions

- Your partner will provide a description of a basket.
- Your task is to identify which image they are describing.
- You will select the candidate basket and indicate its position.
"""
    return base



def build_cameron_prompt_messages(
    player: Any, latest_message: str | None, all_history: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Cameron Prompt: "Humanlike" single-agent prompt for the basket referential task.

    The model receives:
    - The "Humanlike" prompt adapted for baskets
    - Recent conversation history
    - Instructions for the specific role
    """
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    base_system = _build_cameron_base_prompt(player, ai_role)

    if ai_role == "matcher":
        cameron_instructions = (
            "You are currently playing the role of the MATCHER in this interaction.\n\n"
            "Your `utterance` should be a single concise, natural-language message you will SAY to the DIRECTOR in the chat. "
            "If unsure between candidates, ask about discriminating features (e.g., ask about handle shape, flower color, or pattern details that would distinguish the confusable options). Keep it very casual as instructed.\n\n"
            "Rules for `selection`:\n"
            "- The `candidate_index` should be an integer 1-18 from the numbered candidate tiles, or null if asking for clarification.\n"
            "- The `position` should be an integer 1-12 for which position this basket goes in, or null for next available.\n"
            "- `ready_to_submit` should be true ONLY when submitting final 12-basket order, otherwise false.\n"
            "- If you are asking for clarification (not committing yet), set `candidate_index` to null.\n"
            "- If you DO commit, set `position` to the position you are currently trying to fill (usually the lowest-numbered empty position).\n"
            "- If you set `candidate_index`, your `utterance` should state that you placed/are placing the basket in that position, otherwise ask the DIRECTOR to describe the next basket.\n"
            "- Never mention candidate indices, IDs, or filenames in your utterance."
        )
    else:
        cameron_instructions = (
            "You are currently playing the role of the DIRECTOR in this interaction.\n\n"
            "Your `utterance` should be a single concise, natural-language message you will SAY to the MATCHER in the chat. "
            "Focus on features that discriminate the target basket from similar-looking ones. Keep it very casual as instructed."
        )

    instruction_messages: List[Dict[str, Any]] = [
        {"role": "developer", "content": base_system},
        {"role": "developer", "content": cameron_instructions},
    ]

    history_messages = _build_ai_messages_from_history(player, all_history)
    max_history = _get_max_history_turns(player)
    if len(history_messages) > max_history:
        history_messages = history_messages[-max_history:]

    chat_messages: List[Dict[str, Any]] = instruction_messages + history_messages

    if latest_message:
        chat_messages.append({"role": "user", "content": latest_message})

    return chat_messages
