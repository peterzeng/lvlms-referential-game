from os import environ
import os

# Load environment variables from a local .env file if present (for local/dev convenience)
try:
    from dotenv import load_dotenv  # type: ignore
    # resolve project root as directory of this settings.py
    _SETTINGS_DIR = os.path.dirname(os.path.abspath(__file__))
    _PROJECT_ROOT = _SETTINGS_DIR
    # look for ".env" in project root
    load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))
except Exception:
    # dotenv is optional in production; safe to ignore if unavailable
    pass

# SESSION_CONFIGS = [
#     # dict(
#     #     name='public_goods',
#     #     app_sequence=['public_goods'],
#     #     num_demo_participants=3,
#     # ),
# ]

SESSION_CONFIGS = [
    # Grid view: Set 1
    dict(
        name='referential_task_set1',
        display_name="Basket Grid Experiment (Set 1) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='grid',
        basket_set=1,
    ),
    # Grid view: Set 2
    dict(
        name='referential_task_set2',
        display_name="Basket Grid Experiment (Set 2) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='grid',
        basket_set=2,
    ),
    # Grid view: Set 3
    dict(
        name='referential_task_set3',
        display_name="Basket Grid Experiment (Set 3) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='grid',
        basket_set=3,
    ),
    # Grid view: Set 4
    dict(
        name='referential_task_set4',
        display_name="Basket Grid Experiment (Set 4) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='grid',
        basket_set=4,
    ),
    # Grid view: Set 5
    dict(
        name='referential_task_set5',
        display_name="Basket Grid Experiment (Set 5) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='grid',
        basket_set=5,
    ),
    # Sequential director variant keeps working; defaults to Set 1 unless overridden in session
    dict(
        name='referential_task_sequential',
        display_name="Basket Grid Experiment (Sequential Director) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='sequential',
        basket_set=1,
    ),
    # Sequential director variant using Set 2
    dict(
        name='referential_task_sequential_set2',
        display_name="Basket Grid Experiment (Sequential Director, Set 2) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='sequential',
        basket_set=2,
    ),
    # Sequential director variant using Set 3
    dict(
        name='referential_task_sequential_set3',
        display_name="Basket Grid Experiment (Sequential Director, Set 3) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='sequential',
        basket_set=3,
    ),
    # Sequential director variant using Set 4
    dict(
        name='referential_task_sequential_set4',
        display_name="Basket Grid Experiment (Sequential Director, Set 4) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='sequential',
        basket_set=4,
    ),
    # Sequential director variant using Set 5
    dict(
        name='referential_task_sequential_set5',
        display_name="Basket Grid Experiment (Sequential Director, Set 5) — P1: Director, P2: Matcher",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='sequential',
        basket_set=5,
    ),
    # Shapes demo: single-round, colored shapes instead of baskets
    dict(
        name='referential_task_shapes_demo',
        display_name="Shapes Demo (Single Round)",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=2,
        director_view='shapes_demo',
        basket_set=1,
        num_rounds=1,
    ),
]

# if you set a property in SESSION_CONFIG_DEFAULTS, it will be inherited by all configs
# in SESSION_CONFIGS, except those that explicitly override it.
# the session config can be accessed from methods in your apps as self.session.config,
# e.g. self.session.config['participation_fee']

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00,
    participation_fee=0.00,
    doc="",
    # Set your Prolific return URL here; can be overridden per session config
    prolific_return_url=environ.get('PROLIFIC_RETURN_URL', ''),
)

# Rooms let you share one stable link like /room/basket_room/
ROOMS = [
    dict(
        name='basket_room',
        display_name='Basket Room',
        # participant_label_file='participant_labels.txt',  # optional
        # use_secure_urls=True,  # set True when recruiting externally
    ),
]

ROOM_DEFAULTS = dict(participation_fee=0)

PARTICIPANT_FIELDS = [
    # Stable dyad identifier and group metadata persisted in participant.vars
    # (see referential_task.GridTaskWaitPage.after_all_players_arrive)
    'pair_id',
    'group_id_db',
    'group_id_in_subsession',
    'id_in_group',
    'partner_code',
    'partner_id_in_group',
    'partner_role',
    # Final-round survey responses stored once per participant (instead of per round)
    # These are populated from referential_task.Player fields on the final round.
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
SESSION_FIELDS = []

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'

# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """
<script>
(function(){
  function relabelNode(node){
    if (!node) return;
    try {
      var text = (node.textContent || '').trim();
      if (text === 'P1') node.textContent = 'Director';
      if (text === 'P2') node.textContent = 'Matcher';
    } catch(e) {}
  }
  function relabelAll(){
    try {
      // Links, buttons, table cells
      var nodes = document.querySelectorAll('a, button, td, th, span, div');
      nodes.forEach(function(n){
        var t = (n.textContent || '').trim();
        if (t === 'P1' || t === 'p1') {
          n.textContent = 'Director';
          n.setAttribute && n.setAttribute('aria-label','Director');
          n.setAttribute && n.setAttribute('title','Director (demo)');
        } else if (t === 'P2' || t === 'p2') {
          n.textContent = 'Matcher';
          n.setAttribute && n.setAttribute('aria-label','Matcher');
          n.setAttribute && n.setAttribute('title','Matcher (demo)');
        }
      });
    } catch(e) {}
  }
  function startObserver(){
    try {
      var obs = new MutationObserver(function(mutations){
        mutations.forEach(function(m){
          if (m.type === 'childList') {
            m.addedNodes && m.addedNodes.forEach(function(n){
              if (n.nodeType === 3) { // text
                relabelNode(n.parentNode);
              } else {
                relabelAll();
              }
            });
          } else if (m.type === 'characterData') {
            relabelNode(m.target);
          }
        });
      });
      obs.observe(document.documentElement || document.body, {subtree:true, childList:true, characterData:true});
    } catch(e) {}
  }
  function init(){
    relabelAll();
    startObserver();
    // Run again after a tick in case oTree hydrates late
    setTimeout(relabelAll, 100);
    window.addEventListener('load', relabelAll);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
"""

SECRET_KEY = '3966170701770'
