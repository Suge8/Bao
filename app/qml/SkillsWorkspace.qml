pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    objectName: "skillsWorkspaceRoot"

    property bool active: false
    property var skillsService: null
    property string currentMode: "installed"
    property string draftSkillId: ""
    property bool draftDirty: false
    property bool syncingDraft: false
    property var editorRef: null
    property real revealOpacity: 1.0
    property real revealScale: 1.0
    property real revealShift: 0.0

    readonly property bool hasSkillsService: skillsService !== null
    readonly property bool hasSkillsSignals: hasSkillsService
        && typeof skillsService.changed !== "undefined"
        && typeof skillsService.operationFinished !== "undefined"
    readonly property var overview: hasSkillsService ? (skillsService.overview || {}) : ({})
    readonly property var installedSkills: hasSkillsService ? (skillsService.skills || []) : []
    readonly property var selectedSkill: hasSkillsService ? (skillsService.selectedSkill || {}) : ({})
    readonly property string selectedSkillId: hasSkillsService ? String(skillsService.selectedSkillId || "") : ""
    readonly property string selectedContent: hasSkillsService ? String(skillsService.selectedContent || "") : ""
    readonly property string skillQueryValue: hasSkillsService ? String(skillsService.query || "") : ""
    readonly property string sourceFilterValue: hasSkillsService ? String(skillsService.sourceFilter || "all") : "all"
    readonly property bool serviceBusy: hasSkillsService
        && typeof skillsService.busy !== "undefined"
        && skillsService.busy
    readonly property var discoverResults: hasSkillsService ? (skillsService.discoverResults || []) : []
    readonly property var selectedDiscoverItem: hasSkillsService ? (skillsService.selectedDiscoverItem || {}) : ({})
    readonly property string selectedDiscoverId: hasSkillsService ? String(skillsService.selectedDiscoverId || "") : ""
    readonly property string discoverQueryValue: hasSkillsService ? String(skillsService.discoverQuery || "") : ""
    readonly property string discoverReferenceValue: hasSkillsService ? String(skillsService.discoverReference || "") : ""
    readonly property var discoverTask: hasSkillsService
        ? (skillsService.discoverTask || {})
        : ({ state: "idle", kind: "", message: "", reference: "" })
    readonly property var installedFilterOptions: [
        { value: "all", zh: "全部", en: "All" },
        { value: "ready", zh: "现在可用", en: "Ready now" },
        { value: "needs_setup", zh: "需设置", en: "Needs setup" },
        { value: "instruction_only", zh: "仅指导", en: "Instruction only" },
        { value: "workspace", zh: "工作区", en: "Workspace" },
        { value: "shadowed", zh: "已覆盖", en: "Overridden" }
    ]
    readonly property string effectiveUiLanguage: {
        if (typeof uiLanguage === "string" && uiLanguage !== "auto")
            return uiLanguage
        if (typeof autoLanguage === "string")
            return autoLanguage
        return "en"
    }
    readonly property bool isZhLang: effectiveUiLanguage === "zh"

    function tr(zh, en) {
        return isZhLang ? zh : en
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

    function localizedSkillName(skill) {
        return localizedText(skill ? skill.displayName : null, skill && skill.name ? skill.name : "")
    }

    function localizedSkillDescription(skill) {
        return localizedText(
            skill ? skill.displaySummary : null,
            skill && skill.summary ? skill.summary : ""
        )
    }

    function skillIconSource(skill) {
        if (!skill)
            return labIcon("toolbox")
        return String(skill.iconSource || labIcon("toolbox"))
    }

    function sourceLabel(skill) {
        return String(skill.source || "") === "workspace" ? tr("工作区", "Workspace") : tr("内建", "Built-in")
    }

    function primaryStatusLabel(skill) {
        if (!skill)
            return ""
        if (skill.shadowed)
            return tr("已覆盖", "Overridden")
        var statusLabel = localizedText(skill.statusLabel, "")
        if (statusLabel)
            return statusLabel
        if (skill.always)
            return tr("常驻", "Always on")
        return ""
    }

    function primaryStatusColor(skill) {
        if (!skill)
            return textSecondary
        if (skill.shadowed)
            return "#F59E0B"
        if (String(skill.status || "") === "needs_setup")
            return statusError
        if (String(skill.status || "") === "instruction_only")
            return "#8B5CF6"
        if (skill.always)
            return accent
        return "#22C55E"
    }

    function selectedSkillValue(key, fallbackValue) {
        var value = root.selectedSkill[key]
        return (typeof value === "undefined" || value === null) ? fallbackValue : value
    }

    function selectedSkillFlag(key) {
        return !!root.selectedSkillValue(key, false)
    }

    function selectedDiscoverValue(key, fallbackValue) {
        var value = root.selectedDiscoverItem[key]
        return (typeof value === "undefined" || value === null) ? fallbackValue : value
    }

    function discoverTaskTone(state) {
        switch (String(state || "")) {
        case "working":
            return accent
        case "completed":
            return "#22C55E"
        case "failed":
            return statusError
        case "cancelled":
            return "#F59E0B"
        default:
            return textSecondary
        }
    }

    function discoverTaskLabel(state) {
        switch (String(state || "")) {
        case "working":
            return tr("进行中", "Working")
        case "completed":
            return tr("已完成", "Completed")
        case "failed":
            return tr("失败", "Failed")
        case "cancelled":
            return tr("已取消", "Cancelled")
        default:
            return tr("空闲", "Idle")
        }
    }

    function toastMessage(code, ok) {
        if (!ok)
            return code
        if (code === "created")
            return tr("技能已创建", "Skill created")
        if (code === "saved")
            return tr("技能已保存", "Skill saved")
        if (code === "deleted")
            return tr("技能已删除", "Skill deleted")
        if (code === "installed")
            return tr("技能已导入到工作区", "Skill imported into workspace")
        if (code === "search_ok")
            return tr("搜索完成", "Search complete")
        return code
    }

    function playReveal() {
        revealOpacity = motionPageRevealStartOpacity
        revealScale = motionPageRevealStartScale
        revealShift = motionPageShiftSubtle
        revealAnimation.restart()
    }

    function headerTitle() {
        return workspaceString("workspace_skills_title", "技能", "Skills")
    }

    function currentHeaderCaption() {
        return workspaceString(
            "workspace_skills_caption",
            "管理 AI 拓展技能",
            "Manage AI extension skills"
        )
    }

    function syncDraft(force) {
        if (!hasSkillsService || !editorRef)
            return
        var selectedId = root.selectedSkillId
        if (!force && draftDirty && draftSkillId === selectedId && editorRef.text !== root.selectedContent)
            return
        syncingDraft = true
        draftSkillId = selectedId
        editorRef.text = root.selectedContent
        draftDirty = false
        syncingDraft = false
    }

    onActiveChanged: if (active) playReveal()
    onSelectedSkillIdChanged: syncDraft(true)
    onSelectedContentChanged: syncDraft(false)
    Component.onCompleted: syncDraft(true)

    Connections {
        target: root.hasSkillsSignals ? skillsService : null

        function onOperationFinished(message, ok) {
            globalToast.show(root.toastMessage(message, ok), ok)
            if (ok && (message === "deleted" || message === "installed"))
                root.syncDraft(true)
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
                anchors.margins: 22
                spacing: 18

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
                        spacing: 8

                        Item {
                            Layout.fillWidth: true
                            implicitHeight: 52

                            Row {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 10

                                WorkspaceHeroIcon {
                                    iconSource: root.icon("book-stack")
                                }

                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2

                                    Text {
                                        text: root.headerTitle()
                                        color: textPrimary
                                        font.pixelSize: typeTitle - 1
                                        font.weight: weightBold
                                    }

                                    Text {
                                        text: root.currentHeaderCaption()
                                        color: textSecondary
                                        font.pixelSize: typeMeta
                                        maximumLineCount: 1
                                        elide: Text.ElideRight
                                    }
                                }
                            }

                            Item {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.verticalCenter: parent.verticalCenter
                                width: modeTabBar.implicitWidth
                                height: modeTabBar.implicitHeight

                                SegmentedTabs {
                                    id: modeTabBar
                                    anchors.centerIn: parent
                                    currentValue: root.currentMode
                                    items: [
                                        {
                                            value: "installed",
                                            label: root.tr("已安装", "Installed"),
                                            icon: root.icon("book-stack")
                                        },
                                        {
                                            value: "discover",
                                            label: root.tr("发现", "Discover"),
                                            icon: root.icon("page-search")
                                        }
                                    ]
                                    onSelected: function(value) { root.currentMode = value }
                                }
                            }

                            Item {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                width: rightHeaderActions.implicitWidth
                                height: rightHeaderActions.implicitHeight

                                RowLayout {
                                    id: rightHeaderActions
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 8

                                    PillActionButton {
                                        text: tr("目录地址", "Folder path")
                                        iconSource: root.labIcon("copy-file-path")
                                        minHeight: 34
                                        horizontalPadding: 18
                                        outlined: true
                                        fillColor: "transparent"
                                        hoverFillColor: bgCardHover
                                        outlineColor: borderSubtle
                                        hoverOutlineColor: borderDefault
                                        textColor: textPrimary
                                        onClicked: if (root.hasSkillsService) skillsService.openWorkspaceFolder()
                                    }

                                    PillActionButton {
                                        visible: root.currentMode === "installed"
                                        text: tr("新建技能", "New skill")
                                        iconSource: root.icon("circle-spark")
                                        minHeight: 34
                                        horizontalPadding: 18
                                        fillColor: accent
                                        hoverFillColor: accentHover
                                        onClicked: createSkillModal.open()
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 28
                    color: isDark ? "#17120F" : "#FFFDFC"
                    border.width: 1
                    border.color: isDark ? "#18FFFFFF" : "#12000000"

                    Loader {
                        anchors.fill: parent
                        anchors.margins: 12
                        sourceComponent: root.currentMode === "installed" ? installedPane : discoverPane
                    }
                }
            }
        }
    }

    Component {
        id: installedPane

        SplitView {
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
                            id: searchInput
                            property bool baoClickAwayEditor: true
                            anchors.fill: parent
                            hoverEnabled: true
                            leftPadding: 14
                            rightPadding: 14
                            background: null
                            color: textPrimary
                            placeholderText: root.tr("搜索技能…", "Search skills…")
                            placeholderTextColor: textPlaceholder
                            selectionColor: textSelectionBg
                            selectedTextColor: textSelectionFg
                            font.pixelSize: typeBody
                            text: root.skillQueryValue
                            onTextEdited: if (root.hasSkillsService) skillsService.setQuery(text)
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Repeater {
                            model: root.installedFilterOptions

                            delegate: PillActionButton {
                                required property var modelData

                                Layout.fillWidth: true
                                text: root.isZhLang ? modelData.zh : modelData.en
                                minHeight: 34
                                horizontalPadding: 14
                                outlined: true
                                fillColor: root.sourceFilterValue === modelData.value ? accentMuted : "transparent"
                                hoverFillColor: root.sourceFilterValue === modelData.value ? accentMuted : bgCardHover
                                outlineColor: root.sourceFilterValue === modelData.value ? accent : borderSubtle
                                hoverOutlineColor: root.sourceFilterValue === modelData.value ? accentHover : borderDefault
                                textColor: textPrimary
                                onClicked: if (root.hasSkillsService) skillsService.setSourceFilter(modelData.value)
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

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            Layout.fillWidth: true
                            text: root.tr("技能列表", "Skills")
                            color: textPrimary
                            font.pixelSize: typeLabel
                            font.weight: weightBold
                        }

                        Rectangle {
                            radius: 11
                            color: isDark ? "#20FFFFFF" : "#14000000"
                            implicitHeight: 22
                            implicitWidth: listCountLabel.implicitWidth + 16

                            Text {
                                id: listCountLabel
                                anchors.centerIn: parent
                                text: tr("显示 ", "Showing ") + String(root.installedSkills.length) + tr(" · 就绪 ", " · Ready ") + String(root.overview.readyCount || 0) + tr(" · 待设置 ", " · Setup ") + String(root.overview.needsSetupCount || 0)
                                color: textSecondary
                                font.pixelSize: typeMeta
                                font.weight: weightBold
                            }
                        }
                    }

                    ListView {
                        id: skillList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 10
                        bottomMargin: 12
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollIndicator.vertical: ScrollIndicator {
                            visible: false
                            width: 4
                            contentItem: Rectangle {
                                implicitWidth: 2
                                radius: 1
                                color: isDark ? "#28FFFFFF" : "#22000000"
                            }
                        }
                        model: root.installedSkills

                        delegate: Item {
                            id: skillDelegateRoot
                            required property var modelData

                            width: skillList.width
                            implicitHeight: skillCard.implicitHeight + (sectionHeader.visible ? sectionHeader.implicitHeight + 8 : 0)
                            property bool selected: root.selectedSkillId === modelData.id

                            Column {
                                anchors.fill: parent
                                spacing: 8

                                Item {
                                    id: sectionHeader
                                    width: parent.width
                                    implicitHeight: sectionHeaderText.implicitHeight
                                    visible: !!skillDelegateRoot.modelData.showSectionHeader

                                    Text {
                                        id: sectionHeaderText
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        text: root.localizedText(skillDelegateRoot.modelData.sectionTitle, "")
                                        color: textSecondary
                                        font.pixelSize: typeMeta
                                        font.weight: weightBold
                                    }
                                }

                                Rectangle {
                                    id: skillCard
                                    width: parent.width
                                    implicitHeight: 120
                                    radius: 22
                                    color: skillArea.containsMouse
                                           ? (skillDelegateRoot.selected ? (isDark ? "#241914" : "#FFF1E2") : bgCardHover)
                                           : (skillDelegateRoot.selected ? (isDark ? "#201612" : "#FFF7F0") : (isDark ? "#17120F" : "#FFFFFF"))
                                    border.width: skillDelegateRoot.selected ? 1.5 : 1
                                    border.color: skillDelegateRoot.selected ? accent : (isDark ? "#14FFFFFF" : "#10000000")

                                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                    ColumnLayout {
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
                                                color: skillDelegateRoot.selected ? (isDark ? "#302015" : "#F1D8BE") : (isDark ? "#211915" : "#F2E6D9")
                                                border.width: skillDelegateRoot.selected ? 1 : 0
                                                border.color: skillDelegateRoot.selected ? accent : "transparent"

                                                AppIcon {
                                                    anchors.centerIn: parent
                                                    width: 18
                                                    height: 18
                                                    source: root.skillIconSource(skillDelegateRoot.modelData)
                                                    sourceSize: Qt.size(width, height)
                                                }
                                            }

                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: root.localizedSkillName(skillDelegateRoot.modelData)
                                                    color: textPrimary
                                                    font.pixelSize: typeBody
                                                    font.weight: weightBold
                                                    elide: Text.ElideRight
                                                }

                                                Text {
                                                    Layout.fillWidth: true
                                                    text: root.localizedSkillDescription(skillDelegateRoot.modelData)
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
                                                outlineColor: skillDelegateRoot.selected ? accent : borderSubtle
                                                glyphColor: skillDelegateRoot.selected ? accent : textSecondary
                                                onClicked: if (root.hasSkillsService) skillsService.selectSkill(skillDelegateRoot.modelData.id)
                                            }
                                        }

                                        Row {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            clip: true

                                            Repeater {
                                                model: [
                                                    { visible: true, text: root.sourceLabel(skillDelegateRoot.modelData), tone: skillDelegateRoot.modelData.source === "workspace" ? "#22C55E" : "#60A5FA" },
                                                    { visible: !!root.primaryStatusLabel(skillDelegateRoot.modelData), text: root.primaryStatusLabel(skillDelegateRoot.modelData), tone: root.primaryStatusColor(skillDelegateRoot.modelData) }
                                                ]

                                                delegate: Rectangle {
                                                    required property var modelData

                                                    visible: modelData.visible
                                                    radius: 11
                                                    height: 22
                                                    color: Qt.rgba(Qt.color(modelData.tone).r, Qt.color(modelData.tone).g, Qt.color(modelData.tone).b, isDark ? 0.18 : 0.10)
                                                    border.width: 1
                                                    border.color: Qt.rgba(Qt.color(modelData.tone).r, Qt.color(modelData.tone).g, Qt.color(modelData.tone).b, isDark ? 0.34 : 0.24)
                                                    width: badgeText.implicitWidth + 16

                                                    Text {
                                                        id: badgeText
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
                                        id: skillArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        acceptedButtons: Qt.LeftButton
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: if (root.hasSkillsService) skillsService.selectSkill(skillDelegateRoot.modelData.id)
                                    }
                                }
                            }
                        }

                        footer: Item {
                            width: skillList.width
                            height: root.installedSkills.length === 0 ? 180 : 0

                            Column {
                                anchors.centerIn: parent
                                width: Math.min(parent.width - 40, 280)
                                spacing: 10
                                visible: parent.height > 0

                                Text {
                                    width: parent.width
                                    text: root.tr("没有匹配的技能", "No matching skills")
                                    color: textPrimary
                                    font.pixelSize: typeBody
                                    font.weight: weightBold
                                    horizontalAlignment: Text.AlignHCenter
                                }

                                Text {
                                    width: parent.width
                                    text: root.tr("试试清空搜索，或切换筛选范围。", "Try clearing the search, or switch the filter scope.")
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

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: detailSummaryColumn.implicitHeight + 16
                        radius: 16
                        color: isDark ? "#181310" : "#FFF9F3"
                        border.width: 1
                        border.color: isDark ? "#12FFFFFF" : "#10000000"

                        Column {
                            id: detailSummaryColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 10
                            spacing: 8

                            Text {
                                width: parent.width
                                text: root.localizedSkillName(root.selectedSkill) || root.tr("选择一个技能", "Choose a skill")
                                color: textPrimary
                                font.pixelSize: typeLabel
                                font.weight: weightBold
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                text: root.selectedSkillId
                                      ? root.localizedText(root.selectedSkill.displayDetail, root.localizedSkillDescription(root.selectedSkill))
                                      : root.tr("从中栏选择一个技能后，这里会显示说明、状态和可编辑内容。", "Choose a skill from the list to inspect its summary, status, and editable content.")
                                color: textSecondary
                                font.pixelSize: typeCaption
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                wrapMode: Text.WordWrap
                            }

                            Flow {
                                width: parent.width
                                spacing: 8

                                Repeater {
                                    model: [
                                        { visible: root.selectedSkillFlag("name"), text: root.sourceLabel(root.selectedSkill), tone: root.selectedSkillValue("source", "") === "workspace" ? "#22C55E" : "#60A5FA" },
                                        { visible: !!root.primaryStatusLabel(root.selectedSkill), text: root.primaryStatusLabel(root.selectedSkill), tone: root.primaryStatusColor(root.selectedSkill) }
                                    ]

                                    delegate: Rectangle {
                                        required property var modelData

                                        visible: modelData.visible
                                        radius: 10
                                        height: 20
                                        color: isDark ? "#1D1713" : "#FFFFFF"
                                        border.width: 1
                                        border.color: isDark ? "#16FFFFFF" : "#10000000"
                                        width: detailBadgeText.implicitWidth + 14

                                        Text {
                                            id: detailBadgeText
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
                                visible: root.selectedSkillFlag("statusDetailDisplay")
                                text: root.localizedText(root.selectedSkillValue("statusDetailDisplay", ""), "")
                                color: textSecondary
                                font.pixelSize: typeCaption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                visible: root.selectedSkillFlag("missingRequirements")
                                text: root.tr("缺失依赖：", "Missing requirements: ") + String(root.selectedSkillValue("missingRequirements", ""))
                                color: statusError
                                font.pixelSize: typeCaption
                                font.weight: weightBold
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                visible: root.selectedSkillFlag("path")
                                text: String(root.selectedSkillValue("path", ""))
                                color: textSecondary
                                font.pixelSize: typeCaption
                                wrapMode: Text.WrapAnywhere
                            }

                            Flow {
                                width: parent.width
                                spacing: 8
                                visible: (root.selectedSkillValue("linkedCapabilities", []) || []).length > 0

                                Repeater {
                                    model: root.selectedSkillValue("linkedCapabilities", [])

                                    delegate: Rectangle {
                                        required property var modelData

                                        radius: 11
                                        height: 24
                                        color: isDark ? "#1D1713" : "#FFFFFF"
                                        border.width: 1
                                        border.color: isDark ? "#16FFFFFF" : "#10000000"
                                        width: capabilityText.implicitWidth + 22

                                        Text {
                                            id: capabilityText
                                            anchors.centerIn: parent
                                            text: root.localizedText(modelData.displayName, "")
                                            color: textPrimary
                                            font.pixelSize: typeCaption
                                            font.weight: weightBold
                                        }
                                    }
                                }
                            }

                            Column {
                                width: parent.width
                                spacing: 4
                                visible: (root.selectedSkillValue("examplePrompts", []) || []).length > 0

                                Text {
                                    width: parent.width
                                    text: root.tr("示例提示词", "Example prompts")
                                    color: textPrimary
                                    font.pixelSize: typeMeta
                                    font.weight: weightBold
                                }

                                Repeater {
                                    model: root.selectedSkillValue("examplePrompts", [])

                                    delegate: Text {
                                        required property string modelData

                                        width: detailSummaryColumn.width
                                        text: "• " + modelData
                                        color: textSecondary
                                        font.pixelSize: typeCaption
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 20
                        color: isDark ? "#100C0A" : "#F6EFE6"
                        border.width: 1
                        border.color: isDark ? "#12FFFFFF" : "#10000000"

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true

                                Text {
                                    Layout.fillWidth: true
                                    text: root.selectedSkillValue("source", "") === "workspace" ? root.tr("编辑技能文件", "Edit skill file") : root.tr("查看技能文件", "View skill file")
                                    color: textPrimary
                                    font.pixelSize: typeLabel
                                    font.weight: weightBold
                                }

                                PillActionButton {
                                    visible: root.selectedSkillFlag("path")
                                    text: root.tr("目录地址", "Folder path")
                                    iconSource: root.labIcon("copy-file-path")
                                    minHeight: 34
                                    horizontalPadding: 18
                                    outlined: true
                                    fillColor: isDark ? "#1D1612" : "#FFF8F1"
                                    hoverFillColor: bgCardHover
                                    outlineColor: borderSubtle
                                    hoverOutlineColor: borderDefault
                                    textColor: textPrimary
                                    onClicked: skillsService.openSelectedFolder()
                                }

                                Text {
                                    visible: root.draftDirty
                                    text: root.tr("未保存", "Unsaved")
                                    color: statusWarning
                                    font.pixelSize: typeMeta
                                    font.weight: weightBold
                                }
                            }

                            ScrollView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                                TextArea {
                                    id: editor
                                    objectName: "skillsEditor"
                                    property bool baoClickAwayEditor: true
                                    readOnly: !root.selectedSkillFlag("canEdit")
                                    color: textPrimary
                                    placeholderText: root.tr("这里显示技能的 SKILL.md 内容。", "This shows the selected skill's SKILL.md content.")
                                    placeholderTextColor: textPlaceholder
                                    background: null
                                    wrapMode: TextArea.Wrap
                                    leftPadding: sizeFieldPaddingX - 2
                                    rightPadding: sizeFieldPaddingX
                                    topPadding: 15
                                    bottomPadding: 12
                                    font.pixelSize: typeBody
                                    selectionColor: textSelectionBg
                                    selectedTextColor: textSelectionFg

                                    Component.onCompleted: {
                                        root.editorRef = editor
                                        root.syncDraft(true)
                                    }

                                    onTextChanged: {
                                        if (root.syncingDraft)
                                            return
                                        root.draftDirty = root.draftSkillId !== "" && text !== root.selectedContent
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true

                                PillActionButton {
                                    visible: root.selectedSkillFlag("canEdit")
                                    text: root.tr("还原", "Revert")
                                    minHeight: 34
                                    horizontalPadding: 18
                                    outlined: true
                                    fillColor: "transparent"
                                    hoverFillColor: bgCardHover
                                    outlineColor: borderSubtle
                                    hoverOutlineColor: borderDefault
                                    textColor: textPrimary
                                    onClicked: root.syncDraft(true)
                                }

                                Item { Layout.fillWidth: true }

                                PillActionButton {
                                    visible: root.selectedSkillFlag("canDelete")
                                    text: root.tr("删除", "Delete")
                                    minHeight: 34
                                    horizontalPadding: 18
                                    outlined: true
                                    fillColor: "transparent"
                                    hoverFillColor: isDark ? "#20F05A5A" : "#14F05A5A"
                                    outlineColor: statusError
                                    hoverOutlineColor: statusError
                                    textColor: statusError
                                    onClicked: skillsService.deleteSelectedSkill()
                                }

                                PillActionButton {
                                    visible: root.selectedSkillFlag("canEdit")
                                    text: root.tr("保存", "Save")
                                    minHeight: 34
                                    horizontalPadding: 20
                                    fillColor: accent
                                    hoverFillColor: accentHover
                                    buttonEnabled: root.draftDirty
                                    onClicked: skillsService.saveSelectedContent(editor.text)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: discoverPane

        SplitView {
            orientation: Qt.Horizontal
            spacing: 10
            handle: WorkspaceSplitHandle {}

            Rectangle {
                SplitView.preferredWidth: 520
                SplitView.minimumWidth: 360
                SplitView.fillWidth: true
                SplitView.fillHeight: true
                radius: 24
                color: "transparent"
                border.width: 0

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 42
                        radius: 16
                        color: bgInput
                        border.width: 1
                        border.color: borderSubtle

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 8
                            spacing: 8

                            TextField {
                                id: discoverQueryInput
                                property bool baoClickAwayEditor: true
                                Layout.fillWidth: true
                                hoverEnabled: true
                                leftPadding: 0
                                rightPadding: 0
                                background: null
                                color: textPrimary
                                placeholderText: root.tr("输入关键词搜索技能", "Search skills by keyword")
                                placeholderTextColor: textPlaceholder
                                selectionColor: textSelectionBg
                                selectedTextColor: textSelectionFg
                                font.pixelSize: typeBody
                                text: root.discoverQueryValue
                                onTextEdited: if (root.hasSkillsService) skillsService.setDiscoverQuery(text)
                            }

                            AsyncActionButton {
                                text: tr("搜索", "Search")
                                iconSource: root.icon("page-search")
                                minHeight: 32
                                horizontalPadding: 16
                                busy: root.serviceBusy
                                buttonEnabled: root.discoverQueryValue.trim().length > 0
                                onClicked: skillsService.searchRemote()
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 42
                        radius: 16
                        color: bgInput
                        border.width: 1
                        border.color: borderSubtle

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 8
                            spacing: 8

                            TextField {
                                id: discoverRefInput
                                property bool baoClickAwayEditor: true
                                Layout.fillWidth: true
                                hoverEnabled: true
                                leftPadding: 0
                                rightPadding: 0
                                background: null
                                color: textPrimary
                                placeholderText: "vercel-labs/agent-skills@frontend-design"
                                placeholderTextColor: textPlaceholder
                                selectionColor: textSelectionBg
                                selectedTextColor: textSelectionFg
                                font.pixelSize: typeBody
                                text: root.discoverReferenceValue
                                onTextEdited: if (root.hasSkillsService) skillsService.setDiscoverReference(text)
                            }

                            AsyncActionButton {
                                text: tr("导入", "Import")
                                iconSource: root.icon("circle-spark")
                                minHeight: 32
                                horizontalPadding: 16
                                busy: root.serviceBusy
                                buttonEnabled: root.discoverReferenceValue.trim().length > 0
                                onClicked: skillsService.installDiscoverReference()
                            }

                            IconCircleButton {
                                buttonSize: 30
                                iconSource: root.icon("page-search")
                                glyphSize: 15
                                fillColor: "transparent"
                                hoverFillColor: bgCardHover
                                outlineColor: borderSubtle
                                glyphColor: textSecondary
                                onClicked: if (root.hasSkillsService) skillsService.openSkillsRegistry()
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            Layout.fillWidth: true
                            text: root.tr("搜索结果", "Search results")
                            color: textPrimary
                            font.pixelSize: typeLabel
                            font.weight: weightBold
                        }

                        Rectangle {
                            radius: 11
                            color: isDark ? "#20FFFFFF" : "#14000000"
                            implicitHeight: 22
                            implicitWidth: discoverCountLabel.implicitWidth + 16

                            Text {
                                id: discoverCountLabel
                                anchors.centerIn: parent
                                text: String(root.discoverResults.length)
                                color: textSecondary
                                font.pixelSize: typeMeta
                                font.weight: weightBold
                            }
                        }
                    }

                    ListView {
                        id: discoverList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 10
                        bottomMargin: 12
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollIndicator.vertical: ScrollIndicator {
                            visible: false
                            width: 4
                            contentItem: Rectangle {
                                implicitWidth: 2
                                radius: 1
                                color: isDark ? "#28FFFFFF" : "#22000000"
                            }
                        }
                        model: root.discoverResults

                        delegate: Item {
                            id: discoverDelegateRoot
                            required property var modelData

                            width: discoverList.width
                            implicitHeight: 112
                            property bool selected: root.selectedDiscoverId === modelData.id

                            Rectangle {
                                anchors.fill: parent
                                radius: 22
                                color: discoverArea.containsMouse
                                       ? (discoverDelegateRoot.selected ? (isDark ? "#241914" : "#FFF1E2") : bgCardHover)
                                       : (discoverDelegateRoot.selected ? (isDark ? "#201612" : "#FFF7F0") : (isDark ? "#17120F" : "#FFFFFF"))
                                border.width: discoverDelegateRoot.selected ? 1.5 : 1
                                border.color: discoverDelegateRoot.selected ? accent : (isDark ? "#14FFFFFF" : "#10000000")

                                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                ColumnLayout {
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
                                            color: discoverDelegateRoot.selected ? (isDark ? "#302015" : "#F1D8BE") : (isDark ? "#211915" : "#F2E6D9")
                                            border.width: discoverDelegateRoot.selected ? 1 : 0
                                            border.color: discoverDelegateRoot.selected ? accent : "transparent"

                                            AppIcon {
                                                anchors.centerIn: parent
                                                width: 18
                                                height: 18
                                                source: root.icon("circle-spark")
                                                sourceSize: Qt.size(width, height)
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2

                                            Text {
                                                Layout.fillWidth: true
                                                text: String(discoverDelegateRoot.modelData.title || discoverDelegateRoot.modelData.name || "")
                                                color: textPrimary
                                                font.pixelSize: typeBody
                                                font.weight: weightBold
                                                elide: Text.ElideRight
                                            }

                                            Text {
                                                Layout.fillWidth: true
                                                text: discoverDelegateRoot.modelData.summary
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
                                            outlineColor: discoverDelegateRoot.selected ? accent : borderSubtle
                                            glyphColor: discoverDelegateRoot.selected ? accent : textSecondary
                                            onClicked: if (root.hasSkillsService) skillsService.selectDiscoverItem(discoverDelegateRoot.modelData.id)
                                        }
                                    }

                                    Row {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Text {
                                            text: {
                                                var publisher = String(discoverDelegateRoot.modelData.publisher || "")
                                                var version = String(discoverDelegateRoot.modelData.version || "")
                                                if (publisher && version)
                                                    return publisher + " · " + version
                                                return publisher || version
                                            }
                                            color: textSecondary
                                            font.pixelSize: typeMeta
                                            visible: text.length > 0
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: discoverDelegateRoot.modelData.reference
                                        color: accent
                                        font.pixelSize: typeMeta
                                        elide: Text.ElideRight
                                    }
                                }

                                MouseArea {
                                    id: discoverArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    acceptedButtons: Qt.LeftButton
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: if (root.hasSkillsService) skillsService.selectDiscoverItem(discoverDelegateRoot.modelData.id)
                                }
                            }
                        }

                        footer: Item {
                            width: discoverList.width
                            height: root.discoverResults.length === 0 ? 180 : 0

                            Column {
                                anchors.centerIn: parent
                                width: Math.min(parent.width - 40, 280)
                                spacing: 10
                                visible: parent.height > 0

                                Text {
                                    width: parent.width
                                    text: root.tr("还没有结果", "No results yet")
                                    color: textPrimary
                                    font.pixelSize: typeBody
                                    font.weight: weightBold
                                    horizontalAlignment: Text.AlignHCenter
                                }

                                Text {
                                    width: parent.width
                                    text: root.tr("输入关键词，或直接填写技能引用。", "Search by keyword, or provide a direct skill reference.")
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

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: discoverSummaryColumn.implicitHeight + 16
                        radius: 16
                        color: isDark ? "#181310" : "#FFF9F3"
                        border.width: 1
                        border.color: isDark ? "#12FFFFFF" : "#10000000"

                        Column {
                            id: discoverSummaryColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 10
                            spacing: 8

                            Text {
                                width: parent.width
                                text: String(root.selectedDiscoverValue("title", root.selectedDiscoverValue("name", root.tr("选择一个候选技能", "Choose a candidate skill"))))
                                color: textPrimary
                                font.pixelSize: typeLabel
                                font.weight: weightBold
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                text: String(root.selectedDiscoverValue("summary", root.tr("从中栏选择一个候选技能后，这里会显示引用、信任信息与导入动作。", "Choose a candidate from the list to inspect its reference, trust notes, and import action.")))
                                color: textSecondary
                                font.pixelSize: typeCaption
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                wrapMode: Text.WordWrap
                            }

                            Flow {
                                width: parent.width
                                spacing: 8

                                Rectangle {
                                    radius: 10
                                    height: 22
                                    color: isDark ? "#1D1713" : "#FFFFFF"
                                    border.width: 1
                                    border.color: isDark ? "#16FFFFFF" : "#10000000"
                                    width: publisherBadge.implicitWidth + 14
                                    visible: publisherBadge.text.length > 0

                                    Text {
                                        id: publisherBadge
                                        anchors.centerIn: parent
                                        text: String(root.selectedDiscoverValue("publisher", ""))
                                        color: textPrimary
                                        font.pixelSize: 11
                                        font.weight: weightBold
                                    }
                                }

                                Rectangle {
                                    radius: 10
                                    height: 22
                                    color: isDark ? "#1D1713" : "#FFFFFF"
                                    border.width: 1
                                    border.color: isDark ? "#16FFFFFF" : "#10000000"
                                    width: installStateBadge.implicitWidth + 14
                                    visible: installStateBadge.text.length > 0

                                    Text {
                                        id: installStateBadge
                                        anchors.centerIn: parent
                                        text: root.localizedText(root.selectedDiscoverValue("installStateLabel", ""), "")
                                        color: textPrimary
                                        font.pixelSize: 11
                                        font.weight: weightBold
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                text: String(root.selectedDiscoverValue("reference", root.discoverReferenceValue))
                                color: accent
                                font.pixelSize: typeCaption
                                wrapMode: Text.WrapAnywhere
                            }

                            Text {
                                width: parent.width
                                text: root.localizedText(root.selectedDiscoverValue("trustNote", ""), root.tr("选择结果后，直接导入到当前工作区。", "Select a result and import it into the current workspace."))
                                color: textSecondary
                                font.pixelSize: typeCaption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                visible: (root.selectedDiscoverValue("requires", []) || []).length > 0
                                text: root.tr("导入前提：", "Import prerequisites: ") + String((root.selectedDiscoverValue("requires", []) || []).join(", "))
                                color: textSecondary
                                font.pixelSize: typeCaption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                text: root.localizedText(root.selectedDiscoverValue("installStateDetail", ""), "")
                                color: textSecondary
                                font.pixelSize: typeCaption
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: taskSummaryColumn.implicitHeight + 16
                        radius: 16
                        color: isDark ? "#181310" : "#FFF9F3"
                        border.width: 1
                        border.color: isDark ? "#12FFFFFF" : "#10000000"

                        Column {
                            id: taskSummaryColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 10
                            spacing: 6

                            Row {
                                width: parent.width
                                spacing: 8

                                Rectangle {
                                    radius: 10
                                    height: 22
                                    width: taskStateLabel.implicitWidth + 14
                                    color: Qt.rgba(Qt.color(root.discoverTaskTone(root.discoverTask.state)).r,
                                                   Qt.color(root.discoverTaskTone(root.discoverTask.state)).g,
                                                   Qt.color(root.discoverTaskTone(root.discoverTask.state)).b,
                                                   isDark ? 0.18 : 0.10)
                                    border.width: 1
                                    border.color: Qt.rgba(Qt.color(root.discoverTaskTone(root.discoverTask.state)).r,
                                                          Qt.color(root.discoverTaskTone(root.discoverTask.state)).g,
                                                          Qt.color(root.discoverTaskTone(root.discoverTask.state)).b,
                                                          isDark ? 0.34 : 0.24)

                                    Text {
                                        id: taskStateLabel
                                        anchors.centerIn: parent
                                        text: root.discoverTaskLabel(root.discoverTask.state)
                                        color: textPrimary
                                        font.pixelSize: 11
                                        font.weight: weightBold
                                    }
                                }

                                Text {
                                    text: root.discoverTask.kind === "install" ? root.tr("导入任务", "Import task") : root.tr("搜索任务", "Search task")
                                    color: textSecondary
                                    font.pixelSize: typeCaption
                                    visible: root.discoverTask.state !== "idle"
                                }
                            }

                            Text {
                                width: parent.width
                                text: root.discoverTask.message
                                      ? root.discoverTask.message
                                      : root.tr("搜索或导入时，这里会显示当前任务状态。", "Current search/import status will appear here.")
                                color: root.discoverTask.state === "failed" ? statusError : textSecondary
                                font.pixelSize: typeCaption
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                width: parent.width
                                visible: (root.discoverTask.reference || "").length > 0
                                text: root.discoverTask.reference || ""
                                color: accent
                                font.pixelSize: typeCaption
                                wrapMode: Text.WrapAnywhere
                            }
                        }
                    }

                }
            }
        }
    }

    AppModal {
        id: createSkillModal
        title: root.tr("新建工作区技能", "Create workspace skill")
        closeText: root.tr("关闭", "Close")
        maxModalWidth: 560
        maxModalHeight: 420
        darkMode: isDark

        onOpened: {
            skillNameInput.text = ""
            skillDescriptionInput.text = ""
            skillNameInput.forceActiveFocus()
        }

        Column {
            width: parent.width
            spacing: 14

            Text {
                width: parent.width
                text: root.tr("技能名只允许小写字母、数字和连字符，创建后直接写入当前工作区。", "Skill names accept lowercase letters, digits, and hyphens, then get written directly into the current workspace.")
                color: textSecondary
                font.pixelSize: typeMeta
                wrapMode: Text.WordWrap
            }

            Rectangle {
                width: parent.width
                height: 44
                radius: 16
                color: skillNameInput.activeFocus ? bgInputFocus : (skillNameInput.hovered ? bgInputHover : bgInput)
                border.width: skillNameInput.activeFocus ? 1.5 : 1
                border.color: skillNameInput.activeFocus ? borderFocus : borderSubtle

                TextField {
                    id: skillNameInput
                    property bool baoClickAwayEditor: true
                    anchors.fill: parent
                    hoverEnabled: true
                    leftPadding: sizeFieldPaddingX
                    rightPadding: sizeFieldPaddingX
                    topPadding: 0
                    bottomPadding: 0
                    background: null
                    color: textPrimary
                    placeholderText: root.tr("例如：design-ops", "For example: design-ops")
                    placeholderTextColor: textPlaceholder
                    selectionColor: textSelectionBg
                    selectedTextColor: textSelectionFg
                    font.pixelSize: typeBody
                }
            }

            Rectangle {
                width: parent.width
                height: 120
                radius: 18
                color: skillDescriptionInput.activeFocus ? bgInputFocus : (skillDescriptionInput.hovered ? bgInputHover : bgInput)
                border.width: skillDescriptionInput.activeFocus ? 1.5 : 1
                border.color: skillDescriptionInput.activeFocus ? borderFocus : borderSubtle

                TextArea {
                    id: skillDescriptionInput
                    property bool baoClickAwayEditor: true
                    anchors.fill: parent
                    hoverEnabled: true
                    background: null
                    wrapMode: TextArea.Wrap
                    leftPadding: sizeFieldPaddingX
                    rightPadding: sizeFieldPaddingX
                    topPadding: 12
                    bottomPadding: 12
                    color: textPrimary
                    placeholderText: root.tr("一句话描述这个技能何时使用。", "Describe when this skill should be used.")
                    placeholderTextColor: textPlaceholder
                    selectionColor: textSelectionBg
                    selectedTextColor: textSelectionFg
                    font.pixelSize: typeBody
                }
            }
        }

        footer: [
            PillActionButton {
                text: root.tr("创建技能", "Create skill")
                minHeight: 34
                horizontalPadding: 24
                fillColor: accent
                hoverFillColor: accentHover
                buttonEnabled: skillNameInput.text.trim().length > 0
                onClicked: {
                    if (!root.hasSkillsService)
                        return
                    if (skillsService.createSkill(skillNameInput.text, skillDescriptionInput.text))
                        createSkillModal.close()
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
