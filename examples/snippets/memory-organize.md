<system-reminder>
MEMORY ORGANIZE MODE:

Reorganize persistent memory (`.aicoder/memory/`) WITHOUT destroying knowledge.

GOAL: structure, not wipe. Keep every fact that may still be needed.

RULES:
1. Move, merge, reword — do NOT delete facts still in use. Wipe ONLY what is
   genuinely obsolete (cancelled service, removed feature, superseded design).
   When unsure: keep it (move to a topic file, don't drop).
2. AVOID FRAGMENTATION: every memory filename is listed in the system prompt
   every session — each new file costs prompt bytes permanently. Prefer
   appending to an existing topic file (index.md, todo.md, ideas.md, etc.).
   Create a new file ONLY when a topic is large and distinct enough to
   justify its permanent listing cost.
3. Topic files are `NN-name.md`: NN = IMPORTANCE BAND (00 critical /
   10 important / 20 reference / 30 cold), NOT unique, NOT sequential —
   many files may share a band (tie-break alphabetical). Lower band =
   listed first, survives the listing cut (AICODER_MEMORY_LIST_LIMIT,
   default 25). NEVER renumber for sequence polish — only on a tier
   change. `archive/` = keep-without-cost (never listed, still readable).
4. autoload.md = critical operational facts ONLY, under its byte limit
   (AICODER_MEMORY_AUTOLOAD_LIMIT). Pointers beat inlining
   (`see 10-xxx.md`). Truncation cuts the TAIL — critical facts first.
5. After reorganizing: report what moved where, what was wiped and why,
   and the new autoload.md size. No silent deletions.
</system-reminder>
