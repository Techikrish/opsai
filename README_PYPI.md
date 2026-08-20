# opsai

**AI terminal command helper.** Ask in plain English, get the exact command —
no long explanations, no chatter.

```
$ opsai 'roll back the last deployment in kubernetes'
  > kubectl rollout undo deployment/my-app
    Reverts the deployment to its previous revision
```

Forgot that one kubectl, docker, git or systemd incantation? Working with
Kubernetes, EKS, or plain shell and can't recall the flag? Just ask `opsai`
in plain English and copy the answer straight into your terminal.

## Best use case: fully local with Ollama

`opsai` shines as a **100% local, private, offline-friendly** setup using
Ollama with a tiny model. A small **0.5B model is perfect** for this — command
completion is a simple task, so the small model answers fast on CPU with no
GPU, and your queries never leave your machine.

```bash
ollama pull qwen2.5:0.5b
opsai --base-url http://localhost:11434/v1 --model qwen2.5:0.5b 'get the pods in the kube-system namespace'
```

Want it as the default? Save it once:

```bash
opsai --config
# Base URL: http://localhost:11434/v1
# Model:    qwen2.5:0.5b
# API key:  (skip - not needed for local models)
```

Bigger local models (7B+) give even better answers on capable hardware — the
interface is identical.

## Install

```bash
pip install opsai
```

## Works with any OpenAI-compatible API

OpenAI, Groq, Ollama, LM Studio — anything speaking the
`/v1/chat/completions` protocol:

| Provider | Base URL | Example model |
|---|---|---|
| Ollama (local, recommended) | `http://localhost:11434/v1` | `qwen2.5:0.5b` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| LM Studio (local) | `http://localhost:1234/v1` | any loaded model |

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

Per-invocation overrides: `--base-url`, `--model`, `--api-key`.
Persistent (non-secret) settings live in `~/.config/opsai/config.json`.
Precedence: `--flag` > env var > config file > defaults.

## API keys (when not using local models)

`opsai --config` stores your key in the **OS keyring** (GNOME Keyring /
KWallet / Keychain / Credential Manager) — never written to disk. No keyring
backend? Use the environment:

```bash
export OPSAI_API_KEY="your-key"      # or OPENAI_API_KEY
export OPSAI_BASE_URL="https://api.groq.com/openai/v1"   # optional
export OPSAI_MODEL="llama-3.3-70b-versatile"             # optional
```

## Security

- **Never executes anything.** `opsai` only displays commands; there is no
  code path that runs them.
- **Sends only your query** plus a fixed system prompt — no shell history,
  no environment, no telemetry.
- **API key** lives in the OS keyring or an env var. Never logged, redacted
  from all error output, never sent on HTTP redirects.
- **HTTPS only** (except localhost for local model servers).
- **Danger flagging:** `rm -rf`, `sudo`, `mkfs`, `dd`, `curl | sh`, etc. are
  printed with a warning banner.
- **Terminal escape sanitization:** model output is scrubbed of ANSI/control
  characters before display.

## License

MIT
