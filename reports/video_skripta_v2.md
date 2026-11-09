# eVijećnica: video od 3 minute, verzija 2

Video je stranica `web/film.html` (`/film` na lokalnom poslužitelju i na https://vijecnica.vercel.app/film):
sedam scena s točnim vremenima i titlovima na ekranu. `web/record_film.py` snima je u
`deploy/film/vijecnica.mp4` (1920×1080, točno 3:00, bez zvuka) i piše titlove u `deploy/film/vijecnica.srt`.
Naracija ispod jednaka je titlovima (izvor istine je popis `SUBS` u `web/film.html`); oko 300 riječi, mirnim tempom.

## Što trebaš napraviti (oko 45 minuta)
1. **Glas** (15 min): otvori `deploy/film/vijecnica.mp4`, pusti ga i čitaj titlove naglas dok se vrte; snimi glas
   (QuickTime → Nova audio snimka, ili mobitel) u tihoj sobi. Ako zaostaješ, nije problem: u montaži pomakni rečenice.
2. **Montaža** (15 min, iMovie, CapCut ili Canva): video + glas; po želji tiha glazba ispod (bez autorskih prava).
   Titlovi su već u slici. Po želji umetni 8–10 s snimke s Reddita u scenu 4 (`reports/reddit_demo.md`).
3. **Objava** (10 min): YouTube „neizlistano” (unlisted), uz video učitaj `vijecnica.srt` kao titlove. Provjeri da
   se poveznica otvara u privatnom prozoru, i stavi je u e-poruku (`datathon/prijava_email_izazov_A.md`).

Ako želiš oštriju sliku: otvori `http://localhost:8103/film` u Chromeu preko cijelog ekrana (1920×1080) i snimi
ga QuickTimeom; stranica se sama vrti 3 minute.

## Scene i naracija

### 0:00–0:15 · 1 · Problem (problem)
**Slika:** Lijevo prva stranica zapisnika 5. sjednice Gradskog vijeća Čakovca (63 stranice), desno valni oblik i trajanje snimke 8. sjednice Velike Gorice (7:03:24). Pojavljuje se pitanje „Gdje si ovo mogao saznati?”

> `0:00` Tvoje gradsko vijeće upravo je odlučilo o proračunu, vrtićima i parkingu.
> `0:06` Gdje si to mogao saznati? U zapisniku od šezdeset tri stranice.
> `0:11` Ili u snimci sjednice od sedam sati.

### 0:15–0:35 · 2 · Mladi (ciljani korisnici)
**Slika:** Tri brojke iz Studije o mladima Hrvatska 2024. (FES/IDI), s izvorom na ekranu.

> `0:15` Više od trećine mladih nije izašlo na prethodne izbore, iako su mogli.
> `0:21` Najčešći razlog: „ništa se ne bi promijenilo”.
> `0:25` Lokalnoj vlasti vjeruje tek 13,6 posto mladih.
> `0:30` Teško je vjerovati nečemu što ne vidiš.

### 0:35–1:25 · 3 · Demo (funkcionalnosti)
**Slika:** Živi feed u okviru mobitela: početni ekran → Čakovec → kartica grada (mandati, izlaznost, stanovnici) → karusel → rasprava → izvor ispod objave → objava „Prijenos sjednica gradskog vijeća uživo nije prošao”. Desno pet koraka.

> `0:35` eVijećnica to mijenja. Odabereš svoj grad, recimo Čakovec,
> `0:41` i odmah vidiš tko čini gradsko vijeće i koliko je ljudi izašlo na izbore.
> `0:48` Svaka odluka je karusel od minute: što je odlučeno, što to znači za tebe,
> `0:54` tko je što rekao i kako se glasovalo. Ispod je službeni izvor.
> `1:01` Vijest je i ono što nije prošlo:
> `1:04` u Čakovcu je prijedlog da se sjednice snimaju i prenose uživo odbijen,
> `1:10` s dvanaest glasova protiv. Na Krku isto.
> `1:16` Prekidač „Samo bitno” ostavlja odluke koje se izravno tiču stanovnika.

### 1:25–1:45 · 4 · Instagram i Reddit (kanali)
**Slika:** Tri prave slike karusela (Čakovec, Krk, Zagreb s glasovanjem klubova) i ista objava kao Reddit tekst. Ako ste objavili privatni subreddit (reports/reddit_demo.md), ovdje u montaži možete umetnuti 8–10 s snimke s Reddita.

> `1:25` Iste objave izlaze kao slike za Instagram
> `1:30` i kao tekst za Reddit, gdje ljudi mogu raspravljati i ispravljati,
> `1:36` uvijek s izvorom ispod objave.

### 1:45–2:15 · 5 · Podaci (skupovi podataka, tehnički pristup)
**Slika:** Izvori preko API-ja (data.gov.hr CKAN, jpt.gov.hr, DZS, registar birača, porezne stope, DIP), brojke iz baze i rezultat pretraživača 556 jedinica.

> `1:45` Podatke uzimamo s dvadeset službenih stranica gradova i općina
> `1:50` i s Portala otvorenih podataka, preko API-ja: registar jedinica, popis stanovništva, birače i porezne stope.
> `1:58` Izborne rezultate pretvaramo u mandate.
> `2:01` Naš pretraživač pregledao je svih 556 jedinica i našao snimke sjednica kod njih 87.
> `2:08` Snimke pretvaramo u tekst: sedam sati sjednice za manje od sat vremena.

### 2:15–2:40 · 6 · Povjerenje (tehnički pristup, kvaliteta)
**Slika:** Prava stranica 14 zapisnika 3. sjednice Čakovca: predsjednik kaže 11 za, zaključak 16 za i 5 protiv, a vijeće ima 19 članova → „Ne objavljujemo”.

> `2:15` Umjetna inteligencija piše samo iz zapisnika, a svaka brojka prolazi automatsku provjeru.
> `2:22` U jednom zapisniku Čakovca predsjednik vijeća najavio je 11 glasova za, a zaključak kaže 16.
> `2:28` Uz 5 protiv to je 21 glas, a vijeće ima 19 članova. Takav rezultat ne objavljujemo.
> `2:35` Odabir je bez urednika: pravila su javna i ista za sve.

### 2:40–3:00 · 7 · Kraj (očekivana korist, daljnji razvoj)
**Slika:** Logo, „Tvoj grad, u minuti.”, poveznice, licence, izazov.

> `2:40` Kod i podaci su otvoreni.
> `2:44` Sljedeći korak: svih 556 vijeća i pilot s jednim gradom ili savjetom mladih.
> `2:51` eVijećnica. Tvoj grad, u minuti.

## Provjera prije predaje
- Trajanje 3:00 (žiri ocjenjuje video od 3 minute).
- Brojke: 20 jedinica, 205 sjednica, 3.621 točka, 2.188 s ishodom, 1.014 objava (upiti u `ARHITEKTURA.md`, „Provjera
  brojki”); mladi: Studija o mladima Hrvatska 2024., FES/IDI; Čakovec 4/12/2 i 11 ↔ 16+5: zapisnici 4. i 3. sjednice;
  556/495/292/87: `data/discover/summary.json` (pretraživač, bez ručne provjere uzorka, pa „našao”, a ne „ima”).
- Bez imena privatnih osoba. Imena u kadru (predsjednik vijeća i gradonačelnica u zapisniku i kartici grada) su
  javne dužnosti u službenim dokumentima.
