import QtQuick 2.15
import QtQuick.Controls 2.15

import QtQuick.Layouts 1.15

ApplicationWindow {
    id: root
    visible: true
    width: 1100
    height: 720
    title: "bao"
    flags: Qt.Window | Qt.FramelessWindowHint

    // Keep the outer window fully transparent; we draw everything inside
    // a rounded, clipped Rectangle so the visible window has rounded corners.
    color: "transparent"

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
        "nav_chat": "聊天",
        "nav_settings": "设置",
        "sidebar_sessions": "会话",
        "sidebar_no_sessions": "暂无会话",
        "chat_empty_title": "开始对话",
        "chat_empty_hint": "在下面输入消息",
        "chat_gateway": "网关",
        "gateway_idle": "网关空闲",
        "gateway_starting": "启动中…",
        "gateway_error": "错误",
        "button_start_gateway": "启动网关",
        "button_restart": "重启",
        "chat_placeholder": "给 bao 发消息…",
        "section_app": "应用",
        "section_agent_defaults": "代理默认设置",
        "section_provider": "提供商",
        "section_channels": "渠道",
        "section_tools": "工具",
        "ui_language": "界面语言",
        "ui_language_auto": "自动（跟随系统）",
        "ui_language_zh": "中文",
        "ui_language_en": "English",
        "settings_save": "保存",
        "settings_saved_hint": "已保存 — 点击启动网关生效",
        "settings_save_failed": "保存失败"
    })

    readonly property var stringsEn: ({
        "nav_chat": "Chat",
        "nav_settings": "Settings",
        "sidebar_sessions": "Sessions",
        "sidebar_no_sessions": "No sessions yet",
        "chat_empty_title": "Start a conversation",
        "chat_empty_hint": "Type a message below",
        "chat_gateway": "Gateway",
        "gateway_idle": "Gateway idle",
        "gateway_starting": "Starting…",
        "gateway_error": "Error",
        "button_start_gateway": "Start Gateway",
        "button_restart": "Restart",
        "chat_placeholder": "Message bao…",
        "section_app": "App",
        "section_agent_defaults": "Agent Defaults",
        "section_provider": "Provider",
        "section_channels": "Channels",
        "section_tools": "Tools",
        "ui_language": "UI Language",
        "ui_language_auto": "Auto (System)",
        "ui_language_zh": "Chinese",
        "ui_language_en": "English",
        "settings_save": "Save",
        "settings_saved_hint": "Saved — click Start Gateway to apply",
        "settings_save_failed": "Save failed"
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

    Component.onCompleted: _applyUiLanguageFromConfig()

    Connections {
        target: configService
        function onConfigLoaded() { root._applyUiLanguageFromConfig() }
    }

    // ── Design Tokens ─────────────────────────────────────────────────
    readonly property string fontFamily: "Helvetica Neue"

    // Surface colors
    readonly property color bgBase:          isDark ? "#0C0C14" : "#F7F8FA"
    readonly property color bgSidebar:       isDark ? "#111119" : "#EDEEF2"
    readonly property color bgCard:          isDark ? "#16161F" : "#FFFFFF"
    readonly property color bgCardHover:     isDark ? "#1C1C28" : "#F5F5FA"
    readonly property color bgInput:         isDark ? "#1A1A26" : "#F2F3F7"
    readonly property color bgInputHover:    isDark ? "#1E1E2C" : "#ECEDF3"
    readonly property color bgInputFocus:    isDark ? "#1C1C2A" : "#FFFFFF"
    readonly property color bgElevated:      isDark ? "#1E1E2A" : "#FFFFFF"

    // Text colors
    readonly property color textPrimary:     isDark ? "#E8E8F0" : "#111118"
    readonly property color textSecondary:   isDark ? "#8A8AA0" : "#6B7280"
    readonly property color textTertiary:    isDark ? "#55556A" : "#9CA3AF"
    readonly property color textPlaceholder: isDark ? "#44445A" : "#B0B5C0"

    // Border colors
    // NOTE: QML 8-digit hex uses #AARRGGBB (NOT #RRGGBBAA like CSS).
    readonly property color borderSubtle:    isDark ? "#08FFFFFF" : "#08000000"
    readonly property color borderDefault:   isDark ? "#0FFFFFFF" : "#0F000000"
    readonly property color borderFocus:     "#7C6CF0"

    // Accent
    readonly property color accent:          "#7C6CF0"
    readonly property color accentHover:     "#6B5BD9"
    readonly property color accentMuted:     isDark ? "#187C6CF0" : "#107C6CF0"
    readonly property color accentGlow:      "#307C6CF0"

    // Status
    readonly property color statusSuccess:   "#34D399"
    readonly property color statusWarning:   "#FBBF24"
    readonly property color statusError:     "#F87171"

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
                height: 48

                // Drag the frameless window by the title bar background.
                // Ignore the traffic-light area so the buttons remain clickable.
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton
                    hoverEnabled: true
                    cursorShape: Qt.ArrowCursor
                    onPressed: function(mouse) {
                        if (mouse.x < 92) {
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
                    spacing: 8
                    Repeater {
                        model: [
                            { color: "#FF5F57", hoverColor: "#FF3B30", action: "close" },
                            { color: "#FEBC2E", hoverColor: "#F5A623", action: "minimize" },
                            { color: "#28C840", hoverColor: "#1DB954", action: "maximize" }
                        ]
                        delegate: Rectangle {
                            width: 14; height: 14; radius: 7
                            color: tlHover.containsMouse ? modelData.hoverColor : modelData.color
                            opacity: tlHover.containsMouse ? 1.0 : 0.85
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Behavior on opacity { NumberAnimation { duration: 120 } }

                            Text {
                                anchors.centerIn: parent
                                text: modelData.action === "close" ? "✕" :
                                      modelData.action === "minimize" ? "−" : "+"
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
                                    if (modelData.action === "close") root.close()
                                    else if (modelData.action === "minimize") root.showMinimized()
                                    else root.showMaximized()
                }
            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: "bao"
                    color: root.textPrimary
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    font.letterSpacing: 0.5
                    opacity: 0.7
                }

                Item { Layout.fillWidth: true }

                // Spacer to balance traffic lights
                Item { width: 62 }
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
                        onSessionSelected: function(key) { if (sessionService) sessionService.selectSession(key) }
                        onSessionDeleteRequested: function(key) { if (sessionService) sessionService.deleteSession(key) }
                    }

                    StackLayout {
                        id: stack
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: root.startView === "settings" ? 1 : 0

                        // Force settings if config is missing/invalid
                        Component.onCompleted: {
                            if (configService && !configService.isValid) {
                                stack.currentIndex = 1
                                sidebar.currentView = "settings"
                            }
                        }

                        ChatView {
                            id: chatView
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
}
