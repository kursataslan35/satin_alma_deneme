# Denetim Analitiği — çalışma kuralları

Bu klasör iç denetim analitik senaryolarını geliştirir: veriyi okur, profiller, kalite
kapısından geçirir, senaryoyu çalıştırır ve sonucu Excel rapora yazar.

## Komutlar
- Kurulum: `pip install -r requirements.txt`
- Testler: `python -m pytest -q` (bu klasörde çalıştır)
- Senaryo çalıştırma: `python calistir.py <senaryo_kodu> veri/<dosya>` → `raporlar/` altına Excel

## Yapı
- `ortak/` — tüm senaryoların kullandığı araçlar
  - `veri.py`: dosya okuma (her hücre metin), Türkçe sayı/tarih dönüşümü, SHA-256 parmak izi
  - `sayi_tarih.py`: "1.250.000,00", "75.000", "15.03.2024" gibi biçimleri okur
  - `profil.py`: sütun profili (gerçek tip, doluluk, tekillik, aralık, bulgular)
  - `kalite.py`: `Kontrol` tanımları ve kalite kapısı (kritik → senaryo durur, uyarı → devam)
  - `olcum.py`: cevap anahtarıyla isabet / yakalama ölçümü
  - `rapor.py`: Excel çıktısı (Özet, Profil, Kalite, İstisnalar, Doğrulama)
- `senaryolar/<kod>/` — her senaryo kendi klasöründe:
  - `kart.md`: risk, denetim sorusu, veri, mantık, öncelik, doğrulama, sınırlamalar
  - `senaryo.py`: `AD`, `ANAHTAR`, `kalite_kontrolleri()`, `calistir(df)`, isteğe bağlı `gercek_sorunlular(df)`
  - `test_senaryo.py`: küçük, elle yazılmış veriyle beklenen istisnalar
- `veri/` ve `raporlar/` git'e girmez.

## Yeni senaryo eklerken sıra
1. Önce `kart.md` yaz ve kullanıcıyla mantığı netleştir; kod yazmadan onay al.
2. Veriyi `ortak.profil` ile profille, bulguları kullanıcıya göster.
3. Kalite kontrollerini karta göre tanımla; hangi kontrolün kritik olduğunu kullanıcıya sor.
4. `calistir(df)` ve testleri yaz; testler en az şunları kapsasın: istisna olan satır, istisna
   olmayan satır, Türkçe biçimli değer, kapıyı kapatan bozuk veri.
5. `python -m pytest -q` yeşil olmadan bitmiş sayma.
6. Gerçek veriyle `calistir.py` çalıştır, Excel'i kullanıcıya gönder, sonucu yorumla.

## Kurallar
- **Gerçek veri asla git'e, koda, test dosyasına veya commit mesajına girmez.** Testlerde uydurma veri kullan.
- Sayı ve tarihleri her zaman `ortak.veri.sayiya_cevir` / `tarihe_cevir` ile dönüştür; `float()`,
  `pd.to_numeric` veya pandas'ın tip tahminini kullanma (Türkçe biçimleri yanlış okur).
- Okunamayan veya hatalı satırı sessizce atma; kalite kontrolüyle raporla.
- Cevap anahtarı (`fraud_flag` gibi) yalnızca doğrulama içindir; senaryo mantığında kullanılmaz.
- Senaryo çıktısında her istisnanın bir `neden` açıklaması olsun; denetçi Excel'i tek başına anlayabilmeli.
- Kullanıcıya Türkçe, sade ve kısa yaz; teknik terimi ilk kullanımda açıkla.
