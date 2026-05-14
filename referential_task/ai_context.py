"""
Visual context injection for AI prompts in the basket referential task.

This module handles:
- Loading basket image URLs for director and matcher pools
- Injecting visual grid context into AI prompts (image on first turn, reminder otherwise)

The main prompt text is in prompt.py. This module handles the visual/image aspects.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import Player


# ---------------------------------------------------------------------------
# Image URL Loading
# ---------------------------------------------------------------------------


def _load_shared_grid_image_urls(player: "Player") -> list[dict[str, Any]]:
    """Return a list of {'slot': slot_dict, 'data_url': 'data:image/...'} for the shared grid.

    If images cannot be resolved, returns an empty list and callers should gracefully
    fall back to text-only prompting.
    """
    from .ai_utils import _image_rel_to_data_url

    if not hasattr(player, "group"):
        return []
    try:
        shared_grid = json.loads(getattr(player.group, "shared_grid", "") or "[]")
    except Exception:
        shared_grid = []

    results: list[dict[str, Any]] = []
    for slot in shared_grid or []:
        img_path = (slot.get("image") or "").lstrip("/ ")
        if not img_path:
            continue
        data_url = _image_rel_to_data_url(img_path)
        if not data_url:
            continue
        results.append({"slot": slot, "data_url": data_url})
    return results


def _load_matcher_pool_image_urls(player: "Player") -> list[dict[str, Any]]:
    """Return image URLs for the matcher's full choice pool (targets + distractors).

    For the MATCHER role we want to approximate the staging area the human
    matcher sees: the 12 target baskets from the director's grid plus the
    additional distractor baskets drawn from the preset `fullList` for the
    configured basket set.
    """
    from .ai_utils import _image_rel_to_data_url

    # Start with the 12 target baskets from the shared grid
    base = _load_shared_grid_image_urls(player)
    if not base:
        return base

    # Build a set of already-included relative image paths
    seen_paths: set[str] = set()
    for item in base:
        slot = item.get("slot") or {}
        img_path = (slot.get("image") or "").lstrip("/ ")
        if img_path:
            seen_paths.add(img_path)

    # Load preset fullList for this basket_set, mirroring DraggableGridPage.vars_for_template
    try:
        if hasattr(player, "session") and player.session:
            try:
                set_num = int(player.session.config.get("basket_set", 1))
            except Exception:
                set_num = 1
        else:
            set_num = 1
        if set_num == 2:
            preset_filename = "grids_presets2.json"
        elif set_num == 3:
            preset_filename = "grids_presets3.json"
        elif set_num == 4:
            preset_filename = "grids_presets4.json"
        elif set_num == 5:
            preset_filename = "grids_presets5.json"
        else:
            preset_filename = "grids_presets1.json"
        preset_path = os.path.join(os.path.dirname(__file__), preset_filename)
        with open(preset_path, "r", encoding="utf-8") as f:
            presets = json.load(f)
        preset_full_list: list[str] = []
        for item in presets.get("rounds", []):
            if isinstance(item, dict) and "fullList" in item:
                preset_full_list = [
                    f"images/{img}" for img in item.get("fullList", []) or []
                ]
                break
    except Exception:
        preset_full_list = []

    # Add a small number of extras from preset_full_list that aren't already in
    # the 12-basket grid.
    extras: list[dict[str, Any]] = []
    MAX_EXTRAS = 6
    for rel_path in preset_full_list or []:
        if len(extras) >= MAX_EXTRAS:
            break
        rel_path = rel_path.lstrip("/ ")
        if rel_path in seen_paths:
            continue
        data_url = _image_rel_to_data_url(rel_path)
        if not data_url:
            continue
        extras.append(
            {
                "slot": {"image": rel_path, "basket_id": None},
                "data_url": data_url,
            }
        )

    # Use the same deterministic shuffle as the prompt-side pool builder so
    # candidate_index maps back to the exact image the matcher saw.
    combined = base + extras
    try:
        import random

        round_num = int(getattr(player, "round_number", 1) or 1)
        seed = 4242 + (set_num * 100) + round_num
        rng = random.Random(seed)
        rng.shuffle(combined)
    except Exception:
        pass
    return combined


# ---------------------------------------------------------------------------
# Visual Grid Context Injection
# ---------------------------------------------------------------------------


def _get_ai_role(player: "Player") -> str | None:
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"
    if ai_role not in ("director", "matcher"):
        return None
    return ai_role


def _load_visual_context_cache(group: Any) -> dict[str, str]:
    try:
        raw_cache = getattr(group, "ai_visual_context_cached_urls", "") or "{}"
        parsed = json.loads(raw_cache) if isinstance(raw_cache, str) else raw_cache
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if v}
    except Exception:
        pass
    return {}


def _save_visual_context_cache(group: Any, cache: dict[str, str]) -> None:
    try:
        group.ai_visual_context_cached_urls = json.dumps(cache)
    except Exception:
        pass


def _visual_context_cache_key(player: "Player", ai_role: str) -> str:
    current_round = getattr(player, "round_number", 1) or 1
    return f"{ai_role}:round:{current_round}"


def _get_visual_context_image_url(player: "Player", ai_role: str) -> str | None:
    """Return the cached/generated visual context image for this role and round."""
    import logging

    from .ai_utils import (
        _build_ai_director_grid_composite,
        _build_ai_matcher_grid_composite,
    )

    if not hasattr(player, "group"):
        return None

    cache = _load_visual_context_cache(player.group)
    cache_key = _visual_context_cache_key(player, ai_role)
    cached_url = cache.get(cache_key)
    current_round = getattr(player, "round_number", 1) or 1

    if cached_url:
        logging.info(
            "[VISUAL_CONTEXT] Using cached image for %s round %d, URL length: %d bytes",
            ai_role,
            current_round,
            len(cached_url),
        )
        return cached_url

    if ai_role == "director":
        image_url = _build_ai_director_grid_composite(player)
    elif ai_role == "matcher":
        image_url = _build_ai_matcher_grid_composite(player)
    else:
        return None

    if not image_url:
        logging.warning("[VISUAL_CONTEXT] No image generated for %s", ai_role)
        return None

    cache[cache_key] = image_url
    _save_visual_context_cache(player.group, cache)

    logging.info(
        "[VISUAL_CONTEXT] Generated and cached image for %s round %d, URL length: %d bytes",
        ai_role,
        current_round,
        len(image_url),
    )
    return image_url


def _build_visual_context_message(
    player: "Player", ai_role: str, image_url: str
) -> dict[str, Any]:
    current_round = getattr(player, "round_number", 1) or 1

    try:
        style = (
            getattr(player.session, "config", {}).get("prompt_style")
            or getattr(player.session, "config", {}).get("prompt_strategy")
            or ""
        )
    except Exception:
        style = ""

    if ai_role == "director":
        intro_text = (
            f"ROUND {current_round} TARGET GRID: This image shows the 12 baskets you must describe for ROUND {current_round}.\n\n"
            "The grid shows 2 rows × 6 columns with Baskets 1–6 on the top row and Baskets 7–12 on the bottom row. "
            "IMPORTANT: Pair this image only with the Round "
            f"{current_round} conversation below. Describe ONE BASKET PER MESSAGE, in order (1, 2, 3, ..., 12). "
            "Wait for your partner to confirm before moving to the next basket. "
            "Your MATCHER partner sees these 12 baskets mixed with 6 additional distractors in their candidate pool."
        )
    elif style == "natural":
        intro_text = (
            f"ROUND {current_round} CANDIDATE POOL: This image shows the 18 candidates you can choose from for ROUND {current_round}.\n\n"
            "The pool contains 12 TRUE TARGETS (which the DIRECTOR will describe) mixed with 6 DISTRACTORS. "
            "Each candidate is numbered 1-18. Pair this image only with the Round "
            f"{current_round} conversation below.\n\n"
            "When you identify a basket, respond naturally and state which candidate number (1-18) you're "
            "placing in which position (1-12). For example: 'Got it! I'll place candidate 7 in position 3.'"
        )
    else:
        intro_text = (
            f"ROUND {current_round} CANDIDATE POOL: This image shows the 18 candidates you can choose from for ROUND {current_round}.\n\n"
            "The pool contains 12 TRUE TARGETS (which the DIRECTOR will describe) mixed with 6 DISTRACTORS. "
            "Each candidate is numbered 1-18. Pair this image only with the Round "
            f"{current_round} conversation below. Use these numbers in your action tags (e.g., [PLACE:7,3]).\n\n"
            "IMPORTANT: Look at this image to find the candidate that matches each description, then include "
            "the candidate NUMBER in your [PLACE:C,P] tag."
        )

    multimodal_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": intro_text,
        },
        {
            "type": "image_url",
            "image_url": {
                "url": image_url,
            },
        },
    ]

    return {
        "role": "user",
        "content": multimodal_content,
    }


def _round_visual_context_messages(player: "Player", ai_role: str) -> dict[int, dict[str, Any]]:
    """Build visual context blocks for all available rounds for this role."""
    try:
        all_round_players = player.in_all_rounds()
    except Exception:
        all_round_players = [player]

    by_round: dict[int, dict[str, Any]] = {}
    for round_player in all_round_players:
        try:
            round_num = int(getattr(round_player, "round_number", 1) or 1)
        except Exception:
            continue
        image_url = _get_visual_context_image_url(round_player, ai_role)
        if image_url:
            by_round[round_num] = _build_visual_context_message(
                round_player, ai_role, image_url
            )
    return by_round


def _message_starts_round(message: dict[str, Any]) -> int | None:
    content = message.get("content")
    if not isinstance(content, str):
        return None
    marker = content.lstrip()
    if not marker.startswith("═══ ROUND "):
        return None
    try:
        rest = marker.split("ROUND ", 1)[1]
        return int(rest.split(None, 1)[0])
    except Exception:
        return None


def _inject_visual_grid_context(player: "Player", messages: list[dict[str, Any]]):
    """Inject a multimodal grid message so the AI sees the basket layout.

    The image is included on EVERY turn for both roles because:
    - Each OpenAI API call is stateless - the model can't "remember" previous calls
    - The conversation history only contains text messages, not the original image
    - Without the image, the AI can't map descriptions to candidate numbers (matcher)
      or know which basket to describe next (director)

    We cache the generated image URL to avoid expensive regeneration on each turn.

    - Director: 2×6 grid of the 12 target baskets
    - Matcher: 3×6 grid of the 18 candidate baskets
    """
    if not messages:
        return messages

    ai_role = _get_ai_role(player)
    if ai_role is None:
        return messages

    current_round = getattr(player, "round_number", 1) or 1

    try:
        use_cross_round_history = bool(
            getattr(player.session, "config", {}).get("cross_round_history", False)
        )
    except Exception:
        use_cross_round_history = False

    # Insert after any leading instruction messages so they still anchor behavior,
    # but before conversation history and the latest human turn.
    idx = 0
    while idx < len(messages) and messages[idx].get("role") in ("developer", "system"):
        idx += 1

    if use_cross_round_history:
        round_contexts = _round_visual_context_messages(player, ai_role)
        if not round_contexts:
            return messages

        result: list[dict[str, Any]] = messages[:idx]
        inserted_rounds: set[int] = set()
        for message in messages[idx:]:
            marker_round = _message_starts_round(message)
            if marker_round is not None and marker_round in round_contexts:
                result.append(round_contexts[marker_round])
                inserted_rounds.add(marker_round)
            result.append(message)

        # Round 1 often has no boundary marker because it is the first block.
        current_context = round_contexts.get(current_round)
        if current_context and current_round not in inserted_rounds:
            result.insert(idx, current_context)
        return result

    image_url = _get_visual_context_image_url(player, ai_role)
    if not image_url:
        return messages

    grid_message = _build_visual_context_message(player, ai_role, image_url)
    return messages[:idx] + [grid_message] + messages[idx:]
