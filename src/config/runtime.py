"""Checked-in runtime defaults that are safe to share.

Machine-specific database credentials remain in the ignored ``config.py``.
"""

import os


DATE_INPUT_ORDER = os.getenv("DATE_INPUT_ORDER", "MDY").strip().upper()

