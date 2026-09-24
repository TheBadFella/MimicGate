"""
Live multi-tab browser monitor and dashboard routes for MimicGate.

Provides endpoints to inspect, snapshot, reset, and close background browser tabs,
access gateway telemetry and recent request activity, plus a self-contained square
dark dashboard inspired by UnpackUI.
"""

from __future__ import annotations

import time
from typing import Any
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from src.api.browser_gate import (
    capture_browser_screenshot,
    close_browser_tab,
    get_concurrency_stats,
    get_tab_pool,
    list_browser_tabs,
    reset_browser_tab,
)
from src.api.telemetry import telemetry
from src.config import Config
from src.log import setup_logging

log = setup_logging("monitor_routes")

router = APIRouter(tags=["Monitor"])

_SERVER_START_TIME = time.monotonic()


@router.get("/v1/tabs")
async def get_tabs() -> dict[str, Any]:
    """List all open browser tabs, concurrency state, and diagnostics."""
    pool = get_tab_pool()
    tabs = await list_browser_tabs()
    uptime_sec = round(time.monotonic() - _SERVER_START_TIME, 1)
    concurrency = get_concurrency_stats()
    telemetry_summary = telemetry.get_summary()

    diagnostics = {
        "provider": Config.PROVIDER,
        "provider_url": Config.provider_url(),
        "channel": Config.BROWSER_CHANNEL,
        "headless": Config.HEADLESS,
        "stealth": True,
        "display": f"{getattr(Config, 'VIEWPORT_WIDTH', 1366)}x{getattr(Config, 'VIEWPORT_HEIGHT', 768)}",
        "novnc_url": "http://localhost:5800",
    }

    return {
        "provider": Config.PROVIDER,
        "provider_url": Config.provider_url(),
        "max_concurrent_requests": Config.MAX_CONCURRENT_REQUESTS,
        "max_active_tabs": Config.MAX_ACTIVE_TABS,
        "tab_pool_active": pool is not None,
        "uptime_seconds": uptime_sec,
        "tab_count": len(tabs),
        "concurrency": concurrency,
        "telemetry": telemetry_summary,
        "diagnostics": diagnostics,
        "tabs": tabs,
    }


@router.get("/v1/tabs/{index}/screenshot")
async def get_tab_screenshot(index: int) -> Response:
    """Return a JPEG screenshot for a specific browser tab index."""
    try:
        jpeg_bytes = await capture_browser_screenshot(index)
        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.warning("Tab %s screenshot failed: %s", index, exc)
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <rect width="640" height="360" fill="#111111"/>
  <rect width="640" height="360" fill="none" stroke="#2d2d2d" stroke-width="2"/>
  <text x="50%" y="45%" text-anchor="middle" fill="#777777" font-family="monospace" font-size="14" font-weight="bold">PREVIEW UNAVAILABLE</text>
  <text x="50%" y="58%" text-anchor="middle" fill="#555555" font-family="monospace" font-size="11">Tab {index}: {str(exc)[:45]}</text>
</svg>"""
        return Response(
            content=svg.encode("utf-8"),
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )


@router.post("/v1/tabs/{index}/close")
async def close_tab(index: int) -> dict[str, Any]:
    """Close an idle worker tab by index (Tab 0 control page cannot be closed)."""
    try:
        return await close_browser_tab(index)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/v1/tabs/{index}/reset")
async def reset_tab(index: int) -> dict[str, Any]:
    """Reset a worker or control tab back to clean new chat / provider home."""
    try:
        return await reset_browser_tab(index)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/v1/gateway/activity")
async def get_gateway_activity() -> dict[str, Any]:
    """Return rolling gateway request activity and latency metrics."""
    return {
        "summary": telemetry.get_summary(),
        "concurrency": get_concurrency_stats(),
        "requests": telemetry.get_recent_requests(30),
    }


@router.get("/preview", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
@router.get("/v1/preview", response_class=HTMLResponse)
async def preview_dashboard() -> HTMLResponse:
    """
    Serve the Live Multi-Tab Preview Dashboard.
    Follows UnpackUI square dark aesthetic with live tabs, telemetry, playground, and activity feed.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MimicGate — Live Monitor</title>
  <link rel="icon" type="image/png" href="/assets/favicon-32x32.png" />
  <style>
    :root {
      --dash-bg: #090909;
      --dash-panel: #111111;
      --dash-card: #151515;
      --dash-border: #242424;
      --dash-border-strong: #383838;
      --dash-text: #eaeaea;
      --dash-heading: #ffffff;
      --dash-muted: #888888;
      --dash-dim: #505050;
      --dash-accent: #80e8ba;
      --dash-good: #16c784;
      --dash-warn: #f6c453;
      --dash-bad: #ff4d5e;
      --dash-cyan: #38bdf8;
      --dash-purple: #c084fc;
      --font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      border-radius: 0 !important;
    }

    body {
      background: var(--dash-bg);
      color: var(--dash-text);
      font-family: var(--font-sans);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background-image: 
        linear-gradient(to right, rgba(255, 255, 255, 0.015) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255, 255, 255, 0.015) 1px, transparent 1px);
      background-size: 24px 24px;
    }

    header {
      background: #0f0f0f;
      border-bottom: 1px solid var(--dash-border);
      padding: 10px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo-img {
      width: 28px;
      height: 28px;
      display: block;
      border: 1px solid var(--dash-border);
      background: #181818;
      object-fit: cover;
    }
    .brand-title {
      font-size: 1.12rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--dash-heading);
      line-height: 1;
    }
    .brand-title span { color: var(--dash-accent); }

    .stamp-chip {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 4px 10px;
      border: 1px solid var(--dash-border);
      background: #141414;
      color: var(--dash-text);
      font-size: 0.72rem;
      font-family: var(--font-mono);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .stamp-chip::before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50% !important;
      background: var(--dash-good);
      box-shadow: 0 0 8px rgba(22, 199, 132, 0.8);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { opacity: 0.7; }
      50% { opacity: 1; transform: scale(1.1); }
      100% { opacity: 0.7; }
    }

    .brand-gh-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
      border: 1px solid var(--dash-border);
      background: #141414;
      color: var(--dash-muted);
      text-decoration: none;
      transition: color 0.15s, border-color 0.15s, background 0.15s;
    }
    .brand-gh-link:hover {
      color: #ffffff;
      border-color: var(--dash-border-strong);
      background: #202020;
    }

    .nav-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .btn-square {
      background: #171717;
      border: 1px solid var(--dash-border);
      color: var(--dash-text);
      padding: 6px 14px;
      font-size: 0.78rem;
      font-family: var(--font-mono);
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      transition: background 0.1s, border-color 0.1s;
    }
    .btn-square:hover {
      background: #222222;
      border-color: var(--dash-border-strong);
      color: #ffffff;
    }
    .btn-square-active {
      background: #252525;
      border-color: var(--dash-accent);
      color: var(--dash-accent);
    }
    .btn-square-danger {
      border-color: rgba(255, 77, 94, 0.4);
      color: var(--dash-bad);
      background: #181213;
    }
    .btn-square-danger:hover {
      background: rgba(255, 77, 94, 0.18);
      border-color: var(--dash-bad);
      color: #ffffff;
    }

    main {
      max-width: 1440px;
      width: 100%;
      margin: 0 auto;
      padding: 20px 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    /* Diagnostics Banner */
    .diag-banner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #121212;
      border: 1px solid var(--dash-border);
      padding: 10px 16px;
      font-size: 0.78rem;
    }
    .diag-left {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }
    .diag-item {
      display: flex;
      align-items: center;
      gap: 6px;
      font-family: var(--font-mono);
    }
    .diag-label { color: var(--dash-muted); }
    .diag-val { color: var(--dash-heading); font-weight: 600; }
    .diag-status-ok {
      color: var(--dash-good);
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .diag-status-warn {
      color: var(--dash-warn);
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }

    /* Top Stat Row */
    .stat-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
    }
    .stat-card {
      background: var(--dash-panel);
      border: 1px solid var(--dash-border);
      border-top: 3px solid var(--dash-border);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-height: 80px;
      justify-content: center;
    }
    .stat-card.accent-warn { border-top-color: var(--dash-warn); }
    .stat-card.accent-cyan { border-top-color: var(--dash-cyan); }
    .stat-card.accent-bad { border-top-color: var(--dash-bad); }
    .stat-card.accent-good { border-top-color: var(--dash-good); }
    .stat-card.accent-mint { border-top-color: var(--dash-accent); }
    .stat-card.accent-purple { border-top-color: var(--dash-purple); }

    .stat-label {
      font-size: 0.7rem;
      text-transform: uppercase;
      font-family: var(--font-mono);
      font-weight: 600;
      letter-spacing: 0.08em;
      color: var(--dash-muted);
    }
    .stat-value {
      font-size: 1.65rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: var(--dash-heading);
      line-height: 1.1;
    }
    .stat-sub {
      font-size: 0.72rem;
      font-family: var(--font-mono);
      color: var(--dash-muted);
    }

    /* Submetrics Strip */
    .submetric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 1px;
      background: var(--dash-border);
      border: 1px solid var(--dash-border);
    }
    .submetric-item {
      background: var(--dash-panel);
      padding: 9px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.76rem;
    }
    .submetric-item span:first-child { color: var(--dash-muted); }
    .submetric-item span:last-child {
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--dash-heading);
    }

    /* Panels */
    .dashboard-panel {
      background: var(--dash-panel);
      border: 1px solid var(--dash-border);
      display: flex;
      flex-direction: column;
    }
    .panel-header {
      padding: 14px 18px;
      border-bottom: 1px solid var(--dash-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #131313;
    }
    .panel-title-wrap h2 {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--dash-heading);
      letter-spacing: -0.01em;
    }
    .panel-title-wrap p {
      font-size: 0.74rem;
      color: var(--dash-muted);
      margin-top: 2px;
    }

    /* Tabs Grid (Cards View) */
    .tabs-grid {
      padding: 18px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 18px;
    }

    .tab-card {
      background: var(--dash-card);
      border: 1px solid var(--dash-border);
      display: flex;
      flex-direction: column;
      transition: border-color 0.15s;
    }
    .tab-card:hover {
      border-color: var(--dash-border-strong);
    }
    .tab-header {
      padding: 10px 14px;
      background: #191919;
      border-bottom: 1px solid var(--dash-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .tab-title-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tab-badge {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--dash-cyan);
    }
    .tab-status-pill {
      font-family: var(--font-mono);
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 2px 7px;
      border: 1px solid transparent;
      letter-spacing: 0.05em;
    }
    .status-control {
      background: rgba(192, 132, 252, 0.15);
      border-color: var(--dash-purple);
      color: var(--dash-purple);
    }
    .status-idle {
      background: rgba(22, 199, 132, 0.15);
      border-color: var(--dash-good);
      color: var(--dash-good);
    }
    .status-busy, .status-generating, .status-submitting {
      background: rgba(246, 196, 83, 0.15);
      border-color: var(--dash-warn);
      color: var(--dash-warn);
    }

    .tab-preview-wrap {
      position: relative;
      width: 100%;
      height: 220px;
      background: #000;
      overflow: hidden;
      border-bottom: 1px solid var(--dash-border);
      cursor: zoom-in;
    }
    .tab-preview-img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      transition: transform 0.2s ease;
    }
    .tab-preview-wrap:hover .tab-preview-img {
      transform: scale(1.02);
    }
    .tab-overlay-actions {
      position: absolute;
      top: 8px;
      right: 8px;
      display: flex;
      gap: 6px;
      opacity: 0.85;
    }

    .tab-meta-box {
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 5px;
      font-size: 0.76rem;
      background: #141414;
    }
    .tab-meta-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .tab-meta-label { color: var(--dash-muted); }
    .tab-meta-value {
      font-family: var(--font-mono);
      color: var(--dash-text);
      max-width: 250px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .tab-footer-actions {
      padding: 8px 14px;
      background: #111111;
      border-top: 1px solid var(--dash-border);
      display: flex;
      justify-content: flex-end;
      gap: 8px;
    }

    /* Compact View Styling */
    .tabs-compact {
      padding: 12px 18px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .compact-tab-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--dash-card);
      border: 1px solid var(--dash-border);
      padding: 8px 12px;
      gap: 12px;
    }
    .compact-left {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .compact-thumb {
      width: 72px;
      height: 44px;
      border: 1px solid var(--dash-border);
      object-fit: cover;
      background: #000;
      cursor: zoom-in;
    }
    .compact-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .compact-title {
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--dash-heading);
      font-family: var(--font-mono);
    }
    .compact-sub {
      font-size: 0.72rem;
      color: var(--dash-muted);
      font-family: var(--font-mono);
    }

    /* Tables */
    .table-wrap {
      width: 100%;
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.78rem;
    }
    th {
      padding: 10px 14px;
      background: #141414;
      color: var(--dash-muted);
      font-weight: 700;
      text-transform: uppercase;
      font-size: 0.68rem;
      letter-spacing: 0.06em;
      border-bottom: 1px solid var(--dash-border);
      font-family: var(--font-mono);
    }
    td {
      padding: 10px 14px;
      border-bottom: 1px solid var(--dash-border);
      color: var(--dash-text);
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .mono { font-family: var(--font-mono); }

    /* Playground Panel */
    .playground-body {
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      background: #131313;
    }
    .playground-row {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    .pg-label {
      font-size: 0.75rem;
      font-family: var(--font-mono);
      color: var(--dash-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .pg-select, .pg-input {
      background: #1a1a1a;
      border: 1px solid var(--dash-border);
      color: var(--dash-heading);
      padding: 8px 12px;
      font-size: 0.8rem;
      font-family: var(--font-mono);
    }
    .pg-textarea {
      width: 100%;
      min-height: 70px;
      background: #181818;
      border: 1px solid var(--dash-border);
      color: var(--dash-heading);
      padding: 10px 12px;
      font-size: 0.82rem;
      font-family: var(--font-mono);
      resize: vertical;
    }
    .pg-textarea:focus, .pg-select:focus, .pg-input:focus {
      outline: none;
      border-color: var(--dash-accent);
    }
    .pg-output-box {
      width: 100%;
      min-height: 90px;
      max-height: 240px;
      overflow-y: auto;
      background: #0b0b0b;
      border: 1px solid var(--dash-border);
      padding: 12px;
      font-family: var(--font-mono);
      font-size: 0.8rem;
      color: #98ff98;
      white-space: pre-wrap;
      line-height: 1.4;
    }
    .pg-meta-status {
      font-size: 0.72rem;
      font-family: var(--font-mono);
      color: var(--dash-muted);
    }

    /* Modal */
    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.9);
      z-index: 200;
      align-items: center;
      justify-content: center;
      padding: 24px;
      cursor: zoom-out;
    }
    .modal.active { display: flex; }
    .modal-content {
      max-width: 92vw;
      max-height: 92vh;
      border: 1px solid var(--dash-border-strong);
      box-shadow: 0 0 40px rgba(0, 0, 0, 0.9);
      background: #000;
    }
    .modal-content img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <img src="/assets/mimicgate_icon.png" alt="MimicGate" class="brand-logo-img" />
      <div class="brand-title">Mimic<span>Gate</span></div>
      <div class="stamp-chip">Live</div>
      <a href="https://github.com/TheBadFella/MimicGate" target="_blank" rel="noopener noreferrer" class="brand-gh-link" title="MimicGate on GitHub" aria-label="GitHub Repository">
        <svg height="15" width="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9 1.01 1.34.46.72 1.54.48 1.9.36.01.67.01 1.25.01 1.41 0 .21-.15.46-.55.38A8.013 8.013 0 0 1 0 8c0-4.42 3.58-8 8-8z"></path>
        </svg>
      </a>
    </div>
    <div class="nav-actions">
      <button class="btn-square" id="btn-toggle-density" onclick="toggleDensity()">Compact View</button>
      <button class="btn-square" id="btn-toggle-refresh" onclick="toggleAutoRefresh()">Pause</button>
      <button class="btn-square" onclick="fetchData()">Refresh</button>
      <a href="http://localhost:5800" target="_blank" class="btn-square" title="Open interactive noVNC desktop session">noVNC (:5800)</a>
      <a href="/docs" target="_blank" class="btn-square">API Docs</a>
    </div>
  </header>

  <main>
    <!-- Diagnostics & Stealth Banner (Item 2) -->
    <div class="diag-banner">
      <div class="diag-left">
        <div class="diag-item">
          <span class="diag-label">Session Status:</span>
          <span class="diag-val diag-status-ok" id="diag-auth">ONLINE</span>
        </div>
        <div class="diag-item">
          <span class="diag-label">Stealth Engine:</span>
          <span class="diag-val" id="diag-stealth">ACTIVE</span>
        </div>
        <div class="diag-item">
          <span class="diag-label">Resolution:</span>
          <span class="diag-val" id="diag-display">1366x768</span>
        </div>
        <div class="diag-item">
          <span class="diag-label">Channel:</span>
          <span class="diag-val" id="diag-channel">chrome</span>
        </div>
      </div>
      <div>
        <a href="http://localhost:5800" target="_blank" class="btn-square" style="padding: 3px 10px; font-size: 0.72rem;">VNC Remote Console</a>
      </div>
    </div>

    <!-- Top Stat Cards (Item 1 Telemetry) -->
    <div class="stat-row">
      <div class="stat-card accent-warn">
        <div class="stat-label">Active Tabs</div>
        <div class="stat-value" id="val-active-tabs">0</div>
        <div class="stat-sub" id="sub-active-tabs">Cap: 4</div>
      </div>
      <div class="stat-card accent-cyan">
        <div class="stat-label">In-Flight / Concurrency</div>
        <div class="stat-value" id="val-concurrency">0 / 3</div>
        <div class="stat-sub" id="sub-concurrency">Queue: 0</div>
      </div>
      <div class="stat-card accent-good">
        <div class="stat-label">Avg Latency</div>
        <div class="stat-value" id="val-latency">0.0s</div>
        <div class="stat-sub" id="sub-requests">0 total reqs</div>
      </div>
      <div class="stat-card accent-mint">
        <div class="stat-label">Success Rate</div>
        <div class="stat-value" id="val-success-rate">100%</div>
        <div class="stat-sub" id="sub-errors">0 errors</div>
      </div>
      <div class="stat-card accent-purple">
        <div class="stat-label">Provider</div>
        <div class="stat-value" id="val-provider" style="font-size: 1.3rem;">—</div>
        <div class="stat-sub" id="sub-provider-url">chatgpt.com</div>
      </div>
      <div class="stat-card accent-bad">
        <div class="stat-label">Uptime</div>
        <div class="stat-value" id="val-uptime" style="font-size: 1.3rem;">0s</div>
        <div class="stat-sub">Tab Pool Active</div>
      </div>
    </div>

    <!-- Secondary Meta Strip -->
    <div class="submetric-grid">
      <div class="submetric-item">
        <span>Provider Base URL</span>
        <span id="pill-url">—</span>
      </div>
      <div class="submetric-item">
        <span>Tab Pool Strategy</span>
        <span>LRU Eviction</span>
      </div>
      <div class="submetric-item">
        <span>Auto-Refresh Interval</span>
        <span id="pill-refresh">2.0s</span>
      </div>
      <div class="submetric-item">
        <span>Control Tab Mode</span>
        <span>Protected (#0)</span>
      </div>
    </div>

    <!-- Active Browser Tabs Section (Item 5 & Item 6) -->
    <div class="dashboard-panel">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h2 id="tabs-section-heading">Active Browser Tabs (0)</h2>
          <p>Real-time visual monitoring, screenshot zoom, reset, and tab lifecycle controls.</p>
        </div>
        <div class="nav-actions">
          <button class="btn-square" onclick="fetchData()">Reload Screenshots</button>
        </div>
      </div>

      <div id="tabs-container" class="tabs-grid">
        <!-- Rendered dynamically -->
      </div>
    </div>

    <!-- Interactive Quick Prompt Playground (Item 3) -->
    <div class="dashboard-panel">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h2>Quick Prompt Playground</h2>
          <p>Test gateway streaming completions directly against the active browser pool.</p>
        </div>
        <button class="btn-square" id="btn-toggle-pg" onclick="togglePlayground()">Collapse</button>
      </div>
      <div class="playground-body" id="pg-body">
        <div class="playground-row">
          <span class="pg-label">Model:</span>
          <select id="pg-model-select" class="pg-select">
            <option value="chatgpt-browser">chatgpt-browser (default)</option>
            <option value="gpt-5.6-sol">gpt-5.6-sol</option>
            <option value="gpt-5.5">gpt-5.5</option>
            <option value="claude-3-7-sonnet">claude-3-7-sonnet</option>
            <option value="gemini-3.8-flash">gemini-3.8-flash</option>
          </select>
          <span class="pg-label" style="margin-left: 12px;">Session Key:</span>
          <input type="text" id="pg-session-input" class="pg-input" placeholder="ephemeral (auto-tab)" style="width: 180px;" />
        </div>
        <textarea id="pg-prompt-input" class="pg-textarea" placeholder="Type a prompt to test the live browser tab (e.g. 'Explain quantum entanglement in 2 sentences')..."></textarea>
        <div class="playground-row" style="justify-content: space-between;">
          <div style="display: flex; gap: 8px; align-items: center;">
            <button class="btn-square btn-square-active" id="btn-pg-send" onclick="sendPlaygroundPrompt()">Send Prompt</button>
            <button class="btn-square btn-square-danger" id="btn-pg-abort" onclick="abortPlaygroundPrompt()" disabled>Stop</button>
            <button class="btn-square" onclick="clearPlayground()">Clear</button>
          </div>
          <span class="pg-meta-status" id="pg-meta-timer">Ready</span>
        </div>
        <div class="pg-output-box" id="pg-output">Response stream will appear here...</div>
      </div>
    </div>

    <!-- Gateway Request Activity Feed (Item 4) -->
    <div class="dashboard-panel">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h2>Gateway Request Activity (Live Feed)</h2>
          <p>Rolling telemetry log of incoming API calls, model routing, latency, and status codes.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width: 28px;"></th>
              <th>Time</th>
              <th>Method</th>
              <th>Endpoint</th>
              <th>Model</th>
              <th>Status</th>
              <th>Latency</th>
              <th>Client IP</th>
            </tr>
          </thead>
          <tbody id="activity-table-body">
            <tr><td colspan="8" style="text-align: center; color: var(--dash-muted); padding: 18px; font-family: var(--font-mono);">No request activity recorded yet. Call /v1/chat/completions or use the Playground.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Session Registry Table -->
    <div class="dashboard-panel">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h2>Session Registry</h2>
          <p>Active persistent session keys mapped to underlying browser tabs and thread URLs.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Tab Index</th>
              <th>Session Identity</th>
              <th>State</th>
              <th>Last Active</th>
              <th>Current Page URL</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="table-body">
            <tr><td colspan="6" style="text-align: center; color: var(--dash-muted); padding: 24px; font-family: var(--font-mono);">Loading session table...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- High-Res Zoom Modal -->
  <div class="modal" id="modal" onclick="closeModal()">
    <div class="modal-content" onclick="event.stopPropagation()">
      <img id="modal-img" src="" alt="Enlarged Tab Snapshot" />
    </div>
  </div>

  <script>
    let isAutoRefresh = true;
    let refreshInterval = null;
    let isCompact = localStorage.getItem("mimicgate_density") === "compact";
    let playgroundAbortController = null;

    function formatUptime(seconds) {
      if (seconds < 60) return `${Math.floor(seconds)}s`;
      if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
      return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
    }

    function toggleDensity() {
      isCompact = !isCompact;
      localStorage.setItem("mimicgate_density", isCompact ? "compact" : "cards");
      document.getElementById("btn-toggle-density").textContent = isCompact ? "Cards View" : "Compact View";
      fetchData();
    }

    function togglePlayground() {
      const body = document.getElementById("pg-body");
      const btn = document.getElementById("btn-toggle-pg");
      if (body.style.display === "none") {
        body.style.display = "flex";
        btn.textContent = "Collapse";
      } else {
        body.style.display = "none";
        btn.textContent = "Expand";
      }
    }

    function openModal(src) {
      const modal = document.getElementById("modal");
      const modalImg = document.getElementById("modal-img");
      modalImg.src = src;
      modal.classList.add("active");
    }

    function closeModal() {
      document.getElementById("modal").classList.remove("active");
    }

    async function closeTab(index) {
      if (!confirm(`Are you sure you want to close worker Tab #${index}?`)) return;
      try {
        const res = await fetch(`/v1/tabs/${index}/close`, { method: "POST" });
        if (!res.ok) {
          const err = await res.json();
          alert(`Error closing tab: ${err.detail || 'Failed'}`);
        }
        await fetchData();
      } catch (err) {
        alert(`Failed to request tab close: ${err}`);
      }
    }

    async function resetTab(index) {
      if (!confirm(`Reset Tab #${index} back to a clean new chat?`)) return;
      try {
        const res = await fetch(`/v1/tabs/${index}/reset`, { method: "POST" });
        if (!res.ok) {
          const err = await res.json();
          alert(`Error resetting tab: ${err.detail || 'Failed'}`);
        }
        await fetchData();
      } catch (err) {
        alert(`Failed to reset tab: ${err}`);
      }
    }

    function reloadSingleTab(index) {
      const img = document.getElementById(`tab-img-${index}`);
      if (img) {
        img.src = `/v1/tabs/${index}/screenshot?t=${Date.now()}`;
      }
    }

    async function sendPlaygroundPrompt() {
      const prompt = document.getElementById("pg-prompt-input").value.trim();
      if (!prompt) return;
      const model = document.getElementById("pg-model-select").value;
      const sessionKey = document.getElementById("pg-session-input").value.trim();
      const output = document.getElementById("pg-output");
      const meta = document.getElementById("pg-meta-timer");
      const btnSend = document.getElementById("btn-pg-send");
      const btnAbort = document.getElementById("btn-pg-abort");

      output.textContent = "";
      btnSend.disabled = true;
      btnAbort.disabled = false;
      const startTime = performance.now();
      meta.textContent = "Streaming...";

      playgroundAbortController = new AbortController();

      try {
        const headers = { "Content-Type": "application/json" };
        if (sessionKey) headers["x-session-key"] = sessionKey;

        const resp = await fetch("/v1/chat/completions", {
          method: "POST",
          headers,
          signal: playgroundAbortController.signal,
          body: JSON.stringify({
            model: model,
            messages: [{ role: "user", content: prompt }],
            stream: true
          })
        });

        if (!resp.ok) {
          const err = await resp.text();
          output.textContent = `HTTP ${resp.status} Error:\n${err}`;
          meta.textContent = `Failed (${((performance.now() - startTime) / 1000).toFixed(1)}s)`;
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || !trimmed.startsWith("data:")) continue;
            const dataStr = trimmed.replace(/^data:\\s*/, "");
            if (dataStr === "[DONE]") break;
            try {
              const json = JSON.parse(dataStr);
              const delta = json.choices?.[0]?.delta?.content || "";
              output.textContent += delta;
              output.scrollTop = output.scrollHeight;
            } catch (_) {}
          }
        }
        const totalSec = ((performance.now() - startTime) / 1000).toFixed(1);
        meta.textContent = `Completed in ${totalSec}s`;
      } catch (err) {
        if (err.name === "AbortError") {
          meta.textContent = "Aborted";
          output.textContent += "\\n[Stream cancelled by user]";
        } else {
          output.textContent += `\\n[Stream error: ${err}]`;
          meta.textContent = "Error";
        }
      } finally {
        btnSend.disabled = false;
        btnAbort.disabled = true;
        fetchData();
      }
    }

    function abortPlaygroundPrompt() {
      if (playgroundAbortController) {
        playgroundAbortController.abort();
      }
    }

    function clearPlayground() {
      document.getElementById("pg-output").textContent = "Response stream will appear here...";
      document.getElementById("pg-prompt-input").value = "";
      document.getElementById("pg-meta-timer").textContent = "Ready";
    }

    async function loadModels() {
      try {
        const res = await fetch("/v1/models");
        if (res.ok) {
          const data = await res.json();
          const select = document.getElementById("pg-model-select");
          if (data.data && Array.isArray(data.data) && data.data.length) {
            select.innerHTML = data.data.map(m => `<option value="${m.id}">${m.id}</option>`).join("");
          }
        }
      } catch (_) {}
    }

    function renderDashboard(data) {
      const conc = data.concurrency || {};
      const tele = data.telemetry || {};
      const diag = data.diagnostics || {};

      document.getElementById("val-active-tabs").textContent = data.tab_count || 0;
      document.getElementById("sub-active-tabs").textContent = `Cap: ${data.max_active_tabs || 4}`;

      const inFlight = conc.in_flight !== undefined ? conc.in_flight : 0;
      const maxConc = conc.max_concurrency || data.max_concurrent_requests || 3;
      document.getElementById("val-concurrency").textContent = `${inFlight} / ${maxConc}`;
      document.getElementById("sub-concurrency").textContent = `Queue: ${conc.waiting || 0} waiting`;

      const avgLatencySec = ((tele.avg_latency_ms || 0) / 1000).toFixed(1);
      document.getElementById("val-latency").textContent = `${avgLatencySec}s`;
      document.getElementById("sub-requests").textContent = `${tele.total_requests || 0} total reqs`;

      document.getElementById("val-success-rate").textContent = `${tele.success_rate_percent || 100}%`;
      document.getElementById("sub-errors").textContent = `${tele.failed_requests || 0} errors`;

      document.getElementById("val-provider").textContent = (data.provider || "chatgpt").toUpperCase();
      document.getElementById("sub-provider-url").textContent = (data.provider_url || "chatgpt.com").replace(/^https?:\\/\\//, '');
      document.getElementById("val-uptime").textContent = formatUptime(data.uptime_seconds || 0);
      document.getElementById("pill-url").textContent = data.provider_url || "https://chatgpt.com";

      if (diag.display) document.getElementById("diag-display").textContent = diag.display;
      if (diag.channel) document.getElementById("diag-channel").textContent = diag.channel;
      if (diag.stealth !== undefined) document.getElementById("diag-stealth").textContent = diag.stealth ? "ACTIVE" : "DISABLED";

      renderTabs(data.tabs || []);
      renderTable(data.tabs || []);
    }

    function renderTabs(tabs) {
      document.getElementById("tabs-section-heading").textContent = `Active Browser Tabs (${tabs.length})`;
      const container = document.getElementById("tabs-container");

      if (isCompact) {
        container.className = "tabs-compact";
      } else {
        container.className = "tabs-grid";
      }

      if (!tabs.length) {
        container.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--dash-muted); font-family: var(--font-mono); font-size: 0.82rem;">
            No browser tabs currently active. A worker tab will launch when the gateway receives a request.
          </div>
        `;
        return;
      }

      if (isCompact) {
        container.innerHTML = tabs.map(tab => {
          const timestamp = Date.now();
          const screenshotSrc = `/v1/tabs/${tab.index}/screenshot?t=${timestamp}`;
          const statusClass = tab.is_control ? 'status-control' : (tab.is_busy ? 'status-busy' : 'status-idle');
          const statusLabel = tab.state ? tab.state.toUpperCase() : (tab.is_control ? 'CONTROL' : tab.is_busy ? 'BUSY' : 'IDLE');

          const closeBtn = tab.is_control
            ? `<span style="font-size: 0.7rem; color: var(--dash-dim); font-family: var(--font-mono);">PROTECTED</span>`
            : `<button class="btn-square btn-square-danger" style="padding: 3px 8px; font-size: 0.7rem;" onclick="closeTab(${tab.index})">Close</button>`;

          return `
            <div class="compact-tab-row">
              <div class="compact-left">
                <img src="${screenshotSrc}" class="compact-thumb" onclick="openModal('${screenshotSrc}')" title="Click to zoom" />
                <div class="compact-info">
                  <div class="compact-title">#${tab.index} &bull; ${tab.title || 'Tab'}</div>
                  <div class="compact-sub">${tab.session_key || 'ephemeral'} &bull; ${tab.url || 'about:blank'}</div>
                </div>
              </div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="tab-status-pill ${statusClass}">${statusLabel}</span>
                <button class="btn-square" style="padding: 3px 8px; font-size: 0.7rem;" onclick="resetTab(${tab.index})">Reset</button>
                <button class="btn-square" style="padding: 3px 8px; font-size: 0.7rem;" onclick="reloadSingleTab(${tab.index})">Snapshot</button>
                ${closeBtn}
              </div>
            </div>
          `;
        }).join("");
        return;
      }

      container.innerHTML = tabs.map(tab => {
        const timestamp = Date.now();
        const screenshotSrc = `/v1/tabs/${tab.index}/screenshot?t=${timestamp}`;
        const statusClass = tab.is_control ? 'status-control' : (tab.is_busy ? 'status-busy' : 'status-idle');
        const statusLabel = tab.state ? tab.state.toUpperCase() : (tab.is_control ? 'CONTROL' : tab.is_busy ? 'BUSY' : 'IDLE');

        const closeBtn = tab.is_control
          ? `<span style="font-size: 0.7rem; color: var(--dash-dim); font-family: var(--font-mono); text-transform: uppercase;">Protected</span>`
          : `<button class="btn-square btn-square-danger" style="padding: 2px 8px; font-size: 0.7rem;" onclick="closeTab(${tab.index})">Close</button>`;

        return `
          <div class="tab-card">
            <div class="tab-header">
              <div class="tab-title-group">
                <span class="tab-badge">#${tab.index}</span>
                <span class="tab-status-pill ${statusClass}">${statusLabel}</span>
              </div>
              <div>${closeBtn}</div>
            </div>
            <div class="tab-preview-wrap" onclick="openModal('${screenshotSrc}')" title="Click to enlarge screenshot">
              <img id="tab-img-${tab.index}" src="${screenshotSrc}" alt="Tab ${tab.index} Preview" class="tab-preview-img" onerror="this.src='/v1/tabs/${tab.index}/screenshot?t=' + Date.now()" />
              <div class="tab-overlay-actions">
                <button class="btn-square" style="padding: 2px 6px; font-size: 0.68rem; background: rgba(0,0,0,0.7);" onclick="event.stopPropagation(); reloadSingleTab(${tab.index})">Snapshot</button>
              </div>
            </div>
            <div class="tab-meta-box">
              <div class="tab-meta-row">
                <span class="tab-meta-label">Title</span>
                <span class="tab-meta-value" title="${tab.title}">${tab.title || '—'}</span>
              </div>
              <div class="tab-meta-row">
                <span class="tab-meta-label">Session</span>
                <span class="tab-meta-value">${tab.session_key || 'ephemeral'}</span>
              </div>
              <div class="tab-meta-row">
                <span class="tab-meta-label">URL</span>
                <span class="tab-meta-value" title="${tab.url}">${tab.url || '—'}</span>
              </div>
              <div class="tab-meta-row">
                <span class="tab-meta-label">Last Active</span>
                <span class="tab-meta-value">${tab.last_active_seconds_ago !== null ? tab.last_active_seconds_ago + 's ago' : 'active'}</span>
              </div>
            </div>
            <div class="tab-footer-actions">
              <button class="btn-square" style="padding: 2px 8px; font-size: 0.7rem;" onclick="resetTab(${tab.index})">Reset Chat</button>
              <button class="btn-square" style="padding: 2px 8px; font-size: 0.7rem;" onclick="reloadSingleTab(${tab.index})">Force Snapshot</button>
            </div>
          </div>
        `;
      }).join("");
    }

    function renderTable(tabs) {
      const tbody = document.getElementById("table-body");
      if (!tabs.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--dash-muted); padding: 24px; font-family: var(--font-mono);">No active sessions registered.</td></tr>`;
        return;
      }

      tbody.innerHTML = tabs.map(tab => {
        const closeAction = tab.is_control
          ? `<span style="color: var(--dash-dim);">—</span>`
          : `<button class="btn-square btn-square-danger" style="padding: 2px 8px; font-size: 0.7rem;" onclick="closeTab(${tab.index})">Close</button>`;

        const statusClass = tab.is_control ? 'status-control' : tab.is_busy ? 'status-busy' : 'status-idle';
        const statusText = tab.state ? tab.state.toUpperCase() : (tab.is_control ? 'CONTROL' : tab.is_busy ? 'BUSY' : 'IDLE');

        return `
          <tr>
            <td class="mono">#${tab.index}</td>
            <td class="mono">${tab.session_key || 'ephemeral'}</td>
            <td><span class="tab-status-pill ${statusClass}">${statusText}</span></td>
            <td class="mono">${tab.last_active_seconds_ago !== null ? tab.last_active_seconds_ago + 's ago' : 'active'}</td>
            <td class="mono" style="max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${tab.url}">${tab.url || 'about:blank'}</td>
            <td>
              <div style="display: flex; gap: 4px;">
                <button class="btn-square" style="padding: 2px 6px; font-size: 0.7rem;" onclick="resetTab(${tab.index})">Reset</button>
                ${closeAction}
              </div>
            </td>
          </tr>
        `;
      }).join("");
    }

    const expandedRequestIds = new Set();

    function escapeHtml(str) {
      if (!str) return "";
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function toggleRequestDetail(id) {
      const row = document.getElementById(`detail-${id}`);
      const arrow = document.getElementById(`arrow-${id}`);
      if (!row) return;
      if (expandedRequestIds.has(id)) {
        expandedRequestIds.delete(id);
        row.style.display = "none";
        if (arrow) arrow.textContent = "▶";
      } else {
        expandedRequestIds.add(id);
        row.style.display = "table-row";
        if (arrow) arrow.textContent = "▼";
      }
    }

    function renderActivity(data) {
      const tbody = document.getElementById("activity-table-body");
      const requests = data.requests || [];
      if (!requests.length) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--dash-muted); padding: 18px; font-family: var(--font-mono);">No request activity recorded yet. Call /v1/chat/completions or use the Playground.</td></tr>`;
        return;
      }

      tbody.innerHTML = requests.map(req => {
        const isOk = req.status_code >= 200 && req.status_code < 400;
        const statusBadge = isOk
          ? `<span style="color: var(--dash-good); font-family: var(--font-mono); font-weight: 700;">${req.status_code} OK</span>`
          : `<span style="color: var(--dash-bad); font-family: var(--font-mono); font-weight: 700;">${req.status_code} ERR</span>`;

        const isExpanded = expandedRequestIds.has(req.id);
        const arrowChar = isExpanded ? "▼" : "▶";
        const detailDisplay = isExpanded ? "table-row" : "none";
        const payloadFormatted = req.payload
          ? escapeHtml(req.payload)
          : "(No payload body - GET request or query only)";

        return `
          <tr class="activity-row" onclick="toggleRequestDetail('${req.id}')" style="cursor: pointer;" title="Click to toggle request details">
            <td style="width: 28px; text-align: center; color: var(--dash-muted); font-size: 0.65rem;"><span id="arrow-${req.id}">${arrowChar}</span></td>
            <td class="mono">${req.time_str}</td>
            <td class="mono" style="font-weight: 700;">${req.method}</td>
            <td class="mono" style="max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${req.path}</td>
            <td class="mono">${req.model}</td>
            <td>${statusBadge}</td>
            <td class="mono">${req.duration_ms}ms</td>
            <td class="mono">${req.client_ip}</td>
          </tr>
          <tr id="detail-${req.id}" class="activity-detail-row" style="display: ${detailDisplay}; background: #0c0c0c;">
            <td colspan="8" style="padding: 12px 18px; border-bottom: 1px solid var(--dash-border);">
              <div style="display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--dash-muted); text-transform: uppercase;">Request Payload &amp; Details (${req.id})</span>
                  <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--dash-accent);">${req.method} ${req.path} &bull; ${req.duration_ms}ms</span>
                </div>
                <pre style="background: #141414; border: 1px solid var(--dash-border); padding: 10px 12px; font-family: var(--font-mono); font-size: 0.75rem; color: #7dd3fc; max-height: 220px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; margin: 0;">${payloadFormatted}</pre>
              </div>
            </td>
          </tr>
        `;
      }).join("");
    }

    async function fetchData() {
      try {
        const [tabsRes, actRes] = await Promise.all([
          fetch("/v1/tabs"),
          fetch("/v1/gateway/activity")
        ]);
        if (tabsRes.ok) {
          const data = await tabsRes.json();
          renderDashboard(data);
        }
        if (actRes.ok) {
          const actData = await actRes.json();
          renderActivity(actData);
        }
      } catch (err) {
        console.error("Dashboard fetch error:", err);
      }
    }

    function toggleAutoRefresh() {
      const btn = document.getElementById("btn-toggle-refresh");
      isAutoRefresh = !isAutoRefresh;
      if (isAutoRefresh) {
        btn.textContent = "Pause";
        startAutoRefresh();
      } else {
        btn.textContent = "Resume";
        clearInterval(refreshInterval);
      }
    }

    function startAutoRefresh() {
      clearInterval(refreshInterval);
      refreshInterval = setInterval(fetchData, 2000);
    }

    // Initial boot
    if (isCompact) {
      document.getElementById("btn-toggle-density").textContent = "Cards View";
    }
    loadModels();
    fetchData();
    startAutoRefresh();
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)
