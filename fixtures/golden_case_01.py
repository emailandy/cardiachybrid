"""
Realistic 22-minute resuscitation case (golden_case_01) built from clinical plausibility.

Narrative:
    22-min OHCA. EMS compressions on arrival, handoff at 0:40. Initial rhythm
    VF at 1:15, shocked at 1:22. LUCAS applied 2:10–2:48. Epi at 3:05, 8:10,
    13:20. Second shock 5:30, third 9:45. Intubation attempt 1 fails at 6:20
    (bougie, blade out at 6:52), attempt 2 succeeds 7:05–7:40. Provider crowding
    obscures the chest 11:00–11:30. A-line placed 12:15; the reading at 14:22 is
    partially occluded by a hand. ROSC at 16:40, lost at 19:10. Case ends 22:00.
"""
from __future__ import annotations

import datetime
from typing import Any
import generated.redcap_fields as rf
from generated.models import (
    EventStream,
    Event,
    Interval,
    Evidence,
    CaseFields,
    CoverageNote,
)


def _ev(ts: float, text: str) -> list[Evidence]:
    return [
        Evidence(
            t_start_s=ts,
            t_end_s=ts + 1.0,
            text=text,
            speaker="lead",
            source_file="golden_audio.wav",
            confidence=0.99,
        )
    ]


def build_golden_case_01() -> EventStream:
    """Constructs the realistic 22-minute resuscitation golden case."""
    events: list[Event] = []
    intervals: list[Interval] = []

    # 1. Arrival & EMS handoff (0:00 to 0:40 = 0s to 40s)
    events.append(
        Event(
            type="patient_enters_room",
            timestamp_s=0.0,
            attributes={
                "cpr_in_progress": True,
                "ohca_ihca": "1",
                "video_start_late": "2",
                "video_brought_by_ems": "1",
                "iv_io_in_place_arrival": "1",
                "video_access_type": "1",
            },
            evidence=_ev(0.0, "Patient arrives with EMS CPR in progress"),
        )
    )
    events.append(
        Event(
            type="ems_handoff_begin",
            timestamp_s=10.0,
            attributes={},
            evidence=_ev(10.0, "EMS handoff begins"),
        )
    )
    events.append(
        Event(
            type="ems_handoff_end",
            timestamp_s=40.0,
            attributes={},
            evidence=_ev(40.0, "EMS handoff ends at 0:40"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=38.0,
            t_end_s=42.0,
            attributes={
                "reasons": ["stretcher_transfer", "pulse_check"],
                "pulse_check": True,
            },
        )
    )

    # 2. Initial VF rhythm check at 1:15 (75s) and Shock #1 at 1:22 (82s)
    events.append(
        Event(
            type="rhythm_check",
            timestamp_s=75.0,
            attributes={"rhythm": "VF"},
            evidence=_ev(75.0, "Initial rhythm VF at 1:15"),
        )
    )
    events.append(
        Event(
            type="defibrillation_shock",
            timestamp_s=82.0,
            attributes={"shock_delivered": True, "energy_j": 200},
            evidence=_ev(82.0, "First shock delivered at 1:22"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=74.0,
            t_end_s=84.0,
            attributes={
                "reasons": ["rhythm_determination", "defibrillation"],
                "rhythm_check": True,
            },
        )
    )

    # 3. LUCAS applied 2:10–2:48 (130s to 168s)
    events.append(
        Event(
            type="mccd_application_start",
            timestamp_s=130.0,
            attributes={
                "provider": "ed",
                "device": "lucas",
                "mccd_obstacles": ["none"],
            },
            evidence=_ev(130.0, "LUCAS application started at 2:10"),
        )
    )
    events.append(
        Event(
            type="mccd_compressions_effective",
            timestamp_s=168.0,
            attributes={"effective": True},
            evidence=_ev(168.0, "LUCAS compressions effective at 2:48"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=130.0,
            t_end_s=168.0,
            attributes={
                "reasons": ["mccd_placement"],
                "mccd_placement": True,
            },
        )
    )

    # 4. Epinephrine administrations at 3:05 (185s), 8:10 (490s), 13:20 (800s)
    events.append(
        Event(
            type="medication_administration",
            timestamp_s=185.0,
            attributes={
                "drug": "epinephrine",
                "dose": "1mg",
                "route": "iv",
                "drug_name_text": "epinephrine",
            },
            evidence=_ev(185.0, "Epinephrine 1mg IV at 3:05"),
        )
    )
    events.append(
        Event(
            type="medication_administration",
            timestamp_s=490.0,
            attributes={
                "drug": "epinephrine",
                "dose": "1mg",
                "route": "iv",
                "drug_name_text": "epinephrine",
            },
            evidence=_ev(490.0, "Epinephrine 1mg IV at 8:10"),
        )
    )
    events.append(
        Event(
            type="medication_administration",
            timestamp_s=800.0,
            attributes={
                "drug": "epinephrine",
                "dose": "1mg",
                "route": "iv",
                "drug_name_text": "epinephrine",
            },
            evidence=_ev(800.0, "Epinephrine 1mg IV at 13:20"),
        )
    )

    # 5. Second shock at 5:30 (330s), third shock at 9:45 (585s)
    events.append(
        Event(
            type="rhythm_check",
            timestamp_s=325.0,
            attributes={"rhythm": "VF"},
            evidence=_ev(325.0, "Rhythm VF at 5:25"),
        )
    )
    events.append(
        Event(
            type="defibrillation_shock",
            timestamp_s=330.0,
            attributes={"shock_delivered": True, "energy_j": 200},
            evidence=_ev(330.0, "Second shock at 5:30"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=324.0,
            t_end_s=332.0,
            attributes={
                "reasons": ["rhythm_determination", "defibrillation"],
                "rhythm_check": True,
            },
        )
    )

    events.append(
        Event(
            type="rhythm_check",
            timestamp_s=580.0,
            attributes={"rhythm": "VF"},
            evidence=_ev(580.0, "Rhythm VF at 9:40"),
        )
    )
    events.append(
        Event(
            type="defibrillation_shock",
            timestamp_s=585.0,
            attributes={"shock_delivered": True, "energy_j": 200},
            evidence=_ev(585.0, "Third shock at 9:45"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=579.0,
            t_end_s=587.0,
            attributes={
                "reasons": ["rhythm_determination", "defibrillation"],
                "rhythm_check": True,
            },
        )
    )

    # 6. Intubation Attempt 1 fails at 6:20 (380s, bougie, blade out 6:52 = 412s)
    #    Attempt 2 succeeds 7:05–7:40 (425s to 460s)
    events.append(
        Event(
            type="airway_attempt",
            timestamp_s=380.0,
            attributes={
                "device": "ett",
                "successful": False,
                "attempt_number": 1,
            },
            evidence=_ev(380.0, "First intubation attempt failed 6:20-6:52"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=380.0,
            t_end_s=412.0,
            attributes={
                "reasons": ["airway_placement"],
                "airway_placement": True,
            },
        )
    )

    events.append(
        Event(
            type="airway_attempt",
            timestamp_s=425.0,
            attributes={
                "device": "ett",
                "successful": True,
                "attempt_number": 2,
            },
            evidence=_ev(425.0, "Second intubation attempt succeeded 7:05-7:40"),
        )
    )
    events.append(
        Event(
            type="airway_confirmation",
            timestamp_s=462.0,
            attributes={"method": "etco2"},
            evidence=_ev(462.0, "ETT confirmed by ETCO2 at 7:42"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=425.0,
            t_end_s=460.0,
            attributes={
                "reasons": ["airway_placement"],
                "airway_placement": True,
            },
        )
    )

    # 7. Provider crowding obscures chest 11:00–11:30 (660s to 690s)
    #    We put a pulse check CCI in this window (CCI #8 at 675s)
    events.append(
        Event(
            type="pulse_check",
            timestamp_s=675.0,
            attributes={"pulse_palpable": False},
            evidence=_ev(675.0, "Pulse check during provider crowding at 11:15"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=670.0,
            t_end_s=680.0,
            attributes={
                "reasons": ["pulse_check"],
                "pulse_check": True,
            },
        )
    )

    # 8. Arterial line placed 12:15 (735s); reading at 14:22 (862s) is partially occluded
    events.append(
        Event(
            type="vascular_access",
            timestamp_s=735.0,
            attributes={
                "access_types": ["arterial_line"],
                "successful": True,
            },
            evidence=_ev(735.0, "A-line placed at 12:15"),
        )
    )
    # CCI #9 at 862s with low-confidence OCR reading (0.75, below HIGH threshold 0.92 -> abstains)
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=858.0,
            t_end_s=866.0,
            attributes={
                "reasons": ["arterial_line", "pulse_check"],
                "aline_sbp": 95,
            },
        )
    )

    # 9. Additional CCIs to reach exactly 12 CCIs (10, 11, 12)
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=920.0,
            t_end_s=925.0,
            attributes={"reasons": ["pulse_check"], "pulse_check": True},
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=980.0,
            t_end_s=985.0,
            attributes={"reasons": ["pulse_check"], "pulse_check": True},
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=1040.0,
            t_end_s=1045.0,
            attributes={"reasons": ["pulse_check"], "pulse_check": True},
        )
    )

    # 10. ROSC at 16:40 (1000s), lost at 19:10 (1150s)
    events.append(
        Event(
            type="rosc_detected",
            timestamp_s=1000.0,
            attributes={"pulse_palpable": True},
            evidence=_ev(1000.0, "ROSC detected at 16:40"),
        )
    )
    events.append(
        Event(
            type="rosc_lost",
            timestamp_s=1150.0,
            attributes={"arrest_recurred": True},
            evidence=_ev(1150.0, "ROSC lost at 19:10"),
        )
    )
    intervals.append(
        Interval(
            type="rosc",
            t_start_s=1000.0,
            t_end_s=1150.0,
            attributes={"sbp": 115, "dbp": 75},
        )
    )

    # 11. Case ends at 22:00 (1320s)
    events.append(
        Event(
            type="cpr_initiated_ed",
            timestamp_s=1155.0,
            attributes={"ed_compressions": True},
            evidence=_ev(1155.0, "CPR resumed after ROSC loss"),
        )
    )
    events.append(
        Event(
            type="death_pronounced",
            timestamp_s=1320.0,
            attributes={},
            evidence=_ev(1320.0, "Death pronounced at 22:00"),
        )
    )

    case_fields = CaseFields(
        recording_started_late=False,
        arrest_location="ohca",
        brought_by_ems=True,
        cpr_in_progress_upon_arrival=True,
        adv_airway_on_arrival=False,
        ems_pads_switched=False,
        mccd_ed_provenance="ems",
        ed_mccd_outcome="success",
    )

    return EventStream(
        case_id="golden_case_01",
        t0=datetime.datetime(
            2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc
        ),
        duration_s=1320.0,
        events=events,
        intervals=intervals,
        coverage=[
            CoverageNote(
                type="provider_crowding",
                text="Provider crowding obscures the chest from 11:00 to 11:30 (660s to 690s)",
            )
        ],
        fields=case_fields,
    )


def build_event_stream() -> EventStream:
    """Alias returning golden_case_01."""
    return build_golden_case_01()
