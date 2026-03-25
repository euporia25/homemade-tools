import json
import os
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
SAVE_DIR = Path(os.environ.get("LORA_SAVE_DIR", BASE_DIR / "downloads"))
URL_LIST_FILE = Path(os.environ.get("LORA_URL_LIST_FILE", BASE_DIR / "urls.txt"))
API_TOKEN = os.environ.get("CIVITAI_API_TOKEN", "")


def build_headers():
    headers = {}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return headers


HEADERS = build_headers()


def get_model_info(model_id):
    url = f"https://civitai.com/api/v1/models/{model_id}"
    response = requests.get(url, headers=HEADERS, timeout=30)
    if response.status_code == 200:
        return response.json()

    print(f"モデル情報の取得に失敗: {model_id} (HTTP {response.status_code})")
    return None


def download_file(url, filepath):
    with requests.get(url, headers=HEADERS, stream=True, timeout=30) as response:
        if response.status_code == 401:
            print(
                "認証エラー: 必要なモデルのダウンロードには "
                "CIVITAI_API_TOKEN の設定が必要です。"
            )
            return False

        response.raise_for_status()
        with open(filepath, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=8192):
                file_obj.write(chunk)

    return True


def create_json(filepath, trigger_words):
    json_data = {
        "description": "",
        "sd version": "SDXL",
        "activation text": ", ".join(trigger_words),
        "preferred weight": 0,
        "negative text": "",
        "notes": "",
    }
    with open(filepath, "w", encoding="utf-8") as file_obj:
        json.dump(json_data, file_obj, ensure_ascii=False, indent=4)


def load_model_ids(filepath):
    with open(filepath, "r", encoding="utf-8") as file_obj:
        return [line.strip() for line in file_obj if line.strip()]


def main():
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    if not URL_LIST_FILE.exists():
        print(f"URL一覧ファイルが見つかりません: {URL_LIST_FILE}")
        return

    model_ids = load_model_ids(URL_LIST_FILE)

    for model_id in model_ids:
        model_info = get_model_info(model_id)
        if not model_info:
            continue

        model_name = model_info["name"].replace(" ", "_")
        print(f"\n=== {model_name} を処理中 ===")

        version = model_info["modelVersions"][0]
        trigger_words = version.get("trainedWords", [])
        files = version.get("files", [])

        safetensors_file = None
        for file_info in files:
            if file_info["name"].endswith(".safetensors"):
                safetensors_file = file_info
                break

        if not safetensors_file:
            print("safetensors ファイルが見つかりません")
            continue

        download_url = safetensors_file["downloadUrl"]
        safetensors_path = SAVE_DIR / f"{model_name}.safetensors"
        json_path = SAVE_DIR / f"{model_name}.json"

        print(f"ダウンロード中: {safetensors_path}")
        if download_file(download_url, safetensors_path):
            create_json(json_path, trigger_words)
            print(f"完了: {model_name} (Trigger Words: {', '.join(trigger_words)})")


if __name__ == "__main__":
    main()
