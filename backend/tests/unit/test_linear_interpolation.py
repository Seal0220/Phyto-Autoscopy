from app.analysis.tracking.linear_interpolation import (
    TrackPoint,
    interpolate_missing_track,
)


def point(frame, x, y, kind="Automatic", barrier=None):
    return TrackPoint(
        frame_id=frame,
        timestamp=f"2026-01-01T00:00:0{frame}+00:00",
        x_px=x,
        y_px=y,
        detection_type=kind,
        valid=x is not None,
        barrier=barrier,
    )


def test_linear_interpolation_preserves_middle_zero_coordinates() -> None:
    result = interpolate_missing_track(
        [point(0, -1, 2), point(1, None, None, "Missing"), point(2, 1, 4)],
        maximum_gap_seconds=10,
    )
    assert result[1].x_px == 0
    assert result[1].y_px == 3
    assert result[1].detection_type == "Interpolated"


def test_linear_interpolation_does_not_cross_barriers_or_edges() -> None:
    result = interpolate_missing_track(
        [
            point(0, None, None, "Missing"),
            point(1, 1, 1),
            point(2, None, None, "Missing", "unpaired"),
            point(3, 3, 3),
        ],
        maximum_gap_seconds=10,
    )
    assert result[0].x_px is None
    assert result[2].x_px is None


def test_linear_interpolation_rejects_long_gap() -> None:
    values = [
        TrackPoint(1, "2026-01-01T00:00:00+00:00", 0, 0, "Automatic", True),
        TrackPoint(2, "2026-01-01T00:01:00+00:00", None, None, "Missing", False),
        TrackPoint(3, "2026-01-01T00:02:00+00:00", 2, 2, "Automatic", True),
    ]
    assert interpolate_missing_track(values, maximum_gap_seconds=30)[1].x_px is None
