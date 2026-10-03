"""Bir senaryoyu uçtan uca çalıştırır: oku → profil → kalite kapısı → senaryo → doğrulama → Excel.

Kullanım:
    python calistir.py <senaryo_adi> <veri_dosyasi> [--cikti raporlar/]

Çıkış kodu: 0 tamamlandı, 2 kalite kapısı kapalı (senaryo çalışmadı).
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ortak.kalite import kalite_kapisi
from ortak.olcum import karsilastir
from ortak.profil import profile_records
from ortak.rapor import rapor_yaz
from ortak.veri import oku, parmak_izi

KOK = Path(__file__).resolve().parent


def _kod_surumu() -> str:
    try:
        surum = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=KOK, capture_output=True,
                               text=True, check=True).stdout.strip()
        degisiklik = subprocess.run(["git", "status", "--porcelain", "--", "ortak", "senaryolar"],
                                    cwd=KOK, capture_output=True, text=True, check=True).stdout.strip()
        return surum + (" (commit edilmemiş değişiklik var)" if degisiklik else "")
    except (OSError, subprocess.CalledProcessError):
        return "bilinmiyor"


def calistir(senaryo_adi: str, veri_yolu: str | Path, cikti_klasoru: str | Path = KOK / "raporlar") -> dict:
    senaryo = importlib.import_module(f"senaryolar.{senaryo_adi}.senaryo")
    veri_yolu = Path(veri_yolu)
    zaman = datetime.now()
    df = oku(veri_yolu)
    print(f"1/5 Veri okundu: {len(df)} satır, {len(df.columns)} sütun")

    profil = profile_records(df.to_dict("records"), list(df.columns))
    print(f"2/5 Profil çıkarıldı: {profil['issue_count']} bulgu")

    kalite = kalite_kapisi(df, senaryo.kalite_kontrolleri())
    print(f"3/5 Kalite kapısı: {kalite['durum']}")

    istisnalar, dogrulama = None, None
    if kalite["durum"] != "kapali":
        istisnalar = senaryo.calistir(df)
        print(f"4/5 Senaryo çalıştı: {len(istisnalar)} istisna")
        cevap = getattr(senaryo, "gercek_sorunlular", None)
        if cevap is not None:
            dogrulama = karsilastir(df[senaryo.ANAHTAR], istisnalar[senaryo.ANAHTAR], cevap(df))
            print(f"    Doğrulama: isabet %{dogrulama['isabet_yuzde']}, "
                  f"yakalama %{dogrulama['yakalama_yuzde']}")
    else:
        print("4/5 Senaryo ÇALIŞMADI: kritik kalite kontrolü başarısız")

    ozet = {
        "Senaryo": senaryo.AD, "Senaryo kodu": senaryo_adi,
        "Çalıştırma zamanı": zaman.strftime("%d.%m.%Y %H:%M:%S"),
        "Veri dosyası": veri_yolu.name, "Veri parmak izi (SHA-256)": parmak_izi(veri_yolu),
        "Kod sürümü": _kod_surumu(), "Satır sayısı": len(df),
        "Kalite kapısı": {"acik": "Açık", "uyarili": "Açık (uyarılı)", "kapali": "Kapalı"}[kalite["durum"]],
        "İstisna sayısı": len(istisnalar) if istisnalar is not None else "çalışmadı",
    }
    if dogrulama:
        ozet.update({"İsabet %": dogrulama["isabet_yuzde"], "Yakalama %": dogrulama["yakalama_yuzde"]})
    rapor = rapor_yaz(Path(cikti_klasoru) / f"{senaryo_adi}_{zaman:%Y%m%d_%H%M%S}.xlsx",
                      ozet, profil, kalite, istisnalar, dogrulama)
    print(f"5/5 Rapor yazıldı: {rapor}")
    return {"kalite": kalite, "istisnalar": istisnalar, "dogrulama": dogrulama, "rapor": rapor}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("senaryo"); parser.add_argument("veri")
    parser.add_argument("--cikti", default=str(KOK / "raporlar"))
    args = parser.parse_args(argv)
    sonuc = calistir(args.senaryo, args.veri, args.cikti)
    return 2 if sonuc["kalite"]["durum"] == "kapali" else 0


if __name__ == "__main__":
    sys.exit(main())
