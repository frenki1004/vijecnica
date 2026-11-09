# eVijećnica

**Demo:** https://vijecnica.vercel.app (1.186 objava iz 22 grada i općine; strojni nacrti, javni demo bez prijave)

eVijećnica prikuplja službene podatke o sjednicama gradskih i općinskih vijeća (dnevni red, zapisnike, rezultate glasovanja, poimenično glasovanje, pitanja vijećnika i snimke sjednica), sprema ih u jednu pretraživu bazu i iz njih izrađuje kratke, neutralne objave za društvene mreže, s oznakom grada i teme (`#Zagreb #promet`).

**Za koga:** prvenstveno za mlade od 16 do 30 godina koji lokalnu politiku ne prate jer je teško čitljiva (dnevni red na jednoj stranici, glasovanje u PDF-u, zapisnik tjednima kasnije). Isti podaci služe novinarima, udrugama i istraživačima (JSON API, MCP poslužitelj za AI agente, CSV izvoz) te samim gradovima kao uzor strojno čitljive objave.

**Zašto:** odluke vijeća izravno utječu na promet, vrtiće, odvoz otpada i lokalne poreze, a podaci o njima su javni, ali razasuti i u formatima koji nisu strojno čitljivi.

Projekt je prijavljen na Datathon Portala otvorenih podataka (MPUDT), izazov A „Društvo i javne usluge”; uvjeti su u dokumentu „Javni poziv za sudjelovanje u Datathonu Portala otvorenih podataka (MPUDT)”.

- Tehnička arhitektura, standardi, integracija i preduvjeti: [ARHITEKTURA.md](ARHITEKTURA.md)
- Pitch (3 minute): [reports/pitch_hr.md](reports/pitch_hr.md)
- Licenca koda: [EUPL-1.2](LICENSE)

## Stanje 8. 11. 2026.

Brojke su iz `data/vijecnica.db` i `data/posts/posts.json`; upiti za provjeru su u [ARHITEKTURA.md](ARHITEKTURA.md#provjera-brojki).

| | |
|---|---|
| jedinice lokalne samouprave | 29, od toga 13 od 15 najvećih gradova (saziv 2025.–2029.) |
| sjednice | 327 (od toga 6 zakazanih, s dnevnim redom) |
| točke dnevnog reda | 6.373 |
| točke s ishodom glasovanja (rezultat ili broj glasova) | 4.036 |
| pojedinačni glasovi iz poimeničnog glasovanja (samo Zagreb, 565 točaka) | 26.498 |
| pitanja vijećnika s odgovorom (Zagreb, Rijeka, Krk) | 343 |
| snimke sjednica / strojno transkribirane | 191 / 26 |
| objave za društvene mreže | 1.200 iz 22 jedinice (1.075 o pojedinoj točki, 125 pregleda jednoglasnih odluka); za zadnje sjednice pisane i iz materijala i snimki |
| slike za Instagram (1080×1350) | 4.016 |

### Pokrivenost po jedinicama

„Ishod” = točke kojima je poznat rezultat ili broj glasova. „Zapisnici” = sjednice za koje je preuzet tekst zapisnika.

| jedinica | skupljač | što daje izvor | sjednice | zapisnici | točke | s ishodom | objave |
|---|---|---|---|---|---|---|---|
| Zagreb | `collect/docs.py`, `list_videos.py` | dnevni red, poimenično glasovanje (PDF), nazočnost, pitanja s fonogramom, zapisnici, snimke (YouTube) | 15 | 14 | 588 | 565 | 203 |
| Šibenik | `collect/sibenik.py` | dnevni red, akti (.docx), zapisnici, snimke (YouTube) | 7 | 6 | 236 | 176 | 131 |
| Opatija | `collect/netcom.py` | eSjednice: dnevni red, dokumenti, zapisnici | 14 | 13 | 177 | 137 | 89 |
| Rijeka | `collect/rijeka.py` | dnevni red, doneseni akti, zapisnici, vijesti sa sjednica, pitanja, snimke (YouTube) | 13 | 11 | 174 | 124 | 79 |
| Ogulin | `collect/netcom.py` | eSjednice: dnevni red, zapisnici, popis snimki | 8 | 7 | 178 | 145 | 72 |
| Krk | `collect/krk.py` | dnevni red, skenirani zapisnici (OCR), vijesti sa sjednica, aktualni sat, snimke (MP3) | 8 | 6 | 125 | 86 | 69 |
| Slavonski Brod | `collect/brod.py` | dnevni red, gotovo doslovni zapisnici, snimke (MP3) | 10 | 8 | 180 | 105 | 67 |
| Čakovec | `collect/cakovec.py` | dnevni red s materijalima, doslovni zapisnici (dio skeniran, OCR), snimke (MP3) | 7 | 7 | 180 | 175 | 62 |
| Osijek | `collect/osijek.py` | dnevni red s materijalima, zapisnici, snimke (audio, YouTube) | 10 | 5 | 301 | 175 | 59 |
| Viškovo | `collect/netcom.py` | eSjednice: dnevni red, zapisnici (dio skeniran, OCR) | 14 | 12 | 179 | 125 | 53 |
| Senj | `collect/netcom.py` | eSjednice: dnevni red, zapisnici | 12 | 11 | 145 | 131 | 50 |
| Kastav | `collect/netcom.py` | eSjednice: dnevni red, zapisnici | 11 | 10 | 116 | 87 | 48 |
| Varaždin | `collect/varazdin.py` | dnevni red s materijalima, skraćeni zapisnici (skenovi, OCR), snimke (YouTube) | 10 | 7 | 378 | 257 | 39 |
| Split | `collect/netcom.py` | eSjednice: dnevni red, dokumenti, zapisnici | 18 | 17 | 436 | 193 | 33 |
| Punat | `collect/netcom.py` | eSjednice: dnevni red, zapisnici | 10 | 9 | 199 | 157 | 32 |
| Dubrovnik | `collect/dubrovnik.py` | saziv s dnevnim redom, snimke (YouTube); zapisnik i materijali iz paketa materijala preuzetog ručno | 13 | 1 | 340 | 57 | 31 |
| Zadar | `collect/zadar.py` | dnevni red s materijalima, izvadci iz zapisnika (skenovi, OCR), snimke (YouTube) | 14 | 13 | 287 | 187 | 26 |
| Pula | `collect/pula.py` | dnevni red s materijalima, skraćeni zapisnici | 14 | 12 | 276 | 227 | 20 |
| Karlovac | `collect/karlovac.py` | dnevni red, zapisnici (Word, u paketu materijala), snimke (YouTube) | 21 | 17 | 292 | 286 | 14 |
| Sisak | `collect/sisak.py` | dnevni red s materijalima, zapisnici (skenovi, OCR) | 11 | 10 | 193 | 173 | 12 |
| Kaštela | `collect/kastela.py` | dnevni red s materijalima, zapisnici (dio skeniran, OCR), snimke (YouTube) | 9 | 8 | 244 | 205 | 9 |
| Bjelovar | `collect/bjelovar.py` | najave s materijalima, zapisnici (.docx), snimke (YouTube) | 12 | 11 | 306 | 263 | 2 |
| Kostrena | `collect/netcom.py` | eSjednice: samo donesene odluke | 10 | 0 | 138 | 0 | 0 |
| Novi Vinodolski | `collect/netcom.py` | eSjednice: dnevni red, odluke | 9 | 0 | 75 | 0 | 0 |
| Makarska | `collect/netcom.py` | eSjednice: dnevni red, odluke | 8 | 0 | 107 | 0 | 0 |
| Ploče | `collect/netcom.py` | eSjednice: dnevni red, odluke, popis snimki | 9 | 0 | 99 | 0 | 0 |
| Omišalj | `collect/netcom.py` | eSjednice: dnevni red, odluke | 9 | 0 | 137 | 0 | 0 |
| Baška | `collect/netcom.py` | eSjednice: dnevni red, odluke | 10 | 0 | 139 | 0 | 0 |
| Čavle | `collect/netcom.py` | eSjednice: dnevni red, odluke | 11 | 0 | 148 | 0 | 0 |
| **ukupno** | | | **327** | **215** | **6.373** | **4.036** | **1.200** |

15 gradova ima vlastiti skupljač; 14 jedinica na sustavu NetCom eSjednice pokriva jedan zajednički skupljač (`collect/netcom.py`). Za sedam jedinica bez preuzetih zapisnika (redovi s 0 zapisnika) baza ima dnevni red i odluke, ali ne i glasovanje, pa iz njih zasad nema objava.

Snimke: strojno je transkribirano 26 snimki (sve 12 Slavonskog Broda, 4 Zagreba, 3 Ogulina, po 2 Krka i Rijeke, po jedna Čakovca, Osijeka i Šibenika), uglavnom zadnje sjednice; transkribirana je i zadnja sjednica Velike Gorice (7 sati, `collect/audio_sites.py`), koja još nije u bazi jer za nju nema skupljača zapisnika. Ostale snimke su popisane (`videos`), ali još nisu transkribirane.

Detaljni pregled po sjednici i točki (web stranica `/`, JSON API, MCP alati) trenutačno je izrađen za Zagreb, Slavonski Brod, Krk i Rijeku; feed objava (`/feed`) pokriva sve 22 jedinice s objavama. Vidi [ograničenja](ARHITEKTURA.md#10-ograničenja-i-daljnji-razvoj).

## Quickstart

Ubuntu 24.04, Python 3.12 (transkripcija na Apple siliconu: macOS).

```bash
# sustavni alati: pdftotext/pdftoppm (zapisnici i glasovanja), tesseract + hrvatski jezik (skenirani zapisnici),
# ffmpeg (audio), node (yt-dlp za YouTube)
sudo apt install poppler-utils tesseract-ocr tesseract-ocr-hrv ffmpeg nodejs
pipx install yt-dlp

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. prikupljanje (svaki skupljač kešira preuzeto u data/<jedinica>/raw/ i piše data/<jedinica>/docs/session_NN.json)
.venv/bin/python collect/list_videos.py            # Zagreb: popis snimki s YouTubea -> data/videos.json
.venv/bin/python collect/docs.py                   # Zagreb: sve sjednice; ili: collect/docs.py 14 15; collect/docs.py --refresh-latest 2
.venv/bin/python collect/brod.py --audio           # Slavonski Brod (--audio preuzima i MP3 snimke)
.venv/bin/python collect/krk.py                    # Krk (--audio preuzima i MP3 snimke)
.venv/bin/python collect/rijeka.py                 # Rijeka (--fresh ponovno dohvaća stranice)
.venv/bin/python collect/osijek.py                 # Osijek (--fresh)
.venv/bin/python collect/sibenik.py                # Šibenik (--fresh)
.venv/bin/python collect/netcom.py                 # 13 jedinica na eSjednicama; ili: collect/netcom.py opatija senj [--fresh]

# 2. baza (SQLite + FTS5), gradi se iznova iz JSON-a za nekoliko sekundi
.venv/bin/python db/build.py

# 3. web, JSON API i MCP poslužitelj
.venv/bin/python mcp_server.py --http 8103         # http://localhost:8103 (/, /feed, /demo, /api/..., /mcp)
.venv/bin/python mcp_server.py                     # bez --http: MCP preko stdio (Claude Desktop, Claude Code)

# 4. otvoreni podaci: CSV + datapackage.json u data/export/
.venv/bin/python export/export.py
export/check_rebuild.sh                            # ponovna izgradnja bez mreže i usporedba sha256 izvoza
```

Objave (koraci su opisani u [ARHITEKTURA.md](ARHITEKTURA.md#3-tok-podataka)):

```bash
.venv/bin/python posts/build_queue.py --city brod --last 3 > data/posts/queue_brod.json   # odabir točaka po pravilu
# pisac (LLM) prema posts/writer_prompt.md: queue_<grad>.json -> data/posts/drafts_<grad>.json
.venv/bin/python posts/assemble.py                  # spaja nacrte s glasovima i oznakama -> data/posts/posts.json
uv run --with playwright python posts/export_png.py # PNG karuseli 1080x1350 (poslužitelj mora raditi)
.venv/bin/python posts/export_reddit.py             # Markdown za ručnu objavu na Redditu -> data/posts/reddit/
```

Dnevno osvježavanje (Zagreb, cron): `run_daily.sh`.

### Transkripcija snimki (neobavezno)

- **CPU:** `.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 && .venv/bin/pip install -r requirements-asr.txt`, zatim `.venv/bin/python asr/transcribe_local.py --city brod --threads 3` (faster-whisper large-v3-turbo + Silero VAD).
- **Apple silicon:** `asr/transcribe_mlx_local.py --city brod` lokalno ili `asr/run_queue.py` na udaljenom Macu (mlx-whisper s modelom `GoranS/whisper-large-v3-turbo-hr-parla`, pretvorenim s `asr/convert_hf.py`). Udaljeni Mac: `VIJECNICA_ASR_HOST` (ili `config_local.py`, vidi `config_local.example.py`) i `VIJECNICA_ASR_ROOT`.
- Točnost: na 9. sjednici Slavonskog Broda WER 0,309 prema gotovo doslovnom zapisniku (88 od 95 odlomaka koje zapisnik prenosi, 11.817 riječi), a svih 11 rezultata glasovanja koje je predsjedatelj izgovorio s brojem glasova prepoznato je točno (`eval_brod.py`, `reports/asr_eval_brod_9.json`).

## Kako radi, ukratko

```
collect/*.py ──> data/<jedinica>/docs/*.json ──> db/build.py ──> data/vijecnica.db (SQLite + FTS5)
asr/*.py ─────> data/**/transcripts/*.json ──┘                         │
                                                                       ├─> mcp_server.py: web (/), JSON API (/api/*), MCP (/mcp)
                                                                       ├─> export/export.py: CSV + datapackage.json (CKAN / Frictionless)
                                                                       └─> posts/build_queue.py -> LLM pisac -> posts/assemble.py
                                                                              └─> /feed, export_png.py (Instagram), export_reddit.py (Reddit)
```

1. **Prikupljanje:** skupljači čitaju službene web stranice i portale (HTML, PDF, DOCX, JSON odgovore eSjednica), sve keširaju i ne zaobilaze zabrane pristupa (najviše jedan zahtjev u sekundi po portalu eSjednica).
2. **Parsiranje:** iz zapisnika se izdvajaju dijelovi po točkama i rečenice o glasovanju; dijelovi se povezuju s točkama dnevnog reda **po naslovu**, a ne po broju.
3. **Baza:** `db/build.py` gradi SQLite bazu s FTS5 pretraživanjem (bez obzira na dijakritike) iz JSON datoteka, koje su izvor istine.
4. **Objave:** fiksno pravilo bira točke (svaka s barem jednim glasom protiv ili suzdržanim dobiva objavu, ostale idu u pregled „Ukratko”), LLM piše tekst prema javnim pravilima, kod dodaje glasove, izvor i oznake, a osoba pregledava prije objave.
5. **Objava podataka:** CSV i Frictionless `datapackage.json` spremni za CKAN (data.gov.hr), JSON API i MCP.

## Izvori podataka

- **Portal otvorenih podataka (data.gov.hr, CKAN API):** konektor `collect/datagovhr.py` preko CKAN API-ja (`package_show`) preuzima registar svih 556 jedinica (živi JSON API jpt.gov.hr: oznaka, OIB, županija), adresar s web-stranicama, popis stanovništva 2021., broj birača po jedinici (registar birača, 2026.), porezne stope 2025. i 2026. te sastav Gradske skupštine Zagreba, i popisuje skupove koje naših 20 jedinica samo objavljuje. Rezultati lokalnih izbora 2025. nisu na portalu (DIP ondje ima do 2021.), pa se uzimaju s izbori.hr i preračunavaju u mandate (D'Hondt, prag 5 %). `db/build.py` sve povezuje u pogled `city_overview` (tko ima većinu, odaziv, birači, uz broj sjednica i glasovanja). Pokretanje: `../.venv/bin/python collect/datagovhr.py [--voters]`, pa `db/build.py`. data.gov.hr je ujedno i predviđeno odredište objave: izvoz (`data/export/datapackage.json`) pripremljen je za CKAN, ali na portalu još ništa nije objavljeno.
- **Službene stranice gradova:** web.zagreb.hr, slavonski-brod.hr, grad-krk.hr, rijeka.hr, osijek.hr, sibenik.hr.
- **NetCom eSjednice:** javni portali 13 jedinica (sjednice.opatija.hr, gradsenj.esjednice.hr, …; popis u `collect/netcom.py`, `UNITS`).
- **Snimke sjednica:** YouTube kanali gradova (Zagreb, Rijeka, Osijek, Šibenik) i MP3 zapisi na gradskim stranicama (Slavonski Brod, Krk) ili eSjednicama.
- **Model za prepoznavanje govora:** `GoranS/whisper-large-v3-turbo-hr-parla` (Whisper doučen na hrvatskom korpusu ParlaSpeech) i `faster-whisper large-v3-turbo`.

Svaka preuzeta datoteka zapisana je u `data/export/raw_manifest.json` (sha256, veličina, vrijeme dohvata).

## Licence

- **Kod:** [European Union Public Licence v. 1.2 (EUPL-1.2)](LICENSE), službeni tekst Europske komisije.
- **Podaci: licenca je navedena po resursu** u `data/export/datapackage.json`:
  - Izvedeni podaci (struktura, stupci, strojni transkripti i njihovo vrijeme, prepoznati govornici, rezultati iz snimke, obećanja) objavljuju se pod licencom [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  - Službeni tekst koji se prenosi doslovno (naslovi točaka, pitanja, fonogrami, zapisnici) nije naš: za njega vrijede uvjeti izvora i ponovna uporaba informacija prema Zakonu o pravu na pristup informacijama (NN 25/13, 85/15, 69/22).
- Podaci su strojno obrađeni i mogu sadržavati pogreške; službeni dokumenti uvijek imaju prednost. Tekst objava piše AI uz ljudski pregled; to piše na zadnjem slajdu svake objave u feedu i u tekstu za Reddit.
