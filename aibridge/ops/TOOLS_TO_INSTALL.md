# Herramientas que faltan (lista viva)

Cada vez que Claude o un agente Hermes necesita algo que no está instalado, se anota acá con quién lo pidió,
dónde falló y cómo instalarlo. Lo que dice **host** requiere sudo en VM105; lo que dice **imagen** ya está
puesto en el Dockerfile y llega con el próximo rebuild.

## Para instalar vos (host VM105, necesita sudo)

| Herramienta | Para qué | Dónde falló | Instalar |
|---|---|---|---|
| `bc` | cronometrar arranques en scripts de shell (restas con decimales) | VM105, `ssh aibridge@... 'bc'` → `bc: command not found` (2026-10-07) | `sudo apt install bc` |
| regla de firewall puerto 3099 | que nginx (contenedor) alcance al despertador del host | `curl` desde `aibridge-web` a `172.21.0.1:3099` → timeout (ufw descarta INPUT desde redes docker) | `sudo ufw allow from 172.21.0.0/16 to any port 3099 proto tcp` |

## Imagen de Hermes (Dockerfile.hermes-agent-base)

| Herramienta | Para qué | Dónde falló | Estado |
|---|---|---|---|
| `ripgrep` (`rg`) | `search_files` de Hermes se niega a buscar en amplio sin `rg` | herand 8x, hereug 3x | agregado, falta rebuild y recrear |
| `uuid-runtime` (`uuidgen`) | nombres de directorios en `/web-outputs/<uuid>/` | herand 2x, hereug 3x | agregado, falta rebuild y recrear |
| `procps` (`pkill`, `pgrep`) | reiniciar el gateway de Hermes sin buscar PIDs en `/proc` | hernik, 2026-10-07 (`pkill: not found`) | agregado, falta rebuild y recrear |

## Decididas a propósito (no instalar salvo que cambies de idea)

| Herramienta | Por qué no |
|---|---|
| `pdflatex` / texlive | son varios GB; los PDF se hacen con weasyprint o `generate-pdf.mjs`. Falló 5x en herand y hereug cuando el agente lo intentó |
