from __future__ import annotations

import base64
import datetime
import hashlib
import io
import json
import os
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .models import Constants, Player

# Re-exported names (including "private" helpers) so that `referential_task.pages`
# can import `*` from this module and still expose the underscore-prefixed
# helpers expected by the prompt strategy modules (prompt_v1 / v2 / v3).
__all__ = [
    "_resolve_static_image_path",
    "_image_rel_to_data_url",
    "_build_ai_director_grid_composite",
    "_debug_save_ai_director_grid_image",
    "_build_ai_matcher_grid_composite",
    "_debug_save_ai_matcher_grid_image",
    "_load_shared_grid_image_urls",
    "_load_matcher_pool_image_urls",
    "_inject_task_background",
    "_inject_visual_grid_context",
    "_should_log_v3_reasoning",
    "_get_ai_client",
    "_build_ai_messages_from_history",
    "_get_max_history_turns",
    "_get_prompt_strategy_name",
    "_generate_ai_reply",
    "_update_ai_partial_sequence",
    "_is_reasoning_model",
    "_get_ai_model",
    "_get_ai_reasoning_effort",
    "_build_model_params",
    "TASK_BACKGROUND",
    "REASONING_MODELS",
    "DEFAULT_MODEL",
    "DEFAULT_REASONING_EFFORT",
]


from openai import OpenAI

# Static image cache for VLM context images
_STATIC_IMAGE_CACHE: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Shared task background (mirrors what human participants see at game start)
# ---------------------------------------------------------------------------
TASK_BACKGROUND = """
TASK BACKGROUND (shared with both partners):
You are on a team with a partner. Your goal is to work together to match the correct order of a set of baskets. The game consists of 4 rounds, and in each round, your team must correctly order 12 baskets.

There are two distinct roles: the Director and the Matcher. Both partners see the same 12 target baskets, but the Matcher sees additional distractor baskets mixed in.

Director: Sees the correct target sequence for the 12 baskets and describes each basket one by one (in order starting with the upper-left basket) to the Matcher via live chat.

Matcher: Sees these 12 target baskets plus some additional baskets. As the Director describes each basket, the Matcher interprets the description, asks clarifying questions if needed, and selects the correct target basket.

You can communicate back and forth as much as needed. If you discover an error, it is fine to make corrections within a round. When the round is finished, the Matcher submits the sequence, and both players see the score.
""".strip()


def _inject_task_background(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepend the shared task background as the first system message.

    This ensures the AI has the same high-level context that human participants
    receive at the start of the game, regardless of which prompt strategy is used.
    """
    if not messages:
        return messages

    background_message = {
        "role": "system",
        "content": TASK_BACKGROUND,
    }
    return [background_message] + messages


def _resolve_static_image_path(rel_path: str) -> str | None:
    """Resolve a static image path like 'images/025.png' to a filesystem path.

    We support a few layouts:
    - <project_root>/_static/<rel_path>
    - <project_root>/main/Human-VLM-Game/_static/<rel_path> (Heroku-style bundle)
    - An explicit STATIC_IMAGE_ROOT env override.
    """
    if not rel_path:
        return None

    rel_path = rel_path.lstrip("/ ")

    # Highest priority: explicit override
    explicit_root = os.environ.get("STATIC_IMAGE_ROOT", "").strip()
    candidates: list[str] = []
    if explicit_root:
        candidates.append(os.path.join(explicit_root, rel_path))

    # Project-root-based fallbacks
    app_dir = os.path.dirname(__file__)
    project_root = os.path.dirname(app_dir)
    candidates.append(os.path.join(project_root, "_static", rel_path))
    candidates.append(
        os.path.join(project_root, "main", "Human-VLM-Game", "_static", rel_path)
    )

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _image_rel_to_data_url(rel_path: str) -> str | None:
    """Convert a static image path (e.g., 'images/025.png') to a data URL for GPT‑4o."""
    if not rel_path:
        return None

    # Simple in-memory cache to avoid re-reading the same files
    cache_key = rel_path.lstrip("/ ")
    cached = _STATIC_IMAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    fs_path = _resolve_static_image_path(cache_key)
    if not fs_path:
        return None

    try:
        with open(fs_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"
        _STATIC_IMAGE_CACHE[cache_key] = data_url
        return data_url
    except Exception:
        return None


def _load_font(size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font with fallback to default.

    Tries common system font paths for a clean sans-serif font.
    """
    font_candidates = [
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    # Fallback to default
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _get_text_dimensions(
    draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont
) -> tuple[int, int]:
    """Get text dimensions using modern Pillow API with fallback."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for older Pillow versions
        try:
            return draw.textsize(text, font=font)
        except Exception:
            return (len(text) * 8, 14)


def _draw_label_badge(
    draw: ImageDraw.Draw,
    img_canvas: Image.Image,
    text: str,
    center_x: int,
    center_y: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    bg_color: tuple[int, int, int],
    text_color: tuple[int, int, int],
    padding: int = 6,
    min_width: int = 28,
) -> None:
    """Draw a text label with a rounded rectangle background badge."""
    tw, th = _get_text_dimensions(draw, text, font)
    badge_w = max(tw + padding * 2, min_width)
    badge_h = th + padding * 2

    x0 = center_x - badge_w // 2
    y0 = center_y - badge_h // 2
    x1 = x0 + badge_w
    y1 = y0 + badge_h

    # Draw rounded rectangle background
    radius = min(8, badge_h // 2)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=bg_color)

    # Draw text centered in badge
    tx = x0 + (badge_w - tw) // 2
    ty = y0 + (badge_h - th) // 2
    draw.text((tx, ty), text, font=font, fill=text_color)


def _draw_dashed_rect(
    draw: ImageDraw.Draw,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    dash_length: int = 10,
    gap_length: int = 6,
    width: int = 2,
) -> None:
    """Draw a dashed rectangle border."""
    # Top edge
    x = x0
    while x < x1:
        end_x = min(x + dash_length, x1)
        draw.line([(x, y0), (end_x, y0)], fill=color, width=width)
        x += dash_length + gap_length

    # Bottom edge
    x = x0
    while x < x1:
        end_x = min(x + dash_length, x1)
        draw.line([(x, y1), (end_x, y1)], fill=color, width=width)
        x += dash_length + gap_length

    # Left edge
    y = y0
    while y < y1:
        end_y = min(y + dash_length, y1)
        draw.line([(x0, y), (x0, end_y)], fill=color, width=width)
        y += dash_length + gap_length

    # Right edge
    y = y0
    while y < y1:
        end_y = min(y + dash_length, y1)
        draw.line([(x1, y), (x1, end_y)], fill=color, width=width)
        y += dash_length + gap_length


def _build_ai_director_grid_composite(player: Player) -> str | None:
    """
    Render a 2×6 grid image showing the 12 target baskets the AI director must describe.

    Each position (1–12) is drawn as a tile with the basket image and a clear slot label.
    This provides the director with a single composite image rather than 12 separate images,
    mirroring the visual context approach used for the matcher.

    Layout:
    - 2 rows × 6 columns for the 12 logical positions
    - Top row: Slots 1-6 (left to right)
    - Bottom row: Slots 7-12 (left to right)
    - Clear slot badges indicating the order for describing
    """
    if not hasattr(player, "group"):
        return None

    # Ensure the shared grid is created/refreshed for the current round
    # This is critical for AI vs AI observation mode where rounds may advance
    # without the normal page flow that refreshes the grid
    try:
        current_round = int(getattr(player, "round_number", 1) or 1)
        # Refresh grid if missing or if we're in a new round
        # (safety check: ensure grid exists for current round)
        try:
            shared_grid = json.loads(getattr(player.group, "shared_grid", "") or "[]")
            if not shared_grid:
                # Grid is empty, create it for current round
                import logging
                logging.info("[AI_DIRECTOR_GRID] Empty grid detected, creating for round %d", current_round)
                player.group.create_shared_grid(round_number=current_round)
                shared_grid = json.loads(getattr(player.group, "shared_grid", "") or "[]")
        except Exception:
            # Grid parsing failed, recreate it
            import logging
            logging.warning("[AI_DIRECTOR_GRID] Failed to parse grid, recreating for round %d", current_round)
            player.group.create_shared_grid(round_number=current_round)
            try:
                shared_grid = json.loads(getattr(player.group, "shared_grid", "") or "[]")
            except Exception:
                shared_grid = []
    except Exception:
        # Fallback: try to load existing grid
        try:
            shared_grid = json.loads(getattr(player.group, "shared_grid", "") or "[]")
        except Exception:
            shared_grid = []

    if not shared_grid:
        return None

    # Grid geometry: 2 rows × 6 columns for 12 baskets
    COLS = 6
    ROWS = 2
    TILE_W = 220
    TILE_H = 220
    PADDING = 12
    HEADER_H = 50
    INSTRUCTION_H = 36
    canvas_w = COLS * TILE_W + (COLS + 1) * PADDING
    grid_height = ROWS * TILE_H + (ROWS + 1) * PADDING
    canvas_h = PADDING + HEADER_H + INSTRUCTION_H + grid_height + PADDING

    # Color scheme - consistent with matcher grid
    bg_color = (240, 242, 245)
    slot_bg = (255, 255, 255)
    border_color = (70, 130, 180)  # Steel blue for all slots
    text_color = (50, 60, 70)
    header_color = (30, 40, 50)
    badge_bg = (70, 130, 180)  # Steel blue badges
    badge_text = (255, 255, 255)
    instruction_color = (80, 90, 100)

    img_canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(img_canvas)

    # Load fonts
    font_header = _load_font(24)
    font_label = _load_font(18)
    font_instruction = _load_font(14)

    # --- Header ---
    heading = "TARGET SEQUENCE (Baskets 1–12)"
    if font_header is not None:
        try:
            draw.text(
                (PADDING + 4, PADDING + 10),
                heading,
                font=font_header,
                fill=header_color,
            )
        except Exception:
            pass

    # --- Instruction line ---
    instruction = "Describe in order: top row (1->6) then bottom row (7->12). Focus on one basket at a time."
    if font_instruction is not None:
        try:
            draw.text(
                (PADDING + 4, PADDING + HEADER_H + 4),
                instruction,
                font=font_instruction,
                fill=instruction_color,
            )
        except Exception:
            pass

    # --- 2×6 Grid of target baskets ---
    grid_origin_y = PADDING + HEADER_H + INSTRUCTION_H
    for logical_pos in range(1, 13):
        row = (logical_pos - 1) // COLS
        col = (logical_pos - 1) % COLS

        x0 = PADDING + col * (TILE_W + PADDING)
        y0 = grid_origin_y + row * (TILE_H + PADDING)
        x1 = x0 + TILE_W
        y1 = y0 + TILE_H

        # Draw slot background with border
        draw.rectangle([x0, y0, x1, y1], fill=slot_bg, outline=border_color, width=3)

        # Get the basket image for this position
        slot_idx = logical_pos - 1
        if slot_idx < len(shared_grid):
            slot = shared_grid[slot_idx]
            rel_img_path = (slot.get("image") or "").lstrip("/ ")
            if rel_img_path:
                fs_path = _resolve_static_image_path(rel_img_path)
                if fs_path and os.path.exists(fs_path):
                    try:
                        with Image.open(fs_path) as basket_img:
                            basket_img = basket_img.convert("RGB")
                            # Fit basket image into the tile with margins
                            margin = 14
                            target_w = max(1, TILE_W - 2 * margin)
                            target_h = max(1, TILE_H - 2 * margin - 30)  # room for label
                            basket_img.thumbnail(
                                (target_w, target_h), Image.Resampling.LANCZOS
                            )
                            bw, bh = basket_img.size
                            bx = x0 + (TILE_W - bw) // 2
                            by = y0 + (TILE_H - bh) // 2 - 12
                            img_canvas.paste(basket_img, (bx, by))
                    except Exception:
                        pass

        # Draw position label badge at bottom center
        label = str(logical_pos)
        badge_center_x = x0 + TILE_W // 2
        badge_center_y = y1 - 18
        if font_label is not None:
            _draw_label_badge(
                draw,
                img_canvas,
                label,
                badge_center_x,
                badge_center_y,
                font_label,
                badge_bg,
                badge_text,
                padding=8,
                min_width=36,
            )

    # Save debug image (best-effort, errors are logged but don't break the flow)
    _debug_save_ai_director_grid_image(player, img_canvas)

    # Encode as data URL
    try:
        buf = io.BytesIO()
        img_canvas.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def _debug_save_ai_director_grid_image(player: Player, img_canvas: Image.Image) -> None:
    """
    Save the AI director grid composite as a PNG under the project's _static folder.

    This lets researchers visually confirm the image context sent to the director AI.
    """
    import logging
    import datetime
    
    logging.info("[AI_DEBUG] _debug_save_ai_director_grid_image called")
    
    try:
        app_dir = os.path.dirname(__file__)
        project_root = os.path.dirname(app_dir)
        debug_dir = os.path.join(project_root, "_static", "ai_debug")
        
        logging.info("[AI_DEBUG] Creating debug dir: %s", debug_dir)
        os.makedirs(debug_dir, exist_ok=True)

        session_code = ""
        try:
            if hasattr(player, "session") and player.session:
                session_code = getattr(player.session, "code", "") or ""
        except Exception as e:
            logging.warning("[AI_DEBUG] Failed to get session_code: %s", e)
            session_code = ""

        group_id = ""
        try:
            if hasattr(player, "group") and player.group:
                group_id = str(getattr(player.group, "id", "") or "")
        except Exception as e:
            logging.warning("[AI_DEBUG] Failed to get group_id: %s", e)
            group_id = ""

        round_num = ""
        try:
            round_num = str(getattr(player, "round_number", "") or "")
        except Exception as e:
            logging.warning("[AI_DEBUG] Failed to get round_num: %s", e)
            round_num = ""

        # Add timestamp to make filenames unique and traceable
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        parts = ["ai_director_grid"]
        if session_code:
            parts.append(session_code)
        if group_id:
            parts.append(f"g{group_id}")
        if round_num:
            parts.append(f"r{round_num}")
        parts.append(timestamp)
        filename = "_".join(parts) + ".png"

        path = os.path.join(debug_dir, filename)
        logging.info("[AI_DEBUG] Saving image to: %s", path)
        img_canvas.save(path, format="PNG")
        logging.info("[AI_DEBUG] Successfully saved director grid image to: %s", path)
    except Exception as e:
        import traceback
        logging.error("[AI_DEBUG] Failed to save director grid image: %s: %s\n%s", type(e).__name__, e, traceback.format_exc())


def _build_ai_matcher_grid_composite(player: Player) -> str | None:
    """
    Render a 2×6 grid image showing the AI matcher's current 12-slot sequence.

    Each logical position (1–12) is drawn as a tile. If the AI has chosen a
    basket for that position, we render the basket image; otherwise the tile is
    shown as an empty placeholder with a dashed border. This mirrors the visual
    layout used in the researcher debug popup so that the model's visual
    context is 1:1 with what the human sees.

    Visual enhancements:
    - Large, readable fonts for all labels
    - Badge-style labels with background for high contrast
    - Dashed borders for empty slots
    - Prominent section headers
    - Legend explaining the blue border meaning
    """
    # Only meaningful when there is a group object.
    if not hasattr(player, "group"):
        return None

    # Load the incremental AI partial sequence accumulated so far.
    try:
        partial = json.loads(getattr(player.group, "ai_partial_sequence", "") or "[]")
    except Exception:
        partial = []

    # Build an index of image paths by explicit logical position 1–12.
    MAX_SLOTS = 12
    slot_images: list[str | None] = [None] * MAX_SLOTS
    if isinstance(partial, list):
        for item in partial:
            if not isinstance(item, dict):
                continue
            pos = item.get("position")
            img = (item.get("image") or "").lstrip("/ ")
            try:
                pos_int = int(pos)
            except Exception:
                continue
            if 1 <= pos_int <= MAX_SLOTS and img:
                # Later entries overwrite earlier ones for the same position.
                slot_images[pos_int - 1] = img

    # Load the matcher pool (targets + distractors) for the staging grid.
    try:
        pool_items = _load_matcher_pool_image_urls(player)
    except Exception:
        pool_items = []
    pool_paths: list[str | None] = []
    for item in pool_items or []:
        slot = item.get("slot") or {}
        img_path = (slot.get("image") or "").lstrip("/ ")
        if img_path:
            pool_paths.append(img_path)
    # Limit to the first 18 items (3×6 grid) just like the human staging area.
    MAX_POOL_SLOTS = 18
    if len(pool_paths) > MAX_POOL_SLOTS:
        pool_paths = pool_paths[:MAX_POOL_SLOTS]
    if len(pool_paths) < MAX_POOL_SLOTS:
        pool_paths.extend([None] * (MAX_POOL_SLOTS - len(pool_paths)))

    # Track which pool baskets are already used in the 12-slot sequence so we
    # can lightly highlight them in the staging grid.
    used_paths = {p for p in slot_images if p}

    # Grid geometry:
    #   - Top: 2 rows × 6 columns for the 12 logical positions (target row)
    #   - Bottom: 3 rows × 6 columns for the staging pool of candidates
    COLS = 6
    TARGET_ROWS = 2
    STAGING_ROWS = 3
    TILE_W = 220
    TILE_H = 220
    PADDING = 12
    HEADER_H = 40  # increased for larger headers
    LEGEND_H = 32  # space for legend at bottom
    canvas_w = COLS * TILE_W + (COLS + 1) * PADDING

    target_height = TARGET_ROWS * TILE_H + (TARGET_ROWS + 1) * PADDING
    staging_height = STAGING_ROWS * TILE_H + (STAGING_ROWS + 1) * PADDING
    canvas_h = (
        PADDING
        + HEADER_H
        + target_height
        + PADDING
        + HEADER_H
        + staging_height
        + PADDING
        + LEGEND_H
        + PADDING
    )

    # Color scheme - refined for better contrast
    bg_color = (240, 242, 245)  # slightly darker background
    slot_bg_empty = (255, 255, 255)  # white for empty slots
    slot_bg_filled = (255, 255, 255)  # white for filled slots
    border_color = (180, 186, 194)
    border_empty = (160, 170, 180)  # slightly different for empty
    border_selected = (41, 128, 185)  # stronger blue for selected
    text_color = (50, 60, 70)
    header_color = (30, 40, 50)
    badge_bg_slot = (70, 130, 180)  # steel blue for slot badges
    badge_bg_candidate = (100, 100, 110)  # gray for candidate badges
    badge_text = (255, 255, 255)  # white text on badges
    empty_text_color = (150, 160, 170)  # muted for empty slot placeholder

    img_canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(img_canvas)

    # Load fonts at different sizes
    font_header = _load_font(22)
    font_label = _load_font(18)
    font_small = _load_font(14)
    font_empty = _load_font(32)  # large "?" for empty slots

    # --- Section Header: Current Sequence ---
    heading1 = "YOUR CURRENT SEQUENCE (Positions 1–12)"
    if font_header is not None:
        try:
            draw.text(
                (PADDING + 4, PADDING + 8),
                heading1,
                font=font_header,
                fill=header_color,
            )
        except Exception:
            pass

    # --- Top block: 12-slot target grid (2×6) ---
    target_origin_y = PADDING + HEADER_H
    for logical_pos in range(1, MAX_SLOTS + 1):
        row = (logical_pos - 1) // COLS
        col = (logical_pos - 1) % COLS

        x0 = PADDING + col * (TILE_W + PADDING)
        y0 = target_origin_y + row * (TILE_H + PADDING)
        x1 = x0 + TILE_W
        y1 = y0 + TILE_H

        rel_img_path = slot_images[logical_pos - 1]
        is_empty = rel_img_path is None

        if is_empty:
            # Draw empty slot with dashed border
            draw.rectangle([x0, y0, x1, y1], fill=slot_bg_empty)
            _draw_dashed_rect(draw, x0, y0, x1, y1, border_empty, dash_length=12, gap_length=8, width=3)

            # Draw large "?" in center for empty slots
            if font_empty is not None:
                try:
                    qw, qh = _get_text_dimensions(draw, "?", font_empty)
                    qx = x0 + (TILE_W - qw) // 2
                    qy = y0 + (TILE_H - qh) // 2 - 15
                    draw.text((qx, qy), "?", font=font_empty, fill=empty_text_color)
                except Exception:
                    pass
        else:
            # Draw filled slot with solid border
            draw.rectangle([x0, y0, x1, y1], fill=slot_bg_filled, outline=border_color, width=3)

            fs_path = _resolve_static_image_path(rel_img_path)
            if fs_path and os.path.exists(fs_path):
                try:
                    with Image.open(fs_path) as basket_img:
                        basket_img = basket_img.convert("RGB")
                        # Fit basket image into the tile with margins
                        margin = 14
                        target_w = max(1, TILE_W - 2 * margin)
                        target_h = max(1, TILE_H - 2 * margin - 30)  # leave room for label
                        basket_img.thumbnail(
                            (target_w, target_h), Image.Resampling.LANCZOS
                        )
                        bw, bh = basket_img.size
                        bx = x0 + (TILE_W - bw) // 2
                        by = y0 + (TILE_H - bh) // 2 - 12
                        img_canvas.paste(basket_img, (bx, by))
                except Exception:
                    pass

        # Draw position label badge at bottom center
        label = str(logical_pos)
        badge_center_x = x0 + TILE_W // 2
        badge_center_y = y1 - 18
        if font_label is not None:
            _draw_label_badge(
                draw,
                img_canvas,
                label,
                badge_center_x,
                badge_center_y,
                font_label,
                badge_bg_slot,
                badge_text,
                padding=8,
                min_width=36,
            )

    # --- Section Header: Candidate Pool ---
    staging_origin_y = target_origin_y + target_height + PADDING + HEADER_H
    heading2 = "CANDIDATE POOL (Choose from these baskets)"
    if font_header is not None:
        try:
            draw.text(
                (PADDING + 4, staging_origin_y - HEADER_H + 8),
                heading2,
                font=font_header,
                fill=header_color,
            )
        except Exception:
            pass

    # --- Bottom block: 3×6 staging grid of candidate baskets ---
    for idx, rel_path in enumerate(pool_paths):
        row = idx // COLS
        col = idx % COLS

        x0 = PADDING + col * (TILE_W + PADDING)
        y0 = staging_origin_y + row * (TILE_H + PADDING)
        x1 = x0 + TILE_W
        y1 = y0 + TILE_H

        is_used = rel_path and rel_path in used_paths
        outline_color = border_selected if is_used else border_color
        outline_width = 4 if is_used else 2

        draw.rectangle([x0, y0, x1, y1], fill=slot_bg_filled, outline=outline_color, width=outline_width)

        if rel_path:
            fs_path = _resolve_static_image_path(rel_path)
            if fs_path and os.path.exists(fs_path):
                try:
                    with Image.open(fs_path) as basket_img:
                        basket_img = basket_img.convert("RGB")
                        margin = 14
                        target_w = max(1, TILE_W - 2 * margin)
                        target_h = max(1, TILE_H - 2 * margin - 30)  # leave room for label
                        basket_img.thumbnail(
                            (target_w, target_h), Image.Resampling.LANCZOS
                        )
                        bw, bh = basket_img.size
                        bx = x0 + (TILE_W - bw) // 2
                        by = y0 + (TILE_H - bh) // 2 - 12
                        img_canvas.paste(basket_img, (bx, by))
                except Exception:
                    pass

        # Draw candidate index badge at bottom center
        label = str(idx + 1)
        badge_center_x = x0 + TILE_W // 2
        badge_center_y = y1 - 18
        if font_label is not None:
            _draw_label_badge(
                draw,
                img_canvas,
                label,
                badge_center_x,
                badge_center_y,
                font_label,
                badge_bg_candidate,
                badge_text,
                padding=8,
                min_width=36,
            )

    # --- Legend at bottom ---
    legend_y = canvas_h - LEGEND_H - PADDING + 4
    if font_small is not None:
        try:
            # Draw legend items
            legend_x = PADDING + 8

            # Blue border indicator
            draw.rectangle(
                [legend_x, legend_y + 4, legend_x + 24, legend_y + 24],
                fill=None,
                outline=border_selected,
                width=3,
            )
            legend_x += 32
            draw.text(
                (legend_x, legend_y + 6),
                "= Already placed in sequence",
                font=font_small,
                fill=text_color,
            )

            # Dashed border indicator
            legend_x += 220
            _draw_dashed_rect(
                draw,
                legend_x,
                legend_y + 4,
                legend_x + 24,
                legend_y + 24,
                border_empty,
                dash_length=6,
                gap_length=4,
                width=2,
            )
            legend_x += 32
            draw.text(
                (legend_x, legend_y + 6),
                "= Empty position (needs a basket)",
                font=font_small,
                fill=text_color,
            )
        except Exception:
            pass

    # Persist a debug PNG under _static/ so researchers can visually confirm
    # what the model sees. This intentionally mirrors the AI matcher debug row.
    try:
        _debug_save_ai_matcher_grid_image(player, img_canvas)
    except Exception:
        # Debugging is best-effort only; never break the main flow.
        pass

    # Encode the composite as a data URL for GPT‑4o.
    try:
        buf = io.BytesIO()
        img_canvas.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def _build_round_feedback_image(player: Player) -> str | None:
    """
    Render a feedback image showing round results with correct/incorrect highlighting.

    This mirrors what the human sees on the RoundFeedback page:
    - A 2×6 grid of the 12 positions
    - Green border for correct placements
    - Red border for incorrect placements
    - Header showing "Round X Feedback: Y/12 correct"

    Returns a data URL for the image, or None if generation fails.
    """
    if not hasattr(player, "group"):
        return None

    # Load the correct sequence and matcher's submissions
    try:
        shared_grid = json.loads(player.group.shared_grid or "[]")
        matcher_sequence = json.loads(player.group.matcher_sequence or "[]")
    except Exception:
        return None

    if not shared_grid:
        return None

    # Build correct sequence
    correct_sequence = [slot.get("image") for slot in shared_grid]

    # Build matcher's submissions by position
    matcher_by_pos = {}
    for item in matcher_sequence or []:
        if not isinstance(item, dict):
            continue
        pos = item.get("position")
        try:
            pos_int = int(pos)
        except (TypeError, ValueError):
            continue
        if 1 <= pos_int <= 12 and pos_int not in matcher_by_pos:
            matcher_by_pos[pos_int] = item

    # Grid geometry
    COLS = 6
    ROWS = 2
    TILE_W = 180
    TILE_H = 180
    PADDING = 10
    HEADER_H = 50
    LEGEND_H = 30

    canvas_w = COLS * TILE_W + (COLS + 1) * PADDING
    grid_height = ROWS * TILE_H + (ROWS + 1) * PADDING
    canvas_h = PADDING + HEADER_H + grid_height + LEGEND_H + PADDING

    # Colors
    bg_color = (245, 247, 250)
    correct_border = (40, 167, 69)  # Green
    incorrect_border = (220, 53, 69)  # Red
    correct_bg = (234, 247, 238)  # Light green
    incorrect_bg = (248, 215, 218)  # Light red
    text_color = (50, 60, 70)
    badge_text = (255, 255, 255)

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    img_canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(img_canvas)

    # Load fonts
    try:
        header_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except Exception:
        try:
            header_font = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            header_font = ImageFont.load_default()

    try:
        badge_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except Exception:
        try:
            badge_font = ImageFont.truetype("arial.ttf", 18)
        except Exception:
            badge_font = ImageFont.load_default()

    # Count correct placements and prepare slot data
    correct_count = 0
    slots_data = []
    for i in range(12):
        correct_img = correct_sequence[i] if i < len(correct_sequence) else None
        submitted_entry = matcher_by_pos.get(i + 1)
        submitted_img = submitted_entry.get("image") if submitted_entry else None

        is_correct = (
            submitted_img is not None
            and correct_img is not None
            and submitted_img == correct_img
        )
        if is_correct:
            correct_count += 1

        slots_data.append({
            "position": i + 1,
            "image": submitted_img,  # Show what was submitted
            "is_correct": is_correct,
        })

    # Draw header
    round_num = getattr(player, "round_number", "?")
    header_text = f"Round {round_num} Feedback: {correct_count}/12 correct"
    header_y = PADDING + 10
    try:
        bbox = draw.textbbox((0, 0), header_text, font=header_font)
        text_w = bbox[2] - bbox[0]
    except Exception:
        text_w = len(header_text) * 12
    header_x = (canvas_w - text_w) // 2
    draw.text((header_x, header_y), header_text, fill=text_color, font=header_font)

    # Draw grid
    grid_top = PADDING + HEADER_H
    for idx, slot in enumerate(slots_data):
        row = idx // COLS
        col = idx % COLS
        x = PADDING + col * (TILE_W + PADDING)
        y = grid_top + PADDING + row * (TILE_H + PADDING)

        # Choose colors based on correctness
        if slot["is_correct"]:
            border = correct_border
            fill = correct_bg
        else:
            border = incorrect_border
            fill = incorrect_bg

        # Draw slot background
        draw.rectangle([x, y, x + TILE_W, y + TILE_H], fill=fill, outline=border, width=4)

        # Draw basket image if present
        img_path = slot["image"]
        if img_path:
            try:
                full_path = _resolve_static_image_path(img_path)
                if full_path and os.path.isfile(full_path):
                    basket_img = Image.open(full_path).convert("RGBA")
                    # Scale to fit with padding
                    inner_size = min(TILE_W, TILE_H) - 20
                    basket_img.thumbnail((inner_size, inner_size), Image.Resampling.LANCZOS)
                    # Center in tile
                    bx = x + (TILE_W - basket_img.width) // 2
                    by = y + (TILE_H - basket_img.height) // 2
                    img_canvas.paste(basket_img, (bx, by), basket_img)
            except Exception:
                pass

        # Draw position badge
        badge_text_str = str(slot["position"])
        badge_w, badge_h = 28, 24
        badge_x = x + 6
        badge_y = y + 6
        badge_color = correct_border if slot["is_correct"] else incorrect_border
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=6,
            fill=badge_color,
        )
        try:
            bbox = draw.textbbox((0, 0), badge_text_str, font=badge_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except Exception:
            tw, th = 10, 14
        draw.text(
            (badge_x + (badge_w - tw) // 2, badge_y + (badge_h - th) // 2 - 1),
            badge_text_str,
            fill=badge_text,
            font=badge_font,
        )

    # Draw legend
    legend_y = grid_top + grid_height + 5
    legend_items = [
        (correct_border, "Correct"),
        (incorrect_border, "Incorrect"),
    ]
    legend_x = PADDING + 10
    for color, label in legend_items:
        draw.rectangle([legend_x, legend_y, legend_x + 16, legend_y + 16], fill=color)
        draw.text((legend_x + 22, legend_y - 2), label, fill=text_color, font=badge_font)
        legend_x += 100

    # Save debug copy locally
    _debug_save_round_feedback_image(player, img_canvas)

    # Encode as data URL
    try:
        buf = io.BytesIO()
        img_canvas.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def _debug_save_round_feedback_image(player: Player, img_canvas: Image.Image) -> None:
    """
    Save the round feedback image as a PNG under the project's _static folder.

    This lets researchers review the visual feedback that would be shown to the AI
    for cross-round history context.
    """
    try:
        app_dir = os.path.dirname(__file__)
        project_root = os.path.dirname(app_dir)
        debug_dir = os.path.join(project_root, "_static", "ai_debug")
        os.makedirs(debug_dir, exist_ok=True)

        session_code = ""
        try:
            if hasattr(player, "session") and player.session:
                session_code = getattr(player.session, "code", "") or ""
        except Exception:
            session_code = ""

        group_id = ""
        try:
            if hasattr(player, "group") and player.group:
                group_id = str(getattr(player.group, "id", "") or "")
        except Exception:
            group_id = ""

        round_num = ""
        try:
            round_num = str(getattr(player, "round_number", "") or "")
        except Exception:
            round_num = ""

        parts = ["round_feedback"]
        if session_code:
            parts.append(session_code)
        if group_id:
            parts.append(f"g{group_id}")
        if round_num:
            parts.append(f"r{round_num}")
        filename = "_".join(parts) + ".png"

        path = os.path.join(debug_dir, filename)
        img_canvas.save(path, format="PNG")
    except Exception:
        # Strictly best-effort; ignore any filesystem errors.
        pass


def _debug_save_ai_matcher_grid_image(player: Player, img_canvas: Image.Image) -> None:
    """
    Save the AI matcher grid composite as a PNG under the project's _static folder.

    This lets researchers open a static URL or file and visually confirm that the
    image context sent to GPT‑4o matches the AI matcher debug view and human UI.
    """
    import logging
    import datetime
    
    logging.info("[AI_DEBUG] _debug_save_ai_matcher_grid_image called")
    
    try:
        app_dir = os.path.dirname(__file__)
        project_root = os.path.dirname(app_dir)
        debug_dir = os.path.join(project_root, "_static", "ai_debug")
        
        logging.info("[AI_DEBUG] Creating debug dir: %s", debug_dir)
        os.makedirs(debug_dir, exist_ok=True)

        session_code = ""
        try:
            if hasattr(player, "session") and player.session:
                session_code = getattr(player.session, "code", "") or ""
        except Exception as e:
            logging.warning("[AI_DEBUG] Failed to get session_code: %s", e)
            session_code = ""

        group_id = ""
        try:
            if hasattr(player, "group") and player.group:
                group_id = str(getattr(player.group, "id", "") or "")
        except Exception as e:
            logging.warning("[AI_DEBUG] Failed to get group_id: %s", e)
            group_id = ""

        round_num = ""
        try:
            round_num = str(getattr(player, "round_number", "") or "")
        except Exception as e:
            logging.warning("[AI_DEBUG] Failed to get round_num: %s", e)
            round_num = ""

        # Add timestamp to make filenames unique and traceable
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        parts = ["ai_matcher_grid"]
        if session_code:
            parts.append(session_code)
        if group_id:
            parts.append(f"g{group_id}")
        if round_num:
            parts.append(f"r{round_num}")
        parts.append(timestamp)
        filename = "_".join(parts) + ".png"

        path = os.path.join(debug_dir, filename)
        logging.info("[AI_DEBUG] Saving matcher image to: %s", path)
        img_canvas.save(path, format="PNG")
        logging.info("[AI_DEBUG] Successfully saved matcher grid image to: %s", path)
    except Exception as e:
        import traceback
        logging.error("[AI_DEBUG] Failed to save matcher grid image: %s: %s\n%s", type(e).__name__, e, traceback.format_exc())


def _load_shared_grid_image_urls(player: Player) -> list[dict[str, Any]]:
    """Return a list of {'slot': slot_dict, 'data_url': 'data:image/...'} for the shared grid.

    If images cannot be resolved, returns an empty list and callers should gracefully
    fall back to text-only prompting.
    """
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


def _load_matcher_pool_image_urls(player: Player) -> list[dict[str, Any]]:
    """Return image URLs for the matcher's full choice pool (targets + distractors).

    For the MATCHER role we want to approximate the staging area the human
    matcher sees: the 12 target baskets from the director's grid plus the
    additional distractor baskets drawn from the preset `fullList` for the
    configured basket set.
    """
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
    set_num = 5  # Default; updated below if session config is available
    try:
        if hasattr(player, "session") and player.session:
            try:
                set_num = int(player.session.config.get("basket_set", 5))
            except Exception:
                set_num = 5
        else:
            set_num = 5
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
    # the 12‑basket grid.
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

    # Shuffle the combined pool using the same deterministic seed as the human
    # matcher's staging area (see DraggableGridPage.vars_for_template).
    # This ensures the AI matcher sees baskets in the exact same order.
    import random
    combined = base + extras
    try:
        round_num = int(getattr(player, "round_number", 1) or 1)
    except Exception:
        round_num = 1
    seed = 4242 + (set_num * 100) + round_num
    rng = random.Random(seed)
    rng.shuffle(combined)
    return combined


def _inject_visual_grid_context(player: Player, messages: list[dict[str, Any]]):
    """Inject a multimodal grid message so the AI sees the 12-basket layout.

    This wrapper is applied on top of all prompt strategies (v1/v2/v3/etc.)
    so that the only differences between strategies are in how the model is
    instructed to reason and respond, not in whether it has visual access
    to the baskets.
    """
    if not messages:
        return messages

    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"
    if ai_role not in ("director", "matcher"):
        return messages

    # Both roles now receive a single composite grid image:
    # - Director: 2×6 grid of the 12 target baskets to describe
    # - Matcher: 12-slot sequence (top) + candidate pool (bottom)
    composite_url = None
    if ai_role == "director":
        composite_url = _build_ai_director_grid_composite(player)
    else:
        composite_url = _build_ai_matcher_grid_composite(player)

    if not composite_url:
        # Shapes demo or static images missing; fall back to text-only prompts.
        import logging
        logging.warning("[VISUAL_CONTEXT] No composite_url generated for %s", ai_role)
        return messages
    
    import logging
    # Log a short hash of the image so we can verify different rounds get different images
    # (without flooding logs with 700KB of base64)
    img_hash = hashlib.md5(composite_url.encode()).hexdigest()[:12] if composite_url else "none"
    logging.info(
        "[VISUAL_CONTEXT] Generated composite image for %s, round=%s, URL length: %d bytes, hash=%s",
        ai_role, 
        getattr(player, "round_number", "?"),
        len(composite_url) if composite_url else 0, 
        img_hash
    )

    # Get current round number for explicit context
    current_round = getattr(player, "round_number", 1) or 1

    if ai_role == "director":
        intro_text = (
            f"ROUND {current_round} TARGET GRID: This image shows the 12 baskets you must describe for the CURRENT round. "
            f"Previous round feedback shows DIFFERENT baskets - use that to learn from mistakes, "
            f"but describe ONLY the baskets in THIS image.\n\n"
            "The grid shows 2 rows × 6 columns with Baskets 1–6 on the top row and Baskets 7–12 on the bottom row. "
            "IMPORTANT: Describe ONE BASKET PER MESSAGE, not all at once. Wait for your partner to confirm before moving to the next basket. "
            "Your MATCHER partner sees these 12 baskets mixed with additional distractors in their pool."
        )
    else:
        intro_text = (
            f"ROUND {current_round} MATCHER VIEW: This image shows your current sequence state for the CURRENT round. "
            f"Previous round feedback shows DIFFERENT baskets - use that to learn from mistakes, "
            f"but select ONLY from the baskets in THIS image.\n\n"
            "In the composite image, the TOP TWO ROWS show your CURRENT 12‑position sequence as the MATCHER "
            "(positions 1–12), and the BOTTOM THREE ROWS show your CANDIDATE POOL of baskets you can choose from. "
            "Positions with baskets in the top grid are your current guesses; empty positions are still unfilled or were "
            "cleared when you moved a basket. Every basket the DIRECTOR describes is one of the 12 true targets "
            "hidden within this candidate pool."
        )

    multimodal_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": intro_text,
        },
        {
            "type": "image_url",
            "image_url": {
                "url": composite_url,
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


def _should_log_v3_reasoning(player: Player) -> bool:
    """Return True if we should persist V3 reasoning JSON for this session.

    Controlled by (in order of precedence):
    - session.config['log_v3_reasoning'] (truthy)
    - LOG_V3_REASONING environment variable ('1', 'true', 'yes')
    """
    try:
        if hasattr(player, "session") and player.session:
            if bool(player.session.config.get("log_v3_reasoning", False)):
                return True
    except Exception:
        pass

    flag = os.environ.get("LOG_V3_REASONING", "").strip().lower()
    return flag in ("1", "true", "yes")


def _get_ai_client():
    """Return an OpenAI client if configured, otherwise None.

    We fail gracefully when the library or API key is missing so the app
    can still run (the chat will simply not have an AI partner reply).
    """
    if OpenAI is None:
        return None
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


# ---------------------------------------------------------------------------
# Model Configuration Helpers
# ---------------------------------------------------------------------------

# Reasoning models use reasoning_effort parameter instead of temperature
REASONING_MODELS = frozenset([
    "gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.2-pro", "gpt-5.2-chat-latest",
    "o1", "o1-mini", "o1-preview", "o3", "o3-mini",
])

# Default model and reasoning effort
DEFAULT_MODEL = "gpt-5.2"
DEFAULT_REASONING_EFFORT = "none"  # Options: "none", "low", "medium", "high"


def _is_reasoning_model(model: str) -> bool:
    """Check if the model is a reasoning model that uses reasoning_effort parameter.
    
    Reasoning models (GPT-5+, o1, o3) use `reasoning_effort` instead of `temperature`.
    Traditional models (GPT-4o, GPT-4) use `temperature`.
    """
    if not model:
        return False
    model_lower = model.lower().strip()
    # Check exact matches first
    if model_lower in REASONING_MODELS:
        return True
    # Check prefixes for versioned models
    for prefix in ("gpt-5", "o1", "o3"):
        if model_lower.startswith(prefix):
            return True
    return False


def _get_ai_model(player: Player | None) -> str:
    """Get the AI model to use for this session.
    
    Priority:
    1. session.config['ai_model']
    2. OPENAI_MODEL environment variable
    3. DEFAULT_MODEL (gpt-5.2)
    """
    # Session-level override
    try:
        if player and hasattr(player, "session") and player.session:
            cfg_model = player.session.config.get("ai_model")
            if isinstance(cfg_model, str) and cfg_model.strip():
                return cfg_model.strip()
    except Exception:
        pass
    
    # Environment variable
    env_model = os.environ.get("OPENAI_MODEL", "").strip()
    if env_model:
        return env_model
    
    return DEFAULT_MODEL


def _get_ai_reasoning_effort(player: Player | None) -> str | None:
    """Get the reasoning effort level for reasoning models.
    
    Priority:
    1. session.config['ai_reasoning_effort']
    2. AI_REASONING_EFFORT environment variable
    3. DEFAULT_REASONING_EFFORT ("none")
    
    Returns None for traditional models that don't support reasoning_effort.
    Valid values: "none", "low", "medium", "high"
    """
    # Session-level override
    try:
        if player and hasattr(player, "session") and player.session:
            cfg_effort = player.session.config.get("ai_reasoning_effort")
            if isinstance(cfg_effort, str) and cfg_effort.strip():
                return cfg_effort.strip().lower()
    except Exception:
        pass
    
    # Environment variable
    env_effort = os.environ.get("AI_REASONING_EFFORT", "").strip().lower()
    if env_effort:
        return env_effort
    
    return DEFAULT_REASONING_EFFORT


def _build_model_params(player: Player | None, response_format: dict | None = None) -> dict[str, Any]:
    """Build model-specific parameters for the OpenAI API call.
    
    Returns a dict with model-appropriate parameters:
    - For reasoning models (GPT-5+, o1, o3): uses reasoning_effort
    - For traditional models (GPT-4o): uses temperature
    """
    model = _get_ai_model(player)
    params: dict[str, Any] = {"model": model}
    
    if _is_reasoning_model(model):
        # Reasoning models use reasoning_effort instead of temperature
        effort = _get_ai_reasoning_effort(player)
        if effort:
            params["reasoning_effort"] = effort
    else:
        # Traditional models use temperature
        params["temperature"] = 0
    
    # Add response format if specified (works for both model types)
    if response_format is not None:
        params["response_format"] = response_format
    
    return params


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


def _build_ai_messages_from_history(player: Player, history):
    """Convert stored chat history into OpenAI chat messages.

    - Human messages are mapped to role='user'
    - AI messages are mapped to role='assistant'
    - Feedback/system messages are mapped to role='user' (shared context info)
    - Feedback messages with images become multimodal content
    """
    messages: list[dict[str, Any]] = []
    human_role = (
        player.field_maybe_none("player_role") or player.participant.vars.get("role")
    )
    ai_role = "matcher" if human_role == "director" else "director"

    for msg in history:
        sender = msg.get("sender_role")
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        if sender == ai_role:
            role = "assistant"
        elif sender == "system" or msg.get("is_feedback"):
            # Feedback messages are shared context (both players see round results)
            # Treat as user message to maintain conversation flow
            role = "user"
        else:
            role = "user"

        # Handle multimodal feedback messages with images
        image_url = msg.get("image_url")
        if image_url and msg.get("is_feedback"):
            # Create multimodal content for feedback with visual
            content = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]
            messages.append({"role": role, "content": content})
        else:
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


def _get_max_history_turns(player: Player) -> int:
    """Return an upper bound on how many past turns to send to the model.

    Configurable via either:
    - session.config['ai_max_history_turns']
    - AI_MAX_HISTORY_TURNS environment variable

    Defaults to 16, and is clamped to the range [4, 500] for safety.
    GPT-4o supports 128K tokens (~500-1000 dialogue turns depending on length),
    so higher values are feasible for cross-round entrainment studies.
    """
    default = 16
    try:
        if hasattr(player, "session") and player.session:
            raw = player.session.config.get("ai_max_history_turns")
            if isinstance(raw, int) and raw > 0:
                return max(4, min(raw, 500))
    except Exception:
        pass

    env_val = os.environ.get("AI_MAX_HISTORY_TURNS", "").strip()
    if env_val:
        try:
            n = int(env_val)
            if n > 0:
                return max(4, min(n, 500))
        except Exception:
            pass
    return default


def _get_prompt_strategy_name(player: Player) -> str:
    """Return the configured prompt strategy name.

    Strategy can be set per-session via `session.config['prompt_strategy']`
    (e.g., 'simple', 'weiling') or globally via PROMPT_STRATEGY env var.
    Defaults to 'simple' for backward compatibility.
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

    # Default to v1/simple prompting
    return "v1"


def _generate_ai_reply(player: Player, latest_message):
    """Generate a GPT‑4o reply for the AI partner, given the latest human message.

    Returns a dict of the form:
        {
            "text": "<utterance to show in chat>" or None,
            "selection": {
                "basket_id": int | None,   # for MATCHER role only
                "ready_to_submit": bool,   # whether the matcher wants to submit now
            } | None,
        }

    For non‑matcher roles (AI as DIRECTOR) the ``selection`` field is always None.
    This function is intentionally conservative and fails silently if the
    OpenAI client is not available or any error occurs.
    """
    # Safety check: Ensure the shared grid is refreshed for the current round
    # This is critical for AI vs AI observation mode where rounds may advance
    # without the normal page flow that refreshes the grid
    try:
        if hasattr(player, "group") and hasattr(player, "round_number"):
            current_round = int(getattr(player, "round_number", 1) or 1)
            # Check if grid exists and is valid
            try:
                shared_grid = json.loads(getattr(player.group, "shared_grid", "") or "[]")
                if not shared_grid:
                    # Grid is empty, refresh it for current round
                    import logging
                    logging.info("[AI_REPLY] Empty grid detected at round %d, refreshing...", current_round)
                    player.group.create_shared_grid(round_number=current_round)
            except Exception:
                # Grid parsing failed, refresh it
                import logging
                logging.warning("[AI_REPLY] Failed to parse grid at round %d, refreshing...", current_round)
                try:
                    player.group.create_shared_grid(round_number=current_round)
                except Exception:
                    pass  # Continue anyway, let _build_ai_director_grid_composite handle it
    except Exception:
        pass  # Non-fatal, continue with reply generation
    
    client = _get_ai_client()
    if client is None:
        # Optional: surface a visible debug message instead of failing silently.
        if _ai_debug_enabled(player):
            human_role = (
                player.field_maybe_none("player_role")
                or player.participant.vars.get("role")
            )
            ai_role = "matcher" if human_role == "director" else "director"
            return {
                "text": (
                    "[DEBUG] The AI partner is not configured on the server "
                    "(missing OpenAI client or OPENAI_API_KEY), so you will "
                    f"not receive automated replies from the {ai_role.upper()} in this session."
                ),
                "selection": None,
            }
        return None

    def _build_matcher_json_instruction(player: Player, strategy_name: str) -> str:
        """Build a matcher‑specific system instruction for JSON + basket IDs.

        This is intentionally concise — behavioral rules (lowest position first,
        announcing moves, ready-to-submit phrasing) are defined in the base
        prompts (v1/v2/v3). This instruction only standardizes the JSON schema.
        """
        instructions = (
            "You MUST respond with valid JSON containing BOTH an \"utterance\" field AND a \"selection\" field:\n"
            "{\n"
            '  "utterance": "<your natural language response to show in the chat - describe what you see, ask questions, or confirm your choice>",\n'
            '  "selection": {\n'
            '    "candidate_index": <integer 1–18 from the numbered candidate tiles, or null if asking for clarification>,\n'
            '    "position": <integer 1–12 for which position this basket goes in, or null for next available>,\n'
            '    "ready_to_submit": <true only when submitting final 12‑basket order, otherwise false>\n'
            "  }\n"
            "}\n\n"
            "Rules:\n"
            "- The \"utterance\" field is REQUIRED - this is what the human will see in the chat.\n"
            "- Never mention candidate indices, IDs, or filenames in your utterance.\n"
            "- If you reuse a candidate_index already placed elsewhere, the system moves it (old position becomes empty).\n"
            "- Set ready_to_submit to true only once, when you're confident in all 12 positions."
        )
        return instructions

    def _parse_reply_json(
        text: str,
        *,
        player: Player,
        strategy_name: str,
        ai_role: str,
        use_v3_cot: bool,
    ):
        """Parse a JSON-structured reply into (utterance, selection_dict)."""
        utterance = None  # Start with None, not raw text
        selection = None
        if not text:
            return None, None

        try:
            import logging

            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end <= start:
                logging.info(
                    "[AI_MATCHER] JSON envelope not found; treating reply as plain text. "
                    "session=%s round=%s strategy=%s ai_role=%s text_snip=%s",
                    getattr(getattr(player, "session", None), "code", None),
                    getattr(player, "round_number", None),
                    strategy_name,
                    ai_role,
                    (text[:120] + "…") if len(text) > 120 else text,
                )
                # No JSON found - return the text as plain utterance
                return (text or "").strip() or None, None
            json_str = text[start:end]
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return (text or "").strip() or None, None

            # Extract utterance if provided
            u = data.get("utterance")
            if isinstance(u, str) and u.strip():
                utterance = u.strip()

            # Optional selection block (used when AI is the MATCHER)
            if ai_role == "matcher":
                sel = data.get("selection")
                if isinstance(sel, dict):
                    # Primary field is `candidate_index` for the composite‑grid matcher.
                    cand_raw = sel.get("candidate_index")
                    pos = sel.get("position")
                    try:
                        cand_int = int(cand_raw) if cand_raw is not None else None
                    except Exception:
                        cand_int = None
                    try:
                        pos_int = int(pos) if pos is not None else None
                    except Exception:
                        pos_int = None
                    ready = bool(sel.get("ready_to_submit", False))
                    selection = {
                        "candidate_index": cand_int,
                        "position": pos_int,
                        "ready_to_submit": ready,
                    }
                    # logging.info(
                    #     "[AI_MATCHER] Parsed selection: session=%s round=%s candidate_index=%s position=%s ready=%s strategy=%s",
                    #     getattr(getattr(player, "session", None), "code", None),
                    #     getattr(player, "round_number", None),
                    #     cand_int,
                    #     pos_int,
                    #     ready,
                    #     strategy_name,
                    # )

            # Optional: log full reasoning JSON for V3 CoT runs
            if (
                use_v3_cot
                and data.get("reasoning") is not None
                and hasattr(player, "group")
            ):
                try:
                    try:
                        existing = json.loads(
                            getattr(player.group, "ai_reasoning_log", "[]") or "[]"
                        )
                    except Exception:
                        existing = []
                    if not isinstance(existing, list):
                        existing = []
                    human_role = (
                        player.field_maybe_none("player_role")
                        or player.participant.vars.get("role")
                    )
                    ai_role_local = "matcher" if human_role == "director" else "director"
                    log_entry = {
                        "round_number": getattr(player, "round_number", None),
                        "timestamp": datetime.datetime.now().isoformat(),
                        "strategy_name": strategy_name,
                        "human_role": human_role,
                        "ai_role": ai_role_local,
                        "reasoning": data.get("reasoning"),
                        "utterance": utterance,
                        "raw_text": text,
                    }
                    existing.append(log_entry)
                    player.group.ai_reasoning_log = json.dumps(
                        existing, ensure_ascii=False
                    )
                except Exception:
                    # Logging should never break the main flow
                    pass

            return utterance, selection
        except Exception:
            # Fall back to plain-text behavior - return original text if not JSON
            plain_text = (text or "").strip()
            # Don't return raw JSON as utterance
            if plain_text.startswith("{") and plain_text.endswith("}"):
                return None, None
            return plain_text or None, None

    try:
        import logging
        # logging.info("[AI_DEBUG] Starting _generate_ai_reply for player round=%s", getattr(player, "round_number", None))
        
        # Load full chat history: human + AI messages.
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
        feedback_msgs = []  # Synthetic round feedback messages
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
                        # Optionally tag with round number for entrainment analysis
                        if round_num is not None and "round_number" not in m:
                            m = dict(m)  # shallow copy to avoid mutating stored data
                            m["round_number"] = round_num
                        human_msgs.append(m)
                # AI messages from this round's group (FIXED: was missing before)
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
                
                # For completed rounds (before current), inject feedback summary
                # This mirrors what the human sees on the RoundFeedback screen
                if round_num is not None and round_num < current_round:
                    correct_count = _compute_round_correct_count(p_round)
                    if correct_count is not None:
                        # Generate visual feedback image (same as human sees)
                        feedback_image_url = _build_round_feedback_image(p_round)
                        feedback_msgs.append({
                            "text": (
                                f"[ROUND {round_num} FEEDBACK: We got {correct_count}/12 baskets correct. "
                                f"Green borders = correct placements, Red borders = mistakes. "
                                f"Use this feedback to learn what went wrong and improve your communication/selection strategy. "
                                f"NOTE: This image shows Round {round_num}'s baskets which are DIFFERENT from the current round.]"
                            ),
                            "sender_role": "system",
                            "round_number": round_num,
                            "is_feedback": True,  # Used for sort ordering
                            "image_url": feedback_image_url,  # Visual feedback (may be None)
                        })
        else:
            # Single-round history (no cross-round context)
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
            # No feedback messages in single-round mode
            feedback_msgs = []

        # Merge and sort by (round_number, timestamp) for coherent history
        # This ensures feedback messages appear at the end of their respective rounds
        all_history = []
        for m in human_msgs + ai_msgs + feedback_msgs:
            if isinstance(m, dict):
                all_history.append(m)
        all_history.sort(
            key=lambda m: (
                m.get("round_number") or 0,  # Group by round first
                1 if m.get("is_feedback") else 0,  # Feedback sorts last within round
                m.get("server_ts") or "",
                m.get("timestamp") or "",
            )
        )

        # Choose prompt strategy and build chat messages accordingly
        strategy_name = _get_prompt_strategy_name(player)
        human_role = (
            player.field_maybe_none("player_role") or player.participant.vars.get("role")
        )
        ai_role = "matcher" if human_role == "director" else "director"

        # Map visual aliases onto the underlying Weiling strategy
        if strategy_name in (
            "director_visual",
            "visual_director",
            "matcher_visual",
            "visual_matcher",
        ):
            strategy_for_prompt = "v2"
        else:
            strategy_for_prompt = strategy_name

        # Lazily import prompt strategy modules
        from . import prompt_v1, prompt_v2, prompt_v3

        if strategy_for_prompt in ("weiling", "v2"):
            chat_messages = prompt_v2.build_weiling_prompt_messages(
                player, latest_message, all_history
            )
            use_v3_cot = False
        elif strategy_for_prompt in ("v3", "v3_cot"):
            chat_messages = prompt_v3.build_v3_cot_prompt_messages(
                player, latest_message, all_history
            )
            use_v3_cot = True
        else:
            # v1/simple is the default
            chat_messages = prompt_v1.build_simple_prompt_messages(
                player, latest_message, all_history
            )
            use_v3_cot = False

        # Inject shared task background so AI has same context as human participants
        chat_messages = _inject_task_background(chat_messages)

        # Inject multimodal visual grid context for all strategies (when images
        # are available).
        chat_messages = _inject_visual_grid_context(player, chat_messages)
        
        # For AI Director at round start, add an explicit "start" message
        # so the model knows to begin with Basket 1 for THIS round (not continue from previous)
        if ai_role == "director" and latest_message is None:
            current_round = getattr(player, "round_number", 1) or 1
            chat_messages.append({
                "role": "user",
                "content": (
                    f"START OF ROUND {current_round}: This is a NEW round with the baskets in a DIFFERENT ORDER. "
                    f"The basket positions have been reshuffled - Basket 1 in this round is NOT the same as Basket 1 from previous rounds. "
                    f"Please describe ONLY Basket 1 (top-left in the grid) for now. "
                    f"Do NOT describe multiple baskets - just Basket 1. Wait for a response before moving to Basket 2."
                )
            })
            logging.info("[AI_DIRECTOR] Added explicit start prompt for round %d", current_round)

        # For fairness across prompt strategies, ALWAYS (matcher role only) inject
        # an explicit, machine-readable view of the current 12-slot sequence state.
        # This prevents the model from needing to infer null/unfilled slots from the image.
        if ai_role == "matcher":
            try:
                seq_state = _build_matcher_current_sequence_state_for_prompt(player)
                seq_state_text = (
                    "AUTHORITATIVE CURRENT MATCHER SEQUENCE STATE (for this turn):\n"
                    "- There are 12 positions total.\n"
                    "- `sequence_candidate_indices` is a length-12 array aligned to positions 1..12.\n"
                    "- A value of null means that position is EMPTY/unfilled right now.\n"
                    "- Default `reasoning.target_position` is the LOWEST-NUMBERED null entry in `sequence_candidate_indices` (unless the DIRECTOR explicitly revisits a specific basket number).\n"
                    "- You MUST NOT set `selection.ready_to_submit` true if ANY entry is null.\n"
                    f"{json.dumps(seq_state, ensure_ascii=False)}"
                )
                insert_idx = 0
                while (
                    insert_idx < len(chat_messages)
                    and isinstance(chat_messages[insert_idx], dict)
                    and chat_messages[insert_idx].get("role") == "system"
                ):
                    insert_idx += 1
                chat_messages = (
                    chat_messages[:insert_idx]
                    + [{"role": "system", "content": seq_state_text}]
                    + chat_messages[insert_idx:]
                )
            except Exception:
                pass

        # When the AI is acting as MATCHER, append an additional system message
        # that standardises the JSON output format — but skip for v3/CoT since
        # that strategy already includes a complete selection schema in its prompt.
        if ai_role == "matcher" and not use_v3_cot:
            matcher_instr = _build_matcher_json_instruction(player, strategy_for_prompt)
            matcher_system_msg = {"role": "system", "content": matcher_instr}
            insert_idx = 0
            while (
                insert_idx < len(chat_messages)
                and chat_messages[insert_idx].get("role") == "system"
            ):
                insert_idx += 1
            chat_messages = (
                chat_messages[:insert_idx]
                + [matcher_system_msg]
                + chat_messages[insert_idx:]
            )

        # Debug: log the explicit sequence state we pass into the model (matcher only).
        # This helps verify that the model is actually being shown null/unfilled positions.
        try:
            if (
                ai_role == "matcher"
                and _ai_debug_enabled(player)
                and isinstance(chat_messages, list)
            ):
                seq_msg = None
                for m in chat_messages:
                    if not isinstance(m, dict):
                        continue
                    if m.get("role") != "system":
                        continue
                    content = m.get("content")
                    if (
                        isinstance(content, str)
                        and content.startswith(
                            "AUTHORITATIVE CURRENT MATCHER SEQUENCE STATE"
                        )
                    ):
                        seq_msg = content
                        break
                if seq_msg:
                    # Try to parse out the embedded JSON for a compact summary.
                    seq_json = None
                    try:
                        json_start = seq_msg.find("{")
                        if json_start != -1:
                            seq_json = json.loads(seq_msg[json_start:])
                    except Exception:
                        seq_json = None

                    if isinstance(seq_json, dict) and "sequence_candidate_indices" in seq_json:
                        indices = seq_json.get("sequence_candidate_indices")
                        filled = (
                            sum(1 for x in indices if x is not None)
                            if isinstance(indices, list)
                            else None
                        )
                        logging.info(
                            "[AI_DEBUG] Matcher sequence passed to model: filled=%s/12 indices=%s",
                            filled,
                            indices,
                        )
                    else:
                        logging.info(
                            "[AI_DEBUG] Matcher sequence system msg passed to model (raw): %s",
                            seq_msg,
                        )
        except Exception:
            # Best-effort debug only; never break the main flow.
            pass

        # Build model-specific parameters (handles reasoning vs traditional models)
        response_format = None
        if ai_role == "matcher":
            response_format = {"type": "json_object"}

        # Get model parameters based on configured model type
        completion_kwargs = _build_model_params(player, response_format)
        completion_kwargs["messages"] = chat_messages

        # Debug: log message structure to verify image is included
        for i, msg in enumerate(chat_messages):
            role = msg.get("role", "?")
            content = msg.get("content")
            if isinstance(content, list):
                # Multimodal message
                parts_desc = []
                for part in content:
                    if isinstance(part, dict):
                        ptype = part.get("type", "?")
                        if ptype == "image_url":
                            url = (part.get("image_url") or {}).get("url", "")
                            parts_desc.append(f"image_url({len(url)} chars)")
                        elif ptype == "text":
                            text_preview = (part.get("text") or "")[:50]
                            parts_desc.append(f"text({text_preview}...)")
                        else:
                            parts_desc.append(f"{ptype}(?)")
                logging.info("[API_MSG %d] role=%s, multimodal: %s", i, role, ", ".join(parts_desc))
            else:
                content_preview = str(content)[:80] if content else "(empty)"
                logging.info("[API_MSG %d] role=%s, content: %s...", i, role, content_preview)
        
        try:
            completion = client.chat.completions.create(**completion_kwargs)
        except Exception as api_err:
            logging.error("[AI_DEBUG] OpenAI API call failed: %s: %s", type(api_err).__name__, api_err)
            raise
        
        # logging.info("[AI_DEBUG] API call succeeded, parsing response")
        reply = completion.choices[0].message.content
        logging.info("[AI_DEBUG] Raw reply type: %s, value preview: %s", type(reply).__name__, str(reply) if reply else None)
        
        if isinstance(reply, list):
            # Newer SDKs may return a list of content parts; join them
            logging.info("[AI_DEBUG] Reply is a list with %d items", len(reply))
            reply = "".join(
                (part.get("text", "") if isinstance(part, dict) else str(getattr(part, 'text', '')))
                for part in reply
            )
        text = (reply or "").strip()

        # For all strategies we attempt to parse a JSON envelope with
        # {reasoning, utterance, selection}.
        utterance, selection = _parse_reply_json(
            text,
            player=player,
            strategy_name=strategy_name,
            ai_role=ai_role,
            use_v3_cot=use_v3_cot,
        )
        return {"text": utterance, "selection": selection}
    except Exception as e:
        # Log the full exception with traceback for debugging
        import logging
        import traceback
        logging.error(
            "[AI_DEBUG] Exception in _generate_ai_reply: %s: %s\n%s",
            type(e).__name__, e, traceback.format_exc()
        )
        
        # Optional: surface an explicit debug message when configured.
        if _ai_debug_enabled(player):
            err_name = type(e).__name__
            err_msg = str(e)[:100] if str(e) else ""
            return {
                "text": (
                    "[DEBUG] The AI partner encountered an error and is currently offline "
                    f"(error type: {err_name}). {err_msg}. The human can continue the task without AI replies."
                ),
                "selection": None,
            }
        # Fail silently; the human can still continue without AI reply
        return None


def _update_ai_partial_sequence(player: Player, selection: dict[str, Any] | None):
    """
    Update the group's incremental AI matcher sequence based on a single
    basket choice for the current turn.

    Instead of asking the model for the full 12‑basket sequence on every
    turn, we maintain an incremental sequence in `ai_partial_sequence`.
    """
    # `selection` must be a dict with fields
    #   {"candidate_index": int|None, "position": int|None, ...}
    selected_candidate_index = None
    target_position = None
    if isinstance(selection, dict):
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

    # If there is no concrete basket choice (clarification-only turn), do not
    # modify the partial sequence; just return the existing state.
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
    partial_sorted = [by_pos[p] for p in sorted(by_pos.keys())]
    try:
        group.ai_partial_sequence = json.dumps(partial_sorted)
    except Exception:
        # Do not let debug state break the main flow.
        pass
    return partial_sorted


# ---------------------------------------------------------------------------
# AI Partner Perceptions (post-task survey from AI's perspective)
# ---------------------------------------------------------------------------

AI_PARTNER_PERCEPTION_PROMPT = """
You just completed a collaborative task with a human partner across 4 rounds.
In this task, you and your partner had to work together to correctly order 12 baskets.

Based on the complete conversation history below, please evaluate your human partner
by answering the same questions that human participants answer about their partners.

For each statement, provide a rating from 1 to 5 where:
1 = strongly disagree
2 = disagree
3 = neutral
4 = agree
5 = strongly agree

Please respond with a JSON object in the following format:
{
    "partner_capable": <1-5>,
    "partner_helpful": <1-5>,
    "partner_understood": <1-5>,
    "partner_adapted": <1-5>,
    "collaboration_improved": <1-5>,
    "partner_comment": "<your comment about how your partner did the task>"
}

The questions are:
- partner_capable: "My partner was capable of doing their task"
- partner_helpful: "My partner was helpful to me for completing my task"
- partner_understood: "My partner understood what I was trying to communicate"
- partner_adapted: "My partner adapted to the way I communicated over time"
- collaboration_improved: "Our collaboration improved over time"
- partner_comment: "Please comment about how your partner did the task"

Be honest and thoughtful in your evaluation. Consider the entire conversation history,
including how well your partner communicated, followed instructions, asked clarifying
questions, and adapted over the course of the 4 rounds.
""".strip()


def generate_ai_partner_perceptions(player: Player) -> dict[str, Any] | None:
    """Generate AI's perceptions of the human partner at the end of the experiment.

    This mirrors the PartnerPerceptions questions that humans answer about their
    AI partner, but from the AI's perspective about the human.

    Returns a dict with keys:
        - partner_capable (int 1-5)
        - partner_helpful (int 1-5)
        - partner_understood (int 1-5)
        - partner_adapted (int 1-5)
        - collaboration_improved (int 1-5)
        - partner_comment (str)
    Or None if generation fails.
    """
    import logging

    client = _get_ai_client()
    if client is None:
        logging.warning("[AI_PERCEPTIONS] No OpenAI client available")
        return None

    try:
        # Gather complete chat history across all rounds
        all_messages = []

        # Get all rounds for this participant
        participant = player.participant
        all_players = participant.get_players()

        for round_player in all_players:
            round_num = round_player.round_number

            # Get human messages for this round
            try:
                grid_messages = getattr(round_player, 'grid_messages', None) or "[]"
                human_msgs = json.loads(grid_messages)
                for msg in human_msgs:
                    if isinstance(msg, dict):
                        msg["round"] = round_num
                        all_messages.append(msg)
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

            # Get AI messages for this round
            try:
                ai_msgs = json.loads(round_player.group.ai_messages or "[]")
                for msg in ai_msgs:
                    if isinstance(msg, dict):
                        msg["round"] = round_num
                        all_messages.append(msg)
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

        # Sort all messages by timestamp
        def _ts_key(m):
            return (
                m.get("round", 0),
                m.get("server_ts") or m.get("timestamp") or "",
            )

        all_messages.sort(key=_ts_key)

        if not all_messages:
            logging.warning("[AI_PERCEPTIONS] No messages found in history")
            return None

        # Format conversation history for the AI
        human_role = (
            player.field_maybe_none("player_role") or player.participant.vars.get("role")
        )
        ai_role = "matcher" if human_role == "director" else "director"

        conversation_text = f"Your role in the task was: {ai_role.upper()}\n"
        conversation_text += f"Your human partner's role was: {human_role.upper()}\n\n"
        conversation_text += "=== COMPLETE CONVERSATION HISTORY ===\n\n"

        current_round = 0
        for msg in all_messages:
            msg_round = msg.get("round", 0)
            if msg_round != current_round:
                current_round = msg_round
                conversation_text += f"\n--- Round {current_round} ---\n\n"

            sender = msg.get("sender_role", "unknown")
            text = msg.get("text", "")
            if text:
                # Label messages clearly
                if sender == ai_role:
                    label = f"YOU ({ai_role})"
                elif sender == human_role:
                    label = f"HUMAN PARTNER ({human_role})"
                else:
                    label = sender.upper()
                conversation_text += f"{label}: {text}\n"

        # Build the prompt
        messages = [
            {"role": "system", "content": AI_PARTNER_PERCEPTION_PROMPT},
            {"role": "user", "content": conversation_text},
        ]

        # Call the API with model-specific parameters
        perception_params = _build_model_params(player)
        perception_params["messages"] = messages
        
        # Reasoning models (o1, o3) use max_completion_tokens instead of max_tokens
        if _is_reasoning_model(_get_ai_model(player)):
            perception_params["max_completion_tokens"] = 500
        else:
            perception_params["max_tokens"] = 500
        
        response = client.chat.completions.create(**perception_params)

        reply = response.choices[0].message.content
        if not reply:
            logging.warning("[AI_PERCEPTIONS] Empty response from API")
            return None

        # Parse JSON response
        reply = reply.strip()

        # Extract JSON from markdown code blocks if present
        if "```json" in reply:
            start = reply.find("```json") + 7
            end = reply.find("```", start)
            if end > start:
                reply = reply[start:end].strip()
        elif "```" in reply:
            start = reply.find("```") + 3
            end = reply.find("```", start)
            if end > start:
                reply = reply[start:end].strip()

        perceptions = json.loads(reply)

        # Validate and clamp values
        result = {}
        for key in ["partner_capable", "partner_helpful", "partner_understood", "partner_adapted", "collaboration_improved"]:
            val = perceptions.get(key)
            if isinstance(val, (int, float)):
                result[key] = max(1, min(5, int(val)))
            else:
                result[key] = 3  # Default to neutral if missing

        result["partner_comment"] = str(perceptions.get("partner_comment", ""))[:2000]

        # Store in the group
        group = player.group
        group.ai_partner_capable = result["partner_capable"]
        group.ai_partner_helpful = result["partner_helpful"]
        group.ai_partner_understood = result["partner_understood"]
        group.ai_partner_adapted = result["partner_adapted"]
        group.ai_collaboration_improved = result["collaboration_improved"]
        group.ai_partner_comment = result["partner_comment"]
        group.ai_partner_perceptions_raw = json.dumps(perceptions)

        logging.info("[AI_PERCEPTIONS] Generated perceptions: %s", result)
        return result

    except Exception as e:
        import traceback
        logging.error(
            "[AI_PERCEPTIONS] Error generating perceptions: %s: %s\n%s",
            type(e).__name__, e, traceback.format_exc()
        )
        return None



