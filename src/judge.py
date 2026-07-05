# -*- coding: utf-8 -*-
"""模型B(智谱 glm-4.5v 视觉)判卷。【全图判卷】：题干PNG + 标准答案PNG + AI解答PNG(截图)。
输出：{correct, error_point, raw}。主模型异常时回退 config.B_FALLBACK。
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
            "请判断该AI解答是否正确——**逐个式子**对照标准答案与AI解答，仔细核查："
            "物理模型、所列方程、**正负号 / 系数 / 上下标 / 积分限 / 边界条件**、推导与最终结果。"
            "物理竞赛大题，错一个负号也算错；不确定时倾向判错。\n"
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
        "现在给出判断。严格只返回一个 JSON，不要额外文字：\n"
        '{"correct": true或false, "error_point": "若错误，必须写清三点：'
        '①错在第几问/哪个式子(标明式子编号) ②AI写成了什么(或忽略了什么关键项) '
        '③对照标准答案，正确的应该是什么；若正确填\\"解答正确\\""}'})
    return parts


def _parse(msg):
    m = re.search(r"\{.*\}", msg, re.S)
    raw = m.group(0) if m else msg
    try:
        d = json.loads(raw)
        return {"correct": bool(d.get("correct", False)),
                "error_point": str(d.get("error_point", "")).strip() or "（未给出错点）",
                "raw": msg}
    except Exception:
        return {"correct": False, "error_point": msg.strip()[:300], "raw": msg}


def judge(stem_pngs, answer_pngs, reply_pngs, model=None, _depth=0):
    """全图判卷。reply_pngs: A 解答截图路径列表。"""
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
