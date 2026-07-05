# -*- coding: utf-8 -*-
"""docx → PNG：Word COM 把 docx 渲染为 PDF，PyMuPDF 把 PDF 每页转 PNG。

Word COM 渲染最忠实(公式、排版、字体、配图原样)，适合把题干/答案
喂给多模态模型(豆包 A / GLM-4V B)。一题可能多页 → 多张 PNG。
"""
import os
import pathlib
import win32com.client as win32
import fitz  # PyMuPDF

WD_FORMAT_PDF = 17
_word = None


def _get_word():
    """复用同一个 Word 进程。late binding(DynamicDispatch)更健壮。"""
    global _word
    if _word is None:
        _word = win32.Dispatch("Word.Application")
        _word.Visible = False
        _word.DisplayAlerts = False
    return _word


def _docx_to_pdf_soffice(docx_path, pdf_path):
    """Mac/Linux 用 LibreOffice headless 把 docx 转 pdf。需装 LibreOffice(soffice 在 PATH)。"""
    import subprocess
    docx_path = os.path.abspath(str(docx_path))
    out_dir = os.path.abspath(str(pathlib.Path(pdf_path).parent))
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", out_dir, docx_path], check=True, timeout=180)
    produced = pathlib.Path(out_dir) / (pathlib.Path(docx_path).stem + ".pdf")
    if produced != pathlib.Path(pdf_path) and produced.exists():
        produced.rename(pdf_path)
    return pdf_path


def docx_to_pdf(docx_path, pdf_path):
    import sys as _sys
    import time
    # 非 Windows: 用 LibreOffice headless (跨平台)
    if _sys.platform != "win32":
        return _docx_to_pdf_soffice(docx_path, pdf_path)
    # Windows: 用 Word COM
    docx_path = os.path.abspath(str(docx_path))
    pdf_path = os.path.abspath(str(pdf_path))
    pathlib.Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    global _word
    last_err = None
    for attempt in range(3):   # RPC 失败时重置 Word 进程重试
        try:
            word = _get_word()
            doc = word.Documents.Open(docx_path, ReadOnly=True)
            break
        except Exception as e:
            last_err = e
            _word = None
            time.sleep(1)
    else:
        raise last_err
    try:
        try:
            doc.SaveAs2(pdf_path, FileFormat=WD_FORMAT_PDF)
        except Exception:
            doc.SaveAs(pdf_path, FileFormat=WD_FORMAT_PDF)
    finally:
        try:
            doc.Close(SaveChanges=False)
        except Exception:
            pass
    return pdf_path


def pdf_to_pngs(pdf_path, out_dir, dpi=200, prefix="page"):
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open(str(pdf_path))
    try:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        paths = []
        for i, page in enumerate(pdf):
            pix = page.get_pixmap(matrix=mat)
            fp = out_dir / f"{prefix}_{i + 1}.png"
            pix.save(str(fp))
            paths.append(str(fp))
        return paths
    finally:
        pdf.close()


def docx_to_pngs(docx_path, out_dir, dpi=200, prefix="page"):
    """docx → PNG 路径列表(每页一张)。中间 PDF 留在同目录便于排查。"""
    docx_path = pathlib.Path(docx_path)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / (docx_path.stem + ".pdf")
    docx_to_pdf(docx_path, pdf_path)
    return pdf_to_pngs(pdf_path, out_dir, dpi=dpi, prefix=prefix)


def quit_word():
    global _word
    if _word is not None:
        try:
            _word.Quit()
        except Exception:
            pass
        _word = None


def _main():
    import sys
    if len(sys.argv) < 2:
        print("用法: python -X utf8 src/docx_to_png.py <input.docx> [out_dir] [dpi]")
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "tmp/png_out"
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    try:
        pngs = docx_to_pngs(src, out, dpi=dpi)
        print(f"生成 {len(pngs)} 张 PNG:")
        for p in pngs:
            sz = pathlib.Path(p).stat().st_size // 1024
            print(f"  {p}  ({sz} KB)")
    finally:
        quit_word()


if __name__ == "__main__":
    _main()
