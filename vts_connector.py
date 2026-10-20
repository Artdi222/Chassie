"""VTS transport with explicit, acknowledged expression-file transitions.

The per-model manifest owns emotion/FX files only. Costume and unrelated manual
expressions stay untouched. Every transition refreshes live state, including after
reconnect, so toggles and cached hotkey names cannot invert the requested state.
"""
import asyncio
import json
import logging
import math
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed
from avatar import load_manifest
from avatar.manifest import DEFAULT_MANIFEST

logger = logging.getLogger("vts")
_TOKEN_FILE = "vts_token.json"


class VTSConnector:
    def __init__(self, config: dict):
        cfg = config["vts"]
        self._host = cfg["host"]
        self._port = cfg["port"]
        self._plugin_name = cfg["plugin_name"]
        self._plugin_developer = cfg["plugin_developer"]
        self._fade_time = max(0.0, min(2.0, float(cfg.get("expression_fade_time", 0.25))))
        self.manifest = load_manifest(cfg.get("expression_manifest", DEFAULT_MANIFEST))
        self._ws = None
        self._token = None
        self._authenticated = False
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._transition_lock = asyncio.Lock()
        self._inventory: dict[str, bool] = {}
        self._inventory_valid = False
        self.current_emotion: str | None = None
        self.last_error: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    async def start(self):
        """Controller-compatible startup alias."""
        await self.connect()

    async def connect(self):
        self._authenticated = False
        self._inventory_valid = False
        self.current_emotion = None
        if self._ws:
            await self._ws.close()
        self._ws = await websockets.connect(f"ws://{self._host}:{self._port}")
        self._load_token()
        await self.authenticate()
        if self._authenticated:
            await self.reconcile_expressions()

    async def authenticate(self):
        """Perform the VTS plugin authentication flow."""
        if self._token:
            # Try existing token
            resp = await self._send_request("AuthenticationRequest", {
                "pluginName": self._plugin_name,
                "pluginDeveloper": self._plugin_developer,
                "authenticationToken": self._token,
            })
            if resp and resp.get("data", {}).get("authenticated", False):
                self._authenticated = True
                logger.info("Authenticated with saved token.")
                return
            else:
                logger.info("Saved token invalid, requesting new one...")

        # Request new token (user must click "Allow" in VTS)
        resp = await self._send_request("AuthenticationTokenRequest", {
            "pluginName": self._plugin_name,
            "pluginDeveloper": self._plugin_developer,
            "pluginIcon": "",
        })

        if not resp or "data" not in resp:
            logger.error("Failed to request auth token from VTS.")
            return

        self._token = resp["data"].get("authenticationToken")
        if not self._token:
            logger.error("No token received from VTS.")
            return

        self._save_token()
        logger.info("Received new auth token. Please click 'Allow' in VTube Studio...")

        # Now authenticate with the new token
        resp = await self._send_request("AuthenticationRequest", {
            "pluginName": self._plugin_name,
            "pluginDeveloper": self._plugin_developer,
            "authenticationToken": self._token,
        })

        if resp and resp.get("data", {}).get("authenticated", False):
            self._authenticated = True
            logger.info("Authentication successful.")
        else:
            logger.error("Authentication failed. Did you click 'Allow' in VTube Studio?")

    def _error(self, message: str) -> bool:
        self.last_error = message
        logger.warning("%s", message)
        return False

    @staticmethod
    def _ack(response: dict | None, message_type: str) -> bool:
        return bool(response and response.get("messageType") == message_type
                    and isinstance(response.get("data"), dict))

    async def _refresh_inventory(self) -> bool:
        self._inventory_valid = False
        if not self._authenticated:
            return self._error("VTS is not authenticated; expressions are unavailable")
        response = await self._send_request("ExpressionStateRequest", {"details": False})
        if not self._ack(response, "ExpressionStateResponse"):
            return self._error("VTS expression inventory unavailable; reconnect and retry")
        data = response["data"]
        if not data.get("modelLoaded") or data.get("modelID") != self.manifest.model_id:
            self._inventory = {}
            self.current_emotion = None
            return self._error(f"Load the configured avatar model ({self.manifest.model_id}) in VTS")
        entries = data.get("expressions")
        if not isinstance(entries, list) or any(
                not isinstance(e, dict) or not isinstance(e.get("file"), str)
                or not isinstance(e.get("active"), bool) for e in entries):
            return self._error("VTS returned a malformed expression inventory")
        self._inventory = {entry["file"]: entry["active"] for entry in entries}
        if len(self._inventory) != len(entries):
            return self._error("VTS returned duplicate expression filenames; resolve the model assets")
        self._inventory_valid = True
        return True

    async def query_hotkeys(self):
        """Compatibility alias; now queries expression files, never fuzzy hotkeys."""
        async with self._transition_lock:
            return await self._refresh_inventory()

    def get_capabilities(self) -> dict:
        """Cached diagnostics for UI; no network calls and no visual-approval claim."""
        return {
            "backend": "vts", "authenticated": self._authenticated,
            "model_id": self.manifest.model_id,
            "inventory_available": self._inventory_valid and self._authenticated,
            "current_emotion": self.current_emotion, "error": self.last_error,
            "emotions": {
                emotion: {
                    "files": list(mapping.files), "preview_required": mapping.preview_required,
                    "note": mapping.note,
                    "available": self._inventory_valid and self._authenticated
                        and all(f in self._inventory for f in mapping.files),
                    "missing_files": [f for f in mapping.files if f not in self._inventory]
                        if self._inventory_valid else [],
                } for emotion, mapping in self.manifest.emotions.items()
            },
        }

    async def trigger_emotion(self, emotion: str) -> bool:
        mapping = self.manifest.emotions.get(emotion)
        if mapping is None:
            return self._error(f"Unknown avatar emotion: {emotion}")
        async with self._transition_lock:
            self.current_emotion = None
            if not await self._refresh_inventory():
                return False
            missing = [f for f in mapping.files if f not in self._inventory]
            if missing:
                return self._error("Missing VTS expression files: " + ", ".join(missing))
            wanted = set(mapping.files)
            # Only this manifest's expression and FX files belong to the controller.
            # Refreshing catches manual changes and expressions left after a crash.
            changes = [(f, False) for f in sorted(self.manifest.managed_files)
                       if self._inventory.get(f) and f not in wanted]
            changes += [(f, True) for f in mapping.files if not self._inventory[f]]
            for filename, active in changes:
                response = await self._send_request("ExpressionActivationRequest", {
                    "expressionFile": filename, "fadeTime": self._fade_time, "active": active,
                })
                if not self._ack(response, "ExpressionActivationResponse"):
                    self._inventory_valid = False
                    return self._error(f"VTS did not acknowledge expression {filename}; retry to reconcile")
                self._inventory[filename] = active
            self.current_emotion = emotion
            self.last_error = None
            return True

    async def preview_emotion(self, emotion: str) -> bool:
        """Apply the named candidate; explicit reset remains available to the UI."""
        return await self.trigger_emotion(emotion)

    async def reconcile_expressions(self) -> bool:
        """Reconnect starts neutral, clearing only this model's managed emotion/FX."""
        return await self.trigger_emotion("neutral")

    async def reset_expressions(self) -> bool:
        return await self.trigger_emotion("neutral")

    async def reset(self) -> bool:
        result = await self.reset_expressions()
        await self.set_mouth_open(0.0)
        return result

    async def set_mouth_open(self, value: float):
        if not math.isfinite(value):
            return False
        return await self.set_parameter("MouthOpen", max(0.0, min(1.0, value)))

    async def set_parameter(self, param: str, value: float):
        if not self._authenticated or not math.isfinite(value):
            return False
        response = await self._send_request("InjectParameterDataRequest", {
            "parameterValues": [{"id": param, "value": float(value)}],
        })
        return self._ack(response, "InjectParameterDataResponse")

    async def disconnect(self):
        try:
            if self._authenticated:
                await self.reset()
        finally:
            if self._ws:
                await self._ws.close()
            self._ws = None
            self._authenticated = False
            self._inventory_valid = False
            self.current_emotion = None

    async def _send_request(self, message_type: str, data: dict) -> dict | None:
        async with self._lock:
            if not self._ws:
                return None
            self._request_id += 1
            request_id = str(self._request_id)
            request = {
                "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
                "requestID": request_id, "messageType": message_type, "data": data,
            }
            try:
                async with asyncio.timeout(5.0):
                    await self._ws.send(json.dumps(request))
                    while True:
                        response = json.loads(await self._ws.recv())
                        if not isinstance(response, dict) or response.get("requestID") != request_id:
                            continue  # Unsolicited events never acknowledge our mutation.
                        if response.get("messageType") == "APIError":
                            self._error(f"VTS rejected {message_type} (error {response.get('data', {}).get('errorID')})")
                            return None
                        if response.get("messageType") != message_type.removesuffix("Request") + "Response":
                            self._error(f"VTS returned an unexpected response to {message_type}")
                            return None
                        return response
            except asyncio.CancelledError:
                # A canceled request has uncertain server-side state. Reconnect/query
                # before the next transition rather than accepting a late response.
                await self._invalidate_connection()
                raise
            except (TimeoutError, ConnectionClosed, ValueError, OSError) as exc:
                self._error(f"VTS transport failed during {message_type}: {type(exc).__name__}")
                await self._invalidate_connection()
                return None

    async def _invalidate_connection(self):
        ws, self._ws = self._ws, None
        self._authenticated = False
        self._inventory_valid = False
        self.current_emotion = None
        if ws:
            try:
                await ws.close()
            except Exception:
                pass

    def _load_token(self):
        """Load saved auth token from file."""
        token_path = Path(_TOKEN_FILE)
        if token_path.exists():
            try:
                data = json.loads(token_path.read_text())
                self._token = data.get("token")
            except Exception:
                self._token = None

    def _save_token(self):
        """Save auth token to file."""
        if self._token:
            try:
                Path(_TOKEN_FILE).write_text(json.dumps({"token": self._token}))
            except Exception as e:
                logger.warning("Could not save VTS token: %s", e)
