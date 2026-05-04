"""
Model accuracy report — reads prediction_log.jsonl and produces performance metrics
across sub-sector tags, company types, and market regimes.

Usage:
    python -m ml.accuracy_report           # prints to stdout
    python -m ml.accuracy_report --json    # JSON output
"""
import json
import sys
from collections import defaultdict
from ml.log import PREDICTION_LOG_PATH


def _load_labeled() -> list:
    records = []
    try:
        with open(PREDICTION_LOG_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line.strip())
                    if r.get('actual_price_365d') and r.get('predicted_price'):
                        records.append(r)
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return records


def _mae(errors: list) -> float:
    return sum(abs(e) for e in errors) / len(errors) if errors else 0.0


def _bias(errors: list) -> float:
    return sum(errors) / len(errors) if errors else 0.0


def generate_report() -> dict:
    records = _load_labeled()
    if not records:
        return {'error': 'No labeled records in prediction log'}

    overall_errors = []
    by_tag    = defaultdict(list)
    by_type   = defaultdict(list)
    by_regime = defaultdict(list)

    for r in records:
        predicted = float(r['predicted_price'])
        actual    = float(r['actual_price_365d'])
        pct_error = (predicted - actual) / actual  # positive = overestimate

        overall_errors.append(pct_error)
        by_tag[r.get('sub_sector_tag', 'unknown')].append(pct_error)
        by_type[r.get('company_type', 'unknown')].append(pct_error)
        by_regime[r.get('market_regime', 'unknown')].append(pct_error)

    def _summary(group: dict) -> dict:
        return {
            k: {'n': len(v), 'mae_pct': round(_mae(v) * 100, 1), 'bias_pct': round(_bias(v) * 100, 1)}
            for k, v in sorted(group.items(), key=lambda x: -len(x[1]))
        }

    return {
        'n_labeled':    len(records),
        'overall_mae':  round(_mae(overall_errors) * 100, 1),
        'overall_bias': round(_bias(overall_errors) * 100, 1),
        'by_tag':       _summary(by_tag),
        'by_type':      _summary(by_type),
        'by_regime':    _summary(by_regime),
    }


def print_report(report: dict) -> None:
    if 'error' in report:
        print(f"No data: {report['error']}")
        return

    print(f"\nML Accuracy Report  —  {report['n_labeled']} labeled predictions")
    print(f"Overall MAE: {report['overall_mae']}%   Bias: {report['overall_bias']}%\n")

    for section, label in [('by_type', 'By Company Type'), ('by_regime', 'By Market Regime'), ('by_tag', 'By Sub-Sector Tag')]:
        print(f"{label}:")
        print(f"  {'Group':<30} {'N':>5}  {'MAE%':>7}  {'Bias%':>7}")
        print(f"  {'-'*52}")
        for k, v in report[section].items():
            print(f"  {k:<30} {v['n']:>5}  {v['mae_pct']:>6.1f}%  {v['bias_pct']:>6.1f}%")
        print()


if __name__ == '__main__':
    report = generate_report()
    if '--json' in sys.argv:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
