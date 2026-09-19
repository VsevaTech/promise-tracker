# Example conversations

| File | What it demonstrates |
| --- | --- |
| `conversation_ru.txt` | 20 synthetic messages → 3 commitments: two with exact dates ("завтра до 18:00", "до пятницы") and one with none ("по срокам вернусь отдельно") that lands in **Needs confirmation**. |
| `conversation_en.txt` | English wording, a weekday deadline and an absolute date, plus hedged statements ("I can't promise a fix date today") that are deliberately not extracted. |

Every name, company and figure here is invented. Nothing comes from a real conversation.

```bash
curl -s localhost:8000/api/extract \
  -H 'content-type: application/json' \
  --data "$(python -c 'import json,sys;print(json.dumps({"conversation":open("examples/conversation_ru.txt").read(),"reference_date":"2026-09-14"}))')" | jq
```
