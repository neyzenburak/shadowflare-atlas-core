# Yaratık sıralaması ve haritaya ışınlanma

## Yaratık kataloğu

**Yaratıklar** filtresi seçildiğinde sıralamaya üç seçenek eklenir:

- Ham EXP · yüksekten düşüğe
- Ham EXP · düşükten yükseğe
- Episode ve harita ilerleyişi

EXP sıralaması, yaratığın bütün varyantlarındaki en yüksek ham EXP’ye göre yapılır.
Kartta en düşük–en yüksek aralık gösterilir; kart açıldığında en yüksek EXP’li
varyant seçilir. Sıfır EXP geçerli bir değerdir; bilinmeyen değerler sona gider.
Eşit EXP’de rehberdeki ilk karşılaşma, ardından isim sırası kullanılır.

İlerleyiş sıralaması `SF_WORLD.maps` içindeki rehber Episode ve harita `order`
alanlarını kullanır. Yaratığın yerleştirildiği en erken harita esas alınır.
Kartta Episode ve o harita gösterilir; açıldığında o haritadaki varyant seçilir.
Bu sıralama, görev koşuluyla daha sonra etkinleşen yaratıklar için bir hikâye
etkinleşme sırası iddiası taşımaz. Metin araması seçilen sıralamayı korur.
Eşyalara dönünce eşya sıralama seçenekleri geri gelir.

## Canlı harita geçişi

**Haritalar** sekmesinde bir bölge seçip **Giriş noktasına ışınlan** düğmesine bas.
**İşlemden önce kaydet** kutucuğu varsayılan olarak kapalıdır; tercih tarayıcıda
hatırlanır ve yerdeki eşya satışının kayıt seçeneğinden bağımsızdır. Seçiliyse
güncel ilerleme oyunun kendi yazıcısıyla kaydedilip doğrulanır ve yedeklenir.
Kapalıyken Atlas bu ön adımı atlar. Oyuna döndüğünde özgün bölge geçişi çalışır. Hedef senaryo kimliği, karakter
ve başlangıç girişi doğrulanır. Kamera, yoldaş ve harita nesnelerini oyun yükler.
Aynı haritayı seçmek de o haritanın girişine döndürür.

209 senaryolu harita desteklenir. Normal başlangıç giriş grubu 0’dır.
`03240000` ve `04130000` haritalarında 0 bulunmadığından ilk tam giriş grubu 50
kullanılır: dosyadaki nokta kimlikleri 200–203. Dört oyuncu yuvasının tamamı
doğrulanmıştır. Senaryosu olmayan `f00_03`, `d03_11_00`, `d03_12_00`
görsellerinde düğme kapalıdır; bu kaynaklarda oynanabilir senaryo veya giriş yoktur.

İmleçte eşya varken geçiş başlatılmaz. Bu durum `0x48ce34` elde tutulan eşya
işaretçisinden okunur; oyuncu `+0x2dc` alanı hareket/eylem durumudur ve bu kontrol
için kullanılmaz. Yalnızca tek oyunculu, canlı ve kimliği değişmemiş karaktere
istek gönderilir. Başka geçiş veya hikâye ekranı açıkken istek reddedilir.

## Native yol ve testler

Oyuncu güncelleme girişindeki geçici, tek seferlik istek, özgün `CHANGESCENARIO`
komutunun (`0x43218f..0x4321ba`) yazdığı dört alanı aynı oyun iş parçacığında
yazar: `+0x440` hedef senaryo, `+0x444` giriş grubu, `+0x454 = -1` oyuncu
seçicisi ve en son `+0x43c = 1` bekleyen geçiş bayrağı.
`0x41e825` özgün kontrol döngüsü `0x41c9a0` ve `0x426200` üzerinden yüklemeyi
yürütür. Yardımcı yükleyiciyi kendi iş parçacığından çağırmaz, senaryoya dosya
yazmaz, görev veya waypoint açma bayraklarını elle değiştirmez.

Native giriş kimliği `giriş grubu × 4 + oyuncu yuvası`dır. `0x427930` bu kimliği
senaryonun nokta tablosunda bulur. Noktaları `Scenario.Mct` dosyasından alan özgün
okuyucu `0x429467..0x4294e3`, dosyadaki `[id,x,y,yön]` kaydını bellekte
`[id,yön,x,y]` olarak saklar. Hem aynı bölge hem bölge değiştirerek giriş yolları
ayrı ayrı incelenmiş ve çalıştırılmıştır. Kalıcı EXE değişikliği yapılmaz.

`map-travel-plan.json`, 209 senaryonun kimliklerini, dört başlangıç noktasını ve
native işlev parmak izlerini içerir. Kurulumdaki MCT farklıysa dosya bütünüyle
ayrıştırılır ve gerçek girişler birebir karşılaştırılır; metin çevirisi tek
başına engel değildir. Plan `python tools/build_map_travel_plan.py` ile araştırma
fikstürlerinden yeniden üretilebilir.

`test_map_travel.py`, 209 × 4 × 2 = 1.672 giriş çözümlemesini özgün EXE’nin
komutlarıyla x86 emülatöründe yürütür. Ayrıca bütün kaynak MCT dosyaları,
kimlik bağlama, tek seferlik çalıştırma, bozuk dosyalar, tutulan eşya ve diğer
istek engelleri test edilir. Node testleri EXP/rehber sırası, doğru varyant,
arama, bilinmeyen değerler ve gerçek canlı kontrol olaylarını doğrular.

## Canlı doğrulama

26 Ekim 2026 tarihli denemede Berini Village → Remote Town geçişi
`[89898, 2811]`, ardından Remote Town → Immortal Remains geçişi
`[95281, -5532]` konumunda tamamlandı. İki konum da hedef dosyasındaki gerçek
girişle birebir eşleşti; geçici giriş kancası her işlemden sonra geri yüklendi.
Negatif Y koordinatı da işaretli tamsayı olarak doğrulandı. Kullanıcı haritanın
girişinde belirdiğini oyun içinde ayrıca doğruladı.
