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
    players_per_group = 2  # Two players for collaborative task
    num_rounds = 4


class Subsession(BaseSubsession):
    def creating_session(self):
        # Groups are now formed dynamically on the wait page using group_by_arrival_time
        # Keep the same groups in later rounds
        if self.round_number > 1:
            self.group_like_round(1)


class Group(BaseGroup):
    # Store the shared grid that both Director and Matcher see
    shared_grid = models.LongStringField(blank=True, initial='[]')
    
    # Store the target basket(s) that Director needs to communicate
    target_baskets = models.LongStringField(blank=True, initial='[]')
    
    # Store Matcher's sequence selections
    matcher_sequence = models.LongStringField(blank=True, initial='[]')
    
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

        - Default: 4x3 baskets (12) using presets or random images.
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
        return grid, targets


class Player(BasePlayer):
    # Prolific participant ID (collected at start)
    prolific_participant_id = models.StringField(blank=True)
    
    # Experiment timing (stored at participant level for persistence)
    experiment_start_time = models.StringField(blank=True)  # ISO timestamp when experiment started
    experiment_end_time = models.StringField(blank=True)    # ISO timestamp when experiment ended
    
    # Player role: 'director' or 'matcher'
    player_role = models.StringField(choices=['director', 'matcher'], blank=True)
    
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
    # - Convenience fields for analysis
    # 
    # NOTE ON IDENTIFIERS
    # -------------------
    # To make downstream analysis easier and ensure consistency across
    # different exports (wide CSV, custom export, transcript scripts), we
    # expose:
    # - group_id_db: Django's database PK for the group (legacy, stable within a session)
    # - group_id_in_subsession: oTree's id_in_subsession (matches wide CSV columns
    #   like referential_task.1.group.id_in_subsession)
    # - pair_id: stable identifier for the dyad across all rounds within a session.
    #   This is set once when the pair is first matched and then stored on
    #   each participant via participant.vars['pair_id'].
def custom_export(players):
    """oTree hook: customize the app's CSV export in the Data tab.

    Columns:
    - session_code, round_number, group_id, id_in_group, participant_code, role
    - prolific_participant_id: Prolific ID entered at the start
    - experiment_start_time: ISO timestamp when participant started the experiment
    - experiment_end_time: ISO timestamp when participant completed the experiment
    - experiment_duration_minutes: Total time taken in minutes (calculated from start to end)
    - chat_transcript: readable conversation transcript with timestamps (one message per line)
    - chat_log_json: combined messages from both players, sorted by timestamp (JSON format)
    - matcher_sequence_json: group-level sequence submitted by matcher
    - selected_sequence_json: this player's own selected sequence (matcher only)
    - sequence_accuracy: matcher's accuracy (%)
    - completion_time: ISO timestamp when this player marked task complete
    - left_waiting_room: ISO timestamp when player left/navigated away from waiting room
    - waiting_room_exit_reason: reason for leaving ('prolific_button_click', 'page_hidden', 'page_unload')
    - prolific_exit_clicked: ISO timestamp when player clicked "Return to Prolific" button (indicates intentional exit)
    - attention_round_q: current round's attention check response
    - attention_round_correct: whether current round's attention check was correct
    - Post-task survey fields: partner ratings, AI perception, AI experience
    """
    # Header row
    yield [
        'session_code',
        'round_number',
        # Group identifiers
        'group_id_db',
        'group_id_in_subsession',
        # Invariant pair identifier shared by both players in a dyad
        'pair_id',
        'id_in_group',
        'participant_code',
        'prolific_participant_id',
        'role',
        # Experiment timing
        'experiment_start_time',
        'experiment_end_time',
        'experiment_duration_minutes',
        'round_duration_seconds',
        'round_duration_formatted',
        'chat_transcript',
        'chat_log_json',
        'matcher_sequence_json',
        'selected_sequence_json',
        'sequence_accuracy',
        'completion_time',
        # Waiting room tracking
        'left_waiting_room',
        'waiting_room_exit_reason',
        'prolific_exit_clicked',
        # Attention check (per round)
        'attention_round_q',
        'attention_round_correct',
        # Post-task survey
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
    ]

    for p in players:
        try:
            # Messages from self
            my_msgs = json.loads(p.grid_messages or '[]')
        except Exception:
            my_msgs = []
        # Messages from partner (if any)
        partner = p.get_others_in_group()[0] if p.get_others_in_group() else None
        try:
            partner_msgs = json.loads(partner.grid_messages or '[]') if partner else []
        except Exception:
            partner_msgs = []

        # Tag messages with sender id for clarity (non-destructive)
        def _tag(msg_list, sender_role):
            tagged = []
            for m in (msg_list or []):
                if isinstance(m, dict):
                    tagged.append({
                        'text': m.get('text'),
                        'timestamp': m.get('timestamp'),
                        'server_ts': m.get('server_ts'),
                        'sender_role': m.get('sender_role', sender_role),
                    })
            return tagged

        combined = _tag(my_msgs, getattr(p, 'player_role', None)) + _tag(partner_msgs, getattr(partner, 'player_role', None) if partner else None)

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
        selected_sequence_json = getattr(p, 'selected_sequence', '[]') or '[]'

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
        experiment_start = getattr(p, 'experiment_start_time', None) or p.participant.vars.get('experiment_start_time')
        experiment_end = getattr(p, 'experiment_end_time', None) or p.participant.vars.get('experiment_end_time')
        
        # For early rounds (not last round), completion_time is the de facto end time
        # because experiment_end_time might only be set on the last page
        if not experiment_end and getattr(p, 'completion_time', None):
            experiment_end = p.completion_time

        # Calculate duration in minutes if both timestamps available
        duration_minutes = None
        if experiment_start and experiment_end:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(experiment_start)
                end_dt = datetime.fromisoformat(experiment_end)
                duration_seconds = (end_dt - start_dt).total_seconds()
                duration_minutes = round(duration_seconds / 60, 2)
            except Exception:
                duration_minutes = None
        
        # Calculate round-specific duration
        round_duration_seconds = None
        round_duration_formatted = None
        try:
            # Get current round's start and end times from player fields
            r_start = getattr(p, 'experiment_start_time', None)
            r_end = getattr(p, 'experiment_end_time', None)
            if r_start and r_end:
                from datetime import datetime
                start_dt = datetime.fromisoformat(r_start)
                end_dt = datetime.fromisoformat(r_end)
                duration_total_seconds = (end_dt - start_dt).total_seconds()
                round_duration_seconds = round(duration_total_seconds, 2)
                
                # Format as "X minutes Y seconds"
                minutes = int(duration_total_seconds // 60)
                seconds = int(duration_total_seconds % 60)
                if minutes > 0:
                    round_duration_formatted = f"{minutes} minutes {seconds} seconds"
                else:
                    round_duration_formatted = f"{seconds} seconds"
        except Exception:
            round_duration_seconds = None
            round_duration_formatted = None
        
        # Build row
        # Group identifiers
        group_db_id = getattr(p.group, 'id', None)
        group_subsession_id = getattr(p.group, 'id_in_subsession', None)

        # Stable pair identifier (set at matching time and persisted via participant vars)
        pair_id = p.participant.vars.get('pair_id')

        yield [
            getattr(p.session, 'code', None),
            p.round_number,
            group_db_id,
            group_subsession_id,
            pair_id,
            p.id_in_group,
            getattr(p.participant, 'code', None),
            prolific_id,
            getattr(p, 'player_role', None),
            # Experiment timing
            experiment_start,
            experiment_end,
            duration_minutes,
            round_duration_seconds,
            round_duration_formatted,
            chat_transcript,
            json.dumps(combined, ensure_ascii=False),
            matcher_sequence_json,
            selected_sequence_json,
            accuracy,
            completion_time,
            # Waiting room tracking
            getattr(p, 'left_waiting_room', None),
            getattr(p, 'waiting_room_exit_reason', None),
            getattr(p, 'prolific_exit_clicked', None),
            # Attention check (per round)
            attention_selected,
            attention_correct,
            # Post-task survey values (will repeat each round; use last round for analysis)
            getattr(p, 'partner_capable', None),
            getattr(p, 'partner_helpful', None),
            getattr(p, 'partner_understood', None),
            getattr(p, 'partner_adapted', None),
            getattr(p, 'collaboration_improved', None),
            getattr(p, 'partner_comment', None),
            getattr(p, 'partner_human_vs_ai', None),
        getattr(p, 'partner_human_vs_ai_why', None),
        getattr(p, 'ai_familiarity', None),
        getattr(p, 'ai_usage_frequency', None),
        getattr(p, 'ai_used_for_task', None),
        ]
