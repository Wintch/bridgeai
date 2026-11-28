# Two versions of a change (website)

## Two versions ("probá dos versiones", "mostrame A y B")
1. Make version A in the files. `gateway web variante guardar a-estrellas` keeps it (a local branch, never published)
   and puts the working copy back to the published site.
2. Make version B. `gateway web variante guardar b-copos`.
3. Show each in turn: `gateway web variante usar a-estrellas`, then `gateway web vista`, send; then
   `gateway web variante usar b-copos`, `gateway web vista`, send. Ask which one they want (or "ninguna").
4. The chosen one: `gateway web variante usar NAME`, then `gateway web publicar "..."`. Afterwards
   `gateway web variante borrar` the others (or keep them if the person wants to come back to them).
- Names: lowercase letters, digits and hyphens. `gateway web variante lista` shows what is saved and which one is in the
  working copy. Unsaved edits are never thrown away to switch: save them as a variant first, or `descartar`.
- "ya no encaja con el sitio publicado": the person changed the same files elsewhere since; redo the change on top.
- `variante guardar NAME --reemplazar` overwrites a variant with the same name.
