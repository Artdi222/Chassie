import asyncio
import json
from pathlib import Path

from avatar import load_manifest, audit_assets
from emotion_parser import VALID_EMOTIONS
from vts_connector import VTSConnector

CONFIG = {"vts": {"host": "localhost", "port": 8001, "plugin_name": "test", "plugin_developer": "test", "expression_reset_delay": 0}}

class FakeVTS(VTSConnector):
    def __init__(self):
        super().__init__(CONFIG)
        self._authenticated = True
        self.state = {name: False for name in self.manifest.managed_files}
        self.state["costume_v0000.exp3.json"] = True
        self.calls = []
        self.fail_file = None
        self.loaded_model = self.manifest.model_id
        self.inventory_available = True

    async def _send_request(self, kind, data):
        self.calls.append((kind, data.copy()))
        await asyncio.sleep(0)
        if kind == "ExpressionStateRequest":
            if not self.inventory_available:
                return None
            return {"messageType": "ExpressionStateResponse", "data": {
                "modelLoaded": True, "modelID": self.loaded_model,
                "expressions": [{"file": name, "active": active} for name, active in self.state.items()]}}
        if kind == "ExpressionActivationRequest":
            if data["expressionFile"] == self.fail_file:
                return {"messageType": "APIError", "data": {"errorID": 1, "message": "no"}}
            self.state[data["expressionFile"]] = data["active"]
            return {"messageType": "ExpressionActivationResponse", "data": {}}
        return {"messageType": kind.replace("Request", "Response"), "data": {}}

    @property
    def mutations(self):
        return [data for kind, data in self.calls if kind == "ExpressionActivationRequest"]


def run(coro):
    return asyncio.run(coro)


def test_vts_manifest_maps_every_emotion():
    manifest = load_manifest()
    assert set(manifest.emotions) == VALID_EMOTIONS
    assert manifest.emotions["angry"].preview_required


def test_repeated_emotion_is_idempotent_and_neutral_preserves_outfit():
    async def scenario():
        vts = FakeVTS()
        assert await vts.trigger_emotion("happy")
        assert len(vts.mutations) == 2
        assert await vts.trigger_emotion("happy")
        assert len(vts.mutations) == 2
        assert await vts.reset_expressions()
        assert vts.state["costume_v0000.exp3.json"]
        assert not any(vts.state[f] for f in vts.manifest.managed_files)
    run(scenario())


def test_unknown_or_missing_mapping_does_not_mutate():
    async def scenario():
        vts = FakeVTS()
        assert not await vts.trigger_emotion("missing")
        del vts.state["smile.exp3.json"]
        assert not await vts.trigger_emotion("happy")
        assert not vts.mutations
        assert "smile.exp3.json" in vts.last_error
    run(scenario())


def test_reconcile_manual_change_and_reconnect_state():
    async def scenario():
        vts = FakeVTS()
        await vts.trigger_emotion("happy")
        vts.state["cry.exp3.json"] = True
        vts.state["smile.exp3.json"] = False
        assert await vts.trigger_emotion("happy")
        assert not vts.state["cry.exp3.json"]
        assert vts.state["smile.exp3.json"]
        fresh = FakeVTS()
        fresh.state.update(vts.state)
        assert await fresh.reconcile_expressions()
        assert not any(fresh.state[f] for f in fresh.manifest.managed_files)
        assert fresh.state["costume_v0000.exp3.json"]
    run(scenario())


def test_failed_activation_is_not_reported_as_success_and_retry_recovers():
    async def scenario():
        vts = FakeVTS()
        vts.fail_file = "smile.exp3.json"
        assert not await vts.trigger_emotion("happy")
        assert vts.current_emotion is None
        assert not vts.state["smile.exp3.json"]
        vts.fail_file = None
        assert await vts.trigger_emotion("happy")
        assert vts.current_emotion == "happy"
    run(scenario())


def test_transitions_serialized():
    async def scenario():
        vts = FakeVTS()
        results = await asyncio.gather(vts.trigger_emotion("happy"), vts.trigger_emotion("sad"))
        assert results == [True, True]
        assert {f for f, active in vts.state.items() if active} == {
            "costume_v0000.exp3.json", "cry.exp3.json", "fx_2_pale2.exp3.json"}
    run(scenario())


def test_wrong_model_and_unavailable_inventory_do_not_mutate():
    async def scenario():
        vts = FakeVTS()
        vts.loaded_model = "different-model"
        assert not await vts.trigger_emotion("happy")
        assert not vts.mutations
        vts.loaded_model = vts.manifest.model_id
        vts.inventory_available = False
        assert not await vts.trigger_emotion("happy")
        assert not vts.mutations
    run(scenario())


def test_deactivation_error_leaves_current_emotion_unknown_and_can_retry():
    async def scenario():
        vts = FakeVTS()
        await vts.trigger_emotion("happy")
        vts.fail_file = "smile.exp3.json"
        assert not await vts.trigger_emotion("sad")
        assert vts.current_emotion is None
        assert not vts.state["cry.exp3.json"]
        assert not vts.get_capabilities()["inventory_available"]
        vts.fail_file = None
        assert await vts.trigger_emotion("sad")
        assert not vts.state["smile.exp3.json"]
    run(scenario())


def test_audit_missing_asset_is_actionable(tmp_path):
    report = audit_assets(load_manifest(), tmp_path)
    assert any("smile.exp3.json" in error for error in report["errors"])


def test_manifest_rejects_outfit_in_emotion_mapping(tmp_path):
    import pytest
    data = json.loads(Path("avatar/ulvm2_0001.json").read_text())
    data["emotions"]["happy"]["expression"] = "costume_v0000.exp3.json"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="never an outfit"):
        load_manifest(path)


class Socket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.closed = False

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return json.dumps(item)

    async def close(self):
        self.closed = True


def test_transport_ignores_unrelated_event_and_checks_response_type():
    async def scenario():
        vts = VTSConnector(CONFIG)
        socket = Socket([
            {"requestID": "event", "messageType": "ModelLoadedEvent", "data": {}},
            {"requestID": "1", "messageType": "ExpressionActivationResponse", "data": {}},
            {"requestID": "2", "messageType": "HotkeyTriggerResponse", "data": {}},
        ])
        vts._ws = socket
        assert await vts._send_request("ExpressionActivationRequest", {})
        assert await vts._send_request("ExpressionActivationRequest", {}) is None
    run(scenario())


def test_transport_api_error_is_not_success():
    async def scenario():
        vts = VTSConnector(CONFIG)
        vts._ws = Socket([{"requestID": "1", "messageType": "APIError", "data": {"errorID": 42}}])
        assert await vts._send_request("ExpressionActivationRequest", {}) is None
        assert "42" in vts.last_error
    run(scenario())


def test_timeout_invalidates_connection_and_state():
    async def scenario():
        vts = VTSConnector(CONFIG)
        vts._authenticated = True
        vts.current_emotion = "happy"
        socket = Socket([TimeoutError()])
        vts._ws = socket
        assert await vts._send_request("ExpressionStateRequest", {}) is None
        assert socket.closed
        assert not vts.is_authenticated
        assert vts.current_emotion is None
    run(scenario())


def test_cancellation_invalidates_connection_without_claiming_success():
    async def scenario():
        import pytest
        vts = VTSConnector(CONFIG)
        vts._authenticated = True
        socket = Socket([asyncio.CancelledError()])
        vts._ws = socket
        with pytest.raises(asyncio.CancelledError):
            await vts._send_request("ExpressionActivationRequest", {})
        assert socket.closed
        assert not vts.is_authenticated
    run(scenario())
