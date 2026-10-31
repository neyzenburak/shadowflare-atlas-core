# AI kapalı yaratık doğurma

Drop Atlas'ta bir yaratık ve görünüm/drop varyantı seç. Görselin altındaki
**Adet** alanına 1–2000 arasında tam sayı yazıp **Seçili yaratığı yanıma doğur**
düğmesine bas. Oyuna dön; istek oyun döngüsünde tamamlanır. Bir istekteki bütün
yaratıklar aynı dünya koordinatında, iç içe yerleştirilir.

**Son doğurduğum grubu kaldır**, yalnızca son isteğin yaratıklarını ganimet ve
deneyim üretmeden geri alır. Normal yaratıklara dokunmaz. Grup zaten yoksa
eksik örnekler atlanır. İlgili canlılık/etkileşim kayıtları da temizlenir;
mevcut görev bayrakları korunur.

2000 adedin kod testini geçmesi, oyunda akıcı çizileceği anlamına gelmez.
Canlı denemede 2000 Dread Raptor ciddi yavaşlamaya yol açtı; son grup geri
alındığında 5 saniyelik ölçüm 29,8 FPS ve 50 ms üstünde sıfır kare verdi.
Küçük adetlerle başla; 2000 bir performans garantisi değildir.

İlk nokta, karakterin yakınında yaratığın gerçek gövdesinin sığdığı yürünebilir
zeminde aranır. Sonraki örnekler aynı noktayı paylaşır. Her birinin kimliği,
canı, isabet kaydı ve ölümü ayrıdır. Seçili senaryo varyantının canı, seviyesi,
görünümü, parça renkleri ve drop grubu kullanılır. Ölümde etkin drop çarpanı ve
Grail filtresi dahil mevcut ganimet kuralları çalışır.

Canlıyken yürümez ve saldırmaz. Hasar, hedefleme, ölüm animasyonu, ganimet ve
nesnenin temizlenmesi oyunun özgün yollarını kullanır. Diğer yaratıkların AI'ı
değişmez. Doğurulan yaratıklar kalıcı bir harita düzenlemesi değildir.

## Uygulama

- `mob_spawn.py`, Atlas örneğini özgün `Scenario.Mct` kaydıyla doğrular.
  79 alanlı kaynak özellikleri, özgün yükleyicinin 72 alanlı düzenine çevrilir.
- Görünümde etkin parça maskeleri ve RGB çarpanları korunur. Kaynak animasyon
  dizilerinin uzunluğu ile modelin kullandığı gerçek parça sayısı ayrıdır.
- Ana oyun iş parçacığında özgün nesne fabrikası, ortak kurucu, özellik
  yükleyici ve ad yükleyici çağrılır. Her örnek için yeni, boş bir kimlik alınır.
- Canlı düşman tablosuna ve üç etkileşim bayrağına sıralı kayıt eklenir.
  Mevcut görev ve yaratık kayıtlarının bütün alanları korunur. Dizilerin belleği
  oyunun kendi ayırıcısıyla ayrılır; özgün harita temizleyicisi tarafından salınır.
- Yalnızca yeni örneğin sanal yöntem tablosundaki güncelleme işlevi değiştirilir.
  Boşta çizim/animasyon çalışır; boşta animasyondaki üç saldırı üretimi kaldırılır.
  Can sıfır olduğunda özgün ölüm güncellemesine dönülür.
- `+34c` etkinlik alanı sıfırdır: özgün mermi kodu aksi halde görünür hedefi
  atlar. `+34` kaynak etiket yüksekliğidir; ad ve can çubuğu ayakta kalmaz.
- Geçici istek yönlendirmesi kaldırılıp belleği serbest bırakılır. Ortak pasif
  davranış sayfası, örneklerin dönüş adresleri geçerli kalsın diye oyun kapanana
  kadar tutulur. Yardımcı yeniden açıldığında doğrulanmış sayfa tekrar kullanılır.

Adet sınırı hem HTML hem sunucu tarafında doğrulanır. Kısmen tamamlanan bir
istekte gerçek oluşturulan adet bildirilir; otomatik tekrar gönderilmez.
Oturum kayıtları `app/mob-spawn-sessions/` altındadır; Git'e ve ZIP'e eklenmez.

## Kontroller

`tests/test_mob_spawn.py`, x86 kodunu Unicorn'da çalıştırır: fabrika çağrı
sırası, zemin reddi, kimlik çakışması, etkileşim kayıtlarının korunması, özgün
özellik dönüşümü, parça renkleri, pasif güncelleme, ölüm geçişi ve aynı noktada
2000 ayrı örnek. Özgün EXE fikstürü varsa planın kod özetleri de doğrulanır.
