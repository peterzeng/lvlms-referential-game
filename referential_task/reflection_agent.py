import json
import logging
from referential_task.ai_utils import _get_ai_client
import sqlite3

def generate_reflection_directives(session_id, current_round, config, db_path="data.sqlite"):
    """
    Runs an inter-round reflection agent to analyze mistakes from the previous round
    and formulate directives for the next round.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT shared_grid, matcher_sequence, ai_messages FROM game_sessions WHERE session_id = ? AND round_number = ?", (session_id, current_round))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return ""
        
    shared_grid_str, matcher_seq_str, ai_msgs_str = row
    
    # Load JSONs
    try:
        shared_grid = json.loads(shared_grid_str or "[]")
        matcher_seq = json.loads(matcher_seq_str or "[]")
        ai_msgs = json.loads(ai_msgs_str or "[]")
    except Exception:
        return ""

    # Calculate which baskets were marked incorrect (this is the only feedback players get)
    incorrect_positions = []
    
    # Create a quick lookup for matcher placements by position
    matcher_by_pos = {}
    for item in matcher_seq:
        if isinstance(item, dict) and "position" in item:
            pos = item.get("position")
            try:
                pos_int = int(pos)
                matcher_by_pos[pos_int] = item.get("image")
            except Exception:
                pass
                
    for i, slot in enumerate(shared_grid):
        correct_image = slot.get("image")
        pos = i + 1
        placed_image = matcher_by_pos.get(pos)
        if placed_image != correct_image:
            incorrect_positions.append(pos)
    
    history_text = ""
    for msg in ai_msgs:
        role = msg.get("sender_role", "unknown")
        text = msg.get("text", "")
        history_text += f"{role}: {text}\n"
        
    prompt = f"""You are a Reflection Agent analyzing a communication game.
    
    The Director and Matcher just finished Round {current_round}.
    
    System Feedback:
    The following positions were marked as INCORRECT: {incorrect_positions}.
    Note: Neither player knows exactly what the other intended or placed for these positions. They only know these positions were wrong.
    
    Dialogue History:
    {history_text}
    
    Your task:
    1. Look at the dialogue history for the positions that were marked INCORRECT.
    2. Analyze the dialogue to understand WHY the miscommunication likely occurred (e.g., was a description ambiguous? Did they use the same nickname for two different baskets?).
    3. Generate explicit DIRECTIVES for the next round to prevent this error. For example: "Directive: Next round, the Director must be careful when describing the 'duck basket' and explicitly mention its beak, because it seems to have been confused."
    
    Output strictly in JSON with this schema:
    {{
        "analysis": "<your analysis>",
        "directives": ["<directive 1>", "<directive 2>"]
    }}
    """
    
    client = _get_ai_client()
    if not client:
        return ""
        
    try:
        response = client.chat.completions.create(
            model=config.get("ai_model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        directives = parsed.get("directives", [])
        
        # Log the reflection analysis for our records
        logging.info(f"[REFLECTION_AGENT] Analysis for Round {current_round}:\n{json.dumps(parsed, indent=2)}")
        
        if directives:
            return "REFLECTION AGENT DIRECTIVES FROM PREVIOUS ROUND:\n" + "\n".join(f"- {d}" for d in directives)
        return ""
    except Exception as e:
        logging.error(f"[REFLECTION_AGENT] Failed: {e}")
        return ""
