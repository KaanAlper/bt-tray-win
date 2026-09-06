#!/usr/bin/env python3
"""
bt-tray-win — Bluetooth kulaklik profil degistirici (Windows tray).

Sorun:
    Bluetooth kulaklik ayni anda tek profil calistirir.
      A2DP (Stereo)     -> 44.1 kHz stereo cikis, mikrofon YOK
      HFP  (Hands-Free) -> 8-16 kHz mono, mikrofon VAR
    OBS / Discord / Teams kulakligin mikrofonunu actigi anda Windows
    kulakligi zorla Hands-Free profiline dusurur ve ses "telsiz" olur.

Cozum:
    Bu tray, Hands-Free AG Audio PnP aygitini enable/disable ederek
    Windows'un profil degistirmesini engeller.
      Muzik Modu     -> HFP aygiti disabled  -> kulaklik A2DP'de kilitli
      Mikrofon Modu  -> HFP aygiti enabled   -> mikrofon calisir

Kullanim:
    Sol tik   : iki mod arasinda gecis
    Sag tik   : menu (mod secimi, varsayilan mod, yenile, cikis)

Yonetici yetkisi gerekir (PnP aygit enable/disable icin).
"""

from __future__ import annotations

import base64
import ctypes
import datetime
import json
import os
import subprocess
import sys
import threading
import time
import traceback

from PIL import Image, ImageDraw, ImageFont
import pystray

APP_NAME = "bt-tray-win"
POLL_SECONDS = 3
ICON_SIZE = 64
CREATE_NO_WINDOW = 0x08000000

COLOR_MUSIC = (33, 150, 243)   # mavi  - A2DP
COLOR_MIC = (244, 67, 54)      # kirmizi - HFP
COLOR_NONE = (120, 120, 120)   # gri   - aygit yok

MODE_MUSIC = "music"
MODE_MIC = "mic"
MODE_NONE = "none"
MODE_ASK = "ask"  # varsayilan mod: hicbir sey yapma

MODE_LABELS = {
    MODE_MUSIC: "Muzik Modu (A2DP)",
    MODE_MIC: "Mikrofon Modu (HFP)",
    MODE_ASK: "Dokunma (mevcut halini koru)",
}


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def log_path() -> str:
    return os.path.join(data_dir(), "error.log")


def log_error(context: str, exc: BaseException) -> None:
    """--noconsole ile derlenen exe'de traceback ekrana dusmez; diske yazar."""
    try:
        os.makedirs(data_dir(), exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {stamp} | {context} =====\n")
            fh.write("".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__)))
    except Exception:
        pass


def load_config() -> dict:
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"default_mode": MODE_MUSIC}


def save_config(cfg: dict) -> None:
    path = config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception as exc:
        log_error("save_config", exc)


# --------------------------------------------------------------------------
# PowerShell koprusu
# --------------------------------------------------------------------------

# CREATE_NO_WINDOW ile acilan gizli konsol OEM codepage kullanir (tr-TR'de
# cp857), Python ise text=True ile ANSI codepage'e (cp1254) gore decode eder.
# Kulaklik adinda Latin-disi karakter varsa bu uyusmazlik UnicodeDecodeError
# ya da mojibake uretir. Iki tarafi da UTF-8'e sabitliyoruz; Constrained
# Language Mode'da [Console] erisimi engellenebildigi icin try/catch sarili.
PS_PRELUDE = (
    "try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }\n"
)


def run_ps(script: str, timeout: int = 30) -> str:
    """PowerShell'i -EncodedCommand ile calistirir (tirnak cehennemi yok)."""
    encoded = base64.b64encode((PS_PRELUDE + script).encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded,
            ],
            capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            encoding="utf-8", errors="replace",
        )
    except Exception as exc:
        log_error("run_ps", exc)
        return ""
    if result.returncode != 0 and result.stderr:
        log_error("run_ps stderr", RuntimeError(result.stderr.strip()[:2000]))
    return result.stdout or ""


PS_FIND = r"""
$ErrorActionPreference = 'SilentlyContinue'
$all = Get-CimInstance Win32_PnPEntity
$hf = $all | Where-Object {
    $_.DeviceID -like 'BTHENUM\{0000111e*' -or
    $_.DeviceID -like 'BTHENUM\{00001108*'
}
if (-not $hf) {
    # UUID eslesmesi bosa duserse isimden ariyoruz, ama yine sadece Bluetooth
    # aygitlari icinde: aksi halde 'Hands-Free' gecen alakasiz bir aygit
    # (arac kiti vb.) HFP sanilabilir.
    $hf = $all | Where-Object {
        $_.DeviceID -like 'BTHENUM*' -and
        ($_.Name -like '*Hands-Free*' -or $_.Name -like '*Hands Free*')
    }
}
$hf | Select-Object DeviceID, Name, ConfigManagerErrorCode | ConvertTo-Json -Compress
"""


def find_hfp_devices() -> list[dict]:
    """Hands-Free profil aygitlarini dondurur.

    ConfigManagerErrorCode: 0 = calisiyor, 22 = disabled, 45 = bagli degil.
    """
    raw = run_ps(PS_FIND).strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception as exc:
        log_error(f"find_hfp_devices JSON parse: {raw[:500]!r}", exc)
        return []
    # ConvertTo-Json tek kayitta nesne, hic kayit yoksa `null` dondurur.
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        return []
    return [d for d in data if isinstance(d, dict) and d.get("DeviceID")]


def set_devices_enabled(devices: list[dict], enabled: bool) -> str:
    """Aygitlari enable/disable eder, PowerShell hata metnini dondurur ('' = temiz)."""
    if not devices:
        return ""
    verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
    lines = ["$ErrorActionPreference = 'Stop'", "$errs = @()"]
    for dev in devices:
        device_id = str(dev["DeviceID"]).replace("'", "''")
        lines.append(
            f"try {{ {verb} -InstanceId '{device_id}' -Confirm:$false }} "
            f"catch {{ $errs += $_.Exception.Message }}"
        )
    lines.append("$errs -join ' | '")
    out = run_ps("\n".join(lines), timeout=60).strip()
    if out:
        log_error(f"{verb} basarisiz", RuntimeError(out))
    return out


def categorize(devices: list[dict]) -> str:
    """HFP aygitlari kapaliysa muzik modu, aciksa mikrofon modu."""
    if not devices:
        return MODE_NONE
    for dev in devices:
        if dev.get("ConfigManagerErrorCode") != 22:
            return MODE_MIC
    return MODE_MUSIC


# --------------------------------------------------------------------------
# Ikon
# --------------------------------------------------------------------------

def _font(size: int):
    for name in ("seguisym.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_icon(state: str) -> Image.Image:
    color = {MODE_MUSIC: COLOR_MUSIC, MODE_MIC: COLOR_MIC, MODE_NONE: COLOR_NONE}[state]
    glyph = {MODE_MUSIC: "♪", MODE_MIC: "M", MODE_NONE: "—"}[state]

    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = 4
    box = (margin, margin, ICON_SIZE - margin, ICON_SIZE - margin)

    if state == MODE_NONE:
        draw.ellipse(box, outline=color, width=5)
        text_color = color
    else:
        draw.ellipse(box, fill=color)
        text_color = (255, 255, 255)

    font = _font(38)
    draw.text((ICON_SIZE / 2, ICON_SIZE / 2 - 2), glyph,
              fill=text_color, font=font, anchor="mm")
    return image


# --------------------------------------------------------------------------
# Yonetici yetkisi
# --------------------------------------------------------------------------

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Yonetici olarak yeniden baslatir. ShellExecuteW <=32 dondururse hatadir
    (en yaygin sebep: kullanici UAC istemini reddetti)."""
    params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    if not getattr(sys, "frozen", False):
        params = f'"{os.path.abspath(sys.argv[0])}" {params}'.strip()
    rc = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1)
    if rc <= 32:
        log_error("relaunch_as_admin", RuntimeError(f"ShellExecuteW rc={rc}"))
        return False
    return True


# --------------------------------------------------------------------------
# Tray
# --------------------------------------------------------------------------

class BTTray:
    def __init__(self) -> None:
        self.config = load_config()
        self.devices: list[dict] = []
        self.state = MODE_NONE
        self.lock = threading.Lock()
        # pystray'in win32 backend'i _update_menu() icinde HMENU'yu
        # DestroyMenu edip yeniden kuruyor ve bunu kilitlemiyor. Ikon/baslik
        # yazmalarini kendi thread'lerimiz arasinda seri hale getiriyoruz.
        self.ui_lock = threading.Lock()
        self.stop_event = threading.Event()

        self.icon = pystray.Icon(
            APP_NAME,
            make_icon(MODE_NONE),
            "Bluetooth profili araniyor...",
            menu=self._build_menu(),
        )

    # -- menu -------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        def default_item(mode: str) -> pystray.MenuItem:
            # pystray action'lari en fazla 2 argumanli olabilir; 0 argumanli
            # closure kullaniyoruz ki `mode` her cagri icin dogru baglansin.
            return pystray.MenuItem(
                MODE_LABELS[mode],
                lambda: self.set_default_mode(mode),
                checked=lambda _item: self.config.get("default_mode") == mode,
                radio=True,
            )

        return pystray.Menu(
            pystray.MenuItem("Gecis yap", self.on_toggle, default=True, visible=False),
            pystray.MenuItem(
                MODE_LABELS[MODE_MUSIC],
                lambda: self.apply_mode(MODE_MUSIC),
                checked=lambda _item: self.state == MODE_MUSIC,
                radio=True,
            ),
            pystray.MenuItem(
                MODE_LABELS[MODE_MIC],
                lambda: self.apply_mode(MODE_MIC),
                checked=lambda _item: self.state == MODE_MIC,
                radio=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Varsayilan mod",
                pystray.Menu(
                    default_item(MODE_MUSIC),
                    default_item(MODE_MIC),
                    default_item(MODE_ASK),
                ),
            ),
            pystray.MenuItem("Yenile", self.on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Cikis", self.on_quit),
        )

    # -- eylemler ---------------------------------------------------------

    def on_toggle(self, _icon=None, _item=None) -> None:
        target = MODE_MIC if self.state == MODE_MUSIC else MODE_MUSIC
        self.apply_mode(target)

    def apply_mode(self, mode: str) -> None:
        threading.Thread(target=self._apply_mode_worker, args=(mode,), daemon=True).start()

    def _apply_mode_worker(self, mode: str) -> None:
        try:
            with self.lock:
                devices = self.devices or find_hfp_devices()
                if not devices:
                    self._notify("Bluetooth kulaklik bulunamadi",
                                 "Kulaklik bagli mi? Sag tik > Yenile.")
                    return
                error = set_devices_enabled(devices, enabled=(mode == MODE_MIC))
            time.sleep(1.0)
            self.refresh(force=True)
            if error:
                self._notify("Profil degistirilemedi",
                             "Yonetici olarak calistigindan emin ol. "
                             f"Ayrinti: {log_path()}")
            else:
                self._notify(
                    MODE_LABELS[mode],
                    "Stereo kilitli, mikrofon kapali." if mode == MODE_MUSIC
                    else "Mikrofon acik, ses kalitesi dusuk.",
                )
        except Exception as exc:
            log_error(f"apply_mode({mode})", exc)

    def set_default_mode(self, mode: str) -> None:
        # update_menu() cagirmiyoruz: pystray menu aksiyonlarini Icon._handler
        # ile sariyor ve callback'ten sonra kendisi zaten guncelliyor -- hem de
        # mesaj dongusu thread'inde, yani yarissiz.
        try:
            self.config["default_mode"] = mode
            save_config(self.config)
        except Exception as exc:
            log_error(f"set_default_mode({mode})", exc)

    def on_refresh(self) -> None:
        """Menuden gelen 'Yenile': WMI sorgusu mesaj dongusunu bloklamasin."""
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            self.refresh(force=True)
        except Exception as exc:
            log_error("on_refresh", exc)

    def apply_default_mode(self) -> None:
        mode = self.config.get("default_mode", MODE_MUSIC)
        if self.state == MODE_NONE:
            # Kulaklik bagli degil (acilista sik gorulur); her boot'ta
            # gereksiz "bulunamadi" balonu cikarmayalim.
            return
        if mode in (MODE_MUSIC, MODE_MIC) and self.state != mode:
            self._apply_mode_worker(mode)

    def on_quit(self, _icon=None, _item=None) -> None:
        self.stop_event.set()
        self.icon.stop()

    # -- durum ------------------------------------------------------------

    def refresh(self, force: bool = False) -> None:
        devices = find_hfp_devices()
        state = categorize(devices)
        if not force and state == self.state and devices == self.devices:
            return
        self.devices = devices
        self.state = state
        with self.ui_lock:
            self.icon.icon = make_icon(state)
            self.icon.title = self._title()

    def _title(self) -> str:
        if self.state == MODE_NONE:
            return "Bluetooth kulaklik yok"
        name = str(self.devices[0].get("Name") or "Bluetooth kulaklik")
        for suffix in (" Hands-Free AG Audio", " Hands-Free", " Eller Serbest"):
            name = name.replace(suffix, "")
        return f"{name.strip()} - {MODE_LABELS[self.state]}"

    def _notify(self, title: str, message: str) -> None:
        try:
            self.icon.notify(message, title)
        except Exception as exc:
            log_error("notify", exc)

    # -- dongu ------------------------------------------------------------

    def _poll_loop(self) -> None:
        try:
            self.refresh(force=True)
            self.apply_default_mode()
        except Exception as exc:
            log_error("ilk tarama", exc)
        while not self.stop_event.wait(POLL_SECONDS):
            try:
                self.refresh()
            except Exception as exc:
                log_error("poll", exc)

    def run(self) -> None:
        self.icon.run(setup=lambda _icon: threading.Thread(
            target=self._poll_loop, daemon=True).start())


def main() -> int:
    if sys.platform != "win32":
        print("Bu uygulama sadece Windows uzerinde calisir.", file=sys.stderr)
        return 1
    if not is_admin():
        if not relaunch_as_admin():
            # UAC reddedildi. --noconsole'da hicbir iz kalmadigindan
            # kullanici "cift tikladim, hicbir sey olmadi" ile bas basa kalir.
            ctypes.windll.user32.MessageBoxW(
                None,
                "bt-tray yonetici yetkisi olmadan calisamaz.\n\n"
                "Bluetooth profilini degistirmek PnP aygitini enable/disable "
                "etmeyi gerektiriyor ve bu islem yonetici izni istiyor.",
                APP_NAME, 0x30,
            )
            return 1
        return 0
    try:
        BTTray().run()
    except Exception as exc:
        log_error("main", exc)
        ctypes.windll.user32.MessageBoxW(
            None,
            f"bt-tray beklenmedik bir hatayla kapandi.\n\n{exc}\n\n"
            f"Ayrinti: {log_path()}",
            APP_NAME, 0x10,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
