"""
Response completion detector.

The ChatGPT web UI changes often, so this module avoids depending on a single
turn container shape. It scans several known message/turn patterns, aligns all
wait/extract work to the newest assistant turn, and captures diagnostics when
the browser cannot prove a response is complete.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from patchright.async_api import Page
from patchright._impl._errors import TargetClosedError

from src.browser.human import idle_mouse_movement
from src.config import Config
from src.log import setup_logging
from src.selectors import Selectors

log = setup_logging("detector")


_CONVERSATION_SNAPSHOT_JS = r"""
() => {
    const textHash = (value) => {
        const text = String(value || "");
        let hash = 0;
        for (let i = 0; i < text.length; i++) {
            hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
        }
        return Math.abs(hash).toString(36);
    };

    const textOf = (el) => ((el && (el.innerText || el.textContent)) || "").trim();

    const isVisible = (el) => {
        if (!el) return false;
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== "hidden" &&
            style.display !== "none";
    };

    const copySelector = [
        'button[data-testid="copy-turn-action-button"]',
        'button[data-testid*="copy" i]',
        'button[aria-label*="copy" i]',
        '[role="button"][aria-label*="copy" i]'
    ].join(",");

    const preferredTurnCopySelector = [
        'button[data-testid="copy-turn-action-button"]',
        'button[aria-label="Copy response" i]',
        'button[aria-label="Copy message" i]',
        '[role="button"][aria-label="Copy response" i]',
        '[role="button"][aria-label="Copy message" i]'
    ].join(",");

    const isCodeCopyButton = (el) => {
        if (!el) return false;
        const label = [
            el.getAttribute("aria-label") || "",
            el.getAttribute("data-testid") || "",
            textOf(el).slice(0, 80)
        ].join(" ").toLowerCase();
        return Boolean(el.closest("pre, code, .code-block, [data-testid*='code' i]")) ||
            label.includes("copy code");
    };
    const isTableCopyButton = (el) => {
        if (!el) return false;
        const label = [
            el.getAttribute("aria-label") || "",
            el.getAttribute("data-testid") || "",
            textOf(el).slice(0, 80)
        ].join(" ").toLowerCase();
        return Boolean(el.closest("._tableContainer, ._tableWrapper, table")) ||
            label.includes("copy table");
    };
    const isTurnCopyButton = (el) => !isCodeCopyButton(el) && !isTableCopyButton(el);

    const findTurnCopyButton = (root) => {
        const preferred = Array.from(root.querySelectorAll(preferredTurnCopySelector))
            .filter(isTurnCopyButton);
        const visiblePreferred = preferred.find(isVisible);
        if (visiblePreferred) return visiblePreferred;
        if (preferred.length) return preferred[preferred.length - 1];

        const fallback = Array.from(root.querySelectorAll(copySelector))
            .filter(isTurnCopyButton);
        const visibleFallback = fallback.filter(isVisible);
        return visibleFallback[visibleFallback.length - 1] || fallback[fallback.length - 1] || null;
    };

    const stopSelector = [
        'button[data-testid="stop-button"]',
        'button[aria-label="Stop answering"]',
        'button[aria-label="Stop generating"]',
        'button[aria-label*="stop" i]'
    ].join(",");

    const sendSelector = [
        'button[data-testid="send-button"]',
        '#composer-submit-button',
        'button[aria-label="Send prompt"]',
        'button[aria-label*="send" i]'
    ].join(",");

    const hasGeneratedImage = (root) => {
        if (!root) return false;
        if (root.querySelector('img[alt="Generated image"], img[alt*="generated" i], div[id^="image-"], div[class*="imagegen-image"]')) {
            return true;
        }
        for (const img of root.querySelectorAll("img")) {
            const w = img.naturalWidth || img.width || 0;
            const h = img.naturalHeight || img.height || 0;
            const src = img.currentSrc || img.src || "";
            if ((w > 180 || h > 180) && (
                src.includes("backend-api/estuary") ||
                src.includes("files.oaiusercontent.com") ||
                src.includes("chatgpt.com/backend-api") ||
                src.startsWith("blob:") ||
                src.startsWith("data:image/")
            )) {
                return true;
            }
        }
        return false;
    };

    const roleOf = (root) => {
        if (!root) return "";
        const ownRole = root.getAttribute("data-message-author-role") || root.getAttribute("data-turn") || "";
        if (ownRole === "assistant" || ownRole === "user") return ownRole;
        const roleEl = root.querySelector('[data-message-author-role="assistant"], [data-message-author-role="user"]');
        if (roleEl) return roleEl.getAttribute("data-message-author-role") || "";
        if (root.matches(".agent-turn") || root.querySelector(".agent-turn") || hasGeneratedImage(root)) return "assistant";
        const label = [
            root.getAttribute("aria-label") || "",
            root.getAttribute("data-testid") || "",
            textOf(root).slice(0, 80)
        ].join(" ").toLowerCase();
        if (label.includes("chatgpt said")) return "assistant";
        if (label.includes("you said")) return "user";
        return "";
    };

    const stableIdOf = (root) => {
        const attrs = ["data-message-id", "data-turn-id", "data-testid", "data-testid-message-id", "id"];
        for (const attr of attrs) {
            const value = root.getAttribute(attr);
            if (value) return value;
        }
        const child = root.querySelector("[data-message-id], [data-turn-id], [data-testid-message-id]");
        if (child) {
            for (const attr of attrs) {
                const value = child.getAttribute(attr);
                if (value) return value;
            }
        }
        return "";
    };

    const bestTextFor = (root, role) => {
        const selectors = role === "assistant" ? [
            '[data-message-author-role="assistant"] .markdown',
            '[data-message-author-role="assistant"] .prose',
            '[data-message-author-role="assistant"]',
            ".markdown",
            ".prose",
            "[data-start]",
        ] : [
            '[data-message-author-role="user"]',
            '[data-testid*="user" i]',
        ];
        const parts = [];
        if (role && root.matches(`[data-message-author-role="${role}"]`)) {
            const own = textOf(root);
            if (own) parts.push(own);
        }
        for (const selector of selectors) {
            for (const el of root.querySelectorAll(selector)) {
                const text = textOf(el);
                if (text) parts.push(text);
            }
        }
        if (!parts.length) {
            const text = textOf(root);
            if (text) parts.push(text);
        }
        parts.sort((a, b) => b.length - a.length);
        return (parts[0] || "").trim();
    };

    const rootSet = new Set();
    const addRoot = (el) => {
        if (!el) return;
        const promoted = el.closest([
            "article",
            'section[data-testid^="conversation-turn-"]',
            'div[data-testid^="conversation-turn-"]',
            'section[data-turn]',
            'div[data-turn]'
        ].join(",")) || el;
        rootSet.add(promoted);
    };

    const selectors = [
        "article",
        'section[data-testid^="conversation-turn-"]',
        'div[data-testid^="conversation-turn-"]',
        '[data-testid*="conversation-turn" i]',
        'section[data-turn]',
        'div[data-turn]',
        '[data-message-author-role="assistant"]',
        '[data-message-author-role="user"]',
        ".agent-turn",
        'div[class*="group/conversation-turn"]'
    ];

    for (const selector of selectors) {
        for (const el of document.querySelectorAll(selector)) addRoot(el);
    }

    const roots = Array.from(rootSet)
        .filter((el) => document.documentElement.contains(el))
        .map((el) => ({ el, rect: el.getBoundingClientRect(), role: roleOf(el) }))
        .filter((item) => item.role === "assistant" || item.role === "user")
        .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);

    const turns = [];
    const seen = new Set();
    for (const item of roots) {
        const root = item.el;
        const role = item.role;
        const rect = item.rect;
        const text = bestTextFor(root, role);
        const hasImage = hasGeneratedImage(root);
        const hasCopyButton = Boolean(findTurnCopyButton(root));
        if (role === "assistant" && !text && !hasImage && !hasCopyButton) continue;
        if (role === "user" && !text) continue;

        const stableId = stableIdOf(root);
        const key = stableId || `${role}:${Math.round(rect.top)}:${textHash(text.slice(0, 250))}`;
        if (seen.has(`${role}:${key}`)) continue;
        seen.add(`${role}:${key}`);

        const index = turns.length;
        const signatureToken = stableId || `${Math.round(rect.top)}:${textHash(text.slice(0, 500))}`;
        const signature = `${role}:${signatureToken}`;
        turns.push({
            role,
            index,
            signature,
            stableId,
            hasCopyButton,
            hasImage,
            text,
            textLength: text.length,
            rect: {
                top: rect.top,
                left: rect.left,
                width: rect.width,
                height: rect.height,
                x: rect.left + rect.width / 2,
                y: rect.top + Math.min(Math.max(rect.height / 2, 20), Math.max(rect.height - 10, 20)),
            },
            htmlSample: (root.outerHTML || "").slice(0, 1200),
        });
    }

    const assistantTurns = turns.filter((turn) => turn.role === "assistant");
    const userTurns = turns.filter((turn) => turn.role === "user");
    const visibleStops = Array.from(document.querySelectorAll(stopSelector)).filter(isVisible);
    const visibleSends = Array.from(document.querySelectorAll(sendSelector)).filter(isVisible);
    const main = document.querySelector("main") || document.body;
    const composer = document.querySelector("#prompt-textarea, div[contenteditable='true'][id='prompt-textarea'], div[contenteditable='true']");
    const composerText = textOf(composer);

    return {
        url: location.href,
        title: document.title || "",
        assistantTurns,
        userTurns,
        latestAssistant: assistantTurns.length ? assistantTurns[assistantTurns.length - 1] : null,
        latestUser: userTurns.length ? userTurns[userTurns.length - 1] : null,
        assistantCount: assistantTurns.length,
        userCount: userTurns.length,
        copyButtonCount: assistantTurns.filter((turn) => turn.hasCopyButton).length,
        hasStopButton: visibleStops.length > 0,
        hasSendButton: visibleSends.length > 0,
        composerTextLength: composerText.length,
        composerTextSample: composerText.slice(0, 500),
        mainTextSample: textOf(main).slice(0, 5000),
        stats: {
            articleCount: document.querySelectorAll("article").length,
            roleNodeCount: document.querySelectorAll("[data-message-author-role]").length,
            copyButtonNodeCount: document.querySelectorAll(copySelector).length,
            stopButtonNodeCount: document.querySelectorAll(stopSelector).length,
        },
    };
}
"""


_CLICK_LATEST_COPY_BUTTON_JS = r"""
(previousSignature) => {
    const textHash = (value) => {
        const text = String(value || "");
        let hash = 0;
        for (let i = 0; i < text.length; i++) {
            hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
        }
        return Math.abs(hash).toString(36);
    };
    const textOf = (el) => ((el && (el.innerText || el.textContent)) || "").trim();
    const isVisible = (el) => {
        if (!el) return false;
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== "hidden" &&
            style.display !== "none";
    };
    const copySelector = [
        'button[data-testid="copy-turn-action-button"]',
        'button[data-testid*="copy" i]',
        'button[aria-label*="copy" i]',
        '[role="button"][aria-label*="copy" i]'
    ].join(",");
    const preferredTurnCopySelector = [
        'button[data-testid="copy-turn-action-button"]',
        'button[aria-label="Copy response" i]',
        'button[aria-label="Copy message" i]',
        '[role="button"][aria-label="Copy response" i]',
        '[role="button"][aria-label="Copy message" i]'
    ].join(",");
    const hasGeneratedImage = (root) => {
        if (!root) return false;
        if (root.querySelector('img[alt="Generated image"], img[alt*="generated" i], div[id^="image-"], div[class*="imagegen-image"]')) return true;
        for (const img of root.querySelectorAll("img")) {
            const w = img.naturalWidth || img.width || 0;
            const h = img.naturalHeight || img.height || 0;
            const src = img.currentSrc || img.src || "";
            if ((w > 180 || h > 180) && (src.includes("backend-api/estuary") || src.includes("files.oaiusercontent.com") || src.startsWith("blob:") || src.startsWith("data:image/"))) return true;
        }
        return false;
    };
    const isCodeCopyButton = (el) => {
        if (!el) return false;
        const label = [
            el.getAttribute("aria-label") || "",
            el.getAttribute("data-testid") || "",
            textOf(el).slice(0, 80)
        ].join(" ").toLowerCase();
        return Boolean(el.closest("pre, code, .code-block, [data-testid*='code' i]")) ||
            label.includes("copy code");
    };
    const isTableCopyButton = (el) => {
        if (!el) return false;
        const label = [
            el.getAttribute("aria-label") || "",
            el.getAttribute("data-testid") || "",
            textOf(el).slice(0, 80)
        ].join(" ").toLowerCase();
        return Boolean(el.closest("._tableContainer, ._tableWrapper, table")) ||
            label.includes("copy table");
    };
    const isTurnCopyButton = (el) => !isCodeCopyButton(el) && !isTableCopyButton(el);
    const findTurnCopyButton = (root) => {
        const preferred = Array.from(root.querySelectorAll(preferredTurnCopySelector))
            .filter(isTurnCopyButton);
        const visiblePreferred = preferred.find(isVisible);
        if (visiblePreferred) return visiblePreferred;
        if (preferred.length) return preferred[preferred.length - 1];

        const fallback = Array.from(root.querySelectorAll(copySelector))
            .filter(isTurnCopyButton);
        const visibleFallback = fallback.filter(isVisible);
        return visibleFallback[visibleFallback.length - 1] || fallback[fallback.length - 1] || null;
    };
    const roleOf = (root) => {
        const ownRole = root.getAttribute("data-message-author-role") || root.getAttribute("data-turn") || "";
        if (ownRole === "assistant" || ownRole === "user") return ownRole;
        const roleEl = root.querySelector('[data-message-author-role="assistant"], [data-message-author-role="user"]');
        if (roleEl) return roleEl.getAttribute("data-message-author-role") || "";
        if (root.matches(".agent-turn") || root.querySelector(".agent-turn") || hasGeneratedImage(root)) return "assistant";
        return "";
    };
    const stableIdOf = (root) => {
        const attrs = ["data-message-id", "data-turn-id", "data-testid", "data-testid-message-id", "id"];
        for (const attr of attrs) {
            const value = root.getAttribute(attr);
            if (value) return value;
        }
        const child = root.querySelector("[data-message-id], [data-turn-id], [data-testid-message-id]");
        if (child) {
            for (const attr of attrs) {
                const value = child.getAttribute(attr);
                if (value) return value;
            }
        }
        return "";
    };
    const bestTextFor = (root, role) => {
        const selectors = role === "assistant" ? [
            '[data-message-author-role="assistant"] .markdown',
            '[data-message-author-role="assistant"] .prose',
            '[data-message-author-role="assistant"]',
            ".markdown",
            ".prose",
            "[data-start]"
        ] : ['[data-message-author-role="user"]'];
        const parts = [];
        if (root.matches(`[data-message-author-role="${role}"]`)) {
            const own = textOf(root);
            if (own) parts.push(own);
        }
        for (const selector of selectors) {
            for (const el of root.querySelectorAll(selector)) {
                const text = textOf(el);
                if (text) parts.push(text);
            }
        }
        if (!parts.length) parts.push(textOf(root));
        parts.sort((a, b) => b.length - a.length);
        return (parts[0] || "").trim();
    };
    const rootSet = new Set();
    const addRoot = (el) => {
        if (!el) return;
        rootSet.add(el.closest([
            "article",
            'section[data-testid^="conversation-turn-"]',
            'div[data-testid^="conversation-turn-"]',
            'section[data-turn]',
            'div[data-turn]'
        ].join(",")) || el);
    };
    for (const selector of [
        "article",
        'section[data-testid^="conversation-turn-"]',
        'div[data-testid^="conversation-turn-"]',
        '[data-testid*="conversation-turn" i]',
        'section[data-turn]',
        'div[data-turn]',
        '[data-message-author-role="assistant"]',
        ".agent-turn",
        'div[class*="group/conversation-turn"]'
    ]) {
        for (const el of document.querySelectorAll(selector)) addRoot(el);
    }
    const roots = Array.from(rootSet)
        .map((el) => ({ el, rect: el.getBoundingClientRect(), role: roleOf(el) }))
        .filter((item) => item.role === "assistant")
        .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
    const turns = [];
    const seen = new Set();
    for (const item of roots) {
        const text = bestTextFor(item.el, item.role);
        const stableId = stableIdOf(item.el);
        const key = stableId || `${item.role}:${Math.round(item.rect.top)}:${textHash(text.slice(0, 250))}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const index = turns.length;
        const signatureToken = stableId || `${Math.round(item.rect.top)}:${textHash(text.slice(0, 500))}`;
        turns.push({
            root: item.el,
            rect: item.rect,
            signature: `${item.role}:${signatureToken}`,
        });
    }
    const latest = turns.length ? turns[turns.length - 1] : null;
    if (!latest) return { clicked: false, reason: "no-assistant-turn", signature: null };
    if (previousSignature && latest.signature === previousSignature) {
        return { clicked: false, reason: "stale-turn", signature: latest.signature };
    }

    let btn = findTurnCopyButton(latest.root);
    if (!btn) {
        const rootRect = latest.root.getBoundingClientRect();
        const nearby = Array.from(document.querySelectorAll(copySelector))
            .filter((candidate) => {
                const rect = candidate.getBoundingClientRect();
                return isTurnCopyButton(candidate) &&
                    rect.top >= rootRect.top - 10 &&
                    rect.top <= rootRect.bottom + 120 &&
                    rect.left >= rootRect.left - 60 &&
                    rect.left <= rootRect.right + 60;
            })
            .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
        btn = nearby[nearby.length - 1] || null;
    }
    if (!btn) return { clicked: false, reason: "no-copy-button", signature: latest.signature };
    btn.click();
    return { clicked: true, reason: "ok", signature: latest.signature };
}
"""


_LATEST_IMAGE_EXTRACTION_JS = r"""
(previousSignature) => {
    const textHash = (value) => {
        const text = String(value || "");
        let hash = 0;
        for (let i = 0; i < text.length; i++) {
            hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
        }
        return Math.abs(hash).toString(36);
    };
    const textOf = (el) => ((el && (el.innerText || el.textContent)) || "").trim();
    const hasGeneratedImage = (root) => {
        if (!root) return false;
        if (root.querySelector('img[alt="Generated image"], img[alt*="generated" i], div[id^="image-"], div[class*="imagegen-image"]')) return true;
        for (const img of root.querySelectorAll("img")) {
            const w = img.naturalWidth || img.width || 0;
            const h = img.naturalHeight || img.height || 0;
            const src = img.currentSrc || img.src || "";
            if ((w > 180 || h > 180) && (src.includes("backend-api/estuary") || src.includes("files.oaiusercontent.com") || src.includes("chatgpt.com/backend-api") || src.startsWith("blob:") || src.startsWith("data:image/"))) return true;
        }
        return false;
    };
    const roleOf = (root) => {
        const ownRole = root.getAttribute("data-message-author-role") || root.getAttribute("data-turn") || "";
        if (ownRole === "assistant" || ownRole === "user") return ownRole;
        const roleEl = root.querySelector('[data-message-author-role="assistant"], [data-message-author-role="user"]');
        if (roleEl) return roleEl.getAttribute("data-message-author-role") || "";
        if (root.matches(".agent-turn") || root.querySelector(".agent-turn") || hasGeneratedImage(root)) return "assistant";
        return "";
    };
    const stableIdOf = (root) => {
        const attrs = ["data-message-id", "data-turn-id", "data-testid", "data-testid-message-id", "id"];
        for (const attr of attrs) {
            const value = root.getAttribute(attr);
            if (value) return value;
        }
        const child = root.querySelector("[data-message-id], [data-turn-id], [data-testid-message-id]");
        if (child) {
            for (const attr of attrs) {
                const value = child.getAttribute(attr);
                if (value) return value;
            }
        }
        return "";
    };
    const rootSet = new Set();
    const addRoot = (el) => {
        if (!el) return;
        rootSet.add(el.closest([
            "article",
            'section[data-testid^="conversation-turn-"]',
            'div[data-testid^="conversation-turn-"]',
            'section[data-turn]',
            'div[data-turn]'
        ].join(",")) || el);
    };
    for (const selector of [
        "article",
        'section[data-testid^="conversation-turn-"]',
        'div[data-testid^="conversation-turn-"]',
        '[data-testid*="conversation-turn" i]',
        'section[data-turn]',
        'div[data-turn]',
        '[data-message-author-role="assistant"]',
        ".agent-turn",
        'div[class*="group/conversation-turn"]'
    ]) {
        for (const el of document.querySelectorAll(selector)) addRoot(el);
    }
    const roots = Array.from(rootSet)
        .map((el) => ({ el, rect: el.getBoundingClientRect(), role: roleOf(el) }))
        .filter((item) => item.role === "assistant" && hasGeneratedImage(item.el))
        .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
    const turns = [];
    const seen = new Set();
    for (const item of roots) {
        const text = textOf(item.el);
        const stableId = stableIdOf(item.el);
        const key = stableId || `${item.role}:${Math.round(item.rect.top)}:${textHash(text.slice(0, 250))}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const index = turns.length;
        const signatureToken = stableId || `${Math.round(item.rect.top)}:${textHash(text.slice(0, 500))}`;
        turns.push({
            root: item.el,
            signature: `${item.role}:${signatureToken}`,
        });
    }
    const latest = turns.length ? turns[turns.length - 1] : null;
    if (!latest || (previousSignature && latest.signature === previousSignature)) return [];

    let images = Array.from(latest.root.querySelectorAll([
        'img[alt="Generated image"]',
        'img[alt*="generated" i]',
        'div[id^="image-"] img',
        'div[class*="imagegen-image"] img'
    ].join(",")));
    if (!images.length) {
        images = Array.from(latest.root.querySelectorAll("img")).filter((img) => {
            const w = img.naturalWidth || img.width || 0;
            const h = img.naturalHeight || img.height || 0;
            const src = img.currentSrc || img.src || "";
            return (w > 180 || h > 180) && (
                src.includes("backend-api/estuary") ||
                src.includes("files.oaiusercontent.com") ||
                src.includes("chatgpt.com/backend-api") ||
                src.startsWith("blob:") ||
                src.startsWith("data:image/")
            );
        });
    }

    const seenUrls = new Set();
    const turnText = textOf(latest.root);
    const titleCandidates = [];
    for (const el of latest.root.querySelectorAll("button, span, div")) {
        const text = textOf(el);
        if (!text || text.length < 5 || text.length > 240) continue;
        if (/creating image|image created|generated image|image/i.test(text)) {
            titleCandidates.push(text.replace(/creating image/ig, "").replace(/image created/ig, "").trim());
        }
    }
    if (!titleCandidates.length) {
        for (const line of turnText.split(/\n+/)) {
            const cleaned = line.trim();
            if (cleaned.length > 5 && cleaned.length < 240 && !/chatgpt said|copy|download/i.test(cleaned)) {
                titleCandidates.push(cleaned);
            }
        }
    }
    const title = (titleCandidates.find(Boolean) || "").trim();

    const results = [];
    for (const img of images) {
        const url = img.currentSrc || img.src || "";
        if (!url || seenUrls.has(url)) continue;
        seenUrls.add(url);
        results.push({
            url,
            alt: img.alt || "",
            title,
            turnSignature: latest.signature,
        });
    }
    return results;
}
"""


def normalize_assistant_text(text: str | None) -> str:
    """Normalize extracted assistant text for validation and comparisons."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^ChatGPT said:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^You said:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def is_incomplete_response_text(text: str | None) -> bool:
    """Return true when text looks like transient thinking/status UI."""
    cleaned = normalize_assistant_text(text)
    if not cleaned:
        return True

    lower = cleaned.lower()
    markers = [
        "pro thinking",
        "thinking",
        "searching for",
        "searching the web",
        "analyzing",
        "working on",
        "please wait",
        "gathering",
        "creating image",
        "generating image",
        "image is being",
        "just a moment",
        "loading",
    ]

    if any(marker in lower for marker in markers):
        if len(cleaned) < 240:
            return True
        if lower.startswith((
            "pro thinking",
            "thinking",
            "searching",
            "analyzing",
            "working on",
            "gathering",
            "creating image",
            "generating image",
            "loading",
        )):
            return True

    return False


def _empty_snapshot() -> dict[str, Any]:
    return {
        "found": False,
        "index": -1,
        "signature": None,
        "stableId": "",
        "hasCopyButton": False,
        "hasImage": False,
        "hasStopButton": False,
        "text": "",
        "textLength": 0,
        "rect": {},
    }


def _empty_conversation_snapshot() -> dict[str, Any]:
    return {
        "url": "",
        "title": "",
        "assistantTurns": [],
        "userTurns": [],
        "latestAssistant": None,
        "latestUser": None,
        "assistantCount": 0,
        "userCount": 0,
        "copyButtonCount": 0,
        "hasStopButton": False,
        "hasSendButton": False,
        "composerTextLength": 0,
        "composerTextSample": "",
        "mainTextSample": "",
        "stats": {},
    }


async def _conversation_snapshot(page: Page) -> dict[str, Any]:
    try:
        snapshot = await page.evaluate(_CONVERSATION_SNAPSHOT_JS)
    except Exception as e:
        log.debug(f"Conversation snapshot failed: {e}")
        return _empty_conversation_snapshot()

    if not isinstance(snapshot, dict):
        return _empty_conversation_snapshot()

    normalized = _empty_conversation_snapshot()
    normalized.update(snapshot)
    for key in ("assistantTurns", "userTurns"):
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
    return normalized


async def _latest_assistant_turn_snapshot(page: Page) -> dict[str, Any]:
    """Return metadata for the latest assistant turn across known UI layouts."""
    conversation = await _conversation_snapshot(page)
    latest = conversation.get("latestAssistant")
    if not isinstance(latest, dict):
        snapshot = _empty_snapshot()
    else:
        snapshot = _empty_snapshot()
        snapshot.update(latest)
        snapshot["found"] = True
    snapshot["hasStopButton"] = bool(conversation.get("hasStopButton"))
    return snapshot


async def get_latest_assistant_turn_signature(page: Page) -> str | None:
    """Return signature for the latest assistant turn, if available."""
    snapshot = await _latest_assistant_turn_snapshot(page)
    signature = snapshot.get("signature")
    return signature if isinstance(signature, str) and signature else None


async def get_latest_user_turn_signature(page: Page) -> str | None:
    """Return signature for the latest user turn, if available."""
    conversation = await _conversation_snapshot(page)
    latest = conversation.get("latestUser")
    if not isinstance(latest, dict):
        return None
    signature = latest.get("signature")
    return signature if isinstance(signature, str) and signature else None


async def count_assistant_messages(page: Page) -> int:
    """Count assistant turns using the robust conversation scanner."""
    snapshot = await _conversation_snapshot(page)
    return int(snapshot.get("assistantCount") or 0)


async def count_user_messages(page: Page) -> int:
    """Count user turns using the robust conversation scanner."""
    snapshot = await _conversation_snapshot(page)
    return int(snapshot.get("userCount") or 0)


async def page_has_stop_button(page: Page) -> bool:
    """Return whether a visible stop button is currently present."""
    snapshot = await _conversation_snapshot(page)
    return bool(snapshot.get("hasStopButton"))


async def _detect_image_in_latest_turn(page: Page, previous_turn_signature: str | None = None) -> bool:
    """Check if the newest assistant turn contains an image."""
    snapshot = await _latest_assistant_turn_snapshot(page)
    signature = snapshot.get("signature")
    is_new_turn = previous_turn_signature is None or (
        isinstance(signature, str) and signature != previous_turn_signature
    )
    return bool(is_new_turn and snapshot.get("hasImage"))


async def _count_copy_buttons(page: Page) -> int:
    """Count assistant turns that currently expose a copy button."""
    snapshot = await _conversation_snapshot(page)
    return int(snapshot.get("copyButtonCount") or 0)


def _remaining_timeout_ms(start: float, timeout_ms: int) -> int:
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return max(0, timeout_ms - elapsed_ms)


async def _wait_for_new_turn_signature(
    page: Page,
    previous_turn_signature: str,
    timeout_ms: int,
) -> bool:
    """Wait until latest assistant-turn signature differs from previous one."""
    elapsed = 0.0
    poll_interval = Config.POLL_INTERVAL_MS / 1000
    heartbeat = 10

    while elapsed * 1000 < timeout_ms:
        snapshot = await _latest_assistant_turn_snapshot(page)
        signature = snapshot.get("signature")
        if isinstance(signature, str) and signature and signature != previous_turn_signature:
            log.debug(f"New assistant turn detected: {signature} (prev: {previous_turn_signature})")
            return True

        if int(elapsed) > 0 and int(elapsed) % heartbeat == 0:
            log.debug(f"Still waiting for new assistant turn... ({int(elapsed)}s)")

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    log.debug("Timed out waiting for a new assistant-turn signature")
    return False


async def wait_for_response_complete(
    page: Page,
    expected_msg_count: int | None = None,
    timeout_ms: int | None = None,
    previous_turn_signature: str | None = None,
) -> bool:
    """
    Wait until ChatGPT finishes generating the current response.

    The total wait is bounded by one timeout budget. Fast positive signals
    (copy button, image, stop button disappear) are used first, then text
    stability gets the remaining budget.
    """
    timeout = timeout_ms or Config.RESPONSE_TIMEOUT
    start = time.monotonic()
    log.info(f"Waiting for response (timeout: {timeout}ms)...")

    pre_copy_count = await _count_copy_buttons(page)
    log.debug(f"Copy buttons before send: {pre_copy_count}")

    if previous_turn_signature:
        wait_ms = min(30000, _remaining_timeout_ms(start, timeout))
        if wait_ms > 0:
            log.debug(f"Previous assistant turn signature: {previous_turn_signature}")
            await _wait_for_new_turn_signature(page, previous_turn_signature, timeout_ms=wait_ms)
    elif expected_msg_count is not None:
        log.debug(f"Waiting for assistant message #{expected_msg_count}...")
        waited = 0
        wait_ms = min(30000, _remaining_timeout_ms(start, timeout))
        while waited < wait_ms:
            current_count = await count_assistant_messages(page)
            if current_count >= expected_msg_count:
                log.debug(f"Assistant message target reached (count: {current_count})")
                break
            await asyncio.sleep(0.5)
            waited += 500

    remaining = _remaining_timeout_ms(start, timeout)
    if remaining <= 0:
        return False

    log.debug("Waiting briefly for copy button or image on latest assistant turn...")
    quick_signal_timeout = min(max(10000, timeout // 4), remaining)
    completed = await _wait_for_copy_button_or_image(
        page,
        pre_copy_count,
        quick_signal_timeout,
        previous_turn_signature,
    )
    if completed == "copy":
        log.info("Response complete - copy button appeared on latest turn")
        return True
    if completed == "image":
        log.info("Response complete - generated image detected on latest turn")
        return True

    remaining = _remaining_timeout_ms(start, timeout)
    if remaining <= 0:
        return False

    log.info("Copy/image completion not detected, trying stop-button strategy...")
    try:
        result = await _wait_via_stop_button(page, remaining)
        if result:
            return True
    except Exception as e:
        log.debug(f"Stop button strategy failed: {e}")

    remaining = _remaining_timeout_ms(start, timeout)
    if remaining <= 0:
        return False

    log.info("Falling back to text-stability detection...")
    try:
        return await _wait_via_text_stability(page, remaining, previous_turn_signature)
    except Exception as e:
        log.error(f"All strategies failed: {e}")
        return False


async def _check_page_error(page: Page) -> str | None:
    """Check if the page is showing an error state (DNS failure, crash, etc.).

    Returns error description string if an error is detected, None otherwise.
    """
    try:
        error = await page.evaluate(
            """
            () => {
                // Chrome error pages
                const body = document.body ? document.body.innerText : '';
                if (body.includes('DNS_PROBE_FINISHED_NXDOMAIN')) return 'DNS_PROBE_FINISHED_NXDOMAIN';
                if (body.includes('ERR_NAME_NOT_RESOLVED')) return 'ERR_NAME_NOT_RESOLVED';
                if (body.includes('ERR_CONNECTION_REFUSED')) return 'ERR_CONNECTION_REFUSED';
                if (body.includes('ERR_INTERNET_DISCONNECTED')) return 'ERR_INTERNET_DISCONNECTED';
                if (body.includes('ERR_CONNECTION_TIMED_OUT')) return 'ERR_CONNECTION_TIMED_OUT';
                // ChatGPT error states
                if (body.includes('Something went wrong')) return 'ChatGPT_something_went_wrong';
                if (body.includes("We're experiencing high demand")) return 'ChatGPT_high_demand';
                if (document.title && document.title.includes('is not available')) return 'page_not_available';
                return null;
            }
            """
        )
        return error
    except Exception:
        return None


async def _wait_for_copy_button_or_image(
    page: Page,
    pre_copy_count: int,
    timeout_ms: int,
    previous_turn_signature: str | None = None,
) -> str | None:
    """Wait for either copy-button readiness or generated image on the latest turn."""
    elapsed = 0.0
    poll_interval = Config.POLL_INTERVAL_MS / 1000
    heartbeat = 10
    first_snapshot_logged = False

    while elapsed * 1000 < timeout_ms:
        try:
            snapshot = await _latest_assistant_turn_snapshot(page)
        except TargetClosedError:
            log.error("Page/browser closed while waiting for response")
            return None
        except Exception as e:
            log.warning(f"Snapshot failed ({type(e).__name__}): {e}")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            continue

        signature = snapshot.get("signature")
        is_new_turn = previous_turn_signature is None or (
            isinstance(signature, str) and signature != previous_turn_signature
        )

        # Log the first snapshot for diagnostics
        if not first_snapshot_logged and elapsed >= 2:
            first_snapshot_logged = True
            turn_text = (snapshot.get("text") or "")[:200]
            all_turns = await _dump_all_turns(page)
            log.debug(
                f"First snapshot at {int(elapsed)}s | "
                f"prev_sig={previous_turn_signature} cur_sig={signature} "
                f"is_new={is_new_turn} copy={snapshot.get('hasCopyButton')} "
                f"text[:{len(turn_text)}]={turn_text!r}"
            )
            log.debug(f"All turns ({len(all_turns)}): {all_turns}")

        if is_new_turn and snapshot.get("hasCopyButton"):
            log.info(
                f"Copy button detected on latest turn {signature}"
            )
            return "copy"

        if previous_turn_signature is None and await _count_copy_buttons(page) > pre_copy_count:
            log.info("Response complete - copy button count increased")
            return "copy"

        if is_new_turn and snapshot.get("hasImage"):
            await asyncio.sleep(1.0)
            log.debug(f"Generated image detected on latest turn {signature}")
            return "image"

        if int(elapsed) > 0 and int(elapsed) % heartbeat == 0:
            log.debug(f"Still waiting for copy button or image... ({int(elapsed)}s)")
            await idle_mouse_movement(page)

            # Check for page-level errors every heartbeat to fail fast
            page_error = await _check_page_error(page)
            if page_error:
                log.error(f"Page error detected while waiting: {page_error}")
                return None

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    # Diagnostic: save screenshot on timeout
    try:
        await page.screenshot(path="logs/detector_timeout.png")
        log.info("Saved timeout screenshot to logs/detector_timeout.png")
    except Exception as e:
        log.debug(f"Could not save timeout screenshot: {e}")

    log.warning(f"Neither copy button nor image found after {int(elapsed)}s")
    return None


async def _wait_via_stop_button(page: Page, timeout_ms: int) -> bool:
    """Wait for stop button appear -> disappear cycle, or disappear if already visible."""
    stop_selector = ", ".join(Selectors.STOP_BUTTON)
    elapsed = 0
    heartbeat_interval = 5

    if not await page_has_stop_button(page):
        log.debug("Waiting for stop button to appear...")
        try:
            await page.wait_for_selector(stop_selector, state="visible", timeout=min(10000, timeout_ms))
            log.info("Stop button appeared - response is streaming")
        except Exception:
            log.debug("Stop button never appeared (short response or selector changed)")
            return False
    else:
        log.info("Stop button visible - response is streaming")

    log.debug("Waiting for stop button to disappear...")
    while elapsed * 1000 < timeout_ms:
        if not await page_has_stop_button(page):
            log.info("Stop button disappeared - streaming done")
            return True
        await asyncio.sleep(heartbeat_interval)
        elapsed += heartbeat_interval
        log.debug(f"Still streaming... ({elapsed}s elapsed)")
        await idle_mouse_movement(page)

    log.warning(f"Timed out after {elapsed}s waiting for stop button")
    return False


async def _wait_via_text_stability(
    page: Page,
    timeout_ms: int,
    previous_turn_signature: str | None = None,
) -> bool:
    """Last resort: poll latest assistant-turn text and wait until stable."""
    stable_count = 0
    required_stable = 4
    last_text = ""
    elapsed = 0.0
    poll_interval = Config.POLL_INTERVAL_MS / 1000

    while elapsed * 1000 < timeout_ms:
        snapshot = await _latest_assistant_turn_snapshot(page)
        signature = snapshot.get("signature")
        text = snapshot.get("text") if isinstance(snapshot.get("text"), str) else ""

        if previous_turn_signature and signature == previous_turn_signature:
            stable_count = 0
            last_text = ""
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            continue

        if snapshot.get("hasImage"):
            await asyncio.sleep(1.0)
            log.info("Generated image detected during text-stability wait")
            return True

        if text and text == last_text:
            stable_count += 1
            log.debug(f"Text stable ({stable_count}/{required_stable})")
            if stable_count >= required_stable:
                if snapshot.get("hasStopButton"):
                    log.debug("Text is stable but stop button remains visible; continuing wait")
                    stable_count = 0
                elif is_incomplete_response_text(text) and not bool(snapshot.get("hasCopyButton")):
                    log.debug("Stable text looks like transient status; continuing wait")
                    stable_count = 0
                else:
                    log.info("Response text stabilized - complete")
                    return True
        else:
            stable_count = 0
            last_text = text

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    log.warning(f"Text stability timed out after {int(elapsed)}s")
    return False


async def extract_last_response_via_copy(
    page: Page,
    previous_turn_signature: str | None = None,
) -> str:
    """
    Extract latest assistant response by clicking copy on the latest turn.

    Falls back to DOM text from the same newest assistant turn.
    """
    log.debug("Attempting extraction via latest-turn copy button...")

    try:
        await page.context.grant_permissions(["clipboard-read", "clipboard-write"])

        if previous_turn_signature:
            await _wait_for_new_turn_signature(page, previous_turn_signature, timeout_ms=8000)

        latest = await _latest_assistant_turn_snapshot(page)
        rect = latest.get("rect") if isinstance(latest.get("rect"), dict) else {}
        if rect and "x" in rect and "y" in rect:
            try:
                await page.mouse.move(float(rect["x"]), float(rect["y"]), steps=8)
                await asyncio.sleep(0.15)
            except Exception:
                pass

        pre_clipboard = await page.evaluate("navigator.clipboard.readText().catch(() => '')")
        await page.evaluate("navigator.clipboard.writeText('').catch(() => {})")

        click_result = await page.evaluate(_CLICK_LATEST_COPY_BUTTON_JS, previous_turn_signature)

        if isinstance(click_result, dict) and click_result.get("clicked"):
            await asyncio.sleep(0.3)
            content = await page.evaluate("navigator.clipboard.readText().catch(() => '')")
            if content and content.strip() and content.strip() != str(pre_clipboard).strip():
                log.info(
                    "Extracted via copy button (latest-turn): "
                    f"{len(content)} chars, turn={click_result.get('signature')}"
                )
                return content.strip()
            log.debug("Clipboard unchanged/empty after latest-turn copy click")
        else:
            reason = click_result.get("reason") if isinstance(click_result, dict) else "unknown"
            log.debug(f"Latest-turn copy click not used: {reason}")

    except Exception as e:
        log.warning(f"Copy button extraction failed: {e}")

    log.info("Falling back to latest-turn DOM extraction...")
    return await _extract_via_dom(page, previous_turn_signature)


async def _extract_via_dom(
    page: Page,
    previous_turn_signature: str | None = None,
) -> str:
    """Fallback extraction: text from latest assistant turn only."""
    snapshot = await _latest_assistant_turn_snapshot(page)
    signature = snapshot.get("signature")
    if previous_turn_signature and signature == previous_turn_signature:
        log.error("Could not extract any latest assistant response")
        return ""

    text = snapshot.get("text") if isinstance(snapshot.get("text"), str) else ""
    if text and text.strip():
        cleaned = normalize_assistant_text(text)
        if is_incomplete_response_text(cleaned):
            log.debug("Latest-turn DOM text looks incomplete/transient; waiting for a fuller reply")
            return ""
        log.debug(f"Extracted via DOM (latest-turn): {len(cleaned)} chars")
        return cleaned

    log.error("Could not extract any latest assistant response")
    return ""


async def extract_latest_assistant_turn_images(
    page: Page,
    previous_turn_signature: str | None = None,
) -> list[dict[str, str]]:
    """Return generated image metadata from the newest assistant image turn."""
    try:
        result = await page.evaluate(_LATEST_IMAGE_EXTRACTION_JS, previous_turn_signature)
    except Exception as e:
        log.debug(f"Latest image extraction failed: {e}")
        return []

    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


async def capture_response_diagnostics(
    page: Page,
    label: str,
    previous_turn_signature: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """
    Capture screenshot + DOM state to logs/diagnostics and return JSON path.

    Used when send/complete/extract logic fails so selector drift can be fixed
    from the artifact instead of from timeout logs alone.
    """
    Config.ensure_dirs()
    diagnostics_dir = Config.LOG_DIR / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    safe_label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_") or "diagnostic"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = diagnostics_dir / f"{stamp}_{safe_label}"
    screenshot_path = Path(f"{base}.png")
    json_path = Path(f"{base}.json")

    data: dict[str, Any] = {
        "label": label,
        "previous_turn_signature": previous_turn_signature,
        "extra": extra or {},
        "snapshot": await _conversation_snapshot(page),
        "page_url": getattr(page, "url", ""),
    }

    try:
        html_sample = await page.evaluate(
            """
            () => {
                const main = document.querySelector('main') || document.body;
                return {
                    mainText: ((main && (main.innerText || main.textContent)) || '').slice(0, 10000),
                    mainHtml: ((main && main.outerHTML) || '').slice(0, 30000),
                };
            }
            """
        )
        data["html_sample"] = html_sample
    except Exception as e:
        data["html_sample_error"] = str(e)

    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
        data["screenshot_path"] = str(screenshot_path)
    except Exception as e:
        data["screenshot_error"] = str(e)

    try:
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        log.warning(f"Response diagnostic captured: {json_path}")
        return str(json_path)
    except Exception as e:
        log.warning(f"Could not write response diagnostic: {e}")
        return ""


# Keep old name as alias for backward compat.
extract_last_response = extract_last_response_via_copy
