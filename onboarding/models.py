from otree.api import (
    models,
    widgets,
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
)


doc = """
Onboarding app: Collect participant info and ensure they complete tutorial before matching
"""


class Constants(BaseConstants):
    name_in_url = 'onboarding'
    players_per_group = None  # No grouping in onboarding - participants work solo
    num_rounds = 1


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    # Prolific participant ID (collected at start)
    prolific_participant_id = models.StringField(blank=True)
    
    # Experiment timing
    experiment_start_time = models.StringField(blank=True)
    
    # Device tracking (captured on DeviceCheck page)
    device_type = models.StringField(blank=True)  # 'mobile', 'tablet', 'desktop'
    user_agent = models.LongStringField(blank=True)  # Full browser user agent string
    screen_width = models.IntegerField(blank=True)
    screen_height = models.IntegerField(blank=True)
    is_mobile_detected = models.BooleanField(blank=True)  # True if mobile warning was shown
    
    # Attention check responses (DEPRECATED, kept for backward compatibility)
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
    
    # Comprehension check (shown on PreTaskWizard)
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

