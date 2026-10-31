# EXP etkinliği ve seviyeyi yeniden kazanma

Kontrol Masası → **EXP etkinliği**: kaydırıcı ve sayı alanı ×1–1000 çalışır.
Uygula, yaratık öldürmelerinden karaktere yazılan ham EXP’yi çarpar; **×1 · Kapat**
normal kazanıma döner. Drop çarpanından bağımsızdır. Yoldaş EXP’si, silah/büyü
gelişimi, öldürme sayaçları ve görev ödülleri çarpılmaz. Çarpan başlangıçta ×1’dir.

Oyunun özgün seviye atlama kuralı korunur: bir öldürmede en fazla bir seviye
atlatır ve o anda kalan fazla EXP’yi sıfırlar. Karakterin doğal üst sınırı 100’dür.

**Statları koru, seviyeyi düşür** alanına mevcut seviyenden küçük bir sayı yazıp
düğmeye bas. İşlem önce oyunun kendi kayıt işleviyle güncel ilerlemeyi kaydeder,
doğrular ve yedekler. Oyuna dönüldüğünde seviye bir kez değiştirilir ve mevcut
EXP sıfırlanır. Temel statlar, eşyalar, görevler ve öğrenilmiş beceriler korunur.
Sonraki seviye atlamasında oyun kendi sınıf geçmişi ve büyüme tablolarından
bonusları tekrar ekler. Örneğin 79 → 78 → 79 döngüsü bonusları yeniden verir;
Atlas bonus miktarlarını elle yazmaz. Seviye/EXP sabitleme ve tek öldürmede
seviye atlama hilesi açıkken işlem reddedilir.

Atlas’taki yaratık kartında **HAM EXP** seçili varyantın tam hasar katkısıyla,
çarpansız deneyimini gösterir. 18.788 yerleşim, 1.496 varyant kontrol edildi.
Enemy Hole’ın bir varyantında yerleşime göre 600 veya 800 EXP bulunduğundan
600–800 aralığı gösterilir. Diğer varyantların her biri tek değere sahiptir.
Hasar katkısı paylaşıldığında oyunun katkı tablosu önce uygulanır, EXP çarpanı
sonra devreye girer.

## Native uygulama

- ShadowFlare v2.004 oyuncu öldürme EXP yolu: `0x4134a0`.
- `0x413579` noktasındaki tam iki komut (8 bayt) geçici yönlendirilir. Girişte
  EAX mevcut EXP, EDX hesaplanan ham kazanım, ESI yerel oyuncudur. Çarpılan
  toplam oyuncu `+0xe8` alanına yazılır; işlevin geri kalanı özgün kalır.
  Normal akıştaki bir sonraki bayrak kullanımı kendi CMP komutundan gelir.
- ×1, çok oyunculu mod veya 5 saniyelik yardımcı kalp atışının süresi dolduğunda
  tam özgün komutlar çalışır. Kapatmada yönlendirme kaldırılır. Aktif çarpanda
  64 bit çarpım ve taşma kontrolü, 32 bit EXP sayacının sıfıra sarmasını önler.
- Senaryo değerlerindeki alan 13, native yaratık `+0x17c` alanına gider.
  Tablo 14 hasar katkısını; tablo 13 bir sonraki seviye için gereken EXP’yi verir.
- Seviyeyi düşürme, oyuncu güncelleme girişindeki tek seferlik istekle oyun
  iş parçacığında yürür. Yalnızca `+0x34` ve `+0xe8` değiştirilir; `0x450080`
  özgün türetilmiş statları yeniler. Temel statların `+0x38..+0xbf` aralığı
  işlem öncesi/sonrası karşılaştırılır. Fark varsa önceki statlar, seviye ve EXP
  geri yüklenir. Oyuncu, harita, canlılık ve beklenen seviye yeniden denetlenir.
- Özgün `0x412fb0` seviye atlama işlevi önce seviyeyi artırır, sınıf geçmişini
  kaydeder, sonra tablodaki bonusları temel statlara **ekler**. Daha önce ulaşılan
  en yüksek seviyeyi kontrol eden bir engel bulunmuyor. İşlev değiştirilmez.

`experience-plan.json` desteklenen native blokların SHA-256 değerlerini içerir.
Yeniden üretmek için geliştirme ortamında `python tools/build_experience_plan.py`
çalıştırılır; araştırma dizinindeki EXE/tablo/yerleşim dökümleri gerekir. Araç,
yerel `data.js` varyantlarını da gerçek yerleşimlerin EXP aralıklarıyla günceller.

## Doğrulama

`tests/test_experience.py` x86 emülatöründe katsayıları, kalp atışı, çok oyunculu
geçişi, taşmayı, ABI’yi ve seviye işlemini çalıştırır. Özgün EXE fikstürü mevcutsa
gerçek öldürme EXP ve seviye atlama komutları yürütülür: katkı → çarpan sırası,
tek öldürme sayacı, EXP sıfırlama ve iki defa 79 → 78 → 79 bonusu doğrulanır.
Sadece tablo ve ses/arayüz bağımlılıkları test ikameleriyle sağlanır.
Node kontrol testi, çarpan taslağının polling ile kaybolmadığını, sınırları,
seçili karakter bağını ve seviye isteği sonucunun arayüze yansımasını kontrol eder.

Canlı denemede 81 → 80 geçişinin temel statları bayt düzeyinde aynı kaldı.
Karakter yeniden 81 olduğunda HP 1.635 → 1.665, MP 1.435 → 1.465,
Strength 434 → 438 ve Attack 320 → 326 ölçüldü. Native EXP kancası
100.000 ham EXP’nin ×1000 ile 100.000.000 yazıldığını kaydetti. Deneme
sonunda etkinlik ×1’e kapatıldı. Tarayıcıda kontroller, gerçek karakter seviyesi,
mob EXP kartı ve aç/kapat işlemi doğrulandı; konsol hatası görülmedi.
