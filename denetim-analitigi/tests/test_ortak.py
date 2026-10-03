import pandas as pd
import pytest

from ortak.kalite import Kontrol, kalite_kapisi
from ortak.olcum import karsilastir
from ortak.veri import oku, sayiya_cevir, tarihe_cevir


def test_turkce_sayi_ve_tarih_okunur_okunamayan_bos_kalir():
    sayilar = sayiya_cevir(pd.Series(["1.250.000,00", "75.000", "12,5", "abc"]))
    assert sayilar.iloc[:3].tolist() == [1_250_000.0, 75_000.0, 12.5]
    assert pd.isna(sayilar.iloc[3])
    tarihler = tarihe_cevir(pd.Series(["15.03.2024", "2024-03-16", "31.02.2024"]))
    assert tarihler.iloc[0] == pd.Timestamp("2024-03-15") and pd.isna(tarihler.iloc[2])


def test_noktali_virgullu_csv_her_hucreyi_metin_olarak_okur(tmp_path):
    dosya = tmp_path / "x.csv"
    dosya.write_text("no;tutar\n001;1.250,00\n", encoding="utf-8-sig")
    df = oku(dosya)
    assert df.to_dict("records") == [{"no": "001", "tutar": "1.250,00"}]


@pytest.mark.parametrize("kontrol, beklenen_hatali", [
    (Kontrol("a", "bos_olmamali"), 1),
    (Kontrol("a", "tekil"), 2),
    (Kontrol("b", "sayi"), 1),
    (Kontrol("b", "aralik", parametre={"en_az": 0}), 2),
    (Kontrol("c", "liste", parametre={"degerler": ["TRY", "USD"]}), 1),
])
def test_kontrol_turleri(kontrol, beklenen_hatali):
    df = pd.DataFrame({"a": ["x", "x", "", "y"], "b": ["1", "-2", "abc", ""], "c": ["TRY", "USD", "TL", "TRY"]})
    assert kalite_kapisi(df, [kontrol])["sonuclar"][0]["hatali_satir"] == beklenen_hatali


def test_kapi_kritik_hatada_kapanir_uyarida_acik_kalir_tolerans_gecirir():
    df = pd.DataFrame({"a": ["x", ""]})
    assert kalite_kapisi(df, [Kontrol("a", "bos_olmamali", "kritik")])["durum"] == "kapali"
    assert kalite_kapisi(df, [Kontrol("a", "bos_olmamali", "uyari")])["durum"] == "uyarili"
    toleransli = Kontrol("a", "bos_olmamali", "kritik", {"tolerans_yuzde": 50})
    assert kalite_kapisi(df, [toleransli])["durum"] == "acik"


def test_isabet_ve_yakalama():
    sonuc = karsilastir(["A", "B", "C", "D"], bulunanlar=["A", "B"], gercek_sorunlular=["A", "C"])
    assert (sonuc["dogru_pozitif"], sonuc["yanlis_pozitif"], sonuc["yanlis_negatif"]) == (1, 1, 1)
    assert (sonuc["isabet_yuzde"], sonuc["yakalama_yuzde"]) == (50.0, 50.0)
