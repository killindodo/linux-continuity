"""
Audio and Video Capture Manager for Linux Continuity.
Provides webcam frame grabbing and live microphone audio streaming via ffmpeg / v4l2 / PulseAudio.
Developed by killindodo
"""

import os
import time
import shutil
import subprocess
from typing import Optional, Dict, Any


class AVCaptureManager:
    def __init__(self):
        self.video_device = "/dev/video0"
        self._last_frame: Optional[bytes] = None
        self._last_frame_time: float = 0.0
        self._cache_ttl: float = 0.5  # Cache frame for 500ms to prevent v4l2 device locking

    def has_webcam(self) -> bool:
        return os.path.exists(self.video_device)

    def has_mic(self) -> bool:
        # Check if ffmpeg with pulse or arecord is available
        return bool(shutil.which("ffmpeg") or shutil.which("arecord") or shutil.which("pw-record"))

    def get_status(self) -> Dict[str, Any]:
        return {
            "has_webcam": self.has_webcam(),
            "webcam_device": self.video_device if self.has_webcam() else None,
            "has_mic": self.has_mic()
        }

    def capture_frame(self, width: int = 640, height: int = 360, quality: int = 3) -> Optional[bytes]:
        """
        Captures a single JPEG snapshot from the PC webcam.
        Uses a short cache to prevent v4l2 bus conflicts.
        """
        now = time.time()
        if self._last_frame and (now - self._last_frame_time) < self._cache_ttl:
            return self._last_frame

        if not self.has_webcam() or not shutil.which("ffmpeg"):
            return None

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "v4l2",
            "-video_size", f"{width}x{height}",
            "-i", self.video_device,
            "-frames:v", "1",
            "-q:v", str(quality),
            "-f", "image2",
            "-vcodec", "mjpeg",
            "-"
        ]

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=2.0
            )
            if res.returncode == 0 and res.stdout and len(res.stdout) > 500:
                self._last_frame = res.stdout
                self._last_frame_time = now
                return self._last_frame
        except Exception:
            pass

        return self._last_frame

    def open_camera_on_desktop(self) -> bool:
        """Launches a live camera viewer window directly on the PC desktop."""
        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"

        # Try desktop camera apps or ffplay
        if shutil.which("cheese"):
            try:
                subprocess.Popen(["cheese"], env=env)
                return True
            except Exception:
                pass

        if shutil.which("guvcview"):
            try:
                subprocess.Popen(["guvcview"], env=env)
                return True
            except Exception:
                pass

        if shutil.which("ffplay"):
            try:
                subprocess.Popen([
                    "ffplay",
                    "-f", "v4l2",
                    "-video_size", "1280x720",
                    "-window_title", "Linux Continuity - Camera",
                    self.video_device
                ], env=env)
                return True
            except Exception:
                pass

        return False


# Singleton instance
av_mgr = AVCaptureManager()
