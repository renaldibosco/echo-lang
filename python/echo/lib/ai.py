"""AI helpers. Uses YOUR key, stored only on your own device. Nothing is sent until an ai...() function runs.

Setup once:   ai_setup("claude", "YOUR-KEY")      (or "gemini", "openai")
Or set environment variables ECHO_AI_PROVIDER, ECHO_AI_KEY, ECHO_AI_MODEL, ECHO_AI_URL.
"""
import json
import os
import urllib.error
import urllib.request

from ..errors import EchoRuntimeError
from ..values import show
from . import builtin

A = "ai"

DEFAULT_MODELS = {"claude": "claude-haiku-5-5", "gemini": "gemini-2.5-flash", "openai": "gpt-4o-mini"}
ALIASES = {"anthropic": "claude", "google": "gemini", "chatgpt": "openai", "openai-compatible": "openai"}


def _config_path():
    home = os.environ.get("ECHO_HOME") or os.path.join(os.path.expanduser("~"), ".echo")
    return os.path.join(home, "config.json")


def _config():
    cfg = {}
    try:
        with open(_config_path(), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass
    for key, env in (("provider", "ECHO_AI_PROVIDER"), ("key", "ECHO_AI_KEY"), ("model", "ECHO_AI_MODEL"),
                     ("url", "ECHO_AI_URL")):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    if cfg.get("provider"):
        cfg["provider"] = ALIASES.get(cfg["provider"].lower(), cfg["provider"].lower())
    return cfg


@builtin("ai_setup", A, "ai_setup(provider, key, model=nothing, url=nothing) saves your AI key on this device")
def _ai_setup(provider, key, model=None, url=None):
    provider = ALIASES.get(show(provider).lower(), show(provider).lower())
    if provider not in DEFAULT_MODELS:
        raise EchoRuntimeError("Unknown AI provider '%s'." % provider, hint="Use 'claude', 'gemini' or 'openai'.")
    cfg = {"provider": provider, "key": show(key)}
    if model:
        cfg["model"] = show(model)
    if url:
        cfg["url"] = show(url)
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return "AI ready: %s (%s). Key saved only on this device." % (provider, cfg.get("model", DEFAULT_MODELS[provider]))


@builtin("ai_status", A, "ai_status() shows which AI is set up (never shows the key)")
def _ai_status():
    cfg = _config()
    if not cfg.get("key"):
        return "No AI key set. Run: ai_setup(\"claude\", \"YOUR-KEY\")"
    p = cfg.get("provider", "claude")
    return "AI: %s, model %s" % (p, cfg.get("model", DEFAULT_MODELS.get(p, "?")))


def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code in (401, 403):
            raise EchoRuntimeError("The AI service rejected the key (%d)." % e.code, hint="Check it with ai_setup().")
        raise EchoRuntimeError("AI service error %d: %s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise EchoRuntimeError("Can't reach the AI service (%s). Are you online?" % e.reason)


def ask_ai(prompt, system=None):
    cfg = _config()
    key = cfg.get("key")
    if not key:
        raise EchoRuntimeError("No AI key set.", hint='Run once: ai_setup("claude", "YOUR-KEY")  (or gemini / openai)')
    provider = cfg.get("provider", "claude")
    model = cfg.get("model") or DEFAULT_MODELS.get(provider)
    prompt = show(prompt)
    if provider == "claude":
        body = {"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        data = _post(cfg.get("url") or "https://api.anthropic.com/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, body)
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()
    if provider == "gemini":
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = (cfg.get("url") or "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model)
        data = _post(url, {"content-type": "application/json", "x-goog-api-key": key}, body)
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
        except (KeyError, IndexError):
            raise EchoRuntimeError("The AI gave no answer.")
    if provider == "openai":
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        data = _post(cfg.get("url") or "https://api.openai.com/v1/chat/completions",
                     {"authorization": "Bearer " + key, "content-type": "application/json"},
                     {"model": model, "messages": msgs})
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            raise EchoRuntimeError("The AI gave no answer.")
    raise EchoRuntimeError("Unknown AI provider '%s'." % provider)


ECHO_GUIDE = """You write code in Echo, a simple English-like programming language for biology.
Rules: one statement per line; blocks close with `end`. Comments start with #.
set x to 5 | x = 5 | x += 1 | say "GC is {gc(seq)}%" | ask "Name?" into name
if a > 1 then ... else if ... else ... end | repeat 3 times ... end | while c ... end
for each item in list ... end | for i from 1 to 10 step 2 ... end | break | continue
define name(a, b = 2) ... return a + b end | fn(x) -> x * 2 | try ... catch err ... end | fail "msg"
record Gene(name, seq) | lists [1, 2] (index from 0) | maps {name: "gfp", length: 720} m.name
logic: and or not xor nand nor xnor | `x in list` | text + number joins as text
bio: dna gc at base_counts complement reverse_complement transcribe translate find_orfs find_motif
tm primer_check primer_info design_primers pcr_program restriction_sites digest align protein_mass
isoelectric_point gravy protein_info parse_fasta read_fasta to_fasta gel dilute copy_number
other: length upper lower split join replace sort map filter range(1, 5)=[1..5] mean stdev
linear_fit train predict sha256 caesar truth_table to_binary.
Reply with only Echo code, no explanation, no markdown fences."""


@builtin("ai", A, "ai(question) asks your AI and returns its answer as text")
def ai(prompt, system=None):
    return ask_ai(prompt, show(system) if system else None)


@builtin("ai_code", A, "ai_code(task) asks the AI to write Echo code for a task (returns the code as text)")
def _ai_code(task):
    out = ask_ai("Write Echo code for this task:\n" + show(task), ECHO_GUIDE)
    if out.startswith("```"):
        out = out.split("\n", 1)[1] if "\n" in out else ""
        out = out.rsplit("```", 1)[0]
    return out.strip()


@builtin("ai_explain", A, "ai_explain(text) explains code, a sequence or a result in simple words")
def _ai_explain(text):
    return ask_ai("Explain this simply for a biology student:\n\n" + show(text),
                  "You are a friendly biology and programming teacher. Be short and clear.")
