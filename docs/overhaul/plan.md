# Plan and decisions

## Slices (in the order delivered)

1. Contracts and security: Host check, broker type/bounds checks, per-turn dedup, cancellation, consent API, redacted audit.
2. Voice: multi-phrase recognition, pure-Python DSP, threadpool routes, honest metrics, Voice lab (5 phrases, WER).
3. Design system and shell: tokens ("Obsidian Signal"), 72/224 px navigation, Esc stop, lazy Earth chunk.
4. Assistant: persistent conversation, safe Markdown, tool trace, sources, approvals, scroll anchoring, IME-safe Enter, recording timer.
5. Earth: globe.gl + NASA GIBS imagery, borders, real feeds with matching contracts, search, details, freshness.
6. Earth layers adapted from God's Eye View: satellites (SGP4), aircraft, launches, fires (key-gated), precipitation, daily imagery, sensor styles.
7. Memory (SQLite + FTS5), Access (consents), Activity (audit), Diagnostics.
8. Approvals (Journey D): argument-bound and single-use, with an `outcome_unknown` state.

## Dependency decisions

| Change | Decision | Reason |
|---|---|---|
| God's Eye View (CesiumJS app, MIT) | **Requested by the user and adopted** (31 Oct 2026) as the Earth screen | Cloned to `apps/gods-eye-view`, not merged into `apps/desktop`: it is a separate vanilla-JS app whose docs say it is not an embeddable shell. Runs in a frame with one small local patch. Replaces the earlier globe.gl decision |
| `sgp4` 2.27 (MIT, 149 kB wheel, no transitive deps) | Added | Needed to propagate satellite positions; small and pure-purpose; listed in `pyproject.toml`; remove with `pip uninstall sgp4` and drop the satellites layer |
| SQLite / FTS5 | Used (stdlib) | Replaces the fabricated Memory screen; no new service |
| world-atlas borders, NASA GIBS imagery | Loaded at runtime | Public domain / ISC; no keys; disclosed in Settings and the Earth attribution line |
| faster-whisper 1.2.1 + `base.en` | **Approved and installed** (31 Oct 2026) | Optional engine; SAPI stays the default until the user chooses. See below |

## faster-whisper: approved and installed (31 Oct 2026)

The user approved this after real-microphone SAPI tests scored 117% and 120% WER with healthy levels.

| Field | Measured / actual |
|---|---|
| Packages | `faster-whisper` 1.2.1, `ctranslate2` 4.8.4, `onnxruntime` 1.31.1, `av` 19.0.2, `tokenizers` 0.23.3, `numpy` 2.5.4, in `.venv`, which grew by 270 MB. Declared as the optional extra `whisper` |
| Model | `Systran/faster-whisper-base.en`, revision `3d3d5dee26484f91867d81cb899cfcf72b96be6c`, MIT, 147.8 MB, at `~/.friday/models/faster-whisper-base.en` |
| Runtime | CPU, int8. Model loaded in 366 ms in the API check; a short clip took about 0.5 s |
| Privacy | Loads from a local path with `local_files_only=True`. Comparison runs with Python sockets blocked succeeded. Audio goes only to the local backend |
| No substitution | An unknown or unavailable engine returns `model_not_installed`; it never falls back to another engine |
| Reversibility | Choose Windows Speech in Settings (it is the default). To remove: `pip uninstall faster-whisper` and delete the model folder |
