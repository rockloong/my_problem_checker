# -*- coding: utf-8 -*-
"""火山方舟体验中心网页自动化(模型A=豆包解题)。

playwright 持久登录态(首次手动登录, 之后复用)；
对每道题：上传题干PNG + 提交 + 等回复完整 + 点"分享"生成 exsc 链接。

⚠️ DOM 选择器(输入框/发送/上传/分享按钮)需先用 probe() 探查实际页面后填充，
   见下方 TODO 标记。不同网站/版本 DOM 不同，无法预先写死。
"""
import pathlib
import sys
import time
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config


def launch(headless=False):
    """启动持久化浏览器上下文(登录态存 browser_data/)。首次 headless=False 方便手动登录。"""
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(config.BROWSER_PROFILE),
        headless=headless,
        viewport={"width": 1400, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    return pw, ctx


def probe(url=None, headless=True, dump_file=None):
    """探查页面结构：打印 URL/标题 + 主要可交互元素，用于定位 DOM 选择器。"""
    url = url or config.A_SITE_URL
    pw, ctx = launch(headless=headless)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print(f"[ ] 打开 {url} ...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print("URL :", page.url)
        print("标题:", page.title())
        info = page.evaluate("""() => {
            const sel = 'input,textarea,button,[role=textbox],[contenteditable=true],[class*=input],[class*=send]';
            return [...document.querySelectorAll(sel)].slice(0, 50).map(e => ({
                tag: e.tagName,
                type: e.type || '',
                role: e.getAttribute('role') || '',
                ph: (e.placeholder || '').slice(0, 40),
                txt: (e.innerText || '').slice(0, 30),
                cls: (e.className || '').toString().slice(0, 60),
            }));
        }""")
        print(f"\n可交互元素({len(info)}个):")
        for e in info:
            print("  ", e)
        if dump_file:
            pathlib.Path(dump_file).write_text(
                "\n".join(str(e) for e in info), encoding="utf-8")
        return info
    finally:
        ctx.close()
        pw.stop()


def solve_one(ctx, stem_pngs, prompt_text="请详细解答这道物理竞赛题，写出完整的推导过程和最终结果。", reply_png_path=None):
    """对一道题：上传题干PNG + 发送 + 等回复完毕 + 分享拿链接。

    返回 {"solution": 回复文本, "share_link": 分享链接}。
    关键：豆包点"分享"(右上角 ~1358,15)后当前对话默认勾选，直接"复制链接"即可（别点全选）。
    完毕检测：body 文本长度连续 3 次(6秒)不变。
    """
    import pyperclip
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # 1. 上传题干PNG(多张一起传)
    if stem_pngs:
        try:
            page.locator("input[type=file]").first.set_input_files(stem_pngs)
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"  [警告] 上传图片失败: {e}")

    # 2. 输入提示 + 回车发送
    ta = page.locator("textarea[placeholder*='发消息']").first
    ta.click()
    page.keyboard.type(prompt_text, delay=30)
    page.wait_for_timeout(800)
    page.keyboard.press("Enter")

    # 3. 等回复完毕(body 文本长度连续 3 次=6秒 不变)，最多 ~3 分钟
    prev, stable = -1, 0
    for _ in range(90):
        page.wait_for_timeout(2000)
        L = page.evaluate("()=>document.body.innerText.length")
        stable = stable + 1 if L == prev else 0
        prev = L
        if stable >= 3:
            break

    # 4. 抓回复(prompt 之后到结尾的文本，去掉尾部输入栏/侧边栏干扰)
    body = page.evaluate("()=>document.body.innerText")
    idx = body.rfind(prompt_text)
    reply = body[idx + len(prompt_text):].strip() if idx >= 0 else body[-1500:]
    for marker in ["全选\n分享图片", "复制链接", "快速\nPPT", "AI 生成可能有误", "新对话"]:
        mi = reply.find(marker)
        if mi > 50:
            reply = reply[:mi].strip()
            break

    # 4.5 截图豆包回复 → A解答PNG(只截对话区 main，去掉左侧边栏历史对话的干扰)
    if reply_png_path:
        try:
            page.evaluate("()=>{const s=document.scrollingElement||document.body; if(s)s.scrollTop=s.scrollHeight;}")
            page.wait_for_timeout(800)
            shot = False
            for sel in ["main", "[role=main]", "[class*=message-list]", "[class*=conversation]"]:
                el = page.locator(sel).last
                if el.count() > 0:
                    try:
                        el.screenshot(path=str(reply_png_path))
                        shot = True
                        break
                    except Exception:
                        pass
            if not shot:
                page.screenshot(path=str(reply_png_path), full_page=True)
        except Exception as e:
            print(f"  [警告] 截图回复失败: {e}")

    # 5. 分享 → 复制链接(右上角分享后当前对话默认勾选，直接复制链接；加重试+JS兜底)
    link = ""
    for attempt in range(3):
        pyperclip.copy("___SENTINEL___")
        try:
            page.evaluate(
                "() => {const b=[...document.querySelectorAll('button')].find(b=>{const r=b.getBoundingClientRect();"
                "return Math.abs(r.x-1358)<14&&Math.abs(r.y-15)<14;}); if(b)b.click();}")
            page.wait_for_timeout(1800)
            try:
                page.get_by_text("复制链接", exact=True).first.click(timeout=4000)
            except Exception:
                # JS 兜底: 直接 click 含"复制链接"的 button
                page.evaluate(
                    "() => {const els=[...document.querySelectorAll('*')].filter(e=>(e.innerText||'').trim()==='复制链接'&&e.offsetParent);"
                    "let p=els[0]; while(p&&p.tagName!=='BUTTON')p=p.parentElement; if(p)p.click();}")
            page.wait_for_timeout(2500)
            link = pyperclip.paste()
            if link and link != "___SENTINEL___":
                break
        except Exception as e:
            print(f"  [警告] 复制链接重试{attempt+1}: {e}")
        page.wait_for_timeout(1000)
    return {"solution": reply, "share_link": link,
            "reply_png": str(reply_png_path) if reply_png_path else ""}


def login():
    """非headless打开火山方舟，等用户手动登录后关闭浏览器，登录态存 browser_data/。"""
    pw, ctx = launch(headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(config.A_SITE_URL)
    print("\n" + "=" * 56)
    print(f"浏览器已打开 {config.A_SITE_URL}")
    print("请在浏览器里：")
    print("  1. 点'登录'，完成登录(抖音/手机号/扫码)")
    print("  2. 登录后【发一条测试消息，确认豆包能回复】(关键!)")
    print("  3. 确认能收到回复后，关闭浏览器窗口")
    print("=" * 56)
    print("脚本会自动检测登录、然后自动保存并关闭(不用你手动关浏览器)。")
    # 第1步：等页面加载完(登录按钮出现)，避免加载阶段 count=0 误判
    print("等待页面加载...")
    try:
        page.locator("button:has-text('登录')").wait_for(state="visible", timeout=30000)
        print("页面加载完。现在请在浏览器里【登录豆包】。")
    except Exception:
        print("页面加载慢；若已看到豆包页面，请直接登录。")
    # 第2步：连续 2 次检测到登录按钮消失，才算真正登录(避免加载瞬间误判)
    logged = False
    stable = 0
    for _ in range(120):  # 最多等 6 分钟
        try:
            page.wait_for_timeout(3000)
            if page.locator("button:has-text('登录')").count() == 0:
                stable += 1
                if stable >= 2:
                    logged = True
                    break
            else:
                stable = 0
        except Exception:
            break  # 浏览器被手动关闭
    if logged:
        print("[检测到登录成功] 登录态已写入，5秒后自动保存关闭。")
        try:
            page.wait_for_timeout(5000)
        except Exception:
            pass
    else:
        print("[未检测到登录或浏览器已被关]")
    try:
        ctx.close()   # 关键：优雅关闭，确保登录态写入磁盘
    except Exception:
        pass
    pw.stop()
    print("[完成] 登录态已保存到 browser_data/")
    try:
        pw.stop()
    except Exception:
        pass


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "login":
        login()
    elif cmd == "probe":
        probe(headless=False)
    else:
        print("用法: python -X utf8 src/doubao_auto.py login | probe")
