"""Senaryo sonucunu bilinen bir cevap anahtarıyla karşılaştırma.

İsabet (precision): işaretlenenlerin yüzde kaçı gerçekten sorunlu?
Yakalama (recall): gerçek sorunların yüzde kaçını bulduk?
"""

from __future__ import annotations

from typing import Iterable


def karsilastir(tum_anahtarlar: Iterable, bulunanlar: Iterable, gercek_sorunlular: Iterable) -> dict:
    tum = set(tum_anahtarlar)
    bulunan = set(bulunanlar) & tum
    gercek = set(gercek_sorunlular) & tum
    dogru_pozitif = bulunan & gercek
    yanlis_pozitif = bulunan - gercek
    yanlis_negatif = gercek - bulunan
    return {
        "dogru_pozitif": len(dogru_pozitif),
        "yanlis_pozitif": len(yanlis_pozitif),
        "yanlis_negatif": len(yanlis_negatif),
        "dogru_negatif": len(tum - bulunan - gercek),
        "isabet_yuzde": round(len(dogru_pozitif) / len(bulunan) * 100, 2) if bulunan else None,
        "yakalama_yuzde": round(len(dogru_pozitif) / len(gercek) * 100, 2) if gercek else None,
        "yanlis_pozitif_ornek": sorted(map(str, yanlis_pozitif))[:20],
        "yanlis_negatif_ornek": sorted(map(str, yanlis_negatif))[:20],
    }
