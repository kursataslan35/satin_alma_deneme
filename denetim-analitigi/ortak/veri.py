"""Kaynak dosyayı değiştirmeden okuma.

Her hücre metin olarak okunur; sayı ve tarih dönüşümü bilinçli olarak
`ortak.sayi_tarih` ile yapılır. Böylece "1.250,00" veya "15.03.2024" gibi
Türkçe biçimler pandas'ın tahminine bırakılmaz.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from ortak.sayi_tarih import parse_date, parse_number


def _ayirac(ilk_satir: str) -> str:
    """Türkçe Excel CSV'yi ';' ile ayırır, çünkü ',' ondalık işaretidir."""
    sayilar = {ayirac: ilk_satir.count(ayirac) for ayirac in (",", ";", "\t")}
    en_cok = max(sayilar, key=sayilar.get)
    return en_cok if sayilar[en_cok] > sayilar[","] else ","


def oku(yol: str | Path, sayfa: str | int = 0) -> pd.DataFrame:
    yol = Path(yol)
    if yol.suffix.lower() in {".xlsx", ".xlsm"}:
        df = pd.read_excel(yol, sheet_name=sayfa, dtype=str, keep_default_na=False)
    else:
        with yol.open(encoding="utf-8-sig") as dosya:
            ilk_satir = dosya.readline()
        df = pd.read_csv(yol, sep=_ayirac(ilk_satir), dtype=str, keep_default_na=False,
                         encoding="utf-8-sig")
    df.columns = [str(sutun).strip() for sutun in df.columns]
    return df


def parmak_izi(yol: str | Path) -> str:
    """Dosyanın SHA-256 özeti; rapor hangi verinin kullanıldığını kanıtlar."""
    return hashlib.sha256(Path(yol).read_bytes()).hexdigest()


def sayiya_cevir(seri: pd.Series) -> pd.Series:
    """Okunamayan değerler NaN olur; kalite kontrolü bunları ayrıca raporlar."""
    def cevir(deger):
        try:
            return parse_number(deger)
        except (TypeError, ValueError):
            return float("nan")
    return seri.map(cevir).astype(float)


def tarihe_cevir(seri: pd.Series) -> pd.Series:
    def cevir(deger):
        try:
            return pd.Timestamp(parse_date(deger))
        except (TypeError, ValueError):
            return pd.NaT
    return pd.to_datetime(seri.map(cevir))


def tr_bicim(sayi: float, ondalik: int = 0) -> str:
    """1234567.5 → '1.234.567' (ondalik=0) veya '1.234.567,50' (ondalik=2)."""
    metin = f"{sayi:,.{ondalik}f}"
    return metin.replace(",", "X").replace(".", ",").replace("X", ".")
