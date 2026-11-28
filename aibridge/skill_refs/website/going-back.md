# Going back to an earlier version (website)

## Going back ("volvé a como estaba ayer", "al backup del lunes")
- `gateway web volver ayer` (also `anteayer`, `el lunes`, `hace 3 días`, `2026-11-07`, `07/11/2026`; a weekday is the last one
  before today): lists the publishes of that day (hash, time, message), picks the last one up to the end of that day
  and puts those files in the working copy as they were, WITHOUT publishing. Then the normal flow: `vista`, send the
  pictures, ask "¿publico?", and on their yes `gateway web publicar "Volver a como estaba el AAAA-MM-DD"` (the exact
  message the command printed; add `--borrar` when it listed files that would be deleted). The result is a NEW commit on top:
  history is never rewritten and `gateway web deshacer` undoes it. `gateway web descartar` leaves things as they were.
- **Dates are commit times, not the moment of the upload.** A change made offline or left unpushed carries the day it
  was made. So read the list the command prints: if the person means another publish of that day (the last one may be
  the broken one), pick it by its code, `gateway web volver 1a2b3c4`; the codes are also in `gateway web estado`. Tell the
  person which publish you chose (its time and message) when you show the pictures.
- `gateway web volver ayer --directo` checks, publishes and verifies at once, with no pictures. Use `--directo` ONLY
  when the person said to publish it without looking ("volvelo directo", "publicalo ya"); otherwise it is the same
  as publishing something unseen.
- Files that did not exist on that day would be deleted: the command lists them all. Show the list to the person and
  use `--borrar` (with `publicar`, or with `--directo`) only if they agree. Pages published from elsewhere after that day,
  and any work not published, need care: the command refuses while there are unpublished changes (publish, `variante
  guardar`, or `descartar` first).
- "no tenía ninguna publicación hasta..." = the site is younger than that date; tell them the first date.
