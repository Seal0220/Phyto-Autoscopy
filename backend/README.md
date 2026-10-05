# Phyto-Autoscopy backend

This directory is the API-only FastAPI hardware backend. It contains camera and motor control, scheduling, settings, records, local storage, and the authenticated status WebSocket.

It is not a browser entry point and deliberately contains no templates, static assets, Jinja routes, or frontend JavaScript. Start the full stack from the repository root with `start.bat`; the Next.js BFF in `../frontend` is the only browser-facing service. This backend never starts, stops, or monitors the frontend.

Helper scripts remain available from either directory, for example:

```bash
python backend/scripts/validate_config.py
```

Windows CUDA vision packages for the project's Python 3.12 environment can be
installed with:

```powershell
.venv/Scripts/python.exe backend/scripts/install_cuda_vision.py
```

This pins and verifies SHA256 hashes of the community Windows builds from
[OpenCV CUDA](https://github.com/Breakthrough/opencv-python-cuda/releases/tag/4.13.0-dev1)
and [PyCOLMAP CUDA/cuDSS](https://github.com/lyehe/build_gpu_colmap/releases/tag/v4.2.0-3).
The installer downloads approximately 3.2 GB, installs into a separate directory
inside `.venv`, and activates it only after checking CUDA availability. Restart
the application manually to load the new packages. Existing processes retain
their loaded versions. Remove `.venv/Lib/site-packages/phyto_cuda_vision.pth` to
return to the original CPU packages.

Analysis preprocessing decodes each PNG once, creates a lossless TIFF cache,
and applies intrinsics/undistortion in the same traversal. OpenCV CUDA remapping
is preferred, with PyTorch CUDA and then CPU fallbacks. SIFT extraction, matching,
ORB features, and Ceres bundle adjustment request CUDA when available.

Image preprocessing starts at the logical CPU core count and measures actual
throughput while trying larger concurrency windows, up to eight times the core
count and at most 128. It retains the fastest measured window, preferring fewer
threads when speeds differ by less than 10%. RAM (60% available) and CUDA memory
(70% available) bound every requested worker count. Restored results and fresh
images are tuned separately. Immutable camera maps are shared across threads;
each worker has its own CUDA stream and image buffers.
Workers overlap source decoding, lossless TIFF
encoding, CUDA remapping on separate streams, and output writes. Lookahead is
bounded by the memory-limited worker ceiling; decoded images are never accumulated
for the entire record. Progress displays the currently selected concurrency.
Frequent progress updates use a separate small `analysis_run_progress` row, so
they never rewrite the large frozen manifests in `analysis_runs`. Preview and
progress notifications refresh at most twice per second, while every completed
image still saves its own durable checkpoint. Current image requests select only
one view and its paths. Analysis uses lossless TIFF; browser previews use JPEG.
GPU/CPU undistortion totals include checkpoint results with their original backend;
`沿用已完成影像` counts validated outputs that do not need to be computed again.
Pause stops dispatching new images, waits for in-flight images to save their
checkpoints, and closes every decoder, CUDA cache, and worker thread. A resumed
run selects its concurrency again using the resources available at that time.

Use **暫停並保存** in an analysis to stop at a safe step, then **恢復分析** to
continue. Image and round checkpoints are persisted under `checkpoints/steps.sqlite3`.
Training saves weights, optimizer/scheduler state, densification state, RNG state,
and the completed iteration. Large training snapshots are periodic and saved on
pause; forced termination can replay iterations since the latest snapshot.
Native extraction or triangulation calls finish their current step before a pause
takes effect. Source identity and checkpoint outputs are checked before reuse.

If automatic fixed stereo pose estimation cannot find valid shared features, the
analysis enters **等待人工雙鏡頭配對** and opens a human review dialog. Mark at least
eight corresponding static positions in the undistorted top and side images,
then use **驗證配對並繼續分析**. The paired images must come from the same round and
snapshot. Manual pairs still pass essential geometry, positive depth,
reprojection, and parallax checks; invalid pairs remain editable for correction.
Accepted poses, the submitted pairs, and the authenticated reviewer are saved
before continuing from existing image checkpoints. This review cannot be skipped
through the later tip-review action. On startup, earlier runs that failed because
fixed stereo pose estimation had no valid shared features enter the same review
state, retaining their diagnostic images.
