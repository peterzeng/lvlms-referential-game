"""
AI sequence management for the basket referential task.

This module handles:
- Updating the incremental AI matcher sequence based on basket choices
- Managing the partial sequence state across turns
- Handling place, clear, and move actions

This is used by page_views.py to track the AI matcher's selections.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Player


def _update_ai_partial_sequence(player: "Player", selection: dict[str, Any] | None):
    """
    Update the group's incremental AI matcher sequence based on an action.

    Actions supported:
    - place: Add a candidate basket to a position
    - clear: Remove basket from a position
    - move: Move basket from one position to another
    - submit: No sequence change (handled elsewhere)
    - None: No action, return existing state

    Instead of asking the model for the full 12-basket sequence on every
    turn, we maintain an incremental sequence in `ai_partial_sequence`.
    """
    from .ai_context import _load_matcher_pool_image_urls

    if not isinstance(selection, dict):
        # No selection provided, return existing state
        try:
            return json.loads(
                getattr(player.group, "ai_partial_sequence", "") or "[]"
            )
        except Exception:
            return None

    action = selection.get("action")
    
    # Handle clear action
    if action == "clear":
        return _handle_clear_action(player, selection)
    
    # Handle move action
    if action == "move":
        return _handle_move_action(player, selection)
    
    # Handle place action (or legacy format without explicit action)
    selected_candidate_index = None
    target_position = None
    try:
        if selection.get("candidate_index") is not None:
            selected_candidate_index = int(selection.get("candidate_index"))
    except Exception:
        selected_candidate_index = None
    try:
        if selection.get("position") is not None:
            target_position = int(selection.get("position"))
    except Exception:
        target_position = None

    # If no candidate index, no placement can happen
    if selected_candidate_index is None:
        try:
            return json.loads(
                getattr(player.group, "ai_partial_sequence", "") or "[]"
            )
        except Exception:
            return None

    group = player.group
    try:
        partial = json.loads(getattr(group, "ai_partial_sequence", "") or "[]")
    except Exception:
        partial = []

    # Determine which logical position to update.
    # IMPORTANT: positions that were "cleared" by a move are stored with
    # {"position": k, "image": None}. Those should be considered EMPTY, so they
    # must NOT count as "used" when selecting the next available slot.
    used_positions: set[int] = set()
    for item in partial:
        if not isinstance(item, dict):
            continue
        pos_raw = item.get("position")
        img = item.get("image")
        # Only treat a position as used if it currently has a non-empty image.
        if not img:
            continue
        try:
            pos_int = int(pos_raw)
        except Exception:
            continue
        if 1 <= pos_int <= 12:
            used_positions.add(pos_int)
    if isinstance(target_position, int) and 1 <= target_position <= 12:
        pos = target_position
    else:
        # Legacy behaviour: append to the next unused slot.
        pos = 1
        while pos in used_positions and pos <= 12:
            pos += 1
    if pos < 1 or pos > 12:
        # Already have 12 positions filled; nothing to update.
        return partial

    # Map the selected candidate index onto a slot in the matcher's pool.
    try:
        pool_items = _load_matcher_pool_image_urls(player)
    except Exception:
        pool_items = []
    try:
        idx_zero_based = int(selected_candidate_index) - 1
    except Exception:
        idx_zero_based = -1
    candidate_slot = None
    if 0 <= idx_zero_based < len(pool_items):
        candidate_slot = (pool_items[idx_zero_based] or {}).get("slot") or None
    if not candidate_slot:
        # If we cannot map this candidate index back to a known slot, bail out.
        return partial

    selected_image = candidate_slot.get("image")
    selected_original_position = candidate_slot.get("position")

    # If this physical basket is already present anywhere in the partial
    # sequence, treat the new selection as a move.
    previous_pos = None
    for item in partial:
        if not isinstance(item, dict):
            continue
        try:
            item_pos = int(item.get("position"))
        except Exception:
            item_pos = None
        same_image = selected_image is not None and item.get("image") == selected_image
        same_orig = (
            selected_original_position is not None
            and item.get("originalPosition") == selected_original_position
        )
        if same_image or same_orig:
            previous_pos = item_pos
            break

    # Remove any previous entry for this logical position or previous_pos.
    # NOTE: Stored JSON may contain positions as strings, ints, or floats.
    # Always compare using int-normalized positions to avoid duplicates like:
    #   {"position": "3", "image": None} and {"position": 3, "image": "..."}.
    cleaned: list[dict[str, Any]] = []
    for item in partial:
        if not isinstance(item, dict):
            continue
        try:
            item_pos_int = int(item.get("position"))
        except Exception:
            # Keep malformed entries out of the debug state.
            continue
        if item_pos_int == pos or (previous_pos is not None and item_pos_int == previous_pos):
            continue
        cleaned.append(item)
    partial = cleaned
    # If the basket was moved from another position, mark that position as empty
    if previous_pos is not None:
        partial.append(
            {
                "position": previous_pos,
                "image": None,
                "originalPosition": None,
            }
        )
    partial.append(
        {
            "position": pos,
            "image": candidate_slot.get("image"),
            "originalPosition": candidate_slot.get("position"),
        }
    )
    # Final pass: de-duplicate by logical position (last write wins).
    # This prevents rendering/logic issues if earlier state included duplicates.
    partial_sorted = _dedupe_and_sort(partial)
    try:
        group.ai_partial_sequence = json.dumps(partial_sorted)
    except Exception:
        # Do not let debug state break the main flow.
        pass
    return partial_sorted


def _dedupe_and_sort(partial: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """De-duplicate by logical position (last write wins) and sort."""
    by_pos: dict[int, dict[str, Any]] = {}
    for item in partial:
        if not isinstance(item, dict):
            continue
        try:
            p_int = int(item.get("position"))
        except Exception:
            continue
        if 1 <= p_int <= 12:
            by_pos[p_int] = item
    return [by_pos[p] for p in sorted(by_pos.keys())]


def _handle_clear_action(player: "Player", selection: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Handle the clear action: remove basket from a position."""
    group = player.group
    try:
        partial = json.loads(getattr(group, "ai_partial_sequence", "") or "[]")
    except Exception:
        partial = []

    try:
        clear_pos = int(selection.get("position"))
    except Exception:
        logging.warning("[AI_SEQ] Clear action missing valid position")
        return partial

    if not (1 <= clear_pos <= 12):
        logging.warning("[AI_SEQ] Clear position out of range: %s", clear_pos)
        return partial

    # Mark the position as cleared (empty)
    # Remove any existing entry for this position
    cleaned = [item for item in partial 
               if isinstance(item, dict) and _get_pos(item) != clear_pos]
    
    # Add an empty placeholder
    cleaned.append({
        "position": clear_pos,
        "image": None,
        "originalPosition": None,
    })

    partial_sorted = _dedupe_and_sort(cleaned)
    try:
        group.ai_partial_sequence = json.dumps(partial_sorted)
    except Exception:
        pass
    
    logging.info("[AI_SEQ] Cleared position %d", clear_pos)
    return partial_sorted


def _handle_move_action(player: "Player", selection: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Handle the move action: relocate basket from one position to another."""
    group = player.group
    try:
        partial = json.loads(getattr(group, "ai_partial_sequence", "") or "[]")
    except Exception:
        partial = []

    try:
        from_pos = int(selection.get("from_position"))
        to_pos = int(selection.get("to_position"))
    except Exception:
        logging.warning("[AI_SEQ] Move action missing valid positions")
        return partial

    if not (1 <= from_pos <= 12 and 1 <= to_pos <= 12):
        logging.warning("[AI_SEQ] Move positions out of range: %s > %s", from_pos, to_pos)
        return partial

    # Find the item at from_pos
    source_item = None
    for item in partial:
        if isinstance(item, dict) and _get_pos(item) == from_pos:
            source_item = item
            break

    if source_item is None or not source_item.get("image"):
        logging.warning("[AI_SEQ] No basket at position %d to move", from_pos)
        return partial

    # Remove both from_pos and to_pos entries
    cleaned = [item for item in partial 
               if isinstance(item, dict) and _get_pos(item) not in (from_pos, to_pos)]
    
    # Add empty placeholder at from_pos
    cleaned.append({
        "position": from_pos,
        "image": None,
        "originalPosition": None,
    })
    
    # Add the moved basket at to_pos
    cleaned.append({
        "position": to_pos,
        "image": source_item.get("image"),
        "originalPosition": source_item.get("originalPosition"),
    })

    partial_sorted = _dedupe_and_sort(cleaned)
    try:
        group.ai_partial_sequence = json.dumps(partial_sorted)
    except Exception:
        pass
    
    logging.info("[AI_SEQ] Moved basket from position %d to %d", from_pos, to_pos)
    return partial_sorted


def _get_pos(item: dict[str, Any]) -> int | None:
    """Extract position as int from a sequence item."""
    try:
        return int(item.get("position"))
    except Exception:
        return None


def _validate_submit_readiness(player: "Player") -> dict[str, Any]:
    """Check if the AI matcher's sequence is ready for submission.
    
    Returns:
        {
            "ready": bool,  # True if all 12 positions are filled
            "filled_count": int,  # Number of filled positions
            "empty_positions": list[int],  # List of empty position numbers
            "message": str | None,  # Error message if not ready
        }
    """
    group = player.group
    try:
        partial = json.loads(getattr(group, "ai_partial_sequence", "") or "[]")
    except Exception:
        partial = []
    
    # Check which positions are filled (have non-null images)
    filled_positions: set[int] = set()
    for item in partial:
        if not isinstance(item, dict):
            continue
        pos = _get_pos(item)
        if pos is not None and 1 <= pos <= 12:
            img = item.get("image")
            if img:  # Only count as filled if image is non-null/non-empty
                filled_positions.add(pos)
    
    empty_positions = [p for p in range(1, 13) if p not in filled_positions]
    filled_count = len(filled_positions)
    
    if filled_count == 12:
        return {
            "ready": True,
            "filled_count": 12,
            "empty_positions": [],
            "message": None,
        }
    else:
        return {
            "ready": False,
            "filled_count": filled_count,
            "empty_positions": empty_positions,
            "message": (
                f"Cannot submit yet! Only {filled_count}/12 positions filled. "
                f"Empty positions: {empty_positions}. "
                f"Please ask for descriptions of the empty positions."
            ),
        }
