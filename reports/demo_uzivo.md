# eVijećnica: demo uživo (točno 3 minute)

Za prezentaciju pred žirijem ili snimku zaslona. Tri dijela: web (što vidi građanin), Reddit (gdje se raspravlja),
MCP (kako AI asistent odgovara iz istih podataka). Svaki korak ima rezervu ako nešto zapne.

## Priprema (10 minuta prije)
1. **Poslužitelj** (za MCP i lokalni feed): `cd drustvo_i_javne_usluge && ../.venv/bin/python mcp_server.py --http 8103`
2. **AI asistent s MCP-om**, npr. Claude Code u drugom terminalu:
   `claude mcp add --transport http evijecnica http://localhost:8103/mcp`, zatim `claude` i provjera `/mcp`
   (treba pisati 17 alata). Claude Desktop: Settings → Connectors → isti URL.
3. **Kartice u pregledniku**, ovim redom (svaka preko cijelog ekrana):
   - https://vijecnica.vercel.app/intro (uvod s brojkama; sam se vrti 35 s, → ili razmaknica za dalje)
   - https://vijecnica.vercel.app u **privatnom prozoru** (da se pokaže početni ekran, ne zadnji odabrani grad)
   - privatni subreddit s tri objave iz `reports/reddit_demo.md` (ako ga nema: otvori `data/posts/reddit/weekly/cakovec-2025-W51.md`)
   - https://vijecnica.vercel.app/demo (snimljeni odgovori agenta, rezerva za MCP)
4. Po želji zvuk računala uključen, ako u MCP koraku pustiš isječak gradske snimke.

---

## 0:00–0:35 Uvod: pogledajmo brojke (35 s, stranica /intro)
Stranica se vrti sama; govori preko nje.
> „Pogledajmo brojke. Na lokalnim izborima 2025. u dvadeset najvećih gradova nije glasovalo 957 tisuća ljudi,
> šest od deset. U Kaštelima, Osijeku i Rijeci dvoje od troje. Među mladima više od trećine nije glasovalo,
> a najčešći razlog je: ništa se ne bi promijenilo. Nije da ih nije briga: politika izgleda presloženo da bi je sam
> procijenio. A ne moraš znati sve o politici. Dovoljno je znati što je tvoje vijeće odlučilo.
> Glasaj. Budi dio promjene.”

## 0:35–1:40 Web (65 s)
1. **Početni ekran** (10 s): skupine i grafikon izlaznosti.
   > „eVijećnica pokriva svih petnaest najvećih gradova i pokazuje gdje je izlaznost najniža.”
2. **Brckovljani** (12 s), u skupini s najnižom izlaznošću.
   > „Najniža izlaznost u Hrvatskoj, a vijeće za ovaj saziv nije objavilo nijedan zapisnik.”
3. Logo → **Zagreb** → objava **„Porez na nekretnine … 8,00 eura po m² umjesto 5,00”** (28 s). Listaj: naslovnica
   (pečat grada) → što je odlučeno → **kako su glasali klubovi**.
   > „Zapisnik kaže samo ‚izmjene lokalnih poreza’. Brojku smo pročitali iz prijedloga odluke, a kako su glasali
   > klubovi iz službenog poimeničnog glasovanja. Ispod svake objave je izvor.”
4. **Čakovec** → **„Prijenos sjednica gradskog vijeća uživo nije prošao”** (15 s), pečat „NIJE PROŠLO”.
   > „Vijest je i ono što nije prošlo.”

**Rezerva:** isto lokalno na http://localhost:8103/feed.

## 1:40–2:00 Reddit (20 s)
Tjedni pregled Čakovca i objava o prijenosu sjednica.
> „Ista objava ide i na Reddit, s tablicom glasovanja i izvorom. Objavljuje osoba, ne bot.”

**Rezerva:** `data/posts/reddit/weekly/cakovec-2025-W51.md`.

## 2:00–2:45 MCP: pitaj vijeće (45 s)
U Claude Codeu ili Claude Desktopu (postavi pitanja prije snimanja, pa samo pokaži odgovore):
1. **„Kako su glasali klubovi o porezu na nekretnine u Zagrebu?”** → `get_item`: 24 za, 7 protiv, po klubovima.
2. **„Što su vijećnici u Velikoj Gorici govorili o vrtićima?”** → `search`: što je rečeno, s vremenom u snimci.
3. **„Koja su obećanja dana na aktualnom satu u Zagrebu?”** → `promises`: 57 obećanja s citatom i rokom.
> „Isti podaci dostupni su svakom AI asistentu, preko otvorenog MCP poslužitelja. Odgovor uvijek ima izvor:
> točku, zapisnik ili trenutak u snimci.”

**Rezerva:** https://vijecnica.vercel.app/demo (snimljeni razgovori).

## 2:45–3:00 Kraj (15 s)
Početni ekran.
> „Podaci s Portala otvorenih podataka preko API-ja, a sve skupljeno vraćamo kao otvorene podatke; kod je otvoren.
> eVijećnica: tvoj grad, u minuti.”

---

## Ako žiri pita
- **Je li AI pouzdan?** Piše samo iz zapisnika i materijala; brojke se automatski provjeravaju; u Čakovcu smo tako
  našli zapisnik u kojem zbroj glasova (21) premašuje broj vijećnika (19) i taj rezultat ne objavljujemo.
- **Zašto ne svih 556 jedinica?** Pretraživač je pregledao svih 556: 292 objavljuju zapisnike. Isti postupak radi
  svugdje gdje ima zapisnika; za 14 jedinica na sustavu eSjednice dovoljan je jedan skupljač.
- **Samobor i Dubrovnik?** Dubrovnik i Samobor dijelom ograničavaju automatski pristup (robots.txt); te pakete
  preuzela je osoba, a Samobor je izričito isključio AI sustave, pa to piše u izvorima i jedinicu uklanjamo ako se Grad protivi.
