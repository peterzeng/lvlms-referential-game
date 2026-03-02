# AI-AI Referential Director-Matcher Game

This repository contains an AI-AI simulation of the referential director-matcher game. The project was previously built on oTree, but this branch has been fully refactored to use a lightweight **FastAPI** backend to run automated AI-to-AI simulations without the overhead of human participant management.

## Experiment Overview

In this simulation, two AI agents (Vision-Language Models) are paired as the **Director** and the **Matcher**. Over 4 rounds:

- The **Director** describes their entire 2x6 grid so the Matcher can reconstruct the sequence (left-to-right, top-to-bottom order).
- The **Matcher** has a staging area (bottom) with 18 baskets and a target area (top) with 12 empty cells arranged in 2 rows of 6.
- The **Matcher** "clicks" (via AI sequence generation) baskets in the staging area to place them in the target area, matching the exact order that baskets appear on the director's screen.
- The goal is for the matcher to correctly reproduce the director's basket sequence, using only the director's descriptions.

## Technology Stack

- **FastAPI** (Python 3.11+) handles simulation routing and backend AI logic.
- **SQLite** for persisting game logs locally (`data.sqlite`).
- **Jinja2** for rendering the simulation observation dashboard.
- **JavaScript & Bootstrap** for the interactive dashboard UI.
- **OpenAI & Google Gemini SDKs** for the agent interactions.

## Setup Instructions

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/Human-VLM-Game.git
   cd Human-VLM-Game
   git checkout <this-branch>
   ```
2. **Set up your Python environment** (recommended: conda)

   ```bash
   conda create -n langviscog python=3.11
   conda activate langviscog
   pip install -r requirements.txt
   ```
3. **Set API Keys in `.env`**
   Add your API keys to the `.env` file or export them directly:

   ```bash
   export OPENAI_API_KEY="sk-..."
   export GEMINI_API_KEY="AIzaSy..."
   ```
4. **Run the FastAPI Local Server**

   ```bash
   conda run -n langviscog python main.py
   ```
5. **Observe the Simulation**
   Open your browser and navigate to `http://127.0.0.1:8000/`.
   Use the UI dashboard to initialize the session, and use the "Next Turn" or "Auto-Play" buttons to monitor the agents.

## Data Persistence & Exporting

As the simulation progresses, all logs—including the generated chat messages, sequences, reasoning logs, and configuration parameters—are written immediately to the local `data.sqlite` DB in the `game_sessions` table.

### Exporting to JSON for Analysis

To extract the session configurations, completed chat transcripts, and detailed step-by-step reasoning outputs into a portable JSON file for your data analysis scripts, simply run:

```bash
conda run -n langviscog python scripts/export_to_json.py
```

This script will automatically query `data.sqlite`, safely traverse all historical turns, and write a prettified JSON array structured specifically for analytic usage to `data/exported_sessions.json`.

## Simulation Parameters & Model Swapping

The simulation allows you to easily plug and play with different language models (e.g. `gpt-4o-mini`, `gpt-5.2`, `gemini-3-flash-preview`).

You can select the specific models you want for the **Director** and the **Matcher** individually directly from the dropdowns on the web interface dashboard before clicking "Start Simulation". Alternatively, you can override default behavior in `main.py`'s `start_game` route or set the `AI_DIRECTOR_MODEL` and `AI_MATCHER_MODEL` environment variables.

Simulation delays, API prompt strategies, and reasoning efforts can additionally be configured per-session within the code configurations. Presets for the underlying basket grids can be tweaked inside the `referential_task/grids_presetsN.json` files.
