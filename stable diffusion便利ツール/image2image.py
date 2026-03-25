import base64
import json
import os
import re
from pathlib import Path

import requests
from PIL import Image


# =========================================
# Settings
# =========================================
BASE_DIR = Path(__file__).resolve().parent  # このスクリプトがあるフォルダ
API_URL = "http://127.0.0.1:7860"  # Automatic1111 API URL
LORA_DIR = BASE_DIR / "loras"  # LoRAフォルダ
INPUT_IMAGE_PATH = BASE_DIR / "input" / "sample.png"  # 元画像のパス
OUTPUT_DIR = BASE_DIR / "output"  # 出力先フォルダ
MODEL_NAME = "your-model-name.safetensors [model-hash]"  # 使用するモデル名

BASE_PROMPT_PART1 = ""  # 描きたい主題を書く
BASE_PROMPT_PART2 = ""  # 服装・背景・構図などを書く
BASE_PROMPT_PART3 = ""  # 表情・ポーズ・雰囲気などを書く
BASE_PROMPT_PART4 = (
    ""
)  # 品質や画風の共通プロンプト
BASE_PROMPT = ", ".join(
    part
    for part in [BASE_PROMPT_PART1, BASE_PROMPT_PART2, BASE_PROMPT_PART3, BASE_PROMPT_PART4]
    if part
)
NEGATIVE_PROMPT = (
    ""
)  # 描きたくない要素

STEPS = 20  # 生成ステップ数
CFG_SCALE = 7.0  # プロンプトの効き具合
IMAGE_CFG_SCALE = 1.5  # 元画像の反映度
DENOISING_STRENGTH = 0.75  # 元画像からどれくらい変化させるか
SAMPLER_NAME = "DPM++ 2M"  # 使用するサンプラー
SCHEDULER = "Automatic"  # 使用するスケジューラ
RESIZE_MODE = 0  # 0 = Just resize
WIDTH = 1024  # 出力画像の幅
HEIGHT = 1536  # 出力画像の高さ
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}  # 対応入力形式

OUTPUT_DIR.mkdir(exist_ok=True)


def switch_model():
    response = requests.post(
        f"{API_URL}/sdapi/v1/options",
        json={"sd_model_checkpoint": MODEL_NAME},
        timeout=60,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            "Model switch failed. Check MODEL_NAME against /sdapi/v1/sd-models. "
            f"Current MODEL_NAME: {MODEL_NAME}"
        ) from exc


def fetch_lora_alias_map():
    response = requests.get(f"{API_URL}/sdapi/v1/loras", timeout=60)
    response.raise_for_status()

    alias_map = {}
    for item in response.json():
        lora_path = item.get("path")
        alias = item.get("alias") or item.get("name")
        if lora_path and alias:
            alias_map[os.path.normcase(lora_path)] = alias

    return alias_map


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def next_output_path(out_dir, base_name):
    index = 0
    while True:
        out_path = out_dir / f"{base_name}_{index}.png"
        if not out_path.exists():
            return out_path
        index += 1


def load_lora_prompt_and_weight(lora_dir, lora_name):
    lora_json = lora_dir / f"{lora_name}.json"
    lora_prompt = ""
    lora_weight = 1.0

    if lora_json.exists():
        with open(lora_json, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
            lora_prompt = data.get("activation text", "").strip()
            lora_weight = data.get("preferred weight", 1.0)

    if not lora_weight or lora_weight <= 0:
        lora_weight = 1.0

    return lora_prompt, lora_weight


def split_prompt_parts(prompt_text):
    if not prompt_text:
        return []
    return [part.strip() for part in prompt_text.split(",") if part.strip()]


def dedupe_prompt_parts(*prompt_texts):
    merged_parts = []
    seen = set()

    for prompt_text in prompt_texts:
        for part in split_prompt_parts(prompt_text):
            if part not in seen:
                seen.add(part)
                merged_parts.append(part)

    return ", ".join(merged_parts)


def parse_a1111_parameters(parameters_text):
    if not parameters_text:
        return "", ""

    negative_prompt = ""
    prompt = parameters_text.strip()

    negative_match = re.search(
        r"\nNegative prompt:\s*(.*?)\n(?:Steps:|Sampler:|CFG scale:|Seed:)",
        parameters_text,
        flags=re.DOTALL,
    )
    if negative_match:
        negative_prompt = negative_match.group(1).strip()
        prompt = parameters_text[:negative_match.start()].strip()
    else:
        steps_match = re.search(r"\nSteps:", parameters_text)
        if steps_match:
            prompt = parameters_text[:steps_match.start()].strip()

    return prompt, negative_prompt


def decode_exif_user_comment(exif_bytes):
    if not exif_bytes:
        return ""

    if exif_bytes.startswith(b"UNICODE\x00\x00"):
        payload = exif_bytes[9:]
        try:
            return payload.decode("utf-16-le", errors="ignore")
        except UnicodeDecodeError:
            return payload.decode("utf-16", errors="ignore")

    if exif_bytes.startswith(b"UNICODE\x00"):
        payload = exif_bytes[8:]
        try:
            return payload.decode("utf-16-le", errors="ignore")
        except UnicodeDecodeError:
            return payload.decode("utf-16", errors="ignore")

    if exif_bytes.startswith(b"ASCII\x00\x00\x00"):
        return exif_bytes[8:].decode("ascii", errors="ignore")

    return exif_bytes.decode("utf-8", errors="ignore")


def extract_user_comment_from_raw_exif(raw_exif_bytes):
    if not raw_exif_bytes:
        return ""

    for marker in (b"UNICODE\x00\x00", b"UNICODE\x00", b"ASCII\x00\x00\x00"):
        index = raw_exif_bytes.find(marker)
        if index >= 0:
            return decode_exif_user_comment(raw_exif_bytes[index:])

    return ""


def load_embedded_prompts(image_path):
    with Image.open(image_path) as image:
        metadata_candidates = [
            image.info.get("parameters"),
            image.info.get("comment"),
            image.info.get("Description"),
            image.info.get("UserComment"),
        ]
        exif = image.getexif()
        if exif:
            metadata_candidates.append(decode_exif_user_comment(exif.get(0x9286)))
        metadata_candidates.append(
            extract_user_comment_from_raw_exif(image.info.get("exif"))
        )

    for candidate in metadata_candidates:
        if not candidate:
            continue
        if isinstance(candidate, bytes):
            candidate = candidate.decode("utf-8", errors="ignore")
        prompt, negative_prompt = parse_a1111_parameters(candidate)
        if prompt or negative_prompt:
            return prompt, negative_prompt

    return "", ""


def build_full_prompt(image_prompt, lora_tag_name, lora_prompt, lora_weight):
    prompt_prefix = f"<lora:{lora_tag_name}:{lora_weight}>"
    return dedupe_prompt_parts(image_prompt, prompt_prefix, lora_prompt, BASE_PROMPT)


def generate_img2img(full_prompt, negative_prompt, input_image_path, output_base_name):
    init_image = encode_image_to_base64(input_image_path)
    payload = {
        "init_images": [init_image],
        "prompt": full_prompt,
        "negative_prompt": negative_prompt,
        "steps": STEPS,
        "sampler_name": SAMPLER_NAME,
        "scheduler": SCHEDULER,
        "cfg_scale": CFG_SCALE,
        "image_cfg_scale": IMAGE_CFG_SCALE,
        "denoising_strength": DENOISING_STRENGTH,
        "resize_mode": RESIZE_MODE,
        "width": WIDTH,
        "height": HEIGHT,
        "seed": -1,
        "batch_size": 1,
    }

    response = requests.post(
        f"{API_URL}/sdapi/v1/img2img",
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()

    for image_data in data.get("images", []):
        output_path = next_output_path(OUTPUT_DIR, output_base_name)
        decoded_image = base64.b64decode(image_data.split(",", 1)[-1])
        with open(output_path, "wb") as output_file:
            output_file.write(decoded_image)
        print(f"Saved: {output_path}")


def validate_input_image(image_path):
    if not image_path.is_file():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported input image format. Use PNG/JPG/JPEG/WEBP/BMP.")


def main():
    switch_model()

    if not LORA_DIR.is_dir():
        raise FileNotFoundError(f"LoRA folder not found: {LORA_DIR}")

    validate_input_image(INPUT_IMAGE_PATH)
    lora_alias_map = fetch_lora_alias_map()
    image_prompt, image_negative_prompt = load_embedded_prompts(INPUT_IMAGE_PATH)

    lora_files = sorted(
        file_name for file_name in os.listdir(LORA_DIR) if file_name.endswith(".safetensors")
    )
    if not lora_files:
        raise FileNotFoundError(f"No LoRA files found in {LORA_DIR}")

    input_stem = INPUT_IMAGE_PATH.stem

    for lora_file in lora_files:
        lora_name = Path(lora_file).stem
        lora_path = LORA_DIR / lora_file
        lora_tag_name = lora_alias_map.get(os.path.normcase(str(lora_path)), lora_name)
        safe_lora_name = re.sub(r'[\\/*?:"<>|]', "_", lora_name)
        lora_prompt, lora_weight = load_lora_prompt_and_weight(LORA_DIR, lora_name)
        full_prompt = build_full_prompt(
            image_prompt, lora_tag_name, lora_prompt, lora_weight
        )
        full_negative_prompt = dedupe_prompt_parts(
            image_negative_prompt, NEGATIVE_PROMPT
        )
        output_base_name = f"{input_stem}_{safe_lora_name}"

        print(
            f"Generating img2img | input={INPUT_IMAGE_PATH.name} "
            f"| lora={lora_name} | tag={lora_tag_name} | weight={lora_weight}"
        )
        generate_img2img(
            full_prompt,
            full_negative_prompt,
            INPUT_IMAGE_PATH,
            output_base_name,
        )

    print("All img2img generations completed.")


if __name__ == "__main__":
    main()
