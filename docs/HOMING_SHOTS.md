# Güdümlü ok ve taş

**Canlı kontrol → Güdümlü ok ve taş → Aç / Kapat.** Crossbow, bowgun,
bow ve slingshot ailesindeki normal silah atışları, doğrudan hedeflenen
yaratığı Flame Strike'ın kendi yönlendirme koduyla takip eder. Seçim yerel
`app/homing-settings.json` dosyasında saklanır; yeni kurulumda kapalıdır.

Tekli ve çoklu atışlarda her mermi ayrı takip eder. Silahın ok/taş sayısı,
yelpaze açıları, görünüşü, hasar verisi, hızı, yaşam süresi ve çarpışma
denetimi korunur. Değişiklik yeni mermilere uygulanır; aç/kapat sırasında
havadakiler mevcut uçuşunu tamamlar. Yaratık hedeflenmeden zemine ateş
edilirse özgün uçuş kullanılır. Hedef ölür veya kaybolursa oyunun kendi
Flame Strike davranışı takibi bırakır; yeni hedef seçilmez. İsabet ve
duvar kontrolü özgün oyundadır; bu özellik isabet garantisi vermez.

## Native uygulama

`0x42a777`, normal silah efektinin mermi oluşturma çağrısıdır. Özgün
`CALL 0x429dd0`, çağrının ABI'sini koruyan kısa bir sarmalayıcıya yönlenir.
Sarmalayıcı EFLAGS ve bütün genel yazmaçları korur. Yalnızca tek oyuncuda,
yerel karakterin aynı haritadaki normal silah efektlerinde (0–7) ve yaşayan
bir yaratık hedefinde çalışır. Büyü efektleri ve düşman atışları kapsam dışıdır.

Özgün `0x42a300` kodu mermi paketini hazırlar. Özgün kurucu kopyalamadan önce
yalnızca iki alan değişir:

| Paket alanı | Nesne alanı | Değer | İşlev |
|---|---|---|---|
| `+0x08` | `+0xd8` | 1 | Kare başına hedef takibi |
| `+0x0c` | `+0xdc` | 20 | Flame Strike dönüş hızı |

Flame Strike bu ayarı `0x42d6e0` / `0x42da24` yolunda kullanır. Mermilerin
gerçek hareketi `0x45e1e0` içinde kalır. Native hedef kimliği, hedef kaybı,
açı normalleştirme ve `0x4140a0` hareket matematiği değiştirilmez. Hedefe
ait ham bir bellek işaretçisi saklanmaz.

İkili atışın native kaynağı sabit konum (0), diğerlerinin oyuncu konumu (1)
olarak işaretlidir. İkisi de kaynak karakter kimliğiyle doğrulanır. Bu ayrım,
iki ok atan silahların yanlışlıkla kapsam dışında kalmasını önler.

Doğrulanmış EXE ve yedi kod bölgesinin SHA-256 değeri denetlenir. İlk
bağlantıdan önce kayıtların yedeği alınır. Oyun EXE/DLL'si veya save içeriği
değiştirilmez. Yardımcı kapanırken çağrı geri alınır; sarmalayıcı içinde
devam eden çağrı bitmeden belleği serbest bırakılmaz.

## Doğrulama

`tests/test_homing_shots.py` sekiz test içerir. Unicorn içinde özgün oyunun
x86 kodu yürütülür:

- Gerçek iki silah atış döngüsünde 1–7 mermi ve ikili atış kaynağı.
- Sekiz normal efekt türünde görsel, hasar, hız ve diğer paket alanlarının
  birebir korunması; yalnızca iki takip alanının değişmesi.
- Gerçek native hareket, açı ve x87 matematiğiyle hareketli hedefe kıvrılma.
- Ölü/kayıp hedef, NPC, farklı karakter, farklı harita ve çok oyuncuda geçiş.
- Yazmaçlar, bayraklar, yığın ve özgün kurucu argümanlarının korunması.

24 Ekim 2026: tam proje testleri **116/116 geçti**. Açık oyundaki üçlü
atışla canlı bellek örnekleri de toplandı: 60 örnekte 82 ayrı mermi
görüldü; birden çok örnekte yakalanan 7 merminin yönünün uçuş sırasında
değiştiği ölçüldü. Bu sayılar toplam isabet veya toplam kıvrılan mermi
sayısı değildir; örnekleme aralığında yakalanabilen mermilerdir.

Yerel API: `POST /api/live/homing-shots`, gövde `{"enabled":true/false}`.
Mevcut localhost Origin/Host ve oturum anahtarı denetimleri geçerlidir.
Durum `homingShots` altında görünür. Tanılama, sabit alanlarla sınırlı,
salt okunur `POST /api/live/diagnostic {"homingShots":true}` örneğini sağlar.
