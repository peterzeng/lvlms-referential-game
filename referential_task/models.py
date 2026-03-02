from otree.api import (
    models,
    widgets,
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    Currency as c,
    currency_range,
)
import json


doc = """
Your app description
"""


class Constants(BaseConstants):
    name_in_url = 'referential_task'
    # In this branch we run exclusively human–AI sessions.
    # oTree does not allow players_per_group = 1, so we set it to None
    # and form one-player groups manually in Subsession.creating_session
    # using set_group_matrix.
    players_per_group = None
    num_rounds = 4


class Subsession(BaseSubsession):
    def creating_session(self):
        """Per-round setup for human–VLM (human–AI) and AI vs AI sessions.

        GROUPING:
        - Each participant is placed in their own one-player group.
        - This is critical for both human–AI mode (where each human plays with an AI)
          and AI vs AI mode (where each observer watches their own AI pair).
        - Round 1: explicitly set one-player groups via set_group_matrix.
        - Round 2+: copy grouping from round 1 via group_like_round.

        ROLES:
        - In human–AI mode: the human's role is set via config or randomized.
        - In AI vs AI mode: both director and matcher are AIs; the human is just observing.

        IMPORTANT: This method runs ONCE when the session is created.
        All participant slots already exist at this point, so we can safely
        iterate over all players and assign them to separate groups.
        """
        import random
        import logging

        # Check if this is an AI vs AI session
        try:
            is_ai_vs_ai = bool(self.session.config.get('ai_vs_ai_mode', False))
        except Exception:
            is_ai_vs_ai = False

        # Ensure that each participant is in their own one-player group.
        # With players_per_group = None, we must define the group matrix
        # explicitly on round 1. Later rounds copy this grouping.
        if self.round_number == 1:
            players = self.get_players()

            # CRITICAL: Create one group per player to ensure isolation.
            # This prevents the bug where all participants end up in the same group.
            group_matrix = [[p] for p in players]
            self.set_group_matrix(group_matrix)

            logging.info(
                "[GROUPING] Round 1: Created %d one-player groups for %d players (ai_vs_ai=%s)",
                len(group_matrix), len(players), is_ai_vs_ai
            )

            # Initial role assignment and grid creation
            for group in self.get_groups():
                players_in_group = group.get_players()
                if not players_in_group:
                    continue
                player = players_in_group[0]

                # In AI vs AI mode, the human is just an observer - set a marker role
                if is_ai_vs_ai:
                    # For AI vs AI, we mark the player as "observer" but they don't
                    # actively participate. The AI Director and Matcher roles are
                    # handled by the AI agents, not the human player.
                    player.player_role = 'observer'
                    player.participant.vars['role'] = 'observer'
                    player.participant.vars['partner_role'] = None  # No human partner
                else:
                    # Determine the human's role for this session.
                    # Prefer an explicit session config override, otherwise randomize.
                    try:
                        cfg_role = self.session.config.get('human_role')
                    except Exception:
                        cfg_role = None
                    if isinstance(cfg_role, str):
                        cfg_role = cfg_role.strip().lower()
                    if cfg_role not in ['director', 'matcher']:
                        cfg_role = random.choice(['director', 'matcher'])
                    role = cfg_role

                    player.player_role = role
                    player.participant.vars['role'] = role

                    # Store AI partner role metadata for downstream use (e.g., exports)
                    player.participant.vars['partner_role'] = (
                        'matcher' if role == 'director' else 'director'
                    )

                # Persist basic identifiers for convenience/analysis
                player.participant.vars['group_id'] = getattr(group, 'id', None)
                player.participant.vars['id_in_group'] = player.id_in_group

                # Create the shared grid for this group's first round
                group.create_shared_grid(round_number=self.round_number)

                logging.info(
                    "[GROUPING] Group %s: player=%s role=%s",
                    getattr(group, 'id', None),
                    getattr(player.participant, 'code', None),
                    player.player_role
                )
        else:
            # Keep groups consistent across rounds (one player per group)
            self.group_like_round(1)

            # Restore roles from participant vars if needed
            for group in self.get_groups():
                for player in group.get_players():
                    if not player.field_maybe_none('player_role'):
                        stored_role = player.participant.vars.get('role')
                        if stored_role:
                            player.player_role = stored_role

            # Create/refresh the shared grid for this round
            for group in self.get_groups():
                group.create_shared_grid(round_number=self.round_number)


class Group(BaseGroup):
    # Store the shared grid that both Director and Matcher see
    shared_grid = models.LongStringField(blank=True, initial='[]')
    
    # Store the target basket(s) that Director needs to communicate
    target_baskets = models.LongStringField(blank=True, initial='[]')
    
    # Store Matcher's sequence selections
    matcher_sequence = models.LongStringField(blank=True, initial='[]')

    # Incremental AI matcher sequence (researcher/debug use only).
    # This tracks the AI's growing 12‑basket guess across the dialogue,
    # so we can visualize its per‑turn placements in the debug view.
    ai_partial_sequence = models.LongStringField(blank=True, initial='[]')

    # Store AI partner chat messages (shared at the group level)
    # This mirrors the structure of Player.grid_messages so we can reuse
    # transcript-building and export logic by treating these as partner messages.
    ai_messages = models.LongStringField(blank=True, initial='[]')
    # Optional: store AI partner reasoning logs for V3 CoT runs
    # This is a JSON list of objects, each containing:
    # - round_number, timestamp, strategy_name
    # - human_role, ai_role
    # - reasoning (as returned by the model)
    # - utterance (final message shown to the human)
    # - raw_text (raw model output before parsing)
    ai_reasoning_log = models.LongStringField(blank=True, initial='[]')

    # AI's perceptions of the human partner (generated at end of experiment)
    # Mirrors the human's partner_* fields but from the AI's perspective
    ai_partner_capable = models.IntegerField(blank=True, null=True)
    ai_partner_helpful = models.IntegerField(blank=True, null=True)
    ai_partner_understood = models.IntegerField(blank=True, null=True)
    ai_partner_adapted = models.IntegerField(blank=True, null=True)
    ai_collaboration_improved = models.IntegerField(blank=True, null=True)
    ai_partner_comment = models.LongStringField(blank=True)
    # Raw JSON response from AI for debugging/analysis
    ai_partner_perceptions_raw = models.LongStringField(blank=True)

    # AI vs AI mode: Director's perceptions of Matcher
    ai_director_partner_capable = models.IntegerField(blank=True, null=True)
    ai_director_partner_helpful = models.IntegerField(blank=True, null=True)
    ai_director_partner_understood = models.IntegerField(blank=True, null=True)
    ai_director_partner_adapted = models.IntegerField(blank=True, null=True)
    ai_director_collaboration_improved = models.IntegerField(blank=True, null=True)
    ai_director_partner_comment = models.LongStringField(blank=True)
    ai_director_perceptions_raw = models.LongStringField(blank=True)

    # AI vs AI mode: Matcher's perceptions of Director
    ai_matcher_partner_capable = models.IntegerField(blank=True, null=True)
    ai_matcher_partner_helpful = models.IntegerField(blank=True, null=True)
    ai_matcher_partner_understood = models.IntegerField(blank=True, null=True)
    ai_matcher_partner_adapted = models.IntegerField(blank=True, null=True)
    ai_matcher_collaboration_improved = models.IntegerField(blank=True, null=True)
    ai_matcher_partner_comment = models.LongStringField(blank=True)
    ai_matcher_perceptions_raw = models.LongStringField(blank=True)

    def assign_roles(self):
        """Assign Director and Matcher roles to players"""
        import random
        players = self.get_players()
        if len(players) >= 2:
            shuffled_players = players[:]
            random.shuffle(shuffled_players)
            shuffled_players[0].player_role = 'director'
            shuffled_players[1].player_role = 'matcher'
    
    def create_shared_grid(self, round_number=None):
        """Create a grid for the task.

        - Default: 2x6 baskets (12) using presets or random images.
        - Shapes demo: 5 colored shapes (no images) for tutorial recording.
        """
        import random
        import os
        # Shapes demo mode (feature-flagged via session config)
        try:
            view_mode = str(self.session.config.get('director_view', 'grid'))
        except Exception:
            view_mode = 'grid'

        if view_mode == 'shapes_demo':
            # Define available shapes and colors
            shapes = ['circle', 'square', 'triangle', 'star', 'hexagon']
            colors = ['red', 'blue', 'green', 'yellow', 'purple', 'orange']
            # Build pool of unique (color, shape) combos
            pool = [(c, s) for c in colors for s in shapes]
            random.shuffle(pool)
            # Pick 5 unique combos for the director sequence
            selected = pool[:5]
            grid = []
            for idx, (color, shape) in enumerate(selected, start=1):
                grid.append({
                    'position': f"{idx}",
                    'row': 1,
                    'col': idx,
                    'image': f"shape:{color}:{shape}",  # token used for server-side equality checks
                    'basket_id': idx,
                    'shape': shape,
                    'color': color,
                })
            # No specific targets; director communicates the full 5-sequence
            self.shared_grid = json.dumps(grid)
            self.target_baskets = json.dumps([])
            # Clear any prior matcher sequence
            self.matcher_sequence = json.dumps([])
            self.ai_partial_sequence = json.dumps([])
            return grid, []
        # Choose preset file based on session config `basket_set` (supports 1, 2, 3)
        try:
            set_num = int(self.session.config.get('basket_set', 1))
        except Exception:
            set_num = 1
        if set_num == 2:
            preset_filename = 'grids_presets2.json'
        elif set_num == 3:
            preset_filename = 'grids_presets3.json'
        elif set_num == 4:
            preset_filename = 'grids_presets4.json'
        elif set_num == 5:
            preset_filename = 'grids_presets5.json'
        else:
            preset_filename = 'grids_presets1.json'
        preset_path = os.path.join(os.path.dirname(__file__), preset_filename)
        grid = []
        targets = []
        use_preset = False
        if round_number is None:
            round_number = 1  # fallback
        # Try to load preset
        try:
            with open(preset_path, 'r') as f:
                presets = json.load(f)
            for round_cfg in presets.get('rounds', []):
                if round_cfg.get('round') == round_number:
                    basket_files = [f'images/{img}' for img in round_cfg['baskets']]
                    # Build grid
                    position_index = 0
                    for row in range(1, 4):
                        for col in range(1, 5):
                            grid.append({
                                'position': f"{row}{col}",
                                'row': row,
                                'col': col,
                                'image': basket_files[position_index],
                                'basket_id': position_index + 1
                            })
                            position_index += 1
                    # No explicit targets in preset; keep empty so director communicates full sequence
                    use_preset = True
                    break
        except Exception:
            pass
        if not use_preset:
            # Fallback to random
            all_images = [f'images/{i:03d}.png' for i in range(1, 71)]
            selected_images = random.sample(all_images, 12)
            grid = []
            position_index = 0
            for row in range(1, 4):
                for col in range(1, 5):
                    grid.append({
                        'position': f"{row}{col}",
                        'row': row,
                        'col': col,
                        'image': selected_images[position_index],
                        'basket_id': position_index + 1
                    })
                    position_index += 1
            # Randomly select 1 basket as target
            target_index = random.choice(range(12))
            targets = [grid[target_index]]
        self.shared_grid = json.dumps(grid)
        self.target_baskets = json.dumps(targets)
        # Reset matcher/AI sequences at the start of each round
        self.matcher_sequence = json.dumps([])
        self.ai_partial_sequence = json.dumps([])
        return grid, targets


class Player(BasePlayer):
    # Prolific participant ID (collected at start)
    prolific_participant_id = models.StringField(blank=True)
    
    # Experiment timing (stored at participant level for persistence)
    experiment_start_time = models.StringField(blank=True)  # ISO timestamp when experiment started
    experiment_end_time = models.StringField(blank=True)    # ISO timestamp when experiment ended
    
    # Player role: 'director', 'matcher', or 'observer' (AI vs AI mode)
    player_role = models.StringField(choices=['director', 'matcher', 'observer'], blank=True)
    
    # Communication messages for grid task
    grid_messages = models.LongStringField(blank=True, initial='[]')
    
    # Readable chat transcript (auto-populated from grid_messages and partner messages)
    chat_transcript = models.LongStringField(blank=True)
    
    # Store Matcher's basket sequence (list of basket positions in order)
    selected_sequence = models.LongStringField(blank=True, initial='[]')
    
    # Task completion status
    task_completed = models.BooleanField(initial=False)
    
    # Track if sequence is correct (calculated after Matcher submits)
    sequence_accuracy = models.FloatField(blank=True)
    
    # Store timestamp when task was completed
    completion_time = models.StringField(blank=True)
    
    # Track if user left the waiting room (navigated away or clicked "Return to Prolific")
    left_waiting_room = models.StringField(blank=True)  # ISO timestamp
    waiting_room_exit_reason = models.StringField(blank=True)  # 'prolific_button_click', 'page_hidden', 'page_unload'
    prolific_exit_clicked = models.StringField(blank=True)  # ISO timestamp when "Return to Prolific" button was clicked

    # Attention check responses (round 1 only - DEPRECATED, keeping for backward compatibility)
    attention_q1 = models.StringField(
        choices=[
            ['A', 'Red'],
            ['B', 'Blue'],
            ['C', 'Green'],
            ['D', 'Yellow'],
        ],
        widget=widgets.RadioSelect,
        blank=True,
    )
    attention_q2 = models.StringField(
        choices=[
            ['A', 'Cat'],
            ['B', 'Dog'],
            ['C', 'Duck'],
            ['D', 'Giraffe'],
        ],
        widget=widgets.RadioSelect,
        blank=True,
    )
    attention_q3 = models.StringField(
        choices=[
            ['A', '3'],
            ['B', '5'],
            ['C', '7'],
            ['D', '9'],
        ],
        widget=widgets.RadioSelect,
        blank=True,
    )

    # Round-specific attention check (one question per round, rounds 1-3)
    attention_round_q = models.StringField(
        choices=[
            ['A', 'Option A'],
            ['B', 'Option B'],
            ['C', 'Option C'],
            ['D', 'Option D'],
        ],
        widget=widgets.RadioSelect,
        label='',
    )

    # Comprehension check (shown on TaskInstructions page)
    comprehension_check = models.StringField(
        choices=[
            ['a', 'The Director'],
            ['b', 'The Matcher'],
            ['c', 'Both players must submit their answers'],
            ['d', 'The answers are submitted automatically'],
        ],
        widget=widgets.RadioSelect,
        label='Based on the instructions you have just read, who is responsible for submitting the final sequence of 12 baskets at the end of each round?',
        blank=True,
    )

    # Post-task: Partner-specific perceptions (Jakesch et al., 2023)
    partner_capable = models.IntegerField(
        choices=[1, 2, 3, 4, 5],
        label='My partner was capable of doing their task',
        widget=widgets.RadioSelectHorizontal,
    )
    partner_helpful = models.IntegerField(
        choices=[1, 2, 3, 4, 5],
        label='My partner was helpful to me for completing my task',
        widget=widgets.RadioSelectHorizontal,
    )
    partner_understood = models.IntegerField(
        choices=[1, 2, 3, 4, 5],
        label='My partner understood what I was trying to communicate',
        widget=widgets.RadioSelectHorizontal,
    )
    partner_adapted = models.IntegerField(
        choices=[1, 2, 3, 4, 5],
        label='My partner adapted to the way I communicated over time',
        widget=widgets.RadioSelectHorizontal,
    )
    collaboration_improved = models.IntegerField(
        choices=[1, 2, 3, 4, 5],
        label='Our collaboration improved over time',
        widget=widgets.RadioSelectHorizontal,
    )
    partner_comment = models.LongStringField(
        label='Please comment about how your partner did the task.',
    )

    # Partner seemed human vs AI slider + explanation
    partner_human_vs_ai = models.IntegerField(
        min=0,
        max=100,
        label='My partner seemed… (0 = Human, 100 = AI chatbot)',
    )
    partner_human_vs_ai_why = models.LongStringField(
        label='Why?',
    )

    # Post-task: General AI experience and use
    ai_familiarity = models.StringField(
        choices=[
            ['not_at_all', 'Not at all familiar'],
            ['slightly', 'Slightly familiar'],
            ['moderately', 'Moderately familiar'],
            ['very', 'Very familiar'],
            ['extremely', 'Extremely familiar'],
        ],
        label='How familiar are you with AI (such as ChatGPT, Gemini, or others)?',
        widget=widgets.RadioSelect,
    )

    ai_usage_frequency = models.StringField(
        choices=[
            ['daily', 'Daily'],
            ['weekly', 'Weekly'],
            ['monthly', 'Monthly'],
            ['rarely', 'Rarely'],
            ['never', 'Never'],
        ],
        label='How often do you use ChatGPT/other chat-based AIs?',
        widget=widgets.RadioSelect,
    )

    ai_used_for_task = models.StringField(
        choices=[
            ['yes', 'Yes'],
            ['no', 'No'],
        ],
        label='Did you use ChatGPT/other chat-based AIs to help you complete today’s task?',
        widget=widgets.RadioSelect,
    )


# Custom export for oTree Data page
# Produces one row per player per round including:
# - Combined chat log (both players) with timestamps
# - Matcher's submitted order (sequence) and accuracy
# - End-of-experiment fields only on final round to reduce clutter
def custom_export(players):
    """oTree hook: customize the app's CSV export in the Data tab.

    Columns (per-round):
    - session_code, round_number, group_id, participant_code, role
    - prolific_participant_id: Prolific ID entered at the start
    - experiment_start_time: ISO timestamp when participant started
    - chat_transcript: readable conversation transcript with timestamps
    - chat_log_json: combined messages sorted by timestamp (JSON)
    - matcher_sequence_json: sequence submitted by matcher
    - sequence_accuracy: matcher's accuracy (%)
    - completion_time: ISO timestamp when task completed
    - attention_round_q, attention_round_correct: attention check data

    Columns (final round only - empty for rounds 1-3):
    - experiment_end_time, experiment_duration_minutes: timing summary
    - Partner perceptions: partner_capable, partner_helpful, etc.
    - AI experience: ai_familiarity, ai_usage_frequency, ai_used_for_task
    - AI partner perceptions: ai_partner_capable, ai_partner_helpful, etc.
    - ai_reasoning_log: CoT reasoning log (JSON)
    """
    # Header row
    yield [
        'session_code',
        'round_number',
        'group_id',
        'participant_code',
        'prolific_participant_id',
        'role',
        # Experiment timing (start always shown, end only on final round)
        'experiment_start_time',
        'experiment_end_time',
        'experiment_duration_minutes',
        # Per-round task data
        'chat_transcript',
        'chat_log_json',
        'matcher_sequence_json',
        'sequence_accuracy',
        'completion_time',
        # Attention check (per round)
        'attention_round_q',
        'attention_round_correct',
        # Post-task survey (final round only)
        'partner_capable',
        'partner_helpful',
        'partner_understood',
        'partner_adapted',
        'collaboration_improved',
        'partner_comment',
        'partner_human_vs_ai',
        'partner_human_vs_ai_why',
        'ai_familiarity',
        'ai_usage_frequency',
        'ai_used_for_task',
        # AI data (final round only)
        'ai_reasoning_log',
        'ai_partner_capable',
        'ai_partner_helpful',
        'ai_partner_understood',
        'ai_partner_adapted',
        'ai_collaboration_improved',
        'ai_partner_comment',
        # AI vs AI mode perceptions (final round only)
        'ai_director_partner_capable',
        'ai_director_partner_helpful',
        'ai_director_partner_understood',
        'ai_director_partner_adapted',
        'ai_director_collaboration_improved',
        'ai_director_partner_comment',
        'ai_matcher_partner_capable',
        'ai_matcher_partner_helpful',
        'ai_matcher_partner_understood',
        'ai_matcher_partner_adapted',
        'ai_matcher_collaboration_improved',
        'ai_matcher_partner_comment',
    ]

    for p in players:
        try:
            # Messages from self
            my_msgs = json.loads(p.grid_messages or '[]')
        except Exception:
            my_msgs = []

        # Messages from human partner (if any; not used in human–AI mode)
        partner = p.get_others_in_group()[0] if p.get_others_in_group() else None
        try:
            partner_msgs = json.loads(partner.grid_messages or '[]') if partner else []
        except Exception:
            partner_msgs = []

        # Messages from AI partner (group-level)
        try:
            ai_msgs = json.loads(p.group.ai_messages or '[]')
        except Exception:
            ai_msgs = []

        # Tag messages with sender id for clarity (non-destructive)
        def _tag(msg_list, sender_role):
            tagged = []
            for m in (msg_list or []):
                if isinstance(m, dict):
                    tagged.append({
                        'text': m.get('text'),
                        'timestamp': m.get('timestamp'),
                        'server_ts': m.get('server_ts'),
                        # Prefer the stored sender_role (for AI messages) but
                        # fall back to the provided default for backwards
                        # compatibility with legacy human–human data.
                        'sender_role': m.get('sender_role', sender_role),
                    })
            return tagged

        # Tag and combine all messages: self, (optional) human partner, and AI
        combined = (
            _tag(my_msgs, getattr(p, 'player_role', None))
            + _tag(partner_msgs, getattr(partner, 'player_role', None) if partner else None)
            + _tag(ai_msgs, p.participant.vars.get('partner_role'))
        )

        # Sort by server_ts if available, then by client timestamp
        def _ts_key(m):
            return (
                m.get('server_ts') or '' ,
                m.get('timestamp') or ''
            )
        try:
            combined.sort(key=_ts_key)
        except Exception:
            pass

        # Sequences
        try:
            matcher_sequence_json = p.group.matcher_sequence or '[]'
        except Exception:
            matcher_sequence_json = '[]'

        # Accuracy and completion time
        accuracy = getattr(p, 'sequence_accuracy', None)
        completion_time = getattr(p, 'completion_time', None)

        # Attention check data for this round
        attention_responses = p.participant.vars.get('attention_round_responses', {})
        current_round_attention = attention_responses.get(p.round_number, {})
        attention_selected = current_round_attention.get('selected', None)
        attention_correct = current_round_attention.get('is_correct', None)

        # Create readable chat transcript
        transcript_lines = []
        for msg in combined:
            try:
                # Use server timestamp if available, otherwise client timestamp
                ts = msg.get('server_ts') or msg.get('timestamp') or ''
                # Extract time portion (HH:MM:SS) from ISO timestamp
                if 'T' in ts:
                    time_part = ts.split('T')[1].split('.')[0] if '.' in ts else ts.split('T')[1]
                else:
                    time_part = ts
                
                sender = msg.get('sender_role', 'unknown')
                text = msg.get('text', '')
                transcript_lines.append(f"[{time_part}] {sender}: {text}")
            except Exception:
                # If parsing fails, include raw message
                text = msg.get('text', '')
                sender = msg.get('sender_role', 'unknown')
                transcript_lines.append(f"{sender}: {text}")
        
        chat_transcript = '\r\n'.join(transcript_lines)

        # Get prolific_participant_id from participant vars (persisted across rounds) or from current player
        prolific_id = p.participant.vars.get('prolific_participant_id') or getattr(p, 'prolific_participant_id', None)
        
        # Get experiment timing from participant vars (persisted) or current player
        experiment_start = p.participant.vars.get('experiment_start_time') or getattr(p, 'experiment_start_time', None)
        
        # Check if this is the final round - only include end-of-experiment data there
        is_final_round = p.round_number == Constants.num_rounds
        
        # End-of-experiment timing (final round only)
        experiment_end = None
        duration_minutes = None
        if is_final_round:
            experiment_end = p.participant.vars.get('experiment_end_time') or getattr(p, 'experiment_end_time', None)
            if experiment_start and experiment_end:
                try:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(experiment_start)
                    end_dt = datetime.fromisoformat(experiment_end)
                    duration_seconds = (end_dt - start_dt).total_seconds()
                    duration_minutes = round(duration_seconds / 60, 2)
                except Exception:
                    duration_minutes = None
        
        # Build row - end-of-experiment fields are None for non-final rounds
        yield [
            getattr(p.session, 'code', None),
            p.round_number,
            getattr(p.group, 'id', None),
            getattr(p.participant, 'code', None),
            prolific_id,
            getattr(p, 'player_role', None),
            # Experiment timing
            experiment_start,
            experiment_end,  # final round only
            duration_minutes,  # final round only
            # Per-round task data
            chat_transcript,
            json.dumps(combined, ensure_ascii=False),
            matcher_sequence_json,
            accuracy,
            completion_time,
            # Attention check (per round)
            attention_selected,
            attention_correct,
            # Post-task survey (final round only)
            getattr(p, 'partner_capable', None) if is_final_round else None,
            getattr(p, 'partner_helpful', None) if is_final_round else None,
            getattr(p, 'partner_understood', None) if is_final_round else None,
            getattr(p, 'partner_adapted', None) if is_final_round else None,
            getattr(p, 'collaboration_improved', None) if is_final_round else None,
            getattr(p, 'partner_comment', None) if is_final_round else None,
            getattr(p, 'partner_human_vs_ai', None) if is_final_round else None,
            getattr(p, 'partner_human_vs_ai_why', None) if is_final_round else None,
            getattr(p, 'ai_familiarity', None) if is_final_round else None,
            getattr(p, 'ai_usage_frequency', None) if is_final_round else None,
            getattr(p, 'ai_used_for_task', None) if is_final_round else None,
            # AI data (final round only)
            getattr(getattr(p, 'group', None), 'ai_reasoning_log', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_partner_capable', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_partner_helpful', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_partner_understood', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_partner_adapted', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_collaboration_improved', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_partner_comment', None) if is_final_round else None,
            # AI vs AI mode perceptions (final round only)
            getattr(getattr(p, 'group', None), 'ai_director_partner_capable', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_director_partner_helpful', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_director_partner_understood', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_director_partner_adapted', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_director_collaboration_improved', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_director_partner_comment', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_matcher_partner_capable', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_matcher_partner_helpful', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_matcher_partner_understood', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_matcher_partner_adapted', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_matcher_collaboration_improved', None) if is_final_round else None,
            getattr(getattr(p, 'group', None), 'ai_matcher_partner_comment', None) if is_final_round else None,
        ]
