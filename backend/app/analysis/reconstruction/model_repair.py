"""Versioned reference-model repairs. Original geometry and annotations stay intact."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import numpy as np

from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.export.json_export import write_json_atomic
from app.analysis.pose_alignment.model_review import _gaussian_model
from app.analysis.reconstruction.dataset_adapter import _materialize_read_only_image
from app.analysis.reconstruction.gsplat_trainer import PLANT_TRAINING_VERSION
from app.analysis.reconstruction.reference_pose_refinement import REFERENCE_GEOMETRY_VERSION
from app.analysis.reconstruction.reference_sfm import reference_image_name
from app.analysis.rounds.paths import round_artifact_directory


@lru_cache(maxsize=128)
def _digest(path: str, size: int, modified: int) -> str:
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def model_digest(path: Path) -> str:
    path = path.resolve()
    stat = path.stat()
    return _digest(str(path), stat.st_size, stat.st_mtime_ns)


def repair_directory(root: Path, round_key: str) -> Path:
    return round_artifact_directory(root, round_key) / 'pose_debug/model_repairs'


def read_model_repair(root: Path, round_key: str, original_path: Path) -> dict | None:
    """Read only a complete repair belonging to this exact original model."""
    active = repair_directory(root, round_key) / 'active.json'
    if not active.is_file():
        return None
    context = json.loads(active.read_text(encoding='utf-8'))
    repair = context['repair']
    original_path.resolve().relative_to(root.resolve())
    if repair['source_gaussian_sha256'] != model_digest(original_path):
        return None  # A different original model cannot inherit this repair.
    candidate = Path(context['model']['gaussian_model_path']).resolve()
    candidate.relative_to(root.resolve())
    sparse = Path(context['reference']['sparse_path']).resolve()
    sparse.relative_to(root.resolve())
    quality = context['reference']['quality']['initial_geometry_validation']
    if (repair.get('status') != 'accepted' or quality.get('status') != 'passed'
            or not sparse.is_dir() or repair['gaussian_sha256'] != model_digest(candidate)):
        raise ValueError('修復模型資料不完整，原始模型仍保留。')
    return context


def reference_context(root: Path, round_key: str, *, original: bool = False) -> dict:
    path = round_artifact_directory(root, round_key) / 'pose_debug/model_reference/context.json'
    context = json.loads(path.read_text(encoding='utf-8'))
    if original or not (repair_directory(root, round_key) / 'active.json').is_file():
        return context
    repair = read_model_repair(root, round_key, Path(context['model']['gaussian_model_path']))
    return repair or context


def reuse_reference_features(source: Path, destination: Path, job: dict) -> None:
    """Copy verified features into a new reconstruction; never reuse its poses."""
    signature = step_signature({'version': 4, 'geometry_version': REFERENCE_GEOMETRY_VERSION,
        'refine_geometry': job.get('refine_geometry', True), 'views': job['selected_views'],
        'intrinsics': job['intrinsics_snapshot'], 'action': job.get('reference_action'),
        'settings': job['parameters'], 'mapping_camera_ids': job.get('mapping_camera_ids'),
        'source_signature': job.get('source_signature')})
    with sqlite3.connect((source / 'checkpoints/steps.sqlite3').resolve().as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute("SELECT item,signature,payload FROM steps WHERE stage='reference_sfm'").fetchall()
    records = {item: json.loads(payload) for item, saved_signature, payload in rows if saved_signature == signature}
    if not {'database', 'extracting_features', 'matching_features'} <= records.keys():
        return  # Different inputs require fresh, correctly masked features.
    destination.mkdir(parents=True, exist_ok=True)
    database = destination / 'database.db'
    if database.exists():
        return  # Preserve a candidate's own resumable mapping and journal.
    with sqlite3.connect((source / 'database.db').resolve().as_uri() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(database) as copy:
            original.backup(copy)
    images = destination / 'images'
    images.mkdir(exist_ok=True)
    for view in job['selected_views']:
        image = Path(view['undistorted_path']).resolve()
        if model_digest(image) != view['undistorted_sha256']:
            raise ValueError('修復輸入影像已變更，不能沿用既有特徵。')
        _materialize_read_only_image(image, images / reference_image_name(view))
    with StepJournal(destination) as journal:
        for stage in ('database', 'extracting_features', 'matching_features'):
            journal.save('reference_sfm', stage, signature, records[stage])


def validate_repair_candidate(original: dict, candidate: dict) -> dict:
    quality = candidate['reference']['quality']['initial_geometry_validation']
    if quality.get('status') != 'passed':
        raise ValueError('修復候選的影像幾何未通過檢查，保留原模型。')
    model = candidate['model']
    if (model['model_quality'].get('training_version') != PLANT_TRAINING_VERSION
            or model['training_iterations'] < original['model']['training_iterations']):
        raise ValueError('修復模型尚未完成原定訓練品質，保留原模型。')
    path = Path(model['gaussian_model_path']).resolve()
    stat = path.stat()
    vertices, *_ = _gaussian_model(str(path), stat.st_size, stat.st_mtime_ns, True)
    if any(not np.isfinite(vertices[name]).all() for name in vertices.dtype.names):
        raise ValueError('修復模型含無效 Gaussian，保留原模型。')
    log_scales = np.column_stack([vertices[f'scale_{i}'] for i in range(3)])
    quaternion = np.column_stack([vertices[f'rot_{i}'] for i in range(4)])
    if (not np.isfinite(np.exp(log_scales.astype(np.float64))).all()
            or np.any(np.linalg.norm(quaternion, axis=1) < 1e-8)):
        raise ValueError('修復模型的尺寸或旋轉無效，保留原模型。')
    visible = vertices['opacity'] > -np.log(3.)  # sigmoid(opacity) > .25
    ordered = np.sort(log_scales, axis=1)
    needles = ordered[:, 2] - ordered[:, 1] > np.log(10.)
    fraction = float(np.mean(needles[visible])) if visible.any() else 1.
    if fraction > .05:
        raise ValueError('修復模型仍有過多細長 Gaussian，不替換原模型。')
    return {**quality, 'gaussian_count': len(vertices), 'visible_needle_fraction': fraction}


def rebuild_reference_model(root: Path, round_key: str, *, cancel_event, progress) -> tuple[dict, dict]:
    """Run only on an explicit repair/resume; original checkpoints are untouched."""
    from app.analysis.reconstruction.reconstruction_worker import run_reconstruction_worker
    directory = round_artifact_directory(root, round_key) / 'pose_debug/model_reference'
    original = json.loads((directory / 'context.json').read_text(encoding='utf-8'))
    source_hash = model_digest(Path(original['model']['gaussian_model_path']))
    version = step_signature({'source': source_hash, 'training': PLANT_TRAINING_VERSION})[:16]
    candidate_root = repair_directory(root, round_key) / 'candidates' / version
    job = json.loads((directory / 'sfm/worker/job.json').read_text(encoding='utf-8'))
    job.update(stabilize_initial_geometry=True, mapping_camera_ids=['rotating'])
    reuse_reference_features(directory / 'sfm', candidate_root / 'sfm', job)
    reference = run_reconstruction_worker(job, candidate_root / 'sfm', cancel_event, progress_callback=progress)
    training = json.loads((directory / 'model/worker/job.json').read_text(encoding='utf-8'))
    views = [view for view in reference['views'] if view['camera_id'] == 'rotating']
    training.update(geometry_signature=reference['signature'], initial_sparse_path=reference['sparse_path'],
        selected_views=views, camera_poses=[{'view_id': view['view_id'], 'valid': True, 'pose_source': 'sfm',
            'rotation_matrix': np.asarray(view['pose'])[:3, :3].tolist(),
            'translation_vector_mm': np.asarray(view['pose'])[:3, 3].tolist()} for view in views])
    result = run_reconstruction_worker(training, candidate_root / 'model', cancel_event, progress_callback=progress)
    if model_digest(Path(original['model']['gaussian_model_path'])) != source_hash:
        raise ValueError('原模型已變更，未套用修復。')
    return original, {'reference': reference, 'model': result}


def activate_repair(root: Path, round_key: str, original: dict, candidate: dict) -> Path:
    """Publish a side copy, preserving every original file and database row."""
    quality = validate_repair_candidate(original, candidate)
    source = Path(original['model']['gaussian_model_path']).resolve()
    source.relative_to(root.resolve())
    source_hash = model_digest(source)
    candidate_hash = model_digest(Path(candidate['model']['gaussian_model_path']))
    directory = repair_directory(root, round_key)
    version = directory / step_signature({'source': source_hash, 'candidate': candidate_hash})[:16]
    version.mkdir(parents=True, exist_ok=True)
    context = deepcopy(original)
    context.update(reference=deepcopy(candidate['reference']), model=deepcopy(candidate['model']))
    # A new reference frame must never inherit the old metric registration.
    context.pop('measurement_reference', None)
    context['reference_model_policy'] = 'immutable_per_round_v1'
    outputs = ('gaussian_model_path', 'plant_gaussian_model_path', 'background_gaussian_model_path',
               'point_cloud_path', 'plant_point_cloud_path', 'background_point_cloud_path', 'checkpoint_path')
    for name in outputs:
        value = context['model'].get(name)
        if value:
            destination = version / 'model' / name / Path(value).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copy2(value, destination)
            context['model'][name] = str(destination.resolve())
    previews = []
    for index, value in enumerate(context['model'].get('preview_paths', [])):
        destination = version / 'renders' / f'{index}_{Path(value).name}'
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            shutil.copy2(value, destination)
        previews.append(str(destination.resolve()))
    context['model']['preview_paths'] = previews
    sparse = version / 'sparse/0'
    shutil.copytree(context['reference']['sparse_path'], sparse, dirs_exist_ok=True)
    context['reference']['sparse_path'] = str(sparse.resolve())
    cloud = context['reference'].get('point_cloud_path')
    if cloud:
        destination = version / 'sparse' / Path(cloud).name
        shutil.copy2(cloud, destination)
        context['reference']['point_cloud_path'] = str(destination.resolve())
    reference_path = version / 'reference.json'
    context['reference']['reference_path'] = str(reference_path.resolve())
    write_json_atomic(reference_path, context['reference'])
    context['repair'] = {'status': 'accepted', 'source_gaussian_sha256': source_hash,
        'gaussian_sha256': candidate_hash, 'quality': quality,
        'source_model_path': source.relative_to(root.resolve()).as_posix(),
        'original_annotations_preserved': True}
    write_json_atomic(version / 'context.json', context)
    if model_digest(source) != source_hash:
        raise ValueError('原模型在修復期間已變更，未套用候選模型。')
    active = directory / 'active.json'
    write_json_atomic(active, context)
    return active
