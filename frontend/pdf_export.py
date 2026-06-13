"""使用 fpdf2 从分析结果生成 PDF 报告。"""

from __future__ import annotations

import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import fpdf as _fpdf_mod
from fpdf import FPDF


# fpdf2（社区维护的分支）和已被废弃的 pyfpdf 1.x 都以 `fpdf` 命名导入，
# 同时安装两者时，磁盘上最后安装的会覆盖另一个。pyfpdf 1.x 将每页编码为
# latin-1，因此任何中文字符都会在库内部抛出神秘的
# `UnicodeEncodeError: 'latin-1' codec can't encode` 错误（issue #54）。
# 这里提前检测错误的库版本，并告诉用户如何修复，而不是在 PDF 渲染中途崩溃。
_FPDF_VERSION = getattr(_fpdf_mod, "__version__", None) or getattr(_fpdf_mod, "FPDF_VERSION", "0")


def _ensure_fpdf2() -> None:
    try:
        major = int(str(_FPDF_VERSION).split(".")[0])
    except (ValueError, IndexError):
        major = 0
    if major < 2:
        raise RuntimeError(
            f"检测到旧版 fpdf (pyfpdf {_FPDF_VERSION})，它用 latin-1 编码、无法处理中文，"
            "会导致 PDF 导出崩溃（issue #54）。请执行：\n"
            '    pip uninstall -y fpdf && pip install "fpdf2>=2.8.0"\n'
            "（fpdf 与 fpdf2 都以 `fpdf` 名称导入、互相冲突，必须卸载旧的 fpdf），"
            "或改用「下载 Markdown」导出。"
        )


# 各操作系统的 CJK 字体候选列表。优先尝试当前操作系统的字体，
# 这样 Windows/Linux/macOS 用户无需手动配置即可获得可用的 PDF。
_WIN_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",    # 微软雅黑 Bold
    "C:/Windows/Fonts/simhei.ttf",    # 黑体
    "C:/Windows/Fonts/simsun.ttc",    # 宋体
    "C:/Windows/Fonts/simfang.ttf",   # 仿宋
]
_MAC_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
_LINUX_FONTS = [
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]

# 在递归扫描中，下列子字符串可可靠标识支持 CJK 的字体
#（刻意排除 "noto"，因为它也会匹配仅支持拉丁字符的 Noto 系列）。
_CJK_FONT_KEYWORDS = (
    "msyh", "simhei", "simsun", "simfang", "yahei", "fangsong",
    "pingfang", "heiti", "stheiti", "stsong", "songti", "kaiti",
    "hiragino sans gb", "arial unicode",
    "notosanscjk", "notoserifcjk", "notosanssc", "notoserifsc",
    "sourcehansans", "sourcehanserif", "wqy", "uming", "ukai",
)


def _font_candidates() -> list[str]:
    """返回 CJK 字体路径列表，优先当前操作系统的字体。"""
    system = platform.system()
    if system == "Windows":
        return _WIN_FONTS + _MAC_FONTS + _LINUX_FONTS
    if system == "Darwin":
        return _MAC_FONTS + _WIN_FONTS + _LINUX_FONTS
    return _LINUX_FONTS + _MAC_FONTS + _WIN_FONTS


def _search_dirs() -> list[str]:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return ["C:/Windows/Fonts"]
    if system == "Darwin":
        return ["/System/Library/Fonts", "/Library/Fonts", str(home / "Library/Fonts")]
    return ["/usr/share/fonts", "/usr/local/share/fonts", str(home / ".fonts")]


def _find_cjk_font() -> str | None:
    """跨平台查找支持 CJK 的 TTF/TTC/OTF 字体。

    1. 尝试已知的各操作系统候选路径。
    2. 回退到递归扫描常用字体目录，寻找文件名中包含 CJK 关键词的字体文件。
    """
    for path in _font_candidates():
        if Path(path).exists():
            return path

    for directory in _search_dirs():
        dpath = Path(directory)
        if not dpath.exists():
            continue
        for ext in ("*.ttc", "*.ttf", "*.otf"):
            try:
                for font_path in sorted(dpath.rglob(ext)):
                    if any(k in font_path.name.lower() for k in _CJK_FONT_KEYWORDS):
                        return str(font_path)
            except OSError:
                continue
    return None


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


def _strip_md_inline(text: str) -> str:
    """移除行内 Markdown 格式：**加粗**、*斜体*、`代码`、[链接](url)。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text


def _signal_color(signal: str) -> tuple[int, int, int]:
    s = signal.upper()
    if "BUY" in s:
        return (34, 197, 94)
    if "SELL" in s:
        return (239, 68, 68)
    return (251, 191, 36)


_REPORT_SECTIONS = [
    ("market_report", "技术分析报告"),
    ("sentiment_report", "市场情绪报告"),
    ("news_report", "新闻舆情报告"),
    ("fundamentals_report", "基本面报告"),
    ("policy_report", "政策分析报告"),
    ("hot_money_report", "游资追踪报告"),
    ("lockup_report", "解禁/减持报告"),
]


class _ReportPDF(FPDF):
    def __init__(self, ticker: str, trade_date: str, signal: str) -> None:
        super().__init__()
        self.ticker = ticker
        self.trade_date = trade_date
        self.signal = signal
        font_path = _find_cjk_font()
        if not font_path:
            raise RuntimeError(
                "未找到可用的中文字体，无法生成 PDF。请安装一款中文字体后重试"
                "（Windows 自带微软雅黑/黑体，macOS 自带苹方，Linux 可 "
                "`apt install fonts-noto-cjk`），或改用「下载 Markdown」导出。"
            )
        self.add_font("CJK", "", font_path)
        self.add_font("CJK", "B", font_path)

    def _use_font(self, style: str = "", size: int = 10) -> None:
        self.set_font("CJK", style, size)

    def header(self) -> None:
        self._use_font("", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 6, f"A股多Agent投研分析  |  {self.ticker}  |  {self.trade_date}", align="C")
        self.ln(8)
        self.set_draw_color(60, 60, 60)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self._use_font("", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, f"Page {self.page_no()}/{{nb}}", align="C")
        self.ln(4)
        self._use_font("", 6)
        self.set_text_color(160, 160, 160)
        self.cell(0, 4, "仅供学习研究，不构成投资建议", align="C")

    def add_cover(self) -> None:
        self.add_page()
        self.ln(60)

        self._use_font("B", 24)
        self.set_text_color(255, 90, 31)
        self.cell(0, 12, "A股多Agent投研分析报告", align="C")
        self.ln(20)

        self._use_font("B", 36)
        self.set_text_color(30, 30, 30)
        self.cell(0, 18, self.ticker, align="C")
        self.ln(16)

        self._use_font("", 14)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"分析日期: {self.trade_date}", align="C")
        self.ln(8)
        self.cell(0, 10, f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")
        self.ln(20)

        r, g, b = _signal_color(self.signal)
        self._use_font("B", 40)
        self.set_text_color(r, g, b)
        self.cell(0, 20, self.signal.upper(), align="C")
        self.ln(20)

        self._use_font("", 9)
        self.set_text_color(120, 120, 120)
        self.multi_cell(
            0, 5,
            "免责声明: 本报告由 AI 多 Agent 系统自动生成, 仅供学习研究与技术演示, "
            "不构成任何投资建议。投资决策请咨询持牌专业机构。"
            "使用本报告所产生的任何损失由使用者自行承担。",
            align="C",
        )

    def add_section(self, title: str, content: str) -> None:
        self.add_page()
        self._use_font("B", 16)
        self.set_text_color(255, 90, 31)
        self.cell(0, 10, title)
        self.ln(12)

        cleaned = _strip_think(content)
        self._render_markdown(cleaned)

    def _render_markdown(self, text: str) -> None:
        """将 Markdown 格式文本渲染为带基本样式的 PDF 内容。"""
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 空行 → 添加小间距
            if not stripped:
                self.ln(3)
                i += 1
                continue

            # 标题：### → 11pt，## → 13pt，# → 14pt
            if stripped.startswith("###"):
                self._use_font("B", 11)
                self.set_text_color(50, 50, 50)
                self.cell(0, 7, stripped.lstrip("#").strip())
                self.ln(8)
                i += 1
                continue
            if stripped.startswith("##"):
                self._use_font("B", 13)
                self.set_text_color(40, 40, 40)
                self.cell(0, 8, stripped.lstrip("#").strip())
                self.ln(9)
                i += 1
                continue
            if stripped.startswith("#"):
                self._use_font("B", 14)
                self.set_text_color(255, 90, 31)
                self.cell(0, 9, stripped.lstrip("#").strip())
                self.ln(10)
                i += 1
                continue

            # 水平分割线
            if stripped in ("---", "***", "___"):
                self.set_draw_color(180, 180, 180)
                y = self.get_y() + 2
                self.line(10, y, self.w - 10, y)
                self.ln(6)
                i += 1
                continue

            # 列表项（-、*、数字列表）
            if re.match(r"^[-*]\s", stripped) or re.match(r"^\d+[.)]\s", stripped):
                self._use_font("", 10)
                self.set_text_color(40, 40, 40)
                if re.match(r"^[-*]\s", stripped):
                    bullet = "  •  "
                    body = stripped[2:].strip()
                else:
                    m = re.match(r"^(\d+[.)])\s*(.*)", stripped)
                    bullet = f"  {m.group(1)} "
                    body = m.group(2)
                body = _strip_md_inline(body)
                self.set_x(self.l_margin)
                self.multi_cell(0, 5.5, bullet + body, wrapmode="CHAR")
                i += 1
                continue

            # 表格行（|col|col|）→ 渲染为带间距的纯文本
            if stripped.startswith("|") and stripped.endswith("|"):
                # 跳过分隔行，如 |---|---|
                if re.match(r"^\|[-:\s|]+\|$", stripped):
                    i += 1
                    continue
                self._use_font("", 9)
                self.set_text_color(60, 60, 60)
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                row_text = "    ".join(_strip_md_inline(c) for c in cells)
                self.set_x(self.l_margin)
                self.multi_cell(0, 5, row_text, wrapmode="CHAR")
                i += 1
                continue

            # 普通段落 — 收集连续的非特殊行
            para_lines = []
            while i < len(lines):
                ln = lines[i].strip()
                if not ln or ln.startswith("#") or ln.startswith("|") or re.match(r"^[-*]\s", ln) or re.match(r"^\d+[.)]\s", ln) or ln in ("---", "***", "___"):
                    break
                para_lines.append(ln)
                i += 1

            if para_lines:
                self._use_font("", 10)
                self.set_text_color(40, 40, 40)
                para = " ".join(para_lines)
                para = _strip_md_inline(para)
                self.set_x(self.l_margin)
                self.multi_cell(0, 5.5, para, wrapmode="CHAR")
                self.ln(2)
                continue

            i += 1


def _collect_sections(final_state: dict[str, Any]) -> list[tuple[str, str]]:
    """组装 PDF 和 Markdown 共用的 (标题, 内容) 报告章节列表。

    确保两种导出格式从同一数据源生成，保持内容同步。
    """
    sections: list[tuple[str, str]] = []

    for key, title in _REPORT_SECTIONS:
        content = final_state.get(key, "")
        if content:
            sections.append((title, _strip_think(str(content))))

    debate = final_state.get("investment_debate_state")
    if debate and isinstance(debate, dict):
        parts = []
        if debate.get("bull_history"):
            parts.append(f"=== 多方论点 ===\n{debate['bull_history']}")
        if debate.get("bear_history"):
            parts.append(f"\n=== 空方论点 ===\n{debate['bear_history']}")
        if debate.get("judge_decision"):
            parts.append(f"\n=== 研究经理决策 ===\n{debate['judge_decision']}")
        if parts:
            sections.append(("多空辩论", _strip_think("\n".join(parts))))

    trader_decision = final_state.get("trader_investment_decision", "")
    if trader_decision:
        sections.append(("交易员决策", _strip_think(str(trader_decision))))

    inv_plan = final_state.get("investment_plan", "")
    if inv_plan:
        sections.append(("最终投资建议", _strip_think(str(inv_plan))))

    risk = final_state.get("risk_debate_state")
    if risk and isinstance(risk, dict):
        parts = []
        for key_name, label in [("aggressive_history", "激进观点"),
                                 ("conservative_history", "保守观点"),
                                 ("neutral_history", "中性观点")]:
            if risk.get(key_name):
                parts.append(f"=== {label} ===\n{risk[key_name]}")
        if risk.get("judge_decision"):
            parts.append(f"\n=== 风控决策 ===\n{risk['judge_decision']}")
        if parts:
            sections.append(("风控评估", _strip_think("\n".join(parts))))

    final_decision = final_state.get("final_trade_decision", "")
    if final_decision:
        sections.append(("最终决策", _strip_think(str(final_decision))))

    return sections


def generate_pdf(final_state: dict[str, Any], ticker: str, trade_date: str, signal: str) -> bytes:
    """生成 PDF 报告并以字节形式返回。

    Raises:
        RuntimeError: 安装了错误的 fpdf 库（issue #54）或系统中没有可用的 CJK 字体时抛出。
            调用方应捕获此异常并回退到 Markdown 导出。
    """
    _ensure_fpdf2()
    pdf = _ReportPDF(ticker, trade_date, signal)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    pdf.add_cover()
    for title, content in _collect_sections(final_state):
        pdf.add_section(title, content)

    return bytes(pdf.output())


def generate_markdown(final_state: dict[str, Any], ticker: str, trade_date: str, signal: str) -> str:
    """生成 Markdown 报告。无需字体，始终可用 — 安全导出方式。

    当系统缺少 CJK 字体时（常见于最小化安装的 Linux/Windows），
    这是 PDF 的可靠替代方案。
    """
    out = [
        "# A股多Agent投研分析报告",
        "",
        f"- **股票代码**：{ticker}",
        f"- **分析日期**：{trade_date}",
        f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- **交易信号**：**{signal.upper()}**",
        "",
        "> ⚠️ 本报告由 AI 多 Agent 系统自动生成，仅供学习研究与技术演示，"
        "不构成任何投资建议。投资决策请咨询持牌专业机构，使用本报告所产生的"
        "任何损失由使用者自行承担。",
        "",
        "---",
        "",
    ]
    for title, content in _collect_sections(final_state):
        out.append(f"## {title}")
        out.append("")
        out.append(content)
        out.append("")

    return "\n".join(out)
