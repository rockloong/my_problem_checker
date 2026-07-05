# -*- coding: utf-8 -*-
"""打包模块：把错题归档成 错题 文件夹 + 打 zip；A 答对时清理中间文件。

命名(模仿样板)：
  组文件夹  错题-YYYYMMDD-序号-主题/
    题干/主题第X题.docx
    答案/主题第X题.docx
    链接及说明.docx
"""
import pathlib
import shutil
import zipfile
import datetime
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config
import report

# 受保护、绝不能删的顶层目录名(相对项目根)
PROTECTED_NAMES = {"原题目", "src", "browser_data", "out", ".git"}


def archive_wrong_problem(problem, share_link, error_point,
                          stem_docx, answer_docx, out_root, theme, seq, date_str=None):
    """把一道错题归档成一个 错题 文件夹，并生成报告。返回该文件夹路径。"""
    date_str = date_str or datetime.date.today().strftime("%Y%m%d")
    cn = problem["cn_idx"]
    v = dict(date=date_str, seq=seq, theme=theme, cn=cn, int=problem["int_idx"])
    grp_dir = pathlib.Path(out_root) / config.WRONG_FOLDER_FMT.format(**v)
    (grp_dir / "题干").mkdir(parents=True, exist_ok=True)
    (grp_dir / "答案").mkdir(parents=True, exist_ok=True)

    fname = config.DOCX_NAME_FMT.format(**v)
    shutil.copy2(stem_docx, grp_dir / "题干" / fname)
    shutil.copy2(answer_docx, grp_dir / "答案" / fname)
    report.make_report(share_link, error_point, grp_dir / config.REPORT_NAME)
    return grp_dir


def make_zip(grp_dirs, zip_path):
    """把多个 错题 文件夹打成一个 zip(保留 错题-.../题干|答案/... 层级)。"""
    zip_path = pathlib.Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for d in grp_dirs:
            d = pathlib.Path(d)
            base = d.parent
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(base))
    return zip_path


def cleanup_problem_files(*paths):
    """删除一道题的中间产物(文件或文件夹)。

    安全：路径任意一段落在 PROTECTED_NAMES(原题目/src/browser_data/out) 时拒绝删除。
    """
    deleted = 0
    for p in paths:
        if not p:
            continue
        p = pathlib.Path(p)
        try:
            parts = set(p.resolve().parts)
        except Exception:
            parts = set(p.parts)
        if parts & PROTECTED_NAMES:
            print(f"  [保护] 拒绝删除(触及受保护目录): {p}")
            continue
        try:
            if p.is_file():
                p.unlink()
                deleted += 1
            elif p.is_dir():
                shutil.rmtree(p)
                deleted += 1
        except Exception as e:
            print(f"  [警告] 删除失败 {p}: {e}")
    return deleted
