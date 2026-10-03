"""Veri kalitesi kontrolleri ve senaryodan önce çalışan kalite kapısı.

Seviye "kritik" olan bir kontrol başarısızsa senaryo çalışmaz; "uyari"
seviyesindekiler senaryoyu durdurmaz ama rapora yazılır. Hatalı satırlar
asla sessizce popülasyondan çıkarılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from ortak.veri import sayiya_cevir, tarihe_cevir


@dataclass(frozen=True)
class Kontrol:
    sutun: str
    tur: str                      # bos_olmamali, tekil, sayi, tarih, aralik, liste, tutarlilik
    seviye: str = "uyari"         # kritik | uyari
    parametre: dict[str, Any] = field(default_factory=dict)
    aciklama: str = ""

    @property
    def ad(self) -> str:
        return self.aciklama or f"{self.sutun} · {self.tur}"


def _bos(seri: pd.Series) -> pd.Series:
    return seri.isna() | (seri.astype(str).str.strip() == "")


def _hatali_satirlar(df: pd.DataFrame, k: Kontrol) -> pd.Series:
    if k.tur == "tutarlilik":
        # parametre["kural"]: DataFrame alıp her satır için True (tutarlı) dönen fonksiyon
        kural: Callable[[pd.DataFrame], pd.Series] = k.parametre["kural"]
        return ~kural(df).fillna(False).astype(bool)
    if k.sutun not in df.columns:
        return pd.Series(True, index=df.index)
    seri = df[k.sutun]
    bos = _bos(seri)
    if k.tur == "bos_olmamali":
        return bos
    if k.tur == "tekil":
        temiz = seri.astype(str).str.strip()
        return ~bos & temiz.duplicated(keep=False)
    if k.tur == "sayi":
        return ~bos & sayiya_cevir(seri).isna()
    if k.tur == "tarih":
        return ~bos & tarihe_cevir(seri).isna()
    if k.tur == "aralik":
        sayi = sayiya_cevir(seri)
        hata = sayi.isna() & ~bos
        if "en_az" in k.parametre:
            hata |= sayi < k.parametre["en_az"]
        if "en_cok" in k.parametre:
            hata |= sayi > k.parametre["en_cok"]
        return hata
    if k.tur == "liste":
        izinli = {str(deger).strip() for deger in k.parametre["degerler"]}
        return bos | ~seri.astype(str).str.strip().isin(izinli)
    raise ValueError(f"bilinmeyen kontrol türü: {k.tur}")


def kalite_kapisi(df: pd.DataFrame, kontroller: list[Kontrol]) -> dict[str, Any]:
    sonuclar = []
    for k in kontroller:
        hata = _hatali_satirlar(df, k)
        tolerans = float(k.parametre.get("tolerans_yuzde", 0))
        oran = float(hata.mean() * 100) if len(df) else 0.0
        sonuclar.append({
            "kontrol": k.ad, "sutun": k.sutun, "tur": k.tur, "seviye": k.seviye,
            "durum": "basarisiz" if oran > tolerans else "gecti",
            "hatali_satir": int(hata.sum()), "taranan_satir": len(df),
            "basari_yuzde": round(100 - oran, 2),
            "ornek_satirlar": [int(i) for i in df.index[hata][:10]],
        })
    basarisiz = [s for s in sonuclar if s["durum"] == "basarisiz"]
    if any(s["seviye"] == "kritik" for s in basarisiz):
        durum = "kapali"
    elif basarisiz:
        durum = "uyarili"
    else:
        durum = "acik"
    return {"durum": durum, "sonuclar": sonuclar}
