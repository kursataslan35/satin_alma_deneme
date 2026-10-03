"""Çalıştırma sonucunu tek bir Excel dosyasına yazar: özet, profil, kalite, istisnalar, doğrulama."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


TIP_ADLARI = {"number": "Sayı", "integer": "Tam sayı", "date": "Tarih", "text": "Metin",
              "boolean": "Evet/Hayır", "mixed": "Karışık", "empty": "Boş"}


def _profil_tablosu(profil: dict[str, Any]) -> pd.DataFrame:
    satirlar = []
    for s in profil["columns"]:
        satirlar.append({
            "Sütun": s["name"], "Gerçek tip": TIP_ADLARI.get(s["inferred_type"], s["inferred_type"]),
            "Doluluk %": s["filled_pct"], "Farklı değer": s["distinct_count"],
            "Anahtar adayı": "Evet" if s["is_key_candidate"] else "",
            "En küçük": s.get("numeric", {}).get("min", s.get("dates", {}).get("min", "")),
            "En büyük": s.get("numeric", {}).get("max", s.get("dates", {}).get("max", "")),
            "En sık değerler": ", ".join(f"{v['value']} ({v['count']})" for v in s["top_values"][:3]),
            "Bulgular": "; ".join(i["message"] for i in s["issues"]),
        })
    return pd.DataFrame(satirlar)


def _kalite_tablosu(kalite: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Kontrol": s["kontrol"], "Seviye": "Kritik" if s["seviye"] == "kritik" else "Uyarı",
        "Sonuç": "Geçti" if s["durum"] == "gecti" else "Başarısız",
        "Hatalı satır": s["hatali_satir"], "Taranan satır": s["taranan_satir"],
        "Başarı %": s["basari_yuzde"],
        "Örnek satır no (Excel)": ", ".join(str(i + 2) for i in s["ornek_satirlar"]),
    } for s in kalite["sonuclar"]])


def _genislik_ayarla(writer: pd.ExcelWriter) -> None:
    for sayfa in writer.book.worksheets:
        for sutun in sayfa.columns:
            uzunluk = max((len(str(hucre.value)) for hucre in sutun if hucre.value is not None), default=8)
            sayfa.column_dimensions[sutun[0].column_letter].width = min(max(10, uzunluk + 2), 60)
        sayfa.freeze_panes = "A2"


def rapor_yaz(yol: str | Path, ozet: dict[str, Any], profil: dict[str, Any], kalite: dict[str, Any],
              istisnalar: pd.DataFrame | None, dogrulama: dict[str, Any] | None) -> Path:
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(yol, engine="openpyxl") as writer:
        pd.DataFrame(list(ozet.items()), columns=["Bilgi", "Değer"]).to_excel(
            writer, sheet_name="Özet", index=False)
        _profil_tablosu(profil).to_excel(writer, sheet_name="Profil", index=False)
        _kalite_tablosu(kalite).to_excel(writer, sheet_name="Kalite", index=False)
        if istisnalar is not None:
            istisnalar.to_excel(writer, sheet_name="İstisnalar", index=False)
        if dogrulama:
            pd.DataFrame([
                ("Doğru pozitif (bulundu, gerçekten sorunlu)", dogrulama["dogru_pozitif"]),
                ("Yanlış pozitif (bulundu, sorunlu değil)", dogrulama["yanlis_pozitif"]),
                ("Yanlış negatif (kaçırıldı)", dogrulama["yanlis_negatif"]),
                ("Doğru negatif", dogrulama["dogru_negatif"]),
                ("İsabet %", dogrulama["isabet_yuzde"]),
                ("Yakalama %", dogrulama["yakalama_yuzde"]),
                ("Yanlış pozitif örnekleri", ", ".join(dogrulama["yanlis_pozitif_ornek"])),
                ("Yanlış negatif örnekleri", ", ".join(dogrulama["yanlis_negatif_ornek"])),
            ], columns=["Ölçü", "Değer"]).to_excel(writer, sheet_name="Doğrulama", index=False)
        _genislik_ayarla(writer)
    return yol
