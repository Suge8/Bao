import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property bool active: false
    property string currentScope: "installed"
    property var toolsService: null
    property var configService: null
    property string uiLanguage: "auto"
    property string autoLanguage: "en"
    readonly property bool hasToolsService: toolsService !== null
    readonly property bool hasToolsSignals: hasToolsService
        && typeof toolsService.changed !== "undefined"
        && typeof toolsService.operationFinished !== "undefined"
    readonly property bool hasConfigService: configService !== null
    readonly property string effectiveUiLanguage: {
        if (typeof uiLanguage === "string" && uiLanguage !== "auto")
            return uiLanguage
        if (typeof autoLanguage === "string")
            return autoLanguage
        return "en"
    }
    readonly property bool isZhLang: effectiveUiLanguage === "zh"
    readonly property var allItems: hasToolsService && typeof toolsService.items !== "undefined"
        ? (toolsService.items || [])
        : []
    readonly property var installedItems: allItems.filter(function(item) { return item.kind === "builtin" })
    readonly property var serverItems: allItems.filter(function(item) { return item.kind === "mcp_server" })
    readonly property var selectedItem: hasToolsService && typeof toolsService.selectedItem !== "undefined"
        ? (toolsService.selectedItem || ({}))
        : ({})
    readonly property string selectedItemId: hasToolsService && typeof toolsService.selectedItemId !== "undefined"
        ? String(toolsService.selectedItemId || "")
        : ""
    readonly property var overview: hasToolsService && typeof toolsService.overview !== "undefined"
        ? (toolsService.overview || ({}))
        : ({})
    property real revealOpacity: 1.0
    property real revealScale: 1.0
    property real revealShift: 0.0

    function tr(zh, en) {
        return isZhLang ? zh : en
    }

    function localizedText(value, fallback) {
        if (value && typeof value === "object") {
            var primary = isZhLang ? value.zh : value.en
            var secondary = isZhLang ? value.en : value.zh
            if (primary !== undefined && primary !== null && String(primary))
                return String(primary)
            if (secondary !== undefined && secondary !== null && String(secondary))
                return String(secondary)
        }
        if (value !== undefined && value !== null && typeof value !== "object" && String(value))
            return String(value)
        return String(fallback || "")
    }

    function itemDisplayName(item) {
        return localizedText(item.displayName, item.name || "")
    }

    function itemDisplaySummary(item) {
        return localizedText(item.displaySummary, item.summary || "")
    }

    function itemDisplayDetail(item) {
        return localizedText(item.displayDetail, item.detail || item.summary || "")
    }

    function bundleLabel(bundle) {
        if (bundle && typeof bundle === "object")
            return localizedText(bundle, "")
        switch (String(bundle || "")) {
        case "core":
            return tr("核心", "Core")
        case "web":
            return tr("网页", "Web")
        case "desktop":
            return tr("桌面", "Desktop")
        case "code":
            return tr("代码", "Code")
        case "mcp":
            return tr("MCP", "MCP")
        default:
            return String(bundle || "")
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
        return tr(fallbackZh, fallbackEn)
    }

    function itemIconSource(item) {
        return String(item.iconSource || labIcon("toolbox"))
    }

    function itemIconBackdrop(item) {
        switch (String(item.status || "")) {
        case "healthy":
        case "ready":
            return isDark ? "#1B1A12" : "#FFF2E2"
        case "configured":
            return isDark ? "#111B22" : "#EEF7FF"
        case "blocked":
        case "error":
            return isDark ? "#241111" : "#FFF0EE"
        default:
            return isDark ? "#171512" : "#F8F4EF"
        }
    }

    function capabilityLabel(capability) {
        if (capability && typeof capability === "object")
            return localizedText(capability, "")
        switch (String(capability || "")) {
        case "Filesystem":
            return tr("文件系统", "Filesystem")
        case "Workspace":
            return tr("工作区", "Workspace")
        case "Authoring":
            return tr("编辑", "Authoring")
        case "Shell":
            return tr("命令行", "Shell")
        case "Local host":
            return tr("本机", "Local host")
        case "Diagnostics":
            return tr("诊断", "Diagnostics")
        case "Codegen":
            return tr("代码生成", "Codegen")
        case "Refactor":
            return tr("重构", "Refactor")
        case "Debug":
            return tr("调试", "Debug")
        case "Search":
            return tr("搜索", "Search")
        case "Fetch":
            return tr("抓取", "Fetch")
        case "Browser":
            return tr("浏览器", "Browser")
        case "Embeddings":
            return tr("向量", "Embeddings")
        case "Retrieval":
            return tr("检索", "Retrieval")
        case "Memory":
            return tr("记忆", "Memory")
        case "Image":
            return tr("图像", "Image")
        case "Creative":
            return tr("创作", "Creative")
        case "Generation":
            return tr("生成", "Generation")
        case "Persistence":
            return tr("持久化", "Persistence")
        case "Curation":
            return tr("整理", "Curation")
        case "Plan":
            return tr("计划", "Plan")
        case "Delegate":
            return tr("委派", "Delegate")
        case "Track":
            return tr("追踪", "Track")
        case "Messaging":
            return tr("消息", "Messaging")
        case "Support":
            return tr("支持", "Support")
        case "Schedule":
            return tr("调度", "Schedule")
        case "Reminder":
            return tr("提醒", "Reminder")
        case "Automation":
            return tr("自动化", "Automation")
        case "Desktop":
            return tr("桌面", "Desktop")
        case "Input":
            return tr("输入", "Input")
        case "Visual":
            return tr("视觉", "Visual")
        case "External":
            return tr("外部", "External")
        case "MCP":
            return "MCP"
        case "STDIO":
            return "STDIO"
        case "HTTP":
            return "HTTP"
        case "Setup":
            return tr("待配置", "Setup")
        default:
            return String(capability || "")
        }
    }

    function statusLabel(item) {
        if (item && item.displayStatusLabel)
            return localizedText(item.displayStatusLabel, item.statusLabel || "")
        switch (String(item.status || "")) {
        case "healthy":
            return tr("已连接", "Connected")
        case "ready":
            return tr("已就绪", "Ready")
        case "configured":
            return tr("已设置", "Configured")
        case "limited":
            return tr("受限", "Limited")
        case "disabled":
            return tr("已关闭", "Disabled")
        case "needs_setup":
            return tr("待配置", "Needs setup")
        case "unavailable":
            return tr("不可用", "Unavailable")
        case "blocked":
            return tr("受阻", "Blocked")
        case "error":
            return tr("异常", "Error")
        default:
            return String(item.statusLabel || "")
        }
    }

    function statusDetail(item) {
        return localizedText(item.statusDetailDisplay, item.statusDetail || "")
    }

    function exposureNote(item) {
        return localizedText(item.exposureSummaryDisplay, "")
    }

    function attentionAction(item) {
        return localizedText(item.attentionActionDisplay, "")
    }

    function runtimeStateText(item) {
        return localizedText(item.runtimeStateDisplay, "")
    }

    function includesSummary(item) {
        if (item && item.includesSummaryDisplay)
            return localizedText(item.includesSummaryDisplay, "")
        var count = Number((item.includedTools || []).length)
        if (count <= 0)
            return tr("这个能力族没有单独的用户侧配置入口。", "This capability family does not expose separate end-user configuration.")
        if (item.kind === "mcp_server")
            return tr("本次探测共发现 ", "Latest probe found ") + count + tr(" 个运行时工具", " runtime tools")
        return tr("包含 ", "Includes ") + count + tr(" 个底层工具", " underlying tools")
    }

    function detailStatusNote(item) {
        if (!item || !item.kind)
            return ""
        var attentionReason = localizedText(item.attentionReasonDisplay, "")
        if (attentionReason)
            return attentionReason
        return statusDetail(item)
    }

    function listBadges(item) {
        if (item && item.badges && item.badges.length)
            return item.badges
        var badges = []
        var status = statusLabel(item)
        if (status)
            badges.push({ text: status, tone: statusTone(item) })
        if (item.kind === "builtin") {
            var bundle = bundleLabel(item.bundle)
            if (bundle)
                badges.push({ text: bundle, tone: "#60A5FA" })
        } else if (item.kind === "mcp_server") {
            var transport = capabilityLabel(item.configValues && item.configValues.transport ? String(item.configValues.transport).toUpperCase() : "")
            if (transport)
                badges.push({ text: transport, tone: "#60A5FA" })
        }
        return badges
    }

    function summaryMetricLabel(key) {
        if (key && typeof key === "object")
            return localizedText(key, "")
        switch (key) {
        case "available":
            return tr("当前可用", "Available now")
        case "recent_exposure":
            return tr("最近暴露", "Exposed recently")
        case "mcp_connected":
            return tr("MCP 已连通", "MCP connected")
        case "builtin":
            return tr("工具族", "Families")
        case "mcp":
            return tr("MCP 源", "MCP sources")
        case "attention":
            return tr("待配/异常", "Setup / errors")
        default:
            return key
        }
    }

    function slimSchemaModeFromValue(value) {
        if (value === true)
            return "enabled"
        if (value === false)
            return "disabled"
        return "inherit"
    }

    function slimSchemaValueFromMode(mode) {
        if (mode === "enabled")
            return true
        if (mode === "disabled")
            return false
        return null
    }

    function readConfig(path, fallbackValue) {
        if (!hasConfigService)
            return fallbackValue
        var value = configService.getValue(path)
        return value === undefined || value === null ? fallbackValue : value
    }

    function toastMessage(code, ok) {
        if (!ok)
            return code
        if (code === "saved")
            return tr("工具配置已保存", "Tool settings saved")
        if (code === "deleted")
            return tr("MCP 服务已删除", "MCP server deleted")
        if (code === "probe_ok")
            return tr("连接测试成功", "Connection test succeeded")
        return code
    }

    function playReveal() {
        revealOpacity = motionPageRevealStartOpacity
        revealScale = motionPageRevealStartScale
        revealShift = motionPageShiftSubtle
        revealAnimation.restart()
    }

    function reloadDetailPanels() {
        if (installedDetailLoader.active) {
            installedDetailLoader.active = false
            installedDetailLoader.active = true
        }
        if (serverDetailLoader.active) {
            serverDetailLoader.active = false
            serverDetailLoader.active = true
        }
    }

    function ensureSelectionForScope() {
        if (!hasToolsService || currentScope === "policies")
            return
        var items = currentScope === "servers" ? serverItems : installedItems
        if (!items.length)
            return
        var selected = selectedItem || {}
        if (!selected.id) {
            toolsService.selectItem(items[0].id)
            return
        }
        if (currentScope === "installed" && selected.kind !== "builtin") {
            toolsService.selectItem(items[0].id)
            return
        }
        if (currentScope === "servers" && selected.kind !== "mcp_server")
            toolsService.selectItem(items[0].id)
    }

    function statusTone(item) {
        switch (String(item.status || "")) {
        case "healthy":
        case "ready":
            return accent
        case "configured":
            return "#60A5FA"
        case "limited":
            return "#F59E0B"
        case "disabled":
        case "needs_setup":
        case "unavailable":
            return "#F97316"
        case "blocked":
        case "error":
            return statusError
        default:
            return textSecondary
        }
    }

    function scopeIntroTitle() {
        return workspaceString("workspace_tools_title", "工具", "Tools")
    }

    function scopeIntroCaption() {
        return workspaceString(
            "workspace_tools_caption",
            "管理 AI 可用工具",
            "Manage AI available tools"
        )
    }

    function installedDetailComponent(item) {
        switch (String(item.formKind || "overview")) {
        case "exec":
            return execDetailComponent
        case "web":
            return webDetailComponent
        case "embedding":
            return embeddingDetailComponent
        case "image_generation":
            return imageGenerationDetailComponent
        case "desktop":
            return desktopDetailComponent
        case "coding":
            return codingDetailComponent
        default:
            return builtinOverviewDetailComponent
        }
    }

    function serverDraftFromItem(item) {
        var values = (item && item.configValues) ? item.configValues : {}
        return {
            previousName: values.previousName || "",
            name: values.name || "",
            transport: values.transport || "stdio",
            command: values.command || "",
            argsText: values.argsText || "",
            envText: values.envText || "",
            url: values.url || "",
            headersText: values.headersText || "",
            toolTimeoutSeconds: values.toolTimeoutSeconds || 30,
            maxTools: values.maxTools || 0,
            slimSchema: values.slimSchema
        }
    }

    onActiveChanged: {
        if (active) {
            playReveal()
            ensureSelectionForScope()
        }
    }

    onCurrentScopeChanged: {
        if (hasToolsService) {
            if (currentScope === "installed" && toolsService.sourceFilter === "mcp")
                toolsService.setSourceFilter("all")
            else if (currentScope === "servers" && toolsService.sourceFilter === "builtin")
                toolsService.setSourceFilter("mcp")
        }
        ensureSelectionForScope()
    }

    onSelectedItemIdChanged: reloadDetailPanels()

    Component.onCompleted: ensureSelectionForScope()

    Connections {
        target: root.hasToolsSignals ? toolsService : null

        function onChanged() {
            root.ensureSelectionForScope()
        }

        function onOperationFinished(message, ok) {
            globalToast.show(root.toastMessage(message, ok), ok)
        }
    }

    Item {
        anchors.fill: parent
        opacity: root.revealOpacity
        scale: root.revealScale
        transform: Translate { x: root.revealShift }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 16
            radius: 30
            color: bgCard
            border.width: 1
            border.color: isDark ? "#20FFFFFF" : "#146E4B2A"

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: isDark ? "#08FFFFFF" : "#0DFFF7EF"
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 14

                CalloutPanel {
                    Layout.fillWidth: true
                    panelColor: isDark ? "#15100D" : "#FFF7F0"
                    panelBorderColor: isDark ? "#22FFFFFF" : "#14000000"
                    overlayColor: isDark ? "#0BFFFFFF" : "#08FFFFFF"
                    overlayVisible: true
                    sideGlowVisible: false
                    accentBlobVisible: false
                    padding: 14

                    ColumnLayout {
                        width: parent.width
                        spacing: 10

                        Item {
                            Layout.fillWidth: true
                            implicitHeight: 52

                            Row {
                                id: toolsHeaderIntro
                                anchors.left: parent.left
                                anchors.right: toolsHeaderCenter.left
                                anchors.rightMargin: 18
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 10

                                WorkspaceHeroIcon {
                                    iconSource: root.labIcon("toolbox")
                                }

                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.max(0, toolsHeaderIntro.width - 44)
                                    spacing: 2

                                    Text {
                                        width: parent.width
                                        text: scopeIntroTitle()
                                        color: textPrimary
                                        font.pixelSize: typeTitle - 1
                                        font.weight: weightBold
                                        elide: Text.ElideRight
                                    }

                                    Text {
                                        width: parent.width
                                        text: scopeIntroCaption()
                                        color: textSecondary
                                        font.pixelSize: typeMeta
                                        maximumLineCount: 1
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            Item {
                                id: toolsHeaderCenter
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.verticalCenter: parent.verticalCenter
                                width: scopeTabBar.implicitWidth
                                height: scopeTabBar.implicitHeight

                                SegmentedTabs {
                                    id: scopeTabBar
                                    anchors.centerIn: parent
                                    preferredTrackWidth: 250
                                    fillSegments: true
                                    currentValue: root.currentScope
                                    items: [
                                        {
                                            value: "installed",
                                            label: tr("已安装", "Installed"),
                                            icon: labIcon("toolbox")
                                        },
                                        {
                                            value: "servers",
                                            label: "MCP",
                                            icon: icon("database-settings")
                                        },
                                        {
                                            value: "policies",
                                            label: tr("策略", "Policies"),
                                            icon: icon("ios-settings")
                                        }
                                    ]
                                    onSelected: function(value) { root.currentScope = value }
                                }
                            }

                            Item {
                                id: toolsHeaderActionSlot
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                width: toolsHeaderActions.implicitWidth
                                height: toolsHeaderActions.implicitHeight

                                RowLayout {
                                    id: toolsHeaderActions
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 8

                                    AsyncActionButton {
                                        visible: root.currentScope === "servers"
                                        text: root.hasToolsService && toolsService.busy ? tr("测试中", "Testing") : tr("新增 MCP 服务", "Add MCP server")
                                        iconSource: icon("circle-spark")
                                        busy: root.hasToolsService
                                            && typeof toolsService.busy !== "undefined"
                                            && toolsService.busy
                                        minHeight: 34
                                        horizontalPadding: 18
                                        fillColor: accent
                                        hoverFillColor: accentHover
                                        onClicked: createServerModal.open()
                                    }
                                }
                            }
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8

                            Repeater {
                                model: (root.overview.summaryMetrics || []).length ? (root.overview.summaryMetrics || []) : [
                                    {
                                        key: "available",
                                        displayLabel: { "zh": "当前可用", "en": "Available now" },
                                        value: Number(root.overview.availableCount || 0),
                                        tone: accent
                                    },
                                    {
                                        key: "recent_exposure",
                                        displayLabel: { "zh": "最近暴露", "en": "Exposed recently" },
                                        value: Number(root.overview.recentExposureCount || 0),
                                        tone: "#34D399"
                                    },
                                    {
                                        key: "mcp_connected",
                                        displayLabel: { "zh": "MCP 已连通", "en": "MCP connected" },
                                        value: Number(root.overview.healthyMcpCount || 0),
                                        tone: "#60A5FA"
                                    },
                                    {
                                        key: "attention",
                                        displayLabel: { "zh": "需处理", "en": "Needs attention" },
                                        value: Number(root.overview.attentionCount || 0),
                                        tone: statusError
                                    }
                                ]

                                delegate: Rectangle {
                                    required property var modelData

                                    implicitWidth: metricRow.implicitWidth + 18
                                    implicitHeight: 38
                                    radius: 14
                                    color: isDark ? "#181310" : "#FFFDFC"
                                    border.width: 1
                                    border.color: isDark ? "#12FFFFFF" : "#0E000000"

                                    Row {
                                        id: metricRow
                                        anchors.centerIn: parent
                                        spacing: 8

                                        Rectangle {
                                            width: 7
                                            height: 7
                                            radius: 3.5
                                            color: modelData.tone
                                            anchors.verticalCenter: parent.verticalCenter
                                        }

                                        Text {
                                            text: root.summaryMetricLabel(modelData.displayLabel || modelData.key)
                                            color: textSecondary
                                            font.pixelSize: typeCaption
                                            font.weight: weightBold
                                            anchors.verticalCenter: parent.verticalCenter
                                        }

                                        Text {
                                            text: String(modelData.value)
                                            color: textPrimary
                                            font.pixelSize: typeLabel
                                            font.weight: weightBold
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.currentScope === "installed" ? 0 : (root.currentScope === "servers" ? 1 : 2)

                    SplitView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        orientation: Qt.Horizontal
                        spacing: 10
                        handle: WorkspaceSplitHandle {}

                        Rectangle {
                            SplitView.preferredWidth: 152
                            SplitView.minimumWidth: 144
                            SplitView.maximumWidth: 164
                            SplitView.fillHeight: true
                            radius: 24
                            color: "transparent"
                            border.width: 0
                            border.color: "transparent"

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 10

                                Text {
                                    text: tr("筛选", "Filters")
                                    color: textPrimary
                                    font.pixelSize: typeMeta
                                    font.weight: weightBold
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 42
                                    radius: 16
                                    color: bgInput
                                    border.width: 1
                                    border.color: borderSubtle

                                    TextField {
                                        id: installedSearchField
                                        property bool baoClickAwayEditor: true
                                        anchors.fill: parent
                                        leftPadding: 14
                                        rightPadding: 14
                                        background: null
                                        color: textPrimary
                                        placeholderText: tr("搜索能力或工具…", "Search tools…")
                                        placeholderTextColor: textPlaceholder
                                        selectionColor: textSelectionBg
                                        selectedTextColor: textSelectionFg
                                        text: root.hasToolsService && typeof toolsService.query !== "undefined"
                                            ? String(toolsService.query || "")
                                            : ""
                                        onTextEdited: if (root.hasToolsService) toolsService.setQuery(text)
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Repeater {
                                        model: [
                                            { value: "all", zh: "全部", en: "All" },
                                            { value: "builtin", zh: "内建", en: "Built-in" },
                                            { value: "attention", zh: "异常/待配", en: "Errors / setup" }
                                        ]

                                        delegate: PillActionButton {
                                            required property var modelData

                                            Layout.fillWidth: true
                                            text: root.tr(modelData.zh, modelData.en)
                                            minHeight: 34
                                            horizontalPadding: 14
                                            outlined: true
                                            fillColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accentMuted : "transparent"
                                            hoverFillColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accentMuted : bgCardHover
                                            outlineColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accent : borderSubtle
                                            hoverOutlineColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accentHover : borderDefault
                                            textColor: textPrimary
                                            onClicked: if (root.hasToolsService) toolsService.setSourceFilter(modelData.value)
                                        }
                                    }
                                }

                                Item { Layout.fillHeight: true }
                            }
                        }

                        Rectangle {
                            SplitView.preferredWidth: 356
                            SplitView.minimumWidth: 280
                            SplitView.fillWidth: true
                            SplitView.fillHeight: true
                            radius: 24
                            color: "transparent"
                            border.width: 0
                            border.color: "transparent"

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 12

                                RowLayout {
                                    Layout.fillWidth: true

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("内建能力族", "Built-in families")
                                        color: textPrimary
                                        font.pixelSize: typeLabel
                                        font.weight: weightBold
                                    }

                                    Rectangle {
                                        radius: 11
                                        color: isDark ? "#20FFFFFF" : "#14000000"
                                        implicitHeight: 22
                                        implicitWidth: builtinsCountLabel.implicitWidth + 16

                                        Text {
                                            id: builtinsCountLabel
                                            anchors.centerIn: parent
                                            text: String(root.installedItems.length)
                                            color: textSecondary
                                            font.pixelSize: typeMeta
                                            font.weight: weightBold
                                        }
                                    }
                                }

                                ListView {
                                    id: builtinList
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    clip: true
                                    spacing: 10
                                    bottomMargin: 12
                                    model: root.installedItems
                                    ScrollIndicator.vertical: ScrollIndicator {
                                        visible: false
                                        width: 4
                                        contentItem: Rectangle {
                                            implicitWidth: 2
                                            radius: 1
                                            color: isDark ? "#28FFFFFF" : "#22000000"
                                        }
                                    }

                                    delegate: Item {
                                        id: builtinDelegateRoot
                                        required property var modelData

                                        width: builtinList.width
                                        implicitHeight: 120
                                        property bool selected: root.hasToolsService && toolsService.selectedItemId === modelData.id

                                        Rectangle {
                                            anchors.fill: parent
                                            radius: 22
                                            color: builtinArea.containsMouse
                                                   ? (builtinDelegateRoot.selected ? (isDark ? "#241914" : "#FFF1E2") : bgCardHover)
                                                   : (builtinDelegateRoot.selected ? (isDark ? "#201612" : "#FFF7F0") : (isDark ? "#17120F" : "#FFFFFF"))
                                            border.width: builtinDelegateRoot.selected ? 1.5 : 1
                                            border.color: builtinDelegateRoot.selected ? accent : (isDark ? "#14FFFFFF" : "#10000000")

                                            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                            Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                            ColumnLayout {
                                                id: builtinCardColumn
                                                anchors.fill: parent
                                                anchors.margins: 12
                                                anchors.bottomMargin: 16
                                                spacing: 8

                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 8

                                                    Rectangle {
                                                        Layout.alignment: Qt.AlignTop
                                                        implicitWidth: 36
                                                        implicitHeight: 36
                                                        Layout.preferredWidth: implicitWidth
                                                        Layout.preferredHeight: implicitHeight
                                                        radius: 12
                                                        color: root.itemIconBackdrop(builtinDelegateRoot.modelData)
                                                        border.width: builtinDelegateRoot.selected ? 1 : 0
                                                        border.color: builtinDelegateRoot.selected ? accent : "transparent"

                                                        AppIcon {
                                                            anchors.centerIn: parent
                                                            width: 18
                                                            height: 18
                                                            source: root.itemIconSource(builtinDelegateRoot.modelData)
                                                            sourceSize: Qt.size(width, height)
                                                        }
                                                    }

                                                    ColumnLayout {
                                                        Layout.fillWidth: true
                                                        spacing: 2

                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: root.itemDisplayName(builtinDelegateRoot.modelData)
                                                            color: textPrimary
                                                            font.pixelSize: typeBody
                                                            font.weight: weightBold
                                                            elide: Text.ElideRight
                                                        }

                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: root.itemDisplaySummary(builtinDelegateRoot.modelData)
                                                            color: isDark ? textSecondary : "#5A4537"
                                                            font.pixelSize: typeMeta
                                                            wrapMode: Text.WordWrap
                                                            maximumLineCount: 2
                                                            elide: Text.ElideRight
                                                        }
                                                    }

                                                    IconCircleButton {
                                                        buttonSize: 30
                                                        glyphText: "→"
                                                        glyphSize: typeLabel
                                                        fillColor: "transparent"
                                                        hoverFillColor: bgCardHover
                                                        outlineColor: builtinDelegateRoot.selected ? accent : borderSubtle
                                                        glyphColor: builtinDelegateRoot.selected ? accent : textSecondary
                                                        onClicked: if (root.hasToolsService) toolsService.selectItem(builtinDelegateRoot.modelData.id)
                                                    }
                                                }

                                                Row {
                                                    Layout.fillWidth: true
                                                    spacing: 8
                                                    clip: true

                                                    Repeater {
                                                        model: root.listBadges(builtinDelegateRoot.modelData)

                                                        delegate: Rectangle {
                                                            required property var modelData
                                                            radius: 11
                                                            height: 22
                                                            color: Qt.rgba(Qt.color(modelData.tone).r, Qt.color(modelData.tone).g, Qt.color(modelData.tone).b, isDark ? 0.18 : 0.10)
                                                            border.width: 1
                                                            border.color: Qt.rgba(Qt.color(modelData.tone).r, Qt.color(modelData.tone).g, Qt.color(modelData.tone).b, isDark ? 0.34 : 0.24)
                                                            width: builtinBadgeText.implicitWidth + 16

                                                            Text {
                                                                id: builtinBadgeText
                                                                anchors.centerIn: parent
                                                                text: modelData.text
                                                                color: textPrimary
                                                                font.pixelSize: typeCaption
                                                                font.weight: weightBold
                                                            }
                                                        }
                                                    }
                                                }
                                            }

                                            MouseArea {
                                                id: builtinArea
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                acceptedButtons: Qt.LeftButton
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: if (root.hasToolsService) toolsService.selectItem(builtinDelegateRoot.modelData.id)
                                            }
                                        }
                                    }

                                    footer: Item {
                                        width: builtinList.width
                                        height: root.installedItems.length === 0 ? 180 : 0

                                        Column {
                                            anchors.centerIn: parent
                                            width: Math.min(parent.width - 40, 280)
                                            spacing: 10
                                            visible: parent.height > 0

                                            Text {
                                                width: parent.width
                                                text: tr("没有匹配的工具族", "No tool family matches this view")
                                                color: textPrimary
                                                font.pixelSize: typeBody
                                                font.weight: weightBold
                                                horizontalAlignment: Text.AlignHCenter
                                            }

                                            Text {
                                                width: parent.width
                                            text: tr("试试清空搜索，或切到 MCP 页面管理外部服务。", "Try clearing the search, or switch to the MCP page for external servers.")
                                                color: textSecondary
                                                font.pixelSize: typeMeta
                                                wrapMode: Text.WordWrap
                                                horizontalAlignment: Text.AlignHCenter
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            SplitView.preferredWidth: 468
                            SplitView.minimumWidth: 320
                            SplitView.fillWidth: true
                            SplitView.fillHeight: true
                            radius: 24
                            color: "transparent"
                            border.width: 0
                            border.color: "transparent"

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 8

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 10

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 4

                                        Text {
                                            Layout.fillWidth: true
                                            text: root.itemDisplayName(root.selectedItem) || tr("选择一个能力族", "Choose a capability family")
                                            color: textPrimary
                                            font.pixelSize: typeLabel
                                            font.weight: weightBold
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: root.itemDisplayDetail(root.selectedItem) || tr("从中栏选择一个能力族后，这里会显示说明、状态和可配置项。", "Choose a capability family from the list to inspect its summary, status, and configurable settings.")
                                            color: textSecondary
                                            font.pixelSize: typeCaption
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: builtinSummaryColumn.implicitHeight + 16
                                    radius: 16
                                    color: isDark ? "#181310" : "#FFF9F3"
                                    border.width: 1
                                    border.color: isDark ? "#12FFFFFF" : "#10000000"

                                    Column {
                                        id: builtinSummaryColumn
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: 10
                                        spacing: 6

                                        Flow {
                                            width: parent.width
                                            spacing: 8

                                            Repeater {
                                                model: root.listBadges(root.selectedItem)

                                                delegate: Rectangle {
                                                    required property var modelData

                                                    radius: 10
                                                    height: 20
                                                    color: isDark ? "#1D1713" : "#FFFFFF"
                                                    border.width: 1
                                                    border.color: isDark ? "#16FFFFFF" : "#10000000"
                                                    width: builtinCapabilityText.implicitWidth + 14

                                                    Text {
                                                        id: builtinCapabilityText
                                                        anchors.centerIn: parent
                                                        text: modelData.text
                                                        color: textPrimary
                                                        font.pixelSize: 11
                                                        font.weight: weightBold
                                                    }
                                                }
                                            }
                                        }

                                        Text {
                                            width: parent.width
                                            visible: text.length > 0
                                            text: root.detailStatusNote(root.selectedItem)
                                            color: root.statusTone(root.selectedItem)
                                            font.pixelSize: typeCaption
                                            font.weight: weightBold
                                            wrapMode: Text.WordWrap
                                        }

                                        Text {
                                            width: parent.width
                                            text: root.includesSummary(root.selectedItem)
                                            color: textSecondary
                                            font.pixelSize: typeCaption
                                            wrapMode: Text.WordWrap
                                        }

                                        Text {
                                            width: parent.width
                                            visible: text.length > 0
                                            text: root.exposureNote(root.selectedItem)
                                            color: textSecondary
                                            font.pixelSize: typeCaption
                                            wrapMode: Text.WordWrap
                                        }

                                        Text {
                                            width: parent.width
                                            visible: text.length > 0
                                            text: root.attentionAction(root.selectedItem)
                                            color: accent
                                            font.pixelSize: typeCaption
                                            font.weight: weightBold
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }

                                Loader {
                                    id: installedDetailLoader
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    active: true
                                    sourceComponent: root.installedDetailComponent(root.selectedItem)
                                }
                            }
                        }
                    }

                    SplitView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        orientation: Qt.Horizontal
                        spacing: 10
                        handle: WorkspaceSplitHandle {}

                        Rectangle {
                            SplitView.preferredWidth: 152
                            SplitView.minimumWidth: 144
                            SplitView.maximumWidth: 164
                            SplitView.fillHeight: true
                            radius: 24
                            color: "transparent"
                            border.width: 0
                            border.color: "transparent"

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 10

                                Text {
                                    text: tr("MCP 筛选", "MCP filters")
                                    color: textPrimary
                                    font.pixelSize: typeMeta
                                    font.weight: weightBold
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 42
                                    radius: 16
                                    color: bgInput
                                    border.width: 1
                                    border.color: borderSubtle

                                    TextField {
                                        id: serverSearchField
                                        property bool baoClickAwayEditor: true
                                        anchors.fill: parent
                                        leftPadding: 14
                                        rightPadding: 14
                                        background: null
                                        color: textPrimary
                                        placeholderText: tr("搜索服务或工具…", "Search servers…")
                                        placeholderTextColor: textPlaceholder
                                        selectionColor: textSelectionBg
                                        selectedTextColor: textSelectionFg
                                        text: root.hasToolsService && typeof toolsService.query !== "undefined"
                                            ? String(toolsService.query || "")
                                            : ""
                                        onTextEdited: if (root.hasToolsService) toolsService.setQuery(text)
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Repeater {
                                        model: [
                                            { value: "all", zh: "全部", en: "All" },
                                            { value: "mcp", zh: "仅 MCP", en: "Only MCP" },
                                            { value: "attention", zh: "异常/待配", en: "Errors / setup" }
                                        ]

                                        delegate: PillActionButton {
                                            required property var modelData

                                            Layout.fillWidth: true
                                            text: root.tr(modelData.zh, modelData.en)
                                            minHeight: 34
                                            horizontalPadding: 14
                                            outlined: true
                                            fillColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accentMuted : "transparent"
                                            hoverFillColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accentMuted : bgCardHover
                                            outlineColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accent : borderSubtle
                                            hoverOutlineColor: root.hasToolsService && toolsService.sourceFilter === modelData.value ? accentHover : borderDefault
                                            textColor: textPrimary
                                            onClicked: if (root.hasToolsService) toolsService.setSourceFilter(modelData.value)
                                        }
                                    }
                                }

                                Item { Layout.fillHeight: true }
                            }
                        }

                        Rectangle {
                            SplitView.preferredWidth: 348
                            SplitView.minimumWidth: 280
                            SplitView.fillWidth: true
                            SplitView.fillHeight: true
                            radius: 24
                            color: "transparent"
                            border.width: 0
                            border.color: "transparent"

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 12

                                RowLayout {
                                    Layout.fillWidth: true

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("已配置服务", "Configured servers")
                                        color: textPrimary
                                        font.pixelSize: typeLabel
                                        font.weight: weightBold
                                    }

                                    Rectangle {
                                        radius: 11
                                        color: isDark ? "#20FFFFFF" : "#14000000"
                                        implicitHeight: 22
                                        implicitWidth: serverCountLabel.implicitWidth + 16

                                        Text {
                                            id: serverCountLabel
                                            anchors.centerIn: parent
                                            text: String(root.serverItems.length)
                                            color: textSecondary
                                            font.pixelSize: typeMeta
                                            font.weight: weightBold
                                        }
                                    }
                                }

                                ListView {
                                    id: serverList
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    clip: true
                                    spacing: 10
                                    bottomMargin: 12
                                    model: root.serverItems
                                    ScrollIndicator.vertical: ScrollIndicator {
                                        visible: false
                                        width: 4
                                        contentItem: Rectangle {
                                            implicitWidth: 2
                                            radius: 1
                                            color: isDark ? "#28FFFFFF" : "#22000000"
                                        }
                                    }

                                    delegate: Item {
                                        id: serverDelegateRoot
                                        required property var modelData

                                        width: serverList.width
                                        implicitHeight: 120
                                        property bool selected: root.hasToolsService && toolsService.selectedItemId === modelData.id

                                        Rectangle {
                                            anchors.fill: parent
                                            radius: 22
                                            color: serverArea.containsMouse
                                                   ? (serverDelegateRoot.selected ? (isDark ? "#241914" : "#FFF1E2") : bgCardHover)
                                                   : (serverDelegateRoot.selected ? (isDark ? "#201612" : "#FFF7F0") : (isDark ? "#17120F" : "#FFFFFF"))
                                            border.width: serverDelegateRoot.selected ? 1.5 : 1
                                            border.color: serverDelegateRoot.selected ? accent : (isDark ? "#14FFFFFF" : "#10000000")

                                            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                            Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                            ColumnLayout {
                                                id: serverCardColumn
                                                anchors.fill: parent
                                                anchors.margins: 12
                                                anchors.bottomMargin: 16
                                                spacing: 8

                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 8

                                                    Rectangle {
                                                        Layout.alignment: Qt.AlignTop
                                                        implicitWidth: 36
                                                        implicitHeight: 36
                                                        Layout.preferredWidth: implicitWidth
                                                        Layout.preferredHeight: implicitHeight
                                                        radius: 12
                                                        color: root.itemIconBackdrop(serverDelegateRoot.modelData)
                                                        border.width: serverDelegateRoot.selected ? 1 : 0
                                                        border.color: serverDelegateRoot.selected ? accent : "transparent"

                                                        AppIcon {
                                                            anchors.centerIn: parent
                                                            width: 18
                                                            height: 18
                                                            source: icon("database-settings")
                                                            sourceSize: Qt.size(width, height)
                                                        }
                                                    }

                                                    ColumnLayout {
                                                        Layout.fillWidth: true
                                                        spacing: 2

                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: String(serverDelegateRoot.modelData.name || "")
                                                            color: textPrimary
                                                            font.pixelSize: typeBody
                                                            font.weight: weightBold
                                                            elide: Text.ElideRight
                                                        }

                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: root.statusDetail(serverDelegateRoot.modelData)
                                                            color: isDark ? textSecondary : "#5A4537"
                                                            font.pixelSize: typeMeta
                                                            wrapMode: Text.WordWrap
                                                            maximumLineCount: 2
                                                            elide: Text.ElideRight
                                                        }
                                                    }

                                                    IconCircleButton {
                                                        buttonSize: 30
                                                        glyphText: "→"
                                                        glyphSize: typeLabel
                                                        fillColor: "transparent"
                                                        hoverFillColor: bgCardHover
                                                        outlineColor: serverDelegateRoot.selected ? accent : borderSubtle
                                                        glyphColor: serverDelegateRoot.selected ? accent : textSecondary
                                                        onClicked: if (root.hasToolsService) toolsService.selectItem(serverDelegateRoot.modelData.id)
                                                    }
                                                }

                                                Row {
                                                    Layout.fillWidth: true
                                                    spacing: 8
                                                    clip: true

                                                    Repeater {
                                                        model: root.listBadges(serverDelegateRoot.modelData)

                                                        delegate: Rectangle {
                                                            required property var modelData
                                                            radius: 11
                                                            height: 22
                                                            color: Qt.rgba(Qt.color(modelData.tone).r, Qt.color(modelData.tone).g, Qt.color(modelData.tone).b, isDark ? 0.18 : 0.10)
                                                            border.width: 1
                                                            border.color: Qt.rgba(Qt.color(modelData.tone).r, Qt.color(modelData.tone).g, Qt.color(modelData.tone).b, isDark ? 0.34 : 0.24)
                                                            width: serverBadgeText.implicitWidth + 16

                                                            Text {
                                                                id: serverBadgeText
                                                                anchors.centerIn: parent
                                                                text: modelData.text
                                                                color: textPrimary
                                                                font.pixelSize: typeCaption
                                                                font.weight: weightBold
                                                            }
                                                        }
                                                    }
                                                }
                                            }

                                            MouseArea {
                                                id: serverArea
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                acceptedButtons: Qt.LeftButton
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: if (root.hasToolsService) toolsService.selectItem(serverDelegateRoot.modelData.id)
                                            }
                                        }
                                    }

                                    footer: Item {
                                        width: serverList.width
                                        height: root.serverItems.length === 0 ? 180 : 0

                                        Column {
                                            anchors.centerIn: parent
                                            width: Math.min(parent.width - 40, 280)
                                            spacing: 10
                                            visible: parent.height > 0

                                            Text {
                                                width: parent.width
                                                text: tr("还没有 MCP 服务", "No MCP servers yet")
                                                color: textPrimary
                                                font.pixelSize: typeBody
                                                font.weight: weightBold
                                                horizontalAlignment: Text.AlignHCenter
                                            }

                                            Text {
                                                width: parent.width
                                                text: tr("点击左侧按钮新建一个 server，或导入你已有的 MCP JSON。", "Create a server from the left rail, or import an MCP definition you already use.")
                                                color: textSecondary
                                                font.pixelSize: typeMeta
                                                wrapMode: Text.WordWrap
                                                horizontalAlignment: Text.AlignHCenter
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            SplitView.preferredWidth: 492
                            SplitView.minimumWidth: 340
                            SplitView.fillWidth: true
                            SplitView.fillHeight: true
                            radius: 24
                            color: "transparent"
                            border.width: 0
                            border.color: "transparent"

                            Loader {
                                id: serverDetailLoader
                                anchors.fill: parent
                                anchors.margins: 16
                                active: true
                                sourceComponent: root.selectedItem.kind === "mcp_server" ? mcpServerDetailComponent : emptyServerDetailComponent
                            }
                        }
                    }

                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentWidth: width
                        contentHeight: policyStackColumn.implicitHeight
                        clip: true

                        ColumnLayout {
                            id: policyStackColumn
                            width: parent.width
                            spacing: 16

                            Rectangle {
                                Layout.fillWidth: true
                                radius: 24
                                color: isDark ? "#15100D" : "#FFF9F2"
                                border.width: 1
                                border.color: isDark ? "#18FFFFFF" : "#12000000"
                                implicitHeight: policyColumn.implicitHeight + 32

                                ColumnLayout {
                                    id: policyColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 16
                                    spacing: 14

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("暴露模式", "Exposure mode")
                                        color: textPrimary
                                        font.pixelSize: typeLabel
                                        font.weight: weightBold
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("Bao 每轮只暴露必要工具。这里控制默认暴露模式，以及允许参与自动选择的工具 bundle。", "Bao only exposes the tools needed for the current turn. Control the default exposure mode and the bundles eligible for automatic selection here.")
                                        color: textSecondary
                                        font.pixelSize: typeBody
                                        wrapMode: Text.WordWrap
                                    }

                                    RowLayout {
                                        spacing: 10
                                        Layout.fillWidth: true

                                        Repeater {
                                            model: [
                                                { value: "auto", zh: "自动", en: "Auto" },
                                                { value: "off", zh: "关闭自动暴露", en: "Off" }
                                            ]

                                            delegate: PillActionButton {
                                                required property var modelData

                                                text: root.tr(modelData.zh, modelData.en)
                                                fillColor: String(root.overview.toolExposureMode || "auto") === modelData.value ? accent : "transparent"
                                                hoverFillColor: String(root.overview.toolExposureMode || "auto") === modelData.value ? accentHover : bgCardHover
                                                outlineColor: String(root.overview.toolExposureMode || "auto") === modelData.value ? accent : borderSubtle
                                                textColor: String(root.overview.toolExposureMode || "auto") === modelData.value ? "#FFFFFFFF" : textSecondary
                                                outlined: String(root.overview.toolExposureMode || "auto") !== modelData.value
                                                onClicked: if (root.hasToolsService) toolsService.saveConfig({"tools.toolExposure.mode": modelData.value})
                                            }
                                        }
                                    }

                                    Flow {
                                        Layout.fillWidth: true
                                        spacing: 10

                                        Repeater {
                                            model: root.overview.exposureBundleOptions || []

                                            delegate: PillActionButton {
                                                required property var modelData
                                                readonly property bool enabledBundle: (root.overview.toolExposureBundles || []).indexOf(modelData.key) !== -1

                                                text: root.localizedText(modelData.displayLabel, modelData.key)
                                                outlined: true
                                                fillColor: enabledBundle ? accentMuted : "transparent"
                                                hoverFillColor: enabledBundle ? accentMuted : bgCardHover
                                                outlineColor: enabledBundle ? accent : borderSubtle
                                                hoverOutlineColor: enabledBundle ? accentHover : borderDefault
                                                textColor: textPrimary
                                                onClicked: {
                                                    if (!root.hasToolsService)
                                                        return
                                                    var bundles = (root.overview.toolExposureBundles || []).slice(0)
                                                    var index = bundles.indexOf(modelData.key)
                                                    if (index === -1)
                                                        bundles.push(modelData.key)
                                                    else
                                                        bundles.splice(index, 1)
                                                    toolsService.saveConfig({"tools.toolExposure.bundles": bundles})
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                radius: 24
                                color: isDark ? "#15100D" : "#FFF9F2"
                                border.width: 1
                                border.color: isDark ? "#18FFFFFF" : "#12000000"
                                implicitHeight: workspacePolicyColumn.implicitHeight + 32

                                ColumnLayout {
                                    id: workspacePolicyColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 16
                                    spacing: 14

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("工作区限制", "Workspace restrictions")
                                        color: textPrimary
                                        font.pixelSize: typeLabel
                                        font.weight: weightBold
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("当你需要更强的本地安全边界时，可以把文件与命令的作用范围收束到当前 workspace。", "When you want a stricter local safety boundary, keep file and command access scoped to the current workspace.")
                                        color: textSecondary
                                        font.pixelSize: typeBody
                                        wrapMode: Text.WordWrap
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 12

                                        Switch {
                                            id: restrictSwitch
                                            checked: Boolean(root.overview.restrictToWorkspace)
                                            onToggled: if (root.hasToolsService) toolsService.saveConfig({"tools.restrictToWorkspace": checked})
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2

                                            Text {
                                                text: tr("限制到 workspace", "Restrict to workspace")
                                                color: textPrimary
                                                font.pixelSize: typeBody
                                                font.weight: weightBold
                                            }

                                            Text {
                                                Layout.fillWidth: true
                                                text: tr("开启后，文件和命令工具默认只在工作区目录内操作。", "When enabled, file and command tools stay scoped to the workspace directory by default.")
                                                color: textSecondary
                                                font.pixelSize: typeMeta
                                                wrapMode: Text.WordWrap
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                radius: 24
                                color: isDark ? "#15100D" : "#FFF9F2"
                                border.width: 1
                                border.color: isDark ? "#18FFFFFF" : "#12000000"
                                implicitHeight: observabilityColumn.implicitHeight + 32

                                ColumnLayout {
                                    id: observabilityColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 16
                                    spacing: 14

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("最近一次工具观测", "Latest tool observability")
                                        color: textPrimary
                                        font.pixelSize: typeLabel
                                        font.weight: weightBold
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: tr("这里显示最近一次运行的工具调用摘要，用来判断自动暴露是否真的有帮助。", "This shows the latest tool-call summary so you can tell whether auto exposure is actually helping.")
                                        color: textSecondary
                                        font.pixelSize: typeBody
                                        wrapMode: Text.WordWrap
                                    }

                                    Flow {
                                        Layout.fillWidth: true
                                        spacing: 10

                                        Repeater {
                                            model: root.overview.observability || []

                                            delegate: Rectangle {
                                                required property var modelData

                                                visible: textLabel.text.length > 0
                                                radius: 14
                                                implicitHeight: 38
                                                implicitWidth: metricPair.implicitWidth + 18
                                                color: isDark ? "#181310" : "#FFFDFC"
                                                border.width: 1
                                                border.color: isDark ? "#12FFFFFF" : "#0E000000"

                                                Row {
                                                    id: metricPair
                                                    anchors.centerIn: parent
                                                    spacing: 8

                                                    Text {
                                                        id: textLabel
                                                        text: String(modelData.label || "")
                                                        color: textSecondary
                                                        font.pixelSize: typeCaption
                                                        font.weight: weightBold
                                                    }

                                                    Text {
                                                        text: String(modelData.value || "")
                                                        color: textPrimary
                                                        font.pixelSize: typeLabel
                                                        font.weight: weightBold
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
            }
        }
    }

    Component {
        id: builtinOverviewDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: overviewDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            ColumnLayout {
                id: overviewDetailLayout
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: overviewColumn.implicitHeight + 28

                    ColumnLayout {
                        id: overviewColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 10

                        Text {
                            Layout.fillWidth: true
                            text: root.tr("当前状态", "Current state")
                            color: textPrimary
                            font.pixelSize: typeLabel
                            font.weight: weightBold
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.statusDetail(root.selectedItem) || ""
                            color: textSecondary
                            font.pixelSize: typeBody
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: root.runtimeStateText(root.selectedItem)
                            color: textSecondary
                            font.pixelSize: typeCaption
                            font.weight: weightBold
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: root.exposureNote(root.selectedItem)
                            color: textSecondary
                            font.pixelSize: typeCaption
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: root.attentionAction(root.selectedItem)
                            color: accent
                            font.pixelSize: typeCaption
                            font.weight: weightBold
                            wrapMode: Text.WordWrap
                        }

                        Repeater {
                            model: root.selectedItem.metaLines || []

                            delegate: Text {
                                required property var modelData
                                Layout.fillWidth: true
                                text: "• " + String(modelData)
                                color: textSecondary
                                font.pixelSize: typeMeta
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: execDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: execDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            ColumnLayout {
                id: execDetailLayout
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: execColumn.implicitHeight + 28

                    ColumnLayout {
                        id: execColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 12

                        Text { text: root.tr("执行策略", "Execution policy"); color: textPrimary; font.pixelSize: typeLabel; font.weight: weightBold }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text { text: root.tr("超时（秒）", "Timeout (s)"); color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: execTimeoutField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    text: String(root.selectedItem.configValues.timeout || 60)
                                    color: textPrimary
                                    placeholderText: "60"
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text { text: root.tr("沙箱模式", "Sandbox mode"); color: textSecondary; font.pixelSize: typeMeta }
                                ComboBox {
                                    id: execSandboxCombo
                                    Layout.fillWidth: true
                                    model: ["full-auto", "semi-auto", "read-only"]
                                    currentIndex: Math.max(0, model.indexOf(String(root.selectedItem.configValues.sandboxMode || "semi-auto")))
                                }
                            }
                        }

                        Text { text: root.tr("PATH 追加", "PATH append"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: execPathField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            text: String(root.selectedItem.configValues.pathAppend || "")
                            color: textPrimary
                            placeholderText: root.tr("可选路径，用冒号分隔", "Optional path list, colon-separated")
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            Switch {
                                id: execRestrictSwitch
                                checked: Boolean(root.selectedItem.configValues.restrictToWorkspace)
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.tr("将执行范围限制在当前 workspace", "Restrict execution to the current workspace")
                                color: textPrimary
                                font.pixelSize: typeBody
                                wrapMode: Text.WordWrap
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            PillActionButton {
                                text: root.tr("保存执行策略", "Save exec settings")
                                iconSource: icon("circle-spark")
                                fillColor: accent
                                hoverFillColor: accentHover
                                onClicked: if (root.hasToolsService) toolsService.saveConfig({
                                    "tools.exec.timeout": parseInt(execTimeoutField.text || "60"),
                                    "tools.exec.pathAppend": execPathField.text,
                                    "tools.exec.sandboxMode": execSandboxCombo.currentText,
                                    "tools.restrictToWorkspace": execRestrictSwitch.checked
                                })
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: webDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: webDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            ColumnLayout {
                id: webDetailLayout
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: webColumn.implicitHeight + 28

                    ColumnLayout {
                        id: webColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 12

                        Text { text: root.tr("搜索与抓取", "Search and retrieval"); color: textPrimary; font.pixelSize: typeLabel; font.weight: weightBold }

                        Text { text: root.tr("搜索 provider", "Search provider"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: webProviderField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            text: String(root.selectedItem.configValues.provider || "")
                            color: textPrimary
                            placeholderText: "tavily / brave / exa"
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: "Tavily"; color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: tavilyField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    echoMode: TextInput.Password
                                    text: String(root.selectedItem.configValues.tavilyApiKey || "")
                                    color: textPrimary
                                    placeholderText: "tvly-..."
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: "Brave"; color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: braveField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    echoMode: TextInput.Password
                                    text: String(root.selectedItem.configValues.braveApiKey || "")
                                    color: textPrimary
                                    placeholderText: "BSA..."
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: "Exa"; color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: exaField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    echoMode: TextInput.Password
                                    text: String(root.selectedItem.configValues.exaApiKey || "")
                                    color: textPrimary
                                    placeholderText: "exa_..."
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: root.tr("最大结果数", "Max results"); color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: webMaxResultsField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    text: String(root.selectedItem.configValues.maxResults || 5)
                                    color: textPrimary
                                    placeholderText: "5"
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            Switch {
                                id: webBrowserEnabledSwitch
                                checked: Boolean(root.selectedItem.configValues.browserEnabled)
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.tr("启用托管浏览器自动化。Bao 只在需要交互页面、登录流或反爬回退时按需启动。", "Enable managed browser automation. Bao only starts it on demand for interactive pages, login flows, or anti-bot fallback.")
                                color: textPrimary
                                font.pixelSize: typeBody
                                wrapMode: Text.WordWrap
                            }
                        }

                        Text {
                            text: root.tr("Runtime 状态", "Runtime status")
                            color: textSecondary
                            font.pixelSize: typeMeta
                        }

                        Text {
                            Layout.fillWidth: true
                            text: Boolean(root.selectedItem.configValues.browserAvailable)
                                  ? root.tr("托管浏览器 runtime 已就绪。", "Managed browser runtime is ready.")
                                  : String(root.selectedItem.configValues.browserStatusDetail || root.tr("托管浏览器 runtime 尚未就绪。", "Managed browser runtime is not ready yet."))
                            color: textPrimary
                            font.pixelSize: typeBody
                            wrapMode: Text.WordWrap
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: String(root.selectedItem.configValues.browserProfilePath || "").length > 0
                            text: root.tr("托管 profile", "Managed profile") + ": " + String(root.selectedItem.configValues.browserProfilePath || "")
                            color: textSecondary
                            font.pixelSize: typeMeta
                            wrapMode: Text.WrapAnywhere
                        }

                        Text {
                            Layout.fillWidth: true
                            visible: String(root.selectedItem.configValues.browserRuntimeRoot || "").length > 0
                            text: root.tr("Runtime 目录", "Runtime root") + ": " + String(root.selectedItem.configValues.browserRuntimeRoot || "")
                            color: textSecondary
                            font.pixelSize: typeMeta
                            wrapMode: Text.WrapAnywhere
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            PillActionButton {
                                text: root.tr("保存 Web 配置", "Save web settings")
                                iconSource: icon("circle-spark")
                                fillColor: accent
                                hoverFillColor: accentHover
                                onClicked: if (root.hasToolsService) toolsService.saveConfig({
                                    "tools.web.search.provider": webProviderField.text,
                                    "tools.web.search.tavilyApiKey": tavilyField.text,
                                    "tools.web.search.braveApiKey": braveField.text,
                                    "tools.web.search.exaApiKey": exaField.text,
                                    "tools.web.search.maxResults": parseInt(webMaxResultsField.text || "5"),
                                    "tools.web.browser.enabled": webBrowserEnabledSwitch.checked
                                })
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: embeddingDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: embeddingDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            ColumnLayout {
                id: embeddingDetailLayout
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: embeddingColumn.implicitHeight + 28

                    ColumnLayout {
                        id: embeddingColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 12

                        Text { text: root.tr("向量嵌入", "Embeddings"); color: textPrimary; font.pixelSize: typeLabel; font.weight: weightBold }

                        Text { text: root.tr("模型", "Model"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: embeddingModelField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            text: String(root.selectedItem.configValues.model || "")
                            color: textPrimary
                            placeholderText: "text-embedding-3-small"
                        }

                        Text { text: root.tr("API Key", "API Key"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: embeddingKeyField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            echoMode: TextInput.Password
                            text: String(root.selectedItem.configValues.apiKey || "")
                            color: textPrimary
                            placeholderText: "sk-..."
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: root.tr("基础地址", "Base URL"); color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: embeddingBaseUrlField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    text: String(root.selectedItem.configValues.baseUrl || "")
                                    color: textPrimary
                                    placeholderText: "https://api.openai.com/v1"
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: root.tr("维度", "Dim"); color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: embeddingDimField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    text: String(root.selectedItem.configValues.dim || 0)
                                    color: textPrimary
                                    placeholderText: "0"
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            PillActionButton {
                                text: root.tr("保存 Embedding 配置", "Save embedding settings")
                                iconSource: icon("circle-spark")
                                fillColor: accent
                                hoverFillColor: accentHover
                                onClicked: if (root.hasToolsService) toolsService.saveConfig({
                                    "tools.embedding.model": embeddingModelField.text,
                                    "tools.embedding.apiKey": embeddingKeyField.text,
                                    "tools.embedding.baseUrl": embeddingBaseUrlField.text,
                                    "tools.embedding.dim": parseInt(embeddingDimField.text || "0")
                                })
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: imageGenerationDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: imageDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            ColumnLayout {
                id: imageDetailLayout
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: imageColumn.implicitHeight + 28

                    ColumnLayout {
                        id: imageColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 12

                        Text { text: root.tr("图像生成", "Image generation"); color: textPrimary; font.pixelSize: typeLabel; font.weight: weightBold }

                        Text { text: root.tr("API Key", "API Key"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: imageKeyField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            echoMode: TextInput.Password
                            text: String(root.selectedItem.configValues.apiKey || "")
                            color: textPrimary
                            placeholderText: "AIza..."
                        }

                        Text { text: root.tr("模型", "Model"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: imageModelField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            text: String(root.selectedItem.configValues.model || "")
                            color: textPrimary
                            placeholderText: "gemini-2.0-flash-exp-image-generation"
                        }

                        Text { text: root.tr("基础地址", "Base URL"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: imageBaseUrlField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            text: String(root.selectedItem.configValues.baseUrl || "")
                            color: textPrimary
                            placeholderText: "https://generativelanguage.googleapis.com/v1beta"
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            PillActionButton {
                                text: root.tr("保存图像配置", "Save image settings")
                                iconSource: icon("circle-spark")
                                fillColor: accent
                                hoverFillColor: accentHover
                                onClicked: if (root.hasToolsService) toolsService.saveConfig({
                                    "tools.imageGeneration.apiKey": imageKeyField.text,
                                    "tools.imageGeneration.model": imageModelField.text,
                                    "tools.imageGeneration.baseUrl": imageBaseUrlField.text
                                })
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: desktopDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: desktopDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            ColumnLayout {
                id: desktopDetailLayout
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: desktopColumn.implicitHeight + 28

                    ColumnLayout {
                        id: desktopColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 12

                        Text { text: root.tr("桌面自动化", "Desktop automation"); color: textPrimary; font.pixelSize: typeLabel; font.weight: weightBold }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            Switch {
                                id: desktopEnabledSwitch
                                checked: Boolean(root.selectedItem.configValues.enabled)
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.tr("允许 Bao 通过截图、点击、键盘和滚动操作当前桌面。", "Allow Bao to act on the current desktop with screenshots, clicks, keyboard input, and scrolling.")
                                color: textPrimary
                                font.pixelSize: typeBody
                                wrapMode: Text.WordWrap
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            PillActionButton {
                                text: root.tr("保存桌面权限", "Save desktop access")
                                iconSource: icon("circle-spark")
                                fillColor: accent
                                hoverFillColor: accentHover
                                onClicked: if (root.hasToolsService) toolsService.saveConfig({"tools.desktop.enabled": desktopEnabledSwitch.checked})
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: codingDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: codingDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            ColumnLayout {
                id: codingDetailLayout
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: codingColumn.implicitHeight + 28

                    ColumnLayout {
                        id: codingColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 12

                        Text { text: root.tr("可用后端", "Available backends"); color: textPrimary; font.pixelSize: typeLabel; font.weight: weightBold }

                        Text {
                            Layout.fillWidth: true
                            text: root.tr("这里不配置具体参数，只展示当前环境里可用的编程后端。", "This panel does not configure per-backend settings; it only shows the coding backends available in the current environment.")
                            color: textSecondary
                            font.pixelSize: typeMeta
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            wrapMode: Text.WordWrap
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8

                            Repeater {
                                model: (root.selectedItem.configValues.backends || []).length
                                       ? root.selectedItem.configValues.backends
                                       : [root.tr("当前未检测到后端", "No backend detected")]

                                delegate: Rectangle {
                                    required property var modelData

                                    radius: 12
                                    height: 26
                                    color: isDark ? "#1D1713" : "#FFFFFF"
                                    border.width: 1
                                    border.color: isDark ? "#16FFFFFF" : "#10000000"
                                    width: codingBackendLabel.implicitWidth + 18

                                    Text {
                                        id: codingBackendLabel
                                        anchors.centerIn: parent
                                        text: String(modelData)
                                        color: textPrimary
                                        font.pixelSize: typeCaption
                                        font.weight: weightBold
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: emptyServerDetailComponent

        ColumnLayout {
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: root.tr("选择一个 MCP 服务", "Choose an MCP server")
                color: textPrimary
                font.pixelSize: typeTitle
                font.weight: weightBold
            }

            Text {
                Layout.fillWidth: true
                text: root.tr("从中栏选一个已存在的服务，或从左侧新建一个 server。", "Select an existing server from the middle column, or create a new one from the left rail.")
                color: textSecondary
                font.pixelSize: typeBody
                wrapMode: Text.WordWrap
            }
        }
    }

    Component {
        id: mcpServerDetailComponent

        Flickable {
            contentWidth: width
            contentHeight: serverDetailLayout.implicitHeight
            clip: true
            ScrollIndicator.vertical: ScrollIndicator {
                visible: false
                width: 4
                contentItem: Rectangle {
                    implicitWidth: 2
                    radius: 1
                    color: isDark ? "#28FFFFFF" : "#22000000"
                }
            }

            readonly property var initialDraft: root.serverDraftFromItem(root.selectedItem)

            ColumnLayout {
                id: serverDetailLayout
                width: parent.width
                spacing: 14

                Text {
                    Layout.fillWidth: true
                    text: String(root.selectedItem.name || root.tr("MCP 服务", "MCP server"))
                    color: textPrimary
                    font.pixelSize: typeTitle
                    font.weight: weightBold
                }

                Text {
                    Layout.fillWidth: true
                    text: root.statusDetail(root.selectedItem) || root.tr("编辑 server 定义，保存后会写入配置；测试按钮会直接复用 MCP 握手逻辑。", "Edit the server definition and save it to config. The Test action reuses the real MCP handshake path.")
                    color: textSecondary
                    font.pixelSize: typeBody
                    wrapMode: Text.WordWrap
                }

                Rectangle {
                    Layout.fillWidth: true
                    radius: 20
                    color: isDark ? "#130F0C" : "#FBF7F2"
                    border.width: 1
                    border.color: isDark ? "#12FFFFFF" : "#10000000"
                    implicitHeight: serverInspectorColumn.implicitHeight + 28

                    ColumnLayout {
                        id: serverInspectorColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 12

                        Text { text: root.tr("服务定义", "Server definition"); color: textPrimary; font.pixelSize: typeLabel; font.weight: weightBold }

                        Text { text: root.tr("名称", "Name"); color: textSecondary; font.pixelSize: typeMeta }
                        TextField {
                            id: serverNameField
                            property bool baoClickAwayEditor: true
                            Layout.fillWidth: true
                            text: initialDraft.name
                            color: textPrimary
                        }

                        Text { text: root.tr("Transport", "Transport"); color: textSecondary; font.pixelSize: typeMeta }
                        ComboBox {
                            id: serverTransportCombo
                            Layout.fillWidth: true
                            model: ["stdio", "http"]
                            currentIndex: Math.max(0, model.indexOf(String(initialDraft.transport || "stdio")))
                        }

                        ColumnLayout {
                            visible: serverTransportCombo.currentText === "stdio"
                            Layout.fillWidth: true
                            spacing: 10

                            Text { text: root.tr("命令", "Command"); color: textSecondary; font.pixelSize: typeMeta }
                            TextField {
                                id: serverCommandField
                                property bool baoClickAwayEditor: true
                                Layout.fillWidth: true
                                text: initialDraft.command
                                color: textPrimary
                                placeholderText: "npx"
                            }

                            Text { text: root.tr("参数（每行一个）", "Args (one per line)"); color: textSecondary; font.pixelSize: typeMeta }
                            TextArea {
                                id: serverArgsField
                                property bool baoClickAwayEditor: true
                                Layout.fillWidth: true
                                Layout.preferredHeight: 96
                                text: initialDraft.argsText
                                wrapMode: TextArea.Wrap
                                color: textPrimary
                            }

                            Text { text: root.tr("环境变量（KEY=VALUE）", "Environment (KEY=VALUE)"); color: textSecondary; font.pixelSize: typeMeta }
                            TextArea {
                                id: serverEnvField
                                property bool baoClickAwayEditor: true
                                Layout.fillWidth: true
                                Layout.preferredHeight: 88
                                text: initialDraft.envText
                                wrapMode: TextArea.Wrap
                                color: textPrimary
                            }
                        }

                        ColumnLayout {
                            visible: serverTransportCombo.currentText === "http"
                            Layout.fillWidth: true
                            spacing: 10

                            Text { text: root.tr("URL", "URL"); color: textSecondary; font.pixelSize: typeMeta }
                            TextField {
                                id: serverUrlField
                                property bool baoClickAwayEditor: true
                                Layout.fillWidth: true
                                text: initialDraft.url
                                color: textPrimary
                                placeholderText: "https://example.com/mcp"
                            }

                            Text { text: root.tr("Headers（Header: Value）", "Headers (Header: Value)"); color: textSecondary; font.pixelSize: typeMeta }
                            TextArea {
                                id: serverHeadersField
                                property bool baoClickAwayEditor: true
                                Layout.fillWidth: true
                                Layout.preferredHeight: 88
                                text: initialDraft.headersText
                                wrapMode: TextArea.Wrap
                                color: textPrimary
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: root.tr("工具超时", "Tool timeout"); color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: serverTimeoutField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    text: String(initialDraft.toolTimeoutSeconds || 30)
                                    color: textPrimary
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text { text: root.tr("最大工具数", "Max tools"); color: textSecondary; font.pixelSize: typeMeta }
                                TextField {
                                    id: serverMaxToolsField
                                    property bool baoClickAwayEditor: true
                                    Layout.fillWidth: true
                                    text: String(initialDraft.maxTools || 0)
                                    color: textPrimary
                                }
                            }
                        }

                        Text { text: root.tr("Slim schema", "Slim schema"); color: textSecondary; font.pixelSize: typeMeta }
                        ComboBox {
                            id: serverSlimSchemaMode
                            Layout.fillWidth: true
                            model: ["inherit", "enabled", "disabled"]
                            currentIndex: Math.max(0, model.indexOf(root.slimSchemaModeFromValue(initialDraft.slimSchema)))
                            textRole: "display"

                            delegate: ItemDelegate {
                                width: ListView.view ? ListView.view.width : implicitWidth
                                text: modelData === "inherit" ? root.tr("继承全局设置", "Inherit global setting")
                                     : modelData === "enabled" ? root.tr("强制启用", "Force enable")
                                     : root.tr("强制关闭", "Force disable")
                            }

                            contentItem: Text {
                                leftPadding: 0
                                rightPadding: serverSlimSchemaMode.indicator.width + serverSlimSchemaMode.spacing
                                text: serverSlimSchemaMode.currentText === "inherit" ? root.tr("继承全局设置", "Inherit global setting")
                                     : serverSlimSchemaMode.currentText === "enabled" ? root.tr("强制启用", "Force enable")
                                     : root.tr("强制关闭", "Force disable")
                                color: textPrimary
                                font.pixelSize: typeBody
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: probeColumn.implicitHeight + 20
                            radius: 18
                            color: isDark ? "#17110E" : "#FFFDFC"
                            border.width: 1
                            border.color: isDark ? "#12FFFFFF" : "#10000000"

                            Column {
                                id: probeColumn
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 8

                                Text {
                                    width: parent.width
                                    text: root.tr("最近一次探测", "Latest probe")
                                    color: textSecondary
                                    font.pixelSize: typeMeta
                                    font.weight: weightBold
                                    font.letterSpacing: letterWide
                                }

                                Text {
                                    width: parent.width
                                    text: root.selectedItem.probe && root.selectedItem.probe.error
                                          ? String(root.selectedItem.probe.error)
                                          : (root.selectedItem.probe && root.selectedItem.probe.toolNames && root.selectedItem.probe.toolNames.length
                                             ? root.selectedItem.probe.toolNames.join(", ")
                                             : root.tr("还没有探测结果。", "No probe result yet."))
                                    color: root.selectedItem.probe && root.selectedItem.probe.error ? statusError : textPrimary
                                    font.pixelSize: typeMeta
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            function draftPayload() {
                                return {
                                    previousName: initialDraft.previousName,
                                    name: serverNameField.text,
                                    transport: serverTransportCombo.currentText,
                                    command: serverCommandField.text,
                                    argsText: serverArgsField.text,
                                    envText: serverEnvField.text,
                                    url: serverUrlField.text,
                                    headersText: serverHeadersField.text,
                                    toolTimeoutSeconds: serverTimeoutField.text,
                                    maxTools: serverMaxToolsField.text,
                                    slimSchema: root.slimSchemaValueFromMode(serverSlimSchemaMode.currentText)
                                }
                            }

                            PillActionButton {
                                text: root.tr("测试连接", "Test")
                                iconSource: icon("activity")
                                outlined: true
                                fillColor: "transparent"
                                hoverFillColor: bgCardHover
                                outlineColor: borderSubtle
                                hoverOutlineColor: borderDefault
                                textColor: textPrimary
                                onClicked: if (root.hasToolsService) toolsService.probeMcpServerPayload(parent.draftPayload())
                            }

                            PillActionButton {
                                text: root.tr("保存服务", "Save server")
                                iconSource: icon("circle-spark")
                                fillColor: accent
                                hoverFillColor: accentHover
                                onClicked: if (root.hasToolsService) toolsService.saveMcpServer(parent.draftPayload())
                            }

                            Item { Layout.fillWidth: true }

                            PillActionButton {
                                text: root.tr("删除", "Delete")
                                fillColor: statusError
                                hoverFillColor: Qt.darker(statusError, 1.06)
                                onClicked: if (root.hasToolsService) toolsService.deleteMcpServer(initialDraft.previousName)
                            }
                        }
                    }
                }
            }
        }
    }

    AppModal {
        id: createServerModal
        title: tr("新增 MCP 服务", "Create MCP server")
        closeText: tr("关闭", "Close")
        darkMode: isDark
        maxModalWidth: 620
        maxModalHeight: 680

        onOpened: {
            createNameField.text = ""
            createTransportCombo.currentIndex = 0
            createCommandField.text = ""
            createArgsField.text = ""
            createEnvField.text = ""
            createUrlField.text = ""
            createHeadersField.text = ""
            createTimeoutField.text = "30"
            createMaxToolsField.text = "0"
            createSlimSchemaSwitch.checked = false
            createNameField.forceActiveFocus()
        }

        ColumnLayout {
            width: parent.width
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: tr("支持 stdio 和 HTTP 两种 transport。创建后会写入 `tools.mcpServers`。", "Both stdio and HTTP transports are supported. Bao writes the result into `tools.mcpServers`.")
                color: textSecondary
                font.pixelSize: typeMeta
                wrapMode: Text.WordWrap
            }

            Text { text: tr("名称", "Name"); color: textSecondary; font.pixelSize: typeMeta }
            TextField {
                id: createNameField
                property bool baoClickAwayEditor: true
                Layout.fillWidth: true
                color: textPrimary
            }

            Text { text: tr("Transport", "Transport"); color: textSecondary; font.pixelSize: typeMeta }
            ComboBox {
                id: createTransportCombo
                Layout.fillWidth: true
                model: ["stdio", "http"]
            }

            ColumnLayout {
                visible: createTransportCombo.currentText === "stdio"
                Layout.fillWidth: true
                spacing: 10

                Text { text: tr("命令", "Command"); color: textSecondary; font.pixelSize: typeMeta }
                TextField { id: createCommandField; property bool baoClickAwayEditor: true; Layout.fillWidth: true; color: textPrimary; placeholderText: "npx" }

                Text { text: tr("参数（每行一个）", "Args (one per line)"); color: textSecondary; font.pixelSize: typeMeta }
                TextArea { id: createArgsField; property bool baoClickAwayEditor: true; Layout.fillWidth: true; Layout.preferredHeight: 86; color: textPrimary; wrapMode: TextArea.Wrap }

                Text { text: tr("环境变量（KEY=VALUE）", "Environment (KEY=VALUE)"); color: textSecondary; font.pixelSize: typeMeta }
                TextArea { id: createEnvField; property bool baoClickAwayEditor: true; Layout.fillWidth: true; Layout.preferredHeight: 76; color: textPrimary; wrapMode: TextArea.Wrap }
            }

            ColumnLayout {
                visible: createTransportCombo.currentText === "http"
                Layout.fillWidth: true
                spacing: 10

                Text { text: tr("URL", "URL"); color: textSecondary; font.pixelSize: typeMeta }
                TextField { id: createUrlField; property bool baoClickAwayEditor: true; Layout.fillWidth: true; color: textPrimary; placeholderText: "https://example.com/mcp" }

                Text { text: tr("Headers（Header: Value）", "Headers (Header: Value)"); color: textSecondary; font.pixelSize: typeMeta }
                TextArea { id: createHeadersField; property bool baoClickAwayEditor: true; Layout.fillWidth: true; Layout.preferredHeight: 76; color: textPrimary; wrapMode: TextArea.Wrap }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                TextField { id: createTimeoutField; property bool baoClickAwayEditor: true; Layout.fillWidth: true; color: textPrimary; placeholderText: root.tr("超时秒数", "Timeout seconds") }
                TextField { id: createMaxToolsField; property bool baoClickAwayEditor: true; Layout.fillWidth: true; color: textPrimary; placeholderText: root.tr("最大工具数（0=不限）", "Max tools (0=unlimited)") }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Switch { id: createSlimSchemaSwitch }
                Text {
                    Layout.fillWidth: true
                    text: tr("覆盖全局 slim schema 设置", "Override the global slim schema setting")
                    color: textPrimary
                    font.pixelSize: typeBody
                    wrapMode: Text.WordWrap
                }
            }
        }

        footer: [
            PillActionButton {
                text: root.tr("测试", "Test")
                iconSource: icon("activity")
                outlined: true
                fillColor: "transparent"
                hoverFillColor: bgCardHover
                outlineColor: borderSubtle
                hoverOutlineColor: borderDefault
                textColor: textPrimary
                onClicked: if (root.hasToolsService) toolsService.probeMcpServerPayload({
                    name: createNameField.text,
                    transport: createTransportCombo.currentText,
                    command: createCommandField.text,
                    argsText: createArgsField.text,
                    envText: createEnvField.text,
                    url: createUrlField.text,
                    headersText: createHeadersField.text,
                    toolTimeoutSeconds: createTimeoutField.text,
                    maxTools: createMaxToolsField.text,
                    slimSchema: createSlimSchemaSwitch.checked
                })
            },
            PillActionButton {
                text: root.tr("创建服务", "Create server")
                iconSource: icon("circle-spark")
                fillColor: accent
                hoverFillColor: accentHover
                onClicked: {
                    if (!root.hasToolsService)
                        return
                    if (toolsService.saveMcpServer({
                        name: createNameField.text,
                        transport: createTransportCombo.currentText,
                        command: createCommandField.text,
                        argsText: createArgsField.text,
                        envText: createEnvField.text,
                        url: createUrlField.text,
                        headersText: createHeadersField.text,
                        toolTimeoutSeconds: createTimeoutField.text,
                        maxTools: createMaxToolsField.text,
                        slimSchema: createSlimSchemaSwitch.checked
                    }))
                        createServerModal.close()
                }
            }
        ]
    }

    SequentialAnimation {
        id: revealAnimation

        ParallelAnimation {
            NumberAnimation { target: root; property: "revealOpacity"; to: 1.0; duration: motionUi; easing.type: easeStandard }
            NumberAnimation { target: root; property: "revealScale"; to: 1.0; duration: motionPanel; easing.type: easeEmphasis }
            NumberAnimation { target: root; property: "revealShift"; to: 0.0; duration: motionPanel; easing.type: easeEmphasis }
        }
    }
}
