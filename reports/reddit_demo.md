# Reddit demo za video (Čakovec)

Cilj: snimiti pravu objavu na Redditu, ne lažni prikaz. Traje oko 15 minuta.

1. Na Redditu (prijavljen svojim računom): **Create a community** → ime npr. `VijecnicaDemo` → tip **Private** → Create.
2. U postavkama zajednice dodaj **post flair** `Čakovec`.
3. Za svaku od tri objave ispod: **pročitaj je cijelu** (zadnji redak kaže da ju je pregledala osoba, pa to mora biti istina),
   zatim **Create post → Text**, zalijepi naslov i tijelo (uključi Markdown editor), odaberi flair i objavi.
4. Kao moderator prikvači prvi komentar iz `data/posts/reddit/README.md` (odjeljak „Prvi komentar”).
5. Snimanje: preglednik 1920×1080, zum 125 %; pomakni se kroz tjedni pregled, otvori objavu „nije prošao” i pokaži tablicu glasovanja i izvor.
   Ne izmišljaj komentare drugih ljudi; u naraciji je dovoljno reći da ljudi mogu komentirati i ispravljati.

Objave su izvoz `posts/export_reddit.py` (datoteke u `data/posts/reddit/`).

---

## tjedni pregled: sve odluke 4. sjednice

**Naslov:**

```
[Čakovec] Što je gradsko vijeće odlučilo (17. 12. 2025.)
```

**Tijelo (Markdown):**

````markdown
Pregled odluka s 4. sjednice (17. 12. 2025.) prema službenom zapisniku. Odluke s glasovima protiv ili suzdržanima imaju i zasebnu objavu s detaljima.

### Bivša tvornica MTČ u centru: plan za stanove, park i garažu

**Usvojeno** (17 za, 2 protiv, 0 suzdržano)

Donesen je urbanistički plan za oko 3,9 ha u centru, na mjestu bivše tvornice MTČ i parkirališta uz Trg Republike. Predviđeni su pretežito stambeni blokovi, zgrada gradske uprave s garažom do 300 mjesta, park i pješačko-biciklističke staze.

### Proračun za 2025. smanjen za 5,6 milijuna eura, investicije odgođene

**Usvojeno** (14 za, 2 protiv, 1 suzdržano)

Drugim izmjenama proračuna za 2025. prihodi se smanjuju za 5.590.000, a rashodi za 5.630.000 eura. Ulaganja se smanjuju za 7.000.000 eura jer su nabave trajale dulje, a za društvene djelatnosti ide 1.800.000 eura više, najviše za vrtiće i osnovne škole.

### Pravila trošenja proračuna za 2025. usklađena s rebalansom

**Usvojeno** (14 za, 2 protiv, 1 suzdržano)

Vijeće je promijenilo odluku koja određuje kako se troši gradski proračun za 2025. Promjene prate drugi rebalans (izmjene i dopune) proračuna za tu godinu. Za je glasovalo 14 vijećnika, 2 protiv, 1 suzdržan.

### Plan gradnje komunalne infrastrukture za 2025. prati rebalans

**Usvojeno** (14 za, 0 protiv, 3 suzdržano)

Vijeće je promijenilo plan gradnje komunalne infrastrukture Grada za 2025. Promjene proizlaze iz drugog rebalansa (izmjena i dopuna) gradskog proračuna za tu godinu. Za 14, protiv 0, suzdržana 3. Nitko se nije javio za raspravu.

### Održavanje komunalne infrastrukture usklađeno s izmjenama proračuna

**Usvojeno** (16 za, 0 protiv, 1 suzdržano)

Plan održavanja cesta, rasvjete i ostale komunalne infrastrukture za 2025. promijenjen je jer je promijenjen proračun. Rasprave nije bilo.

### Proračun za 2026.: oko 101 milijun eura, najveća ulaganja u škole

**Usvojeno** (14 za, 0 protiv, 4 suzdržano)

Vijeće je donijelo gradski proračun za 2026. s projekcijama za 2027. i 2028. Prema gradonačelnici, rashodi i izdaci iznose oko 101 milijun eura, od toga 46 milijuna za investicije. Najveća ulaganja idu u gradnju i dogradnju škola. Za 14, suzdržana 4.

### Kako će se trošiti gradski proračun u 2026.

**Usvojeno** (14 za, 0 protiv, 3 suzdržano)

Uz proračun za 2026. vijeće je donijelo i odluku o njegovu izvršavanju, odnosno pravila po kojima se proračun troši tijekom godine. Donošenje te odluke zakonska je obveza. Za 14, protiv 0, suzdržana 3. Nitko se nije javio za raspravu.

### Plan gradnje za 2026.: manje gradskog novca za stazu Štefanec–Ivanovec

**Usvojeno** (17 za, 0 protiv, 1 suzdržano)

Vijeće je donijelo plan gradnje komunalne infrastrukture za 2026., koji se donosi zajedno s proračunom. U raspravi se govorilo o pješačko-biciklističkoj stazi i autobusnom stajalištu Štefanec–Ivanovec, kojima je iznos u planu smanjen za 50 %.

### Plan održavanja komunalne infrastrukture za 2026.

**Usvojeno** (16 za, 0 protiv, 1 suzdržano)

Vijeće je donijelo plan održavanja komunalne infrastrukture za 2026. Donosi se zajedno s proračunom za 2026. Rasprave nije bilo.

### Odvoz otpada: manje kante i rjeđi odvoz vreća

**Usvojeno** (14 za, 4 protiv, 0 suzdržano)

Nova pravila odvoza otpada: tvrtke dobivaju spremnike od 360 umjesto 1100 litara, građani mogu kantu od 120 zamijeniti manjom od 80 litara, a vreće i zeleni otpad voze se svaki drugi tjedan, osim kod stambenih zgrada.

### Bicikli i romobili zabranjeni u pješačkoj zoni cijele godine

**Usvojeno** (17 za, 0 protiv, 1 suzdržano)

Vijeće je zabranilo vožnju bicikala i romobila tijekom cijele godine u pješačkoj zoni: Ulicom kralja Tomislava, Ulicom Katarine Zrinski, dijelom Ulice Matice hrvatske i stazama perivoja. Iznimke su vozila osoba s invaliditetom i službe poput dostave pošte.

### Prijenos sjednica gradskog vijeća uživo nije prošao

**Nije usvojeno** (4 za, 12 protiv, 2 suzdržano)

Prijedlog jednog vijećnika da se sjednice vijeća snimaju i video prenose na gradskim internetskim stranicama nije prošao: 4 za, 12 protiv, 2 suzdržana. Prijedlog je uvodio i „povredu Poslovnika”, način da se na sjednici upozori na kršenje pravila rada.

## Jednoglasno (Ukratko)

- Izmjene Strategije razvoja urbanog područja Čakovec i akcijskog plana
- Izmjene programa za kulturu, sport, socijalu, zdravstvo i demografiju za 2025.
- Programi za kulturu, sport, socijalu, tehničku kulturu i zdravstvo za 2026.
- Program demografskih mjera za 2026.
- Financiranje osnovnih škola (decentralizirane funkcije) u 2025.
- Financiranje romske i srpske nacionalne manjine za 2025. i 2026.
- Raspodjela novca političkim strankama u vijeću za 2026.
- Financijski planovi Javne vatrogasne postrojbe za 2025. i 2026.
- Strategija upravljanja gradskom imovinom 2025.–2030. i plan za nekretnine 2026.
- Zamjena zemljišta za gradnju područne škole Sjever
- Uvođenje Riznice Grada Čakovca
- Dopune pravila o dimnjačarskim poslovima
- Civilna zaštita i plan za prirodne nepogode za 2026.
- Programi za novac od poljoprivrednog zemljišta u 2025.

---

*Izvor: zapisnik 4. sjednice Gradskog vijeća, 17. 12. 2025.*

Objavu je automatski pripremio projekt eVijećnica, a pregledala ju je osoba. Ispravke uz izvor dobrodošle su u komentarima.
````

---

## prijedlog koji nije prošao

**Naslov:**

```
[Čakovec] Prijenos sjednica gradskog vijeća uživo nije prošao (4 za, 12 protiv, 2 suzdržano) [gradska uprava]
```

**Tijelo (Markdown):**

````markdown
**Što je odlučeno**

Prijedlog jednog vijećnika da se sjednice vijeća snimaju i video prenose na gradskim internetskim stranicama nije prošao: 4 za, 12 protiv, 2 suzdržana. Prijedlog je uvodio i „povredu Poslovnika”, način da se na sjednici upozori na kršenje pravila rada.

**Zašto je važno**

Da je prošao, sjednice gradskog vijeća mogao bi gledati uživo na stranicama Grada Čakovca.

**Tko je što rekao**

- **vijećnik (predlagatelj)**: Prijenos bi pridonio transparentnosti, a ne bi imao trošak jer je oprema nabavljena još u prošlom mandatu.
- **vijećnik (predlagatelj)**: Povreda Poslovnika ne štiti oporbu nego svakog člana vijeća i red na sjednici; slično imaju Varaždin, Našice i Hrvatski sabor.

**Glasovanje**

| Za | Protiv | Suzdržano | Rezultat |
|---|---|---|---|
| 4 | 12 | 2 | Nije usvojeno |

---

*Izvor: zapisnik 4. sjednice Gradskog vijeća, 17. 12. 2025.*

Objavu je automatski pripremio projekt eVijećnica, a pregledala ju je osoba. Ispravke uz izvor dobrodošle su u komentarima.
````

---

## polugodišnji proračun 2026.

**Naslov:**

```
[Čakovec] Pola godine proračuna 2026.: prihodi 28,4 milijuna, manjak 5,46 (14 za, 2 protiv, 0 suzdržano) [proračun]
```

**Tijelo (Markdown):**

````markdown
**Što je odlučeno**

Vijeće je prihvatilo izvještaj o proračunu za prvih šest mjeseci 2026. Prihodi su bili 28,4 milijuna eura, rashodi 29,39 milijuna. Ukupni iskazani manjak na dan 30. lipnja je 5,46 milijuna eura, od čega je 4,07 milijuna preneseno iz prethodnih godina. Rezultat: 14 za, 2 protiv.

**Zašto je važno**

Od više od 40 milijuna eura planiranih ulaganja u 2026. do lipnja je izvršeno 4,6 milijuna, odnosno 10 %; gradnja škola tek je počela.

**Tko je što rekao**

- **Gradonačelnica (predlagateljica)**: Manjak je većinom prenesen i metodološke je naravi; Grad predfinancira projekte iz EU fondova, a prihodi su veći za 26,42 % nego lani.
- **vijećnik**: Pita kako će se pokriti manjak od 5,46 milijuna eura i hoće li se zbog njega odgađati investicije ili Grad dodatno zaduživati.
- **Gradonačelnica (predlagateljica)**: Pri izradi proračuna za 2027. Grad će, ako bude potrebno, razmotriti zatvaranje investicija kroz proračun ili kreditno zaduženje.

**Glasovanje**

| Za | Protiv | Suzdržano | Rezultat |
|---|---|---|---|
| 14 | 2 | 0 | Usvojeno |

---

*Izvor: zapisnik 8. sjednice Gradskog vijeća, 14. 10. 2026.*

Objavu je automatski pripremio projekt eVijećnica, a pregledala ju je osoba. Ispravke uz izvor dobrodošle su u komentarima.
````
