# Yağmur ve geniş ekran

Arayüz düzeltmesinin v7 sürümü, yağmuru etkin çözünürlüğe uyarlar. Ayrı bir
anahtar gerekmez; **Geniş ekran → Düzeltmeyi uygula** ile birlikte açılır.
Oyunun mevcut yağmuru kullanılır: haritanın hava koşulu, renk, hız, açı ve
çizgi uzunluğu korunur. Yağmursuz haritaya yağmur eklenmez.

Özgün `0x41fe20` yordamı damlaları `rand() % 1000 - 180` aralığında üretir;
damlanın Y konumu 479'a ulaşınca düğümü serbest bırakır. Geniş ekran yaması
dünyayı büyütse de bu sabitler aynı kalmıştır. Damlalar sola eğildiğinden,
ekranın sağına doğanların da aşağı inerken görünür alana girmesi gerekir.

Yeni yatay pay `ceil(180 × yükseklik / 480)`, üretim genişliği
`ekran genişliği + 2 × pay`, silinme eşiği `yükseklik - 1` olur. 640×480'de
üçü de özgün değerleridir. 1920×900'de pay 338, üretim genişliği 2596 olur.
Doğum sayısı bu genişliğin 1000'e oranıyla çarpılır. Kesirli kalan sonraki
kareye aktarılır; böylece yağmur geniş ekranda seyrelmez. Yüksekliğin etkisi
damlaların uzayan ömründen gelir; doğum sayısı ayrıca yükseklikle çarpılmaz.

Yama fonksiyon girişinden çağrıyı sarar. Özgün döngü her doğumda yoğunluk
alanını tekrar okuduğu için alan çağrı süresince ölçeklenir, dönüşten önce
eski değeri geri yüklenir. Yordamın iki argümanı, dönüş değeri ve koruması
gereken yazmaçlar korunur. Yağmur kapanınca yeni doğum yapılmaz; mevcut
damlalar özgün yöntemle silinir. Oyun EXE/DLL dosyaları değiştirilmez.

Geri alma, kod baytlarını doğrular. Yağmur çağrısı hâlâ sürüyorsa dönüşte
kullanılacak küçük yama alanı oyun kapanana kadar tutulur. Böylece dönüş
adresi serbest bırakılmış belleğe işaret etmez.

`tests/test_rain_fix.py` özgün x86 kodunu Unicorn ile çalıştırır:

- 640×480'de aynı rastgele sayı dizisi, düğümler ve çizim paketleri;
- 640×480–7680×4320 aralığındaki altı çözünürlükte rüzgâr payı ve sağ alt kapsama;
- 1000 karede kesirli üretimin tam toplamı, durma ve yoğunluk değişimi;
- eski alt sınırı geçen damlanın yaşaması ve yeni sınırda serbest bırakılması;
- özgün `RKC_UPDIB` ve `RKC_DIB` ile 1920×900'ün sağ alt bölgesine gerçek çizgi çizimi;
- yeni yamaların tam komut sınırları ve içlerine atlayan dal bulunmaması;
- çağrı sürerken geri alındığında dönüşün tamamlanması ve boşta belleğin serbest bırakılması.

EXE/DLL test dosyaları depoda bulunmaz. `SHADOWFLARE_FIXTURE_DIR`, bu dosyaların
yerel kopyasını içeren dizine ayarlanabilir.
