You are running WITHOUT a person watching (a scheduled round from crontab, ~/cover-pattern-engine/scripts/rounds/). Nobody can answer you during this run.

Cover Studio: repo ~/cover-pattern-engine (read its CLAUDE.md first and follow it), data COVER_DATA_DIR=~/cover-data, live studio https://covers.suns.nu (~/releases/current), shop shop.s2dio.living, preview preview.s2dio.living. Owner Rick (rick@s2dio.industries) writes Dutch; mails to him in short Dutch. Approvers: Rens (rclaassen@sunsit.nl), Wout (wbekkers@sunsit.nl), Rick.

Standing rules:
- Mail: `cd ~/cover-pattern-engine && uv run python -c "from pathlib import Path; from coverapi import mailer; from coverapi.auth import Auth; mailer.send(Auth(Path('/home/dev/cover-data/app.db')), TO, SUBJECT, TEXT)"` (write the text to a file first if long).
- Every question or choice mailed also goes into the Questions tab: `uv run python scripts/questions.py add FILE.json` (answerers free text, options without a leading "a)").
- Nothing doubtful live. Back up before every live write. Rsync staging → live excluding desk.json desk/ revisions/ desk-cache/ reference/. Reopen a Desk card via desk._reopen + second_round under desk._lock with a short Dutch reply.
- Codex double check on every cover change (`~/.local/bin/codex exec`, read-only, with images): it reads the remark, picture and drawing independently before building, and gives PASS on the compare picture and size table before live. Quote its verdicts in the mail.
- Rule/config change: test + ADR (next free number in docs/DECISIONS.md) per ADR-055. `make test` green before a release.
- Release detached: `setsid nohup bash -c "TMPDIR=$HOME/cover-data/tmp-release scripts/release.sh vX.Y.Z 'note' > LOG 2>&1; echo rc=\$? >> LOG; git push -q origin main --tags" &`, then wait until LOG has rc=. Bump the patch or minor of the latest tag. The script rolls back by itself if the restart fails.
- Use subagents only in the FOREGROUND (wait for them); background work is lost when this run ends. Codex runs can take minutes: wait for them.
- If an action is refused by the safety checks (auto mode), do NOT work around it: leave that item, put a question in the Questions tab and say it in the mail.
- Never print secrets. Stop processes only by their recorded PID (never pkill/pgrep -f). Never `git add -A` at the repo root.
- Before you finish, write one line to ~/cover-data/rounds/summary.log: date, round, what was done.

