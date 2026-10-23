import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import gbt_baseline as g  # noqa: E402


def test_metrics_counts_only_the_validation_split():
    res = pd.DataFrame({
        "split": ["validation"] * 4 + ["train"],
        "label": ["scam", "scam", "legit", "legit", "scam"],
        "alarm": [True, False, True, False, True],
    })
    m = g.metrics(res)
    assert (m["scam_n"], m["scam_alarmed"], m["legit_n"], m["false_alarms"]) == (2, 1, 2, 1)
    assert m["recall"] == 0.5 and m["false_alarm_rate"] == 0.5


def test_no_rule_alerts_has_the_columns_decide_expects():
    a = g.no_rule_alerts()
    assert list(a.columns) == ["session_id", "t", "rule"] and len(a) == 0


def test_hyperparameters_are_fixed_and_deterministic():
    assert g.GBT_PARAMS["random_state"] == 0 and g.GBT_PARAMS["n_estimators"] == 100
