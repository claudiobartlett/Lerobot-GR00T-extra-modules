import subprocess
import numpy as np
import cv2
import time
from pypylon import pylon

# ----------------------------------------
# Configure your Basler camera
# ----------------------------------------
cam = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
cam.Open()
cam.PixelFormat = "BGR8"

# -----------------------------
# Try to brighten via camera settings first
# -----------------------------
try:
    # Auto exposure if available
    if hasattr(cam, "ExposureAuto"):
        try:
            cam.ExposureAuto.SetValue("Continuous")
        except:
            try:
                cam.ExposureAuto = "Continuous"
            except:
                pass

    # Exposure time
    if hasattr(cam, "ExposureTime"):
        try:
            cam.ExposureTime.SetValue(20000.0)
        except:
            try:
                cam.ExposureTime = 20000.0
            except:
                pass
    elif hasattr(cam, "ExposureTimeAbs"):
        try:
            cam.ExposureTimeAbs.SetValue(20000.0)
        except:
            try:
                cam.ExposureTimeAbs = 20000.0
            except:
                pass

    # Gain bump
    if hasattr(cam, "Gain"):
        try:
            min_gain = cam.Gain.GetMin()
            max_gain = cam.Gain.GetMax()
            target = min(max_gain, max(min_gain, min_gain + (max_gain - min_gain) * 0.2))
            cam.Gain.SetValue(target)
        except:
            try:
                cam.Gain = getattr(cam, "Gain", 0) + 5
            except:
                pass

except Exception as e:
    print("Warning: failed to set one or more camera properties for brightness:", e)

# ----------------------------------------
# Output converter
# ----------------------------------------
converter = pylon.ImageFormatConverter()
converter.OutputPixelFormat = pylon.PixelType_BGR8packed
converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

cam.StartGrabbing()

# ----------------------------------------
# Virtual camera output settings
# ----------------------------------------
OUTPUT_WIDTH = 640
OUTPUT_HEIGHT = 480
FPS = 15   # final FPS we output to v4l2loopback

# Software FPS limiter
FRAME_INTERVAL = 1.0 / FPS
last_frame_time = 0

ffmpeg = subprocess.Popen([
    "ffmpeg",
    "-loglevel", "error",
    "-y",
    "-f", "rawvideo",
    "-pixel_format", "bgr24",
    "-video_size", f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
    "-framerate", str(FPS),
    "-i", "-",
    "-f", "v4l2",
    "/dev/video10",
], stdin=subprocess.PIPE)

# ----------------------------------------
# Main loop (push frames to virtual cam)
# ----------------------------------------
try:
    while cam.IsGrabbing():
        grab = cam.RetrieveResult(1000)
        if grab.GrabSucceeded():
            img = converter.Convert(grab)
            frame = img.GetArray()

            # Brightness fallback
            try:
                frame = cv2.convertScaleAbs(frame, alpha=1.0, beta=0)
            except:
                pass

            # -----------------------------
            # Zoom-out   (scale entire image to 640×480)
            # -----------------------------
            frame = cv2.resize(
                frame,
                (OUTPUT_WIDTH, OUTPUT_HEIGHT),
                interpolation=cv2.INTER_AREA
            )

            # -----------------------------
            # Software FPS limiter — ENFORCE 15 FPS
            # -----------------------------
            now = time.time()
            if now - last_frame_time >= FRAME_INTERVAL:
                ffmpeg.stdin.write(frame.tobytes())
                last_frame_time = now
            # -----------------------------

        grab.Release()

except KeyboardInterrupt:
    pass

cam.Close()
ffmpeg.stdin.close()
ffmpeg.wait()
