from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.browser.manager import BrowserManager
from src.config import Config


async def main() -> int:
    timeout_seconds = 900
    deadline = time.time() + timeout_seconds
    browser = BrowserManager()

    print("=" * 72, flush=True)
    print("CatGPT login helper", flush=True)
    print(f"Browser data dir: {Config.BROWSER_DATA_DIR}", flush=True)
    print("A browser window will open. Log into ChatGPT there.", flush=True)
    print("This helper will close automatically once login is detected.", flush=True)
    print("=" * 72, flush=True)

    try:
        await browser.start()
        await browser.navigate(Config.CHATGPT_URL)

        while time.time() < deadline:
            if await browser.is_logged_in():
                print("LOGIN DETECTED", flush=True)
                await asyncio.sleep(3)
                return 0
            print("Waiting for login...", flush=True)
            await asyncio.sleep(5)

        print("Timed out waiting for login.", flush=True)
        return 1
    finally:
        await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
