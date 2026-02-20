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
    # --- Core AI–human grid configs (Set 5 by default) ---
    #
    # Prompt strategies (all of these see the same visual 12‑basket grid via
    # `_inject_visual_grid_context` in `referential_task/pages.py` whenever
    # images are available):
    # - v1  = Simple baseline prompt:
    #         short role description, no explicit KB hints, no JSON reasoning.
    # - v2  = “Weiling‑style” rich prompt:
    #         detailed role + round context, optional KB basket hints when
    #         `use_kb=True`.
    # - v3  = CoT / JSON reasoning on top of v2:
    #         same rich prompt as v2, but the model must reply with
    #         {"reasoning": {...}, "utterance": "..."}; only `utterance`
    #         is shown to the human; reasoning can be logged when
    #         `log_v3_reasoning=True`.
    #
    # Visual context is therefore NOT unique to any one strategy; differences
    # between v1 / v2 / v3 are in text instructions, KB usage, and whether
    # JSON reasoning is requested.
    
    # Baseline V1: simple prompt (visual grid), human is Matcher
    dict(
        name='referential_task_grid_human_matcher',
        display_name="Basket Grid Human–VLM (Set 5, Human = Matcher, V1 simple)",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        human_role='matcher',
        prompt_strategy='v1',
        testing_skip_enabled=False, 
        testing_debug_enabled=True,
        ai_debug_enabled=True
    ),
    # V2: Weiling-style rich prompt (visual grid) + optional KB hints, human is Matcher
    dict(
        name='referential_task_grid_human_matcher_v2',
        display_name="Basket Grid Human–VLM (Set 5, Human = Matcher, V2 Weiling)",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        human_role='matcher',
        testing_debug_enabled=True,
        prompt_strategy='v2',
        testing_skip_enabled=False, 
    ),
    # V3: CoT prompt on top of V2 (JSON reasoning + utterance, visual grid), human is Matcher
    dict(
        name='referential_task_grid_human_matcher_v3',
        display_name="Basket Grid Human–VLM (Set 5, Human = Matcher, V3 CoT)",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        human_role='matcher',
        prompt_strategy='v3',
        testing_debug_enabled=True,
        log_v3_reasoning=True,
        testing_skip_enabled=False, 
    ),

    # Baseline V1: simple prompt (visual grid), human is Director
    dict(
        name='referential_task_grid_human_director',
        display_name="Basket Grid Human–VLM (Set 5, Human = Director, V1 simple)",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        human_role='director',
        prompt_strategy='v1',
        testing_debug_enabled=True,
        testing_skip_enabled=False, 
        ai_debug_enabled=True
    ),
    # V2: Weiling-style rich prompt (visual grid) + optional KB hints, human is Director
    dict(
        name='referential_task_grid_human_director_v2',
        display_name="Basket Grid Human–VLM (Set 5, Human = Director, V2 Weiling)",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        human_role='director',
        prompt_strategy='v2',
        testing_debug_enabled=True,
        testing_skip_enabled=False,
    ),
    # V3: CoT prompt on top of V2 (JSON reasoning + utterance, visual grid), human is Director
    dict(
        name='referential_task_grid_human_director_v3',
        display_name="Basket Grid Human–VLM (Set 5, Human = Director, V3 CoT)",
        app_sequence=['onboarding', 'referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        human_role='director',
        prompt_strategy='v3',
        log_v3_reasoning=True,
        testing_debug_enabled=True,
        testing_skip_enabled=False, 
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
    # By default, do NOT use the text KnowledgeBase (KB); all strategies rely
    # on visual context + dialogue alone unless a session explicitly opts in.
    use_kb=False,
    # Cross-round history: AI sees full dialogue history from all prior rounds.
    # Essential for entrainment studies in human-AI settings.
    cross_round_history=True,
    # Maximum number of dialogue turns to include in AI prompts.
    # With cross_round_history=True, 200 turns covers ~4 rounds of rich dialogue.
    # GPT-4o supports 128K tokens (~500+ turns). Adjust as needed.
    ai_max_history_turns=200,
    # ---------------------------------------------------------------------------
    # AI Model Configuration
    # ---------------------------------------------------------------------------
    # AI model to use. Defaults to 'gpt-5.2' (latest reasoning model).
    # Other options: 'gpt-5', 'gpt-5.1', 'gpt-4o', 'o1', 'o3', etc.
    # Can also be set via OPENAI_MODEL environment variable.
    ai_model='gpt-5.2',
    # Reasoning effort for reasoning models (gpt-5+, o1, o3).
    # Options: 'none' (fastest), 'low', 'medium', 'high' (slowest, most thorough).
    # Ignored for traditional models (gpt-4o) which use temperature=0 instead.
    # Can also be set via AI_REASONING_EFFORT environment variable.
    ai_reasoning_effort='none',
)

# Rooms let you share one stable link per condition (e.g., /room/grid_matcher_v1/)
# Each of these maps 1:1 to a session config above, so you can hand out
# persistent URLs for that specific prompt/role variant.
ROOMS = [
    dict(name='basket_room', display_name='Basket Room'),
    dict(name='grid_matcher_v1', display_name='Grid Human = Matcher (v1 simple)'),
    dict(name='grid_matcher_v2', display_name='Grid Human = Matcher (v2 Weiling)'),
    dict(name='grid_matcher_v3', display_name='Grid Human = Matcher (v3 CoT)'),
    dict(name='grid_director_v1', display_name='Grid Human = Director (v1 simple)'),
    dict(name='grid_director_v2', display_name='Grid Human = Director (v2 Weiling)'),
    dict(name='grid_director_v3', display_name='Grid Human = Director (v3 CoT)'),
    # Add participant_label_file/use_secure_urls here if you need named IDs or secure links.
]

ROOM_DEFAULTS = dict(participation_fee=0)

PARTICIPANT_FIELDS = []
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
