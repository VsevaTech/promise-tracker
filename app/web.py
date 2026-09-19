"""Form parsing helpers for the confirmation step."""

from __future__ import annotations

from datetime import date, datetime, time

from app.models import Commitment, DueStatus, ResolutionReason


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value.strip())
    except ValueError:
        return None


def commitments_from_form(form: dict[str, list[str] | str]) -> list[Commitment]:
    """Rebuild the user-confirmed commitments out of the posted form.

    The user is the final authority: whatever date they left in the field wins,
    including one they typed for a commitment the extractor refused to resolve.
    """

    def values(key: str) -> list[str]:
        raw = form.get(key, [])
        return raw if isinstance(raw, list) else [raw]

    ids = values("id")
    selected = set(values("include"))
    confirmed: list[Commitment] = []

    for position, commitment_id in enumerate(ids):
        if commitment_id not in selected:
            continue

        def field(name: str, index: int = position) -> str:
            items = values(name)
            return items[index] if index < len(items) else ""

        due_date = _parse_date(field("due_date"))
        confirmed.append(
            Commitment(
                id=commitment_id,
                speaker=field("speaker").strip(),
                recipient=field("recipient").strip() or None,
                what=field("what").strip() or "Commitment",
                source_quote=field("source_quote").strip(),
                due_expression=field("due_expression").strip() or None,
                anchor=(
                    datetime.fromisoformat(field("anchor")) if field("anchor").strip() else None
                ),
                due_date=due_date,
                due_time=_parse_time(field("due_time")),
                status=DueStatus.RESOLVED if due_date else DueStatus.NEEDS_CONFIRMATION,
                reason=ResolutionReason.OK if due_date else ResolutionReason.NO_DEADLINE,
            )
        )
    return confirmed
