from __future__ import annotations

"""
Thin compatibility wrapper for oTree.

Historically, all page classes, AI helpers, and admin-report utilities for the
`referential_task` app lived in this single `pages.py` file. To keep the
codebase maintainable, the implementation has been split into:

- `ai_utils.py`   – OpenAI / VLM helpers and shared AI matcher utilities
- `page_views.py` – Page subclasses, page_sequence, and admin report helpers

To avoid breaking any existing imports or oTree expectations, we simply
re-export everything from those modules here, so external callers can continue
to import from `referential_task.pages` as before.
"""

from .ai_utils import *  # noqa: F401,F403
from .page_views import *  # noqa: F401,F403


