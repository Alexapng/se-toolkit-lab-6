# Task 1 Plan

## Goal

Build a minimal CLI agent in `agent.py` that:

- accepts the user question as the first command-line argument;
- loads LLM settings from environment variables, with `.env.agent.secret` as local convenience;
- calls an OpenAI-compatible chat completions endpoint;
- prints exactly one JSON object to stdout with `answer` and `tool_calls`.

## LLM provider and model

- Provider: Qwen Code API
- Model: `coder-model`
- Transport: standard-library `urllib.request` against `POST /chat/completions`

Using the standard library keeps Task 1 independent from virtualenv state and avoids adding another SDK.

## Proposed structure

Keep `agent.py` small and split it into a few helpers:

1. `load_env_file(path)` reads `.env.agent.secret` and fills missing environment variables.
2. `load_settings()` validates `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL`.
3. `ask_llm(question, settings)` sends the request and extracts the first text answer.
4. `main()` parses the CLI input, calls the helper functions, and prints the JSON result.

## Data flow

1. User runs `uv run agent.py "question"`.
2. `agent.py` reads config from the process environment and `.env.agent.secret`.
3. The script sends a chat-completions request to the configured LLM.
4. The script prints:

```json
{"answer": "...", "tool_calls": []}
```

## Error handling

- Missing CLI question: print an error to stderr and exit non-zero.
- Missing LLM config: print an error to stderr and exit non-zero.
- HTTP timeout / non-200 response / invalid LLM payload: print an error to stderr and exit non-zero.
- Stdout must stay JSON-only on success.

## Test plan

Create one regression test in a root-level `tests/` directory.

The test should:

1. run `agent.py` as a subprocess;
2. inject fake `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL` through the environment;
3. mock the HTTP call so the test does not depend on a real provider;
4. parse stdout as JSON;
5. assert that `answer` exists and `tool_calls` is present as a list.

## Documentation

Create `AGENT.md` with:

- the agent purpose and current scope;
- required environment variables;
- the chosen Qwen provider/model;
- how to run the CLI and tests.
