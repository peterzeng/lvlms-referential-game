"""
AI partner perceptions for the basket referential task.

This module handles:
- Generating AI's perceptions of the human partner at experiment end
- Mirrors the PartnerPerceptions questions humans answer

This is used by page_views.py on the AIExperience page.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import Player


# ---------------------------------------------------------------------------
# AI Partner Perception Prompt
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


# ---------------------------------------------------------------------------
# Generate AI Partner Perceptions
# ---------------------------------------------------------------------------


def generate_ai_partner_perceptions(player: "Player") -> dict[str, Any] | None:
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
    from .ai_utils import _get_ai_client, _get_ai_model, _build_api_call_kwargs

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

        # Call the API with model configuration from session or environment
        model = _get_ai_model(player)
        api_kwargs = _build_api_call_kwargs(
            model=model,
            messages=messages,
            player=player,
            max_tokens=500,
        )
        logging.info("[AI_PERCEPTIONS] Using model: %s", model)
        response = client.chat.completions.create(**api_kwargs)

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

def generate_ai_vs_ai_perceptions(player: "Player") -> bool:
    """Generate mutual AI perceptions (Director evaluating Matcher, and Matcher evaluating Director).
    
    This is called automatically in AI-vs-AI mode at the end of Round 4.
    """
    from .ai_utils import _get_ai_client, _build_api_call_kwargs
    client = _get_ai_client()
    if client is None:
        logging.warning("[AI_VS_AI_PERCEPTIONS] No OpenAI client available")
        return False

    try:
        # Gather complete chat history across all rounds
        all_messages = []
        if hasattr(player, "in_all_rounds"):
            all_players = player.in_all_rounds()
        else:
            all_players = [player]

        for round_player in all_players:
            round_num = round_player.round_number
            try:
                ai_msgs = json.loads(round_player.group.ai_messages or "[]")
                for msg in ai_msgs:
                    if isinstance(msg, dict):
                        msg["round"] = round_num
                        all_messages.append(msg)
            except Exception:
                pass

        if not all_messages:
            logging.warning("[AI_VS_AI_PERCEPTIONS] No messages found in history")
            return False

        # Build conversation text
        conversation_text_base = "=== COMPLETE CONVERSATION HISTORY ===\n\n"
        current_round = 0
        for msg in all_messages:
            msg_round = msg.get("round", 0)
            if msg_round != current_round:
                current_round = msg_round
                conversation_text_base += f"\n--- Round {current_round} ---\n\n"

            sender = msg.get("sender_role", "unknown")
            text = msg.get("text", "")
            if text:
                conversation_text_base += f"{sender.upper()}: {text}\n"

        def evaluate_partner(evaluator_role: str, partner_role: str):
            prefix = f"Your role in the task was: {evaluator_role.upper()}\n"
            prefix += f"Your partner's role was: {partner_role.upper()}\n\n"
            conversation_text = prefix + conversation_text_base
            
            messages = [
                {"role": "system", "content": AI_PARTNER_PERCEPTION_PROMPT},
                {"role": "user", "content": conversation_text},
            ]
            
            model = player.session.config.get(f"ai_{evaluator_role}_model") or player.session.config.get("ai_model", "gpt-4o-mini")
            
            api_kwargs = _build_api_call_kwargs(
                model=model,
                messages=messages,
                player=player,
                max_tokens=600,
            )
            response = client.chat.completions.create(**api_kwargs)
            
            reply = response.choices[0].message.content
            if not reply: return None
            
            reply = reply.strip()
            if "```json" in reply:
                reply = reply[reply.find("```json")+7:reply.rfind("```")].strip()
            elif "```" in reply:
                reply = reply[reply.find("```")+3:reply.rfind("```")].strip()
                
            perceptions = json.loads(reply)
            result = {}
            for key in ["partner_capable", "partner_helpful", "partner_understood", "partner_adapted", "collaboration_improved"]:
                val = perceptions.get(key)
                if isinstance(val, (int, float)):
                    result[key] = max(1, min(5, int(val)))
                else:
                    result[key] = 3
            result["partner_comment"] = str(perceptions.get("partner_comment", ""))[:2000]
            result["_raw"] = perceptions
            return result

        # 1. Director evaluating Matcher
        logging.info("[AI_VS_AI_PERCEPTIONS] Fetching Director's perceptions...")
        dir_eval = evaluate_partner("director", "matcher")
        if dir_eval:
            group = player.group
            group.ai_director_partner_capable = dir_eval["partner_capable"]
            group.ai_director_partner_helpful = dir_eval["partner_helpful"]
            group.ai_director_partner_understood = dir_eval["partner_understood"]
            group.ai_director_partner_adapted = dir_eval["partner_adapted"]
            group.ai_director_collaboration_improved = dir_eval["collaboration_improved"]
            group.ai_director_partner_comment = dir_eval["partner_comment"]
            group.ai_director_perceptions_raw = json.dumps(dir_eval["_raw"])

        # 2. Matcher evaluating Director
        logging.info("[AI_VS_AI_PERCEPTIONS] Fetching Matcher's perceptions...")
        mat_eval = evaluate_partner("matcher", "director")
        if mat_eval:
            group = player.group
            group.ai_matcher_partner_capable = mat_eval["partner_capable"]
            group.ai_matcher_partner_helpful = mat_eval["partner_helpful"]
            group.ai_matcher_partner_understood = mat_eval["partner_understood"]
            group.ai_matcher_partner_adapted = mat_eval["partner_adapted"]
            group.ai_matcher_collaboration_improved = mat_eval["collaboration_improved"]
            group.ai_matcher_partner_comment = mat_eval["partner_comment"]
            group.ai_matcher_perceptions_raw = json.dumps(mat_eval["_raw"])

        return True
    except Exception as e:
        import traceback
        logging.error("[AI_VS_AI_PERCEPTIONS] Error generating AI vs AI perceptions: %s\n%s", e, traceback.format_exc())
        return False

