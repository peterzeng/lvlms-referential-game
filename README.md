# Human-LVLM Director-Matcher Game

This repository contains an interactive director-matcher game experiment implemented with [oTree](https://www.otree.org/). The experiment is designed to study communication and reference in a collaborative visual task.

## Which branch runs which experiment?

Each pairing of the experiment lives on its own branch. **Check out the branch that matches the pairing you want to run:**

| Branch         | Pairing                | What runs                                                                 |
| -------------- | ---------------------- | ------------------------------------------------------------------------- |
| `main`         | **Human–AI / AI–Human** | One human paired with a VLM partner (GPT‑5.2). The human plays Director *or* Matcher; the AI plays the other role. |
| **`human-human`** *(you are here)* | **Human–Human** | Two human participants, one Director and one Matcher. No AI. |
| `ai-ai`        | **AI–AI**              | Both Director and Matcher played by the VLM.                              |

The rest of this README documents the **`human-human` (Human–Human)** branch.

## Experiment Overview

In this game, two participants are paired as the **Director** and the **Matcher**. Over 3 rounds:

- The **Director** describes their entire 2x6 grid so the Matcher can reconstruct the sequence (left-to-right, top-to-bottom order).
- The **Matcher** has a staging area (bottom) with 18 baskets and a target area (top) with 12 empty cells arranged in 2 rows of 6.
- The **Matcher** clicks baskets in the staging area to place them in the target area, matching the exact order that baskets appear on the director's screen.
- The goal is for the matcher to correctly reproduce the director's basket sequence, using only the director's descriptions.

## Experimental Design

### Staging Area

- Located at the bottom of the matcher's interface
- Contains all 18 baskets in a 3x6 grid layout
- Baskets are clickable and become greyed out when selected
- Selected baskets appear in the target area in the order they were clicked

### Target Area

- Located above the staging area
- Contains 12 empty cells arranged in 2 rows of 6
- Fills with selected baskets in the order they were clicked from the staging area
- Represents the matcher's attempt to reproduce the director's basket sequence

## Running and Managing Sessions

- Start the server:

  - Activate env and run: `otree devserver`
  - Open `http://localhost:8000`
- Number of rounds: 3. Each round re-randomizes the matcher's staging area (18 baskets: 12 from director’s grid + 6 distractors) and preserves the director's 2x6 grid.

## Collecting Results (Experimenter)

You have 2 ways to retrieve results after participants finish:

1) Admin report (web UI, one-click export)

   - Go to `http://localhost:8000/admin` → Sessions → your session → Monitor → `referential_task` → choose a round
   - The Admin Report shows per-group summary and provides download buttons:
     - Download JSON: compact JSON with `round_number`, per-group `correct_sequence`, `submitted_sequence`, `accuracy`, `submitted_at`, and `matcher_id_in_group`.
     - Download CSV: compact CSV with the same fields for the selected round.
2) CSV export (full data)

   - In the session page, click “Data / Download”. You will get:
     - Player CSV: includes `sequence_accuracy`, `selected_sequence`, `task_completed`, `completion_time`, `grid_messages`.
     - Group CSV: includes `shared_grid`, `target_baskets`, `matcher_sequence`.
   - Filter to round 3 or aggregate as needed.

Note: Participants never see accuracy; it is only visible in the admin/exports.

The experiment is run in real time, with both participants interacting through a visually rich, modern web interface.

## Features

- **Real-time chat** between director and matcher, with a clean, modern UI.
- **Draggable and clickable grid** of basket images for easy selection.
- **Preset or randomized basket grids** for each round (configurable).
- **Results page** showing performance and selections.

## Technology Stack

- **oTree** (Python/Django-based) for experiment logic and real-time communication
- **JavaScript** for interactive UI (see `_static/js/`)
- **Bootstrap** for responsive, modern styling
- **SQLite** (default) for local data storage

## Setup Instructions

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/Human-VLM-Game.git
   cd Human-VLM-Game
   ```
2. **Set up your Python environment** (recommended: conda)

   ```bash
   conda create -n langviscog python=3.11
   conda activate langviscog
   pip install -r requirements.txt
   ```
3. **Run the oTree server**

   ```bash
   otree devserver
   ```

   Or, if using a Procfile (e.g., for Heroku):

   ```bash
   otree runprodserver 8000
   ```
4. **Access the experiment**

   Open your browser and go to `http://localhost:8000/`.
5. **Static files**

   Basket images are in `_static/images/` and `baskets-internet/`. CSS and JS are in `_static/css/` and `_static/js/`.

## Human–Human Mode

This branch (`human-human`) runs the referential task **purely as a human–human interaction**. There is **no human–AI / AI–human mode** nor **AI–AI mode** in this branch — both roles are always played by real participants.

For the human–AI / AI–human experiment, switch to the **`main`** branch; for the AI–AI experiment, switch to the **`ai-ai`** branch (see the branch table at the top of this README).

In this setup, each oTree group contains exactly **two human participants**:

- **P1 = Director** and **P2 = Matcher**.
- The Director and Matcher views, chat, and feedback are all driven by the two humans; no AI back-end and no OpenAI API key are involved.

No API key or extra configuration is needed — just install dependencies and run the oTree server (see **Setup Instructions** above), then create a session for one of the configs below.

### Session configurations

On the oTree demo page (`http://localhost:8000/`) this branch exposes **two-human session configs** (all with `num_demo_participants = 2`, so each session produces two participant links — one Director, one Matcher):

**Grid director view** (Director sees the full 2x6 grid at once):

- `referential_task_set1` — Basket Set 1.
- `referential_task_set2` — Basket Set 2.
- `referential_task_set3` — Basket Set 3.
- `referential_task_set4` — Basket Set 4.
- `referential_task_set5` — Basket Set 5.

**Sequential director view** (Director reveals baskets one at a time):

- `referential_task_sequential` — Basket Set 1.
- `referential_task_sequential_set2` — Basket Set 2.
- `referential_task_sequential_set3` — Basket Set 3.
- `referential_task_sequential_set4` — Basket Set 4.
- `referential_task_sequential_set5` — Basket Set 5.

**Other:**

- `referential_task_shapes_demo` — single-round shapes demo (colored shapes instead of baskets; roles assigned to the two humans).

## Preset Grid Configurations

To use preset basket grids for specific rounds, edit the file `referential_task/grids_presets.json`.

- Each entry in the `rounds` list specifies a round and the 12 basket images to use.
- If a round is not specified, the game will use a random grid for that round.

Example structure:

```
{
  "rounds": [
    {
      "round": 1,
      "baskets": [
        "001.png", "002.png", "003.png", "004.png",
        "005.png", "006.png", "007.png", "008.png",
        "009.png", "010.png", "011.png", "012.png"
      ]
    },
    {
      "round": 2,
      "baskets": [ ... ]
    }
    // Add more rounds as needed
  ]
}
```

- The `baskets` list must contain exactly 12 filenames (from the `images/` directory, without the path).

## Customization

- To change the basket images, add/remove files in the `_static/images/` or `baskets-internet/` folders and update the presets as needed.
- To modify the UI, edit the templates in `referential_task/templates/referential_task/` and the JS/CSS in `_static/js/` and `_static/css/`.

## Analysis & Helper Scripts

The `scripts/` directory contains useful utilities for working with the experimental data:

- `clean_all_apps_wide.py`: Cleans/normalizes the wide-format all-apps export.
- `export_round_level_csv.py`: Exports round-level results to CSV.
- `format_chat_transcript.py`: Formats chat logs into readable transcripts.

## Contact

For questions or contributions, please open an issue or contact the maintainer.

### Admin Report

The admin report now summarizes each group's accuracy and provides CSV/JSON downloaders (AdminReport page).
