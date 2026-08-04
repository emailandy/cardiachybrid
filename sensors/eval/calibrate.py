"""
Sensor calibration harness (S00).
Loads external calibration profiles from YAML (`sensors/calibration/*.yaml`) keyed by bay
or device model (never hardcodes thresholds). Strictly enforces minimum case-count guards,
refusing to calibrate when n < 5 cases (Q-017).
"""

from pathlib import Path
from typing import Any, Callable
from codegen.yamlio import load_yaml
from sensors.eval.metrics import ScoreCard


class CalibrationHarness:
    """Deterministic calibration harness for sensor threshold tuning."""

    @staticmethod
    def load_calibration_config(config_path: Path | str, key: str) -> dict[str, Any]:
        """
        Loads YAML calibration parameters from sensors/calibration/*.yaml keyed by bay
        or device model. Raises KeyError if key is not declared in the config file.
        """
        p = Path(config_path)
        if not p.exists():
            raise FileNotFoundError(f"Calibration config file not found: {p}")
        data = load_yaml(p)
        if not isinstance(data, dict):
            raise ValueError(f"Calibration config file must evaluate to a dictionary: {p}")

        profiles = data.get("profiles", data)
        if not isinstance(profiles, dict) or key not in profiles:
            raise KeyError(
                f"Calibration profile key {key!r} not found in {p}. "
                f"Available keys: {sorted(profiles.keys()) if isinstance(profiles, dict) else []}"
            )

        profile_data = profiles[key]
        if not isinstance(profile_data, dict):
            raise ValueError(f"Profile {key!r} in {p} must evaluate to a dictionary.")
        return profile_data

    @staticmethod
    def calibrate_thresholds(
        cases_ground_truth: list[dict[str, Any]],
        candidate_thresholds: list[dict[str, Any]],
        score_fn: Callable[[list[dict[str, Any]], dict[str, Any], dict[str, Any]], ScoreCard],
    ) -> tuple[dict[str, Any], ScoreCard]:
        """
        Evaluates candidate thresholds across a collection of ground-truth cases.
        Unconditionally refuses to execute if len(cases_ground_truth) < 5 (Q-017).
        Returns (best_threshold_dict, best_scorecard).
        """
        n_cases = len(cases_ground_truth)
        if n_cases < 5:
            raise ValueError(
                f"Calibration refused: n={n_cases} cases provided (minimum n=5 required). "
                "Grid-searching thresholds against fewer than 5 cases is overfitting with extra steps. "
                "Blocked on Q-017 (Gold set required for sensor accuracy validation)."
            )

        if not candidate_thresholds:
            raise ValueError("No candidate thresholds provided for calibration.")

        best_score = -1.0
        best_threshold: dict[str, Any] = candidate_thresholds[0]
        best_card: ScoreCard | None = None

        for thresh in candidate_thresholds:
            # Score across all provided cases
            score_cards: list[ScoreCard] = []
            for case_gt in cases_ground_truth:
                card = score_fn(cases_ground_truth, case_gt, thresh)
                score_cards.append(card)

            avg_val = sum(c.value for c in score_cards) / len(score_cards)
            if avg_val > best_score or best_card is None:
                best_score = avg_val
                best_threshold = thresh
                best_card = score_cards[0]  # Representative scorecard

        assert best_card is not None
        return best_threshold, best_card
