# Ctrl + sol tıkla ışınlanma

24 Ekim 2026'da v2 açık oyunda doğrulandı: oyuncu boş zemine ışınlanıldığını
ve duvarın reddedildiğini doğruladı. İlk sürümde kapanmış metin penceresinin
giriş türü açık pencere sanılıyordu; v2 gerçek pencere bayraklarını kullanır.
Bu durum ayrıca bir regresyon testiyle korunur.

**Canlı kontrol → Ctrl + tıkla ışınlan** panelinden açılır ve kapatılır. Ayar
yerelde saklanır. Tek oyunculu oyunda, bütün oyun panelleri kapalıyken Ctrl
basılı tutularak zemine sol tıklanır. Her basış bir kez çalışır; fareyi basılı
tutup sürüklemek ardışık ışınlanma oluşturmaz.

Envanter, durum, beceri, harita, satıcı, diyalog, adet penceresi ve hikâye ekranı
etkin olduğunda özgün giriş işleyicisi kullanılır. HUD üzerindeki tıklamalar,
normal sol tık ve sağ tık korunur. Elde eşya varken çalışmaz.

Hedef, oyunun özgün kamera ofsetleri ve `CalcWorldPos` dönüşümüyle bulunur.
Karakterin ayak dikdörtgeninin kapladığı bütün hücreler canlı zemin verisinden
kontrol edilir; harita dışı ve engelli hücreler reddedilir. Ardından yürüyüşün
kullandığı `0x4145b0` çarpışma yordamı sahne nesneleriyle karakterleri de denetler.
Aradaki yolun açık olması aranmaz; yalnızca hedefte durulabilir olması gerekir.

Başarıda konum değiştirilir; özgün `0x44e960(1)` konum geçmişini yeniler ve
`0x4542f0` eski yürüyüş hedefini sıfırlar. Hareket durumu beklemeye döner.
Kamera ve karakter çizimini oyunun normal güncellemesi yapar. Reddedilen hedef
karakteri hareket ettirmez.

Yalnızca `0x443571` çağrısı değiştirilir; hedef, özgün `0x441c00` giriş
işleyicisidir. Doğrulanmış tam komut sınırındaki bu beş baytlık çağrı, paket
ve satıcı kısayollarının yamalarıyla çakışmaz. Yordamlar hash ile denetlenir.
Kapatmada özgün çağrı geri yüklenir; süren çağrı tamamlanmadan yama belleği
serbest bırakılmaz. EXE/DLL dosyaları değiştirilmez.

`tests/test_ctrl_teleport.py` x86 kodunu çalıştırır. Özgün koordinat dönüşümü,
konum geçmişi, yürüyüş sıfırlama ve çarpışma yordamları test edilir. Dört
çözünürlük, negatif koordinatlar, kamera ofseti, karakterin kenarında kalan
engeller, harita sınırları, bütün panel bayrakları, HUD, kapatma ve basılı tutma
durumları kapsanır. Özgün EXE ve `RKC_RPGSCRN.dll` yerel test dosyalarıdır.

## Oyun açıkken kayıt

Kimliği doğrulanmış yerel `POST /api/live/save`, özgün `0x44b580` kayıt yordamını
seçili karakterin oyun iş parçacığında bir kez çalıştırır. Oyun kapanmaz.
Tamamlanan dosya karakter adı, seviye, boyut ve sağlama toplamıyla doğrulanır;
sonra karakter dosyaları ve harita keşif maskeleri yerel yedeğe kopyalanır.
Önceki kayıt da işlemden önce ayrıca yedeklenir. Bu yöntem dosya biçimini
yeniden üretmez; oyunun kendi kayıt biçimini ve mevcut yığın değerlerini kullanır.
