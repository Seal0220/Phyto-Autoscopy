from __future__ import annotations

import argparse
import json
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from app.analysis.export.json_export import write_json_atomic
from app.analysis.reconstruction.backend import (
    unsupported_reconstruction_outputs,
)
from app.analysis.reconstruction.backend_registry import (
    ReconstructionBackendRegistry,
)


class WorkerCancelled(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_job(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Round 重建工作格式無效。")
    return payload


def _public_error(error: BaseException) -> str:
    message = str(error).strip()
    if isinstance(error, MemoryError) or "out of memory" in message.lower():
        return "CUDA 記憶體不足，請降低模型品質後重試該 Round。"
    return message or type(error).__name__


def _result_value(result: object, name: str, default: object = None) -> object:
    value = getattr(result, name, default)
    return value() if callable(value) else value


def execute_job(
    job_path: Path,
    output_dir: Path,
    result_path: Path,
    progress_path: Path,
    cancel_path: Path,
) -> int:
    job = _read_job(job_path)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    backend_name = str(job.get("backend") or "").strip()
    parameters = job.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError("Round 重建工作缺少模型設定。")
    backend = ReconstructionBackendRegistry().get(backend_name)
    readiness = backend.check_availability()
    if not readiness.get("available"):
        raise RuntimeError("；".join(readiness.get("errors") or ["模型後端不可用。"]))
    capabilities = readiness.get("capabilities")
    if not isinstance(capabilities, Mapping):
        capabilities = {}
    requested_capabilities = {
        "scene_gaussian_export": bool(
            parameters.get("export_gaussians", True)
        ),
        "plant_gaussian_export": bool(
            parameters.get("export_plant_gaussians", False)
        ),
        "background_gaussian_export": bool(
            parameters.get("export_background_gaussians", False)
        ),
        "scene_point_cloud_export": bool(
            parameters.get("export_point_cloud", True)
        ),
        "render_preview_export": bool(
            parameters.get("export_render_preview", True)
        ),
    }
    unsupported = unsupported_reconstruction_outputs(
        capabilities,
        requested_capabilities,
    )
    if unsupported:
        raise RuntimeError(
            "所選模型後端不支援要求的輸出："
            + "、".join(unsupported)
        )

    def check_cancel() -> None:
        if cancel_path.exists():
            backend.cancel()
            raise WorkerCancelled("三維模型工作已由使用者取消。")

    def progress(
        stage: str,
        value: float,
        message: str | None,
    ) -> None:
        check_cancel()
        write_json_atomic(
            progress_path,
            {
                "stage": stage,
                "progress": min(max(float(value), 0.0), 1.0),
                "message": message,
                "updated_at": _utc_now(),
            },
        )

    try:
        progress("selecting_reconstruction_views", 0.0, "正在建立本輪唯讀模型資料集。")
        dataset = backend.prepare_dataset(job, output_dir)
        check_cancel()
        progress("extracting_features", 0.01, "正在建立本輪稀疏幾何。")
        training_result = backend.train(
            dataset,
            parameters,
            output_dir / "model",
            progress_callback=progress,
            cancel_check=check_cancel,
        )
        check_cancel()

        outputs: dict[str, Any] = {
            "gaussian_model_path": None,
            "plant_gaussian_model_path": None,
            "background_gaussian_model_path": None,
            "point_cloud_path": None,
            "preview_paths": [],
        }
        if bool(parameters.get("export_gaussians", True)):
            progress("exporting", 0.93, "正在輸出 Gaussian 模型。")
            outputs["gaussian_model_path"] = str(
                backend.export_gaussians(
                    training_result,
                    output_dir / "model" / "gaussians.ply",
                )
            )
        if bool(parameters.get("export_plant_gaussians", False)):
            exporter = getattr(
                backend,
                "export_plant_gaussians",
                None,
            )
            if not callable(exporter):
                raise RuntimeError(
                    "所選模型後端不支援輸出純植物 Gaussian 模型。"
                )
            progress("isolating_plant_model", 0.95, "正在輸出純植物 Gaussian 模型。")
            outputs["plant_gaussian_model_path"] = str(
                exporter(
                    training_result,
                    output_dir / "model" / "plant_gaussians.ply",
                )
            )
        if bool(parameters.get("export_background_gaussians", False)):
            exporter = getattr(
                backend,
                "export_background_gaussians",
                None,
            )
            if not callable(exporter):
                raise RuntimeError(
                    "所選模型後端不支援輸出背景 Gaussian 模型。"
                )
            progress("isolating_plant_model", 0.955, "正在輸出背景 Gaussian 模型。")
            outputs["background_gaussian_model_path"] = str(
                exporter(
                    training_result,
                    output_dir / "model" / "background_gaussians.ply",
                )
            )
        if bool(parameters.get("export_point_cloud", True)):
            progress("extracting_model_point_cloud", 0.96, "正在輸出場景點雲。")
            outputs["point_cloud_path"] = str(
                backend.export_point_cloud(
                    training_result,
                    output_dir / "model" / "scene_point_cloud.ply",
                )
            )
        if bool(parameters.get("export_render_preview", True)):
            progress("exporting", 0.98, "正在輸出模型預覽。")
            outputs["preview_paths"] = [
                str(path)
                for path in backend.render_views(
                    training_result,
                    [],
                    output_dir / "renders",
                )
            ]

        training = getattr(training_result, "training", training_result)
        metrics = dict(_result_value(training, "metrics", {}) or {})
        sparse = dict(_result_value(training_result, "sparse", {}) or {})
        plant_export_quality = dict(
            _result_value(
                training_result,
                "plant_export_quality",
                {},
            )
            or {}
        )
        checkpoint_path = _result_value(training, "checkpoint_path")
        payload = {
            "status": "completed",
            "analysis_id": job.get("analysis_id"),
            "round_key": job.get("round_key"),
            "backend": backend.name,
            "backend_version": backend.version,
            "repository_url": backend.repository_url,
            "repository_commit": backend.repository_commit,
            "license": backend.license,
            "environment": dict(readiness.get("environment") or {}),
            "source_view_ids": [
                str(item.get("view_id"))
                for item in job.get("selected_views", [])
                if isinstance(item, Mapping)
            ],
            "training_iterations": int(
                _result_value(training, "completed_steps", 0) or 0
            ),
            "training_duration_seconds": float(
                _result_value(training, "duration_seconds", 0.0) or 0.0
            ),
            "gaussian_count": metrics.get("gaussian_count"),
            "point_count": metrics.get("initial_sparse_point_count")
            or sparse.get("quality", {}).get("point_count"),
            "model_quality": {
                **metrics,
                "sparse_initialization": sparse.get("quality", {}),
                "plant_gaussian_export": plant_export_quality,
                "backend_readiness": readiness,
            },
            "refined_camera_poses": list(
                sparse.get("refined_camera_poses") or []
            ),
            "checkpoint_path": (
                str(checkpoint_path)
                if checkpoint_path is not None
                and Path(checkpoint_path).is_file()
                else None
            ),
            **outputs,
            "completed_at": _utc_now(),
        }
        progress("exporting", 1.0, "本輪三維模型已完成。")
        write_json_atomic(
            output_dir / "model" / "model_metadata.json",
            payload,
        )
        write_json_atomic(result_path, payload)
        return 0
    except WorkerCancelled as error:
        write_json_atomic(
            result_path,
            {
                "status": "cancelled",
                "analysis_id": job.get("analysis_id"),
                "round_key": job.get("round_key"),
                "error": str(error),
                "completed_at": _utc_now(),
            },
        )
        return 2
    except BaseException as error:
        (output_dir / "worker_error.log").write_text(
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
            encoding="utf-8",
        )
        write_json_atomic(
            result_path,
            {
                "status": "failed",
                "analysis_id": job.get("analysis_id"),
                "round_key": job.get("round_key"),
                "error": _public_error(error),
                "error_type": type(error).__name__,
                "completed_at": _utc_now(),
            },
        )
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--cancel", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        return execute_job(
            arguments.job,
            arguments.output,
            arguments.result,
            arguments.progress,
            arguments.cancel,
        )
    except BaseException as error:
        arguments.output.mkdir(parents=True, exist_ok=True)
        (arguments.output / "worker_error.log").write_text(
            "".join(
                traceback.format_exception(
                    type(error),
                    error,
                    error.__traceback__,
                )
            ),
            encoding="utf-8",
        )
        write_json_atomic(
            arguments.result,
            {
                "status": "failed",
                "error": _public_error(error),
                "error_type": type(error).__name__,
                "completed_at": _utc_now(),
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
