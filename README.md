# Human-LVLM Director-Matcher Game

Code and data for:

> **LVLMs and Humans Ground Differently in Referential Communication**
> Peter Zeng, Weiling Li, Amie J. Paige, Zhengxiang Wang, Panagiotis Kaliosis,
> Dimitris Samaras, Gregory Zelinsky, Susan E. Brennan, and Owen Rambow.
> *Proceedings of ACL 2026* (Long Papers), pages 9061–9087.
> [aclanthology.org/2026.acl-long.410](https://aclanthology.org/2026.acl-long.410/)

This repository contains an interactive director-matcher game experiment implemented with [oTree](https://www.otree.org/), used to study communication and reference in a collaborative visual task. The paper reports a factorial design over director-matcher pairings (human-human, human-AI, AI-human, AI-AI) matching pictures of baskets, objects with no conventionally lexicalized labels.

## Corpus

The corpus of 356 dialogues (89 pairs over 4 rounds each) is available on
[Google Drive](https://drive.google.com/drive/folders/1y4utpf5zErb7VKe8qW5U9I4AMlFd5uxx?usp=sharing).

We intend to move the corpus to an archival host with a DOI so that it has a
stable, citable location; this README will be updated when that happens.

## Which branch runs which experiment?

Each pairing lives on its own branch. **Check out the branch matching the pairing you want to run.** Commit SHAs are given so you can pin an exact version.

| Branch | Pairing / purpose | Last updated | Pinned commit |
| ------ | ----------------- | ------------ | ------------- |
| **`main`** *(you are here)* | **Human–AI / AI–Human.** One human paired with a VLM partner (GPT-5.2). The human plays Director *or* Matcher; the AI plays the other role. | 2026-07-01 | [`d7b5cf3`](https://github.com/peterzeng/lvlms-referential-game/tree/d7b5cf3ccd53cf5bfbecd13be8e2299c45f2b9f7) |
| `human-human` | **Human–Human.** Two human participants, one Director and one Matcher, no AI. Most recent version of the human-human pipeline. | 2026-07-01 | [`be03c82`](https://github.com/peterzeng/lvlms-referential-game/tree/be03c821af456202437069271dad8d0d4bb3400f) |
| `ai-ai2` | **AI–AI.** Both roles played by the VLM. Supersedes `ai-ai`; prefer this branch. | 2026-05-13 | [`fd7614e`](https://github.com/peterzeng/lvlms-referential-game/tree/fd7614e58b64f903e34e83221c6d8ddca1878322) |
| `ai-ai` | **AI–AI (earlier).** Retained for provenance. | 2026-03-02 | [`5167820`](https://github.com/peterzeng/lvlms-referential-game/tree/5167820d89232baae75943c7925e055a9eb946be) |
| `analysis` | Analysis notebooks and scripts (accuracy, efficiency, lexical overlap). | 2026-04-22 | [`85d80b1`](https://github.com/peterzeng/lvlms-referential-game/tree/85d80b1e7c1c284e4db040164566f232d6619f68) |
| `emnlp` | Follow-up prompting experiments; **now maintained separately** (see below). | 2026-05-24 | [`59d4364`](https://github.com/peterzeng/lvlms-referential-game/tree/59d43645ee9039b89e6881c9af14177300a49906) |

## Related repository

The follow-up study comparing implicit and explicit prompting strategies has its
own repository: **[implicit-vs-explicit-prompting](https://github.com/peterzeng/implicit-vs-explicit-prompting)**.
It was split out from the `emnlp` branch above.

## License

Code in this repository is MIT licensed; see [`LICENSE`](LICENSE). The corpus is
released separately (see **Corpus** above) and is not covered by the code
license. Human participants gave informed consent, and the released dialogues
contain no participant identifiers.

---

The rest of this README documents the **`main` (Human–AI / AI–Human)** branch.

## Experiment Overview

In this game, two participants are paired as the **Director** and the **Matcher**. Over 4 rounds:

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
- Number of rounds: 4 (`Constants.num_rounds` in `referential_task/models.py`). Each round re-randomizes the matcher's staging area (18 baskets: 12 from director’s grid + 6 distractors) and preserves the director's 2x6 grid.

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
   - Filter to round 4 (the final round) or aggregate as needed.

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
   git clone https://github.com/peterzeng/lvlms-referential-game.git
   cd lvlms-referential-game
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

## Human–AI and AI–Human Mode and GPT‑5.2 Integration

This branch (`main`) runs the referential task **purely as a human–VLM (human–AI) or AI–human interaction**. There is **no human–human mode** nor **AI–AI mode** in this branch.

For the human–human experiment, switch to the **`human-human`** branch; for the AI–AI experiment, switch to the **`ai-ai`** branch (see the branch table at the top of this README).

In this setup, each oTree group contains exactly **one human participant**.

- The “partner” is always an AI agent (a VLM back-end using OpenAI's `gpt-5.2` model).
- The human UI (Director/Matcher views, chat, feedback) remains the same as in the original human–human setup, but the other role is always played by the AI.

To enable the AI partner:

1. Install dependencies (includes the OpenAI Python client):

   ```bash
   pip install -r requirements.txt
   ```
2. Set your OpenAI API key in the environment (for example on macOS/Linux):

   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

   On Windows PowerShell:

   ```powershell
   $env:OPENAI_API_KEY="sk-..."
   ```
3. Run the oTree server as usual and create a session for `referential_task`.

If no API key is set or the OpenAI client is unavailable, the experiment will still run, but the partner will not send AI-generated replies.

### Choosing the human's role (Director vs Matcher)

On the oTree demo page (`http://localhost:8000/`) this branch exposes **single-human session configs** (all with `num_demo_participants = 1`, so there is exactly one human link per session; the partner is always the AI bot):

- `referential_task_grid_human_matcher` — **Human = Matcher, AI = Director** (grid view, Set 5, v1 prompt).
- `referential_task_grid_human_matcher_v2` — **Human = Matcher, AI = Director** (grid view, Set 5, v2 prompt).
- `referential_task_grid_human_matcher_v3` — **Human = Matcher, AI = Director** (grid view, Set 5, v3 prompt).
- `referential_task_grid_human_director` — **Human = Director, AI = Matcher** (grid view, Set 5, v1 prompt).
- `referential_task_grid_human_director_v2` — **Human = Director, AI = Matcher** (grid view, Set 5, v2 prompt).
- `referential_task_grid_human_director_v3` — **Human = Director, AI = Matcher** (grid view, Set 5, v3 prompt).
- `referential_task_shapes_demo` — single-round shapes demo (colored shapes instead of baskets; human role randomized).

All of these use the same **visual 12‑basket grid** as context for the AI whenever images are available; the differences between v1/v2/v3 are in how the AI is instructed to reason and respond.

### Prompt strategy variants (v1 vs v2 vs v3)

For the basket tasks, the `prompt_strategy` controls how the AI partner is prompted. The main variants are:

- **`v1` – Simple baseline**

  - Short, generic system prompt that just explains the role (Director or Matcher) and high-level task.
  - No explicit knowledge-base (KB) hints and no structured reasoning format.
  - Still sees the full 12‑basket grid visually via GPT‑4o.
- **`v2` – Weiling-style rich prompt**

  - Detailed, role-specific system prompt with round number and game-state context.
  - Optionally includes KB-based basket hints when `use_kb=True` in the session config.
  - Emphasizes distinctive visual features, comparative language, and avoiding basket IDs.
  - Also sees the same visual 12‑basket grid as v1.
- **`v3` – CoT / JSON reasoning on top of v2**

  - Uses the same rich Weiling-style system prompt as v2 (including optional KB hints).
  - Adds an extra instruction that the model must reply in **strict JSON** with:
    - `"reasoning"` – a structured, step-by-step discriminative analysis.
    - `"utterance"` – a single natural-language message shown to the human.
  - Server-side code parses out `utterance` for the chat UI and can optionally log the full `reasoning` JSON for analysis.
  - Also uses the same visual 12‑basket grid as v1 and v2.

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

The `scripts/` directory contains useful utilities for working with the experimental data and development:

- `calculate_round_times.py`: Calculates timing metrics for each round from exported data.
- `format_chat_transcript.py`: Formats chat logs into readable transcripts.
- `test_director_grid.py`: Local testing script for the director's grid view.
- `generate_knowledge_base.py`: Helper script to generate knowledge base JSON data for the AI.

## Contact

For questions or contributions, please open an issue or contact the maintainer.

### Admin Report

The admin report now summarizes each group's accuracy and provides CSV/JSON downloaders (AdminReport page).
