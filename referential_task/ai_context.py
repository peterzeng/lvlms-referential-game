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
    from .ai_image_utils import _image_rel_to_data_url

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
    from .ai_image_utils import _image_rel_to_data_url

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

    # Standardize the combined pool order (base + extras) for consistency.
    # Sort by image path to ensure deterministic ordering.
    combined = base + extras
    combined.sort(key=lambda x: (x.get("slot") or {}).get("image", ""))
    return combined


# ---------------------------------------------------------------------------
# Visual Grid Context Injection
# ---------------------------------------------------------------------------


def _visual_context_already_sent_this_round(player: "Player") -> bool:
    """Check if visual context has already been sent for the current round.
    
    Uses the group-level tracking field to avoid re-sending large images.
    """
    current_round = getattr(player, "round_number", 1) or 1
    sent_round = getattr(player.group, "ai_visual_context_sent_round", 0) or 0
    return sent_round == current_round


def _mark_visual_context_sent(player: "Player"):
    """Mark that visual context has been sent for the current round."""
    current_round = getattr(player, "round_number", 1) or 1
    player.group.ai_visual_context_sent_round = current_round


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
    import logging

    from .ai_image_utils import (
        _build_ai_director_grid_composite,
        _build_candidate_pool_image,
    )

    if not messages:
        return messages

    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"
    if ai_role not in ("director", "matcher"):
        return messages

    current_round = getattr(player, "round_number", 1) or 1
    already_sent = _visual_context_already_sent_this_round(player)
    
    # Try to use cached image URL first (avoids expensive regeneration)
    cached_url = getattr(player.group, "ai_visual_context_cached_url", "") or ""
    image_url = None
    
    if already_sent and cached_url:
        # Use cached image on subsequent turns
        image_url = cached_url
        logging.info(
            "[VISUAL_CONTEXT] Using cached image for %s round %d, URL length: %d bytes",
            ai_role, current_round, len(image_url)
        )
    else:
        # Generate new image on first turn
        if ai_role == "director":
            image_url = _build_ai_director_grid_composite(player)
        else:
            image_url = _build_candidate_pool_image(
                player,
                load_matcher_pool_func=_load_matcher_pool_image_urls,
            )
        
        if not image_url:
            logging.warning("[VISUAL_CONTEXT] No image generated for %s", ai_role)
            return messages
        
        # Cache the image URL for subsequent turns
        try:
            player.group.ai_visual_context_cached_url = image_url
        except Exception:
            pass  # Don't fail if caching fails
        
        # Mark that we've generated visual context for this round
        _mark_visual_context_sent(player)
        
        logging.info(
            "[VISUAL_CONTEXT] Generated and cached image for %s round %d, URL length: %d bytes",
            ai_role, current_round, len(image_url)
        )

    # Build intro text based on role and prompt style
    from .prompt import get_prompt_style
    style = get_prompt_style(player)
    
    if ai_role == "director":
        intro_text = (
            f"ROUND {current_round} TARGET GRID: This image shows the 12 baskets you must describe.\n\n"
            "The grid shows 2 rows × 6 columns with Baskets 1–6 on the top row and Baskets 7–12 on the bottom row. "
            "IMPORTANT: Describe ONE BASKET PER MESSAGE, in order (1, 2, 3, ..., 12). "
            "Wait for your partner to confirm before moving to the next basket. "
            "Your MATCHER partner sees these 12 baskets mixed with 6 additional distractors in their candidate pool."
        )
    elif style == "natural":
        # Natural style - simpler intro without action tag references
        intro_text = (
            f"ROUND {current_round} CANDIDATE POOL: This image shows the 18 candidates you can choose from.\n\n"
            "The pool contains 12 TRUE TARGETS (which the DIRECTOR will describe) mixed with 6 DISTRACTORS. "
            "Each candidate is numbered 1-18.\n\n"
            "When you identify a basket, respond naturally and state which candidate number (1-18) you're "
            "placing in which position (1-12). For example: 'Got it! I'll place candidate 7 in position 3.'"
        )
    else:
        # Tagged styles - include action tag instructions
        intro_text = (
            f"ROUND {current_round} CANDIDATE POOL: This image shows the 18 candidates you can choose from.\n\n"
            "The pool contains 12 TRUE TARGETS (which the DIRECTOR will describe) mixed with 6 DISTRACTORS. "
            "Each candidate is numbered 1-18. Use these numbers in your action tags (e.g., [PLACE:7,3]).\n\n"
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

    grid_message = {
        "role": "user",
        "content": multimodal_content,
    }

    # Insert after any leading system messages so they still anchor behavior,
    # but before conversation history and the latest human turn.
    idx = 0
    while idx < len(messages) and messages[idx].get("role") == "system":
        idx += 1

    return messages[:idx] + [grid_message] + messages[idx:]

