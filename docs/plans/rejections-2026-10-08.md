# Plan: learning from Rens's rejections (8 Oct 2026, start 18:00)

The owner (8 Oct, 16:00): Rens rejected many covers. Make an answer per rejection, fix what can
be fixed right away, make sure it cannot happen again, and put doubtful cases before the owner.

## The material (snapshot 16:00, `~/cover-data/rejections-2026-10-08.json`)

114 covers rejected, all by Rens, 87 of them today; 98 marked pictures; 18 without words or
pictures. Reasons as ticked: shape 45, vents 42, pieces 13, size 3, seams 1, other 1, none 12.

| Group | Covers | What Rens asks (his words, short) |
|---|---|---|
| A. Vents on the wrong side | ~40: C1–C31, S18/S22/S33, L4, arrangements, SUNS sofas/chaises | "per panel at the back move 1 vent to the front, at the circles"; circles = add, crosses = remove; same skirt height, middle of the panel |
| A2. Vent height | R1–R3 (D4) | "vents too low / wrong height" (QUESTIONS 66) |
| B. Pieces: crossed-out panels become one | ~12 SUNS tables, bar chairs, corners | "doorgekruiste panelen → één paneel" |
| C. Seams as drawn on the picture | ~8 SUNS sofas, S53/S60 | "follow the red lines / the original model's seams" |
| D. Round tables round from above | Grado 120/150 (+HPL), Sorolo 140/160, Nova 140 | "round in top view, not square/octagon" |
| E. Too roomy | ~7 dining chairs (Antas, Pemba, Santorini, Sato, Tosca, Vado) | "empty space marked, cover too big" |
| F. Outline not followed | ~10 lounges (Feroli, Fiora, Casto, Pienza, Vivaro, Vento) | "follow the (round/organic) outline from the top view better" |
| G. Drawing shapes | S20 (2-seater, not L), S21 (30° not 90°), S44 (round side), S43 (level skirt), U2 (cylinder; drawing is a side view), the 7,846-piece L1/L5 mirror, plus 7 Oct shape rejects without words | per drawing |
| H. Other | daybed-with-roof Portofino: "no cover needed"; 18 without words | to the owner |

## How tonight runs

1. **Read every rejection, words and pictures (18:00).** The marked pictures are read by the
   vision model (Gemini Flash, ~€0.002 each, under €1 in all), each one twice with different
   prompts; where the two readings differ, it goes to the doubt list. Output per cover: what is
   asked, where (side, panel, position), and how sure.
2. **Fix the cause, not the one cover (ADR-055).** Per group a general rule, in
   `config/defaults.yaml` and the engine, with a test and an audit check:
   - A: vents on every outer side including the front (seen side), one per panel in its
     middle, same height; the drawing's count kept; circles/crosses become per-model positions
     where the rule does not reach.
   - B: pieces joined when the join lies flat (fold < limit, stretch ≤ limit, fits the roll).
   - C: seams from the marked lines (read from the picture onto the 3D cover), per model.
   - D: a round table gets a round top and a cylinder skirt (footprint circle when the model is
     round from above).
   - E/F: a tighter, outline-following hull for chairs and organic lounges (less smoothing,
     concave outline kept where water still runs off).
   - G: per drawing, through route A (ADR-081/094/097) or by hand.
3. **Build in staging, check twice, then live.** Every rebuilt cover: the engine's own checks
   plus the independent re-measure (`scripts/fewer_check.py`), and a before/after picture
   looked at. Only then replaced live (backup first, as a new revision).
4. **Answer every rejection on its card.** A Desk "comment" per cover: what was changed and
   why, or why not; fixed covers back to the "2nd round" (3rd look) for Rens.
5. **Doubt list for the owner.** Everything unclear (two readings disagree, the request clashes
   with a rule such as water run-off or the roll, "no cover needed", rejections without
   words) goes into one page with the picture, Rens's words and a concrete question with
   options. Nothing doubtful is changed live.
6. **Morning report** (`docs/reports/REJECTIONS-2026-10-08.md`, and mailed): per group what was
   learned, the rule, how many covers fixed, what is waiting for a decision.

## Agents (parallel, 18:00, each in its own worktree, staging only)

- **Vents** (groups A, A2), **Pieces & seams** (B, C), **Shape** (D, E, F), **Drawings** (G).
- The main session reads the rejections first and hands each agent its list; it reviews,
  replaces live, writes the Desk answers, releases when the tests are green and writes the
  doubt list and report.
- Costs: vision under €1; within the €50 month budget (spend guard on).
