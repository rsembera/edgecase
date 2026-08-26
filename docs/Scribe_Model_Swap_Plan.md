# AI Scribe Model Swap: Hermes 3 → Gemma 4 12B QAT

> **Historical record** — the July 2026 Hermes-to-Gemma evaluation and swap, completed. Gemma 4 12B QAT has been the shipped model since.

**Decided:** July 18, 2026, after a scored 4-model bake-off (see below).
**Status:** Planned, not started. Hermes 3 remains in production until executed.

## Decision

Replace Hermes-3-Llama-3.1-8B (Q4_K_M) with **google/gemma-4-12b-qat (Q4_0, QAT
build)** as the sole Scribe model. No user-facing model picker: one validated
model, forced. Architecture keeps the door open for a curated second preset
(Granite 4.1 8B, the runner-up) if a real small-RAM user ever needs it.

## Bake-off results (3 planted-error notes: restraint / temperament / composure)

| Model | Errors fixed | Traps | Notes |
|---|---|---|---|
| **Gemma 4 12B QAT** | 14/14 | 2/2 | Champion. Near-zero unauthorized edits; preserved charting shorthand; zero flinch on SI/abuse content (single-shot w/ task prompt; its chat-mode "cloud security" refusals never surface). |
| Granite 4.1 8B | 14/14 | 2/2 | Runner-up. Perfect recall + composure, but wholesale style-normalized the shorthand note (~17 unauthorized edits). Promptable defect. Faster than Gemma. |
| Hermes 3 (incumbent) | 13/14 | 2/2 | Missed "boundry" — the shorthand note's only real error — while making unauthorized expansions around it. Erratic, per the June 2026 production record (rewrites, "Mr A" sanitization). |
| Gemma 4 E4B | 8/8 on Note A | 2/2 | DQ'd: narrates a reasoning essay into plain output, welded to the answer, THROUGH an explicit "output only" instruction, with thinking off. Edit quality was actually perfect. |

## Swap checklist (est. ~2h; wildcard = llama-cpp-python bump)

**Stage 1 — library bump (the rollback point):**
1. `pip install -U llama_cpp_python` in venv (compiles new Metal wheel, ~10 min).
   Current pin: 0.3.16 (late 2025). Gemma 4 arch needs mid-2026 llama.cpp.
2. Update `requirements.txt` pin.
3. **Verify Hermes still works on the new bindings** (load + one Scribe proofread).
   This is the rollback point: if anything breaks later, Hermes-on-new-lib works.

**Stage 2 — model swap:**
4. Symlink the already-downloaded GGUF from LM Studio's models dir into
   `edgecase/models/` (no 7 GB re-download). Update `MODEL_REPO` /
   `MODEL_FILENAME` in `ai/assistant.py` (+ download-size expectations).
5. `chat_format='chatml'` → `chat_format=None` (use the GGUF's embedded
   template — proven working in LM Studio tonight). Plan B if embedded
   template misbehaves: manual Gemma formatter from the model docs.
6. `STOP_TOKENS`: ChatML tokens (`<|im_start|>`, `<|im_end|>`) are
   Hermes-specific. Make per-model or defer to template EOS. Gemma uses
   `<end_of_turn>`.
7. **Verify thinking stays OFF**: render the actual chat template with our
   messages and inspect for `<|think|>` mechanics. LM Studio's per-chat toggle
   proved it's controllable; confirm our single-shot path never activates it.
   (Symptom if wrong: 90-second proofreads and/or essays in output.)
8. Per-action temperature: proofread → 0.1 (writeup/expand/condense stay 0.3).
   Already agreed 2026-07-18, deferred pending bake-off.

**Stage 3 — verification:**
9. New test (the E4B lesson): Scribe output must contain zero reasoning
   artifacts — no "thinking process" narration, no `<|think|>`/`<start_of_turn>`
   fragments, no corrections-list preamble.
10. Full suite + ruff. Real Scribe proofread on a genuine note = acceptance test.
11. CHANGELOG + docs (Navigation Map's Hermes references, Project Status).

## Deliberate scope exclusions
- Packaged .dmg/.deb keep shipping Hermes until the v2 release train rebuilds
  them (bundled llama-cpp-python wheel; same lockstep as the crypto copy).
- Hermes GGUF stays on disk as instant rollback. Retirement, not deletion.
- No model picker. No Granite preset until a real user needs it.
