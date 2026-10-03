"""Bordro: ödenen maaş sistemdeki maaştan farklı. Ayrıntılar kart.md'de."""

from __future__ import annotations

import pandas as pd

from ortak.kalite import Kontrol
from ortak.veri import sayiya_cevir, tr_bicim

AD = "Bordro: ödenen maaş sistemdeki maaştan farklı"
ANAHTAR = "employee_id"
ONCELIK_ESIK_YUZDE = 10.0


def _fark_tutarli(df: pd.DataFrame) -> pd.Series:
    sistem, odenen = sayiya_cevir(df["salary_system"]), sayiya_cevir(df["salary_received"])
    fark = sayiya_cevir(df["salary_difference"])
    return (sistem - odenen - fark).abs() < 0.01


def kalite_kontrolleri() -> list[Kontrol]:
    kontroller = [
        Kontrol("employee_id", "bos_olmamali", "kritik"),
        Kontrol("employee_id", "tekil", "uyari"),
        Kontrol("salary_system", "sayi", "kritik"),
        Kontrol("salary_received", "sayi", "kritik"),
        Kontrol("salary_system", "aralik", "uyari", {"en_az": 0}),
        Kontrol("salary_received", "aralik", "uyari", {"en_az": 0}),
        Kontrol("department", "bos_olmamali", "uyari"),
        Kontrol("position", "bos_olmamali", "uyari"),
    ]
    # Fark sütunu varsa hesapla tutarlı olmalı; değilse kaynak sistem hesabına güvenilemez.
    kontroller.append(Kontrol("salary_difference", "tutarlilik", "kritik", {"kural": _fark_tutarli},
                              "salary_difference = salary_system − salary_received"))
    return kontroller


def calistir(df: pd.DataFrame) -> pd.DataFrame:
    sistem, odenen = sayiya_cevir(df["salary_system"]), sayiya_cevir(df["salary_received"])
    fark = odenen - sistem
    istisna = fark.abs() > 0.005
    sonuc = df.loc[istisna, [ANAHTAR, "department", "position"]].copy()
    sonuc["sistemdeki_maas"] = sistem[istisna]
    sonuc["odenen_maas"] = odenen[istisna]
    sonuc["fark"] = fark[istisna]
    sonuc["fark_yuzde"] = (fark[istisna].abs() / sistem[istisna] * 100).round(2)
    sonuc["yon"] = fark[istisna].map(lambda x: "eksik ödeme" if x < 0 else "fazla ödeme")
    sonuc["oncelik"] = sonuc["fark_yuzde"].map(lambda x: "yüksek" if x >= ONCELIK_ESIK_YUZDE else "orta")
    sonuc["neden"] = sonuc.apply(
        lambda r: (f"Ödenen {tr_bicim(r.odenen_maas)}, sistemde {tr_bicim(r.sistemdeki_maas)} "
                   f"({r.yon}, %{tr_bicim(r.fark_yuzde, 2)})"),
        axis=1)
    return sonuc.sort_values("fark_yuzde", ascending=False).reset_index(drop=True)


def gercek_sorunlular(df: pd.DataFrame) -> set:
    """Cevap anahtarı yalnızca doğrulama içindir; senaryo mantığında kullanılmaz."""
    if "fraud_flag" not in df.columns:
        return set()
    return set(df.loc[df["fraud_flag"].astype(str).str.strip() == "1", ANAHTAR])
