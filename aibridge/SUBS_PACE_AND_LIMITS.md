# Subtitle downloads: pace, limits and times

The address the machines leave through is valuable and cannot be replaced quickly, so `subs-fetch` is paced for the address first and for the hours saved second.
This file is the reference for every number. The code is `subs_fetch.py` (and `subs_new.py` for the schedule); the rules for the agent are in `SKILL_downloads.md`;
the design notes are in `HERMES_ARCHITECTURE.md` ("Subtitle pace, the sweet spot", "more than one egress").

## Pace (pauses between the site's requests)

| Pace | `--sleep-requests` | `--sleep-subtitles` | About, per video | Two channels at once | Status |
|---|---|---|---|---|---|
| `fast` | 0.5 s | 1.5 s | 4 s | | never use on a real backlog |
| `normal` | 1 s | 2.5 s | 6 s | ~300 an hour measured | ran a whole day on a fresh address, then a soft block when pushed to 5 channels |
| `slow` | 2 s | 6 s | 11 s | ~590 an hour measured (~0.3 requests a second) | held for an hour with no event |
| `gentle` | 8 s | 20 s | 17 s with no captions, ~37 s with captions | ~200 an hour expected (~0.1 requests a second) | DEFAULT since 2026-11-21 (`SUBS_PACE`) |

The `ios` client costs 2 requests a video plus one caption download when captions exist. The figures for `gentle` are expected, not measured yet: the ledger
(below) turns them into measured ones.

## Limits and times (defaults; the environment variable changes each)

| What | Value | Variable |
|---|---|---|
| Channels downloading at once | 2 | `SUBS_SLOTS` |
| Rest after a rate limit (HTTP 429, "confirm you're not a bot"), shared by every instance, extend-only, the job ends with exit 75 | 120 min | `SUBS_COOLDOWN_MIN` |
| Rest after a soft block (captions silently held back), always longer than the rate-limit rest | 240 min | `SUBS_SOFT_COOLDOWN_MIN` |
| Soft-block detector (`NocapGuard`): window, share of caption-less videos that trips it, minimum seen | 30 videos, over 50 %, 20 | in code |
| Canary before a soft-block verdict: videos of the same channel that already have captions asked again, checks a run | 3, at most 10 | `CANARY_N`, `CANARY_MAX` |
| A "no captions" answer is remembered, then asked again after | 14 days | `NOCAPS_RETRY_DAYS` |
| A private, members-only or removed video is remembered, then asked again after | 14 days | `UNAVAILABLE_RETRY_DAYS` |
| A channel listing is reused for | 6 h | `IDS_CACHE_HOURS` |
| `--new` looks at the newest videos of each channel | 40 | `RECENT` |
| `--backlog N`: no channel gets a slice smaller than | 20 videos | in code |
| Schedule `subs-nuevos` | every 3 h: `--all --new`, then `--all --backlog 170`, 55 min in all | `SUBS_BACKLOG_PER_RUN` |
| Stall alarm: the person is told once when the missing count has not dropped for | 24 h | `SUBS_STALL_HOURS` |
| Client | `ios` (needs `--ignore-no-formats-error`, see below) | `SUBS_CLIENT` |

## Request rates seen (the evidence behind the defaults)

- 5 to 6 channels at once, 3 requests a video, ~0.95 requests a second (~1,100 to 1,300 videos an hour): ran for hours on two days without a block, then on a fresh start the
  site answered 95 % of the videos without captions (a soft block). The first backlog at ~1,500 videos an hour wrote 4,250 false "no captions".
- 2 channels, `normal`, `ios`: ~0.4 requests a second, ~300 videos an hour: a whole day without an event on a fresh address.
- 2 channels, `slow`, `ios`: ~0.3 requests a second, ~590 videos an hour for about an hour, no event.
- A marked address answers about 15 videos a round and then rate-limits; the canary does not change that.

## Two failures that looked like a block and were not

1. A soft block is real, but a long run of caption-less videos at the end of a channel is normal (shorts, streams). The canary tells them apart.
2. With the `ios` client the site can answer with pictures only (SABR). yt-dlp then ends with `Requested format is not available` BEFORE it writes the captions it found,
   so a command without `--ignore-no-formats-error` gets nothing on videos that have captions. The canary command lacked it for a week and called every backlog tail a soft block.
   Both commands carry the flag now and a selftest checks it.

## The ledger and the rule for changing the pace

Every finished channel run appends one line of numbers to `.subs-metrics.jsonl` beside the channels (time, pace, slots, seconds, videos, new files, errors, outcome `ok`,
`limited` or `soft`; no channel name). `subs-fetch --pace-report PARENT` sums it per day: videos an hour per channel running, and the rate limits and soft blocks.

Rule: a pace stays for a full day with a CLEAN report before one step up is tried (`gentle` to `slow`, or 2 to 3 slots; one change at a time). Any rate limit or soft block puts it back one
step and the day counts again. The pace is never raised because a backlog is long; adding channels lengthens the backlog and does not raise the request rate.

## Time to finish

Videos missing divided by the speed of the pace. At `gentle`, about 200 an hour with the manual run and about 55 an hour from the schedule alone (170 videos every 3 h): 3,500 videos
take ~18 hours with a manual run going, ~2.5 days with the schedule alone. Each new channel adds its missing videos to the same budget.

## yt-dlp version

The image pins yt-dlp on the nightly channel (yt-dlp-nightly-builds) with its SHA-256, on purpose, while the site keeps changing; it moves back to the stable release when that catches up.
