# Temel veri kaynakları — deneysel bulgular (2026-11-17)

Hepsi bu makineden gerçekten denendi. Resmi/belgeli API DEĞİL; endpoint'ler değişebilir.

## KAP (kap.org.tr) — açıklanma zamanı için ANA kaynak
- Liste: POST https://www.kap.org.tr/tr/api/disclosure/members/byCriteria
  payload: fromDate/toDate (aynı takvim yılı içinde), memberType="IGS", disclosureClass="FR" (finansal rapor), diğer alanlar boş
  (tam anahtar listesi: kod için Halley projesi `bist_haber/kap.py` ile uyumlu; marketOidList, disclosureIndexList, fromSrc=False vb.)
- Yanıt alanları: publishDate ("10.11.2025 20:11:03", saniye hassasiyetli), stockCodes, subject ("Finansal Rapor", "Faaliyet Raporu", "Sorumluluk Beyanı"),
  year, period (3/6/9/12), disclosureIndex, disclosureClass, hasMultiLanguageSupport, modifyStatus
- Aynı finansal dönem için birden fazla kayıt var (Finansal Rapor + Faaliyet Raporu + Sorumluluk Beyanı + düzeltmeler) → "Finansal Rapor" konusu filtrelenmeli, düzeltmeler (modifyStatus) ele alınmalı
- Derinlik: 2017 ve 2020 pencerelerinde kayıt döndü. 2015-03 ve 2024-03 pencerelerinde THYAO kaydı çıkmadı (neden araştırılmadı: tarih penceresi mi, konu adı mı?)
- Rakamlar: GET /tr/api/notification/export/excel/<disclosureIndex> → 1.7 MB HTML "xls"; değerler hücrelerin title="" özniteliğinde; 731 tablo; XBRL kavram adı çıktısında YOK (kap-scrapper projesi sayfadan XBRL kavramı çekiyor, denenmedi)
- Hız sınırı: 429/403/503 ve bağlantı kesme bildirilmiş; istekler arası bekleme + yeniden deneme şart
- Bildirim zamanı borsa kapanışından sonra olabilir (BIMAS 3Ç-2025: 10.11.2025 20:11) → fiyat tepkisi bir SONRAKİ işlem gününde başlar

## İş Yatırım MaliTablo — rakamlar için pratik kaynak
- GET https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/Data.aspx/MaliTablo?companyCode=THYAO&exchange=TRY&financialGroup=XI_29&year1=..&period1=..(4 dönem/istek)
- JSON: itemCode, itemDescTr, itemDescEng, value1..value4. TARİH ALANI YOK.
- Sanayi: XI_29 (139-147 kalem); Bankalar: UFRS (192 kalem, banka bilanço/gelir kalemleri). Yanlış grup → 0 satır (hata vermez!)
- Geçmiş derin: THYAO 2010 ve 2016 döndü
- Gelir tablosu değerleri YTD KÜMÜLATİF (THYAO satış gelirleri: 3A=176.7mr, 6A=408.0mr, 9A=690.8mr, 12A=975.7mr) → çeyreklik için fark alınmalı
- Resmi API değil; `isyatirimhisse` PyPI paketi aynı endpoint'i sarıyor

## Fintables
- Herkese açık API bulunamadı. Excel dışa aktarma site tarafından belirtiliyor (hesap/abonelik gereksinimi doğrulanmadı). Veriyi KAP/BIST'ten işliyor.

## Açık riskler
- TMS 29 enflasyon muhasebesi (2023 sonu →): dönem sonu satın alma gücüyle yeniden ifade; farklı tarihlerde yayınlanan aynı dönem rakamları karşılaştırılamayabilir. Hâlâ doğrulanmadı.
- Bir dönemin ilk yayın rakamı ile sonradan revize/yeniden ifade edilmiş rakamı farklı olabilir (point-in-time için ilk yayını saklamak gerekir).

---
## DÜZELTME / EK (2026-11-17, ikinci araştırma): KAP'ın RESMİ REST API'si VAR
(Önceki "belgeli resmi API bulunamadı" ifadem eksikti.)
- Resmi doküman: "KAP Veri Yayın Servisi REST API Entegrasyonu" (kap.org.tr/tr/api/about/content-file/8a019492945fbe080194b26d8bed4873, PDF). 11 servis:
  disclosures, disclosureDetail, downloadAttachment, lastDisclosureIndex, members, memberDetail, funds, fundDetail,
  memberSecurities, blockedDisclosures, caEventStatus
- Kurumsal yol: Borsa İstanbul ile VERİ DAĞITIM SÖZLEŞMESİ → MKK yetkilendirmesi (IP bazlı) → API KEY e-postayla. Destek: kapdestek@mkk.com.tr
- Geliştirici yolu: MKK API Portal https://apiportal.mkk.com.tr (duyuru 13.01.2025; "uygulama ücretsizdir"; 12 KAP servisi).
  Adımlar (duyuruya göre): hesap aç → ONAY bekle → uygulama oluştur (API key) → API ürününe kaydol → test ortamı → prod'a geçiş (koşulları belirsiz)
  Portal tek sayfa JS uygulaması; içeriği curl ile okunamadı → kota/koşullar DOĞRULANMADI
- Üçüncü taraf: PyPI `pykapfinance` 0.1.1 (resmi değil; test modunda varsayılan API key içerir; prod: key+secret → 24 saatlik token; gateway apigwdev.mkk.com.tr),
  `pykap` 0.2.0 (siteyi parse eder). Test verisi "canlı ortamın tarihsel verisi"; indeks 538004'ten başlıyor (bizim sondajlarımıza göre ≈ 2016-17).
- API yalnızca bildirim meta verisi + ek dosya veriyor görünüyor; yapılandırılmış bilanço rakamı döndürdüğü DOĞRULANMADI.
- Lisans: Borsa İstanbul verisinin yeniden dağıtımı yasak → ham veriyi rapora/repoya koyma, yalnızca yerel önbellek.

---
## Üçüncü ekleme: resmi API'nin yapısı (pykapfinance 0.1.1 kaynak kodundan okundu — ÇALIŞTIRILMADI, canlı API ile DOĞRULANMADI)
- Chrome eklentisi bu oturumda bağlı değildi; MKK portalı (Apinizer tabanlı SPA) `/api/*` uç noktalarında 401 veriyor → katalog/doküman/kota GİRİŞ gerektiriyor.
- Gateway: prod https://apigw.mkk.com.tr · test https://apigwdev.mkk.com.tr ; yollar /api/vyk/<servis>
- Auth: GET /auth/generateToken?apiKey=… → Bearer token (prod, 24 saat); test modunda Basic (key)
- disclosures: TARİHE GÖRE DEĞİL, İNDEKSE GÖRE; "disclosureIndex'ten başlayarak ilk 50 kayıt"; indeks ≥ 538004; filtreler: disclosureTypes, disclosureClass, companyId.
  Liste yanıtında YAYIN ZAMANI yok (disclosureIndex, type, class, title, companyId, acceptedDataFileTypes, subReportIds).
- disclosureDetail/{index}?fileType=data|html[&subReportList=…]: `time` (yayın zamanı), year, period, consolidation, attachmentUrls, presentation, flatData, htmlMessage
  → FR için flatData/alt raporların YAPILANDIRILMIŞ bilanço rakamı içerip içermediği BİLİNMİYOR (acceptedDataFileTypes + subReportIds ipucu veriyor).
- Maliyet tahmini: 30 şirket × ~40 çeyrek, her bildirim için ayrı detay çağrısı → binlerce istek; hız sınırı gerekecek.
- KARAR: pykapfinance içindeki hazır "varsayılan test API anahtarı" KULLANILMADI (kullanıcıya verilmiş kimlik bilgisi değil). Kendi anahtarımız için portal hesabı gerekli.

---
## Dördüncü ekleme: RESMİ OpenAPI spec okundu (docs/kap_apispec.json, kullanıcının MKK portalından indirdiği dosya)
- "KAP VYK API", OpenAPI 3.0.3, sürüm 0.0.1-apinizer-337. Sunucu: https://apigwdev.mkk.com.tr/api/vyk (YALNIZCA test/dev ağ geçidi). Güvenlik: HTTP Basic (+ AuthResponse{token}).
- 11 uç nokta, pykapfinance kaynak kodu ile BİREBİR UYUMLU (önceki üçüncü taraf bulgularımız doğrulandı).
- /disclosures: disclosureIndex (zorunlu) + disclosureTypes/disclosureClass/companyId; "ilk 50 bildirim"; tarih filtresi YOK. Yanıt: disclosureIndex, disclosureType/Class, subReportIds, title, companyId, acceptedDataFileTypes (yayın zamanı YOK)
- /disclosureDetail/{idx}?fileType=html|data[&subReportList]: time (yayın zamanı, string), year, period{tr,en}, consolidation, attachmentUrls[{url,fileName}],
  flatData[{id, content:object}], presentation[{id, content:object}], htmlMessages[{id,tr,en}], blockedStatus…  → alt rapor başına serbest biçimli `content` nesnesi
- Spec'te: kota/hız sınırı YOK, XBRL/finansal/hasılat anahtar kelimesi YOK, örnekler yer tutucu ("string") → flatData'nın bilanço kalemi içerip içermediği SPEC'ten ÇIKARILAMAZ; gerçek çağrı gerekir.
- Sıradaki doğrulama: kullanıcının kendi API anahtarıyla (.env) disclosures→disclosureDetail zinciri denenecek; bir FR bildiriminde flatData/presentation içeriği incelenecek.

---
## Beşinci ekleme: RESMİ API GERÇEK ÇAĞRILARLA DENENDİ (2026-11-17, kullanıcının kendi anahtarıyla, test ağ geçidi)
- Plan: "Free — 6 çağrı/dk throttling". İstemci (src/bist/kap_official.py) çağrılar arası 10,5 sn bekler. Günlük kota bilinmiyor.
- İlk denemede 401 OI001 "Credential is not allowed for this API Proxy" → uygulamanın KAP ürününe ABONE olması gerekiyordu (abonelik sonrası 200).
- /lastDisclosureIndex → 1231017 = "Test Bildirimi", 31.12.2023 18:30:29 → TEST ORTAMI VERİSİ 2023 SONUNDA BİTİYOR.
- Test ortamı kapsamı: FR bildirimleri ≈ Şubat 2023 (indeks ~1.103.282) → Aralık 2023. THYAO için: FY2022 (idx 1118481, yayın 01.03.2023 18:22:22), 3 Aylık 2023 (idx 1146464.., 03.05.2023 18:22:17)... Yani şirket başına ~4 rapor.
  Üretim ortamı (tam geçmiş) için Borsa İstanbul veri dağıtım sözleşmesi gerekir (resmi doküman) → öğrenci için muhtemelen yok.
- /disclosures filtreleri sunucuda uygulanıyor (companyId + disclosureClass çalışıyor); yanıtta bildirim başına subReportIds var:
  `general_role_<n>` = finansal tablolar (210015 Finansal Durum, 310003 Kâr/Zarar, 520003 Nakit Akış, 610000 Özkaynak Değişim), `oda-…` = faaliyet raporu/sorumluluk beyanı
  → detay çağrısı yalnızca general_role_* içeren bildirimler için gerekir (çağrı sayısını ~3 kat azaltır).
- /disclosureDetail/{idx}?fileType=data (fileType yalnızca html|data; "presentation" → 400):
  `time` = tam yayın zamanı "01.03.2023 18:22:22"; `presentation[]` = XBRL tarzı ağaç: ContextList (dönemler, CURR/PREV) + ReportItem (name "Revenue", langs tr/en, Values[{contextId,currency,rounding,value}]).
  Doğrulandı: THYAO FY2022 Revenue = 311.169.000.000 TRY (2021: 97.378.000.000). flatData boş geldi (FR için kullanılmıyor). ~180 KB/bildirim.
  Her bildirim önceki dönem karşılaştırma değerlerini de taşır (PREV) → YENİDEN İFADE edilmiş olabilir; point-in-time için yalnızca CURR dönemi ilk yayın değeri olarak alınmalı.
- Haber: BIST kapanışı 18:00; THYAO bildirimleri 18:22 → fiyat tepkisi ertesi işlem günü.
- Maliyet: ~1.450 çağrı (30 şirket × 40 çeyrek + liste sayfaları) ≈ 4 saat @ 6/dk — yalnızca ÜRETİM ortamı erişilirse anlamlı; test ortamında ~150 çağrı yeter.

---
## Altıncı ekleme: temel veri hattı kuruldu (2026-11-17)
- KAP site endpoint'i tek yanıtta EN FAZLA 2000 kayıt döndürür (2026-08 tam 2000 geldi → 8 şirketin Q2-2026 raporu kesilmişti). fetch_disclosure_times.py artık 2000'e ulaşınca pencereyi ikiye böler (2026-08 → 2206 kayıt). 2025-08 = 1900 (cap altı).
- KAP `period` = ÇEYREK NUMARASI (1..4; 4 = yıllık), İş Yatırım `period` = 3/6/9/12 ay.
- 'Finansal Rapor' konusu filtrelenir (+ 'Finansal Rapor Bildirimi'). Aynı dönem için faaliyet raporu / sorumluluk beyanı da gelir; düzeltmeler modify_status = DUZELTILEN/DUZENLENEN (65/64 kayıt).
- Eşleşme: İş Yatırım şirket-dönemlerinin 1293/1317'si KAP yayın zamanına bağlandı; eksikler = MPARK/ENJSA/MAVI halka arz öncesi + 2026Q2 (cap sorunu, düzeltildi).
- Bildirimlerin %87,5'i 18:00'den sonra veya hafta sonu → olay günü = bir sonraki işlem günü (effective_trade_date; açılış öncesi 09:40 kuralı).
- Anomaliler (suspect_lag > 100 gün, 17 kayıt): TRALT 2015-2017 dönemleri (2018'de halka arz sonrası toplu yayın, halka arz öncesi), BIMAS/AKSEN/TRALT 2023Q4 (2024-05 yayın; SPK TMS29 erteleme/yeniden yayın olabilir — DOĞRULANMADI).
- Dosyalar: data/processed/{kap_fr_disclosures, fundamentals_raw, fundamental_calendar}.parquet
