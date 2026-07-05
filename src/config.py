# -*- coding: utf-8 -*-
"""全局配置。

敏感信息(API key)优先从环境变量读取，兜底从 ~/.claude.json 读已配的智谱 key。
模型A(解题)走火山方舟网页自动化；模型B(判卷)走智谱 GLM API。
"""
import os
import json
import pathlib

# ---------------------------------------------------------------- 路径
ROOT = pathlib.Path(__file__).resolve().parent.parent        # 豆包测评/
SRC  = pathlib.Path(__file__).resolve().parent               # src/
INPUT_DIR       = ROOT / "原题目"        # 原始题目合集(输入)
OUTPUT_DIR      = ROOT / "out"          # 最终输出(zip 等)
TMP_DIR         = ROOT / "tmp"          # 中间产物(题干图、A/B 的原始返回等)
BROWSER_PROFILE = ROOT / "browser_data" # playwright 持久登录态(首次手动登录后复用)

for _d in (OUTPUT_DIR, TMP_DIR, BROWSER_PROFILE):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 模型 A (解题: 火山方舟网页)
A_MODEL_NAME   = "豆包(免费网页版)"
A_SITE_URL     = "https://www.doubao.com/chat/"
A_CONCURRENCY  = 1                       # 第一版串行; 跑通后调大实现并发
A_REPLY_TIMEOUT_MS = 300_000             # 单题等待豆包回复的最长时间(5 分钟)

# ---------------------------------------------------------------- 模型 B (判卷: 智谱 GLM API)
def _load_zhipu_key() -> str:
    """优先环境变量，兜底从 ~/.claude.json 的 MCP 配置里取已配的智谱 key。"""
    key = os.environ.get("ZHIPU_API_KEY") or os.environ.get("Z_AI_API_KEY")
    if key:
        return key.strip()
    cj = pathlib.Path.home() / ".claude.json"
    if cj.exists():
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            srv = (data.get("mcpServers") or {}).get("zai-mcp-server") or {}
            key = (srv.get("env") or {}).get("Z_AI_API_KEY")
        except Exception:
            key = None
    return (key or "").strip()

ZHIPU_API_KEY = _load_zhipu_key()
ZHIPU_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
# 模型B(判卷)用智谱视觉模型——看题干/答案 PNG + A 的解析文本。
# 注意: glm-5.x / 4.6 等纯文本模型在本端点不接受图片(content.type 仅允许 text);
# 视觉能力须用 glm-4.5v / glm-4v-plus 系列(实测本 key 均可调，models 列表未列出)。
B_MODEL_NAME    = os.environ.get("B_MODEL") or "glm-4.5v"       # 主：最强视觉推理
B_FALLBACK      = os.environ.get("B_FALLBACK") or "glm-4v-plus"  # 备：主模型异常/空回复时回退
B_VISION_MODELS = ["glm-4.5v", "glm-4v-plus", "glm-4v-flash", "glm-4v"]
# 模型B 的 API 入口——用户可用环境变量换成任意兼容 OpenAI chat/completions 格式的视觉模型
# (GPT-4o / Claude / Gemini 等，判物理负号更准)：
#   set B_API_URL=...  B_API_KEY=...  B_MODEL=...  B_FALLBACK=...
# 不设则默认用智谱 GLM 视觉模型。
B_API_URL = os.environ.get("B_API_URL") or ZHIPU_API_URL
B_API_KEY = os.environ.get("B_API_KEY") or ZHIPU_API_KEY

# ---------------------------------------------------------------- 拆分 / 命名
# 题号用中文数字: "第一题" / "第一题答案"
CN_NUMS = "一二三四五六七八九十"
# 当前批次的主题词(命名 错题-...-主题/ 用)。main 可按输入文件名覆盖。
DEFAULT_THEME = "电磁"
# 报告里那行固定说明文字
REPORT_NOTE_LINE = "我在豆包与 AI 对话，快来看看吧"

# ===== 输出命名模板(用户可自定义) =====
# 可用变量: {date} 日期  {seq} 序号  {theme} 主题  {cn} 中文题号  {int} 阿拉伯题号
WRONG_FOLDER_FMT = "错题-{date}-{seq:02d}-{theme}"  # 错题文件夹名
DOCX_NAME_FMT   = "{theme}第{cn}题.docx"          # 题干/答案文件名
REPORT_NAME     = "链接及说明.docx"                # 报告文件名
ZIP_NAME_FMT    = "错题集_{theme}.zip"             # 最终 zip 名

def warn_if_no_b_key():
    if not ZHIPU_API_KEY:
        print("[警告] 未找到智谱 API key，请设置环境变量 ZHIPU_API_KEY，"
              "或保证 ~/.claude.json 里 zai-mcp-server.env.Z_AI_API_KEY 存在。")
