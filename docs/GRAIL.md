# Premium Chronicle · v2

Grail, `rarity == 2` olan 457 ayrı katalog kimliğini kapsar. Aynı adlı farklı
kimlikler ayrı kayıttır. Oyun ve save dosyaları değiştirilmez. Yerel yardımcı
açıkken tek oyunculu karakterin başarılı yerden çantaya transferleri izlenir.

Katalogdaki 456 Premium, yaratıkların bağlı olduğu standart drop havuzlarında
pozitif nominal olasılığa sahiptir. Gamble Boots bu havuzlarda bulunmaz;
kartında işaretlenir ve **Standart mob havuzunda yok** filtresiyle görülebilir.
Bu, görev veya özel ödül yollarından da elde edilemeyeceği anlamına gelmez.

## Elde edilen bilginin anlamı

- **Yerden toplandı:** Takip açıkken oyun çantaya eklemeyi tamamladı. İlk
  toplama zamanı, bölge ve sonraki toplama sayısı SQLite'a kaydedilir. Satmak,
  yere bırakmak veya karakterden çıkmak geçmiş kaydı silmez.
- **Takip öncesinde mevcut:** İlk save okumasındaki ekipman/çanta veya bu
  karaktere ilk canlı bağlanmadaki ekipman/çanta/depo taramasında görüldü.
  Tarih, hangi yaratıktan düştüğü ve satın alınıp alınmadığı çıkarılmaz.
- **Elle işaretlendi:** Kullanıcı geçmiş bir buluntuyu hatırladığı için Buldum'a
  bastı. Bu işaret geri alınabilir; otomatik toplama kanıtını silmez.
- **Kaydı yok:** Günlüğün kanıtı yoktur. Eşyanın geçmişte hiç düşmediği sonucu
  çıkarılamaz. Eski satılan eşyaların tam geçmişi save eşya listesinden bulunamaz.

İlerleme, bu üç kanıt türünün birleşimidir; aynı eşya bir kere sayılır.
Mevcut veya elle işaretli eşya sonradan toplanırsa tarih ve toplama sayısı
eklenir, toplam tekrar artmaz. Yeni grail bildirimi Atlas sayfasında gösterilir;
oyun içi tooltip veya identify sistemi değiştirilmez.

## Save okuması ve karakter ayrımı

`ShadowFlare0005` biçimi salt okunur çözülür. Açık karakter başlığından sonra
gövde boyutu, XOR anahtarı ve signed-byte sağlama toplamı gelir. Gövde önce
256 baytlık native ters dönüşüm tablosuyla açılır, sonra XOR uygulanır.
Sağlama toplamı, boyut ve yinelenen karakter başlığı kontrol edilir.
11 ekipman alanı ve ana çanta kayıtları, boyut alanlarına göre okunur; dosyada
eşya kimlikleri aranarak tahmin yapılmaz. Devam eden autosave'in eksik veya
tutarsız okunması listeye aktarılmaz; sonraki tarama beklenir.

Profil kimliği oyun klasörü + save yuvası + karakter adından türetilir. Aynı
adlı farklı save'ler ayrıdır. Aynı yuvayı aynı adla yeni karakter için yeniden
kullanmak eski profili paylaşır; oyunda doğrulanmış kalıcı karakter GUID'si
bulunmadığından böyle bir yeniden oluşturmayı otomatik ayırma iddiası yoktur.
Kayıt yuvası/adı değiştirilirse ayrı profil oluşur. Açık karakterin save dosyası,
oyunun kendi aktif dosya nesnesinden alınır; benzer isimle eşleme yapılmaz.

## Native gözlem

`grail_native.py` üç doğrulanmış girişe geri alınabilir detour yerleştirir:

1. `0x449ef0`: Yerden toplama. Gerçek dünya nesne kimliği, tek oyunculu mod,
   boş imleç ve Premium sınıfı doğrulanınca bekleyen eşya/karakter kimliği
   özel alana alınır. Özgün işlev çalışır. Başarısız dönüşte bekleyen işaret
   temizlenir. İmleçte başka eşya varken başarısız ikinci tıklama öncekinin
   bekleyen kaydını bozmaz.
2. `0x466bc0`: Özgün listeye ekleme talimatları aynen yürütülür. Eklenen nesne
   bekleyen yerden toplama nesnesiyse ve hedef tam olarak bu karakterin ana
   çantasıysa olay yayımlanır. Envanter açıkken imleçte tutma olay oluşturmaz;
   sonradan çantaya yerleştirme oluşturur. Doğrudan depoya koyma sayılmaz.
3. `0x465640`: İmleçteki bekleyen nesne silinirse işaret temizlenir. Böylece
   yeniden kullanılan bellek adresi bir alışverişi toplama gibi gösteremez.

Satın alma, ödülün doğrudan çantaya eklenmesi, tam çanta nedeniyle başarısız
tıklama ve Premium olmayan eşyalar yeni toplama kaydı üretmez. Elle oluşturulup
**yere bırakılan** bir eşyanın sonradan toplanması da yerden toplamadır; sistem
bir eşyanın ilk kez hangi düşmandan üretildiğini kanıtlamaz.

Küçük native kayıtlar önce tamamlanır, sonra sıra numarası yayımlanır. Python
yaklaşık 250 ms'de bir bunları kalıcı günlüğe geçirir. 2.048 olaylık halka,
ganimet/eşya sınırı değildir. Tüketici bu halkayı aşacak kadar gecikirse kayıp
sayısı kalıcı olarak saklanır ve arayüzde gösterilir. Takip yardımcının kapalı
olduğu zamanı geriye dönük dolduramaz. Kapatılırken girişler geri alınır,
tamamlanan olaylar boşaltılır, devam eden çağrı ve komut işaretçileri güvenli
duruma gelince özel bellek serbest bırakılır.

Sağ tıkla satış aynı silme işlevini doğrular. `Grail.original_bytes`, yalnızca
kendi kurulu detour baytları hâlâ birebir eşleşiyorsa özgün görünümü sağlar;
QuickSell'in SHA-256 kontrolleri bu görünümde çalışır. Başka bir yama gizlenmez.

## Saklama ve arayüz

v2, drop filtresi ve kırmızı ışın için karaktere bağlı ortak bir native tablo
yayınlar. Arayüzde gezilen başka profil bu tabloyu değiştirmez. Gerçek yerel
oyuncu, ad ve save yolu her okumada doğrulanır; karakter değişimindeki eski
tablo kullanılmaz. Veriler yalnızca değişince oyun kısa süre duraklatılarak
yayınlanır. Bu sırada bekleyen toplama olayları yeniden boşaltılır; henüz
Python’a aktarılmamış bir başarılı toplamanın işareti kaybolmaz.

Başarılı çanta ekleme hook’u, günlük halkasına yazdıktan hemen sonra ilgili
tablo kaydını da bulunmuş yapar. İmleçte tutmak, başarısız toplama, depo veya
satıcı işlemi bu işareti oluşturmaz. Böylece tekrar filtresi ve yerdeki diğer
kopyaların kırmızı işareti aynı oyun çağrısından sonra güncellenebilir.
Bağımlı drop/ışın hook’ları kapatılmadan ortak Grail belleği serbest bırakılmaz.

Veri: `app/grail-data/chronicle.sqlite3`. İşlemler transaction kullanır; DB
bağlantıları her işlemde kapatılır. Bu klasör, kayıt yedekleri ve native oturum
manifestleri Git'e ve dağıtım ZIP'ine dahil edilmez. **Günlüğü indir**, seçili
profilin kanıt alanlarını JSON olarak indirir. Oyun görselleri mevcut yerel
Atlas ikonlarıdır. Arama, kategori/durum filtresi, seviye/isim/tarih sıralaması,
48 kartlık sayfalama, karakter seçimi ve açık karakteri otomatik takip vardır.

## Doğrulama

14 grail testi: özgün EXE'de gerçek toplama dalı, yer bulma, listeye ekleme ve
silme kodları Unicorn'da yürütülür. UI/ses ve harita çıkarma bağımlılıkları test
nesneleriyle sağlanır. Başarı, dolu çanta, imleçten yerleştirme, ikinci başarısız
tıklama, satıcı/ödül istisnaları, nesne adresinin yeniden kullanılması, depo,
halka sarılması, QuickSell ile birlikte satış ve özgün SHA denetimleri kapsanır.
Saf veri testleri profil ayrımı, kalıcılık, tekrar sayımı, elle işaretin geri
alınması, save çözümü ve bozuk save reddini kapsar.

23 Ekim 2026 canlı doğrulaması: açık karakterin Bloody No-Mask eşyasını
yerden çantaya alması kaydedildi; tarih/bölge/kimlik ve bir toplama doğrulandı.
Önceden mevcut olduğu için toplam koleksiyon sayısı artmadı. Arayüzde karakter
değiştirme, arama, elle işaretleme/geri alma ve gerçek JSON indirme doğrulandı.
Günlük, yardımcı yeniden başlatıldıktan sonra da korunur.
Sonrasında Knuckle Breaker ilk kez toplandı; Cold Ruins bölgesi ve toplama
zamanı kaydedildi, toplam 3/457 oldu ve Atlas'ta gerçek ilk-buluntu bildirimi
göründü. Böylece hem mevcut eşyanın yeniden toplanması hem yeni kayıt ve
bildirim yolu canlı oyunda doğrulandı.
