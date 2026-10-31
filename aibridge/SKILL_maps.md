---
name: maps
description: "Places, routes and map pictures with checked coordinates: `gateway mapa buscar|puntos|ruta`. Use it for any where-is, how-do-I-get-there or mark-it-on-a-map request instead of web search coordinates or a hand-made HTML map."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [maps, geocoding, route, directions, transit, location]
---

# Maps

On 2026-10-31 a model took coordinates from web search results, drew them on a Leaflet HTML page, and the pins landed
in the wrong places; the page then failed on a computer (OpenStreetMap tiles: 403, CARTO: "API KEY REQUIRED"), and the
bus lines and frequencies it gave were guessed. One command does all of it right:

- `gateway mapa buscar "Reserva Ecológica Vicente López"`: up to 3 matches with address, coordinates, distance from
  the person's last pin, and a Google Maps link. Nearest to the person first; `--cerca PLACE` to look elsewhere.
- `gateway mapa puntos "Plaza X" "Calle Y 1234, Florida" "-34.53,-58.49"`: several places, numbered, on one picture.
- `gateway mapa ruta aquí "Parque Centenario" --modo transporte`: the route. `--modo pie` (default), `auto` or `bici`
  print distance, time and steps; `transporte` prints the Google Maps link that routes buses, trains and the subte with
  real lines and times (no free service does that from here). Every route also draws the picture.
- `gateway mapa donde` (or `donde "-34.52,-58.48"`): the street address, barrio and town of the person's last pin or
  of a point. Use it whenever you say where someone is.
- A PLACE is a text, `lat,lon`, or `aquí` for the person's last location pin (the track file).
- It works with or without a Geoapify key: without one (or when its daily quota ends) it searches with Photon and
  OpenStreetMap, routes with OpenStreetMap's router and draws the picture itself. Same commands, same output. Only
  when that keyless path could not answer does it print a 💡 line suggesting the person's own free key: pass that on
  once, in one sentence; never bring it up otherwise.

Rules:
- **Never write coordinates yourself**, not from memory and not from a web page. If `gateway mapa` does not find a place
  it says so: ask for the street, the barrio or the town and search again.
- **Never name a street, barrio or town from coordinates yourself**: on 2026-10-31 a pin was given a barrio 10 km
  off. Run `gateway mapa donde`.
- A name that came from a voice note may be misheard ("до Кото", to Coto, arrived as "Дакота" and matched towns in the
  US). When every match is far away the command says so: think of a nearby shop or place that sounds alike and search
  that, or ask.
- Never state bus numbers, train branches or frequencies that did not come from the link or a page you read in this
  turn; for public transport, send the link and say it opens the real route with the times of right now.
- Send the picture: the command prints `Imagen del mapa: PATH`; write `MEDIA:PATH` in your reply (the picture and the
  links open on any phone or computer). Put the "open the route" link in the same reply.
- Do not build HTML or Leaflet maps unless the person asks for an interactive page; a picture plus the link is what
  works everywhere.
