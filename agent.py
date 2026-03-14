#!/usr/bin/env python3
"""Documentation agent CLI."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILES = (Path(".env.agent.secret"),)
MAX_TOOL_CALLS = 10
SYSTEM_PROMPT = """
You are a documentation agent for this repository.

Use the available tools to inspect the project wiki before answering questions.
- Start with list_files when you need to discover which wiki file is relevant.
- Then use read_file to read the most relevant file.
- Base your answer on the tool results, not on prior knowledge.
- When you are ready to answer, respond with a JSON object:
  {"answer": "...", "source": "wiki/file.md#section-anchor"}
- The source must be a repository-relative wiki path plus a section anchor.
- If the question asks about wiki contents in general, choose the most relevant wiki source you used.
- Do not invent files or anchors.
""".strip()
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files and directories inside the repository. "
                "Use this first to discover relevant wiki files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from the project root, for example wiki",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a text file from the repository. Use this after list_files to inspect wiki content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative file path from the project root, for example wiki/git-vscode.md"
                        ),
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


@dataclass(frozen=True)
class Settings:
    api_key: str
    api_base: str
    model: str


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs without overriding existing env vars."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings() -> Settings:
    """Load and validate LLM settings."""
    for env_file in ENV_FILES:
        load_env_file(env_file)

    api_key = os.environ.get("LLM_API_KEY", "").strip()
    api_base = os.environ.get("LLM_API_BASE", "").strip().rstrip("/")
    model = os.environ.get("LLM_MODEL", "").strip()

    missing = [
        name
        for name, value in (
            ("LLM_API_KEY", api_key),
            ("LLM_API_BASE", api_base),
            ("LLM_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return Settings(api_key=api_key, api_base=api_base, model=model)


def resolve_repo_path(path_str: str) -> Path:
    """Resolve a repository-relative path and reject traversal."""
    candidate = Path(path_str)
    if candidate.is_absolute():
        raise ValueError("Path must be relative to the project root")

    resolved = (PROJECT_ROOT / candidate).resolve(strict=False)
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("Path escapes the project root") from exc
    return resolved


def list_files(path: str) -> str:
    """List files and directories at the given relative path."""
    try:
        target = resolve_repo_path(path)
    except ValueError as exc:
        return f"Error: {exc}"

    if not target.exists():
        return "Error: path does not exist"
    if not target.is_dir():
        return "Error: path is not a directory"

    entries = []
    for child in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        suffix = "/" if child.is_dir() else ""
        try:
            relative = child.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            relative = child.name
        entries.append(f"{relative}{suffix}")
    return "\n".join(entries)


def read_file(path: str) -> str:
    """Read a file from the repository."""
    try:
        target = resolve_repo_path(path)
    except ValueError as exc:
        return f"Error: {exc}"

    if not target.exists():
        return "Error: file does not exist"
    if not target.is_file():
        return "Error: path is not a file"

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "Error: file is not valid UTF-8 text"


def call_llm(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """Send the current conversation to the LLM and return the assistant message."""
    payload = {
        "model": settings.model,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    request = Request(
        url=f"{settings.api_base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"LLM request failed with status {exc.code}: {body}") from exc
    except URLError as exc:
        raise ValueError(f"Cannot reach LLM API: {exc.reason}") from exc

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM response is missing choices[0].message") from exc

    if not isinstance(message, dict):
        raise ValueError("LLM response message is not an object")
    return message


def execute_tool(name: str, args: dict[str, Any]) -> str:
    """Execute a supported tool and return its string result."""
    if name == "list_files":
        return list_files(str(args.get("path", "")))
    if name == "read_file":
        return read_file(str(args.get("path", "")))
    return f"Error: unknown tool '{name}'"


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    """Parse JSON tool arguments."""
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid tool arguments JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Tool arguments must decode to an object")
    return parsed


def extract_final_response(content: str) -> tuple[str, str]:
    """Parse the model's final answer and source from JSON content."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("Final LLM response is not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Final LLM response must be a JSON object")

    answer = parsed.get("answer")
    source = parsed.get("source")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Final response is missing a non-empty string 'answer'")
    if not isinstance(source, str):
        raise ValueError("Final response is missing string 'source'")
    return answer.strip(), source.strip()


def run_agent(question: str, settings: Settings) -> dict[str, Any]:
    """Run the agentic loop until a final answer is produced."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    executed_tool_calls: list[dict[str, Any]] = []
    last_answer = ""
    last_source = ""

    while len(executed_tool_calls) < MAX_TOOL_CALLS:
        assistant_message = call_llm(messages, settings)
        assistant_content = assistant_message.get("content") or ""
        raw_tool_calls = assistant_message.get("tool_calls") or []

        message_for_history: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_content,
        }
        if raw_tool_calls:
            message_for_history["tool_calls"] = raw_tool_calls
        messages.append(message_for_history)

        if not raw_tool_calls:
            answer, source = extract_final_response(assistant_content)
            return {
                "answer": answer,
                "source": source,
                "tool_calls": executed_tool_calls,
            }

        remaining = MAX_TOOL_CALLS - len(executed_tool_calls)
        for tool_call in raw_tool_calls[:remaining]:
            function = tool_call.get("function") or {}
            name = function.get("name", "")
            args = parse_tool_arguments(function.get("arguments") or "{}")
            result = execute_tool(name, args)
            executed_tool_calls.append({"tool": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": result,
                }
            )

        if assistant_content.strip():
            try:
                last_answer, last_source = extract_final_response(assistant_content)
            except ValueError:
                pass

    fallback_answer = last_answer or "I could not finish within the tool-call limit."
    return {
        "answer": fallback_answer,
        "source": last_source,
        "tool_calls": executed_tool_calls,
    }


def main() -> int:
    """CLI entrypoint."""
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Usage: uv run agent.py \"Your question\"", file=sys.stderr)
        return 1

    question = sys.argv[1].strip()

    try:
        settings = load_settings()
        result = run_agent(question, settings)
    except Exception as exc:
        print(f"agent.py error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
