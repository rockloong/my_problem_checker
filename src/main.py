# -*- coding: utf-8 -*-
"""端到端主流程(真A全自动)：
  批量渲染PNG → 浏览器循环[A解题→B判卷] → A对则不打包/A错则打包 → zip

用法: python -X utf8 src/main.py <题目docx> <主题> [题数]
      默认: 原题目/量子-电磁学.docx  电磁  2
"""
import sys
import pathlib
import shutil

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config
import splitter as sp
import docx_to_png as dp
import judge
import packager as pk
import doubao_auto as da


def run(input_docx, theme, start=None, end=None):
    problems = sp.split_docx(str(input_docx))
    if start:
        problems = [p for p in problems if p["int_idx"] >= start]
    if end:
        problems = [p for p in problems if p["int_idx"] <= end]
    print(f"\n==== 共 {len(problems)} 题 | 主题={theme} | 题号 {start or 1}–{end or '末'} ====")

    work = pathlib.Path(config.TMP_DIR) / f"run_{theme}"
    if work.exists():
        shutil.rmtree(work)

    # —— 第1阶段：批量渲染每题的题干/答案 PNG（Word 用完即关）——
    items = []
    for p in problems:
        cn = p["cn_idx"]
        sd, ad = work / f"第{cn}题_题干.docx", work / f"第{cn}题_答案.docx"
        sp.make_docx_snippet(p, "stem", sd)
        sp.make_docx_snippet(p, "answer", ad)
        spng = dp.docx_to_pngs(sd, work / f"第{cn}题_题干PNG", prefix="s")
        apng = dp.docx_to_pngs(ad, work / f"第{cn}题_答案PNG", prefix="a")
        items.append({"problem": p, "stem_docx": str(sd), "answer_docx": str(ad),
                      "stem_png": spng, "answer_png": apng})
        print(f"  渲染 第{cn}题: 题干{len(spng)}张 答案{len(apng)}张")
    dp.quit_word()
    print("PNG 渲染完成，启动浏览器开始解题...\n")

    # —— 第2阶段：浏览器循环 A解题 → B判卷 → 打包 ——
    wrong = []
    pw, ctx = da.launch(headless=False)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(config.A_SITE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)
        for i, it in enumerate(items, 1):
            cn = it["problem"]["cn_idx"]
            print(f"[{i}/{len(items)}] 第{cn}题  {it['problem']['title'][:30]}")
            # 新对话(避免上下文污染)
            try:
                page.keyboard.press("Control+Shift+K")
                page.wait_for_timeout(2500)
            except Exception:
                pass
            # A 解题(含截图回复)
            reply_png = str(work / f"第{cn}题_reply.png")
            a = da.solve_one(ctx, it["stem_png"], reply_png_path=reply_png)
            print(f"   链接: {a['share_link'][:70]}")
            # B 判卷(三图: 题干 + 标准答案 + A解答截图)
            res = judge.judge(it["stem_png"], it["answer_png"],
                              [reply_png] if a.get("reply_png") else [])
            if res["correct"]:
                print(f"   → A 正确，不打包")
            else:
                seq = len(wrong) + 1
                ws = res.get("wrong_step", "")
                print(f"   → A 错误" + (f" 【{ws}】" if ws else "") + f": {res['error_point']}")
                ep = (f"【错步】{ws}\n{res['error_point']}" if ws else res["error_point"])
                grp = pk.archive_wrong_problem(
                    it["problem"], a["share_link"], ep,
                    it["stem_docx"], it["answer_docx"],
                    config.OUTPUT_DIR, theme, seq)
                wrong.append(grp)
    finally:
        ctx.close()
        pw.stop()

    print(f"\n==== 完成：错题 {len(wrong)} 道 ====")
    if wrong:
        zip_p = pk.make_zip(wrong, config.OUTPUT_DIR / config.ZIP_NAME_FMT.format(theme=theme))
        print(f"zip: {zip_p} ({pathlib.Path(zip_p).stat().st_size // 1024} KB)")


def _pick_docx():
    """弹文件选择对话框，让用户选题目 docx。"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="选择题目合集 (Word 文档)",
            filetypes=[("Word 文档", "*.docx *.doc"), ("所有文件", "*.*")],
        )
        root.destroy()
        return path
    except Exception:
        return ""


if __name__ == "__main__":
    a = sys.argv
    if len(a) >= 4:
        # 命令行模式: main.py <docx> <主题> <起始题号> [结束题号]
        run(a[1], a[2], int(a[3]), int(a[4]) if len(a) > 4 else None)
    else:
        # 交互模式: 弹窗让用户选文件
        docx = a[1] if len(a) > 1 else _pick_docx()
        if not docx:
            docx = input("未选文件，请输入题目 docx 路径: ").strip()
        if not docx:
            print("未提供文件，退出。"); sys.exit(1)
        # 主题默认从文件名推断(如"量子-电磁学" → "电磁学")
        default_theme = pathlib.Path(docx).stem.replace("量子-", "") or "题目"
        theme = a[2] if len(a) > 2 else (
            input(f"主题(回车={default_theme}): ").strip() or default_theme)
        rng = input("题号范围(如 7-10，回车=全部): ").strip()
        start = end = None
        if rng:
            if "-" in rng:
                s, e = rng.split("-", 1)
                start, end = int(s), int(e)
            else:
                start = int(rng)
        run(docx, theme, start, end)
