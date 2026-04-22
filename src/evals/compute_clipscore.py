import argparse
import logging
import os
from typing import List

import pandas as pd
import torch
from PIL import Image
from tqdm import tqdm
from transformers import CLIPModel, CLIPProcessor


MODEL_NAME = "openai/clip-vit-large-patch14"


def load_clip(model_name: str, device: str):
    model = CLIPModel.from_pretrained(model_name).to(device).eval()
    proc = CLIPProcessor.from_pretrained(model_name)
    return model, proc


@torch.inference_mode()
def clipscore_batch(
    model: CLIPModel,
    proc: CLIPProcessor,
    image_paths: List[str],
    captions: List[str],
    device: str,
    use_fp16: bool = True,
) -> List[float]:
    """
    Per-sample CLIPScore: score = max(100 * cosine(image_emb, text_emb), 0)
    Returns one float per (image, caption) pair.
    """
    assert len(image_paths) == len(captions)

    scores = [-1.0] * len(image_paths)

    # Collect valid items (non-empty caption + image can be opened)
    valid_images = []
    valid_caps = []
    valid_local_indices = []

    for i, (p, c) in enumerate(zip(image_paths, captions)):
        if not isinstance(c, str) or c.strip() == "":
            scores[i] = -1.0
            continue
        try:
            img = Image.open(p).convert("RGB")
        except Exception:
            scores[i] = -1.0
            continue

        valid_images.append(img)
        valid_caps.append(c)
        valid_local_indices.append(i)

    if not valid_images:
        return scores

    max_len = int(model.config.text_config.max_position_embeddings)  # 77 for ViT-L/14

    inputs = proc(
        text=valid_caps,
        images=valid_images,
        return_tensors="pt",
        padding=True,
        truncation=True,        
        max_length=max_len,    
    ).to(device)

    autocast_enabled = (device.startswith("cuda") and use_fp16)
    with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=autocast_enabled):
        out = model(**inputs)
        img = out.image_embeds
        txt = out.text_embeds

        img = img / img.norm(dim=-1, keepdim=True)
        txt = txt / txt.norm(dim=-1, keepdim=True)

        cos = (img * txt).sum(dim=-1)                 # [B]
        batch_scores = torch.clamp(cos * 100.0, min=0) # [B]

    batch_scores = batch_scores.detach().cpu().tolist()
    for local_i, s in zip(valid_local_indices, batch_scores):
        scores[local_i] = float(s)

    return scores


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "aligned_extracted_object_descriptions_csv",
        type=str,
        help="Path to CSV file with filename and object_description columns.",
    )
    parser.add_argument(
        "--image_root",
        type=str,
        default="data/images",
        help="Optional root directory prepended to filename paths from the CSV.",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=32,
        help="Batch size for CLIP scoring.",
    )
    parser.add_argument(
        "--output_csv",
        type=str,
        default="",
        help="Optional output path. If omitted, overwrites the input CSV.",
    )
    parser.add_argument(
        "--no_fp16",
        action="store_true",
        help="Disable FP16 autocast (slower, but can be useful for debugging).",
    )

    args = parser.parse_args()
    df = pd.read_csv(args.aligned_extracted_object_descriptions_csv)

    # Column checks
    if "filename" not in df.columns or "object_description" not in df.columns:
        raise ValueError("CSV must contain 'filename' and 'object_description' columns.")

    # If clip_score exists and has some computed values, compute only missing ones.
    if "clip_score" not in df.columns:
        df["clip_score"] = float("nan")

    to_compute_mask = df["clip_score"].isna()
    num_to_compute = int(to_compute_mask.sum())
    if num_to_compute == 0:
        logging.info("CLIP scores already computed in the CSV file.")
        
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda":
            # Often speeds up matmul on Ampere (3090)
            torch.backends.cuda.matmul.allow_tf32 = True

        logging.info(f"Loading CLIP model {MODEL_NAME} on {device}...")
        model, proc = load_clip(MODEL_NAME, device)

        # Resolve paths + captions for rows that need computation
        indices = df.index[to_compute_mask].tolist()

        def resolve_path(fn: str) -> str:
            fn = str(fn)
            return os.path.join(args.image_root, fn) if args.image_root else fn

        bs = max(1, args.batch_size)
        use_fp16 = not args.no_fp16

        logging.info(f"Computing {num_to_compute} CLIP scores with batch_size={bs} (fp16={use_fp16})")

        for start in tqdm(range(0, len(indices), bs), desc="CLIPScore", unit="batch"):
            batch_idx = indices[start : start + bs]

            batch_paths = [resolve_path(df.at[i, "filename"]) for i in batch_idx]
            batch_caps = [df.at[i, "object_description"] for i in batch_idx]

            batch_scores = clipscore_batch(
                model=model,
                proc=proc,
                image_paths=batch_paths,
                captions=batch_caps,
                device=device,
                use_fp16=use_fp16,
            )

            for i, s in zip(batch_idx, batch_scores):
                df.at[i, "clip_score"] = s

    # ------------------------------------------------------------------
    # Contrastive CLIPScore (CLIPCon) per (pair_id, round_ix)
    # CLIPCon(row) = clip_score(row) - mean(clip_score(other rows in group))
    # ------------------------------------------------------------------
    required_cols = {"pair_id", "round_ix", "clip_score"}
    missing = required_cols - set(df.columns)
    if missing:
        logging.warning(f"Skipping contrastive_clip_score; missing columns: {sorted(missing)}")
    else:
        # Treat invalid scores (-1) as NaN so they don't affect group means
        s = df["clip_score"].astype(float)
        s_valid = s.mask(s < 0)  # -1 -> NaN

        g = df.groupby(["pair_id", "round_ix"], sort=False)

        # sum and count of valid scores within each group
        group_sum = g["clip_score"].transform(lambda x: x.mask(x < 0).sum(skipna=True))
        group_cnt = g["clip_score"].transform(lambda x: x.mask(x < 0).count())

        # mean of distractors for each row (exclude itself)
        # mean_other = (sum - self) / (count - 1)
        mean_other = (group_sum - s_valid) / (group_cnt - 1)

        # contrastive score
        clip_con = s_valid - mean_other

        # If group has <2 valid items, mean_other is inf/NaN; keep as NaN
        # For invalid original scores, keep -1 (or change to NaN if you prefer)
        df["contrastive_clip_score"] = clip_con
        df.loc[s < 0, "contrastive_clip_score"] = -1.0

        logging.info("Computed contrastive_clip_score grouped by (pair_id, round_ix).")


    out_path = args.output_csv.strip() or args.aligned_extracted_object_descriptions_csv
    df.to_csv(out_path, index=False)
    logging.info(f"Done. Wrote: {out_path}")


if __name__ == "__main__":
    main()
