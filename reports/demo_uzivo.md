# eVijećnica: demo uživo (točno 3 minute)

Za prezentaciju pred žirijem ili snimku zaslona. Tok: problem → kako smo došli do podataka → web (snalaženje po
#mjesto i #tema) → Reddit → MCP (RAG nad zapisnicima i transkriptima) → misao vodilja. Oko 400 riječi, mirnim tempom.

## Priprema (10 minuta prije)
1. **Poslužitelj** (za MCP i lokalni feed): `cd drustvo_i_javne_usluge && ../.venv/bin/python mcp_server.py --http 8103`
2. **AI asistent s MCP-om**, npr. Claude Code u drugom terminalu:
   `claude mcp add --transport http evijecnica http://localhost:8103/mcp`, zatim `claude` i provjera `/mcp`
   (treba pisati 17 alata). Claude Desktop: Settings → Connectors → isti URL.
3. **Kartice u pregledniku**, ovim redom (svaka preko cijelog ekrana):
   - https://evijecnica.vercel.app/intro (uvod s brojkama i scena „kako smo došli do podataka”; → ili razmaknica za dalje)
   - https://evijecnica.vercel.app u **privatnom prozoru** (da se pokaže početni ekran, ne zadnji odabrani grad)
   - privatni subreddit s tri objave iz `reports/reddit_demo.md` (ako ga nema: otvori `data/posts/reddit/weekly/cakovec-2025-W51.md`)
   - https://evijecnica.vercel.app/demo (snimljeni odgovori agenta, rezerva za MCP)

---

## 0:00–0:25 Problem (25 s, /intro)
Stranica se vrti sama: brojač neglasača, izlaznost po gradovima, mladi.
> „Pogledajmo brojke. Na lokalnim izborima 2025. u dvadeset najvećih gradova nije glasovalo 957 tisuća ljudi,
> šest od deset. Među mladima više od trećine, a najčešći razlog je: ništa se ne bi promijenilo. Nije da ih nije
> briga. Politika izgleda presloženo da bi je sam procijenio.”

## 0:25–1:05 Kako smo došli do podataka (40 s, /intro)
Animirani tok u šest koraka: data.gov.hr → pretraživač → skupljači → govor u tekst → AI piše objave → baza i MCP.
> „Zato smo napravili eVijećnicu. Krenuli smo od Portala otvorenih podataka: preko API-ja uzimamo registar svih
> 556 gradova i općina s adresama njihovih stranica, popis stanovništva, birače i porezne stope, a iz rezultata
> izbora računamo mandate i izlaznost. Zatim smo automatski pregledali svih 556 stranica i našli gdje vijeća
> objavljuju zapisnike i snimke. Skupljači preuzimaju zapisnike, materijale i audio snimke sjednica, a snimke
> pretvaramo u tekst: sedam sati sjednice za manje od sat vremena. Umjetna inteligencija iz zapisnika, materijala
> i transkripata piše objave, a svaka se brojka automatski provjerava. Sve ide u jednu pretraživu bazu koju MCP
> poslužitelj otvara svakom AI asistentu.”

## 1:05–1:55 Web: snalaženje po #mjesto i #tema (50 s)
1. **Početni ekran** (10 s): petnaest najvećih gradova, općine s najnižom izlaznošću, grafikon izlaznosti.
   > „Evo kako to izgleda. Pokrivamo svih petnaest najvećih gradova Hrvatske, i za svaki piše kolika je bila izlaznost.”
2. **#mjesto** (12 s): odabir grada u izborniku (npr. Zagreb) → kartica grada: stanovnici, birači, izlaznost,
   sastav vijeća.
   > „Odabereš svoje mjesto i vidiš samo svoje vijeće: tko u njemu sjedi i što je odlučilo.”
3. **#tema** (14 s): klik na temu (npr. #proračun ili #vrtićiiškole), pa klik na hashtag u samoj objavi.
   > „Ili kreneš od teme koja te zanima. Svaki hashtag je poveznica, pa jednim klikom vidiš istu temu u drugim gradovima.”
4. **Objava** (14 s): „Samo bitno” uključeno, listanje vrtuljka (naslovnica s pečatom grada → što je odlučeno →
   kako se glasalo), pečat „NIJE PROŠLO”, izvor ispod objave, „Zašto ovo vidim?”.
   > „Svaka objava stane u minutu: što je odlučeno, kako se glasalo i što to znači za tebe. Vijest je i ono što
   > nije prošlo. Ispod svake objave je izvor: zapisnik, materijal ili trenutak u snimci.”

**Rezerva:** isto lokalno na http://localhost:8103/feed.

## 1:55–2:10 Reddit (15 s)
Tjedni pregled Čakovca i objava o prijenosu sjednica.
> „Svaka objava odmah je spremna i za društvene mreže. Plan: najvažnije objave tjedna na Instagram, a tjedni
> pregled grada na Reddit, gdje se raspravlja. Objavljuje osoba, ne bot.”

**Rezerva:** `data/posts/reddit/weekly/cakovec-2025-W51.md`.

## 2:10–2:45 MCP: pitaj vijeće (35 s)
U Claude Codeu ili Claude Desktopu (postavi pitanja prije snimanja, pa samo pokaži odgovore):
1. **„Kako su glasali klubovi o porezu na nekretnine u Zagrebu?”** → `get_item`: 24 za, 7 protiv, po klubovima.
2. **„Što su vijećnici u Velikoj Gorici govorili o vrtićima?”** → `search` po transkriptu: što je rečeno, s vremenom u snimci.
3. **„Koja su obećanja dana na aktualnom satu u Zagrebu?”** → `promises`: obećanja s citatom i rokom.
> „Sve to dostupno je i AI asistentima, preko otvorenog MCP poslužitelja. To je RAG: asistent ne izmišlja, nego
> prvo pretraži našu bazu zapisnika i transkripata sjednica, pa odgovori iz onoga što je našao. Zato odgovor
> uvijek ima izvor: točku dnevnog reda, zapisnik ili trenutak u snimci.”

**Rezerva:** https://evijecnica.vercel.app/demo (snimljeni razgovori).

## 2:45–3:00 Misao vodilja (15 s)
Završni ekran /intro: „Glasaj. Budi dio promjene.” → logo.
> „Ne moraš znati sve o politici. Dovoljno je znati što je tvoje vijeće odlučilo. Glasaj. Budi dio promjene.
> eVijećnica: tvoj grad, u minuti.”

---

## Ako žiri pita
- **Je li AI pouzdan?** Piše samo iz zapisnika, materijala i transkripata; brojke se automatski provjeravaju; u
  Čakovcu smo tako našli zapisnik u kojem zbroj glasova (21) premašuje broj vijećnika (19) i taj rezultat ne objavljujemo.
- **Je li to RAG?** Da, u širem smislu: asistent preko MCP alata pretražuje bazu (SQLite s pretraživanjem punog
  teksta, FTS5) i odgovara iz pronađenih zapisa, s izvorom. Nije vektorska baza; za službene dokumente točno
  pretraživanje po riječima i brojkama pokazalo se dovoljnim.
- **Zašto ne svih 556 jedinica?** Pretraživač je pregledao svih 556: 292 objavljuju zapisnike, a snimke smo našli
  kod njih 87. Isti postupak radi svugdje gdje ima zapisnika; za 14 jedinica na sustavu eSjednice dovoljan je jedan
  skupljač. Na webu je gumb „Moj grad nije na popisu” kojim građani predlažu sljedeće gradove.
- **Medijan izlaznosti 49,68 %?** Medijan izlaznosti 555 gradova i općina (izbor vijeća 2025., 1. krug), izračunat iz
  DIP-ovih rezultata; ukupna izlaznost u Hrvatskoj je 43,64 %.
- **Samobor i Dubrovnik?** Dubrovnik i Samobor dijelom ograničavaju automatski pristup (robots.txt); te pakete
  preuzela je osoba, a Samobor je izričito isključio AI sustave, pa to piše u izvorima i jedinicu uklanjamo ako se Grad protivi.
