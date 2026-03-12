import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    objectName: "cronWorkspaceRoot"

    property bool active: false
    property var appRoot: null
    readonly property bool hasCronService: typeof cronService !== "undefined" && cronService !== null
    readonly property var draft: hasCronService ? cronService.draft : ({})
    readonly property var selectedTask: hasCronService ? cronService.selectedTask : ({})
    readonly property bool hasDraft: hasCronService ? cronService.hasDraft : false
    readonly property bool hasSelection: hasCronService ? cronService.hasSelection : false
    readonly property bool editingNewTask: hasCronService ? cronService.editingNewTask : false
    readonly property bool showingExistingTask: draftString("id", "") !== ""
    readonly property var visibleTask: showingExistingTask ? selectedTask : ({})
    readonly property string resolvedLang: {
        if (typeof effectiveLang === "string" && effectiveLang !== "")
            return effectiveLang
        if (typeof uiLanguage === "string" && uiLanguage !== "auto")
            return uiLanguage
        if (typeof autoLanguage === "string" && autoLanguage !== "")
            return autoLanguage
        return "en"
    }
    property real revealOpacity: 1.0
    property real revealScale: 1.0
    property real revealShift: 0.0

    readonly property color cronAccent: isDark ? Qt.rgba(1.0, 0.69, 0.20, 1.0) : Qt.rgba(0.95, 0.56, 0.05, 1.0)
    readonly property color cronAccentHover: isDark ? Qt.rgba(1.0, 0.74, 0.30, 1.0) : Qt.rgba(0.98, 0.61, 0.10, 1.0)
    readonly property color panelFill: bgCard
    readonly property color panelBorder: isDark ? "#20FFFFFF" : "#126E4B2A"
    readonly property color sectionFill: isDark ? "#16110E" : "#FCF8F3"
    readonly property color fieldFill: isDark ? "#120E0C" : "#F7EFE6"
    readonly property color fieldHoverFill: isDark ? "#171210" : "#F9F3EB"
    readonly property color fieldBorder: isDark ? "#18FFFFFF" : "#14000000"
    readonly property color selectedRowFill: isDark ? "#211813" : "#FFF1E3"
    readonly property color selectedRowBorder: cronAccent

    function tr(zh, en) {
        return resolvedLang === "zh" ? zh : en
    }

    function playReveal() {
        revealOpacity = motionPageRevealStartOpacity
        revealScale = motionPageRevealStartScale
        revealShift = motionPageShiftSubtle
        revealAnimation.restart()
    }

    function setDraft(path, value) {
        if (hasCronService)
            cronService.updateDraftField(path, value)
    }

    function chooseTask(taskId) {
        if (hasCronService)
            cronService.selectTask(taskId)
    }

    function openSelectedSession() {
        if (appRoot)
            appRoot.activeWorkspace = "sessions"
        if (hasCronService)
            cronService.openSelectedSession()
    }

    function draftString(key, fallback) {
        var value = draft[key]
        if (value === undefined || value === null)
            return fallback || ""
        return String(value)
    }

    function draftBool(key, fallback) {
        var value = draft[key]
        if (value === undefined || value === null)
            return !!fallback
        return Boolean(value)
    }

    function statusItems() {
        return [
            { key: "all", label: tr("全部", "All") },
            { key: "enabled", label: tr("启用中", "Enabled") },
            { key: "issues", label: tr("异常", "Errors") }
        ]
    }

    function statusLabel(statusKey) {
        switch (statusKey) {
        case "scheduled":
            return tr("已调度", "Scheduled")
        case "error":
            return tr("异常", "Error")
        case "idle_ok":
            return tr("已就绪", "Ready")
        case "disabled":
            return tr("已停用", "Disabled")
        default:
            return tr("未安排", "Not scheduled")
        }
    }

    function statusColor(statusKey) {
        switch (statusKey) {
        case "scheduled":
            return cronAccent
        case "error":
            return statusError
        case "idle_ok":
            return statusSuccess
        case "disabled":
            return textTertiary
        default:
            return textSecondary
        }
    }

    function statusSurface(statusKey) {
        switch (statusKey) {
        case "scheduled":
            return isDark ? "#23180F" : "#FFF2E2"
        case "error":
            return isDark ? "#2A1513" : "#FFF1EE"
        case "idle_ok":
            return isDark ? "#132116" : "#EFF9F1"
        case "disabled":
            return isDark ? "#161616" : "#F3F1EE"
        default:
            return isDark ? "#17120F" : "#F7F2EC"
        }
    }

    function summaryText(value, fallbackZh, fallbackEn) {
        var text = String(value || "")
        return text !== "" ? text : tr(fallbackZh, fallbackEn)
    }

    function icon(path) {
        return "../resources/icons/vendor/iconoir/" + path + ".svg"
    }

    function labIcon(path) {
        return "../resources/icons/vendor/lucide-lab/" + path + ".svg"
    }

    function scheduleModeHint() {
        var kind = draftString("schedule_kind", "every")
        if (kind === "at")
            return tr("适合一次性提醒，例如明天上午提醒我。", "Best for one-time reminders like reminding you tomorrow morning.")
        if (kind === "cron")
            return tr("高级模式，只有在你清楚 Cron 语法时再使用。", "Advanced mode. Use it only if you are comfortable with cron syntax.")
        return ""
    }

    function deliveryHint() {
        return draftBool("deliver", false)
            ? tr("Bao 执行后会把结果发到你指定的渠道。", "Bao will send the result to the channel you choose.")
            : ""
    }

    onActiveChanged: {
        if (active) {
            playReveal()
            if (hasCronService)
                cronService.refresh()
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
                    panelColor: isDark ? "#15100E" : "#FFFBF7"
                    panelBorderColor: isDark ? "#1CFFFFFF" : "#12000000"
                    overlayColor: isDark ? "#08FFFFFF" : "#04FFFFFF"
                    overlayVisible: true
                    sideGlowVisible: false
                    accentBlobVisible: false
                    padding: 14

                    RowLayout {
                        id: headerRow
                        width: parent.width
                        spacing: 12

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            RowLayout {
                                spacing: 10

                                Rectangle {
                                    width: 40
                                    height: 40
                                    radius: 14
                                    color: isDark ? "#1E1612" : "#FFF0DE"

                                    Image {
                                        anchors.centerIn: parent
                                        width: 18
                                        height: 18
                                        source: root.icon("calendar-rotate")
                                        sourceSize: Qt.size(width, height)
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                        mipmap: true
                                    }
                                }

                                ColumnLayout {
                                    spacing: 2

                                    Text {
                                        text: tr("定时任务", "Scheduled Tasks")
                                        color: textPrimary
                                        font.pixelSize: typeTitle
                                        font.weight: weightBold
                                    }

                                    Text {
                                        text: tr("给 Bao 安排自动提醒和周期工作。", "Set up reminders and recurring work for Bao.")
                                        color: textSecondary
                                        font.pixelSize: typeMeta
                                    }
                                }
                            }

                            Text {
                                color: textSecondary
                                font.pixelSize: typeMeta
                                text: tr("在这里集中管理提醒、投递和自动任务。", "Manage reminders, delivery, and recurring work in one place.")
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                wrapMode: Text.WordWrap
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.alignment: Qt.AlignRight | Qt.AlignTop
                            spacing: 8

                            PillActionButton {
                                text: tr("新建任务", "New task")
                                iconSource: root.icon("circle-spark")
                                fillColor: cronAccent
                                hoverFillColor: cronAccentHover
                                onClicked: if (hasCronService) cronService.newDraft()
                            }

                            PillActionButton {
                                text: tr("刷新", "Refresh")
                                iconSource: root.labIcon("watch-loader")
                                fillColor: "transparent"
                                hoverFillColor: bgCardHover
                                outlineColor: borderSubtle
                                textColor: textSecondary
                                outlined: true
                                onClicked: if (hasCronService) cronService.refresh()
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: hasCronService && cronService.noticeText !== ""
                    radius: 18
                    color: cronService.noticeSuccess ? (isDark ? "#132015" : "#ECF8EF") : (isDark ? "#2A1513" : "#FFF1EE")
                    border.width: 1
                    border.color: cronService.noticeSuccess ? (isDark ? "#245A37" : "#AED9B6") : (isDark ? "#6B2A22" : "#F0B2A8")
                    implicitHeight: noticeLabel.implicitHeight + 18

                    Text {
                        id: noticeLabel
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: 14
                        text: cronService.noticeText
                        color: cronService.noticeSuccess ? textPrimary : statusError
                        font.pixelSize: typeLabel
                        font.weight: weightMedium
                        wrapMode: Text.WordWrap
                    }
                }

                SplitView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    orientation: Qt.Horizontal
                    spacing: 10
                    handle: Item {
                        implicitWidth: 10
                        implicitHeight: 10

                        Column {
                            anchors.centerIn: parent
                            spacing: 6

                            Repeater {
                                model: 18

                                delegate: Rectangle {
                                    width: 2
                                    height: 4
                                    radius: 1
                                    color: isDark ? "#18FFFFFF" : "#16000000"
                                }
                            }
                        }
                    }

                    Item {
                        id: listPanel
                        objectName: "cronListPanel"
                        SplitView.preferredWidth: 320
                        SplitView.minimumWidth: 288
                        SplitView.maximumWidth: 340
                        SplitView.fillHeight: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 2
                            spacing: 12

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 44
                            radius: 18
                            color: searchArea.containsMouse ? fieldHoverFill : fieldFill
                            border.width: searchField.activeFocus ? 1.5 : 1
                            border.color: searchField.activeFocus ? borderFocus : fieldBorder

                            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                            Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                            MouseArea {
                                id: searchArea
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.NoButton
                            }

                            TextField {
                                id: searchField
                                property bool baoClickAwayEditor: true
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                anchors.verticalCenter: parent.verticalCenter
                                hoverEnabled: true
                                color: textPrimary
                                placeholderText: tr("搜索任务名称、消息或渠道", "Search tasks, messages, or channels")
                                placeholderTextColor: textPlaceholder
                                background: null
                                leftPadding: 26
                                rightPadding: 0
                                topPadding: 0
                                bottomPadding: 0
                                verticalAlignment: TextInput.AlignVCenter
                                selectionColor: textSelectionBg
                                selectedTextColor: textSelectionFg
                                onTextEdited: if (hasCronService) cronService.setFilterQuery(text)

                                Image {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 16
                                    height: 16
                                    source: root.icon("page-search")
                                    sourceSize: Qt.size(width, height)
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                    mipmap: true
                                    opacity: 0.52
                                }
                            }
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8

                            Repeater {
                                model: root.statusItems()

                                delegate: PillActionButton {
                                    required property var modelData
                                    text: modelData.label
                                    fillColor: hasCronService && cronService.statusFilter === modelData.key ? cronAccent : "transparent"
                                    hoverFillColor: hasCronService && cronService.statusFilter === modelData.key ? cronAccentHover : bgCardHover
                                    outlineColor: hasCronService && cronService.statusFilter === modelData.key ? cronAccent : borderSubtle
                                    textColor: hasCronService && cronService.statusFilter === modelData.key ? "#FFFFFFFF" : textSecondary
                                    outlined: !hasCronService || cronService.statusFilter !== modelData.key
                                    horizontalPadding: 14
                                    minHeight: 30
                                    onClicked: if (hasCronService) cronService.setStatusFilter(modelData.key)
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                text: tr("任务列表", "Task list")
                                color: textPrimary
                                font.pixelSize: typeBody + 1
                                font.weight: weightBold
                            }

                            Item { Layout.fillWidth: true }

                            Text {
                                text: hasCronService ? (cronService.visibleTaskCount + " / " + cronService.totalTaskCount) : "0 / 0"
                                color: textSecondary
                                font.pixelSize: typeMeta
                                font.weight: weightBold
                            }
                        }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            Loader {
                                anchors.fill: parent
                                active: hasCronService && cronService.visibleTaskCount === 0
                                sourceComponent: Component {
                                    Item {
                                        Column {
                                            anchors.centerIn: parent
                                            width: Math.min(parent.width - 32, 220)
                                            spacing: 10

                                            Text {
                                                width: parent.width
                                                text: tr("当前没有符合条件的任务", "No tasks match the current view")
                                                color: textPrimary
                                                font.pixelSize: typeBody + 1
                                                font.weight: weightBold
                                                wrapMode: Text.WordWrap
                                                horizontalAlignment: Text.AlignHCenter
                                            }

                                            Text {
                                                width: parent.width
                                                text: tr("你可以从右上角新建任务，或调整搜索和筛选。", "Create a task from the top right, or adjust search and filters.")
                                                color: textSecondary
                                                font.pixelSize: typeBody
                                                wrapMode: Text.WordWrap
                                                horizontalAlignment: Text.AlignHCenter
                                            }
                                        }
                                    }
                                }
                            }

                            ListView {
                                id: taskList
                                objectName: "cronTaskList"
                                anchors.fill: parent
                                anchors.topMargin: 4
                                visible: !hasCronService || cronService.visibleTaskCount > 0
                                clip: true
                                spacing: 8
                                model: hasCronService ? cronService.tasksModel : null

                                delegate: Rectangle {
                                    objectName: isDraft ? "cronDraftRow" : "cronTaskRow_" + taskId
                                    required property string taskId
                                    required property string name
                                    required property bool enabled
                                    required property string statusKey
                                    required property string scheduleSummary
                                    required property string nextRunText
                                    required property string lastResultText
                                    required property bool isDraft
                                    color: hasCronService && cronService.activeListItemId === taskId ? selectedRowFill : (rowHit.containsMouse ? bgCardHover : "transparent")
                                    radius: 18
                                    border.width: hasCronService && cronService.activeListItemId === taskId ? 1.2 : 1
                                    border.color: hasCronService && cronService.activeListItemId === taskId ? selectedRowBorder : fieldBorder
                                    width: taskList.width
                                        implicitHeight: rowColumn.implicitHeight + 16

                                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                    MouseArea {
                                        id: rowHit
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.chooseTask(taskId)
                                    }

                                    ColumnLayout {
                                        id: rowColumn
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        spacing: 6

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8

                                            Image {
                                                width: 16
                                                height: 16
                                                source: statusKey === "error" ? root.icon("message-alert") : root.icon("calendar-rotate")
                                                sourceSize: Qt.size(width, height)
                                                fillMode: Image.PreserveAspectFit
                                                smooth: true
                                                mipmap: true
                                                opacity: 0.9
                                            }

                                            Rectangle {
                                                radius: 10
                                                color: root.statusSurface(statusKey)
                                                implicitHeight: 22
                                                implicitWidth: stateLabel.implicitWidth + 16

                                                Text {
                                                    id: stateLabel
                                                    anchors.centerIn: parent
                                                    text: root.statusLabel(statusKey)
                                                    color: root.statusColor(statusKey)
                                                    font.pixelSize: typeMeta
                                                    font.weight: weightBold
                                                }
                                            }

                                            Item { Layout.fillWidth: true }

                                        PillActionButton {
                                            visible: !isDraft
                                            iconSource: enabled ? root.icon("bubble-xmark") : root.icon("circle-spark")
                                            text: enabled ? tr("停用", "Pause") : tr("启用", "Enable")
                                            fillColor: "transparent"
                                            hoverFillColor: enabled ? (isDark ? "#311816" : "#FFF0EC") : bgCardHover
                                            outlineColor: enabled ? statusError : borderSubtle
                                            hoverOutlineColor: enabled ? statusError : borderDefault
                                            textColor: enabled ? statusError : textSecondary
                                            outlined: true
                                            horizontalPadding: 10
                                            minHeight: 26
                                                onClicked: {
                                                    root.chooseTask(taskId)
                                                    if (hasCronService)
                                                        cronService.setSelectedEnabled(!enabled)
                                                }
                                            }
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: name
                                            color: textPrimary
                                            font.pixelSize: typeBody
                                            font.weight: weightBold
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: scheduleSummary
                                            color: textSecondary
                                            font.pixelSize: typeBody
                                            elide: Text.ElideRight
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 10

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2

                                                Text {
                                                    text: tr("下次执行", "Next run")
                                                    color: textTertiary
                                                    font.pixelSize: typeMeta
                                                    font.weight: weightBold
                                                }

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: summaryText(nextRunText, "未安排", "Not scheduled")
                                                    color: textPrimary
                                                    font.pixelSize: typeBody
                                                    elide: Text.ElideRight
                                                }
                                            }

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2

                                                Text {
                                                    text: tr("最近结果", "Last result")
                                                    color: textTertiary
                                                    font.pixelSize: typeMeta
                                                    font.weight: weightBold
                                                }

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: lastResultText
                                                    color: statusKey === "error" ? statusError : textPrimary
                                                    font.pixelSize: typeBody
                                                    elide: Text.ElideRight
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
                        id: detailPanel
                        objectName: "cronDetailPanel"
                        SplitView.preferredWidth: 620
                        SplitView.minimumWidth: 420
                        SplitView.fillWidth: true
                        SplitView.fillHeight: true

                        Loader {
                            anchors.fill: parent
                            active: !hasDraft
                            sourceComponent: Component {
                                Item {
                                    Column {
                                        anchors.centerIn: parent
                                        width: Math.min(parent.width - 40, 320)
                                        spacing: 10

                                    Text {
                                        width: parent.width
                                        text: hasCronService && cronService.totalTaskCount === 0
                                              ? tr("从右上角创建第一个任务", "Create your first task from the top right")
                                              : tr("先从左边选中一个任务", "Select a task from the left first")
                                        color: textPrimary
                                        font.pixelSize: typeTitle
                                        font.weight: weightBold
                                        wrapMode: Text.WordWrap
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    Text {
                                        width: parent.width
                                        text: hasCronService && cronService.totalTaskCount === 0
                                              ? tr(
                                                    "创建后，这里会一步步引导你设置执行时间和消息内容。",
                                                    "After you create one, this area guides you through the time and message setup."
                                                    )
                                              : tr(
                                                    "选中后，这里会一步步引导你完成设置。",
                                                    "After you select one, this area guides you through the setup step by step."
                                                    )
                                        color: textSecondary
                                        font.pixelSize: typeBody
                                        wrapMode: Text.WordWrap
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                    }
                                }
                            }
                        }

                        ScrollView {
                            id: detailScroll
                            anchors.fill: parent
                            anchors.margins: 2
                            visible: hasDraft
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: Math.max(0, detailScroll.availableWidth)
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 4

                                    Text {
                                        text: editingNewTask ? tr("正在新建任务", "Creating a task") : tr("任务详情", "Task details")
                                        color: textSecondary
                                        font.pixelSize: typeMeta
                                        font.weight: weightBold
                                        font.letterSpacing: letterWide
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: draftString("name", "") !== "" ? draftString("name", "") : tr("未命名任务", "Untitled task")
                                        color: textPrimary
                                        font.pixelSize: typeLabel
                                        font.weight: weightBold
                                        wrapMode: Text.NoWrap
                                        elide: Text.ElideRight
                                    }
                                }

                                Flow {
                                    Layout.alignment: Qt.AlignRight | Qt.AlignTop
                                    spacing: 8

                                    Rectangle {
                                        radius: 12
                                        color: root.statusSurface(String(root.visibleTask.status_key || (draftBool("enabled", true) ? "scheduled" : "disabled")))
                                        implicitHeight: 30
                                        implicitWidth: detailStateLabel.implicitWidth + 18

                                        Text {
                                            id: detailStateLabel
                                            anchors.centerIn: parent
                                            text: root.showingExistingTask ? root.statusLabel(String(root.visibleTask.status_key || "draft")) : (draftBool("enabled", true) ? tr("已启用", "Enabled") : tr("已停用", "Disabled"))
                                            color: root.showingExistingTask ? root.statusColor(String(root.visibleTask.status_key || "draft")) : (draftBool("enabled", true) ? statusSuccess : textSecondary)
                                            font.pixelSize: typeLabel
                                            font.weight: weightBold
                                        }
                                    }

                                    PillActionButton {
                                        text: draftBool("delete_after_run", false) ? tr("执行后删除", "Delete after run") : tr("保留任务", "Keep task")
                                        fillColor: draftBool("delete_after_run", false) ? statusWarning : "transparent"
                                        hoverFillColor: draftBool("delete_after_run", false) ? Qt.darker(statusWarning, 1.05) : bgCardHover
                                        outlineColor: draftBool("delete_after_run", false) ? statusWarning : borderSubtle
                                        textColor: draftBool("delete_after_run", false) ? "#FFFFFFFF" : textSecondary
                                        outlined: !draftBool("delete_after_run", false)
                                        onClicked: root.setDraft("delete_after_run", !draftBool("delete_after_run", false))
                                    }
                                }
                            }

                            CalloutPanel {
                                id: statusPanel
                                objectName: "cronStatusPanel"
                                Layout.fillWidth: true
                                panelColor: root.statusSurface(String(root.visibleTask.status_key || (draftBool("enabled", true) ? "scheduled" : "disabled")))
                                panelBorderColor: fieldBorder
                                sideGlowVisible: root.showingExistingTask
                                sideGlowColor: isDark ? "#18FFFFFF" : "#14FFB33D"
                                sideGlowWidthFactor: 0.24
                                padding: 14

                                ColumnLayout {
                                    width: parent.width
                                    spacing: 10

                                    RowLayout {
                                        width: parent.width
                                        spacing: 10

                                        Rectangle {
                                            width: 34
                                            height: 34
                                            radius: 17
                                            color: isDark ? "#19130F" : "#FFF4E6"

                                            Image {
                                                anchors.centerIn: parent
                                                width: 18
                                                height: 18
                                                source: root.labIcon("watch-activity")
                                                sourceSize: Qt.size(width, height)
                                                fillMode: Image.PreserveAspectFit
                                                smooth: true
                                                mipmap: true
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2

                                            Text {
                                                text: tr("任务状态", "Task status")
                                                color: textPrimary
                                                font.pixelSize: typeBody + 1
                                                font.weight: weightBold
                                            }

                                            Text {
                                                Layout.fillWidth: true
                                                text: root.showingExistingTask ? root.statusLabel(String(root.visibleTask.status_key || "draft")) : tr("还没有选中任务", "No task selected yet")
                                                color: root.showingExistingTask ? root.statusColor(String(root.visibleTask.status_key || "draft")) : textSecondary
                                                font.pixelSize: typeBody
                                                wrapMode: Text.WordWrap
                                            }
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: root.showingExistingTask ? String(root.visibleTask.schedule_summary || "") : tr("从左边选中一个任务后，这里会显示状态和快捷操作。", "After you select a task, this area shows status and quick actions.")
                                        color: textSecondary
                                        font.pixelSize: typeBody
                                        wrapMode: Text.WordWrap
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        visible: root.showingExistingTask
                                        radius: 16
                                        color: isDark ? "#14100D" : "#FAF3EB"
                                        border.width: 1
                                        border.color: fieldBorder
                                        implicitHeight: metricsGrid.implicitHeight + 24

                                        GridLayout {
                                            id: metricsGrid
                                            anchors.fill: parent
                                            anchors.margins: 12
                                            columns: 2
                                            columnSpacing: 14
                                            rowSpacing: 10

                                            Repeater {
                                                model: [
                                                    { label: tr("下一次执行", "Next run"), icon: root.icon("clock-rotate-right"), value: summaryText(root.visibleTask.next_run_text, "未安排", "Not scheduled") },
                                                    { label: tr("最近结果", "Last result"), icon: root.icon("message-text"), value: summaryText(root.visibleTask.last_result_text, "暂无", "None yet") },
                                                    { label: tr("最近执行", "Last run"), icon: root.icon("activity"), value: summaryText(root.visibleTask.last_run_text, "从未执行", "Never run") },
                                                    { label: tr("任务对话", "Task chat"), icon: root.icon("chat-lines"), value: summaryText(root.visibleTask.session_key, "保存后生成", "Created after save") }
                                                ]

                                                delegate: Item {
                                                    required property var modelData
                                                    Layout.fillWidth: true
                                                    implicitHeight: metricValue.implicitHeight + 24

                                                    Column {
                                                        anchors.fill: parent
                                                        spacing: 4

                                                        Row {
                                                            spacing: 8

                                                            Image {
                                                                width: 16
                                                                height: 16
                                                                source: modelData.icon
                                                                sourceSize: Qt.size(width, height)
                                                                fillMode: Image.PreserveAspectFit
                                                                smooth: true
                                                                mipmap: true
                                                                opacity: 0.72
                                                            }

                                                            Text {
                                                                text: modelData.label
                                                                color: textTertiary
                                                                font.pixelSize: typeMeta
                                                                font.weight: weightBold
                                                            }
                                                        }

                                                        Text {
                                                            id: metricValue
                                                            width: parent.width
                                                            text: modelData.value
                                                            color: textPrimary
                                                            font.pixelSize: typeBody
                                                            wrapMode: Text.WordWrap
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        visible: root.showingExistingTask && String(root.visibleTask.last_error || "") !== ""
                                        radius: 16
                                        color: isDark ? "#2A1513" : "#FFF1EE"
                                        border.width: 1
                                        border.color: isDark ? "#6B2A22" : "#F0B2A8"
                                        implicitHeight: latestErrorText.implicitHeight + 28

                                        Column {
                                            anchors.fill: parent
                                            anchors.margins: 12
                                            spacing: 4

                                            Text {
                                                text: tr("最近错误", "Latest error")
                                                color: statusError
                                                font.pixelSize: typeMeta
                                                font.weight: weightBold
                                            }

                                            Text {
                                                id: latestErrorText
                                                width: parent.width
                                                text: String(root.visibleTask.last_error || "")
                                                color: textPrimary
                                                font.pixelSize: typeBody
                                                wrapMode: Text.WordWrap
                                            }
                                        }
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        visible: root.showingExistingTask
                                        id: statusActionRow

                                        AsyncActionButton {
                                            Layout.preferredWidth: 156
                                            text: tr("现在执行一次", "Run now")
                                            busy: hasCronService && cronService.busy
                                            buttonEnabled: root.showingExistingTask && hasCronService && !cronService.busy
                                            fillColor: cronAccent
                                            hoverFillColor: cronAccentHover
                                            iconSource: root.icon("play")
                                            onClicked: if (hasCronService) cronService.runSelectedNow()
                                        }

                                        PillActionButton {
                                            Layout.preferredWidth: 132
                                            iconSource: draftBool("enabled", true) ? root.icon("bubble-xmark") : root.icon("circle-spark")
                                            text: draftBool("enabled", true) ? tr("暂停任务", "Pause task") : tr("启用任务", "Enable task")
                                            fillColor: "transparent"
                                            hoverFillColor: draftBool("enabled", true) ? (isDark ? "#311816" : "#FFF0EC") : bgCardHover
                                            outlineColor: draftBool("enabled", true) ? statusError : borderSubtle
                                            hoverOutlineColor: draftBool("enabled", true) ? statusError : borderDefault
                                            textColor: draftBool("enabled", true) ? statusError : textSecondary
                                            outlined: true
                                            buttonEnabled: root.showingExistingTask && hasCronService && !cronService.busy
                                            onClicked: if (hasCronService) cronService.setSelectedEnabled(!draftBool("enabled", true))
                                        }

                                        PillActionButton {
                                            Layout.preferredWidth: 144
                                            text: tr("查看任务对话", "Open task chat")
                                            iconSource: root.icon("chat-lines")
                                            fillColor: "transparent"
                                            hoverFillColor: bgCardHover
                                            outlineColor: borderSubtle
                                            textColor: textSecondary
                                            outlined: true
                                            buttonEnabled: root.showingExistingTask
                                            onClicked: root.openSelectedSession()
                                        }

                                        Item { Layout.fillWidth: true }
                                    }
                                }
                            }

                            Item {
                                Layout.fillWidth: true
                                implicitHeight: basicsColumn.implicitHeight

                                ColumnLayout {
                                    id: basicsColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    spacing: 10

                                    Text {
                                        text: tr("任务名称", "Task name")
                                        color: textPrimary
                                        font.pixelSize: typeBody + 1
                                        font.weight: weightBold
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: 44
                                        radius: 16
                                        color: nameHit.containsMouse ? fieldHoverFill : fieldFill
                                        border.width: nameInput.activeFocus ? 1.5 : 1
                                        border.color: nameInput.activeFocus ? borderFocus : fieldBorder

                                        MouseArea {
                                            id: nameHit
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            acceptedButtons: Qt.NoButton
                                        }

                                        TextField {
                                            id: nameInput
                                            property bool baoClickAwayEditor: true
                                            anchors.fill: parent
                                            anchors.leftMargin: 14
                                            anchors.rightMargin: 14
                                            hoverEnabled: true
                                            text: draftString("name", "")
                                            color: textPrimary
                                            placeholderText: tr("任务名称", "Task name")
                                            placeholderTextColor: textPlaceholder
                                            background: null
                                            leftPadding: 0
                                            rightPadding: 0
                                            topPadding: 0
                                            bottomPadding: 0
                                            verticalAlignment: TextInput.AlignVCenter
                                            selectionColor: textSelectionBg
                                            selectedTextColor: textSelectionFg
                                            onTextEdited: root.setDraft("name", text)
                                        }
                                    }
                                }
                            }

                            Item {
                                Layout.fillWidth: true
                                implicitHeight: scheduleColumn.implicitHeight

                                ColumnLayout {
                                    id: scheduleColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    spacing: 10

                                    Text {
                                        text: tr("执行时间", "Schedule")
                                        color: textPrimary
                                        font.pixelSize: typeBody + 1
                                        font.weight: weightBold
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        id: scheduleModeRow

                                        PillActionButton {
                                            Layout.preferredWidth: 96
                                            text: tr("重复", "Repeat")
                                            horizontalPadding: 12
                                            fillColor: draftString("schedule_kind", "every") === "every" ? cronAccent : "transparent"
                                            hoverFillColor: draftString("schedule_kind", "every") === "every" ? cronAccentHover : bgCardHover
                                            outlineColor: draftString("schedule_kind", "every") === "every" ? cronAccent : borderSubtle
                                            textColor: draftString("schedule_kind", "every") === "every" ? "#FFFFFFFF" : textSecondary
                                            outlined: draftString("schedule_kind", "every") !== "every"
                                            onClicked: root.setDraft("schedule_kind", "every")
                                        }

                                        PillActionButton {
                                            Layout.preferredWidth: 96
                                            text: tr("单次", "Once")
                                            horizontalPadding: 12
                                            fillColor: draftString("schedule_kind", "every") === "at" ? cronAccent : "transparent"
                                            hoverFillColor: draftString("schedule_kind", "every") === "at" ? cronAccentHover : bgCardHover
                                            outlineColor: draftString("schedule_kind", "every") === "at" ? cronAccent : borderSubtle
                                            textColor: draftString("schedule_kind", "every") === "at" ? "#FFFFFFFF" : textSecondary
                                            outlined: draftString("schedule_kind", "every") !== "at"
                                            onClicked: root.setDraft("schedule_kind", "at")
                                        }

                                        PillActionButton {
                                            Layout.preferredWidth: 96
                                            text: tr("高级", "Advanced")
                                            horizontalPadding: 12
                                            fillColor: draftString("schedule_kind", "every") === "cron" ? cronAccent : "transparent"
                                            hoverFillColor: draftString("schedule_kind", "every") === "cron" ? cronAccentHover : bgCardHover
                                            outlineColor: draftString("schedule_kind", "every") === "cron" ? cronAccent : borderSubtle
                                            textColor: draftString("schedule_kind", "every") === "cron" ? "#FFFFFFFF" : textSecondary
                                            outlined: draftString("schedule_kind", "every") !== "cron"
                                            onClicked: root.setDraft("schedule_kind", "cron")
                                        }

                                        Item { Layout.fillWidth: true }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        visible: root.scheduleModeHint().length > 0
                                        text: root.scheduleModeHint()
                                        color: textSecondary
                                        font.pixelSize: typeMeta
                                        wrapMode: Text.WordWrap
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: 44
                                        visible: draftString("schedule_kind", "every") === "every"
                                        radius: 16
                                        color: everyHit.containsMouse ? fieldHoverFill : fieldFill
                                        border.width: everyInput.activeFocus ? 1.5 : 1
                                        border.color: everyInput.activeFocus ? borderFocus : fieldBorder

                                        MouseArea {
                                            id: everyHit
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            acceptedButtons: Qt.NoButton
                                        }

                                        TextField {
                                            id: everyInput
                                            property bool baoClickAwayEditor: true
                                            anchors.fill: parent
                                            anchors.leftMargin: 14
                                            anchors.rightMargin: 14
                                            hoverEnabled: true
                                            text: draftString("every_minutes", "60")
                                            color: textPrimary
                                            placeholderText: tr("每隔多少分钟执行一次", "Repeat interval in minutes")
                                            placeholderTextColor: textPlaceholder
                                            background: null
                                            leftPadding: 0
                                            rightPadding: 0
                                            topPadding: 0
                                            bottomPadding: 0
                                            verticalAlignment: TextInput.AlignVCenter
                                            inputMethodHints: Qt.ImhDigitsOnly
                                            selectionColor: textSelectionBg
                                            selectedTextColor: textSelectionFg
                                            onTextEdited: root.setDraft("every_minutes", text)
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: 44
                                        visible: draftString("schedule_kind", "every") === "at"
                                        radius: 16
                                        color: atHit.containsMouse ? fieldHoverFill : fieldFill
                                        border.width: atInput.activeFocus ? 1.5 : 1
                                        border.color: atInput.activeFocus ? borderFocus : fieldBorder

                                        MouseArea {
                                            id: atHit
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            acceptedButtons: Qt.NoButton
                                        }

                                        TextField {
                                            id: atInput
                                            property bool baoClickAwayEditor: true
                                            anchors.fill: parent
                                            anchors.leftMargin: 14
                                            anchors.rightMargin: 14
                                            hoverEnabled: true
                                            text: draftString("at_input", "")
                                            color: textPrimary
                                            placeholderText: tr("时间，例如 2026-03-12T09:00", "Time, for example 2026-03-12T09:00")
                                            placeholderTextColor: textPlaceholder
                                            background: null
                                            leftPadding: 0
                                            rightPadding: 0
                                            topPadding: 0
                                            bottomPadding: 0
                                            verticalAlignment: TextInput.AlignVCenter
                                            selectionColor: textSelectionBg
                                            selectedTextColor: textSelectionFg
                                            onTextEdited: root.setDraft("at_input", text)
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: 44
                                        visible: draftString("schedule_kind", "every") === "cron"
                                        radius: 16
                                        color: cronExprHit.containsMouse ? fieldHoverFill : fieldFill
                                        border.width: cronExprInput.activeFocus ? 1.5 : 1
                                        border.color: cronExprInput.activeFocus ? borderFocus : fieldBorder

                                        MouseArea {
                                            id: cronExprHit
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            acceptedButtons: Qt.NoButton
                                        }

                                        TextField {
                                            id: cronExprInput
                                            property bool baoClickAwayEditor: true
                                            anchors.fill: parent
                                            anchors.leftMargin: 14
                                            anchors.rightMargin: 14
                                            hoverEnabled: true
                                            text: draftString("cron_expr", "")
                                            color: textPrimary
                                            placeholderText: tr("Cron 表达式，例如 0 9 * * 1-5", "Cron expression, for example 0 9 * * 1-5")
                                            placeholderTextColor: textPlaceholder
                                            background: null
                                            leftPadding: 0
                                            rightPadding: 0
                                            topPadding: 0
                                            bottomPadding: 0
                                            verticalAlignment: TextInput.AlignVCenter
                                            selectionColor: textSelectionBg
                                            selectedTextColor: textSelectionFg
                                            onTextEdited: root.setDraft("cron_expr", text)
                                        }
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: 44
                                        visible: draftString("schedule_kind", "every") === "cron"
                                        radius: 16
                                        color: timezoneHit.containsMouse ? fieldHoverFill : fieldFill
                                        border.width: timezoneInput.activeFocus ? 1.5 : 1
                                        border.color: timezoneInput.activeFocus ? borderFocus : fieldBorder

                                        MouseArea {
                                            id: timezoneHit
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            acceptedButtons: Qt.NoButton
                                        }

                                        TextField {
                                            id: timezoneInput
                                            property bool baoClickAwayEditor: true
                                            anchors.fill: parent
                                            anchors.leftMargin: 14
                                            anchors.rightMargin: 14
                                            hoverEnabled: true
                                            text: draftString("timezone", "")
                                            color: textPrimary
                                            placeholderText: tr("时区，可留空，例如 Australia/Sydney", "Timezone, optional, for example Australia/Sydney")
                                            placeholderTextColor: textPlaceholder
                                            background: null
                                            leftPadding: 0
                                            rightPadding: 0
                                            topPadding: 0
                                            bottomPadding: 0
                                            verticalAlignment: TextInput.AlignVCenter
                                            selectionColor: textSelectionBg
                                            selectedTextColor: textSelectionFg
                                            onTextEdited: root.setDraft("timezone", text)
                                        }
                                    }
                                }
                            }

                            Item {
                                Layout.fillWidth: true
                                implicitHeight: deliveryColumn.implicitHeight

                                ColumnLayout {
                                    id: deliveryColumn
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    spacing: 10

                                    Text {
                                        text: tr("消息与投递", "Message and delivery")
                                        color: textPrimary
                                        font.pixelSize: typeBody + 1
                                        font.weight: weightBold
                                    }

                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: 154
                                        radius: 18
                                        color: messageInput.activeFocus ? fieldHoverFill : fieldFill
                                        border.width: messageInput.activeFocus ? 1.5 : 1
                                        border.color: messageInput.activeFocus ? borderFocus : fieldBorder

                                        TextArea {
                                            id: messageInput
                                            property bool baoClickAwayEditor: true
                                            anchors.fill: parent
                                            anchors.margins: 12
                                            text: draftString("message", "")
                                            color: textPrimary
                                            placeholderText: tr("任务执行时要发送给 Bao 的消息或指令", "The message or instruction Bao should receive when the task runs")
                                            placeholderTextColor: textPlaceholder
                                            wrapMode: TextArea.Wrap
                                            selectByMouse: true
                                            background: null
                                            selectionColor: textSelectionBg
                                            selectedTextColor: textSelectionFg
                                            onTextChanged: if (activeFocus) root.setDraft("message", text)
                                        }
                                    }

                                    Flow {
                                        width: parent.width
                                        spacing: 8

                                        PillActionButton {
                                            text: draftBool("deliver", false) ? tr("发送结果到渠道", "Send result to channel") : tr("只在 Bao 内运行", "Run inside Bao only")
                                            fillColor: draftBool("deliver", false) ? cronAccent : "transparent"
                                            hoverFillColor: draftBool("deliver", false) ? cronAccentHover : bgCardHover
                                            outlineColor: draftBool("deliver", false) ? cronAccent : borderSubtle
                                            textColor: draftBool("deliver", false) ? "#FFFFFFFF" : textSecondary
                                            outlined: !draftBool("deliver", false)
                                            onClicked: root.setDraft("deliver", !draftBool("deliver", false))
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        visible: root.deliveryHint().length > 0
                                        text: tr("任务完成后会自动发到下面的渠道和目标。", "When finished, Bao sends the result to the channel and target below.")
                                        color: textSecondary
                                        font.pixelSize: typeMeta
                                        wrapMode: Text.WordWrap
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: 44
                                            radius: 16
                                            color: channelHit.containsMouse ? fieldHoverFill : fieldFill
                                            border.width: channelInput.activeFocus ? 1.5 : 1
                                            border.color: channelInput.activeFocus ? borderFocus : fieldBorder
                                            opacity: draftBool("deliver", false) ? 1.0 : 0.6

                                            MouseArea {
                                                id: channelHit
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                acceptedButtons: Qt.NoButton
                                            }

                                            TextField {
                                                id: channelInput
                                                property bool baoClickAwayEditor: true
                                                anchors.fill: parent
                                                anchors.leftMargin: 14
                                                anchors.rightMargin: 14
                                                enabled: draftBool("deliver", false)
                                                hoverEnabled: true
                                                text: draftString("channel", "")
                                                color: textPrimary
                                                placeholderText: tr("渠道，例如 telegram", "Channel, for example telegram")
                                                placeholderTextColor: textPlaceholder
                                                background: null
                                                leftPadding: 0
                                                rightPadding: 0
                                                topPadding: 0
                                                bottomPadding: 0
                                                verticalAlignment: TextInput.AlignVCenter
                                                selectionColor: textSelectionBg
                                                selectedTextColor: textSelectionFg
                                                onTextEdited: root.setDraft("channel", text)
                                            }
                                        }

                                        Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: 44
                                            radius: 16
                                            color: targetHit.containsMouse ? fieldHoverFill : fieldFill
                                            border.width: targetInput.activeFocus ? 1.5 : 1
                                            border.color: targetInput.activeFocus ? borderFocus : fieldBorder
                                            opacity: draftBool("deliver", false) ? 1.0 : 0.6

                                            MouseArea {
                                                id: targetHit
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                acceptedButtons: Qt.NoButton
                                            }

                                            TextField {
                                                id: targetInput
                                                property bool baoClickAwayEditor: true
                                                anchors.fill: parent
                                                anchors.leftMargin: 14
                                                anchors.rightMargin: 14
                                                enabled: draftBool("deliver", false)
                                                hoverEnabled: true
                                                text: draftString("target", "")
                                                color: textPrimary
                                                placeholderText: tr("目标，例如 chat id / 电话", "Target, for example chat id / phone")
                                                placeholderTextColor: textPlaceholder
                                                background: null
                                                leftPadding: 0
                                                rightPadding: 0
                                                topPadding: 0
                                                bottomPadding: 0
                                                verticalAlignment: TextInput.AlignVCenter
                                                selectionColor: textSelectionBg
                                                selectedTextColor: textSelectionFg
                                                onTextEdited: root.setDraft("target", text)
                                            }
                                        }
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                id: footerActionRow

                                AsyncActionButton {
                                    Layout.preferredWidth: 150
                                    text: editingNewTask ? tr("创建任务", "Create task") : tr("保存任务", "Save task")
                                    busy: hasCronService && cronService.busy
                                    buttonEnabled: hasCronService && !cronService.busy
                                    fillColor: cronAccent
                                    hoverFillColor: cronAccentHover
                                    iconSource: root.icon("circle-spark")
                                    onClicked: if (hasCronService) cronService.saveDraft()
                                }

                                PillActionButton {
                                    Layout.preferredWidth: 132
                                    text: tr("另存副本", "Save as copy")
                                    iconSource: root.labIcon("copy-file-path")
                                    fillColor: "transparent"
                                    hoverFillColor: bgCardHover
                                    outlineColor: borderSubtle
                                    textColor: textSecondary
                                    outlined: true
                                    buttonEnabled: root.showingExistingTask
                                    onClicked: if (hasCronService) cronService.duplicateSelected()
                                }

                                PillActionButton {
                                    Layout.preferredWidth: 132
                                    text: tr("删除任务", "Delete task")
                                    iconSource: root.labIcon("tab-x")
                                    fillColor: "transparent"
                                    hoverFillColor: isDark ? "#311816" : "#FFF0EC"
                                    outlineColor: statusError
                                    hoverOutlineColor: statusError
                                    textColor: statusError
                                    outlined: true
                                    buttonEnabled: root.showingExistingTask
                                    onClicked: deleteModal.open()
                                }

                                Item { Layout.fillWidth: true }
                            }
                        }
                    }
                }

            }
        }
    }

        }

    AppModal {
        id: deleteModal
        darkMode: isDark
        title: tr("删除这个任务？", "Delete this task?")
        closeText: tr("取消", "Cancel")
        maxModalWidth: 460
        maxModalHeight: 260

        ColumnLayout {
            width: parent.width
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: tr(
                          "这会删除调度定义，但不会删除已经产生的 cron 会话历史。",
                          "This deletes the scheduled definition, but keeps any existing cron session history."
                          )
                color: textSecondary
                font.pixelSize: typeBody
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true

                Item { Layout.fillWidth: true }

                PillActionButton {
                    text: tr("确认删除", "Delete task")
                    fillColor: statusError
                    hoverFillColor: Qt.darker(statusError, 1.06)
                    onClicked: {
                        deleteModal.close()
                        if (hasCronService)
                            cronService.deleteSelected()
                    }
                }
            }
        }
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
