"""Senaryoyu sınamak için cevap anahtarlı sentetik fatura verisi üretir (gerçek veri değildir).

Kullanım:  python -m senaryolar.satinalma_mukerrer_fatura.ornek_veri_uret
Çıktı:     veri/ornek_mukerrer_fatura.csv  (git'e girmez)

`cevap_anahtari` sütunu bilerek eklenen tekrar kayıtları gösterir: seviye1 / seviye2 / seviye3.
Asıl kayıtlar ve tuzaklar boştur. Tuzaklar mükerrer gibi görünüp olmayan kayıtlardır.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from ortak.veri import tr_bicim

TEDARIKCILER = [("T001", "Atlas Ofis Malzemeleri"), ("T002", "Kuzey Lojistik A.Ş."),
                ("T003", "Ege Danışmanlık"), ("T004", "Marmara Yapı"), ("T005", "Anadolu Bilişim")]
KULLANICILAR = ["ayse.k", "mehmet.y", "zeynep.a", "can.d"]
SUTUNLAR = ["kayit_no", "fatura_no", "tedarikci_kodu", "tedarikci_adi", "siparis_no", "fatura_tarihi",
            "tutar", "para_birimi", "olusturan", "cevap_anahtari"]


def uret(satir_sayisi: int = 300, tohum: int = 7) -> list[dict]:
    rnd = random.Random(tohum)
    kayitlar = []

    def ekle(fatura_no, kod, ad, tarih, tutar, para="TRY", cevap="", siparis=None):
        kayitlar.append({"fatura_no": fatura_no, "tedarikci_kodu": kod, "tedarikci_adi": ad,
                         "siparis_no": siparis or f"SAS-2024-{rnd.randint(1, 400):04d}",
                         "fatura_tarihi": tarih.strftime("%d.%m.%Y"), "tutar": tr_bicim(tutar, 2),
                         "para_birimi": para, "olusturan": rnd.choice(KULLANICILAR), "cevap_anahtari": cevap})
        return kayitlar[-1]

    for i in range(1, satir_sayisi + 1):
        kod, ad = rnd.choice(TEDARIKCILER)
        ekle(f"FTR-2024-{i:04d}", kod, ad, date(2024, 1, 2) + timedelta(days=rnd.randint(0, 340)),
             round(rnd.uniform(500, 250_000), 2), rnd.choice(["TRY"] * 8 + ["USD", "EUR"]))
    asil = list(kayitlar)

    # Seviye 1: aynı tedarikçi + aynı fatura no, birkaç gün sonra yeniden girilmiş
    for k in rnd.sample(asil, 4):
        ekle(k["fatura_no"], k["tedarikci_kodu"], k["tedarikci_adi"],
             date(*reversed([int(x) for x in k["fatura_tarihi"].split(".")])) + timedelta(days=rnd.randint(0, 15)),
             float(k["tutar"].replace(".", "").replace(",", ".")), k["para_birimi"], "seviye1", k["siparis_no"])

    # Seviye 2: fatura no biçimi farklı yazılmış
    bicimler = [lambda n: n.replace("-", ""), lambda n: n.lower(), lambda n: n.replace("-", " "),
                lambda n: n.replace("-", "/")]
    for k, bicim in zip(rnd.sample(asil, 4), bicimler):
        ekle(bicim(k["fatura_no"]), k["tedarikci_kodu"], k["tedarikci_adi"],
             date(*reversed([int(x) for x in k["fatura_tarihi"].split(".")])) + timedelta(days=rnd.randint(1, 10)),
             float(k["tutar"].replace(".", "").replace(",", ".")), k["para_birimi"], "seviye2")

    # Seviye 3: numarası değiştirilip aynı tutarla 30 gün içinde yeniden girilmiş
    for n, k in enumerate(rnd.sample(asil, 4)):
        ekle(f"FTR-2024-{9000 + n}", k["tedarikci_kodu"], k["tedarikci_adi"],
             date(*reversed([int(x) for x in k["fatura_tarihi"].split(".")])) + timedelta(days=rnd.randint(3, 25)),
             float(k["tutar"].replace(".", "").replace(",", ".")), k["para_birimi"], "seviye3")

    # Tuzak 1: aynı fatura no, farklı tedarikçi (mükerrer değil; inceleme notu)
    for k in rnd.sample(asil, 2):
        diger = next(t for t in TEDARIKCILER if t[0] != k["tedarikci_kodu"])
        ekle(k["fatura_no"], diger[0], diger[1], date(2024, 6, 10), round(rnd.uniform(1_000, 9_000), 2))
    # Tuzak 2: aylık sabit kira (her ayın 1'i, aynı tutar); Şubat→Mart 29 gün
    for ay in range(1, 13):
        ekle(f"KIRA-2024-{ay:02d}", "T006", "Merkez Plaza Kira", date(2024, ay, 1), 85_000.00)
    # Tuzak 3: iade faturası (negatif, aynı tutar) ve farklı para biriminde aynı tutar
    k = asil[0]
    tutar = float(k["tutar"].replace(".", "").replace(",", "."))
    tarih = date(*reversed([int(x) for x in k["fatura_tarihi"].split(".")]))
    ekle("IADE-2024-0001", k["tedarikci_kodu"], k["tedarikci_adi"], tarih + timedelta(days=5), -tutar,
         k["para_birimi"])
    ekle("FTR-2024-8001", k["tedarikci_kodu"], k["tedarikci_adi"], tarih + timedelta(days=7), tutar,
         "EUR" if k["para_birimi"] != "EUR" else "USD")

    rnd.shuffle(kayitlar)
    for i, kayit in enumerate(kayitlar, start=1):
        kayit["kayit_no"] = f"5100{i:06d}"
    return kayitlar


def yaz(yol: Path) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    with yol.open("w", encoding="utf-8-sig") as dosya:
        dosya.write(";".join(SUTUNLAR) + "\n")
        for k in uret():
            dosya.write(";".join(str(k[s]) for s in SUTUNLAR) + "\n")
    return yol


if __name__ == "__main__":
    print(yaz(Path(__file__).resolve().parents[2] / "veri" / "ornek_mukerrer_fatura.csv"))
