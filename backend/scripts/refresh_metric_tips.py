"""Apply a verified fixed-camera calibration and measure existing tips only."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

import numpy as np

from _bootstrap import bootstrap


def main():
    bootstrap()
    from app.analysis.artifacts import AnalysisArtifacts
    from app.analysis.run_metadata import utc_now_iso
    from app.analysis.rounds.paths import round_artifact_directory
    from app.analysis.tip.metric_measurement import measure_image_tip
    from app.database.connection import Database
    from app.models.analysis_models import CameraPoseResult
    from app.repositories.analysis_repository import AnalysisRepository
    from app.services.analysis_service import AnalysisService

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_id")
    parser.add_argument("--registration", required=True, type=Path)
    parser.add_argument("--round-key", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database", type=Path, default=Path("data/database/phyto_autoscopy.sqlite3"))
    args = parser.parse_args()
    database = Database(args.database)
    repository = AnalysisRepository(database)
    service = object.__new__(AnalysisService)
    service.repository, service._lock, service.progress_callback = repository, RLock(), None
    try:
        run = repository.get(args.analysis_id)
        if run is None:
            raise ValueError("Analysis does not exist.")
        if args.apply and run.status not in {"paused", "completed", "partially_completed", "cancelled", "failed"}:
            raise RuntimeError("Pause the active analysis before applying metric backfill; existing work was left unchanged.")
        artifacts = AnalysisArtifacts(Path(run.output_path))
        service._artifacts = lambda _: artifacts
        source = round_artifact_directory(artifacts.root, args.round_key) / "pose_debug/model_reference"
        context = json.loads((source / "context.json").read_text(encoding="utf-8"))
        registration = json.loads(args.registration.read_text(encoding="utf-8"))
        quality = registration["quality"]
        if quality.get("source_reference_signature") != context["reference"]["signature"]:
            raise ValueError("The measurement calibration belongs to another reference geometry.")
        if not np.isclose(quality["baseline_mm"], run.parameters["pose_strategy"]["baseline_mm"]):
            raise ValueError("The measured baseline changed after calibration.")
        validation = quality["fixed_camera_localization"]
        captures = validation["captures"]
        if (validation.get("validation") != "shared_pose_on_independent_captures" or len(captures) < 3
                or len({item["view_id"] for item in captures}) != len(captures)
                or any(item["inlier_count"] < 24 or item["rmse_px"] > 3.7 for item in captures)):
            raise ValueError("Fixed-camera localization lacks successful independent capture checks.")
        source_views = {view.view_id: view for view in repository.list_views(run.analysis_id, args.round_key)}
        if any(item["view_id"] not in source_views or source_views[item["view_id"]].camera_id != "top" for item in captures):
            raise ValueError("Calibration captures do not belong to its source round.")
        worker_job = json.loads((source / "sfm/worker/job.json").read_text(encoding="utf-8"))
        if worker_job["intrinsics_snapshot"] != run.intrinsics_snapshot:
            raise ValueError("Camera intrinsics changed after the calibration input was frozen.")
        matrices = {camera: np.asarray(registration["poses"][camera]) for camera in ("top", "side")}
        centers = {}
        for camera, matrix in matrices.items():
            if (matrix.shape != (4, 4) or not np.isfinite(matrix).all()
                    or not np.allclose(matrix[3], [0, 0, 0, 1])
                    or not np.allclose(matrix[:3, :3] @ matrix[:3, :3].T, np.eye(3), atol=1e-6)
                    or not np.isclose(np.linalg.det(matrix[:3, :3]), 1., atol=1e-6)):
                raise ValueError("Invalid calibrated camera pose.")
            centers[camera] = -(matrix[:3, :3].T @ matrix[:3, 3])
        if not np.isclose(np.linalg.norm(centers["top"] - centers["side"]), quality["baseline_mm"], atol=1e-3):
            raise ValueError("Calibration poses disagree with the measured baseline.")
        rounds = repository.list_rounds(run.analysis_id)
        existing_poses = repository.list_camera_poses(run.analysis_id)
        if any(pose.valid for pose in existing_poses):
            raise RuntimeError("Existing calibrated poses must be reviewed before replacing their coordinate frame.")
        poses = []
        views_by_round = {}
        poses_by_round = {}
        for item in rounds:
            views = views_by_round[item.round_key] = repository.list_views(run.analysis_id, item.round_key)
            round_poses = []
            for view in views:
                if view.camera_id not in matrices:
                    continue
                matrix = matrices[view.camera_id]
                round_poses.append(CameraPoseResult(analysis_id=run.analysis_id, round_key=item.round_key,
                    view_id=view.view_id, camera_id=view.camera_id, rotation_matrix=matrix[:3, :3].tolist(),
                    translation_vector_mm=matrix[:3, 3].tolist(), camera_center_world_mm=centers[view.camera_id].tolist(),
                    pose_source="rig_stereo", valid=True))
            poses.extend(round_poses)
            poses_by_round[item.round_key] = round_poses
        tips = repository.list_tip_landmarks(run.analysis_id)
        corrections = repository.list_tip_corrections(run.analysis_id)
        resolved = {tip.round_key: tip for tip in tips}
        for correction in corrections:
            resolved[correction.round_key] = correction.corrected_tip
        preview = [measure_image_tip(tip, views_by_round[tip.round_key], poses_by_round[tip.round_key], run.intrinsics_snapshot,
            maximum_error_px=float(run.parameters.get("tip_analysis", {}).get("maximum_reprojection_error_px", 5))) for tip in resolved.values()]
        summary = {"analysis_id": run.analysis_id, "fixed_camera_pose_count": len(poses),
                   "image_tips": sum(tip.image_tip_confirmed for tip in preview),
                   "metric_tips": sum(tip.valid for tip in preview), "applied": args.apply}
        print(json.dumps(summary), flush=True)
        if not args.apply:
            return
        backup = Path("data/temp/metric_tip_repairs") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup.mkdir(parents=True)
        models = repository.list_round_models(run.analysis_id)
        snapshot = {"run": run.model_dump(mode="json", exclude={"parameters"}),
                    "rounds": [item.model_dump(mode="json") for item in rounds],
                    "poses": [pose.model_dump(mode="json") for pose in existing_poses],
                    "tips": [tip.model_dump(mode="json") for tip in tips],
                    "corrections": [item.model_dump(mode="json") for item in corrections],
                    "trajectory": [item.model_dump(mode="json") for item in repository.list_tip_trajectory(run.analysis_id)],
                    "models": [item.model_dump(mode="json") for item in models]}
        (backup / "before.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        def checksum(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        protected = {artifacts.root / model.model_path for model in models if model.model_path}
        protected.update((artifacts.root / "rounds").rglob("*.pt"))
        hashes = {str(path): checksum(path) for path in protected if path.is_file()}
        (backup / "protected_hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
        if (repository.get(run.analysis_id).status != run.status
                or repository.list_tip_corrections(run.analysis_id) != corrections
                or repository.list_tip_landmarks(run.analysis_id) != tips):
            raise RuntimeError("The analysis changed while preparing its backup; no calibration was applied.")
        service._store_model_registration(run, registration, round_key=args.round_key)
        repository.replace_camera_poses(run.analysis_id, poses)
        repository.update_pose_alignment(run.analysis_id, camera_pose_results=[pose.model_dump(mode="json") for pose in poses],
            pose_estimation_version="shared_fixed_render_pnp_v1", pose_quality={**quality, "coordinate_unit": "millimetre",
                "source_round_key": args.round_key, "absolute_accuracy_verified": False}, updated_at=utc_now_iso())
        result = service.refresh_existing_tip_measurements(run.analysis_id)
        after = repository.get(run.analysis_id)
        original_clicks = lambda items: [{name: getattr(item, name) for name in (
            "correction_id", "operator_id", "created_at", "reason", "invalid", "observations",
            "model_point_id", "model_signature", "model_point_relative_xyz")} for item in items]
        unchanged = {"model_and_training_bytes": all(checksum(Path(path)) == value for path, value in hashes.items()),
            "model_results": models == repository.list_round_models(run.analysis_id),
            "operator_annotations": original_clicks(corrections) == original_clicks(repository.list_tip_corrections(run.analysis_id)),
            "lifecycle": all(getattr(run, name) == getattr(after, name) for name in ("status", "stage", "progress", "current_frame", "total_frames"))}
        report = {**summary, **result, "unchanged": unchanged, "backup": str(backup)}
        (backup / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        if not all(unchanged.values()):
            raise RuntimeError("Concurrent changes detected; inspect the measurement backfill report.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
