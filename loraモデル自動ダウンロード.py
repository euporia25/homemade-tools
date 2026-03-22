import requests
import json
import os

# === 設定 ===
SAVE_DIR = r"C:\AI\stable-diffusion-webui\models\Lora\ウマ娘"
URL_LIST_FILE = "urls.txt"  # モデルIDを記載したテキストファイル
API_TOKEN = "ceaf2f924df336290ae5cef17eedfa1a"  # 必要ならCivitaiのAPIキーを設定

os.makedirs(SAVE_DIR, exist_ok=True)

headers = {}
if API_TOKEN:
    headers["Authorization"] = f"Bearer {API_TOKEN}"

# === モデル情報取得 ===
def get_model_info(model_id):
    url = f"https://civitai.com/api/v1/models/{model_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"モデル情報取得失敗: {model_id} (HTTP {response.status_code})")
        return None

# === safetensorsファイルをダウンロード ===
def download_file(url, filepath):
    with requests.get(url, headers=headers, stream=True) as r:
        if r.status_code == 401:
            print("認証エラー: APIトークンが必要です。CivitaiのAPIキーを設定してください。")
            return False
        r.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return True


# === JSON作成 ===
def create_json(filepath, trigger_words):
    json_data = {
        "description": "",
        "sd version": "SDXL",
        "activation text": ", ".join(trigger_words),
        "preferred weight": 0,
        "negative text": "",
        "notes": ""
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)

# === メイン処理 ===
with open(URL_LIST_FILE, "r", encoding="utf-8") as f:
    model_ids = [line.strip() for line in f if line.strip()]

for model_id in model_ids:
    model_info = get_model_info(model_id)
    if not model_info:
        continue

    # モデル名
    model_name = model_info["name"].replace(" ", "_")
    print(f"\n=== {model_name} を処理中 ===")

    # 最新バージョンの情報を取得
    version = model_info["modelVersions"][0]
    trigger_words = version.get("trainedWords", [])
    files = version.get("files", [])

    # safetensorsファイルを探す
    safetensors_file = None
    for file in files:
        if file["name"].endswith(".safetensors"):
            safetensors_file = file
            break

    if not safetensors_file:
        print("safetensorsファイルが見つかりません")
        continue

    download_url = safetensors_file["downloadUrl"]

    # 保存先ファイルパス
    safetensors_path = os.path.join(SAVE_DIR, f"{model_name}.safetensors")
    json_path = os.path.join(SAVE_DIR, f"{model_name}.json")

    # ダウンロード
    print(f"ダウンロード中: {safetensors_path}")
    download_file(download_url, safetensors_path)

    # JSON作成
    create_json(json_path, trigger_words)
    print(f"完了: {model_name} (Trigger Words: {', '.join(trigger_words)})")
