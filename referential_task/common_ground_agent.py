from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, List
from referential_task.ai_utils import _get_ai_client


def _common_ground_session_key(ai_role: str) -> str:
    return f"{ai_role}_common_ground"


def _normalize_common_ground_state(raw_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    raw_state = raw_state or {}
    agreed_terms_by_image = raw_state.get("agreed_terms_by_image", {})
    uncertainties = raw_state.get("uncertainties", [])
    return {
        "agreed_terms_by_image": dict(agreed_terms_by_image) if isinstance(agreed_terms_by_image, dict) else {},
        "partner_beliefs": raw_state.get("partner_beliefs", "") or "",
        "uncertainties": list(uncertainties) if isinstance(uncertainties, list) else [],
        "current_target_position": raw_state.get("current_target_position"),
        "last_updated_round": raw_state.get("last_updated_round"),
    }


def _project_agreed_terms_to_current_round(
    player: Any, agreed_terms_by_image: Dict[str, List[str]] | None
) -> Dict[str, List[str]]:
    agreed_terms_by_image = agreed_terms_by_image or {}
    try:
        shared_grid = json.loads(getattr(player.group, "shared_grid", "[]") or "[]")
    except Exception:
        shared_grid = []

    if not shared_grid:
        return {}

    projected: Dict[str, List[str]] = {}
    for idx, slot in enumerate(shared_grid):
        image_path = slot.get("image", "")
        if image_path in agreed_terms_by_image:
            projected[str(idx + 1)] = agreed_terms_by_image[image_path]
    return projected


def format_common_ground_summary(common_ground: Dict[str, Any] | None) -> str:
    """Render structured common-ground state into the prompt summary block."""
    common_ground = common_ground or {}
    return (
        "=== YOUR CURRENT COMMON GROUND (INTERNAL STATE) ===\n"
        f"Agreed Terms: {json.dumps(common_ground.get('agreed_terms_per_position', {}), indent=2)}\n"
        f"Current Target Position: {common_ground.get('current_target_position')}\n"
        f"Your Uncertainties: {json.dumps(common_ground.get('uncertainties', []))}\n"
        f"Your Belief About Partner: {common_ground.get('partner_beliefs', '')}\n"
        "==================================================="
    )

def extract_common_ground(player: Any, history_messages: List[Dict[str, Any]], ai_role: str) -> tuple:
    """
    Calls a smaller/faster LLM to extract the current common ground state.
    Uses separate prompts for Director and Matcher to accurately model their distinct perspectives.

    Returns:
        A tuple of (formatted_summary: str, raw_parsed: dict | None).
        The formatted_summary is injected into the conversational LLM's prompt.
        The raw_parsed dict contains the extractor's structured output for data logging.
    """
    client = _get_ai_client()
    if not client or not history_messages:
        return "No history available yet.", None

    history_text = ""
    for msg in history_messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            content = " ".join(text_parts)
        history_text += f"{role}: {content}\n"

    if ai_role == "director":
        system_prompt = (
            "You are the internal Common Ground Tracking agent for the DIRECTOR in a referential matching game.\n"
            "Your job is to analyze the dialogue history and determine what you (the Director) believe the Matcher has successfully understood.\n\n"
            "RULES:\n"
            "1. ONLY extract a nickname if the Matcher CONFIRMED placement (said 'Placed', 'Done', 'Got it', etc.).\n"
            "2. The nickname should be the MINIMUM DISCRIMINATING phrase you used that the Matcher accepted.\n"
            "3. UNIQUENESS: Every nickname must be unambiguous across the whole set.\n"
            "4. Track what you believe the Matcher currently thinks about your descriptions.\n\n"
            "Respond strictly in JSON with this schema:\n"
            "{\n"
            '  "agreed_terms_per_position": {"1": ["duck basket"], "2": ["dark gray-brown rounded"], ...},\n'
            '  "current_target_position": <integer or null>,\n'
            '  "uncertainties": ["<list of any current confusions, debates, or ambiguities you perceive from the Matcher>"],\n'
            '  "partner_beliefs": "<summary of what you believe the MATCHER currently thinks>"\n'
            "}"
        )
    else:
        system_prompt = (
            "You are the internal Common Ground Tracking agent for the MATCHER in a referential matching game.\n"
            "Your job is to analyze the dialogue history and determine what you (the Matcher) believe the Director means by their descriptions.\n\n"
            "RULES:\n"
            "1. ONLY extract a nickname if YOU (the Matcher) CONFIRMED placement (said 'Placed', 'Done', 'Got it', etc.).\n"
            "2. The nickname should be the MINIMUM DISCRIMINATING phrase from the Director's description that you used to successfully identify the basket.\n"
            "3. UNIQUENESS: Every nickname must be unambiguous across the whole set.\n"
            "4. Track what you believe the Director is currently intending.\n\n"
            "Respond strictly in JSON with this schema:\n"
            "{\n"
            '  "agreed_terms_per_position": {"1": ["duck basket"], "2": ["dark gray-brown rounded"], ...},\n'
            '  "current_target_position": <integer or null>,\n'
            '  "uncertainties": ["<list of any current confusions, debates, or ambiguities you are experiencing>"],\n'
            '  "partner_beliefs": "<summary of what you believe the DIRECTOR is currently intending>"\n'
            "}"
        )

    try:
        extractor_model = os.environ.get("AI_EXTRACTOR_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=extractor_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Dialogue History:\n{history_text}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        raw_json = response.choices[0].message.content
        parsed = json.loads(raw_json)
        formatted_summary = format_common_ground_summary(parsed)
        logging.info(f"[CG_AGENT_{ai_role.upper()}] Extractor Output:\n{formatted_summary}")
        return formatted_summary, parsed
    except Exception as e:
        logging.error(f"[CG_AGENT_{ai_role.upper()}] Extraction failed: {e}")
        return "Common ground extraction failed.", None


def load_persistent_common_ground(player: Any, ai_role: str) -> Dict[str, Any]:
    """Load the persistent per-role common-ground memory from session config."""
    key = _common_ground_session_key(ai_role)
    raw_state = player.session.config.get(key, {})
    state = _normalize_common_ground_state(raw_state)

    # Bootstrap from the shared conceptual pact map if the role-specific store
    # does not yet have any image-linked nicknames.
    if not state["agreed_terms_by_image"]:
        pact_map = player.session.config.get("conceptual_pacts", {})
        if isinstance(pact_map, dict):
            state["agreed_terms_by_image"] = dict(pact_map)

    return state


def save_persistent_common_ground(player: Any, ai_role: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Persist the per-role common-ground memory into session config."""
    normalized = _normalize_common_ground_state(state)
    player.session.config[_common_ground_session_key(ai_role)] = normalized
    return normalized


def update_persistent_common_ground(
    player: Any,
    ai_role: str,
    current_cg: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Update the persistent per-role memory with the latest extracted state."""
    state = load_persistent_common_ground(player, ai_role)
    current_cg = current_cg or {}

    agreed_terms = current_cg.get("agreed_terms_per_position", {})
    if isinstance(agreed_terms, dict):
        try:
            shared_grid = json.loads(getattr(player.group, "shared_grid", "[]") or "[]")
        except Exception:
            shared_grid = []

        for pos_str, nicknames in agreed_terms.items():
            try:
                slot_idx = int(pos_str) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= slot_idx < len(shared_grid) and nicknames:
                image_path = shared_grid[slot_idx].get("image", "")
                if image_path:
                    state["agreed_terms_by_image"][image_path] = nicknames

    if "partner_beliefs" in current_cg:
        state["partner_beliefs"] = current_cg.get("partner_beliefs", "") or ""
    if "uncertainties" in current_cg:
        uncertainties = current_cg.get("uncertainties", [])
        state["uncertainties"] = list(uncertainties) if isinstance(uncertainties, list) else []
    if "current_target_position" in current_cg:
        state["current_target_position"] = current_cg.get("current_target_position")

    state["last_updated_round"] = getattr(player, "round_number", None)
    return save_persistent_common_ground(player, ai_role, state)


def build_persistent_common_ground_for_prompt(
    player: Any,
    ai_role: str,
    current_cg: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the current prompt-facing summary from persistent per-role memory."""
    state = update_persistent_common_ground(player, ai_role, current_cg)
    projected_terms = _project_agreed_terms_to_current_round(player, state.get("agreed_terms_by_image"))

    current_cg = current_cg or {}
    if current_cg:
        partner_beliefs = current_cg.get("partner_beliefs", "") or state.get("partner_beliefs", "")
        uncertainties = current_cg.get("uncertainties", [])
        if not isinstance(uncertainties, list):
            uncertainties = state.get("uncertainties", [])
        current_target_position = current_cg.get("current_target_position")
    else:
        partner_beliefs = (
            "You and your partner have established shared nicknames in earlier rounds. "
            "Reuse the agreed terms below for the same basket images in this round."
            if projected_terms else state.get("partner_beliefs", "")
        )
        uncertainties = []
        current_target_position = None

    return {
        "agreed_terms_per_position": projected_terms,
        "current_target_position": current_target_position,
        "uncertainties": uncertainties,
        "partner_beliefs": partner_beliefs,
        "memory_source": "persistent_per_role",
        "last_updated_round": state.get("last_updated_round"),
    }


def build_conceptual_pact_map(player: Any) -> Dict[str, List[str]]:
    """Build an image_path → nicknames mapping from a completed round's CG + shared_grid.

    Called once at round boundaries (after a round completes) to persist
    agreed-upon nicknames across rounds. The mapping is keyed by basket image
    path so that it remains valid even when basket positions are reshuffled.

    The result is stored on ``player.session.config["conceptual_pacts"]``,
    merging with (and overwriting) any existing pacts from earlier rounds.

    Returns the updated pact map.
    """
    from referential_task.ai_utils import _build_ai_messages_from_history

    # --- 1. Extract CG from the completed round's dialogue ---
    try:
        ai_msgs = json.loads(getattr(player.group, "ai_messages", "[]") or "[]")
    except Exception:
        ai_msgs = []

    if not ai_msgs:
        logging.info("[CG_PACT_MAP] No messages to extract pacts from.")
        return player.session.config.get("conceptual_pacts", {})

    # Build chat-format messages (the CG agent expects this format)
    history_messages = _build_ai_messages_from_history(player, ai_msgs)

    # Run the CG extraction (using a neutral "director" perspective for the summary)
    client = _get_ai_client()
    if not client or not history_messages:
        return player.session.config.get("conceptual_pacts", {})

    history_text = ""
    for msg in history_messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            content = " ".join(text_parts)
        history_text += f"{role}: {content}\n"

    system_prompt = (
        "You are analyzing a completed round of a referential matching game to extract agreed nicknames.\n\n"
        "RULES:\n"
        "1. ONLY extract a nickname if the Matcher CONFIRMED placement (said 'Placed', 'Done', 'Got it', etc.).\n"
        "2. The nickname should be the MINIMUM DISCRIMINATING phrase that was agreed upon.\n"
        "3. UNIQUENESS: Every nickname must be unambiguous across the whole set.\n\n"
        "Respond strictly in JSON with this schema:\n"
        "{\n"
        '  "agreed_terms_per_position": {"1": ["duck basket"], "2": ["dark gray-brown rounded"], ...}\n'
        "}"
    )

    agreed_terms = {}
    try:
        extractor_model = os.environ.get("AI_EXTRACTOR_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=extractor_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Dialogue History:\n{history_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw_json = response.choices[0].message.content
        parsed = json.loads(raw_json)
        agreed_terms = parsed.get("agreed_terms_per_position", {})
    except Exception as e:
        logging.error(f"[CG_PACT_MAP] Extraction failed: {e}")
        return player.session.config.get("conceptual_pacts", {})

    # --- 2. Map position-keyed nicknames to image paths ---
    try:
        shared_grid = json.loads(getattr(player.group, "shared_grid", "[]") or "[]")
    except Exception:
        shared_grid = []

    # Existing pacts from earlier rounds (if any)
    pact_map: Dict[str, List[str]] = dict(player.session.config.get("conceptual_pacts", {}))

    for pos_str, nicknames in agreed_terms.items():
        try:
            pos_int = int(pos_str)
        except (TypeError, ValueError):
            continue
        slot_idx = pos_int - 1
        if 0 <= slot_idx < len(shared_grid):
            image_path = shared_grid[slot_idx].get("image", "")
            if image_path and nicknames:
                # Overwrite with latest agreed terms (most recent entrainment wins)
                pact_map[image_path] = nicknames

    # --- 3. Store on session.config for cross-round persistence ---
    player.session.config["conceptual_pacts"] = pact_map

    round_num = getattr(player, "round_number", "?")
    logging.info(
        f"[CG_PACT_MAP] Built pact map after Round {round_num}: "
        f"{len(pact_map)} baskets with nicknames"
    )
    return pact_map


def get_pacts_by_position_for_current_round(player: Any) -> Dict[str, List[str]]:
    """Return stored conceptual pacts re-keyed to the current round's positions."""
    pact_map = player.session.config.get("conceptual_pacts", {})
    if not isinstance(pact_map, dict):
        return {}
    return _project_agreed_terms_to_current_round(player, pact_map)


def get_pacts_for_current_round(player: Any) -> str:
    """Look up stored conceptual pacts and re-key them to the current round's positions.

    Reads ``session.config["conceptual_pacts"]`` (image_path → nicknames) and
    the current round's ``shared_grid`` (position → image_path) to produce a
    summary of previously-established nicknames keyed by the current positions.

    Returns a formatted string suitable for inclusion in the CG summary block.
    Returns an empty string if no pacts are available.
    """
    pacts_by_position = get_pacts_by_position_for_current_round(player)

    if not pacts_by_position:
        return ""

    formatted = (
        "=== PREVIOUSLY ESTABLISHED NICKNAMES ===\n"
        "These nicknames were agreed upon in earlier rounds.\n"
        "The same baskets appear in this round but may be in DIFFERENT positions.\n"
        f"Nicknames by current position: {json.dumps(pacts_by_position, indent=2)}\n"
        "========================================"
    )
    return formatted
