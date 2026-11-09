"""KozmoStok -> GitHub push (dulwich). Token ortam degiskeninden okunur, ciktiya yazilmaz.

Kullanim:
  KOZMO_TOKEN=*** python kozmo_push.py <kullanici> <depo> [dal]
  KOZMO_TOKEN_DOSYA=yol python kozmo_push.py <kullanici> <depo> [dal]

Depo yoksa `--olustur` ile private depo acilir (repo yetkisi gerekir).
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request

from dulwich import porcelain
from dulwich.repo import Repo

PROJE = r"C:/Users/Kosmonovo/Downloads/KozmoStok/KozmoStok"


def _token():
    token = os.environ.get("KOZMO_TOKEN", "").strip()
    dosya = os.environ.get("KOZMO_TOKEN_DOSYA", "").strip()
    if not token and dosya:
        with open(dosya, "r", encoding="utf-8") as f:
            token = f.read().strip()
    return token


def _api(token, yol, veri=None):
    url = "https://api.github.com" + yol
    govde = json.dumps(veri).encode() if veri is not None else None
    req = urllib.request.Request(url, data=govde, method="POST" if veri is not None else "GET")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "kozmostok")
    req.add_header("Accept", "application/vnd.github+json")
    if govde:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def _depo_var(token, kullanici, depo):
    durum, _ = _api(token, "/repos/%s/%s" % (kullanici, depo))
    return durum == 200


def _depo_olustur(token, depo):
    durum, veri = _api(token, "/user/repos", {"name": depo, "private": True, "auto_init": False})
    if durum in (200, 201):
        print("depo olusturuldu:", veri.get("full_name"))
        return True
    print("HATA: depo olusturulamadi (durum %s)" % durum)
    return False


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    kullanici, depo = sys.argv[1], sys.argv[2]
    dal = sys.argv[3] if len(sys.argv) > 3 else "main"
    olustur = "--olustur" in sys.argv
    try:
        token = _token()
    except OSError as e:
        print("HATA: token dosyasi okunamadi:", e)
        return 4
    if not token:
        print("HATA: KOZMO_TOKEN veya KOZMO_TOKEN_DOSYA tanimli degil.")
        return 3

    if not _depo_var(token, kullanici, depo):
        print("UYARI: %s/%s erisilebilir degil (yok veya yetki yok)." % (kullanici, depo))
        if not olustur:
            print("Depoyu GitHub'da olusturun ya da --olustur ekleyin.")
            return 6
        if not _depo_olustur(token, depo):
            return 6

    repo = Repo(PROJE)
    url = "https://%s:%s@github.com/%s/%s.git" % (kullanici, token, kullanici, depo)
    cikti, hata = io.BytesIO(), io.BytesIO()
    try:
        porcelain.push(repo, url, "refs/heads/%s:refs/heads/%s" % (dal, dal),
                       outstream=cikti, errstream=hata)
    except Exception as e:
        print("PUSH HATASI:", str(e).replace(token, "***")[:400])
        return 1

    gunluk = (cikti.getvalue() + hata.getvalue()).decode("utf-8", "replace")
    gunluk = gunluk.replace(token, "***")
    for satir in gunluk.splitlines():
        if satir.strip():
            print("  " + satir.strip())

    if "refusing to allow" in gunluk or "workflow" in gunluk and "scope" in gunluk:
        print("SONUC: REDDEDILDI - token'da 'workflow' yetkisi yok.")
        return 5

    try:
        uzak = repo.get_refs()
        yerel = repo.refs[b"refs/heads/" + dal.encode()].decode()
    except KeyError:
        yerel = ""
    print("SONUC: gonderildi -> refs/heads/%s %s" % (dal, yerel[:10]))
    print("depo: https://github.com/%s/%s" % (kullanici, depo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
