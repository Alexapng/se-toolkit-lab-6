from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        payload = json.loads(body)
        question = payload["messages"][-1]["content"]

        response = {
            "choices": [
                {
                    "message": {
                        "content": f"Mock answer for: {question}",
                    }
                }
            ]
        }
        encoded = json.dumps(response).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class AgentCliTests(unittest.TestCase):
    def test_agent_outputs_json_with_answer_and_tool_calls(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLMHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        env = os.environ.copy()
        env["LLM_API_KEY"] = "test-key"
        env["LLM_API_BASE"] = f"http://127.0.0.1:{server.server_port}/v1"
        env["LLM_MODEL"] = "coder-model"

        try:
            result = subprocess.run(
                [sys.executable, "agent.py", "What does REST stand for?"],
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=60,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)

        self.assertIn("answer", output)
        self.assertIsInstance(output["answer"], str)
        self.assertIn("tool_calls", output)
        self.assertEqual(output["tool_calls"], [])
