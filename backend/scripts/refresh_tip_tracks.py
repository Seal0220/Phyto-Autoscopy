"""Repair existing tip tracks only; never start an analysis or train a model."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from _bootstrap import bootstrap


def main() -> None:
    bootstrap()
    from app.analysis.artifacts import AnalysisArtifacts
    from app.database.connection import Database
    from app.repositories.analysis_repository import AnalysisRepository
    from app.services.analysis_service import AnalysisService

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_id")
    parser.add_argument("--database", type=Path, default=Path("data/database/phyto_autoscopy.sqlite3"))
    parser.add_argument("--staged", type=Path, help="Apply a read-only replay after its writer has stopped.")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("Database does not exist.")
    database = Database(args.database)
    repository = AnalysisRepository(database)
    # No AppContext, migrations, job manager or server is created.
    service = object.__new__(AnalysisService)
    service.repository = repository
    service._lock = RLock()
    service.progress_callback = None
    run = service._require_run(args.analysis_id)
    if run.status not in {"partially_completed", "completed", "paused", "cancelled", "failed"}:
        raise RuntimeError("Tip backfill requires an idle analysis; its current work was left unchanged.")
    artifacts = AnalysisArtifacts(Path(run.output_path).resolve())
    service._artifacts = lambda _: artifacts
    backup = Path("data/temp/tip_track_repairs") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup.mkdir(parents=True)
    snapshot = {
        "run": run.model_dump(mode="json"),
        "rounds": [item.model_dump(mode="json") for item in repository.list_rounds(args.analysis_id)],
        "landmarks": [item.model_dump(mode="json") for item in repository.list_tip_landmarks(args.analysis_id)],
        "observations": [item.model_dump(mode="json") for item in repository.list_tip_observations(args.analysis_id)],
        "corrections": [item.model_dump(mode="json") for item in repository.list_tip_corrections(args.analysis_id)],
        "trajectory": [item.model_dump(mode="json") for item in repository.list_tip_trajectory(args.analysis_id)],
        "models": [item.model_dump(mode="json") for item in repository.list_round_models(args.analysis_id)],
    }
    (backup / "before.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    def checksum(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    protected = {artifacts.root / item["model_path"] for item in snapshot["models"] if item.get("model_path")}
    protected.update((artifacts.root / "checkpoints").rglob("*.sqlite3"))
    protected.update((artifacts.root / "rounds").rglob("*.pt"))
    protected_hashes = {str(path): checksum(path) for path in protected if path.is_file()}
    (backup / "protected_hashes.json").write_text(json.dumps(protected_hashes, indent=2), encoding="utf-8")
    print(json.dumps({"backup": str(backup), "existing_rounds": len(snapshot["landmarks"]),
                      "confirmed_before": sum(item.get("image_tip_confirmed", False) for item in snapshot["landmarks"])}), flush=True)

    def progress(index, total, tip):
        print(json.dumps({"round": tip.round_id, "processed": index, "total": total,
                          "confirmed": tip.image_tip_confirmed,
                          "observations": tip.image_observations,
                          "failures": {camera: detail.get("reason") for camera, detail in tip.tracking.get("cameras", {}).items()
                                       if detail.get("reason")}}), flush=True)

    try:
        if args.staged:
            from app.models.analysis_models import TipCorrection, TipLandmark, TipObservation2D

            staged = json.loads(args.staged.read_text(encoding="utf-8"))
            if staged.get("analysis_id") != args.analysis_id:
                raise ValueError("The staged replay belongs to another analysis.")
            corrections = [TipCorrection.model_validate(item) for item in staged["corrections"]]
            if corrections != repository.list_tip_corrections(args.analysis_id):
                raise RuntimeError("Manual corrections changed; replay the captures again.")
            current = {item.round_key: item for item in repository.list_tip_landmarks(args.analysis_id)}
            initial = {key: TipLandmark.model_validate(payload) for key, payload in staged["initial"].items()}
            updates = []
            for payload in staged["landmarks"]:
                landmark = TipLandmark.model_validate(payload)
                if landmark.round_key not in staged["observations"]:
                    continue
                previous = current.get(landmark.round_key)
                if previous != initial.get(landmark.round_key):
                    raise RuntimeError("A tip result changed after replay; no staged updates were applied.")
                if (previous is None or landmark.analysis_id != args.analysis_id
                        or previous.tip_id != landmark.tip_id
                        or previous.record_id != landmark.record_id
                        or previous.mode_id != landmark.mode_id or previous.round_id != landmark.round_id):
                    raise ValueError("A staged replay may update only its existing round results.")
                observations = [TipObservation2D.model_validate(item)
                                for item in staged["observations"][landmark.round_key]]
                if (not landmark.image_tip_confirmed or len(observations) != 2
                        or {item.view_id for item in observations} != set(landmark.supporting_view_ids)
                        or not all(item.selected for item in observations)
                        or not all(landmark.tracking.get("cameras", {}).get(camera, {}).get("identity_verified")
                                   for camera in ("top", "side"))):
                    raise ValueError("Only a verified pair of existing camera observations may be applied.")
                if any(item.analysis_id != args.analysis_id or item.round_key != landmark.round_key
                       for item in observations):
                    raise ValueError("Staged observations belong to another round.")
                retained = {key: previous.tracking[key] for key in ("model_tip", "measurement_warning")
                            if key in previous.tracking}
                landmark = landmark.model_copy(update={"tracking": {**landmark.tracking, **retained}})
                updates.append((previous, landmark, observations))
            applied = 0
            try:
                for previous, landmark, observations in updates:
                    if not repository.refresh_existing_tip_track(landmark, observations,
                            expected_tip=previous, expected_corrections=corrections):
                        raise RuntimeError("Concurrent tip edits detected; staged application stopped.")
                    artifacts.write_tip_landmark(landmark)
                    applied += 1
            finally:
                if applied:
                    service._refresh_tip_correction_artifacts(run, resolve_pending=False, preserve_status=True)
            result = {"updated_rounds": applied, "existing_rounds": len(current),
                      "confirmed_rounds": sum(item.image_tip_confirmed
                                              for item in service._resolved_tip_landmarks(args.analysis_id))}
        else:
            result = service.refresh_existing_tip_tracks(args.analysis_id, progress_callback=progress)
        after = repository.get(args.analysis_id)
        unchanged = {
            "model_and_checkpoint_bytes": all(checksum(Path(path)) == value for path, value in protected_hashes.items()),
            "manual_corrections": snapshot["corrections"] == [item.model_dump(mode="json") for item in repository.list_tip_corrections(args.analysis_id)],
            "analysis_lifecycle": all(getattr(run, key) == getattr(after, key) for key in ("status", "stage", "progress", "current_frame", "total_frames")),
            "model_results": snapshot["models"] == [item.model_dump(mode="json") for item in repository.list_round_models(args.analysis_id)],
        }
        report = {**result, "unchanged": unchanged, "backup": str(backup),
                  "lifecycle_before": {key: getattr(run, key) for key in ("status", "stage", "progress", "current_frame", "total_frames")},
                  "lifecycle_after": {key: getattr(after, key) for key in ("status", "stage", "progress", "current_frame", "total_frames")}}
        (backup / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        if not all(unchanged.values()):
            raise RuntimeError("Concurrent changes detected; inspect the repair report.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
