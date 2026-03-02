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
    # =========================================================================
    # AI vs AI Configurations
    # =========================================================================
    # These sessions run both Director AND Matcher as AI agents.
    # A human observer watches the AIs play and can control the pace.
    # Useful for evaluating VLM performance on the basket matching task.
    #
    # Prompt strategies:
    # - v1  = Simple baseline prompt:
    #         short role description, no explicit KB hints, no JSON reasoning.
    # - v2  = "Weiling‑style" rich prompt:
    #         detailed role + round context, optional KB basket hints when
    #         `use_kb=True`.
    # - v3  = CoT / JSON reasoning on top of v2:
    #         same rich prompt as v2, but the model must reply with
    #         {"reasoning": {...}, "utterance": "..."}; only `utterance`
    #         is shown to the human; reasoning can be logged when
    #         `log_v3_reasoning=True`.
    # =========================================================================

    # AI vs AI with V1 (simple) prompts
    dict(
        name='ai_vs_ai_v1',
        display_name="AI vs AI (Set 5, V1 Simple)",
        app_sequence=['referential_task'],  # Skip onboarding for AI vs AI
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        ai_vs_ai_mode=True,  # Key flag for AI vs AI mode
        prompt_strategy='v1',
        testing_debug_enabled=True,
        testing_skip_enabled=True,
        ai_debug_enabled=True,
        ai_vs_ai_delay=0,  # Seconds between turns in auto-play mode
        ai_vs_ai_max_turns=60,  # Max turns per round before stopping
    ),

    # AI vs AI with V2 (Weiling-style) prompts
    dict(
        name='ai_vs_ai_v2',
        display_name="AI vs AI (Set 5, V2 Weiling)",
        app_sequence=['referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        ai_vs_ai_mode=True,
        prompt_strategy='v2',
        testing_debug_enabled=True,
        testing_skip_enabled=True,
        ai_debug_enabled=True,
        ai_vs_ai_delay=0,
        ai_vs_ai_max_turns=60,
    ),

    # AI vs AI with V3 (CoT) prompts
    dict(
        name='ai_vs_ai_v3',
        display_name="AI vs AI (Set 5, V3 CoT)",
        app_sequence=['referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        ai_vs_ai_mode=True,
        prompt_strategy='v3',
        log_v3_reasoning=True,
        testing_debug_enabled=True,
        testing_skip_enabled=True,
        ai_debug_enabled=True,
        ai_vs_ai_delay=0,
        ai_vs_ai_max_turns=60,
    ),

    # =========================================================================
    # Mixed AI vs AI Configurations (Different models playing different roles)
    # =========================================================================
    # These sessions allow different AI models to play Director and Matcher.
    # Useful for cross-model evaluation and comparison studies.
    #
    # Per-role configuration keys:
    # - ai_director_model: Model for Director role
    # - ai_matcher_model: Model for Matcher role
    # - ai_director_reasoning_effort: Reasoning for Director (GPT-5.2+)
    # - ai_matcher_reasoning_effort: Reasoning for Matcher (GPT-5.2+)
    # - ai_director_thinking_budget: Thinking budget for Director (Gemini)
    # - ai_matcher_thinking_budget: Thinking budget for Matcher (Gemini)
    # =========================================================================

    # GPT-5.2 Director vs Gemini 2.5 Pro Matcher
    dict(
        name='ai_vs_ai_gpt_vs_gemini',
        display_name="AI vs AI: GPT-5.2 Director vs Gemini-3-Flash Matcher V3",
        app_sequence=['referential_task'],
        num_demo_participants=1,  
        director_view='grid',
        basket_set=5,
        ai_vs_ai_mode=True,
        prompt_strategy='v3',
        # Director uses GPT-5.2
        ai_director_model='gpt-5.2',
        ai_director_reasoning_effort='none',
        # Matcher uses Gemini 3 Flash
        ai_matcher_model='gemini-3-flash-preview',
        ai_matcher_thinking_level='low',  # Minimal thinking
        testing_debug_enabled=True,
        testing_skip_enabled=True,
        ai_debug_enabled=True,
        ai_vs_ai_delay=0,
        ai_vs_ai_max_turns=60,
    ),

    # Gemini 3 Flash Director vs GPT-5.2 Matcher
    dict(
        name='ai_vs_ai_gemini_vs_gpt',
        display_name="AI vs AI: Gemini-3-Flash Director vs GPT-5.2 Matcher",
        app_sequence=['referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        ai_vs_ai_mode=True,
        prompt_strategy='v2',
        # Director uses Gemini 3 Flash
        ai_director_model='gemini-3-flash-preview',
        ai_director_thinking_level='low',  # Minimal thinking
        # Matcher uses GPT-5.2
        ai_matcher_model='gpt-5.2',
        ai_matcher_reasoning_effort='none',
        testing_debug_enabled=True,
        testing_skip_enabled=True,
        ai_debug_enabled=True,
        ai_vs_ai_delay=0,
        ai_vs_ai_max_turns=60,
    ),

    # Gemini 3 Flash vs Gemini 3 Flash (both roles)
    dict(
        name='ai_vs_ai_gemini_v2',
        display_name="AI vs AI: Gemini-3-Flash (V2 Weiling)",
        app_sequence=['referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        ai_vs_ai_mode=True,
        prompt_strategy='v2',
        # Both roles use Gemini 3 Flash
        ai_model='gemini-3-flash-preview',
        ai_thinking_level='low',  # Minimal thinking (equivalent to "none" reasoning)
        testing_debug_enabled=True,
        testing_skip_enabled=True,
        ai_debug_enabled=True,
        ai_vs_ai_delay=0,
        ai_vs_ai_max_turns=60,
    ),

    # =========================================================================
    # Data Collection Configurations (No Debug Output)
    # =========================================================================
    # Clean sessions for running parallel data collection experiments.
    # All debug/testing UI disabled for production-quality data.
    # =========================================================================

    # GPT-5.2 vs GPT-5.2 - Data Collection (V3 CoT)
    dict(
        name='ai_52_vs_52_data',
        display_name="[Data] GPT-5.2 vs GPT-5.2 (V3 CoT)",
        app_sequence=['referential_task'],
        num_demo_participants=1,
        director_view='grid',
        basket_set=5,
        ai_vs_ai_mode=True,
        prompt_strategy='v3',
        log_v3_reasoning=True,  # Log reasoning for analysis
        # Both roles use GPT-5.2
        ai_model='gpt-5.2',
        ai_reasoning_effort='none',
        # Debug/testing UI disabled for clean data collection
        testing_debug_enabled=False,
        testing_skip_enabled=False,
        ai_debug_enabled=False,
        ai_vs_ai_delay=0,
        ai_vs_ai_max_turns=60,
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
    
    # =========================================================================
    # AI Model Configuration
    # =========================================================================
    # Global AI model (applies to both roles if role-specific not set).
    # Supported providers and models:
    #   OpenAI:
    #   - GPT-5.2+: "gpt-5.2", "gpt-5.2-mini" (supports reasoning_effort param)
    #   - Pre-5.2: "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", etc.
    #   Google Gemini:
    #   - Gemini 3: "gemini-3-flash-preview", "gemini-3-pro-preview" (supports thinking_level)
    #   - Gemini 2.5: "gemini-2.5-pro" (supports thinking_budget)
    #   - Legacy: "gemini-2.0-flash", "gemini-1.5-pro", etc.
    #
    # Environment variables:
    #   - OPENAI_API_KEY: Required for OpenAI models
    #   - GEMINI_API_KEY or GOOGLE_API_KEY: Required for Gemini models
    #   - OPENAI_MODEL: Default model (session config takes priority)
    ai_model=environ.get('OPENAI_MODEL', 'gpt-5.2'),
    
    # Reasoning effort for GPT-5.2+ models only. Ignored for pre-5.2 models.
    # Valid values: "none", "low", "medium", "high" (controls depth of reasoning)
    ai_reasoning_effort="none",
    
    # Thinking budget for Gemini models (0 = minimal, higher = more reasoning)
    # Only applies to Gemini 2.5+ models with thinking support.
    ai_thinking_budget=0,
    
    # =========================================================================
    # Per-Role AI Configuration (for mixed model experiments)
    # =========================================================================
    # These override the global ai_model/ai_reasoning_effort for specific roles.
    # Useful for testing GPT-5.2 Director vs Gemini Matcher, etc.
    #
    # ai_director_model: Model for Director role (e.g., "gpt-5.2", "gemini-3-flash-preview")
    # ai_director_reasoning_effort: Reasoning for Director (GPT-5.2+)
    # ai_director_thinking_level: Thinking level for Director (Gemini 3+: "low", "medium", "high")
    # ai_director_thinking_budget: Thinking budget for Director (Gemini 2.5, legacy)
    #
    # ai_matcher_model: Model for Matcher role
    # ai_matcher_reasoning_effort: Reasoning for Matcher (GPT-5.2+)
    # ai_matcher_thinking_level: Thinking level for Matcher (Gemini 3+)
    # ai_matcher_thinking_budget: Thinking budget for Matcher (Gemini 2.5, legacy)
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
