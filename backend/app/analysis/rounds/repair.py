from __future__ import annotations


def round_repair_scope(run, round_keys, *, preserve_geometry_keys=()):
    """Persist an explicit round selection across worker pauses and resumes."""
    return {
        "round_keys": list(round_keys),
        "preserve_geometry_keys": list(preserve_geometry_keys),
        "previous_stage": run.stage, "previous_progress": run.progress,
        "previous_current_frame": run.current_frame, "previous_total_frames": run.total_frames,
    }


def has_unfinished_rounds(rounds, repaired_keys):
    return any(item.status in {
        "ready", "preprocessed", "reconstructing", "model_completed", "model_failed", "ready_tip_only", "cancelled",
    } and item.round_key not in repaired_keys for item in rounds)


def rounds_needing_auto_repair(rounds, models, landmarks, corrections):
    """Select unresolved failures, preserving manual exclusions and valid edits."""
    models = {item.round_key: item for item in models}
    landmarks = {item.round_key: item for item in landmarks}
    corrections = {item.round_key: item for item in corrections}
    selected = []
    for item in rounds:
        model = models.get(item.round_key)
        correction = corrections.get(item.round_key)
        landmark = correction.corrected_tip if correction else landmarks.get(item.round_key)
        geometry_failed = item.status in {"failed", "alignment_pending", "model_failed"} or (
            model is not None and model.status in {"failed", "alignment_pending"}
        )
        tip_failed = not (correction and correction.invalid) and (
            bool(correction and correction.pending_alignment)
            or (item.status in {"tip_invalid", "tip_only"} and not (landmark and landmark.valid))
        )
        if geometry_failed or tip_failed:
            selected.append(item)
    return selected
