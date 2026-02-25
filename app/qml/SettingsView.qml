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

    function tr(zh, en) {
        return isZh ? zh : en
    }

    ScrollView {
        id: settingsScroll
        anchors.fill: parent
        contentWidth: settingsScroll.availableWidth
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Item {
            width: settingsScroll.availableWidth
            implicitHeight: innerCol.implicitHeight + 80

            ColumnLayout {
                id: innerCol
                width: Math.min(Math.max(settingsScroll.availableWidth - 64, 320), 720)
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top
                anchors.topMargin: 40
                spacing: spacingXl

                // ── Agent Defaults ───────────────────────────────────────
                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_app

                    ColumnLayout {
                        spacing: spacingMd
                        width: parent.width

                        SettingsSelect {
                            label: strings.ui_language
                            dotpath: "ui.language"
                            options: [
                                { label: strings.ui_language_auto, value: "auto" },
                                { label: strings.ui_language_zh, value: "zh" },
                                { label: strings.ui_language_en, value: "en" }
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
                        spacing: spacingMd
                        width: parent.width

                        SettingsField {
                            label: tr("工作目录", "Workspace")
                            placeholder: "~/.bao/workspace"
                            dotpath: "agents.defaults.workspace"
                        }
                        SettingsField {
                            label: tr("模型", "Model")
                            placeholder: "e.g. openai/gpt-4o"
                            dotpath: "agents.defaults.model"
                        }
                        SettingsField {
                            label: tr("轻量模型", "Utility Model")
                            placeholder: "e.g. openrouter/google/gemini-flash-1.5"
                            dotpath: "agents.defaults.utilityModel"
                        }
                        SettingsField {
                            label: tr("体验模型", "Experience Model")
                            placeholder: "utility / main / none"
                            dotpath: "agents.defaults.experienceModel"
                        }
                        SettingsField {
                            label: tr("最大 Token", "Max Tokens")
                            placeholder: "8192"
                            dotpath: "agents.defaults.maxTokens"
                            inputType: "number"
                        }
                        SettingsField {
                            label: tr("温度", "Temperature")
                            placeholder: "0.1"
                            dotpath: "agents.defaults.temperature"
                            inputType: "number"
                        }
                        SettingsField {
                            label: tr("工具最大迭代次数", "Max Tool Iterations")
                            placeholder: "20"
                            dotpath: "agents.defaults.maxToolIterations"
                            inputType: "number"
                        }
                        SettingsField {
                            label: tr("记忆窗口", "Memory Window")
                            placeholder: "50"
                            dotpath: "agents.defaults.memoryWindow"
                            inputType: "number"
                        }
                    }
                }

                // ── Provider ─────────────────────────────────────────────
                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_provider

                    ColumnLayout {
                        spacing: spacingMd
                        width: parent.width

                        Text {
                            text: tr("提供商名称对应 config 里的 key（例如 openaiCompatible）", "Provider name is the key in config (e.g. openaiCompatible)")
                            color: textTertiary
                            font.pixelSize: 12
                            font.italic: true
                        }
                        SettingsField {
                            id: provNameField
                            label: tr("提供商名称", "Provider Name")
                            placeholder: "e.g. openaiCompatible"
                            dotpath: "_providerName"
                        }
                        SettingsField {
                            id: provTypeField
                            label: tr("类型", "Type")
                            placeholder: "openai / anthropic / gemini"
                            dotpath: "_providerType"
                        }
                        SettingsField {
                            id: provKeyField
                            label: tr("API 密钥", "API Key")
                            placeholder: "sk-..."
                            dotpath: "_providerApiKey"
                            isSecret: true
                        }
                        SettingsField {
                            id: provBaseField
                            label: tr("API 基础地址", "API Base URL")
                            placeholder: "https://api.openai.com/v1"
                            dotpath: "_providerApiBase"
                        }
                        SettingsField {
                            id: provModeField
                            label: tr("API 模式", "API Mode")
                            placeholder: "auto / responses / completions"
                            dotpath: "_providerApiMode"
                        }
                        Component.onCompleted: {
                            if (!configService) return
                            var p = configService.getFirstProvider()
                            if (p && p.name) {
                                provNameField.presetText(p.name)
                                provTypeField.presetText(p.type || "")
                                provKeyField.presetText(p.apiKey || "")
                                provBaseField.presetText(p.apiBase || "")
                                provModeField.presetText(p.apiMode || "")
                            }
                        }
                    }
                }

                // ── Channels ─────────────────────────────────────────────
                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_channels
                    ColumnLayout {
                        spacing: 18
                        width: parent.width

                        ChannelRow {
                            width: parent.width
                            channelName: tr("Telegram", "Telegram")
                            enabledPath: "channels.telegram.enabled"
                            fields: [
                                { label: tr("Bot Token", "Bot Token"), dotpath: "channels.telegram.token", placeholder: "123456:ABC-DEF...", isSecret: true },
                                { label: tr("代理", "Proxy"), dotpath: "channels.telegram.proxy", placeholder: tr("socks5://...（可选）", "socks5://... (optional)") }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("Discord", "Discord")
                            enabledPath: "channels.discord.enabled"
                            fields: [
                                { label: tr("Bot Token", "Bot Token"), dotpath: "channels.discord.token", placeholder: "MTIz...", isSecret: true }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("WhatsApp", "WhatsApp")
                            enabledPath: "channels.whatsapp.enabled"
                            fields: [
                                { label: tr("桥接地址", "Bridge URL"), dotpath: "channels.whatsapp.bridgeUrl", placeholder: "ws://localhost:3001" },
                                { label: tr("桥接 Token", "Bridge Token"), dotpath: "channels.whatsapp.bridgeToken", placeholder: tr("（可选）", "(optional)"), isSecret: true }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("飞书", "Feishu")
                            enabledPath: "channels.feishu.enabled"
                            fields: [
                                { label: tr("应用 ID", "App ID"), dotpath: "channels.feishu.appId", placeholder: "" },
                                { label: tr("应用 Secret", "App Secret"), dotpath: "channels.feishu.appSecret", placeholder: "", isSecret: true },
                                { label: tr("加密 Key", "Encrypt Key"), dotpath: "channels.feishu.encryptKey", placeholder: tr("（可选）", "(optional)"), isSecret: true },
                                { label: tr("验证 Token", "Verification Token"), dotpath: "channels.feishu.verificationToken", placeholder: tr("（可选）", "(optional)"), isSecret: true }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("Slack", "Slack")
                            enabledPath: "channels.slack.enabled"
                            fields: [
                                { label: tr("Bot Token", "Bot Token"), dotpath: "channels.slack.botToken", placeholder: "xoxb-...", isSecret: true },
                                { label: tr("App Token", "App Token"), dotpath: "channels.slack.appToken", placeholder: "xapp-...", isSecret: true },
                                { label: tr("线程内回复", "Reply In Thread"), dotpath: "channels.slack.replyInThread", placeholder: tr("true / false", "true / false") },
                                { label: tr("表情反应", "React Emoji"), dotpath: "channels.slack.reactEmoji", placeholder: "eyes" },
                                { label: tr("群组策略", "Group Policy"), dotpath: "channels.slack.groupPolicy", placeholder: "mention" }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("钉钉", "DingTalk")
                            enabledPath: "channels.dingtalk.enabled"
                            fields: [
                                { label: tr("Client ID", "Client ID"), dotpath: "channels.dingtalk.clientId", placeholder: "" },
                                { label: tr("Client Secret", "Client Secret"), dotpath: "channels.dingtalk.clientSecret", placeholder: "", isSecret: true }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("QQ", "QQ")
                            enabledPath: "channels.qq.enabled"
                            fields: [
                                { label: tr("应用 ID", "App ID"), dotpath: "channels.qq.appId", placeholder: "" },
                                { label: tr("密钥", "Secret"), dotpath: "channels.qq.secret", placeholder: "", isSecret: true }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("邮件", "Email")
                            enabledPath: "channels.email.enabled"
                            fields: [
                                { label: tr("IMAP 主机", "IMAP Host"), dotpath: "channels.email.imapHost", placeholder: "imap.gmail.com" },
                                { label: tr("IMAP 端口", "IMAP Port"), dotpath: "channels.email.imapPort", placeholder: "993", inputType: "number" },
                                { label: tr("IMAP 用户名", "IMAP Username"), dotpath: "channels.email.imapUsername", placeholder: "" },
                                { label: tr("IMAP 密码", "IMAP Password"), dotpath: "channels.email.imapPassword", placeholder: "", isSecret: true },
                                { label: tr("SMTP 主机", "SMTP Host"), dotpath: "channels.email.smtpHost", placeholder: "smtp.gmail.com" },
                                { label: tr("SMTP 端口", "SMTP Port"), dotpath: "channels.email.smtpPort", placeholder: "587", inputType: "number" },
                                { label: tr("SMTP 用户名", "SMTP Username"), dotpath: "channels.email.smtpUsername", placeholder: "" },
                                { label: tr("SMTP 密码", "SMTP Password"), dotpath: "channels.email.smtpPassword", placeholder: "", isSecret: true },
                                { label: tr("发件地址", "From Address"), dotpath: "channels.email.fromAddress", placeholder: "" }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("iMessage", "iMessage")
                            enabledPath: "channels.imessage.enabled"
                            fields: [
                                { label: tr("轮询间隔（秒）", "Poll Interval (s)"), dotpath: "channels.imessage.pollInterval", placeholder: "2.0", inputType: "number" },
                                { label: tr("服务", "Service"), dotpath: "channels.imessage.service", placeholder: "iMessage" }
                            ]
                        }
                        ChannelRow {
                            width: parent.width
                            channelName: tr("Mochat", "Mochat")
                            enabledPath: "channels.mochat.enabled"
                            fields: [
                                { label: tr("基础地址", "Base URL"), dotpath: "channels.mochat.baseUrl", placeholder: "https://mochat.io" },
                                { label: tr("Claw Token", "Claw Token"), dotpath: "channels.mochat.clawToken", placeholder: "", isSecret: true },
                                { label: tr("Agent 用户 ID", "Agent User ID"), dotpath: "channels.mochat.agentUserId", placeholder: "" }
                            ]
                        }
                    }
                }
                // ── Tools ─────────────────────────────────────────────────
                SettingsSection {
                    Layout.fillWidth: true
                    title: strings.section_tools
                    ColumnLayout {
                        spacing: spacingMd
                        width: parent.width
                        Text {
                            text: tr("网页搜索", "Web Search")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        SettingsField {
                            label: tr("搜索提供商", "Search Provider")
                            placeholder: "tavily / brave"
                            dotpath: "tools.web.search.provider"
                        }
                        SettingsField {
                            label: tr("Tavily API 密钥", "Tavily API Key")
                            placeholder: "tvly-..."
                            dotpath: "tools.web.search.tavilyApiKey"
                            isSecret: true
                        }
                        SettingsField {
                            label: tr("Brave API 密钥", "Brave API Key")
                            placeholder: "BSA..."
                            dotpath: "tools.web.search.braveApiKey"
                            isSecret: true
                        }
                        Text {
                            text: tr("执行", "Exec")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField {
                            label: tr("超时（秒）", "Timeout (s)")
                            placeholder: "60"
                            dotpath: "tools.exec.timeout"
                            inputType: "number"
                        }
                        Text {
                            text: tr("向量嵌入", "Embedding")
                            color: textSecondary
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.topMargin: 8
                        }
                        SettingsField {
                            label: tr("嵌入模型", "Embedding Model")
                            placeholder: "e.g. text-embedding-3-small"
                            dotpath: "tools.embedding.model"
                        }
                        SettingsField {
                            label: tr("嵌入 API 密钥", "Embedding API Key")
                            placeholder: "sk-..."
                            dotpath: "tools.embedding.apiKey"
                            isSecret: true
                        }
                        SettingsField {
                            label: tr("嵌入基础地址", "Embedding Base URL")
                            placeholder: "https://api.openai.com/v1"
                            dotpath: "tools.embedding.baseUrl"
                        }
                    }
                }
                // ── Save row ─────────────────────────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    Item { Layout.fillWidth: true }
                    Text {
                        id: statusText
                        text: ""
                        color: text.startsWith("\u2713") ? statusSuccess : statusError
                        font.pixelSize: 14
                        visible: text !== ""
                        Timer {
                            id: clearStatus
                            interval: 3000
                            onTriggered: statusText.text = ""
                        }
                    }
                    Rectangle {
                        width: 120; height: 40; radius: radiusMd
                        color: saveHover.containsMouse ? accentHover : accent
                        Behavior on color { ColorAnimation { duration: 150 } }
                        Text {
                            anchors.centerIn: parent
                            text: strings.settings_save
                            color: "#FFFFFF"
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.3
                        }
                        MouseArea {
                            id: saveHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.saveAll()
                        }
                    }
                }
            }
        }
    }

    function saveAll() {
        if (!configService) return
        var changes = {}
        collectFields(innerCol, changes)
        var pName = changes["_providerName"]
        var providerFields = ["_providerType", "_providerApiKey", "_providerApiBase", "_providerApiMode"]
        var realKeys = ["type", "apiKey", "apiBase", "apiMode"]
        for (var i = 0; i < providerFields.length; i++) {
            var val = changes[providerFields[i]]
            if (pName && val) changes["providers." + pName + "." + realKeys[i]] = val
            delete changes[providerFields[i]]
        }
        delete changes["_providerName"]

        if (changes.hasOwnProperty("ui.language")) {
            changes["ui"] = {"language": changes["ui.language"]}
            delete changes["ui.language"]
        }

        var ok = configService.save(changes)
        if (ok) {
            statusText.text = "\u2713 " + strings.settings_saved_hint
        } else {
            statusText.text = "\u2717 " + strings.settings_save_failed
        }
        clearStatus.restart()
    }

    function collectFields(item, changes) {
        for (var i = 0; i < item.children.length; i++) {
            var child = item.children[i]
            if (child.hasOwnProperty("dotpath") && child.hasOwnProperty("currentValue")) {
                var v = child.currentValue
                if (v !== undefined && v !== null && String(v) !== "") {
                    changes[child.dotpath] = v
                }
            }
            collectFields(child, changes)
        }
    }
}
