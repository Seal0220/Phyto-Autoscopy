"""Keep native COLMAP/ONNX lifetimes separate from the CUDA renderer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def match_reference_images(job):
    import pycolmap
    root = Path(job["root"])
    database_path = root / "features.db"
    names, size, matrix = job["names"], job["size"], np.asarray(job["matrix"])
    if not database_path.exists():
        with pycolmap.Database.open(database_path) as database:
            scene = pycolmap.Reconstruction()
            camera = pycolmap.Camera(camera_id=1, model="PINHOLE", width=size[0], height=size[1],
                params=[matrix[0, 0], matrix[1, 1], matrix[0, 2], matrix[1, 2]], has_prior_focal_length=True)
            scene.add_camera_with_trivial_rig(camera)
            database.write_camera(camera, use_camera_id=True)
            for rig in scene.rigs.values():
                database.write_rig(rig, use_rig_id=True)
            for image_id, name in enumerate(names, 1):
                scene.add_image_with_trivial_frame(pycolmap.Image(image_id=image_id, camera_id=1, name=name))
                database.write_frame(scene.frame(image_id), use_frame_id=True)
                database.write_image(scene.image(image_id), use_image_id=True)
    reader = pycolmap.ImageReaderOptions()
    reader.mask_path = root / "masks"
    extraction = pycolmap.FeatureExtractionOptions()
    extraction.num_threads = 4
    extraction.type = pycolmap.FeatureExtractorType.ALIKED_N16ROT
    extraction.aliked.max_num_features, extraction.aliked.min_score = 2048, .1
    pycolmap.extract_features(database_path, root / "images", names,
        reader_options=reader, extraction_options=extraction, device=pycolmap.Device.cpu)
    matching = pycolmap.FeatureMatchingOptions()
    matching.num_threads = 2
    matching.type = pycolmap.FeatureMatcherType.ALIKED_LIGHTGLUE
    pycolmap.match_exhaustive(database_path, matching_options=matching, device=pycolmap.Device.cpu)
    arrays = {}
    with pycolmap.Database.open(database_path) as database:
        for image_id in range(1, len(names) + 1):
            arrays[f"keypoints_{image_id}"] = np.asarray(database.read_keypoints(image_id))[:, :2]
        for first in range(1, job["render_count"] + 1):
            for second in range(job["render_count"] + 1, len(names) + 1):
                arrays[f"matches_{first}_{second}"] = database.read_matches(first, second)
    # Publish only after all extraction, matching and reads have finished.
    with (root / "matches.tmp").open("wb") as handle:
        np.savez_compressed(handle, **arrays)
    (root / "matches.tmp").replace(root / "matches.npz")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, type=Path)
    args = parser.parse_args()
    match_reference_images(json.loads(args.job.read_text(encoding="utf-8")))
