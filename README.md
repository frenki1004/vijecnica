# Vijećnica

Što je gradsko vijeće odlučilo, tko je kako glasao i što je rečeno na sjednici, s poveznicom na točan trenutak snimke. Zagreb i Slavonski Brod, saziv 2025.–2029.

- Web: http://localhost:8103 · MCP: http://localhost:8103/mcp · primjeri agenta: `/demo`
- Otvoreni podaci: `data/export/` (CKAN / Frictionless `datapackage.json`, licenca po resursu)
- Pitch (hrvatski): `reports/pitch_hr.md` · tehnički opis: `CLAUDE.md`
- Pokrivenost: transkribirano 1 od 33 zagrebačke snimke (14. sjednica, 4. dio) i 4 od 12 brodskih (8., 9., 10. sjednica); stanje u `list_cities` → `coverage`.

## Quickstart (Ubuntu 24.04, Python 3.12)
```bash
sudo apt install poppler-utils ffmpeg nodejs          # pdftotext -bbox (glasovanja), ffprobe/ffmpeg (audio), node (yt-dlp)
pipx install yt-dlp                                    # ili ~/.local/bin/yt-dlp; collect/list_videos.py ga zove s --js-runtimes node
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python collect/list_videos.py                # popis snimki Zagreba (YouTube)
.venv/bin/python collect/docs.py                       # Zagreb: dnevni red, glasovanja, nazočnost, pitanja, zapisnici
.venv/bin/python collect/brod.py --audio               # Slavonski Brod: sjednice, zapisnici, MP3 snimke
.venv/bin/python db/build.py && .venv/bin/python export/export.py
.venv/bin/python mcp_server.py --http 8103             # web + /mcp; bez --http = stdio za Claude Code
```
Offline rebuild (bez mreže, iz `data/docs`, `data/brod/docs` i transkripata) i usporedba hasheva izvoza: `export/check_rebuild.sh`.

## Transkripcija
- **CPU (bilo koje računalo):** `.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch && .venv/bin/pip install -r requirements-asr.txt`, zatim `.venv/bin/python asr/transcribe_local.py --city brod --threads 3` (faster-whisper + Silero VAD; ~1x realtime na 2 jezgre).
- **Apple silicon (brže):** `asr/run_queue.py` šalje audio na Mac i pokreće `asr/transcribe.py` (mlx-whisper, model `GoranS/whisper-large-v3-turbo-hr-parla` pretvoren s `asr/convert_hf.py`). Host i mapa: `VIJECNICA_ASR_HOST` (ili `ASR_HOST` u `config_local.py`, vidi `config_local.example.py`), `VIJECNICA_ASR_ROOT` (zadano `/Volumes/g710jobs`).
- Točnost: na 9. sjednici Slavonskog Broda ≈68 % riječi strojnog zapisa slaže se s gotovo doslovnim zapisnikom (WER 0,32 na 10 984 riječi, na 86 od 99 odlomaka koje zapisnik prenosi; `eval_brod.py`, metoda u izvještaju `reports/asr_eval_brod_9.json`).

## Izvor i licenca
Izvor: Grad Zagreb (web.zagreb.hr), Grad Slavonski Brod (slavonski-brod.hr); strojno izvedeni podaci.

Izvedeni podaci (struktura, transkripti, prepoznati govornici, rezultati iz snimke, obećanja) objavljuju se pod licencom [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Službeni tekst koji se prenosi doslovno (naslovi točaka, pitanja, fonogrami, zapisnici) nije naš: za njega vrijede uvjeti izvora i ponovna uporaba prema Zakonu o pravu na pristup informacijama. Licenca je navedena za svaki resurs u `datapackage.json`, uz `raw_manifest.json` (sha256 i vrijeme dohvata svake preuzete datoteke). Podaci su strojni i mogu sadržavati pogreške; službeni dokumenti uvijek imaju prednost. Ništa još nije objavljeno na data.gov.hr.
