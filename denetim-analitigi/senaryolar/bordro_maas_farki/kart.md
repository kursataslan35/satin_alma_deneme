# Senaryo kartı — Bordro: ödenen maaş sistemdeki maaştan farklı

| Alan | İçerik |
|---|---|
| **Kod** | `bordro_maas_farki` |
| **Süreç** | İnsan Kaynakları — Bordro |
| **Risk** | Çalışana bordro sisteminde tanımlı tutardan farklı ödeme yapılması (eksik ödeme, fazla ödeme, yetkisiz değişiklik, suistimal). |
| **Denetim sorusu** | Ödenen maaş, sistemde tanımlı maaşla aynı mı? |
| **Veri** | Bordro satırları: `employee_id`, `department`, `position`, `salary_system`, `salary_received`, `salary_difference`, (varsa) `fraud_flag` |
| **Kalite ön koşulları** | Kritik: çalışan no dolu; iki maaş sütunu sayı olarak okunabilir; fark sütunu `sistem − ödenen` ile tutarlı. Uyarı: çalışan no tekil, maaşlar ≥ 0, departman/pozisyon listede. |
| **Mantık** | `salary_received ≠ salary_system` olan her satır istisnadır. Yön: ödenen < sistem → *eksik ödeme*, ödenen > sistem → *fazla ödeme*. |
| **Öncelik** | Fark sistem maaşının %10'u veya fazlası → **yüksek**, altı → **orta**. Eşik `ONCELIK_ESIK_YUZDE` ile değiştirilebilir. |
| **Çıktı** | İstisna listesi: çalışan, departman, pozisyon, iki maaş, fark, fark %, yön, öncelik, neden. |
| **Doğrulama** | Veride `fraud_flag` varsa cevap anahtarı olarak kullanılır; isabet ve yakalama oranı raporlanır. Gerçek veride bu sütun olmaz; yerine geçmiş denetim bulguları kullanılır. |
| **Sınırlamalar** | Fark yasal kesinti, avans veya dönem kayması gibi meşru nedenlerden kaynaklanabilir; istisnalar İK ile incelenmeden bulgu sayılmaz. |
