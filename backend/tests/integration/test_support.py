from __future__ import annotations

import json
from pathlib import Path


TEST_BFF_TOKEN = "test-bff-token"


def authorized_headers() -> dict[str, str]:
    return {
        "X-Phyto-BFF-Token": TEST_BFF_TOKEN,
        "X-Phyto-Actor": "pytest-operator",
        "X-Phyto-Role": "operator",
    }


def write_test_config(tmp_path: Path, monkeypatch) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PHYTO_AUTOSCOPY_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("PHYTO_AUTOSCOPY_MOCK", "1")
    monkeypatch.setenv("PHYTO_AUTOSCOPY_BFF_TOKEN", TEST_BFF_TOKEN)
    monkeypatch.setenv(
        "PHYTO_AUTOSCOPY_AUDIT_LOG",
        str(data_dir / "logs" / "audit.jsonl"),
    )

    (config_dir / "default.json").write_text(
        json.dumps(
            {
                "project": {
                    "name": "Phyto-Autoscopy",
                    "name_zh": "綠色自視症",
                    "device_name": "CHLOROCULUS",
                    "device_version": "0.1",
                },
                "hardware": {"mock_mode": True, "camera_scan_max_index": 3},
                "paths": {
                    "captures_dir": str(data_dir / "captures"),
                    "snapshots_dir": str(data_dir / "snapshots"),
                    "calibration_dir": str(data_dir / "calibration"),
                    "analysis_dir": str(data_dir / "analysis"),
                    "database_path": str(data_dir / "database" / "test.sqlite3"),
                    "logs_dir": str(data_dir / "logs"),
                    "temp_dir": str(data_dir / "temp"),
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (config_dir / "cameras.json").write_text(
        json.dumps(
            {
                "cameras": {
                    "top": {"device_name": "CHLOROCULUS EYE-TOP", "device_index": 0},
                    "side": {
                        "device_name": "CHLOROCULUS EYE-SIDE",
                        "device_index": 1,
                    },
                    "rotating": {
                        "device_name": "CHLOROCULUS EYE-ARM",
                        "device_index": 2,
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (config_dir / "motor.json").write_text(
        json.dumps(
            {
                "motor": {
                    "name": "CHLOROCULUS_ARM_MOTOR",
                    "controller": "phidget_stepper_bipolar_hc",
                    "gear_ratio": 1.0,
                    "minimum_angle_deg": 0,
                    "maximum_angle_deg": 360,
                    "velocity_limit_deg_s": 3,
                    "maximum_velocity_limit_deg_s": 6,
                    "acceleration_deg_s2": 3,
                    "maximum_acceleration_deg_s2": 6,
                    "current_limit_amp": 1.5,
                    "maximum_current_limit_amp": 2.4,
                    "stabilization_delay_ms": 0,
                }
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "schedule.json").write_text(
        json.dumps(
            {
                "schedule": {
                    "capture_interval_seconds": 60,
                    "duration_seconds": 14400,
                    "rotation_start_deg": 0,
                    "rotation_end_deg": 15,
                    "rotation_step_deg": 15,
                    "stabilization_delay_ms": 0,
                    "capture_on_return": True,
                }
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "analysis.json").write_text(
        json.dumps({"analysis": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (config_dir / "calibration.json").write_text(
        json.dumps({"calibration": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (config_dir / "logging.json").write_text(
        json.dumps({"logging": {"level": "INFO", "file_name": "test.log"}}),
        encoding="utf-8",
    )
    return config_dir
