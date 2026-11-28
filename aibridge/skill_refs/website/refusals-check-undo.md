# What publicar refuses; check, undo, start over (website)

## What publicar refuses, and what to do
- **A `.css`/`.js` changed but the page still loads it with the same `?v=`:** raise that number in the HTML (e.g.
  `style.css?v=17` -> `?v=18`). Cloudflare keeps those files 4 hours by their URL; without it nobody sees the change.
- **A file would be deleted:** only if the person asked for exactly that, repeat with `--borrar`. Otherwise put it back
  (`git -C /workdir/web/<site> restore FILE`, the one git command allowed besides `gateway web`).
- **A `.bak`, `~` or temp file:** never keep copies inside the site folder (they would be public). The history is the
  backup: every publish can be undone.
- **Over 25 MiB:** recompress it (video, big image); Cloudflare Pages does not take it.
- **"cambió los mismos archivos desde otro lado (FILES)":** the person changed those files elsewhere. Nothing was
  published; tell them which files, and ask which version they want. To keep the published one:
  `gateway web descartar` (your unpublished work is kept in a `hermes-guardado-*` branch, the site does not change),
  then redo the change on top if they still want it.
- **"marcas de conflicto":** a file has `<<<<<<<` / `>>>>>>>` lines; fix the file by hand, never publish it like that.

## Check, undo, start over
- `gateway web verificar`: whether the last publish is what the site serves now. Use it after "does not show yet",
  a few minutes later; `estado` only says the home page answers, which proves nothing about the change.
- `gateway web deshacer`: reverts YOUR last publish (never a change the person pushed from elsewhere) and publishes
  again; it prints which one. For another one: `gateway web deshacer COMMIT`, with the code from the `estado` list
  (check the name next to it). "no se puede deshacer limpio" = later changes touch the same lines: nothing was
  published; ask the person what should stay. Offer `deshacer` whenever the person does not like a change.
- `gateway web descartar`: drops what is not published yet and goes back to the published site (kept in a branch).
