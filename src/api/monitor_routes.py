"""
Live multi-tab browser monitor and dashboard routes for MimicGate.

Provides endpoints to inspect, snapshot, and close background browser tabs,
plus a self-contained dark dashboard in the Unpackerr style.
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
        # Return a fallback SVG placeholder so the UI card renders cleanly
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <rect width="640" height="360" fill="#131418"/>
  <text x="50%" y="45%" text-anchor="middle" fill="#6c7380" font-family="sans-serif" font-size="16">Preview Unavailable</text>
  <text x="50%" y="58%" text-anchor="middle" fill="#444b55" font-family="monospace" font-size="12">Tab {index}: {str(exc)[:45]}</text>
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
    """Serve the real-time dark multi-tab monitor dashboard."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MimicGate — Live Multi-Tab Monitor</title>
  <link rel="icon" type="image/png" href="/assets/favicon-32x32.png" />
  <style>
    :root {
      --bg: #090a0d;
      --surface: #101216;
      --card-bg: #15171d;
      --border: #232732;
      --border-accent: #2e3442;
      --text-main: #f0f3f8;
      --text-muted: #7e8799;
      --text-dim: #4d5463;
      --accent-mint: #80e8ba;
      --accent-cyan: #38bdf8;
      --accent-yellow: #facc15;
      --accent-purple: #c084fc;
      --accent-red: #f87171;
      --accent-blue: #60a5fa;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text-main);
      font-family: var(--font-sans);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      padding: 0;
      background-image: 
        linear-gradient(to right, rgba(255, 255, 255, 0.02) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
      background-size: 32px 32px;
    }

    /* Top Navigation */
    header {
      background: rgba(16, 18, 22, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
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
    .brand-logo {
      width: 28px;
      height: 28px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #1b1e26;
      border: 1px solid var(--border);
    }
    .brand-title {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .brand-title span { color: var(--accent-mint); }
    .badge-live {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: rgba(128, 232, 186, 0.1);
      border: 1px solid rgba(128, 232, 186, 0.3);
      color: var(--accent-mint);
      font-size: 0.72rem;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .badge-live::before {
      content: "";
      width: 6px;
      height: 6px;
      background: var(--accent-mint);
      border-radius: 50%;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(128, 232, 186, 0.7); }
      70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(128, 232, 186, 0); }
      100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(128, 232, 186, 0); }
    }

    .nav-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .btn {
      background: #181b22;
      border: 1px solid var(--border);
      color: var(--text-main);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 0.82rem;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      transition: all 0.15s ease;
    }
    .btn:hover {
      background: #222630;
      border-color: var(--border-accent);
      color: #fff;
    }
    .btn-danger {
      border-color: rgba(248, 113, 113, 0.3);
      color: var(--accent-red);
    }
    .btn-danger:hover {
      background: rgba(248, 113, 113, 0.12);
      border-color: var(--accent-red);
    }

    /* Container */
    main {
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Metric Summary Strip (Unpackerr top cards) */
    .metric-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
    }
    .metric-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-top: 3px solid var(--border-accent);
      border-radius: 6px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .metric-card.accent-mint { border-top-color: var(--accent-mint); }
    .metric-card.accent-cyan { border-top-color: var(--accent-cyan); }
    .metric-card.accent-yellow { border-top-color: var(--accent-yellow); }
    .metric-card.accent-purple { border-top-color: var(--accent-purple); }
    .metric-card.accent-blue { border-top-color: var(--accent-blue); }
    .metric-card.accent-red { border-top-color: var(--accent-red); }

    .metric-label {
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-muted);
    }
    .metric-value {
      font-size: 1.6rem;
      font-weight: 700;
      font-family: var(--font-mono);
      line-height: 1;
      color: #ffffff;
    }

    /* Sub-metrics Pill Row */
    .submetric-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
    }
    .submetric-pill {
      background: #111317;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.8rem;
    }
    .submetric-pill span:first-child { color: var(--text-muted); }
    .submetric-pill span:last-child {
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--text-main);
    }

    /* Section Containers */
    .section-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .section-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(21, 23, 29, 0.4);
    }
    .section-title-wrap h2 {
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: -0.01em;
    }
    .section-title-wrap p {
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 2px;
    }

    /* Tab Cards Grid */
    .tab-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 16px;
      padding: 20px;
    }
    .tab-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transition: border-color 0.2s ease, transform 0.2s ease;
    }
    .tab-card:hover {
      border-color: var(--border-accent);
      transform: translateY(-2px);
    }
    .tab-card-header {
      padding: 10px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #181b22;
      border-bottom: 1px solid var(--border);
    }
    .tab-identity {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tab-index-badge {
      background: #252a36;
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      color: var(--accent-cyan);
    }
    .tab-status-pill {
      font-size: 0.72rem;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 9999px;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .tab-status-pill.status-control {
      background: rgba(192, 132, 252, 0.12);
      color: var(--accent-purple);
      border: 1px solid rgba(192, 132, 252, 0.3);
    }
    .tab-status-pill.status-busy {
      background: rgba(250, 204, 21, 0.12);
      color: var(--accent-yellow);
      border: 1px solid rgba(250, 204, 21, 0.3);
    }
    .tab-status-pill.status-idle {
      background: rgba(128, 232, 186, 0.12);
      color: var(--accent-mint);
      border: 1px solid rgba(128, 232, 186, 0.3);
    }

    .tab-preview-wrap {
      position: relative;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #0d0e12;
      border-bottom: 1px solid var(--border);
      overflow: hidden;
      cursor: zoom-in;
    }
    .tab-preview-img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      transition: opacity 0.2s ease;
    }
    .tab-card-body {
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 0.78rem;
    }
    .tab-meta-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .tab-meta-label { color: var(--text-muted); }
    .tab-meta-value {
      font-family: var(--font-mono);
      color: var(--text-main);
      max-width: 240px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    /* History Table */
    .history-table-wrap {
      width: 100%;
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.82rem;
    }
    th {
      padding: 12px 16px;
      background: #151820;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.7rem;
      letter-spacing: 0.05em;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      color: var(--text-main);
    }
    tr:hover td { background: rgba(255, 255, 255, 0.015); }
    .mono { font-family: var(--font-mono); }

    /* Modal for enlarged screenshot */
    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.85);
      backdrop-filter: blur(8px);
      z-index: 200;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .modal.active { display: flex; }
    .modal-content {
      max-width: 90vw;
      max-height: 90vh;
      border-radius: 8px;
      border: 1px solid var(--border-accent);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
      overflow: hidden;
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
      <div class="brand-logo">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#80e8ba" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
        </svg>
      </div>
      <div class="brand-title">MimicGate <span>Monitor</span></div>
      <div class="badge-live">Live</div>
    </div>
    <div class="nav-actions">
      <button class="btn" id="btn-toggle-refresh" onclick="toggleAutoRefresh()">Pause</button>
      <button class="btn" onclick="fetchData()">Refresh</button>
      <a href="http://localhost:5800" target="_blank" class="btn" title="Open full interactive noVNC desktop">noVNC GUI (:5800)</a>
      <a href="/docs" target="_blank" class="btn">API Docs</a>
    </div>
  </header>

  <main>
    <!-- Top Metric Strip (Unpackerr Style) -->
    <div class="metric-strip">
      <div class="metric-card accent-mint">
        <div class="metric-label">Active Tabs</div>
        <div class="metric-value" id="val-active-tabs">0</div>
      </div>
      <div class="metric-card accent-cyan">
        <div class="metric-label">Max Tabs Cap</div>
        <div class="metric-value" id="val-max-tabs">0</div>
      </div>
      <div class="metric-card accent-yellow">
        <div class="metric-label">Concurrency</div>
        <div class="metric-value" id="val-concurrency">0</div>
      </div>
      <div class="metric-card accent-purple">
        <div class="metric-label">Provider</div>
        <div class="metric-value" id="val-provider" style="font-size: 1.3rem;">—</div>
      </div>
      <div class="metric-card accent-blue">
        <div class="metric-label">Uptime</div>
        <div class="metric-value" id="val-uptime" style="font-size: 1.3rem;">0s</div>
      </div>
      <div class="metric-card accent-mint">
        <div class="metric-label">Gateway Status</div>
        <div class="metric-value" style="font-size: 1.3rem; color: var(--accent-mint);">READY</div>
      </div>
    </div>

    <!-- Secondary Context Pills -->
    <div class="submetric-row">
      <div class="submetric-pill">
        <span>Provider Base URL</span>
        <span id="pill-url">—</span>
      </div>
      <div class="submetric-pill">
        <span>Tab Pool Mode</span>
        <span id="pill-pool">Active (LRU Eviction)</span>
      </div>
      <div class="submetric-pill">
        <span>Auto-Refresh Interval</span>
        <span id="pill-refresh">2.0s</span>
      </div>
    </div>

    <!-- Active Tabs Section -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-title-wrap">
          <h2 id="tabs-section-heading">Active Browser Tabs (0)</h2>
          <p>Real-time visual monitoring of background worker tabs, session affinity, and conversation threads.</p>
        </div>
        <div class="nav-actions">
          <button class="btn" onclick="fetchData()">Reload Screenshots</button>
        </div>
      </div>

      <div class="tab-grid" id="tabs-container">
        <!-- Rendered dynamically -->
      </div>
    </div>

    <!-- Sessions and Concurrency Table -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-title-wrap">
          <h2>Session Registry</h2>
          <p>Active persistent session keys mapped to underlying browser tabs and thread URLs.</p>
        </div>
      </div>
      <div class="history-table-wrap">
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
      document.getElementById("val-max-tabs").textContent = data.max_active_tabs || 5;
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
          <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--text-muted);">
            No browser tabs currently active. A tab will launch when the gateway receives a request.
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
          ? `<span style="font-size: 0.72rem; color: var(--text-dim);">Protected</span>`
          : `<button class="btn btn-danger" style="padding: 2px 8px; font-size: 0.72rem;" onclick="closeTab(${tab.index})">Close</button>`;

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
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 24px;">No active sessions registered.</td></tr>`;
        return;
      }

      tbody.innerHTML = tabs.map(tab => {
        const closeAction = tab.is_control
          ? `<span style="color: var(--text-dim);">—</span>`
          : `<button class="btn btn-danger" style="padding: 2px 8px; font-size: 0.72rem;" onclick="closeTab(${tab.index})">Close</button>`;

        return `
          <tr>
            <td class="mono">#${tab.index}</td>
            <td class="mono">${tab.session_key || 'ephemeral'}</td>
            <td><span class="tab-status-pill ${tab.is_control ? 'status-control' : tab.is_busy ? 'status-busy' : 'status-idle'}">${tab.is_control ? 'Control' : tab.is_busy ? 'Busy' : 'Idle'}</span></td>
            <td>${tab.last_active_seconds_ago !== null ? tab.last_active_seconds_ago + 's ago' : 'active'}</td>
            <td class="mono" style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${tab.url}">${tab.url || 'about:blank'}</td>
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
