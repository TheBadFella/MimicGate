from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.browser.manager import BrowserManager
from src.chatgpt.client import ChatGPTClient
from src.config import Config
from src.selectors import Selectors


MANUAL_STEPS = """Manual thread create/delete verification:
1. Make sure no other local CatGPT process is using the same browser profile.
2. Open the browser/noVNC and go to https://chatgpt.com.
3. Confirm the composer is visible.
4. Click New Chat.
5. Send a short unique marker prompt, such as: Reply with exactly catgpt-delete-smoke-123
6. As soon as the URL becomes https://chatgpt.com/c/<thread_id>, copy that thread id.
7. If the response spins forever, click Stop generating; a completed response is not required for deletion testing.
8. Hover the matching sidebar row, click its row-scoped three-dot menu, click Delete, and confirm.
9. Verify no sidebar link remains for /c/<thread_id>.

Automated equivalent:
    .\\.venv\\Scripts\\python.exe test_scratch\\live_thread_delete_fast.py
"""


async def first_selector(page, selectors: list[str], timeout: int = 5000):
    for selector in selectors:
        try:
            el = await page.wait_for_selector(selector, timeout=timeout, state="visible")
            if el:
                return selector, el
        except Exception:
            continue
    return None, None


async def main() -> int:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "live_thread_delete_fast.log"
    marker = f"catgpt-delete-smoke-{uuid4().hex[:10]}"
    browser = BrowserManager()

    def log(line: str) -> None:
        stamped = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}"
        print(stamped, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(stamped + "\n")

    log("=" * 72)
    log("Fast live ChatGPT thread create/delete check starting")
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
        before_threads = await client.list_threads()
        before_ids = {thread["id"] for thread in before_threads}
        log(f"Sidebar thread count before send: {len(before_ids)}")

        prompt = f"Reply with exactly this marker and nothing else: {marker}"
        log(f"Typing marker prompt: {marker}")
        input_selector, input_el = await first_selector(page, Selectors.CHAT_INPUT)
        if not input_el:
            log("FAILED: could not find ChatGPT composer.")
            return 3

        await input_el.click()
        await page.keyboard.insert_text(prompt)
        log(f"Typed prompt using selector: {input_selector}")

        send_selector, send_button = await first_selector(page, Selectors.SEND_BUTTON)
        if not send_button:
            log("FAILED: could not find send button.")
            return 4
        await send_button.click()
        log(f"Clicked send using selector: {send_selector}")

        thread_id = ""
        deadline = time.time() + 60
        while time.time() < deadline:
            match = re.search(r"/c/([a-f0-9-]+)", page.url)
            if match:
                thread_id = match.group(1)
                break
            after_threads = await client.list_threads()
            new_ids = [thread["id"] for thread in after_threads if thread["id"] not in before_ids]
            if new_ids:
                thread_id = new_ids[0]
                log(f"Detected new sidebar thread id: {thread_id}")
                break
            await asyncio.sleep(0.5)

        log(f"URL after send: {page.url}")
        log(f"Captured thread id: {thread_id or '<missing>'}")
        if not thread_id:
            screenshot_path = log_dir / f"live_thread_delete_fast_missing_thread_{int(time.time())}.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            log(f"Saved failure screenshot: {screenshot_path}")
            log("FAILED: thread URL was not created after sending prompt.")
            return 5

        _, stop_button = await first_selector(page, Selectors.STOP_BUTTON, timeout=1000)
        if stop_button:
            log("Generation is still active; clicking stop before deletion.")
            try:
                await stop_button.click()
                await asyncio.sleep(2)
            except Exception as exc:
                log(f"Stop click failed but deletion will still be attempted: {exc!r}")

        log(f"Deleting thread {thread_id}")
        deleted = await client.delete_thread(thread_id)
        log(f"delete_thread returned: {deleted}")

        await asyncio.sleep(3)
        remaining = await page.query_selector(f"a[href*='/c/{thread_id}']")
        log(f"Sidebar link still present: {bool(remaining)}")
        log(f"Current URL after deletion: {page.url}")

        if deleted and remaining is None:
            log("PASS: thread was created and deleted.")
            return 0

        log("FAILED: delete flow did not fully verify.")
        return 6
    except Exception as exc:
        log(f"FAILED with exception: {exc!r}")
        return 1
    finally:
        await browser.close()
        log(f"Log written to: {log_path}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
