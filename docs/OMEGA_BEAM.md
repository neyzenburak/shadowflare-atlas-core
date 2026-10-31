# Warrior özel yetenekleri

Kontrol Masası’ndaki **Özel yetenekler** kartından açılır/kapatılır. Tercih yerelde
saklanır. Yalnızca tek oyunculu oyunda, yaşayan yerel Warrior’da (sınıf 6),
paneller ve hikâye ekranları kapalıyken çalışır. İmleçte eşya olmamalıdır.
Omega veya Meteor seçilir. **Sol Alt + sağ tık** tek kullanım başlatır;
Omega için imlecin bir yaratığın üzerinde olması gerekir. Sağ Alt kullanılmaz;
normal sağ tık, diğer sınıflar, beceri seçimi ve mana değişmez.

Omega uçuşu veya meteor/nükleer düşüşü bitene kadar yeni özel atış başlatılmaz.
Meteorlar ya da başlıklar yere düştüğünde yeni atış hemen açılır; önceki
alevlerin ve mantar bulutlarının kalan 3 saniyeleri bağımsız olarak tamamlanır.
Bekleyen yer efektleri hasar çağrısı yapmaz. Hedef ölürse,
harita/karakter/sınıf değişirse uçuş iptal edilir. Uzun bir takibin ömrü
45 saniyedir. Aç/kapat işlemi devam eden uçuşu iptal eder.
Yetenek veya sürpriz mod değişikliği de devam eden görsel döngüyü iptal eder;
daha önce verilmiş hasar geri alınmaz.

## Meteor yağmuru ve sürpriz mod

Atış anında gerçek oyun görünümündeki canlı yaratıklar seçilir. Güncel
`screen +0x10` görüş dikdörtgeni, `+0x40` kamera kayması ve özgün izdüşüm
ölçeği kullanılır. 1920×900 sabiti yoktur; başka çözünürlükler de desteklenir.
Görüş sınırını kesen küçük gövde payı dahil edilir. NPC, ölü nesne, başka
haritadaki veya ekranın uzağındaki yaratıklar eklenmez. Tekrarlanan liste
bağlantıları aynı hedefi iki kez seçmez.

Her meteor veya nükleer başlık kendi yaratığının kimlik/işaretçi çiftine
bağlıdır. 0,85 saniyelik düşüş boyunca konumu yeniden okunur; hareketli
yaratığın üstüne doğru ilerler. Ölen hedef başka bir yaratığa aktarılmaz.
İsabetten sonra alev veya mantar bulutu dünyadaki çarpışma konumunda 3
saniye kalır ve kamera ile kayar.
Yer efekti uçuş nesnesinden ayrı tutulur; yeni bir atış başladığında önceki
efekt silinmez ve süresi sıfırlanmaz. Harita veya sınıf değiştiğinde temizlenir.

Hasar çarpışmada bir kez Attack ×3’tür. Alev ve mantar bulutu ek hasar
çağrısı yapmaz; üst üste binen alanlar ×2 olmaz. Yakın efektler çizimde
birleştirilebilse de bütün benzersiz hedeflerin hasarı ayrı ayrı uygulanır.
Native işlem en fazla 64 kayıtlık gruplarla yürütülür. Her kayıtta tür,
kimlik, nesne işaretçisi, canlılık ve harita yeniden doğrulanır. Aynı kayıt
çağrıdan önce tüketilmiş olarak işaretlenir; gruptaki mükerrer hedefler
atlanır. Python tarafında da gruplar arasında tekrarlar elenir.

## Rota ve çarpışma

`omega_path.py`, oyunun gerçek isometrik izdüşümünde A* araması yapar.
Sekiz yönlü arama, önceki yönü de durumun parçası olarak saklar: dönüşler
45° veya 90° olur. Düz parçalar birleştirilir. Başlangıç ve hedef arasındaki
kısa son bağlantılar da aynı açı kuralına uyar. Hareketli hedef takip edilir;
yeniden hesaplanan yol, uçmakta olan ışının yönünü devralır.

Zemin verisi gerçek haritanın çarpışma hücrelerinden okunur. Kapı ve diğer
katı sahne nesnelerinin anlık dikdörtgenleri de hesaba katılır. Her kenarın
tamamı örneklenir; yalnızca uç noktalarının boş olması yeterli değildir.
İlerleme sırasında küçük nokta grupları özgün oyun iş parçacığında yeniden
denetlenir: zemin sınırı ve `0x4145b0` çarpışma yolu kullanılır. Açık/geçilebilir
nesne durumu özgün kontrolün sorumluluğundadır.

Oyun tarafından sonradan reddedilen bir nokta rota hesabına geri beslenir.
Bu engelin çevresinde alternatif yol aranır; aynı yanlış rota tekrar tekrar
denenip iki başarısız denemeden sonra iptal edilmez. Yeni engeller için kesit
ile çember kesişimi de kontrol edilir; çok küçük bir engel örnekler arasında
kaybolmaz. Hiç yol yoksa ışın ilk engelin önüne kadar ilerleyip dumanla söner.

Omega artık sabit piksel hızı kullanmaz. Uçuş başladığında bir saniyelik
varış zamanı sabitlenir; kalan mesafe ve kalan süreye göre ilerler. Yeniden
hesaplanan rota bu zamanı sıfırlamaz. Hareketli hedef için arama en fazla
yaklaşık 0,28 saniyede bir yapılır. Son ışık izi 0,15 saniyede söner.
Başarılı çarpışma denetimi olmadan baş ilerletilmez; gerçek kare hızı, son
hedef düzeltmesi veya yeni bir engeli dolaşma süreyi uzatabilir.

## Hasar ve kimlik

Oyunun girdi yolu `0x441cf2` noktasında geçici olarak kancalanır. Özgün
hedef listesinden yaşayan bir yaratık seçilir; kimliği, nesne işaretçisi,
harita ve kaynak karakter bağlanır. Temel Attack yerine ekranda görünen
güncel Attack (`oyuncu +0x1b4`) alınır ve ×3 hesaplanır.

Hasar yalnızca ışın hedefe ulaştığında uygulanır. Hedef kimliği özgün
`0x4299e0` ile yeniden çözülür; tür, işaretçi, canlılık ve mesafe tekrar
doğrulanır. NPC, eski nesne, başka karakter veya haritaya hasar verilemez.
Normal hedef kaybında başka yaratığa aktarılmaz.

Özgün canavar vuruşu `0x459690` çağrılır. Paketin kaynak türü 0 ve kaynak
kimliği oyuncunun yuvasıdır. `paket +0x94 = 1`, `0x412a40` hasar hesabının
özgün sabit hasar yolunu seçer: rastgele çarpan ve savunma indirimi eklemeden
`paket +0x10` değerini döndürür. Böylece hasar tam Attack ×3’tür. Can azsa
normal şekilde sıfıra iner. Can, ölüm, EXP ve drop süreçlerini oyun yürütür.

## Çizim ve yaşam süresi

`0x41ebfd` çizim dalında özgün bayraklar ve her iki dallanma sonucu korunur.
Neon kırmızı gövde, parlak çekirdek, uç kıvılcımları ve çarpışma dumanı
oyunun kendi `RKC_UPDIB::SetPacket` eklemeli DIB çizimine gönderilir.
`RKC_RPGSCRN::CalcRealPos` ve güncel kamera kayması kullanılır; efekt bir
masaüstü kaplaması değildir. Ekran dışındaki parçalar kırpılır.

Omega için 24 küçük DIB, meteor/patlama/alev/nükleer başlık/mantar bulutu için
52 ek DIB kullanılır. Görseller `special_effects.py` içinde prosedürel olarak
üretilir; yeni bir runtime bağımlılığı yoktur. Her görselin boyutu ve bağlama
noktası ayrı bir tabloda tutulur. Çizim, 4.096 kayıt kapasiteli üç tampon
kullanır. Üç kayıt tamponu ve okuyan tamponu bildiren
native protokol, oyun tarafından okunmakta olan koordinatların üzerine yazılmasını
önler. Çizim çağrıları DIB’yi tutabildiği için ayrılmış atlas belleği yardımcı
kapanırken serbest bırakılmaz; oyun süreci bitince Windows geri alır.

Girdi ve çizim kancalarında 2,5 saniyelik yardımcı kalp atışı kontrolü vardır.
Yardımcı kapanırken iki kanca da özgün hâline döner. Kalıcı EXE değişikliği
yapılmaz. Ctrl + tıkla ışınlanma ve Premium/Magic eşya ışınlarıyla ayrı
noktaları kullanır.

## Derleme ve doğrulama

Runtime yalnızca Python standart kitaplığını kullanır. İncelenebilir kaynaklar
`tools/omega_input.asm` ve `tools/omega_render.asm` içindedir.
`python tools/build_omega_beam_plan.py`, geliştirici bağımlılıklarıyla
`app/omega-beam-plan.json` dosyasını üretir. Native işlev parmak izleri ve
DLL çizim işlevleri bağlanmadan önce doğrulanır.

`tests/test_omega_beam.py`, gerçek x86 kodunu iki farklı yükleme adresinde,
özgün DLL izdüşümünü ve sabit hasar hızlı yolunu emülatörde yürütür.
Sınıf/tuş/panel engelleri, hedef kimliği, yalnızca varışta tek vuruş,
çarpışma çağrısı ABI’si, özgün çizim dalları, kapalı oda, engel geri beslemesi
ve hareketli hedefe dönüş test edilir. Frontend testi gerçek aç/kapat olaylarını
ve eski yardımcıda düğmelerin devre dışı kalmasını doğrular.

29 Ekim 2026 canlı testinde Attack 887 iken hedefin canı 10.000 → 7.339 →
4.678 → 2.017 azaldı; her tam vuruş 2.661 hasar verdi, sonraki vuruş hedefi
normal şekilde öldürdü. Kullanıcı kırmızı ışını gördüğünü ve rota düzeltmesinden
sonra daha önce sönmüş olduğu koridorda dolaşıp hedefe ulaştığını doğruladı.
Hareketli hedeflerin son kayıtlarında 90°’yi aşan kırılma bulunmadı.

Aynı gün güncellenmiş sürümde kullanıcı yeni Omega hızını, hareketli
hedefleri izleyen meteorları, 3 saniyelik alevleri ve sürpriz moddaki mantar
bulutlarını doğruladı. Son nükleer kullanımda görüş alanındaki 6 hedefin
6’sı vuruldu; canı yeterli her hedefte hasar 2.661 olarak okundu. 248 test
çalıştırıldı; bir ortam bağımlı test atlandı, diğerleri geçti. Bunlara native grup hasarı,
mükerrer hedefin tek vuruş alması, görünür yaratık seçimi, hedef takibi,
3 saniyelik görsel döngü ve yetenek/checkbox arayüz olayları dahildir.

Yeniden atış güncellemesinin testinde, ilk yer efekti görünürken ikinci
native Alt + sağ tık kabul edilir. Her iki efektin süresi kendi isabetinden
itibaren ölçülür. Eski bulut sönerken yeni bir düşüşün atış kilidini açmaması,
yer efektlerinin ek hasar üretmemesi ve harita/sınıf değişiminde temizlenmesi
de meteor ve sürpriz mod için doğrulanır.
