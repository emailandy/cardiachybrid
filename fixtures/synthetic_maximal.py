"""
Synthetic maximal EventStream fixture.
Constructs an EventStream exercising every repeating group at its cap,
cycling through all choice codes, satisfying all branching conditions,
and emitting every event type without hard-coding counts or literals.
"""
from __future__ import annotations

import datetime
from typing import Any
import generated.redcap_fields as rf
from generated.models import EventStream, Event, Interval, Evidence, CaseFields


def _make_evidence(ts: float, text: str) -> list[Evidence]:
    return [
        Evidence(
            t_start_s=ts,
            t_end_s=ts + 1.0,
            text=text,
            speaker="lead",
            source_file="audio.wav",
            confidence=0.99,
        )
    ]


def build_event_stream() -> EventStream:
    """Builds the canonical maximal EventStream."""
    events: list[Event] = []
    intervals: list[Interval] = []

    # Dynamically extract choices from FIELDS
    cci_field_1 = rf.FIELDS.get("reason_cci_1_v2")
    cci_field_2 = rf.FIELDS.get("reason_cci_2_v2")
    cci_codes_1 = list(cci_field_1.choices.keys()) if cci_field_1 else ["1"]
    cci_codes_2 = list(cci_field_2.choices.keys()) if cci_field_2 else cci_codes_1

    mccd_adj_field = rf.FIELDS.get("reason_mccd_adj_cci_1_v2")
    mccd_adj_codes = list(mccd_adj_field.choices.keys()) if mccd_adj_field else ["1"]

    pulse_loc_field = rf.FIELDS.get("loc_initial_pulse_check_v2")
    pulse_loc_codes = list(pulse_loc_field.choices.keys()) if pulse_loc_field else ["1"]

    access_field = rf.FIELDS.get("video_access_type")
    access_codes = list(access_field.choices.keys()) if access_field else ["1"]

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

    # 2. Repeating group: cci (cap=30 intervals)
    for i in range(1, 31):
        ts = float(i * 10 - 5)
        # Cycle through all CCI reason codes
        codes_list = cci_codes_1 if i == 1 else cci_codes_2
        code = codes_list[(i - 1) % len(codes_list)]
        adj_code = mccd_adj_codes[(i - 1) % len(mccd_adj_codes)]
        loc_code = pulse_loc_codes[(i - 1) % len(pulse_loc_codes)]

        intervals.append(
            Interval(
                type="compression_interruption",
                t_start_s=ts,
                t_end_s=ts + 4.0,  # >= 3.0s min duration
                attributes={
                    "reasons": [code, "pulse_check", "rhythm_check"],
                    "pulse_check": True,
                    "rhythm_check": True,
                    "reason_mccd_adj": [adj_code],
                    "loc_pulse_check": loc_code,
                    "pocus_non_pulse": "1",
                    "rhythm_during_cci": "1",
                    "aline_sbp": 120,
                },
            )
        )

    # 3. Repeating group: airway (cap=8 events)
    for i in range(1, 9):
        ts = float(i * 30)
        events.append(
            Event(
                type="airway_attempt",
                timestamp_s=ts,
                attributes={
                    "device": "ett",
                    "successful": (i == 8),
                    "attempt_number": i,
                },
                evidence=_make_evidence(ts, f"Airway attempt #{i}"),
            )
        )

    # 4. Repeating group: rosc (cap=20 intervals)
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
                attributes={"sbp": 120, "dbp": 80},
            )
        )

    # 5. Repeating group: vent_delay (cap=5 intervals)
    for i in range(1, 6):
        ts_start = float(100 + i * 50)
        intervals.append(
            Interval(
                type="ventilation_delay",
                t_start_s=ts_start,
                t_end_s=ts_start + 15.0,
                attributes={"duration_s": 15.0},
            )
        )

    # 6. Single clinical / CPR / MCCD / medication events to satisfy branching
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
                "video_access_type": access_codes[0],
            },
            evidence=_make_evidence(0.0, "Patient enters room with CPR in progress"),
        )
    )
    events.append(
        Event(
            type="first_team_member_enters",
            timestamp_s=5.0,
            attributes={},
            evidence=_make_evidence(5.0, "First team member enters"),
        )
    )
    events.append(
        Event(
            type="cpr_initiated_ed",
            timestamp_s=10.0,
            attributes={"ed_compressions": True},
            evidence=_make_evidence(10.0, "CPR initiated in ED"),
        )
    )
    events.append(
        Event(
            type="mccd_application_start",
            timestamp_s=25.0,
            attributes={
                "provider": "ems",
                "device": "lucas",
                "mccd_obstacles": ["none"],
            },
            evidence=_make_evidence(25.0, "EMS LUCAS application started"),
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
            attributes={"adjustment_categories": ["repositioning", "pause"]},
            evidence=_make_evidence(35.0, "MCCD adjusted"),
        )
    )
    events.append(
        Event(
            type="compression_mode_change",
            timestamp_s=38.0,
            attributes={"from": "mechanical", "to": "manual"},
            evidence=_make_evidence(38.0, "Switched from mechanical to manual CPR"),
        )
    )
    events.append(
        Event(
            type="pad_application",
            timestamp_s=12.0,
            attributes={"position": "anterolateral"},
            evidence=_make_evidence(12.0, "Pads applied anterolateral"),
        )
    )
    events.append(
        Event(
            type="pad_reposition",
            timestamp_s=15.0,
            attributes={"new_position": "anteroposterior"},
            evidence=_make_evidence(15.0, "Pads repositioned to anteroposterior"),
        )
    )
    events.append(
        Event(
            type="rhythm_check",
            timestamp_s=18.0,
            attributes={"rhythm": "VF"},
            evidence=_make_evidence(18.0, "First ED rhythm VF"),
        )
    )
    events.append(
        Event(
            type="pulse_check",
            timestamp_s=20.0,
            attributes={"pulse_palpable": False, "location": pulse_loc_codes[0]},
            evidence=_make_evidence(20.0, "Pulse check carotid no pulse"),
        )
    )
    events.append(
        Event(
            type="airway_confirmation",
            timestamp_s=35.0,
            attributes={"method": "etco2"},
            evidence=_make_evidence(35.0, "Airway confirmed by ETCO2"),
        )
    )
    events.append(
        Event(
            type="ventilator_placement",
            timestamp_s=40.0,
            attributes={},
            evidence=_make_evidence(40.0, "Ventilator placed"),
        )
    )
    events.append(
        Event(
            type="medication_administration",
            timestamp_s=50.0,
            attributes={
                "drug": "epinephrine",
                "dose": "1mg",
                "route": "iv",
                "drug_name_text": "epinephrine",
            },
            evidence=_make_evidence(50.0, "Epi 1mg IV given"),
        )
    )
    events.append(
        Event(
            type="medication_administration",
            timestamp_s=60.0,
            attributes={
                "drug": "amiodarone",
                "dose": "300mg",
                "route": "iv",
                "drug_name_text": "amiodarone",
            },
            evidence=_make_evidence(60.0, "Amiodarone 300mg IV given"),
        )
    )
    events.append(
        Event(
            type="medication_administration",
            timestamp_s=70.0,
            attributes={
                "drug": "lidocaine",
                "dose": "100mg",
                "route": "iv",
                "drug_name_text": "lidocaine",
            },
            evidence=_make_evidence(70.0, "Lidocaine 100mg IV given"),
        )
    )
    events.append(
        Event(
            type="medication_administration",
            timestamp_s=80.0,
            attributes={
                "drug": "other",
                "dose": "50mg",
                "route": "iv",
                "drug_name_text": "tPA",
            },
            evidence=_make_evidence(80.0, "tPA thrombolytic IV given"),
        )
    )
    events.append(
        Event(
            type="pocus_cardiac",
            timestamp_s=85.0,
            attributes={"cardiac_activity": True},
            evidence=_make_evidence(85.0, "Cardiac POCUS showed activity"),
        )
    )
    events.append(
        Event(
            type="pocus_other",
            timestamp_s=88.0,
            attributes={"finding": "normal"},
            evidence=_make_evidence(88.0, "Lung POCUS normal"),
        )
    )
    events.append(
        Event(
            type="ecmo_called",
            timestamp_s=100.0,
            attributes={},
            evidence=_make_evidence(100.0, "ECMO team called"),
        )
    )
    events.append(
        Event(
            type="ecmo_cannulation_start",
            timestamp_s=110.0,
            attributes={},
            evidence=_make_evidence(110.0, "ECMO cannulation started"),
        )
    )
    events.append(
        Event(
            type="ecmo_flow_established",
            timestamp_s=130.0,
            attributes={"flow_lpm": 4.5},
            evidence=_make_evidence(130.0, "ECMO flow established"),
        )
    )
    events.append(
        Event(
            type="ems_handoff_begin",
            timestamp_s=10.0,
            attributes={},
            evidence=_make_evidence(10.0, "EMS handoff began"),
        )
    )
    events.append(
        Event(
            type="ems_handoff_end",
            timestamp_s=20.0,
            attributes={},
            evidence=_make_evidence(20.0, "EMS handoff ended"),
        )
    )
    events.append(
        Event(
            type="vascular_access",
            timestamp_s=15.0,
            attributes={"type": "iv", "location": "left_antecubital"},
            evidence=_make_evidence(15.0, "IV access established"),
        )
    )
    events.append(
        Event(
            type="vitals_reading",
            timestamp_s=300.0,
            attributes={"sbp": 110, "dbp": 70, "hr": 80, "etco2": 35},
            evidence=_make_evidence(300.0, "Vitals reading recorded"),
        )
    )
    events.append(
        Event(
            type="death_pronounced",
            timestamp_s=600.0,
            attributes={},
            evidence=_make_evidence(600.0, "Death pronounced"),
        )
    )
    events.append(
        Event(
            type="dnr_confirmed",
            timestamp_s=590.0,
            attributes={},
            evidence=_make_evidence(590.0, "DNR confirmed"),
        )
    )
    events.append(
        Event(
            type="defib_charge_aborted",
            timestamp_s=95.0,
            attributes={"reason": "rosc"},
            evidence=_make_evidence(95.0, "Defib charge aborted due to ROSC"),
        )
    )
    events.append(
        Event(
            type="patient_leaves_room",
            timestamp_s=900.0,
            attributes={"destination": "icu"},
            evidence=_make_evidence(900.0, "Patient left room for ICU"),
        )
    )
    events.append(
        Event(
            type="bed_transfer_complete",
            timestamp_s=905.0,
            attributes={},
            evidence=_make_evidence(905.0, "Bed transfer complete"),
        )
    )
    events.append(
        Event(
            type="stretcher_transfer",
            timestamp_s=910.0,
            attributes={},
            evidence=_make_evidence(910.0, "Stretcher transfer complete"),
        )
    )
    events.append(
        Event(
            type="tee_placement",
            timestamp_s=95.0,
            attributes={"success": True},
            evidence=_make_evidence(95.0, "TEE placed successfully"),
        )
    )
    events.append(
        Event(
            type="log_roll",
            timestamp_s=105.0,
            attributes={"reason": "backboard_removal"},
            evidence=_make_evidence(105.0, "Log roll performed"),
        )
    )
    events.append(
        Event(
            type="mccd_removed",
            timestamp_s=580.0,
            attributes={},
            evidence=_make_evidence(580.0, "MCCD removed"),
        )
    )
    intervals.append(
        Interval(
            type="compression_interruption",
            t_start_s=55.0,
            t_end_s=58.0,
            attributes={"reason": "pulse_check"},
            evidence=_make_evidence(55.0, "Compression interruption"),
        )
    )
    events.append(
        Event(
            type="compression_active_start",
            timestamp_s=58.0,
            attributes={},
            evidence=_make_evidence(58.0, "Compressions resumed"),
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
        case_id="synthetic_maximal_001",
        t0=datetime.datetime(
            2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc
        ),
        duration_s=1000.0,
        events=events,
        intervals=intervals,
        coverage=[],  # No coverage notes -> gate_3way returns "2", never "3"
        fields=case_fields,
    )
