"""KozmoStok -> GitHub push (dulwich). Token ortam degiskeninden okunur, loglanmaz.

Kullanim:
  KOZMO_TOKEN=*** python kozmo_push.py <kullanici> <depo> [dal]
"""
import os
import sys

from dulwich import porcelain
from dulwich.repo import Repo

PROJE = r"C:/Users/Kosmonovo/Downloads/KozmoStok/KozmoStok"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    kullanici, depo = sys.argv[1], sys.argv[2]
    dal = sys.argv[3] if len(sys.argv) > 3 else "main"
    token = os.environ.get("KOZMO_TOKEN", "").strip()
    dosya = os.environ.get("KOZMO_TOKEN_DOSYA", "").strip()
    if not token and dosya:
        try:
            with open(dosya, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except OSError as e:
            print("HATA: token dosyasi okunamadi:", e)
            return 4
    if not token:
        print("HATA: KOZMO_TOKEN veya KOZMO_TOKEN_DOSYA tanimli degil.")
        return 3
    repo = Repo(PROJE)
    url = "https://%s:%s@github.com/%s/%s.git" % (kullanici, token, kullanici, depo)
    try:
        sonuc = porcelain.push(repo, url, "refs/heads/%s:refs/heads/%s" % (dal, dal))
    except Exception as e:
        mesaj = str(e).replace(token, "***")
        print("PUSH HATASI:", mesaj[:400])
        return 1
    print("push tamam:", sonuc)
    print("depo: https://github.com/%s/%s" % (kullanici, depo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
