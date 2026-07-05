# 豆包错题测评

自动用**豆包**解题 + **视觉大模型**判卷,筛出豆包做错的题,打包成错题集。

## 它做什么
读入一份**题目合集 Word**(含题干+答案) → 拆分每道题 → 把题干图发给**豆包**解题 → 用**视觉大模型**(默认智谱 GLM,可换 GPT-4o 等)对比豆包解答和标准答案 → 筛出豆包做错的题,生成报告(分享链接 + 错点)打包成 zip。

## 题目 Word 格式要求
- 每道题以「**第X题**」开头(中文数字:第一题/第二题/.../第十题)。
- 紧跟「**第X题答案**」给出标准答案。
- 题干、答案均支持 Word 公式编辑器(OMML)和图片。
- 答案紧跟题干(顺序:题干 → 答案 → 下一题 → ...)。
- 缺答案的题会自动跳过;答案标题笔误的题也会跳过。

## 使用

### 1. 装依赖
```bash
pip install -r requirements.txt
python -m playwright install chromium
```
> docx→PNG:Windows 用 Microsoft Word;Mac/Linux 需装 LibreOffice(`soffice` 在 PATH)。

### 2. 首次登录豆包(一次性,之后免登录)
```bash
python src/doubao_auto.py login
```
浏览器打开豆包 → 登录(抖音/手机号/扫码) → 脚本自动检测并保存登录态(**别手动关浏览器**,否则登录态丢失)。

### 3. 跑测评
```bash
python src/main.py
```
**交互式**:弹窗选你的题目 docx → 输入主题、题号范围(如 `7-10`,或回车全部) → 浏览器自动逐题解题 + 判卷 → 错题打包。

### 4. 输出
```
out/错题集_<主题>.zip
  错题-日期-序号-<主题>/
    题干/<主题>第X题.docx
    答案/<主题>第X题.docx
    链接及说明.docx    ← 豆包分享链接 + 判卷给的错点(三点:哪个式子/AI写的/正确应是什么)
```

## 配置(可选)

**判卷模型 B**——默认智谱 `glm-4.5v`。换成判物理负号更准的视觉模型(GPT-4o / Claude / Gemini),设环境变量即可(兼容 OpenAI 格式):
```bash
set B_API_URL=https://api.openai.com/v1/chat/completions
set B_API_KEY=sk-...
set B_MODEL=gpt-4o
```
见 `.env.example`。智谱 key 也可显式设 `ZHIPU_API_KEY`。

**输出命名**——改 `src/config.py` 的模板(`WRONG_FOLDER_FMT` / `DOCX_NAME_FMT` / `ZIP_NAME_FMT`),支持变量 `{date}` `{seq}` `{theme}` `{cn}` `{int}`。

## ⚠️ 判卷需人工复核
视觉模型判物理公式的正负号/系数**有误差**(可能误判或漏判)。请把程序当「错题候选筛选器」:zip 里的错点扫一眼确认,别完全信任。

## 代码结构
| 文件 | 职责 |
|---|---|
| `src/splitter.py` | docx 拆分(正则识别「第X题」+顺序就近配对题干/答案) |
| `src/docx_to_png.py` | docx→PNG(Word COM / LibreOffice headless) |
| `src/doubao_auto.py` | 豆包网页自动化(playwright,上传题干图+拿分享链接) |
| `src/judge.py` | 视觉判卷(三图:题干+标准答案+豆包解答截图) |
| `src/report.py` | 生成「链接及说明.docx」 |
| `src/packager.py` | 错题归档 + 打 zip(答对的题丢弃) |
| `src/main.py` | 主流程(交互式入口) |
| `src/config.py` | 配置(模型/命名/路径) |
