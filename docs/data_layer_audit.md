# Veri katmanı denetimi — PDF gereksinimleri vs. elimizdekiler (2026-11-17)

Durum: ✅ doğrulandı · ⚠️ kullanılabilir ama sınırlı · ❌ eksik/yapılacak

## 1. Piyasa verisi
| Gereksinim | Durum | Kanıt / not |
|---|---|---|
| 30 hisse + XU100 günlük OHLCV, 2015→ | ✅ | 88.436 satır, yarım bar atıldı; CCOLA bölünmesi düzeltildi (KAP'tan teyit edilmedi) |
| Sektör benchmark / peer medyan | ✅ | `universe.csv` peer_group; ASELS tek başına ("peer group too small") |
| Hacim tabanlı göstergeler | ⚠️ | 1.555 sıfır-hacim günü bayraklı (SASA 202: Yahoo hatası şüphesi); ECILC 2020-03-12 +%31.9 doğrulanmadı |

## 2. Temel veri (Fintables yerine KAP + İş Yatırım + resmi API)
| Gereksinim | Durum | Kanıt / not |
|---|---|---|
| Kapsam: 30 hisse × 2015Q1→2026Q3 | ✅ | 214.863 satır; sanayi/banka/sigorta ayrı şema |
| Yayın zamanı (point-in-time) | ✅ | KAP: 1.301 şirket-dönem, saniyeli; %98,2 eşleşme; 2000-kayıt kesilmesi düzeltildi |
| "Fiyata yansıma günü" kuralı | ✅ | 1.298 olayda gün-0 mutlak anormal getiri %2,84 vs. gün-1 %1,52 / baseline %1,48 → kural doğrulandı |
| Çeyreklik de-kümülasyon + oran seti | ✅ | THYAO Q1+Q2+Q3 = 9A kümülatif (birebir); büyüme/kârlılık/kaldıraç/likidite/nakit dönüşümü; banka+sigorta ayrı |
| Değerleme (F/K, PD/DD, FD/FAVÖK) | ⚠️ | Hesaplanabilir (F/K medyan 11); 20/30 hissede sermaye değişmiş → "güncel sermaye × bölünme-düzeltmeli fiyat" kullanılacak; TURSG özkaynak eşlenmedi |
| **Değerlerin İLK YAYIN (point-in-time) olması** | ⚠️ **kritik** | aşağıya bak |

### 2.1 Kritik bulgu: İş Yatırım değerleri TMS 29 döneminde ilk yayın değeri DEĞİL
Resmi KAP API (test ortamı, FY2022 + 2023Q1-Q3, 24 şirket, 1.800 karşılaştırma) ile İş Yatırım karşılaştırıldı:

- Kontrol grubu: TL dışı fonksiyonel para birimli, enflasyon muhasebesinden muaf 4 şirket (THYAO, EREGL, ENKAI, PGSUS) **%99 birebir** → ayrıştırma ve eşleştirme doğru.
- **Nominal dönem (≤ 2022 Q3) orijinal:** KAP'ın PREV karşılaştırmaları ile eşleşme: akış kalemleri %90–93, FY2021 bilanço %86–88. Kalan uyuşmazlık KRDMD, EKGYO, OYAKC'de yoğun (şirkete özgü yeniden ifade; OYAKC 2021 aktif KAP 4,9 mr vs İş Yatırım 27,9 mr).
- **TMS 29 dönemi (FY2022 →) yeniden ifade edilmiş:** FY2022 ve 2023Q1-Q3 gelir/kâr/nakit kalemlerinde İş Yatırım/KAP-orijinal oranı ≈ 1,5–2,0 (20/24 şirket); 2023 ara dönem BİLANÇOLARI orijinal (oran 1,00), FY2022 bilançosu yeniden ifade edilmiş (~1,67).
- Çıkarım: İş Yatırım her dönemi, sonraki yılın karşılaştırma verisiyle üzerine yazıyor gibi davranıyor (gözlenen: FY2022 ve 2023 ara akışlar). 2024-2026 için DOĞRULANAMADI (resmi test ortamı yalnızca 2023).
- Sonuç: YoY büyüme, TTM toplamlar ve düzey (TRY) karşılaştırmaları TMS 29 döneminde farklı satın alma gücü birimleri karıştırabilir. Aynı dönemin kendi içindeki ORANLAR (marj, kaldıraç, likidite) bu sorundan büyük ölçüde etkilenmez.

Olay sayıları: nominal dönem (≤2022Q3, geç yayın hariç) 812 olay (hisse başına 18–28); TMS 29 dönemi (≥2022Q4) 479 olay.

## 3. Henüz doğrulanamayanlar
- Bankalar (AKBNK), sigorta (TURSG), holdingler (KCHOL, TCELL) için sayısal karşılaştırma yapılmadı (XBRL adları farklı); yalnızca 24 sanayi hissesi doğrulandı. TRALT resmi test ortamında yok.
- AKBNK 2025Q3 bilançosu kaynakta boş (2 farklı sorguda da 0) → NaN, ilgili dönemin TTM oranları NaN.
- TURSG 2026Q3 net kâr −5,5 mr (YTD 9A < 6A): şüpheli, KAP ile teyit edilmedi.
- BIMAS/AKSEN/TRALT 2023Q4 yayını Mayıs 2024 (130+ gün gecikme): neden doğrulanmadı.

## 4. Henüz yapılmayan veri katmanları
Makro (kur, TCMB faizi, Fed, TÜİK enflasyon) ve haber/konuşma katmanı.

## 5. Önerilen kullanım kuralları (analiz aşamasında uygulanacak)
1. Senaryo 4 ana analiz: nominal dönem (≤2022Q3, ~812 olay). TMS 29 dönemi (479 olay) AYRI rejim, duyarlılık analizi olarak raporlanır.
2. TMS 29 döneminde düzey-tabanlı büyüme yerine ORAN değişimleri (marj, ROE, kaldıraç, likidite, nakit dönüşümü) kullanılır.
3. Gelişmiş seçenek (isteğe bağlı): KAP site Excel çıktısından her ilk yayındaki CURR/PREV'i çekmek (≈480 dosya, ~1,7 MB/dosya, kırılgan ayrıştırma).
4. Şüpheli şirket-dönemler (suspect_lag, KRDMD/EKGYO/OYAKC yeniden ifadeleri) Risk Gate'te soft warning.
