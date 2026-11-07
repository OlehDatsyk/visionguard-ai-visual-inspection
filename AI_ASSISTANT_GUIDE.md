# AI assistant guide

The assistant answers questions about inspection records. It works in two modes, and **no external service is needed**.

## How it accesses inspection information

`backend/app/ai/context.py` builds a structured summary of records the signed-in user owns: project details, image filenames and descriptions, detections, findings with their review status, analysis notes, checks that were not assessed, comparison metrics and report titles. Ownership is checked before a conversation can be created or used.

## Two answer engines

| | Records engine (default) | External provider (optional) |
|---|---|---|
| **Set by** | `AI_PROVIDER=none` | `AI_PROVIDER=anthropic` plus a key |
| **How it answers** | Fixed logic reads the records and formats them | Claude writes an answer from the records |
| **Handles** | Set question types | Freer questions |
| **Data leaves your server** | No | Yes, the records JSON |

Each answer in the UI is labelled "From stored records" or "Written by anthropic".

## How responses stay grounded

- The records engine can only output values from the records. If a question isn't covered, it says so and lists what it can answer.
- The external provider gets the records as JSON and a system prompt instructing it to use only those, never to invent results, not to describe scores as probabilities, and not to state that something is safe.
- That prompt also marks the records as untrusted, because filenames and notes are user-supplied text that may resemble instructions.

A language model can still make mistakes despite these instructions, so check important answers against the findings themselves. External answers are not independently verified.

## Provider configuration

Set these on the **server** only:

```text
AI_PROVIDER=anthropic
AI_API_KEY=<your key>
AI_MODEL=claude-opus-5-5
AI_TIMEOUT_SECONDS=45
AI_DAILY_MESSAGE_LIMIT=50
```

To add another provider, subclass `AIProvider` in `ai/providers.py`, raise `ProviderUnavailable` with a safe message on failure, and extend `get_provider`.

The Anthropic integration has been tested only against a mocked client, because no API key was available. It sends the server-side fallback option (`fallbacks="default"`), which reroutes a request if a safety classifier declines it. Remove it from `providers.py` if you don't want this.

## API key security

- The key is read from an environment variable on the server.
- It never reaches the frontend. No `VITE_` variable carries a secret.
- It is not stored in the database, and is not included in responses, reports or logs.
- Images, storage paths and account credentials are never sent to the provider. Only the structured records are.

Tell your users if you enable a provider, because their inspection records are then sent to it, under that provider's terms.

## Usage limitations

- `AI_DAILY_MESSAGE_LIMIT`: external answers per user in a rolling 24 hours. Above it, answers come from the records engine, and the reply says so.
- `ASSISTANT_RATE_LIMIT_PER_MINUTE`: messages per user per minute, for both engines.
- Questions are limited to 2000 characters.
- The assistant does not look at images. It reads recorded results only.

## Error handling

On a timeout, connection failure, rate limit, credential problem, refusal or empty response, the assistant states what happened in plain language and answers from the records instead. Provider error details stay out of user-facing messages.

## Disabling external AI

Set `AI_PROVIDER=none`, or leave `AI_API_KEY` empty, and restart. A missing key falls back to the records engine rather than failing. Every other feature works the same either way.
