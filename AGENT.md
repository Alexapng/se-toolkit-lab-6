# Agent

## Purpose

`agent.py` is the first version of the lab agent. In Task 1 it does one job only:

- read a question from the command line;
- call an LLM through an OpenAI-compatible API;
- print one JSON object to stdout with `answer` and `tool_calls`.

There are no tools and no agent loop yet. `tool_calls` is always an empty array in this task.

## Provider

- Provider: Qwen Code API
- Model: `coder-model`
- Protocol: OpenAI-compatible `POST /chat/completions`
- HTTP client: Python standard library (`urllib.request`)

## Configuration

The agent uses these environment variables:

- `LLM_API_KEY`
- `LLM_API_BASE`
- `LLM_MODEL`

For local development, `agent.py` also reads `.env.agent.secret` with a simple `KEY=VALUE` parser and fills any missing variables from that file. Explicit environment variables take precedence, which keeps the script compatible with the autochecker.

## Flow

1. `main()` reads the first CLI argument as the question.
2. `load_settings()` validates the LLM configuration.
3. `ask_llm()` sends the request with `urllib.request`.
4. The script prints JSON to stdout:

```json
{"answer": "...", "tool_calls": []}
```

Any debug or error output goes to stderr.

## Run

```bash
uv run agent.py "What does REST stand for?"
```

## Test

```bash
uv run pytest tests/test_agent.py
```

Fallback if the project virtualenv is unavailable:

```bash
python -m unittest tests.test_agent
```
