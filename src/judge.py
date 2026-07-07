# -*- coding: utf-8 -*-
"""模型B(视觉)判卷。【按小问逐个核对】：正确的小问跳过，错误的逐个详细分析。
输出：{correct, wrong_steps, error_point, raw}。空回复/失败回退 config.B_FALLBACK。
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
            "请【按小问逐个核对】(题目通常分为 (1)(2)(3)… 小问):\n"
            "1. 对每一小问, 对照标准答案判断 AI 该问解答是否正确"
            "(最终结果 + 关键中间式子都对 = 正确)。\n"
            "2. 正确的小问直接跳过, 不用说。\n"
            "3. 错误的小问, 按标准答案【详细核对】:\n"
            "   - 标准答案里的关键式子, AI 生成结果中有没有(漏没漏关键式子)?\n"
            "   - AI 的推导过程是否正确?\n"
            "   - 是否存在化简错误 / 计算错误 / 正负号 / 系数错误?\n"
            "   - 定位 AI 在这一问里具体哪一步开始出错。\n"
            "⚠️ 把【所有】错误的小问都列出来, 不只第一个, 后面的也要判。\n"
            "⚠️ wrong_steps 数组里只能放【判为错误】的小问; 判为正确的小问, 绝对不要放进数组。\n"
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
        "现在给出判断。严格只返回 JSON, 不要 markdown 代码块、不要额外文字:\n"
        '{"wrong_steps": [{"question": "(1)", "reason": "AI在这一问具体错在哪(一句话)"}]}\n'
        "规则: ① wrong_steps 只放判为【错误】的小问; 正确的小问完全不放进数组。"
        "② reason 必须说错在哪(错步+为什么), 不能写\"一致/正确/无错\"。"
        "③ 输出尽量短, 不要复述公式。④ 若 AI 全对, 返回 []。"
    })
    return parts


def _parse(msg):
    msg2 = msg.strip()
    if msg2.startswith("```"):                # 去 markdown 代码块
        msg2 = msg2.strip("`")
        if msg2.startswith("json"):
            msg2 = msg2[4:]
    m = re.search(r"\{.*\}", msg2, re.S)
    raw = m.group(0) if m else msg2
    if raw.count("[") > raw.count("]"):        # 被截断 → 补齐括号
        raw = raw.rstrip(", \n") + "]}"
    try:
        d = json.loads(raw)
        steps = d.get("wrong_steps", []) or []
        bad = ["完全一致", "一致", "无错", "无误", "相符", "相同", "对的", "没算错", "正确无误"]
        steps = [s for s in steps
                 if not any(k in (str(s.get("reason", "")) + str(s.get("why_wrong", ""))) for k in bad)]
        if not steps:
            return {"correct": True, "wrong_steps": [], "error_point": "解答正确", "raw": msg}
        parts = [f"{s.get('question', '?')}: {s.get('reason') or s.get('why_wrong', '')}"
                 for s in steps]
        return {"correct": False, "wrong_steps": steps,
                "error_point": "\n".join(parts), "raw": msg}
    except Exception:
        return {"correct": False, "wrong_steps": [], "error_point": msg.strip()[:600], "raw": msg}


def _merge_if_many(paths, tag):
    """多张图竖向拼成 1 张(规避视觉模型图片数量上限)。"""
    paths = [p for p in paths if p and pathlib.Path(p).exists()]
    if len(paths) <= 1:
        return paths
    try:
        from PIL import Image
        out = pathlib.Path(pathlib.Path(paths[0]).parent / f"_merged_{tag}.png")
        imgs = [Image.open(p).convert("RGB") for p in paths]
        w = max(im.width for im in imgs)
        h = sum(im.height for im in imgs)
        canvas = Image.new("RGB", (w, h), "white")
        y = 0
        for im in imgs:
            canvas.paste(im, (0, y))
            y += im.height
        canvas.save(out)
        return [str(out)]
    except ImportError:
        return paths


def judge(stem_pngs, answer_pngs, reply_pngs, model=None, _depth=0):
    """按小问逐个核对判卷。reply_pngs: A 解答截图路径列表。"""
    model = model or config.B_MODEL_NAME
    stem_pngs = [p for p in stem_pngs if p and pathlib.Path(p).exists()]
    answer_pngs = [p for p in answer_pngs if p and pathlib.Path(p).exists()]
    reply_pngs = [p for p in reply_pngs if p and pathlib.Path(p).exists()]
    # 图片总数 > 4 → 题干、答案各自竖拼成 1 张(智谱视觉模型限图数量)
    if len(stem_pngs) + len(answer_pngs) + len(reply_pngs) > 4:
        stem_pngs = _merge_if_many(stem_pngs, "stem")
        answer_pngs = _merge_if_many(answer_pngs, "answer")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_content(stem_pngs, answer_pngs, reply_pngs)}],
        "max_tokens": 2048,
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
