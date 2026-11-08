"""Convert a Hugging Face Whisper checkpoint (transformers format) to mlx-whisper's format.

Usage: python convert_hf.py <hf_repo_or_dir> <out_dir>
Writes <out_dir>/config.json (ModelDimensions) and weights.safetensors (float16).
"""
import json
import re
import sys
from pathlib import Path

import mlx.core as mx
from huggingface_hub import snapshot_download

RENAMES = [
    (r"^model\.", ""),
    (r"^encoder\.layer_norm\.", "encoder.ln_post."),
    (r"^decoder\.layer_norm\.", "decoder.ln."),
    (r"^decoder\.embed_tokens\.", "decoder.token_embedding."),
    (r"^decoder\.embed_positions\.weight$", "decoder.positional_embedding"),
    (r"\.layers\.", ".blocks."),
    (r"\.self_attn_layer_norm\.", ".attn_ln."),
    (r"\.encoder_attn_layer_norm\.", ".cross_attn_ln."),
    (r"\.final_layer_norm\.", ".mlp_ln."),
    (r"\.self_attn\.", ".attn."),
    (r"\.encoder_attn\.", ".cross_attn."),
    (r"\.q_proj\.", ".query."),
    (r"\.k_proj\.", ".key."),
    (r"\.v_proj\.", ".value."),
    (r"\.out_proj\.", ".out."),
    (r"\.fc1\.", ".mlp1."),
    (r"\.fc2\.", ".mlp2."),
]


def rename(key):
    for pat, rep in RENAMES:
        key = re.sub(pat, rep, key)
    return key


def main(src, out):
    path = Path(src) if Path(src).exists() else Path(snapshot_download(
        repo_id=src, allow_patterns=["*.json", "model.safetensors", "*.txt"]))
    cfg = json.loads((path / "config.json").read_text())
    dims = {
        "n_mels": cfg["num_mel_bins"],
        "n_audio_ctx": cfg["max_source_positions"],
        "n_audio_state": cfg["d_model"],
        "n_audio_head": cfg["encoder_attention_heads"],
        "n_audio_layer": cfg["encoder_layers"],
        "n_vocab": cfg["vocab_size"],
        "n_text_ctx": cfg["max_target_positions"],
        "n_text_state": cfg["d_model"],
        "n_text_head": cfg["decoder_attention_heads"],
        "n_text_layer": cfg["decoder_layers"],
    }
    weights = {}
    for k, v in mx.load(str(path / "model.safetensors")).items():
        # encoder positions are recomputed as sinusoids; proj_out is tied to token_embedding
        if k in ("model.encoder.embed_positions.weight", "proj_out.weight"):
            continue
        k = rename(k)
        if "conv" in k and k.endswith(".weight"):
            v = v.swapaxes(1, 2)  # torch (out, in, k) -> mlx (out, k, in)
        weights[k] = v.astype(mx.float16)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    mx.save_safetensors(str(out / "weights.safetensors"), weights)
    (out / "config.json").write_text(json.dumps({**dims, "model_type": "whisper"}, indent=2))
    print(f"{len(weights)} tensors, dims {dims}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
