"""Localize an unregistered top camera against an unchanged Gaussian map.

The motor orbit constrains the search hemisphere, never supplies an accepted
pose. Rendered RGB/depth bridges the large viewing-angle difference. PnP is
fitted on one real image and checked on two other captures before sharing the
physical camera pose. This verifies image consistency, not absolute accuracy.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np

from app.analysis.checkpoints import StepJournal, step_signature
from app.analysis.export.json_export import write_json_atomic
from app.analysis.pose_alignment.model_reference import aggregate_fixed_camera_poses, model_camera_pose
from app.analysis.pose_alignment.model_review import _gaussian_model
from app.analysis.reconstruction.dataset_adapter import _sha256
from app.analysis.rounds.paths import safe_artifact_name


RENDER_REGISTRATION_VERSION = 2


def validate_render_pose(pose, observations, matrix, axis, *, minimum_inliers=24, threshold_px=3.7):
    """Check the same fixed pose in every capture, without refitting holdouts."""
    pose = np.asarray(pose, dtype=float)
    if (pose.shape != (4, 4) or not np.isfinite(pose).all()
            or not np.allclose(pose[3], [0, 0, 0, 1])
            or not np.allclose(pose[:3, :3] @ pose[:3, :3].T, np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(pose[:3, :3]), 1., atol=1e-6)):
        raise ValueError("俯視備援姿態無效。")
    axis = np.asarray(axis, dtype=float)
    inclination = float(np.rad2deg(np.arccos(np.clip(pose[2, :3] @ axis, -1., 1.))))
    if inclination > 25:
        raise ValueError("俯視備援姿態與旋臂軸線不一致。")
    if len(observations) < 3 or len({item["view_id"] for item in observations}) != len(observations):
        raise ValueError("俯視備援至少需要三張不同擷取的影像驗證。")
    results = []
    for observation in observations:
        xyz, pixels = np.asarray(observation["xyz"]), np.asarray(observation["pixels"])
        if (xyz.ndim != 2 or xyz.shape[1] != 3 or pixels.shape != (len(xyz), 2)
                or len(xyz) < minimum_inliers or not np.isfinite(xyz).all() or not np.isfinite(pixels).all()):
            raise ValueError("俯視備援的影像對應點無效或不足。")
        projected = cv2.projectPoints(xyz, cv2.Rodrigues(pose[:3, :3])[0], pose[:3, 3], matrix, None)[0].reshape(-1, 2)
        errors = np.linalg.norm(projected - pixels, axis=1)
        depth = (xyz @ pose[:3, :3].T + pose[:3, 3])[:, 2]
        keep = np.flatnonzero(np.isfinite(errors) & (errors <= threshold_px) & (depth > 0))
        if len(keep) < minimum_inliers or len(keep) < len(xyz) * .5:
            raise ValueError("俯視備援在其他擷取影像的有效對應點不足。")
        # A tiny cluster can fit a wrong camera despite a low pixel residual.
        spread = np.linalg.eigvalsh(np.cov(pixels[keep].T))
        if spread[0] < 9. or np.ptp(pixels[keep], axis=0).min() < 20.:
            raise ValueError("俯視備援的對應點分布不足，無法確定姿態。")
        results.append({"view_id": observation["view_id"], "inlier_count": len(keep),
                        "match_count": len(xyz), "rmse_px": float(np.sqrt(np.mean(errors[keep] ** 2))),
                        "inlier_indices": keep.tolist()})
    return {"captures": results, "top_axis_inclination_deg": inclination,
            "validation": "shared_pose_on_independent_captures", "threshold_px": threshold_px,
            "absolute_accuracy_verified": False}


def select_render_pose(candidates):
    """Require a unique branch; visually similar opposite views are common."""
    if not candidates:
        raise ValueError("俯視渲染定位未通過跨影像驗證。")
    candidates.sort(key=lambda item: sum(c["inlier_count"] for c in item["quality"]["captures"]), reverse=True)
    best = candidates[0]
    for candidate in candidates[1:]:
        delta = np.asarray(candidate["pose"])[:3, :3] @ np.asarray(best["pose"])[:3, :3].T
        angle = np.rad2deg(np.arccos(np.clip((np.trace(delta) - 1.) / 2., -1., 1.)))
        if angle < 10:
            continue
        best_support = sum(c["inlier_count"] for c in best["quality"]["captures"])
        other_support = sum(c["inlier_count"] for c in candidate["quality"]["captures"])
        if best_support < other_support * 1.25:
            raise ValueError("俯視渲染定位有方向歧義，請補人工對齊。")
    return best


def _target_image_and_mask(view):
    # Only three already-decoded captures are needed. Reuse SfM's exact masks
    # and CPU decoding, avoiding a second native GPU decoder lifetime here.
    image = cv2.imdecode(np.fromfile(view["undistorted_path"], dtype=np.uint8), cv2.IMREAD_COLOR)
    mask = cv2.imdecode(np.fromfile(view["feature_mask_path"], dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None or mask is None or image.shape[:2] != mask.shape:
        raise ValueError("俯視定位影像或前景遮罩無法讀取。")
    return image, mask > 0


def _crop_target(view, matrix):
    image, mask = _target_image_and_mask(view)
    y, x = np.where(mask)
    if len(x) < 100:
        raise ValueError("俯視定位找不到完整的植物與盆栽區域。")
    x0, y0 = max(0, int(x.min()) - 24), max(0, int(y.min()) - 24)
    x1, y1 = min(image.shape[1], int(x.max()) + 25), min(image.shape[0], int(y.max()) + 25)
    cropped_matrix = matrix.copy()
    cropped_matrix[:2, 2] -= [x0, y0]
    return image[y0:y1, x0:x1], mask[y0:y1, x0:x1], cropped_matrix, (x0, y0, x1, y1)


class _GaussianRenderer:
    def __init__(self, path, matrix, width, height):
        import torch
        from gsplat.rendering import rasterization
        if not torch.cuda.is_available():
            raise ValueError("俯視渲染定位需要可用的 CUDA；可先跳過並補人工對齊。")
        self.torch, self.rasterize = torch, rasterization
        self.width, self.height = width, height
        stat = path.stat()
        vertices = _gaussian_model(str(path), stat.st_size, stat.st_mtime_ns, True)[0]
        self.means = self.tensor(np.stack([vertices[key] for key in ("x", "y", "z")], axis=1))
        self.quats = self.tensor(np.stack([vertices[f"rot_{i}"] for i in range(4)], axis=1))
        self.scales = self.tensor(np.exp(np.stack([vertices[f"scale_{i}"] for i in range(3)], axis=1)))
        self.opacities = self.tensor(1 / (1 + np.exp(-np.clip(vertices["opacity"], -80, 80))))
        self.colors = self.tensor(np.clip(np.stack([vertices[f"f_dc_{i}"] for i in range(3)], axis=1) * .28209479177387814 + .5, 0, 1))
        leaf = ((self.colors[:, 1] - self.colors[:, 0] + .035) / .09).clamp(0, 1)
        leaf *= (self.colors.max(dim=1).values / .5).clamp(0, 1)
        self.semantic_colors = torch.cat([self.colors, leaf[:, None]], dim=1)
        self.matrix = self.tensor(matrix[None])

    def tensor(self, value):
        return self.torch.as_tensor(np.asarray(value).copy(), dtype=self.torch.float32, device="cuda")

    def render(self, pose, *, semantic=False, depth=False):
        return self.rasterize(self.means, self.quats, self.scales, self.opacities,
            self.semantic_colors if semantic else self.colors, pose[None], self.matrix, self.width, self.height,
            render_mode="RGB+ED" if depth else "RGB", near_plane=.01, far_plane=1e6, packed=False)[:2]


def _search_and_refine(renderer, reference, target, mask, matrix, *, cancel_check, progress):
    torch = renderer.torch
    axis = np.asarray(reference["orbit"]["direction"], dtype=float)
    base = np.asarray(reference["orbit"]["base_camera_to_world"])
    # Image down establishes the physical lower hemisphere independently of
    # motor sign and arbitrary SfM world orientation.
    if axis @ base[:3, 1] < 0:
        axis = -axis
    basis = base[:3, 0].copy()
    basis -= basis @ axis * axis
    basis /= np.linalg.norm(basis)
    rotation0 = np.stack([basis, np.cross(axis, basis), axis])
    center = np.median(renderer.means.cpu().numpy(), axis=0)
    y, x = np.where(mask)
    pixel_center = np.array([x.mean(), y.mean()])
    rgb_target = renderer.tensor(cv2.cvtColor(target, cv2.COLOR_BGR2RGB) / 255.)
    mask_target = renderer.tensor(mask)
    choices = []
    with torch.no_grad():
        for factor in (.8, 1.07, 1.34, 1.61, 1.87, 2.14, 2.68):
            cancel_check()
            depth = float(reference["orbit"]["radius"]) * factor
            for angle in range(0, 360, 10):
                a = math.radians(angle)
                roll = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
                rotation = roll @ rotation0
                translation = -rotation @ center
                translation[2] += depth
                translation[:2] += (pixel_center - matrix[:2, 2]) * depth / matrix[[0, 1], [0, 1]]
                pose = np.eye(4)
                pose[:3, :3], pose[:3, 3] = rotation, translation
                rgb, alpha = renderer.render(renderer.tensor(pose))
                visible = alpha[0, :, :, 0] > .3
                iou = (visible * mask_target).sum() / (visible | mask_target.bool()).sum().clamp(min=1)
                score = float(1 - iou + torch.abs(rgb[0] - rgb_target).mean())
                choices.append((score, angle, pose))
    choices.sort(key=lambda row: row[0])
    starts = [choices[0], next(row for row in choices if abs((row[1] - choices[0][1] + 180) % 360 - 180) > 90)]
    leaf_target = renderer.tensor((target[:, :, 1].astype(float) > target[:, :, 0] * 1.1)
                                 & (target[:, :, 1].astype(float) > target[:, :, 2] * 1.04) & mask)

    def blur(value, size):
        return torch.nn.functional.avg_pool2d(value[None, None], size, stride=1, padding=size // 2)[0, 0] if size > 1 else value

    results = []
    for index, (_, _, initial) in enumerate(starts):
        delta = torch.zeros(6, device="cuda", requires_grad=True)
        base_pose = renderer.tensor(initial)
        optimizer = torch.optim.Adam([delta], lr=.0015)
        for step in range(501):
            if step % 25 == 0:
                cancel_check()
                progress("aligning_model_cameras", .15 + .35 * (index + step / 501) / len(starts), "俯視：渲染與實拍姿態精修")
            w, z = delta[:3], delta[0] * 0
            skew = torch.stack([torch.stack([z, -w[2], w[1]]), torch.stack([w[2], z, -w[0]]), torch.stack([-w[1], w[0], z])])
            rotation = torch.matrix_exp(skew)
            pose = torch.cat([torch.cat([rotation @ base_pose[:3, :3], (base_pose[:3, 3] + delta[3:])[:, None]], dim=1), base_pose[3:]], dim=0)
            rgb, alpha = renderer.render(pose, semantic=True)
            size = 11 if step < 160 else 5 if step < 320 else 1
            inclination = torch.acos((pose[2, :3] @ renderer.tensor(axis)).clamp(-1 + 1e-7, 1 - 1e-7))
            loss = (torch.abs(blur(alpha[0, :, :, 0], size) - blur(mask_target, size)).mean()
                    + torch.abs(blur(rgb[0, :, :, 3], size) - blur(leaf_target, size)).mean()
                    + torch.relu(inclination - math.radians(20)) ** 2)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        with torch.no_grad():
            rgb, alpha = renderer.render(pose, depth=True)
            results.append({"pose": pose.detach().cpu().numpy(), "rgb_depth": rgb[0].cpu().numpy(),
                            "alpha": alpha[0, :, :, 0].cpu().numpy()})
    return results, axis


def _match_renders(root, renders, views, crop, matrix, *, cancel_check):
    images, masks = root / "images", root / "masks"
    images.mkdir(parents=True, exist_ok=True)
    masks.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = crop
    factor = min(4., 1024. / max(x1 - x0, y1 - y0))
    size = (round((x1 - x0) * factor), round((y1 - y0) * factor))
    scale = np.array(size) / [x1 - x0, y1 - y0]
    names = []
    for index, render in enumerate(renders):
        name = f"render_{index}.png"
        names.append(name)
        rgb = np.clip(render["rgb_depth"][:, :, :3] * 255, 0, 255).astype(np.uint8)
        cv2.imwrite(str(images / name), cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), size))
        cv2.imwrite(str(masks / (name + ".png")), cv2.resize((render["alpha"] > .5).astype(np.uint8) * 255, size, interpolation=cv2.INTER_NEAREST))
    for index, view in enumerate(views):
        cancel_check()
        name = f"capture_{index}.png"
        names.append(name)
        # Fixed cameras share intrinsics, but masks may move slightly between
        # captures. Always use the first capture's exact crop coordinates.
        raw, full_mask = _target_image_and_mask(view)
        cv2.imwrite(str(images / name), cv2.resize(raw[y0:y1, x0:x1], size))
        cv2.imwrite(str(masks / (name + ".png")), cv2.resize(full_mask[y0:y1, x0:x1].astype(np.uint8) * 255, size, interpolation=cv2.INTER_NEAREST))
    k = matrix.copy()
    k[:2, 2] -= [x0, y0]
    k[:2, 2] += .5
    k[:2] *= scale[:, None]
    job_path = root / "features.json"
    write_json_atomic(job_path, {"root": str(root.resolve()), "names": names, "size": size,
                                "matrix": k.tolist(), "render_count": len(renders)})
    _run_feature_worker(root, job_path, cancel_check=cancel_check)
    observations = []
    with np.load(root / "matches.npz", allow_pickle=False) as arrays:
        keys = {i: arrays[f"keypoints_{i}"] for i in range(1, len(names) + 1)}
        for index, render in enumerate(renders):
            captures = []
            for capture_index, view in enumerate(views):
                pairs = arrays[f"matches_{index + 1}_{len(renders) + capture_index + 1}"]
                if len(pairs) < 4:
                    captures = []
                    break
                pixels = keys[index + 1][pairs[:, 0]] / scale - .5
                coordinates = np.rint(pixels).astype(int)
                depth = render["rgb_depth"][np.clip(coordinates[:, 1], 0, y1 - y0 - 1), np.clip(coordinates[:, 0], 0, x1 - x0 - 1), 3]
                alpha = render["alpha"][np.clip(coordinates[:, 1], 0, y1 - y0 - 1), np.clip(coordinates[:, 0], 0, x1 - x0 - 1)]
                objects = (np.c_[pixels + [x0, y0], np.ones(len(pixels))] @ np.linalg.inv(matrix).T) * depth[:, None]
                objects = (objects - render["pose"][:3, 3]) @ render["pose"][:3, :3]
                target = keys[len(renders) + capture_index + 1][pairs[:, 1]] / scale - .5 + [x0, y0]
                keep = np.isfinite(depth) & (depth > 0) & (alpha > .5)
                captures.append({"view_id": view["view_id"], "xyz": objects[keep], "pixels": target[keep]})
            observations.append(captures)
    return observations


def _run_feature_worker(root, job_path, *, cancel_check):
    environment = os.environ.copy()
    backend_root = Path(__file__).resolve().parents[3]
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(backend_root), environment.get("PYTHONPATH")]))
    with (root / "features.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-m", "app.analysis.reconstruction.reference_feature_worker",
            "--job", str(job_path.resolve())], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        try:
            while process.poll() is None:
                cancel_check()
                time.sleep(.1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
    cancel_check()
    if process.returncode != 0 or not (root / "matches.npz").is_file():
        raise ValueError("俯視特徵配對工作失敗，請查看定位診斷或補人工對齊。")


def localize_reference_top(job, root, *, progress, cancel_check):
    reference, model = job["reference"], job["model"]
    path = Path(model["gaussian_model_path"])
    fixed, _ = aggregate_fixed_camera_poses(reference["views"], orbit_radius=reference["orbit"]["radius"])
    views = sorted((v for v in job["selected_views"] if v["camera_id"] == "top"), key=lambda v: v["view_id"])
    # Distinct snapshots are essential: three copies of one frame do not validate
    # a physical fixed pose. Select across this round's capture interval.
    unique = {str(v.get("snapshot_id") or v["view_id"]): v for v in views}
    views = list(unique.values())
    if "side" not in fixed or len(views) < 3:
        raise ValueError("渲染定位需要已驗證的側視鏡頭及三次俯視擷取。")
    views = [views[0], views[len(views) // 2], views[-1]]
    mask_root = Path(reference["sparse_path"]).parents[1] / "feature_masks"
    views = [{**view, "feature_mask_path": str(mask_root / (
        f"top__{safe_artifact_name(view['view_id'])}{Path(view['undistorted_path']).suffix.lower()}.png"))} for view in views]
    signature = step_signature({"version": RENDER_REGISTRATION_VERSION, "reference": reference["signature"],
        "fixed_poses": fixed, "model": _sha256(path), "views": views,
        "intrinsics": job["intrinsics_snapshot"], "settings": job["parameters"]})
    root = root / signature
    root.mkdir(parents=True, exist_ok=True)
    with StepJournal(root) as journal:
        saved = journal.get("render_registration", "top", signature)
        if saved is not None:
            return saved
    cancel_check()
    matrix = np.asarray(job["intrinsics_snapshot"]["top"]["undistorted_camera_matrix"], dtype=float)
    target, mask, cropped_matrix, crop = _crop_target(views[0], matrix)
    progress("aligning_model_cameras", .05, "俯視：搜尋影像支持的相機方向")
    with StepJournal(root) as journal:
        rendered = journal.get("render_registration", "renders", signature)
    if rendered is None:
        renderer = _GaussianRenderer(path, cropped_matrix, target.shape[1], target.shape[0])
        renders, axis = _search_and_refine(renderer, reference, target, mask, cropped_matrix, cancel_check=cancel_check, progress=progress)
        # Resume against the exact same rendered depth/keypoints. Re-rendering
        # while reusing old native feature records would mix two geometries.
        render_path = root / "renders.npz"
        arrays = {f"{key}_{i}": value for i, render in enumerate(renders) for key, value in render.items()}
        with (root / "renders.tmp").open("wb") as handle:
            np.savez_compressed(handle, axis=axis, **arrays)
        (root / "renders.tmp").replace(render_path)
        with StepJournal(root) as journal:
            journal.save("render_registration", "renders", signature, {"path": str(render_path), "count": len(renders)}, outputs=[render_path])
    else:
        with np.load(rendered["path"], allow_pickle=False) as arrays:
            renders = [{key: arrays[f"{key}_{i}"] for key in ("pose", "rgb_depth", "alpha")} for i in range(rendered["count"])]
            axis = arrays["axis"]
    observations = _match_renders(root, renders, views, crop, matrix, cancel_check=cancel_check)
    candidates, failures = [], []
    threshold = min(3.7, float(job["parameters"].get("maximum_pnp_reprojection_error_px", 5)))
    minimum = max(24, int(job["parameters"].get("minimum_stereo_inliers", 24)))
    for index, captures in enumerate(observations):
        cancel_check()
        try:
            if not captures or len(captures[0]["xyz"]) < minimum:
                raise ValueError("渲染與俯視影像的有效配對不足。")
            pose, _ = model_camera_pose(captures[0]["xyz"], captures[0]["pixels"], matrix, threshold)
            quality = validate_render_pose(pose, captures, matrix, axis, minimum_inliers=minimum, threshold_px=threshold)
            candidates.append({"pose": pose.tolist(), "quality": quality, "render_index": index})
        except ValueError as error:
            failures.append({"render_index": index, "reason": str(error)})
    write_json_atomic(root / "diagnostics.json", {"candidates": candidates, "rejected_candidates": failures,
        "reference_signature": reference["signature"], "crop": crop, "matrix": matrix.tolist()})
    selected = select_render_pose(candidates)
    result = {"status": "completed", "poses": {**fixed, "top": selected["pose"]}, "quality": {
        **selected["quality"], "method": "render_depth_pnp_with_heldout_captures", "version": RENDER_REGISTRATION_VERSION,
        "rejected_candidates": failures, "reference_signature": reference["signature"]}}
    output = root / "registration.json"
    write_json_atomic(output, result)
    with StepJournal(root) as journal:
        journal.save("render_registration", "top", signature, result, outputs=[output])
    progress("aligning_model_cameras", 1., "俯視：跨影像姿態驗證通過")
    return result
