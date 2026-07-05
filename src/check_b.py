# -*- coding: utf-8 -*-
"""健康检查：验证智谱 GLM API(模型B) 的 key / 模型名 / endpoint 是否可用。
用法：  python -X utf8 src/check_b.py
"""
import sys
import pathlib
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config


def main() -> bool:
    print("=== 模型B(智谱GLM) 健康检查 ===")
    if not config.ZHIPU_API_KEY:
        print("[失败] 未加载到智谱 key")
        return False

    headers = {"Authorization": f"Bearer {config.ZHIPU_API_KEY}",
               "Content-Type": "application/json"}
    payload = {
        "model": config.B_MODEL_NAME,
        "messages": [{"role": "user", "content": "只回复两个字：你好"}],
        "max_tokens": 20,
    }
    print(f"[ ] POST {config.ZHIPU_API_URL}  (model={config.B_MODEL_NAME})")
    try:
        r = requests.post(config.ZHIPU_API_URL, headers=headers, json=payload, timeout=60)
    except Exception as e:
        print(f"[失败] 网络异常: {e}")
        return False

    print("    HTTP", r.status_code)
    if r.status_code != 200:
        print("    响应:", r.text[:500])
        low = r.text.lower()
        if "model" in low and config.B_MODEL_NAME.lower() in low:
            print(f"    [提示] 模型名 '{config.B_MODEL_NAME}' 可能不存在，"
                  f"可把 config.B_MODEL_NAME 改成 glm-4.5 / glm-4-plus / glm-4-flash 等再试")
        return False

    data = r.json()
    msg = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    print("[成功] B 回复:", repr(msg.strip()))
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
