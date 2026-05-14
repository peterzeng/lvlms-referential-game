#!/usr/风/env python3
import sys
import os
import argparse
import json
import logging
import re
from datetime import datetime

# Add project root to path so we can import from referential_task and main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from referential_task.state import Player, Group, Session, Constants
from referential_task.ai_utils import run_ai_vs_ai_turn
from referential_task.ai_perceptions import generate_ai_vs_ai_perceptions

import sqlite3
import random
from pathlib import Path
from referential_task.ai_utils import get_ai_vs_ai_status

DB_FILE = "data.sqlite"

def get_total_rounds(session=None):
    """Return the configured number of rounds, falling back to the task default."""
    try:
        if session is not None:
            return int(session.config.get("num_rounds") or Constants.num_rounds)
    except Exception:
        pass
    return Constants.num_rounds

def get_experiment_family(prompt_strategy):
    strategy = str(prompt_strategy or "").lower()
    if "cameron" in strategy:
        return "Cameron"
    if "acl" in strategy:
        return "ACL"
    return "Other"

def sanitize_path_part(value, fallback="session"):
    text = str(value or "").strip() or fallback
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or fallback

def get_experiment_export_dir(config, session_id):
    prompt_strategy = config.get("prompt_strategy", "unknown")
    prefix = sanitize_path_part(config.get("session_prefix") or session_id)
    current_date = datetime.now().strftime("%Y-%m-%d")
    return Path("data") / "experiments" / get_experiment_family(prompt_strategy) / current_date / prefix

def get_preset_grid(round_number=1, set_num=5):
    """Load a grid preset like oTree did in create_shared_grid"""
    preset_filename = f"grids_presets{set_num}.json"
    preset_path = Path("referential_task") / preset_filename
    
    grid = []
    try:
        if preset_path.exists():
            with open(preset_path, "r") as f:
                presets = json.load(f)
            for round_cfg in presets.get("rounds", []):
                if round_cfg.get("round") == round_number:
                    basket_files = [f"images/{img}" for img in round_cfg["baskets"]]
                    position_index = 0
                    for row in range(1, 4):
                        for col in range(1, 5):
                            grid.append({
                                "position": f"{row}{col}",
                                "row": row,
                                "col": col,
                                "image": basket_files[position_index],
                                "basket_id": position_index + 1
                            })
                            position_index += 1
                    break
    except Exception as e:
        logger.error(f"Error loading preset: {e}")

    # Fallback to random if no preset found
    if not grid:
        all_images = [f"images/{i:03d}.png" for i in range(1, 71)]
        selected_images = random.sample(all_images, 12)
        position_index = 0
        for row in range(1, 4):
            for col in range(1, 5):
                grid.append({
                    "position": f"{row}{col}",
                    "row": row,
                    "col": col,
                    "image": selected_images[position_index],
                    "basket_id": position_index + 1
                })
                position_index += 1

    return grid

def save_state_to_db(session_id, player):
    """Save or update the current simulation state in SQLite"""
    group = player.group
    session = player.session
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Check if record exists
    c.execute("SELECT id FROM game_sessions WHERE session_id = ? AND round_number = ?", 
              (session_id, player.round_number))
    row = c.fetchone()
    
    status = get_ai_vs_ai_status(player)
    
    if row:
        c.execute('''
            UPDATE game_sessions SET 
                shared_grid = ?,
                target_baskets = ?,
                ai_partial_sequence = ?,
                ai_messages = ?,
                ai_reasoning_log = ?,
                matcher_sequence = ?,
                status = ?,
                ai_director_reasoning = ?,
                ai_matcher_reasoning = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            group.shared_grid,
            group.target_baskets,
            group.ai_partial_sequence,
            group.ai_messages,
            group.ai_reasoning_log,
            group.matcher_sequence,
            json.dumps(status),
            group.ai_director_perceptions_raw,
            group.ai_matcher_perceptions_raw,
            row[0]
        ))
    else:
        c.execute('''
            INSERT INTO game_sessions (
                session_id, round_number, config, shared_grid, target_baskets,
                ai_partial_sequence, ai_messages, ai_reasoning_log, matcher_sequence,
                status, ai_director_reasoning, ai_matcher_reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id,
            player.round_number,
            json.dumps(session.config),
            group.shared_grid,
            group.target_baskets,
            group.ai_partial_sequence,
            group.ai_messages,
            group.ai_reasoning_log,
            group.matcher_sequence,
            json.dumps(status),
            group.ai_director_perceptions_raw,
            group.ai_matcher_perceptions_raw
        ))
    
    conn.commit()
    conn.close()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("batch_runner")

def run_single_session(session_id: str, config: dict):
    logger.info(f"=== Starting Session: {session_id} ===")
    
    session = Session(config)
    round_number = 1
    
    # Initialize Round 1
    group = Group()
    grid = get_preset_grid(round_number=round_number, set_num=config.get("basket_set", 5))
    group.shared_grid = json.dumps(grid)
    player = Player(role="observer", group=group, session=session, round_number=round_number)
    
    save_state_to_db(session_id, player)
    
    failed_turns = 0
    last_status = None
    
    while True:
        # Play a turn
        try:
            run_ai_vs_ai_turn(player)
            save_state_to_db(session_id, player)
            
            # Check for infinite loop (e.g., API key missing)
            current_status = json.dumps(get_ai_vs_ai_status(player))
            if current_status == last_status:
                failed_turns += 1
                if failed_turns > 5:
                    logger.error(f"Session {session_id} stalled. Status hasn't changed for 5 turns. Breaking loop to prevent infinite retry. Please check API keys.")
                    break
            else:
                failed_turns = 0
                last_status = current_status
                
        except Exception as e:
            logger.error(f"Error during turn in session {session_id}: {e}")
            break
            
        # Check if round is complete
        if getattr(player, "task_completed", False):
            logger.info(f"Session {session_id} - Round {round_number} complete.")
            
            total_rounds = get_total_rounds(session)
            if round_number < total_rounds:
                # Mirror the app flow so agreed nicknames persist across rounds
                # in batch experiments too.
                try:
                    from referential_task.common_ground_agent import build_conceptual_pact_map
                    build_conceptual_pact_map(player)
                except Exception as pact_error:
                    logger.warning(
                        f"Failed to build conceptual pact map for {session_id} round {round_number}: {pact_error}"
                    )
                
                # Advance to next round
                round_number += 1
                new_group = Group()
                new_grid = get_preset_grid(
                    round_number=round_number,
                    set_num=config.get("basket_set", 5),
                )
                new_group.shared_grid = json.dumps(new_grid)

                player = Player(role="observer", group=new_group, session=session, round_number=round_number)
                save_state_to_db(session_id, player)
            else:
                # Final round complete: End of session
                logger.info(f"Session {session_id} - All {total_rounds} rounds complete. Generating perceptions...")
                if not getattr(player, "perceptions_generated", False):
                    player.perceptions_generated = True
                    generate_ai_vs_ai_perceptions(player)
                    save_state_to_db(session_id, player)
                    
                    # Manual auto-export (similar to main.py logic)
                    try:
                        export_dir = get_experiment_export_dir(config, session_id)
                        export_dir.mkdir(parents=True, exist_ok=True)
                        
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("SELECT session_id, round_number, config, shared_grid, target_baskets, ai_partial_sequence, ai_messages, ai_reasoning_log, matcher_sequence, status, ai_director_reasoning, ai_matcher_reasoning, updated_at FROM game_sessions WHERE session_id = ? ORDER BY round_number", (session_id,))
                        rows = c.fetchall()
                        conn.close()
                        
                        sessions_data = []
                        for row in rows:
                            (s_id, r_num, config_txt, shared_grid_txt, target_baskets_txt,
                             partial_seq_txt, ai_msgs_txt, ai_reasoning_txt, matcher_seq_txt,
                             status_txt, director_reasoning_txt, matcher_reasoning_txt, updated_at) = row
                            
                            def safe_json(val):
                                try: return json.loads(val) if val else []
                                except Exception: return val

                            sessions_data.append({
                                "session_id": s_id,
                                "round_number": r_num,
                                "updated_at": updated_at,
                                "config": safe_json(config_txt),
                                "status": safe_json(status_txt),
                                "shared_grid": safe_json(shared_grid_txt),
                                "target_baskets": safe_json(target_baskets_txt),
                                "ai_partial_sequence": safe_json(partial_seq_txt),
                                "matcher_sequence": safe_json(matcher_seq_txt),
                                "ai_messages": safe_json(ai_msgs_txt),
                                "ai_reasoning_log": safe_json(ai_reasoning_txt),
                                "ai_director_reasoning": safe_json(director_reasoning_txt),
                                "ai_matcher_reasoning": safe_json(matcher_reasoning_txt)
                            })
                            
                        export_path = export_dir / f"{session_id}_data.json"
                        with open(export_path, 'w', encoding='utf-8') as f:
                            json.dump(sessions_data, f, indent=4)
                        logger.info(f"Successfully auto-exported to {export_path}")
                        
                        # Automatically generate visuals and transcript
                        import subprocess
                        import sys
                        logger.info("Auto-generating visualizations and transcript...")
                        try:
                            subprocess.run([sys.executable, "scripts/export_json_session.py", str(export_path)], check=True)
                        except Exception as viz_e:
                            logger.error(f"Failed to generate visualizations: {viz_e}")
                    except Exception as export_e:
                        logger.error(f"Auto-export failed: {export_e}")
                
                # Session completely finished
                break
                
    logger.info(f"=== Finished Session: {session_id} ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run headless AI vs AI experimental sessions.")
    parser.add_argument("--sessions", type=int, default=1, help=f"Number of full sessions ({Constants.num_rounds} rounds each) to run.")
    parser.add_argument("--prompt-strategy", type=str, default="ACL_prompt", help="Prompt strategy (ACL_prompt or cameron-prompt).")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="Model to use for both agents.")
    parser.add_argument("--director-model", type=str, help="Specific model for director (overrides --model).")
    parser.add_argument("--matcher-model", type=str, help="Specific model for matcher (overrides --model).")
    parser.add_argument("--session-prefix", type=str, default="batch", help="Prefix for the session ID.")
    parser.add_argument("--basket-set", type=int, default=5, help="Basket set to use.")
    
    args = parser.parse_args()
    
    config = {
        "ai_vs_ai_mode": True,
        "director_view": "grid",
        "basket_set": args.basket_set,
        "num_rounds": Constants.num_rounds,
        "session_prefix": args.session_prefix,
        "prompt_strategy": args.prompt_strategy,
        "ai_director_model": args.director_model or args.model,
        "ai_matcher_model": args.matcher_model or args.model,
        "ai_reasoning_effort": "none",
    }
    
    logger.info(f"Starting batch run of {args.sessions} sessions.")
    logger.info(f"Config: {json.dumps(config, indent=2)}")
    
    timestamp = datetime.now().strftime("%H%M%S")
    for i in range(1, args.sessions + 1):
        session_id = f"{args.session_prefix}_{timestamp}_{i}"
        run_single_session(session_id, config)
        
    logger.info("Batch run complete!")
