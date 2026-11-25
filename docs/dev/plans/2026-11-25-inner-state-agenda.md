# Inner State, Agenda & Layered Memory — Implementation Plan

> For agentic workers: execute task by task, test first (`superpowers-test-driven-development`),
> verify before claiming done (`superpowers-verification-before-completion`). Keep diffs minimal
> (ponytail). Checkboxes track progress. One commit per task, only when the user asks to commit.

**Goal:** Chassie decides what to bring up from her own agenda, learns when initiatives land,
and never loses a memory she chose to keep.

**Spec:** the 2026-11-25 discussion, summarized in "Decisions" below. Background analysis of
AIRI / OpenAmika / Neuro-sama lives in that conversation; this file is the source of truth.

**Tech stack:** Python 3.12, asyncio, pytest (`.venv/bin/python -m pytest`), JSON/JSONL files under
`.chassie/` next to `reminders.json`. No new dependencies.

## Decisions (user, 2026-11-25)

- Light fiction: her own "life" is digital/mental only (reading, music, watching along, sleepy);
  never physical-world claims. Optional: a real article read via Hermes web tools.
- Mood may go low: murung and ngambek allowed. Sulk is caused by how she is treated in a
  conversation, never by the owner being away, busy or closing the app. Sulk drops at once when
  the owner is sad or needs real help; it changes style, never refuses help; decays in 15–30 min;
  not carried into the next session as a mood.
- Memory consolidation is automatic, no approval. Never hard-delete (supersede), log every change
  to the vault, back up before a batch, never touch notes the owner edited, respect tombstones,
  NOOP when unsure.
- Rejected: spoken filler/reflex on every turn (sounded like a "hmm…" tic), full GraphRAG,
  multimodal RAG, agentic RAG on every turn.

## Global constraints

- VOICEVOX only; one Normal style (memory: single-normal-voice). Output protocol is the NDJSON in
  `brain/bilingual.py`; every new model line is a JSON object parsed there, never spoken.
- Capture now, process later: anything that must survive the app closing is written
  synchronously without an LLM. LLM processing happens on the next start or while idle.
- Owner-only: agenda, signals and memory writes happen only in personal scope.
- 4 GB VRAM / 8 GB RAM laptop: no new models in phases 0–1.

## Roadmap

| Phase | Content | Status |
|---|---|---|
| 0 | Save memory lines as soon as parsed; owner name instead of hardcoded `Artdi:` | done 2026-11-25 |
| 1 | Agenda store + model agenda lines + agenda in context + agenda initiatives + learned timing | done 2026-11-25 |
| 2 | Inner state: mood (valence/energy, decay to persona baseline), sulk, closeness → emotion hints, prosody, initiative thresholds | done 2026-11-25 |
| 3 | Layered memory: fact metadata, ADD/UPDATE/SUPERSEDE/NOOP consolidation, core profile, wikilink entity hop, recency×importance×relevance scoring | later plan |
| 4 | Light fiction: daily activity (+ optional real article → `share` agenda item) | later plan |
| 5 | Adaptive endpointing + instant non-verbal face reaction | later plan |

---

## Phase 0

### Task 0.1: Memory lines are saved the moment they are parsed

Problem: `_route` (`brain/orchestrator.py:432`) buffers `memory` lines in `_turn_memories`;
`_save_turn_memories` runs only after a completed turn (`:609`). Barge-in, Stop, an error or
closing the app drops a memory Chassie already decided to keep.

**Files:** modify `brain/orchestrator.py` (`_route`, `_produce_speech`, `_run_turn`,
`_save_turn_memories`); test `tests/test_automatic_memory.py`.

**Interface:** `async def _save_memory(self, content: str, extras: dict) -> None` — owner scope
re-checked at save time; at most 3 per turn (counter reset in `_produce_speech`); same
`self._vault.call('remember', content, session='chassie', title=..., category=...)` as today.
`_save_turn_memories` and `_turn_memories` are deleted.

- [x] Test: owner app, `_automatic_memory=True`, `_vault=Mock(call=Mock(return_value={'saved':True}))`,
  stream yields a memory line then raises `RuntimeError` → after `_run_turn`, `vault.call` was
  called with `'remember'` and the fact. Also: a guest scope → not called.
- [x] Run, see it fail; implement; run the file and the full suite.

### Task 0.2: Session recap uses the owner's name

Problem: `_summarize` (`brain/orchestrator.py:781`) labels user lines `'Artdi: '`.

**Interface:** `def _owner_name(self) -> str` — owner profile name, else `'Owner'`; reused by
`_vault_recall` (which computes the same thing inline today).

- [x] Test: `make_owner(app)` (profile "Owner") + summarize → the text passed to
  `complete_once` starts its first line with `Owner: `, and contains no `Artdi`.
- [x] Fail → implement → pass → full suite.

---

## Phase 1

### Task 1.1: Agenda store and signal log (`brain/agenda.py`, new)

**Interfaces (produced):**
```python
KINDS = ('follow_up', 'promise', 'curiosity', 'share')
MAX_ATTEMPTS = 2

class AgendaStore(ReminderStore):          # reuses its atomic JSON _read/_write
    def add(self, text, kind, *, source, earliest=None, expires=None, priority=.5) -> dict
        # text 3-200 chars, kind in KINDS; same text (casefold) still open → returns it.
        # item: {id, text, kind, source, earliest, expires, priority, attempts:0, status:'open'}
        # expires default: +14 days. earliest None = now.
    def open(self, now=None) -> list[dict]  # status open, earliest<=now, not expired; drops expired
    def best(self, now=None) -> dict | None # max by priority, then oldest
    def raised(self, identifier)            # attempts+1; status 'dropped' at MAX_ATTEMPTS
    def resolve(self, identifier)           # status 'done'

class SignalLog:                           # .chassie/signals.jsonl, append-only, no LLM
    def __init__(self, path)
    def add(self, event: str, reason: str, now=None)   # event in ('raised','answered')
    def acceptance(self, reason, hour, now=None) -> float
        # (answered+1)/(raised+2) for this reason within ±2 h of `hour`, last 30 days. Default .5.
```
- [x] Tests (`tests/test_agenda.py`): add/dedupe/validation; `open` filters earliest/expired and
  prunes expired; `raised` twice → dropped; `best` picks priority; acceptance: no data → .5,
  3 raised/3 answered at 21h → .8, other hours/reasons ignored, >30 days ignored.

### Task 1.2: Model writes and closes agenda items

Model lines (owner scope only, never spoken), parsed in `BilingualChunker._parse`:
- `{"agenda":"<short text in display language>","kind":"promise|curiosity|follow_up","when":"YYYY-MM-DDTHH:MM"}`
  (`when` optional) → `('agenda', text, kind, when)`.
- `{"agenda_done":"<id>"}` → `('agenda_done', id)`.

Prompt (`bilingual_prompt`): short "Agenda" paragraph — write an agenda line for her own promises
("nanti aku cariin"), things she is curious to ask later, and plans worth following up when no
reminder fits; write `agenda_done` when an item listed in context `agenda` has been talked about.

Orchestrator `_route`: `agenda` → `self._agenda.add(..., source='chat', earliest=parse_time(when) if when)`;
invalid time → log and ignore. `agenda_done` → `self._agenda.resolve(id)`.
Diary: `_reflection_loop` adds each written open loop as `follow_up` (source `diary:<day>`,
expires +7 days).

- [x] Tests: chunker parses/validates both lines (bad kind, short text, extra keys → ValueError);
  a turn with an agenda line in personal scope stores it, in guest scope does not;
  `agenda_done` resolves; reflection loop with stubbed `complete_once` adds loops to the agenda.

### Task 1.3: Agenda in the turn context

`_context_text` personal scope: `payload['agenda']=[{'id','text','kind'} for top 2 open items]`
with a note: things you may bring up if they fit naturally; never list them; write
`agenda_done` once talked about. Budget loop drops `agenda` before `memories`.

- [x] Test: owner with two open items → context has both with ids; guest scope → no `agenda`.

### Task 1.4: Agenda initiatives and learned timing

`decide()` gains keyword args `agenda_item=None, acceptance=lambda reason: .5`:
- Learned timing: quiet threshold for `quiet`, `agenda`, `app` is
  `base * clamp(.5 / acceptance(reason), .5, 4)` (well-received reasons come sooner, ignored ones later).
- New reason `agenda` before the generic `quiet` fallback: open `agenda_item` and
  `quiet >= MODES[mode]['quiet'] * factor('agenda') / 2` → `('agenda', item, set(screen))`.
- Sensor reasons (look, opened, returned, screen, noticed, late_night) are unchanged.

`initiative_text('agenda', item, now)`: "Something on your mind to bring up: "<text>" (<kind>).
Bring it up naturally in your own words, as a question or a short remark; skip if it no longer fits."
`_start_initiative`: for `agenda` → `self._agenda.raised(item['id'])` and the queue item carries
`'reason':'agenda'` as today's items do.
Signals are logged only for initiatives that were actually spoken: in `_run_turn`, after a
non-skipped initiative turn (reason not `look`/`reminder`/`opened`) → `self._signals.add('raised', reason)`
and `self._initiative.pending_signal=(reason, time.monotonic())`.
`_note_activity(user=True)` within 10 min of `pending_signal` → `signals.add('answered', reason)`,
then clear it. Closing the app or ignoring her simply leaves `raised` without `answered`.

- [x] Tests (`tests/test_initiative.py`): agenda item fires at half the quiet time and before
  `quiet`; low acceptance delays `quiet`, high acceptance brings it sooner (bounded);
  existing tests keep passing unchanged; `_start_initiative('agenda', item, set())` increments
  attempts; user activity after an initiative logs `answered`; a skipped initiative logs no `raised`.

### Wiring

`Orchestrator.__init__`: `self._agenda=AgendaStore(selection_path.with_name('agenda.json'))`,
`self._signals=SignalLog(selection_path.with_name('signals.jsonl'))`.
`_initiative_loop`: `agenda_item=self._agenda.best() if self._owner_alone() else None`,
`acceptance=lambda r: self._signals.acceptance(r, datetime.datetime.now().hour)`.

### Done when

- Full suite green (`.venv/bin/python -m pytest -q`).
- Skipped on purpose (add when needed): agenda UI panel; backfilling open loops from diaries
  written before this change; a "closed soon after initiative" signal (closing already counts as
  not answered).

---

## Phase 2: Inner state (`brain/mood.py`, new)

State file `.chassie/inner-state.json` (atomic write on every change, no LLM):
`{valence -1..1, energy 0..1, sulk: null|{level, cause, since}, closeness 0..1, last_day, updated}`.

**Dynamics (wall clock, so closing the app lets her settle):**
- valence decays to baseline .3 (half-life 20 min); energy decays to a clock target
  (00–05h .25, 06–08h .45, 22–23h .4, else .6; half-life 30 min).
- `react(emotion)`: each spoken sentence nudges valence/energy a little (table `REACT`).
- `feel(feeling, because)` from the model line `{"feel":"sulky|down|better","because":"..."}`:
  sulky → sulk level 1 and valence −.25; down → valence −.35; better → sulk cleared, valence +.25.
- sulk level halves every 10 min; gone below .2 or after 30 min; **cleared on load** (never carried
  into the next session).
- `met(now)`: first owner turn of a day → closeness += (1 − closeness) × .03 (starts at .1).

**Effects:**
- Context (every scope): `inner_state` = mood/energy/closeness in words, plus `sulking.about`.
  Rules live in the prompt: let feelings colour word choice and emotions, never announce them;
  sulk only about how she is treated in this conversation, never about the owner being away, busy
  or closing the app; while sulking be pouty and shorter but never refuse help; write
  `{"feel":"better"}` at once if they are sad, need real help, apologize or cheer her up.
- Prosody: `ProsodyPlanner.mood = (pitch offset, intonation ×, speed ×)` from `Mood.prosody()`,
  set by `TTSEngine.begin_turn(mood=...)`; `reset()` keeps it.
- Initiatives: `decide(..., restraint=Mood.restraint())` multiplies every learned wait:
  sulking ×3, energy < .35 ×1.6, else ×1.

**Interfaces:** `Mood(path)` with `react(emotion, now=None)`, `feel(feeling, because='', now=None)`,
`met(now=None)`, `describe(now=None) -> dict`, `prosody(now=None) -> tuple`, `restraint(now=None) -> float`.
Parser: `('feel', feeling, because)`.

**Tests:** `tests/test_mood.py` (decay, clock energy, sulk lifecycle and reload, closeness once a
day, prosody direction, clamping), feel-line parsing, a turn with a feel line changes the mood and
the context carries `inner_state`, planner applies mood, `decide` restraint.

Skipped on purpose: idle animation from mood, mood shown in the UI.

---

## Phase 3: Layered memory

The plugin is symlinked into Hermes (`scripts/install_hermes_plugin.sh`), so the repo copy of
`hermes_plugin/chassie/store.py` is live. Markdown stays the source of truth; metadata lives in each
managed note's front-matter. No schema migration: the index fingerprint moves to `index-v3` once.

**Plugin (`store.py`):**
- `facts() -> list[dict]`: managed notes as `{id, path, title, content, date, importance (1-3, default 2),
  superseded_by, edited}`. `edited` = the body no longer hashes to its id (the owner changed it).
- `mark(identifier, *, superseded_by=None, importance=None)`: rewrite those front-matter keys of a
  managed note only; values validated (`superseded_by` must be another managed id).
- `refresh()`: a managed note with `superseded_by` is indexed with kind `superseded`.
- `Memory log.md` in the managed folder is never indexed nor listed in `Memories.md`.

**Consolidation (`memory/consolidation.py`), automatic, in `_reflection_loop` when idle:**
- New = active managed facts not in `.chassie/consolidated.json`; at most 20 per run. For each, up to
  4 similar active facts (semantic rank if loaded, else keyword search).
- One `complete_once` call → `{"ops":[{"op":"supersede","old","by","why"},{"op":"importance","id","level"}]}`.
  Applied only when every id is in the batch, `old != by`, and neither note is `edited`. Unsure → no op.
- Before applying: zip the managed folder to `.chassie/memory-backups/<stamp>.zip` (keep 5).
  Every supersede appends a line to `_generated/chassie/Memory log.md` (importance changes are not logged).
- Then, after the last batch of new facts, a second call writes the core profile
  `_generated/chassie-profile.md` (≤ 2000 chars; People, Routines, Likes and dislikes, Sensitive topics,
  Humor and style) from active facts sorted by importance then recency.

**Recall (`_vault_recall`):**
- Rows of kind `superseded` never reach the model.
- Always: owner note, core profile, latest diary, then the 6 active facts with the best
  `importance × 0.5^(age_days/30)` (importance cached from `facts()` at warmup and after consolidation).
- Query part unchanged (keyword + e5, RRF, top 3), then an entity hop: up to 2 notes whose file name is
  linked (`[[X]]`) from what was found or named in the query, excluding the owner link and `Memories`.

**Skipped on purpose:** merging two facts into a new one (supersede covers changed facts), showing
superseded facts in `Memories.md`, `owner_name` for the plugin's hardcoded `[[Artdi]]` link (needs the
owner's config; ask first).

**Upgrade note:** Hermes and Chassie share `~/.hermes/chassie-state/index.sqlite`. After pulling Phase 3,
restart Hermes (`hermes gateway restart`) so both use the `index-v3` fingerprint; otherwise each
re-indexes the vault the other just indexed. The first consolidation treats every existing fact as
new and works through them 20 at a time (two model calls for the last batch, one for the others).
