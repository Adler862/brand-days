# brand-days

Recurring weekly/monthly promotions from mainland-China restaurant and retail chains
(e.g. KFC's "Crazy Thursday", monthly member days on the 8th) turned into a
**calendar that reminds you at 20:00 the evening before**.

A hand-verified dataset with a small `.ics` generator. No push service, no registration,
and no dependency beyond PyYAML and icalendar.

> There is no scraper here, and this is not a deal aggregator. Every entry was verified by
> hand and carries a `source` and a `verified_at` field, so coverage is limited. Only
> **predictable, recurring** promotions are included; flash sales and random coupon drops
> are left out because a calendar can do nothing useful with them.

## Subscribe

Paste this URL into any client that supports "subscribe to calendar by URL"
(Google Calendar, Apple Calendar, Outlook, Thunderbird):

```
https://cdn.jsdelivr.net/gh/Adler862/brand-days@main/deals.ics
```

jsDelivr is used because `raw.githubusercontent.com` is unreachable from many networks in
mainland China. jsDelivr caches for ~12 hours, so edits are not instant.

## Generate it yourself

Windows (PowerShell):

```powershell
git clone https://github.com/Adler862/brand-days.git
cd brand-days
python -m pip install -r requirements.txt
python gen.py                  # data/*.yaml -> deals.ics + index.html
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

- The calendar is generated for a **365-day window**. Most Chinese Android calendar apps can
  only *import* `.ics` and cannot subscribe to one, and they discard event UIDs on import,
  so a re-import duplicates every event. The long window keeps manual refreshes down to
  0–2 per year.
- `VTIMEZONE` is embedded explicitly. `icalendar` writes only the `TZID=Asia/Shanghai`
  reference by default; a client that cannot resolve it shifts every event by 8 hours and
  reports no error at all.
- Events are generated concretely rather than with `RRULE`. `RRULE` cannot express a
  cancelled week, an undecided date, or two time windows on the same day, and working around
  that means maintaining an `EXDATE` list on the side.
- Only entries marked `tier: core` + `confidence: verified` reach the calendar. Unfiltered,
  a week would contain 30+ events and the whole calendar would get muted.

Data lives in `data/offers.yaml` (verified, recurring), `data/pending.yaml` (leads awaiting
verification) and `data/oneoff.yaml` (time-limited, documentation only).

Design rationale and verification notes: [SPEC.md](SPEC.md) (Chinese).
Full documentation: [README.md](README.md) (Chinese).

## License

MIT. Data is provided under the same terms — forks and PRs welcome.
