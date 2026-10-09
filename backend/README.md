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

For **rotating** analyses without ArUco, all valid images from the reference
round's three cameras enter CUDA SIFT and joint COLMAP mapping. Plant/pot/soil
feature masks exclude background equipment. Initialization requires a verified
rotating pair with a motor baseline of 10–90 degrees; repeated fixed frames
cannot establish depth. Motor angles and registered camera centres fit a
rotation axis and a circular pose prior, with residuals in the quality report.
Fixed-camera poses use MAD outlier rejection and Huber-weighted camera-centre
and SO(3) rotation means. If both cameras register, reference 3DGS trains once
using every valid image in the shared relative coordinate frame. Otherwise
fixed-camera registration is retried before final reference training. If a camera
still cannot register, a trained Gaussian alignment preview uses only the
successfully registered views, keeping the selected training quality and the
plant/pot foreground. It is marked `alignment_3dgs` with purpose
`camera_alignment_preview`; it supplies identifiable landmarks for manual alignment
and does not replace the final three-camera model. Missing camera poses are never
invented. Preview training has a separate checkpoint and survives pause/resume.
Sparse tracks initialize training without another extraction pass;
top/side feature overlap is not required when they connect through rotating views.

If registration needs help, **對齊相機** opens the trained alignment preview
in a WebGL viewer above the two images. Legacy runs retain their existing
Gaussian reference and drafts. Runs showing the older `sfm_points` glyphs can
manually select **重建預覽**, which returns to camera review after creating the
dense preview. Changing the preview signature hides stale Gaussian selections.
Click a real world-space anchor to select it,
drag to orbit, right-drag to pan, or scroll inside
the preview to zoom. The only control button is **重設鏡頭**. Scrolling outside
the preview moves the page; focused keyboard controls use arrows, Shift+arrows,
+/- and 0. Select at least four
distinct known 3D reference points and their physical positions in both images.
Clicking a new model anchor creates another correspondence; clicking an existing
anchor selects its pair. Numbered markers keep previously selected points visible.
PnP checks positive depth and reprojection; ambiguous geometry needs another
point. The browser preserves PLY vertex order and verifies its SHA-256; the
server resolves coordinates from the same PLY, validates the model signature
and rejects faint/background points. Existing sparse anchors and drafts remain
usable without retraining. Large Gaussian arrays are not duplicated in JSON.
Only after registration does the measured stereo baseline set millimetre scale;
the axis and measured top height define the world frame. Each round uses that
rig and motor orbit as initial poses, followed by constrained refinement and its
own model/tip analysis. SfM snapshots, reference training and registration are
durable; resuming an accepted review keeps its registered camera poses.
Each round automatically builds one **immutable auxiliary reference 3DGS** from
its successfully registered views. All captured cameras are supplied to SfM;
only registered views can train the model, and actual per-camera counts make
missing registration explicit. Subsequent image tip edits and metric camera
registration never retrain or distort that model. Accepted SfM, training and
registration results survive a pause. Metric registration and calibrated tip
triangulation remain separate from the model's visual-reference role. Image
tracking uses fixed top/side observations of the operator-identified shoot;
unregistered or rejected geometry cannot create millimetre measurements.
Round outputs preserve supporting camera counts, rejected observations and
reprojection diagnostics, without averaging coordinates across rounds or
claiming that pixel residuals alone prove absolute millimetre accuracy.
Earlier rotating runs waiting for direct stereo matching become **paused** on
startup, ready for the user to resume this new workflow. No work starts by itself.

With plant masking enabled, reconstruction retains the plant, pot and soil and
supervises foreground opacity plus transparent background. The visible pot rim
seeds a bounded segmentation of the dark pot; the enclosure and detached lamps
are excluded. A separate plant-only mask remains available for tip measurements
and plant-only exports. Content-derived training crops preserve small subjects at
native resolution within the preset's pixel budget, with matching principal-point
and resize corrections. The default backend now uses
[3DGS MCMC](https://github.com/ubc-vision/3dgs-mcmc) through gsplat's
`MCMCStrategy`: opacity-based relocation, bounded Gaussian growth and stochastic
position updates replace gradient-threshold splitting and opacity resets.
Opacity and scale regularization use coefficients of 0.01. Progressive third-degree
spherical harmonics and antialiased rasterization are used in training, exported
previews and the interactive viewer. Foreground models have a 100,000-Gaussian
budget, never below the initial sparse count; scene models have a 1,000,000-Gaussian
budget. Camera poses remain fixed. The previous imposed covariance shape objective
is removed. A strategy change cannot supply missing camera registrations or
establish measurement accuracy. Multi-view mask evidence filters sparse
initialization and exported Gaussians in both relative and metric coordinates.
Mask content and the training version invalidate older tensor checkpoints and
reference model caches. SfM may still use scene features to estimate camera poses.
On startup, pending rotating model reviews using an older training version become
paused without deleting their artifacts or starting work. The user resumes the
analysis to rebuild the reference; current-version reviews remain unchanged.

Per-round tip editing uses one simultaneous undistorted **top/side** pair with
the reference model below it. Rotating images remain available in the image
gallery but are not editable tip inputs. A model pick submits a Gaussian ID and
model signature; the server resolves its unchanged PLY vertex and applies the
separately saved model-to-world registration. Without metric registration the
pick is retained as pending and omitted from valid trajectory measurements.
Pending image/model picks resolve when registration becomes available, retaining
their correction ID. Manual corrections can update live charts while other rounds
train. Existing immutable reference models are reused until explicitly rebuilt.

The default tip workflow is now **manually seeded temporal tracking**. Before
training the first complete round of each mode, prepare its first two fixed-camera
pairs and pause at `waiting_for_tip_seed`. Identify the same shoot apex in top
and side images. Plant support, visible pixels, texture, and the next available
frame validate the seed; a confirmed save resumes processing after the pausing
worker exits. Existing image corrections can initialize tracking without
requiring a registered reference model. Later rounds use that identity, or a newer
manual correction, with local appearance matching, subpixel peak fitting,
distinctiveness and forward/backward checks. Brief occlusions are skipped;
an unverified target remains a gap for optional correction. No coordinate is
interpolated into a verified measurement. `image_tip_confirmed` and
`image_observations` describe image identity; `valid` and millimetre coordinates
still require calibrated multi-view geometry. Missing model-camera registration
cannot erase a good image seed. Tracking never changes the reference PLY.

This follows the temporal identity and correction principle in Ruiz-Melero et al.,
Sensors 2024, 24(3), 747, sections 2.3.2–2.3.4; it is not an implementation of
their full mixture-of-Gaussians/epipolar minimum-path detector. Internal matching
scores and return errors do not establish the paper's measurement accuracy.
Read-only `round-feature-correspondences` exposes actual COLMAP observations
supported by plant masks in at least two displayed cameras, with shared IDs for
linked highlighting. Unregistered cameras have no fabricated correspondence.
The approximately 295° side-camera mount provided by the operator is recorded
as an azimuth reference against the rotating motor angles, never an exact
measurement or a constraint that overwrites image-estimated poses.

For **fixed** analyses, if automatic stereo pose estimation cannot find valid shared features, the
analysis enters **等待人工雙鏡頭配對** and expands the inline human review section.
The page scrolls to the section; images use their natural height and the document
owns scrolling. Mark at least five corresponding physical positions in the
undistorted top and side images, then use **驗證並繼續**. Visible bud tips, leaf
tips and stem nodes are eligible when they identify the same physical point in
both views. The paired images must come from the same round and
snapshot. Manual pairs still pass essential geometry, positive depth,
reprojection, and parallax checks; invalid pairs remain editable for correction.
The five-point solver can return several poses; all are checked, and ambiguous
results require another correspondence. Four pairs cannot estimate unknown
stereo extrinsics. The last validation's inlier count and original pair indices
are saved with the draft and shown in the review interface; editing points clears
the previous verdict.
Accepted poses, the submitted pairs, and the authenticated reviewer are saved
before continuing from existing image checkpoints. This review cannot be skipped
through the later tip-review action. On startup, earlier runs that failed because
fixed stereo pose estimation had no valid shared features enter the same review
state, retaining their diagnostic images.
