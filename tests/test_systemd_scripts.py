import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "fleet" / "bin"


def test_modified_service_scripts_parse_as_bash():
    scripts = [BIN / "apply-config-systemd.sh", BIN / "board-medic.sh",
               BIN / "hub-tunnel.sh"]
    result = subprocess.run(["bash", "-n", *map(str, scripts)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_every_sitting_timer_has_a_generated_unit():
    text = (BIN / "apply-config-systemd.sh").read_text()
    sitting = re.search(r'^SITTING="([^"]+)"', text, re.M)
    assert sitting
    generated = set(re.findall(r"^\s*unit\s+([\w-]+)\s", text, re.M))
    assert set(sitting.group(1).split()) <= generated


def test_board_medic_selects_init_system_not_service_health():
    text = (BIN / "board-medic.sh").read_text()
    assert "command -v systemctl" in text
    assert "systemctl --user status ccd-board.service" not in text
    assert "systemctl --user restart ccd-board.service" in text
    assert "launchctl kickstart" in text


def test_legacy_tunnel_script_cannot_retarget_the_hub_by_default():
    text = (BIN / "hub-tunnel.sh").read_text()
    assert 'HOST="nuc.planetarycouncil.org"' in text
    assert 'HOST="hub.planetarycouncil.org"' not in text
    assert '"${1:-}" != "--apply"' in text
    assert "DNS unchanged" in text
