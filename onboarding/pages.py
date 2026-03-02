from otree.api import Currency as c, currency_range
from ._builtin import Page
from .models import Constants, Player


class ParticipantID(Page):
    """Collect Prolific participant ID at the very start."""
    template_name = 'onboarding/ParticipantID.html'

    form_model = 'player'
    form_fields = ['prolific_participant_id']

    def vars_for_template(self):
        """
        Enable a developer/testing-only skip button when running locally or when configured.
        Mirrors the logic used in PreTaskWizard so the same flag/environment
        controls both entry points.
        """
        # Default: disabled
        testing_skip = False
        # Allow enabling via session config
        try:
            cfg = self.session.config if hasattr(self, 'session') and self.session else {}
        except Exception:
            cfg = {}
        if cfg:
            testing_skip = bool(cfg.get('testing_skip_enabled', False))

        # Also auto-enable if DEBUG env var is set (handy for local demos)
        try:
            import os as _os
            if _os.environ.get('DEBUG', '').lower() in ('1', 'true', 'yes'):
                testing_skip = True
        except Exception:
            pass

        return {
            'testing_skip_enabled': testing_skip,
        }

    def error_message(self, values):
        """Validate that a Prolific participant ID was entered."""
        prolific_id = values.get('prolific_participant_id', '').strip()
        
        if not prolific_id:
            return 'Please enter your Prolific participant ID to continue.'
        
        # Optional: Check if the ID has a reasonable length (Prolific IDs are typically 24 characters)
        if len(prolific_id) < 5:
            return 'Please enter a valid Prolific participant ID. It should be at least 5 characters long.'
        
        return None

    def before_next_page(self, timeout_happened=False):
        """Store participant ID and optionally mark onboarding as skipped for demos."""
        # Handle demo/testing skip: triggered by a hidden field posted from the template
        try:
            request = getattr(self, 'request', None)
            skip_flag = request.POST.get('demo_skip_to_task') if request is not None else None
        except Exception:
            skip_flag = None

        if skip_flag:
            # Mark a lightweight flag so later onboarding pages can auto-skip
            self.participant.vars['demo_skip_to_task'] = True
            # Ensure any flows that gate on these vars see onboarding as "passed"
            self.participant.vars['attention_passed'] = True
            self.participant.vars['comprehension_passed'] = True
            self.participant.vars['onboarding_complete'] = True

        # Store participant ID in participant vars for persistence across apps.
        if self.player.prolific_participant_id:
            self.participant.vars['prolific_participant_id'] = self.player.prolific_participant_id
        
        # Capture experiment start time
        import datetime
        start_time = datetime.datetime.now().isoformat()
        self.player.experiment_start_time = start_time
        self.participant.vars['experiment_start_time'] = start_time


class DeviceCheck(Page):
    """Check if user is on a desktop/laptop computer before allowing them to proceed."""
    template_name = 'onboarding/DeviceCheck.html'

    def is_displayed(self):
        """
        For demo/testing runs where the first page's skip button was used, skip
        this page entirely so participants go straight to the main task.
        """
        if self.participant.vars.get('demo_skip_to_task'):
            return False
        return True

    def vars_for_template(self):
        prolific_url = None
        try:
            prolific_url = self.session.config.get('prolific_return_url')
        except Exception:
            prolific_url = None
        return {
            'prolific_return_url': prolific_url,
        }
    
    @staticmethod
    def live_method(player: Player, data):
        """Capture device information sent from client"""
        if 'device_info' in data:
            info = data['device_info']
            player.device_type = info.get('device_type', '')
            player.user_agent = info.get('user_agent', '')[:1000]  # Truncate if too long
            player.screen_width = info.get('screen_width', 0)
            player.screen_height = info.get('screen_height', 0)
            player.is_mobile_detected = info.get('is_mobile', False)
            
            # Store in participant vars for easy access across apps
            player.participant.vars['device_type'] = player.device_type
            player.participant.vars['is_mobile_detected'] = player.is_mobile_detected
            
            return {player.id_in_group: {'success': True}}
        return {player.id_in_group: {'success': False}}


class AttentionCheck(Page):
    """DEPRECATED: Pre-task attention check replaced by per-round checks."""
    template_name = 'onboarding/AttentionCheck.html'

    form_model = 'player'
    form_fields = ['attention_q1', 'attention_q2', 'attention_q3']

    def is_displayed(self):
        # DISABLED: Attention checks now happen after each round in main task
        # Always mark as passed for backward compatibility
        self.participant.vars['attention_passed'] = True
        return False

    def error_message(self, values):
        return None

    def before_next_page(self, timeout_happened=False):
        """Mark participant for pass/fail."""
        correct_q1 = 'A'  # Q1 correct: Red
        correct_q2 = 'C'  # Q2 correct: Duck
        correct_q3 = 'B'  # Q3 correct: 5
        selected_q1 = (self.player.attention_q1 or '').strip()
        selected_q2 = (self.player.attention_q2 or '').strip()
        selected_q3 = (self.player.attention_q3 or '').strip()
        passed = (selected_q1 == correct_q1) and (selected_q2 == correct_q2) and (selected_q3 == correct_q3)
        self.participant.vars['attention_passed'] = passed
        self.participant.vars['attention_selected'] = {'q1': selected_q1, 'q2': selected_q2, 'q3': selected_q3}


class Disqualify(Page):
    """DEPRECATED: Pre-task disqualification replaced by per-round checks."""
    template_name = 'onboarding/Disqualify.html'

    def is_displayed(self):
        # DISABLED
        return False

    def vars_for_template(self):
        prolific_url = None
        try:
            prolific_url = self.session.config.get('prolific_return_url')
        except Exception:
            prolific_url = None
        return {
            'prolific_return_url': prolific_url,
        }


class PreTaskWizard(Page):
    """Single-page, client-side wizard for pre-task steps: consent & instructions."""
    template_name = 'onboarding/PreTaskWizard.html'
    
    form_model = 'player'
    form_fields = ['comprehension_check']

    def vars_for_template(self):
        # Enable a developer/testing-only skip button when running locally or when configured
        try:
            cfg = self.session.config if hasattr(self, 'session') and self.session else {}
        except Exception:
            cfg = {}
        testing_skip = bool(cfg.get('testing_skip_enabled', False))
        # Also auto-enable if DEBUG is set
        try:
            import os as _os
            if _os.environ.get('DEBUG', '').lower() in ('1', 'true', 'yes'):
                testing_skip = True
        except Exception:
            pass
        prolific_url = None
        try:
            prolific_url = self.session.config.get('prolific_return_url')
        except Exception:
            prolific_url = None
        
        # Track comprehension check attempts
        attempts = self.participant.vars.get('comprehension_attempts', 0)
        failed_once = self.participant.vars.get('comprehension_failed_once', False)
        failed_twice = self.participant.vars.get('comprehension_failed_twice', False)
        
        return {
            'testing_skip_enabled': testing_skip,
            'prolific_return_url': prolific_url,
            'comprehension_attempts': attempts,
            'failed_once': failed_once,
            'failed_twice': failed_twice,
        }

    def is_displayed(self):
        # If the participant used the demo skip from the first page, skip this wizard.
        if self.participant.vars.get('demo_skip_to_task'):
            return False

        # Hide for shapes demo; otherwise show if attention was passed
        if getattr(self.session.config, 'get', None):
            if self.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        return self.participant.vars.get('attention_passed') is True
    
    def error_message(self, values):
        """Validate comprehension check answer"""
        if 'comprehension_check' not in values or not values['comprehension_check']:
            return None  # Skip validation if not answered yet
        
        correct_answer = 'b'  # The Matcher is responsible for submitting
        selected = values['comprehension_check']
        
        # Track attempts
        attempts = self.participant.vars.get('comprehension_attempts', 0)
        attempts += 1
        self.participant.vars['comprehension_attempts'] = attempts
        
        if selected != correct_answer:
            if attempts == 1:
                # First failure
                self.participant.vars['comprehension_failed_once'] = True
                return "That's not quite right. Please read the instructions carefully. You have one more chance to answer correctly."
            else:
                # Second failure
                self.participant.vars['comprehension_failed_twice'] = True
                return "Unfortunately, you did not pass the comprehension check. According to Prolific's policy, please return your submission by clicking 'Cancel participation' on Prolific. This will not affect your approval rate."
        
        # Correct answer - mark as passed
        self.participant.vars['comprehension_passed'] = True
        return None
    
    def before_next_page(self, timeout_happened=False):
        """Allow developer testing skip and mark onboarding complete."""
        # Handle testing skip. If the template posted the special hidden field,
        # persist it into participant.vars so future checks can see it.
        try:
            request = getattr(self, 'request', None)
            posted_skip = request.POST.get('__testing_skip_triggered') if request is not None else None
        except Exception:
            posted_skip = None

        if posted_skip:
            self.participant.vars['testing_skip_triggered'] = True

        if bool(self.participant.vars.get('testing_skip_triggered')):
            self.participant.vars['attention_passed'] = True
            self.participant.vars['comprehension_passed'] = True
        
        # Mark onboarding as complete - this signals readiness for matching
        self.participant.vars['onboarding_complete'] = True


page_sequence = [
    ParticipantID,
    DeviceCheck,
    AttentionCheck,  # DEPRECATED (not displayed)
    Disqualify,      # DEPRECATED (not displayed)
    PreTaskWizard,
]

