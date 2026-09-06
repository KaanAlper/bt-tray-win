"""Menu ve durum mantigi testleri.

pystray action'lari en fazla 2 argumanli olabilir (MenuItem._assert_action);
daha fazlasi ValueError firlatir ve uygulama aciliste cokerdi. Bu testler
menunun tamamini kurar, her ogenin text/checked/visible/enabled property'sini
okur ve her action'i tetikler.

Windows'a ozgu cagrilar (PowerShell/PnP) stub'lanir, bu yuzden Linux CI
uzerinde de calisir.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("PYSTRAY_BACKEND", "dummy")

import bt_tray  # noqa: E402


FAKE_DEVICES = [
    {
        "DeviceID": r"BTHENUM\{0000111e-0000-1000-8000-00805f9b34fb}_LOCALMFG&000f\7&x&0",
        "Name": "WH-1000XM4 Hands-Free AG Audio",
        "ConfigManagerErrorCode": 22,
    }
]


@pytest.fixture
def tray(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(bt_tray, "find_hfp_devices", lambda: list(FAKE_DEVICES))
    monkeypatch.setattr(bt_tray, "set_devices_enabled", lambda devices, enabled: None)
    monkeypatch.setattr(bt_tray, "run_ps", lambda *a, **k: "")
    tray = bt_tray.BTTray()
    # Dummy backend native menu/ikon guncellemesini implemente etmiyor.
    monkeypatch.setattr(tray.icon, "update_menu", lambda: None)
    return tray


def walk(menu):
    """Menudeki tum ogeleri (alt menuler dahil) sirayla dondurur."""
    for item in menu:
        yield item
        if item.submenu is not None:
            yield from walk(item.submenu)


def test_menu_builds_and_every_item_is_readable(tray):
    """Her MenuItem kurulabilmeli ve property'leri hatasiz okunabilmeli."""
    items = list(walk(tray.icon.menu))
    assert len(items) >= 8

    for item in items:
        assert isinstance(item.text, str) and item.text
        assert item.checked in (True, False, None)
        assert isinstance(item.visible, bool)
        assert isinstance(item.enabled, bool)


def test_every_action_is_invocable(tray):
    """Regresyon: 3 argumanli lambda pystray'de ValueError firlatiyordu.

    Her action'i pystray'in kendi cagri bicimiyle (_action(icon, item))
    tetikliyoruz.
    """
    for item in walk(tray.icon.menu):
        if item.submenu is not None:
            continue
        item(tray.icon)  # MenuItem.__call__ -> self._action(icon, self)


def test_default_mode_menu_binds_correct_mode(tray):
    """Alt menudeki her oge kendi modunu yazmali (closure late-binding tuzagi)."""
    submenu = next(i.submenu for i in tray.icon.menu if i.submenu is not None)
    label_to_mode = {v: k for k, v in bt_tray.MODE_LABELS.items()}

    for item in submenu:
        item(tray.icon)
        assert tray.config["default_mode"] == label_to_mode[item.text]
        assert item.checked is True


def test_default_mode_persists_to_disk(tray, tmp_path):
    tray.set_default_mode(bt_tray.MODE_MIC)
    assert bt_tray.load_config()["default_mode"] == bt_tray.MODE_MIC


def test_categorize_states():
    assert bt_tray.categorize([]) == bt_tray.MODE_NONE
    assert bt_tray.categorize([{"ConfigManagerErrorCode": 22}]) == bt_tray.MODE_MUSIC
    assert bt_tray.categorize([{"ConfigManagerErrorCode": 0}]) == bt_tray.MODE_MIC
    assert bt_tray.categorize([{"ConfigManagerErrorCode": 45}]) == bt_tray.MODE_MIC
    # Karisik durum: biri bile acik ise mikrofon modundayiz.
    assert bt_tray.categorize(
        [{"ConfigManagerErrorCode": 22}, {"ConfigManagerErrorCode": 0}]
    ) == bt_tray.MODE_MIC


def test_icons_render_for_all_states():
    for state in (bt_tray.MODE_MUSIC, bt_tray.MODE_MIC, bt_tray.MODE_NONE):
        image = bt_tray.make_icon(state)
        assert image.size == (bt_tray.ICON_SIZE, bt_tray.ICON_SIZE)
        assert image.mode == "RGBA"
        assert image.getbbox() is not None  # bos ikon degil


def test_title_strips_hands_free_suffix(tray):
    tray.devices = list(FAKE_DEVICES)
    tray.state = bt_tray.MODE_MUSIC
    assert tray._title() == "WH-1000XM4 - " + bt_tray.MODE_LABELS[bt_tray.MODE_MUSIC]

    tray.state = bt_tray.MODE_NONE
    assert "bulunamadi" in tray._title().lower() or "yok" in tray._title().lower()


def test_toggle_flips_between_modes(tray, monkeypatch):
    applied = []
    monkeypatch.setattr(tray, "apply_mode", applied.append)

    tray.state = bt_tray.MODE_MUSIC
    tray.on_toggle()
    tray.state = bt_tray.MODE_MIC
    tray.on_toggle()
    tray.state = bt_tray.MODE_NONE
    tray.on_toggle()

    assert applied == [bt_tray.MODE_MIC, bt_tray.MODE_MUSIC, bt_tray.MODE_MUSIC]


def test_apply_mode_calls_pnp_with_right_flag(tray, monkeypatch):
    calls = []
    monkeypatch.setattr(bt_tray, "set_devices_enabled",
                        lambda devices, enabled: calls.append(enabled))
    monkeypatch.setattr(tray, "refresh", lambda force=False: None)
    monkeypatch.setattr(bt_tray.time, "sleep", lambda _s: None)

    tray._apply_mode_worker(bt_tray.MODE_MUSIC)
    tray._apply_mode_worker(bt_tray.MODE_MIC)

    assert calls == [False, True]


def test_find_devices_parses_single_object(monkeypatch):
    """ConvertTo-Json tek kayitta dizi degil nesne dondurur."""
    monkeypatch.setattr(bt_tray, "run_ps", lambda *a, **k:
                        '{"DeviceID":"BTHENUM\\\\x","Name":"A","ConfigManagerErrorCode":22}')
    assert bt_tray.find_hfp_devices() == [
        {"DeviceID": "BTHENUM\\x", "Name": "A", "ConfigManagerErrorCode": 22}
    ]


def test_find_devices_survives_garbage(monkeypatch):
    for junk in ("", "   ", "not json", "null", "[]"):
        monkeypatch.setattr(bt_tray, "run_ps", lambda *a, _j=junk, **k: _j)
        assert bt_tray.find_hfp_devices() == []


def test_set_devices_enabled_builds_correct_powershell(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    scripts = []
    monkeypatch.setattr(bt_tray, "run_ps",
                        lambda script, **k: scripts.append(script) or "")

    bt_tray.set_devices_enabled(FAKE_DEVICES, enabled=False)
    bt_tray.set_devices_enabled(FAKE_DEVICES, enabled=True)

    assert "Disable-PnpDevice" in scripts[0] and "Enable-PnpDevice" not in scripts[0]
    assert "Enable-PnpDevice" in scripts[1] and "Disable-PnpDevice" not in scripts[1]
    assert FAKE_DEVICES[0]["DeviceID"] in scripts[0]
    # Tek aygitin hatasi digerlerini durdurmamali.
    assert "try {" in scripts[0] and "catch {" in scripts[0]


def test_set_devices_enabled_logs_powershell_error(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(bt_tray, "run_ps", lambda *a, **k: "Access is denied.")

    error = bt_tray.set_devices_enabled(FAKE_DEVICES, enabled=False)

    assert error == "Access is denied."
    assert "Access is denied." in open(bt_tray.log_path(), encoding="utf-8").read()


def test_apply_mode_notifies_on_failure(tray, monkeypatch):
    monkeypatch.setattr(bt_tray, "set_devices_enabled",
                        lambda devices, enabled: "Access is denied.")
    monkeypatch.setattr(tray, "refresh", lambda force=False: None)
    monkeypatch.setattr(bt_tray.time, "sleep", lambda _s: None)
    notes = []
    monkeypatch.setattr(tray, "_notify", lambda t, m: notes.append(t))

    tray._apply_mode_worker(bt_tray.MODE_MUSIC)

    assert notes == ["Profil degistirilemedi"]


def test_poll_loop_survives_a_failing_refresh(tray, monkeypatch, tmp_path):
    """Poll thread'i olurse tray gri kalir ve --noconsole'da sessiz cokerdi."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(tray, "refresh", lambda force=False: (_ for _ in ()).throw(
        RuntimeError("wmi patladi")))
    monkeypatch.setattr(tray, "apply_default_mode", lambda: None)
    tray.stop_event.set()  # dongu govdesine girmeden ciksin

    tray._poll_loop()  # exception disari sizmamali

    assert "wmi patladi" in open(bt_tray.log_path(), encoding="utf-8").read()


# --------------------------------------------------------------------------
# Windows'a ozgu yollar (kod inceleme bulgulari icin regresyon testleri)
# --------------------------------------------------------------------------

def test_run_ps_forces_utf8_on_both_sides(monkeypatch):
    """tr-TR'de OEM (cp857) ve ANSI (cp1254) codepage'leri farkli; ikisi de
    UTF-8'e sabitlenmezse kulaklik adi mojibake olur ya da decode patlar."""
    captured = {}

    class FakeResult:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeResult()

    monkeypatch.setattr(bt_tray.subprocess, "run", fake_run)
    bt_tray.run_ps("Write-Output 'x'")

    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["errors"] == "replace"
    assert "text" not in captured["kwargs"]  # locale'e gore decode etmesin

    import base64
    script = base64.b64decode(captured["cmd"][-1]).decode("utf-16-le")
    assert "[Console]::OutputEncoding" in script
    assert script.startswith("try {")  # CLM'de patlamasin diye sarili


def test_run_ps_logs_subprocess_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(bt_tray.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("powershell yok")))

    assert bt_tray.run_ps("x") == ""
    assert "powershell yok" in open(bt_tray.log_path(), encoding="utf-8").read()


def test_find_devices_logs_unparseable_output(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(bt_tray, "run_ps", lambda *a, **k: "Get-CimInstance : hata")

    assert bt_tray.find_hfp_devices() == []
    log = open(bt_tray.log_path(), encoding="utf-8").read()
    assert "Get-CimInstance" in log  # ham cikti log'a girmeli


def test_refresh_never_touches_menu_from_background(tray, monkeypatch):
    """pystray win32 _update_menu() HMENU'yu DestroyMenu ediyor; mesaj dongusu
    ayni anda TrackPopupMenuEx ile onu gosteriyor olabilir."""
    monkeypatch.setattr(tray.icon, "update_menu",
                        lambda: pytest.fail("refresh() arka plandan menuye dokunmamali"))
    tray.refresh(force=True)


def test_apply_default_mode_silent_when_no_headset(tray, monkeypatch):
    """Acilista kulaklik bagli degilse her boot'ta 'bulunamadi' balonu cikmasin."""
    applied = []
    monkeypatch.setattr(tray, "_apply_mode_worker", applied.append)

    tray.state = bt_tray.MODE_NONE
    tray.config["default_mode"] = bt_tray.MODE_MUSIC
    tray.apply_default_mode()
    assert applied == []

    tray.state = bt_tray.MODE_MIC
    tray.apply_default_mode()
    assert applied == [bt_tray.MODE_MUSIC]


def test_relaunch_as_admin_reports_uac_refusal(monkeypatch, tmp_path):
    """ShellExecuteW <=32 donerse (UAC 'Hayir') uygulama sessizce kapanmamali."""
    monkeypatch.setenv("APPDATA", str(tmp_path))

    class FakeShell32:
        def __init__(self, rc):
            self.rc = rc

        def ShellExecuteW(self, *args):
            return self.rc

    class FakeWindll:
        def __init__(self, rc):
            self.shell32 = FakeShell32(rc)

    monkeypatch.setattr(bt_tray.ctypes, "windll", FakeWindll(5), raising=False)
    assert bt_tray.relaunch_as_admin() is False
    assert "rc=5" in open(bt_tray.log_path(), encoding="utf-8").read()

    monkeypatch.setattr(bt_tray.ctypes, "windll", FakeWindll(42), raising=False)
    assert bt_tray.relaunch_as_admin() is True


def test_name_fallback_is_limited_to_bluetooth_devices():
    """'Hands-Free' gecen alakasiz bir aygit HFP sanilmamali."""
    assert "BTHENUM*" in bt_tray.PS_FIND
    fallback = bt_tray.PS_FIND.split("if (-not $hf)")[1]
    assert "$_.DeviceID -like 'BTHENUM*' -and" in fallback
