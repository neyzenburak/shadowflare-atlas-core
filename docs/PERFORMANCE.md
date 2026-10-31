# Yoğun ganimet: 23 Ekim 2026

Son sürüm: render performansı v11. Oyuncu yoğun eşya yığınları arasında
20 saniye yürürken, 2.293 yer eşyası korunarak **29,65 FPS** ölçüldü.
Oyuncu, önceki belirgin yürüyüş kasmasının düzeldiğini doğruladı.

| Yürüyüş ölçümü | Sonuç |
|---|---:|
| Tamamlanan kare / süre | 593 / 20,0004 sn |
| Medyan kaydedilmiş kare aralığı | 33,19 ms |
| %95 / %99 yüzdelik | 37,55 / 41,94 ms |
| En uzun kaydedilmiş aralık | 60,20 ms |
| 50 ms / 100 ms üstü kaydedilmiş aralık | 2 / 0 |

Ölçüm oyun kare tamamlanma sayacının yaklaşık 2 ms aralıkla okunmasıdır;
oyun thread'leri durdurulmaz. Okumalar arasında kaçırılan 25 kare geçişi
ayrı sayılır; bunlar için tek tek kare süresi uydurulmaz. FPS bütün kare
farkından hesaplanır; yüzdelikler yalnızca kaydedilebilen aralıklara aittir.

## Karşılaştırma ve sınırlar

İlk karşılaştırma aynı süreç, aynı görünüm ve 2.293 eşya ile yapıldı:

| Uygulama | Kare | Süre | FPS |
|---|---:|---:|---:|
| Önceki doğrudan liste sıralaması | 73 | 5,0003 sn | 14,60 |
| Artımlı ilişki tablosu | 121 | 5,0039 sn | 24,18 |
| İlişki tablosu + ardışık örtüşme aramaları | 121 | 5,0007 sn | 24,20 |

Son ekleme bu ilk görünümde belirgin ek FPS kazancı göstermedi; tekrarlı
indeks aramalarını kaldırdı. Sonraki vurgu döngüsü düzeltmesinde yaklaşık
28 FPS görüldü. Oyuncu, envanter doluyken toplama girişiminin bile akıcılığı
değiştirdiğini; bazı yoğun konumlarda durunca hâlâ kasma olduğunu bildirdi.

Ara v10 sürümünde dururken yaklaşık 29 FPS görülmesine rağmen oyuncu
yürürken hâlâ kasma bildirdi. Görünen liste boyu değişince önbelleğin
yeniden kurulması v11'de giderildi. Son ölçüm yürüyüş sırasında alındı.

Son ölçüm öncekilerle aynı oyun sürecinde ve aynı 2.293 eşya ile alındı;
karakter bu arada hareket ettiği için ilk 14,60 FPS kaydıyla birebir aynı
kameradan alınmış bir karşılaştırma değildir. Bütün yoğunluklarda sabit FPS
veya oyunun bütün hatalarının giderildiği iddia edilmez.

Thread örneklemesi bağlamları okumak için kısa durdurmalar yapar ve ölçümü
etkileyebilir. Pasif sayaç kaydı thread durdurmaz; iki yöntem ayrı tutulur.
Yerel teşhis kayıtları ve bellek görüntüleri GitHub'a yüklenmez.

## Son değişiklik neden gerekliydi?

Liste sırası kayan nesneler, önceki önbellekte pek çok sabit nesneyi değişmiş
gösteriyordu. Yalnızca nesnenin bellek adresini eşlemek de canlı oyunda işe
yaramadı: çizim nesnelerinin yeniden kurulması önbelleği sürekli bozdu.
Bu deneme yaklaşık 15 FPS kaldı ve son sürümde kullanılmıyor.

v11, sıralamayı belirleyen tam `(left, top, right, bottom, group)` değerlerini
eşler. Hash yalnızca aday bulur; beş değerin tamamı ayrıca karşılaştırılır.
Eşleşen eski geometri aynı matris hücresini kullanır. İlk geçişte eşleşmeyen
girdiler, değişmeyenler eşlendikten sonra boşta kalan hücrelere atanır.
Yalnızca değişen geometriye bağlı satır ve sütunlar yeniden hesaplanır.
Girdi sırası ayrıca tutulur; özgün eşitlik ve döngü çözme davranışı korunur.

Birbirinin aynı konum ve geometriye sahip eşyalar ayrı girdiler olarak
eşlenir. Görsel birleştirme, eşya silme veya eşya/tur sınırı uygulanmaz.
Farklı listeler için sekiz önbellek girdisi vardır. Bu sayı eşya kapasitesi
değildir. Alan, ihtiyaç arttıkça 256 kaydın katlarına büyür; görünen nesne
sayısı azalınca korunur. Bir girdi değiştirilirse eski alan serbest bırakılır.

Yürürken özgün listeden çıkan geometriye ait hesaplar bellekte kalabilir.
Etkin girdi bit maskesi, derece ve sıralama hesabına yalnızca o karede
özgün oyunun listelediği nesneleri dahil eder. İlişkilerin ters matrisi,
görünen liste boyu değişince bütün ilişkileri yeniden kurmadan etkin giriş
derecelerini hesaplamayı sağlar. Yeni görünen nesneler bütün eski nesnelerin
tekrar hesaplanmasına yol açmaz.

## Korunan davranış

- Sıralama ilişkisi özgün DLL ile aynıdır; işaretli 32 bit toplama davranışı
  ve döngüsel bağımlılıklarda ilk kalan nesnenin seçilmesi korunur.
- Eşit öncelikli adaylarda özgün girdi sırası korunur. Taşınan hücrelerde
  özgün flags/transparency sıfırlama davranışı uygulanır.
- Önceki render nesnesi veya hücresi üzerinden veri okunmaz. Güncel hücreler
  her çağrıda yenilenir. Hash çakışması yaklaşık eşleşme sayılmaz.
- Bellek ayrılamazsa önceki tam liste algoritması çalışır; eşya silinmez.
- Ardışık arama yalnızca dört doğrulanmış döngüde kullanılır: üç örtüşme
  döngüsü ve bir nesne vurgu döngüsü. Çağıran, liste, baş hücre, stack frame
  ve sıralama nesli kontrol edilir. Diğer çağrılar özgün Get işlevini kullanır.
- Vurgu döngüsünün kodu, eriştiği RGB işlevleri ve import hedefleri doğrulanır;
  bu döngü nesne bağlantılarını veya liste üyeliğini değiştirmez.
- Yardımcı kapanırken çağrılar geri alınır; etkin çağrılar bitince önbellek
  alanları ve 8 KB kod alanı serbest bırakılır.

Her önbellek alanının boyu, büyüyen kapasite `C`, `H = nextpow2(2*C)` ve
satır genişliği `S = C/8` için:

```text
48*C + 8*H + S + 2*C*S bayt
```

İlk bölüm metadata, sonuç sırası, derece, değişen girdiler ve özgün girdi
sırasıdır; diğer bölümler tam geometri araması, etkin girdi maskesi ve
ilişkilerin iki yönlü bit tablolarıdır.

## Doğrulama ve kapsam

33 test yerel özgün DLL'yi Unicorn'da oracle olarak çalıştırır. Özgün EXE
bulunduğunda vurgu döngüsü de iki sürümle yürütülür; RGB değişimleri, nesne
bağlantıları ve döngü sonundaki register değerleri karşılaştırılır.

Testler sıralama, hücre özellikleri, çift yönlü bağlantılar, stack/register
düzeni, negatif ve taşan koordinatlar, yenilenen render hücreleri ve nesneleri,
değişen geometri, değişen girdi sırası, aynı geometrili yinelenen girdiler,
kasıtlı hash çakışmaları, görünürlük değişimleri, etkin olmayan geometrinin
sıralamadan dışlanması, kapasite büyümesi, liste boyuna geri dönüş, önbellek tahliyesi ve bellek
ayırma başarısızlığını kapsar. 5.000 nesne kapasite sınırı olmadan korunur;
iki Get türünde de 5.000 ardışık arama doğrulanır. Farklı nesil/listeler ve
yabancı çağrılar özgün yola döner.

Özgün EXE/DLL test dosyaları ve kişisel oyun verileri yerel kalır. Çalışma
zamanında assembler, Unicorn veya başka pip bağımlılığı gerekmez.
