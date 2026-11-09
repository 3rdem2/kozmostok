# KozmoStok — Kurulum ve Paketleme

## 1. Paket icerigi

| Dosya | Aciklama |
|---|---|
| `KozmoStok.exe` (Windows) | Uygulama (konsol penceresi acmaz) |
| `KozmoStok.app` (macOS) | Uygulama paketi |
| `_internal/` | Python, PyQt6, psycopg2 ve diger kutuphaneler |
| `_internal/assets/` | Logo, etiket sablonlari, urun gorselleri |
| `_internal/config.ini` | Sunucu baglantisi — sifre **sifreli** (`enc:v1:...`) |
| `_internal/surum.json` | Kurulu surum bilgisi |

Kullanici verisi (log, rapor, yedek, etiket, SQLite dosyasi) uygulama klasorune
yazilmaz; isletim sisteminin kullanici klasorune yazilir:

- Windows: `%LOCALAPPDATA%\KozmoStok`
- macOS: `~/Library/Application Support/KozmoStok`

Tasinabilir (USB) kullanim icin exe'nin yanina bos bir `portable.ini` koyun;
veri exe klasorunde tutulur. `KOZMOSTOK_VERI` ortam degiskeni klasoru zorlar.

## 2. Windows kurulum

1. `KozmoStok-win.zip` dosyasini `C:\KozmoStok` gibi kalici bir klasore acin.
2. `KozmoStok.exe` dosyasina cift tiklayin.
3. Ilk acilista SmartScreen "Windows korumali bilgisayarinizi korudu" derse:
   **Ek bilgi → Yine de calistir**.
4. Kisayol icin exe'ye sag tik → **Kisayol olustur**, masaustune tasiyin.

Imzasiz exe oldugu icin SmartScreen uyarisi normaldir. Uyariyi tamamen
kaldirmak icin kod imzalama sertifikasi (OV/EV) gerekir.

## 3. macOS kurulum

1. `KozmoStok-mac.zip` dosyasini acin, `KozmoStok.app` dosyasini
   **Applications** klasorune surukleyin.
2. Ilk acilis: uygulamaya **sag tik → Ac → Ac**. (Cift tik Gatekeeper
   nedeniyle engellenebilir.)
3. Engel devam ederse Terminal'de:

```bash
xattr -dr com.apple.quarantine /Applications/KozmoStok.app
open /Applications/KozmoStok.app
```

Apple Silicon Mac'lerde "hasar gormus, cop kutusuna tasiyin" hatasi imzasiz
arm64 ikililerde gorulur; paketleme betigi `codesign --sign -` ile ad-hoc imza
attigi icin bu hata cikmaz.

Uyarisiz (sessiz) kurulum icin Apple Developer Program uyeligi (yillik ucretli)
ve `notarytool` ile noterleme gerekir. Sirket ici 4 makinede ad-hoc imza
yeterlidir.

## 4. Guncelleme

Program icinde iki yerden calisir: ust bardaki **Guncelle** dugmesi ve
**Yonetim → Sistem** sekmesi.

1. **Yonetim → Sistem** sekmesinde *Manifest adresi* alanina sunucudaki
   `surum.json` adresini yazip **Adresi kaydet**.
2. **Guncellemeyi kontrol et** → yeni surum varsa **Guncelle**.
3. Program zip'i indirir, `sha256` dogrular, kapanir, dosyalari degistirir ve
   yeniden acilir.

Manifest ornegi:

```json
{
  "surum": "1.0.1",
  "url": "https://ornek.com/kozmostok/KozmoStok-1.0.1-win.zip",
  "sha256": "zip dosyasinin sha256 ozeti",
  "notlar": "Etiket sablonu duzeltmesi"
}
```

`sha256` uretimi:

```bash
# Windows
certutil -hashfile KozmoStok-win.zip SHA256
# macOS
shasum -a 256 KozmoStok-mac.zip
```

Zip'in icinde tek bir ust klasor (`KozmoStok/...`) veya dogrudan uygulama
dosyalari bulunabilir; ikisi de desteklenir. `paketle_win.bat` dogrudan
dosyalari paketler.

## 5. Sifre ve dosya korumasi

- `config.ini` icindeki veritabani sifresi `enc:v1:` onekli sifreli metin olarak
  tutulur (PBKDF2-HMAC-SHA256 + HMAC akis sifresi + dogrulama etiketi).
  Dosyayi acan kisi sifreyi duz metin gormez.
- Sifre degistirmek icin **Yonetim → Sistem** sekmesini kullanin; kaydederken
  otomatik sifrelenir. Elle duzenlemek gerekirse:

```bash
python -c "from core.kasa import sifrele; print(sifrele('YENI_SIFRE'))"
```

- Kaynak kod paket icine `.pyc` olarak gomulur, ayri `.py` dosyasi dagitilmaz.
- Anahtar uygulama icinde gomulu oldugu icin bu koruma "dosyayi okuyan kisiye
  karsi" duzeyindedir; tersine muhendislige karsi mutlak koruma degildir.
  Daha siki koruma icin veritabani tarafinda kisitli yetkili kullanici acin.
## 6. Derleme

Windows (bu makinede):
```bat
paketle_win.bat
```

macOS (Mac veya GitHub Actions macOS runner):

```bash
./paketle_mac.sh
```

PyInstaller capraz derleme yapmaz: Windows paketi Windows'ta, macOS paketi
macOS'ta uretilir. GitHub Actions ile Mac paketi icin
`.github/workflows/build-macos.yml` hazirdir (depoyu GitHub'a push edip
**Actions → macOS paket → Run workflow**).

### 6.1 GitHub Actions ile Mac paketi (adim adim)

1. GitHub'da bos bir **private** depo acin (ornek: `kozmostok`).
2. Proje klasorunde Git'i baslatin ve gonderin (Git kurulu olmali):

```bash
cd KozmoStok
git init
git add .
git commit -m "KozmoStok 1.0.0"
git branch -M main
git remote add origin https://github.com/KULLANICI/kozmostok.git
git push -u origin main
```

`.gitignore` sayesinde `dist/`, `build/`, `*.zip`, `*.exe`, `logs/`, `yedekler/`,
`raporlar/`, `db/` depoya girmez. `assets/urun_gorselleri` (~85 MB) girer;
gorselleri depoda tutmak istemezseniz `.gitignore`'a
`assets/urun_gorselleri/` satirini ekleyin (pakette gorseller bos gelir).

3. GitHub'da **Actions** sekmesi → sol listede **macOS paket** → **Run workflow**
   → **Run workflow**. Derleme ~5-8 dakika surer.
4. Bitince calisma sayfasinin altindaki **Artifacts** bolumunden
   `KozmoStok-mac` dosyasini indirin (zip). Icerik:
   `KozmoStok-mac.zip`, `KozmoStok-mac.dmg` ve sha256 dosyalari.
5. Artifact'lar 90 gun saklanir; kalici dagitim icin ayni dosyalari
   **Releases** bolumune yukleyin.

Not: Depo private ise artifact'i yalnizca depoya erisimi olan hesaplar indirir.
Surum etiketiyle de tetiklenir: `git tag v1.0.0 && git push --tags`.

### 6.2 Git kurulu olmadan gonderim (dulwich)

Bu makinede `git` yok; depo `dulwich` (saf Python) ile olusturuldu ve ilk commit
atildi. Gonderim icin yalnizca bir GitHub token'i gerekir:

```bash
pip install dulwich
KOZMO_TOKEN=*** python kozmo_push.py KULLANICI DEPO main
```

Token'i komut satirina yazmak istemezseniz bir dosyaya koyup yolunu verin:

```bash
KOZMO_TOKEN_DOSYA=C:/gecici/token.txt python kozmo_push.py KULLANICI DEPO main
```

Dosya yolu verilmezse betik `KOZMO_TOKEN` ortam degiskenine bakar; ikisi de
yoksa `HATA: KOZMO_TOKEN veya KOZMO_TOKEN_DOSYA tanimli degil.` yazar.

Token GitHub → Settings → Developer settings → Fine-grained tokens
(https://github.com/settings/tokens?type=beta) bolumunden uretilir; yalnizca
ilgili depoya `Contents: Read and write` yetkisi verilir. Formun en altindaki
yesil **Generate token** dugmesine basilmadan token olusmaz; olusan
`github_pat_...` metni yalnizca bir kez gosterilir, sayfadan cikilirsa
kurtarilamaz ve yeni token uretmek gerekir. Klasik token alternatifi:
https://github.com/settings/tokens/new → scope `repo` → `ghp_...`.
Token komut satirina yazilmaz, ortam degiskeninden okunur ve hata mesajlarinda
maskelenir. Gonderim sonrasi token'i iptal edip yenilemek en guvenlisidir.

### 6.3 Token gorunmuyorsa

Token formu doldurulup **Generate token** dugmesine basilmadan token olusmaz.
Dugme formun en altindadir ve su kosullar saglanmadan pasif kalir: ad yazilmis,
sure secilmis, depo secilmis, `Contents: Read and write` isaretlenmis. Token
uretilince acilan sayfada `github_pat_...` kutusu ve kopyalama simgesi cikar;
sayfa yenilenirse veya baska sayfaya gecilirse token bir daha gosterilmez,
yenisi uretilmelidir. Kurum (organization) hesabinda token "Pending approval"
durumunda kalabilir; bu durumda depo sahibinin onaylamasi gerekir.

### 6.4 Token yerine tarayici girisi

`git` kurulursa (Git for Windows, Git Credential Manager ile birlikte gelir)
token gerekmez: `git push` komutu tarayici penceresi acar, GitHub'a giris
yapilir ve kimlik bilgisi Windows Kimlik Bilgileri'nde saklanir. Kurulum:
`winget install --id Git.Git -e`.

### 6.5 Depo adi ve dal

Yerel depo `main` dali uzerinde durur (GitHub varsayilani). Push komutunda dal
belirtilmezse `main` kullanilir. Depo adi buyuk/kucuk harf duyarlidir; adres
`https://github.com/KULLANICI/DEPO` bicimindedir. Ilk push'ta GitHub'da depo
bos olmalidir; README eklenmisse once `git pull --rebase` gerekir.

### 6.6 Kontrol listesi

- [ ] GitHub'da bos private depo acildi
- [ ] Token olusturuldu ve `Contents: Read and write` verildi
- [ ] Token bir dosyaya yazildi (sohbete/koda degil)
- [ ] `python kozmo_push.py KULLANICI DEPO main` calistirildi
- [ ] Actions → macOS paket → Run workflow yesil
- [ ] Artifact `KozmoStok-mac` indirildi
- [ ] Token iptal edildi

### 6.7 Depo adresi ornegi

`https://github.com/erdemtug/kozmostok` → kullanici `erdemtug`, depo `kozmostok`.
Push komutu: `python kozmo_push.py erdemtug kozmostok main`.

### 6.8 Push sonrasi

Push basarili olunca depo sayfasinda 287 dosya gorunur. **Actions** sekmesinde
`macOS paket` is akisi listelenir; ilk calistirma `workflow_dispatch` ile elle
baslatilir. Derleme bitince artifact indirilir, ardindan token iptal edilir.

### 6.9 Sorun giderme

| Belirti | Cozum |
|---|---|
| `No valid credentials provided` | Token yanlis/suresi dolmus ya da `Contents: Read and write` verilmemis |
| `404` | Kullanici/depo adi yanlis veya token o depoya yetkili degil |
| Actions'ta `macOS paket` yok | `.github/workflows/build-macos.yml` push edilmemis |
| `No module named psycopg2` | Runner bagimliligi kuramadi; log satirini inceleyin |
| Mac'te "hasar gormus" | Ad-hoc imza atlanmis; `codesign --force --deep --sign -` |

## 7. Surum ve ozet

| Surum | Paket | Boyut | sha256 |
|---|---|---|---|
| 1.0.0 (2026-11-09) | `KozmoStok-win.zip` | 128,9 MB | `969968faa6c90571e7615e60c2af2c310c9bf2a5cc60b75aca71e4bba30aba51` |

Zip icinde ust klasor yoktur: `KozmoStok.exe` + `_internal/` dogrudan kokte
bulunur. `_internal/config.ini` sifreli surumdur; bu dosyayi degistirirseniz
ozet de degisir.

## 8. Bilinen sinirlar
- Urun gorselleri hala `assets/urun_gorselleri` klasorunden ve veritabanindaki
  mutlak yollardan okunur; baska bilgisayarda eski kayitlarin gorselleri
  gorunmeyebilir (gorsellerin veritabanina tasinmasi ayri is).
- Etiket yazdirma program uzerinden yapilmaz; `.axpx` uretilip Argox yazilimi
  ile basilir.
