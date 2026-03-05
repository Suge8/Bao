import QtQuick 2.15
import QtQuick.Controls 2.15

import QtQuick.Layouts 1.15

ApplicationWindow {
    id: root
    visible: true
    width: 1100
    height: 720
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
    property bool isDark: true

    property string uiLanguage: "auto" // auto | zh | en
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
        "sidebar_no_sessions": "暂无会话",
        "chat_empty_title": "开始对话",
        "chat_empty_hint": "在下面输入消息",
        "chat_gateway": "网关",
        "gateway_idle": "已停止",
        "gateway_starting": "启动中…",
        "gateway_running": "运行中",
        "gateway_stopped": "已停止",
        "gateway_error": "错误",
        "button_start_gateway": "启动网关",
        "button_restart": "重启",
        "button_stop_gateway": "停止",
        "chat_placeholder": "给 Bao 发消息…",
        "chat_loading_history": "加载会话中…",
        "section_app": "应用",
        "section_agent_defaults": "代理默认设置",
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
        "empty_idle_title": "网关未启动",
        "empty_idle_hint": "点击左侧网关胶囊启动网关",
        "session_delete_ok": "会话已删除",
        "session_delete_fail": "删除失败",
        "channel_desktop": "桌面",
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
        "copied_ok": "已复制",
    })

    readonly property var stringsEn: ({
        "sidebar_sessions": "Sessions",
        "sidebar_no_sessions": "No sessions yet",
        "chat_empty_title": "Start a conversation",
        "chat_empty_hint": "Type a message below",
        "chat_gateway": "Gateway",
        "gateway_idle": "Stopped",
        "gateway_starting": "Starting\u2026",
        "gateway_running": "Running",
        "gateway_stopped": "Stopped",
        "gateway_error": "Error",
        "button_start_gateway": "Start Gateway",
        "button_restart": "Restart",
        "button_stop_gateway": "Stop",
        "chat_placeholder": "Message Bao\u2026",
        "chat_loading_history": "Loading session\u2026",
        "section_app": "App",
        "section_agent_defaults": "Agent Defaults",
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
        "empty_idle_title": "Gateway not started",
        "empty_idle_hint": "Click the gateway capsule in the sidebar to start",
        "session_delete_ok": "Session deleted",
        "session_delete_fail": "Delete failed",
        "channel_desktop": "Desktop",
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
        "copied_ok": "Copied",
    })

    readonly property var strings: (
        uiLanguage === "zh" ? stringsZh
        : uiLanguage === "en" ? stringsEn
        : (autoLanguage === "zh" ? stringsZh : stringsEn)
    )

    function _applyUiLanguageFromConfig() {
        if (!configService) return
        var v = configService.getValue("ui.language")
        if (v === "auto" || v === "zh" || v === "en") uiLanguage = v
    }
    // Resolved language for backend (never "auto")
    readonly property string effectiveLang: {
        if (uiLanguage === "zh" || uiLanguage === "en") return uiLanguage
        return autoLanguage
    }
    onEffectiveLangChanged: if (chatService) chatService.setLanguage(effectiveLang)

    Component.onCompleted: _applyUiLanguageFromConfig()

    Connections {
        target: configService
        function onConfigLoaded() { root._applyUiLanguageFromConfig() }
    }

    Connections {
        target: sessionService
        function onDeleteCompleted(_key, ok, error) {
            if (!ok)
                globalToast.show(strings.session_delete_fail + (error ? (": " + error) : ""), false)
        }
    }

    // ── Design Tokens ─────────────────────────────────────────────────
    readonly property string fontFamily: "Helvetica Neue"

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
    readonly property color borderFocus:     "#FF9A2E"

    // Accent
    readonly property color accent:          "#FFA11A"
    readonly property color accentHover:     "#FF8600"
    readonly property color accentMuted:     isDark ? "#48FFA11A" : "#30FFA11A"
    readonly property color accentGlow:      "#95FFA11A"

    // Status
    readonly property color statusSuccess:   "#22C55E"
    readonly property color statusWarning:   "#F59E0B"
    readonly property color statusError:     "#F05A5A"
    readonly property color textSelectionBg: isDark ? "#80FFA11A" : "#66FFA11A"
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
    readonly property real motionCopyFlashPeak: 0.42
    readonly property real motionAuraNearPeak: 0.34
    readonly property real motionAuraFarPeak: 0.2
    readonly property real motionTypingPulseMinOpacity: 0.28
    readonly property int motionEnterOffsetY: 10
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
    readonly property int sizeSidebarHeader: 38
    readonly property int sizeSessionRow: 38
    readonly property int sizeCapsuleHeight: 48
    readonly property int sizeBubbleRadius: 18
    readonly property int sizeSystemBubbleRadius: 11
    readonly property int sizeAppIcon: 44

    // Gateway emphasis tokens
    readonly property color gatewayBgRunningHover: isDark ? "#6622C55E" : "#4A22C55E"
    readonly property color gatewayBgErrorHover: isDark ? "#40F05A5A" : "#2AF05A5A"
    readonly property color gatewayBgStartingHover: isDark ? "#68F59E0B" : "#4CF59E0B"
    readonly property color gatewayBgIdleHover: isDark ? "#52FFA11A" : "#3CFFA11A"
    readonly property color gatewayBgRunning: isDark ? "#5222C55E" : "#3A22C55E"
    readonly property color gatewayBgError: isDark ? "#30F05A5A" : "#20F05A5A"
    readonly property color gatewayBgStarting: isDark ? "#48F59E0B" : "#36F59E0B"
    readonly property color gatewayBgIdle: isDark ? "#3AFFA11A" : "#2AFFA11A"
    readonly property color gatewayBorderRunning: isDark ? "#A022C55E" : "#7A22C55E"
    readonly property color gatewayBorderError: isDark ? "#54F05A5A" : "#3AF05A5A"
    readonly property color gatewayBorderStarting: isDark ? "#8AF59E0B" : "#70F59E0B"
    readonly property color gatewayBorderIdleHover: isDark ? "#78FFA11A" : "#56FFA11A"
    readonly property color gatewayBorderIdle: isDark ? "#58FFA11A" : "#3AFFA11A"
    readonly property color gatewayGlowRunning: isDark ? "#B022C55E" : "#8A22C55E"
    readonly property color gatewayTextRunning: isDark ? "#A8EAC3" : "#177C43"
    readonly property color gatewayTextStarting: isDark ? "#FFD484" : "#B56800"
    readonly property color gatewayTextIdle: isDark ? "#FFC58A" : "#B86A12"

    // Session emphasis tokens
    readonly property color sessionRowActiveBg: isDark ? "#68FFA11A" : "#48FFA11A"
    readonly property color sessionRowHoverBg: isDark ? "#08FFFFFF" : "#06000000"
    readonly property color sessionRowActiveBorder: isDark ? "#C0FFA11A" : "#A6FFA11A"
    readonly property color sessionLeadingActiveBg: isDark ? "#78FFA11A" : "#58FFA11A"
    readonly property color sessionLeadingIdleBg: isDark ? "#10FFFFFF" : "#12000000"
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
    readonly property color chatSystemBubbleBg: isDark ? "#24FFA11A" : "#15000000"
    readonly property color chatSystemBubbleErrorBg: isDark ? "#20F05A5A" : "#14F05A5A"
    readonly property color chatSystemBubbleErrorBorder: isDark ? "#58F05A5A" : "#42F05A5A"
    readonly property color chatSystemBubbleOverlay: isDark ? "#22FFA11A" : "#18FFA11A"
    readonly property color chatSystemBubbleErrorOverlay: "#08F05A5A"
    readonly property color chatBubbleCopyFlashUser: "#40FFFFFF"
    readonly property color chatBubbleErrorTint: "#15F05A5A"
    readonly property color chatEmptyIconBg: isDark ? "#10FFFFFF" : "#08000000"
    readonly property color chatErrorBadgeBg: isDark ? "#18F87171" : "#10F87171"
    readonly property color chatComposerSendDisabled: isDark ? "#1A1A26" : "#E5E7EB"



    font.family: fontFamily

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
                        id: sidebar
                        Layout.preferredWidth: 240
                        Layout.fillHeight: true
                        currentView: root.startView
                        onViewRequested: function(view) { stack.currentIndex = view === "chat" ? 0 : 1 }
                        onNewSessionRequested: if (sessionService) sessionService.newSession("")
                        onSessionSelected: function(key) {
                            if (sessionService) sessionService.selectSession(key)
                            stack.currentIndex = 0
                            sidebar.currentView = "chat"
                        }
                        onSessionDeleteRequested: function(key) {
                            if (!sessionService)
                                return
                            sessionService.deleteSession(key)
                            globalToast.show(strings.session_delete_ok, true)
                        }
                    }

                    StackLayout {
                        id: stack
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: root.startView === "settings" ? 1 : 0

                        // Force settings if config is missing/invalid
                        Component.onCompleted: {
                            if (configService && (!configService.isValid || configService.needsSetup)) {
                                stack.currentIndex = 1
                                sidebar.currentView = "settings"
                            }
                        }

                        ChatView {
                            id: chatView
                            onMessageCopied: globalToast.show(strings.copied_ok, true)
                        }

                        SettingsView {
                            id: settingsView
                            appRoot: root
                        }
                    }
                }
            }
        }

    }


    // Window drag is handled inside titleBar to avoid blocking traffic lights.

    AppToast {
        id: globalToast
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
}
