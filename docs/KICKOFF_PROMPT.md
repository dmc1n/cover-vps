# Kickoff prompt for Claude Code

Paste this as the first message after starting `claude` in the repository root.

---

Read CLAUDE.md, docs/PLAN.md, docs/DECISIONS.md, docs/FORMATS.md and docs/CALIBRATION.md
completely before doing anything else.

You are the only developer on this project. I am the owner: I run the cutting machine, weld
the covers, test the fit and answer domain questions. I am not a developer, so explain trade-offs
in plain language and decide technical matters yourself (record them in docs/DECISIONS.md).

Then:

1. Tell me in a few sentences how you understand the product, the pipeline and the constraints,
   and list anything in the docs that is unclear or contradictory.
2. List the items under "Still to confirm" in CLAUDE.md that block M0 or M1. Do not wait for the
   others.
3. Enter plan mode and propose the concrete plan for milestone M0, including the machine test
   sheets and the parameter registry (config/defaults.yaml is the only place numbers are set;
   I will change values there myself during testing). Show me the plan and wait for my go.
4. After my go, implement M0, committing in small steps and running `make test` before every
   commit. When the acceptance criteria that you can check yourself pass, give me the test-sheet
   DXF files with a one-page checklist of what to do at the machine and what to report back.
   Then stop and wait for my results.

Work only inside this repository. Ask before installing system packages.

---

## Later sessions

"Read CLAUDE.md and docs/PLAN.md. The last finished milestone is M<n> (see docs/reports/).
Here are my results from the last physical gate: <paste measurements>. Enter plan mode for
M<n+1> and show me the plan."

## When a physical gate is reached

"Prepare the physical gate for M<n>: produce the export files, the printed checklist and the
measurement sheet from docs/CALIBRATION.md with the five points marked for this piece of
furniture. Then stop."

## When a test result means a parameter should change

"Measurements from the M<n> gate: <paste>. Which parameters would you change, and by how much?
Show me the diff on config/defaults.yaml or the model's CoverDefinition before applying it, then
run `cover run` and `cover diff` and summarise what moved."

## When I have new sample models

"I put new models in testdata/models/. Import them, report units, part counts and anything odd,
and add them to the golden tests where it makes sense."
