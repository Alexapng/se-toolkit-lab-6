# Agent

## Purpose

`agent.py` is now a documentation agent. It answers repository questions by calling an LLM and giving the LLM two tools:

- `list_files` to discover files and directories
- `read_file` to inspect file contents

The Task 2 goal is wiki-based question answering. The agent should look through `wiki/`, read the relevant documentation, and then answer with evidence from the repository instead of relying on prior knowledge.

## Provider

- Provider: Qwen Code API
- Model: `coder-model`
- Protocol: OpenAI-compatible `POST /chat/completions`
- HTTP client: Python standard library (`urllib.request`)

## Configuration

The agent reads these environment variables:

- `LLM_API_KEY`
- `LLM_API_BASE`
- `LLM_MODEL`

For local development it also reads `.env.agent.secret` and fills any missing values from that file. Explicit environment variables still win, which keeps the agent compatible with the autochecker.

## Tools

### `list_files`

- input: repository-relative directory path
- output: newline-separated file and directory listing
- main use: discover relevant wiki files before reading them

### `read_file`

- input: repository-relative file path
- output: file contents as UTF-8 text, or an error string
- main use: read the wiki file that contains the answer

## Tool security

Both tools resolve the requested path against the project root. They reject:

- absolute paths
- `..` traversal that would escape the repository

If a path is invalid, the tool returns an error string instead of crashing the agent.

## Agentic loop

1. `main()` reads the CLI question.
2. `run_agent()` starts a conversation with a system prompt, the user question, and the tool schemas.
3. If the LLM returns `tool_calls`, the agent executes all tool calls from that assistant turn.
4. Each tool result is appended back to the conversation as a `tool` message.
5. The loop repeats until the LLM returns a final message without tool calls.
6. The agent enforces a maximum of 10 executed tool calls.

The final assistant message is expected to be JSON with:

```json
{"answer": "...", "source": "wiki/file.md#section-anchor"}
```

`agent.py` parses that JSON and then prints the CLI result:

```json
{"answer": "...", "source": "...", "tool_calls": [...]}
```

## Prompt strategy

The system prompt tells the model to inspect the repository wiki before answering, prefer `list_files` for discovery, use `read_file` for evidence, and return a repository-relative wiki source with a section anchor. This keeps answers grounded in the project documentation and makes the output easy to validate in tests.

## Run

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

## Test

```bash
uv run pytest tests/test_agent.py
```

Fallback if the project virtualenv is unavailable:

```bash
python -m unittest tests.test_agent
```
