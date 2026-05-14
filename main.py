import sys
import os
from dotenv import load_dotenv

load_dotenv()
import json
import logging
import random
import re
import subprocess
from pathlib import Path
from datetime import datetime

import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from referential_task.state import Player, Group, Session
from referential_task.state import Constants
from referential_task.ai_utils import run_ai_vs_ai_turn, get_ai_vs_ai_status, _load_matcher_pool_image_urls

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Referential Game AI-AI Simulation")

# Database setup
DB_FILE = "data.sqlite"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS game_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            round_number INTEGER,
            config TEXT,
            shared_grid TEXT,
            target_baskets TEXT,
            ai_partial_sequence TEXT,
            ai_messages TEXT,
            ai_reasoning_log TEXT,
            matcher_sequence TEXT,
            status TEXT,
            ai_director_reasoning TEXT,
            ai_matcher_reasoning TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

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


# Mount static files
app.mount("/static", StaticFiles(directory="_static"), name="static")

# Setup Jinja2 templates location
# We will create a fresh directory for standalone templates
templates = Jinja2Templates(directory="templates")

# In-memory storage of simulation states
# Key: session_id, Value: dict containing Player object and status
active_simulations = {}

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
    prompt_strategy = config.get("prompt_strategy", "unknown") if isinstance(config, dict) else "unknown"
    prefix = config.get("session_prefix") if isinstance(config, dict) else None
    prefix = sanitize_path_part(prefix or session_id)
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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main simulation UI."""
    # Render the AIvsAIObservation dashboard
    return templates.TemplateResponse("AIvsAIObservation.html", {"request": request})

@app.post("/api/game/start")
async def start_game(data: dict):
    """Initialize a new simulation round."""
    session_id = data.get("session_id", "local_test_1")
    round_number = int(data.get("round_number", 1))
    
    # Configure session
    session_config = {
        "ai_vs_ai_mode": True,
        "director_view": "grid",
        "basket_set": int(data.get("basket_set", 5)),
        "num_rounds": Constants.num_rounds,
        "session_prefix": data.get("session_prefix") or session_id,
        "prompt_strategy": data.get("prompt_strategy", "ACL_prompt"),
        "ai_director_model": data.get("director_model") or os.environ.get("AI_DIRECTOR_MODEL", "gpt-4o-mini"),
        "ai_matcher_model": data.get("matcher_model") or os.environ.get("AI_MATCHER_MODEL", "gpt-4o-mini"),
        "ai_reasoning_effort": data.get("reasoning_effort", "none"),
    }

    session = Session(session_config)
    
    group = Group()
    grid = get_preset_grid(round_number=round_number, set_num=session_config["basket_set"])
    group.shared_grid = json.dumps(grid)
    
    player = Player(role="observer", group=group, session=session, round_number=round_number)
    
    active_simulations[session_id] = {
        "player": player,
        "round": round_number,
        "status": "ready"
    }
    
    save_state_to_db(session_id, player)
    
    return JSONResponse({"status": "Simulation started", "session_id": session_id})

@app.post("/api/game/turn")
async def play_turn(data: dict):
    """Execute one turn of the AI vs AI interaction."""
    session_id = data.get("session_id")
    if session_id not in active_simulations:
        return JSONResponse({"error": "Simulation not found"}, status_code=404)
        
    sim = active_simulations[session_id]
    player = sim["player"]
    
    try:
        run_ai_vs_ai_turn(player)
        save_state_to_db(session_id, player)
        
        # Auto-advance to the next round if the current one is completely finished
        if getattr(player, "task_completed", False):
            current_round = player.round_number
            total_rounds = get_total_rounds(player.session)
            if current_round < total_rounds:
                # Build conceptual pact map from the completed round's CG + shared_grid.
                # This maps image_path → nicknames so that agreed terms persist across
                # rounds even when basket positions are reshuffled.
                try:
                    from referential_task.common_ground_agent import build_conceptual_pact_map
                    build_conceptual_pact_map(player)
                    logger.info(f"Built conceptual pact map after Round {current_round}")
                except Exception as e:
                    logger.warning(f"Failed to build conceptual pact map: {e}")

                next_round = current_round + 1
                
                # Initialize new game state for the next round
                new_group = Group()
                new_grid = get_preset_grid(
                    round_number=next_round,
                    set_num=player.session.config.get("basket_set", 5),
                )
                new_group.shared_grid = json.dumps(new_grid)

                new_player = Player(role="observer", group=new_group, session=player.session, round_number=next_round)
                
                # Overwrite active simulation with the new round's player
                active_simulations[session_id]["player"] = new_player
                active_simulations[session_id]["round"] = next_round
                
                # Save the fresh next round to DB immediately
                save_state_to_db(session_id, new_player)
                
                # Update the active reference so the status returned matches the new round
                player = new_player
            else:
                # Final round complete: Evaluate mutual perceptions
                if not getattr(player, "perceptions_generated", False):
                    player.perceptions_generated = True
                    logger.info("Round %s finished! Fetching AI vs AI mutual perceptions.", current_round)
                    from referential_task.ai_perceptions import generate_ai_vs_ai_perceptions
                    generate_ai_vs_ai_perceptions(player)
                    save_state_to_db(session_id, player)
                    
                    # --- AUTO-EXPORT DATA ---
                    try:
                        logger.info("Auto-exporting full session data to structured data folder...")
                        export_dir = get_experiment_export_dir(player.session.config, session_id)
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

                        transcript_export_cmd = [
                            sys.executable,
                            "scripts/export_json_session.py",
                            str(export_path),
                        ]
                        result = subprocess.run(
                            transcript_export_cmd,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        if result.returncode == 0:
                            logger.info(
                                "Successfully generated transcript/visual export for %s",
                                export_path,
                            )
                            if result.stdout:
                                logger.info("Session export output: %s", result.stdout.strip())
                        else:
                            logger.error(
                                "Transcript/visual export failed for %s with exit code %s: %s",
                                export_path,
                                result.returncode,
                                (result.stderr or result.stdout or "").strip(),
                            )
                    except Exception as export_e:
                        logger.error(f"Auto-export failed: {export_e}")

        status = get_ai_vs_ai_status(player)
        return JSONResponse({"status": "Turn executed", "game_status": status})
    except Exception as e:
        logger.exception("Error during turn")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/game/state")
async def get_state(session_id: str):
    """Get the current state of the simulation for the UI."""
    if session_id not in active_simulations:
        return JSONResponse({"error": "Simulation not found"}, status_code=404)
        
    sim = active_simulations[session_id]
    player = sim["player"]
    group = player.group
    
    status = get_ai_vs_ai_status(player)
    
    ai_messages = []
    if group.ai_messages:
        try:
            ai_messages = json.loads(group.ai_messages)
        except Exception:
            pass
            
    partial_sequence = []
    if group.ai_partial_sequence:
        try:
            partial_sequence = json.loads(group.ai_partial_sequence)
        except Exception:
            pass
            
    reasoning_log = []
    if group.ai_reasoning_log:
        try:
            reasoning_log = json.loads(group.ai_reasoning_log)
        except Exception:
            pass

    pool_urls = _load_matcher_pool_image_urls(player) or []
    matcher_pool = [item.get("slot", {}).get("image", "").lstrip("/ ") for item in pool_urls if item.get("slot", {}).get("image")]

    return JSONResponse({
        "status": status,
        "round_number": player.round_number,
        "prompt_strategy": player.session.config.get("prompt_strategy", "ACL_prompt"),
        "director_model": player.session.config.get("ai_director_model", "unknown"),
        "matcher_model": player.session.config.get("ai_matcher_model", "unknown"),
        "ai_messages": ai_messages,
        "partial_sequence": partial_sequence,
        "reasoning_log": reasoning_log,
        "shared_grid": json.loads(group.shared_grid),
        "matcher_pool": matcher_pool
    })

@app.get("/api/game/export")
async def export_session(session_id: str, generate_artifacts: bool = False):
    """Export the current session's data as a JSON file."""
    if not os.path.exists(DB_FILE):
        return JSONResponse({"error": "Database not found"}, status_code=404)
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT session_id, round_number, config, shared_grid, target_baskets, ai_partial_sequence, ai_messages, ai_reasoning_log, matcher_sequence, status, ai_director_reasoning, ai_matcher_reasoning, updated_at FROM game_sessions WHERE session_id = ? ORDER BY round_number", (session_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return JSONResponse({"error": "Session not found"}, status_code=404)

    sessions = []
    for row in rows:
        (s_id, r_num, config_txt, shared_grid_txt, target_baskets_txt,
         partial_seq_txt, ai_msgs_txt, ai_reasoning_txt, matcher_seq_txt,
         status_txt, director_reasoning_txt, matcher_reasoning_txt, updated_at) = row
        
        def safe_json(val):
            try:
                return json.loads(val) if val else []
            except Exception:
                return val

        session_data = {
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
        }
        sessions.append(session_data)

    if generate_artifacts:
        try:
            config = sessions[0].get("config", {}) if sessions else {}
            export_dir = get_experiment_export_dir(config, session_id)
            export_dir.mkdir(parents=True, exist_ok=True)

            export_path = export_dir / f"{session_id}_data.json"
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=4)
            logger.info("UI export wrote session data to %s", export_path)

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/export_json_session.py",
                    str(export_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                logger.info(
                    "UI export generated transcript/visual artifacts for %s",
                    export_path,
                )
                if result.stdout:
                    logger.info("Session export output: %s", result.stdout.strip())
            else:
                logger.error(
                    "UI transcript/visual export failed for %s with exit code %s: %s",
                    export_path,
                    result.returncode,
                    (result.stderr or result.stdout or "").strip(),
                )
        except Exception as export_e:
            logger.error("UI export artifact generation failed: %s", export_e)

    headers = {
        "Content-Disposition": f"attachment; filename={session_id}_data.json"
    }
    return JSONResponse(content=sessions, headers=headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
