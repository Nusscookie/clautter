"""Face-based zoom point detection using OpenCV Haar cascade.

Samples frames at 1 fps, runs face detection on each, and returns ZoomPoint
objects at timestamps where a face is confidently present. This is semantically
correct for talking-head content — zooms on the speaker, not on loud sounds.

The zoom is centered on the detected face: the largest face bbox per sampled
frame yields a normalized offset from frame center, carried on the ZoomPoint as
`pan`/`tilt`. The applier maps these to Resolve's Pan/Tilt clip properties
(in project pixels) so the zoom pushes toward the speaker, not the frame middle.

Uses cv2's built-in Haar cascade (ships with opencv-python, no model download).
"""

from __future__ import annotations
import os
from typing import TYPE_CHECKING

from src.utils.logger import get_logger
from src.zooms.analyzer import ZoomPoint, _ZOOM_DURATION_MS

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


def detect_zoom_points_face(
    file_path: str,
    clip_start_frame: int = 0,
    src_start_frame: int = 0,
    src_end_frame: int = -1,
    fps: float = 25.0,
    sample_interval_sec: float = 1.0,
    max_per_minute: int = 4,
    zoom_amount: float = 1.15,
    zoom_duration_ms: float = _ZOOM_DURATION_MS,
    min_confidence: float = 0.7,
    pan_tilt_strength: float = 0.6,
) -> list[ZoomPoint]:
    """Detect zoom points using OpenCV face detection.

    Args:
        file_path:           Source media file path.
        clip_start_frame:    Timeline frame at which this clip starts.
        src_start_frame:     First source frame of the clip in the media file.
        src_end_frame:       Last source frame (-1 = end of file).
        fps:                 Timeline frame rate.
        sample_interval_sec: How often to sample frames for face detection.
        max_per_minute:      Max zoom points per minute.
        zoom_amount:         Zoom scale factor (1.15 = 115%).
        zoom_duration_ms:    Duration of each zoom region in ms.
        min_confidence:      Unused — kept for API compatibility. Cascade uses
                             fixed scale/neighbor params instead.
        pan_tilt_strength:   How hard to push the frame toward the face. 0 =
                             always frame-center; 1 = fully shift the face to
                             center. Scaled against project resolution downstream.

    Returns:
        List of ZoomPoint objects sorted by timeline_frame.

    Raises:
        ImportError: If opencv-python is not installed.
        FileNotFoundError: If the media file does not exist.
    """
    try:
        import cv2
    except ImportError as e:
        raise ImportError(
            "opencv-python is required for face detection. "
            "Install with: pip install opencv-python"
        ) from e

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        raise RuntimeError(
            f"Could not load Haar cascade from {cascade_path}. "
            "Reinstall opencv-python."
        )

    log.debug(
        "detect_zoom_points_face: %s | interval=%.1fs | max=%d/min",
        os.path.basename(file_path),
        sample_interval_sec,
        max_per_minute,
    )

    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {file_path}")

    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS) or fps
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        src_start_sec = src_start_frame / fps
        src_end_sec = (src_end_frame / fps) if src_end_frame >= 0 else (total_frames / video_fps)

        clip_duration_sec = max(0.0, src_end_sec - src_start_sec)
        if clip_duration_sec < sample_interval_sec:
            log.debug("Clip too short for face sampling: %.1fs", clip_duration_sec)
            return []

        min_spacing_ms = (60_000.0 / max(max_per_minute, 1)) if max_per_minute > 0 else 99_999.0
        zoom_dur_frames = max(1, int((zoom_duration_ms / 1000.0) * fps))

        # Each entry: (timestamp_ms, norm_dx, norm_dy) where norm_d* is the
        # face-center offset from frame center as a fraction of frame size
        # in [-0.5, 0.5]. norm_dx > 0 = face right of center.
        face_hits: list[tuple[float, float, float]] = []

        t = src_start_sec
        while t < src_end_sec:
            frame_num = int(t * video_fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                t += sample_interval_sec
                continue

            frame_h, frame_w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(60, 60),
            )

            if len(faces) > 0:
                # Largest face = the speaker.
                fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
                face_cx = fx + fw / 2.0
                face_cy = fy + fh / 2.0
                norm_dx = (face_cx / frame_w) - 0.5 if frame_w else 0.0
                norm_dy = (face_cy / frame_h) - 0.5 if frame_h else 0.0
                face_hits.append((t * 1000.0, norm_dx, norm_dy))
                log.debug(
                    "Face at %.2fs (frame %d) offset dx=%.2f dy=%.2f",
                    t, frame_num, norm_dx, norm_dy,
                )

            t += sample_interval_sec

    finally:
        cap.release()

    if not face_hits:
        log.info("No faces detected in '%s'", os.path.basename(file_path))
        return []

    # Apply max_per_minute spacing — keep only well-spaced detections
    points: list[ZoomPoint] = []
    last_accepted_ms = -min_spacing_ms

    for face_ms, norm_dx, norm_dy in face_hits:
        if face_ms - last_accepted_ms < min_spacing_ms:
            continue

        rel_sec = (face_ms / 1000.0) - src_start_sec
        timeline_frame = clip_start_frame + int(rel_sec * fps)

        # Shift the frame opposite to the face offset so the speaker moves
        # toward center. Resolve Pan>0 moves image right, Tilt>0 moves it up.
        pan = -norm_dx * pan_tilt_strength
        tilt = -norm_dy * pan_tilt_strength

        points.append(ZoomPoint(
            timeline_frame=timeline_frame,
            duration_frames=zoom_dur_frames,
            zoom_amount=zoom_amount,
            energy_dbfs=0.0,
            pan=pan,
            tilt=tilt,
        ))
        last_accepted_ms = face_ms

    log.info(
        "Found %d zoom point(s) via face detection in '%s'",
        len(points),
        os.path.basename(file_path),
    )
    return points
