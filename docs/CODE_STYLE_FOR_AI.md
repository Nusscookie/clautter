# Writing readable code in Clutter — a guide for AI instances

> Read this before adding a feature or a dependency. It is the *why* behind
> the conventions in `CLAUDE.md`. `CLAUDE.md` says **what** the rules are;
> this file teaches you how to **not make the codebase worse** as it grows.

The plugin grows one feature at a time. Each feature is small, but if every
feature copies the last one's plumbing, the codebase rots into N near-identical
copies of the same thing. The single goal of this guide: **a new feature should
add code, not duplicate it.**

If you remember one sentence: **when a single logical change forces you to edit
many files, that is a bug in the code's structure, not a fact of life — fix the
structure first.**

---

## 1. Before you write code, search for the pattern

This repo already centralizes its shared things. Before writing a literal, a
constant, or a "call X" function, grep for it — it probably already exists.

| You're about to write… | It already lives in… |
|---|---|
| a hex color, a `~/.clutter` path, a track name (`"Music"`), a settings key | `src/constants.py` (`COLORS`, `PATHS`, `TRACKS`, `SETTINGS_KEYS`) |
| an HTTP call to a cloud LLM | `src/utils/llm_providers.py` (`call_llm`) |
| a JSON-array parse of an LLM reply | `src/utils/llm_providers.py` (`extract_json_array`) |
| a settings read/write | `src/settings/manager.py` |
| a log line | `src/utils/logger.py` (`log.info/warn/error`, never `print`) |

A new literal or call that matches an existing one is a copy. **Reuse it.**

---

## 2. One mechanism per job

If a router/registry/dispatcher already exists for a job, do not *also* inline
an `if/elif` chain that does the same routing. Pick one.

This is not hypothetical — it's the exact bug this guide was written after.
`llm_director.py` had **both** an inline `if chosen == "OpenAI": … elif …`
chain **and** a generic `_dispatch_call()` router, in the same file, doing the
same dispatch. Two ways to do one thing means the next editor has to guess
which one to update, and they'll update the wrong one (or only one).

---

## 3. "Add one thing" should be one edit

When adding a provider / preset / tab / bucket forces you to touch many files
or paste a block into several places, that is the signal to introduce a
**table or registry**, not another copy.

Litmus test: *"To add the next one of these, how many places do I edit?"*
If the answer is more than one or two, restructure so it becomes one.

**Worked example — the change that prompted this guide.** Adding the Anthropic
provider used to mean editing **6 files** and pasting the same HTTP boilerplate
into **3** of them. The five providers (`openai/gemini/minimax/nvidia/
anthropic`) were each written out **three times** — once per call site
(B-roll director, reranker, mood analyzer) — ~15 near-identical functions,
with the provider URLs and the model-name lookup duplicated alongside.

The fix was a **provider registry**: one `ProviderSpec` per provider (its key
setting, model setting, default model, request builder, response extractor) in
`src/utils/llm_providers.py`, and one `call_llm(provider, prompt, settings, …)`
that every call site uses. ~15 functions collapsed to 1. Adding the next
provider is now: one `_SPECS` entry + one settings field + one UI row.

The shape to reach for when you see this smell:

```python
@dataclass(frozen=True)
class ThingSpec:
    name: str
    # …the fields that DIFFER between things…
    build: Callable[...]     # the behavior that differs

_SPECS: dict[str, ThingSpec] = { "A": ThingSpec(...), "B": ThingSpec(...) }

def do_thing(name, ...):          # one function, all things
    spec = _SPECS[name]
    ...
```

Put in the spec only what *differs*. Everything shared lives once in the
function. (E.g. OpenAI/Minimax/NVIDIA share one request shape — they share a
builder; only the URL differs.)

---

## 4. Define constants once

URLs, API endpoints, keys, track names, hex colors, magic numbers — define them
in exactly one place. If you find the same string in two files, that's a future
bug: someone updates one and not the other. (This refactor found `_OPENAI_URL`
defined in three files and a stale `api.minimax.chat` URL in one of them while
the other two used `api.minimax.io`.)

---

## 5. No import hacks

Imports go at the top of the file, or are lazy-imported inside the worker
function (per `CLAUDE.md`, to keep tab startup snappy). Never jam an `import` at
the **bottom** of a file with `# noqa` to paper over module-level code that
references it. That mood_analyzer had `import requests` at line 327, after the
functions that used it — a flag that the code was structured wrong. If you feel
the urge to add a `noqa`, stop and fix the structure instead.

---

## 6. Match the surrounding style

From `CLAUDE.md`, non-negotiable in this repo:

- `from __future__ import annotations` at the top.
- PEP 604 unions (`X | None`, not `Optional[X]`). Type hints on every public
  function. `Any` only at the CTk boundary or for opaque Resolve objects.
- A module docstring on every file.
- Don't nest `def`s more than two deep. Extract a helper at ~50+ lines.
- Reference `COLORS`/`PATHS`/`TRACKS`/`SETTINGS_KEYS` — don't inline the value.

Code should read like the file it lives in. Match the neighbors' naming,
comment density, and idioms.

---

## 7. When refactoring, keep behavior identical — and verify

A cleanup that changes outputs is not a cleanup, it's a risk. Preserve the
observable behavior (same providers, same prompts, same params per call site)
and prove it:

- `py -3.12 -c "import <the modules you touched>; print('ok')"` — no import-time breakage.
- Grep for the names you deleted — they should be **gone**, with no dangling references.
- Smoke the call sites with a fake `settings` + a monkeypatched network call, and confirm each still parses a canned reply.
- `py -3.12 gui.py` still opens (disconnected state is fine without Resolve).

---

## TL;DR checklist before you commit a feature

- [ ] Did I grep for an existing constant / helper before writing a new one?
- [ ] Is there exactly **one** mechanism for this job (no duplicate router)?
- [ ] To add the *next* one of these, do I edit only one or two places?
- [ ] Are all my constants defined once?
- [ ] Imports at top or lazy-in-worker — no bottom-of-file `noqa` hack?
- [ ] Does it match the file's existing style?
- [ ] If I refactored, is behavior identical and verified?
