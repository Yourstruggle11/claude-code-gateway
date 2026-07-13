# Adding or changing a provider

LiteLLM owns provider translation. The launcher only needs a public model alias, so most
providers require three changes:

1. Add the provider credential to `.env` (or inject it through a secret manager).
2. Add a `model_list` entry to `config.yaml` using LiteLLM's current provider syntax.
3. Set `GATEWAY_MODEL` and, optionally, `GATEWAY_SMALL_MODEL` to the new aliases.

Run `claude-gateway doctor`, then test in a non-sensitive project. Adding a provider does not
require editing Python.

These commands assume `.venv` is active (`source .venv/bin/activate` on macOS/Linux,
`source .venv/Scripts/activate` in Windows Git Bash, or `.venv\Scripts\Activate.ps1` in
PowerShell).

## Example: add OpenRouter alongside Gemini

Add the key and selected alias to `.env`:

```dotenv
OPENROUTER_API_KEY=replace-with-your-key
GATEWAY_MODEL=openrouter-coding
```

Append a route to `model_list` in `config.yaml`:

```yaml
  - model_name: openrouter-coding
    litellm_params:
      model: openrouter/<publisher>/<model-id>
      api_key: os.environ/OPENROUTER_API_KEY
```

Replace the angle-bracket values with an actual current model ID. Keeping a stable local alias
means provider model IDs can change without changing Claude Code launch commands.

## Included examples

Files in `examples/providers/` are standalone starting points. Copy one to
`config.local.yaml`, replace model/deployment placeholders, add its environment variables, and
set `GATEWAY_CONFIG=config.local.yaml`.

| Provider | Credential approach | Notes |
| --- | --- | --- |
| Gemini API | API key | Easiest default; create the key in Google AI Studio |
| OpenAI | API key | Choose a model that supports the tools/features you need |
| OpenRouter | API key | Model ID includes publisher and model |
| Ollama | None by default | Local daemon must already be running |
| Anthropic | API key | Routes through LiteLLM rather than directly |
| Vertex AI | Application Default Credentials | Requires project and region configuration |
| Azure OpenAI | API key or supported Azure auth | Uses deployment name, endpoint, and API version |

## Compatibility checklist

Before documenting a provider as working, verify:

- a basic streamed text response;
- tool/function calling;
- multi-turn context;
- Claude Code's main and background model selections;
- expected handling of system prompts and images;
- cancellation with Ctrl+C;
- rate-limit and authentication errors are understandable;
- no credential, prompt, or response is written to logs.

Cross-provider translation is not semantic emulation. `drop_params: true` prevents unsupported
fields from breaking every request, but it cannot give a model capabilities that its API lacks.

## When to split configurations

Keep one `config.yaml` when routes share the same trust boundary and operators. Use separate
configuration files or gateway processes when providers have different users, retention rules,
network exposure, or production credentials. Simplicity is valuable only while the security and
operational boundary remains the same.
