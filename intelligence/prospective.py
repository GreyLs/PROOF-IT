"""Pre-outcome evaluation. Intentions are never relabelled as employment.

Only frozen server predictions and subsequent decisions may enter the live
report. Offline independent cohorts use the same bounded, role/version-scoped
protocol; score files alone cannot authorize certificate activation.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone
import numpy as np
from scipy.stats import t

VERSION = 'prospective-intentions-1.0.0'


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone_required')
    return parsed.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def protocol(payload, *, _created_at=None):
    role, grade = payload.get('role'), payload.get('grade')
    if not isinstance(role, str) or not 1 <= len(role) <= 80 or grade not in ('junior', 'middle', 'senior', 'lead'):
        raise ValueError('role_grade')
    kind = payload.get('kind', 'forecast')
    if kind not in ('forecast', 'parallel_forms'):
        raise ValueError('kind')
    start, end = timestamp(payload['start_at']), timestamp(payload['end_at'])
    created = datetime.now(timezone.utc) if _created_at is None else timestamp(_created_at)
    if start >= end:
        raise ValueError('observation_window')
    if created > start:
        raise ValueError('protocol_must_precede_enrollment')
    model = payload.get('model_version')
    if not isinstance(model, str) or not 1 <= len(model) <= 100:
        raise ValueError('model_version')
    result = dict(version=VERSION, kind=kind, role=role, grade=grade, created_at=created.isoformat(),
                  model_version=model, start_at=start.isoformat(), end_at=end.isoformat(),
                  minimum_complete_pairs=120, minimum_class_count=20,
                  primary_metric='Brier' if kind == 'forecast' else 'paired-theta-TOST',
                  alpha=.05, planned_looks=1, margin=.2,
                  washout_hours=48, ece_bins=10, bootstrap_replicates=1000,
                  activation_requires=['independent cohort provenance', 'approved independent expert',
                                       'role/version publication', 'psychometric item review'],
                  autonomous_hiring_decision=False)
    if kind=='forecast':
        stage=payload.get('stage','offer')
        if stage not in ('vacancy','offer'):raise ValueError('stage')
        result['stage']=stage
    result['protocol_sha256'] = digest(result)
    return result


def check_protocol(p, kind):
    q = {key: value for key, value in p.items() if key != 'protocol_sha256'}
    if digest(q) != p.get('protocol_sha256') or p.get('kind') != kind:
        raise ValueError('protocol_integrity')
    expected = protocol(p, _created_at=p['created_at'])
    if expected != p:
        raise ValueError('protocol_contract')


def _probability(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('probability')
    return float(value)


def _scores(predictions, labels):
    p, y = np.asarray(predictions, dtype=float), np.asarray(labels, dtype=float)
    if not len(p):
        return None
    clipped = np.clip(p, 1e-12, 1-1e-12)
    bins = []
    ece = 0.
    for index in range(10):
        selected = np.minimum((p*10).astype(int), 9) == index
        if selected.any():
            n = int(selected.sum()); confidence = float(p[selected].mean()); rate = float(y[selected].mean())
            ece += n/len(p)*abs(confidence-rate)
            bins.append({'bin': index, 'n': n, 'mean_probability': confidence, 'observed_rate': rate})
    # Pairwise AUC with ties, bounded cohort size. No misleading AUC on one class.
    positives, negatives = p[y == 1], p[y == 0]
    auc = None
    if len(positives) and len(negatives):
        ordered = np.sort(negatives)
        auc = float(np.mean((np.searchsorted(ordered, positives, 'left') +
                    .5*(np.searchsorted(ordered, positives, 'right')-
                        np.searchsorted(ordered, positives, 'left')))/len(negatives)))
    return {'n': len(p), 'positives': int(y.sum()), 'negatives': int(len(p)-y.sum()),
            'brier': float(np.mean((p-y)**2)),
            'log_loss': float(-np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped))),
            'ece_10_equal_width': ece, 'auc': auc, 'calibration_bins': bins}


def forecast_report(payload):
    records = payload.get('records', [])
    if not isinstance(records, list) or len(records) > 5000:
        raise ValueError('cohort_limit')
    complete = []; excluded = {'synthetic': 0, 'censored': 0}; seen = set()
    by_stage = {stage: [] for stage in ('vacancy', 'offer')}
    for row in records:
        identity = (row['vacancy_id'], row['candidate_id'], row['stage'], row['model_version'])
        if identity in seen or row['stage'] not in by_stage or row['model_version'] != 'bilateral-market-1.0.0':
            raise ValueError('duplicate_or_version')
        seen.add(identity)
        if type(row.get('synthetic')) is not bool:
            raise ValueError('synthetic_provenance_required')
        if row.get('synthetic') is True:
            excluded['synthetic'] += 1; continue
        prediction_at = timestamp(row['created_at'])
        if row.get('candidate_accepts') is None or row.get('employer_accepts') is None:
            excluded['censored'] += 1; continue
        if any(type(row[key]) is not bool for key in ('candidate_accepts', 'employer_accepts')):
            raise ValueError('outcome')
        if min(timestamp(row['candidate_decided_at']), timestamp(row['employer_decided_at'])) <= prediction_at:
            raise ValueError('outcome_leakage')
        prediction = row['prediction']
        for key in ('candidate_acceptance', 'employer_acceptance'):
            _probability(prediction[key]['mean'])
        joint = prediction.get('joint_point_estimate')
        if joint is not None:
            _probability(joint)
        by_stage[row['stage']].append(row); complete.append(row)
    stages = {}
    for stage, rows in by_stage.items():
        metrics = {}
        for side in ('candidate', 'employer'):
            metrics[side] = _scores([r['prediction'][side+'_acceptance']['mean'] for r in rows],
                                   [r[side+'_accepts'] for r in rows])
        paired = [r for r in rows if r['prediction'].get('joint_point_estimate') is not None]
        metrics['joint'] = _scores([r['prediction']['joint_point_estimate'] for r in paired],
                                  [r['candidate_accepts'] and r['employer_accepts'] for r in paired])
        metrics['joint_point_coverage'] = len(paired)/len(rows) if rows else 0
        metrics['adequate_class_counts'] = all(metrics[side] is not None and metrics[side]['n'] >= 120 and
                         min(metrics[side]['positives'], metrics[side]['negatives']) >= 20
                         for side in ('candidate', 'employer'))
        stages[stage] = metrics
    role_blocks = {}
    for stage, rows in by_stage.items():
        blocks = {}
        for row in rows:
            context = row['prediction'].get('context') or {}
            block = str(context.get('role', 'unspecified'))+':'+str(context.get('grade', 'unspecified'))
            blocks.setdefault(block, []).append(row)
        role_blocks[stage] = {block: {side: _scores(
            [row['prediction'][side+'_acceptance']['mean'] for row in items],
            [row[side+'_accepts'] for row in items]) for side in ('candidate', 'employer')}
            for block, items in blocks.items()}
    return {'version': VERSION, 'evaluation_kind': 'prospective prequential intention evaluation',
            'complete_pairs': len(complete), 'excluded': excluded, 'stages': stages, 'role_blocks': role_blocks,
            'status': 'observations_available' if complete else 'awaiting_real_observations',
            'real_employment_validated': False, 'production_calibration_authorized': False,
            'uncertainty_note': 'Repeated candidates/vacancies are dependent; no independent-population confidence claim.',
            'report_sha256': digest(records)}


def parallel_report(payload):
    p = payload['protocol']; check_protocol(p, 'parallel_forms')
    rows = payload['records']
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError('cohort_limit')
    seen = set(); used = []; excluded = {'synthetic': 0, 'incomplete': 0, 'flagged_for_review': 0}
    for r in rows:
        if r['participant_id'] in seen:
            raise ValueError('repeated_participant')
        seen.add(r['participant_id'])
        if (r['role'], r['grade'], r['model_version']) != (p['role'], p['grade'], p['model_version']):
            raise ValueError('mixed_role_grade_version')
        if r.get('synthetic') is not False:
            excluded['synthetic'] += 1; continue
        if r.get('review_required') is not False:
            excluded['flagged_for_review'] += 1; continue
        if r.get('complete') is not True:
            excluded['incomplete'] += 1; continue
        assigned = timestamp(r['assigned_at']); first = timestamp(r['first_at']); second = timestamp(r['second_at'])
        if not timestamp(p['start_at']) <= assigned <= first < second <= timestamp(p['end_at']):
            raise ValueError('protocol_window')
        if (second-first).total_seconds() < 48*3600:
            raise ValueError('washout')
        from intelligence.experiments import assign
        assigned_form = assign({'identity': r['participant_id'], 'scope': p['role']+':'+p['grade'], 'version': p['model_version']})
        if r['order'] != ('AB' if assigned_form['variant'] == 'A' else 'BA'):
            raise ValueError('randomization_mismatch')
        for key in ('theta_a', 'theta_b', 'anchor_a', 'anchor_b'):
            if isinstance(r[key], bool) or not isinstance(r[key], (int, float)) or not math.isfinite(r[key]) or abs(r[key]) > 6:
                raise ValueError('score')
        for key in ('form_a_sha256', 'form_b_sha256', 'source_sha256'):
            if not isinstance(r.get(key), str) or len(r[key]) != 64 or any(c not in '0123456789abcdef' for c in r[key]):
                raise ValueError('source_digest')
        if r['form_a_sha256'] == r['form_b_sha256']:
            raise ValueError('identical_forms')
        used.append(r)
    def tost(differences):
        if len(differences) < 2:
            return None
        d = np.asarray(differences); mean = float(d.mean()); se = float(d.std(ddof=1)/math.sqrt(len(d)))
        probability = (0. if abs(mean) < .2 else 1.) if se == 0 else max(
            float(t.sf((mean+.2)/se, len(d)-1)), float(t.cdf((mean-.2)/se, len(d)-1)))
        radius = float(t.ppf(.95, len(d)-1))*se
        return {'mean_difference': mean, 'interval_90': [mean-radius, mean+radius], 'tost_p': probability,
                'equivalent': probability < .05, 'n': len(d)}
    theta = tost([r['theta_a']-r['theta_b'] for r in used])
    anchors = tost([r['anchor_a']-r['anchor_b'] for r in used])
    orders = {order: tost([r['theta_a']-r['theta_b'] for r in used if r['order'] == order]) for order in ('AB', 'BA')}
    ab = sum(r['order'] == 'AB' for r in used)
    from scipy.stats import binomtest
    srm = float(binomtest(ab, len(used), .5).pvalue) if used else None
    gate = bool(len(used) >= 120 and theta['equivalent'] and anchors['equivalent'] and srm >= .01 and
                all(v and v['n'] >= 40 and v['equivalent'] for v in orders.values()))
    return {'version': VERSION, 'protocol_sha256': p['protocol_sha256'], 'n': len(used), 'excluded': excluded,
            'theta': theta, 'anchors': anchors, 'order_blocks': orders, 'srm_exact_p': srm,
            'statistical_gate_passed': gate, 'production_activation_allowed': False,
            'activation_requires': p['activation_requires'], 'generalizes_to_other_roles': False,
            'source_note': 'Operator-supplied independent cohort; hashes bind artifacts, not human authenticity.',
            'report_sha256': digest(rows)}


def macro_ablation(payload):
    """Fixed temporal holdout, paired loss delta, cluster-by-date bootstrap."""
    p = payload['protocol']; check_protocol(p, 'forecast')
    rows = payload['records']; cutoff = timestamp(p['start_at'])
    if not isinstance(rows, list) or not 2 <= len(rows) <= 5000:
        raise ValueError('cohort')
    dates = {}; seen = set()
    for r in rows:
        if r['id'] in seen or r.get('synthetic') is not False:
            raise ValueError('duplicate_or_synthetic')
        seen.add(r['id'])
        if (r['role'], r['grade'], r['model_version']) != (p['role'], p['grade'], p['model_version']):
            raise ValueError('scope')
        if r.get('stage')!=p['stage']:
            raise ValueError('stage_scope')
        at = timestamp(r['prediction_at'])
        if not timestamp(r['trained_until']) < cutoff <= at < timestamp(r['outcome_at']) <= timestamp(p['end_at']):
            raise ValueError('temporal_holdout')
        if timestamp(r['macro_published_at']) > at:
            raise ValueError('macro_lookahead')
        if type(r['outcome']) is not bool:
            raise ValueError('outcome')
        baseline, enhanced = _probability(r['baseline']), _probability(r['with_macro'])
        dates.setdefault(at.date().isoformat(), []).append((enhanced-r['outcome'])**2-(baseline-r['outcome'])**2)
    clusters = list(dates.values()); rng = np.random.default_rng(7401)
    boot = [float(np.mean([d for i in rng.integers(0, len(clusters), len(clusters)) for d in clusters[i]])) for _ in range(1000)]
    interval = [float(x) for x in np.quantile(boot, [.025, .975])]
    return {'version': VERSION, 'metric': 'Brier(with_macro) - Brier(baseline)', 'n': len(rows),
            'date_clusters': len(clusters), 'mean_delta': float(np.mean([d for x in clusters for d in x])),
            'cluster_bootstrap_interval_95': interval, 'bootstrap_replicates': 1000,
            'incremental_accuracy_gate_passed': len(rows) >= 120 and len(clusters) >= 30 and interval[1] < 0,
            'ranking_effect': 0, 'forecast_activation_allowed': False,
            'interpretation': 'Paired prospective predictive gain, not a causal market effect.',
            'protocol_sha256': p['protocol_sha256'], 'report_sha256': digest(rows)}
