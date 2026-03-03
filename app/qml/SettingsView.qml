import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15


Rectangle {
    id: root
    color: "transparent"

    property var appRoot: null
    readonly property bool isZh: appRoot
                                 ? (appRoot.uiLanguage === "zh" || (appRoot.uiLanguage === "auto" && appRoot.autoLanguage === "zh"))
                                 : false
    property var _providerList: []

    function tr(zh, en) {
        return isZh ? zh : en
    }

    function _translateError(msg) {
        if (msg.indexOf("token_required:") === 0) {
            var channel = msg.split(":")[1]
            var names = {"telegram": "Telegram", "discord": "Discord", "slack": "Slack"}
            var name = names[channel] || channel
            return tr(name + " 启用时需要填写 Token", name + " requires a token when enabled")
        }
        return msg
    }

    function _loadProviders() {
        if (!configService) return
        _providerList = configService.getProviders() || []
    }

    // No longer needed — _addNewProvider uses dotpath insertion

    function _addNewProvider() {
        if (!configService) return
        var name = "provider" + (_providerList.length + 1)
        var changes = {}
        changes["providers." + name] = {"type": "openai", "apiKey": ""}
        var ok = configService.save(changes)
        toast.show(ok ? strings.settings_saved_hint : strings.settings_save_failed, ok)
        if (ok) _loadProviders()
    }

    function saveAll() {
        if (!configService) return
        var changes = {}
        collectFields(innerCol, changes)

        var providerChanges = {}
        for (var i = 0; i < root._providerList.length; i++) {
            var prefix = "_prov_" + i + "_"
            var origName = root._providerList[i].name
            var newName = changes[prefix + "name"] || origName
            var prov = {}
            var fieldNames = ["type", "apiKey", "apiBase"]
            for (var j = 0; j < fieldNames.length; j++) {
                var fk = prefix + fieldNames[j]
                if (changes[fk] !== undefined) prov[fieldNames[j]] = changes[fk]
                delete changes[fk]
            }
            delete changes[prefix + "name"]
            if (Object.keys(prov).length > 0) {
                providerChanges[newName] = prov
                for (var key in prov) {
                    changes["providers." + newName + "." + key] = prov[key]
                }
            }
        }

        var toDelete = []
        for (var k in changes) {
            if (k.startsWith("_prov_") || k.startsWith("_new_prov_")) toDelete.push(k)
        }
        for (var d = 0; d < toDelete.length; d++) delete changes[toDelete[d]]

        if (changes.hasOwnProperty("ui.language")) {
            changes["ui"] = {"language": changes["ui.language"]}
            delete changes["ui.language"]
        }

        var ok = configService.save(changes)
        if (ok) {
            toast.show(strings.settings_saved_hint, true)
            root._loadProviders()
        }
    }

    function collectFields(item, changes) {
        if (!item || !item.children) return
        for (var i = 0; i < item.children.length; i++) {
            var child = item.children[i]
            if (child && typeof child.dotpath === "string" && child.dotpath !== "" && child.currentValue !== undefined) {
                var v = child.currentValue
                changes[child.dotpath] = v
            }
            // Traverse Loader loaded item for ChannelRow fields
            if (child && child.item) {
                var loaded = child.item
                if (typeof loaded.dotpath === "string" && loaded.dotpath !== "" && loaded.currentValue !== undefined) {
                    var lv = loaded.currentValue
                    changes[loaded.dotpath] = lv
                }
                collectFields(loaded, changes)
            }
            collectFields(child, changes)
        }
    }

    Component.onCompleted: _loadProviders()

    WheelHandler {
        id: settingsWheelProxy
        target: null
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function(event) {
            var flick = settingsScroll.contentItem
            if (!flick) return
            var maxY = Math.max(0, flick.contentHeight - flick.height)
            if (maxY <= 0) return
            var deltaY = event.pixelDelta.y !== 0 ? -event.pixelDelta.y : (-event.angleDelta.y / 3)
            var nextY = flick.contentY + deltaY
            if (nextY < 0) nextY = 0
            if (nextY > maxY) nextY = maxY
            flick.contentY = nextY
            event.accepted = true
        }
    }

    ScrollView {
        id: settingsScroll
        anchors.fill: parent
        contentWidth: scrollContent.width
        contentHeight: scrollContent.height
        ScrollBar.vertical.policy: ScrollBar.AlwaysOn
        clip: true

        Item {
            id: scrollContent
            width: settingsScroll.availableWidth
            height: innerCol.implicitHeight + 96
            implicitHeight: height

            ColumnLayout {
                id: innerCol
                width: Math.min(Math.max(settingsScroll.availableWidth - 64, 320), 820)
                height: implicitHeight
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top
                anchors.topMargin: 72
                spacing: spacingXl

                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_app

                    ColumnLayout {
                        width: parent.width
                        spacing: spacingMd

                        SettingsSelect {
                            label: strings.ui_language
                            dotpath: "ui.language"
                            options: [
                                {"label": strings.ui_language_auto, "value": "auto"},
                                {"label": strings.ui_language_zh, "value": "zh"},
                                {"label": strings.ui_language_en, "value": "en"}
                            ]
                            onValueChanged: function(v) {
                                if (root.appRoot) root.appRoot.uiLanguage = v
                                if (configService && configService.isValid) {
                                    configService.save({"ui": {"language": v}})
                                }
                            }
                        }
                    }
                }

                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_agent_defaults

                    ColumnLayout {
                        width: parent.width
                        spacing: spacingMd

                        SettingsField { label: tr("工作目录", "Workspace"); dotpath: "agents.defaults.workspace"; placeholder: "~/.bao/workspace" }
                        SettingsField { label: tr("主模型", "Model"); dotpath: "agents.defaults.model"; placeholder: "openai/gpt-4o" }
                        SettingsField { label: tr("轻量模型", "Utility Model"); dotpath: "agents.defaults.utilityModel"; placeholder: "openrouter/google/gemini-flash-1.5"; description: tr("后台任务用的轻量模型（经验提取、标题生成等）", "Lightweight model for background tasks (experience extraction, title generation)") }
                        SettingsField { label: tr("经验模型", "Experience Model"); dotpath: "agents.defaults.experienceModel"; placeholder: "utility / main / none"; description: tr("utility = 用轻量模型 / main = 用主模型 / none = 关闭", "utility = use utility model / main = use primary model / none = disabled") }
                        SettingsListField { label: tr("模型列表", "Models"); dotpath: "agents.defaults.models"; placeholder: "model1, model2"; description: tr("聊天中可通过 /model 命令切换的模型", "Models available for switching via /model command") }

                        SettingsCollapsible {
                            Layout.fillWidth: true
                            title: tr("高级选项", "Advanced")

                            ColumnLayout {
                                width: parent.width
                                spacing: spacingMd

                                SettingsField { label: tr("最大 Token", "Max Tokens"); dotpath: "agents.defaults.maxTokens"; placeholder: "8192"; inputType: "number"; description: tr("单次回复的最大 token 数", "Max tokens per response") }
                                SettingsField { label: tr("温度", "Temperature"); dotpath: "agents.defaults.temperature"; placeholder: "0.1"; inputType: "number"; description: tr("越低越确定，越高越随机（0-2）", "Lower = more deterministic, higher = more random (0-2)") }
                                SettingsField { label: tr("工具迭代上限", "Max Tool Iterations"); dotpath: "agents.defaults.maxToolIterations"; placeholder: "20"; inputType: "number"; description: tr("单轮对话中最多调用工具的次数", "Max tool calls per conversation turn") }
                                SettingsField { label: tr("记忆窗口", "Memory Window"); dotpath: "agents.defaults.memoryWindow"; placeholder: "50"; inputType: "number"; description: tr("保留最近多少条消息作为上下文", "Number of recent messages kept as context") }
                                SettingsSelect {
                                    label: tr("上下文管理", "Context Management")
                                    dotpath: "agents.defaults.contextManagement"
                                    description: tr("长对话上下文窗口管理策略", "Strategy for managing context window in long conversations")
                                    options: [
                                        {"label": tr("关闭", "off"), "value": "off"},
                                        {"label": tr("观察", "observe"), "value": "observe"},
                                        {"label": tr("自动", "auto"), "value": "auto"},
                                        {"label": tr("激进", "aggressive"), "value": "aggressive"}
                                    ]
                                }
                                SettingsSelect {
                                    label: tr("推理强度", "Reasoning Effort")
                                    dotpath: "agents.defaults.reasoningEffort"
                                    description: tr("控制模型推理扩展强度；Auto = 不显式设置", "Controls model reasoning extension; Auto = do not set explicitly")
                                    options: [
                                        {"label": tr("自动", "Auto"), "value": null},
                                        {"label": "off", "value": "off"},
                                        {"label": "low", "value": "low"},
                                        {"label": "medium", "value": "medium"},
                                        {"label": "high", "value": "high"}
                                    ]
                                }
                                SettingsField { label: tr("工具输出预览字符", "Tool Output Preview Chars"); dotpath: "agents.defaults.toolOutputPreviewChars"; placeholder: "3000"; inputType: "number"; description: tr("外置后保留在消息中的预览长度", "Preview length kept in message after offloading") }
                                SettingsField { label: tr("工具输出外置字符", "Tool Output Offload Chars"); dotpath: "agents.defaults.toolOutputOffloadChars"; placeholder: "8000"; inputType: "number"; description: tr("超过此长度的工具输出自动外置到文件", "Tool output exceeding this length is offloaded to file") }
                                SettingsField { label: tr("上下文压实字节估算", "Context Compact Bytes Est"); dotpath: "agents.defaults.contextCompactBytesEst"; placeholder: "240000"; inputType: "number"; description: tr("触发上下文压实的估算字节阈值", "Estimated byte threshold to trigger context compaction") }
                                SettingsField { label: tr("压实保留最近工具块", "Compact Keep Recent Tool Blocks"); dotpath: "agents.defaults.contextCompactKeepRecentToolBlocks"; placeholder: "4"; inputType: "number"; description: tr("压实时保留最近几组工具调用", "Number of recent tool call groups kept during compaction") }
                                SettingsField { label: tr("产物保留天数", "Artifact Retention Days"); dotpath: "agents.defaults.artifactRetentionDays"; placeholder: "7"; inputType: "number"; description: tr("外置产物文件的自动清理天数", "Days before offloaded artifact files are auto-cleaned") }
                                SettingsToggle { label: tr("发送进度", "Send Progress"); dotpath: "agents.defaults.sendProgress" }
                                SettingsToggle { label: tr("发送工具提示", "Send Tool Hints"); dotpath: "agents.defaults.sendToolHints" }
                            }
                        }
                    }
                }

                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_provider

                    ColumnLayout {
                        width: parent.width
                        spacing: spacingMd

                        Repeater {
                            model: root._providerList

                            delegate: Rectangle {
                                Layout.fillWidth: true
                                radius: radiusMd
                                color: isDark ? "#0DFFFFFF" : "#08000000"
                                border.color: borderSubtle
                                border.width: 1
                                implicitHeight: cardCol.implicitHeight + 24

                                property bool expanded: false
                                property var provData: modelData || ({})

                                ColumnLayout {
                                    id: cardCol
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: spacingMd
                                    spacing: spacingMd

                                    Item {
                                        Layout.fillWidth: true
                                        implicitHeight: 32

                                        RowLayout {
                                            anchors.fill: parent
                                            spacing: 8

                                            Text {
                                                text: expanded ? "▾" : "▸"
                                                color: textTertiary
                                                font.pixelSize: 12
                                            }
                                            Text {
                                                text: provData.name || ""
                                                color: textPrimary
                                                font.pixelSize: 14
                                                font.weight: Font.Medium
                                                Layout.fillWidth: true
                                            }
                                            Rectangle {
                                                radius: radiusSm
                                                color: isDark ? "#14FFFFFF" : "#10000000"
                                                implicitHeight: 24
                                                implicitWidth: badgeText.implicitWidth + 14

                                                Text {
                                                    id: badgeText
                                                    anchors.centerIn: parent
                                                    text: provData.type || ""
                                                    color: textSecondary
                                                    font.pixelSize: 12
                                                }
                                            }
                                            Rectangle {
                                                width: 28
                                                height: 28
                                                radius: radiusSm
                                                color: deleteHover.containsMouse ? (isDark ? "#30F87171" : "#20F87171") : "transparent"
                                                Behavior on color { ColorAnimation { duration: 150 } }

                                                Text {
                                                    anchors.centerIn: parent
                                                    text: "\u2715"
                                                    color: deleteHover.containsMouse ? statusError : textTertiary
                                                    font.pixelSize: 13
                                                }

                                                MouseArea {
                                                    id: deleteHover
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    acceptedButtons: Qt.LeftButton
                                                    scrollGestureEnabled: false
                                                    cursorShape: Qt.PointingHandCursor
                                                    onClicked: {
                                                        if (!configService || !provData.name) return
                                                        var ok = configService.removeProvider(provData.name)
                                                        toast.show(ok ? strings.settings_saved_hint : strings.settings_save_failed, ok)
                                                        if (ok) root._loadProviders()
                                                    }
                                                }
                                            }
                                        }

                                        MouseArea {
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.top: parent.top
                                            anchors.bottom: parent.bottom
                                            anchors.rightMargin: 36
                                            acceptedButtons: Qt.LeftButton
                                            scrollGestureEnabled: false
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: expanded = !expanded
                                        }
                                    }

                                    ColumnLayout {
                                        visible: expanded
                                        Layout.fillWidth: true
                                        spacing: spacingMd

                                        SettingsField {
                                            label: tr("名称", "Name")
                                            placeholder: "openaiCompatible"
                                            dotpath: "_prov_" + index + "_name"
                                            Component.onCompleted: presetText(provData.name || "")
                                        }
                                        SettingsField {
                                            label: tr("类型", "Type")
                                            placeholder: "openai / anthropic / gemini"
                                            dotpath: "_prov_" + index + "_type"
                                            description: tr("openai 兼容大多数第三方 / anthropic / gemini", "openai compatible with most third-party providers / anthropic / gemini")
                                            Component.onCompleted: presetText(provData.type || "")
                                        }
                                        SettingsField {
                                            label: tr("API 密钥", "API Key")
                                            placeholder: "sk-..."
                                            dotpath: "_prov_" + index + "_apiKey"
                                            isSecret: true
                                            Component.onCompleted: presetText(provData.apiKey || "")
                                        }
                                        SettingsField {
                                            label: tr("API 地址", "API Base URL")
                                            placeholder: "https://api.openai.com/v1"
                                            dotpath: "_prov_" + index + "_apiBase"
                                            description: tr("自定义端点地址，留空使用官方默认", "Custom endpoint URL, leave empty for official default")
                                            Component.onCompleted: presetText(provData.apiBase || "")
                                    }
                                }
                            }
                        }

                        }

                        Rectangle {
                            Layout.fillWidth: true
                            height: 42
                            radius: radiusMd
                            color: addHover.containsMouse ? (isDark ? "#0AFFFFFF" : "#08000000") : "transparent"
                            border.color: accent
                            border.width: 1
                            opacity: addHover.containsMouse ? 1.0 : 0.7

                            Behavior on color { ColorAnimation { duration: 150 } }
                            Behavior on opacity { NumberAnimation { duration: 150 } }

                            Text {
                                anchors.centerIn: parent
                                text: "+ " + strings.section_provider_add
                                color: accent
                                font.pixelSize: 13
                                font.weight: Font.Medium
                            }

                            MouseArea {
                                id: addHover
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton
                                scrollGestureEnabled: false
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root._addNewProvider()
                            }
                        }
                    }
                }

                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_channels

                    ColumnLayout {
                        width: parent.width
                        spacing: 18

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Telegram", "Telegram")
                            enabledPath: "channels.telegram.enabled"
                            fields: [
                                {"label": tr("Bot Token", "Bot Token"), "dotpath": "channels.telegram.token", "placeholder": "123456:ABC-DEF...", "isSecret": true},
                                {"label": tr("代理", "Proxy"), "dotpath": "channels.telegram.proxy", "placeholder": "socks5://127.0.0.1:1080"},
                                {"label": tr("回复引用原消息", "Reply To Message"), "dotpath": "channels.telegram.replyToMessage", "placeholder": "true / false"},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.telegram.allowFrom", "placeholder": "123456789, @name", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Discord", "Discord")
                            enabledPath: "channels.discord.enabled"
                            fields: [
                                {"label": tr("Bot Token", "Bot Token"), "dotpath": "channels.discord.token", "placeholder": "MTIz...", "isSecret": true},
                                {"label": tr("网关地址", "Gateway URL"), "dotpath": "channels.discord.gatewayUrl", "placeholder": "wss://gateway.discord.gg/?v=10&encoding=json"},
                                {"label": tr("意图位掩码", "Intents"), "dotpath": "channels.discord.intents", "placeholder": "37377", "inputType": "number"},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.discord.allowFrom", "placeholder": "user_id_1, user_id_2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("WhatsApp", "WhatsApp")
                            enabledPath: "channels.whatsapp.enabled"
                            fields: [
                                {"label": tr("桥接地址", "Bridge URL"), "dotpath": "channels.whatsapp.bridgeUrl", "placeholder": "ws://localhost:3001"},
                                {"label": tr("桥接令牌", "Bridge Token"), "dotpath": "channels.whatsapp.bridgeToken", "placeholder": tr("可选", "optional"), "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.whatsapp.allowFrom", "placeholder": "+8613800138000", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("飞书", "Feishu")
                            enabledPath: "channels.feishu.enabled"
                            fields: [
                                {"label": tr("应用 ID", "App ID"), "dotpath": "channels.feishu.appId", "placeholder": ""},
                                {"label": tr("应用密钥", "App Secret"), "dotpath": "channels.feishu.appSecret", "placeholder": "", "isSecret": true},
                                {"label": tr("加密 Key", "Encrypt Key"), "dotpath": "channels.feishu.encryptKey", "placeholder": tr("可选", "optional"), "isSecret": true},
                                {"label": tr("验证 Token", "Verification Token"), "dotpath": "channels.feishu.verificationToken", "placeholder": tr("可选", "optional"), "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.feishu.allowFrom", "placeholder": "open_id_1, open_id_2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Slack", "Slack")
                            enabledPath: "channels.slack.enabled"
                            fields: [
                                {"label": tr("Bot Token", "Bot Token"), "dotpath": "channels.slack.botToken", "placeholder": "xoxb-...", "isSecret": true},
                                {"label": tr("App Token", "App Token"), "dotpath": "channels.slack.appToken", "placeholder": "xapp-...", "isSecret": true}
                            ]
                            advancedFields: [
                                {"label": tr("线程回复", "Reply In Thread"), "dotpath": "channels.slack.replyInThread", "placeholder": "true / false"},
                                {"label": tr("反应表情", "React Emoji"), "dotpath": "channels.slack.reactEmoji", "placeholder": "eyes"},
                                {"label": tr("群组策略", "Group Policy"), "dotpath": "channels.slack.groupPolicy", "placeholder": "mention / open / allowlist"},
                                {"label": tr("模式", "Mode"), "dotpath": "channels.slack.mode", "placeholder": "socket"},
                                {"label": tr("Webhook 路径", "Webhook Path"), "dotpath": "channels.slack.webhookPath", "placeholder": "/slack/events"},
                                {"label": tr("用户只读 Token", "User Token Read Only"), "dotpath": "channels.slack.userTokenReadOnly", "placeholder": "true / false"},
                                {"label": tr("群组允许列表", "Group Allow From"), "dotpath": "channels.slack.groupAllowFrom", "placeholder": "C123, C456", "isList": true},
                                {"label": tr("私信开关", "DM Enabled"), "dotpath": "channels.slack.dm.enabled", "placeholder": "true / false"},
                                {"label": tr("私信策略", "DM Policy"), "dotpath": "channels.slack.dm.policy", "placeholder": "open / allowlist"},
                                {"label": tr("私信允许列表", "DM Allow From"), "dotpath": "channels.slack.dm.allowFrom", "placeholder": "U123, U456", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("钉钉", "DingTalk")
                            enabledPath: "channels.dingtalk.enabled"
                            fields: [
                                {"label": tr("Client ID", "Client ID"), "dotpath": "channels.dingtalk.clientId", "placeholder": ""},
                                {"label": tr("Client Secret", "Client Secret"), "dotpath": "channels.dingtalk.clientSecret", "placeholder": "", "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.dingtalk.allowFrom", "placeholder": "staff_id_1, staff_id_2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("QQ", "QQ")
                            enabledPath: "channels.qq.enabled"
                            fields: [
                                {"label": tr("应用 ID", "App ID"), "dotpath": "channels.qq.appId", "placeholder": ""},
                                {"label": tr("密钥", "Secret"), "dotpath": "channels.qq.secret", "placeholder": "", "isSecret": true},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.qq.allowFrom", "placeholder": "openid1, openid2", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("邮件", "Email")
                            enabledPath: "channels.email.enabled"
                            fields: [
                                {"label": tr("IMAP 主机", "IMAP Host"), "dotpath": "channels.email.imapHost", "placeholder": "imap.gmail.com"},
                                {"label": tr("IMAP 端口", "IMAP Port"), "dotpath": "channels.email.imapPort", "placeholder": "993", "inputType": "number"},
                                {"label": tr("IMAP 用户名", "IMAP Username"), "dotpath": "channels.email.imapUsername", "placeholder": ""},
                                {"label": tr("IMAP 密码", "IMAP Password"), "dotpath": "channels.email.imapPassword", "placeholder": "", "isSecret": true},
                                {"label": tr("SMTP 主机", "SMTP Host"), "dotpath": "channels.email.smtpHost", "placeholder": "smtp.gmail.com"},
                                {"label": tr("SMTP 端口", "SMTP Port"), "dotpath": "channels.email.smtpPort", "placeholder": "587", "inputType": "number"},
                                {"label": tr("SMTP 用户名", "SMTP Username"), "dotpath": "channels.email.smtpUsername", "placeholder": ""},
                                {"label": tr("SMTP 密码", "SMTP Password"), "dotpath": "channels.email.smtpPassword", "placeholder": "", "isSecret": true},
                                {"label": tr("发件地址", "From Address"), "dotpath": "channels.email.fromAddress", "placeholder": ""},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.email.allowFrom", "placeholder": "alice@example.com, bob@example.com", "isList": true}
                            ]
                            advancedFields: [
                                {"label": tr("IMAP 邮箱", "IMAP Mailbox"), "dotpath": "channels.email.imapMailbox", "placeholder": "INBOX"},
                                {"label": tr("IMAP SSL", "IMAP Use SSL"), "dotpath": "channels.email.imapUseSsl", "placeholder": "true / false"},
                                {"label": tr("SMTP TLS", "SMTP Use TLS"), "dotpath": "channels.email.smtpUseTls", "placeholder": "true / false"},
                                {"label": tr("SMTP SSL", "SMTP Use SSL"), "dotpath": "channels.email.smtpUseSsl", "placeholder": "true / false"},
                                {"label": tr("授权确认", "Consent Granted"), "dotpath": "channels.email.consentGranted", "placeholder": "true / false"},
                                {"label": tr("自动回复", "Auto Reply Enabled"), "dotpath": "channels.email.autoReplyEnabled", "placeholder": "true / false"},
                                {"label": tr("轮询间隔秒", "Poll Interval Seconds"), "dotpath": "channels.email.pollIntervalSeconds", "placeholder": "30", "inputType": "number"},
                                {"label": tr("标记已读", "Mark Seen"), "dotpath": "channels.email.markSeen", "placeholder": "true / false"},
                                {"label": tr("正文最大字符", "Max Body Chars"), "dotpath": "channels.email.maxBodyChars", "placeholder": "12000", "inputType": "number"},
                                {"label": tr("主题前缀", "Subject Prefix"), "dotpath": "channels.email.subjectPrefix", "placeholder": "Re: "}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("iMessage", "iMessage")
                            enabledPath: "channels.imessage.enabled"
                            fields: [
                                {"label": tr("轮询间隔", "Poll Interval"), "dotpath": "channels.imessage.pollInterval", "placeholder": "2.0", "inputType": "number"},
                                {"label": tr("服务", "Service"), "dotpath": "channels.imessage.service", "placeholder": "iMessage"},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.imessage.allowFrom", "placeholder": "+8613800138000", "isList": true}
                            ]
                        }

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Mochat", "Mochat")
                            enabledPath: "channels.mochat.enabled"
                            fields: [
                                {"label": tr("基础地址", "Base URL"), "dotpath": "channels.mochat.baseUrl", "placeholder": "https://mochat.io"},
                                {"label": tr("Claw 令牌", "Claw Token"), "dotpath": "channels.mochat.clawToken", "placeholder": "", "isSecret": true},
                                {"label": tr("Agent 用户 ID", "Agent User ID"), "dotpath": "channels.mochat.agentUserId", "placeholder": ""},
                                {"label": tr("允许列表", "Allow From"), "dotpath": "channels.mochat.allowFrom", "placeholder": "group1, group2", "isList": true}
                            ]
                            advancedFields: [
                                {"label": tr("Socket 地址", "Socket URL"), "dotpath": "channels.mochat.socketUrl", "placeholder": ""},
                                {"label": tr("Socket 路径", "Socket Path"), "dotpath": "channels.mochat.socketPath", "placeholder": "/socket.io"},
                                {"label": tr("禁用 Msgpack", "Disable Msgpack"), "dotpath": "channels.mochat.socketDisableMsgpack", "placeholder": "true / false", "inputType": "bool"},
                                {"label": tr("重连延迟毫秒", "Reconnect Delay Ms"), "dotpath": "channels.mochat.socketReconnectDelayMs", "placeholder": "1000", "inputType": "number"},
                                {"label": tr("最大重连延迟毫秒", "Max Reconnect Delay Ms"), "dotpath": "channels.mochat.socketMaxReconnectDelayMs", "placeholder": "10000", "inputType": "number"},
                                {"label": tr("连接超时毫秒", "Connect Timeout Ms"), "dotpath": "channels.mochat.socketConnectTimeoutMs", "placeholder": "10000", "inputType": "number"},
                                {"label": tr("刷新间隔毫秒", "Refresh Interval Ms"), "dotpath": "channels.mochat.refreshIntervalMs", "placeholder": "30000", "inputType": "number"},
                                {"label": tr("监视超时毫秒", "Watch Timeout Ms"), "dotpath": "channels.mochat.watchTimeoutMs", "placeholder": "25000", "inputType": "number"},
                                {"label": tr("监视上限", "Watch Limit"), "dotpath": "channels.mochat.watchLimit", "placeholder": "100", "inputType": "number"},
                                {"label": tr("重试延迟毫秒", "Retry Delay Ms"), "dotpath": "channels.mochat.retryDelayMs", "placeholder": "500", "inputType": "number"},
                                {"label": tr("最大重试次数", "Max Retry Attempts"), "dotpath": "channels.mochat.maxRetryAttempts", "placeholder": "0", "inputType": "number"},
                                {"label": tr("回复延迟模式", "Reply Delay Mode"), "dotpath": "channels.mochat.replyDelayMode", "placeholder": "off / non-mention"},
                                {"label": tr("回复延迟毫秒", "Reply Delay Ms"), "dotpath": "channels.mochat.replyDelayMs", "placeholder": "120000", "inputType": "number"},
                                {"label": tr("会话列表", "Sessions"), "dotpath": "channels.mochat.sessions", "placeholder": "session1, session2", "isList": true},
                                {"label": tr("面板列表", "Panels"), "dotpath": "channels.mochat.panels", "placeholder": "panel1, panel2", "isList": true}
                            ]
                        }
                    }
                }

                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_gateway

                    ColumnLayout {
                        width: parent.width
                        spacing: spacingMd

                        SettingsField { label: tr("主机", "Host"); dotpath: "gateway.host"; placeholder: "0.0.0.0" }
                        SettingsField { label: tr("端口", "Port"); dotpath: "gateway.port"; placeholder: "18790"; inputType: "number" }
                        SettingsToggle { label: tr("启用心跳", "Heartbeat Enabled"); dotpath: "gateway.heartbeat.enabled" }
                        SettingsField { label: tr("心跳间隔秒", "Heartbeat Interval Seconds"); dotpath: "gateway.heartbeat.intervalS"; placeholder: "1800"; inputType: "number" }
                    }
                }

                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_tools

                    ColumnLayout {
                        width: parent.width
                        spacing: spacingMd

                        Text {
                            text: tr("网页搜索", "Web Search")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        SettingsField { label: tr("搜索提供商", "Provider"); dotpath: "tools.web.search.provider"; placeholder: "tavily / brave" }
                        SettingsField { label: tr("Tavily API 密钥", "Tavily API Key"); dotpath: "tools.web.search.tavilyApiKey"; placeholder: "tvly-..."; isSecret: true }
                        SettingsField { label: tr("Brave API 密钥", "Brave API Key"); dotpath: "tools.web.search.braveApiKey"; placeholder: "BSA..."; isSecret: true }

                        Text {
                            text: tr("执行工具", "Exec")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField { label: tr("超时秒数", "Timeout"); dotpath: "tools.exec.timeout"; placeholder: "60"; inputType: "number" }

                        Text {
                            text: tr("向量嵌入", "Embedding")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField { label: tr("模型", "Model"); dotpath: "tools.embedding.model"; placeholder: "text-embedding-3-small" }
                        SettingsField { label: tr("API 密钥", "API Key"); dotpath: "tools.embedding.apiKey"; placeholder: "sk-..."; isSecret: true }
                        SettingsField { label: tr("基础地址", "Base URL"); dotpath: "tools.embedding.baseUrl"; placeholder: "https://api.openai.com/v1" }

                        SettingsField { label: tr("搜索最大结果数", "Web Search Max Results"); dotpath: "tools.web.search.maxResults"; placeholder: "5"; inputType: "number" }
                        SettingsField { label: tr("嵌入维度", "Embedding Dim"); dotpath: "tools.embedding.dim"; placeholder: "0"; inputType: "number" }

                        Text {
                            text: tr("图像生成", "Image Generation")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField { label: tr("API 密钥", "API Key"); dotpath: "tools.imageGeneration.apiKey"; placeholder: "AIza..."; isSecret: true }
                        SettingsField { label: tr("模型", "Model"); dotpath: "tools.imageGeneration.model"; placeholder: "gemini-2.0-flash-exp-image-generation" }
                        SettingsField { label: tr("基础地址", "Base URL"); dotpath: "tools.imageGeneration.baseUrl"; placeholder: "https://generativelanguage.googleapis.com/v1beta" }
                        Text {
                            text: tr("桌面自动化", "Desktop Automation")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsToggle { label: tr("启用桌面操作", "Enable Desktop Control"); dotpath: "tools.desktop.enabled" }
                        SettingsToggle { label: tr("限制到工作区", "Restrict To Workspace"); dotpath: "tools.restrictToWorkspace" }
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                }
            }
        }
    }

    Rectangle {
        id: saveButton
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: spacingXl
        anchors.rightMargin: spacingXl
        width: 120
        height: 40
        radius: radiusMd
        color: saveHover.containsMouse ? accentHover : accent
        z: 20

        Behavior on color { ColorAnimation { duration: 150 } }

        Text {
            anchors.centerIn: parent
            text: strings.settings_save
            color: "#FFFFFFFF"
            font.pixelSize: 14
            font.weight: Font.DemiBold
            font.letterSpacing: 0.2
        }

        MouseArea {
            id: saveHover
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            scrollGestureEnabled: false
            cursorShape: Qt.PointingHandCursor
            onClicked: root.saveAll()
        }
    }

    AppToast {
        id: toast
        anchors.top: saveButton.bottom
        anchors.right: saveButton.right
        anchors.topMargin: 8
        z: 21
        successBg: isDark ? "#1F7A4D" : "#16A34A"
        errorBg: isDark ? "#B84040" : "#DC2626"
        textColor: "#FFFFFF"
        duration: 2600
    }

    Connections {
        target: configService
        function onSaveError(msg) {
            toast.show(root._translateError(msg), false)
        }
    }
}
