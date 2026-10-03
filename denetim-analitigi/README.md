# Denetim Analitiği

İç denetim senaryolarını tekrarlanabilir şekilde çalıştıran küçük bir Python projesi.
Akış: **oku → profil → kalite kapısı → senaryo → doğrulama → Excel rapor**.

```bash
pip install -r requirements.txt
python -m pytest -q
python calistir.py bordro_maas_farki veri/dataset_fraud_payroll.csv
```

Senaryolar `senaryolar/` altında; her birinin `kart.md` dosyası ne aradığını anlatır.
Çalışma kuralları ve yeni senaryo ekleme sırası `CLAUDE.md` içinde.
