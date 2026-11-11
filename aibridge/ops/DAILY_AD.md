# Daily ad: "Persona del día" (`ops/daily_ad.py`)

A way to carry ads that helps the community instead of selling it: once a day, right after a person's
assistant wakes up because they wrote to it, the bot shows **one service made by another person who uses bridgeai**, as
a Telegram message with the link preview of that service's website.

```
📣 Persona del día (anuncio)

Esculturas y objetos hechos a mano
https://<their site>/

Un servicio de alguien que también usa bridgeai. Sale una vez por día, al despertar.
        [ link preview: the site's og:image, title and description, drawn by Telegram ]
```

The label is in the person's language (`es` Persona del día / anuncio, `en` Person of the day / ad, `ru` Человек дня /
реклама). It always says it is an ad.

## Rules (enforced in the code, tested in `ops/daily_ad_selftest.py`)

| Rule | Why |
|---|---|
| Opt-in for the reader: a stack gets ads only when it is listed in `"stacks"` of `ops/ads.json`. | Nobody gets ads they did not agree to. |
| Opt-in for the advertiser: an ad runs only with a `"consent"` date (the day its owner agreed); `"until"` ends it. | Promoting someone's service needs their yes, and an end date. |
| Only after a wake caused by the person's own Telegram message: never a cron wake, never the web chat, never a message out of the blue. | It shows up only when the person is already opening the chat. |
| At most once per local day per stack (`"tz"`, default `America/Argentina/Buenos_Aires`; set your own). | Once a day is the whole budget. |
| Sent `"delay_s"` seconds after the wake (default 20). | "Listo para trabajar" and the answer to the waiting message come first. |
| Never the person's own ad (`"owner_stacks"`); round-robin over the ads that are active, consented and not expired. | Fair turns, nothing odd. |
| Only to the stack's own allowed Telegram user. | The bot never writes to anyone else. |
| A plain `https` URL and fixed text; no tracking parameters, no counting of clicks. | Nothing about the reader leaves the server; Telegram's servers fetch the preview, not the person's phone. |
| The bot token travels only inside the request; it is never printed or logged. | As every other ops tool. |

## Files

- `ops/ads.json` (VM, not in git; copy `ops/ads.json.example`): `enabled`, `stacks`, `tz`, `delay_s`, `ads` (`id`, `url`,
  `title` as text or `{es, en, ru}`, `owner_stacks`, `consent`, `until`, `active`).
- `ops/ads_state.json` (written by the tool, 0600): per stack, the last day an ad was shown, which one, and the next turn.
- `ops/daily_ad.log`: one JSON line per send or skip (stack, ad id, language; never message text or tokens).
- `ops/wake/on_wake.d/30-daily-ad`: the waker hook. It exits at once unless the wake reason is `telegram`, there is a chat
  id and `ops/ads.json` exists; then it runs `daily_ad.py wake` in the background.

## Operate (VM, as the stack user, in `~/aibridge`)

```
cp ops/ads.json.example ops/ads.json     # then edit: the ads, and the stacks that agreed
python3 ops/daily_ad.py check            # validates the file and fetches each site's og:title, og:description, og:image
python3 ops/daily_ad.py test --stack NAME [--id AD]   # one ad now, to that stack's person (does not use up the day)
python3 ops/daily_ad.py status           # what each stack saw last and the next ad in turn
```

A site with no `og:image` still works, but Telegram then shows a small preview or none: ask its owner to add the tags
(`check` says which are missing). The waker only needs the hook file to be executable; nothing restarts.

## Not built

- **The reader's own switch.** The opt-in is the operator's list. A `/anuncios off|on` command in the bot (and a line in `/ayuda`) would let a person stop it without asking.
- **The web chat** shows nothing: a small banner on wake would be the equivalent, also at most once a day.
- **Fair rotation.** Ads are picked by hand; a fair rule (same length for everyone, in turn) is needed before there are more than a handful.
- **Privacy notice.** An ad of a friend's own service shown to people who agreed is close to a recommendation, but it is still advertising in the reader's chat: say so in your privacy notice. The tool stores only the last day and ad id per stack.
