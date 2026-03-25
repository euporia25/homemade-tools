# stable diffusion便利ツール

Stable Diffusion / AUTOMATIC1111 WebUI まわりで使う自作 Python スクリプト集です。

## 含まれているスクリプト

### `image2image.py`

- AUTOMATIC1111 の `img2img` API を使って画像を生成します
- 入力画像に埋め込まれたプロンプトとネガティブプロンプトを読み取ります
- `loras` フォルダ内の LoRA を順番に適用して、まとめて出力できます
- LoRA と同名の `.json` があれば `activation text` と `preferred weight` を読み込みます

### `loraモデル自動ダウンロード.py`

- Civitai のモデル ID 一覧から LoRA を自動ダウンロードします
- `.safetensors` とあわせて補助用の `.json` を生成します
- API トークンはコードに書かず、環境変数 `CIVITAI_API_TOKEN` から読み込みます

## 必要環境

- Python 3.10 推奨
- `requests`
- `Pillow`
- AUTOMATIC1111 WebUI
- AUTOMATIC1111 API が有効になっていること

インストール例:

```bash
pip install requests pillow
```

## `image2image.py` の使い方

1. AUTOMATIC1111 WebUI を API 有効で起動します
2. `input/sample.png` に元画像を置きます
3. `loras` フォルダに使用したい `.safetensors` を入れます
4. スクリプト内の設定値を必要に応じて変更します
5. 実行すると `output` フォルダに生成画像が保存されます

実行例:

```bash
python image2image.py
```

主な設定項目:

- `API_URL`: WebUI の API URL
- `MODEL_NAME`: 使用するチェックポイント名
- `INPUT_IMAGE_PATH`: 入力画像
- `BASE_PROMPT_PART1` から `BASE_PROMPT_PART4`: 共通で足したいプロンプト
- `NEGATIVE_PROMPT`: 共通ネガティブプロンプト
- `STEPS`, `CFG_SCALE`, `DENOISING_STRENGTH`, `WIDTH`, `HEIGHT`: 生成設定

## `loraモデル自動ダウンロード.py` の使い方

1. 同じフォルダに `urls.txt` を用意します
2. `urls.txt` に Civitai のモデル ID を 1 行ずつ書きます
3. 必要に応じて環境変数を設定します
4. 実行すると既定では `downloads` フォルダへ保存されます

実行例:

```bash
python loraモデル自動ダウンロード.py
```

PowerShell で API トークンを設定する例:

```powershell
$env:CIVITAI_API_TOKEN="your_token"
python .\loraモデル自動ダウンロード.py
```

利用できる環境変数:

- `CIVITAI_API_TOKEN`: Civitai API トークン
- `LORA_SAVE_DIR`: 保存先フォルダ
- `LORA_URL_LIST_FILE`: モデル ID 一覧ファイル

## フォルダ構成例

```text
stable diffusion便利ツール/
├─ image2image.py
├─ loraモデル自動ダウンロード.py
├─ urls.txt
├─ input/
│  └─ sample.png
├─ loras/
│  ├─ example.safetensors
│  └─ example.json
└─ output/
```

## 注意

- `image2image.py` はローカルの AUTOMATIC1111 環境が前提です
- モデル名や LoRA の alias は環境によって異なるので、自分の環境に合わせて設定してください
- Civitai の利用規約や各モデルのライセンスを確認したうえで使用してください
