import os

# Suppress ALL TensorFlow, MediaPipe, and GLOG output
os.environ["GLOG_minloglevel"] = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["MEDIAPIPE_DISABLE_GPU"] = "1"
os.environ["GLOG_logtostderr"] = "0"
os.environ["GLOG_stderrthreshold"] = "3"
os.environ["GLOG_v"] = "0"

# Redirect stderr to devnull for MediaPipe C++ logs
import sys
import io

# Save original stderr
_original_stderr = sys.stderr

# Temporarily redirect stderr during MediaPipe imports
sys.stderr = io.StringIO()

try:
    import cv2
    import mediapipe as mp
finally:
    # Restore stderr
    sys.stderr = _original_stderr

print("MediaPipe and OpenCV loaded (logs suppressed).")
