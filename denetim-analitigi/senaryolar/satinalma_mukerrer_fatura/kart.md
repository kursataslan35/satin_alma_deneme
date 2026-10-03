# Senaryo kartı — Satın alma: mükerrer fatura

| Alan | İçerik |
|---|---|
| **Kod** | `satinalma_mukerrer_fatura` |
| **Süreç** | Satın alma — Satıcı faturası kaydı ve ödeme |
| **Risk** | Aynı faturanın birden fazla kez kaydedilip ödenmesi. Neden hata (elle tekrar giriş, farklı kanaldan gelen ikinci kopya) veya suistimal (numarası değiştirilerek yeniden girilen fatura) olabilir. |
| **Denetim sorusu** | Aynı tedarikçiden aynı fatura birden fazla kez kaydedilmiş mi? |
| **Veri** | Fatura kayıtları: `kayit_no` (muhasebe belge no, tekil), `fatura_no`, `tedarikci_kodu`, `tedarikci_adi`, `fatura_tarihi`, `tutar`, `para_birimi`; yorum için `siparis_no`, `olusturan` |
| **Mantık** | Üç seviye; her kayıt en yüksek öncelikli eşleştiği seviyede raporlanır. |
| | **Seviye 1 — Kesin:** aynı `tedarikci_kodu` + aynı `fatura_no`. Öncelik **yüksek**. |
| | **Seviye 2 — Biçim farkı:** aynı `tedarikci_kodu` + sadeleştirilmiş `fatura_no` aynı (büyük harfe çevir; boşluk, tire, nokta, eğik çizgi gibi harf/rakam dışı karakterleri sil; tamamen rakamsa baştaki sıfırları sil). Öncelik **yüksek**. |
| | **Seviye 3 — Benzer:** aynı `tedarikci_kodu` + aynı `tutar` + aynı `para_birimi` + `fatura_tarihi` farkı **≤ 30 gün** (`GUN_PENCERESI`), `fatura_no` farklı. Negatif tutarlar (iade/alacak) bu seviyeye girmez. Öncelik **orta**. |
| **Gruplama** | Birbirine bağlanan kayıtlar tek grup olur. Grupta en erken tarihli (eşitse en küçük `kayit_no`) kayıt **asıl**, diğerleri **tekrar**. Grup için *olası fazla ödeme* = tekrarların tutar toplamı. |
| **Ek çıktı — inceleme notu** | Farklı tedarikçilerde aynı `fatura_no`. Mükerrer sayılmaz; tedarikçi ana verisinde aynı firmanın iki kodla açılmış olabileceğine işaret eder. Ayrı sayfada listelenir. |
| **Çıktı** | İstisna listesi: grup no, seviye, rol (asıl/tekrar), kayıt bilgileri, olası fazla ödeme, neden. |
| **Doğrulama** | Test verisinde `cevap_anahtari` sütunu tekrar kayıtları işaretler; isabet ve yakalama *tekrar* kayıtlar üzerinden ölçülür. Gerçek veride yerine geçmiş denetim bulguları veya mükerrer ödeme iadeleri kullanılır. |
| **Bilinen yanlış pozitif kaynakları** | Ay başında kesilen sabit tutarlı faturalar (kira, abonelik) Şubat–Mart arasında 30 günden kısa aralıkla gelebilir; Seviye 3'te yakalanabilir. Kısmi teslimatta aynı tutarlı iki ayrı fatura. |
| **Sınırlamalar** | Farklı tedarikçi kodlarıyla açılmış aynı firma Seviye 1–3'te yakalanmaz (inceleme notuna bakılır). Tutarı değiştirilerek tekrar girilen faturalar yakalanmaz. İstisnalar ödeme kayıtlarıyla teyit edilmeden bulgu sayılmaz. |
