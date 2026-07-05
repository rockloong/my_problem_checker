# -*- coding: utf-8 -*-
"""docx 拆分：把"原题目合集"切成一道道带答案的题(无答案的题干按规则丢弃)。

本模块【只做拆分】：识别每道题的题干/答案在原文中的段落范围。
题干和答案的具体内容(文字、公式、配图)一律通过「切片段 docx → PNG」表达，
统一喂给多模态模型(A豆包 / B glm-4.5v)，本模块不提取文本、不转 LaTeX。

每题 Problem：
  cn_idx / int_idx        中文题号 "三" / 阿拉伯 3
  title                   题干标题段文本(如 "第三题 （刚体...，2024）")
  src_path                原 docx 路径
  stem_range/answer_range body 里 p/tbl 块序列的 [start,end) 索引(切片段 docx 用)
"""
import re
import sys
import pathlib
from docx import Document
from lxml import etree

CN = "零一二三四五六七八九十"
_HEAD_ANS = re.compile(r'^\s*第([一二三四五六七八九十]+)题\s*答案')
_HEAD_STEM = re.compile(r'^\s*第([一二三四五六七八九十]+)题(?!\s*答案)')


def cn2int(s: str) -> int:
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN.index(s[1])
    if "十" in s:
        a, b = s.split("十")
        return CN.index(a) * 10 + (CN.index(b) if b else 0)
    return CN.index(s)


def _para_text(p) -> str:
    """段落可读文本(拼接 w:t / m:t 文字，仅供识别标题与判断长度，不转 LaTeX)。"""
    parts = []
    for node in p.iter():
        ln = etree.QName(node).localname
        if ln == "t":            # 同时覆盖 w:t 和 m:t
            parts.append(node.text or "")
        elif ln == "tab":
            parts.append("\t")
        elif ln == "br":
            parts.append("\n")
    return "".join(parts).strip()


def _classify(text):
    m = _HEAD_ANS.match(text)
    if m:
        return "answer", m.group(1)
    m = _HEAD_STEM.match(text)
    if m:
        return "stem", m.group(1)
    return None, None


def _body_blocks(doc):
    body = doc.element.body
    return [c for c in body if etree.QName(c).localname in ("p", "tbl")]


def split_docx(docx_path):
    """返回 Problem 列表(只含有题干且有答案、且内容非空的题)。"""
    docx_path = pathlib.Path(docx_path)
    doc = Document(str(docx_path))
    blocks = _body_blocks(doc)

    # 第一遍：找所有题干/答案标题块
    marks = []  # (kind, cn, block_idx, title_text)
    for i, b in enumerate(blocks):
        if etree.QName(b).localname != "p":
            continue
        text = _para_text(b)
        kind, cn = _classify(text)
        if kind:
            marks.append((kind, cn, i, text))

    # 每个 mark 的内容范围 [idx, 下一个 mark 的 idx)
    mark_end = [marks[k + 1][2] if k + 1 < len(marks) else len(blocks)
                for k in range(len(marks))]

    # 顺序就近配对：每个题干标题，找它之后(到下一个题干前)最近的同题号答案
    used_answer = set()
    problems = []
    for k, (kind, cn, idx, title) in enumerate(marks):
        if kind != "stem":
            continue
        ans_k = None
        for j in range(k + 1, len(marks)):
            mk = marks[j]
            if mk[0] == "stem":              # 答案不会跨到下一道题之后
                break
            if mk[0] == "answer" and mk[1] == cn and j not in used_answer:
                ans_k = j
                break
        if ans_k is None:
            print(f"  [跳过] 第{cn}题: 没找到对应答案，丢弃")
            continue
        used_answer.add(ans_k)

        sr = (idx, mark_end[k])
        ar = (marks[ans_k][2], mark_end[ans_k])
        stem_blocks = blocks[sr[0]:sr[1]]
        ans_blocks = blocks[ar[0]:ar[1]]
        stem_len = sum(len(_para_text(b)) for b in stem_blocks)
        ans_len = sum(len(_para_text(b)) for b in ans_blocks)
        if stem_len < 15 or ans_len < 15:
            print(f"  [跳过] 第{cn}题: 题干({stem_len})或答案({ans_len})内容过短/空，丢弃")
            continue

        problems.append({
            "cn_idx": cn,
            "int_idx": cn2int(cn),
            "title": title,
            "src_path": str(docx_path),
            "stem_range": sr,
            "answer_range": ar,
        })
    return problems


def make_docx_snippet(problem, which, out_path):
    """which='stem'/'answer'。基于原 docx 包只保留对应块，格式/公式/图片全保留。"""
    doc = Document(problem["src_path"])
    body = doc.element.body
    blocks = [c for c in body if etree.QName(c).localname in ("p", "tbl")]
    rng = problem["stem_range"] if which == "stem" else problem["answer_range"]
    keep = set(range(rng[0], rng[1]))
    for i, child in enumerate(blocks):
        if i not in keep:
            body.remove(child)
    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))


def _main():
    if len(sys.argv) < 2:
        print("用法: python -X utf8 src/splitter.py <题目合集.docx>")
        sys.exit(1)
    pros = split_docx(sys.argv[1])
    print(f"\n共拆出 {len(pros)} 道有答案的题：")
    for p in pros:
        print(f"  第{p['cn_idx']}题 ({p['int_idx']})  {p['title']}")


if __name__ == "__main__":
    _main()
