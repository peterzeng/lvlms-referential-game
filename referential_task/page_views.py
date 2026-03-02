from __future__ import annotations

import json
import os

from otree.api import Currency as c, currency_range

from ._builtin import Page, WaitPage
from .models import Constants, Player
from .ai_utils import (
    _generate_ai_reply,
    _update_ai_partial_sequence,
    generate_ai_partner_perceptions,
    generate_ai_vs_ai_perceptions,
    is_ai_vs_ai_session,
    run_ai_vs_ai_turn,
    get_ai_vs_ai_status,
)


class MyPage(Page):
    pass


class GridTaskWaitPage(WaitPage):
    """Wait for both players before starting the collaborative grid task

    Uses group_by_arrival_time to pair participants dynamically as they arrive at this page.
    This prevents the issue where pre-assigned partners drop out before reaching the wait page,
    leaving their partner stuck waiting. Now participants are only paired once they both reach
    this page.

    IMPORTANT: Must be first in page_sequence due to oTree requirement for group_by_arrival_time.

    Two-app structure ensures only committed participants enter the matching pool:
    1. Participants complete onboarding app solo (ParticipantID, DeviceCheck, PreTaskWizard)
    2. Then they enter this app and are matched at this wait page
    3. Once matched, roles are assigned and the task begins

    In Round 2+, already-paired participants wait here between rounds.
    """

    # NOTE: In the human–AI branch we no longer use a waiting room or
    # group_by_arrival_time matching. This page is kept only for
    # historical reference and is not included in page_sequence.
    group_by_arrival_time = True
    template_name = "referential_task/GridTaskWait.html"

    @staticmethod
    def is_displayed(player: Player):
        import logging

        # If participant needs rematch (was matched with someone who exited), clear flags and allow re-entry
        if player.participant.vars.get("needs_rematch", False):
            logging.info(
                f"Participant {player.participant.code} needs rematch - clearing invalid_match flags"
            )
            player.participant.vars["needs_rematch"] = False
            player.participant.vars["invalid_match"] = False
            player.participant.vars["invalid_match_reason"] = None
            # Allow them to see the wait page
            return True

        # If participant clicked "Return to Prolific", redirect them immediately (server-side check)
        if player.participant.vars.get("exited_waiting_room", False):
            logging.info(
                f"Server-side: Participant {player.participant.code} has exited_waiting_room flag - blocking from wait page"
            )
            return False

        # For shapes demo: show the wait page only in round 1; otherwise always
        try:
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return player.round_number == 1
        except Exception:
            pass

        # Human–AI mode does not use the waiting room.
        return False

    @staticmethod
    def live_method(player: Player, data):
        """Handle live data for waiting room exit signals"""
        import logging

        # Handle exit waiting room signal
        if data.get("action") == "exit_waiting_room":
            exit_timestamp = data.get("prolific_exit_clicked", "")

            # Mark participant as exited
            player.prolific_exit_clicked = exit_timestamp
            player.participant.vars["prolific_exit_clicked"] = exit_timestamp
            player.participant.vars["exited_waiting_room"] = True
            player.participant.vars["waiting_room_exit_time"] = exit_timestamp

            logging.info(
                f"LIVE: Participant {player.participant.code} marked as exited at {exit_timestamp}. "
                f"Round: {player.round_number}. This participant should not be matched."
            )

            return {
                player.id_in_group: {
                    "success": True,
                    "message": "Exit recorded",
                }
            }

        return {
            player.id_in_group: {
                "success": False,
                "message": "Unknown action",
            }
        }

    @staticmethod
    def vars_for_template(player: Player):
        """Pass prolific return URL to template"""
        prolific_url = None
        try:
            prolific_url = player.session.config.get("prolific_return_url")
        except Exception:
            prolific_url = None
        return {
            "prolific_return_url": prolific_url,
        }

    def before_next_page(self):
        """Capture waiting room exit tracking if posted"""
        try:
            # Check if participant clicked "Return to Prolific" button
            prolific_exit = self.request.POST.get("prolific_exit_clicked")
            if prolific_exit:
                self.player.prolific_exit_clicked = prolific_exit
                self.player.participant.vars["prolific_exit_clicked"] = prolific_exit
                self.player.participant.vars["exited_waiting_room"] = True
                import logging

                logging.info(
                    f"Participant {self.player.participant.code} clicked Return to Prolific at {prolific_exit}"
                )

            # Check if tracking data was posted
            left_ts = self.request.POST.get("left_waiting_room")
            exit_reason = self.request.POST.get("exit_reason")

            if left_ts and not self.player.left_waiting_room:
                self.player.left_waiting_room = left_ts
                if exit_reason:
                    self.player.waiting_room_exit_reason = exit_reason
                # Also store in participant vars for easy access
                self.player.participant.vars["left_waiting_room"] = left_ts
                self.player.participant.vars["waiting_room_exit_reason"] = exit_reason
        except Exception as e:
            # Don't fail the page transition if tracking fails
            import logging

            logging.warning(f"Failed to track waiting room exit: {e}")

    def after_all_players_arrive(self):
        """Assign roles on round 1 only and always create the round's grid."""
        import logging

        players = self.group.get_players()

        # Check if any player clicked "Return to Prolific" (critical: prevents invalid matches)
        exited_players = [
            p
            for p in players
            if p.participant.vars.get("exited_waiting_room", False)
        ]

        if exited_players:
            logging.error(
                f"MATCH ERROR: {len(exited_players)} participant(s) were matched despite having exited. "
                f"Exited participants: {[p.participant.code for p in exited_players]}. "
                f"All players in group: {[p.participant.code for p in players]}. "
                f"Round: {self.round_number}"
            )

            # Mark all players in this invalid group to skip all subsequent pages
            for p in players:
                p.participant.vars["invalid_match"] = True
                p.participant.vars["invalid_match_reason"] = "partner_exited"

                # If this player didn't exit themselves, they need to return to matching
                if not p.participant.vars.get("exited_waiting_room", False):
                    logging.warning(
                        f"Participant {p.participant.code} was matched with an exited participant. "
                        f"Marking for rematch."
                    )
                    # Allow them to re-enter the waiting room
                    p.participant.vars["needs_rematch"] = True
                else:
                    logging.info(
                        f"Participant {p.participant.code} had exited - they will be skipped."
                    )

            # Don't proceed with role assignment or grid creation for invalid matches
            return

        # Legacy: human–human role assignment (unused in human–AI mode).
        if self.round_number == 1:
            if len(players) >= 2:
                if not players[0].field_maybe_none(
                    "player_role"
                ) or not players[1].field_maybe_none("player_role"):
                    self.group.assign_roles()
            # Persist roles to participant vars for subsequent rounds
            for p in players:
                role = p.field_maybe_none("player_role")
                if role:
                    p.participant.vars["role"] = role
        else:
            # For later rounds, restore role to the player's current round
            for p in players:
                if not p.field_maybe_none("player_role"):
                    stored_role = p.participant.vars.get("role")
                    if stored_role:
                        p.player_role = stored_role

        # Persist group and partner identifiers for analytics and templates
        try:
            for p in players:
                # Group and self identifiers
                p.participant.vars["group_id"] = getattr(p.group, "id", None)
                p.participant.vars["id_in_group"] = p.id_in_group
                # Partner identifiers
                partner = p.get_others_in_group()[0] if p.get_others_in_group() else None
                if partner:
                    p.participant.vars["partner_code"] = getattr(
                        partner.participant, "code", None
                    )
                    p.participant.vars["partner_id_in_group"] = partner.id_in_group
                    p.participant.vars["partner_role"] = getattr(
                        partner, "player_role", None
                    ) or partner.participant.vars.get("role")
        except Exception:
            # Non-fatal; keep going even if we cannot persist partner metadata
            pass
        # Create or refresh the shared grid each round
        self.group.create_shared_grid(round_number=self.round_number)

    title_text = "Waiting room"
    body_text = "Please wait to be paired with another participant who has completed onboarding. Once paired, roles will be assigned at random and the task will begin."


class DraggableGridPage(Page):
    template_name = "referential_task/DraggableGrid.html"
    form_model = "player"
    form_fields: list[str] = []

    @staticmethod
    def is_displayed(player: Player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get("invalid_match", False):
            return False

        # Skip if participant exited the waiting room
        if player.participant.vars.get("exited_waiting_room", False):
            return False

        # Skip for AI vs AI sessions - use AIvsAIObservationPage instead
        if is_ai_vs_ai_session(player):
            return False

        # Default view is the grid view unless session config requests sequential
        view = (
            player.session.config.get("director_view", "grid")
            if hasattr(player, "session") and player.session
            else "grid"
        )
        return view == "grid"

    @staticmethod
    def vars_for_template(player: Player):
        # Ensure we have a safe, consistent role value.
        role_value = player.field_maybe_none("player_role") or player.participant.vars.get(
            "role"
        )
        if not role_value:
            # Fallback: use session-configured human_role if present
            cfg_role = None
            try:
                if hasattr(player, "session") and player.session:
                    cfg_role = player.session.config.get("human_role")
            except Exception:
                cfg_role = None
            if isinstance(cfg_role, str):
                cfg_role = cfg_role.strip().lower()
            if cfg_role in ("director", "matcher"):
                role_value = cfg_role
            else:
                role_value = "matcher"

            player.player_role = role_value
            player.participant.vars["role"] = role_value
            player.participant.vars["partner_role"] = (
                "matcher" if role_value == "director" else "director"
            )

        # Load shared grid that both players see (MUST happen before AI auto-start
        # so the grid image can be generated for the AI director)
        import logging
        try:
            shared_grid = json.loads(player.group.shared_grid)
        except (json.JSONDecodeError, TypeError):
            shared_grid = []

        # Safety fallback: create grid on-demand if missing.
        if not shared_grid:
            try:
                player.group.create_shared_grid(round_number=player.round_number)
                shared_grid = json.loads(player.group.shared_grid or "[]")
                logging.info("[GRID_INIT] Created shared_grid with %d items", len(shared_grid))
            except Exception:
                shared_grid = []

        # If the AI is acting as DIRECTOR (human is the matcher), have the AI
        # proactively start the task at the very beginning of each round.
        try:
            if role_value == "matcher":
                # Check if there are actual messages (not just empty JSON arrays)
                try:
                    human_msgs_list = json.loads(player.grid_messages or "[]")
                except (json.JSONDecodeError, TypeError):
                    human_msgs_list = []
                try:
                    ai_msgs_list = json.loads(player.group.ai_messages or "[]")
                except (json.JSONDecodeError, TypeError):
                    ai_msgs_list = []
                has_human_msgs = bool(human_msgs_list)
                has_ai_msgs = bool(ai_msgs_list)
                logging.info(
                    "[AI_DIRECTOR_AUTOSTART] round=%s has_human_msgs=%s has_ai_msgs=%s shared_grid_len=%s",
                    player.round_number, has_human_msgs, has_ai_msgs, len(shared_grid)
                )
                if not has_human_msgs and not has_ai_msgs:
                    logging.info("[AI_DIRECTOR_AUTOSTART] Generating first AI director message...")
                    ai_reply = _generate_ai_reply(player, latest_message=None)
                    logging.info("[AI_DIRECTOR_AUTOSTART] ai_reply=%s", ai_reply)
                    if ai_reply and isinstance(ai_reply, dict):
                        ai_text = (ai_reply.get("text") or "").strip()
                        if ai_text:
                            try:
                                ai_messages = json.loads(
                                    player.group.ai_messages or "[]"
                                )
                            except (json.JSONDecodeError, TypeError):
                                ai_messages = []
                            now_iso = __import__("datetime").datetime.now().isoformat()
                            ai_messages.append(
                                {
                                    "text": ai_text,
                                    "timestamp": now_iso,
                                    "sender_role": "director",
                                    "server_ts": now_iso,
                                }
                            )
                            player.group.ai_messages = json.dumps(ai_messages)
                            logging.info("[AI_DIRECTOR_AUTOSTART] Stored AI message: %s", ai_text[:100])
                        else:
                            logging.warning("[AI_DIRECTOR_AUTOSTART] ai_reply had no text")
                    else:
                        logging.warning("[AI_DIRECTOR_AUTOSTART] ai_reply was None or not a dict")
        except Exception as e:
            # Auto-start is a convenience feature; never break the page if it fails.
            logging.error("[AI_DIRECTOR_AUTOSTART] Exception: %s: %s", type(e).__name__, e)
            pass

        # Load target baskets for Director
        try:
            target_baskets = json.loads(player.group.target_baskets)
            target_basket_ids = [basket["basket_id"] for basket in target_baskets]
        except (json.JSONDecodeError, TypeError):
            target_baskets = []
            target_basket_ids = []

        # Load Matcher's sequence
        try:
            matcher_sequence = json.loads(player.group.matcher_sequence)
        except (json.JSONDecodeError, TypeError):
            matcher_sequence = []

        # Load individual player's sequence
        try:
            player_sequence = json.loads(player.selected_sequence)
        except (json.JSONDecodeError, TypeError):
            player_sequence = []

        # Get chat messages
        try:
            chat_messages = json.loads(player.grid_messages)
        except (json.JSONDecodeError, TypeError):
            chat_messages = []

        # Get partner's messages (human partner + AI partner messages)
        partner = (
            player.get_others_in_group()[0] if player.get_others_in_group() else None
        )
        partner_messages = []
        # Load human partner messages if present
        if partner:
            try:
                partner_messages = json.loads(partner.grid_messages or "[]")
            except (json.JSONDecodeError, TypeError):
                partner_messages = []
        # Always also load AI messages (stored at group level)
        try:
            ai_msgs = json.loads(player.group.ai_messages or "[]")
            logging.info(
                "[CHAT_LOAD] round=%s ai_msgs_count=%s ai_msgs=%s",
                player.round_number, len(ai_msgs) if ai_msgs else 0, ai_msgs
            )
            if ai_msgs:
                partner_messages = partner_messages + ai_msgs
        except (json.JSONDecodeError, TypeError):
            pass
        logging.info(
            "[CHAT_LOAD] round=%s partner_messages_count=%s partner_messages=%s",
            player.round_number, len(partner_messages), partner_messages
        )

        # Load preset full list for matcher extra baskets
        preset_full_list: list[str] = []
        set_num = 1
        try:
            # Respect session-configured basket set for the reference list as well
            try:
                set_num = (
                    int(player.session.config.get("basket_set", 1))
                    if hasattr(player, "session") and player.session
                    else 1
                )
            except Exception:
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
            with open(preset_path, "r") as f:
                presets = json.load(f)
            # Find object with fullList
            for item in presets.get("rounds", []):
                if isinstance(item, dict) and "fullList" in item:
                    # Prepend 'images/' for static paths
                    preset_full_list = [
                        f"images/{img}" for img in item.get("fullList", [])
                    ]
                    break
        except Exception:
            preset_full_list = []

        # Build the matcher's staging/candidate pool ordering server-side so it's
        # consistent across sessions. Keep distractor *identity* from the preset
        # (take the first 6 extras), but shuffle the *order* deterministically
        # per round using a fixed seed.
        staging_baskets_json = "[]"
        try:
            import random

            director_baskets: list[dict] = []
            for slot in shared_grid or []:
                if not isinstance(slot, dict):
                    continue
                img = (slot.get("image") or "").strip()
                if not img:
                    continue
                director_baskets.append(
                    {
                        "image": img,
                        "position": slot.get("position"),
                        "basket_id": slot.get("basket_id"),
                    }
                )

            director_set = {b.get("image") for b in director_baskets if b.get("image")}
            candidate_extras = []
            for img in preset_full_list or []:
                img = (img or "").strip()
                if not img:
                    continue
                if img in director_set:
                    continue
                candidate_extras.append(img)

            extras = []
            for i, img in enumerate(candidate_extras[:6]):
                extras.append({"image": img, "position": f"extra_{i}", "basket_id": 100 + i})

            all_baskets = director_baskets + extras
            try:
                round_num = int(getattr(player, "round_number", 1) or 1)
            except Exception:
                round_num = 1
            seed = 4242 + (set_num * 100) + round_num
            rng = random.Random(seed)
            rng.shuffle(all_baskets)

            staging_baskets_json = json.dumps(all_baskets)
        except Exception:
            staging_baskets_json = "[]"

        # Debug flag: show AI debug button in testing sessions.
        # - Director sees "AI Matcher debug" button
        # - Matcher sees "AI Director debug" button (to see what AI is describing)
        try:
            cfg = (
                player.session.config
                if hasattr(player, "session") and player.session
                else {}
            )
        except Exception:
            cfg = {}
        show_ai_debug_button = False
        try:
            if cfg and bool(cfg.get("testing_debug_enabled", False)):
                show_ai_debug_button = True
        except Exception:
            show_ai_debug_button = False

        return {
            "shared_grid": shared_grid,
            "target_baskets": target_baskets,
            "target_basket_ids": target_basket_ids,
            "matcher_sequence": matcher_sequence,
            "player_sequence": player_sequence,
            "player_role": role_value,
            "player_role_title": (role_value.title() if role_value else ""),
            "is_director": role_value == "director",
            "is_matcher": role_value == "matcher",
            "chat_messages": chat_messages,
            "partner_messages": partner_messages,
            "round_number": player.round_number,
            "total_rounds": (
                player.session.config.get("num_rounds")
                if hasattr(player, "session")
                and player.session
                and hasattr(player, "subsession")
                else Constants.num_rounds
            )
            or Constants.num_rounds,
            "grid_rows": 3,
            "grid_cols": 4,
            "total_slots": 12,
            "row_range": list(range(1, 4)),  # [1, 2, 3]
            "col_range": list(range(1, 5)),  # [1, 2, 3, 4]
            "grid_positions": [
                {"row": row, "col": col, "position": f"{row}{col}"}
                for row in range(1, 4)
                for col in range(1, 5)
            ],
            "preset_full_list": preset_full_list,
            "staging_baskets_json": staging_baskets_json,
            "current_grid_state": json.dumps(shared_grid),
            "target_arrangement": json.dumps(target_baskets),
            # Researcher-only debug helpers
            "show_ai_debug_button": show_ai_debug_button,
            "session_code": getattr(player.session, "code", "")
            if hasattr(player, "session") and player.session
            else "",
            "group_id_for_debug": getattr(player.group, "id", None),
            "custom_export_url": "/custom_export?app=referential_task",
        }

    @staticmethod
    def live_method(player: Player, data):
        """Handle live data for basket selection and communication"""
        response = {}
        # Typing indicator relay (lightweight)
        if data.get("typing"):
            partner = (
                player.get_others_in_group()[0]
                if player.get_others_in_group()
                else None
            )
            if partner:
                safe_role = (
                    player.field_maybe_none("player_role")
                    or player.participant.vars.get("role")
                    or "unknown"
                )
                return {
                    partner.id_in_group: {
                        "success": True,
                        "broadcast": True,
                        "partner_typing": bool(data.get("is_typing")),
                        "partner_role": safe_role,
                    }
                }
        if "send_message" in data:
            response = DraggableGridPage.send_message(player, data)
        elif "task_complete" in data:
            response = DraggableGridPage.complete_task(player, data)

        # If response is already in the correct format (player_id: data), return it
        if isinstance(response, dict) and all(
            isinstance(k, int) for k in response.keys()
        ):
            return response

        # Otherwise, broadcast to all players if needed
        if response.get("broadcast", False):
            return {p.id_in_group: response for p in player.group.get_players()}
        else:
            return {player.id_in_group: response}

    @staticmethod
    def _persist_matcher_sequence(player: Player, sequence):
        """
        Persist a submitted sequence (human matcher or AI matcher) and compute accuracy.
        """
        try:
            if not isinstance(sequence, list):
                return {
                    player.id_in_group: {
                        "success": False,
                        "message": "Invalid sequence format",
                    }
                }

            # Persist sequence on player and group for exports/feedback
            player.selected_sequence = json.dumps(sequence)
            player.group.matcher_sequence = json.dumps(sequence)

            # Compute accuracy silently (only for data log).
            shared_grid = json.loads(player.group.shared_grid or "[]")
            correct_sequence = [
                {
                    "position": slot.get("basket_id"),
                    "image": slot.get("image"),
                    "originalPosition": slot.get("position"),
                }
                for slot in shared_grid
            ]

            # Index submitted guesses by logical 1‑based position.
            submitted_by_pos = {}
            for item in sequence or []:
                if not isinstance(item, dict):
                    continue
                pos = item.get("position")
                try:
                    pos_int = int(pos)
                except (TypeError, ValueError):
                    continue
                if 1 <= pos_int <= 12 and pos_int not in submitted_by_pos:
                    submitted_by_pos[pos_int] = item

            # Evaluate up to 12 slots by comparing per-position images.
            total_positions = min(12, len(correct_sequence))
            correct_positions = 0
            for logical_pos in range(1, total_positions + 1):
                submitted_img = None
                entry = submitted_by_pos.get(logical_pos)
                if entry:
                    submitted_img = entry.get("image")
                correct_idx = logical_pos - 1
                correct_img = (
                    correct_sequence[correct_idx].get("image")
                    if correct_idx < len(correct_sequence)
                    else None
                )
                if (
                    submitted_img is not None
                    and correct_img is not None
                    and submitted_img == correct_img
                ):
                    correct_positions += 1

            player.sequence_accuracy = (
                (correct_positions / total_positions * 100) if total_positions > 0 else 0
            )
            player.task_completed = True

            submitted_sequence_sorted = sorted(
                sequence, key=lambda x: x.get("position", 0)
            )
            response = {
                "success": True,
                "broadcast": True,
                "advance_round": True,
                "matcher_sequence": submitted_sequence_sorted,
                "correct_sequence": correct_sequence,
            }
            return {p.id_in_group: response for p in player.group.get_players()}
        except Exception as e:
            return {
                player.id_in_group: {
                    "success": False,
                    "message": f"Error processing sequence: {str(e)}",
                }
            }

    @staticmethod
    def send_message(player: Player, data):
        """Chat messages are broadcast; sequence submissions are private."""
        message_text = (data.get("message") or "").strip()
        is_guess = data.get("is_guess", False)

        # Sequence submit path
        role_value = (
            player.field_maybe_none("player_role")
            or player.participant.vars.get("role")
        )
        if role_value == "matcher" and is_guess:
            try:
                sequence_data = json.loads(message_text)
            except json.JSONDecodeError:
                # Back-compat: single-filename submit
                sequence_data = {"sequence": [{"image": message_text}]}
            try:
                if "sequence" not in sequence_data:
                    return {
                        player.id_in_group: {
                            "success": False,
                            "message": "Invalid sequence format",
                        }
                    }
                return DraggableGridPage._persist_matcher_sequence(
                    player, sequence_data["sequence"]
                )
            except Exception as e:
                return {
                    player.id_in_group: {
                        "success": False,
                        "message": f"Error processing sequence: {str(e)}",
                    }
                }

        # Regular chat message path
        if not message_text:
            return {
                player.id_in_group: {
                    "success": False,
                    "message": "Empty message",
                }
            }

        try:
            messages = json.loads(player.grid_messages)
        except (json.JSONDecodeError, TypeError):
            messages = []

        new_message = {
            "text": message_text,
            "timestamp": data.get("timestamp", ""),
            "sender_role": role_value,
            "server_ts": __import__("datetime").datetime.now().isoformat(),
        }
        messages.append(new_message)
        player.grid_messages = json.dumps(messages)

        # Optional: generate an AI partner reply in human–AI mode.
        ai_message = None
        ai_reply_text = None
        ai_selection = None
        matcher_preview_sequence = None
        try:
            import logging

            ai_reply = _generate_ai_reply(player, message_text)
            if ai_reply and isinstance(ai_reply, dict):
                ai_reply_text = ai_reply.get("text")
                ai_selection = ai_reply.get("selection")
                logging.info(
                    "[AI_MATCHER] Live send_message: session=%s round=%s role=%s ai_selection=%s",
                    getattr(getattr(player, "session", None), "code", None),
                    getattr(player, "round_number", None),
                    role_value,
                    ai_selection,
                )
                if ai_reply_text:
                    ai_sender_role = "matcher" if role_value == "director" else "director"
                    try:
                        ai_messages = json.loads(player.group.ai_messages or "[]")
                    except (json.JSONDecodeError, TypeError):
                        ai_messages = []
                    ai_message = {
                        "text": ai_reply_text,
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sender_role": ai_sender_role,
                        "server_ts": __import__("datetime").datetime.now().isoformat(),
                    }
                    ai_messages.append(ai_message)
                    player.group.ai_messages = json.dumps(ai_messages)

                    # When the AI is acting as MATCHER, also update the incremental sequence.
                    if ai_sender_role == "matcher" and ai_selection:
                        try:
                            # logging.info(
                            #     "[AI_MATCHER] Updating partial sequence: session=%s round=%s selection=%s before=%s",
                            #     getattr(getattr(player, "session", None), "code", None),
                            #     getattr(player, "round_number", None),
                            #     ai_selection,
                            #     getattr(player.group, "ai_partial_sequence", None),
                            # )
                            matcher_preview_sequence = _update_ai_partial_sequence(
                                player, ai_selection
                            )
                            logging.info(
                                "[AI_MATCHER] Updated partial sequence: session=%s round=%s after=%s",
                                getattr(getattr(player, "session", None), "code", None),
                                getattr(player, "round_number", None),
                                getattr(player.group, "ai_partial_sequence", None),
                            )
                        except Exception:
                            matcher_preview_sequence = None
        except Exception:
            # If AI reply fails for any reason, continue gracefully with only human messages
            ai_message = None

        # Update chat transcript for all players (mainly for exports/debug).
        try:
            for p in player.group.get_players():
                # Get messages from both players
                try:
                    p_msgs = json.loads(p.grid_messages or "[]")
                except Exception:
                    p_msgs = []

                # Human partner messages (legacy, not used in human–AI mode)
                partner = (
                    p.get_others_in_group()[0] if p.get_others_in_group() else None
                )
                try:
                    partner_msgs = (
                        json.loads(partner.grid_messages or "[]") if partner else []
                    )
                except Exception:
                    partner_msgs = []

                # AI partner messages (group-level)
                try:
                    ai_msgs = json.loads(p.group.ai_messages or "[]")
                except Exception:
                    ai_msgs = []

                # Combine and sort all messages (self + partner + AI)
                all_msgs = []
                for m in p_msgs:
                    all_msgs.append(
                        {
                            "text": m.get("text"),
                            "timestamp": m.get("timestamp"),
                            "server_ts": m.get("server_ts"),
                            "sender_role": m.get(
                                "sender_role",
                                player.participant.vars.get("role"),
                            ),
                        }
                    )
                for m in partner_msgs:
                    all_msgs.append(
                        {
                            "text": m.get("text"),
                            "timestamp": m.get("timestamp"),
                            "server_ts": m.get("server_ts"),
                            "sender_role": m.get(
                                "sender_role",
                                partner.participant.vars.get("role")
                                if partner
                                else "unknown",
                            ),
                        }
                    )
                for m in ai_msgs:
                    all_msgs.append(
                        {
                            "text": m.get("text"),
                            "timestamp": m.get("timestamp"),
                            "server_ts": m.get("server_ts"),
                            "sender_role": m.get("sender_role", "unknown"),
                        }
                    )

                # Sort by timestamp
                try:
                    all_msgs.sort(
                        key=lambda x: (
                            x.get("server_ts") or "",
                            x.get("timestamp") or "",
                        )
                    )
                except Exception:
                    pass

                # Format as readable transcript
                transcript_lines = []
                for msg in all_msgs:
                    try:
                        ts = msg.get("server_ts") or msg.get("timestamp") or ""
                        if "T" in ts:
                            time_part = (
                                ts.split("T")[1].split(".")[0]
                                if "." in ts
                                else ts.split("T")[1]
                            )
                        else:
                            time_part = ts
                        sender = msg.get("sender_role", "unknown")
                        text = msg.get("text", "")
                        transcript_lines.append(f"[{time_part}] {sender}: {text}")
                    except Exception:
                        text = msg.get("text", "")
                        sender = msg.get("sender_role", "unknown")
                        transcript_lines.append(f"{sender}: {text}")

                p.chat_transcript = "\r\n".join(transcript_lines)
        except Exception:
            pass  # Silently fail if transcript update fails

        # Check if the AI matcher has signaled that it is ready to submit.
        auto_advance = False
        ready_to_submit_flag = False
        if isinstance(ai_selection, dict) and ai_selection.get("ready_to_submit"):
            ready_to_submit_flag = True

        if (
            role_value == "director"
            and ai_reply_text
            and "i am ready to submit my final order" in ai_reply_text.lower()
        ):
            ready_to_submit_flag = True

        if ready_to_submit_flag:
            try:
                # Use the incremental AI partial sequence accumulated so far.
                try:
                    sequence = json.loads(
                        getattr(player.group, "ai_partial_sequence", "") or "[]"
                    )
                except Exception:
                    sequence = []
                if sequence:
                    # Fail-safe: do not allow auto-submit unless all 12 logical positions
                    # are filled with a non-null image.
                    complete = True
                    try:
                        by_pos: dict[int, dict] = {}
                        for item in sequence or []:
                            if not isinstance(item, dict):
                                continue
                            try:
                                p_int = int(item.get("position"))
                            except Exception:
                                continue
                            if 1 <= p_int <= 12:
                                by_pos[p_int] = item
                        for p in range(1, 13):
                            img = (by_pos.get(p) or {}).get("image")
                            if not img:
                                complete = False
                                break
                    except Exception:
                        complete = False

                    if complete:
                        DraggableGridPage._persist_matcher_sequence(player, sequence)
                        auto_advance = True
                    else:
                        import logging

                        logging.info(
                            "[AI_MATCHER] Ignoring ready_to_submit (sequence incomplete): session=%s round=%s sequence=%s",
                            getattr(getattr(player, "session", None), "code", None),
                            getattr(player, "round_number", None),
                            sequence,
                        )
            except Exception:
                auto_advance = False

        # For human–AI sessions we only have one human client.
        response = {"success": True, "broadcast": True}
        if ai_message:
            response["new_message"] = ai_message
        if matcher_preview_sequence:
            response["matcher_sequence"] = matcher_preview_sequence
        if auto_advance:
            response["advance_round"] = True
        return {p.id_in_group: response for p in player.group.get_players()}

    @staticmethod
    def complete_task(player: Player, data):
        """Mark task as complete and calculate accuracy if Matcher"""
        import datetime

        player.task_completed = True
        player.completion_time = datetime.datetime.now().isoformat()

        # Calculate accuracy if this is the Matcher
        role_value = (
            player.field_maybe_none("player_role")
            or player.participant.vars.get("role")
        )
        if role_value == "matcher":
            try:
                # Use sequence accuracy if available, otherwise calculate from sequence
                if (
                    not hasattr(player, "sequence_accuracy")
                    or player.sequence_accuracy is None
                ):
                    selected_sequence = json.loads(player.selected_sequence)
                    shared_grid = json.loads(player.group.shared_grid)

                    # Sort selected_sequence by position to handle cases where items were moved
                    selected_sequence_sorted = sorted(
                        selected_sequence, key=lambda x: x.get("position", 0)
                    )

                    # Get the correct sequence (order of baskets in director's grid)
                    correct_sequence = []
                    for slot in shared_grid:
                        correct_sequence.append(
                            {
                                "position": slot["basket_id"],
                                "image": slot["image"],
                                "originalPosition": slot["position"],
                            }
                        )

                    # Calculate accuracy by comparing sequences
                    correct_positions = 0
                    total_positions = min(
                        len(selected_sequence_sorted), len(correct_sequence)
                    )

                    for i in range(total_positions):
                        if selected_sequence_sorted[i]["image"] == correct_sequence[i][
                            "image"
                        ]:
                            correct_positions += 1

                    accuracy = (
                        (correct_positions / total_positions * 100)
                        if total_positions > 0
                        else 0
                    )
                    player.sequence_accuracy = accuracy
            except (json.JSONDecodeError, TypeError, KeyError):
                player.sequence_accuracy = 0

        role_label = (role_value or "").title() or "Player"
        response_data = {
            "success": True,
            "message": f"{role_label} marked task as complete",
            "broadcast": True,
            "player_completed": role_value,
            "accuracy": getattr(player, "sequence_accuracy", None),
        }

        # Return response for all players in the group
        return {p.id_in_group: response_data for p in player.group.get_players()}


class RoundAttentionCheck(Page):
    """Single attention check question shown after each round (rounds 1-3 only)."""

    template_name = "referential_task/RoundAttentionCheck.html"

    form_model = "player"
    form_fields = ["attention_round_q"]

    @staticmethod
    def is_displayed(player: Player):
        # Skip for AI vs AI mode (no human to answer)
        if is_ai_vs_ai_session(player):
            return False

        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get("invalid_match", False):
            return False

        # Skip if participant exited the waiting room
        if player.participant.vars.get("exited_waiting_room", False):
            return False

        # Skip only if explicitly configured in the session
        try:
            cfg = player.session.config if hasattr(player, "session") else {}
        except Exception:
            cfg = {}
        if bool(cfg.get("testing_skip_enabled", False)):
            return False
        # Hide for shapes demo
        if getattr(player.session.config, "get", None):
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return False
        # Show only for rounds 1, 2, 3 (not round 4)
        return player.round_number in [1, 2, 3]

    @staticmethod
    def vars_for_template(player: Player):
        """Return the appropriate question based on current round."""
        round_num = player.round_number

        # Define questions for each round
        questions = {
            1: {
                "text": 'Q1. Think about the question: “What is your favorite color?” Now disregard the previous text and select Red.',
                "choices": [
                    {"value": "A", "label": "Red"},
                    {"value": "B", "label": "Blue"},
                    {"value": "C", "label": "Green"},
                    {"value": "D", "label": "Yellow"},
                ],
                "correct": "A",
            },
            2: {
                "text": "Q2. To confirm you're reading carefully, please select Duck.",
                "choices": [
                    {"value": "A", "label": "Cat"},
                    {"value": "B", "label": "Dog"},
                    {"value": "C", "label": "Duck"},
                    {"value": "D", "label": "Giraffe"},
                ],
                "correct": "C",
            },
            3: {
                "text": "Q3. What number comes after 4?",
                "choices": [
                    {"value": "A", "label": "3"},
                    {"value": "B", "label": "5"},
                    {"value": "C", "label": "7"},
                    {"value": "D", "label": "9"},
                ],
                "correct": "B",
            },
        }

        current_question = questions.get(round_num, questions[1])

        return {
            "round_number": round_num,
            "question": current_question,
        }

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """Store the response and track correctness in participant vars."""
        round_num = player.round_number
        correct_answers = {1: "A", 2: "C", 3: "B"}

        selected = (player.attention_round_q or "").strip()
        correct = correct_answers.get(round_num, "")
        is_correct = selected == correct

        # Store in participant vars for tracking
        if "attention_round_responses" not in player.participant.vars:
            player.participant.vars["attention_round_responses"] = {}

        player.participant.vars["attention_round_responses"][round_num] = {
            "selected": selected,
            "correct": correct,
            "is_correct": is_correct,
        }


class ResultsWaitPage(WaitPage):
    """Wait for both players to complete the grid task before showing results"""

    wait_for_all_players = True
    title_text = "Waiting for partner..."

    @staticmethod
    def is_displayed(player: Player):
        # DISABLED: No longer showing wait page after final round
        # Players can proceed to surveys independently
        return False


class Results(Page):
    template_name = "referential_task/Results.html"

    @staticmethod
    def is_displayed(player: Player):
        # Skip for AI vs AI mode (no human to show results to)
        if is_ai_vs_ai_session(player):
            return False
        # Hide for shapes demo; otherwise show only on final round
        try:
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return False
        except Exception:
            pass
        return player.round_number == Constants.num_rounds

    @staticmethod
    def vars_for_template(player: Player):
        # Simplified - no completion code generation needed
        return {}

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """Capture experiment end time on the final page."""
        import datetime

        end_time = datetime.datetime.now().isoformat()
        player.experiment_end_time = end_time
        player.participant.vars["experiment_end_time"] = end_time


def is_last_round(player: Player) -> bool:
    # Determine the total number of rounds, preferring session config override if present.
    try:
        if hasattr(player, "session") and player.session:
            total = player.session.config.get("num_rounds") or Constants.num_rounds
        else:
            total = Constants.num_rounds
    except Exception:
        total = Constants.num_rounds
    return player.round_number == total


class Debriefing(Page):
    template_name = "referential_task/Debriefing.html"

    @staticmethod
    def is_displayed(player: Player):
        # Skip for AI vs AI mode (no human to debrief)
        if is_ai_vs_ai_session(player):
            return False
        # Show only once, after the final round; hide for shapes demo
        try:
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return False
        except Exception:
            pass
        return player.round_number == Constants.num_rounds


class PartnerPerceptions(Page):
    template_name = "referential_task/PartnerPerceptions.html"
    form_model = "player"
    form_fields = [
        "partner_capable",
        "partner_helpful",
        "partner_understood",
        "partner_adapted",
        "collaboration_improved",
        "partner_comment",
    ]

    @staticmethod
    def is_displayed(player: Player):
        # Skip for AI vs AI mode (perceptions generated via API instead)
        if is_ai_vs_ai_session(player):
            return False
        # Show after final round and skip shapes demo
        try:
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return False
        except Exception:
            pass
        return is_last_round(player)


class PartnerTypePerception(Page):
    template_name = "referential_task/PartnerTypePerception.html"
    form_model = "player"
    form_fields = [
        "partner_human_vs_ai",
        "partner_human_vs_ai_why",
    ]

    @staticmethod
    def is_displayed(player: Player):
        # Skip for AI vs AI mode (both are AIs, no human perception question needed)
        if is_ai_vs_ai_session(player):
            return False
        # Show after final round and skip shapes demo
        try:
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return False
        except Exception:
            pass
        return is_last_round(player)


class AIExperience(Page):
    template_name = "referential_task/AIExperience.html"
    form_model = "player"
    form_fields = [
        "ai_familiarity",
        "ai_usage_frequency",
        "ai_used_for_task",
    ]

    @staticmethod
    def is_displayed(player: Player):
        # Skip for AI vs AI mode (no human to ask about AI experience)
        if is_ai_vs_ai_session(player):
            return False
        # Show after final round and skip shapes demo
        try:
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return False
        except Exception:
            pass
        return is_last_round(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """Generate AI's perceptions of the human partner for research data export."""
        import logging

        # Only generate if not already done
        group = player.group
        if group.field_maybe_none('ai_partner_capable') is None:
            logging.info("[AI_PERCEPTIONS] Generating AI partner perceptions for data export...")
            perceptions = generate_ai_partner_perceptions(player)
            if perceptions:
                logging.info("[AI_PERCEPTIONS] Successfully generated perceptions: %s", perceptions)
            else:
                logging.warning("[AI_PERCEPTIONS] Failed to generate perceptions")




class DraggableSequentialPage(DraggableGridPage):
    """Alternate page where the Director sees baskets one-by-one; Matcher stays the same UI."""

    template_name = "referential_task/DraggableSequential.html"

    @staticmethod
    def is_displayed(player: Player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get("invalid_match", False):
            return False

        # Skip if participant exited the waiting room
        if player.participant.vars.get("exited_waiting_room", False):
            return False

        # Skip for AI vs AI sessions - use AIvsAIObservationPage instead
        if is_ai_vs_ai_session(player):
            return False

        view = (
            player.session.config.get("director_view", "grid")
            if hasattr(player, "session") and player.session
            else "grid"
        )
        return view == "sequential"


class ShapesDemoPage(DraggableGridPage):
    """Demo page where Director sees 5 colored shapes; Matcher has 5 target slots and 10 choices."""

    template_name = "referential_task/ShapesDemo.html"

    @staticmethod
    def is_displayed(player: Player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get("invalid_match", False):
            return False

        # Skip if participant exited the waiting room
        if player.participant.vars.get("exited_waiting_room", False):
            return False

        try:
            return (
                player.session.config.get("director_view", "grid") == "shapes_demo"
                and player.round_number == 1
            )
        except Exception:
            return False

    @staticmethod
    def vars_for_template(player: Player):
        # Ensure we have a safe role value
        role_value = (
            player.field_maybe_none("player_role")
            or player.participant.vars.get("role")
        )
        # Load shared grid that both players see
        try:
            shared_grid = json.loads(player.group.shared_grid)
        except (json.JSONDecodeError, TypeError):
            shared_grid = []
        # Get chat messages (both players)
        try:
            chat_messages = json.loads(player.grid_messages)
        except (json.JSONDecodeError, TypeError):
            chat_messages = []
        partner = (
            player.get_others_in_group()[0] if player.get_others_in_group() else None
        )
        partner_messages = []
        if partner:
            try:
                partner_messages = json.loads(partner.grid_messages)
            except (json.JSONDecodeError, TypeError):
                partner_messages = []
        return {
            "shared_grid": shared_grid,
            "player_role": role_value,
            "player_role_title": (role_value.title() if role_value else ""),
            "is_director": role_value == "director",
            "is_matcher": role_value == "matcher",
            "chat_messages": chat_messages,
            "partner_messages": partner_messages,
            "round_number": player.round_number,
            "total_rounds": 1,
        }


class AIvsAIObservationPage(Page):
    """Observation page for AI vs AI sessions.

    This page allows researchers to watch two AI agents (Director and Matcher)
    play the basket matching game against each other. The conversation unfolds
    in real-time, and the observer can control the pace.
    """

    template_name = "referential_task/AIvsAIObservation.html"

    @staticmethod
    def is_displayed(player: Player):
        # Only show for AI vs AI sessions
        return is_ai_vs_ai_session(player)

    @staticmethod
    def vars_for_template(player: Player):
        import logging

        # Load shared grid
        try:
            shared_grid = json.loads(player.group.shared_grid)
        except (json.JSONDecodeError, TypeError):
            shared_grid = []

        # Safety fallback: create grid on-demand if missing (same as DraggableGridPage)
        if not shared_grid:
            try:
                player.group.create_shared_grid(round_number=player.round_number)
                shared_grid = json.loads(player.group.shared_grid or "[]")
                logging.info("[AI_VS_AI] Created shared_grid on-demand with %d items", len(shared_grid))
            except Exception as e:
                logging.warning("[AI_VS_AI] Failed to create shared_grid on-demand: %s", e)
                shared_grid = []

        # Get current status
        status = get_ai_vs_ai_status(player)

        # Load preset full list for matcher pool display
        preset_full_list = []
        set_num = 1
        try:
            try:
                set_num = int(player.session.config.get("basket_set", 1))
            except Exception:
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
            with open(preset_path, "r") as f:
                presets = json.load(f)
            for item in presets.get("rounds", []):
                if isinstance(item, dict) and "fullList" in item:
                    preset_full_list = [f"images/{img}" for img in item.get("fullList", [])]
                    break
        except Exception:
            preset_full_list = []

        # Build the staging baskets using the same shuffle as the human matcher page
        # (DraggableGridPage) so the observation shows the same view.
        staging_baskets_json = "[]"
        try:
            import random as _random

            director_baskets = []
            for slot in shared_grid or []:
                if not isinstance(slot, dict):
                    continue
                img = (slot.get("image") or "").strip()
                if not img:
                    continue
                director_baskets.append({
                    "image": img,
                    "position": slot.get("position"),
                    "basket_id": slot.get("basket_id"),
                })

            director_set = {b.get("image") for b in director_baskets if b.get("image")}
            candidate_extras = []
            for img in preset_full_list or []:
                img = (img or "").strip()
                if not img or img in director_set:
                    continue
                candidate_extras.append(img)

            extras = [{"image": img, "position": f"extra_{i}", "basket_id": 100 + i}
                      for i, img in enumerate(candidate_extras[:6])]

            all_baskets = director_baskets + extras

            # Use the same deterministic shuffle as DraggableGridPage
            round_num = int(getattr(player, "round_number", 1) or 1)
            seed = 4242 + (set_num * 100) + round_num
            rng = _random.Random(seed)
            rng.shuffle(all_baskets)

            staging_baskets_json = json.dumps(all_baskets)
        except Exception:
            staging_baskets_json = "[]"

        # Session config for auto-play settings
        try:
            auto_play_delay = float(player.session.config.get("ai_vs_ai_delay", 0))
        except Exception:
            auto_play_delay = 0

        try:
            max_turns = int(player.session.config.get("ai_vs_ai_max_turns", 50))
        except Exception:
            max_turns = 50

        # Get accuracy and format for JavaScript (number or "null" string)
        accuracy = status.get("accuracy")
        accuracy_js = "null" if accuracy is None else str(accuracy)

        return {
            "shared_grid": shared_grid,
            "round_number": player.round_number,
            "total_rounds": Constants.num_rounds,
            "messages": status.get("messages", []),
            "partial_sequence": json.dumps(status.get("partial_sequence", [])),
            "filled_count": status.get("filled_count", 0),
            "is_complete": status.get("is_complete", False),
            "accuracy": accuracy,
            "accuracy_js": accuracy_js,
            "staging_baskets_json": staging_baskets_json,
            "current_grid_state": json.dumps(shared_grid),
            "auto_play_delay": auto_play_delay,
            "max_turns": max_turns,
            "session_code": getattr(player.session, "code", ""),
            "group_id_for_debug": getattr(player.group, "id", None),
        }

    @staticmethod
    def live_method(player: Player, data):
        """Handle live interactions for AI vs AI observation."""
        import logging

        action = data.get("action")

        if action == "next_turn":
            # Execute one turn
            result = run_ai_vs_ai_turn(player)
            status = get_ai_vs_ai_status(player)

            response = {
                "success": True,
                "turn_result": result,
                "status": status,
            }
            return {player.id_in_group: response}

        elif action == "get_status":
            # Get current game status
            status = get_ai_vs_ai_status(player)
            return {
                player.id_in_group: {
                    "success": True,
                    "status": status,
                }
            }

        elif action == "run_to_completion":
            # DEPRECATED: This action used to run all turns in a blocking loop,
            # which caused server-wide blocking. Now handled client-side.
            # Kept for backwards compatibility but just runs a single turn.
            logging.warning(
                "[AI_VS_AI] run_to_completion is deprecated - use client-side polling. "
                "Running single turn instead."
            )
            result = run_ai_vs_ai_turn(player)
            status = get_ai_vs_ai_status(player)

            return {
                player.id_in_group: {
                    "success": True,
                    "turns_run": 1,
                    "is_complete": result.get("is_complete", False),
                    "results": [result],
                    "status": status,
                }
            }

        return {
            player.id_in_group: {
                "success": False,
                "error": f"Unknown action: {action}",
            }
        }

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """Ensure the round is properly recorded before moving on."""
        import logging

        # If the round wasn't completed, mark it as such
        if not player.task_completed:
            import datetime
            player.completion_time = datetime.datetime.now().isoformat()

        # Generate AI vs AI perceptions on the final round
        if is_last_round(player):
            group = player.group
            # Only generate if not already done
            if group.field_maybe_none('ai_director_partner_capable') is None:
                logging.info("[AI_VS_AI] Generating AI vs AI perceptions on final round...")
                perceptions = generate_ai_vs_ai_perceptions(player)
                if perceptions:
                    logging.info("[AI_VS_AI] Successfully generated perceptions for both roles")
                else:
                    logging.warning("[AI_VS_AI] Failed to generate AI vs AI perceptions")


class RoundFeedback(Page):
    """Feedback screen shown after every round (including the final round).

    - Matcher: show their submitted sequence, highlighting incorrect picks in red.
      Do NOT reveal the correct order.
    - Director: show the correct order, highlighting positions the matcher got wrong in red.
      Do NOT show the matcher's submitted images.
    """

    template_name = "referential_task/RoundFeedback.html"

    @staticmethod
    def is_displayed(player: Player):
        # Skip for AI vs AI mode (feedback is already injected into AI context)
        if is_ai_vs_ai_session(player):
            return False

        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get("invalid_match", False):
            return False

        # Skip if participant exited the waiting room
        if player.participant.vars.get("exited_waiting_room", False):
            return False

        # Hide for shapes demo; otherwise show after each round
        try:
            if player.session.config.get("director_view", "grid") == "shapes_demo":
                return False
        except Exception:
            pass
        try:
            cfg_rounds = (
                player.session.config.get("num_rounds")
                if hasattr(player, "session") and player.session
                else None
            )
            total_rounds = cfg_rounds or Constants.num_rounds
        except Exception:
            total_rounds = Constants.num_rounds
        return player.round_number <= total_rounds

    @staticmethod
    def vars_for_template(player: Player):
        import json as _json

        # Determine role
        role_value = (
            player.field_maybe_none("player_role")
            or player.participant.vars.get("role")
        )

        # Load shared grid (correct order)
        try:
            shared_grid = _json.loads(player.group.shared_grid)
        except (ValueError, TypeError):
            shared_grid = []
        correct_sequence = [slot.get("image") for slot in shared_grid]

        # Load matcher submitted sequence (may be < 12 and may contain gaps)
        try:
            matcher_sequence = _json.loads(player.group.matcher_sequence)
        except (ValueError, TypeError):
            matcher_sequence = []

        # Build a dict keyed by logical 1‑based position.
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

        # Build slots for feedback display
        total_slots = 12
        slots = []
        correct_count = 0
        for i in range(total_slots):
            correct_img = correct_sequence[i] if i < len(correct_sequence) else None
            submitted_entry = matcher_by_pos.get(i + 1)
            submitted_img = submitted_entry.get("image") if submitted_entry else None

            if role_value == "matcher":
                # Show what the matcher selected; highlight incorrect picks
                display_img = submitted_img
                is_correct = (
                    submitted_img is not None
                    and correct_img is not None
                    and submitted_img == correct_img
                )
            else:
                # Director sees the correct order; highlight positions the matcher got wrong
                display_img = correct_img
                is_correct = (
                    submitted_img is not None
                    and correct_img is not None
                    and submitted_img == correct_img
                )

            if is_correct:
                correct_count += 1
            slots.append(
                {
                    "position": i + 1,
                    "image": display_img,
                    "is_correct": is_correct,
                }
            )

        return {
            "player_role": role_value,
            "is_director": role_value == "director",
            "is_matcher": role_value == "matcher",
            "round_number": player.round_number,
            "total_rounds": (
                player.session.config.get("num_rounds")
                if hasattr(player, "session") and player.session
                else None
            )
            or Constants.num_rounds,
            "feedback_slots": slots,
            "correct_count": correct_count,
        }


page_sequence = [
    # Human–AI mode: participants arrive directly at the task pages;
    # we do not use a waiting room or dynamic human–human matching.
    # Task pages
    ShapesDemoPage,
    DraggableGridPage,
    DraggableSequentialPage,
    AIvsAIObservationPage,  # AI vs AI mode observation page
    RoundFeedback,
    RoundAttentionCheck,  # One question per round (rounds 1-3)
    ResultsWaitPage,
    PartnerPerceptions,
    PartnerTypePerception,
    AIExperience,
    Debriefing,
    Results,
]


def vars_for_admin_report(subsession):
    """Summarize correct vs submitted sequences and accuracy per group for this round."""
    import datetime

    # Determine whether this session is configured as "AI matcher" (human is Director).
    try:
        session = subsession.session
        human_role_cfg = (
            session.config.get("human_role", "")
            if getattr(session, "config", None)
            else ""
        )
        if isinstance(human_role_cfg, str):
            human_role_cfg = human_role_cfg.strip().lower()
        else:
            human_role_cfg = ""
    except Exception:
        human_role_cfg = ""
    ai_is_matcher_mode = human_role_cfg == "director"

    groups_data = []
    for group in subsession.get_groups():
        # Correct sequence: director's grid order
        try:
            shared_grid = json.loads(group.shared_grid)
        except (json.JSONDecodeError, TypeError):
            shared_grid = []
        correct_sequence = [slot.get("image") for slot in shared_grid]

        # Find a human matcher (human = matcher, AI = director)
        matcher = None
        players_in_group = list(group.get_players())
        for p in players_in_group:
            if p.field_maybe_none("player_role") == "matcher" or p.participant.vars.get(
                "role"
            ) == "matcher":
                matcher = p
                break

        submitted_sequence = []
        accuracy = None
        accuracy_str = None
        submitted_at = None
        matcher_id_in_group = None
        matcher_type = "Human"

        if matcher:
            # Standard human-matcher case: read from the human matcher player.
            try:
                seq = json.loads(matcher.selected_sequence)
                submitted_sequence = [item.get("image") for item in seq]
            except (json.JSONDecodeError, TypeError):
                submitted_sequence = []
            accuracy = getattr(matcher, "sequence_accuracy", None)
            try:
                if accuracy is not None:
                    accuracy_str = f"{float(accuracy):.1f}"
            except Exception:
                accuracy_str = str(accuracy) if accuracy is not None else None
            submitted_at = getattr(matcher, "completion_time", None)
            matcher_id_in_group = matcher.id_in_group
            if submitted_at:
                try:
                    submitted_at = datetime.datetime.fromisoformat(
                        submitted_at
                    ).strftime("%H:%M:%S")
                except Exception:
                    pass
        else:
            # Fallback: AI matcher mode (human = Director, AI = Matcher).
            if ai_is_matcher_mode and players_in_group:
                matcher_type = "AI"
                director_player = players_in_group[0]
                try:
                    seq = json.loads(
                        getattr(group, "matcher_sequence", "") or "[]"
                    )
                    submitted_sequence = [item.get("image") for item in seq]
                except (json.JSONDecodeError, TypeError):
                    submitted_sequence = []

                accuracy = getattr(director_player, "sequence_accuracy", None)
                try:
                    if accuracy is not None:
                        accuracy_str = f"{float(accuracy):.1f}"
                except Exception:
                    accuracy_str = str(accuracy) if accuracy is not None else None

                submitted_at = getattr(director_player, "completion_time", None)
                if submitted_at:
                    try:
                        submitted_at = datetime.datetime.fromisoformat(
                            submitted_at
                        ).strftime("%H:%M:%S")
                    except Exception:
                        pass

        groups_data.append(
            {
                "group_id": group.id,
                "correct_sequence": correct_sequence,
                "submitted_sequence": submitted_sequence,
                "accuracy": accuracy,
                "accuracy_str": accuracy_str,
                "submitted_at": submitted_at,
                "matcher_id_in_group": matcher_id_in_group,
                "matcher_type": matcher_type,
                "correct_sequence_head": " ".join(correct_sequence[:5]),
                "submitted_sequence_head": " ".join(submitted_sequence[:5]),
            }
        )

    return {
        "round_number": subsession.round_number,
        "groups": groups_data,
        "groups_json": json.dumps(groups_data),
        "session_code": getattr(subsession.session, "code", ""),
        # Built-in oTree endpoint for app-level custom export
        "custom_export_url": "/custom_export?app=referential_task",
    }


def admin_report_context(subsession):
    # oTree will use AdminReport.html by default.
    # Point to our standalone custom template explicitly.
    ctx = vars_for_admin_report(subsession)
    ctx["__template_name__"] = "referential_task/AdminReport.html"
    return ctx



