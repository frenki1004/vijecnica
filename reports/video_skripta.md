# Vijećnica: video od 3 minute (scenarij)

Natječaj traži da video jasno prikaže: problem, ciljane korisnike, korištene skupove podataka, glavne
funkcionalnosti, tehnički pristup i očekivanu korist, uz demonstraciju rada (kriterij „Prezentacija rješenja”, 1–10).
Svaka scena ispod označena je time što pokriva. Tekst naratora je oko 430 riječi, što je oko 2:50 mirnog govora.

## Priprema snimanja
- Poslužitelj: `cd drustvo_i_javne_usluge && ../.venv/bin/python mcp_server.py --http 8103`.
- Preglednik u mobilnom prikazu (DevTools → iPhone 14, 390 px) na `http://localhost:8103/feed`. Prije snimanja
  isprazni lokalnu pohranu stranice, da feed krene od „Svi” i uključenog „Samo bitno”.
- Snimka zaslona: QuickTime (Datoteka → Novo snimanje zaslona) ili OBS, 1080p. Glas snimaj zasebno, u tihoj sobi.
- Slike za umetanje: `data/posts/png/<id>/1.png` itd. Dijagram arhitekture: mermaid iz `ARHITEKTURA.md`
  (otvori na GitHubu, gdje se iscrtava).
- Titlovi su obavezni: dio žirija i publike gleda bez zvuka.

---

## 0:00–0:20 · Problem (*problem*)
**Kadar:** brzi rez kroz izvore: PDF poimeničnog glasovanja, skenirani zapisnik (Krk), stranica sjednice s 50
poveznica. Na kraju crni ekran s brojkom.
**Narator:**
> Gradsko vijeće odlučuje o tvom autobusu, vrtiću i odvozu smeća. Ali to što je odlučilo skriveno je u PDF-ovima,
> skeniranim zapisnicima i snimkama od četiri sata. Zapisnik nekad kasni i sto dana.
**Na ekranu:** „Krk, 7. sjednica: 109 dana bez zapisnika”

## 0:20–0:40 · Za koga (*ciljani korisnici*)
**Kadar:** grafika s tri brojke iz studije.
**Narator:**
> Više od trećine mladih nije izašlo na prethodne izbore iako su mogli. Najčešći razlog: „ništa se ne bi
> promijenilo”. Lokalnoj samoupravi vjeruje tek 13,6 posto mladih. Vijećnica je za njih: za mlade od 16 do 30 koji žele znati
> što se događa u njihovu gradu, u minuti, na mobitelu.
**Na ekranu:** „36,8 % nije glasovalo · 13,6 % vjeruje lokalnoj samoupravi” · izvor: Studija o mladima Hrvatska
2024, FES / IDI

## 0:40–1:30 · Demo (*funkcionalnosti*)
**Kadar 1 (0:40):** feed, odabir „Moj grad: Zagreb”, uključen „Samo bitno”, brojač „154 od 952 objava”.
> Odabereš svoj grad, a „Samo bitno” ostavlja odluke koje se tiču stanovnika.

**Kadar 2 (0:52):** objava `zagreb-14-23-1`, listanje karusela do slajda „Kako su glasali klubovi”.
> Svaka odluka je karusel: što je odlučeno, što to znači za tebe, tko je što rekao i kako se glasovalo. Za Zagreb
> iz službenog poimeničnog glasovanja: tko je bio protiv, a tko je bio u dvorani i nije glasovao.

**Kadar 3 (1:10):** objava `krk-5-18-1` („Sjednice vijeća i dalje bez prijenosa uživo”), pa klik na teme
`#proračun`, `#vrtićiiškole`.
> Prijedlog da se sjednice vijeća prenose uživo nije prošao. To je također vijest. Pratiš teme koje te zanimaju,
> u devetnaest gradova i općina.

**Kadar 4 (1:22):** mapa `data/posts/png` s karuselima, pa jedna Reddit datoteka.
> Iste objave izlaze kao slike za Instagram i kao tekst za Reddit, s izvorom ispod svake.

## 1:30–2:05 · Podaci (*korišteni skupovi podataka*)
**Kadar:** tablica izvora (README), pa terminal s upitom nad pogledom `city_overview`:
`sqlite3 -header -column data/vijecnica.db "select city, population, voters_2026, turnout_pct, seats_total, largest_list from city_overview limit 6"`
**Narator:**
> Podaci dolaze sa službenih stranica 19 gradova i općina: 198 sjednica i više od tri tisuće točaka dnevnog reda.
> S Portala otvorenih podataka preko API-ja uzimamo registar svih 556 jedinica, broj birača, popis stanovništva i
> porezne stope, a izborne rezultate s DIP-a pretvaramo u mandate. Tako uz svaku odluku stoji tko ima većinu i
> koliko ljudi ta odluka pogađa.
**Na ekranu:** logotipi/nazivi: data.gov.hr (CKAN API) · jpt.gov.hr · DZS · DIP · službene stranice vijeća · eSjednice

## 2:05–2:35 · Kako radi (*tehnički pristup*)
**Kadar:** dijagram arhitekture iz `ARHITEKTURA.md`, zum na redom: skupljači → baza → odabir → AI pisac → provjere →
feed / Instagram / Reddit / MCP / izvoz.
**Narator:**
> Skupljači čitaju zapisnike, a snimke pretvaramo u tekst prepoznavanjem govora. Pravila bez urednika biraju što
> postaje objava, a umjetna inteligencija piše jednostavnim jezikom, samo iz zapisnika. Svaka brojka prolazi
> automatsku provjeru, a objavu prije izlaska pregledava čovjek. Tako smo uhvatili i greške: sjednicu na kojoj su
> se glasovi pomaknuli za jednu točku i 26 glasovanja kojima su nedostajali glasovi protiv.
**Na ekranu:** „otvoreni kod (EUPL-1.2) · Frictionless/CKAN izvoz · MCP · JSON API”

## 2:35–3:00 · Korist i dalje (*očekivana korist, daljnji razvoj*)
**Kadar:** feed se lista, pa završni ekran s poveznicom na repozitorij.
**Narator:**
> Mladi dobivaju razlog da se uključe, gradovi lakši put do građana, a novinari podatke koje mogu provjeriti. Jedan
> skupljač već pokriva trinaest jedinica na istom sustavu za sjednice, a cilj su svih 556. Tražimo grad ili savjet
> mladih za pilot, i objavu poimeničnog glasovanja u strojnom obliku.
**Na ekranu:** „Vijećnica · vijecnica.vercel.app · github.com/frenki1004/vijecnica · Izazov A: Društvo i javne usluge”

---

## Provjera prije predaje
- Trajanje ≤ 3:00 (žiri ocjenjuje video od 3 minute).
- Svaka izgovorena brojka postoji u `reports/pitch_hr.md` ili u `ARHITEKTURA.md` (odjeljak „Provjera brojki”).
- Bez imena privatnih osoba u kadru. Vijećnici su javne osobe, ali u objavama ih ne imenujemo, pa ne ni u videu.
- Glas, titlovi i tekst na ekranu govore isto.
