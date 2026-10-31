# Yerdeki ganimet görünürlüğü ve satış

Kontrol Masası’ndaki **Beyaz / mavi ganimet** kartında iki ayrı işlem var:

- **Gizle / Göster:** yerdeki Plain ve Magic silah, zırh ve aksesuarları geçici
  olarak gizler. Premium, tüketilebilirler, Mine, altın ve özel eşya türleri
  görünür kalır. Görünmeyen ekipman fare seçimini engellemez; tekrar gösterince
  aynı eşya geri görünür. Magic ışını da bu görünürlük seçimine uyar.
- **Yerdeki beyaz ve mavileri sat:** mevcut haritanın bütün uygun ekipmanını
  oyunun teşhis edilmemiş satış bedelinden altına çevirir. **İşlemden önce
  kaydet** seçiliyse güncel karakter kaydedilir ve Save klasörü yedeklenir. Altın karakterin ayağına
  bırakılır ve elle alınır. Bu işlem kalıcıdır.

Kayıt kutucuğu varsayılan olarak kapalıdır. Seçim tarayıcıda hatırlanır;
haritaya ışınlanmanın kayıt seçimi ayrıdır. Kutucuk kapalıyken Atlas’ın ön
kayıt/yedek adımı atlanır. Seviye düşürme gibi diğer özelliklerin kayıt davranışı
bu seçenekle değişmez.

## Native uygulama

`458a1c` yerdeki eşya nesnesinin sprite paketini hazırlamaya başladığı noktadır.
Gizleme, kategori 0–2 / kalite 0–1 için bu paketi atlayıp `458cc3` ortak
güncellemesine devam eder. Konum, animasyon fiziği, bağlı listeler ve kayıt
verisi değişmez. Envanter ve satıcı çizimi ayrı işlevlerde çalışır. Native fare
sorgusu çizim paketlerinden dünya kimliklerini alır; gizlenen nesnenin paketi
üretilmediğinden Premium’un önünde seçim hedefi oluşturmaz.

Satış isteği `443490` üzerindeki mevcut tek seferlik oyun iş parçacığı
mekanizmasını kullanır. Her aday, dünya kimliğiyle `4299e0` üzerinden tekrar
bulunur; eşya işaretçisi, harita, kategori ve kalite yeniden doğrulanır.
Teşhis bayrağı aynı native çağrı içinde geçici olarak 0 yapılır; `4661c0(1)`
satıcı bedelini hesaplar, ardından özgün bayrak geri konur. Premium elenmesi
bu hesaplamadan önce yapılır.

Toplam 64 bitte tutulur. Gerekli altın nesnelerinin **tamamı**, ekipman
silinmeden önce oyun fabrikasından ayrılır. Ayırma başarısızsa ayrılan nesneler
serbest bırakılır; ekipmanlar yerinde kalır. Native `427a00` yerden ayırır,
`465640` eşya bankasından siler. Başarılı satışların tutarı kadar altın,
`466440` / `4663e0` / `427970` ile normal altın nesneleri olarak yere konur.
Kese başına en fazla 2.147.483.647; kalan tutar ek keseye çıkar.

Grail’in eşya silme çağrısındaki bilinen detour’u, kendi doğrulanmış özgün
bayt okuyucusuyla hesaba katılır; yabancı değişiklikler SHA kontrolünü geçmez.
İstek boyunca otomatik toplama duraklar. Satış altınının istisna tablosu
yayımlandıktan sonra önceki toplama ayarı geri döner. Belirsiz sonuç veya
yayımlanamayan altın istisnasında otomatik toplama kapatılır.

## Satış altınının elle alınması

`sale-gold-ledger.json` yerel karakter/kayıt dosyası, harita, konum ve tutar
kaydını tutar. Native otomatik toplama ayrı bir tabloyu okur; kayıt ilk
eşleşmede canlı dünya kimliğine bağlanır. Aynı adresi alan farklı nesne
istisnayı devralmaz. Yeni oyun sürecinde konum/tutar eşleşmesi yeniden
bağlanabilir. Altının kendi kayıt biçimi değiştirilmez. Dosya GitHub’a ve
dağıtım ZIP’ine girmez; mevcut yerel klasörde tutulur.

## Doğrulama

`tests/test_ground_loot.py`, üretilmiş x86 kodunu Unicorn’da özgün EXE ile
çalıştırır: çizim paketi ve fare kimliği, eşdeğer fizik, native satış bedeli,
teşhis bayrağının korunması, Premium/tüketilebilir ayrımı, fabrika hatasında
geri alma, 32 bit üstü toplamlar, 1.500 eşyalık yığın ve elle alınacak altın
ayrımı test edilir. Işın ve gerçek frontend kontrol testleri de bu seçeneği
kapsar. Assembly kaynakları `tools/native/ground_loot.asm` ve
`tools/native/loot_qol.asm`; üretim için `tools/build_ground_loot.py` ve
`tools/build_loot_qol.py` kullanılır. Çalışan yardımcı ek pip paketi istemez.
`test_operation_save.py` kayıt seçiminin her iki işlemde gerçek kayıt çağrısına
ulaşmasını, kapalıyken atlanmasını ve salt okunur teşhiste kayıt yapılmamasını doğrular.
