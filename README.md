# bt-tray-win

Bluetooth kulaklığın **A2DP (stereo müzik)** ve **HFP (mikrofon)** profilleri arasında sistem tepsisinden tek tıkla geçiş yapan tek dosyalık Windows uygulaması.

## Neden gerekli?

Bluetooth kulaklık aynı anda tek profil çalıştırır:

| Profil | Çıkış | Mikrofon |
|---|---|---|
| A2DP (Stereo) | 44.1 kHz stereo, temiz | yok |
| HFP (Hands-Free) | 8–16 kHz mono, telsiz gibi | var |

OBS, Discord, Teams veya herhangi bir uygulama kulaklığın mikrofonunu açtığı anda Windows kulaklığı zorla Hands-Free profiline düşürür ve ses kalitesi çöker. Windows bu davranışı kapatmak için bir ayar sunmaz.

Bu uygulama **Hands-Free AG Audio** PnP aygıtını enable/disable ederek profili kilitler:

- **Müzik Modu** → HFP aygıtı devre dışı → Windows profili değiştiremez, kulaklık A2DP'de kalır
- **Mikrofon Modu** → HFP aygıtı etkin → mikrofon çalışır (ses kalitesi düşer)

## Kurulum

[Releases](../../releases/latest) sayfasından `bt-tray.exe` indir ve çalıştır. Kurulum yok, tek dosya.

PnP aygıtı enable/disable etmek yönetici yetkisi gerektirdiği için exe açılışta UAC sorar.

## Kullanım

Uygulama sağ alttaki sistem tepsisine yerleşir.

| Eylem | Sonuç |
|---|---|
| Sol tık | İki mod arasında geçiş |
| Sağ tık → Müzik Modu / Mikrofon Modu | Doğrudan mod seç |
| Sağ tık → Varsayılan mod | Açılışta otomatik uygulanacak modu seç |
| Sağ tık → Yenile | Aygıt durumunu yeniden tara |

Tepsi ikonu:

| İkon | Anlam |
|---|---|
| Mavi ♪ | Müzik Modu (A2DP kilitli) |
| Kırmızı M | Mikrofon Modu (HFP açık) |
| Gri — | Bluetooth kulaklık bulunamadı |

### Varsayılan mod

Sağ tık → **Varsayılan mod** altından seçilir, `%APPDATA%\bt-tray-win\config.json` dosyasına yazılır ve uygulama her açıldığında otomatik uygulanır.

- **Müzik Modu (A2DP)** — varsayılan. Her açılışta stereo kilitlenir.
- **Mikrofon Modu (HFP)** — sürekli BT mikrofon kullananlar için.
- **Dokunma** — açılışta mevcut durumu değiştirmez.

### Otomatik başlatma

`Win + R` → `shell:startup` → exe'nin kısayolunu bu klasöre koy. UAC istemini atlamak için Görev Zamanlayıcı'da "En yüksek ayrıcalıklarla çalıştır" seçili bir oturum açma görevi oluşturulabilir.

## Bilinen sınırlar

- Bluetooth'ta "hem stereo ses hem mikrofon" fiziksel olarak mümkün değildir. Yayın yaparken kulaklık mikrofonu isteniyorsa ses kalitesinden feragat edilir; alternatifi ayrı bir mikrofon kullanmaktır.
- LE Audio destekleyen kulaklık + Windows 11 24H2 kombinasyonunda profil düşüşü daha az sorunlu olabilir, bu durumda bu araca ihtiyaç olmayabilir.
- Bazı kulaklıklarda HFP aygıtı yeniden bağlanınca Windows tarafından tekrar etkinleştirilebilir; tray her 3 saniyede durumu tarar ve ikonu günceller.

## Kaynaktan çalıştırma

```powershell
pip install -r requirements.txt
python bt_tray.py
```

## Derleme

```powershell
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --noconsole --uac-admin --name bt-tray bt_tray.py
```

CI (`.github/workflows/build.yml`) `windows-latest` üzerinde aynı komutu çalıştırır; `v*` etiketi push edildiğinde exe'yi Releases'a yükler.

## Linux karşılığı

Bu uygulama Linux'taki `bt-tray` (PySide6 + `pactl set-card-profile`) aracının Windows portudur. Linux'ta PipeWire profil geçişine doğrudan izin verdiği için aygıt devre dışı bırakmaya gerek yoktur.
