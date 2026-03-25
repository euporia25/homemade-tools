import os

# 対象のフォルダ
folder_path = r"C:\AI\stable-diffusion-webui\models\Lora"  # ←ここを変更

# サブフォルダも含めて探索
for root, dirs, files in os.walk(folder_path):
    for filename in files:
        # 先頭の空白を削除
        new_filename = filename.lstrip()

        if new_filename != filename:  # 変更がある場合のみ
            old_path = os.path.join(root, filename)
            new_path = os.path.join(root, new_filename)

            try:
                os.rename(old_path, new_path)
                print(f"[OK] {filename} → {new_filename}")
            except Exception as e:
                print(f"[ERROR] {filename}: {e}")

print("すべての処理が完了しました。")
