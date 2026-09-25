from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.api.server import app
from src.api.browser_gate import BrowserTabPool, configure_tab_pool
from src.config import Config


class _MockPage:
    def __init__(self, url: str = "https://chatgpt.com") -> None:
        self.url = url
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    async def goto(self, url: str, **_kwargs) -> None:
        self.url = url

    async def close(self) -> None:
        self._closed = True

    async def title(self) -> str:
        return "ChatGPT - New Chat"

    async def screenshot(self, **_kwargs) -> bytes:
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00"


class _MockBrowser:
    def __init__(self) -> None:
        self.page = _MockPage("https://chatgpt.com")
        self.context = SimpleNamespace(pages=[self.page])

    async def new_page(self) -> _MockPage:
        page = _MockPage("about:blank")
        self.context.pages.append(page)
        return page


class MonitorRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.browser = _MockBrowser()
        self.pool = BrowserTabPool(self.browser)
        configure_tab_pool(self.browser)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        configure_tab_pool(None)

    def test_preview_html_served_without_auth(self) -> None:
        with patch.object(Config, "API_TOKEN", "secret123"):
            # Ensure /, /preview and /dashboard are accessible without auth
            resp_root = self.client.get("/")
            self.assertEqual(resp_root.status_code, 200)
            self.assertIn("text/html", resp_root.headers["content-type"])
            self.assertIn("MimicGate", resp_root.text)

            resp = self.client.get("/preview")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])
            self.assertIn("MimicGate", resp.text)
            self.assertIn("Active Browser Tabs", resp.text)

            resp_dash = self.client.get("/dashboard")
            self.assertEqual(resp_dash.status_code, 200)

    def test_get_tabs_list(self) -> None:
        resp = self.client.get("/v1/tabs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["tab_count"], 1)
        self.assertTrue(data["tab_pool_active"])
        self.assertEqual(data["tabs"][0]["is_control"], True)
        self.assertEqual(data["tabs"][0]["url"], "https://chatgpt.com")

    def test_get_tab_screenshot(self) -> None:
        resp = self.client.get("/v1/tabs/0/screenshot")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "image/jpeg")
        self.assertTrue(resp.content.startswith(b"\xff\xd8"))

    def test_get_tab_screenshot_out_of_range(self) -> None:
        resp = self.client.get("/v1/tabs/99/screenshot")
        self.assertEqual(resp.status_code, 404)

    def test_close_tab_protects_control_tab(self) -> None:
        resp = self.client.post("/v1/tabs/0/close")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("control tab", resp.json()["detail"].lower())

    def test_reset_tab(self) -> None:
        resp = self.client.post("/v1/tabs/0/reset")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "reset")
        self.assertEqual(data["index"], 0)

    def test_gateway_activity_endpoint(self) -> None:
        resp = self.client.get("/v1/gateway/activity")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("summary", data)
        self.assertIn("concurrency", data)
        self.assertIn("requests", data)
        self.assertIn("total_requests", data["summary"])

    def test_telemetry_captures_request_payload(self) -> None:
        from src.api.telemetry import telemetry
        telemetry.record_request(
            method="POST",
            path="/v1/chat/completions",
            model="gpt-5.6-sol",
            status_code=200,
            duration_ms=150.0,
            payload='{"model": "gpt-5.6-sol", "messages": [{"role": "user", "content": "hi"}]}',
        )
        resp = self.client.get("/v1/gateway/activity")
        self.assertEqual(resp.status_code, 200)
        recent = resp.json()["requests"]
        self.assertTrue(len(recent) > 0)
        entry = recent[0]
        self.assertIn("messages", entry["payload"])
        self.assertEqual(entry["model"], "gpt-5.6-sol")

    def test_vnc_url_resolution_defaults(self) -> None:
        with patch.object(Config, "VNC_PORT", 5800), patch.object(Config, "VNC_URL", ""):
            self.assertEqual(Config.get_vnc_url(), "http://localhost:5800")
            self.assertEqual(Config.get_vnc_url("192.168.1.100"), "http://192.168.1.100:5800")

    def test_vnc_url_resolution_custom_port(self) -> None:
        with patch.object(Config, "VNC_PORT", 5805), patch.object(Config, "VNC_URL", ""):
            self.assertEqual(Config.get_vnc_url(), "http://localhost:5805")
            self.assertEqual(Config.get_vnc_url("proxy.local"), "http://proxy.local:5805")

    def test_vnc_url_resolution_override(self) -> None:
        with patch.object(Config, "VNC_PORT", 5800), patch.object(Config, "VNC_URL", "https://vnc.example.com"):
            self.assertEqual(Config.get_vnc_url(), "https://vnc.example.com")
            self.assertEqual(Config.get_vnc_url("otherhost"), "https://vnc.example.com")

        with patch.object(Config, "VNC_PORT", 5800), patch.object(Config, "VNC_URL", "vnc.example.com"):
            self.assertEqual(Config.get_vnc_url(), "https://vnc.example.com")

    def test_tabs_diagnostics_includes_vnc_settings(self) -> None:
        with patch.object(Config, "VNC_PORT", 5910), patch.object(Config, "VNC_URL", "https://proxy.net/vnc"):
            resp = self.client.get("/v1/tabs")
            self.assertEqual(resp.status_code, 200)
            diag = resp.json()["diagnostics"]
            self.assertEqual(diag["vnc_port"], 5910)
            self.assertEqual(diag["vnc_url_override"], "https://proxy.net/vnc")
            self.assertEqual(diag["novnc_url"], "https://proxy.net/vnc")

    def test_dashboard_html_renders_vnc_settings(self) -> None:
        # Test custom port button label and href
        with patch.object(Config, "VNC_PORT", 5808), patch.object(Config, "VNC_URL", ""):
            resp = self.client.get("/dashboard")
            self.assertEqual(resp.status_code, 200)
            self.assertIn('href="http://localhost:5808"', resp.text)
            self.assertIn("noVNC (:5808)", resp.text)

        # Test reverse-proxy URL override button label and href
        with patch.object(Config, "VNC_PORT", 5800), patch.object(Config, "VNC_URL", "https://my-vnc.domain.org"):
            resp = self.client.get("/dashboard")
            self.assertEqual(resp.status_code, 200)
            self.assertIn('href="https://my-vnc.domain.org"', resp.text)
            self.assertIn("noVNC (Web GUI)", resp.text)


if __name__ == "__main__":
    unittest.main()

