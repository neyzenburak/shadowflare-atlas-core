# Premium seçmeli drop etkinliği

Canlı kontrolün drop etkinliğinde **Sadece Premiumlara uygula** seçeneği,
mevcut çarpanla birlikte **Çarpanı uygula** düğmesiyle uygulanır. Seçim yerel
olarak hatırlanır; başlatıcı çalışan yardımcıyı yükseltirken çarpanı ve seçimi
birlikte aktarır. Çarpan ve Grail filtresi kapalıysa özgün drop çağrısı geri yüklenir.

## Tur davranışı

- ×100, oyunun özgün ganimet işlevini tam 100 kez çalıştırır.
- İlk turdaki bütün sonuçlar korunur. Boss'un bir normal turunda birden çok
  deneme varsa bunların tamamı korunur. Aşağıdaki Grail tekrar filtresi açıksa,
  bulunan Premium sonuçlar bu normal turdan da elenir.
- Seçenek açıkken sonraki 99 turdan yalnızca kategori 0/1/2 ve gerçek eşya
  niteliği 2 olan Premium ekipman kabul edilir.
- Premium olmayan sonuç yeniden zar atılmadan elenir. Boş sonuçlar da boş kalır;
  her bonus tur için bir Premium garanti edilmez.
- Mavi ve beyaz ekipmanlar, Tablet/Meat/Capsule ve diğer tüketilebilirler
  çarpandan yararlanmaz. Mine ve altının mevcut ×1 istisnası da korunur.
- Seçenek kapalıyken önceki etkinlik davranışı devam eder; Mine/altın dışında
  bütün ganimetler çarpandan yararlanır.

Önceden yerde bulunan eşyalara dokunulmaz. Kabul edilen yeni eşyalar mevcut
zemin kontrollü sekizgen dağıtımı kullanır. Eşya veya tur sınırı eklenmez.

## Uygulama

**Grail’de bu karakterin buldukları droplanmasın** seçeneği bağımsız bir
tekrar filtresidir. İlk normal tur dahil bütün yaratık ganimet sonuçlarına
uygulanır ve ×1’de de açık kalır. Kayıtlı toplama, takip öncesinde mevcut
ekipman veya elle **Buldum** kanıtı Grail arayüzündekiyle aynı şekilde bulunmuş
sayılır. Kontrol tam kategori/şablon kimliğiyle yapılır; aynı adlı farklı
seviye kayıtları birleştirilmez. Manuel yere bırakma, satıcı ve görev ödülleri
bu yaratık filtresine girmez. Eşya başka bir Premium ile değiştirilmez.

`grail_policy.py` içindeki sıralı tablo, Grail’in özel belleğinde tutulur.
Yerel oyuncu adresi, adının 12 baytı ve save yolunun 14 baytı her native
okumada doğrulanır. Karakter değişimi veya hazır olmayan tablo durumunda
eski karakterin kayıtları kullanılmaz. Başarılı toplama hook’u ilgili kaydı
aynı oyun çağrısında işaretler; Python olayları kalıcı günlüğe aktarır.
Durumda `excludeFound`, `filterActive`, `grailReady`, `grailProfile`,
`foundKeys` ve `duplicatesSkipped` alanları bulunur. Önbellek anahtarları
Grail seçimini ve bulunan kimlikleri içerir; engellenen eşyaların Atlas
oranları sıfırdır. Kaynak/harita listeleri de buna göre yenilenir.

`drop_event.py` v5 yalnızca düşman ölümündeki `0x45a01c` çağrısını değiştirir.
Ganimet işlevinin doğrulanmış kopyası, gizli bir yığın argümanıyla ölüm başına
ayrı bağlam alır. Çarpan ve Premium seçimi tek hizalı DWORD'dan birlikte
okunur; devam eden bir ölümün politikası ayar değişikliğinden etkilenmez.

Bonus Mine/altın önceki gibi yaratılmadan atlanır. Diğer bonus sonuçlar özgün
`0x462d30` fabrikasından bir kez geçirilir; böylece özgün rastgele özellik
üretimi de çalışır. Premium kontrolü isim veya ID tahmini yerine gerçek
nesnenin `+0xc` kategori ve `+0x18` nitelik alanlarını okur. Reddedilen nesne,
haritaya eklenmeden önce bankanın doğrulanmış `0x465640(Item**)` silme
işleviyle kaldırılır. Premium sonuç özgün konumlandırma ve ekleme yoluna döner.
Grail'in aynı silme girişindeki doğrulanmış gözlem detour'u kontrol sırasında
özgün baytlara yansıtılır; çalışma sırasında gözlemci korunur. Başka bir yama
bu girişe dokunmuşsa üzerine yazılmaz.

API: `POST /api/live/event` için `{"multiplier":100,"premiumOnly":true,"excludeFound":true}`.
Alan verilmezse mevcut seçim korunur. Durumda `premiumOnly`,
`bonusNonPremiumsSkipped` ve `bonusPremiumsAccepted` bulunur; son iki sayaç
yalnızca bonus turları sayar. İlk normal tur bunlara dahil değildir.

Atlas, Premium için `1 - (1-p)^çarpan` olasılığını; diğer eşyalar için normal
olasılığı gösterir. Beklenen adetler de eşya başına aynı kuralla güncellenir.
Eşya, yaratık ve harita önbellekleri çarpanın yanında bu seçimi de dikkate alır.

## Doğrulama

`python -m unittest discover -s tests -p test_drop_event.py -v` özgün EXE
üzerinde Unicorn ile 13 test çalıştırır. Yerel, telifli EXE fixture'ı yoksa
oyun kodu testleri atlanır. Normal/Magic/tüketilebilir sonuçların elenmesi,
üç Premium kategorisi, boss'un tüm normal denemeleri, ×1000, başarısız
yaratma, nesne silme, tur sırasında ayar değişikliği, multiplayer/lease
fallback, çağrı yığını ve kayıtçıların korunması doğrulanır.

`node tests/test_event_model.cjs` olasılıkları, harita önbelleklerini ve gerçek
`live.js` kontrol akışını doğrular. Uygulanmamış kutu seçimi durum sorgusunda
kaybolmaz; başarısız istek Atlas oranlarını değiştirmez.

25 Ekim 2026 canlı denemesinde, aynı oyun süreci açık kalırken 7 yaratıkta
700 tur tamamlandı. Bonus turlardan 10 Premium kabul edildi, 405 Premium
olmayan eşya ve 5 Mine elendi. Bu sayaçlar belirli denemenin sonucudur;
Premium düşeceğine dair garanti değildir. Uygulamadan önce karakter oyunun
özgün kayıt işleviyle kaydedildi ve yedeklendi.

Aynı gün v5 canlı denemesinde 5 yeni yaratıkta 5.000 tur tamamlandı;
karakterin bulduğu 14 Premium sonuç yere eklenmeden elendi. Kırmızı Grail
ışını mevcut yer eşyalarında, yeni yaratık kesilmeden de doğrulandı.
