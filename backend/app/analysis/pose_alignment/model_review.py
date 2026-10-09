from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import numpy as np


def prepare_reference_point_preview(reference: dict, root: Path) -> dict:
    """Display real SfM anchors before training; the splats are point glyphs only.

    Use the existing PLY viewer/anchor validation, without running a 3DGS
    optimizer or supplying guessed poses for cameras that have not registered.
    """
    points = reference["points"]
    xyz = np.asarray([point["xyz"] for point in points], dtype=np.float32)
    if len(points) < 4 or xyz.shape != (len(points), 3) or not np.isfinite(xyz).all():
        raise ValueError("相機對齊缺少四個有效三維參照點。")
    rgb = np.asarray([point.get("rgb", [255, 255, 255]) for point in points], dtype=np.float32)
    if rgb.shape != xyz.shape or not np.isfinite(rgb).all():
        raise ValueError("三維參照點色彩無效。")
    names = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2",
             *(f"f_rest_{i}" for i in range(9)), "opacity", "scale_0", "scale_1", "scale_2",
             "rot_0", "rot_1", "rot_2", "rot_3"]
    vertices = np.zeros(len(points), dtype=[(name, "<f4") for name in names])
    for index, name in enumerate(("x", "y", "z")):
        vertices[name] = xyz[:, index]
        # Brighten the point glyphs for selection, preserving their exact XYZ.
        vertices[f"f_dc_{index}"] = (np.clip(rgb[:, index] / 255., .18, 1.) - .5) / .28209479177387814
    low, high = np.quantile(xyz, [.05, .95], axis=0)
    size = max(float(np.linalg.norm(high - low)) * .0025, 1e-8)
    for index in range(3):
        vertices[f"scale_{index}"] = np.log(size)
    vertices["opacity"], vertices["rot_0"] = 8., 1.
    header = (f"ply\nformat binary_little_endian 1.0\ncomment SfM alignment point glyphs; not a trained 3DGS model\n"
              f"element vertex {len(points)}\n" + "".join(f"property float {name}\n" for name in names) + "end_header\n")
    data = header.encode("ascii") + vertices.tobytes()
    path = root / "alignment_points.ply"
    root.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != data:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"status": "awaiting_camera_alignment", "gaussian_model_path": str(path), "preview_paths": [],
            "model_quality": {"coordinate_unit": "relative", "representation": "sfm_points",
                              "reference_point_count": len(points), "training_camera_counts": {}}}


@lru_cache(maxsize=2)
def _gaussian_model(path: str, size: int, modified: int, include_dark_bounds: bool = False):
    """Read gsplat's world-space PLY without changing its vertex order."""
    data = Path(path).read_bytes()
    end = data.find(b"end_header\n", 0, 65536)
    if end < 0:
        raise ValueError("模型格式不支援選點，請重新匯出 Gaussian 模型。")
    lines = data[:end].decode("ascii").splitlines()
    if lines[:2] != ["ply", "format binary_little_endian 1.0"]:
        raise ValueError("模型必須是未壓縮的 Gaussian PLY。")
    count = 0
    properties = []
    for line in lines[2:]:
        parts = line.split()
        if parts[:2] == ["element", "vertex"]:
            count = int(parts[2])
        elif parts[:2] == ["property", "float"]:
            properties.append((parts[2], "<f4"))
        elif parts and parts[0] not in {"comment", "obj_info"}:
            raise ValueError("模型 PLY 欄位不支援選點。")
    dtype = np.dtype(properties)
    offset = end + len(b"end_header\n")
    if count <= 0 or count > 5_000_000 or len(data) - offset != count * dtype.itemsize:
        raise ValueError("模型資料不完整，請重新匯出。")
    if not {"x", "y", "z", "opacity", "f_dc_0", "f_dc_1", "f_dc_2"}.issubset(dtype.names or ()):
        raise ValueError("模型缺少 Gaussian 座標或色彩。")
    vertices = np.frombuffer(data, dtype=dtype, count=count, offset=offset)
    xyz = np.column_stack([vertices[name] for name in ("x", "y", "z")])
    opacity = 1 / (1 + np.exp(-np.clip(vertices["opacity"], -80, 80)))
    rgb = np.column_stack([vertices[f"f_dc_{i}"] for i in range(3)]) * .28209479177387814 + .5
    selectable = np.isfinite(xyz).all(axis=1) & np.isfinite(rgb).all(axis=1) & (opacity >= 64 / 255) & (rgb.max(axis=1) >= 30 / 255)
    foreground = selectable & (rgb.max(axis=1) >= .3)
    framing = (np.isfinite(xyz).all(axis=1) & np.isfinite(rgb).all(axis=1) & (opacity >= 64 / 255)) if include_dark_bounds else (foreground if foreground.sum() >= 4 else selectable)
    visible = xyz[framing]
    if len(visible) < 4:
        raise ValueError("模型沒有足夠的可見參照點。")
    # Ignore distant floaters when framing the subject, while retaining the full model.
    low, high = np.quantile(visible, [.05, .95], axis=0)
    center = (low + high) / 2
    radius = max(float(np.linalg.norm(high - low) / 2), 1e-6)
    return vertices, selectable, hashlib.sha256(data).hexdigest(), center, radius, low, high


def model_review_reference(context: dict, root: Path) -> dict:
    reference = context["reference"]
    model = context["model"]
    payload = {"signature": reference["signature"], "points": reference["points"],
               "orbit": reference["orbit"], "model_quality": {
                   **model["model_quality"],
                   **({"immutable_reference": True, "reference_only": True}
                      if context.get("reference_model_policy") == "immutable_per_round_v1" else {}),
               }}
    previews = model.get("preview_paths", [])
    payload["preview_path"] = Path(previews[0]).resolve().relative_to(root.resolve()).as_posix() if previews else None
    path_value = model.get("gaussian_model_path")
    if not path_value:
        return payload
    path = Path(path_value).resolve()
    relative = path.relative_to(root.resolve()).as_posix()
    stat = path.stat()
    include_dark = model.get("model_quality", {}).get("foreground_kind") == "plant_and_pot"
    vertices, _, digest, center, radius, low, high = _gaussian_model(str(path), stat.st_size, stat.st_mtime_ns, include_dark)
    # Sparse SfM anchors also include the enclosure. Frame the visible Gaussian
    # subject instead of widening the camera to include discarded scene points.
    signature = hashlib.sha256(f"gaussian-review-v1:{reference['signature']}:{digest}".encode()).hexdigest()
    offset = max((point["id"] for point in reference["points"]), default=-1) + 1
    first = next((view for view in reference["views"] if view.get("camera_id") == "rotating"), reference["views"][0])
    pose = np.asarray(first["pose"], dtype=float)
    camera_center = -pose[:3, :3].T @ pose[:3, 3]
    up = np.asarray((reference.get("orbit") or {}).get("direction", -pose[1, :3]), dtype=float)
    if up @ (-pose[1, :3]) < 0:
        up = -up
    payload.update(signature=signature, gaussian_path=relative, gaussian_sha256=digest, gaussian_count=len(vertices),
                   gaussian_point_offset=offset, center=center.tolist(), radius=radius,
                   initial_camera={"position": camera_center.tolist(), "up": up.tolist()})
    return payload


def model_preview_reference(path: Path, root: Path, pose: np.ndarray | None = None) -> dict:
    """Frame an existing round Gaussian model without creating review artifacts."""
    path = path.resolve()
    relative = path.relative_to(root.resolve()).as_posix()
    stat = path.stat()
    vertices, _, digest, center, radius, *_ = _gaussian_model(
        str(path), stat.st_size, stat.st_mtime_ns, include_dark_bounds=True,
    )
    position = center + np.array([0., -3., 1.5]) * radius
    up = np.array([0., 0., 1.])
    if pose is not None:
        pose = np.asarray(pose, dtype=float)
        if pose.shape == (4, 4) and np.isfinite(pose).all():
            camera_center = -pose[:3, :3].T @ pose[:3, 3]
            camera_up = -pose[1, :3]
            if np.linalg.norm(camera_center - center) > radius * .05 and np.linalg.norm(camera_up) > 1e-8:
                position, up = camera_center, camera_up
    camera = {"position": position.tolist(), "up": up.tolist()}
    signature = hashlib.sha256(f"gaussian-preview-v1:{relative}:{digest}:{camera}".encode()).hexdigest()
    return {
        "signature": signature, "gaussian_path": relative, "gaussian_sha256": digest,
        "gaussian_count": len(vertices), "gaussian_point_offset": 0, "points": [],
        # Leave room for translucent pot walls outside the opaque framing points.
        "center": center.tolist(), "radius": radius * 1.2, "initial_camera": camera,
    }


def model_review_objects(context: dict, root: Path, reference: dict, point_ids: list[int]) -> list[list[float]]:
    """Resolve only server-owned anchors. Client coordinates are never trusted."""
    anchors = {point["id"]: point["xyz"] for point in context["reference"]["points"]}
    path_value = context["model"].get("gaussian_model_path")
    vertices = selectable = None
    if path_value:
        path = Path(path_value).resolve()
        path.relative_to(root.resolve())
        stat = path.stat()
        vertices, selectable, *_ = _gaussian_model(str(path), stat.st_size, stat.st_mtime_ns)
    objects = []
    for point_id in point_ids:
        if point_id in anchors:
            objects.append(anchors[point_id])
            continue
        index = point_id - reference.get("gaussian_point_offset", point_id + 1)
        if vertices is None or index < 0 or index >= len(vertices) or not selectable[index]:
            raise ValueError("模型參照點不存在或過於透明，請重新選取。")
        objects.append([float(vertices[index][name]) for name in ("x", "y", "z")])
    if len({tuple(point) for point in objects}) != len(objects):
        raise ValueError("參照點位置重複，請選擇不同位置。")
    return objects
