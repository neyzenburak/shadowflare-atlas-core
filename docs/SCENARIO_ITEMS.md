# Misc / Special / Scenario Items

Atlas’ın beşinci sekmesi. Çevrimdışı çalışır; oyuna bağlanmaz, görev veya save
durumu değiştirmez. Harita düğmeleri Atlas’ın gerçek oyun haritasını açar.
Oyunda yolculuk için Haritalar’daki mevcut girişe ışınlanma düğmesi kullanılabilir.

## Kapsam

- 39 kayıt: on tüketilebilir ve `4:99000000–99000028` aralığındaki 29 özel eşya.
- 15 eşya türünün 12 haritada toplam 84 hazır konumu.
- Dört kart takası; gereken malzemenin konumuna ve NPC’nin haritasına bağlantılar.
- Dört koruyucu grubu yenildikten sonra oluşan senaryo ödülü.
- Dorojan’ın panzehir diyaloğu ve Barshival’in emanet teslim paketi.
- Standart yaratık tablolarındaki özel eşya kaynakları ve açık NPC teslim dalları.
- White Cloth, Red Thread ve Silver Needle: edinme yolu doğrulanmadı.
  Mrs. Morris’in bu eşyaları teslim alan dalı ayrıca gösterilir. “Kullanılmıyor”
  veya “beta eşyası” sonucu çıkarılmaz.

Arama eşya/NPC/harita adlarını ve takas malzemesinin haritasını kapsar.
Kaynak türü ve eşya türüyle filtrelenir. Aynı eşyanın farklı edinme yolları
ayrı adımlar olarak gösterilir. Atlas eşya panelinden rehbere dönüş bağlantısı var.

## Doğrulanan tetikleyiciler

Kart konuşmaları **32 numaralı “Jurg’u durdur” görevinin tamamlanmasını** ister.
Üzerinde aynı kartın bulunması konuşma dalını değiştirir. Takasta bir malzeme
alınır; kart NPC’nin **o anki** X + 200 / Y konumuna bırakılır. İşaret, NPC’nin
başlangıç konumudur; NPC hareket edebilir.

| Kart | NPC | NPC haritası | Malzeme | Malzemenin hazır haritası |
|---|---|---|---|---|
| Jack | Oscar | Town of Losmans | Mandragora | Lunafuld Beach |
| Queen | Quina | Ponse, Village of Dwarves | Akebi Fruit | Gungstonwald |
| King | Buzzed | A Town of Antalusia | Vitality Source | Ruins of Carn |
| Joker | Barmera | Town of Calado | Mental Source | Coldea Cave |

| Senaryo ödülü | Harita | Yenilmesi gereken koruyucular |
|---|---|---|
| Angel’s Nail | Dragon Cave | Magic Dragon ×2, Saint Dragon |
| Silver Orb | The Ruins of Lukuna | Dark Lesser Demon |
| Gold Orb | The Ruins of Zeres | Lightning Lesser Demon |
| Tears of Oberon | Dark Elves Hiding Place | Flame / Water / Earth / Lightning / Dark Crimson |

Ödüller koruyucuların standart drop havuzundan gelmez. Senaryo, koruyucu
grubunda etkin aktör kalmadığını kontrol edip eşyayı sandığın konumunda üretir.
Aynı ödülün tekrar oluşmasını ayrı bir senaryo durumuyla önler.

Dorojan, zehirlenme hikâyesindeki panzehir görevinde Ponero Cave’den getirilen
Fruit of Poreno karşılığında Antidote verir. Barshival ise 37 numaralı
“Kutsal emanetleri Aziz Sena’ya götür” görevini başlatırken üç emaneti doğrudan
özel eşya alanına koyar. Bunlar erken oyunda koşulsuz eşya alma yöntemleri değildir.

## Veri ve koordinatlar

`tools/build_scenario_items.py` 209 MCT ve 209 SCS dosyasını sınır/EOF
kontrolüyle okur. Elle açıklanan ödül komutlarını, NPC referanslarını, görev 32
koşulunu ve sayısal Table.Tbd gruplarını kontrol eder; tanımadığı biçimde durur.
NPC’nin `DELETEITEM` komutu edinme değil **kullanım/teslim** bağlantısıdır.
Bu bağlantılar ayrı tutulur. MCT/SCS dosyalarının SHA-256 değerleri veriyle saklanır.

Haritadaki işaretler yerel dünya koordinatlarından oyunun dönüşümüyle hesaplanır:
`screenX = trunc((X-Y)*15/100)`, `screenY = trunc((X+Y)*10/100)`.
Negatif değerlerde C’nin sıfıra doğru bölmesi korunur. Yaratık ve çevre çizimi
değişmez; işaretler yalnızca Atlas haritasına eklenen bir katmandır.

```powershell
python tools/build_scenario_items.py --game '\\KEENETIC-7191\WinToUSB\ShadowFlare'
node tests/test_scenario_items.cjs
# DOM testi için jsdom geliştirme bağımlılığı gerekir:
node tests/test_scenario_page.cjs
```

Üretilen `app/assets/scenario-items.js` oyun verisidir: özel Git deposunda
tutulmaz; yerel ZIP’e dahil edilir ve mevcut asset aktarımıyla taşınır.
Derleme oyun dosyalarını, save’i ve canlı yardımcı ayarlarını değiştirmez.
