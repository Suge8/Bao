import os, base64, subprocess, tempfile

# Generate small logo base64 for embedding in hero SVG
_logo_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'resources', 'logo-circle.png')
_tmp = tempfile.mktemp(suffix='.png')
subprocess.run(['sips', '-z', '72', '72', _logo_src, '--out', _tmp], capture_output=True)
with open(_tmp, 'rb') as _f:
    LOGO_B64 = base64.b64encode(_f.read()).decode()
os.unlink(_tmp)

themes = {
    "dark": {
        "bg": "#0a0a0c",
        "bg_gradient_start": "#18181b",
        "bg_gradient_end": "#09090b",
        "panel_bg": "#141417",
        "panel_border": "#27272a",
        "card_bg": "#1c1c21",
        "card_border": "#3f3f46",
        "text_primary": "#ffffff",
        "text_secondary": "#a1a1aa",
        "text_muted": "#71717a",
        "accent": "#f59e0b",
        "accent_muted": "#b45309",
        "accent_bg": "#451a03",
        "line": "rgba(245, 158, 11, 0.4)",
        "glow": "rgba(245, 158, 11, 0.15)",
        "shadow": "rgba(0, 0, 0, 0.6)",
        "mint": "#34d399",
        "sky": "#38bdf8",
        "violet": "#a78bfa",
        "rose": "#fb7185",
        "mint_bg": "#022c22",
        "sky_bg": "#082f49",
        "violet_bg": "#2e1065",
        "rose_bg": "#4c0519",
    },
    "light": {
        "bg": "#fafafa",
        "bg_gradient_start": "#ffffff",
        "bg_gradient_end": "#f4f4f5",
        "panel_bg": "#ffffff",
        "panel_border": "#e4e4e7",
        "card_bg": "#ffffff",
        "card_border": "#d4d4d8",
        "text_primary": "#09090b",
        "text_secondary": "#52525b",
        "text_muted": "#a1a1aa",
        "accent": "#d97706",
        "accent_muted": "#f59e0b",
        "accent_bg": "#fef3c7",
        "line": "rgba(217, 119, 6, 0.3)",
        "glow": "rgba(245, 158, 11, 0.08)",
        "shadow": "rgba(0, 0, 0, 0.08)",
        "mint": "#10b981",
        "sky": "#0ea5e9",
        "violet": "#8b5cf6",
        "rose": "#f43f5e",
        "mint_bg": "#d1fae5",
        "sky_bg": "#e0f2fe",
        "violet_bg": "#ede9fe",
        "rose_bg": "#ffe4e6",
    }
}

icons = {
    'database': '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5M3 5c0 1.66 4 3 9 3s9-1.34 9-3M3 5c0-1.66 4-3 9-3s9 1.34 9 3M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>',
    'brain': '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/><path d="M3.477 10.896a4 4 0 0 1 .585-.396"/><path d="M19.938 10.5a4 4 0 0 1 .585.396"/><path d="M6 18a4 4 0 0 1-1.967-.516"/><path d="M19.967 17.484A4 4 0 0 1 18 18"/>',
    'timer': '<circle cx="12" cy="14" r="8"/><path d="M12 10v4l2 2"/><path d="M10 2h4"/><path d="M12 2v2"/>',
    'git-branch': '<line x1="6" x2="6" y1="3" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
    'terminal': '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
    'monitor': '<rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/>',
    'zap': '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    'server': '<rect width="20" height="8" x="2" y="2" rx="2" ry="2"/><rect width="20" height="8" x="2" y="14" rx="2" ry="2"/><line x1="6" x2="6.01" y1="6" y2="6"/><line x1="6" x2="6.01" y1="18" y2="18"/>',
    'box': '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    'message-square': '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    'cpu': '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    'check-circle': '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    'globe': '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    'code': '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'
}

def get_icon(name, color="#ffffff", size=24, stroke_width=2):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round">{icons.get(name, "")}</svg>'

def esc(s):
    """Escape text for safe embedding in SVG/XML."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


common_defs_template = """
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;display=swap');
      .font-sans {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
      .font-mono {{ font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace; }}
      .text-primary {{ fill: {text_primary}; }}
      .text-secondary {{ fill: {text_secondary}; }}
      .text-muted {{ fill: {text_muted}; }}
      .text-accent {{ fill: {accent}; }}
      .fw-medium {{ font-weight: 500; }}
      .fw-semibold {{ font-weight: 600; }}
      .fw-bold {{ font-weight: 700; }}
      .tracking-tight {{ letter-spacing: -0.02em; }}
      .tracking-wide {{ letter-spacing: 0.1em; }}
      
      @keyframes float {{ 0%, 100% {{ transform: translateY(0px); }} 50% {{ transform: translateY(-8px); }} }}
      @keyframes float-delayed {{ 0%, 100% {{ transform: translateY(0px); }} 50% {{ transform: translateY(-8px); }} }}
      @keyframes pulse {{ 0%, 100% {{ opacity: 0.5; }} 50% {{ opacity: 1; }} }}
      @keyframes line-flow {{ 0% {{ stroke-dashoffset: 24; }} 100% {{ stroke-dashoffset: 0; }} }}
      
      .animate-float {{ animation: float 6s ease-in-out infinite; }}
      .animate-float-delayed {{ animation: float-delayed 7s ease-in-out infinite; animation-delay: 1.5s; }}
      .animate-pulse {{ animation: pulse 4s ease-in-out infinite; }}
      .animate-flow {{ animation: line-flow 1.5s linear infinite; stroke-dasharray: 6 6; }}
    </style>
    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{bg_gradient_start}" />
      <stop offset="100%" stop-color="{bg_gradient_end}" />
    </linearGradient>
    <radialGradient id="glow-grad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{glow}" />
      <stop offset="100%" stop-color="{glow}" stop-opacity="0" />
    </radialGradient>
    <filter id="shadow-md" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="{shadow}" />
    </filter>
    <filter id="shadow-sm" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="{shadow}" />
    </filter>
  </defs>
  <rect width="100%" height="{height}" fill="{bg}" rx="16" />
  <rect width="100%" height="{height}" fill="url(#bg-grad)" rx="16" opacity="0.6" />
  <rect width="100%" height="{height}" fill="transparent" stroke="{panel_border}" stroke-width="2" rx="16" />
"""

def render_hero(t, lang, theme_name):
    title = "Bao"
    eyebrow = "PERSONAL AI THAT HOLDS UP"
    if lang == "zh":
        sub1 = "记得住，能并行，会进化"
        sub2 = "真正的持久记忆 · 闭环经验学习"
        sub3 = "并行长任务引擎 · 无缝接入编程代理体系"
        r1 = ("持久记忆", "LanceDB 向量检索", "database", "accent")
        r2 = ("经验引擎", "策略复用与置信度", "brain", "mint")
        r3 = ("长任务系统", "压实轨迹, 自动收口", "timer", "sky")
        r4 = ("子代理编排", "后台并行静默跑活", "git-branch", "violet")
        r5 = ("编码代理", "Codex / Claude Code", "terminal", "rose")
        r6 = ("九大平台", "一套能力随处可用", "globe", "accent")
    else:
        sub1 = "Remembers more, runs longer, evolves faster"
        sub2 = "True persistent memory · closed-loop learning"
        sub3 = "Parallel long-task engine · seamless coding agents"
        r1 = ("Persistent Memory", "LanceDB vector recall", "database", "accent")
        r2 = ("Experience Engine", "Strategy reuse & scoring", "brain", "mint")
        r3 = ("Long-Run Engine", "Compression & checkpoints", "timer", "sky")
        r4 = ("Subagent Scheduler", "Silent background work", "git-branch", "violet")
        r5 = ("Coding Agent", "Codex / Claude Code", "terminal", "rose")
        r6 = ("9 Platforms", "One capability everywhere", "globe", "accent")

    w, h = 840, 440
    rows = [r1, r2, r3, r4, r5, r6]

    # Build the 6 capability rows for the right panel
    row_height = 50
    row_gap = 6
    panel_padding = 16
    panel_inner_w = 280
    panel_w = panel_inner_w + panel_padding * 2
    panel_h = panel_padding + len(rows) * row_height + (len(rows) - 1) * row_gap + panel_padding
    panel_x = w - panel_w - 40  # 40px right margin
    panel_y = (h - panel_h) // 2  # vertically centered

    rows_svg = ""
    for i, (label, desc, icon_name, color_key) in enumerate(rows):
        ry = panel_padding + i * (row_height + row_gap)
        c = t[color_key]
        bg_key = color_key + "_bg"
        cbg = t.get(bg_key, t['accent_bg'])
        rows_svg += f"""
      <g transform="translate({panel_padding}, {ry})">
        <rect width="{panel_inner_w}" height="{row_height}" rx="12" fill="{t['card_bg']}" stroke="{t['card_border']}" />
        <rect x="10" y="11" width="28" height="28" rx="8" fill="{cbg}" />
        <g transform="translate(14, 15)">{get_icon(icon_name, color=c, size=20)}</g>
        <text x="48" y="22" class="font-sans fw-bold text-primary" font-size="13">{esc(label)}</text>
        <text x="48" y="38" class="font-sans fw-medium text-muted" font-size="11">{esc(desc)}</text>
      </g>"""

    logo_uri = f"data:image/png;base64,{LOGO_B64}"

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {w} {h}" width="100%" height="100%">
{common_defs_template.format(**t, height=h)}
  
  <!-- Subtle Glows -->
  <circle cx="200" cy="180" r="220" fill="url(#glow-grad)" class="animate-pulse" />
  <circle cx="660" cy="260" r="220" fill="url(#glow-grad)" class="animate-pulse" style="animation-delay: 2s;" />

  <!-- === LEFT COLUMN: Branding === -->
  <g transform="translate(48, 56)">
    <!-- Logo + Eyebrow row -->
    <image href="{logo_uri}" x="0" y="0" width="56" height="56" />
    <text x="66" y="30" class="font-sans fw-bold tracking-wide text-accent" font-size="12">{eyebrow}</text>
    <text x="66" y="48" class="font-sans fw-medium text-muted" font-size="11">Your Personal AI Framework</text>

    <!-- Title -->
    <text y="120" class="font-sans fw-bold tracking-tight text-primary" font-size="78">{title}</text>

    <!-- Subtitle -->
    <text y="160" class="font-sans fw-bold tracking-tight text-secondary" font-size="20">{sub1}</text>
    <text y="192" class="font-sans fw-medium text-muted" font-size="14">{sub2}</text>
    <text y="214" class="font-sans fw-medium text-muted" font-size="14">{sub3}</text>

    <!-- Accent bar -->
    <rect y="240" width="60" height="4" rx="2" fill="{t['accent']}" />
    <rect y="240" x="68" width="30" height="4" rx="2" fill="{t['accent']}" opacity="0.4" />
  </g>

  <!-- Connection wire from left to right panel -->
  <path d="M 420 220 C 440 220, {panel_x - 20} 220, {panel_x} 220" fill="none" class="animate-flow" stroke="{t['line']}" stroke-width="2" />
  <circle cx="420" cy="220" r="4" fill="{t['accent']}" />

  <!-- === RIGHT COLUMN: Core Panel === -->
  <g transform="translate({panel_x}, {panel_y})" filter="url(#shadow-md)">
    <rect width="{panel_w}" height="{panel_h}" rx="20" fill="{t['panel_bg']}" stroke="{t['panel_border']}" stroke-width="1.5" />
    {rows_svg}
  </g>

</svg>"""
    return content


def render_features(t, lang, theme_name):
    w, h = 800, 480
    
    if lang == "zh":
        eyebrow = "核心引擎组合"
        title = "不只是聊天，而是一套完整的长效智能层"
        sub = "从底层的 LanceDB 持久记忆到顶层的多代理协作机制，保障核心生产力。"
        t1, s1 = "持久记忆系统", "LanceDB 向量检索 • 偏好分离 • 智能召回"
        t2, s2 = "经验学习引擎", "自动提取教训 • 策略复用 • 置信度校准"
        t3, s3 = "长任务引擎", "轨迹压缩 • 自动校验 • 不阻塞主对话"
        t4, s4 = "子代理并行", "后台分流并行 • 进度透明可追溯 • 无缝续接"
        t5, s5 = "原生编码代理", "支持 Codex / Claude Code • Schema自适配"
        t6, s6 = "桌面端自动化", "跨 9 大平台 • 截图/点击原生感知 • 工具流融合"
    else:
        eyebrow = "CORE CAPABILITIES"
        title = "Built for long-term use, not just chat"
        sub = "From LanceDB persistence at the bottom to multi-agent collaboration at the top."
        t1, s1 = "Persistent Memory", "LanceDB vector recall • Segmented preferences"
        t2, s2 = "Experience Engine", "Auto-extract lessons • Strategy reuse • Confidence scoring"
        t3, s3 = "Long-Run Engine", "Trajectory compression • Auto checkpoints • Non-blocking"
        t4, s4 = "Parallel Subagents", "Background execution • Visible progress • Resumable"
        t5, s5 = "Native Coding Agent", "Codex / Claude Code ready • Auto schema routing"
        t6, s6 = "Desktop Automation", "Across 9 platforms • Screen/click native • Tool fusion"

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">
{common_defs_template.format(**t, height=h)}
  
  <circle cx="150" cy="150" r="200" fill="url(#glow-grad)" class="animate-pulse" />
  <circle cx="650" cy="400" r="200" fill="url(#glow-grad)" class="animate-pulse" style="animation-delay: 1s;" />

  <!-- Header -->
  <g transform="translate(50, 60)">
    <text y="0" class="font-sans fw-bold tracking-wide text-accent" font-size="12">{eyebrow}</text>
    <text y="36" class="font-sans fw-bold tracking-tight text-primary" font-size="28">{title}</text>
    <text y="64" class="font-sans fw-medium text-secondary" font-size="15">{sub}</text>
  </g>

  <!-- Feature Grid -->
  <g transform="translate(50, 160)">
    
    <!-- Row 1 -->
    <g transform="translate(0, 0)">
      <g filter="url(#shadow-sm)">
        <rect width="220" height="120" rx="16" fill="{t['panel_bg']}" stroke="{t['panel_border']}" />
        <rect x="20" y="20" width="36" height="36" rx="8" fill="{t['accent_bg']}" />
        <g transform="translate(26, 26)">
          {get_icon('database', color=t['accent'], size=24)}
        </g>
        <text x="20" y="80" class="font-sans fw-bold text-primary" font-size="15">{t1}</text>
        <text x="20" y="100" class="font-sans fw-medium text-muted" font-size="12">
          <tspan x="20" dy="0">{s1.split('•')[0].strip()}</tspan>
          <tspan x="20" dy="16">{' • '.join(s1.split('•')[1:]).strip() if len(s1.split('•')) > 1 else ''}</tspan>
        </text>
      </g>
    </g>

    <g transform="translate(240, 0)">
      <g filter="url(#shadow-sm)" class="animate-float">
        <rect width="220" height="120" rx="16" fill="{t['panel_bg']}" stroke="{t['panel_border']}" />
        <rect x="20" y="20" width="36" height="36" rx="8" fill="{t['mint_bg']}" />
        <g transform="translate(26, 26)">
          {get_icon('brain', color=t['mint'], size=24)}
        </g>
        <text x="20" y="80" class="font-sans fw-bold text-primary" font-size="15">{t2}</text>
        <text x="20" y="100" class="font-sans fw-medium text-muted" font-size="12">
          <tspan x="20" dy="0">{s2.split('•')[0].strip()}</tspan>
          <tspan x="20" dy="16">{' • '.join(s2.split('•')[1:]).strip() if len(s2.split('•')) > 1 else ''}</tspan>
        </text>
      </g>
    </g>

    <g transform="translate(480, 0)">
      <g filter="url(#shadow-sm)">
        <rect width="220" height="120" rx="16" fill="{t['panel_bg']}" stroke="{t['panel_border']}" />
        <rect x="20" y="20" width="36" height="36" rx="8" fill="{t['sky_bg']}" />
        <g transform="translate(26, 26)">
          {get_icon('timer', color=t['sky'], size=24)}
        </g>
        <text x="20" y="80" class="font-sans fw-bold text-primary" font-size="15">{t3}</text>
        <text x="20" y="100" class="font-sans fw-medium text-muted" font-size="12">
          <tspan x="20" dy="0">{s3.split('•')[0].strip()}</tspan>
          <tspan x="20" dy="16">{' • '.join(s3.split('•')[1:]).strip() if len(s3.split('•')) > 1 else ''}</tspan>
        </text>
      </g>
    </g>

    <!-- Row 2 -->
    <g transform="translate(0, 140)">
      <g filter="url(#shadow-sm)" class="animate-float-delayed">
        <rect width="220" height="120" rx="16" fill="{t['panel_bg']}" stroke="{t['panel_border']}" />
        <rect x="20" y="20" width="36" height="36" rx="8" fill="{t['violet_bg']}" />
        <g transform="translate(26, 26)">
          {get_icon('git-branch', color=t['violet'], size=24)}
        </g>
        <text x="20" y="80" class="font-sans fw-bold text-primary" font-size="15">{t4}</text>
        <text x="20" y="100" class="font-sans fw-medium text-muted" font-size="12">
          <tspan x="20" dy="0">{s4.split('•')[0].strip()}</tspan>
          <tspan x="20" dy="16">{' • '.join(s4.split('•')[1:]).strip() if len(s4.split('•')) > 1 else ''}</tspan>
        </text>
      </g>
    </g>

    <g transform="translate(240, 140)">
      <g filter="url(#shadow-sm)">
        <rect width="220" height="120" rx="16" fill="{t['panel_bg']}" stroke="{t['panel_border']}" />
        <rect x="20" y="20" width="36" height="36" rx="8" fill="{t['rose_bg']}" />
        <g transform="translate(26, 26)">
          {get_icon('terminal', color=t['rose'], size=24)}
        </g>
        <text x="20" y="80" class="font-sans fw-bold text-primary" font-size="15">{t5}</text>
        <text x="20" y="100" class="font-sans fw-medium text-muted" font-size="12">
          <tspan x="20" dy="0">{s5.split('•')[0].strip()}</tspan>
          <tspan x="20" dy="16">{' • '.join(s5.split('•')[1:]).strip() if len(s5.split('•')) > 1 else ''}</tspan>
        </text>
      </g>
    </g>

    <g transform="translate(480, 140)">
      <g filter="url(#shadow-sm)">
        <rect width="220" height="120" rx="16" fill="{t['panel_bg']}" stroke="{t['panel_border']}" />
        <rect x="20" y="20" width="36" height="36" rx="8" fill="{t['accent_bg']}" />
        <g transform="translate(26, 26)">
          {get_icon('monitor', color=t['accent'], size=24)}
        </g>
        <text x="20" y="80" class="font-sans fw-bold text-primary" font-size="15">{t6}</text>
        <text x="20" y="100" class="font-sans fw-medium text-muted" font-size="12">
          <tspan x="20" dy="0">{s6.split('•')[0].strip()}</tspan>
          <tspan x="20" dy="16">{' • '.join(s6.split('•')[1:]).strip() if len(s6.split('•')) > 1 else ''}</tspan>
        </text>
      </g>
    </g>
  </g>
</svg>"""
    return content

def render_arch(t, lang, theme_name):
    w, h = 800, 520
    
    if lang == "zh":
        eyebrow = "ARCHITECTURE"
        title = "底层数据流与模块协作架构"
        sub = "高内聚、低耦合，从交互输入到记忆更新的生命周期一致性管理。"
        i1, d1 = "用户界面请求", "桌面应用、系统指令快捷抓取"
        i2, d2 = "第三方渠道分流", "9大主流平台消息接驳与格式化"
        c1, c2, c3, c4, c5 = "核心运行时 AgentLoop", "长期记忆 (LanceDB)", "闭环经验反馈引擎", "任务编排/轨迹压缩", "子代理调度层"
        o1, o2 = "MCP 协议生态", "桌面端自动化执行"
    else:
        eyebrow = "ARCHITECTURE"
        title = "Information Flow and Module Collaboration"
        sub = "Highly cohesive yet decoupled lifecycle management from input to memory updates."
        i1, d1 = "User Interfaces", "Desktop app, system hooks"
        i2, d2 = "3rd Party Channels", "9 mainstream platforms formatting"
        c1, c2, c3, c4, c5 = "Core Runtime AgentLoop", "LanceDB Persistence", "Experience Engine", "Task & Trajectory", "Subagent Scheduler"
        o1, o2 = "MCP Ecosystem", "Desktop GUI Automation"

    content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" height="100%">
{common_defs_template.format(**t, height=h)}
  
  <g transform="translate(60, 50)">
    <text y="0" class="font-sans fw-bold tracking-wide text-accent" font-size="12">{esc(eyebrow)}</text>
    <text y="32" class="font-sans fw-bold tracking-tight text-primary" font-size="24">{esc(title)}</text>
    <text y="56" class="font-sans fw-medium text-secondary" font-size="14">{esc(sub)}</text>
  </g>

  <!-- Left: Inputs -->
  <g transform="translate(50, 150)">
    <rect width="200" height="80" rx="12" fill="{t['panel_bg']}" stroke="{t['panel_border']}" filter="url(#shadow-sm)" />
    <rect x="0" y="24" width="4" height="32" rx="2" fill="{t['sky']}" />
    <g transform="translate(16, 28)">
        {get_icon('users', color=t['sky'], size=24)}
    </g>
    <text x="50" y="44" class="font-sans fw-bold text-primary" font-size="14">{esc(i1)}</text>
    <text x="20" y="68" class="font-sans fw-medium text-muted" font-size="11">{esc(d1)}</text>
    <path d="M200 40 L 260 40" stroke="{t['line']}" stroke-width="2" class="animate-flow" />
    <circle cx="260" cy="40" r="4" fill="{t['accent']}" />
  </g>
  <g transform="translate(50, 260)">
    <rect width="200" height="80" rx="12" fill="{t['panel_bg']}" stroke="{t['panel_border']}" filter="url(#shadow-sm)" />
    <rect x="0" y="24" width="4" height="32" rx="2" fill="{t['violet']}" />
    <g transform="translate(16, 28)">
        {get_icon('message-square', color=t['violet'], size=24)}
    </g>
    <text x="50" y="44" class="font-sans fw-bold text-primary" font-size="14">{esc(i2)}</text>
    <text x="20" y="68" class="font-sans fw-medium text-muted" font-size="11">{esc(d2)}</text>
    <path d="M200 40 L 260 40" stroke="{t['line']}" stroke-width="2" class="animate-flow" />
    <circle cx="260" cy="40" r="4" fill="{t['accent']}" />
  </g>

  <!-- Center: Core -->
  <g transform="translate(280, 130)" filter="url(#shadow-md)">
    <rect width="250" height="280" rx="20" fill="{t['panel_bg']}" stroke="{t['panel_border']}" stroke-width="2" />
    <g transform="translate(112, 12)">{get_icon('cpu', color=t['primary'] if 'primary' in t else t['text_primary'], size=26)}</g>
    <text x="125" y="58" class="font-sans fw-bold text-primary" font-size="15" text-anchor="middle">{esc(c1)}</text>
    
    <g transform="translate(25, 76)">
      <rect width="200" height="40" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" />
      <g transform="translate(12, 10)">
        {get_icon('database', color=t['accent'], size=20)}
      </g>
      <text x="44" y="25" class="font-sans fw-semibold text-secondary" font-size="13">{esc(c2)}</text>
    </g>
    <g transform="translate(25, 126)">
      <rect width="200" height="40" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" />
      <g transform="translate(12, 10)">
        {get_icon('brain', color=t['mint'], size=20)}
      </g>
      <text x="44" y="25" class="font-sans fw-semibold text-secondary" font-size="13">{esc(c3)}</text>
    </g>
    <g transform="translate(25, 176)">
      <rect width="200" height="40" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" />
      <g transform="translate(12, 10)">
        {get_icon('timer', color=t['rose'], size=20)}
      </g>
      <text x="44" y="25" class="font-sans fw-semibold text-secondary" font-size="13">{esc(c4)}</text>
    </g>
    <g transform="translate(25, 226)">
      <rect width="200" height="40" rx="8" fill="{t['card_bg']}" stroke="{t['card_border']}" />
      <g transform="translate(12, 10)">
        {get_icon('git-branch', color=t['sky'], size=20)}
      </g>
      <text x="44" y="25" class="font-sans fw-semibold text-secondary" font-size="13">{esc(c5)}</text>
    </g>
  </g>

  <!-- Right: Outputs -->
  <g transform="translate(560, 150)">
    <path d="M -30 40 L 0 40" stroke="{t['line']}" stroke-width="2" class="animate-flow" />
    <circle cx="-30" cy="40" r="4" fill="{t['accent']}" />
    <rect width="180" height="80" rx="12" fill="{t['panel_bg']}" stroke="{t['panel_border']}" filter="url(#shadow-sm)" />
    <rect x="176" y="24" width="4" height="32" rx="2" fill="{t['rose']}" />
    <g transform="translate(16, 28)">
        {get_icon('box', color=t['rose'], size=24)}
    </g>
    <text x="50" y="44" class="font-sans fw-bold text-primary" font-size="14">{esc(o1)}</text>
    <text x="20" y="68" class="font-sans fw-medium text-muted" font-size="11">Tools, Files, Cloud</text>
  </g>
  <g transform="translate(560, 260)">
    <path d="M -30 40 L 0 40" stroke="{t['line']}" stroke-width="2" class="animate-flow" />
    <circle cx="-30" cy="40" r="4" fill="{t['accent']}" />
    <rect width="180" height="80" rx="12" fill="{t['panel_bg']}" stroke="{t['panel_border']}" filter="url(#shadow-sm)" />
    <rect x="176" y="24" width="4" height="32" rx="2" fill="{t['accent']}" />
    <g transform="translate(16, 28)">
        {get_icon('monitor', color=t['accent'], size=24)}
    </g>
    <text x="50" y="44" class="font-sans fw-bold text-primary" font-size="14">{esc(o2)}</text>
    <text x="20" y="68" class="font-sans fw-medium text-muted" font-size="11">Screen &amp; Controls</text>
  </g>
  
  <rect x="50" y="450" width="700" height="40" rx="8" fill="{t['accent_bg']}" />
  <text x="400" y="475" class="font-sans fw-semibold text-accent_muted" font-size="13" text-anchor="middle">Fully type-safe execution and strictly bounded contexts.</text>
</svg>"""
    return content


def save():
    out_dir = "/Users/sugeh/Documents/Project/Bao/assets"
    
    for theme_name, t in themes.items():
        # Hero ZH
        with open(f"{out_dir}/hero-{theme_name}.svg", "w") as f:
            f.write(render_hero(t, "zh", theme_name))
        # Hero EN
        with open(f"{out_dir}/hero-en-{theme_name}.svg", "w") as f:
            f.write(render_hero(t, "en", theme_name))
            
        # Features ZH
        with open(f"{out_dir}/features-{theme_name}.svg", "w") as f:
            f.write(render_features(t, "zh", theme_name))
        # Features EN
        with open(f"{out_dir}/features-en-{theme_name}.svg", "w") as f:
            f.write(render_features(t, "en", theme_name))
            
        # Architecture ZH
        with open(f"{out_dir}/architecture-{theme_name}.svg", "w") as f:
            f.write(render_arch(t, "zh", theme_name))
        # Architecture EN
        with open(f"{out_dir}/architecture-en-{theme_name}.svg", "w") as f:
            f.write(render_arch(t, "en", theme_name))

if __name__ == "__main__":
    save()
