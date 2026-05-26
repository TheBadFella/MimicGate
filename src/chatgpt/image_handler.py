"""
Image handler: detects, extracts, and downloads generated images.

The detector owns the latest-turn DOM scan so text and image responses stay
aligned to the same assistant turn.
"""

from __future__ import annotations

import hashlib
import re
import time

from patchright.async_api import Page

from src.chatgpt.detector import extract_latest_assistant_turn_images
from src.chatgpt.models import ImageInfo
from src.config import Config
from src.log import setup_logging

log = setup_logging("image_handler")


async def detect_images_in_response(
    page: Page,
    previous_turn_signature: str | None = None,
) -> list[dict]:
    """
    Check the newest assistant turn for generated images.

    Returns a list of dicts: [{url, alt, title, turnSignature}, ...].
    """
    result = await extract_latest_assistant_turn_images(page, previous_turn_signature)

    if result:
        log.info(f"Detected {len(result)} generated image(s) in response")
        for i, img in enumerate(result):
            log.debug(
                f"  Image {i + 1}: alt='{img.get('alt', '')[:50]}', "
                f"url={img.get('url', '')[:80]}..."
            )
    else:
        log.debug("No generated images detected in response")

    return result or []


async def download_image(page: Page, url: str, filename_hint: str = "") -> str:
    """
    Download an image from a URL using the browser's fetch API.

    Uses the browser context so cookies/auth are preserved for ChatGPT-hosted
    image URLs. Returns the local file path, or an empty string on failure.
    """
    Config.ensure_dirs()

    if filename_hint:
        safe_name = re.sub(r"[^\w\s-]", "", filename_hint)[:60].strip()
        safe_name = re.sub(r"\s+", "_", safe_name)
    else:
        safe_name = hashlib.md5(url.encode()).hexdigest()[:12]
    safe_name = safe_name or "chatgpt_image"

    ts = int(time.time())
    local_path = Config.IMAGES_DIR / f"{safe_name}_{ts}.png"

    log.info(f"Downloading image to {local_path}...")

    try:
        image_data = await page.evaluate(
            """
            async (url) => {
                try {
                    const response = await fetch(url);
                    if (!response.ok) return null;
                    const blob = await response.blob();
                    const reader = new FileReader();
                    return new Promise((resolve) => {
                        reader.onloadend = () => resolve(reader.result);
                        reader.readAsDataURL(blob);
                    });
                } catch (e) {
                    return null;
                }
            }
            """,
            url,
        )

        if image_data and str(image_data).startswith("data:"):
            import base64

            header, b64data = str(image_data).split(",", 1)
            if "png" in header:
                ext = ".png"
            elif "jpeg" in header or "jpg" in header:
                ext = ".jpg"
            elif "webp" in header:
                ext = ".webp"
            else:
                ext = ".png"

            local_path = Config.IMAGES_DIR / f"{safe_name}_{ts}{ext}"
            raw_bytes = base64.b64decode(b64data)
            local_path.write_bytes(raw_bytes)

            size_kb = len(raw_bytes) / 1024
            log.info(f"Image saved: {local_path} ({size_kb:.1f} KB)")
            return str(local_path)

        log.warning("Failed to fetch image data via browser")

    except Exception as e:
        log.error(f"Image download failed: {e}", exc_info=True)

    try:
        import urllib.request

        urllib.request.urlretrieve(url, str(local_path))
        log.info(f"Image saved via urllib: {local_path}")
        return str(local_path)
    except Exception as e:
        log.error(f"Fallback image download failed: {e}")

    return ""


async def extract_images_from_response(
    page: Page,
    previous_turn_signature: str | None = None,
) -> list[ImageInfo]:
    """Detect images in the newest assistant response, download them, and return metadata."""
    raw_images = await detect_images_in_response(page, previous_turn_signature)

    if not raw_images:
        return []

    image_infos: list[ImageInfo] = []
    for img_data in raw_images:
        url = str(img_data.get("url", ""))
        alt = str(img_data.get("alt", ""))
        title = str(img_data.get("title", ""))
        hint = alt or title or "chatgpt_image"
        local_path = await download_image(page, url, filename_hint=hint)

        image_infos.append(
            ImageInfo(
                url=url,
                alt=alt,
                local_path=local_path,
                prompt_title=title,
            )
        )

    log.info(f"Processed {len(image_infos)} image(s)")
    return image_infos
