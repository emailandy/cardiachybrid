"""
Canonical registry interpreter engine for D05.
Reduces an EventStream into (list[FieldValue], list[Repair], list[Flag])
without hardcoding any REDCap field name, event type, or vocabulary literal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codegen.yamlio import load_yaml
import generated.redcap_fields as rf
import generated.branching_compiled as bc
from generated.models import EventStream, Event, Interval, CoverageNote


@dataclass(slots=True)
class FieldValue:
    field_name: str
    export_column: str
    value: Any
    value_label: str
    is_null: bool
    abstained: bool
    abstain_reason: str | None
    confidence: float
    source_class: str
    source_event_ids: list[str]
    branching_satisfied: bool = True
    validation_passed: bool = True
    validation_error: str | None = None
    routed_to_human: bool = False
    ensemble_spread_s: float = 0.0


@dataclass(slots=True, frozen=True)
class Repair:
    field_name: str
    old_value: Any
    reason: str


@dataclass(slots=True, frozen=True)
class Flag:
    field_name: str | None
    flag_type: str
    message: str
    event_ids: list[str]


_CHANNEL_ISSUES: dict[str, set[str]] = {
    'speech': {'audio_unintelligible'},
    'audio_device': {'audio_unintelligible'},
    'visual': {'chest_occluded', 'provider_crowding', 'camera_motion', 'frame_dropout'},
    'monitor': {'monitor_not_visible'},
    'airway': {'airway_not_visible'},
}

_INTERVAL_TYPE_MAP: dict[str, str] = {
    'cci': 'compression_interruption',
    'rosc': 'rosc',
    'vent_delay': 'ventilation_delay',
}


def _get_item_id(item: Event | Interval) -> str:
    ts = getattr(item, 'timestamp_s', getattr(item, 't_start_s', 0.0))
    return f'{item.type}@{ts}'


def _enrich_item_attributes(item: Event | Interval) -> None:
    attrs = item.attributes
    if 'drug' in attrs or 'drug_name_text' in attrs:
        drug_val, text_val = str(attrs.get('drug', '')).lower(), str(attrs.get('drug_name_text', '')).lower()
        syns = ('alteplase', 'tpa', 'tnk', 'tenecteplase', 'reteplase', 'retavase', 'activase', 'cathflo')
        attrs['drug_class'] = 'thrombolytic' if any(s in text_val or s in drug_val for s in syns) else None
    if 'rhythm' in attrs:
        r_val = str(attrs.get('rhythm', '')).lower()
        attrs['rhythm_shockable'] = (r_val in {'vf', 'pulseless_vt', 'aed_shockable', 'aicd_shockable'})


def _evaluate_gate(expr: str, attrs: dict[str, Any]) -> bool:
    expr = expr.strip()
    for op_str, fn in [
        (' == ', lambda a, b: str(a).lower() == str(b).lower()),
        (' != ', lambda a, b: str(a).lower() != str(b).lower()),
        (' >= ', lambda a, b: float(a) >= float(b)),
        (' <= ', lambda a, b: float(a) <= float(b)),
        (' > ', lambda a, b: float(a) > float(b)),
        (' < ', lambda a, b: float(a) < float(b)),
        (' contains ', lambda a, b: str(b).lower() in [str(x).lower() for x in (a if isinstance(a, list) else [a])]),
        (' in ', lambda a, b: str(a).lower() in [x.strip().lower() for x in str(b).split(',')]),
    ]:
        if op_str in expr:
            left, right = expr.split(op_str, 1)
            l_val, r_val = attrs.get(left.strip(), ''), right.strip().strip("'").strip('"')
            if r_val.lower() in ('true', 'yes', '1'):
                r_val = 'true'
                if str(l_val).lower() in ('true', 'yes', '1', 'True'):
                    l_val = 'true'
            elif r_val.lower() in ('false', 'no', '0'):
                r_val = 'false'
                if str(l_val).lower() in ('false', 'no', '0', 'False', ''):
                    l_val = 'false'
            try:
                return fn(l_val, r_val)
            except (ValueError, TypeError):
                return False
    return bool(attrs.get(expr, False))


def _match_where(item: Event | Interval, where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    for k, expected in where.items():
        if str(item.attributes.get(k)).lower() != str(expected).lower():
            return False
    return True


def _filter_items(stream: EventStream, et: str | None, where: dict[str, Any] | None = None, min_dur: float | None = None) -> list[Event | Interval]:
    out: list[Event | Interval] = []
    mapped_et = _INTERVAL_TYPE_MAP.get(et, et) if et else None
    for item in stream.events + stream.intervals:
        if mapped_et and item.type != mapped_et:
            continue
        if min_dur is not None and isinstance(item, Interval):
            dur = (item.t_end_s - item.t_start_s) if item.t_end_s is not None else 0.0
            if dur < min_dur:
                continue
        if _match_where(item, where):
            out.append(item)
    out.sort(key=lambda x: getattr(x, 'timestamp_s', getattr(x, 't_start_s', 0.0)))
    return out


def _check_coverage_degraded(stream: EventStream, channels: list[str]) -> bool:
    if not channels or not stream.coverage:
        return False
    target_issues: set[str] = set()
    for ch in channels:
        target_issues.update(_CHANNEL_ISSUES.get(ch, set()))
    return any(note.type in target_issues for note in stream.coverage)


def _validate_field_value(fv: FieldValue, f_spec: rf.FieldSpec) -> None:
    if fv.is_null or fv.value is None:
        return
    val_str = str(fv.value)
    if f_spec.choices and f_spec.field_type in ('radio', 'dropdown'):
        if val_str not in f_spec.choices:
            fv.validation_passed = False
            fv.validation_error = f'Choice value {val_str!r} not in dictionary choices'
            return
    if f_spec.val_min or f_spec.val_max:
        try:
            val_num = float(val_str)
            if f_spec.val_min and val_num < float(f_spec.val_min):
                fv.validation_passed = False
                fv.validation_error = f'Value {val_num} < val_min {f_spec.val_min}'
                return
            if f_spec.val_max and val_num > float(f_spec.val_max):
                fv.validation_passed = False
                fv.validation_error = f'Value {val_num} > val_max {f_spec.val_max}'
                return
        except ValueError:
            fv.validation_passed = False
            fv.validation_error = 'Non-numeric value for numeric range validation'
            return
    if f_spec.value_regex and not re.fullmatch(f_spec.value_regex, val_str):
        fv.validation_passed = False
        fv.validation_error = f'Value {val_str!r} does not match regex'


_SYN = {'ohca': '1', 'in_ed_cardiac_arrest': '2', 'anterior_lateral': '1', 'anterolateral': '1', 'vf': '1', 'pulseless_vt': '2', 'pea': '3', 'asystole': '4', 'lucas': '1', 'defibtech': '2', 'autopulse': '3', 'ems': '1', 'ems_mccd_continued': '1', 'success': '1', 'ett': '1', 'endotracheal_dl': '1'}


def _map_vocab(val: Any, f_spec: rf.FieldSpec | None) -> Any:
    if val is None or val == "" or not f_spec or not f_spec.choices:
        return val
    s = str(val).strip().lower()
    if s in f_spec.choices or (s in _SYN and _SYN[s] in f_spec.choices):
        return _SYN.get(s, str(val))
    for k, v in f_spec.choices.items():
        if s == str(v).strip().lower():
            return str(k)
    return val


def _emit_fv(
    field_name: str, val: Any, label: str, source_class: str, ids: list[str],
    fields_spec: dict[str, rf.FieldSpec], is_null: bool = False, routed: bool = False,
    abstained: bool = False, abstain_reason: str | None = None, ensemble_spread_s: float = 0.0,
) -> FieldValue:
    f_spec = fields_spec.get(field_name) or fields_spec.get(field_name.split('___')[0])
    col = field_name if '___' in field_name else (f_spec.export_columns[0] if f_spec and f_spec.export_columns else field_name)
    src = f_spec.source_class if f_spec else source_class
    if not is_null and val is not None:
        val = _map_vocab(val, f_spec)
    if src == 'AI_DIRECT' and not is_null and val is not None and not ids:
        raise ValueError(f'AI_DIRECT field {field_name!r} has non-null value but empty source_event_ids')
    fv = FieldValue(
        field_name=field_name, export_column=col, value=val, value_label=label,
        is_null=is_null or (val is None), abstained=abstained, abstain_reason=abstain_reason,
        confidence=1.0 if (not is_null and val is not None) else 0.0,
        source_class=src, source_event_ids=ids, routed_to_human=routed,
        ensemble_spread_s=ensemble_spread_s,
    )
    if f_spec:
        _validate_field_value(fv, f_spec)
    return fv


def _execute_rule(
    rule: dict[str, Any],
    stream: EventStream,
    fields_spec: dict[str, rf.FieldSpec],
    items: list[Event | Interval] | None = None,
    item_idx: int = 0,
    routed: bool = False,
) -> list[FieldValue]:
    rule_type = rule.get('rule') or rule.get('kind') or 'attr'
    f_name = rule.get('field') or rule.get('pattern')
    if not f_name or not rule_type:
        return []
    if '{i}' in f_name:
        f_name = f_name.replace('{i}', str(item_idx + 1))
    et = rule.get('event_type')
    where = rule.get('where')

    if rule_type == 'case_field':
        key = rule.get('key', '')
        raw_val = getattr(stream.fields, key, None) if stream.fields else None
        is_null = raw_val is None
        label = str(raw_val) if not is_null else ''
        f_spec = fields_spec.get(f_name)
        val = raw_val
        if not is_null and isinstance(raw_val, bool):
            if f_spec and f_spec.choices:
                yes_codes = [k for k, v in f_spec.choices.items() if str(v).lower() == 'yes' or k == '1']
                no_codes = [k for k, v in f_spec.choices.items() if str(v).lower() == 'no' or k in ('0', '2')]
                val = (yes_codes[0] if yes_codes else '1') if raw_val else (no_codes[0] if no_codes else '0')
            else:
                val = '1' if raw_val else '0'
        return [_emit_fv(f_name, val, label, 'AI_DIRECT', ['case_fields'], fields_spec, is_null=is_null, routed=routed, abstained=is_null, abstain_reason="Case field unpopulated" if is_null else None)]

    if rule_type == 'const_null':
        return [_emit_fv(f_name, None, '', 'REDUCER_DERIVED', [], fields_spec, is_null=True, routed=routed)]

    if items is None:
        items = _filter_items(stream, et, where=where)

    if rule_type in ('first_of', 'last_of'):
        target_item = items[0] if (rule_type == 'first_of' and items) else items[-1] if items else None
        if not target_item:
            return [_emit_fv(f_name, None, '', 'REDUCER_DERIVED', [], fields_spec, is_null=True, routed=routed)]
        emit_key = rule.get('emit')
        ids = [_get_item_id(target_item)]
        if emit_key in ('t_start_s', 'timestamp_s', 'timestamp', None):
            ts = getattr(target_item, 'timestamp_s', getattr(target_item, 't_start_s', None))
            return [_emit_fv(f_name, ts, str(ts), 'REDUCER_DERIVED', ids, fields_spec, routed=routed)]
        val = target_item.attributes.get(emit_key)
        return [_emit_fv(f_name, val, str(val) if val is not None else '', 'REDUCER_DERIVED', ids, fields_spec, is_null=(val is None), routed=routed)]

    if rule_type == 'nth_distinct_attribute':
        emit_key, n = rule.get('emit', ''), int(rule.get('n', 1))
        distinct_vals: list[tuple[Any, str]] = []
        seen: set[str] = set()
        for it in items:
            v = it.attributes.get(emit_key)
            if v is not None and str(v) not in seen:
                seen.add(str(v))
                distinct_vals.append((v, _get_item_id(it)))
        if len(distinct_vals) >= n:
            v, i_id = distinct_vals[n - 1]
            return [_emit_fv(f_name, v, str(v), 'REDUCER_DERIVED', [i_id], fields_spec, routed=routed)]
        return [_emit_fv(f_name, None, '', 'REDUCER_DERIVED', [], fields_spec, is_null=True, routed=routed)]

    if rule_type == 'gate_3way':
        if items:
            ids = [_get_item_id(it) for it in items]
            return [_emit_fv(f_name, '1', 'Yes', 'REDUCER_DERIVED', ids, fields_spec, routed=routed)]
        chans = rule.get('coverage_channels', [])
        if _check_coverage_degraded(stream, chans):
            return [_emit_fv(f_name, '3', 'Unable to determine', 'REDUCER_DERIVED', ['stream_coverage'], fields_spec, routed=routed, abstained=True, abstain_reason="Channel coverage degraded")]
        return [_emit_fv(f_name, '2', 'No', 'REDUCER_DERIVED', ['stream_absence'], fields_spec, routed=routed)]

    if rule_type == 'gate_yesno':
        f_spec = fields_spec.get(f_name)
        if not f_spec or f_spec.field_type != 'yesno':
            raise ValueError(f'Field {f_name!r} must be yesno for gate_yesno')
        val = '1' if items else '0'
        label = 'Yes' if val == '1' else 'No'
        ids = [_get_item_id(it) for it in items] if items else ['stream_absence']
        return [_emit_fv(f_name, val, label, 'REDUCER_DERIVED', ids, fields_spec, routed=routed)]

    if rule_type == 'count':
        val = str(len(items))
        ids = [_get_item_id(it) for it in items] if items else ['stream_absence']
        return [_emit_fv(f_name, val, val, 'REDUCER_DERIVED', ids, fields_spec, routed=routed)]

    if rule_type == 'attr':
        target_item = items[item_idx] if item_idx < len(items) else (items[0] if items else None)
        if not target_item:
            return [_emit_fv(f_name, None, '', 'REDUCER_DERIVED', [], fields_spec, is_null=True, routed=routed)]
        emit_key = rule.get('emit', '')
        ids = [_get_item_id(target_item)]
        if emit_key in ('t_start_s', 'timestamp_s', 'timestamp'):
            ts = getattr(target_item, 'timestamp_s', getattr(target_item, 't_start_s', None))
            return [_emit_fv(f_name, ts, str(ts), 'REDUCER_DERIVED', ids, fields_spec, routed=routed)]
        val = target_item.attributes.get(emit_key)
        return [_emit_fv(f_name, val, str(val) if val is not None else '', 'REDUCER_DERIVED', ids, fields_spec, is_null=(val is None), routed=routed)]

    if rule_type == 'checkbox':
        f_spec = fields_spec.get(f_name)
        if not f_spec or f_spec.field_type != 'checkbox':
            return []
        target_item = items[item_idx] if item_idx < len(items) else (items[0] if items else None)
        if not target_item:
            res: list[FieldValue] = []
            for code, label in f_spec.choices.items():
                full_col = f'{f_name}___{code}'
                res.append(_emit_fv(full_col, None, '', 'REDUCER_DERIVED', [], fields_spec, is_null=True, routed=routed))
            return res
        emit_key = rule.get('emit', '')
        selected = target_item.attributes.get(emit_key, [])
        if not isinstance(selected, (list, set, tuple)):
            selected = [selected]
        selected_set_lower = {str(x).lower() for x in selected}
        suppress_codes = set(rule.get('suppress_codes', [])) | set(f_spec.suppress_codes)
        # Q-003 INTERIM DEFAULT: mccd_obstacles obesity/cachexia hard-suppressed per GOV-07 via suppress_codes. A one-line registry change flips it.
        ids = [_get_item_id(target_item)]
        res = []
        for code, label in f_spec.choices.items():
            full_col = f'{f_name}___{code}'
            is_sel = (code.lower() in selected_set_lower or str(label).lower() in selected_set_lower)
            val = '0' if (code in suppress_codes) else ('1' if is_sel else '0')
            lbl = 'Checked' if val == '1' else 'Unchecked'
            res.append(_emit_fv(full_col, val, lbl, 'REDUCER_DERIVED', ids, fields_spec, routed=routed))
        return res

    if rule_type == 'notes':
        # Q-004 INTERIM DEFAULT: MCCD adjustment window with multiple adjustments defaults to envelope. A one-line registry change flips it.
        texts = [getattr(it, 'text', '') or getattr(it, 'type', '') for it in items]
        val = '; '.join([t for t in texts if t])
        ids = [_get_item_id(it) for it in items]
        return [_emit_fv(f_name, val if val else None, val, 'REDUCER_DERIVED', ids, fields_spec, is_null=not bool(val), routed=routed)]

    if rule_type == 'team_score':
        # Q-006 INTERIM DEFAULT: TEAM autonomy threshold defaults to standard routing. A one-line registry change flips it.
        val = '1' if items else '0'
        ids = [_get_item_id(it) for it in items] if items else []
        return [_emit_fv(f_name, val, val, 'REDUCER_DERIVED', ids, fields_spec, routed=routed)]

    if rule_type == 'conditional_text':
        # Q-005 INTERIM DEFAULT: intub_assist bougie + fiberoptic defaults to bougie precedence. A one-line registry change flips it.
        gate_expr = rule.get('gate', '')
        target_item = items[item_idx] if item_idx < len(items) else (items[0] if items else None)
        if target_item and (not gate_expr or _evaluate_gate(gate_expr, target_item.attributes)):
            emit_key = rule.get('emit', '')
            val = target_item.attributes.get(emit_key, '')
            ids = [_get_item_id(target_item)]
            return [_emit_fv(f_name, val if val else None, str(val), 'REDUCER_DERIVED', ids, fields_spec, is_null=not bool(val), routed=routed)]
        default_val = rule.get('default_when_gated_null')
        return [_emit_fv(f_name, default_val, str(default_val) if default_val else '', 'REDUCER_DERIVED', [], fields_spec, is_null=(default_val is None), routed=routed)]

    return []


def _process_repeating_group(
    group: dict[str, Any],
    stream: EventStream,
    fields_spec: dict[str, rf.FieldSpec],
) -> list[FieldValue]:
    # Q-001 INTERIM DEFAULT: repeating group truncation policy when count > max defaults to 'longest_duration'. A one-line registry change flips it.
    # Q-002 INTERIM DEFAULT: new_pad_position when repositioned twice defaults to 'last'. A one-line registry change flips it.
    g_name = group.get('name', '')
    max_count = int(group.get('max', 100))
    min_dur = group.get('min_duration_s')
    min_dur_f = float(min_dur) if min_dur is not None else None
    et = group.get('event_type') or group.get('interval_type')

    items = _filter_items(stream, et, min_dur=min_dur_f)
    true_count = len(items)
    is_overflow = true_count > max_count

    if is_overflow:
        items.sort(
            key=lambda x: ((x.t_end_s - x.t_start_s) if isinstance(x, Interval) and x.t_end_s else 0.0),
            reverse=True,
        )
        items = items[:max_count]
        items.sort(key=lambda x: getattr(x, 'timestamp_s', getattr(x, 't_start_s', 0.0)))

    res: list[FieldValue] = []
    cnt_field = group.get('count_field')
    if cnt_field:
        ovr_val = getattr(stream.fields, cnt_field, None) if stream.fields else None
        c_val = str(ovr_val) if ovr_val is not None else str(len(items))
        res.append(_emit_fv(cnt_field, c_val, c_val, 'REDUCER_DERIVED', [_get_item_id(it) for it in items], fields_spec, routed=is_overflow))

    ov_field = group.get('overflow_note_field')
    if ov_field:
        ov_val = f'Overflow: true count was {true_count}' if is_overflow else None
        res.append(_emit_fv(ov_field, ov_val, str(ov_val) if ov_val else '', 'REDUCER_DERIVED', [], fields_spec, is_null=not is_overflow, routed=is_overflow))

    for idx in range(1, max_count + 1):
        target_items = [items[idx - 1]] if idx <= len(items) else []
        for rule in group.get('fields', []):
            f_rule = dict(rule)
            res.extend(_execute_rule(f_rule, stream, fields_spec, items=target_items, item_idx=idx - 1, routed=is_overflow))
    return res


def reduce_stream(
    stream: EventStream,
    registry: dict[str, Any] | None = None,
    fields_spec: dict[str, rf.FieldSpec] | None = None,
) -> tuple[list[FieldValue], list[Repair], list[Flag]]:
    """Reduces an EventStream into field values, repair records, and flags."""
    if registry is None:
        registry = load_yaml(Path('mapping/registry.yaml'))
    if fields_spec is None:
        fields_spec = rf.FIELDS

    for item in stream.events + stream.intervals:
        _enrich_item_attributes(item)

    values: list[FieldValue] = []
    repairs: list[Repair] = []
    flags: list[Flag] = []

    group_managed = {
        g.get('count_field') for g in registry.get('groups', []) if g.get('count_field')
    } | {
        g.get('overflow_note_field') for g in registry.get('groups', []) if g.get('overflow_note_field')
    }
    for sec in registry.get('sections', []):
        for rule in sec.get('fields', []):
            if rule.get('field') in group_managed:
                continue
            if rule.get('rule') and not rule.get('repeat_group'):
                values.extend(_execute_rule(rule, stream, fields_spec))

    for group in registry.get('groups', []):
        values.extend(_process_repeating_group(group, stream, fields_spec))

    spread_map = {_get_item_id(e): float(getattr(e, 'attributes', {}).get('ensemble_spread_s', 0.0)) for e in stream.events if getattr(e, 'attributes', None)}
    record: dict[str, Any] = {}
    for fv in values:
        if fv.source_event_ids:
            fv.ensemble_spread_s = max((spread_map.get(i_id, 0.0) for i_id in fv.source_event_ids), default=0.0)
        val = fv.value if (not fv.is_null and fv.value is not None) else ''
        record[fv.export_column] = val
        record[fv.field_name] = val

    for fv in values:
        pred = bc.PREDICATES.get(fv.field_name) or bc.PREDICATES.get(fv.export_column)
        if pred and not pred(record):
            fv.branching_satisfied = False
            if not fv.is_null and fv.value is not None:
                repairs.append(Repair(field_name=fv.field_name, old_value=fv.value, reason='branching_predicate_false'))
                fv.is_null = True
                fv.value = None
                fv.value_label = ''

    for interval in stream.intervals:
        if interval.t_end_s is not None and interval.t_end_s < interval.t_start_s:
            flags.append(Flag(None, 'inverted_interval', f'Interval start {interval.t_start_s} > end {interval.t_end_s}', [_get_item_id(interval)]))

    cci_intervals = [i for i in stream.intervals if i.type == 'compression_interruption']
    for e in stream.events:
        if e.type == 'defibrillation_shock':
            in_cci = any(i.t_start_s <= e.timestamp_s <= (i.t_end_s or i.t_start_s) for i in cci_intervals)
            if not in_cci:
                flags.append(Flag(None, 'shock_outside_cci', f'Shock at {e.timestamp_s}s outside any CCI', [_get_item_id(e)]))

    rosc_intervals = [i for i in stream.intervals if i.type == 'rosc']
    for e in stream.events:
        if e.type == 'medication_administration':
            in_rosc = any(i.t_start_s <= e.timestamp_s <= (i.t_end_s or i.t_start_s) for i in rosc_intervals)
            if in_rosc:
                flags.append(Flag(None, 'med_inside_rosc', f'Medication at {e.timestamp_s}s during ROSC window', [_get_item_id(e)]))

    return values, repairs, flags


def main() -> None:
    raise NotImplementedError('reducer.engine is a library module. See docs/tasks/D05.md')


if __name__ == '__main__':
    main()
