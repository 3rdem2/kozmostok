"""KozmoStok -> GitHub gonderimi (dulwich).

Uzak main ucundan taze klon alir, yerel kaynak dosyalari uzerine kopyalar,
tek commit atar ve gonderir. Boylece uzaktaki yeni commit'ler geri alinmaz.

Token kozmo-push.txt dosyasindan (veya KOZMO_TOKEN / KOZMO_TOKEN_DOSYA)
okunur; ekrana ve komut satirina yazilmaz.

Kullanim:
  python github_gonder.py [--mesaj "commit mesaji"] [--kuru]
"""
import io
import os
import shutil
import sys
import tempfile
import time

from dulwich import porcelain
from dulwich.index import commit_tree
from dulwich.objects import Commit
from dulwich.repo import Repo

PROJE = os.path.dirname(os.path.abspath(__file__))
KULLANICI = "3rdem2"
DEPO = "kozmostok"
DAL = "main"

# Depoya girecek kaynak dosyalar (config.ini ve veri klasorleri haric).
DOSYALAR = [
    ".gitignore", "KURULUM.md", "KozmoStok.spec", "README.md", "config.ornek.ini",
    "main.py", "requirements.txt", "surum.json",
    "baslat_kozmostok.cmd", "paketle_win.bat", "paketle_mac.sh", "paketle_mac.command",
    "sunucu_baslat.cmd", "pg_gecis.py", "test_ssl_retry.py", "github_gonder.py",
    "core/database.py", "core/db_config.py", "core/gun_sonu_servis.py",
    "core/log_servis.py", "core/rapor_servis.py", "core/sync_servis.py",
    "core/yedek_servis.py", "core/kasa.py", "core/logger.py", "core/yollar.py",
    "core/kullanici_servis.py", "core/urun_servis.py", "core/guncelleme_servis.py",
    "ui/main_window.py", "ui/magaza_ekrani.py", "ui/personel_sayfasi.py",
    "ui/yonetim_panel.py", "ui/giris_ekrani.py", "ui/sistem_sayfalari.py",
]
# Depoda kalmasi gereken, yerelde olmayabilecek dosyalar.
KORUNACAK = ["README.md", "config.ornek.ini"]


def _token():
    t = os.environ.get("KOZMO_TOKEN", "").strip()
    if t:
        return t
    yol = os.environ.get("KOZMO_TOKEN_DOSYA", "").strip()
    if not yol:
        yol = os.path.join(PROJE, "kozmo-push.txt")
    if os.path.isfile(yol):
        with open(yol, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _kopyala(hedef_kok):
    n = 0
    for d in DOSYALAR:
        kaynak = os.path.join(PROJE, d.replace("/", os.sep))
        if not os.path.isfile(kaynak):
            continue
        hedef = os.path.join(hedef_kok, d.replace("/", os.sep))
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        shutil.copy2(kaynak, hedef)
        n += 1
    return n


def _agac_yollari(repo, tree):
    yollar = set()

    def gez(t, onek=b""):
        for ad, mod, sha in t.iteritems():
            yol = onek + ad
            if mod == 0o40000:
                gez(repo[sha], yol + b"/")
            else:
                yollar.add(yol.decode())

    gez(tree)
    return yollar


def main():
    kuru = "--kuru" in sys.argv
    mesaj = "Senkron: iki makine arasi push/pull onarimi, periyodik senkron"
    if "--mesaj" in sys.argv:
        mesaj = sys.argv[sys.argv.index("--mesaj") + 1]

    token = _token()
    if not token:
        print("HATA: token bulunamadi (kozmo-push.txt / KOZMO_TOKEN).")
        return 3

    url = "https://%s:%s@github.com/%s/%s.git" % (KULLANICI, token, KULLANICI, DEPO)
    gecici = tempfile.mkdtemp(prefix="kz_git_")
    klon = os.path.join(gecici, "repo")
    try:
        print("1/4 uzak main klonlaniyor...", flush=True)
        r = porcelain.clone(url, klon, checkout=True, errstream=io.BytesIO())
        uzak_uc = r.head().decode()
        print("   uzak uc:", uzak_uc[:10], flush=True)

        print("2/4 kaynak dosyalar kopyalaniyor...", flush=True)
        n = _kopyala(klon)
        print("   kopyalanan:", n, "dosya", flush=True)

        r = Repo(klon)
        porcelain.add(r, [d for d in DOSYALAR if os.path.isfile(os.path.join(klon, d.replace("/", os.sep)))])
        index = r.open_index()
        if b"config.ini" in index:
            del index[b"config.ini"]
            index.write()
            index = r.open_index()
        agac = commit_tree(r.object_store, index.iterobjects())

        eski = r[r.head()]
        eski_yollar = _agac_yollari(r, r[eski.tree])
        yeni_yollar = _agac_yollari(r, r[agac])
        kayip = sorted(eski_yollar - yeni_yollar)
        if kayip:
            print("HATA: uzakta olup yeni agacta olmayan dosyalar:", kayip[:10])
            return 7
        print("   agac: %d dosya (uzak %d, kayip 0)" % (len(yeni_yollar), len(eski_yollar)), flush=True)

        c = Commit()
        c.tree = agac
        c.parents = [eski.id]
        c.author = c.committer = eski.author
        c.author_time = c.commit_time = int(time.time())
        c.author_timezone = c.commit_timezone = 10800
        c.message = mesaj.encode("utf-8")
        r.object_store.add_object(c)
        r.refs[b"refs/heads/" + DAL.encode()] = c.id
        print("3/4 commit:", c.id.decode()[:10], "| ebeveyn:", eski.id.decode()[:10], flush=True)

        if kuru:
            print("4/4 KURU CALISMA: gonderilmedi.")
            return 0

        cikti, hata = io.BytesIO(), io.BytesIO()
        try:
            porcelain.push(r, url, "refs/heads/%s:refs/heads/%s" % (DAL, DAL),
                           outstream=cikti, errstream=hata)
        except Exception as e:
            print("PUSH HATASI:", str(e).replace(token, "***")[:400])
            return 1
        gunluk = (cikti.getvalue() + hata.getvalue()).decode("utf-8", "replace").replace(token, "***")
        for s in gunluk.splitlines():
            if s.strip():
                print("   " + s.strip())
        print("4/4 gonderildi -> https://github.com/%s/%s" % (KULLANICI, DEPO))
        return 0
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
