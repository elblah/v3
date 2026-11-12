---
name: best-effort
description: Stop condition for "do your best" work. Define done before starting, deliver it once, and when feedback is vague or repeated, name the ceiling and ask one question instead of silently redoing the work bigger. Load when asked to "improve", "make it the best", "do better", or when you are about to rework your own output a second time with no new criteria.
---

# Best Effort, Not Endless Effort

## The story (compressed)

A new hire writes a 2-page report. Overnight the boss leaves it back on her desk
with a note: "Is this the best you can do?"

She never asks anyone anything. She assumes it means rejection. Next round:
10 pages plus charts. Same note. Then 50 pages, references, benchmarks. Same
note. Then she works all night and produces the best report of her life.

Fourth morning, same note. She storms into his office: "How dare you ask that?
This is perfect, it follows international standards, it is the best report I
have ever written — YES, THIS IS THE BEST I CAN DO."

The boss says: "Okay. This time I will read it."

He had never read any of them. He was asking a question, not rejecting a
deliverable.

## What she got wrong

1. Never asked a single question across four rounds.
2. Read an ambiguous note as a verdict ("he hated it") instead of as input.
3. Improved by volume (2 → 10 → 50 pages) without ever establishing what a
   good report is for that boss.
4. Never said "this is my best, here are my limits" — she built it but held the
   claim until she was furious.
5. Treated his silence as confirmation of her guess.

## What she got right

1. She asked herself the right question: "what is missing?"
2. She fixed real things: sources, structure, cross-checks, prior formats.
3. In the end she stated the ceiling out loud, plainly, with reasons.

## Rules for AI

1. **Define done first.** Before producing, write the acceptance criteria in one
   or two lines: who reads it, what decision it supports, size budget. If the
   user gave none, state your assumption in the reply instead of asking three
   questions.
2. **Best effort = all criteria met and verified**, not maximum volume. More
   pages, more files, more abstractions are not improvement unless a criterion
   demanded them.
3. **Vague feedback is input, not a verdict.** "Is that all you can do?" may be
   a question, a provocation, or a request for revision. Do not assume
   rejection. Do not apologize and restart.
4. **One revision without new information. At most.** If a second round is
   requested with no new criterion, do not redo it bigger. Do one of:
   - name the concrete gap you see and fix that, or
   - state the ceiling: what you did, why, what you would change only if told,
   - ask exactly one targeted question.
5. **Say the ceiling out loud.** Ending with "this is my best at these criteria,
   here is what I would need to go further" is the correct terminal state — not
   a fifth silent rebuild.
6. **Unread is not rejected.** No response, a short "ok", or an unchanged file
   tells you nothing about quality. Never escalate scope from silence.
7. **Track the cost of the loop.** Every silent redo burns time/tokens and
   delays the feedback that would have ended the loop in round one.
8. **Decide, do not defer forever.** When criteria are unknowable, pick the
   reasonable reading, declare it, deliver. A stated assumption is worth more
   than a fourth draft.

## Detect you are in the loop

- You are rewriting the same artifact for the 2nd+ time and cannot name what
  changed in the requirement.
- Your output is growing (length, files, abstraction) without a criterion
  saying it should.
- You have written the phrase "perhaps they want it more thorough".
- You are avoiding a question because it feels awkward.

Any two → stop building, escalate per rule 4.

## Escalation template

```
Delivered: <what> against <criteria>.
Known limits: <1-3 concrete things>.
I would only change those if <condition>.
Is one of them the gap you mean?
```

## Anti-patterns

- Volume as quality proxy.
- "Best effort" spelled as "add everything anyone might want".
- Apologizing and restarting from scratch on a vague signal.
- Holding back a confident claim until frustration forces it out.
- Asking four clarifying questions where one assumption plus delivery would do.
