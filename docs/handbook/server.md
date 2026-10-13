# The server

One Hetzner VPS (Ubuntu 26.04, 168.119.50.82). Three things run on it:

| what | how | where |
|---|---|---|
| Caddy | systemd `caddy`, config `/etc/caddy/Caddyfile` (copy of deploy/Caddyfile) | ports 80/443, https://covers.suns.nu, certificate from Let's Encrypt, renewed by itself |
| Cover Studio | systemd `cover-web` (deploy/cover-web.service) | 127.0.0.1:8080 only, behind Caddy |
| watchdog, backup | cron of user dev | every 10 minutes, every night 02:30 |

The firewall (ufw) allows SSH, 80 and 443. fail2ban bans SSH password guessers.

## Everyday commands

```
sudo systemctl status cover-web          # is the app running
sudo systemctl restart cover-web         # after an update of the code
journalctl -u cover-web -n 100           # the app's log
caddy validate --config deploy/Caddyfile --adapter caddyfile   # check a change first (no sudo)
sudo systemctl reload caddy              # after a change of deploy/Caddyfile (copy it first)
tail /var/log/caddy/covers.log           # who visited
sudo fail2ban-client status sshd         # banned addresses
```

## Backups

Every night at 02:30 `scripts/backup.sh` writes `~/backups/cover-data-<date>.tar.gz`: all
models, uploads, jobs, the users and the settings (14 kept, readable only by user dev). The
time of the last good backup is in `~/cover-data/last_backup.txt` and on Settings → System. Still
missing: a copy outside this server (see QUESTIONS.md, #89). Once `COVER_BACKUP_REMOTE` is set
(for example `r2:cover-backups`), every night's archive is copied there too. When that copy
cannot be made (rclone missing, an unknown remote, a failed copy), the local archive stays,
`last_backup.txt` starts with **FAILED** and says why, and the watchdog mails it (ADR-129).
Unset, `last_backup.txt` ends with "off-server copy: not set".

Restore one model: `tar -xzf ~/backups/cover-data-<date>.tar.gz ./models/<id>` in a temporary
folder, then copy it back. Restore everything: stop cover-web, move ~/cover-data aside, unpack
the archive into a new ~/cover-data, start cover-web.

## Updates

Security and normal updates install themselves every day (unattended-upgrades). There is no
automatic reboot, because it would stop running calculations; the watchdog mails when a reboot
has waited more than a week. Reboot: `sudo reboot` (cover-web and Caddy start by themselves).

## Alerts

`scripts/watchdog.py` checks every 10 minutes: the app and https answer, the services run,
disk space, the certificate, the age of the backup, failed services, update errors, a waiting
reboot. A problem is mailed to the alert address (Settings → Mail & notifications;
rick@s2dio.industries) once, again every 6 hours while it lasts, and once more when it is
solved; the last alerts are on Settings → System. It needs the mail server (Settings → Mail &
notifications); until then the alerts are only in `~/cover-data/alerts.log`.

## Versions (to set up with the owner)

Every change is a git commit on GitHub (dmc1n/cover-vps). Plan: a numbered release (git tag
`v1.0`, `v1.1`, …) for every version that goes live; the server runs a tag, not a loose
commit; going back is checking out the previous tag, building and restarting:

```
git fetch --tags && git checkout v1.0
uv sync && (cd apps/web && npm ci && npm run build)
sudo systemctl restart cover-web
```

The data (models, users) is not in git: that is what the backups are for.

## Toegang via Tailscale (2 oktober 2026)

SSH staat sinds 2 oktober 2026 dicht voor internet (`deploy/tailscale-setup.sh lock`). De server
heet **cover-server** (100.76.72.19) in het Tailscale-netwerk van rick@.

- Inloggen: `kitten ssh dev@cover-server` (of `ssh dev@cover-server`) met Tailscale aan.
- Een collega toegang geven: uitnodigen in de Tailscale admin console (Users → Invite).
- Noodtoegang als Tailscale niet werkt: de webconsole bij Hetzner, dan `sudo ufw allow OpenSSH`.
- Open voor internet: alleen 80 en 443 (de website via Caddy).

## Versies en terug naar een vorige versie (ADR-053)

De app draait vanuit `~/releases/current`, een verwijzing naar de live versie (bijvoorbeeld
`~/releases/v1.0.0`). De gegevens (modellen, gebruikers, uploads) staan daarbuiten en blijven
bij elke wissel dezelfde.

- Nieuwe versie live zetten: `scripts/release.sh v1.1.0 "wat er nieuw is"` (test eerst alles,
  zet een versienummer in git, bouwt de versie in een eigen map en schakelt over). Mislukt de
  herstart, of antwoordt de app niet binnen een minuut als die nieuwe versie, dan gaat hij
  vanzelf terug naar de vorige versie, start die opnieuw en zegt dat ("switched back to ...
  automatically"; ook in `~/releases/history.log`). Hetzelfde geldt voor `rollback.sh` (ADR-129).
- Alleen `sudo systemctl restart cover-web` mag zonder wachtwoord. Draait de dienst nog niet
  vanuit `~/releases/current` (de eerste installatie), dan verandert het script niets en print
  het de commando's (`sudo cp ...`, `sudo systemctl daemon-reload`, ...) voor een persoon.
- Terug naar de vorige versie: `scripts/rollback.sh` (ongeveer 10 seconden).
- Terug naar een bepaalde versie: `scripts/rollback.sh v1.0.0`; welke er zijn:
  `scripts/rollback.sh --list`.
- Welke versie live is: Settings → System ("Release (live)"), met de laatste wissels.

## Jobs after a restart (ADR-129)

A calculation runs as a job in the app. When the app stops while a job runs (a release, a
restart, a crash), the job cannot go on. At the next start the app marks every job it left
queued or running as **interrupted**, with the reason ("the server stopped while the step cut
ran"), and ends a calculation that was still running on its own. On the cover's page the job
bar says so and has **Run again** (the same steps, the same trial values). While a job runs, the
bar shows how long one step may take at most (`limits.job_timeout_s`, 4 h); a longer step is
stopped and the job fails with that reason.

## Mail (ADR-129)

Every mail the studio and the shop send is logged in app.db: when, what kind, to whom, the
subject, and "sent" or the error. The text is never logged, nor a password. A mail counts as sent
only when the mail server accepted it. Order notices, the fit question after delivery, requests
and the Desk's digests go through an **outbox**: tried at once, and when that fails again after
1, 2, 4, ... minutes (at most 6 h apart, `limits.mail_*`), 8 tries in all; then the mail is
**failed**. Settings → System & logs → **Mail** lists what waits and what failed, with the last
error, and has **Send again**. The text of a sent mail is removed at once; a failed one's after
14 days. Login codes and password links are never kept: they are sent once, and the person asks
again if one did not arrive. The fit question counts as sent (and is not asked again) only once
the server took it.

## Limits that protect the server (ADR-123)

- **Request sizes.** Caddy refuses a request body over 2 MiB, except on the logged-in upload
  routes (3D models, drawings, references, product and price lists, Desk and question pictures,
  the photo test: 2 GiB) and the shop's photo routes (40 MiB). The app checks each route's own
  limit again before it reads anything (`limits.body_mb`, `limits.upload_mb`, and the routes'
  own caps); too large is answered 413 by the app (502 by Caddy 2.6).
- **Pictures and PDFs** are checked by their size in pixels before they are decoded
  (`limits.image_max_mp`, 40 megapixels; a large phone JPEG is decoded at half or quarter size).
  A drawing has at most `limits.pdf_max_pages` pages; a reference zip at most
  `limits.zip_max_files` files and `limits.zip_max_mb` unpacked; a product or price list at
  most `limits.sheet_max_rows` rows and `limits.sheet_max_cells` cells, and an .xlsx may unpack
  to at most `limits.sheet_max_unpacked_mb`.
- **Background jobs**: each step (import, hull, ..., drape) stops after `limits.job_timeout_s`
  (4 hours) and may reserve at most `limits.job_memory_mb` (12 GiB); the job then shows why. A
  207 MB STEP (the Blocchi sofa) runs every step well inside both.
- **Old price proposals** in `shop_quotes`, `b2b_quotes` and `quotes` go after
  `limits.quotes_keep_days` (60) unless an order or request names them: `scripts/housekeeping.sh`
  daily, by hand `COVER_DATA_DIR=~/cover-data uv run python scripts/quotes_clean.py --dry-run`.
- **The access log** keeps no keys or tokens: the `X-Link-Key` and `X-Api-Key` headers and the
  Referer are left out, and the tokens in order, fit, match, invite and reset links and in
  `?preview=`, `?link=`, `?key=`, `?token=` are written as REDACTED. Caddy 2.6 cannot set the
  log file's mode, so once: `sudo chmod 0640 /var/log/caddy/covers.log` (rolled files keep it).
- **Settings no model can change**: the AI's addresses and every spending cap and visitor limit
  are marked `[server-only]` in `config/defaults.yaml`; a cover's settings, a trial run, a
  learned rule or the web app cannot set them (400), and an AI key is only ever sent to its own
  provider (api.deepseek.com, generativelanguage.googleapis.com).
