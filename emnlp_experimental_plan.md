# EMNLP 2026 Experimental Roadmap: Multi-Agent Pragmatics

## 1. The Core Narrative

Our ACL 2026 paper established that LLMs fail to build "common ground" in multi-turn referential games, often getting stuck in repetitive clarification loops due to an inability to leverage lexical entrainment.

For EMNLP, we hypothesize that this failure stems from **cognitive overload**. Single-agent models struggle to simultaneously act as conversational partners and maintain a coherent, evolving "Theory of Mind" (ToM) across long dialogue contexts.

**Our Contribution:** We propose a modular, **Multi-Agent Pragmatic Architecture** that relieves this cognitive load. By externalizing ToM into dedicated asynchronous tracking and reflection agents, we achieve human-like lexical entrainment and robust error recovery.2. The 3-Agent Architecture (`v6` Strategy)

Instead of relying on a single Conversational Agent, our system utilizes three specialized components:

# A. The Conversational Agent (Actor)

- **Role**: Rapidly generates the next conversational utterance or selection based on the immediate context and the synthesized state provided by the other agents.
- **Prompt Strategy**: Natural Entrainment via Definite Determiners (the `v6` base prompt).

### B. The Common Ground Extractor (Intra-Round Tracker)

- **Role**: Runs asynchronously on every turn to summarize the live dialogue history into a noise-free JSON Pragmatic State.
- **Function**: It extracts the agreed-upon nicknames (lexical entrainment), identifies pending uncertainties, and tracks what the partner currently believes. This distills a massive chat history into a highly salient ToM scratchpad that is injected into the Conversational Agent's prompt.

### C. The Reflection Agent (Inter-Round Repair)

- **Role**: Runs _between_ rounds. It receives the full dialogue history of the preceding round alongside the ground-truth feedback (which baskets were matched incorrectly).
- **Function**: It diagnoses communication breakdowns based solely on the dialogue and failure points. It outputs explicit **Directives** that are prepended to the system prompt for the next round, enabling sophisticated, cross-round repair strategies.

## 3. Experimental Baselines & Ablation

To empirically prove the value of our modular architecture, we will run batch experiments comparing three distinct configurations:

1. **Single-Agent, No Tracking (`v8`)**: The "bare minimum CoT" baseline. This represents the standard approach where an LLM is given the task rules and asked to play.
2. **Single-Agent, Explicit Tracking (`v9`)**: We force the primary Conversational Agent to explicitly write out a `common_ground` JSON scratchpad before speaking. This tests whether simply prompting for ToM is sufficient, or if the single-agent still suffers from cognitive overload.
3. **Multi-Agent Modular Tracking (`v6` + Reflection)**: Our primary contribution. The tracking and reflection are offloaded to dedicated agents.

## 4. Metrics for Success

We will evaluate the strategies across these key metrics:

1. **Placement Accuracy**: The primary success metric (how many baskets out of 12 are matched correctly per round).
2. **Lexical Compression Rate**: Does the Multi-Agent system successfully shorten descriptions (e.g., from 15 words in Round 1 to 2 words in Round 4)?
3. **Repair Efficacy**: When a mistake is made in Round N, what is the probability that the specific basket is described successfully in Round N+1? (The Reflection Agent should vastly improve this).

---

## 5. Execution Guide

To generate high-volume empirical data for the ablation study, you can use the headless batch runner.

### Running the Standard v6 Extractor (No Reflection)

This runs the core contribution (the live Common Ground Extractor) without inter-round reflection:

```bash
python scripts/run_batch_experiment.py --sessions 10 --prompt-strategy v6 --model gpt-4o-mini --session-prefix v6_standard
```

### Running the Full Multi-Agent Paradigm (With Reflection)

This enables the inter-round Reflection Agent to generate directives after each round:

```bash
python scripts/run_batch_experiment.py --sessions 10 --prompt-strategy v6 --model gpt-4o-mini --session-prefix v6_reflect --use-reflection
```

### Running the Baselines

```bash
# v8 Baseline (No Tracking)
python scripts/run_batch_experiment.py --sessions 10 --prompt-strategy v8 --model gpt-4o-mini --session-prefix v8_base

# v9 Baseline (Single-Agent Tracking)
python scripts/run_batch_experiment.py --sessions 10 --prompt-strategy v9 --model gpt-4o-mini --session-prefix v9_single
```

The batch runner will automatically bypass the web UI, complete all 4 rounds, generate perceptions, and dump the structured JSON into `data/experiments/{YYYY-MM-DD}_{prompt_strategy}/` for offline analysis.
