# -*- coding: utf-8 -*-
"""模型B(视觉)判卷。【逐步判卷】：拆 AI 解答为一步步，对照标准答案，定位第一个出错的步骤。
输出：{correct, wrong_step, error_point, raw}。空回复/失败自动回退 config.B_FALLBACK。
"""
import json
import re
import base64
import pathlib
import sys
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config


def _img_data_url(path):
    ext = pathlib.Path(path).suffix.lstrip(".") or "png"
    b = base64.b64encode(pathlib.Path(path).read_bytes()).decode()
    return f"data:image/{ext};base64,{b}"


def _build_content(stem_pngs, answer_pngs, reply_pngs):
    parts = [{
        "type": "text",
        "text": (
            "你是物理竞赛判卷专家。下面依次给出三组图片：① 本题题干；② 标准答案；"
            "③ 某AI模型(豆包)给出的解答(截图)。\n"
            "请【逐步判卷】：把 AI 解答拆成一个个步骤"
            "(受力/受力矩分析 → 列方程 → 代入 → 化简 → 积分 → 求解…)，"
            "对照标准答案的对应步骤，**从前往后找出第一个出错的步骤**。\n"
            "核查要点：物理模型是否选错、所列方程是否成立、"
            "**正负号 / 系数 / 上下标 / 积分限 / 边界条件**、代数化简、最终结果。"
            "物理竞赛大题，错一个负号也算错；后续步骤若依赖前面的错误，定位第一个错步即可，不必全列。\n"
        ),
    }]
    for p in stem_pngs:
        parts += [{"type": "text", "text": "〔题干图〕"},
                  {"type": "image_url", "image_url": {"url": _img_data_url(p)}}]
    for p in answer_pngs:
        parts += [{"type": "text", "text": "〔标准答案图〕"},
                  {"type": "image_url", "image_url": {"url": _img_data_url(p)}}]
    for p in reply_pngs:
        parts += [{"type": "text", "text": "〔AI解答图〕"},
                  {"type": "image_url", "image_url": {"url": _img_data_url(p)}}]
    parts.append({"type": "text", "text":
        "现在给出判断。严格只返回一个 JSON，不要任何额外文字：\n"
        '{"correct": true或false, "wrong_step": "...", "error_point": "..."}\n'
        "字段说明：correct = AI解答是否正确；"
        "wrong_step = 若错误，定位【第一个出错】的步骤(例如 第(1)问列方程那步 / 第(2)问化简指数那步)，若正确填空串；"
        "error_point = 若错误，详细写：①这一步AI具体做了什么(把它写的式子/假设抄出来) "
        "②为什么错(正负号?系数?漏项?物理模型错?积分限?) ③对照标准答案，这一步正确的应该是什么。若正确填\"解答正确\"。"
    })
    return parts


def _parse(msg):
    m = re.search(r"\{.*\}", msg, re.S)
    raw = m.group(0) if m else msg
    try:
        d = json.loads(raw)
        return {"correct": bool(d.get("correct", False)),
                "wrong_step": str(d.get("wrong_step", "")).strip(),
                "error_point": str(d.get("error_point", "")).strip() or "（未给出错点）",
                "raw": msg}
    except Exception:
        return {"correct": False, "wrong_step": "", "error_point": msg.strip()[:300], "raw": msg}


def judge(stem_pngs, answer_pngs, reply_pngs, model=None, _depth=0):
    """逐步判卷。reply_pngs: A 解答截图路径列表。"""
    model = model or config.B_MODEL_NAME
    reply_pngs = [p for p in reply_pngs if p and pathlib.Path(p).exists()]
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_content(stem_pngs, answer_pngs, reply_pngs)}],
        "max_tokens": 2000,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {config.B_API_KEY}", "Content-Type": "application/json"}
    r = requests.post(config.B_API_URL, headers=headers, json=payload, timeout=180)
    if r.status_code != 200:
        if _depth == 0 and config.B_FALLBACK:
            print(f"  [B] 主模型 {model} 失败({r.status_code})，回退 {config.B_FALLBACK}")
            return judge(stem_pngs, answer_pngs, reply_pngs, model=config.B_FALLBACK, _depth=1)
        raise RuntimeError(f"B判卷请求失败 {r.status_code}: {r.text[:300]}")
    msg = r.json()["choices"][0]["message"]["content"]
    if not msg.strip() and _depth == 0 and config.B_FALLBACK:
        print(f"  [B] {model} 空回复，回退 {config.B_FALLBACK}")
        return judge(stem_pngs, answer_pngs, reply_pngs, model=config.B_FALLBACK, _depth=1)
    return _parse(msg)
