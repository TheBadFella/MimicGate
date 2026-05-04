"""
Shared browser-access coordination primitives.

Today CatGPT drives a single ChatGPT page, so every API surface that touches
that page must serialize against the same lock. Keeping the lock in one module
avoids route families accidentally using separate "global" locks.
"""

from __future__ import annotations

import asyncio

# Single-process browser access lock for the shared ChatGPT page.
browser_access_lock = asyncio.Lock()
