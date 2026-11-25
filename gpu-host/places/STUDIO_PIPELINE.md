# Studio pipeline: many editors on Resolve (free), one seat on Resolve Studio (design, not built)

A studio with several editors who use the free DaVinci Resolve and one licensed Resolve Studio seat. Each editor has their own bot (stack) and their own desktop place. The
licensed seat has its own bot and does the Studio-only work for everyone else. This file is the design and the build list. What already exists is marked **(built)**.

## Principles

- **The desktop never signs into Telegram.** The person's Telegram account stays in the Telegram app on their phone or PC and with their own bot. The desktop and the bot share
  exactly two folders, `input` and `output`, through the GPU gate (the place's own token). Nothing else connects them. (built: `place_control.py` file bridge,
  `gateway escritorio subir|bajar|archivos|borrar`)
- **The person sees everything graphically.** `Input` and `Output` are ordinary folders on the desktop. The person reviews, renames and deletes there, and the bot's view
  (`escritorio archivos`) is always the folder as it is. There is no second copy to keep in sync.
- **Originals are kept.** What the person forwards to the bot lands untouched in `input/originals/`. Whatever the bot makes from it goes next to it and never replaces it.
- **The GPU only through the gate.** Conversions, renders and Studio jobs are gate tasks with a lease, like everything else on the host.
- **Between people, only with consent and a log.** A project leaves an editor's place for the Studio seat only when the editor asks, only to a seat of the same studio, and
  every handoff is recorded (who, what, size, when, result).

## The flow

1. **In.** The editor forwards originals (video, audio, images) to their bot. The bot streams each file into `input/originals/` and makes a Resolve-ready copy in
   `input/resolve/` (DNxHR + PCM: free Resolve on Linux reads no AAC and may not read H.264/H.265). (built: `subir` + `to-resolve`, today the original is the
   uploaded file itself and the converted copy goes to `input/resolve/`. To build: an explicit `originals/` folder.)
2. **Ready in Resolve.** The bot writes `input/resolve/manifest.json` (the clips, their originals, the order the editor asked for, an optional project name). Free
   Resolve allows **no external scripting** in recent versions (only Studio does; check on the installed version), so the bot cannot open Resolve and build the project from outside. Two ways that work on the free
   edition:
   - a **script inside Resolve** (Workspace → Scripts → `bridgeai import`), installed in the place image. The editor clicks it once, and it reads the manifest and
     makes the project, the bins and an assembly timeline. Scripts run from that menu are allowed on the free edition (to confirm on the installed version);
   - a **timeline file** (FCPXML or OpenTimelineIO) next to the media, which the editor imports with File → Import → Timeline.
   The script is the better experience. The timeline file is the fallback that needs nothing installed.
3. **Edit.** The editor works in their place, by web (Selkies) or Moonlight.
4. **Out for review.** The editor exports to `output/`. The bot sends it to Telegram, as an mp4 that fits if needed (built: `bajar` + `from-resolve`). It deletes the
   export only after the editor says it arrived (built).
5. **Handoff to the Studio seat**, when the editor asks for it ("send this to Studio for noise reduction"):
   - the editor exports a **project archive** (`.dra`: project and media together) into `output/handoff/NAME/`. The in-Resolve script can do it in one click. Without
     the script, File → Export Project Archive does it by hand;
   - the bot asks the gate to move that folder to the Studio seat's `input/handoff/<origin>/NAME/`. This is a place-to-place copy on the same host, with no Telegram
     (a project is many GB, far over Telegram's 2 GB) and no other network. Between hosts it goes through the object store (`aibridge/BLOB_STORAGE.md`, designed);
   - the request carries a short instruction from the editor (the effect, a preset name or a PowerGrade, the clips, the deadline).
6. **Studio work.** The Studio seat's bot sees the new job and puts it in a queue. Studio **does** have external scripting, so this side can be automatic: restore the
   archive, relink the media, apply the requested Studio-only work (for example noise reduction, Magic Mask, Super Scale, Studio-only Resolve FX, renders above the
   free edition's limits) from presets the studio keeps, render, and export a new archive. The licensed person can also open it and work by hand. (Partly built:
   `gpu-host/resolve_mcp` drives a Resolve session through the gate with a lease. Whether that session is the Studio seat, and the job runner itself, are not built.)
7. **Back.** The result (render and updated archive) goes to the origin place's `input/from-studio/NAME/`, through the same gate copy. The origin bot tells the
   editor, who reviews it on their desktop and sends the final through step 4.

## Queue and status

One Studio seat serves the whole studio, so jobs wait. Every job has a state (`waiting`, `running`, `done`, `failed`, `returned`), a position and an estimate. The origin
bot answers "where is my job?" from that state and never guesses. A job that fails comes back with its reason and the editor's archive untouched. The seat's own
person decides the order when they want to (priority by hand), and otherwise it is first in, first out. This is the same shape as the job ledger and the queue
position + ETA already planned for GPU jobs (`HERMES_ARCHITECTURE.md`, media and jobs sections).

## Rules and limits

- **Studio.** A studio is a named group of stacks: the editors and the seat. A handoff is refused outside it. Membership is set by the operator, never by a bot.
- **Licence.** The Studio licence (an activation key or a USB dongle, tied to the machine) stays on the seat's host. The other places never get it and never see it.
  Whether the studio's licence terms allow the seat to process the other editors' projects is the studio's to check (normal studio work, but it is their contract).
- **Space.** Archives are big. Each handoff is checked against free space on both ends (the file bridge already refuses below 8 GB free) and a per-place quota (not
  built). A returned job is kept until the editor deletes it or a set number of days passes, and the editor is warned before it goes.
- **Privacy.** A handoff copies one person's material into another person's place. The editor's request is the consent, and the log says it happened. Nothing else of
  the origin place (its home folder, its other files) is ever reachable from the seat.
- **Telegram in the image.** Telegram Desktop is installed in the place image but is not part of this flow. Removing it from studio places is an option (less to
  update, nothing to sign into by mistake).

## Build list (in order)

1. `input/originals/` kept apart from the Resolve-ready copies; `subir` records the pair in the manifest.
2. `manifest.json` written by the bot; the in-Resolve `bridgeai import` script (free edition, internal scripting) in the place image; FCPXML/OTIO fallback.
3. `output/handoff/` export (script button + by-hand instructions in the person's guide).
4. Gate endpoint for a place-to-place copy within one studio (both places' tokens, studio membership file, space check, log).
5. Studio seat job runner: queue, restore archive, apply presets, render, export, return, using a gate-leased Resolve Studio session (`resolve_mcp`, `resolve_session.py`).
6. Status verbs for both bots (`estudio enviar|estado|traer`), the ETA from the queue, and a notice when a job comes back.
7. Per-place disk quota and the retention of returned jobs.
8. Between hosts: the same handoff through the object store.
