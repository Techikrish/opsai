# opsai

AI terminal command helper. Ask in plain English, get the exact command.

```
$ opsai 'roll back the last deployment in kubernetes'
  > kubectl rollout undo deployment/my-app
    Reverts the deployment to its previous revision
    Details
      Use `kubectl rollout history deployment/my-app` to list all
      revisions, then `undo --to-revision=<n>` to pick a specific one.
```

## Why opsai?

There are a lot of products that do this — shell plugins, AI chat wrappers,
fancy frameworks with agents, toolchains and workflows. Most are either
heavyweight, require cloud accounts, or try to be your whole terminal
companion.

I wanted something different: a **simple, genuine, easy-to-use tool**. One
binary, one question, one command back. No agents, no autocomplete overlays,
no telemetry — just "what's the command?" and an answer you can paste. So I
built it. opsai is deliberately boring: it prints a command, that's it.

## Best use case: fully local with Ollama

The sweet spot is a **100% local, private setup** with Ollama. **For good,
accurate results use at least a 7B model** — `qwen2.5:7b` is a great default
that fits in ~4.7 GB and runs on most machines. A 0.5B model technically
works but is prone to wrong or hallucinated flags, so treat it as a
resource-constrained fallback only. Either way, **your queries never leave
your machine**.

```bash
ollama pull qwen2.5:7b
opsai --base-url http://localhost:11434/v1 --model qwen2.5:7b 'get the pods in the kube-system namespace'
```

Make it the default:

```bash
opsai --config
# Base URL: http://localhost:11434/v1
# Model:    qwen2.5:7b
# API key:  (not asked - local servers need no key)
```

## Install

```bash
pip install opsai
```

## Setup

```bash
opsai --config        # interactive: base URL, model, API key
```

The API key is stored in your **OS keyring** (GNOME Keyring / KWallet /
Keychain / Credential Manager) — never written to disk. **Local servers
(Ollama/LM Studio) need no API key at all** — opsai detects a localhost base
URL and skips the key requirement. If no keyring backend
is available, use an environment variable instead:

```bash
export OPSAI_API_KEY="your-key"      # or OPENAI_API_KEY
export OPSAI_BASE_URL="https://api.groq.com/openai/v1"   # optional
export OPSAI_MODEL="llama-3.3-70b-versatile"             # optional
```

Non-secret settings live in `~/.config/opsai/config.json` (mode 0600).
Precedence: `--flag` > env var > config file > defaults.

## Usage

```bash
opsai 'reboot into bios'              # one-shot
opsai --chat                          # interactive session with memory
opsai --model gpt-4o-mini 'list pods' # per-invocation override
opsai 'kubectl restart deployment'    # k8s, git, docker, anything
```

### More examples

| You ask | You get |
|---|---|
| `opsai 'restart the nginx deployment in kubernetes'` | `kubectl rollout restart deployment/nginx` |
| `opsai 'roll back the last deployment'` | `kubectl rollout undo deployment/my-app` |
| `opsai 'see all pods in every namespace'` | `kubectl get pods --all-namespaces` |
| `opsai 'ssh into a pod for debugging'` | `kubectl exec -it pod/my-pod -- /bin/sh` |
| `opsai 'port forward a pod to my localhost 8080'` | `kubectl port-forward pod/my-pod 8080:80` |
| `opsai 'restart the eks node group'` | `aws eks update-nodegroup-config --cluster-name my-cluster --nodegroup-name my-ng --scaling-config minSize=1,maxSize=1,desiredSize=1` |
| `opsai 'recreate a docker container from scratch'` | `docker-compose up -d --force-recreate` |
| `opsai 'undo the last git commit but keep the changes'` | `git reset --soft HEAD~1` |
| `opsai 'find what changed in the last commit'` | `git show --stat HEAD` |
| `opsai 'restart the ssh service'` | `sudo systemctl restart ssh` |

> Only your question is sent to the model — the table above is what the
> answer looks like. Always review the command before running it.

### Provider examples

| Provider | Base URL | Example model |
|---|---|---|
| Ollama (local, recommended) | `http://localhost:11434/v1` | `qwen2.5:7b` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| LM Studio (local) | `http://localhost:1234/v1` | any loaded model |

Works with any **OpenAI-compatible** API: OpenAI, Groq, Ollama, LM Studio, etc.

## Security

- **Never executes anything.** `opsai` only displays commands; there is no
  code path that runs them.
- **Sends only your query** plus a fixed system prompt — no shell history,
  no environment, no telemetry.
- **API key** lives in the OS keyring or an env var. It is never logged and
  is redacted from any error output.
- **HTTPS only** (except localhost for local model servers).
- **Danger flagging:** commands involving `rm -rf`, `sudo`, `mkfs`, `dd`,
  `curl | sh`, etc. are printed with a warning banner.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

