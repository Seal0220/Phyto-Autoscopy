"""Audit or repair existing round reference models without resetting analysis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from threading import Event

from _bootstrap import bootstrap


def main() -> None:
    bootstrap()
    from app.analysis.reconstruction.model_repair import (
        activate_repair, read_model_repair, rebuild_reference_model,
    )
    from app.analysis.rounds.paths import round_artifact_directory

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis_id')
    parser.add_argument('--database', type=Path, default=Path('data/database/phyto_autoscopy.sqlite3'))
    parser.add_argument('--round', type=int, action='append', dest='rounds')
    parser.add_argument('--all-unstable', action='store_true')
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT output_path FROM analysis_runs WHERE analysis_id=?', (args.analysis_id,)).fetchone()
        if row is None:
            parser.error('找不到分析紀錄。')
        root = Path(row[0]).resolve()
        models = [json.loads(row[0]) for row in connection.execute(
            'SELECT payload_json FROM analysis_round_models WHERE analysis_id=?', (args.analysis_id,))]
    models.sort(key=lambda model: int(model['round_key'].rsplit('.', 1)[-1]))
    failures = []
    for model in models:
        if model['status'] != 'completed':
            continue
        key = model['round_key']
        number = int(key.rsplit('.', 1)[-1])
        directory = round_artifact_directory(root, key) / 'pose_debug/model_reference'
        original = json.loads((directory / 'context.json').read_text(encoding='utf-8'))
        orbit = original['reference'].get('orbit') or {}
        unstable = orbit.get('rotation_rmse_deg', float('inf')) > 2 or orbit.get('position_rmse_over_radius', float('inf')) > .035
        selected = number in (args.rounds or []) or args.all_unstable and unstable
        try:
            accepted = read_model_repair(root, key, Path(original['model']['gaussian_model_path']))
        except (OSError, ValueError, KeyError):
            accepted = None
        if accepted is not None:
            if selected:
                print(json.dumps({'round_key': key, 'status': 'already_repaired'}, ensure_ascii=False), flush=True)
            continue
        if not args.rounds and not args.all_unstable:
            if unstable:
                print(json.dumps({'round_key': key, 'rotation_rmse_deg': orbit.get('rotation_rmse_deg'),
                    'position_rmse_over_radius': orbit.get('position_rmse_over_radius')}, ensure_ascii=False))
            continue
        if not selected:
            continue
        try:
            event = Event()
            def progress(stage, fraction, message):
                print(json.dumps({'round_key': key, 'stage': stage, 'progress': fraction, 'message': message}, ensure_ascii=False), flush=True)
            original, candidate = rebuild_reference_model(root, key, cancel_event=event, progress=progress)
            active = activate_repair(root, key, original, candidate)
            print(json.dumps({'round_key': key, 'status': 'repaired', 'manifest': str(active)}, ensure_ascii=False), flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as error:
            failures.append(key)
            print(json.dumps({'round_key': key, 'status': 'kept_original', 'reason': str(error)}, ensure_ascii=False), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
