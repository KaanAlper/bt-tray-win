"""Gercek Windows uzerinde calisan smoke test (CI, windows-latest).

Birim testlerinde `run_ps` her zaman monkeypatch'li oldugu icin asil
PowerShell yolu -- ozellikle codepage/encoding davranisi -- baska turlu
dogrulanamiyor. Bu dosya kasten `test_*.py` adinda DEGIL: pytest'in Linux'ta
toplamasini istemiyoruz, gercek powershell.exe gerekiyor.

    python tests/smoke_windows.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_tray  # noqa: E402

# s-cedilla, dotless i, g-breve, u-diaeresis, o-diaeresis, c-cedilla.
# Kaynak dosyayi ASCII tutmak icin kod noktalariyla yaziyoruz.
TURKISH = "şığüöç"
PS_TURKISH = (
    "Write-Output ([string]::Join('', [char[]]("
    "0x015F, 0x0131, 0x011F, 0x00FC, 0x00F6, 0x00E7)))"
)

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def main() -> int:
    if sys.platform != "win32":
        print("Bu smoke test sadece Windows uzerinde anlamli.")
        return 0

    print("PowerShell koprusu:")
    ascii_out = bt_tray.run_ps("Write-Output 'merhaba'")
    check("ASCII cikti", ascii_out.strip() == "merhaba", repr(ascii_out))

    print("\nCodepage (OEM/ANSI uyusmazligi):")
    turkish_out = bt_tray.run_ps(PS_TURKISH).strip()
    check("Turkce karakterler bozulmadan geliyor",
          turkish_out == TURKISH, f"beklenen={TURKISH!r} gelen={turkish_out!r}")
    check("Replacement karakteri yok", "�" not in turkish_out, repr(turkish_out))

    print("\nAygit sorgusu:")
    devices = bt_tray.find_hfp_devices()
    check("find_hfp_devices liste donuyor", isinstance(devices, list), repr(type(devices)))
    print(f"       bulunan HFP aygiti: {len(devices)}")
    for dev in devices:
        print(f"       - {dev.get('Name')!r} code={dev.get('ConfigManagerErrorCode')}")
    # CI runner'inda Bluetooth kulaklik yok; bos liste beklenen sonuc.
    check("bos sonuc cokmeden isleniyor",
          bt_tray.categorize(devices) in
          (bt_tray.MODE_NONE, bt_tray.MODE_MUSIC, bt_tray.MODE_MIC))

    print("\nHatali script sessizce yutulmuyor:")
    bad = bt_tray.run_ps("Bu-Komut-Yok")
    check("gecersiz cmdlet bos stdout donuyor", bad.strip() == "", repr(bad))
    log = bt_tray.log_path()
    check("hata error.log'a yazildi", os.path.exists(log) and
          "Bu-Komut-Yok" in open(log, encoding="utf-8").read())

    print("\nIkon uretimi:")
    for state in (bt_tray.MODE_MUSIC, bt_tray.MODE_MIC, bt_tray.MODE_NONE):
        image = bt_tray.make_icon(state)
        check(f"{state} ikonu", image.size == (bt_tray.ICON_SIZE, bt_tray.ICON_SIZE)
              and image.getbbox() is not None)

    print()
    if failures:
        print(f"{len(failures)} smoke testi basarisiz: {', '.join(failures)}")
        return 1
    print("Tum smoke testleri gecti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
