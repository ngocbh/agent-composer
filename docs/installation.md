# Installation

Agent Compose needs **Python 3.10+**.

```console
pip install agent-composer
```

The distribution name on PyPI is `agent-composer`; the import name is
`agent_composer`; the CLI is `ac`.

```console
ac --help
```

## Provider extras

The core (engine + `ac` CLI) installs with **no LLM SDK**. Each provider is an
optional extra — install the one(s) you actually use:

```console
pip install "agent-composer[anthropic]"   # Claude  (langchain-anthropic)
pip install "agent-composer[openai]"      # GPT     (langchain-openai)
pip install "agent-composer[google]"      # Gemini  (langchain-google-genai)
pip install "agent-composer[ollama]"      # local   (langchain-ollama)
pip install "agent-composer[all]"         # all four
```

Provider SDKs are imported **lazily** — only when a flow actually runs an AGENT
against that provider. Importing a provider you haven't installed raises a clear
`pip install agent-composer[...]` hint rather than a bare `ImportError`.

## Choosing a provider and model

The default provider and model are read from the environment, plus each
provider's own credential variable:

```console
export AGENT_COMPOSER_DEFAULT_PROVIDER=anthropic        # or openai / google / ollama
export AGENT_COMPOSER_DEFAULT_MODEL=claude-sonnet-4-5
export ANTHROPIC_API_KEY=...                            # the provider's own key var
```

A flow can also pin its own model per AGENT node; the environment defaults apply
only where a node leaves the model unset.

### Local models with Ollama

No API key is needed — point at a running Ollama endpoint:

```console
export AGENT_COMPOSER_DEFAULT_PROVIDER=ollama
export AGENT_COMPOSER_DEFAULT_MODEL=llama3.2:3b
export OLLAMA_BASE_URL=http://localhost:11434
ac run examples/hello.yaml --input name=Ada
```

## Development install

To work on Agent Compose itself, install it editable with the test extras:

```console
git clone https://github.com/ngocbh/agent-composer
cd agent-composer
pip install -e ".[all,dev]"
pytest
```

## Next

- [The `ac` CLI](cli.md) — run flows from the terminal.
- [Flow syntax](syntax.md) — the Compose-YAML reference.
