import QtQuick 2.15
import QtQuick.Controls 2.15

import QtQuick.Layouts 1.15

ApplicationWindow {
    id: root
    visible: true

    // Window sizing
    readonly property int defaultWindowWidth: 1100
    readonly property int defaultWindowHeight: 720
    readonly property int minimumWindowWidth: 640
    readonly property int minimumWindowHeight: 600

    width: defaultWindowWidth
    height: defaultWindowHeight
    minimumWidth: minimumWindowWidth
    minimumHeight: minimumWindowHeight
    title: ""
    property bool useNativeTitleBar: true
    readonly property bool useMacTransparentTitleBar: useNativeTitleBar && Qt.platform.os === "osx"
    flags: useNativeTitleBar
           ? (Qt.Window
              | (useMacTransparentTitleBar ? Qt.NoTitleBarBackgroundHint : 0)
              | (useMacTransparentTitleBar ? Qt.ExpandedClientAreaHint : 0))
           : (Qt.Window | Qt.FramelessWindowHint)

    // Frameless mode uses transparent outer window; native mode uses normal background.
    color: useNativeTitleBar ? root.bgBase : "transparent"

    property string startView: "chat"
    readonly property bool hasDesktopPreferences: typeof desktopPreferences !== "undefined" && desktopPreferences !== null
    readonly property bool hasConfigService: typeof configService !== "undefined" && configService !== null
    readonly property bool hasSessionService: typeof sessionService !== "undefined" && sessionService !== null
    readonly property bool hasChatService: typeof chatService !== "undefined" && chatService !== null
    readonly property bool hasDiagnosticsService: typeof diagnosticsService !== "undefined" && diagnosticsService !== null
    readonly property bool isDark: hasDesktopPreferences ? desktopPreferences.isDark : true

    readonly property string uiLanguage: hasDesktopPreferences ? desktopPreferences.uiLanguage : "auto"
    readonly property string autoLanguage: {
        if (typeof systemUiLanguage === "string") {
            var sys = systemUiLanguage.toLowerCase()
            if (sys.startsWith("zh")) return "zh"
            if (sys.startsWith("en")) return "en"
        }
        return String(Qt.locale().name || "").toLowerCase().startsWith("zh") ? "zh" : "en"
    }

    readonly property var stringsZh: ({
        "sidebar_sessions": "会话",
        "sidebar_empty_title": "开始一个新对话",
        "sidebar_empty_hint": "点击即可新建会话",
        "sidebar_empty_cta": "新建对话",
        "sidebar_loading_title": "正在加载会话",
        "sidebar_loading_hint": "稍等一下，历史会话马上出现",
        "chat_empty_title": "开始对话",
        "chat_empty_hint": "在下面输入消息",
        "chat_gateway": "网关",
        "gateway_starting": "启动中…",
        "gateway_running": "运行中",
        "gateway_error": "错误",
        "gateway_channels_idle": "将启动的渠道",
        "gateway_channels_running": "活跃渠道",
        "gateway_channels_error": "异常渠道",
        "button_start_gateway": "启动",
        "chat_placeholder": "给 Bao 发消息…",
        "chat_loading_history": "加载会话中…",
        "section_app": "应用",
        "section_updates": "桌面更新",
        "section_agent_defaults": "回复方式与模型",
        "section_provider": "LLM 提供商",
        "section_channels": "渠道",
        "section_tools": "工具",
        "section_gateway": "网关",
        "section_provider_add": "添加 LLM 提供商",
        "section_provider_remove": "删除",
        "ui_language": "界面语言",
        "ui_language_auto": "自动（跟随系统）",
        "ui_language_zh": "中文",
        "ui_language_en": "English",
        "ui_theme": "界面主题",
        "ui_theme_system": "自动（跟随系统）",
        "ui_theme_light": "浅色",
        "ui_theme_dark": "深色",
        "update_auto_check": "自动更新",
        "update_status_up_to_date": "当前已是最新版本",
        "update_status_error": "更新失败",
        "update_action_check": "检查",
        "update_action_checking": "检查中",
        "update_action_install": "立即更新",
        "update_current_version": "当前版本",
        "update_latest_version": "最新版本",
        "update_modal_title": "发现新版本",
        "update_modal_later": "稍后",
        "update_modal_install": "更新",
        "settings_save": "保存",
        "settings_saved_hint": "已保存 — 重启网关以应用",
        "settings_save_failed": "保存失败",
        "empty_setup_title": "欢迎使用 Bao",
        "empty_setup_hint": "请先在设置中配置 Provider 和模型（点击左下角 logo 进入设置）",
        "empty_starting_hint": "正在连接…",
        "empty_error_hint": "网关启动失败",
        "empty_error_btn": "重试",
        "empty_chat_title": "准备就绪",
        "empty_chat_hint": "在下方输入消息开始对话",
        "empty_chat_idle_hint": "启动网关后即可在这里继续对话",
        "empty_idle_title": "网关未启动",
        "empty_idle_hint": "点击左侧网关胶囊启动网关",
        "session_delete_ok": "会话已删除",
        "session_delete_fail": "删除失败",
        "channel_desktop": "桌面",
        "channel_subagent": "子代理",
        "channel_system": "系统",
        "channel_heartbeat": "心跳",
        "channel_cron": "定时任务",
        "channel_telegram": "Telegram",
        "channel_discord": "Discord",
        "channel_whatsapp": "WhatsApp",
        "channel_feishu": "飞书",
        "channel_slack": "Slack",
        "channel_email": "邮件",
        "channel_qq": "QQ",
        "channel_dingtalk": "钉钉",
        "channel_imessage": "iMessage",
        "channel_other": "其他",
        "bubble_0": "有什么需要帮忙的吗？",
        "bubble_1": "今天也要加油鸭 ᐢ.ˬ.ᐢ",
        "bubble_2": "点我进入设置~",
        "bubble_3": "嘿！你好呀 (◕ᴗ◕)",
        "bubble_4": "我在这里等你哦~",
        "sidebar_diagnostics": "日志",
        "sidebar_diagnostics_hint": "诊断",
        "copied_ok": "已复制",
        "child_session_read_only": "子代理线程为只读视图，请回到主对话继续追加提示。",
        "child_session_from_parent": "来源主会话",
        "child_session_running": "运行中",
        "child_session_failed": "失败",
        "child_session_completed": "已完成",
        "child_session_cancelled": "已取消",
        "parent_active_children": "当前子代理",
        "parent_linked_children": "已链接子代理",
        "parent_open_child_session": "打开子线程",
        "diagnostics_title": "运行诊断与日志",
        "diagnostics_close": "关闭",
        "diagnostics_empty_events": "当前没有结构化诊断事件。",
        "diagnostics_empty_logs": "当前还没有日志输出。",
        "diagnostics_recent_events": "最近诊断",
        "diagnostics_log_tail": "日志尾部",
        "diagnostics_log_file": "日志文件",
        "diagnostics_refresh": "刷新",
        "diagnostics_open_folder": "打开目录",
        "diagnostics_copy_tail": "复制尾部",
        "diagnostics_ask_bao": "发给 Bao",
        "diagnostics_sent": "诊断已发送",
        "diagnostics_gateway_title": "网关状态",
        "diagnostics_gateway_idle": "还没启动",
        "diagnostics_gateway_starting": "正在启动",
        "diagnostics_gateway_running": "运行正常",
        "diagnostics_gateway_error": "启动异常",
        "diagnostics_metrics_title": "运行观测",
    })

    readonly property var stringsEn: ({
        "sidebar_sessions": "Sessions",
        "sidebar_empty_title": "Start a new chat",
        "sidebar_empty_hint": "Click to create one",
        "sidebar_empty_cta": "New chat",
        "sidebar_loading_title": "Loading sessions",
        "sidebar_loading_hint": "Your recent conversations will appear in a moment",
        "chat_empty_title": "Start a conversation",
        "chat_empty_hint": "Type a message below",
        "chat_gateway": "Gateway",
        "gateway_starting": "Starting\u2026",
        "gateway_running": "Running",
        "gateway_error": "Error",
        "gateway_channels_idle": "Channels to start",
        "gateway_channels_running": "Active channels",
        "gateway_channels_error": "Channel issues",
        "button_start_gateway": "Start",
        "chat_placeholder": "Message Bao\u2026",
        "chat_loading_history": "Loading session\u2026",
        "section_app": "App",
        "section_updates": "Desktop Updates",
        "section_agent_defaults": "Response Setup",
        "section_provider": "LLM Provider",
        "section_channels": "Channels",
        "section_tools": "Tools",
        "section_gateway": "Gateway",
        "section_provider_add": "Add LLM Provider",
        "section_provider_remove": "Remove",
        "ui_language": "UI Language",
        "ui_language_auto": "Auto (System)",
        "ui_language_zh": "Chinese",
        "ui_language_en": "English",
        "ui_theme": "Theme",
        "ui_theme_system": "Auto (System)",
        "ui_theme_light": "Light",
        "ui_theme_dark": "Dark",
        "update_auto_check": "Auto Update",
        "update_status_up_to_date": "You're on the latest version",
        "update_status_error": "Update failed",
        "update_action_check": "Check",
        "update_action_checking": "Checking",
        "update_action_install": "Install Now",
        "update_current_version": "Current",
        "update_latest_version": "Latest",
        "update_modal_title": "Update Available",
        "update_modal_later": "Later",
        "update_modal_install": "Install",
        "settings_save": "Save",
        "settings_saved_hint": "Saved \u2014 restart gateway to apply",
        "settings_save_failed": "Save failed",
        "empty_setup_title": "Welcome to Bao",
        "empty_setup_hint": "Configure a Provider and Model in Settings first (click the logo in the bottom-left to open settings)",
        "empty_starting_hint": "Connecting\u2026",
        "empty_error_hint": "Gateway failed to start",
        "empty_error_btn": "Retry",
        "empty_chat_title": "Ready to go",
        "empty_chat_hint": "Type a message below to start chatting",
        "empty_chat_idle_hint": "Start the gateway to continue chatting here",
        "empty_idle_title": "Gateway not started",
        "empty_idle_hint": "Click the gateway capsule in the sidebar to start",
        "session_delete_ok": "Session deleted",
        "session_delete_fail": "Delete failed",
        "channel_desktop": "Desktop",
        "channel_subagent": "Subagent",
        "channel_system": "System",
        "channel_heartbeat": "Heartbeat",
        "channel_cron": "Cron",
        "channel_telegram": "Telegram",
        "channel_discord": "Discord",
        "channel_whatsapp": "WhatsApp",
        "channel_feishu": "Feishu",
        "channel_slack": "Slack",
        "channel_email": "Email",
        "channel_qq": "QQ",
        "channel_dingtalk": "DingTalk",
        "channel_imessage": "iMessage",
        "channel_other": "Other",
        "bubble_0": "Need any help?",
        "bubble_1": "Let's get things done!",
        "bubble_2": "Click me for settings~",
        "bubble_3": "Hey there! (◕ᴗ◕)",
        "bubble_4": "I'm here for you~",
        "sidebar_diagnostics": "Logs",
        "sidebar_diagnostics_hint": "Inspect",
        "copied_ok": "Copied",
        "child_session_read_only": "This subagent thread is read-only. Continue from the parent conversation.",
        "child_session_from_parent": "Spawned from",
        "child_session_running": "Running",
        "child_session_failed": "Failed",
        "child_session_completed": "Completed",
        "child_session_cancelled": "Cancelled",
        "parent_active_children": "Active subagents",
        "parent_linked_children": "Linked subagents",
        "parent_open_child_session": "Open child thread",
        "diagnostics_title": "Runtime Diagnostics & Logs",
        "diagnostics_close": "Close",
        "diagnostics_empty_events": "No structured runtime diagnostics yet.",
        "diagnostics_empty_logs": "No log output has been captured yet.",
        "diagnostics_recent_events": "Recent diagnostics",
        "diagnostics_log_tail": "Log tail",
        "diagnostics_log_file": "Log file",
        "diagnostics_refresh": "Refresh",
        "diagnostics_open_folder": "Open Folder",
        "diagnostics_copy_tail": "Copy Tail",
        "diagnostics_ask_bao": "Ask Bao",
        "diagnostics_sent": "Diagnostics sent",
        "diagnostics_gateway_title": "Gateway State",
        "diagnostics_gateway_idle": "Not started",
        "diagnostics_gateway_starting": "Starting",
        "diagnostics_gateway_running": "Running normally",
        "diagnostics_gateway_error": "Startup issue",
    })

    readonly property var strings: {
        if (uiLanguage === "zh")
            return stringsZh
        if (uiLanguage === "en")
            return stringsEn
        return autoLanguage === "zh" ? stringsZh : stringsEn
    }

    function copyPlainText(text) {
        diagnosticsClipHelper.text = text || ""
        diagnosticsClipHelper.selectAll()
        diagnosticsClipHelper.copy()
        diagnosticsClipHelper.deselect()
    }

    function themedIconSource(name, darkSuffix) {
        var resolvedDarkSuffix = typeof darkSuffix === "string" ? darkSuffix : ""
        return "../resources/icons/" + name + (isDark ? resolvedDarkSuffix : "-light") + ".svg"
    }

    function diagnosticsGatewayState() {
        if (!chatService || typeof chatService.state !== "string" || !chatService.state)
            return "idle"
        if (chatService.state === "running")
            return "running"
        if (chatService.state === "starting")
            return "starting"
        if (chatService.state === "error")
            return "error"
        return "idle"
    }

    function diagnosticsGatewayLabel() {
        var state = diagnosticsGatewayState()
        if (state === "running")
            return strings.diagnostics_gateway_running
        if (state === "starting")
            return strings.diagnostics_gateway_starting
        if (state === "error")
            return strings.diagnostics_gateway_error
        return strings.diagnostics_gateway_idle
    }

    function diagnosticsGatewayIcon() {
        var state = diagnosticsGatewayState()
        if (state === "running")
            return "../resources/icons/gateway-running.svg"
        if (state === "starting")
            return "../resources/icons/gateway-starting.svg"
        if (state === "error")
            return "../resources/icons/gateway-error.svg"
        return "../resources/icons/gateway-idle.svg"
    }

    function diagnosticsGatewayBadgeColor() {
        var state = diagnosticsGatewayState()
        if (state === "running")
            return isDark ? "#1F8A5B" : "#16A34A"
        if (state === "starting")
            return isDark ? "#A45E15" : "#EA8A12"
        if (state === "error")
            return isDark ? "#B14C43" : "#DC5B4F"
        return isDark ? "#725542" : "#C68642"
    }

    function diagnosticsObservabilityItemsSafe() {
        if (!diagnosticsService || !diagnosticsService.observabilityItems)
            return []
        return diagnosticsService.observabilityItems
    }

    function diagnosticsEventsSafe() {
        if (!diagnosticsService || !diagnosticsService.events)
            return []
        return diagnosticsService.events
    }

    function diagnosticsEventCountSafe() {
        if (!diagnosticsService || typeof diagnosticsService.eventCount !== "number")
            return 0
        return diagnosticsService.eventCount
    }

    function diagnosticsLogFilePathSafe() {
        if (!diagnosticsService || typeof diagnosticsService.logFilePath !== "string")
            return ""
        return diagnosticsService.logFilePath
    }

    function diagnosticsRecentLogTextSafe() {
        if (!diagnosticsService || typeof diagnosticsService.recentLogText !== "string")
            return ""
        return diagnosticsService.recentLogText
    }

    function diagnosticsSectionIcon(section) {
        var suffix = isDark ? "dark" : "light"
        if (section === "gateway")
            return "../resources/icons/diag-section-gateway-" + suffix + ".svg"
        if (section === "file")
            return "../resources/icons/diag-section-file-" + suffix + ".svg"
        if (section === "events")
            return "../resources/icons/diag-section-events-" + suffix + ".svg"
        return "../resources/icons/diag-section-logtail-" + suffix + ".svg"
    }

    function diagnosticsObservabilitySummary() {
        var items = diagnosticsObservabilityItemsSafe()
        if (!items.length)
            return ""
        return items.map(function(item) {
            return String(item.label || "") + " " + String(item.value || "")
        }).join("  ·  ")
    }

    // Resolved language for backend (never "auto")
    readonly property string effectiveLang: {
        if (uiLanguage === "zh" || uiLanguage === "en") return uiLanguage
        return autoLanguage
    }
    readonly property bool setupMode: hasConfigService
                                     ? (!configService.isValid || configService.needsSetup)
                                     : true
    property bool _previousSetupMode: true
    property int setupCompletionToken: 0
    readonly property int currentPageIndex: {
        if (setupMode)
            return 1
        if (startView === "settings")
            return 1
        return 0
    }
    onSetupModeChanged: {
        if (_previousSetupMode && !setupMode)
            setupCompletionToken += 1
        _previousSetupMode = setupMode
    }

    Connections {
        target: hasSessionService ? sessionService : null
        function onDeleteCompleted(_key, ok, error) {
            if (ok)
                globalToast.show(strings.session_delete_ok, true)
            else
                globalToast.show(strings.session_delete_fail + (error ? (": " + error) : ""), false)
        }
    }

    // ── Design Tokens ─────────────────────────────────────────────────
    // Surface colors
    readonly property color bgBase:          isDark ? "#130E0B" : "#FCF8F4"
    readonly property color bgSidebar:       isDark ? "#0F0B09" : "#F3ECE6"
    readonly property color bgCard:          isDark ? "#19120E" : "#FFFFFF"
    readonly property color bgCardHover:     isDark ? "#22170F" : "#FFF6EE"
    readonly property color bgInput:         isDark ? "#1A120D" : "#FFF4EA"
    readonly property color bgInputHover:    isDark ? "#23170F" : "#FFEEDF"
    readonly property color bgInputFocus:    isDark ? "#2A1B11" : "#FFFFFF"
    readonly property color bgElevated:      isDark ? "#24170F" : "#FFFFFF"

    // Text colors
    readonly property color textPrimary:     isDark ? "#F7EFE7" : "#261A12"
    readonly property color textSecondary:   isDark ? "#C5AF9E" : "#6B5649"
    readonly property color textTertiary:    isDark ? "#8B7668" : "#9D8473"
    readonly property color textPlaceholder: isDark ? "#705D51" : "#B89D8A"

    // Border colors
    // NOTE: QML 8-digit hex uses #AARRGGBB (NOT #RRGGBBAA like CSS).
    readonly property color borderSubtle:    isDark ? "#20FFA11A" : "#14000000"
    readonly property color borderDefault:   isDark ? "#40FFA11A" : "#24000000"
    readonly property color borderFocus:     "#FFAE38"

    // Accent
    readonly property color accent:          "#FFB33D"
    readonly property color accentHover:     "#FF971A"
    readonly property color accentMuted:     isDark ? "#54FFB33D" : "#34FFB33D"
    readonly property color accentGlow:      "#A8FFB33D"

    // Status
    readonly property color statusSuccess:   "#22C55E"
    readonly property color statusWarning:   "#F59E0B"
    readonly property color statusError:     "#F05A5A"
    readonly property color textSelectionBg: isDark ? "#92FFB33D" : "#70FFB33D"
    readonly property color textSelectionFg: "#1E140E"

    // Spacing
    readonly property int spacingXs: 4
    readonly property int spacingSm: 8
    readonly property int spacingMd: 12
    readonly property int spacingLg: 16
    readonly property int spacingXl: 24
    readonly property int spacingXxl: 32

    // Radius
    readonly property int radiusSm: 8
    readonly property int radiusMd: 12
    readonly property int radiusLg: 16

    // Typography
    readonly property int typeDisplay: 30
    readonly property int typeTitle: 22
    readonly property int typeBody: 15
    readonly property int typeButton: 14
    readonly property int typeLabel: 13
    readonly property int typeMeta: 12
    readonly property int typeCaption: 11
    readonly property real lineHeightBody: 1.4
    readonly property real letterTight: 0.2
    readonly property real letterWide: 0.5
    readonly property int weightRegular: Font.Normal
    readonly property int weightMedium: Font.Medium
    readonly property int weightDemiBold: Font.DemiBold
    readonly property int weightBold: Font.Bold

    // Motion
    readonly property int motionMicro: 120
    readonly property int motionFast: 180
    readonly property int motionUi: 220
    readonly property int motionPanel: 320
    readonly property int motionAmbient: 500
    readonly property int motionBreath: 1100
    readonly property int motionFloat: 1700
    readonly property int motionStagger: 80
    readonly property int motionStatusPulse: 600
    readonly property int motionTrackVelocity: 220
    readonly property int toastDuration: 2200
    readonly property int toastDurationLong: 2600
    readonly property int easeStandard: Easing.OutCubic
    readonly property int easeEmphasis: Easing.OutBack
    readonly property int easeSoft: Easing.InOutSine
    readonly property int easeLinear: Easing.Linear
    readonly property real motionStatusMinOpacityStarting: 0.78
    readonly property real motionStatusMinOpacityError: 0.74
    readonly property real motionGlowPeakOpacity: 0.8
    readonly property real motionDotPulseMinOpacity: 0.3
    readonly property real motionDotPulseScaleMax: 1.4
    readonly property real motionRingIdlePeakOpacity: 0.35
    readonly property real motionRingHoverOpacity: 0.6
    readonly property real motionFloatOffset: 2.5
    readonly property real motionPressScaleStrong: 0.88
    readonly property real motionHoverScaleStrong: 1.15
    readonly property real motionHoverScaleMedium: 1.08
    readonly property real motionHoverScaleSubtle: 1.04
    readonly property real motionBubbleHiddenScale: 0.8
    readonly property real motionToastHiddenScale: 0.92
    readonly property real motionDeleteHiddenScale: 0.92
    readonly property real motionCopyFlashPeak: 0.42
    readonly property real motionAuraNearPeak: 0.34
    readonly property real motionAuraFarPeak: 0.2
    readonly property real motionGreetingSweepPeak: 0.26
    readonly property real motionTypingPulseMinOpacity: 0.28
    readonly property int motionEnterOffsetY: 10
    readonly property int motionPageShift: 18
    readonly property int motionPageShiftSubtle: 10
    readonly property real motionPageRevealStartScale: 0.986
    readonly property real motionPageRevealStartOpacity: 0.84
    readonly property real motionPageAuraPeak: 0.11
    readonly property real motionSelectionScaleActive: 1.018
    readonly property real motionSelectionScaleHover: 1.006
    readonly property real motionSelectionAuraOpacity: 0.12
    readonly property real motionSelectionAuraHiddenScale: 0.96
    readonly property real motionSelectionRailHiddenScale: 0.55
    readonly property real opacityShadowSoft: 0.3
    readonly property real opacityInteractionIdle: 0.65
    readonly property real opacityInteractionHover: 0.95
    readonly property real opacityInactive: 0.85
    readonly property real opacityDimmedActive: 0.9
    readonly property real opacityDimmedIdle: 0.6

    // Component size tokens
    readonly property int sizeControlHeight: 42
    readonly property int sizeControlHeightLg: 48
    readonly property int sizeButton: 40
    readonly property int sizeFieldPaddingX: 14
    readonly property int sizeOptionHeight: 34
    readonly property int sizeDropdownMaxHeight: 240
    readonly property int sizeSidebarHeader: 46
    readonly property int sizeSessionRow: 40
    readonly property int sizeSidebarGroupGap: 12
    readonly property int sizeSidebarHeaderToRowGap: 6
    readonly property int sizeSidebarGroupInnerGap: 4
    readonly property int sizeCapsuleHeight: 64
    readonly property int sizeBubbleRadius: 18
    readonly property int sizeSystemBubbleRadius: 11
    readonly property int sizeAppIcon: 46
    readonly property int sizeGatewayAction: 44
    readonly property int sizeGatewayActionIcon: 28
    readonly property int windowContentInsetTop: useMacTransparentTitleBar ? 72 : spacingLg
    readonly property int windowContentInsetSide: spacingLg
    readonly property int windowContentInsetBottom: spacingLg

    // Gateway emphasis tokens
    readonly property color gatewayTextRunning: isDark ? "#A8EAC3" : "#177C43"
    readonly property color gatewayTextStarting: isDark ? "#FFE2A2" : "#A85D00"
    readonly property color gatewayTextIdle: isDark ? "#FFD3A0" : "#A95A00"
    readonly property color gatewaySurfaceIdleTop: isDark ? "#FF6F3819" : "#FFF6D1A8"
    readonly property color gatewaySurfaceStartingTop: isDark ? "#FF8B5316" : "#FFF1BC60"
    readonly property color gatewaySurfaceRunningTop: isDark ? "#FF145B42" : "#FFC4ECD8"
    readonly property color gatewaySurfaceErrorTop: isDark ? "#FF6B2527" : "#FFF4C8C8"

    // Session emphasis tokens
    readonly property color sidebarListPanelBg: isDark ? "#120A08" : "#FBF2EA"
    readonly property color sidebarListPanelBorder: isDark ? "#14FFFFFF" : "#12000000"
    readonly property color sidebarListPanelOverlay: isDark ? "#06FFFFFF" : "#0AFFFFFF"
    readonly property color sidebarGroupBaseBg: isDark ? "#1A120F" : "#FFF8F1"
    readonly property color sidebarGroupBg: isDark ? "#1A120F" : "#FFF8F1"
    readonly property color sidebarGroupHoverBg: isDark ? "#221714" : "#FFF2E8"
    readonly property color sidebarGroupExpandedBg: isDark ? "#261A16" : "#FFF0E5"
    readonly property color sidebarGroupBorder: "#00000000"
    readonly property color sidebarGroupExpandedBorder: "#00000000"
    readonly property color sidebarGroupHighlight: "#00000000"
    readonly property color sidebarGroupChevronBg: isDark ? "#16FFFFFF" : "#14000000"
    readonly property color sidebarGroupChevronBorder: isDark ? "#18FFFFFF" : "#12000000"
    readonly property color sidebarGroupCountBg: isDark ? "#18FFFFFF" : "#14000000"
    readonly property color sidebarGroupCountText: isDark ? "#F3DCC8" : "#6B4C35"
    readonly property color sidebarScrollbarThumb: isDark ? "#20FFFFFF" : "#16000000"
    readonly property color sidebarHeaderBadgeBg: isDark ? "#26FFD7A8" : "#1CCB8740"
    readonly property color sidebarHeaderBadgeText: isDark ? "#FFF1DE" : "#6D431E"
    readonly property color sessionRowIdleBg: isDark ? "#150E0C" : "#FFF9F4"
    readonly property color sessionRowHoverBg: isDark ? "#1B1311" : "#FFF4EA"
    readonly property color sessionRowActiveBg: isDark ? "#3A2318" : "#FFD9BC"
    readonly property color sessionRowIdleBorder: "#00000000"
    readonly property color sessionRowHoverBorder: "#00000000"
    readonly property color sessionRowActiveBorder: "#00000000"
    readonly property color sessionDeleteHoverBg: isDark ? "#28F87171" : "#22F87171"
    readonly property color sessionDeleteIdleBg: isDark ? "#14FFFFFF" : "#10000000"
    readonly property color sessionDeleteHoverBorder: "#66F87171"
    readonly property color sessionDeleteIdleBorder: isDark ? "#2AFFFFFF" : "#23000000"
    readonly property color sessionDeleteIcon: isDark ? "#F87171" : "#DC2626"
    readonly property color sessionUnreadDot: isDark ? "#F87171" : "#DC2626"

    // Chat emphasis tokens
    readonly property color chatSystemAuraFar: isDark ? "#46FFA11A" : "#36FFA11A"
    readonly property color chatSystemAuraNear: isDark ? "#36FFA11A" : "#2AFFA11A"
    readonly property color chatSystemAuraErrorFar: "#2EF05A5A"
    readonly property color chatSystemAuraErrorNear: "#44F05A5A"
    readonly property color chatSystemBubbleBg: isDark ? "#28FFB33D" : "#16FFB33D"
    readonly property color chatSystemBubbleBorder: isDark ? "#58FFCB7A" : "#42D0892C"
    readonly property color chatSystemBubbleErrorBg: isDark ? "#20F05A5A" : "#14F05A5A"
    readonly property color chatSystemBubbleErrorBorder: isDark ? "#58F05A5A" : "#42F05A5A"
    readonly property color chatSystemBubbleOverlay: isDark ? "#22FFA11A" : "#18FFA11A"
    readonly property color chatSystemBubbleErrorOverlay: "#08F05A5A"
    readonly property color chatSystemText: isDark ? "#F6DEBA" : "#77471A"
    readonly property color chatGreetingAuraFar: isDark ? "#22FFD6A1" : "#0EE0BE93"
    readonly property color chatGreetingAuraNear: isDark ? "#34FFE7C2" : "#18E8C79F"
    readonly property color chatGreetingBubbleBgStart: isDark ? "#FF2B2118" : "#FFF7F3EC"
    readonly property color chatGreetingBubbleBgEnd: isDark ? "#FF201812" : "#FFF7F3EC"
    readonly property color chatGreetingBubbleBorder: isDark ? "#50FFD19A" : "#1F8F6A47"
    readonly property color chatGreetingBubbleOverlay: isDark ? "#10FFFFFF" : "#06FFFFFF"
    readonly property color chatGreetingBubbleHighlight: isDark ? "#88FFF5DF" : "#42FFFFFF"
    readonly property color chatGreetingSweep: isDark ? "#16FFFFFF" : "#10FFFFFF"
    readonly property color chatGreetingAccent: isDark ? "#F6C889" : "#A8641F"
    readonly property color chatGreetingText: isDark ? "#FFF6EA" : "#402715"
    readonly property string chatGreetingIconSource: themedIconSource("ignite", "-dark")
    readonly property color chatBubbleCopyFlashUser: "#40FFFFFF"
    readonly property color chatBubbleErrorTint: "#15F05A5A"
    readonly property color chatEmptyIconBg: isDark ? "#10FFFFFF" : "#1C9A6328"
    readonly property color chatEmptyIconBorder: isDark ? "transparent" : "#2E9A6328"
    readonly property color chatErrorBadgeBg: isDark ? "#18F87171" : "#10F87171"
    readonly property color chatComposerSendGlow: isDark ? "#2EFFB33D" : "#24FF971A"
    readonly property color chatComposerSendHighlight: isDark ? "#2CFFFFFF" : "#20FFFFFF"
    readonly property color chatComposerSendDisabled: isDark ? "#1A1A26" : "#E5E7EB"



    // Rounded "chrome". This is the only visible surface.
    Rectangle {
        id: chrome
        anchors.fill: parent
        radius: 20
        color: root.bgSidebar
        antialiasing: true
        opacity: 1.0

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

        // ── Title bar ────────────────────────────────────────────────
            Item {
                id: titleBar
                Layout.fillWidth: true
                visible: !root.useNativeTitleBar
                height: visible ? 48 : 0

                // Drag the frameless window by the title bar background.
                // Ignore the traffic-light area so the buttons remain clickable.
                MouseArea {
                    anchors.fill: parent
                    visible: !root.useNativeTitleBar
                    enabled: visible
                    acceptedButtons: Qt.LeftButton
                    hoverEnabled: true
                    cursorShape: Qt.ArrowCursor
                    onPressed: function(mouse) {
                        // Ignore traffic lights (left) and gateway controls (right)
                        if (mouse.x < 92 || mouse.x > parent.width - 120) {
                            mouse.accepted = false
                            return
                        }
                        root.startSystemMove()
                    }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 12
                    spacing: 0

                // Traffic lights
                Row {
                    visible: !root.useNativeTitleBar
                    spacing: 8
                    Repeater {
                        model: [
                            { color: "#FF5F57", hoverColor: "#FF3B30", action: "close" },
                            { color: "#FEBC2E", hoverColor: "#F5A623", action: "minimize" },
                            { color: "#28C840", hoverColor: "#1DB954", action: "maximize" }
                        ]
                        delegate: Rectangle {
                            width: 14
                            height: 14
                            radius: 7
                            color: tlHover.containsMouse ? modelData.hoverColor : modelData.color
                            opacity: tlHover.containsMouse ? 1.0 : opacityInactive
                            Behavior on color { ColorAnimation { duration: motionMicro; easing.type: easeStandard } }
                            Behavior on opacity { NumberAnimation { duration: motionMicro; easing.type: easeStandard } }

                            Text {
                                anchors.centerIn: parent
                                text: modelData.action === "close" ? "✕"
                                      : (modelData.action === "minimize" ? "−" : "+")
                                color: "#60000000"
                                font.pixelSize: 8
                                font.weight: Font.Bold
                                visible: tlHover.containsMouse
                            }

                            MouseArea {
                                id: tlHover
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (modelData.action === "close") {
                                        root.close()
                                    } else if (modelData.action === "minimize") {
                                        root.showMinimized()
                                    } else {
                                        root.showMaximized()
                                    }
                                }
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: "Bao"
                    color: root.textPrimary
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    font.letterSpacing: 0.5
                    opacity: 0.7
                }

            }
        }

        // ── Main content ─────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: root.bgBase
                radius: chrome.radius
                antialiasing: true

                // Square the top edge so it meets the title bar cleanly.
                Rectangle {
                    anchors { top: parent.top; left: parent.left; right: parent.right }
                    height: parent.radius
                    color: parent.color
                }

                RowLayout {
                    anchors.fill: parent
                    spacing: 0

                    Sidebar {
                        objectName: "appSidebar"
                        id: sidebar
                        Layout.preferredWidth: 240
                        Layout.fillHeight: true
                        z: 20
                        visible: !root.setupMode
                        showingSettings: root.currentPageIndex === 1
                        activeSessionKey: hasSessionService ? sessionService.activeKey : ""
                        showChatSelection: root.currentPageIndex === 0
                        onSettingsRequested: root.startView = "settings"
                        onDiagnosticsRequested: diagnosticsModal.open()
                        onNewSessionRequested: if (hasSessionService) sessionService.newSession("")
                        onSessionSelected: function(key) {
                            if (hasSessionService) sessionService.selectSession(key)
                            root.startView = "chat"
                        }
                        onSessionDeleteRequested: function(key) {
                            if (!hasSessionService)
                                return
                            sessionService.deleteSession(key)
                        }
                    }

                    StackLayout {
                        objectName: "mainStack"
                        id: stack
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: root.currentPageIndex

                        Item {
                            id: chatPage
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true

                            property bool active: root.currentPageIndex === 0
                            property real revealOpacity: 1.0
                            property real revealScale: 1.0
                            property real revealShift: 0.0
                            property real revealAuraOpacity: 0.0
                            property real completionFlashOpacity: 0.0
                            property real completionFlashScale: 0.94

                            function playReveal(direction, distance) {
                                revealOpacity = motionPageRevealStartOpacity
                                revealScale = motionPageRevealStartScale
                                revealShift = direction * distance
                                revealAuraOpacity = motionPageAuraPeak
                                chatPageReveal.restart()
                            }

                            function playSetupCompletionReveal() {
                                playReveal(-1, motionPageShift + 8)
                                completionFlashOpacity = 0.24
                                completionFlashScale = 0.94
                                setupCompletionReveal.restart()
                            }

                            onActiveChanged: {
                                if (active)
                                    playReveal(-1, motionPageShift)
                            }

                            Connections {
                                target: hasSessionService ? sessionService : null
                                function onActiveKeyChanged(_key) {
                                    if (chatPage.active)
                                        chatPage.playReveal(1, motionPageShiftSubtle)
                                }
                            }

                            Connections {
                                target: root
                                function onSetupCompletionTokenChanged() {
                                    if (chatPage.active)
                                        chatPage.playSetupCompletionReveal()
                                }
                            }

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 8
                                radius: chrome.radius - 8
                                color: root.isDark ? "#14FFA11A" : "#0FFFF1DE"
                                opacity: chatPage.revealAuraOpacity
                                visible: opacity > 0.01
                            }

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 8
                                radius: chrome.radius - 8
                                color: root.isDark ? "#20FFD699" : "#1FD0892C"
                                opacity: chatPage.completionFlashOpacity
                                scale: chatPage.completionFlashScale
                                visible: opacity > 0.01
                            }

                            Item {
                                anchors.fill: parent
                                opacity: chatPage.revealOpacity
                                scale: chatPage.revealScale
                                transform: Translate { x: chatPage.revealShift }

                                ChatView {
                                    id: chatView
                                    anchors.fill: parent
                                    onMessageCopied: globalToast.show(strings.copied_ok, true)
                                }
                            }

                            SequentialAnimation {
                                id: chatPageReveal
                                ParallelAnimation {
                                    NumberAnimation {
                                        target: chatPage
                                        property: "revealOpacity"
                                        to: 1.0
                                        duration: motionUi
                                        easing.type: easeStandard
                                    }
                                    NumberAnimation {
                                        target: chatPage
                                        property: "revealScale"
                                        to: 1.0
                                        duration: motionPanel
                                        easing.type: easeEmphasis
                                    }
                                    NumberAnimation {
                                        target: chatPage
                                        property: "revealShift"
                                        to: 0.0
                                        duration: motionPanel
                                        easing.type: easeEmphasis
                                    }
                                    NumberAnimation {
                                        target: chatPage
                                        property: "revealAuraOpacity"
                                        to: 0.0
                                        duration: motionPanel
                                        easing.type: easeStandard
                                    }
                                }
                            }

                            SequentialAnimation {
                                id: setupCompletionReveal
                                ParallelAnimation {
                                    NumberAnimation {
                                        target: chatPage
                                        property: "completionFlashOpacity"
                                        to: 0.0
                                        duration: motionAmbient
                                        easing.type: easeStandard
                                    }
                                    NumberAnimation {
                                        target: chatPage
                                        property: "completionFlashScale"
                                        to: 1.02
                                        duration: motionUi
                                        easing.type: easeEmphasis
                                    }
                                }
                                NumberAnimation {
                                    target: chatPage
                                    property: "completionFlashScale"
                                    to: 1.0
                                    duration: motionPanel
                                    easing.type: easeSoft
                                }
                            }
                        }

                        Item {
                            id: settingsPage
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true

                            property bool active: root.currentPageIndex === 1
                            property real revealOpacity: 1.0
                            property real revealScale: 1.0
                            property real revealShift: 0.0
                            property real revealAuraOpacity: 0.0

                            function playReveal(direction, distance) {
                                revealOpacity = motionPageRevealStartOpacity
                                revealScale = motionPageRevealStartScale
                                revealShift = direction * distance
                                revealAuraOpacity = motionPageAuraPeak
                                settingsPageReveal.restart()
                            }

                            onActiveChanged: {
                                if (active)
                                    playReveal(1, motionPageShift)
                            }

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 8
                                radius: chrome.radius - 8
                                color: root.isDark ? "#12FFFFFF" : "#10FFFFFF"
                                opacity: settingsPage.revealAuraOpacity
                                visible: opacity > 0.01
                            }

                            Item {
                                anchors.fill: parent
                                opacity: settingsPage.revealOpacity
                                scale: settingsPage.revealScale
                                transform: Translate { x: settingsPage.revealShift }

                                SettingsView {
                                    objectName: "settingsView"
                                    id: settingsView
                                    anchors.fill: parent
                                    appRoot: root
                                    onboardingMode: root.setupMode
                                }
                            }

                            SequentialAnimation {
                                id: settingsPageReveal
                                ParallelAnimation {
                                    NumberAnimation {
                                        target: settingsPage
                                        property: "revealOpacity"
                                        to: 1.0
                                        duration: motionUi
                                        easing.type: easeStandard
                                    }
                                    NumberAnimation {
                                        target: settingsPage
                                        property: "revealScale"
                                        to: 1.0
                                        duration: motionPanel
                                        easing.type: easeEmphasis
                                    }
                                    NumberAnimation {
                                        target: settingsPage
                                        property: "revealShift"
                                        to: 0.0
                                        duration: motionPanel
                                        easing.type: easeEmphasis
                                    }
                                    NumberAnimation {
                                        target: settingsPage
                                        property: "revealAuraOpacity"
                                        to: 0.0
                                        duration: motionPanel
                                        easing.type: easeStandard
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

    }


    // Window drag is handled inside titleBar to avoid blocking traffic lights.

    AppToast {
        id: globalToast
        objectName: "globalToast"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 14
        anchors.rightMargin: 14
        z: 999
        successBg: isDark ? "#1F7A4D" : "#16A34A"
        errorBg: isDark ? "#B84040" : "#DC2626"
        textColor: "#FFFFFF"
        duration: toastDuration
    }

    TextEdit {
        id: diagnosticsClipHelper
        visible: false
        textFormat: TextEdit.PlainText
    }

    AppModal {
        id: diagnosticsModal
        objectName: "diagnosticsModal"
        title: strings.diagnostics_title
        closeText: strings.diagnostics_close
        maxModalWidth: 920
        maxModalHeight: 760
        darkMode: root.isDark
        bodyScrollable: false
        showDefaultCloseAction: false
        onOpened: {
            if (diagnosticsService)
                diagnosticsService.refresh()
            diagnosticsLogTailView.followTail()
        }

        Item {
            id: diagnosticsBody
            width: parent.width
            height: diagnosticsModal.height - 92

            ColumnLayout {
                anchors.fill: parent
                spacing: 16

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 134
                    spacing: 16

                    Rectangle {
                        objectName: "diagnosticsGatewayCard"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 134
                        radius: 16
                        color: isDark ? "#15110F" : "#FBF7F2"
                        border.width: 1
                        border.color: borderSubtle

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                Rectangle {
                                    Layout.preferredWidth: 30
                                    Layout.preferredHeight: 30
                                    radius: 10
                                    color: isDark ? "#1F1814" : "#F1E8DF"

                                    Image {
                                        width: 24
                                        height: 24
                                        anchors.centerIn: parent
                                        source: diagnosticsSectionIcon("gateway")
                                        sourceSize: Qt.size(24, 24)
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        mipmap: true
                                    }
                                }

                                Text {
                                    text: strings.diagnostics_gateway_title
                                    color: textSecondary
                                    font.pixelSize: typeMeta
                                    font.weight: weightBold
                                }

                                Item { Layout.fillWidth: true }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: 1
                                color: borderSubtle
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12

                                Image {
                                    Layout.alignment: Qt.AlignTop
                                    source: diagnosticsGatewayIcon()
                                    sourceSize: Qt.size(28, 28)
                                    width: 28
                                    height: 28
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                    mipmap: true
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Text {
                                            text: diagnosticsGatewayLabel()
                                            color: textPrimary
                                            font.pixelSize: typeBody + 2
                                            font.weight: weightBold
                                        }

                                        Rectangle {
                                            Layout.alignment: Qt.AlignVCenter
                                            width: 8
                                            height: 8
                                            radius: 4
                                            color: diagnosticsGatewayBadgeColor()
                                        }

                                        Item { Layout.fillWidth: true }

                                        Text {
                                            visible: diagnosticsObservabilitySummary() !== ""
                                            text: diagnosticsObservabilitySummary()
                                            color: textSecondary
                                            font.pixelSize: typeMeta - 1
                                            elide: Text.ElideRight
                                            Layout.preferredWidth: 250
                                        }
                                    }

                                }
                            }
                        }
                    }

                    Rectangle {
                        objectName: "diagnosticsLogFileCard"
                        Layout.preferredWidth: 340
                        Layout.preferredHeight: 134
                        radius: 16
                        color: isDark ? "#15110F" : "#FBF7F2"
                        border.width: 1
                        border.color: borderSubtle

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                Rectangle {
                                    Layout.preferredWidth: 30
                                    Layout.preferredHeight: 30
                                    radius: 10
                                    color: isDark ? "#1F1814" : "#F1E8DF"

                                    Image {
                                        width: 24
                                        height: 24
                                        anchors.centerIn: parent
                                        source: diagnosticsSectionIcon("file")
                                        sourceSize: Qt.size(24, 24)
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        mipmap: true
                                    }
                                }

                                Text {
                                    text: strings.diagnostics_log_file
                                    color: textSecondary
                                    font.pixelSize: typeMeta
                                    font.weight: weightBold
                                }

                                Item { Layout.fillWidth: true }

                                PillActionButton {
                                    text: strings.diagnostics_refresh
                                    minHeight: 26
                                    horizontalPadding: 14
                                    fillColor: accentGlow
                                    hoverFillColor: accent
                                    outlineColor: accent
                                    hoverOutlineColor: accent
                                    textColor: isDark ? bgSidebar : "#FFFFFF"
                                    onClicked: if (diagnosticsService) diagnosticsService.refresh()
                                }

                                PillActionButton {
                                    text: strings.diagnostics_open_folder
                                    minHeight: 26
                                    horizontalPadding: 14
                                    fillColor: isDark ? "#1D1611" : "#FFF4E8"
                                    hoverFillColor: isDark ? "#251B14" : "#FFECD8"
                                    outlineColor: borderSubtle
                                    hoverOutlineColor: accent
                                    textColor: textPrimary
                                    outlined: true
                                    onClicked: if (diagnosticsService) diagnosticsService.openLogDirectory()
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: 1
                                color: borderSubtle
                            }

                            Text {
                                Layout.fillWidth: true
                                text: diagnosticsLogFilePathSafe()
                                color: textPrimary
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: typeMeta + 1
                                font.family: Qt.platform.os === "osx" ? "Menlo" : "Monospace"
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 16

                    Rectangle {
                        objectName: "diagnosticsEventsCard"
                        Layout.preferredWidth: 392
                        Layout.fillHeight: true
                        radius: 16
                        color: isDark ? "#15110F" : "#FBF7F2"
                        border.width: 1
                        border.color: borderSubtle

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                Rectangle {
                                    Layout.preferredWidth: 30
                                    Layout.preferredHeight: 30
                                    radius: 10
                                    color: isDark ? "#1F1814" : "#F1E8DF"

                                    Image {
                                        width: 24
                                        height: 24
                                        anchors.centerIn: parent
                                        source: diagnosticsSectionIcon("events")
                                        sourceSize: Qt.size(24, 24)
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        mipmap: true
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: strings.diagnostics_recent_events
                                    color: textPrimary
                                    font.pixelSize: typeBody + 1
                                    font.weight: weightBold
                                }

                                PillActionButton {
                                    text: strings.diagnostics_ask_bao
                                    visible: diagnosticsEventCountSafe() > 0
                                    minHeight: 26
                                    horizontalPadding: 14
                                    fillColor: accentGlow
                                    hoverFillColor: accent
                                    outlineColor: accent
                                    hoverOutlineColor: accent
                                    textColor: isDark ? bgSidebar : "#FFFFFF"
                                    onClicked: {
                                        if (!hasDiagnosticsService || !hasChatService)
                                            return
                                        var prompt = diagnosticsService.buildAssistantPrompt()
                                        if (!prompt)
                                            return
                                        diagnosticsModal.close()
                                        root.startView = "chat"
                                        chatService.sendMessage(prompt)
                                        globalToast.show(strings.diagnostics_sent, true)
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: 1
                                color: borderSubtle
                            }

                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true

                                Column {
                                    anchors.centerIn: parent
                                    spacing: 10
                                    visible: diagnosticsEventCountSafe() === 0

                                    Rectangle {
                                        width: 40
                                        height: 40
                                        radius: 14
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        color: isDark ? "#1F1814" : "#F1E8DF"

                                        Image {
                                            width: 24
                                            height: 24
                                            anchors.centerIn: parent
                                            source: diagnosticsSectionIcon("events")
                                            sourceSize: Qt.size(24, 24)
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true
                                            mipmap: true
                                        }
                                    }

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: strings.diagnostics_empty_events
                                        color: textSecondary
                                        wrapMode: Text.WordWrap
                                        horizontalAlignment: Text.AlignHCenter
                                        font.pixelSize: typeMeta + 1
                                    }
                                }

                                ScrollView {
                                    anchors.fill: parent
                                    visible: diagnosticsEventCountSafe() > 0
                                    clip: true

                                    Column {
                                        width: parent.width
                                        spacing: 0

                                        Repeater {
                                            model: diagnosticsEventsSafe()

                                            delegate: Item {
                                                required property var modelData
                                                width: parent.width
                                                height: eventBody.implicitHeight + 18

                                                Rectangle {
                                                    anchors.left: parent.left
                                                    anchors.top: parent.top
                                                    anchors.bottom: parent.bottom
                                                    width: 3
                                                    radius: 1.5
                                                    color: {
                                                        var level = String(modelData.level || "")
                                                        if (level === "error") return isDark ? "#D06A5B" : "#D65C45"
                                                        if (level === "warning") return isDark ? "#D5A44A" : "#D58B23"
                                                        return isDark ? "#7C6A58" : "#C8B5A2"
                                                    }
                                                }

                                                Column {
                                                    id: eventBody
                                                    anchors.left: parent.left
                                                    anchors.right: parent.right
                                                    anchors.leftMargin: 14
                                                    anchors.rightMargin: 4
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    spacing: 4

                                                    RowLayout {
                                                        width: parent.width
                                                        spacing: 8

                                                        Text {
                                                            text: String(modelData.code || modelData.stage || "event")
                                                            color: textPrimary
                                                            font.pixelSize: typeMeta
                                                            font.weight: weightBold
                                                        }

                                                        Item { Layout.fillWidth: true }

                                                        Text {
                                                            text: String(modelData.timestamp || "")
                                                            color: textTertiary
                                                            font.pixelSize: typeMeta - 1
                                                        }
                                                    }

                                                    Text {
                                                        width: parent.width
                                                        text: String(modelData.message || "")
                                                        color: textPrimary
                                                        wrapMode: Text.WordWrap
                                                        font.pixelSize: typeMeta + 1
                                                        font.weight: weightDemiBold
                                                    }

                                                    Text {
                                                        width: parent.width
                                                        text: [String(modelData.source || ""), String(modelData.session_key || "")].filter(Boolean).join(" · ")
                                                        color: textSecondary
                                                        wrapMode: Text.WordWrap
                                                        font.pixelSize: typeMeta - 1
                                                    }
                                                }

                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        objectName: "diagnosticsLogTailCard"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 16
                        color: isDark ? "#15110E" : "#FBF7F2"
                        border.width: 1
                        border.color: borderSubtle

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                Rectangle {
                                    Layout.preferredWidth: 30
                                    Layout.preferredHeight: 30
                                    radius: 10
                                    color: isDark ? "#1F1814" : "#F1E8DF"

                                    Image {
                                        width: 24
                                        height: 24
                                        anchors.centerIn: parent
                                        source: diagnosticsSectionIcon("logtail")
                                        sourceSize: Qt.size(24, 24)
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        mipmap: true
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: strings.diagnostics_log_tail
                                    color: textPrimary
                                    font.pixelSize: typeBody + 1
                                    font.weight: weightBold
                                }

                                PillActionButton {
                                    text: strings.diagnostics_copy_tail
                                    minHeight: 26
                                    horizontalPadding: 14
                                    fillColor: isDark ? "#1D1611" : "#FFF4E8"
                                    hoverFillColor: isDark ? "#251B14" : "#FFECD8"
                                    outlineColor: borderSubtle
                                    hoverOutlineColor: accent
                                    textColor: textPrimary
                                    outlined: true
                                    onClicked: {
                                        root.copyPlainText(diagnosticsRecentLogTextSafe())
                                        globalToast.show(strings.copied_ok, true)
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: 1
                                color: borderSubtle
                            }

                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true

                                Column {
                                    anchors.centerIn: parent
                                    spacing: 10
                                    visible: !diagnosticsRecentLogTextSafe()

                                    Rectangle {
                                        width: 40
                                        height: 40
                                        radius: 14
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        color: isDark ? "#1F1814" : "#F1E8DF"

                                        Image {
                                            width: 24
                                            height: 24
                                            anchors.centerIn: parent
                                            source: diagnosticsSectionIcon("logtail")
                                            sourceSize: Qt.size(24, 24)
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true
                                            mipmap: true
                                        }
                                    }

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: strings.diagnostics_empty_logs
                                        color: textSecondary
                                        wrapMode: Text.WordWrap
                                        horizontalAlignment: Text.AlignHCenter
                                        font.pixelSize: typeMeta + 1
                                    }
                                }

                                FollowTailLogView {
                                    id: diagnosticsLogTailView
                                    objectName: "diagnosticsLogTailScroll"
                                    anchors.fill: parent
                                    visible: !!diagnosticsRecentLogTextSafe()
                                    text: diagnosticsRecentLogTextSafe()
                                    textColor: textPrimary
                                    fontPixelSize: typeMeta
                                    fontFamily: Qt.platform.os === "osx" ? "Menlo" : "Monospace"
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
