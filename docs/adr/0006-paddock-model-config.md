# 0006: A paddock ModelConfig on gemini-3.5-flash-lite

Status: accepted, 2026-11-15

## Context
The free Gemini tier allowed 20 requests per day for gemini-3.8-flash, and calls took about 2 minutes under load. One eval run needs about 50 model calls. paddock must use free tools only.

## Decision
`agents/paddock-model-config.yaml` points paddock agents at gemini-3.5-flash-lite (function calling supported). kagent's `default-model-config` stays unchanged.

## Consequences
- About 2 seconds per agent case instead of about 2 minutes.
- The free quota still runs out after about 7 cases a day, so the eval runner stops on HTTP 429 and resumes later. Results never count "not run" as blocked.
- A different model can refuse differently; the gateway and tool layers do not depend on the model.
