# Promise Tracker

Paste a conversation — a support thread, a client email chain, a Telegram export — and get back
the **commitments** hiding in it: who promised what, to whom, by when, and the quote that proves
it. Confirm the ones that matter, download an `.ics`, and the promises land in your calendar.

Unlike a task manager, you never retype anything out of the correspondence.

```
conversation → Extract promises → Confirm → Calendar
```

## The one rule that makes it trustworthy

**The AI never computes a date.**

The model is only allowed to copy the deadline *wording* out of the message — `"завтра"`,
`"до пятницы"`, `"by Friday"`, `"25 сентября"`. Turning that wording into a calendar date is plain
deterministic Python ([`app/dates.py`](app/dates.py)), anchored on the timestamp of the message it
came from, and covered by unit tests.

Two consequences:

* **No invented deadlines.** `"Исправим расхождение в отчёте, по срокам вернусь отдельно"` is a
  real commitment with no date. It is shown as **Needs confirmation**, not as a plausible-looking
  Friday. Wording that cannot be resolved to exactly one day — `"на следующей неделе"`, or
  `"до пятницы"` said *on a Friday* — gets the same treatment, with the reason spelled out.
* **Hallucinations cannot reach your calendar.** The extraction schema has no date field at all,
  and any deadline wording that does not literally occur in the conversation is discarded
  (`not_in_source`).

Every commitment carries its `source_quote`, and every field stays editable before export.

## What counts as a commitment

| Extracted | Not extracted |
| --- | --- |
| `Отправлю договор завтра до 18:00.` | `Когда будет договор?` (a question) |
| `Вернёмся с расчётом до пятницы.` | `Постараюсь посмотреть логи, но не обещаю.` (hedged) |
| `We'll return the questionnaire on 25 September.` | `I can't promise a fix date today.` |

## Quick start

```bash
git clone https://github.com/VsevaTech/promise-tracker.git
cd promise-tracker
cp .env.example .env          # optional — the app runs without any key
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
# → http://localhost:8000
```

Docker:

```bash
cp .env.example .env
docker compose up --build     # → http://localhost:8000
```

Then paste [`examples/conversation_ru.txt`](examples/conversation_ru.txt) with reference date
`2026-09-14`. 20 messages in, you get three commitments: two with exact dates
(2026-09-15 18:00 and 2026-09-18) and one flagged **Needs confirmation** — and the `.ics` holds
exactly two reminders.

## Two extraction engines

| Engine | When it runs | Trade-off |
| --- | --- | --- |
| **Gemini** (`app/services/ai.py`) | `GEMINI_API_KEY` is set, or `EXTRACTOR=gemini` | Free tier; better recall on messy wording |
| **Rules** (`app/services/rules.py`) | no key, `EXTRACTOR=rules`, or any AI failure | Zero dependencies, fully offline, lower recall |

A quota error, a timeout or schema-breaking output never crashes the app: it falls back to the
rule-based extractor and says so in the UI. The AI layer is isolated behind one module, so
swapping the provider touches a single file.

## Configuration

All of it comes from the environment — see [`.env.example`](.env.example). Nothing is hardcoded,
including the model id.

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | *(empty)* | Free-tier key from [AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | *(empty)* | e.g. `gemini-3.5-flash` |
| `EXTRACTOR` | `auto` | `auto` \| `gemini` \| `rules` |
| `DEFAULT_DUE_TIME` | `09:00` | Time used when a deadline named a day but no hour |
| `ALARM_MINUTES_BEFORE` | `60` | `VALARM` lead time; `0` disables it |
| `MAX_CONVERSATION_CHARS` | `60000` | Input cap |

## Privacy

* Conversation text is sent to Google Gemini **only when you configure a key**. With no key the
  app is fully local.
* Nothing is persisted: no database, no uploaded files on disk, no conversation in the logs. The
  text lives for the duration of one request.
* The API key is read from the environment only, never logged, never stored, and `.env` is
  git-ignored.
* Tests and CI never contact an AI provider — Gemini is mocked.

## HTTP API

```bash
curl -s localhost:8000/api/extract -H 'content-type: application/json' \
  -d '{"conversation":"[2026-09-14 10:07] Сергей: Отправлю договор завтра до 18:00.","reference_date":"2026-09-14"}'
```

```json
{
  "engine": "rules",
  "commitments": [{
    "speaker": "Сергей",
    "what": "Отправлю договор завтра до 18:00",
    "due_expression": "завтра до 18:00",
    "source_quote": "Отправлю договор завтра до 18:00.",
    "due_date": "2026-09-15",
    "due_time": "18:00:00",
    "status": "resolved",
    "reason": "ok"
  }]
}
```

`GET /healthz` reports the active engine.

## Supported deadline wording

Russian and English, resolved relative to the message timestamp: `сегодня`, `завтра`,
`послезавтра`, `через N дней/недель/месяцев`, `до/к <weekday>`, `до конца недели/месяца`,
`25 сентября`, `25.09.2026`, `2026-09-25`, `today`, `tomorrow`, `in N days`, `by Friday`,
`end of the month`, `Sep 25` — each optionally with a clock time (`завтра до 18:00`, `by Friday 5pm`).

Anything else becomes **Needs confirmation** with a machine-readable reason: `no_deadline`,
`unparseable`, `ambiguous_weekday`, `ambiguous_year`, `no_anchor`, `not_in_source`.

## Development

```bash
pytest          # 104 tests, no API key needed
ruff check .
ruff format --check .
docker build -t promise-tracker .
```

## Layout

```
app/
  dates.py        deterministic deadline resolution — the heart of the project
  parsing.py      chat exports → messages
  models.py       extraction schema (deliberately has no date field)
  extractor.py    parse → extract → resolve, plus the hallucination guard
  ics.py          iCalendar export
  services/
    ai.py         Gemini structured output, isolated
    rules.py      offline fallback extractor
examples/         synthetic conversations
tests/            unit + API tests, Gemini always mocked
```

## License

MIT — see [LICENSE](LICENSE).
