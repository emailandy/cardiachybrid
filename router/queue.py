"""
HITL Review Work-Queue API and Exemplar Store (D09).
Provides a work-queue API over fact_redcap_field for human verification,
generating deep links (-10s offset) and closing the A3 loop by writing
exemplars on human correction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import generated.redcap_fields as rf
from router.policy import _is_team_field


@dataclass(slots=True)
class QueueItem:
    case_id: str
    event_id: str
    field_name: str
    field_label: str
    ai_value: Any
    ai_label: str
    confidence: float
    abstain_reason: str | None
    source_event_ids: list[str]
    video_uri: str
    t_start_s: float
    event_type: str = ""
    required: bool = False
    difficulty: str = "MEDIUM"
    queue_class: str = "objective"  # 'objective' vs 'subjective'
    reviewed: bool = False
    human_value: Any | None = None
    final_value: Any = None
    human_verified_at: str | None = None
    human_verified_by: str | None = None
    note: str | None = None

    @property
    def deep_link(self) -> str:
        """Deep link landing the reviewer 10 seconds before the event."""
        start_offset = max(0.0, float(self.t_start_s) - 10.0)
        base = self.video_uri or "gs://resus-video/unknown.mp4"
        return f"{base}#t={start_offset:.1f}"

    def __post_init__(self) -> None:
        if self.final_value is None:
            self.final_value = self.human_value if self.human_value is not None else self.ai_value


@dataclass(slots=True, frozen=True)
class ExemplarRecord:
    case_id: str
    event_id: str
    field_name: str
    event_type: str
    ai_value: Any
    human_value: Any
    clip_t0: float
    clip_t1: float
    verified_by: str
    verified_at: str


class ExemplarStore:
    """In-memory / persistence store for A3 retrieval-augmented few-shot exemplars."""

    def __init__(self) -> None:
        self._records: list[ExemplarRecord] = []

    def add(self, record: ExemplarRecord) -> None:
        self._records.append(record)

    def get_by_event_type(self, event_type: str) -> list[ExemplarRecord]:
        """Retrieve exemplars matching the given event_type immediately after submission."""
        return [r for r in self._records if r.event_type == event_type]

    def get_by_field(self, field_name: str) -> list[ExemplarRecord]:
        return [r for r in self._records if r.field_name == field_name]

    def clear(self) -> None:
        self._records.clear()


class ReviewQueue:
    """HITL review queue managing QueueItems and writing corrections to ExemplarStore."""

    def __init__(self, exemplar_store: ExemplarStore | None = None) -> None:
        self._items: dict[tuple[str, str], QueueItem] = {}  # keyed by (case_id, field_name)
        self.exemplar_store = exemplar_store or ExemplarStore()

    def enqueue(self, item: QueueItem) -> None:
        """Add or update an item in the review queue."""
        # Determine queue_class: TEAM fields or team_score rule get 'subjective', else 'objective'
        if _is_team_field(item.field_name):
            item.queue_class = "subjective"
        else:
            item.queue_class = "objective"

        # Populate required and difficulty from dictionary if not explicitly set
        spec = rf.FIELDS.get(item.field_name)
        if spec:
            item.required = bool(getattr(spec, "required", item.required))
            item.difficulty = str(getattr(spec, "difficulty", item.difficulty)).upper()

        self._items[(item.case_id, item.field_name)] = item

    def next_item(self, reviewer_id: str | None = None) -> QueueItem | None:
        """
        Return the highest-value unreviewed item in the queue.
        Sorting order:
          1. queue_class: 'objective' (False) before 'subjective' (True)
          2. required: True (not required == False) before False (True)
          3. difficulty: HIGH (-3) before MEDIUM (-2) before LOW (-1)
          4. confidence: lowest confidence first
        """
        unreviewed = [i for i in self._items.values() if not i.reviewed]
        if not unreviewed:
            return None

        diff_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

        def sort_key(item: QueueItem) -> tuple[bool, bool, int, float]:
            is_subj = item.queue_class == "subjective"
            not_req = not item.required
            dr = -diff_rank.get(item.difficulty, 2)
            return (is_subj, not_req, dr, item.confidence)

        unreviewed.sort(key=sort_key)
        return unreviewed[0]

    def submit(
        self,
        reviewer_id: str,
        case_id: str,
        field_name: str,
        human_value: Any,
        note: str | None = None,
    ) -> QueueItem:
        """
        Idempotent submission of human verification/correction.
        Updates human_value, human_verified_at, human_verified_by, and final_value.
        If human_value != ai_value, writes an exemplar row to ExemplarStore.
        """
        key = (case_id, field_name)
        if key not in self._items:
            raise KeyError(f"Item ({case_id}, {field_name}) not found in ReviewQueue")

        item = self._items[key]
        item.human_value = human_value
        item.final_value = human_value
        item.human_verified_by = reviewer_id
        item.human_verified_at = datetime.now(timezone.utc).isoformat()
        item.note = note
        item.reviewed = True

        # Idempotency / A3 loop: write exemplar on correction
        # If human corrected the value, ensure an exemplar record exists
        if str(human_value) != str(item.ai_value):
            clip_t0 = max(0.0, float(item.t_start_s) - 10.0)
            clip_t1 = float(item.t_start_s) + 10.0
            record = ExemplarRecord(
                case_id=item.case_id,
                event_id=item.event_id,
                field_name=item.field_name,
                event_type=item.event_type or item.field_name,
                ai_value=item.ai_value,
                human_value=human_value,
                clip_t0=clip_t0,
                clip_t1=clip_t1,
                verified_by=reviewer_id,
                verified_at=item.human_verified_at,
            )
            # Replace existing exemplar for this case/field if re-submitting
            self.exemplar_store._records = [
                r for r in self.exemplar_store._records
                if not (r.case_id == case_id and r.field_name == field_name)
            ]
            self.exemplar_store.add(record)

        return item

    def list_unreviewed(self) -> list[QueueItem]:
        return [item for item in self._items.values() if not item.reviewed]


def main() -> None:
    raise NotImplementedError("router.queue is an imported module, not a script.")


if __name__ == "__main__":
    main()
