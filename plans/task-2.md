# Task 2 Plan

## Goal

Turn `agent.py` from a single LLM call into a documentation agent that can:

- inspect the `wiki/` directory with `list_files`;
- read wiki files with `read_file`;
- loop between the LLM and tool execution until it has enough evidence;
- return JSON with `answer`, `source`, and `tool_calls`.

## Tool strategy

Define two OpenAI-compatible tool schemas:

1. `list_files`
   - input: `path`
   - use: discover wiki files and directories before reading
2. `read_file`
   - input: `path`
   - use: read the relevant wiki file to find the answer and section anchor

The system prompt should tell the model to:

- start with `list_files` when it does not know which wiki file to inspect;
- use `read_file` to gather evidence;
- give a final JSON object with `answer` and `source`;
- include a wiki file path plus section anchor in `source`.

## Agentic loop

1. Send the user question, system prompt, and tool schemas to the LLM.
2. If the assistant returns `tool_calls`, execute every tool call from that turn.
3. Append one `tool` message per tool result.
4. Ask the LLM again with the updated conversation.
5. Stop when the assistant returns a final text response without tool calls.
6. Enforce a maximum of 10 executed tool calls total.

If the loop ends without a usable final JSON answer, return the best fallback answer and an empty or best-known `source`.

## Path security

Both tools must only access files inside the repository root.

Plan:

1. Resolve the requested relative path against the project root.
2. Reject absolute paths.
3. Reject any resolved path that escapes the project root.
4. Return an error string instead of raising unhandled exceptions.

This prevents `../` traversal and keeps tool access scoped to the project.

## Output shape

The CLI should print one JSON object to stdout:

```json
{
  "answer": "...",
  "source": "wiki/file.md#section-anchor",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."}
  ]
}
```

`tool_calls` records every executed tool call in order.

## Tests

Add two regression tests on top of the existing Task 1 test:

1. A merge-conflict question:
   - fake the LLM so it calls `list_files`, then `read_file`
   - assert `read_file` appears in `tool_calls`
   - assert the `source` points to the wiki file that actually contains the answer
2. A wiki-listing question:
   - fake the LLM so it calls `list_files`
   - assert `list_files` appears in `tool_calls`

The tests should still run `agent.py` as a subprocess and parse stdout JSON.

## Documentation

Update `AGENT.md` to explain:

- the two tools and their security rules;
- how the loop alternates between LLM and tools;
- the final-answer JSON contract;
- the system-prompt strategy for wiki questions.
