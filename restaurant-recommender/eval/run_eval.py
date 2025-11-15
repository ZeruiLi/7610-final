"""Minimal offline evaluation harness for the restaurant recommender.

Usage:
  python run_eval.py --base http://localhost:8010 --k 5 --out eval/report_v1
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import requests


def load_jsonl(path: Path) -> list[dict[str, Any]]:
  with path.open('r', encoding='utf-8') as fh:
    return [json.loads(line) for line in fh if line.strip()]


def normalise(text: Any) -> str:
  if text is None:
    return ''
  value = unicodedata.normalize('NFKC', str(text)).lower()
  value = re.sub(r'[\s\-_,\.·（）()\u3000]+', '', value)
  return value


def candidate_matches(candidate: dict[str, Any], expected: dict[str, Any]) -> bool:
  place = candidate.get('place') or {}
  cand_name = normalise(place.get('name'))
  exp_name = normalise(expected.get('name'))
  if cand_name and exp_name:
    if cand_name in exp_name or exp_name in cand_name:
      return True

  cand_addr = normalise(place.get('address'))
  exp_addr = normalise(expected.get('address'))
  if cand_addr and exp_addr and (cand_addr in exp_addr or exp_addr in cand_addr):
    return True

  return False


def has_trusted_source(candidate: dict[str, Any]) -> bool:
  place = candidate.get('place') or {}
  if place.get('website') or place.get('datasource_url'):
    return True
  detail_sources = candidate.get('detail_sources') or []
  for item in detail_sources:
    if not item:
      continue
    url = item.get('url') if isinstance(item, dict) else None
    if isinstance(url, str) and url.startswith('http'):
      return True
  return False


@dataclass
class EvalResult:
    qid: str
    precision: float
    hit_rate: float
    source_rate: float
    latency_ms: float
    hits: int
    evaluated: int
    median_distance_miles: float
    trust_score: float
    tag_match_rate: float
    hard_satisfaction: float
    error: str | None = None


def evaluate_query(base_url: str, payload: dict[str, Any], labels: list[dict[str, Any]], k: int, timeout: float) -> EvalResult:
  url = f"{base_url}/recommend"
  started = time.perf_counter()
  response = requests.post(url, json={'query': payload['query']}, timeout=timeout)
  latency_ms = (time.perf_counter() - started) * 1000

    if not response.ok:
        snippet = response.text[:200]
        return EvalResult(
            qid=payload['qid'],
            precision=0.0,
            hit_rate=0.0,
            source_rate=0.0,
            latency_ms=latency_ms,
            hits=0,
            evaluated=0,
            median_distance_miles=float('nan'),
            trust_score=0.0,
            tag_match_rate=0.0,
            hard_satisfaction=0.0,
            error=f"HTTP {response.status_code}: {snippet}",
        )

  try:
    data = response.json()
    except ValueError as exc:
        return EvalResult(
            qid=payload['qid'],
            precision=0.0,
            hit_rate=0.0,
            source_rate=0.0,
            latency_ms=latency_ms,
            hits=0,
            evaluated=0,
            median_distance_miles=float('nan'),
            trust_score=0.0,
            tag_match_rate=0.0,
            hard_satisfaction=0.0,
            error=f"invalid json: {exc}",
        )

  candidates: list[dict[str, Any]] = data.get('candidates') or []
  preferences = data.get('preferences') or {}
  top_k = candidates[:k]
  evaluated = len(top_k)

  expected_include = [s.lower() for s in (payload.get('must_include') or [])]
  expected_exclude = [s.lower() for s in (payload.get('must_exclude') or [])]
  expected_dining = payload.get('dining_time')
  strict_open_expected = payload.get('strict_open_check', True)

  hits = 0
  for cand in top_k:
    if any(candidate_matches(cand, expected) for expected in labels):
      hits += 1

  precision = hits / evaluated if evaluated else 0.0
  hit_rate = 1.0 if hits > 0 else 0.0

  source_hits = sum(1 for cand in top_k if has_trusted_source(cand))
  source_rate = source_hits / evaluated if evaluated else 0.0

  distances = [cand.get('distance_miles') for cand in top_k if isinstance(cand.get('distance_miles'), (int, float))]
  median_distance = statistics.median(distances) if distances else float('nan')

  trust_scores = [cand.get('source_trust_score', 0.0) for cand in top_k]
  trust_score = sum(trust_scores) / evaluated if evaluated else 0.0

  has_pref = bool(preferences.get('cuisines') or preferences.get('ambiance'))
  tag_matches = sum(1 for cand in top_k if cand.get('match_cuisine') or cand.get('match_ambience'))
  tag_match_rate = (tag_matches / evaluated) if evaluated else 0.0
  if not has_pref:
    tag_match_rate = 1.0 if evaluated else 0.0

  hard_success = 0
  hard_relevant = bool(expected_include or expected_exclude or expected_dining)
  for cand in top_k:
    violations = {
      str(v).lower()
      for v in (cand.get('violated_constraints') or [])
      if isinstance(v, str)
    }
    ok = True
    if expected_include:
      ok = ok and 'missing_required_cuisine' not in violations and cand.get('match_cuisine', False)
    if expected_exclude:
      # if exclusion violated it would likely appear in violations list; safeguard by checking text
      if any(ex in " ".join(cand.get('primary_tags') or []).lower() for ex in expected_exclude):
        ok = False
    if expected_dining or strict_open_expected:
      if not cand.get('is_open_ok', True):
        ok = False
      if 'opening_hours_unknown' in violations and strict_open_expected:
        ok = False
    if ok:
      hard_success += 1

  hard_satisfaction = 1.0 if evaluated and not hard_relevant else (hard_success / evaluated if evaluated else 0.0)

  return EvalResult(
    qid=payload['qid'],
    precision=precision,
    hit_rate=hit_rate,
    source_rate=source_rate,
    latency_ms=latency_ms,
    hits=hits,
    evaluated=evaluated,
    median_distance_miles=median_distance,
    trust_score=trust_score,
    tag_match_rate=tag_match_rate,
    hard_satisfaction=hard_satisfaction,
  )


def main() -> None:
  parser = argparse.ArgumentParser(description='Offline evaluation for restaurant recommender')
  parser.add_argument('--base', default='http://localhost:8010', help='FastAPI base URL')
  parser.add_argument('--queries', default='eval/queries_v1.jsonl', help='Queries JSONL path')
  parser.add_argument('--judgments', default='eval/judgments_v1.jsonl', help='Judgments JSONL path')
  parser.add_argument('--k', type=int, default=5, help='Cut-off for precision/hit metrics')
  parser.add_argument('--concurrency', type=int, default=2, help='Number of worker threads')
  parser.add_argument('--out', default='eval/report_v1', help='Output directory for reports')
  parser.add_argument('--baseline', help='Optional baseline metrics.csv to compare against')
  parser.add_argument('--timeout', type=float, default=25.0, help='Request timeout in seconds')
  args = parser.parse_args()

  base_url = args.base.rstrip('/')
  out_dir = Path(args.out)
  out_dir.mkdir(parents=True, exist_ok=True)

  queries_path = Path(args.queries)
  judgments_path = Path(args.judgments)

  if not queries_path.exists():
    raise FileNotFoundError(f'queries file not found: {queries_path}')
  if not judgments_path.exists():
    raise FileNotFoundError(f'judgments file not found: {judgments_path}')

  queries = load_jsonl(queries_path)
  judgments = {item['qid']: item.get('labels', []) for item in load_jsonl(judgments_path)}

  results: list[EvalResult] = []
  errors: list[dict[str, Any]] = []

  def task(payload: dict[str, Any]) -> EvalResult:
    try:
      labels = judgments.get(payload['qid'], [])
      return evaluate_query(base_url, payload, labels, args.k, args.timeout)
    except requests.RequestException as exc:
      return EvalResult(
        qid=payload['qid'],
        precision=0.0,
        hit_rate=0.0,
        source_rate=0.0,
        latency_ms=float('nan'),
        hits=0,
        evaluated=0,
        error=str(exc),
      )

  workers = max(1, args.concurrency)
  with ThreadPoolExecutor(max_workers=workers) as executor:
    future_map = {executor.submit(task, payload): payload for payload in queries}
    for future in as_completed(future_map):
      result = future.result()
      results.append(result)
      if result.error:
        errors.append({'qid': result.qid, 'error': result.error})

  results.sort(key=lambda item: item.qid)

  metrics_path = out_dir / 'metrics.csv'
  with metrics_path.open('w', newline='', encoding='utf-8') as fh:
    writer = csv.writer(fh)
    writer.writerow([
      'qid',
      f'precision@{args.k}',
      f'hit@{args.k}',
      'source_rate',
      'latency_ms',
      'hits',
      'evaluated',
      'median_distance_miles',
      'trust_score',
      'tag_match_rate',
      'hard_satisfaction',
      'error',
    ])
    for item in results:
      writer.writerow([
        item.qid,
        f'{item.precision:.3f}',
        f'{item.hit_rate:.3f}',
        f'{item.source_rate:.3f}',
        f'{item.latency_ms:.1f}' if math.isfinite(item.latency_ms) else 'nan',
        item.hits,
        item.evaluated,
        f'{item.median_distance_miles:.2f}' if math.isfinite(item.median_distance_miles) else 'nan',
        f'{item.trust_score:.3f}',
        f'{item.tag_match_rate:.3f}',
        f'{item.hard_satisfaction:.3f}',
        item.error or '',
      ])

  summary_path = out_dir / 'report.md'
  precisions = [item.precision for item in results if not item.error]
  hit_rates = [item.hit_rate for item in results if not item.error]
  source_rates = [item.source_rate for item in results if not item.error]
  latencies = [item.latency_ms for item in results if not item.error and math.isfinite(item.latency_ms)]
  median_miles = [item.median_distance_miles for item in results if not item.error and math.isfinite(item.median_distance_miles)]
  trust_scores = [item.trust_score for item in results if not item.error]
  tag_match_rates = [item.tag_match_rate for item in results if not item.error]
  hard_sats = [item.hard_satisfaction for item in results if not item.error]

  def avg(values: Iterable[float]) -> float:
    return sum(values) / len(values) if values else 0.0

  with summary_path.open('w', encoding='utf-8') as fh:
    fh.write('# Evaluation Summary\n\n')
    fh.write(f'- Queries evaluated: {len(results)}\n')
    fh.write(f'- Errors: {len(errors)}\n')
    fh.write(f'- Precision@{args.k}: {avg(precisions):.3f}\n')
    fh.write(f'- Hit@{args.k}: {avg(hit_rates):.3f}\n')
    fh.write(f'- Source coverage: {avg(source_rates):.3f}\n')
    if latencies:
      fh.write(f'- Latency mean / median (ms): {avg(latencies):.1f} / {statistics.median(latencies):.1f}\n')
    if median_miles:
      fh.write(f'- Median distance (miles): {statistics.median(median_miles):.2f}\n')
    fh.write(f'- Trust score (avg): {avg(trust_scores):.3f}\n')
    fh.write(f'- Preference match rate: {avg(tag_match_rates):.3f}\n')
    fh.write(f'- Hard constraint satisfaction: {avg(hard_sats):.3f}\n')
    fh.write('\n')

    if errors:
      fh.write('## Errors\n')
      for item in errors:
        fh.write(f"- {item['qid']}: {item['error']}\n")

    if args.baseline:
      baseline_path = Path(args.baseline)
      if baseline_path.exists():
        try:
          with baseline_path.open('r', encoding='utf-8') as base_file:
            reader = csv.DictReader(base_file)
            baseline_precisions: list[float] = []
            baseline_hit: list[float] = []
            baseline_source: list[float] = []
            baseline_hard: list[float] = []
            for row in reader:
              try:
                baseline_precisions.append(float(row.get(f'precision@{args.k}', 0.0)))
                baseline_hit.append(float(row.get(f'hit@{args.k}', 0.0)))
                baseline_source.append(float(row.get('source_rate', 0.0)))
                baseline_hard.append(float(row.get('hard_satisfaction', 0.0)))
              except (TypeError, ValueError):
                continue
          fh.write('\n## Baseline comparison\n')
          fh.write(f"- Δ Precision@{args.k}: {avg(precisions) - avg(baseline_precisions):+.3f}\n")
          fh.write(f"- Δ Hit@{args.k}: {avg(hit_rates) - avg(baseline_hit):+.3f}\n")
          fh.write(f"- Δ Source coverage: {avg(source_rates) - avg(baseline_source):+.3f}\n")
          fh.write(f"- Δ Hard satisfaction: {avg(hard_sats) - avg(baseline_hard):+.3f}\n")
        except Exception as exc:
          fh.write(f"\n_Baseline comparison failed: {exc}_\n")

  if errors:
    errors_path = out_dir / 'errors.jsonl'
    with errors_path.open('w', encoding='utf-8') as fh:
      for item in errors:
        fh.write(json.dumps(item, ensure_ascii=False) + '\n')

  print(f'Evaluation finished. Metrics written to {metrics_path}')


if __name__ == '__main__':
  main()
