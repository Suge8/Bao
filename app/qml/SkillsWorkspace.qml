pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property bool active: false
    property string currentMode: "installed"
    property string draftContent: ""
    property string draftSkillId: ""
    property bool draftDirty: false
    property bool syncingDraft: false
    property real revealOpacity: 1.0
    property real revealScale: 1.0
    property real revealShift: 0.0
    property bool installedTabHovered: false
    property bool discoverTabHovered: false

    readonly property bool hasSkillsService: typeof skillsService !== "undefined" && skillsService !== null
    readonly property string effectiveUiLanguage: {
        if (typeof uiLanguage === "string" && uiLanguage !== "auto")
            return uiLanguage
        if (typeof autoLanguage === "string")
            return autoLanguage
        return "en"
    }
    readonly property bool isZhLang: effectiveUiLanguage === "zh"
    readonly property int shadowedCount: {
        if (!hasSkillsService)
            return 0
        var items = skillsService.skills || []
        return items.filter(function(item) { return !!item.shadowed }).length
    }
    readonly property int missingRequirementCount: {
        if (!hasSkillsService)
            return 0
        var items = skillsService.skills || []
        return items.filter(function(item) { return !!item.missingRequirements }).length
    }
    readonly property var builtinSkillLocaleMap: ({
        "agent-browser": { zhName: "浏览器代理", zhDescription: "用于浏览器自动化、截图、表单填写、网页测试与抓取。" },
        "clawhub": { zhName: "ClawHub 技能市场", zhDescription: "用于从 ClawHub 查找、安装或更新技能。" },
        "coding-agent": { zhName: "通用编程代理", zhDescription: "当没有更具体的编程技能时，用于一般编码任务。" },
        "copywriting": { zhName: "营销文案", zhDescription: "用于营销文案、标题、CTA 与页面改写。" },
        "cron": { zhName: "定时任务", zhDescription: "用于安排提醒、周期任务或一次性任务。" },
        "docx": { zhName: "Word 文档", zhDescription: "用于 Word 文档、报告、备忘录、信函、合同或 .docx 文件。" },
        "find-skills": { zhName: "发现技能", zhDescription: "用于查找、安装、推荐技能或扩展新能力。" },
        "github": { zhName: "GitHub", zhDescription: "用于 GitHub issue、PR、Actions、发布或仓库查询。" },
        "image-gen": { zhName: "图像生成", zhDescription: "用于绘图、生成图像、设计视觉内容或插画。" },
        "memory": { zhName: "记忆", zhDescription: "用于记忆检索、整合、偏好管理或项目上下文。" },
        "pdf": { zhName: "PDF", zhDescription: "用于 PDF、扫描件、OCR、表单、内容提取、合并或拆分。" },
        "pptx": { zhName: "演示文稿", zhDescription: "用于幻灯片、演示、路演 deck 或 .pptx 文件。" },
        "skill-creator": { zhName: "技能创建器", zhDescription: "用于创建、更新、打包或整理技能及其资源。" },
        "summarize": { zhName: "总结", zhDescription: "用于总结 URL、文件、播客、视频或提取转录内容。" },
        "tmux": { zhName: "tmux 会话", zhDescription: "用于交互式终端会话、TUI 应用或长生命周期 CLI 工作流。" },
        "weather": { zhName: "天气", zhDescription: "用于查询当前位置天气、预报或天气相关问题。" },
        "xlsx": { zhName: "表格", zhDescription: "用于电子表格、Excel、CSV/TSV 清洗、表格处理或 .xlsx 文件。" }
    })

    function tr(zh, en) {
        return isZhLang ? zh : en
    }

    function icon(path) {
        return "../resources/icons/vendor/iconoir/" + path + ".svg"
    }

    function labIcon(path) {
        return "../resources/icons/vendor/lucide-lab/" + path + ".svg"
    }

    function localizedSkillName(skill) {
        if (!skill)
            return ""
        var rawName = String(skill.name || "")
        if (!isZhLang)
            return rawName
        var localized = builtinSkillLocaleMap[rawName]
        return localized && localized.zhName ? localized.zhName : rawName
    }

    function localizedSkillDescription(skill) {
        if (!skill)
            return ""
        var rawName = String(skill.name || "")
        var rawDescription = String(skill.description || "")
        if (!isZhLang)
            return rawDescription
        var localized = builtinSkillLocaleMap[rawName]
        return localized && localized.zhDescription ? localized.zhDescription : rawDescription
    }

    function skillIconSource(skill) {
        if (!skill)
            return icon("book-stack")
        switch (String(skill.name || "")) {
        case "agent-browser":
            return icon("page-search")
        case "clawhub":
        case "skill-creator":
            return labIcon("toolbox")
        case "coding-agent":
        case "tmux":
            return icon("computer")
        case "copywriting":
        case "summarize":
            return icon("message-text")
        case "cron":
            return icon("calendar-rotate")
        case "find-skills":
            return icon("page-search")
        case "github":
            return icon("activity")
        case "image-gen":
            return icon("circle-spark")
        case "memory":
            return icon("brain-electricity")
        case "pdf":
        case "docx":
        case "pptx":
            return icon("book-stack")
        case "weather":
            return icon("activity")
        case "xlsx":
            return icon("database-settings")
        default:
            return String(skill.source || "") === "workspace" ? labIcon("toolbox") : icon("book-stack")
        }
    }

    function sourceLabel(skill) {
        return String(skill.source || "") === "workspace" ? tr("工作区", "Workspace") : tr("内建", "Built-in")
    }

    function primaryStatusLabel(skill) {
        if (!skill)
            return ""
        if (skill.missingRequirements)
            return tr("需补依赖", "Missing deps")
        if (skill.shadowed)
            return tr("重复", "Duplicate")
        if (skill.always)
            return tr("常驻", "Always on")
        return ""
    }

    function primaryStatusColor(skill) {
        if (!skill)
            return textSecondary
        if (skill.missingRequirements)
            return statusError
        if (skill.shadowed)
            return "#F59E0B"
        if (skill.always)
            return accent
        return textSecondary
    }

    function selectedSkillValue(key, fallbackValue) {
        if (!root.hasSkillsService || !skillsService.selectedSkill)
            return fallbackValue
        var value = skillsService.selectedSkill[key]
        return (typeof value === "undefined" || value === null) ? fallbackValue : value
    }

    function selectedSkillFlag(key) {
        return !!root.selectedSkillValue(key, false)
    }

    function selectedDiscoverValue(key, fallbackValue) {
        if (!root.hasSkillsService || !skillsService.selectedDiscoverItem)
            return fallbackValue
        var value = skillsService.selectedDiscoverItem[key]
        return (typeof value === "undefined" || value === null) ? fallbackValue : value
    }

    function toastMessage(code, ok) {
        if (!ok)
            return code
        if (code === "created")
            return tr("技能已创建", "Skill created")
        if (code === "forked")
            return tr("已复制到工作区", "Copied to workspace")
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

    function syncDraft(force) {
        if (!hasSkillsService)
            return
        var selectedId = skillsService.selectedSkillId || ""
        if (!force && draftDirty && draftSkillId === selectedId)
            return
        syncingDraft = true
        draftSkillId = selectedId
        draftContent = skillsService.selectedContent || ""
        draftDirty = false
        syncingDraft = false
    }

    onActiveChanged: if (active) playReveal()
    Component.onCompleted: syncDraft(true)

    Connections {
        target: root.hasSkillsService ? skillsService : null

        function onChanged() {
            root.syncDraft(root.draftSkillId !== skillsService.selectedSkillId)
        }

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

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12

            Rectangle {
                Layout.fillWidth: true
                radius: 22
                color: isDark ? "#14100D" : "#F7F0E7"
                border.width: 1
                border.color: isDark ? "#1EFFFFFF" : "#12000000"
                implicitHeight: 60

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12

                    Item {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter

                        Text {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            text: tr("技能", "Skills")
                            color: textPrimary
                            font.pixelSize: typeTitle
                            font.weight: weightBold
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter

                        Rectangle {
                            id: modeTabBar
                            anchors.centerIn: parent
                            implicitWidth: modeTabRow.implicitWidth + 8
                            implicitHeight: 46
                            radius: 23
                            color: isDark ? "#12FFFFFF" : "#08000000"
                            border.width: 1
                            border.color: borderSubtle

                            Rectangle {
                                id: modeTabHighlight
                                y: 6
                                height: parent.height - 12
                                radius: height / 2
                                color: accent
                                x: 6 + (installedTab.width + 6) * (root.currentMode === "installed" ? 0 : 1)
                                width: root.currentMode === "installed" ? installedTab.width : discoverTab.width

                                Behavior on x { NumberAnimation { duration: 220; easing.type: easeEmphasis } }
                                Behavior on width { NumberAnimation { duration: 220; easing.type: easeStandard } }
                            }

                            RowLayout {
                                id: modeTabRow
                                anchors.fill: parent
                                anchors.margins: 4
                                spacing: 6

                                Rectangle {
                                    id: installedTab
                                    Layout.preferredWidth: installedTabContent.implicitWidth + 22
                                    Layout.fillHeight: true
                                    radius: 17
                                    color: root.installedTabHovered && root.currentMode !== "installed"
                                           ? (isDark ? "#10FFFFFF" : "#08000000")
                                           : "transparent"

                                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                    Row {
                                        id: installedTabContent
                                        anchors.centerIn: parent
                                        spacing: 8

                                        Image {
                                            width: 15
                                            height: 15
                                            anchors.verticalCenter: parent.verticalCenter
                                            source: root.icon("book-stack")
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true
                                            mipmap: true
                                            opacity: root.currentMode === "installed" ? 1.0 : 0.72
                                        }

                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: root.tr("已安装", "Installed")
                                            color: root.currentMode === "installed" ? "#FFFFFFFF" : textSecondary
                                            font.pixelSize: typeLabel
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onEntered: root.installedTabHovered = true
                                        onExited: root.installedTabHovered = false
                                        onClicked: root.currentMode = "installed"
                                    }
                                }

                                Rectangle {
                                    id: discoverTab
                                    Layout.preferredWidth: discoverTabContent.implicitWidth + 22
                                    Layout.fillHeight: true
                                    radius: 17
                                    color: root.discoverTabHovered && root.currentMode !== "discover"
                                           ? (isDark ? "#10FFFFFF" : "#08000000")
                                           : "transparent"

                                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                    Row {
                                        id: discoverTabContent
                                        anchors.centerIn: parent
                                        spacing: 8

                                        Image {
                                            width: 15
                                            height: 15
                                            anchors.verticalCenter: parent.verticalCenter
                                            source: root.icon("page-search")
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true
                                            mipmap: true
                                            opacity: root.currentMode === "discover" ? 1.0 : 0.72
                                        }

                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: root.tr("发现", "Discover")
                                            color: root.currentMode === "discover" ? "#FFFFFFFF" : textSecondary
                                            font.pixelSize: typeLabel
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onEntered: root.discoverTabHovered = true
                                        onExited: root.discoverTabHovered = false
                                        onClicked: root.currentMode = "discover"
                                    }
                                }
                            }
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter

                        RowLayout {
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

    Component {
        id: installedPane

        SplitView {
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
                            text: root.hasSkillsService ? skillsService.query : ""
                            onTextEdited: if (root.hasSkillsService) skillsService.setQuery(text)
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Repeater {
                            model: [
                                { value: "all", zh: "全部", en: "All" },
                                { value: "workspace", zh: "工作区", en: "Workspace" },
                                { value: "builtin", zh: "内建", en: "Built-in" },
                                { value: "attention", zh: "重复 / 缺依赖", en: "Duplicate / missing deps" }
                            ]

                            delegate: PillActionButton {
                                required property var modelData

                                Layout.fillWidth: true
                                text: root.isZhLang ? modelData.zh : modelData.en
                                minHeight: 34
                                horizontalPadding: 14
                                outlined: true
                                fillColor: root.hasSkillsService && skillsService.sourceFilter === modelData.value ? accentMuted : "transparent"
                                hoverFillColor: root.hasSkillsService && skillsService.sourceFilter === modelData.value ? accentMuted : bgCardHover
                                outlineColor: root.hasSkillsService && skillsService.sourceFilter === modelData.value ? accent : borderSubtle
                                hoverOutlineColor: root.hasSkillsService && skillsService.sourceFilter === modelData.value ? accentHover : borderDefault
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
                                text: root.hasSkillsService
                                      ? (tr("共 ", "Total ") + String(skillsService.totalCount) + tr(" · 重复 ", " · Duplicate ") + root.shadowedCount + tr(" · 缺依赖 ", " · Missing ") + root.missingRequirementCount)
                                      : "0"
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
                        model: root.hasSkillsService ? skillsService.skills : []

                        delegate: Item {
                            id: skillDelegateRoot
                            required property var modelData

                            width: skillList.width
                            implicitHeight: 120
                            property bool selected: root.hasSkillsService && skillsService.selectedSkillId === modelData.id

                            Rectangle {
                                anchors.fill: parent
                                radius: 22
                                color: skillArea.containsMouse
                                       ? (skillDelegateRoot.selected ? (isDark ? "#241914" : "#FFF1E2") : bgCardHover)
                                       : (skillDelegateRoot.selected ? (isDark ? "#201612" : "#FFF7F0") : (isDark ? "#17120F" : "#FFFFFF"))
                                border.width: skillDelegateRoot.selected ? 1.5 : 1
                                border.color: skillDelegateRoot.selected ? accent : (isDark ? "#14FFFFFF" : "#10000000")
                                scale: skillArea.pressed ? 0.99 : (skillArea.containsMouse ? motionHoverScaleSubtle : 1.0)

                                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

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
                                            width: 36
                                            height: 36
                                            radius: 12
                                            color: skillDelegateRoot.selected ? (isDark ? "#302015" : "#F1D8BE") : (isDark ? "#211915" : "#F2E6D9")
                                            border.width: skillDelegateRoot.selected ? 1 : 0
                                            border.color: skillDelegateRoot.selected ? accent : "transparent"

                                            Image {
                                                anchors.centerIn: parent
                                                width: 18
                                                height: 18
                                                source: root.skillIconSource(skillDelegateRoot.modelData)
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
                                        width: parent.width
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

                        footer: Item {
                            width: skillList.width
                            height: root.hasSkillsService && skillsService.totalCount === 0 ? 180 : 0

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

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Text {
                                Layout.fillWidth: true
                                text: root.hasSkillsService ? (root.localizedSkillName(skillsService.selectedSkill) || root.tr("选择一个技能", "Choose a skill")) : root.tr("选择一个技能", "Choose a skill")
                                color: textPrimary
                                font.pixelSize: typeLabel
                                font.weight: weightBold
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.hasSkillsService ? (root.localizedSkillDescription(skillsService.selectedSkill) || root.tr("从中栏选择一个技能后，这里会显示说明、状态和可编辑内容。", "Choose a skill from the list to inspect its summary, status, and editable content.")) : root.tr("从中栏选择一个技能后，这里会显示说明、状态和可编辑内容。", "Choose a skill from the list to inspect its summary, status, and editable content.")
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
                            spacing: 6

                            Flow {
                                width: parent.width
                                spacing: 8

                                Repeater {
                                    model: root.hasSkillsService ? [
                                        { visible: root.selectedSkillFlag("name"), text: root.sourceLabel(skillsService.selectedSkill), tone: root.selectedSkillValue("source", "") === "workspace" ? "#22C55E" : "#60A5FA" },
                                        { visible: !!root.primaryStatusLabel(skillsService.selectedSkill), text: root.primaryStatusLabel(skillsService.selectedSkill), tone: root.primaryStatusColor(skillsService.selectedSkill) }
                                    ] : []

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
                                    text: root.selectedSkillValue("source", "") === "workspace" ? root.tr("编辑技能说明", "Edit skill file") : root.tr("查看技能说明", "View skill file")
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
                                    property bool baoClickAwayEditor: true
                                    readOnly: !root.selectedSkillFlag("canEdit")
                                    text: root.draftContent
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

                                    onTextChanged: {
                                        if (root.syncingDraft)
                                            return
                                        root.draftContent = text
                                        root.draftDirty = root.draftSkillId !== "" && text !== (root.hasSkillsService ? skillsService.selectedContent : "")
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
                                    onClicked: skillsService.saveSelectedContent(root.draftContent)
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
                                text: root.hasSkillsService ? skillsService.discoverQuery : ""
                                onTextEdited: if (root.hasSkillsService) skillsService.setDiscoverQuery(text)
                            }

                            AsyncActionButton {
                                text: tr("搜索", "Search")
                                iconSource: root.icon("page-search")
                                minHeight: 32
                                horizontalPadding: 16
                                busy: root.hasSkillsService && skillsService.busy
                                buttonEnabled: root.hasSkillsService && (skillsService.discoverQuery || "").trim().length > 0
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
                                text: root.hasSkillsService ? skillsService.discoverReference : ""
                                onTextEdited: if (root.hasSkillsService) skillsService.setDiscoverReference(text)
                            }

                            AsyncActionButton {
                                text: tr("导入", "Import")
                                iconSource: root.icon("circle-spark")
                                minHeight: 32
                                horizontalPadding: 16
                                busy: root.hasSkillsService && skillsService.busy
                                buttonEnabled: root.hasSkillsService && (skillsService.discoverReference || "").trim().length > 0
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
                                text: root.hasSkillsService ? String(skillsService.discoverResults.length) : "0"
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
                        model: root.hasSkillsService ? skillsService.discoverResults : []

                        delegate: Item {
                            id: discoverDelegateRoot
                            required property var modelData

                            width: discoverList.width
                            implicitHeight: 112
                            property bool selected: root.hasSkillsService && skillsService.selectedDiscoverId === modelData.id

                            Rectangle {
                                anchors.fill: parent
                                radius: 22
                                color: discoverArea.containsMouse
                                       ? (discoverDelegateRoot.selected ? (isDark ? "#241914" : "#FFF1E2") : bgCardHover)
                                       : (discoverDelegateRoot.selected ? (isDark ? "#201612" : "#FFF7F0") : (isDark ? "#17120F" : "#FFFFFF"))
                                border.width: discoverDelegateRoot.selected ? 1.5 : 1
                                border.color: discoverDelegateRoot.selected ? accent : (isDark ? "#14FFFFFF" : "#10000000")
                                scale: discoverArea.pressed ? 0.99 : (discoverArea.containsMouse ? motionHoverScaleSubtle : 1.0)

                                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                                Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

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
                                            width: 36
                                            height: 36
                                            radius: 12
                                            color: discoverDelegateRoot.selected ? (isDark ? "#302015" : "#F1D8BE") : (isDark ? "#211915" : "#F2E6D9")
                                            border.width: discoverDelegateRoot.selected ? 1 : 0
                                            border.color: discoverDelegateRoot.selected ? accent : "transparent"

                                            Image {
                                                anchors.centerIn: parent
                                                width: 18
                                                height: 18
                                                source: root.icon("circle-spark")
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
                                                Layout.fillWidth: true
                                                text: discoverDelegateRoot.modelData.name
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

                                    Text {
                                        width: parent.width
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
                            height: root.hasSkillsService && skillsService.discoverResults.length === 0 ? 180 : 0

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

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Text {
                                Layout.fillWidth: true
                                text: String(root.selectedDiscoverValue("name", root.tr("选择一个候选技能", "Choose a candidate skill")))
                                color: textPrimary
                                font.pixelSize: typeLabel
                                font.weight: weightBold
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.fillWidth: true
                                text: String(root.selectedDiscoverValue("summary", root.tr("从中栏选择一个候选技能后，这里会显示引用与导入动作。", "Choose a candidate from the list to inspect its reference and import action.")))
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
                            spacing: 6

                            Text {
                                width: parent.width
                                text: String(root.selectedDiscoverValue("reference", root.hasSkillsService ? (skillsService.discoverReference || "") : ""))
                                color: accent
                                font.pixelSize: typeCaption
                                wrapMode: Text.WrapAnywhere
                            }

                            Text {
                                width: parent.width
                                text: root.hasSkillsService && skillsService.lastError ? skillsService.lastError : root.tr("选择结果后，直接导入到当前工作区。", "Select a result and import it into the current workspace.")
                                color: root.hasSkillsService && skillsService.lastError ? statusError : textSecondary
                                font.pixelSize: typeCaption
                                wrapMode: Text.WordWrap
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
