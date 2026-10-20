"""
start.py — One-click launcher for the AI VTuber Companion (Chassie).

Performs startup checks, initializes all components, runs the main loop,
and handles graceful shutdown on Ctrl+C.
"""

import os
import sys

# Suppress TensorFlow and MediaPipe logs
os.environ["GLOG_minloglevel"] = "3"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["MEDIAPIPE_DISABLE_GPU"] = "1"
os.environ["GLOG_logtostderr"] = "0"
os.environ["GLOG_stderrthreshold"] = "3"
os.environ["GLOG_v"] = "0"

import asyncio
import logging
import signal
from pathlib import Path

import yaml

# Suppress TensorFlow warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="tensorflow")
warnings.filterwarnings("ignore", category=FutureWarning, module="tensorflow")

from orchestrator import Orchestrator


def setup_logging(config: dict):
    """Configure logging based on config.yaml settings."""
    log_cfg = config.get("logging", {})
    level_str = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    # Parse format from config
    fmt = log_cfg.get("format", "[{time}] [{level}] [{component}] {message}")
    # Convert to Python logging format
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    date_format = "%H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(log_format, datefmt=date_format)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Suppress verbose aiohttp access logs
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def load_config() -> dict:
    """Load config.yaml from the project directory."""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        print("[ERROR] config.yaml not found. Please create it in the project directory.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def check_python_version():
    """Ensure Python >= 3.10."""
    if sys.version_info < (3, 10):
        print(f"[ERROR] Python 3.10+ required. You have {sys.version}")
        sys.exit(1)


def check_dependencies():
    """Check that required packages are installed."""
    required = [
        ("yaml", "PyYAML"),
        ("numpy", "numpy"),
        ("sounddevice", "sounddevice"),
        ("webrtcvad", "webrtcvad"),
        ("aiohttp", "aiohttp"),
        ("websockets", "websockets"),
    ]

    missing = []
    for module_name, package_name in required:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print(f"[ERROR] Missing packages: {', '.join(missing)}")
        print(f"  Run: pip install {' '.join(missing)}")
        sys.exit(1)


async def check_hermes(config: dict) -> bool:
    """Check if Hermes gateway is reachable."""
    from hermes_bridge import HermesBridge
    bridge = HermesBridge(config)
    try:
        await bridge.connect()
        return await asyncio.wait_for(bridge.health_check(), timeout=5)
    except (OSError, asyncio.TimeoutError):
        return False
    finally:
        await bridge.close()


async def check_vts(config: dict) -> bool:
    """Check if VTube Studio API is reachable."""
    import websockets

    url = f"ws://{config['vts']['host']}:{config['vts']['port']}"
    try:
        ws = await asyncio.wait_for(websockets.connect(url), timeout=3.0)
        await ws.close()
        return True
    except Exception:
        return False


def check_webcam(config: dict) -> bool:
    """Check if webcam is available."""
    if not config["face_tracker"]["enabled"]:
        return True

    try:
        import cv2
        cap = cv2.VideoCapture(config["face_tracker"]["camera_index"])
        if cap.isOpened():
            cap.release()
            return True
        cap.release()
    except Exception:
        pass
    return False


async def run_startup_checks(config: dict):
    """Run all startup checks and report status."""
    print("=" * 50)
    print("  Chassie — AI VTuber Companion")
    print("=" * 50)
    print()

    # Python version
    check_python_version()
    print(f"  [OK] Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # Dependencies
    check_dependencies()
    print("  [OK] Required packages installed")

    # Hermes gateway
    hermes_ok = await check_hermes(config)
    if hermes_ok:
        print(f"  [OK] Hermes gateway reachable at {config['hermes']['gateway_url']}")
    else:
        print(f"  [FAIL] Hermes gateway unreachable at {config['hermes']['gateway_url']}")
        print("         Controls remain available. See docs/hermes-setup.md for API setup.")

    # VTube Studio
    vts_ok = await check_vts(config)
    if vts_ok:
        print(f"  [OK] VTube Studio API at ws://{config['vts']['host']}:{config['vts']['port']}")
    else:
        print(f"  [WARN] VTube Studio API not reachable. Standalone overlay can still be used.")

    # Webcam
    if config["face_tracker"]["enabled"]:
        print("  [--] Camera availability will be checked by the capture worker.")
    else:
        print("  [--] Face tracker disabled in config")

    print()
    print("-" * 50)
    print()


async def main():
    """Main entry point."""
    # Load config
    config = load_config()

    # Setup logging
    setup_logging(config)

    # Handle --debug flag
    if "--debug" in sys.argv:
        logging.getLogger().setLevel(logging.DEBUG)
        print("  [DEBUG] Debug logging enabled")

    # Handle --text flag
    text_mode = "--text" in sys.argv
    if "--no-camera" in sys.argv:
        config.setdefault('face_tracker', {})['enabled'] = False
        config.setdefault('vision', {})['camera_enabled'] = False
    if "--no-screen" in sys.argv:
        config.setdefault('vision', {})['screen_enabled'] = False

    # Run startup checks
    await run_startup_checks(config)

    # Create orchestrator
    orchestrator = Orchestrator(config, text_mode=text_mode)

    # Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        print("\n\nCtrl+C received. Shutting down...")
        shutdown_event.set()

    # Register signal handler
    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, signal_handler)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())

    # Run orchestrator with shutdown handling
    try:
        # Start orchestrator in a task
        orchestrator_task = asyncio.create_task(orchestrator.start())

        # Wait for either orchestrator to finish or shutdown signal
        done, pending = await asyncio.wait(
            [orchestrator_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for completed in done:
            if completed is orchestrator_task:
                completed.result()

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except KeyboardInterrupt:
        pass
    finally:
        # Graceful shutdown with timeout
        try:
            await asyncio.wait_for(orchestrator.stop(), timeout=10.0)
        except asyncio.TimeoutError:
            print("[WARNING] Shutdown timed out. Force exiting.")
        except Exception as e:
            print(f"[WARNING] Shutdown error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
