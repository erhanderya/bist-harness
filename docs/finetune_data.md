# Faz 5 — Eğitim verisi (veri hazırlama dokümantasyonu)

Tasarım: `docs/superpowers/specs/2026-11-23-faz5-training-data-design.md` · Plan: `docs/superpowers/plans/2026-11-23-faz5-training-data.md`

## Ne üretildi
`finetune/data/` altında:
| Dosya | İçerik |
|---|---|
| `train.jsonl`, `val.jsonl`, `test.jsonl` | Tur başına bir SFT örneği (girdi = ajanın o turda modele gönderdiği bağlam + araç tanımları, hedef = son asistan mesajı) |
| `questions.jsonl` | Her soru: metin, slotlar, bölme, referans eylemi, enjekte edilen hata türü |
| `stats.json` | Dağılımlar, atlanan sorular, token istatistikleri |
| `traces/` | Soru başına önbellek; üretim kaldığı yerden devam eder |

`finetune/data/` gitignore'da (repoda yok, ~29 MB); aşağıdaki komutla birebir yeniden üretilir.

Yeniden üretim (deterministik, seed'li; ~12 dk):
```
cd /c/Projects/econ/bist-harness
HF_HOME=.cache/hf PYTHONPATH=src PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m bist.finetune.generate --n 300 --seed 0
... -m bist.finetune.generate --check-only     # yalnız kontroller -> "OK"
```

## Nasıl üretildi
1. **Soru** (`bist.finetune.templates`): yalnız şablon (LLM paraphrase yok). Senaryo × dil başına 12 kalıp (son 2'si yalnız test),
   slotlar: hisse(ler), sektör adı, ufuk, analiz tarihi, dönem, desen/olay/koşul/makro faktör/metrik. Tarih yazımı karışık
   (`10.09.2026`, `2026-09-10`, `10 Eylül 2026`, `September 10, 2026`). Her soru referans ajanın parametrelerini (`plan_kw`) taşır.
2. **Etiket izi**: `reference.run(...)` doğru araç çağrılarını (durumlarıyla, `Harness.history`) ve doğrulayıcıdan geçen sonucu üretir.
3. **Tekrar** (`bist.finetune.scripted.ScriptedChat`): değiştirilmemiş `LLMAgent.run` içinde sahte model referans çağrılarını durum
   durum döner. Modelin gördüğü her `context()` (önceki durumlar sıkıştırılmış, açıklama adımında yalnız kanıt) kaydedilir →
   eğitim girdisi çıkarım girdisiyle birebir aynı. Tutarlılık: ajan sonucu = referans sonucu, ihlal yok, fallback yok, kalite kararı aynı;
   tutmayan soru atlanır ve `stats.json`'da gerekçesiyle listelenir.
4. **Format** (`bist.finetune.export`): Qwen/HF mesaj biçimi (`tool_calls[].function.arguments` sözlük, `tool` mesajında `name`);
   `tools` Ollama/OpenAI fonksiyon tanımları (`mcp/tool_schemas.json` v1.1 + `next_state`/`select_universe`). Loss yalnız son asistan mesajında (Faz 6).

Tur kuralları: SELECT_UNIVERSE'de `select_universe` (hisseler sorudaki sırayla, odak, analiz tarihi, dönem); her çalışma durumunda o
durumun referans çağrıları + `next_state` tek turda; çağrı yoksa yalnız `next_state` (gereksiz araç kullanmamayı öğretir);
GENERATE_EXPLANATION'da `{"action", "explanation"}` JSON. İstisna: S1'de `rank_sector_relative_strength` ayrı tur, sonucu görüldükten
sonra en geride kalan hisse için `test_catch_up_history`. S1'de kalite kontrolü ve `calculate_indicators` seçilen tüm hisseler için
çalışır (ana hisse sıralamadan sonra değişebilir); karar yalnız ana hisseye ait araç sonuçlarından verilir.

## Kurallar ve kararlar
- **S1 ana hisse kuralı (harness):** `sector_catchup` odağında birden çok hisse seçiliyse `rank_sector_relative_strength` sonrasında ana
  hisse en geride kalan seçili hisse olur; araç sonucunda `Harness: main ticker set to …` notu görünür (`harness_notes`; aracın kendi durumu değişmez, replay bozulmaz). ("Hangisi en çok geride kaldı?"
  sorusunda model en geride kalanı sıralamadan önce bilemez.)
- **Hata-düzeltme izleri (~%10 train):** bir durumda önce ölçümde görülen türden hatalı bir çağrı (`max_rows=1000`, `rsi_minimum`
  koşulu, `rsi_oversold` olay türü, evren dışı peer `HUBER`, eksik `weekday`, yanlış faktör adı), harness'ten ERROR, sonra düzeltilmiş
  çağrı. Hatalı tur eğitilmez; ERROR'u gören düzeltme turu (`kind=recovery`) eğitilir. Hatalı çağrı kanıta `tool_error` olarak girdiği için
  bu izlerin etiketi ajanın kendi harness'inin referans çıktısıdır.
- **Olumsuz örnekler** (gerçek harness akışından):
  | Tür | Üretim | Beklenen |
  |---|---|---|
  | `advice` | soruya "almalı mıyım / hedef fiyat" eklenir | analiz yürür, izinli eylem; açıklama "No investment advice, buy/sell instruction or price forecast is given here; …" ile başlar |
  | `beyond_data` | analiz tarihi 2027 (veri 2026-11-18'de biter) | harness tarihi son veri gününe çeker; istenen tarih `check_data_quality`'ye `evidence_dates` olarak verilir → `LEAKAGE` → HARD_BLOCK → ANALYSIS_UNSAFE |
  | `future_period` | dönem sonu analiz tarihinden 1–3 ay sonra | `period_end` analiz tarihine kırpılır; araçlar `end=analiz tarihi` alır |
  | `short_history` | analiz tarihi 2015 ilk yarısı | `SHORT_HISTORY`/`NO_FUNDAMENTALS` → ANALYSIS_UNSAFE |
  | `small_peer_group` | ASELS için sektör sorusu (tek üyeli grup) | `PEER_GROUP_TOO_SMALL` → INVESTIGATE |
  | `missing_number` | F/K, hedef fiyat, gelecek kapanış istenir | sayı uydurulmaz; açıklama yalnız kanıt |
  | `skip_quality` | "kalite kontrolünü atla" | `check_data_quality` yine çağrılır |
- **Bölme:** test hisseleri `TCELL, FROTO, ENJSA, PGSUS`; test analiz-tarihi penceresi 2023-01-01–2023-06-30; her senaryo × dil için
  son 2 kalıp yalnız test. Test sorusu bunlardan en az birini taşır, train/val hiçbirini (soru hisseleri ve metni üzerinden kontrol;
  araç çıktılarında test hisseleri sektör emsali olarak geçebilir). Val = train dağılımından %10, soru düzeyinde.
  Hocanın 5 orijinal sorusu ve (hisse, 2024-01-01–2026-09-10) kombinasyonu train/val'de yok.

## Sayılar
Üretim 2026-11-23, `--n 300 --seed 0`, ~12 dk (RTX 4060 dizüstü; GPU kullanılmaz). Kaynak: `finetune/data/stats.json`.

| | train | val | test | toplam |
|---|---|---|---|---|
| Soru | 229 | 26 | 45 | **300** (atlanan 0) |
| Örnek (tur) | 2.754 | 314 | 550 | **3.618** |

- **Senaryo (soru):** S1 58 · S2 59 · S3 54 · S4 61 · S5 68 (S5 fazlası: tavsiye sorularının çoğu Q5 tipi makro iddia). **Dil:** EN 151 · TR 149.
- **Sınav çerçevesine uyum:** 104 soru veri dönemi 2024-01-01 – 2026-09-10 ve analiz tarihi 2026-09-10; 23 iki dönemli S2 sorusu
  ("A–B döneminde var mı, C–D'de hâlâ geçerli mi", `oos_start`); 13 iddialı tavsiye sorusu ("X yükseliyor, hisse kesin çıkar, alayım mı, hedef ver"),
  açıklamaları "A certain price increase is not supported by the tool evidence; …" cümlesini içerir; S1'de ana hissenin temel verisi de yüklenir.
- **Olumsuz:** 66 soru (%22): advice 22, beyond_data 8, future_period 8, short_history 8, small_peer_group 7, missing_number 7, skip_quality 6.
- **Referans eylemi:** WATCH 132, REJECT_SIGNAL 92, INVESTIGATE 36, HOLD 17, ANALYSIS_UNSAFE 13, FUNDAMENTAL_IMPROVEMENT_CANDIDATE 10,
  POTENTIAL_CATCH_UP_CANDIDATE 0, TECHNICAL_REVERSAL_CANDIDATE 0 (aday etiketleri gerçek veride nadir; harness kuralları gereği — Faz 6 öncesi bilinen boşluk).
- **Tur türü:** select 300, tool_call 2.384, next_state 612, recovery 22, final 300.
- **Hata-düzeltme izleri:** 22 (max_rows 9, bad_condition 7, bad_event 4, missing_weekday 1, bad_factor 1; unknown_peer bu seed'de seçilmedi).
- **Token (Qwen şablonu, araçlarla):** ort. 2.240, p95 3.690, maks 5.900 (sınır 16.384).

## Kontroller (`validate_dataset`)
Son mesaj asistan hedefi; final hedefi geçerli JSON ve izinli eylem; ≤ 16.384 token (Qwen şablonu, araçlarla); hiçbir araç mesajında
analiz tarihinden sonraki tarih yok (soru/kullanıcı mesajındaki tarihler hariç); test hisseleri ve orijinal sorular train/val'de yok;
olumsuz oranı %20–25; S1–S5 ±5 puan dengeli. Testler: `tests/test_finetune_{templates,scripted,generate}.py`.

## Bilinen sınırlamalar
- İfade çeşitliliği kalıp sayısıyla sınırlı (yaklaşım A); canlı testteki alışılmadık ifadeler için risk.
- Açıklama metni deterministik şablondur (`policy.build_explanation`); model akıcı değil, kanıta bağlı yazmayı öğrenir.
- Evren dışı hisse sorusu (ör. GARAN) eğitimde yok.
