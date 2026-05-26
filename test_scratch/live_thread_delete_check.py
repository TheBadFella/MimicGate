from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.browser.manager import BrowserManager
from src.chatgpt.client import ChatGPTClient
from src.config import Config


MANUAL_STEPS = """Manual thread create/delete verification:
1. Stop any running CatGPT container or local API that is using the same browser profile.
2. From the repo root, run: .\\.venv\\Scripts\\python.exe test_scratch\\live_thread_delete_check.py
3. Wait for the browser to open ChatGPT and confirm login.
4. The script creates a new chat, sends a unique marker prompt, captures the /c/<thread_id> URL, and invokes ChatGPTClient.delete_thread(thread_id).
5. If testing manually in noVNC instead, open http://localhost:6080/vnc.html, log in, create a new chat, copy the thread id from the URL, hover the matching sidebar row, open its three-dot menu, click Delete, and confirm.
6. After deletion, verify the sidebar no longer contains a link with that same /c/<thread_id>.
"""


async def main() -> int:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "live_thread_delete_check.log"

    marker = f"catgpt-delete-smoke-{uuid4().hex[:10]}"
    browser = BrowserManager()

    def log(line: str) -> None:
        stamped = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}"
        print(stamped, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(stamped + "\n")

    log("=" * 72)
    log("Live ChatGPT thread create/delete check starting")
    log(f"Manual instructions:\n{MANUAL_STEPS}")
    log(f"Using browser data dir: {Config.BROWSER_DATA_DIR}")

    try:
        page = await browser.start()
        await browser.navigate(Config.CHATGPT_URL)
        await asyncio.sleep(3)

        if not await browser.is_logged_in():
            log("FAILED: ChatGPT login was not detected.")
            return 2

        client = ChatGPTClient(page)
        log("Creating new chat")
        await client.new_chat()

        prompt = f"Reply with exactly this marker and nothing else: {marker}"
        log(f"Sending marker prompt: {marker}")
        response = await client.send_message(prompt)
        thread_id = response.thread_id or client._extract_thread_id()
        log(f"Response text: {response.message!r}")
        log(f"Captured thread id: {thread_id or '<missing>'}")

        if not thread_id:
            log("FAILED: Could not capture a thread id after sending the prompt.")
            return 3

        log(f"Deleting thread {thread_id}")
        deleted = await client.delete_thread(thread_id)
        log(f"delete_thread returned: {deleted}")

        await asyncio.sleep(2)
        remaining = await page.query_selector(f"a[href*='/c/{thread_id}']")
        current_url = page.url
        log(f"Current URL after deletion: {current_url}")
        log(f"Sidebar link still present: {bool(remaining)}")

        if deleted and remaining is None:
            log("PASS: thread was created, delete flow returned true, and sidebar link is gone.")
            return 0

        log("FAILED: delete flow did not fully verify.")
        return 4
    except Exception as exc:
        log(f"FAILED with exception: {exc!r}")
        return 1
    finally:
        await browser.close()
        log(f"Log written to: {log_path}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
