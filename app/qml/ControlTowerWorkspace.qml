import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    objectName: "controlTowerWorkspaceRoot"

    property bool active: false
    property var supervisorService: null
    property var appRoot: null

    readonly property bool hasSupervisorService: supervisorService !== null
    readonly property var overview: hasSupervisorService ? (supervisorService.overview || {}) : ({})
    readonly property var profiles: hasSupervisorService ? (supervisorService.profiles || []) : []
    readonly property var workingItems: hasSupervisorService ? (supervisorService.workingItems || []) : []
    readonly property var completedItems: hasSupervisorService ? (supervisorService.completedItems || []) : []
    readonly property var automationItems: hasSupervisorService ? (supervisorService.automationItems || []) : []
    readonly property var attentionItems: hasSupervisorService ? (supervisorService.attentionItems || []) : []
    readonly property var selectedProfile: hasSupervisorService ? (supervisorService.selectedProfile || {}) : ({})
    readonly property bool hasSelectedProfile: Object.keys(selectedProfile).length > 0
    readonly property bool isChinese: typeof effectiveLang === "string" ? effectiveLang === "zh" : uiLanguage === "zh"
    readonly property color panelFill: bgCard
    readonly property color panelBorder: isDark ? "#20FFFFFF" : "#12000000"
    readonly property color sectionFill: isDark ? "#130E0B" : "#FFFCF8"
    readonly property color sectionBorder: isDark ? "#16FFFFFF" : "#14000000"
    readonly property color tileFill: isDark ? "#17110D" : "#FFFAF5"
    readonly property color tileHover: isDark ? "#1E1511" : "#FFF3E8"
    readonly property color tileActive: isDark ? "#241913" : "#FFEEDC"
    function refreshIfNeeded() {
        if (active && hasSupervisorService)
            supervisorService.refresh()
    }

    function accentColor(key) {
        switch (String(key || "")) {
        case "telegram":
            return isDark ? Qt.rgba(0.33, 0.73, 1.0, 1.0) : Qt.rgba(0.00, 0.60, 0.96, 1.0)
        case "discord":
            return isDark ? Qt.rgba(0.56, 0.60, 1.0, 1.0) : Qt.rgba(0.39, 0.44, 1.0, 1.0)
        case "whatsapp":
            return isDark ? Qt.rgba(0.31, 0.90, 0.53, 1.0) : Qt.rgba(0.00, 0.78, 0.34, 1.0)
        case "feishu":
            return isDark ? Qt.rgba(0.54, 0.71, 1.0, 1.0) : Qt.rgba(0.17, 0.52, 0.98, 1.0)
        case "slack":
            return isDark ? Qt.rgba(0.99, 0.58, 0.76, 1.0) : Qt.rgba(0.83, 0.12, 0.44, 1.0)
        case "qq":
            return isDark ? Qt.rgba(0.61, 0.67, 1.0, 1.0) : Qt.rgba(0.24, 0.40, 0.98, 1.0)
        case "dingtalk":
            return isDark ? Qt.rgba(0.38, 0.74, 1.0, 1.0) : Qt.rgba(0.00, 0.62, 0.97, 1.0)
        case "imessage":
            return isDark ? Qt.rgba(0.54, 0.70, 1.0, 1.0) : Qt.rgba(0.12, 0.62, 1.0, 1.0)
        case "subagent":
            return isDark ? Qt.rgba(1.0, 0.72, 0.24, 1.0) : Qt.rgba(0.96, 0.57, 0.00, 1.0)
        case "cron":
            return isDark ? Qt.rgba(1.0, 0.66, 0.18, 1.0) : Qt.rgba(0.99, 0.58, 0.00, 1.0)
        case "heartbeat":
            return isDark ? Qt.rgba(0.20, 0.90, 0.56, 1.0) : Qt.rgba(0.00, 0.82, 0.40, 1.0)
        case "system":
            return isDark ? Qt.rgba(0.53, 0.82, 1.0, 1.0) : Qt.rgba(0.18, 0.67, 0.98, 1.0)
        default:
            return accent
        }
    }

    function channelLabel(key) {
        switch (String(key || "")) {
        case "desktop":
            return isChinese ? "桌面" : "Desktop"
        case "telegram":
            return "Telegram"
        case "discord":
            return "Discord"
        case "whatsapp":
            return "WhatsApp"
        case "feishu":
            return isChinese ? "飞书" : "Feishu"
        case "slack":
            return "Slack"
        case "qq":
            return "QQ"
        case "dingtalk":
            return isChinese ? "钉钉" : "DingTalk"
        case "imessage":
            return "iMessage"
        case "subagent":
            return isChinese ? "子代理" : "Subagent"
        case "cron":
            return "Cron"
        case "heartbeat":
            return isChinese ? "检查" : "Heartbeat"
        default:
            return isChinese ? "系统" : "System"
        }
    }

    function channelIconSource(key) {
        switch (String(key || "")) {
        case "telegram":
        case "discord":
        case "whatsapp":
        case "feishu":
        case "slack":
        case "qq":
        case "dingtalk":
        case "imessage":
            return "../resources/icons/channel-" + String(key || "") + ".svg"
        case "desktop":
            return "../resources/icons/sidebar-monitor.svg"
        case "subagent":
            return "../resources/icons/sidebar-subagent.svg"
        case "cron":
            return "../resources/icons/sidebar-cron.svg"
        case "heartbeat":
            return "../resources/icons/sidebar-heartbeat.svg"
        default:
            return "../resources/icons/sidebar-chat.svg"
        }
    }

    function icon(path) {
        return "../resources/icons/vendor/iconoir/" + path + ".svg"
    }

    function labIcon(path) {
        return "../resources/icons/vendor/lucide-lab/" + path + ".svg"
    }

    function workspaceString(key, fallbackZh, fallbackEn) {
        if (typeof strings === "object" && strings !== null) {
            var value = strings[key]
            if (value !== undefined && value !== null && String(value))
                return String(value)
        }
        return isChinese ? fallbackZh : fallbackEn
    }

    function solidIcon(path) {
        return "../resources/icons/" + path + ".svg"
    }

    function sectionTitle(kind) {
        switch (kind) {
        case "working":
            return isChinese ? "正在工作" : "Working"
        case "completed":
            return isChinese ? "近 2 小时完成" : "Completed · 2h"
        case "attention":
            return isChinese ? "待处理" : "Needs Review"
        case "automation":
            return isChinese ? "自动化" : "Automation"
        default:
            return ""
        }
    }

    function sectionAccentKey(kind) {
        if (kind === "working")
            return "subagent"
        if (kind === "completed")
            return "desktop"
        if (kind === "attention")
            return "system"
        return "cron"
    }

    function sectionItems(kind) {
        if (kind === "working")
            return workingItems
        if (kind === "completed")
            return completedItems
        if (kind === "automation")
            return automationItems
        return attentionItems
    }

    function profileIsCurrent(profile) {
        return String((profile || {}).id || "") === String(overview.liveProfileId || "")
    }

    function profileIsSelected(profile) {
        return hasSelectedProfile && String((profile || {}).id || "") === String(selectedProfile.id || "")
    }

    function profileAccentKey(profile) {
        var channels = (profile || {}).channelKeys || []
        if (profileIsCurrent(profile) && Boolean(profile.isGatewayLive))
            return channels.length > 0 ? String(channels[0]) : "subagent"
        if (Number(profile.attentionCount || 0) > 0)
            return "heartbeat"
        return channels.length > 0 ? String(channels[0]) : "system"
    }

    function profileTimeLabel(profile) {
        var label = String((profile || {}).updatedLabel || "")
        if (label !== "")
            return label
        label = String((profile || {}).snapshotLabel || "")
        if (label !== "")
            return label
        return isChinese ? "未观测" : "No snapshot"
    }

    function profileActionText(profile) {
        if (profileIsCurrent(profile))
            return isChinese ? "当前" : "Current"
        return isChinese ? "切换" : "Switch"
    }

    function liveProfile() {
        var liveId = String(overview.liveProfileId || "")
        for (var index = 0; index < profiles.length; index += 1) {
            if (String(profiles[index].id || "") === liveId)
                return profiles[index]
        }
        return ({})
    }

    function sharedGatewayLive() {
        return Boolean((liveProfile() || {}).isGatewayLive)
    }

    function scopeTitle() {
        return workspaceString("workspace_control_tower_title", "指挥舱", "Control Tower")
    }

    function scopeCaption() {
        return workspaceString(
            "workspace_control_tower_caption",
            "统一查看分身回复、自动化与待处理事项。",
            "Monitor replies, automation, and review items across profiles."
        )
    }

    function totalSessionCount() {
        if (hasSelectedProfile)
            return Number(selectedProfile.totalSessionCount || 0)
        var total = 0
        for (var index = 0; index < profiles.length; index += 1)
            total += Number(profiles[index].totalSessionCount || 0)
        return total
    }

    function scopeMetricCards() {
        return [
            {
                "label": isChinese ? "分身" : "Profiles",
                "value": hasSelectedProfile ? 1 : Number(profiles.length || 0),
                "accentKey": "system",
                "iconSource": root.solidIcon("sidebar-profiles-solid")
            },
            {
                "label": isChinese ? "总会话" : "Sessions",
                "value": totalSessionCount(),
                "accentKey": "desktop",
                "iconSource": root.solidIcon("sidebar-chat-solid")
            },
            {
                "label": isChinese ? "工作中" : "Working",
                "value": Number(workingItems.length || 0),
                "accentKey": "subagent",
                "iconSource": root.solidIcon("sidebar-monitor-solid")
            },
            {
                "label": isChinese ? "自动化" : "Automation",
                "value": Number(automationItems.length || 0),
                "accentKey": "cron",
                "iconSource": root.solidIcon("sidebar-cron-solid")
            }
        ]
    }

    function itemTimeLabel(item) {
        return String((item || {}).updatedLabel || (item || {}).relativeLabel || "")
    }

    function itemGlyphSources(item) {
        var sources = []
        var keys = (item || {}).channelKeys || []
        for (var index = 0; index < keys.length; index += 1) {
            var source = root.channelIconSource(String(keys[index] || ""))
            if (source !== "" && sources.indexOf(source) === -1)
                sources.push(source)
        }
        if (sources.length === 0) {
            var fallback = String((item || {}).glyphSource || "")
            if (fallback !== "")
                sources.push(fallback)
        }
        return sources
    }

    function emptyTitle(kind) {
        if (kind === "working") {
            if (!sharedGatewayLive())
                return isChinese ? "网关未启动" : "Gateway is not running"
            return isChinese ? "当前无人工作" : "No active workers"
        }
        if (kind === "completed")
            return isChinese ? "近 2 小时没有完成" : "No completions in the last 2 hours"
        if (kind === "automation")
            return isChinese ? "还没有自动化任务" : "No automation tasks yet"
        return isChinese ? "当前没有要处理的问题" : "Nothing needs review right now"
    }

    function selectProfile(profileId) {
        if (hasSupervisorService)
            supervisorService.selectProfile(profileId)
    }

    function activateProfile(profileId) {
        if (hasSupervisorService)
            supervisorService.activateProfile(profileId)
    }

    function openItem(item) {
        if (!hasSupervisorService || !Boolean((item || {}).canOpen))
            return
        supervisorService.selectItem(String(item.id || ""))
        supervisorService.openSelectedTarget()
    }

    onActiveChanged: refreshIfNeeded()

    Rectangle {
        anchors.fill: parent
        anchors.margins: 16
        radius: 30
        color: panelFill
        border.width: 1
        border.color: panelBorder
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 18

        CalloutPanel {
            Layout.fillWidth: true
            panelColor: isDark ? "#15100D" : "#FFF7F0"
            panelBorderColor: isDark ? "#22FFFFFF" : "#14000000"
            overlayColor: isDark ? "#0BFFFFFF" : "#08FFFFFF"
            overlayVisible: true
            sideGlowVisible: false
            accentBlobVisible: false
            padding: 16

            ColumnLayout {
                width: parent.width
                spacing: 14

                Item {
                    Layout.fillWidth: true
                    implicitHeight: 52

                    Row {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        WorkspaceHeroIcon {
                            implicitWidth: 48
                            implicitHeight: 48
                            iconSize: 32
                            iconSource: root.solidIcon("sidebar-control-tower-solid")
                            fillColor: isDark ? "#241710" : "#F6E7D6"
                            outlineColor: isDark ? "#342116" : "#EBC9A0"
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2

                            Text {
                                objectName: "controlTowerScopeTitle"
                                text: root.scopeTitle()
                                color: textPrimary
                                font.pixelSize: typeTitle - 1
                                font.weight: weightBold
                            }

                            Text {
                                text: root.scopeCaption()
                                color: textSecondary
                                font.pixelSize: typeMeta
                                maximumLineCount: 1
                                elide: Text.ElideRight
                            }
                        }
                    }

                    PillActionButton {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: isChinese ? "刷新" : "Refresh"
                        iconSource: root.icon("clock-rotate-right")
                        fillColor: "transparent"
                        hoverFillColor: bgCardHover
                        outlineColor: borderSubtle
                        textColor: textSecondary
                        outlined: true
                        minHeight: 34
                        horizontalPadding: 18
                        onClicked: root.refreshIfNeeded()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14

                    Repeater {
                        model: root.scopeMetricCards()

                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 66
                            radius: 20
                            color: isDark ? "#120E0C" : "#FFFCF8"
                            border.width: 1
                            border.color: isDark ? "#18FFFFFF" : "#12000000"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                anchors.rightMargin: 16
                                spacing: 12

                                Item {
                                    implicitWidth: 42
                                    implicitHeight: 42

                                    AppIcon {
                                        anchors.centerIn: parent
                                        width: 28
                                        height: 28
                                        source: String(modelData.iconSource || "")
                                        sourceSize: Qt.size(width, height)
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1

                                    Text {
                                        text: String(modelData.value)
                                        color: textPrimary
                                        font.pixelSize: typeTitle - 1
                                        font.weight: weightBold
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: String(modelData.label)
                                        color: textSecondary
                                        font.pixelSize: typeCaption
                                        font.weight: weightMedium
                                        elide: Text.ElideRight
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            spacing: 14

            handle: WorkspaceSplitHandle {}

            Item {
                SplitView.preferredWidth: 296
                SplitView.minimumWidth: 272
                SplitView.maximumWidth: 328
                SplitView.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 14

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            objectName: "controlTowerProfilesTitle"
                            text: isChinese ? "分身列表" : "Profiles"
                            color: textPrimary
                            font.pixelSize: typeBody
                            font.weight: weightBold
                        }

                        Item { Layout.fillWidth: true }

                        Rectangle {
                            implicitWidth: profileCountText.implicitWidth + 16
                            implicitHeight: 26
                            radius: 13
                            color: isDark ? "#18110D" : "#FFF7EE"
                            border.width: 1
                            border.color: sectionBorder

                            Text {
                                id: profileCountText
                                anchors.centerIn: parent
                                text: isChinese
                                      ? Number(profiles.length || 0) + " 个分身"
                                      : Number(profiles.length || 0) + " profiles"
                                color: textSecondary
                                font.pixelSize: typeCaption
                                font.weight: weightMedium
                            }
                        }
                    }

                    ScrollView {
                        id: profileScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: profileScroll.availableWidth
                            spacing: 14

                            Repeater {
                                model: profiles

                                delegate: Rectangle {
                                    required property var modelData
                                    objectName: "profileCard_" + String(modelData.id || "")

                                    width: parent.width
                                    implicitHeight: 160
                                    radius: 22
                                    color: root.profileIsSelected(modelData)
                                           ? tileActive
                                           : (profileMouse.containsMouse ? tileHover : tileFill)
                                    border.width: root.profileIsSelected(modelData) ? 1.5 : 1
                                    border.color: root.profileIsSelected(modelData)
                                                  ? root.accentColor(root.profileAccentKey(modelData))
                                                  : (isDark ? "#16FFFFFF" : "#12000000")

                                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                    MouseArea {
                                        id: profileMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.selectProfile(String(modelData.id || ""))
                                    }

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 16
                                        spacing: 14

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 12

                                            WorkerToken {
                                                avatarSource: String(modelData.avatarSource || "")
                                                variant: "primary"
                                                ringColor: root.accentColor(root.profileAccentKey(modelData))
                                                glyphSource: root.channelIconSource((modelData.channelKeys || []).length > 0 ? modelData.channelKeys[0] : "desktop")
                                                statusKey: Number(modelData.attentionCount || 0) > 0
                                                           ? "error"
                                                           : (Boolean(modelData.isGatewayLive) ? "running" : "idle")
                                                active: root.profileIsSelected(modelData)
                                            }

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 6

                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 8

                                                    Text {
                                                        text: String(modelData.displayName || "")
                                                        color: textPrimary
                                                        font.pixelSize: typeBody
                                                        font.weight: weightBold
                                                        elide: Text.ElideRight
                                                    }

                                                    Rectangle {
                                                        implicitWidth: profileTimeText.implicitWidth + 12
                                                        implicitHeight: 22
                                                        radius: 11
                                                        color: isDark ? "#1A120E" : "#FFF5EA"
                                                        border.width: 1
                                                        border.color: isDark ? "#22FFFFFF" : "#14000000"

                                                        Text {
                                                            id: profileTimeText
                                                            anchors.centerIn: parent
                                                            text: root.profileTimeLabel(modelData)
                                                            color: textTertiary
                                                            font.pixelSize: typeCaption
                                                            font.weight: weightMedium
                                                        }
                                                    }

                                                    Item { Layout.fillWidth: true }

                                                    PillActionButton {
                                                        objectName: "profileActivateButton_" + String(modelData.id || "")
                                                        text: root.profileActionText(modelData)
                                                        buttonEnabled: !root.profileIsCurrent(modelData)
                                                        fillColor: root.profileIsCurrent(modelData) ? "transparent" : accent
                                                        hoverFillColor: root.profileIsCurrent(modelData) ? bgCardHover : accentHover
                                                        outlineColor: root.profileIsCurrent(modelData) ? statusSuccess : accent
                                                        textColor: root.profileIsCurrent(modelData) ? statusSuccess : "#FFFFFFFF"
                                                        outlined: root.profileIsCurrent(modelData)
                                                        horizontalPadding: 16
                                                        minHeight: 28
                                                        onClicked: root.activateProfile(String(modelData.id || ""))
                                                    }
                                                }

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: String(modelData.statusSummary || "")
                                                    color: textSecondary
                                                    font.pixelSize: typeCaption
                                                    font.weight: weightMedium
                                                    wrapMode: Text.WordWrap
                                                    maximumLineCount: 2
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6

                                            Repeater {
                                                model: [
                                                    {
                                                        "label": isChinese ? "会话" : "Sessions",
                                                        "value": Number(modelData.totalSessionCount || 0),
                                                        "accentKey": "desktop"
                                                    },
                                                    {
                                                        "label": isChinese ? "工作中" : "Working",
                                                        "value": Number(modelData.workingCount || 0),
                                                        "accentKey": "subagent"
                                                    },
                                                    {
                                                        "label": isChinese ? "自动化" : "Automation",
                                                        "value": Number(modelData.automationCount || 0),
                                                        "accentKey": "cron"
                                                    }
                                                ]

                                                delegate: Rectangle {
                                                    required property var modelData
                                                    implicitWidth: metricRow.implicitWidth + 18
                                                    implicitHeight: 34
                                                    radius: 14
                                                    color: isDark ? "#140E0B" : "#FFF8F1"
                                                    border.width: 1
                                                    border.color: isDark ? "#14FFFFFF" : "#12000000"

                                                    RowLayout {
                                                        id: metricRow
                                                        anchors.centerIn: parent
                                                        spacing: 5

                                                        Text {
                                                            text: String(modelData.value)
                                                            color: textPrimary
                                                            font.pixelSize: typeCaption
                                                            font.weight: weightBold
                                                        }

                                                        Text {
                                                            text: String(modelData.label)
                                                            color: textSecondary
                                                            font.pixelSize: typeCaption
                                                            font.weight: weightMedium
                                                        }
                                                    }
                                                }
                                            }

                                            Item { Layout.fillWidth: true }
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8

                                            Text {
                                                text: isChinese ? "渠道" : "Channels"
                                                color: textTertiary
                                                font.pixelSize: typeCaption
                                                font.weight: weightMedium
                                            }

                                            Repeater {
                                                model: modelData.channelKeys || []

                                                delegate: Rectangle {
                                                    required property var modelData
                                                    width: 24
                                                    height: 24
                                                    radius: 12
                                                    color: Qt.rgba(root.accentColor(String(modelData || "")).r,
                                                                   root.accentColor(String(modelData || "")).g,
                                                                   root.accentColor(String(modelData || "")).b,
                                                                   isDark ? 0.18 : 0.12)
                                                    border.width: 1
                                                    border.color: root.accentColor(String(modelData || ""))

                                                    AppIcon {
                                                        anchors.centerIn: parent
                                                        width: 14
                                                        height: 14
                                                        source: root.channelIconSource(String(modelData || ""))
                                                        sourceSize: Qt.size(width, height)
                                                    }

                                                    ToolTip.visible: channelMouse.containsMouse
                                                    ToolTip.text: root.channelLabel(String(modelData || ""))

                                                    MouseArea {
                                                        id: channelMouse
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        acceptedButtons: Qt.NoButton
                                                    }
                                                }
                                            }

                                            Item { Layout.fillWidth: true }

                                            Rectangle {
                                                visible: Number(modelData.totalChildSessionCount || 0) > 0
                                                implicitWidth: childCountText.implicitWidth + 14
                                                implicitHeight: 24
                                                radius: 12
                                                color: isDark ? "#18120E" : "#FFF6EA"
                                                border.width: 1
                                                border.color: root.accentColor("subagent")

                                                Text {
                                                    id: childCountText
                                                    anchors.centerIn: parent
                                                    text: isChinese
                                                          ? Number(modelData.totalChildSessionCount || 0) + " 个子代理"
                                                          : Number(modelData.totalChildSessionCount || 0) + " subagents"
                                                    color: textSecondary
                                                    font.pixelSize: typeCaption
                                                    font.weight: weightMedium
                                                }
                                            }

                                            Rectangle {
                                                visible: Number(modelData.attentionCount || 0) > 0
                                                implicitWidth: attentionCountText.implicitWidth + 14
                                                implicitHeight: 24
                                                radius: 12
                                                color: isDark ? "#24130F" : "#FFF1E8"
                                                border.width: 1
                                                border.color: statusError

                                                Text {
                                                    id: attentionCountText
                                                    anchors.centerIn: parent
                                                    text: isChinese
                                                          ? Number(modelData.attentionCount || 0) + " 个待处理"
                                                          : Number(modelData.attentionCount || 0) + " need review"
                                                    color: statusError
                                                    font.pixelSize: typeCaption
                                                    font.weight: weightMedium
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                SplitView.fillWidth: true
                SplitView.fillHeight: true

                ScrollView {
                    id: overviewScroll
                    anchors.fill: parent
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                    ColumnLayout {
                        width: overviewScroll.availableWidth
                        spacing: 16

                        Repeater {
                            model: ["working", "completed", "attention", "automation"]

                            delegate: Rectangle {
                                required property string modelData
                                readonly property string sectionKind: modelData
                                readonly property var laneItems: root.sectionItems(sectionKind)

                                Layout.fillWidth: true
                                implicitHeight: laneItems.length === 0 ? 112 : laneHeader.implicitHeight + laneGrid.implicitHeight + 34
                                radius: 24
                                color: tileFill
                                border.width: 1
                                border.color: isDark ? "#14FFFFFF" : "#12000000"

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 16
                                    spacing: 14

                                    RowLayout {
                                        id: laneHeader
                                        Layout.fillWidth: true
                                        spacing: 12

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4

                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 8

                                                Text {
                                                    text: root.sectionTitle(sectionKind)
                                                    color: textPrimary
                                                    font.pixelSize: typeBody
                                                    font.weight: weightBold
                                                }

                                                Rectangle {
                                                    implicitWidth: laneCountText.implicitWidth + 14
                                                    implicitHeight: 24
                                                    radius: 12
                                                    color: isDark ? "#18120E" : "#FFF5EA"
                                                    border.width: 1
                                                    border.color: root.accentColor(root.sectionAccentKey(sectionKind))

                                                    Text {
                                                        id: laneCountText
                                                        anchors.centerIn: parent
                                                        text: Number(laneItems.length || 0)
                                                        color: textPrimary
                                                        font.pixelSize: typeCaption
                                                        font.weight: weightBold
                                                    }
                                                }
                                            }

                                        }

                                        Item { Layout.fillWidth: true }
                                    }

                                    Rectangle {
                                        visible: laneItems.length === 0
                                        Layout.fillWidth: true
                                        implicitHeight: 56
                                        radius: 16
                                        color: isDark ? "#140E0B" : "#FFF8F2"
                                        border.width: 1
                                        border.color: isDark ? "#14FFFFFF" : "#12000000"

                                        Column {
                                            anchors.centerIn: parent
                                            spacing: 0

                                            Text {
                                                anchors.horizontalCenter: parent.horizontalCenter
                                                text: root.emptyTitle(sectionKind)
                                                color: textPrimary
                                                font.pixelSize: typeLabel
                                                font.weight: weightBold
                                            }

                                        }
                                    }

                                    GridLayout {
                                        id: laneGrid
                                        visible: laneItems.length > 0
                                        Layout.fillWidth: true
                                        columns: Math.max(1, Math.min(4, Math.floor((width + columnSpacing) / 176)))
                                        columnSpacing: 14
                                        rowSpacing: 12

                                        Repeater {
                                            model: laneItems

                                            delegate: Rectangle {
                                                required property var modelData
                                                Layout.fillWidth: true
                                                Layout.preferredWidth: laneGrid.columns > 1
                                                                       ? (laneGrid.width - laneGrid.columnSpacing * (laneGrid.columns - 1)) / laneGrid.columns
                                                                       : laneGrid.width
                                                implicitHeight: 62
                                                radius: 16
                                                color: laneItemMouse.containsMouse && Boolean(modelData.canOpen)
                                                       ? tileActive
                                                       : tileHover
                                                border.width: 1
                                                border.color: Boolean(modelData.canOpen)
                                                              ? Qt.rgba(root.accentColor(String(modelData.accentKey || modelData.visualChannel || "system")).r,
                                                                        root.accentColor(String(modelData.accentKey || modelData.visualChannel || "system")).g,
                                                                        root.accentColor(String(modelData.accentKey || modelData.visualChannel || "system")).b,
                                                                        isDark ? 0.28 : 0.18)
                                                              : (isDark ? "#14FFFFFF" : "#12000000")

                                                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                                GridLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 7
                                                    columns: 3
                                                    rows: 2
                                                    columnSpacing: 8
                                                    rowSpacing: 0

                                                    WorkerToken {
                                                        Layout.row: 0
                                                        Layout.column: 0
                                                        Layout.rowSpan: 2
                                                        Layout.alignment: Qt.AlignTop
                                                        avatarSource: String(modelData.avatarSource || "")
                                                        variant: "mini"
                                                        ringColor: root.accentColor(String(modelData.accentKey || modelData.visualChannel || "system"))
                                                        glyphSources: root.itemGlyphSources(modelData)
                                                        glyphSource: String(modelData.glyphSource || "")
                                                        statusKey: String(modelData.statusKey || "idle")
                                                        active: laneItemMouse.containsMouse && Boolean(modelData.canOpen)
                                                    }

                                                    Text {
                                                        Layout.row: 0
                                                        Layout.column: 1
                                                        Layout.fillWidth: true
                                                        text: String(modelData.title || "")
                                                        color: textPrimary
                                                        font.pixelSize: typeMeta
                                                        font.weight: weightBold
                                                        elide: Text.ElideRight
                                                        verticalAlignment: Text.AlignBottom
                                                    }

                                                    Rectangle {
                                                        Layout.row: 0
                                                        Layout.column: 2
                                                        Layout.alignment: Qt.AlignTop | Qt.AlignRight
                                                        implicitWidth: laneStatusText.implicitWidth + 12
                                                        implicitHeight: 20
                                                        radius: 11
                                                        color: isDark ? "#18120E" : "#FFF5EA"
                                                        border.width: 1
                                                        border.color: root.accentColor(String(modelData.accentKey || modelData.visualChannel || "system"))

                                                        Text {
                                                            id: laneStatusText
                                                            anchors.centerIn: parent
                                                            text: String(modelData.statusLabel || "")
                                                            color: textSecondary
                                                            font.pixelSize: typeMeta
                                                            font.weight: weightMedium
                                                        }
                                                    }

                                                    Text {
                                                        Layout.row: 1
                                                        Layout.column: 1
                                                        Layout.fillWidth: true
                                                        Layout.alignment: Qt.AlignTop
                                                        text: String(modelData.summary || "")
                                                        color: textSecondary
                                                        font.pixelSize: typeMeta
                                                        font.weight: weightMedium
                                                        elide: Text.ElideRight
                                                    }

                                                    Text {
                                                        Layout.row: 1
                                                        Layout.column: 2
                                                        Layout.alignment: Qt.AlignTop | Qt.AlignRight
                                                        text: root.itemTimeLabel(modelData)
                                                        visible: text !== ""
                                                        color: textTertiary
                                                        font.pixelSize: typeMeta
                                                        font.weight: weightMedium
                                                        elide: Text.ElideRight
                                                        horizontalAlignment: Text.AlignRight
                                                    }
                                                }

                                                MouseArea {
                                                    id: laneItemMouse
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    enabled: Boolean(modelData.canOpen)
                                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                    onClicked: root.openItem(modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 4
                        }
                    }
                }
            }
        }
    }
}
