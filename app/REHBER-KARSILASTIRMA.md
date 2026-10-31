# ShadowFlare Premium rehberi ile oyun verisinin karşılaştırılması

18 Ekim 2026. Kaynak: kullanıcının `herşey/Guide.html` dosyasından bağlanan 15
Premium eşya sayfası ve bu sayfalardaki özgün JPG’ler. Orijinaller değiştirilmedi.
Görev ve harita görsellerindeki bütün yazılar bu karşılaştırmanın kapsamında değil.

## Rehberin mantığı

HTML sayfalarında eşya kayıtları veya JavaScript ile çalışan bir sınıflandırıcı yok.
Sayfalar önceden hazırlanmış uzun JPG’leri gösteriyor. Eşyalar tek/çift el kılıcı,
katana, balta, arbalet, asa, zırh, başlık, bacaklık, kalkan ve aksesuar başlıklarına
ayrılmış. Bazı başlıklar gereken seviyeye göre ayrıca bölünmüş. Bu nedenle HTML
metninde bir eşya adını aramak, görsellerdeki eşyaları bulmuyor.

## Sonuç

Oyun verisinde kalite sınıfı 2 olan 457 Premium kayıt var. Rehberde 452 panel tespit
edildi. Başlıklar OCR ile çıkarılıp düşük güvenli okumalar özgün görsel üzerinden
kontrol edildi. 443 kayıt eşleştirildi. Aynı adlı dokuz Monolis paneli ve dokuz
Monolis kaydı var; aile rehberde mevcut, tek tek renk/özellik varyantları eşleştirilmedi.

İncelenen Premium listelerinde şu beş kaydın adı bulunmuyor:

| Kayıt | Ad | Gereken seviye | Standart drop kaynağı |
|---|---|---:|---|
| 0:13000600 | Caster Force | 40 | Var; örneğin Devil Jurg |
| 0:80000041 | 備前長船義直 | 35 | Var; örneğin Ancient Dragon |
| 1:31500 | Saint Robe — Premium kaydı | 50 | Var; örneğin Devil Dignosis |
| 2:200007 | Mithril Pendant | 25 | Var; örneğin Phantom Extra Gargoyle |
| 2:200020 | Kyanite Ring | 30 | Var; örneğin Ancient Dragon |

Saint Robe’un aynı adlı Normal kaydı da var. Buradaki sonuç yalnızca Premium
`1:31500` kaydı içindir. Aynı isim, aynı kalite veya aynı kayıt demek değildir.

Bu beş eşya yalnızca dosyada duran erişilemez kayıtlar değil: incelenen standart
drop tablolarında seçilebilir adaylar ve senaryolarda bu grupları kullanan yaratıklar
bulunuyor. Canlı öldürme deneyi yapılmadı. Rehberde bulunmamak, bir eşyanın beta,
kaldırılmış, kullanılmayan veya daha önce kimsenin bilmediği içerik olduğunu kanıtlamaz.

## Tesla Blade düzeltmesi

İki Tesla Blade de `sw51_80.jpg` içinde var:

| Kayıt | Başlığın yaklaşık Y konumu | Gereken seviye | Temel Attack | Sale Price |
|---|---:|---:|---:|---:|
| 0:80000128 | 2689 px | 75 | 3000 | 10000 |
| 0:80000127 | 3414 px | 80 | 5400 | 50000 |

Ad, temel saldırı, seviye ve fiyat iki ayrı oyun kaydıyla eşleşiyor. Atlas içindeki
kaynak düğmesi ilgili rehber görselini doğrudan bu konuma kaydırır.

## Görünüm

Gerçek Font00.njp bitmap fontu ve gerçek envanter ikonları kullanılıyor. Temel
değerler ek özelliklerden ayrı gösteriliyor. Örneğin Knuckle Breaker’da temel
Attack 20 ve ek Attack +45 iki farklı bölümdedir. Accessory gereken seviyeleri de
oyun kaydının kendi alanından okunuyor. Çerçeve yeniden çizildi; koyu taş dokusu
oyunun özgün Status.njp arayüz görselinden alındı.
