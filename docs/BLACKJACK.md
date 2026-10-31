# Her elde Blackjack · K + A

**Kontrol Masası → Trainer → Hileler** altında açılır/kapanır. Trainer aramasına
`blackjack` yazabilirsin. Açıldıktan sonra **yeni bir el başlat**; ilk iki oyuncu
kartı sırasıyla **King ve Ace** olur. Kapatılınca normal dağıtım geri gelir.

Oyunun 17. ve 22. kule katındaki iki blackjack konuşması aynı dağıtıcıyı
kullandığından ikisinde de geçerlidir. Bahis, devam etme, galibiyet serisi ve
eşya/depo ödülü oyunun kendi akışıyla yürür. İki taraf da iki kartla 21 bulursa
beraberlik sayılır. Bu seçenek mevcut bir elin açılmış kartlarını değiştirmez.

## Uygulama

- `blackjack.py`, `40361C` adresindeki yedi baytlık komut sınırına geçici bir
  yönlendirme kurar. Oyunun EXE veya senaryo dosyaları değiştirilmez.
- Yalnızca `48D7F0` blackjack nesnesinin **oyuncu** elindeki ilk iki çekiliş
  değiştirilir. Krupiye, sonraki kartlar ve başka nesneler özgün yolu kullanır.
- Kart adayının rengi korunur; aynı kartın iki kez gelmesini engelleyen özgün
  kontrol gerekirse yeni renk çeker. Joker adayı, geçerli bir K/A rengine çevrilir.
- Kapalı kart işareti, kart sayıları, As’ın 1/11 hesabı ve sonuç karşılaştırması
  oyunun özgün kodunda kalır. Genel rastgele sayı üreteci yamalanmaz.
- Etkinleştirmeden önce dağıtıcı, sıfırlama, puan/sonuç ve betik girişlerinin
  SHA-256 değerleri kontrol edilir. Farklı kod varsa üzerine yazılmaz.
- Trainer’ın mevcut yedekleme, işlem kilidi, kod uygulama ve geri alma yolunu
  kullanır. Trainer reseti veya yardımcının normal kapanışı özgün kodu geri yükler.

Özgün Cheat Engine kayıtları değişmez; ek kayıt `trainer-extras.js` içinde ayrı
tutulur. Denetim, Trainer API sürümü 2’den eski yardımcıda etkinleşmez.

## Kontroller

`tests/test_blackjack.py` özgün EXE’nin gerçek x86 dağıtım, puanlama ve sonuç
işlevlerini Unicorn’da çalıştırır. 128 başlangıç eli, kart tekilliği, renk
çakışmasında yeniden çekme, Joker, kapalı kart, sonraki çekiliş, başka nesne,
beraberlik, kapatma ve Trainer reseti kontrol edilir.

`tests/test_trainer_blackjack.cjs` DOM ortamında görünürlüğü, aramayı,
eski yardımcı uyumluluğunu ve aç/kapat isteklerini doğrular; `jsdom` gerekir.
Canlı oyunda da yeni ellerde K + A görülerek doğrulandı.

```powershell
python -m unittest discover -s tests -p test_blackjack.py -v
node tests/test_trainer_blackjack.cjs
```
