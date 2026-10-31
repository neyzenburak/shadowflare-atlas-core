# Sağ tıkla satış · v1

Satıcı ve envanter açıkken çantadaki eşyaya sağ tık, oyunun özgün satış
işlemini çalıştırır. **Canlı kontrol → Sağ tıkla sat** paneli açma, kapama ve
bu etkinleştirmeden beri tamamlanan satış sayısını gösterir. Yardımcı ilk
açılışta özelliği etkinleştirir; `--no-quick-sell` ile kapalı başlatılabilir.
Çalışan yardımcının yeniden başlatılması açık/kapalı tercihini korur.

## İşlem

- `0x445a7b` konumundaki envanter sağ tık çağrısı sarılır. Satıcı kapalıysa,
  çanta gizliyse, elde taşınan eşya varsa veya hedef çanta hücresi değilse
  özgün `0x44a6f0` işleyicisi çalışır. Çok oyunculu modda kısayol uygulanmaz.
- Hücreyi özgün `0x447290` hit testi bulur. Mevcut geniş ekran düzeltmesinin
  koordinat dönüşümü kullanılır; sabit ekran çözünürlüğü varsayılmaz.
- `0x466b00` çok hücreli eşyanın gerçek kaydını seçer. Eşya çanta listesinden
  geçici ayrılır ve oyunun elde tutulan eşya alanına yerleştirilir.
- `0x44831c` özgün satıcı satış dalı, kendi yığın çerçevesiyle çağrılır.
  Satılabilirlik, normal/satış fiyatları, altın ekleme ve kapasite kontrolü,
  bildirim ve eşya silme bu dalın kendi çağrılarıdır.
- Oyun satışı reddederse özgün liste bağlantısı ve boş imleç geri yüklenir.
  Eşyanın koordinatları ve listedeki sırası korunur. Satılamayan altın kesesine
  veya fiyatı olmayan eşyaya sağ tık, eşya kullanmaya dönüşmez.

Satıcının kendi sağ tıkla satın alma işleyicisi `0x44b020` değiştirilmez.
Takılı ekipman, özel eşya alanı ve Mine alanı satış kısayoluna dahil değildir.
Satış fiyatı sabitlenmez; mevcut trainer fiyat değişiklikleri de özgün işlevden
geçer. Oyun EXE dosyası değiştirilmez.

## Yaşam döngüsü

Kurulumdan önce çağrı ve ilgili özgün işlevlerin baytları doğrulanır ve kayıt
yedeği alınır. Yerel `app/quick-sell-sessions/` manifesti önceki/yeni çağrıyı,
kod alanını ve yedeği kaydeder. Kapatma önce özgün çağrıyı geri getirir; kod
alanı ancak devam eden çağrı kalmadığında ve hiçbir iş parçacığının komut
işaretçisi bu alanda olmadığında serbest bırakılır. Yeni oyun sürecine otomatik
yeniden bağlanılır. Yama tek oyunculu, doğrulanmış v2.004 içindir.

## Doğrulama

`tests/test_quick_sell.py` içindeki 10 Unicorn testi, yerel özgün EXE'nin satış
dalını, liste işlemlerini, hit testini, altın ekleme ve silme işlevlerini yürütür.
Doğrudan sürükleyerek satış sonucu ile kısayolun envanter, altın, silme ve
bildirim sonuçları karşılaştırılır. Fiyat tablosu, bildirim kuyruğu ve test
nesnelerinin oluşturulması/silinmesi test bağımlılıklarıyla sağlanır.

Kapsam: 640/1024/1366/1920 genişlikleri; çok hücreli eşyanın bütün hücreleri;
altın kesesinin dolup yeni kese açılması; dolu çantada altın sığmadığı için
reddedilme ve birebir geri alma; satılamayan eşya ve altın; özgün sıfır satış
fiyatı davranışı; boş hücre ve modal pencere; satıcı/çanta kapalı, elde eşya,
çok oyunculu mod ve ekipman/özel alan için özgün işleyiciye dönüş; art arda
tıklamalar. Yığın dengesi ve korunması gereken kayıtçılar da kontrol edilir.

23 Ekim 2026 canlı doğrulamasında kullanıcı sağ tıkla satışı doğruladı. İlk
sonuçta 13 satış tamamlandı; altın 8.737'den 10.002'ye çıktı ve imleçte eşya
kalmadı. Arayüzde Kapat/Aç işlemleri de doğrulandı; tekrar açıldıktan sonra
kullanıcı 4 eşya daha sattı. Yeni 10 test ve mevcut 33 performans testi geçti.
Otomatik testler başarılı satışları ve reddedilmeyi kapsar; canlı kontrol
kullanıcının mevcut satıcısında yapıldı.
