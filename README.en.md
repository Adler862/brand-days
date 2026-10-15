# brand-days

Recurring weekly/monthly promotions from mainland-China restaurant and retail chains
(e.g. KFC's "Crazy Thursday", monthly member days on the 8th) turned into a
**calendar that reminds you at 20:00 the evening before**.

A hand-verified dataset plus a small `.ics` generator. No push service, no third-party
dependency, no registration.

> This is **not** a scraper or a deal-aggregator. Every entry is manually verified and
> carries a `source` and `verified_at` field. Only **predictable, recurring** promotions
> are included — flash sales and random coupon drops are deliberately excluded, because
> they are meaningless in a calendar.

## Subscribe

Paste this URL into any client that supports "subscribe to calendar by URL"
(Google Calendar, Apple Calendar, Outlook, Thunderbird):

```
https://cdn.jsdelivr.net/gh/Adler862/brand-days@main/deals.ics
```

Served through jsDelivr because `raw.githubusercontent.com` is unreachable from many
networks in mainland China. jsDelivr caches for ~12 hours, so edits are not instant.

## Generate it yourself

Windows (PowerShell):

```powershell
git clone https://github.com/Adler862/brand-days.git
cd brand-days
python -m pip install -r requirements.txt
python gen.py                  # data/*.yaml -> deals.ics
python tools/test_gen.py       # recurrence rules and boundary tests
python tools/check_ics.py      # ICS structure checks (timezone, VALARM, folding)
```

Linux / macOS:

```bash
git clone https://github.com/Adler862/brand-days.git && cd brand-days
python3 -m pip install -r requirements.txt
python3 gen.py
```

## Notes

- The calendar is generated for a **365-day window**. Most Chinese Android calendar apps
  can only *import* `.ics`, not subscribe to it, and they discard event UIDs on import —
  so re-importing duplicates events. A long window keeps manual refreshes down to 0–2 per year.
- `VTIMEZONE` is embedded explicitly: without it, clients that cannot resolve the
  `Asia/Shanghai` TZID will shift every event by 8 hours **without reporting an error**.
- Events are generated concretely instead of using `RRULE`, because `RRULE` cannot express
  a cancelled week, an undecided date, or two time windows on the same day.
- Only entries marked `tier: core` + `confidence: verified` reach the calendar. Unfiltered,
  a week would contain 30+ events, and the whole calendar would simply get muted.

Data lives in `data/offers.yaml` (verified, recurring), `data/pending.yaml` (leads awaiting
verification) and `data/oneoff.yaml` (time-limited, documentation only).

Design rationale and verification notes: [SPEC.md](SPEC.md) (Chinese).
Full documentation: [README.md](README.md) (Chinese).

## License

MIT. Data is provided under the same terms — forks and PRs welcome.
