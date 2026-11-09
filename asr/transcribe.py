"""Transcribe one audio file: Silero VAD cuts speech into <=25 s chunks, mlx-whisper decodes each.

The Croatian ParlaSpeech fine-tune lost timestamp prediction and hallucinates on silence
("Hvala." loops), so timing comes from the VAD and silence never reaches the decoder.

Usage: python transcribe.py <audio> <out.json> [model_dir] [city]
"""
import json
import re
import subprocess
import sys
import time

import mlx_whisper
import numpy as np
import torch
from silero_vad import get_speech_timestamps, load_silero_vad

SR = 16000
MAX_CHUNK = 25.0
PROMPTS = {
    "zagreb": ("Sjednica Gradske skupštine Grada Zagreba. Predsjednik Gradske skupštine, "
               "gradonačelnik Tomislav Tomašević, zastupnici, dnevni red, točka, glasovanje, "
               "zaključak, amandman, prijedlog odluke."),
    "brod": ("Sjednica Gradskog vijeća Grada Slavonskog Broda. Predsjednik Gradskog vijeća Hrvoje Andrić, "
             "gradonačelnik Mirko Duspara, vijećnici, dnevni red, točka, aktualni sat, glasovanje, "
             "zaključak, prijedlog odluke."),
    "krk": ("Sjednica Gradskog vijeća Grada Krka. Predsjednica Gradskog vijeća Iva Tabar, gradonačelnik Darijo "
            "Vasilić, vijećnici, dnevni red, točka, aktualni sat, glasovanje, zaključak, prijedlog odluke."),
    "rijeka": ("Sjednica Gradskog vijeća Grada Rijeke. Gradonačelnica Iva Rinčić, vijećnici, dnevni red, točka, "
               "aktualni sat, glasovanje, amandman, zaključak, prijedlog odluke."),
}
# units from collect/audio_sites.py: no names (we have no member list for them yet), only the vocabulary
for _key, _grad in (("cakovec", "Čakovca"), ("velika_gorica", "Velike Gorice"), ("petrinja", "Petrinje"),
                   ("osijek", "Osijeka"), ("sibenik", "Šibenika"), ("ogulin", "Ogulina")):
    PROMPTS[_key] = (f"Sjednica Gradskog vijeća Grada {_grad}. Predsjednik Gradskog vijeća, gradonačelnik, "
                     "vijećnici, dnevni red, točka, aktualni sat, glasovanje, zaključak, prijedlog odluke.")


def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-f", "s16le",
                          "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def speech_chunks(audio):
    """Merge VAD speech spans into chunks up to MAX_CHUNK s, cutting at the pauses between spans."""
    spans = get_speech_timestamps(torch.from_numpy(audio), load_silero_vad(), sampling_rate=SR,
                                  min_silence_duration_ms=400, speech_pad_ms=150,
                                  max_speech_duration_s=MAX_CHUNK)
    chunks, cur = [], None
    for s in spans:
        a, b = s["start"] / SR, s["end"] / SR
        if cur and b - cur[0] <= MAX_CHUNK and a - cur[1] < 2.0:
            cur[1] = b
        else:
            if cur:
                chunks.append(cur)
            cur = [a, b]
    if cur:
        chunks.append(cur)
    return chunks


def is_junk(text):
    words = re.findall(r"\w+", text.lower())
    if not words:
        return True
    # a word looped many times = decoder stuck
    return len(words) >= 8 and len(set(words)) / len(words) < 0.25


def main(audio_path, out, model="mlx_models/hr-parla", city="zagreb"):
    t0 = time.time()
    audio = load_audio(audio_path)
    chunks = speech_chunks(audio)
    t_vad = time.time() - t0
    segs = []
    for a, b in chunks:
        r = mlx_whisper.transcribe(audio[int(a * SR):int(b * SR)], path_or_hf_repo=model,
                                   language="hr", initial_prompt=PROMPTS[city],
                                   condition_on_previous_text=False,
                                   temperature=(0.0, 0.2, 0.4), compression_ratio_threshold=2.2,
                                   no_speech_threshold=0.6, verbose=None)
        text = " ".join(s["text"].strip() for s in r["segments"]).strip()
        if not is_junk(text):
            segs.append({"start": round(a, 2), "end": round(b, 2), "text": text})
    took = time.time() - t0
    dur = len(audio) / SR
    json.dump({"model": model, "audio": audio_path, "duration": dur, "seconds": took,
               "vad_seconds": t_vad, "speech_seconds": sum(b - a for a, b in chunks),
               "segments": segs}, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(segs)} segments from {len(chunks)} chunks, audio {dur/60:.1f} min, "
          f"took {took/60:.1f} min (VAD {t_vad:.0f}s), {dur/max(took, 1):.1f}x realtime")


if __name__ == "__main__":
    main(*sys.argv[1:])
