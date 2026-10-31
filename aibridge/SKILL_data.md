---
name: live-data
description: "Weather, dollar rates, holidays, inflation, Wikipedia, planes overhead and headlines from one named structured source each: `gateway dato`. Use it before web search for any of these."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [weather, forecast, dollar, exchange-rate, holidays, inflation, wikipedia, planes, adsb, news, rss]
---

# Live data

Web search mixes pages and dates: on 2026-10-31 the bot gave "2% to 47% rain depending on the source". For these
questions run `gateway dato` in the terminal first; it prints the numbers and names the source. No key is needed
(except for `pelis`, below).

- `gateway dato clima [PLACE] [--dias N]`: now, and each day (up to 14) with the rain chance of the two big models
  side by side (ECMWF / GFS), millimetres, wind, UV, sunrise and sunset, and air quality now. PLACE is a text, `lat,lon` or `aquí`; with
  none it uses the person's last pin, else downtown Buenos Aires. When the two models disagree, say so in one line
  ("the European model says 10%, the American 60%"); do not average them or pick one silently.
- `gateway dato dolar`: oficial, blue, MEP (bolsa), CCL, mayorista, cripto, tarjeta, with the update time, a second
  source for the blue, and EUR/BRL/CLP/UYU.
- `gateway dato economia`: last monthly inflation (INDEC) and the months before, riesgo país, UVA.
- `gateway dato feriados [CC]`: next public holidays in Argentina; `ru`, `uy`, `es`... for another country.
- `gateway dato wiki TEXT [--lang es|ru|en]`: the Wikipedia summary and its link (the person's language by default).
- `gateway dato aviones [PLACE] [--km 15]`: aircraft overhead right now: flight code, registration, type, altitude,
  speed, heading, distance. Open ADS-B data has no schedules or origin/destination: look up the flight code on the web
  for that, and say which part came from where.
- `gateway dato noticias [ar|ru|mundo]`: headlines with links from the outlets' RSS feeds. Give titles and links;
  never paste or rewrite whole articles.
- `gateway dato pelis [TITLE]`: in cinemas in Argentina now, or one movie/series with its rating, plot and where it
  streams in Argentina (TMDB). That needs the person's own free TMDB key; without it you get the Wikipedia summary
  and, at most once a week, a 💡 line suggesting the key: pass it on once, in one sentence, never insist. If they say
  no, run `gateway servicios no tmdb`.

If a source is down the command says so: tell the person, and if you then use a web search, say that those numbers
come from a web page, not from the source. Supermarket prices, cinema showtimes, parcel tracking, SUBE balance, train
timetables and SMN alerts have no reliable source here: say so instead of quoting a random page as fact.
