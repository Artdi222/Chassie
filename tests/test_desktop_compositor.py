import subprocess
from unittest.mock import Mock

import pytest

from desktop.compositor import configure_hyprland


def test_other_desktops_do_not_run_hyprctl():
    run=Mock()
    assert configure_hyprland(environ={},run=run) is False
    run.assert_not_called()


@pytest.mark.parametrize('result',[
    subprocess.CompletedProcess([],1,'','socket unavailable'),
    subprocess.CompletedProcess([],0,'Lua error: unknown effect',''),
])
def test_compositor_rejection_is_not_reported_as_success(result):
    with pytest.raises(RuntimeError,match='Hyprland'):
        configure_hyprland(environ={'HYPRLAND_INSTANCE_SIGNATURE':'test'},run=Mock(return_value=result))


def test_missing_or_unresponsive_ipc_is_actionable():
    for error in (FileNotFoundError(),subprocess.TimeoutExpired('hyprctl',3)):
        with pytest.raises(RuntimeError,match='Hyprland'):
            configure_hyprland(environ={'HYPRLAND_INSTANCE_SIGNATURE':'test'},run=Mock(side_effect=error))
