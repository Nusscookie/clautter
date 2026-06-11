"""Face-based zoom *centering* using OpenCV Haar cascade.

Face detection no longer triggers zooms (cuts do — see analyzer.py). Its only
job now is to re-center an already-chosen zoom on the speaker: given a source
frame, sample that frame, find the largest face, and return a normalized
pan/tilt offset that pushes the frame toward the speaker. The applier maps these
to Resolve's Pan/Tilt (static path) or Fusion Center (smooth path) and raises the
zoom so no black edge is exposed.

Uses cv2's built-in Haar cascade (ships with opencv-python, no model download).
"""

from __future__ import annotations
import os

from src.utils.logger import get_logger

log = get_logger(__name__)


def face_offset_at(
    file_path: str,
    src_frame: int,
    fps: float = 25.0,
    pan_tilt_strength: float = 0.6,
) -> tuple[float, float] | None:
    """Return (pan, tilt) to center a zoom on the speaker at ``src_frame``.

    Samples a single frame of the source media, runs Haar-cascade face detection,
    and converts the largest face's offset from frame center into normalized
    pan/tilt in [-0.5, 0.5]. Resolve Pan>0 moves the image right, so the applier
    places the face at Center.X = 0.5 - pan; Tilt>0 moves it up → Center.Y =
    0.5 + tilt. Hence the sign inversion here: shift the frame opposite the face.

    Args:
        file_path:         Source media file path.
        src_frame:         Frame within the source file to sample.
        fps:               Timeline frame rate (unused for sampling; kept for callers).
        pan_tilt_strength: How hard to push toward the face. 0 = always center,
                           1 = fully shift the face to center.

    Returns:
        (pan, tilt) if a face was found, else None (caller does a plain center zoom).

    Raises:
        ImportError: If opencv-python is not installed.
        FileNotFoundError: If the media file does not exist.
    """
    try:
        import cv2
    except ImportError as e:
        raise ImportError(
            "opencv-python is required for face tracking. "
            "Install with: pip install opencv-python"
        ) from e

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        raise RuntimeError(
            f"Could not load Haar cascade from {cascade_path}. Reinstall opencv-python."
        )

    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {file_path}")

    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(src_frame)))
        ret, frame = cap.read()
        if not ret:
            log.debug("face_offset_at: could not read frame %d of %s",
                      src_frame, os.path.basename(file_path))
            return None

        frame_h, frame_w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60),
        )
    finally:
        cap.release()

    if len(faces) == 0:
        return None

    # Largest face = the speaker.
    fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
    face_cx = fx + fw / 2.0
    face_cy = fy + fh / 2.0
    norm_dx = (face_cx / frame_w) - 0.5 if frame_w else 0.0
    norm_dy = (face_cy / frame_h) - 0.5 if frame_h else 0.0

    pan = -norm_dx * pan_tilt_strength
    tilt = -norm_dy * pan_tilt_strength
    log.debug(
        "Face at src_frame=%d offset dx=%.2f dy=%.2f → pan=%.2f tilt=%.2f",
        src_frame, norm_dx, norm_dy, pan, tilt,
    )
    return pan, tilt
