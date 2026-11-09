# eVijećnica: demo uživo (oko 5 minuta)

Za prezentaciju pred žirijem ili snimku zaslona. Tri dijela: web (što vidi građanin), Reddit (gdje se raspravlja),
MCP (kako AI asistent odgovara iz istih podataka). Svaki korak ima rezervu ako nešto zapne.

## Priprema (10 minuta prije)
1. **Poslužitelj** (za MCP i lokalni feed): `cd drustvo_i_javne_usluge && ../.venv/bin/python mcp_server.py --http 8103`
2. **AI asistent s MCP-om**, npr. Claude Code u drugom terminalu:
   `claude mcp add --transport http evijecnica http://localhost:8103/mcp`, zatim `claude` i provjera `/mcp`
   (treba pisati 17 alata). Claude Desktop: Settings → Connectors → isti URL.
3. **Kartice u pregledniku**, ovim redom:
   - https://vijecnica.vercel.app u **privatnom prozoru** (da se pokaže početni ekran, ne zadnji odabrani grad)
   - privatni subreddit s tri objave iz `reports/reddit_demo.md` (ako ga nema: otvori `data/posts/reddit/weekly/cakovec-2025-W51.md`)
   - https://vijecnica.vercel.app/demo (snimljeni odgovori agenta, rezerva za MCP)
4. Zvuk računala uključen (MCP korak pušta isječak gradske snimke).

---

## 0:00 Uvod (20 s)
> „Gradsko vijeće odlučuje o tvom porezu, vrtiću i autobusu. To piše u zapisniku od šezdeset stranica ili u snimci
> od sedam sati. Na lokalnim izborima 2025. u dvadeset najvećih gradova nije glasovalo 957 tisuća ljudi.
> eVijećnica to mijenja.”

## 0:20 Web (2 min)
1. **Početni ekran.** Pokaži tri brojke i tri skupine.
   > „Pokrivamo svih petnaest najvećih gradova. Uz svaki grad je izlaznost i mjesto među 555 jedinica.”
2. **Pet općina s najnižom izlaznošću.** Klikni **Brckovljani** (22 %, najniža u Hrvatskoj).
   > „Ovdje je glasovao svaki peti birač. Vijeće za ovaj saziv nije objavilo nijedan zapisnik. Gdje ljudi najmanje
   > glasuju, rad vijeća je uglavnom nevidljiv. I to je informacija.”
3. Klik na logo (natrag na početni ekran) → **Zagreb**. Kartica grada: tko čini Skupštinu (25 od 47 mjesta), izlaznost.
4. Objava **„Porez na nekretnine u Zagrebu od 2027. 8,00 eura po m² umjesto 5,00”** (pomakni se do nje ili tema
   `#poreziinaknade`). Listaj karusel: što je odlučeno → **kako su glasali klubovi** (poimenično glasovanje) → izvor.
   > „Zapisnik kaže samo da su izmijenjeni lokalni porezi. Brojku 8 eura nismo izmislili: pročitali smo prijedlog odluke.”
5. Klik **„Službeni izvor: zapisnik ↗”**: otvara se službeni PDF Grada.
6. Odaberi **Čakovec** → objava **„Prijenos sjednica gradskog vijeća uživo nije prošao”** (crvena naslovnica, 4 : 12 : 2).
   > „Vijest je i ono što nije prošlo.”

**Rezerva:** ako je mreža spora, isto pokaži lokalno na http://localhost:8103/feed.

## 2:20 Reddit (40 s)
Otvori subreddit: tjedni pregled Čakovca i objava o prijenosu sjednica.
> „Ista objava ide i na Reddit, gdje ljudi raspravljaju i ispravljaju, uvijek s tablicom glasovanja i izvorom.
> Objavljuje osoba, ne bot: sustav priprema tekst, urednik pregleda i objavi.”

**Rezerva:** pokaži datoteku `data/posts/reddit/weekly/cakovec-2025-W51.md` (isti tekst u Markdownu).

## 3:00 MCP: pitaj vijeće (1 min 30 s)
U Claude Codeu (ili Claude Desktopu) postavi redom, na hrvatskom:

1. **„Što je Gradska skupština Zagreba na 14. sjednici odlučila o lokalnim porezima i kako su glasali klubovi?”**
   Agent zove `get_item` i vraća 24 za, 7 protiv i poimenično glasovanje po klubovima (Možemo! 16 i SDP 8 za; protiv Drito 4, HDZ, DP i HNS po jedan).
2. **„Što su vijećnici u Velikoj Gorici govorili o vrtićima? Daj mi trenutak u snimci.”**
   Agent zove `search` i vraća rečenice iz 8. sjednice s vremenom (npr. 3:26:21) i poveznicom na gradsku snimku.
   **Klikni poveznicu: snimka se pušta točno u tom trenutku.** (najzabavniji trenutak dema)
3. **„Koja su obećanja gradonačelnik Zagreba i njegovi suradnici dali na aktualnom satu i jesu li ispunjena?”**
   Agent zove `promises` i `promise_followup`: 57 obećanja s citatom i rokom (npr. Kino Tuškanac, „sljedeće godine”).

> „Svaki AI asistent može pitati vijeće, a odgovor uvijek ima izvor: točku, zapisnik ili trenutak u snimci.”

**Rezerva:** https://vijecnica.vercel.app/demo, šest snimljenih razgovora (pozivi alata i odgovori).

## 4:30 Podaci i otvorenost (20 s)
Na početnom ekranu pokaži „otvoreni podaci preko API-ja data.gov.hr” i (u kartici grada) „Službena stranica ·
N skupova podataka na data.gov.hr”.
> „Stanovništvo, birači, porezne stope i izbori dolaze s Portala otvorenih podataka preko API-ja. Sve što smo
> skupili vraćamo kao otvorene podatke za CKAN, a kod je otvoren.”

## 4:50 Kraj (10 s)
> „eVijećnica: tvoj grad, u minuti. Tražimo prvi grad ili savjet mladih za pilot.”

---

## Ako žiri pita
- **Je li AI pouzdan?** Piše samo iz zapisnika i materijala; brojke se automatski provjeravaju; u Čakovcu smo tako
  našli zapisnik u kojem zbroj glasova (21) premašuje broj vijećnika (19) i taj rezultat ne objavljujemo.
- **Zašto ne svih 556 jedinica?** Pretraživač je pregledao svih 556: 292 objavljuju zapisnike. Isti postupak radi
  svugdje gdje ima zapisnika; za 14 jedinica na sustavu eSjednice dovoljan je jedan skupljač.
- **Samobor i Dubrovnik?** Dubrovnik i Samobor dijelom ograničavaju automatski pristup (robots.txt); te pakete
  preuzela je osoba, a Samobor je izričito isključio AI sustave, pa to piše u izvorima i jedinicu uklanjamo ako se Grad protivi.
