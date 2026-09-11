"""
Diagnostic script for Google Gemini: check page state, input area, model switcher, and turns.

Connects to an existing Chrome instance via CDP on port 9222.
Usage:
    python scripts/diagnose_gemini.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")
from patchright.async_api import async_playwright
from src.gemini.selectors import GeminiSelectors


async def main() -> None:
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    except Exception as e:
        print(f"Failed to connect to CDP on 127.0.0.1:9222: {e}")
        await pw.stop()
        return

    pages = []
    for ctx in browser.contexts:
        for p in ctx.pages:
            if "gemini.google.com" in p.url:
                pages.append(p)

    if not pages:
        print("No open gemini.google.com tab found in the connected Chrome browser.")
        all_urls = [p.url for ctx in browser.contexts for p in ctx.pages]
        print(f"Open tabs ({len(all_urls)}): {all_urls}")
        await pw.stop()
        return

    page = pages[0]
    print("=" * 70)
    print(f"FOUND GEMINI TAB: {page.url}")
    print("=" * 70)

    # 1. Check Login State
    login_info = await page.evaluate(
        """
        () => {
            const hasAvatar = !!document.querySelector('a[aria-label*="Google Account"], img[alt*="Google Account"], #gb');
            const hasLoginBtn = !!document.querySelector('a[href*="accounts.google.com/ServiceLogin"]');
            return { hasAvatar, hasLoginBtn };
        }
        """
    )
    print(f"Login Status: Avatar/Account={login_info['hasAvatar']}, LoginButton={login_info['hasLoginBtn']}")

    # 2. Check Input Area & Send Button
    input_info = await page.evaluate(
        """
        () => {
            const input = document.querySelector('rich-textarea, .ql-editor, div[contenteditable="true"]');
            const sendBtn = document.querySelector('button[aria-label*="Send" i], button:has(mat-icon[data-mat-icon-name="send"])');
            const stopBtn = document.querySelector('button[aria-label*="Stop" i]');
            const micBtn = document.querySelector('speech-dictation-mic-button, button[aria-label*="dictation" i]');
            return {
                hasInput: !!input,
                inputText: input ? (input.innerText || '').trim() : '',
                hasSendBtn: !!sendBtn,
                sendVisible: sendBtn ? sendBtn.offsetParent !== null : false,
                hasStopBtn: !!stopBtn,
                hasMicBtn: !!micBtn,
            };
        }
        """
    )
    print(f"Input Area: {input_info}")

    # 3. Check Mode Switcher
    mode_info = await page.evaluate(
        """
        () => {
            const switcher = document.querySelector('bard-mode-switcher, button[data-test-id="bard-mode-menu-button"]');
            const labelEl = document.querySelector('bard-mode-switcher span.picker-primary-text, button[data-test-id="bard-mode-menu-button"] span.picker-primary-text');
            return {
                hasSwitcher: !!switcher,
                activeLabel: labelEl ? labelEl.innerText.trim() : (switcher ? switcher.innerText.trim() : 'N/A'),
            };
        }
        """
    )
    print(f"Mode Switcher: {mode_info}")

    # 4. Check Turns
    turns_info = await page.evaluate(
        """
        () => {
            const userQueries = document.querySelectorAll('user-query');
            const modelResponses = document.querySelectorAll('model-response');
            const results = [];

            modelResponses.forEach((mr, idx) => {
                const text = (mr.innerText || '').trim();
                const copyBtn = mr.querySelector('button[aria-label*="Copy" i], button:has(mat-icon[data-mat-icon-name="content_copy"])');
                results.push({
                    turn: idx + 1,
                    textLength: text.length,
                    textPreview: text.substring(0, 100).replace(/\\n/g, ' '),
                    hasCopyBtn: !!copyBtn,
                });
            });

            return {
                userQueryCount: userQueries.length,
                modelResponseCount: modelResponses.length,
                turns: results,
            };
        }
        """
    )
    print(f"\\nTurns: {turns_info['userQueryCount']} user queries, {turns_info['modelResponseCount']} assistant responses")
    for t in turns_info["turns"]:
        copy_tag = "[COPY OK]" if t["hasCopyBtn"] else "[NO COPY]"
        print(f"  Response #{t['turn']}: {t['textLength']} chars {copy_tag} - '{t['textPreview']}'")

    print("\\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())

