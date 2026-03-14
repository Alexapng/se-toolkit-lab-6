from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def build_response(message: dict[str, object]) -> bytes:
    payload = {"choices": [{"message": message}]}
    return json.dumps(payload).encode("utf-8")


class FakeLLMHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        payload = json.loads(body)
        messages = payload["messages"]
        question = messages[1]["content"]
        tool_messages = [message for message in messages if message["role"] == "tool"]

        if question == "What does REST stand for?":
            response = build_response(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "answer": "Representational State Transfer.",
                            "source": "wiki/rest-api.md#what-is-rest",
                        }
                    ),
                }
            )
        elif question == "How do you resolve a merge conflict?":
            if not tool_messages:
                response = build_response(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-list-files",
                                "type": "function",
                                "function": {
                                    "name": "list_files",
                                    "arguments": json.dumps({"path": "wiki"}),
                                },
                            },
                            {
                                "id": "call-read-file",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": json.dumps({"path": "wiki/git-vscode.md"}),
                                },
                            },
                        ],
                    }
                )
            else:
                response = build_response(
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": (
                                    "Edit the conflicting file, choose which changes to keep, "
                                    "then mark the conflict as resolved."
                                ),
                                "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
                            }
                        ),
                    }
                )
        elif question == "What files are in the wiki?":
            if not tool_messages:
                response = build_response(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-list-files-only",
                                "type": "function",
                                "function": {
                                    "name": "list_files",
                                    "arguments": json.dumps({"path": "wiki"}),
                                },
                            }
                        ],
                    }
                )
            else:
                response = build_response(
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": "The wiki contains Markdown files such as git-workflow.md, qwen.md, and ssh.md.",
                                "source": "wiki/git-workflow.md#git-workflow-for-tasks",
                            }
                        ),
                    }
                )
        else:
            response = build_response(
                {
                    "role": "assistant",
                    "content": json.dumps({"answer": f"Unhandled question: {question}", "source": ""}),
                }
            )

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        return


class AgentCliTests(unittest.TestCase):
    def run_agent(self, question: str) -> dict[str, object]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLMHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        env = os.environ.copy()
        env["LLM_API_KEY"] = "test-key"
        env["LLM_API_BASE"] = f"http://127.0.0.1:{server.server_port}/v1"
        env["LLM_MODEL"] = "coder-model"

        try:
            result = subprocess.run(
                [sys.executable, "agent.py", question],
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
        return json.loads(result.stdout)

    def test_agent_outputs_json_with_answer_and_tool_calls(self) -> None:
        output = self.run_agent("What does REST stand for?")

        self.assertIn("answer", output)
        self.assertIsInstance(output["answer"], str)
        self.assertIn("source", output)
        self.assertEqual(output["source"], "wiki/rest-api.md#what-is-rest")
        self.assertIn("tool_calls", output)
        self.assertEqual(output["tool_calls"], [])

    def test_agent_uses_read_file_for_merge_conflict_question(self) -> None:
        output = self.run_agent("How do you resolve a merge conflict?")

        self.assertEqual(output["source"], "wiki/git-vscode.md#resolve-a-merge-conflict")
        tool_names = [tool_call["tool"] for tool_call in output["tool_calls"]]
        self.assertIn("read_file", tool_names)
        self.assertIn("list_files", tool_names)

    def test_agent_uses_list_files_for_wiki_listing_question(self) -> None:
        output = self.run_agent("What files are in the wiki?")

        tool_names = [tool_call["tool"] for tool_call in output["tool_calls"]]
        self.assertIn("list_files", tool_names)
