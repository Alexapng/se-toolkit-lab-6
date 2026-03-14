#!/usr/bin/env python3
"""Minimal CLI agent for Task 1."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENV_FILE = Path(".env.agent.secret")
SYSTEM_PROMPT = "Answer the user's question briefly and accurately."


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
    load_env_file(ENV_FILE)

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


def ask_llm(question: str, settings: Settings) -> str:
    """Send the question to the configured LLM and return the text answer."""
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
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
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM response is missing choices[0].message.content") from exc

    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response content is empty")

    return content.strip()


def main() -> int:
    """CLI entrypoint."""
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Usage: uv run agent.py \"Your question\"", file=sys.stderr)
        return 1

    question = sys.argv[1].strip()

    try:
        settings = load_settings()
        answer = ask_llm(question, settings)
    except Exception as exc:
        print(f"agent.py error: {exc}", file=sys.stderr)
        return 1

    result = {"answer": answer, "tool_calls": []}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
