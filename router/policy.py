"""
Confidence router and HITL policy engine (D09).
Evaluates whether a field must be routed to human review based on configuration
in config/routing.yaml and non-negotiable policy rules (such as Q-006 TEAM routing).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codegen.yamlio import load_yaml
import generated.redcap_fields as rf
from reducer.engine import FieldValue


def load_routing_config(config_path: Path | str = "config/routing.yaml") -> dict[str, Any]:
    """Load confidence thresholds and routing parameters from YAML config."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Routing config not found at {config_path}")
    return load_yaml(path)


def _get_field_rule_map(registry_path: Path | str = "mapping/registry.yaml") -> dict[str, str]:
    """Return map of field_name -> rule from mapping/registry.yaml."""
    reg = load_yaml(Path(registry_path))
    rule_map: dict[str, str] = {}
    for sec in reg.get("sections", []):
        for entry in sec.get("fields", []):
            if "field" in entry and "rule" in entry:
                rule_map[str(entry["field"])] = str(entry["rule"])
    return rule_map


def _is_team_field(fv: Any, rule_map: dict[str, str] | None = None) -> bool:
    """
    Q-006 OPEN: TEAM fields route unconditionally until per-item ICC vs.
    two human raters exceeds 0.75. Identified by registry rule ('team_score'),
    not by form_name (all fields share one form) and not by source_class
    (TEAM fields are AI_DERIVED like most others).
    """
    field_name = getattr(fv, "field_name", str(fv))
    if rule_map is None:
        rule_map = _get_field_rule_map()
    return rule_map.get(field_name) == "team_score"


def should_route(
    fv: FieldValue,
    config: dict[str, Any] | None = None,
    rule_map: dict[str, str] | None = None,
    case_utd_rate: float | None = None,
    ensemble_spread_s: float = 0.0,
) -> tuple[bool, str | None]:
    """
    Evaluate whether a FieldValue routes to human review.
    Returns (should_route: bool, first_matching_rule: str | None).
    Rule evaluation order:
      1. TEAM (Q-006)
      2. validation failed
      3. abstained + required
      4. truncated group (routed_to_human flag from reducer)
      5. spread > 3.0s
      6. UTD anomaly (case UTD rate far below expected_utd_floor)
      7. low confidence (confidence < threshold_for(difficulty))
    """
    if config is None:
        config = load_routing_config()
    if rule_map is None:
        rule_map = _get_field_rule_map()

    # 1. TEAM fields always route (Q-006)
    if _is_team_field(fv, rule_map):
        return True, "TEAM (Q-006)"

    # 2. Validation failed
    if not fv.validation_passed:
        return True, "validation failed"

    # 3. Abstained on a REQUIRED field
    spec = rf.FIELDS.get(fv.field_name) or rf.FIELDS.get(fv.field_name.split("___")[0])
    is_required = bool(getattr(spec, "required", False)) if spec else False
    if fv.abstained and is_required:
        return True, "abstained + required"

    # 4. Truncated group (set by reducer in fv.routed_to_human)
    if fv.routed_to_human:
        return True, "truncated group"

    # 5. Ensemble spread > spread_threshold_s
    spread = float(fv.ensemble_spread_s) if fv.ensemble_spread_s > 0.0 else float(ensemble_spread_s)
    spread_thresh = float(config.get("spread_threshold_s", 3.0))
    if spread > spread_thresh:
        return True, "spread > 3.0s"

    # 6. UTD anomaly
    floor = getattr(spec, "expected_utd_floor", None) if spec else None
    margin = float(config.get("utd_anomaly_margin", 0.20))
    if floor is not None and case_utd_rate is not None and case_utd_rate < (float(floor) - margin):
        return True, "UTD anomaly"

    # 7. Low confidence against difficulty threshold
    diff_str = str(getattr(spec, "difficulty", "MEDIUM") if spec else "MEDIUM").upper()
    thresh_map = config.get("confidence_thresholds", {})
    thresh = float(thresh_map.get(diff_str, thresh_map.get("default", 0.85)))
    if fv.confidence < thresh:
        return True, "low confidence"

    return False, None


def evaluate_stream_routing(
    field_values: list[FieldValue],
    config: dict[str, Any] | None = None,
    rule_map: dict[str, str] | None = None,
    case_utd_rate_by_field: dict[str, float] | None = None,
    ensemble_spread_s: float = 0.0,
) -> dict[str, Any]:
    """
    Evaluate routing across a full list of FieldValues and return counts and auto-accept percentage.
    First-match attribution in explicit rule order.
    """
    if config is None:
        config = load_routing_config()
    if rule_map is None:
        rule_map = _get_field_rule_map()
    if case_utd_rate_by_field is None:
        case_utd_rate_by_field = {}

    total = len(field_values)
    auto_accepted = 0
    c_team = 0
    c_val = 0
    c_abstain = 0
    c_trunc = 0
    c_spread = 0
    c_utd = 0
    c_low_conf = 0

    for fv in field_values:
        utd_rate = case_utd_rate_by_field.get(fv.field_name) if case_utd_rate_by_field else None
        if utd_rate is None and case_utd_rate_by_field and "___" in fv.field_name:
            utd_rate = case_utd_rate_by_field.get(fv.field_name.split("___")[0])
        route, reason = should_route(
            fv,
            config=config,
            rule_map=rule_map,
            case_utd_rate=utd_rate,
            ensemble_spread_s=ensemble_spread_s,
        )
        if not route:
            auto_accepted += 1
        elif reason == "TEAM (Q-006)":
            c_team += 1
        elif reason == "validation failed":
            c_val += 1
        elif reason == "abstained + required":
            c_abstain += 1
        elif reason == "truncated group":
            c_trunc += 1
        elif reason == "spread > 3.0s":
            c_spread += 1
        elif reason == "UTD anomaly":
            c_utd += 1
        elif reason == "low confidence":
            c_low_conf += 1

    pct = round(auto_accepted / total * 100.0, 1) if total else 0.0

    return {
        "total_fields_evaluated": total,
        "auto_accepted": auto_accepted,
        "auto_accepted_pct": pct,
        "routed_team_q006": c_team,
        "routed_validation_failed": c_val,
        "routed_abstained_required": c_abstain,
        "routed_truncated_group": c_trunc,
        "routed_spread_gt_3s": c_spread,
        "routed_utd_anomaly": c_utd,
        "routed_low_confidence": c_low_conf,
    }


def main() -> None:
    raise NotImplementedError("router.policy is an imported module, not a script.")


if __name__ == "__main__":
    main()
