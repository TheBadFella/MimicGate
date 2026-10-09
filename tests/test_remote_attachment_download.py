from __future__ import annotations

import asyncio
import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
import uvicorn

from src.api import openai_routes as routes


class _AttachmentHandler(BaseHTTPRequestHandler):
    # HTTP/1.0 exercises the response-owned socket after HTTPConnection drops it.
    def log_message(self, *_args):
        pass

    def do_GET(self):
        try:
            if self.path == "/headers":
                for byte in b"HTTP/1.0 200 OK\r\nContent-Length: 3\r\n\r\nabc":
                    self.connection.sendall(bytes([byte]))
                    time.sleep(0.08)
                return
            if self.path == "/chunked":
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for _ in range(10):
                    self.wfile.write(b"1\r\nx\r\n")
                    self.wfile.flush()
                    time.sleep(0.2)
                self.wfile.write(b"0\r\n\r\n")
                return
            payload = b"proof"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.path == "/slow":
                for byte in payload:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.3)
            else:
                self.wfile.write(payload)
        except OSError:
            pass


class RemoteAttachmentDeadlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _AttachmentHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = patch.multiple(
            routes.Config,
            REMOTE_ATTACHMENT_ALLOW_HTTP=True,
            REMOTE_ATTACHMENT_ALLOW_PRIVATE_NETS=True,
            REMOTE_ATTACHMENT_TIMEOUT_SECONDS=1,
        )
        self.config.start()
        self.addCleanup(self.config.stop)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def test_deadline_interrupts_body_chunk_framing_and_headers(self):
        for endpoint in ("/slow", "/chunked", "/headers"):
            with self.subTest(endpoint=endpoint):
                started = time.monotonic()
                with self.assertRaises(routes.RemoteAttachmentError):
                    routes._download_remote_attachment(self.url + endpoint, f"{self.tmp.name}/file")
                self.assertLess(time.monotonic() - started, 1.6)
                self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_dns_deadline_kills_and_reaps_resolver(self):
        processes = []
        original = routes.subprocess.Popen

        def record(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            return process

        script = "import time; time.sleep(30)"
        started = time.monotonic()
        with patch.object(routes, "_REMOTE_DNS_SCRIPT", script), patch.object(
            routes.subprocess, "Popen", side_effect=record,
        ):
            with self.assertRaises(routes.RemoteAttachmentError):
                routes._download_remote_attachment(
                    f"http://fixture.example:{self.server.server_port}/file", f"{self.tmp.name}/file",
                )
        self.assertLess(time.monotonic() - started, 1.6)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].returncode)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_dns_pinning_preserves_host_and_success_bytes(self):
        calls = []
        original = socket.getaddrinfo

        def record(host, *args, **kwargs):
            calls.append(host)
            return original(host, *args, **kwargs)

        with patch.object(routes, "_REMOTE_DNS_SCRIPT", "print('[\"127.0.0.1\"]')"), patch.object(
            routes.socket, "getaddrinfo", side_effect=record,
        ):
            path = routes._download_remote_attachment(
                f"http://fixture.example:{self.server.server_port}/file", f"{self.tmp.name}/file",
            )
        self.assertEqual(Path(path).read_bytes(), b"proof")
        self.assertNotIn("fixture.example", calls, "connection must not resolve the original host again")

    def test_cancellation_stops_download_and_removes_partial_file(self):
        async def run():
            with patch.object(routes.Config, "REMOTE_ATTACHMENT_TIMEOUT_SECONDS", 15):
                task = asyncio.create_task(routes._download_file(self.url + "/slow", self.tmp.name))
                for _ in range(100):
                    if list(Path(self.tmp.name).iterdir()):
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(list(Path(self.tmp.name).iterdir()), "download must be in progress")
                started = time.monotonic()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertLess(time.monotonic() - started, 0.6)
                self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        asyncio.run(run())

    def test_cancellation_kills_dns_worker(self):
        processes = []
        original = routes.subprocess.Popen

        def record(*args, **kwargs):
            process = original(*args, **kwargs)
            processes.append(process)
            return process

        async def run():
            with patch.object(routes.Config, "REMOTE_ATTACHMENT_TIMEOUT_SECONDS", 15), patch.object(
                routes, "_REMOTE_DNS_SCRIPT", "import time; time.sleep(30)",
            ), patch.object(routes.subprocess, "Popen", side_effect=record):
                task = asyncio.create_task(routes._download_file(
                    f"http://fixture.example:{self.server.server_port}/file", self.tmp.name,
                ))
                for _ in range(100):
                    if processes:
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(processes)
                started = time.monotonic()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertLess(time.monotonic() - started, 0.6)
                self.assertIsNotNone(processes[0].returncode)
                self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        asyncio.run(run())

    def test_tls_handshake_is_inside_deadline(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        accepted = []
        budgets = []
        original_budget = routes._RemoteAttachmentBudget

        def record_budget():
            budget = original_budget()
            budgets.append(budget)
            return budget

        def stall():
            try:
                client, _ = listener.accept()
            except OSError:
                return
            accepted.append(client)
            try:
                while client.recv(4096):
                    pass
            except OSError:
                pass
            finally:
                client.close()

        thread = threading.Thread(target=stall, daemon=True)
        thread.start()
        try:
            started = time.monotonic()
            with patch.object(routes, "_RemoteAttachmentBudget", side_effect=record_budget), self.assertRaises(routes.RemoteAttachmentError):
                routes._download_remote_attachment(
                    f"https://127.0.0.1:{listener.getsockname()[1]}/file", f"{self.tmp.name}/tls",
                )
            self.assertLess(time.monotonic() - started, 1.6)
            # Verify our descriptor directly; remote FIN delivery can lag on Windows.
            self.assertEqual(len(budgets), 1)
            self.assertIsNotNone(budgets[0]._socket)
            self.assertEqual(budgets[0]._socket.fileno(), -1)
            self.assertFalse(budgets[0]._timer.is_alive())
            self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        finally:
            listener.close()
            for client in accepted:
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                client.close()
            thread.join(timeout=3)


class StreamingAttachmentErrorTests(unittest.TestCase):
    def test_rejected_attachment_is_complete_sse_error_over_http(self):
        class Client:
            def __init__(self):
                self.sent = []
            def _extract_thread_id(self):
                return "fixture-thread"
            async def new_chat(self):
                pass
            async def send_message(self, *args, **kwargs):
                self.sent.append((args, kwargs))
                return SimpleNamespace(message="fixture", thread_id="fixture-thread", audio=None)

        client = Client()
        app = FastAPI()
        app.include_router(routes.openai_router)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="critical"))
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        with patch.object(routes, "_get_client", return_value=client), patch.object(
            routes, "_lookup_thread_title", new=AsyncMock(return_value="Fixture"),
        ), patch.object(routes.Config, "REMOTE_ATTACHMENT_ALLOW_HTTP", False):
            thread.start()
            try:
                for _ in range(100):
                    if server.started:
                        break
                    time.sleep(0.01)
                self.assertTrue(server.started)
                for endpoint in ("/v1/chat/completions", "/v1/responses"):
                    with self.subTest(endpoint=endpoint):
                        chat = {"model": "mimicgate-browser", "stream": True, "messages": [
                            {"role": "user", "content": [{"type": "image_url", "image_url": {
                                "url": "http://127.0.0.1:1/fixture.png",
                            }}]},
                        ]}
                        responses = {"model": "mimicgate-browser", "stream": True, "store": False, "input": [
                            {"role": "user", "content": [{"type": "input_image",
                                "image_url": "http://127.0.0.1:1/fixture.png"}]},
                        ]}
                        connection = http.client.HTTPConnection("127.0.0.1", listener.getsockname()[1], timeout=5)
                        try:
                            connection.request("POST", endpoint, json.dumps(
                                responses if endpoint == "/v1/responses" else chat,
                            ), {"Content-Type": "application/json"})
                            response = connection.getresponse()
                            body = response.read().decode()
                            self.assertEqual(response.status, 200)
                            self.assertIn("text/event-stream", response.getheader("Content-Type"))
                            self.assertIn("plain-http remote attachments are disabled", body)
                            self.assertIn("invalid_request_error", body)
                            self.assertTrue(body.endswith("data: [DONE]\n\n"))
                            self.assertNotIn("response.completed", body)
                            self.assertNotIn("chat.completion.chunk", body)
                            if endpoint == "/v1/responses":
                                self.assertIn("event: error\n", body)
                            else:
                                data = body.split("data: ", 1)[1].split("\n", 1)[0]
                                self.assertEqual(json.loads(data)["error"]["code"], "400")
                            self.assertEqual(client.sent, [])
                        finally:
                            connection.close()
            finally:
                server.should_exit = True
                thread.join(timeout=3)
                listener.close()
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
