"""
QI Metrics Layer for Resuscitation Video Analysis (D10).
Computes clinical quality-of-resuscitation metrics directly from EventStream
events and intervals, including interim default CCF denominator option (c) (Q-012).

Every metric row carries metric_definition_version computed declaratively from
the prose formula statements in metrics/definitions.yaml.

Null values are explicitly emitted as None with a descriptive null_reason
(e.g., zero shocks in case -> peri_shock_pause is NULL, not 0).
Every ratio metric records both numerator and denominator for aggregation.
"""
from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from generated.models import Event, EventStream, Interval


@dataclass(slots=True)
class MetricRow:
    case_id: str
    metric_name: str
    value: Any  # float, int, list[float], or None
    numerator: float | int | None
    denominator: float | int | None
    null_reason: str | None
    metric_definition_version: str
    source: str = "COMPUTED"


def get_metric_definition_version() -> str:
    """Compute an 8-character SHA-256 hash over the prose statements in metrics/definitions.yaml."""
    path = Path("metrics/definitions.yaml")
    if not path.exists():
        path = Path(__file__).parent / "definitions.yaml"
    if not path.exists():
        return "unknown"
    import yaml
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return "unknown"
    prose_list = []
    for k in sorted(data.keys()):
        val = data[k]
        if isinstance(val, dict):
            prose_list.append(f"{k}:{val.get('statement', '')}")
    prose_str = "\n".join(prose_list)
    return hashlib.sha256(prose_str.encode("utf-8")).hexdigest()[:8]


def _get_cci_durations(stream: EventStream) -> list[tuple[float, float, float]]:
    """Return list of (t_start, t_end, duration) for all compression_interruption intervals."""
    ccis = []
    for interval in stream.intervals:
        if interval.type == "compression_interruption":
            t_s = float(interval.t_start_s)
            t_e = float(interval.t_end_s) if interval.t_end_s is not None else t_s
            dur = getattr(interval, "duration_s", None)
            if dur is None:
                dur = t_e - t_s
            ccis.append((t_s, t_e, float(dur)))
    return sorted(ccis, key=lambda x: x[0])


def _get_rosc_durations(stream: EventStream) -> list[tuple[float, float, float]]:
    """Return list of (t_start, t_end, duration) for sustained ROSC intervals."""
    roscs = []
    for interval in stream.intervals:
        if interval.type in ("rosc", "sustained_rosc"):
            t_s = float(interval.t_start_s)
            t_e = float(interval.t_end_s) if interval.t_end_s is not None else t_s
            dur = getattr(interval, "duration_s", None)
            if dur is None:
                dur = t_e - t_s
            roscs.append((t_s, t_e, float(dur)))
    return sorted(roscs, key=lambda x: x[0])


def compute_ccf(
    stream: EventStream,
    version: str,
    config: dict[str, Any] | None = None,
) -> MetricRow:
    """
    Compute Chest Compression Fraction (CCF).
    
    Q-012 INTERIM DEFAULT: Candidate (c) — first compression -> termination,
    excluding periods of sustained ROSC. Configurable via ccf_denominator_mode.
    """
    cfg = config or {}
    mode = cfg.get("ccf_denominator_mode", "first_compression_to_termination_excluding_rosc")

    all_times = []
    for ev in stream.events:
        all_times.append(float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0)))
    for inv in stream.intervals:
        all_times.append(float(inv.t_start_s))
        if inv.t_end_s is not None:
            all_times.append(float(inv.t_end_s))

    if not all_times:
        return MetricRow(
            case_id=stream.case_id,
            metric_name="chest_compression_fraction",
            value=None,
            numerator=None,
            denominator=None,
            null_reason="no compressions or zero case duration",
            metric_definition_version=version,
        )

    t_start = min(all_times)
    t_end = max(all_times)
    total_time = t_end - t_start
    if total_time <= 0.0:
        return MetricRow(
            case_id=stream.case_id,
            metric_name="chest_compression_fraction",
            value=None,
            numerator=None,
            denominator=None,
            null_reason="no compressions or zero case duration",
            metric_definition_version=version,
        )

    rosc_time = 0.0
    if "excluding_rosc" in mode:
        for r_s, r_e, r_dur in _get_rosc_durations(stream):
            rosc_time += r_dur
    denom = max(0.0, total_time - rosc_time)
    if denom <= 0.0:
        return MetricRow(
            case_id=stream.case_id,
            metric_name="chest_compression_fraction",
            value=None,
            numerator=None,
            denominator=None,
            null_reason="no compressions or zero case duration",
            metric_definition_version=version,
        )

    ccis = _get_cci_durations(stream)
    cci_time = sum(dur for _, _, dur in ccis)
    num = max(0.0, denom - cci_time)
    val = round(num / denom, 3)
    return MetricRow(
        case_id=stream.case_id,
        metric_name="chest_compression_fraction",
        value=val,
        numerator=round(num, 3),
        denominator=round(denom, 3),
        null_reason=None,
        metric_definition_version=version,
    )


def compute_ccf_epochs(
    stream: EventStream,
    version: str,
    epoch_s: float = 120.0,
) -> MetricRow:
    """Compute CCF array across sequential 2-minute (120s) non-overlapping windows."""
    all_times = []
    for ev in stream.events:
        all_times.append(float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0)))
    for inv in stream.intervals:
        all_times.append(float(inv.t_start_s))
        if inv.t_end_s is not None:
            all_times.append(float(inv.t_end_s))

    if not all_times or (max(all_times) - min(all_times)) <= 0.0:
        return MetricRow(
            case_id=stream.case_id,
            metric_name="ccf_by_2min_epoch",
            value=None,
            numerator=None,
            denominator=None,
            null_reason="case duration shorter than window or no compressions in case",
            metric_definition_version=version,
        )

    t_0 = min(all_times)
    t_end = max(all_times)
    ccis = _get_cci_durations(stream)
    epochs = []
    tot_num = 0.0
    tot_denom = 0.0

    curr = t_0
    while curr < t_end:
        w_end = min(curr + epoch_s, t_end)
        w_dur = w_end - curr
        if w_dur <= 0.0:
            break
        # calculate overlap of CCIs with window [curr, w_end]
        overlap_cci = 0.0
        for c_s, c_e, _ in ccis:
            ov_s = max(curr, c_s)
            ov_e = min(w_end, c_e)
            if ov_e > ov_s:
                overlap_cci += (ov_e - ov_s)
        w_num = max(0.0, w_dur - overlap_cci)
        epochs.append(round(w_num / w_dur, 3))
        tot_num += w_num
        tot_denom += w_dur
        curr = w_end

    return MetricRow(
        case_id=stream.case_id,
        metric_name="ccf_by_2min_epoch",
        value=epochs,
        numerator=round(tot_num, 3),
        denominator=round(tot_denom, 3),
        null_reason=None,
        metric_definition_version=version,
    )


def compute_cci_metrics(stream: EventStream, version: str) -> list[MetricRow]:
    """Compute n_cci_over_10s, longest_cci_s, and median_cci_s."""
    ccis = _get_cci_durations(stream)
    n_total = len(ccis)
    if n_total == 0:
        return [
            MetricRow(
                case_id=stream.case_id,
                metric_name="n_cci_over_10s",
                value=None,
                numerator=None,
                denominator=None,
                null_reason="no CCIs detected in case",
                metric_definition_version=version,
            ),
            MetricRow(
                case_id=stream.case_id,
                metric_name="longest_cci_s",
                value=None,
                numerator=None,
                denominator=None,
                null_reason="no CCIs detected in case",
                metric_definition_version=version,
            ),
            MetricRow(
                case_id=stream.case_id,
                metric_name="median_cci_s",
                value=None,
                numerator=None,
                denominator=None,
                null_reason="no CCIs detected in case",
                metric_definition_version=version,
            ),
        ]

    durations = [dur for _, _, dur in ccis]
    over_10 = sum(1 for d in durations if d > 10.0)
    longest = max(durations)
    med = statistics.median(durations)

    return [
        MetricRow(
            case_id=stream.case_id,
            metric_name="n_cci_over_10s",
            value=over_10,
            numerator=over_10,
            denominator=n_total,
            null_reason=None,
            metric_definition_version=version,
        ),
        MetricRow(
            case_id=stream.case_id,
            metric_name="longest_cci_s",
            value=round(longest, 3),
            numerator=round(longest, 3),
            denominator=1,
            null_reason=None,
            metric_definition_version=version,
        ),
        MetricRow(
            case_id=stream.case_id,
            metric_name="median_cci_s",
            value=round(med, 3),
            numerator=round(med, 3),
            denominator=n_total,
            null_reason=None,
            metric_definition_version=version,
        ),
    ]


def compute_peri_shock_metrics(stream: EventStream, version: str) -> list[MetricRow]:
    """
    Compute peri-shock pause metrics and pre-charged shock rate.
    
    NULL IS NOT ZERO: A case with 0 shocks emits NULL (value=None) for all
    peri-shock pauses and rates, not 0.
    """
    shocks = []
    for ev in stream.events:
        if ev.type == "defibrillation_shock":
            ts = float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0))
            shocks.append((ts, ev))
    shocks.sort(key=lambda x: x[0])
    n_shocks = len(shocks)

    if n_shocks == 0:
        nr = "zero shocks in case"
        return [
            MetricRow(stream.case_id, "peri_shock_pause_pre_s", None, None, None, nr, version),
            MetricRow(stream.case_id, "peri_shock_pause_post_s", None, None, None, nr, version),
            MetricRow(stream.case_id, "median_peri_shock_pause_pre_s", None, None, None, nr, version),
            MetricRow(stream.case_id, "median_peri_shock_pause_post_s", None, None, None, nr, version),
            MetricRow(stream.case_id, "pre_charged_shock_rate", None, 0, 0, nr, version),
        ]

    ccis = _get_cci_durations(stream)
    pre_pauses = []
    post_pauses = []
    n_pre_charged = 0

    for ts, ev in shocks:
        # Pre-shock pause: time from start of surrounding or preceding CCI to ts
        pre_s = 0.0
        post_s = 0.0
        overlapping = [c for c in ccis if c[0] <= ts <= c[1]]
        if overlapping:
            c_s, c_e, _ = overlapping[0]
            pre_s = ts - c_s
            post_s = c_e - ts
        else:
            preceding = [c for c in ccis if c[1] <= ts]
            if preceding:
                pre_s = ts - preceding[-1][0]
            following = [c for c in ccis if c[0] >= ts]
            if following:
                post_s = following[0][1] - ts

        pre_pauses.append(round(pre_s, 3))
        post_pauses.append(round(post_s, 3))

        # Check pre-charging attribute or event
        pre_charged = getattr(ev, "attributes", {}).get("pre_charged", False)
        if pre_charged:
            n_pre_charged += 1

    med_pre = statistics.median(pre_pauses)
    med_post = statistics.median(post_pauses)
    rate_pre = round(n_pre_charged / n_shocks, 3)

    return [
        MetricRow(stream.case_id, "peri_shock_pause_pre_s", pre_pauses, sum(pre_pauses), n_shocks, None, version),
        MetricRow(stream.case_id, "peri_shock_pause_post_s", post_pauses, sum(post_pauses), n_shocks, None, version),
        MetricRow(stream.case_id, "median_peri_shock_pause_pre_s", round(med_pre, 3), round(med_pre, 3), n_shocks, None, version),
        MetricRow(stream.case_id, "median_peri_shock_pause_post_s", round(med_post, 3), round(med_post, 3), n_shocks, None, version),
        MetricRow(stream.case_id, "pre_charged_shock_rate", rate_pre, n_pre_charged, n_shocks, None, version),
    ]


def compute_arrival_intervals(stream: EventStream, version: str) -> list[MetricRow]:
    """Compute arrival_to_pads_s, arrival_to_first_epi_s, shockable_to_first_shock_s."""
    all_times = [float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0)) for ev in stream.events]
    t_arr = min(all_times) if all_times else 0.0

    pad_times = [
        float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0))
        for ev in stream.events
        if ev.type in ("pad_application", "pads_placed")
    ]
    epi_times = [
        float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0))
        for ev in stream.events
        if ev.type == "medication_administered"
        and str(getattr(ev, "attributes", {}).get("medication", "")).lower() == "epinephrine"
    ]
    shockable_times = [
        float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0))
        for ev in stream.events
        if ev.type == "rhythm_check"
        and str(getattr(ev, "attributes", {}).get("rhythm", "")).lower() in ("vf", "vfib", "vt", "vtach")
    ]
    shock_times = [
        float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0))
        for ev in stream.events
        if ev.type == "defibrillation_shock"
    ]

    row_pads = MetricRow(
        case_id=stream.case_id,
        metric_name="arrival_to_pads_s",
        value=round(min(pad_times) - t_arr, 3) if pad_times else None,
        numerator=round(min(pad_times) - t_arr, 3) if pad_times else None,
        denominator=1 if pad_times else None,
        null_reason=None if pad_times else "pad application event absent from stream",
        metric_definition_version=version,
    )

    row_epi = MetricRow(
        case_id=stream.case_id,
        metric_name="arrival_to_first_epi_s",
        value=round(min(epi_times) - t_arr, 3) if epi_times else None,
        numerator=round(min(epi_times) - t_arr, 3) if epi_times else None,
        denominator=1 if epi_times else None,
        null_reason=None if epi_times else "epinephrine administration event absent from stream",
        metric_definition_version=version,
    )

    t_shk_rhy = min(shockable_times) if shockable_times else None
    t_first_shk = min(shock_times) if shock_times else None
    has_pair = t_shk_rhy is not None and t_first_shk is not None and t_first_shk >= t_shk_rhy
    row_shockable = MetricRow(
        case_id=stream.case_id,
        metric_name="shockable_to_first_shock_s",
        value=round(t_first_shk - t_shk_rhy, 3) if has_pair else None,
        numerator=round(t_first_shk - t_shk_rhy, 3) if has_pair else None,
        denominator=1 if has_pair else None,
        null_reason=None if has_pair else "shockable rhythm or defibrillation shock absent from stream",
        metric_definition_version=version,
    )

    return [row_pads, row_epi, row_shockable]


def compute_airway_metrics(stream: EventStream, version: str) -> list[MetricRow]:
    """Compute n_airway_attempts, first_pass_success, cci_seconds_attributable_to_airway."""
    attempts = sorted(
        [ev for ev in stream.events if ev.type == "airway_attempt"],
        key=lambda x: float(x.timestamp_s if x.timestamp_s is not None else (x.t_start_s or 0.0)),
    )
    n_att = len(attempts)
    ccis = _get_cci_durations(stream)

    if n_att == 0:
        return [
            MetricRow(stream.case_id, "n_airway_attempts", 0, 0, 1, None, version),
            MetricRow(stream.case_id, "first_pass_success", None, None, None, "zero airway attempts in case", version),
            MetricRow(stream.case_id, "cci_seconds_attributable_to_airway", 0.0, 0.0, len(ccis), None, version),
        ]

    first_succ = getattr(attempts[0], "attributes", {}).get("successful", False)
    val_succ = 1.0 if first_succ else 0.0

    cci_airway_s = 0.0
    for a in attempts:
        a_ts = float(a.timestamp_s if a.timestamp_s is not None else (a.t_start_s or 0.0))
        for c_s, c_e, c_dur in ccis:
            if c_s <= a_ts <= c_e:
                cci_airway_s += c_dur

    return [
        MetricRow(stream.case_id, "n_airway_attempts", n_att, n_att, 1, None, version),
        MetricRow(stream.case_id, "first_pass_success", val_succ, 1 if first_succ else 0, 1, None, version),
        MetricRow(stream.case_id, "cci_seconds_attributable_to_airway", round(cci_airway_s, 3), round(cci_airway_s, 3), len(ccis), None, version),
    ]


def compute_mccd_metrics(stream: EventStream, version: str) -> list[MetricRow]:
    """Compute mccd_deployment_noflow_s and REDCap calc field replacements."""
    mccd_ccis = []
    ccis = _get_cci_durations(stream)
    mccd_events = [
        ev for ev in stream.events
        if ev.type in ("mccd_application_start", "mccd_on", "mccd_placed")
    ]
    mccd_intervals = [
        inv for inv in stream.intervals
        if inv.type in ("mccd_application", "mccd_on", "mccd_ed")
    ]

    for ev in mccd_events:
        ts = float(ev.timestamp_s if ev.timestamp_s is not None else (ev.t_start_s or 0.0))
        for c_s, c_e, c_dur in ccis:
            if c_s <= ts <= c_e:
                mccd_ccis.append(c_dur)

    noflow_val = sum(mccd_ccis) if (mccd_events or mccd_ccis) else None
    row_noflow = MetricRow(
        case_id=stream.case_id,
        metric_name="mccd_deployment_noflow_s",
        value=round(noflow_val, 3) if noflow_val is not None else None,
        numerator=round(noflow_val, 3) if noflow_val is not None else None,
        denominator=1 if noflow_val is not None else None,
        null_reason=None if noflow_val is not None else "mccd not deployed in case",
        metric_definition_version=version,
    )

    # REDCap Calc field replacements dynamically resolved from FIELDS (I2 compliant)
    from generated.redcap_fields import FIELDS
    calc_fields = [name for name, spec in FIELDS.items() if getattr(spec, "source_class", "") == "REDCAP_CALC"]
    mccd_calc_name = next((name for name in calc_fields if "mccd" in name), "dur_mccd_calc")
    vent_calc_name = next((name for name in calc_fields if "vent" in name), "dur_vent_calc")

    tot_mccd_s = sum(float(getattr(i, "duration_s", 0.0) or ((i.t_end_s or i.t_start_s) - i.t_start_s)) for i in mccd_intervals)
    row_calc_mccd = MetricRow(
        case_id=stream.case_id,
        metric_name=mccd_calc_name,
        value=round(tot_mccd_s, 3) if mccd_intervals else None,
        numerator=round(tot_mccd_s, 3) if mccd_intervals else None,
        denominator=1 if mccd_intervals else None,
        null_reason=None if mccd_intervals else "mccd not applied in ED",
        metric_definition_version=version,
        source="REDCAP_CALC_REPLACEMENT",
    )

    vent_intervals = [
        inv for inv in stream.intervals
        if inv.type in ("ventilator_placement", "ventilator_on", "vent_ed")
    ]
    tot_vent_s = sum(float(getattr(i, "duration_s", 0.0) or ((i.t_end_s or i.t_start_s) - i.t_start_s)) for i in vent_intervals)
    row_calc_vent = MetricRow(
        case_id=stream.case_id,
        metric_name=vent_calc_name,
        value=round(tot_vent_s, 3) if vent_intervals else None,
        numerator=round(tot_vent_s, 3) if vent_intervals else None,
        denominator=1 if vent_intervals else None,
        null_reason=None if vent_intervals else "ventilator not placed in ED",
        metric_definition_version=version,
        source="REDCAP_CALC_REPLACEMENT",
    )

    return [row_noflow, row_calc_mccd, row_calc_vent]


def compute_asr_metrics(stream: EventStream, version: str) -> list[MetricRow]:
    """
    Emit closed_loop_completion_rate and n_unacknowledged_directives as NULL.
    Requires S7 diarized ASR, which does not exist yet. Do not skip rows.
    """
    nr = "requires S7 diarized ASR"
    return [
        MetricRow(stream.case_id, "closed_loop_completion_rate", None, None, None, nr, version),
        MetricRow(stream.case_id, "n_unacknowledged_directives", None, None, None, nr, version),
    ]


def compute_case_metrics(
    stream: EventStream,
    config: dict[str, Any] | None = None,
) -> list[MetricRow]:
    """
    Compute all derived QI metrics and REDCap calc field replacements for a case.
    """
    version = get_metric_definition_version()
    rows: list[MetricRow] = []
    rows.append(compute_ccf(stream, version, config))
    rows.append(compute_ccf_epochs(stream, version))
    rows.extend(compute_cci_metrics(stream, version))
    rows.extend(compute_peri_shock_metrics(stream, version))
    rows.extend(compute_arrival_intervals(stream, version))
    rows.extend(compute_airway_metrics(stream, version))
    rows.extend(compute_mccd_metrics(stream, version))
    rows.extend(compute_asr_metrics(stream, version))
    return rows
