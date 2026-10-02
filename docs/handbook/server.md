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
sudo systemctl reload caddy              # after a change of deploy/Caddyfile (copy it first)
tail /var/log/caddy/covers.log           # who visited
sudo fail2ban-client status sshd         # banned addresses
```

## Backups

Every night at 02:30 `scripts/backup.sh` writes `~/backups/cover-data-<date>.tar.gz`: all
models, uploads, jobs, the users and the settings (14 kept, readable only by user dev). The
time of the last good backup is in `~/cover-data/last_backup.txt` and on the admin page. Still
missing: a copy outside this server (see QUESTIONS.md).

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
reboot. A problem is mailed to the alert address (admin page, System; rick@s2dio.industries)
once, again every 6 hours while it lasts, and once more when it is solved. It needs the mail
server on the admin page; until then the alerts are only in `~/cover-data/alerts.log`.

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
  zet een versienummer in git, bouwt de versie in een eigen map en schakelt over). Antwoordt
  de app daarna niet binnen een minuut, dan gaat hij vanzelf terug naar de vorige versie.
- Terug naar de vorige versie: `scripts/rollback.sh` (ongeveer 10 seconden).
- Terug naar een bepaalde versie: `scripts/rollback.sh v1.0.0`; welke er zijn:
  `scripts/rollback.sh --list`.
- Welke versie live is: de adminpagina, tab System ("Release (live)"), met de laatste wissels.
