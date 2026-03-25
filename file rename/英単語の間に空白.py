import os
import wordninja

# 処理するフォルダを指定
folder_path = r"C:\AI\stable-diffusion-webui\models\Lora\ｚｚｚ遊具・小道具"  # ←ここを変更

# サブフォルダも含めて探索
for root, dirs, files in os.walk(folder_path):
    for filename in files:
        name, ext = os.path.splitext(filename)

        # 英単語を推測してスペースを挿入
        corrected_name = " ".join(wordninja.split(name)) + ext

        # 変更がある場合のみリネーム
        if corrected_name != filename:
            old_path = os.path.join(root, filename)
            new_path = os.path.join(root, corrected_name)

            try:
                os.rename(old_path, new_path)
                print(f"[OK] {filename} → {corrected_name}")
            except Exception as e:
                print(f"[ERROR] {filename}: {e}")

print("すべての処理が完了しました。")
