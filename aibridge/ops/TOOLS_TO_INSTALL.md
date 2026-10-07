# Herramientas que faltan (lista viva)

Cada vez que Claude o un agente Hermes necesita algo que no está instalado, se anota acá con quién lo pidió,
dónde falló y cómo instalarlo. Lo que dice **host** requiere sudo en VM105; lo que dice **imagen** ya está
puesto en el Dockerfile y llega con el próximo rebuild.

## Para instalar vos (host VM105, necesita sudo)

| Herramienta | Para qué | Dónde falló | Instalar |
|---|---|---|---|
| `bc` | cronometrar arranques en scripts de shell (restas con decimales) | VM105, `ssh aibridge@... 'bc'` → `bc: command not found` (2026-10-07) | `sudo apt install bc` |
| ~~regla de firewall puerto 3099~~ | que nginx (contenedor) alcance al despertador del host | hecho 2026-10-07: ufw para hernik y `docker-user-fw.sh` (pinhole por guest) | cada stack nuevo: volver a correr `sudo /usr/local/sbin/docker-user-fw.sh` |

## Imagen de Hermes (Dockerfile.hermes-agent-base)

| Herramienta | Para qué | Dónde falló | Estado |
|---|---|---|---|
| `ripgrep` (`rg`) | `search_files` de Hermes se niega a buscar en amplio sin `rg` | herand 8x, hereug 3x | en la imagen; hernik ya la usa; recreados, ya la tienen |
| `uuid-runtime` (`uuidgen`) | nombres de directorios en `/web-outputs/<uuid>/` | herand 2x, hereug 3x | en la imagen; hernik ya la usa; recreados, ya la tienen |
| `procps` (`pkill`, `pgrep`) | reiniciar el gateway de Hermes sin buscar PIDs en `/proc` | hernik, 2026-10-07 (`pkill: not found`) | en el Dockerfile de la base; en la imagen (recreados los 3 el 2026-10-07)

## Decididas a propósito (no instalar salvo que cambies de idea)

| Herramienta | Por qué no |
|---|---|
| `pdflatex` / texlive | son varios GB; los PDF se hacen con weasyprint o `generate-pdf.mjs`. Falló 5x en herand y hereug cuando el agente lo intentó |
