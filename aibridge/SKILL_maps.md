---
name: maps
description: "Places, routes and map pictures with checked coordinates: `gateway mapa buscar|cerca|puntos|ruta|donde`. Use it for any where-is, how-do-I-get-there or mark-it-on-a-map request instead of web search coordinates or a hand-made HTML map."
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
- `gateway mapa cerca cerveza` (or `supermercado`, `almacén`, `bar`, `café`, `farmacia`, `cajero`, `heladería`...): the
  nearest places of a KIND around the person's last pin, from OpenStreetMap, with distance, mapped opening hours and a
  picture. Use it for "where can I buy / find X around here". `buscar` matches NAMES: on 2026-11-01 "almacén kiosco
  cerveza" with `buscar` returned shops called "Kiosco Almacén" 17 km away, and the bot said the nearest supermarket
  was 3 km off while two shops selling drinks were 250 m away. Each line says whether the place is open now ("abierto, cierra 23:00" / "cerrado, abre mañana 09:00"), open ones come first and closed ones last: lead with what is open and mention a closed one only if nothing open is near. Mapped hours can be old: say "probably open", not "open".
- `gateway mapa puntos "Plaza X" "Calle Y 1234, Palermo" "-34.6083,-58.3712"`: several places, numbered, on one picture.
- `gateway mapa ruta aquí "Parque Centenario" --modo transporte`: the route. `--modo pie` (default), `auto` or `bici`
  print distance, time and steps; `transporte` prints the Google Maps link that routes buses, trains and the subte with
  real lines and times (no free service does that from here). Every route also draws the picture.
- `gateway mapa donde` (or `donde "-34.60,-58.38"`): the street address, barrio and town of the person's last pin or
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
- Never build an HTML, Leaflet or Folium map, even when an interactive page is asked for: say the command draws a
  picture and gives a link per place (Google Maps opens them interactively), and send those.
- **Do not draw a map yourself with Folium, Leaflet, matplotlib, staticmap or tiles you fetch.** On 2026-11-02 the model
  reached for Folium in 9 different tool calls in one night, and `folium` is not installed in `execute_code` (it failed there at
  least twice); on 2026-10-31 a hand-made page also had its pins off and its tiles refused (OpenStreetMap 403, CARTO "API KEY
  REQUIRED"). Any set of places is
  `gateway mapa puntos "A" "B" "C"` (numbered pins, one picture, a link per place), a route is `gateway mapa ruta`,
  what is around a point is `gateway mapa cerca KIND`. If the person wants something the command cannot do (colours per
  category, a layer, an interactive page), say what it cannot do and offer the picture plus links; do not improvise.
- Around a point that is not the person's pin: `gateway mapa cerca supermercado --cerca "-34.60,-58.38"` (the KIND comes
  first, the point goes in `--cerca`). A pair of coordinates written where the KIND goes is accepted as the point, but
  with no kind the command only explains this and searches nothing.

## Venues and events nearby

The person reads on a phone while walking. List at most five, today's and what is open now first (`cerca` marks open and closed), one short line each; leave out the kinds they said they do not want and other days unless asked. Put the link on the line: the venue's site, the ticket page (Passline...), the profile. Social accounts always as a full link (`https://instagram.com/name`), never a bare `@name`: in Telegram that is a Telegram username and opens nothing. Look first where it is open: the venue's website, the ticket site, a Telegram channel page (`https://t.me/s/name`). Instagram and Facebook show no posts without a login: say so in one sentence, ask for a screenshot of the post and read it with `vision_analyze`; no talk about terms of service.
