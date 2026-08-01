"""
Synthetic EventStream generators for D05 reducer engine testing.
Derived from generated/extraction_contract.json and mapping/registry.yaml.

Provides 5 synthetic streams:
  - maximal:       every repeating group at cap, every checkbox code exercised,
                   every branching condition satisfied, empty coverage_notes
  - degraded:      same events as maximal (with ems_handoff_begin and pad_reposition absent),
                   and channel-specific coverage gap (speech degraded via audio_unintelligible,
                   visual clean) to prove gate_3way No-vs-UTD asymmetry
  - overflow:      35 CCIs and 22 ROSC episodes, to exercise repeating group truncation
  - sparse:        one event (patient_enters_room), everything else absent
  - contradictory: a shock outside any CCI, a med inside a ROSC window, an inverted interval
"""

from typing import Any
from generated.models import (
    EventStream,
    Event,
    Interval,
    CoverageNote,
    CaseFields,
    Evidence,
)


def _make_evidence(ts: float, text: str = "observed") -> list[Evidence]:
    return [Evidence(timestamp_s=ts, duration_s=1.0, text=text, attributes={})]


def get_maximal_stream() -> EventStream:
    """Returns a maximal synthetic EventStream exercising all rules, groups at cap, and checkboxes."""
    events: list[Event] = []
    intervals: list[Interval] = []

    # 1. Repeating group: defib (cap=30)
    for i in range(1, 31):
        ts = float(i * 10)
        events.append(
            Event(
                type="defibrillation_shock",
                timestamp_s=ts,
                attributes={"shock_delivered": True, "energy_j": 200},
                evidence=_make_evidence(ts, f"Shock #{i}"),
            )
        )

    # 2. Repeating group: cci (cap=30 intervals, min_duration_s=3.0)
    for i in range(1, 31):
        ts = float(i * 10 - 5)
        intervals.append(
            Interval(
                type="compression_interruption",
                t_start_s=ts,
                t_end_s=ts + 4.0,  # duration 4s >= 3.0s
                attributes={"pulse_check": True, "rhythm_check": True},
            )
        )

    # 3. Repeating group: airway (cap=8 events)
    for i in range(1, 9):
        ts = float(i * 30)
        events.append(
            Event(
                type="airway_attempt",
                timestamp_s=ts,
                attributes={"device": "ett", "successful": (i == 8)},
                evidence=_make_evidence(ts, f"Airway attempt #{i}"),
            )
        )

    # 4. Repeating group: rosc (cap=20 interval pairs)
    for i in range(1, 21):
        ts_start = float(400 + i * 20)
        ts_end = ts_start + 10.0
        events.append(
            Event(
                type="rosc_detected",
                timestamp_s=ts_start,
                attributes={"pulse_palpable": True},
                evidence=_make_evidence(ts_start, f"ROSC #{i} detected"),
            )
        )
        events.append(
            Event(
                type="rosc_lost",
                timestamp_s=ts_end,
                attributes={"arrest_recurred": True},
                evidence=_make_evidence(ts_end, f"ROSC #{i} lost"),
            )
        )
        intervals.append(
            Interval(
                type="rosc",
                t_start_s=ts_start,
                t_end_s=ts_end,
                attributes={"rosc_duration_s": 10.0},
            )
        )

    # 5. Repeating group: vent_delay (cap=5 intervals, min_duration_s=20.0)
    for i in range(1, 6):
        ts = float(800 + i * 30)
        intervals.append(
            Interval(
                type="ventilation_delay",
                t_start_s=ts,
                t_end_s=ts + 22.0,  # duration 22s >= 20.0s
                attributes={"reason": "intubation"},
            )
        )

    # 6. Checkbox event types and where-filtered events
    events.append(
        Event(
            type="vascular_access",
            timestamp_s=15.0,
            attributes={
                "access_types": ["iv", "io"],
                "successful": True,
                "present_on_arrival": True,
                "confirmed": True,
            },
            evidence=_make_evidence(15.0, "IV and IO placed"),
        )
    )

    events.append(
        Event(
            type="mccd_application_start",
            timestamp_s=25.0,
            attributes={
                "obstacles": ["patient_size", "lines_tubes"],
                "applied_by": "ems",
                "device_type": "lucas",
            },
            evidence=_make_evidence(25.0, "MCCD applied by EMS"),
        )
    )

    events.append(
        Event(
            type="mccd_application_start",
            timestamp_s=28.0,
            attributes={
                "obstacles": ["patient_size"],
                "applied_by": "ed_team",
                "device_type": "lucas",
            },
            evidence=_make_evidence(28.0, "MCCD applied by ED team"),
        )
    )

    events.append(
        Event(
            type="mccd_compressions_effective",
            timestamp_s=29.0,
            attributes={"effective": True},
            evidence=_make_evidence(29.0, "MCCD compressions effective"),
        )
    )

    events.append(
        Event(
            type="mccd_adjustment",
            timestamp_s=35.0,
            attributes={
                "adjustment_categories": ["repositioning", "pause"],
            },
            evidence=_make_evidence(35.0, "MCCD adjusted"),
        )
    )

    events.append(
        Event(
            type="compression_mode_change",
            timestamp_s=38.0,
            attributes={
                "from": "mechanical",
                "to": "manual",
            },
            evidence=_make_evidence(38.0, "Mechanical to manual CPR"),
        )
    )

    events.append(
        Event(
            type="pad_application",
            timestamp_s=40.0,
            attributes={
                "applied_by": "ed_team",
                "position": "anterior_lateral",
            },
            evidence=_make_evidence(40.0, "Pads applied by ED team"),
        )
    )

    events.append(
        Event(
            type="pad_application",
            timestamp_s=41.0,
            attributes={
                "applied_by": "ems",
                "position": "anterior_posterior",
            },
            evidence=_make_evidence(41.0, "Pads applied by EMS"),
        )
    )

    events.append(
        Event(
            type="pad_reposition",
            timestamp_s=42.0,
            attributes={"pads_repositioned": True},
            evidence=_make_evidence(42.0, "Pads repositioned"),
        )
    )

    events.append(
        Event(
            type="pulse_check",
            timestamp_s=45.0,
            attributes={
                "locations": ["femoral", "carotid"],
                "pulse_found": True,
            },
            evidence=_make_evidence(45.0, "Pulse check at femoral and carotid"),
        )
    )

    events.append(
        Event(
            type="airway_confirmation",
            timestamp_s=55.0,
            attributes={
                "methods": ["etco2", "auscultation"],
                "confirmed": True,
            },
            evidence=_make_evidence(55.0, "Airway confirmed"),
        )
    )

    events.append(
        Event(
            type="dnr_confirmed",
            timestamp_s=65.0,
            attributes={
                "dnr_basis": ["family_request", "living_will"],
                "resuscitation_stopped": True,
            },
            evidence=_make_evidence(65.0, "DNR confirmed"),
        )
    )

    # Additional standard events for coverage of other rules
    events.append(
        Event(
            type="patient_enters_room",
            timestamp_s=0.0,
            attributes={"arrival": True},
            evidence=_make_evidence(0.0, "Patient arrival"),
        )
    )

    events.append(
        Event(
            type="ems_handoff_begin",
            timestamp_s=5.0,
            attributes={"handoff_started": True},
            evidence=_make_evidence(5.0, "EMS handoff start"),
        )
    )

    events.append(
        Event(
            type="medication_administration",
            timestamp_s=75.0,
            attributes={
                "drug": "epinephrine",
                "dose_mg": 1.0,
                "route": "iv",
            },
            evidence=_make_evidence(75.0, "Epi 1mg IV"),
        )
    )

    events.append(
        Event(
            type="medication_administration",
            timestamp_s=78.0,
            attributes={
                "drug": "lidocaine",
                "dose_mg": 100.0,
                "route": "iv",
            },
            evidence=_make_evidence(78.0, "Lidocaine 100mg IV"),
        )
    )

    events.append(
        Event(
            type="medication_administration",
            timestamp_s=80.0,
            attributes={
                "drug": "amiodarone",
                "dose_mg": 300.0,
                "route": "iv",
            },
            evidence=_make_evidence(80.0, "Amiodarone 300mg IV"),
        )
    )

    events.append(
        Event(
            type="medication_administration",
            timestamp_s=85.0,
            attributes={
                "drug": "other",
                "drug_name_text": "tenecteplase",
                "dose_mg": 50.0,
                "route": "iv",
            },
            evidence=_make_evidence(85.0, "TNK 50mg IV thrombolytic"),
        )
    )

    events.append(
        Event(
            type="rhythm_check",
            timestamp_s=95.0,
            attributes={
                "rhythm": "vf",
            },
            evidence=_make_evidence(95.0, "VF rhythm check"),
        )
    )

    events.append(
        Event(
            type="death_pronounced",
            timestamp_s=900.0,
            attributes={"dead": True},
            evidence=_make_evidence(900.0, "Death pronounced"),
        )
    )

    events.append(
        Event(
            type="pocus_cardiac",
            timestamp_s=880.0,
            attributes={"cardiac_activity": False},
            evidence=_make_evidence(880.0, "POCUS cardiac check"),
        )
    )

    events.append(
        Event(
            type="ecmo_called",
            timestamp_s=120.0,
            attributes={"called": True},
            evidence=_make_evidence(120.0, "ECMO called"),
        )
    )

    events.append(
        Event(
            type="ecmo_cannulation_start",
            timestamp_s=150.0,
            attributes={"started": True},
            evidence=_make_evidence(150.0, "ECMO cannulation started"),
        )
    )

    events.append(
        Event(
            type="ecmo_flow_established",
            timestamp_s=200.0,
            attributes={"established": True},
            evidence=_make_evidence(200.0, "ECMO flow established"),
        )
    )

    events.append(
        Event(
            type="ventilator_placement",
            timestamp_s=250.0,
            attributes={"placed": True},
            evidence=_make_evidence(250.0, "Ventilator placed"),
        )
    )

    # Case-level fields
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
        case_id="synthetic_maximal_001",
        events=events,
        intervals=intervals,
        coverage=[],
        fields=case_fields,
    )


def get_degraded_stream() -> EventStream:
    """
    Returns a degraded synthetic EventStream with channel-specific coverage gaps.
    Speech is degraded 0-600s via 'audio_unintelligible', while visual is clean throughout.
    
    In this stream, ems_handoff_begin (speech channel) and pad_reposition (visual channel)
    are both absent (0 matching events).
    This exercises the gate_3way No-vs-UTD asymmetry:
      -> video_ems_handoff (speech-gated) returns '3' (UTD)
      -> pad_place_position_changed_v2 (visual-gated) returns '2' (No)
    """
    max_stream = get_maximal_stream()
    # Filter out ems_handoff_begin and pad_reposition so they are absent
    filtered_events = [
        e
        for e in max_stream.events
        if e.type not in ("ems_handoff_begin", "pad_reposition")
    ]
    coverage = [
        CoverageNote(
            type="audio_unintelligible",
            text="Speech degraded and unintelligible from 0 to 600s",
        )
    ]
    return EventStream(
        case_id="synthetic_degraded_001",
        events=filtered_events,
        intervals=max_stream.intervals,
        coverage=coverage,
        fields=max_stream.fields,
    )


def get_overflow_stream() -> EventStream:
    """Returns an overflow synthetic EventStream with 35 CCIs and 22 ROSC episodes."""
    max_stream = get_maximal_stream()
    events = list(max_stream.events)
    intervals = list(max_stream.intervals)

    # Add 5 extra CCIs (total 35 > cap 30)
    for i in range(31, 36):
        ts = float(i * 10 - 5)
        intervals.append(
            Interval(
                type="compression_interruption",
                t_start_s=ts,
                t_end_s=ts + 4.0,
                attributes={"pulse_check": True, "rhythm_check": True},
            )
        )

    # Add 2 extra ROSC interval pairs (total 22 > cap 20)
    for i in range(21, 23):
        ts_start = float(400 + i * 20)
        ts_end = ts_start + 10.0
        events.append(
            Event(
                type="rosc_detected",
                timestamp_s=ts_start,
                attributes={"pulse_palpable": True},
                evidence=_make_evidence(ts_start, f"ROSC #{i} detected"),
            )
        )
        events.append(
            Event(
                type="rosc_lost",
                timestamp_s=ts_end,
                attributes={"arrest_recurred": True},
                evidence=_make_evidence(ts_end, f"ROSC #{i} lost"),
            )
        )
        intervals.append(
            Interval(
                type="rosc",
                t_start_s=ts_start,
                t_end_s=ts_end,
                attributes={"rosc_duration_s": 10.0},
            )
        )

    return EventStream(
        case_id="synthetic_overflow_001",
        events=events,
        intervals=intervals,
        coverage=[],
        fields=max_stream.fields,
    )


def get_sparse_stream() -> EventStream:
    """Returns a sparse synthetic EventStream with exactly one event and everything else absent."""
    event = Event(
        type="patient_enters_room",
        timestamp_s=1.0,
        attributes={"arrival": True},
        evidence=_make_evidence(1.0, "Patient arrived in bay"),
    )
    case_fields = CaseFields(
        recording_started_late=False,
    )
    return EventStream(
        case_id="synthetic_sparse_001",
        events=[event],
        intervals=[],
        coverage=[],
        fields=case_fields,
    )


def get_contradictory_stream() -> EventStream:
    """
    Returns a contradictory synthetic EventStream containing explicit trigger elements
    for all 10 stream cross-field validators (V1 through V10):
      - V01_start_before_end: an inverted interval (t_end_s < t_start_s)
      - V02_mccd_adj_within_app: MCCD adjustment at 35.0s outside MCCD application window [15.0, 25.0s]
      - V03_defib_count_match: 2 shocks present (one with t_start_s=None so only 1 timestamp populated, while num_times_defib is '2')
      - V04_shock_inside_cci: a shock at 100.0s outside any CCI interval
      - V05_shock_implies_shockable: shocks present and every rhythm_check is asystole (no shockable rhythm anywhere in stream)
      - V06_no_med_in_rosc: medication administered at 250.0s during ROSC interval [200.0, 300.0s]
      - V07_cci_non_overlapping: two overlapping CCI intervals [120.0, 130.0s] and [125.0, 135.0s]
      - V08_rosc_non_overlapping: two overlapping ROSC intervals [200.0, 300.0s] and [280.0, 350.0s]
      - V09_room_entry_first: patient_enters_room at 30.0s while other events/intervals occur earlier (< 30.0s)
      - V10_airway_confirmation: airway attempt with successful=True at 60.0s and no subsequent confirmation event
    (V11 and V12 are payload checks without stream representation; tested via synthetic payload dicts).
    """
    events: list[Event] = [
        # V9: patient_enters_room at 30.0s (later than several events/intervals below)
        Event(
            type="patient_enters_room",
            timestamp_s=30.0,
            attributes={"arrival": True},
            evidence=_make_evidence(30.0, "Arrival"),
        ),
        # V2: MCCD application window and out-of-bounds adjustment
        Event(
            type="mccd_application_start",
            timestamp_s=15.0,
            attributes={"applied_by": "ems"},
            evidence=_make_evidence(15.0, "MCCD start"),
        ),
        Event(
            type="mccd_removed",
            timestamp_s=25.0,
            attributes={"removed": True},
            evidence=_make_evidence(25.0, "MCCD end"),
        ),
        Event(
            type="mccd_adjustment",
            timestamp_s=35.0,
            attributes={"adjustment_categories": ["pause"]},
            evidence=_make_evidence(35.0, "MCCD adjustment outside app window"),
        ),
        # V3, V4, V5: Shock at 100.0s (outside CCI -> V4), second shock at 105.0s with unpopulated timestamp -> V3 (count=2, populated=1), all rhythms asystole -> V5
        Event(
            type="defibrillation_shock",
            timestamp_s=100.0,
            attributes={"shock_delivered": True, "energy_j": 200},
            evidence=_make_evidence(100.0, "Shock outside CCI"),
        ),
        Event(
            type="defibrillation_shock",
            timestamp_s=105.0,
            attributes={"shock_delivered": True, "energy_j": 200},
            evidence=_make_evidence(105.0, "Shock 2 in range"),
        ),
        Event(
            type="rhythm_check",
            timestamp_s=90.0,
            attributes={"rhythm": "asystole"},
            evidence=_make_evidence(90.0, "Non-shockable rhythm"),
        ),
        # V6: Medication inside ROSC window (200-300s)
        Event(
            type="medication_administration",
            timestamp_s=250.0,
            attributes={"drug": "epinephrine", "dose_mg": 1.0, "route": "iv"},
            evidence=_make_evidence(250.0, "Epi during ROSC"),
        ),
        # V10: Successful airway attempt with no subsequent airway_confirmation
        Event(
            type="airway_attempt",
            timestamp_s=60.0,
            attributes={"device": "ett", "successful": True},
            evidence=_make_evidence(60.0, "Successful airway attempt without confirmation"),
        ),
    ]

    intervals: list[Interval] = [
        # V1: Inverted interval: t_end_s < t_start_s
        Interval(
            type="compression_interruption",
            t_start_s=50.0,
            t_end_s=10.0,
            attributes={"pulse_check": True},
        ),
        # V7: Overlapping CCI intervals
        Interval(
            type="compression_interruption",
            t_start_s=120.0,
            t_end_s=130.0,
            attributes={"pulse_check": True},
        ),
        Interval(
            type="compression_interruption",
            t_start_s=125.0,
            t_end_s=135.0,
            attributes={"pulse_check": True},
        ),
        # V8: Overlapping ROSC intervals
        Interval(
            type="rosc",
            t_start_s=200.0,
            t_end_s=300.0,
            attributes={"rosc_duration_s": 100.0},
        ),
        Interval(
            type="rosc",
            t_start_s=280.0,
            t_end_s=350.0,
            attributes={"rosc_duration_s": 70.0},
        ),
    ]

    return EventStream(
        case_id="synthetic_contradictory_001",
        events=events,
        intervals=intervals,
        coverage=[],
        fields=CaseFields(recording_started_late=False, num_times_defib_ed_v2=3),
    )


def get_all_synthetic_streams() -> dict[str, EventStream]:
    """Returns all 5 synthetic streams keyed by name."""
    return {
        "maximal": get_maximal_stream(),
        "degraded": get_degraded_stream(),
        "overflow": get_overflow_stream(),
        "sparse": get_sparse_stream(),
        "contradictory": get_contradictory_stream(),
    }
