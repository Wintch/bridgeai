# Missing tools (living list)

Whenever Claude or a Hermes agent needs something that is not installed, it goes here: who needed it, where it failed
and how to install it. **Host** items need sudo on VM105; **image** items are in the Dockerfile and arrive with the next
rebuild. Agents never install packages themselves (`apt`/`apt-get`/`sudo` are forbidden in the SOUL and the
`cron-policy` skill since 2026-11-03): a missing tool is reported and added here.

## For the operator (VM105 host, needs sudo)

| Tool | What for | Where it failed | Install |
|---|---|---|---|
| `bc` | timing boots in shell scripts (decimal subtraction) | VM105, `ssh aibridge@... 'bc'` → `bc: command not found` (2026-10-07) | `sudo apt install bc` |
| ~~firewall rule for port 3099~~ | nginx (a container) reaching the host waker | done 2026-10-07: ufw for hernik and `docker-user-fw.sh` (one pinhole per stack) | for every new stack: `sudo systemctl restart docker-user-fw.service` (system unit `aibridge/docker-user-fw.service`, also re-applies the firewall at boot) |

## Hermes image (Dockerfile.hermes-agent-base)

| Tool | What for | Where it failed | State |
|---|---|---|---|
| `ripgrep` (`rg`) | Hermes's `search_files` refuses wide searches without `rg` | herand 8x, hereug 3x | in the image |
| `uuid-runtime` (`uuidgen`) | folder names in `/web-outputs/<uuid>/` | herand 2x, hereug 3x | in the image |
| `procps` (`pkill`, `pgrep`) | restarting Hermes's gateway without looking up PIDs in `/proc` | hernik, 2026-10-07 (`pkill: not found`) | in the base Dockerfile and the image |

## Left out on purpose (do not install unless you change your mind)

| Tool | Why not |
|---|---|
| `pdflatex` / texlive | several GB; PDFs are made with weasyprint or `generate-pdf.mjs`. It failed 5x on herand and hereug when the agent tried it |
| system `cron` | schedules go through `hermes cron`, which the waker reads; a system crontab dies when the instance sleeps. An agent installed it on 2026-11-02 for a price scrape the person had declined |
