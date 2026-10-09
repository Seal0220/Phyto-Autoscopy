"""Estimate orbit angles from image poses, then calibrate the motor reference."""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


def image_motor_angles(views) -> tuple[np.ndarray, dict]:
    """Motor readings only disambiguate direction and full turns on SO(3)."""
    recorded = np.asarray([view["angle_deg"] for view in views], dtype=float)
    poses = np.asarray([view["pose"] for view in views], dtype=float)
    if not np.isfinite(recorded).all() or not np.isfinite(poses).all():
        raise ValueError("旋臂角度或影像姿態含無效數值。")
    rotations = np.linalg.inv(poses)[:, :3, :3]
    relative = rotations @ rotations[0].T
    logs = Rotation.from_matrix(relative).as_rotvec()
    # Very short baselines give poorly conditioned axis directions. Long
    # relative rotations determine the common axis without using motor angles.
    usable = np.linalg.norm(logs, axis=1) > np.deg2rad(20)
    if usable.sum() < 3:
        raise ValueError("旋臂影像姿態的轉角分布不足，無法校正馬達角度。")
    vectors = logs[usable]
    _, _, right = np.linalg.svd(vectors, full_matrices=False)
    axis = right[0]
    for _ in range(10):
        perpendicular = np.linalg.norm(vectors - (vectors @ axis)[:, None] * axis, axis=1)
        scale = max(float(np.median(perpendicular)) * 1.4826, np.deg2rad(.5))
        weights = np.minimum(1., scale / np.maximum(perpendicular, 1e-12))
        _, _, right = np.linalg.svd(vectors * np.sqrt(weights[:, None]), full_matrices=False)
        axis = right[0]
    steps = Rotation.from_matrix(rotations[1:] @ rotations[:-1].transpose(0, 2, 1)).as_rotvec()
    if np.sum((steps @ axis) * np.diff(recorded)) < 0:
        axis = -axis
    skew = np.column_stack((relative[:, 2, 1] - relative[:, 1, 2],
                            relative[:, 0, 2] - relative[:, 2, 0],
                            relative[:, 1, 0] - relative[:, 0, 1]))
    sine = skew @ axis / 2
    cosine = (np.trace(relative, axis1=1, axis2=2) - np.einsum("i,nij,j->n", axis, relative, axis)) / 2
    observed = np.rad2deg(np.arctan2(sine, cosine))
    observed += 360 * np.round((recorded - recorded[0] - observed) / 360)
    observed += recorded[0]
    calibration = _regress_angles(recorded, observed)
    calibration["observations"] = [
        {"view_id": str(view.get("view_id", view.get("image_name", index))),
         "recorded_angle_deg": float(raw), "image_angle_deg": float(angle),
         "difference_deg": float(angle - raw)}
        for index, (view, raw, angle) in enumerate(zip(views, recorded, observed))
    ]
    return observed, calibration


def _regress_angles(recorded: np.ndarray, observed: np.ndarray) -> dict:
    """Choose a low-order robust correction using held-out angular samples."""
    lower, upper = float(recorded.min()), float(recorded.max())
    origin, scale = (lower + upper) / 2, (upper - lower) / 2
    if scale < 1e-8:
        raise ValueError("馬達角度分布不足，無法回歸校正。")
    normalized = (recorded - origin) / scale
    offsets = observed - recorded
    best = None
    for degree in ((1, 2, 3) if len(recorded) >= 18 else (1,)):
        design = np.polynomial.polynomial.polyvander(normalized, degree)

        def fit(mask):
            initial = np.linalg.lstsq(design[mask], offsets[mask], rcond=None)[0]
            result = least_squares(lambda values: design[mask] @ values - offsets[mask], initial,
                                   loss="soft_l1", f_scale=.5, max_nfev=100)
            return result.x

        coefficients = fit(np.ones(len(recorded), dtype=bool))
        derivative = 1 + np.polynomial.polynomial.polyval(
            np.linspace(-1, 1, 101), np.polynomial.polynomial.polyder(coefficients),
        ) / scale
        if not np.isfinite(coefficients).all() or derivative.min() < .5 or derivative.max() > 1.5:
            continue
        errors = np.zeros(len(recorded))
        for fold in range(5):
            heldout = np.arange(len(recorded)) % 5 == fold
            errors[heldout] = design[heldout] @ fit(~heldout) - offsets[heldout]
        validation_error = float(np.sqrt(np.mean(errors ** 2)))
        # Prefer the simpler fit unless another order improves validation by 10%.
        if best is None or validation_error < best[0] * .9:
            best = (validation_error, coefficients, degree, errors.copy())
    if best is None:
        raise ValueError("影像轉角與馬達紀錄不一致，無法建立可靠的角度參考。")
    error, coefficients, degree, validation_errors = best
    residual = np.polynomial.polynomial.polyval(normalized, coefficients) - offsets
    return {"method": "cross_validated_robust_polynomial", "source": "sfm_rotations",
            "degree": degree, "origin_deg": origin, "scale_deg": scale,
            "coefficients_deg": coefficients.tolist(), "recorded_min_deg": lower, "recorded_max_deg": upper,
            "observation_count": len(recorded), "validation_rmse_deg": error,
            "validation_absolute_p95_deg": float(np.percentile(np.abs(validation_errors), 95)),
            "validation_absolute_max_deg": float(np.max(np.abs(validation_errors))),
            "validation_fraction_below_one_degree": float(np.mean(np.abs(validation_errors) < 1)),
            "validation_scope": "interleaved_angle_prediction_against_joint_sfm",
            "absolute_accuracy_verified": False,
            "prediction_p95_below_one_degree": bool(np.percentile(np.abs(validation_errors), 95) < 1),
            "recorded_difference_rmse_deg": float(np.sqrt(np.mean(offsets ** 2))),
            "maximum_recorded_difference_deg": float(np.max(np.abs(offsets))),
            "regression_rmse_deg": float(np.sqrt(np.mean(residual ** 2)))}


def calibrated_motor_angle(angle_deg: float, orbit) -> float:
    """Use calibrated readings only for views without an image-derived pose."""
    calibration = orbit.get("angle_calibration")
    if not calibration:
        return float(angle_deg)
    coefficients = np.asarray(calibration["coefficients_deg"], dtype=float)
    scale = float(calibration["scale_deg"])
    origin = float(calibration["origin_deg"])
    if scale <= 0 or not np.isfinite([scale, origin, angle_deg]).all() or not np.isfinite(coefficients).all():
        raise ValueError("馬達角度回歸校正資料無效。")
    value = (float(angle_deg) - origin) / scale
    bounded = float(np.clip(value, -1, 1))
    correction = float(np.polynomial.polynomial.polyval(bounded, coefficients))
    # Extrapolate with the boundary slope instead of an unbounded polynomial.
    correction += (value - bounded) * float(np.polynomial.polynomial.polyval(
        bounded, np.polynomial.polynomial.polyder(coefficients),
    ))
    return float(angle_deg) + correction
