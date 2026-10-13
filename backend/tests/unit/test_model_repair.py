from copy import deepcopy
import json
from pathlib import Path
from threading import Event, RLock
from types import SimpleNamespace

import numpy as np
import pytest

from app.analysis.pose_alignment.model_review import model_preview_reference, prepare_reference_point_preview
from app.analysis.reconstruction import model_repair
from app.analysis.reconstruction.gsplat_trainer import PLANT_TRAINING_VERSION
from app.analysis.rounds.paths import round_artifact_directory
from app.models.analysis_models import RoundModelResult
from app.services import analysis_service


KEY = 'record:mode-1:round.47'


def _context(root, name, offset):
    result = prepare_reference_point_preview({'points': [
        {'id': i, 'xyz': [offset + i * .1, i % 2 * .2, i * .03], 'rgb': [20, 180, 30]}
        for i in range(12)
    ]}, root / name)
    sparse = root / name / 'sparse'
    sparse.mkdir()
    (sparse / 'images.bin').write_bytes(b'isolated geometry')
    pose = np.eye(4)
    pose[1, 3], pose[2, 3] = 3, -1
    result.update(training_iterations=500, gaussian_count=12, point_count=12, backend='gsplat_3dgs', backend_version='test')
    result['model_quality'].update(training_version=PLANT_TRAINING_VERSION, immutable_reference=True)
    return {'model': result, 'reference': {'signature': name, 'sparse_path': str(sparse),
        'views': [{'view_id': 'arm', 'camera_id': 'rotating', 'pose': pose.tolist()}],
        'orbit': {'rotation_rmse_deg': .3, 'position_rmse_over_radius': .008, 'direction': [0, 1, 2]},
        'quality': {'initial_geometry_validation': {'status': 'passed', 'rotation_rmse_deg': .3}}},
        'measurement_reference': {'signature': 'original metric registration'}}


@pytest.fixture
def repaired(tmp_path):
    original = _context(tmp_path, 'original', 0)
    candidate = _context(tmp_path, 'candidate', .15)
    path = round_artifact_directory(tmp_path, KEY) / 'pose_debug/model_reference/context.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(original), encoding='utf-8')
    originals = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (tmp_path / 'original').rglob('*') if p.is_file()}
    originals[path] = path.read_bytes(), path.stat().st_mtime_ns
    model_repair.activate_repair(tmp_path, KEY, original, candidate)
    return original, candidate, originals


def test_repair_is_a_validated_side_copy_that_preserves_originals(tmp_path, repaired):
    original, candidate, files = repaired
    context = model_repair.reference_context(tmp_path, KEY)
    assert context['reference']['signature'] == candidate['reference']['signature']
    assert 'measurement_reference' not in context
    assert context['repair']['original_annotations_preserved']
    assert model_repair.reference_context(tmp_path, KEY, original=True) == original
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == files
    assert Path(context['model']['gaussian_model_path']).read_bytes() == Path(candidate['model']['gaussian_model_path']).read_bytes()


def test_changed_original_cannot_inherit_a_stale_repair(tmp_path, repaired):
    original, _, _ = repaired
    path = Path(original['model']['gaussian_model_path'])
    path.write_bytes(path.read_bytes() + b'changed original')
    assert model_repair.read_model_repair(tmp_path, KEY, path) is None
    assert model_repair.reference_context(tmp_path, KEY) == original


def test_corrupt_candidate_cannot_be_displayed_as_repaired(tmp_path, repaired):
    original, _, _ = repaired
    context = model_repair.reference_context(tmp_path, KEY)
    path = Path(context['model']['gaussian_model_path'])
    path.write_bytes(path.read_bytes() + b'corrupt candidate')
    with pytest.raises(ValueError, match='不完整'):
        model_repair.read_model_repair(tmp_path, KEY, Path(original['model']['gaussian_model_path']))


@pytest.mark.parametrize('problem', ['geometry', 'unfinished', 'nan', 'needles'])
def test_failed_candidates_cannot_replace_originals(tmp_path, problem):
    original = _context(tmp_path, 'original', 0)
    candidate = _context(tmp_path, 'candidate', .15)
    if problem == 'geometry':
        candidate['reference']['quality']['initial_geometry_validation']['status'] = 'unstable'
    elif problem == 'unfinished':
        candidate['model']['training_iterations'] = 499
    else:
        path = Path(candidate['model']['gaussian_model_path'])
        header, vertices = path.read_bytes().split(b'end_header\n', 1)
        data = np.frombuffer(vertices, dtype='<f4').copy()
        if problem == 'nan':
            data[3] = np.nan
        else:
            rows = data.reshape(12, -1)
            properties = [line.split()[-1].decode() for line in header.splitlines() if line.startswith(b'property')]
            rows[:, properties.index('scale_0')] = np.log(100.)
        path.write_bytes(header + b'end_header\n' + data.tobytes())
    before = Path(original['model']['gaussian_model_path']).read_bytes()
    with pytest.raises(ValueError):
        model_repair.activate_repair(tmp_path, KEY, original, candidate)
    assert Path(original['model']['gaussian_model_path']).read_bytes() == before
    assert not (model_repair.repair_directory(tmp_path, KEY) / 'active.json').exists()


def _service(root, original):
    pose = original['reference']['views'][0]['pose']
    run = SimpleNamespace(analysis_id='analysis-test', intrinsics_snapshot={'rotating': {'undistorted_camera_matrix': np.eye(3).tolist()}})
    model = RoundModelResult(analysis_id=run.analysis_id, round_key=KEY, model_id='model', backend='gsplat_3dgs',
        backend_version='test', status='completed', model_path=Path(original['model']['gaussian_model_path']).relative_to(root).as_posix(),
        model_quality={'immutable_reference': True, 'initial_camera_pose': pose})
    service = analysis_service.AnalysisService.__new__(analysis_service.AnalysisService)
    service._require_image_context = lambda _: run
    service._artifacts = lambda _: SimpleNamespace(root=root)
    service.get_artifact_path = lambda _, path: root / path
    service._saved_step = lambda *args: {'quality': {'model_to_world': np.eye(4).tolist()}}
    service._stereo_pose_signature = lambda _: 'old-registration'
    service._preview_lock = RLock()
    service.repository = SimpleNamespace(list_round_models=lambda _: [model], list_camera_poses=lambda *args: [])
    return service, run


def test_preview_uses_repair_without_inheriting_old_metric_coordinates(tmp_path, repaired):
    original, _, files = repaired
    service, _ = _service(tmp_path, original)
    service._model_tip_annotation = lambda *args, **kwargs: None
    reference = service.get_round_model_preview('analysis-test', KEY)
    assert reference['model_repaired'] is True
    assert reference['model_to_world'] is None
    assert reference['geometry_warning'] is None
    np.testing.assert_allclose(reference['initial_camera']['orbit_up'], -np.array([0, 1, 2]) / np.sqrt(5))
    repaired_context = model_repair.reference_context(tmp_path, KEY)
    expected = model_preview_reference(Path(repaired_context['model']['gaussian_model_path']), tmp_path,
        np.asarray(repaired_context['reference']['views'][0]['pose']))
    assert reference['signature'] == expected['signature']
    assert 'model_repairs/' in reference['gaussian_path']
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == files


def test_model_list_downloads_the_repair_without_changing_database_payload(tmp_path, repaired):
    original, candidate, _ = repaired
    service, _ = _service(tmp_path, original)
    stored = service.repository.list_round_models('analysis-test')[0]
    before = stored.model_dump()
    visible = service.list_round_models('analysis-test')[0]
    assert 'model_repairs/' in visible.model_path
    assert (tmp_path / visible.model_path).is_file()
    assert visible.gaussian_count == candidate['model']['gaussian_count']
    assert visible.model_quality['model_repaired']
    assert stored.model_dump() == before


def test_manual_model_tip_is_retracked_into_repair_instead_of_copying_xyz(tmp_path, repaired, monkeypatch):
    original, candidate, _ = repaired
    service, run = _service(tmp_path, original)
    old_preview = model_preview_reference(Path(original['model']['gaussian_model_path']), tmp_path,
        np.asarray(original['reference']['views'][0]['pose']))
    correction = SimpleNamespace(round_key=KEY, invalid=False, correction_id='manual-1',
        model_signature=old_preview['signature'], model_point_relative_xyz=[.2, .1, .1])
    before = deepcopy(correction.__dict__)
    service.repository.list_rounds = lambda _: [SimpleNamespace(round_key=KEY, mode_id='mode-1', started_at='2026-01-01', round_id='round.47')]
    service.repository.list_tip_corrections = lambda _: [correction]
    service.repository.list_tip_landmarks = lambda _: []
    service.repository.list_views = lambda *args: []
    checked = []
    def tracker(source, target, point, *args, **kwargs):
        checked.append((source['signature'], target['signature'], point))
        return {'status': 'tracked', 'relative_xyz': [.35, .1, .1]}
    monkeypatch.setattr(analysis_service, 'track_model_tip', tracker)
    preview = service.get_round_model_preview(run.analysis_id, KEY)
    assert checked == [(original['reference']['signature'], candidate['reference']['signature'], [.2, .1, .1])]
    assert preview['model_tip']['relative_xyz'] == [.35, .1, .1]
    assert preview['model_tip']['model_signature'] == preview['signature']
    assert correction.__dict__ == before


def test_pause_keeps_repair_pending_and_never_activates_partial_model(tmp_path, repaired, monkeypatch):
    original, _, files = repaired
    service, run = _service(tmp_path, original)
    request = model_repair.repair_directory(tmp_path, KEY) / 'request.json'
    # Exercise a queued repair with no accepted candidate.
    monkeypatch.setattr(analysis_service, 'read_model_repair', lambda *args: None)
    request.write_text(json.dumps({'status': 'pending', 'source_gaussian_sha256': model_repair.model_digest(Path(original['model']['gaussian_model_path']))}), encoding='utf-8')
    before = request.read_bytes()
    def paused(*args, **kwargs):
        raise analysis_service.AnalysisPausedError('pause repair')
    monkeypatch.setattr(analysis_service, 'rebuild_reference_model', paused)
    with pytest.raises(analysis_service.AnalysisPausedError):
        service._repair_requested_round_model(run, KEY, Event())
    assert request.read_bytes() == before
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == files
