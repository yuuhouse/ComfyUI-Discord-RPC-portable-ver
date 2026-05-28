"""Discord Rich Presence manager for ComfyUI.

Runs pypresence in a dedicated daemon thread with its own asyncio event loop
to avoid blocking the ComfyUI server.
"""

import atexit
import json
import logging
import os
import signal
import threading
import time

logger = logging.getLogger("discord_rpc")


class DiscordRPCManager:
    """Manages Discord Rich Presence connection and updates."""

    def __init__(self, client_id, config, user_dir=""):
        self.client_id = client_id
        self.config = config
        self.user_dir = user_dir
        self.connected = False
        self.should_run = True

        self._lock = threading.Lock()
        session_start_time = time.time()
        self._state = {
            "status": "idle",  # "idle" | "generating"
            "progress_value": 0,
            "progress_max": 0,
            "model_name": "",
            "prompt_id": "",
            "queue_remaining": 0,
            "current_node": "",
            "session_start_time": session_start_time,
            "idle_since": session_start_time,
            "generation_start_time": None,
        }

        self._thread = None
        self._presence = None
        self._update_event = threading.Event()

        # Check for stale lockfile from crashed previous instance
        self._cleanup_stale_lock()

        atexit.register(self._cleanup)

        # Register signal handlers for cleanup (Electron may kill process without atexit)
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, lambda *_: self._cleanup())
            except (OSError, ValueError):
                pass
        if hasattr(signal, "SIGBREAK"):  # Windows only
            try:
                signal.signal(signal.SIGBREAK, lambda *_: self._cleanup())
            except (OSError, ValueError):
                pass

    def start(self):
        """Start the RPC manager daemon thread."""
        if not self.config.get("enabled", True):
            logger.info("[Discord RPC] Disabled by configuration")
            return

        self._write_lock()

        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="DiscordRPCThread",
        )
        self._thread.start()
        logger.info("[Discord RPC] Background thread started")

    def stop(self):
        """Signal the thread to stop."""
        self.should_run = False
        self._update_event.set()

    def apply_config(self, new_config):
        """Apply runtime configuration changes."""
        self.config = new_config

        was_enabled = self.should_run
        is_enabled = new_config.get("enabled", True)

        if was_enabled and not is_enabled:
            # Disable: stop the thread
            self.stop()
            logger.info("[Discord RPC] Disabled via settings")
        elif not was_enabled and is_enabled:
            # Enable: restart
            self.should_run = True
            self.start()
            logger.info("[Discord RPC] Enabled via settings")

    # --- Thread-safe state update methods ---

    def set_idle(self):
        with self._lock:
            if self._state["status"] == "idle":
                return  # Already idle, skip
            self._state["status"] = "idle"
            self._state["progress_value"] = 0
            self._state["progress_max"] = 0
            self._state["generation_start_time"] = None
        self._update_event.set()

    def set_generating(self, prompt_id, model_name=""):
        with self._lock:
            self._state["status"] = "generating"
            self._state["prompt_id"] = prompt_id
            self._state["progress_value"] = 0
            self._state["progress_max"] = 0
            if model_name:
                self._state["model_name"] = model_name
            self._state["generation_start_time"] = time.time()
        self._update_event.set()

    def update_progress(self, value, max_value):
        with self._lock:
            self._state["progress_value"] = value
            self._state["progress_max"] = max_value
        # Don't wake loop for every tick - let it poll on interval

    def update_queue_size(self, remaining):
        with self._lock:
            self._state["queue_remaining"] = remaining

    def update_model_name(self, model_name):
        with self._lock:
            self._state["model_name"] = model_name

    def update_current_node(self, node_name):
        with self._lock:
            self._state["current_node"] = node_name

    # --- Internal thread methods ---

    def _run_loop(self):
        """Main loop in dedicated thread. Handles connection and reconnection."""
        # Set Windows event loop policy for pypresence IPC
        import asyncio

        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        reconnect_interval = self.config.get("reconnect_interval", 15)

        while self.should_run:
            try:
                self._connect()
                # Give Discord time to process the handshake before first update
                time.sleep(1)
                self._update_loop()
            except Exception as e:
                logger.warning(f"[Discord RPC] Connection error: {e}")
                self.connected = False
            finally:
                self._try_close()

            if not self.should_run:
                break

            logger.info(
                f"[Discord RPC] Reconnecting in {reconnect_interval}s..."
            )
            # Sleep in small increments so we can stop quickly
            for _ in range(reconnect_interval):
                if not self.should_run:
                    break
                time.sleep(1)

    def _connect(self):
        """Attempt to connect to Discord IPC."""
        from pypresence import Presence

        self._presence = Presence(self.client_id)
        self._presence.connect()
        # Clear any stale activity from previous session before sending new updates
        try:
            self._presence.clear()
        except Exception:
            pass
        self.connected = True
        logger.info("[Discord RPC] Connected to Discord")

    def _update_loop(self):
        """Rate-limited update loop."""
        iteration = 0
        while self.should_run and self.connected:
            try:
                self._send_update()
            except Exception as e:
                logger.warning(f"[Discord RPC] Update failed: {e}")
                self.connected = False
                break

            # Check if parent (Electron) is still alive every ~30s
            iteration += 1
            if iteration % 6 == 0 and self._is_orphan():
                logger.info("[Discord RPC] Parent process gone (orphaned), disconnecting")
                self.should_run = False
                break

            with self._lock:
                is_generating = self._state["status"] == "generating"

            idle_interval = self.config.get("idle_update_interval", 15)
            gen_interval = self.config.get("generating_update_interval", 5)
            interval = gen_interval if is_generating else idle_interval

            self._update_event.wait(timeout=interval)
            self._update_event.clear()

    def _send_update(self):
        """Send the current state to Discord."""
        if self._presence is None:
            return

        with self._lock:
            state = self._state.copy()

        # Read all config toggles
        show_model = self.config.get("show_model_name", True)
        show_queue = self.config.get("show_queue_info", True)
        show_node = self.config.get("show_node_name", False)
        show_steps = self.config.get("show_step_progress", True)
        show_time = self.config.get("show_elapsed_time", True)
        show_run_time = self.config.get("show_current_run_time", True)
        custom_idle = self.config.get("custom_idle_text", "")
        privacy = self.config.get("privacy_mode", False)

        if state["status"] == "idle":
            # Details line: model name or "ComfyUI"
            if privacy:
                details = "ComfyUI"
            elif show_model and state["model_name"]:
                details = state["model_name"]
            else:
                details = "ComfyUI"

            # State line: custom idle text or "Idle"
            idle_text = custom_idle if custom_idle else "Idle"

            kwargs = dict(
                large_image="comfyui_logo",
                large_text="ComfyUI",
                state=idle_text,
                details=details,
            )
            if show_time:
                kwargs["start"] = int(state["session_start_time"])

            self._presence.update(**kwargs)

        elif state["status"] == "generating":
            progress_pct = 0
            if state["progress_max"] > 0:
                progress_pct = int(
                    state["progress_value"] / state["progress_max"] * 100
                )

            # Build state string (bottom line)
            parts = []
            if show_steps and state["progress_max"] > 0:
                parts.append(
                    f"Step {int(state['progress_value'])}/{int(state['progress_max'])}"
                )

            if show_node and state["current_node"]:
                parts.append(state["current_node"])

            if show_queue and state["queue_remaining"] > 1:
                parts.append(f"Queue: {state['queue_remaining']}")

            if show_run_time and state["generation_start_time"]:
                elapsed = max(0, int(time.time() - state["generation_start_time"]))
                parts.append(f"Run {self._format_duration(elapsed)}")

            step_text = " | ".join(parts) if parts else "Generating..."

            # Details line (top line): model name
            if privacy:
                details = "Generating..."
            elif show_model and state["model_name"]:
                details = state["model_name"]
            else:
                details = "Generating..."

            start_time = state["session_start_time"]

            kwargs = dict(
                large_image="comfyui_generating",
                large_text="Generating",
                small_image=self._get_progress_image(progress_pct),
                small_text=f"{progress_pct}%",
                state=step_text,
                details=details,
            )
            if show_time:
                kwargs["start"] = int(start_time)

            self._presence.update(**kwargs)

    def _try_close(self):
        """Try to cleanly close the presence connection."""
        try:
            if self._presence is not None:
                self._presence.clear()
                self._presence.close()
        except Exception:
            pass
        self._presence = None
        self.connected = False

    def _cleanup(self):
        """Atexit cleanup handler."""
        self.should_run = False
        self._update_event.set()
        self._try_close()
        self._remove_lock()

    # --- Orphan detection & lockfile ---

    def _is_orphan(self):
        """Check if parent process (Electron) is still alive.

        On Windows, uses ctypes to check parent PID via OpenProcess.
        On Unix, checks if reparented to PID 1 (init).
        """
        try:
            if os.name != "nt":
                return os.getppid() == 1

            import ctypes
            kernel32 = ctypes.windll.kernel32
            ppid = os.getppid()
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, ppid
            )
            if handle:
                kernel32.CloseHandle(handle)
                return False  # Parent still alive
            return True  # Parent gone = orphan
        except Exception:
            return False  # If we can't check, assume not orphaned

    def _get_lock_path(self):
        """Get path to the PID lockfile."""
        if self.user_dir:
            return os.path.join(self.user_dir, "discord_rpc.lock")
        return ""

    def _write_lock(self):
        """Write current PID to lockfile."""
        lock_path = self._get_lock_path()
        if not lock_path:
            return
        try:
            with open(lock_path, "w") as f:
                json.dump({"pid": os.getpid(), "timestamp": time.time()}, f)
        except Exception as e:
            logger.debug(f"[Discord RPC] Failed to write lockfile: {e}")

    def _remove_lock(self):
        """Remove the PID lockfile."""
        lock_path = self._get_lock_path()
        if lock_path:
            try:
                os.remove(lock_path)
            except Exception:
                pass

    def _cleanup_stale_lock(self):
        """Check for stale lockfile from a crashed previous instance."""
        lock_path = self._get_lock_path()
        if not lock_path or not os.path.exists(lock_path):
            return
        try:
            with open(lock_path) as f:
                data = json.load(f)
            old_pid = data.get("pid")
            if old_pid and old_pid != os.getpid():
                if os.name == "nt":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x1000, False, old_pid)
                    if handle:
                        kernel32.CloseHandle(handle)
                        logger.warning(
                            f"[Discord RPC] Previous instance (PID {old_pid}) "
                            f"still running - likely a zombie process"
                        )
        except Exception:
            pass

    @staticmethod
    def _get_progress_image(percent):
        """Map percentage to nearest 5% progress asset key."""
        rounded = (percent // 5) * 5
        rounded = min(100, max(0, rounded))
        return f"progress_{rounded:03d}"

    @staticmethod
    def _format_duration(seconds):
        """Format elapsed seconds as H:MM:SS or M:SS."""
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
