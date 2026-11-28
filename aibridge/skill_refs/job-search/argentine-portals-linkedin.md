# Argentine portals, LinkedIn and reading job pages (job-search)

- **Web access (read this before saying a site "can't be reached")**:
  - **To look for job offers on the Argentine portals, run `buscar-empleos "<palabras>" [--zona "<texto>"] [--n 6]` in the terminal** (first read "Which search tool" above: a person whose `portals.yml` has job boards enabled is searched with `scan.mjs`, not with this). One
    command, ~25s: it searches ZonaJobs, Bumeran, Computrabajo and LinkedIn and prints each portal's postings with their
    URLs (`--portales zonajobs,linkedin` to limit). Then read one in full with `browse-page <url> --max 6000`. Do not
    improvise with `web_extract` or `browser_exec` for these portals: it took 200-330s of trial and error and Cloudflare blocks
    them on ZonaJobs.
  - **The person's filters live in a file, not in your memory** (a "no AI" request repeated five
    times was still ignored). The first time a person states what they never want to see (AI, 3D, a technology, a
    sector), write one term per line to `/workdir/jobfinder/config/buscar-empleos.excluir` (create it if missing; `#`
    starts a comment). `buscar-empleos` applies that file on every run, to the posting card AND to the posting's own text,
    and lists what it dropped with the sentence that matched. One-off exclusions: `--excluir "ai,3d"`. Never put "-3D"
    or "no AI" into the search words, and never type an option with a long dash (`—3D`): unknown options are an error.
  - **Every link `buscar-empleos` prints was opened.** `✔ open and verified on <date>` means it was open that day; a
    posting that is gone (404, "listing has ended", redirect) is dropped and counted. `⚠️ could not verify whether it is still open` means the
    portal refused or failed (LinkedIn answers 429 when asked fast): say exactly that, never call it verified. Do not
    hand over a link from `web_search` or from memory without opening it first (`browse-page <url> --max 3000`): ended
    and 404 listings are the most frequent complaint. `--no-verificar` is for a quick look only.
  - **Do not repeat a search that came back empty.** Results are cached 15 minutes. If a portal says it returned nothing
    for several different searches in a row, it is the wrong source for this person (ZonaJobs/Bumeran/Computrabajo are
    Argentine portals: a person who wants remote or worldwide work, in illustration for instance, finds nothing there):
    use `--portales linkedin` and say plainly which sources do not fit instead of re-running them.
  - *Searching the web in general* (companies, salaries, anything else): `web_search` works with no key (backend `keenable`).
  - *Reading job portals* (ZonaJobs, Bumeran, Computrabajo, LinkedIn jobs...): use **`browse-page <url> --links`**
    (real Chromium with a normal browser fingerprint, tested on those four). A results page: `browse-page
    "https://www.zonajobs.com.ar/empleos-busqueda-devops.html" --links --scroll 1`; then open a posting's URL for the
    detail. Prefer this over `web_extract` and over `browser_exec` (the only browser tool left in Hermes v0.23): both are blocked by Cloudflare on ZonaJobs
    ("Sorry, you have been blocked") and `web_extract` returned an error page.
  - Search URL recipes behind `buscar-empleos` (verified; do not guess others, guessed ones returned empty pages):
    - ZonaJobs: `https://www.zonajobs.com.ar/empleos-busqueda-<palabras-con-guiones>.html` (e.g. `...-busqueda-devops.html`)
    - Bumeran: `https://www.bumeran.com.ar/empleos-busqueda-<palabras-con-guiones>.html` (same platform as ZonaJobs)
    - Computrabajo: `https://ar.computrabajo.com/trabajo-de-<palabras>` and `...-en-<zona>` (e.g. `trabajo-de-devops-en-capital-federal`)
    - LinkedIn (public, no login): `https://ar.linkedin.com/jobs/<palabras>-jobs-argentina`
    Run with `--links`: the posting URLs are in the link list (ZonaJobs/Bumeran `/empleos/<slug>-<id>.html`, Computrabajo
    `/ofertas-de-trabajo/oferta-de-trabajo-de-...`, LinkedIn `/jobs/view/...`). Then read one posting with
    `browse-page <posting-url> --max 6000`. Add `--scroll 2` if a list looks short.
  - *A posting on an ATS* (Greenhouse, Ashby, Lever...): `node /workdir/jobfinder/fetch-jd.mjs <url>` is cleaner.
  - Never say a key is missing or a site is down without having tried `browse-page`. If it prints the anti-bot warning,
    say plainly that this site blocked access and offer the alternative (another portal, or the person pastes the text).
  - One page at a time, a couple of seconds apart: this is a person's job search, not a crawler.
  - Few results for a role: ZonaJobs category pages list more than a keyword search, e.g.
    `https://www.zonajobs.com.ar/empleos-area-tecnologia-sistemas-y-telecomunicaciones.html` (add
    `-modalidad-remoto` before `.html` for remote). Read them with `browse-page ... --links` and keep the `/empleos/` links.
  - Pay frequency (local work): weekly pay ("pago semanal") is rare in Argentine postings, most are monthly.
    Search the role first, then filter; "quincenal" finds more than "semanal".

## LinkedIn: load this skill and search, never answer "I can't"

Whenever the person mentions LinkedIn (looking for jobs there, a LinkedIn posting link, "search LinkedIn"), this skill
applies. **Do the search first**, then talk:

- Jobs: `buscar-empleos "<palabras>" --portales linkedin [--zona "<texto>"]`, then `browse-page <posting-url> --max 6000`
  for the detail of the ones that fit. A pasted `linkedin.com/jobs/view/...` link: `browse-page` it directly.
- LinkedIn has no usable open API (job/profile/message APIs are partner-only) and the public pages need no login:
  do not say "LinkedIn has no API" or "I have no access" as the answer, and **do not ask for a LinkedIn login or
  set up the browser vault** for this. Do not call `browser_vault` for LinkedIn.
- Only for things that truly require being logged in (Easy Apply, her own connections/messages, jobs hidden behind the
  login wall): say that one specific thing needs her account, and offer the alternative (she pastes the posting text or
  her profile text/CV, or you search the other portals). If `browse-page` prints the login wall or anti-bot warning
  for a given page, report just that page and keep going with the others.
