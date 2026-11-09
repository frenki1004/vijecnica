# eVijećnica: odakle dolaze podaci, za svaku jedinicu

Stanje baze 9. 11. 2026. (29 jedinica). Sve brojke u ovom dokumentu izračunate su iz `data/vijecnica.db` i `data/posts/` (skripta je
u povijesti razgovora; upiti iste vrste su u `ARHITEKTURA.md`, „Provjera brojki”). Kod: EUPL-1.2. Izvedeni podaci:
CC BY 4.0 ili uvjeti izvora (licenca po resursu u `datapackage.json` izvoza).

## 1. Put podatka, korak po korak

1. **Pronalaženje stranica vijeća.** `collect/discover.py` pregleda službene stranice svih 556 jedinica (adrese iz
   Adresara tijela javne vlasti s data.gov.hr) i bilježi gdje vijeće objavljuje sjednice, zapisnike i snimke
   (`data/discover/registry.json`). Pristojno: robots.txt, najviše jedan zahtjev u sekundi po poslužitelju, blokade se ne zaobilaze.
2. **Skupljanje sjednica.** Za svaku jedinicu skupljač čita službenu stranicu vijeća: popis sjednica, dnevni red,
   materijale (poveznice na PDF/Word dokumente), zapisnik i snimke (vidi tablicu u odjeljku 3). Sve se sprema u
   predmemoriju (`data/<jedinica>/raw/`), pa se izvor ne pita dvaput isto.
3. **Čitanje dokumenata.** Zapisnici: `pdftotext`; skenirani zapisnici bez teksta: OCR (`tesseract`, hrvatski).
   Iz zapisnika se čitaju točke dnevnog reda, nazočnost i rezultat glasovanja za svaku točku. Zagreb: iz PDF-ova
   poimeničnog glasovanja čita se glas svakog zastupnika.
4. **Materijali.** Za objave zadnjih sjednica `collect/materials.py` preuzima prijedlog i obrazloženje svake
   točke (ne obrasce, dopise ni zemljišnoknjižne izvatke) i čita njihov tekst: zapisnik kaže *da* je nešto odlučeno,
   materijal kaže *što* (stope, iznosi, adrese, tko ima korist).
5. **Snimke.** Tonski zapisi (MP3 s gradske stranice ili zvuk YouTube snimke) pretvaraju se u tekst na ovom
   računalu (`asr/`, Whisper s modelom za hrvatski, mlx). Snimka od 7 sati obradi se za manje od sat vremena.
6. **Otvoreni podaci preko API-ja (data.gov.hr).** `collect/datagovhr.py`, odjeljak 2.
7. **Baza.** `db/build.py` sve spaja u jednu SQLite bazu s pretraživanjem punog teksta; pogled `city_overview`
   povezuje sjednice s podacima s data.gov.hr po jedinici (oznaka JLS i OIB).
8. **Odabir objava (bez urednika).** `posts/build_queue.py`: točka s barem jednim glasom protiv ili suzdržanim,
   odbijena ili s nepoznatim brojem glasova dobiva svoju objavu; jednoglasne odluke idu u pregled „Ukratko”.
9. **Pisanje.** AI pisac (`posts/writer_prompt.md`, `posts/write.py`) piše jednostavnim jezikom samo iz zapisnika
   (i materijala), bez imena privatnih osoba i bez vlastitih izračuna; `problems()` automatski provjerava brojke,
   duljine i zadnji redak s izvorom; nesigurnosti idu uredniku u bilješke.
10. **Provjere.** Glasovi se zbrajaju prema broju članova vijeća (npr. Čakovec: 16 + 5 = 21 > 19, rezultat se ne
    objavljuje); brojke u objavi moraju postojati u izvoru.
11. **Izlazi.** Feed (`web/feed.html`), slike za Instagram (`posts/export_png.py`), tekst za Reddit
    (`posts/export_reddit.py`), MCP poslužitelj i JSON API (`mcp_server.py`), otvoreni podaci kao CSV + Frictionless
    Data Package za CKAN (`export/export.py`, preuzimanje na demo stranici).

## 2. Portal otvorenih podataka (data.gov.hr), za sve jedinice

Sve preko CKAN API-ja portala (`package_show`, `package_search`), datoteka se preuzima s adrese koju portal navodi.
Porijeklo svake datoteke (URL, vrijeme, sha256) zapisano je u `data/datagovhr/raw/manifest.json` i u tablici
`datagovhr_sources` baze. Svi navedeni skupovi objavljeni su pod Otvorenom dozvolom (OD).

| skup podataka (data.gov.hr) | izdavač | što uzimamo | gdje se vidi |
|---|---|---|---|
| Popis javnopravnih tijela (`popis-javnopravnih-tijela`, živi JSON API jpt.gov.hr) | Ministarstvo pravosuđa, uprave i digitalne transformacije | svaka JLS: naziv, OIB, službena oznaka, županija | ključ za povezivanje svega po jedinici; kartica grada |
| Adresar tijela javne vlasti (`adresar-tijela-javne-vlasti`) | Središnji državni ured za razvoj digitalnog društva (na portalu označen kao neaktivan) | službena web stranica svake jedinice | pretraživač 556 jedinica; „Službena stranica” na kartici |
| Popis stanovništva 2021. (`statistika-u-nizu-popis-…-2021`) | DZS | broj stanovnika po gradu/općini | kartica grada; veličina vijeća po zakonu |
| Registar birača (`registar-biraca-broj-biraca`) | Ministarstvo pravosuđa, uprave i digitalne transformacije | broj birača po jedinici (zbroj po adresama) | kartica grada |
| Stope poreza na dohodak 2025./2026. (Porezna uprava) | Porezna uprava | niža i viša stopa po jedinici | kartica grada |
| Rezultati lokalnih izbora (`rezultati-lokalnih-izbora`) | DIP | rezultati 2025. (datoteka iz iste DIP arhive jer skup na portalu staje na 2021.): glasovi po listi, izlaznost, gradonačelnik | mandati po listi (D'Hondt, prag 5 %), izlaznost i „tko čini vijeće” na kartici |
| Gradska skupština Grada Zagreba (`gradska-skupstina-grada-zagreba`) | Grad Zagreb | broj mandata po stranci danas | provjera izračuna za Zagreb (47 mjesta) |
| Skupovi podataka svake jedinice (`package_search`, organizacija jedinice) | jedinice | popis vlastitih skupova i njihovih tema | „N skupova podataka na data.gov.hr” na kartici |

Što data.gov.hr **nema**: sjednice, zapisnike ni glasovanja vijeća (provjereno na cijelom katalogu, 3.969 skupova),
pa njih uzimamo sa službenih stranica vijeća.

## 3. Po jedinicama

### Grad Zagreb
- **Službeni izvor:** web.zagreb.hr (sjednice Gradske skupštine) i YouTube kanal Gradske skupštine. Skupljač: `collect/docs.py`, `collect/list_videos.py`.
- **Što uzimamo:** dnevni red s predlagateljem i statusom; materijali po točki (dopis predlagatelja, prijedlog, obrazloženje); **PDF-ovi poimeničnog glasovanja** (kako je glasovao svaki zastupnik); nazočnost; pitanja zastupnika s odgovorima iz fonograma; zapisnik (PDF); snimke sjednica (YouTube).
- **U bazi:** 15 sjednica (14 sa zapisnikom), 588 točaka dnevnog reda (565 s ishodom glasovanja), 26.498 pojedinačnih glasova iz poimeničnog glasovanja; snimke: 33 (4 pretvoreno u tekst); objave: 203.
- **S data.gov.hr:** 767.131 stanovnika (DZS 2021.), 688.411 birača (registar 2026.), porez na dohodak 23 % / 33 % (2026.); vijeće 47 mjesta i izlaznost 42,65 % (DIP 2025.); vlastitih skupova podataka na portalu: 210.

### Grad Šibenik
- **Službeni izvor:** sibenik.hr (stranica saziva 2025.–2029., stranica svake sjednice, najava s materijalima). Skupljač: `collect/sibenik.py`.
- **Što uzimamo:** materijali iz najave sjednice; doneseni akti (.docx); zapisnik (PDF; konstituirajuća sjednica je sken, OCR) sa sažetkom svakog govornika i glasovanjem; snimke (YouTube).
- **U bazi:** 7 sjednica (6 sa zapisnikom), 236 točaka dnevnog reda (176 s ishodom glasovanja); snimke: 7 (0 pretvoreno u tekst); objave: 131.
- **S data.gov.hr:** 42.599 stanovnika (DZS 2021.), 39.718 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 21 mjesta i izlaznost 37,38 % (DIP 2025.); vlastitih skupova podataka na portalu: 23.

### Grad Opatija
- **Službeni izvor:** sjednice.opatija.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice i datumi, točke dnevnog reda, dokumenti po točki, zapisnici (dio skeniran, OCR).
- **U bazi:** 14 sjednica (13 sa zapisnikom), 177 točaka dnevnog reda (137 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 89.
- **S data.gov.hr:** 10.619 stanovnika (DZS 2021.), 10.031 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 15 mjesta i izlaznost 42,88 % (DIP 2025.); vlastitih skupova podataka na portalu: 2.

### Grad Rijeka
- **Službeni izvor:** rijeka.hr (stranice sjednica). Skupljač: `collect/rijeka.py`.
- **Što uzimamo:** dnevni red (blokovi „Točka N.”) s materijalima i donesenim aktima; status točke; zaključci odbora; zapisnik (PDF) s aktualnim satom i rezultatom glasovanja; vijesti sa sjednice (za sjednice bez zapisnika); snimke (YouTube).
- **U bazi:** 13 sjednica (11 sa zapisnikom), 174 točaka dnevnog reda (124 s ishodom glasovanja); snimke: 16 (0 pretvoreno u tekst); objave: 79.
- **S data.gov.hr:** 107.964 stanovnika (DZS 2021.), 99.672 birača (registar 2026.), porez na dohodak 20 % / 25 % (2026.); vijeće 31 mjesta i izlaznost 34,82 % (DIP 2025.); vlastitih skupova podataka na portalu: 181.

### Grad Ogulin
- **Službeni izvor:** gradogulin.esjednice.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice i datumi, točke dnevnog reda, dokumenti po točki, zapisnici (dio skeniran, OCR), popis tonskih zapisa (MP3).
- **U bazi:** 8 sjednica (7 sa zapisnikom), 178 točaka dnevnog reda (145 s ishodom glasovanja); snimke: 21 (0 pretvoreno u tekst); objave: 72.
- **S data.gov.hr:** 12.246 stanovnika (DZS 2021.), 10.454 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 15 mjesta i izlaznost 56,59 % (DIP 2025.); vlastitih skupova podataka na portalu: 18.

### Grad Krk
- **Službeni izvor:** grad-krk.hr (sazivi, vijesti sa sjednica, aktualni sat). Skupljač: `collect/krk.py`.
- **Što uzimamo:** saziv s dnevnim redom i materijalima; vijesti o ishodu (zbroj glasova u tekstu); aktualni sat; **skenirani zapisnici (bez teksta, čitamo OCR-om, tesseract)**; tonski zapisi (MP3).
- **U bazi:** 8 sjednica (6 sa zapisnikom), 125 točaka dnevnog reda (86 s ishodom glasovanja); snimke: 5 (0 pretvoreno u tekst); objave: 69.
- **S data.gov.hr:** 6.816 stanovnika (DZS 2021.), 6.491 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 13 mjesta i izlaznost 38,33 % (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Slavonski Brod
- **Službeni izvor:** slavonski-brod.hr (stranice sjednica). Skupljač: `collect/brod.py`.
- **Što uzimamo:** dnevni red (jedan PDF materijala po točki); gotovo doslovni zapisnik (PDF) s nazočnošću i zbrojem glasova; **tonski zapis (MP3) svake sjednice**.
- **U bazi:** 10 sjednica (8 sa zapisnikom), 180 točaka dnevnog reda (105 s ishodom glasovanja); snimke: 12 (12 pretvoreno u tekst); objave: 67.
- **S data.gov.hr:** 49.891 stanovnika (DZS 2021.), 49.788 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 21 mjesta i izlaznost 35,81 % (DIP 2025.); vlastitih skupova podataka na portalu: 9.

### Grad Čakovec
- **Službeni izvor:** cakovec.hr (kategorija Gradsko vijeće, objava „Održana N. sjednica”). Skupljač: `collect/cakovec.py`, `collect/audio_sites.py`.
- **Što uzimamo:** dnevni red s materijalom po točki; **doslovni zapisnik** (PDF; 4. sjednica je sken, OCR) s formulom glasovanja za svaku odluku; izvod iz zapisnika; **audio zapis (MP3)**.
- **U bazi:** 7 sjednica (7 sa zapisnikom), 180 točaka dnevnog reda (175 s ishodom glasovanja); snimke: 1 (1 pretvoreno u tekst); objave: 62.
- **S data.gov.hr:** 27.122 stanovnika (DZS 2021.), 23.792 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 19 mjesta i izlaznost 40,68 % (DIP 2025.); vlastitih skupova podataka na portalu: 4.

### Grad Osijek
- **Službeni izvor:** osijek.hr/prijenos-sjednice (popis svih sjednica), dokumenti na uredsko.zio.hr. Skupljač: `collect/osijek.py`.
- **Što uzimamo:** dnevni red s materijalima (PDF); zapisnik (PDF, priložen uz točku „usvajanje zapisnika” neke kasnije sjednice); audio arhiva (ZIP) i YouTube.
- **U bazi:** 10 sjednica (5 sa zapisnikom), 301 točaka dnevnog reda (175 s ishodom glasovanja); snimke: 9 (0 pretvoreno u tekst); objave: 59.
- **S data.gov.hr:** 96.313 stanovnika (DZS 2021.), 86.929 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 27 mjesta i izlaznost 33,32 % (DIP 2025.); vlastitih skupova podataka na portalu: 31.

### Općina Viškovo
- **Službeni izvor:** sjednice.opcina-viskovo.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice i datumi, točke dnevnog reda, dokumenti po točki, zapisnici (dio skeniran, OCR).
- **U bazi:** 14 sjednica (12 sa zapisnikom), 179 točaka dnevnog reda (125 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 53.
- **S data.gov.hr:** 16.084 stanovnika (DZS 2021.), 14.891 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 15 mjesta i izlaznost 28,32 % (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Senj
- **Službeni izvor:** gradsenj.esjednice.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice i datumi, točke dnevnog reda, dokumenti po točki, zapisnici (dio skeniran, OCR).
- **U bazi:** 12 sjednica (11 sa zapisnikom), 145 točaka dnevnog reda (131 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 50.
- **S data.gov.hr:** 5.973 stanovnika (DZS 2021.), 5.923 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 13 mjesta i izlaznost 54,72 % (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Kastav
- **Službeni izvor:** sjednice.kastav.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice i datumi, točke dnevnog reda, dokumenti po točki, zapisnici (dio skeniran, OCR).
- **U bazi:** 11 sjednica (10 sa zapisnikom), 116 točaka dnevnog reda (87 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 48.
- **S data.gov.hr:** 10.202 stanovnika (DZS 2021.), 9.554 birača (registar 2026.), porez na dohodak 20 % / 31 % (2026.); vijeće 15 mjesta i izlaznost 35,51 % (DIP 2025.); vlastitih skupova podataka na portalu: 1.

### Općina Punat
- **Službeni izvor:** sjednice.punat.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice i datumi, točke dnevnog reda, dokumenti po točki, zapisnici (dio skeniran, OCR).
- **U bazi:** 10 sjednica (9 sa zapisnikom), 199 točaka dnevnog reda (157 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 32.
- **S data.gov.hr:** 1.900 stanovnika (DZS 2021.), 1.963 birača (registar 2026.), porez na dohodak 15 % / 30 % (2026.); vijeće 9 mjesta i izlaznost 57,27 % (DIP 2025.); vlastitih skupova podataka na portalu: 11.

### Općina Baška
- **Službeni izvor:** opcinabaska.esjednice.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice, točke dnevnog reda i donesene odluke; zapisnici nisu objavljeni na portalu, pa nema glasovanja.
- **U bazi:** 10 sjednica (0 sa zapisnikom), 139 točaka dnevnog reda (0 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 0.
- **S data.gov.hr:** 1.656 stanovnika (DZS 2021.), 1.891 birača (registar 2026.), porez na dohodak 15 % / 25 % (2026.); vijeće 9 mjesta i izlaznost 61,2 % (DIP 2025.); vlastitih skupova podataka na portalu: 4.

### Općina Čavle
- **Službeni izvor:** opcinacavle.esjednice.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice, točke dnevnog reda i donesene odluke; zapisnici nisu objavljeni na portalu, pa nema glasovanja.
- **U bazi:** 11 sjednica (0 sa zapisnikom), 148 točaka dnevnog reda (0 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 0.
- **S data.gov.hr:** 7.059 stanovnika (DZS 2021.), 6.246 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 13 mjesta i izlaznost 32,09 % (DIP 2025.); vlastitih skupova podataka na portalu: 11.

### Općina Kostrena
- **Službeni izvor:** sjednice.kostrena.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: samo donesene odluke (portal nema točke dnevnog reda ni zapisnike).
- **U bazi:** 10 sjednica (0 sa zapisnikom), 138 točaka dnevnog reda (0 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 0.
- **S data.gov.hr:** 4.398 stanovnika (DZS 2021.), 4.153 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 13 mjesta i izlaznost 52,49 % (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Makarska
- **Službeni izvor:** gradmakarska.esjednice.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice, točke dnevnog reda i donesene odluke; zapisnici nisu objavljeni na portalu, pa nema glasovanja.
- **U bazi:** 8 sjednica (0 sa zapisnikom), 107 točaka dnevnog reda (0 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 0.
- **S data.gov.hr:** 13.301 stanovnika (DZS 2021.), 15.384 birača (registar 2026.), porez na dohodak 18 % / 31 % (2026.); vijeće 15 mjesta i izlaznost 44,0 % (DIP 2025.); vlastitih skupova podataka na portalu: 13.

### Grad Novi Vinodolski
- **Službeni izvor:** sjednice.novi-vinodolski.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice, točke dnevnog reda i donesene odluke; zapisnici nisu objavljeni na portalu, pa nema glasovanja.
- **U bazi:** 9 sjednica (0 sa zapisnikom), 75 točaka dnevnog reda (0 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 0.
- **S data.gov.hr:** 4.328 stanovnika (DZS 2021.), 4.995 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 13 mjesta i izlaznost 49,89 % (DIP 2025.); vlastitih skupova podataka na portalu: 2.

### Općina Omišalj
- **Službeni izvor:** opcinaomisalj.esjednice.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice, točke dnevnog reda i donesene odluke; zapisnici nisu objavljeni na portalu, pa nema glasovanja.
- **U bazi:** 9 sjednica (0 sa zapisnikom), 137 točaka dnevnog reda (0 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 0.
- **S data.gov.hr:** 2.992 stanovnika (DZS 2021.), 3.111 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 13 mjesta i izlaznost 40,01 % (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Ploče
- **Službeni izvor:** gradploce.esjednice.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice, točke dnevnog reda i donesene odluke; zapisnici nisu objavljeni na portalu, pa nema glasovanja, popis snimki.
- **U bazi:** 9 sjednica (0 sa zapisnikom), 99 točaka dnevnog reda (0 s ishodom glasovanja); snimke: 7 (0 pretvoreno u tekst); objave: 0.
- **S data.gov.hr:** 8.220 stanovnika (DZS 2021.), 7.761 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 13 mjesta i izlaznost 61,53 % (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Split
- **Službeni izvor:** sjednice.split.hr (NetCom eSjednice, javni portal). Skupljač: `collect/netcom.py` (zajednički za 14 jedinica).
- **Što uzimamo:** eSjednice: sjednice, točke dnevnog reda, dokumenti po točki, zapisnici.
- **U bazi:** 18 sjednica (17 sa zapisnikom), 436 točaka dnevnog reda (193 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 33.
- **S data.gov.hr:** 160.577 stanovnika (DZS 2021.), 143.237 birača (registar 2026.), porez na dohodak 22 % / 32 % (2026.); vijeće 31 mjesta, izlaznost 37,3 % i 87.968 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 3.

### Grad Zadar
- **Službeni izvor:** grad-zadar.hr (popis sjednica i stranica svake sjednice). Skupljač: `collect/zadar.py`.
- **Što uzimamo:** dnevni red s materijalom po točki; službeni **izvadak iz zapisnika** (priložen uz sljedeću sjednicu; skenovi, OCR) s glasovanjem po točki; snimke (YouTube).
- **U bazi:** 14 sjednica (13 sa zapisnikom), 287 točaka dnevnog reda (187 s ishodom glasovanja); snimke: 18 (0 pretvoreno u tekst); objave: 26.
- **S data.gov.hr:** 70.779 stanovnika (DZS 2021.), 64.463 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 27 mjesta, izlaznost 37,12 % i 38.959 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Pula
- **Službeni izvor:** pula.hr (sjednice Gradskog vijeća; robots.txt traži razmak od 10 s, poštujemo ga). Skupljač: `collect/pula.py`.
- **Što uzimamo:** dnevni red s materijalima; **skraćeni zapisnik** (tekst) s glasovanjem po točki.
- **U bazi:** 14 sjednica (12 sa zapisnikom), 276 točaka dnevnog reda (227 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 20.
- **S data.gov.hr:** 52.220 stanovnika (DZS 2021.), 47.783 birača (registar 2026.), porez na dohodak 22 % / 32 % (2026.); vijeće 21 mjesta, izlaznost 40,85 % i 27.855 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Karlovac
- **Službeni izvor:** karlovac.hr (WordPress API sjednica; dnevni red i paket materijala). Skupljač: `collect/karlovac.py`.
- **Što uzimamo:** dnevni red (Word); zapisnici prethodnih sjednica u paketu materijala (čita se samo ta datoteka iz ZIP-a, bez preuzimanja cijelog paketa); snimke (YouTube kanal Grada).
- **U bazi:** 21 sjednica (17 sa zapisnikom), 292 točaka dnevnog reda (286 s ishodom glasovanja); snimke: 25 (0 pretvoreno u tekst); objave: 14.
- **S data.gov.hr:** 49.377 stanovnika (DZS 2021.), 44.575 birača (registar 2026.), porez na dohodak 19 % / 29 % (2026.); vijeće 21 mjesta, izlaznost 40,74 % i 25.928 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 20.

### Grad Varaždin
- **Službeni izvor:** varazdin.hr (stranice sjednica). Skupljač: `collect/varazdin.py`.
- **Što uzimamo:** dnevni red s materijalom po točki; **skraćeni zapisnik** (potpisani sken, OCR) s glasovanjem; snimka svake sjednice (YouTube).
- **U bazi:** 10 sjednica (7 sa zapisnikom), 378 točaka dnevnog reda (257 s ishodom glasovanja); snimke: 10 (0 pretvoreno u tekst); objave: 39.
- **S data.gov.hr:** 43.782 stanovnika (DZS 2021.), 38.582 birača (registar 2026.), porez na dohodak 21 % / 32 % (2026.); vijeće 21 mjesta, izlaznost 39,27 % i 23.115 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 14.

### Grad Dubrovnik
- **Službeni izvor:** dubrovnik.hr (sazivi sjednica) i paketi materijala na cloud.dubrovnik.hr. Skupljač: `collect/dubrovnik.py`.
- **Što uzimamo:** saziv s predloženim dnevnim redom; snimke (YouTube). Zapisnici nisu objavljeni kao zasebne stranice, ali paket materijala sljedeće sjednice sadrži **zapisnik** prethodne. cloud.dubrovnik.hr u robots.txt zabranjuje automatski pristup, pa skupljač ne dira taj poslužitelj: pakete je preuzela osoba preko javne poveznice Grada, a skupljač čita lokalne datoteke (zasad zapisnik 12. sjednice i materijali 12. i 13.).
- **U bazi:** 13 sjednica (1 sa zapisnikom), 340 točaka dnevnog reda (57 s ishodom glasovanja); snimke: 14 (0 pretvoreno u tekst); objave: 31.
- **S data.gov.hr:** 41.562 stanovnika (DZS 2021.), 37.758 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 21 mjesta, izlaznost 47,01 % i 19.451 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 9.

### Grad Sisak
- **Službeni izvor:** sisak.hr (stranice sjednica, zapisnici). Skupljač: `collect/sisak.py`.
- **Što uzimamo:** dnevni red s PDF-om po točki; **zapisnici** (skenovi, OCR); za sjednice 6–9 nacrti zapisnika iz materijala sljedeće sjednice (označeni kao nacrt).
- **U bazi:** 11 sjednica (10 sa zapisnikom), 193 točaka dnevnog reda (173 s ishodom glasovanja); snimke: 0 (0 pretvoreno u tekst); objave: 12.
- **S data.gov.hr:** 40.121 stanovnika (DZS 2021.), 36.771 birača (registar 2026.), porez na dohodak 22 % / 32 % (2026.); vijeće 21 mjesta, izlaznost 50,53 % i 18.035 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 4.

### Grad Kaštela
- **Službeni izvor:** kastela.hr (mandatno razdoblje 2025.–2029.). Skupljač: `collect/kastela.py`.
- **Što uzimamo:** poziv s dnevnim redom, PDF po točki; **zapisnik** kao točka sljedeće sjednice (dio skeniran, OCR); snimke (YouTube).
- **U bazi:** 9 sjednica (8 sa zapisnikom), 244 točaka dnevnog reda (205 s ishodom glasovanja); snimke: 8 (0 pretvoreno u tekst); objave: 9.
- **S data.gov.hr:** 37.794 stanovnika (DZS 2021.), 36.844 birača (registar 2026.), porez na dohodak 20 % / 30 % (2026.); vijeće 21 mjesta, izlaznost 29,24 % i 25.058 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 0.

### Grad Bjelovar
- **Službeni izvor:** bjelovar.hr (najave sjednica, kategorija Zapisnici). Skupljač: `collect/bjelovar.py`.
- **Što uzimamo:** poziv s dnevnim redom i materijalima; **zapisnici** (.docx); snimke (YouTube kanal Grada).
- **U bazi:** 12 sjednica (11 sa zapisnikom), 306 točaka dnevnog reda (263 s ishodom glasovanja); snimke: 5 (0 pretvoreno u tekst); objave: 2.
- **S data.gov.hr:** 36.316 stanovnika (DZS 2021.), 31.792 birača (registar 2026.), porez na dohodak 18 % / 25 % (2026.); vijeće 21 mjesta, izlaznost 36,57 % i 19.991 birača koji nisu glasovali (DIP 2025.); vlastitih skupova podataka na portalu: 6.

### Grad Velika Gorica (u izradi)
- **Službeni izvor:** gorica.hr (sjednice Gradskog vijeća). Skupljač: `collect/audio_sites.py`.
- **Što uzimamo:** audio zapise sjednica (MP3); zadnja sjednica (8., oko 7 sati) pretvorena je u tekst. Zapisnici su
  na OneDriveu, pa zasad nema dnevnog reda ni glasovanja u bazi i nema objava.

### Grad Samobor (nije obuhvaćen)
- Portal eSjednice Grada Samobora ima samo jednu sjednicu iz 2018.; vijeće objavljuje na samobor.hr, za koji skupljač još nije napisan.

### Grad Petrinja (u izradi)
- **Službeni izvor:** petrinja.hr (snimke sjednica). Poslužitelj je dvaput prekinuo vezu, pa ga zasad ne pitamo dalje.
