import pandas as pd

from ortak.kalite import kalite_kapisi
from senaryolar.bordro_maas_farki import senaryo


def _veri(degisiklik=None):
    satirlar = [
        {"employee_id": "E1", "department": "IT", "position": "Staff",
         "salary_system": "10000", "salary_received": "10000", "salary_difference": "0", "fraud_flag": "0"},
        {"employee_id": "E2", "department": "HR", "position": "Manager",
         "salary_system": "20000", "salary_received": "15000", "salary_difference": "5000", "fraud_flag": "1"},
        {"employee_id": "E3", "department": "IT", "position": "Staff",
         "salary_system": "10000", "salary_received": "10.500,00", "salary_difference": "-500", "fraud_flag": "0"},
    ]
    for (satir, sutun), deger in (degisiklik or {}).items():
        satirlar[satir][sutun] = deger
    return pd.DataFrame(satirlar)


def test_eksik_ve_fazla_odeme_istisna_olur_esit_maas_olmaz():
    sonuc = senaryo.calistir(_veri())
    assert list(sonuc["employee_id"]) == ["E2", "E3"]
    assert list(sonuc["yon"]) == ["eksik ödeme", "fazla ödeme"]
    assert list(sonuc["oncelik"]) == ["yüksek", "orta"]      # %25 ve %5
    assert list(sonuc["fark"]) == [-5000.0, 500.0]           # "10.500,00" Türkçe biçimde okundu
    assert sonuc["neden"][0] == "Ödenen 15.000, sistemde 20.000 (eksik ödeme, %25,00)"


def test_temiz_veride_kalite_kapisi_acik():
    assert kalite_kapisi(_veri(), senaryo.kalite_kontrolleri())["durum"] == "acik"


def test_okunamayan_maas_kapiyi_kapatir():
    kapi = kalite_kapisi(_veri({(1, "salary_received"): "bilinmiyor"}), senaryo.kalite_kontrolleri())
    assert kapi["durum"] == "kapali"
    basarisiz = {s["kontrol"] for s in kapi["sonuclar"] if s["durum"] == "basarisiz"}
    assert "salary_received · sayi" in basarisiz


def test_tutarsiz_fark_sutunu_kapiyi_kapatir():
    kapi = kalite_kapisi(_veri({(1, "salary_difference"): "4000"}), senaryo.kalite_kontrolleri())
    assert kapi["durum"] == "kapali"


def test_cevap_anahtari_sadece_isaretli_satirlari_dondurur():
    assert senaryo.gercek_sorunlular(_veri()) == {"E2"}
