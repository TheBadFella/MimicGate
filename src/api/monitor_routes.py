"""
Live multi-tab browser monitor and dashboard routes for MimicGate.

Provides endpoints to inspect, snapshot, and close background browser tabs,
plus a self-contained square dark dashboard inspired by UnpackUI.
"""

from __future__ import annotations

import time
from typing import Any
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

from src.api.browser_gate import (
    capture_browser_screenshot,
    close_browser_tab,
    get_tab_pool,
    list_browser_tabs,
)
from src.config import Config
from src.log import setup_logging

log = setup_logging("monitor_routes")

router = APIRouter(tags=["Monitor"])

_SERVER_START_TIME = time.monotonic()


@router.get("/v1/tabs")
async def get_tabs() -> dict[str, Any]:
    """List all open browser tabs and concurrency state."""
    pool = get_tab_pool()
    tabs = await list_browser_tabs()
    uptime_sec = round(time.monotonic() - _SERVER_START_TIME, 1)

    return {
        "provider": Config.PROVIDER,
        "provider_url": Config.provider_url(),
        "max_concurrent_requests": Config.MAX_CONCURRENT_REQUESTS,
        "max_active_tabs": Config.MAX_ACTIVE_TABS,
        "tab_pool_active": pool is not None,
        "uptime_seconds": uptime_sec,
        "tab_count": len(tabs),
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
        result = await close_browser_tab(index)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/preview", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
@router.get("/v1/preview", response_class=HTMLResponse)
async def preview_dashboard() -> HTMLResponse:
    """Serve the real-time square dark multi-tab monitor dashboard."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MimicGate — Live Monitor</title>
  <link rel="icon" type="image/png" href="/assets/favicon-32x32.png" />
  <style>
    /* UnpackUI-inspired Dark Theme Variables */
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

    /* Global reset to sharp square design */
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      border-radius: 0 !important; /* Strict square UI */
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

    /* Top Navigation Bar */
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
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .brand-title span { color: var(--dash-accent); }

    /* UnpackUI Live Chip */
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
      border-radius: 50% !important; /* Circle indicator inside chip */
      background: var(--dash-good);
      box-shadow: 0 0 8px rgba(22, 199, 132, 0.8);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { opacity: 0.7; }
      50% { opacity: 1; transform: scale(1.1); }
      100% { opacity: 0.7; }
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

    /* Container */
    main {
      max-width: 1440px;
      width: 100%;
      margin: 0 auto;
      padding: 20px 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    /* Top Stat Row (Unpackerr exact top cards) */
    .stat-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
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
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--dash-muted);
      font-family: var(--font-mono);
    }
    .stat-value {
      font-size: 1.85rem;
      font-weight: 800;
      font-family: var(--font-mono);
      line-height: 1;
      color: var(--dash-heading);
    }

    /* Secondary Compact Metrics Grid (UnpackUI secondary strip) */
    .submetric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 8px;
    }
    .submetric-item {
      background: var(--dash-panel);
      border: 1px solid var(--dash-border);
      padding: 9px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.78rem;
    }
    .submetric-item span:first-child {
      color: var(--dash-muted);
    }
    .submetric-item span:last-child {
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--dash-text);
    }

    /* Section Panels */
    .dashboard-panel {
      background: var(--dash-panel);
      border: 1px solid var(--dash-border);
      display: flex;
      flex-direction: column;
    }
    .panel-header {
      padding: 12px 18px;
      border-bottom: 1px solid var(--dash-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #141414;
    }
    .panel-title-wrap h2 {
      font-size: 0.95rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--dash-heading);
    }
    .panel-title-wrap p {
      font-size: 0.76rem;
      color: var(--dash-muted);
      margin-top: 2px;
    }

    /* Tab Cards Grid */
    .tab-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 14px;
      padding: 18px;
    }
    .tab-card {
      background: var(--dash-card);
      border: 1px solid var(--dash-border);
      display: flex;
      flex-direction: column;
      transition: border-color 0.15s ease;
    }
    .tab-card:hover {
      border-color: var(--dash-border-strong);
    }
    .tab-card-header {
      padding: 9px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #181818;
      border-bottom: 1px solid var(--dash-border);
    }
    .tab-identity {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tab-index-badge {
      background: #252525;
      border: 1px solid var(--dash-border-strong);
      font-family: var(--font-mono);
      font-size: 0.72rem;
      font-weight: 700;
      padding: 2px 7px;
      color: var(--dash-cyan);
    }
    .tab-status-pill {
      font-size: 0.7rem;
      font-family: var(--font-mono);
      font-weight: 600;
      padding: 2px 8px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .tab-status-pill.status-control {
      background: rgba(192, 132, 252, 0.12);
      color: var(--dash-purple);
      border: 1px solid rgba(192, 132, 252, 0.3);
    }
    .tab-status-pill.status-busy {
      background: rgba(246, 196, 83, 0.12);
      color: var(--dash-warn);
      border: 1px solid rgba(246, 196, 83, 0.3);
    }
    .tab-status-pill.status-idle {
      background: rgba(22, 199, 132, 0.12);
      color: var(--dash-good);
      border: 1px solid rgba(22, 199, 132, 0.3);
    }

    .tab-preview-wrap {
      position: relative;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #0b0b0b;
      border-bottom: 1px solid var(--dash-border);
      overflow: hidden;
      cursor: zoom-in;
    }
    .tab-preview-img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    .tab-card-body {
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
    .tab-meta-label {
      color: var(--dash-muted);
    }
    .tab-meta-value {
      font-family: var(--font-mono);
      color: var(--dash-text);
      max-width: 250px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    /* UnpackUI Table Styling */
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
      padding: 11px 14px;
      border-bottom: 1px solid var(--dash-border);
      color: var(--dash-text);
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .mono { font-family: var(--font-mono); }

    /* Modal for enlarged screenshot */
    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.88);
      z-index: 200;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .modal.active { display: flex; }
    .modal-content {
      max-width: 90vw;
      max-height: 90vh;
      border: 1px solid var(--dash-border-strong);
      box-shadow: 0 0 30px rgba(0, 0, 0, 0.8);
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
    </div>
    <div class="nav-actions">
      <button class="btn-square" id="btn-toggle-refresh" onclick="toggleAutoRefresh()">Pause</button>
      <button class="btn-square" onclick="fetchData()">Refresh</button>
      <a href="http://localhost:5800" target="_blank" class="btn-square" title="Open full interactive noVNC desktop">noVNC Desktop (:5800)</a>
      <a href="/docs" target="_blank" class="btn-square">API Docs</a>
    </div>
  </header>

  <main>
    <!-- Top Stat Cards (Unpackerr Top Row) -->
    <div class="stat-row">
      <div class="stat-card accent-warn">
        <div class="stat-label">Active Tabs</div>
        <div class="stat-value" id="val-active-tabs">0</div>
      </div>
      <div class="stat-card accent-cyan">
        <div class="stat-label">Max Tabs Cap</div>
        <div class="stat-value" id="val-max-tabs">0</div>
      </div>
      <div class="stat-card accent-bad">
        <div class="stat-label">Concurrency</div>
        <div class="stat-value" id="val-concurrency">0</div>
      </div>
      <div class="stat-card accent-mint">
        <div class="stat-label">Provider</div>
        <div class="stat-value" id="val-provider" style="font-size: 1.35rem;">—</div>
      </div>
      <div class="stat-card accent-purple">
        <div class="stat-label">Uptime</div>
        <div class="stat-value" id="val-uptime" style="font-size: 1.35rem;">0s</div>
      </div>
      <div class="stat-card accent-good">
        <div class="stat-label">Gateway Status</div>
        <div class="stat-value" style="font-size: 1.35rem; color: var(--dash-good);">READY</div>
      </div>
    </div>

    <!-- Secondary Compact Metrics Row (Unpackerr sub-metrics strip) -->
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

    <!-- Active Tabs Section -->
    <div class="dashboard-panel">
      <div class="panel-header">
        <div class="panel-title-wrap">
          <h2 id="tabs-section-heading">Active Browser Tabs (0)</h2>
          <p>Real-time visual monitoring of background worker tabs, session affinity, and conversation threads.</p>
        </div>
        <div class="nav-actions">
          <button class="btn-square" onclick="fetchData()">Reload Screenshots</button>
        </div>
      </div>

      <div class="tab-grid" id="tabs-container">
        <!-- Rendered dynamically -->
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
              <th>Status</th>
              <th>Last Active</th>
              <th>Current Page URL</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="table-body">
            <!-- Rendered dynamically -->
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- Enlarge Image Modal -->
  <div class="modal" id="image-modal" onclick="closeModal()">
    <div class="modal-content" onclick="event.stopPropagation()">
      <img id="modal-img" src="" alt="Enlarged screenshot" />
    </div>
  </div>

  <script>
    let autoRefresh = true;
    let refreshTimer = null;

    async function fetchData() {
      try {
        const res = await fetch("/v1/tabs");
        if (!res.ok) return;
        const data = await res.json();
        renderDashboard(data);
      } catch (err) {
        console.warn("Failed to poll /v1/tabs:", err);
      }
    }

    function renderDashboard(data) {
      document.getElementById("val-active-tabs").textContent = data.tab_count || 0;
      document.getElementById("val-max-tabs").textContent = data.max_active_tabs || 4;
      document.getElementById("val-concurrency").textContent = data.max_concurrent_requests || 3;
      document.getElementById("val-provider").textContent = (data.provider || "chatgpt").toUpperCase();
      document.getElementById("val-uptime").textContent = formatUptime(data.uptime_seconds || 0);
      document.getElementById("pill-url").textContent = data.provider_url || "—";
      document.getElementById("tabs-section-heading").textContent = `Active Browser Tabs (${data.tab_count || 0})`;

      renderTabCards(data.tabs || []);
      renderTable(data.tabs || []);
    }

    function renderTabCards(tabs) {
      const container = document.getElementById("tabs-container");
      if (!tabs.length) {
        container.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--dash-muted); font-family: var(--font-mono); font-size: 0.82rem;">
            No browser tabs currently active. A worker tab will launch when the gateway receives a request.
          </div>
        `;
        return;
      }

      const timestamp = Date.now();
      container.innerHTML = tabs.map(tab => {
        let statusClass = "status-idle";
        let statusLabel = "Idle";
        if (tab.is_control) {
          statusClass = "status-control";
          statusLabel = "Control Tab";
        } else if (tab.is_busy) {
          statusClass = "status-busy";
          statusLabel = "Busy";
        }

        const closeBtn = tab.is_control
          ? `<span style="font-size: 0.7rem; color: var(--dash-dim); font-family: var(--font-mono); text-transform: uppercase;">Protected</span>`
          : `<button class="btn-square btn-square-danger" style="padding: 2px 8px; font-size: 0.7rem;" onclick="closeTab(${tab.index})">Close</button>`;

        return `
          <div class="tab-card">
            <div class="tab-card-header">
              <div class="tab-identity">
                <span class="tab-index-badge">#${tab.index}</span>
                <span class="tab-status-pill ${statusClass}">${statusLabel}</span>
              </div>
              <div>${closeBtn}</div>
            </div>
            <div class="tab-preview-wrap" onclick="openModal('/v1/tabs/${tab.index}/screenshot?t=${timestamp}')">
              <img class="tab-preview-img" src="/v1/tabs/${tab.index}/screenshot?t=${timestamp}" alt="Tab ${tab.index} screenshot" loading="lazy" />
            </div>
            <div class="tab-card-body">
              <div class="tab-meta-row">
                <span class="tab-meta-label">Title</span>
                <span class="tab-meta-value" title="${tab.title || 'Untitled'}">${tab.title || 'Untitled'}</span>
              </div>
              <div class="tab-meta-row">
                <span class="tab-meta-label">Session</span>
                <span class="tab-meta-value">${tab.session_key || '—'}</span>
              </div>
              <div class="tab-meta-row">
                <span class="tab-meta-label">URL</span>
                <span class="tab-meta-value" title="${tab.url || 'about:blank'}">${tab.url || 'about:blank'}</span>
              </div>
              <div class="tab-meta-row">
                <span class="tab-meta-label">Last Active</span>
                <span class="tab-meta-value">${tab.last_active_seconds_ago !== null ? tab.last_active_seconds_ago + 's ago' : 'active'}</span>
              </div>
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

        return `
          <tr>
            <td class="mono">#${tab.index}</td>
            <td class="mono">${tab.session_key || 'ephemeral'}</td>
            <td><span class="tab-status-pill ${tab.is_control ? 'status-control' : tab.is_busy ? 'status-busy' : 'status-idle'}">${tab.is_control ? 'Control' : tab.is_busy ? 'Busy' : 'Idle'}</span></td>
            <td class="mono">${tab.last_active_seconds_ago !== null ? tab.last_active_seconds_ago + 's ago' : 'active'}</td>
            <td class="mono" style="max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${tab.url}">${tab.url || 'about:blank'}</td>
            <td>${closeAction}</td>
          </tr>
        `;
      }).join("");
    }

    async function closeTab(index) {
      if (!confirm(`Are you sure you want to close Tab #${index}?`)) return;
      try {
        const res = await fetch(`/v1/tabs/${index}/close`, { method: "POST" });
        if (res.ok) {
          fetchData();
        } else {
          const err = await res.json();
          alert(`Could not close tab: ${err.detail || 'Unknown error'}`);
        }
      } catch (err) {
        alert(`Error closing tab: ${err}`);
      }
    }

    function formatUptime(sec) {
      if (sec < 60) return `${Math.round(sec)}s`;
      if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
      return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
    }

    function toggleAutoRefresh() {
      autoRefresh = !autoRefresh;
      const btn = document.getElementById("btn-toggle-refresh");
      const pill = document.getElementById("pill-refresh");
      if (autoRefresh) {
        btn.textContent = "Pause";
        pill.textContent = "2.0s";
        startPolling();
      } else {
        btn.textContent = "Resume";
        pill.textContent = "Paused";
        stopPolling();
      }
    }

    function startPolling() {
      stopPolling();
      refreshTimer = setInterval(fetchData, 2000);
    }

    function stopPolling() {
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
    }

    function openModal(src) {
      const modal = document.getElementById("image-modal");
      const img = document.getElementById("modal-img");
      img.src = src;
      modal.classList.add("active");
    }

    function closeModal() {
      document.getElementById("image-modal").classList.remove("active");
    }

    // Initial load and start polling
    fetchData();
    startPolling();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
