pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property bool active: false
    property string currentScope: "memory"
    property string experienceDeprecatedMode: "active"
    property int experienceMinQuality: 0
    property string experienceSortBy: "updated_desc"
    property string noticeText: ""
    property bool noticeSuccess: true
    property string destructiveAction: ""
    property string destructiveKey: ""
    property string destructiveCategory: ""
    property string editorCategory: ""
    property string editorText: ""
    property bool editorDirty: false
    property string appendText: ""
    property string promoteCategory: "project"
    property string memorySearchQuery: ""
    property string experienceSearchQuery: ""
    property real revealOpacity: 1.0
    property real revealScale: 1.0
    property real revealShift: 0.0
    readonly property string memoryIconSource: "../resources/icons/vendor/iconoir/brain-electricity.svg"
    readonly property string experienceIconSource: "../resources/icons/zap.svg"
    readonly property string searchIconSource: "../resources/icons/vendor/iconoir/page-search.svg"
    readonly property string detailIconSource: "../resources/icons/vendor/iconoir/message-text.svg"
    readonly property string refreshIconSource: "../resources/icons/vendor/iconoir/calendar-rotate.svg"
    readonly property string saveIconSource: "../resources/icons/vendor/iconoir/book-stack.svg"
    readonly property string appendIconSource: "../resources/icons/vendor/iconoir/nav-arrow-up.svg"
    readonly property string deprecateIconSource: "../resources/icons/vendor/iconoir/message-alert.svg"
    readonly property string removeIconSource: "../resources/icons/vendor/iconoir/bubble-xmark.svg"
    readonly property bool hasMemoryService: typeof memoryService !== "undefined" && memoryService !== null
    readonly property var memoryStats: hasMemoryService ? memoryService.memoryStats : ({})
    readonly property var experienceStats: hasMemoryService ? memoryService.experienceStats : ({})
    readonly property var selectedMemoryCategory: hasMemoryService ? memoryService.selectedMemoryCategory : ({})
    readonly property var selectedExperience: hasMemoryService ? memoryService.selectedExperience : ({})
    readonly property bool canMutate: hasMemoryService && memoryService.ready && !memoryService.blockingBusy
    readonly property var filteredMemoryCategories: {
        if (!hasMemoryService)
            return []
        var items = memoryService.memoryCategories || []
        var query = normalizeQuery(root.memorySearchQuery)
        if (!query)
            return items
        return items.filter(function(item) {
            var haystack = [item.category || "", item.content || "", item.preview || ""].join(" ").toLowerCase()
            return haystack.indexOf(query) !== -1
        })
    }

    function langCode() {
        if (typeof effectiveLang === "string" && (effectiveLang === "zh" || effectiveLang === "en"))
            return effectiveLang
        if (typeof uiLanguage === "string" && uiLanguage === "zh")
            return "zh"
        return "en"
    }

    function tr(zh, en) {
        return langCode() === "zh" ? zh : en
    }

    function playReveal() {
        root.revealOpacity = motionPageRevealStartOpacity
        root.revealScale = motionPageRevealStartScale
        root.revealShift = motionPageShiftSubtle
        revealAnimation.restart()
    }

    function normalizeQuery(value) {
        return String(value || "").trim().toLowerCase()
    }

    function currentHeaderTitle() {
        return currentScope === "memory" ? tr("长期记忆", "Long-term Memory") : tr("经验", "Experiences")
    }

    function currentHeaderCaption() {
        if (currentScope === "memory")
            return tr("管理 Bao 的长期记忆。", "Manage Bao's long-term memory.")
        return tr("管理 Bao 总结出的经验。", "Manage Bao's extracted experiences.")
    }

    function memoryCategoryTitle(category) {
        switch (String(category || "")) {
        case "preference":
            return tr("偏好记忆", "Preference Memory")
        case "personal":
            return tr("个人记忆", "Personal Memory")
        case "project":
            return tr("项目记忆", "Project Memory")
        case "general":
            return tr("通用记忆", "General Memory")
        default:
            return tr("选择一个分类", "Choose a category")
        }
    }

    function memoryCategoryMeta(detail) {
        var updatedLabel = String(detail.updated_label || "")
        var factCount = Number(detail.fact_count || 0)
        if (!updatedLabel)
            return tr("这里适合保存长期有效的信息。", "Use this area for durable information.")
        return tr(
            "最近更新 " + updatedLabel + " · " + factCount + " 条事实",
            "Updated " + updatedLabel + " · " + factCount + " facts"
        )
    }

    function hasSelectedMemory() {
        return !!String(selectedMemoryCategory.category || "")
    }

    function hasSelectedExperience() {
        return !!String(selectedExperience.key || "")
    }

    function applyExperienceFilters() {
        if (!hasMemoryService)
            return
        memoryService.reloadExperiences(
            root.experienceSearchQuery,
            "",
            "",
            experienceDeprecatedMode,
            experienceMinQuality,
            experienceSortBy
        )
    }

    function selectMemory(category) {
        if (!hasMemoryService)
            return
        memoryService.selectMemoryCategory(category)
        promoteCategory = category
    }

    function syncEditorFromSelection() {
        if (currentScope !== "memory")
            return
        var detail = selectedMemoryCategory
        var category = String(detail.category || "")
        if (!category)
            return
        if (editorDirty && editorCategory === category)
            return
        editorCategory = category
        editorText = String(detail.content || "")
        editorDirty = false
    }

    function openDestructiveModal(action, key, category) {
        destructiveAction = action
        destructiveKey = key
        destructiveCategory = category
        destructiveModal.open()
    }

    function confirmDestructiveAction() {
        if (!hasMemoryService)
            return
        if (destructiveAction === "clearMemory")
            memoryService.clearMemoryCategory(destructiveCategory)
        else if (destructiveAction === "deleteExperience")
            memoryService.deleteExperience(destructiveKey)
        destructiveModal.close()
    }

    function resetExperienceFilters() {
        experienceDeprecatedMode = "active"
        experienceMinQuality = 0
        experienceSortBy = "updated_desc"
        root.experienceSearchQuery = ""
        applyExperienceFilters()
    }

    function onReadyIfNeeded() {
        if (!hasMemoryService || !memoryService.ready)
            return
        memoryService.selectMemoryCategory(promoteCategory)
    }

    onActiveChanged: {
        if (active)
            playReveal()
    }

    Component.onCompleted: {
        playReveal()
        onReadyIfNeeded()
    }

    Connections {
        target: hasMemoryService ? memoryService : null

        function onReadyChanged() {
            root.onReadyIfNeeded()
        }

        function onSelectedMemoryCategoryChanged() {
            root.syncEditorFromSelection()
        }

        function onAppendCommitted() {
            root.appendText = ""
        }

        function onOperationFinished(message, ok) {
            root.noticeText = message
            root.noticeSuccess = ok
            if (root.currentScope === "experience")
                root.applyExperienceFilters()
        }

        function onErrorChanged(error) {
            if (!error)
                return
            root.noticeText = error
            root.noticeSuccess = false
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
                                id: headerTitleRow
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 10

                                Rectangle {
                                    implicitWidth: 34
                                    implicitHeight: 34
                                    radius: 17
                                    color: isDark ? "#1D1713" : "#F3E7DA"
                                    border.width: 1
                                    border.color: borderSubtle

                                    Image {
                                        anchors.centerIn: parent
                                        width: 18
                                        height: 18
                                        source: root.currentScope === "memory" ? root.memoryIconSource : root.experienceIconSource
                                        fillMode: Image.PreserveAspectFit
                                        smooth: true
                                    }
                                }

                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2

                                    Text {
                                        text: root.currentHeaderTitle()
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

                            Rectangle {
                                id: topTabBar
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.verticalCenter: parent.verticalCenter
                                implicitWidth: topTabRow.implicitWidth + 8
                                implicitHeight: 46
                                radius: 23
                                color: isDark ? "#12FFFFFF" : "#08000000"
                                border.width: 1
                                border.color: borderSubtle

                                Rectangle {
                                    id: topTabHighlight
                                    y: 6
                                    height: parent.height - 12
                                    radius: height / 2
                                    color: accent
                                    x: 6 + (memoryTab.width + 6) * (root.currentScope === "memory" ? 0 : 1)
                                    width: root.currentScope === "memory" ? memoryTab.width : experienceTab.width

                                    Behavior on x { NumberAnimation { duration: 220; easing.type: easeEmphasis } }
                                    Behavior on width { NumberAnimation { duration: 220; easing.type: easeStandard } }
                                }

                                RowLayout {
                                    id: topTabRow
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    spacing: 6

                                    Rectangle {
                                        id: memoryTab
                                        Layout.preferredWidth: memoryTabContent.implicitWidth + 22
                                        Layout.fillHeight: true
                                        radius: 17
                                        color: memoryTabHover.containsMouse && root.currentScope !== "memory"
                                               ? (isDark ? "#10FFFFFF" : "#08000000")
                                               : "transparent"

                                        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                        Row {
                                            id: memoryTabContent
                                            anchors.centerIn: parent
                                            spacing: 6

                                            Image {
                                                width: 14
                                                height: 14
                                                source: root.memoryIconSource
                                                fillMode: Image.PreserveAspectFit
                                                smooth: true
                                                opacity: root.currentScope === "memory" ? 1.0 : 0.72
                                            }

                                            Text {
                                                text: root.tr("长期记忆", "Memory")
                                                color: root.currentScope === "memory" ? "#FFFFFFFF" : textSecondary
                                                font.pixelSize: typeLabel
                                                font.weight: Font.DemiBold
                                            }
                                        }

                                        MouseArea {
                                            id: memoryTabHover
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                root.currentScope = "memory"
                                                root.syncEditorFromSelection()
                                            }
                                        }
                                    }

                                    Rectangle {
                                        id: experienceTab
                                        Layout.preferredWidth: experienceTabContent.implicitWidth + 22
                                        Layout.fillHeight: true
                                        radius: 17
                                        color: experienceTabHover.containsMouse && root.currentScope !== "experience"
                                               ? (isDark ? "#10FFFFFF" : "#08000000")
                                               : "transparent"

                                        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

                                        Row {
                                            id: experienceTabContent
                                            anchors.centerIn: parent
                                            spacing: 6

                                            Image {
                                                width: 14
                                                height: 14
                                                source: root.experienceIconSource
                                                fillMode: Image.PreserveAspectFit
                                                smooth: true
                                                opacity: root.currentScope === "experience" ? 1.0 : 0.72
                                            }

                                            Text {
                                                text: root.tr("经验", "Experiences")
                                                color: root.currentScope === "experience" ? "#FFFFFFFF" : textSecondary
                                                font.pixelSize: typeLabel
                                                font.weight: Font.DemiBold
                                            }
                                        }

                                        MouseArea {
                                            id: experienceTabHover
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                root.currentScope = "experience"
                                                root.applyExperienceFilters()
                                            }
                                        }
                                    }
                                }
                            }

                            AsyncActionButton {
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: root.hasMemoryService && memoryService.blockingBusy ? root.tr("处理中", "Working") : root.tr("刷新", "Refresh")
                                busy: root.hasMemoryService && memoryService.blockingBusy
                                iconSource: root.refreshIconSource
                                fillColor: isDark ? "#2A1B11" : "#E7D5C7"
                                hoverFillColor: isDark ? "#342116" : "#DDC7B6"
                                textColor: textPrimary
                                spinnerColor: textPrimary
                                spinnerSecondaryColor: isDark ? "#A0F7EFE7" : "#886B5649"
                                spinnerHaloColor: isDark ? "#24FFFFFF" : "#186B5649"
                                minHeight: 36
                                horizontalPadding: 18
                                onClicked: {
                                    if (root.currentScope === "memory")
                                        memoryService.refreshMemoryCategories()
                                    else
                                        root.applyExperienceFilters()
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    visible: root.noticeText !== ""
                    implicitHeight: noticeRow.implicitHeight + 18
                    radius: 18
                    color: root.noticeSuccess ? (isDark ? "#142317" : "#ECF8EF") : (isDark ? "#2A1513" : "#FFF1EE")
                    border.width: 1
                    border.color: root.noticeSuccess ? (isDark ? "#235D36" : "#AED9B6") : (isDark ? "#6B2A22" : "#F0B2A8")

                    RowLayout {
                        id: noticeRow
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 10

                        Rectangle {
                            implicitWidth: 8
                            implicitHeight: 8
                            radius: 4
                            color: root.noticeSuccess ? statusSuccess : statusError
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.noticeText
                            color: textPrimary
                            font.pixelSize: typeLabel
                            wrapMode: Text.WordWrap
                        }

                        IconCircleButton {
                            buttonSize: 28
                            glyphText: "✕"
                            glyphSize: typeCaption
                            fillColor: "transparent"
                            hoverFillColor: bgCardHover
                            outlineColor: borderSubtle
                            glyphColor: textSecondary
                            onClicked: root.noticeText = ""
                        }
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

                    Rectangle {
                        SplitView.preferredWidth: 420
                        SplitView.minimumWidth: 320
                        SplitView.maximumWidth: 520
                        SplitView.fillHeight: true
                        radius: 24
                        color: "transparent"
                        border.width: 0

                        Loader {
                            anchors.fill: parent
                            anchors.margins: 14
                            active: true
                            sourceComponent: root.currentScope === "memory" ? memoryBrowserComponent : experienceBrowserComponent
                        }
                    }

                    Rectangle {
                        SplitView.preferredWidth: 520
                        SplitView.minimumWidth: 420
                        SplitView.fillWidth: true
                        SplitView.fillHeight: true
                        radius: 24
                        color: "transparent"
                        border.width: 0

                        Loader {
                            anchors.fill: parent
                            anchors.margins: 14
                            active: true
                            sourceComponent: root.currentScope === "memory" ? memoryDetailComponent : experienceDetailComponent
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            color: isDark ? "#7A0E0B09" : "#60FCF8F4"
            visible: root.hasMemoryService && memoryService.blockingBusy

            LoadingOrbit {
                anchors.centerIn: parent
                width: 42
                height: 42
                running: parent.visible
                color: accent
                secondaryColor: accentHover
                haloColor: accentGlow
                haloOpacity: 0.18
                showCore: false
            }
        }
    }

    Component {
        id: memoryBrowserComponent

        ColumnLayout {
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: root.tr("选择分类", "Choose a category")
                    color: textPrimary
                    font.pixelSize: typeLabel
                    font.weight: weightBold
                }

                Text {
                    text: root.tr("先选分类，再在右侧查看和编辑。", "Pick a category first, then review and edit on the right.")
                    color: textSecondary
                    font.pixelSize: typeMeta
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 40
                radius: 16
                color: memorySearchField.activeFocus ? bgInputFocus : (memorySearchField.hovered ? bgInputHover : bgInput)
                border.width: memorySearchField.activeFocus ? 1.5 : 1
                border.color: memorySearchField.activeFocus ? borderFocus : borderSubtle

                Image {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: 16
                    height: 16
                    source: root.searchIconSource
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    opacity: 0.75
                }

                TextField {
                    id: memorySearchField
                    property bool baoClickAwayEditor: true
                    anchors.fill: parent
                    leftPadding: 36
                    rightPadding: 12
                    background: null
                    color: textPrimary
                    text: root.memorySearchQuery
                    placeholderText: root.tr("搜索分类或记忆内容…", "Search categories or memory text…")
                    placeholderTextColor: textPlaceholder
                    selectionColor: textSelectionBg
                    selectedTextColor: textSelectionFg
                    font.pixelSize: typeLabel
                    onTextChanged: if (root.memorySearchQuery !== text) root.memorySearchQuery = text
                }
            }

            Flow {
                Layout.fillWidth: true
                width: parent.width
                spacing: 8

                Repeater {
                    model: ["preference", "personal", "project", "general"]

                    delegate: PillActionButton {
                        required property var modelData
                        text: modelData === "preference" ? root.tr("偏好", "Preference")
                              : modelData === "personal" ? root.tr("个人", "Personal")
                              : modelData === "project" ? root.tr("项目", "Project")
                              : root.tr("通用", "General")
                        outlined: true
                        fillColor: String(root.selectedMemoryCategory.category || "") === modelData ? accentMuted : "transparent"
                        hoverFillColor: String(root.selectedMemoryCategory.category || "") === modelData ? accentMuted : bgCardHover
                        outlineColor: String(root.selectedMemoryCategory.category || "") === modelData ? accent : borderSubtle
                        textColor: textPrimary
                        onClicked: root.selectMemory(modelData)
                    }
                }
            }

                Text {
                    Layout.fillWidth: true
                    text: root.tr(
                              "已使用分类 " + Number(root.memoryStats.used_categories || 0) + "/" + Number(root.memoryStats.total_categories || 0)
                              + " · 事实 " + Number(root.memoryStats.total_facts || 0) + " 条",
                              "Used categories " + Number(root.memoryStats.used_categories || 0) + "/" + Number(root.memoryStats.total_categories || 0)
                              + " · " + Number(root.memoryStats.total_facts || 0) + " facts"
                          )
                    color: textSecondary
                    font.pixelSize: typeMeta
                }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "transparent"
                border.width: 0

                Loader {
                    anchors.fill: parent
                    active: true
                    sourceComponent: memoryListComponent
                }
            }
        }
    }

    Component {
        id: experienceBrowserComponent

        ColumnLayout {
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: root.tr("选择经验", "Choose an experience")
                    color: textPrimary
                    font.pixelSize: typeLabel
                    font.weight: weightBold
                }

                Text {
                    text: root.tr("筛选你关心的经验，再在右侧决定是否保留。", "Filter the experiences you care about, then decide what to keep on the right.")
                    color: textSecondary
                    font.pixelSize: typeMeta
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 40
                radius: 16
                color: experienceSearchField.activeFocus ? bgInputFocus : (experienceSearchField.hovered ? bgInputHover : bgInput)
                border.width: experienceSearchField.activeFocus ? 1.5 : 1
                border.color: experienceSearchField.activeFocus ? borderFocus : borderSubtle

                Image {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: 16
                    height: 16
                    source: root.searchIconSource
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    opacity: 0.75
                }

                TextField {
                    id: experienceSearchField
                    property bool baoClickAwayEditor: true
                    anchors.fill: parent
                    leftPadding: 36
                    rightPadding: 12
                    background: null
                    color: textPrimary
                    text: root.experienceSearchQuery
                    placeholderText: root.tr("搜索任务、经验、关键词…", "Search tasks, lessons, keywords…")
                    placeholderTextColor: textPlaceholder
                    selectionColor: textSelectionBg
                    selectedTextColor: textSelectionFg
                    font.pixelSize: typeLabel
                    onTextChanged: {
                        if (root.experienceSearchQuery !== text)
                            root.experienceSearchQuery = text
                        root.applyExperienceFilters()
                    }
                }
            }

            Flow {
                Layout.fillWidth: true
                width: parent.width
                spacing: 8

                Repeater {
                    model: ["active", "high_quality", "deprecated", "all"]

                    delegate: PillActionButton {
                        required property var modelData
                        text: modelData === "active" ? root.tr("活跃", "Active")
                              : modelData === "high_quality" ? root.tr("高质量", "High quality")
                              : modelData === "deprecated" ? root.tr("已停用", "Deprecated")
                              : root.tr("全部", "All")
                        outlined: true
                        fillColor: {
                            if (modelData === "active")
                                return root.experienceDeprecatedMode === "active" && root.experienceMinQuality === 0 ? accentMuted : "transparent"
                            if (modelData === "high_quality")
                                return root.experienceDeprecatedMode === "active" && root.experienceMinQuality === 4 ? accentMuted : "transparent"
                            if (modelData === "deprecated")
                                return root.experienceDeprecatedMode === "deprecated" ? accentMuted : "transparent"
                            return root.experienceDeprecatedMode === "all" ? accentMuted : "transparent"
                        }
                        hoverFillColor: bgCardHover
                        outlineColor: fillColor === "transparent" ? borderSubtle : accent
                        textColor: textPrimary
                        onClicked: {
                            if (modelData === "active") {
                                root.experienceDeprecatedMode = "active"
                                root.experienceMinQuality = 0
                            } else if (modelData === "high_quality") {
                                root.experienceDeprecatedMode = "active"
                                root.experienceMinQuality = 4
                            } else if (modelData === "deprecated") {
                                root.experienceDeprecatedMode = "deprecated"
                                root.experienceMinQuality = 0
                            } else {
                                root.experienceDeprecatedMode = "all"
                                root.experienceMinQuality = 0
                            }
                            root.applyExperienceFilters()
                        }
                    }
                }
            }

            Flow {
                Layout.fillWidth: true
                width: parent.width
                spacing: 8

                Repeater {
                    model: ["updated_desc", "quality_desc", "uses_desc"]

                    delegate: PillActionButton {
                        required property var modelData
                        text: modelData === "quality_desc" ? root.tr("按质量", "By quality")
                              : modelData === "uses_desc" ? root.tr("按复用", "By reuse")
                              : root.tr("最近更新", "Recent")
                        minHeight: 30
                        horizontalPadding: 14
                        outlined: true
                        fillColor: root.experienceSortBy === modelData ? accentMuted : "transparent"
                        hoverFillColor: root.experienceSortBy === modelData ? accentMuted : bgCardHover
                        outlineColor: root.experienceSortBy === modelData ? accent : borderSubtle
                        textColor: textPrimary
                        onClicked: {
                            root.experienceSortBy = modelData
                            root.applyExperienceFilters()
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.tr("结果数 ", "Results ") + (root.hasMemoryService ? (memoryService.experienceItems || []).length : 0)
                color: textSecondary
                font.pixelSize: typeMeta
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "transparent"
                border.width: 0

                Loader {
                    anchors.fill: parent
                    active: true
                    sourceComponent: experienceListComponent
                }
            }
        }
    }

    Component {
        id: memoryListComponent

        Item {
            ListView {
                anchors.fill: parent
                model: root.filteredMemoryCategories
                spacing: 10
                clip: true

                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: 136
                    radius: radiusLg
                    color: String(root.selectedMemoryCategory.category || "") === String(modelData.category || "")
                           ? sessionRowActiveBg
                           : (cardMouse.containsMouse ? bgCardHover : (isDark ? "#1A1411" : "#FFFFFF"))
                    border.width: 1
                    border.color: String(root.selectedMemoryCategory.category || "") === String(modelData.category || "") ? accent : borderSubtle
                    scale: String(root.selectedMemoryCategory.category || "") === String(modelData.category || "") ? motionSelectionScaleActive : (cardMouse.containsMouse ? motionSelectionScaleHover : 1.0)

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        color: "transparent"
                        border.width: 0
                        opacity: String(root.selectedMemoryCategory.category || "") === String(modelData.category || "") ? 0.1 : 0.0
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: isDark ? "#18FFD8B0" : "#10FFC58A" }
                            GradientStop { position: 1.0; color: "transparent" }
                        }

                        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                    }

                    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                Layout.fillWidth: true
                                text: {
                                    if (modelData.category === "preference") return tr("偏好", "Preference")
                                    if (modelData.category === "personal") return tr("个人", "Personal")
                                    if (modelData.category === "project") return tr("项目", "Project")
                                    return tr("通用", "General")
                                }
                                color: textPrimary
                                font.pixelSize: typeButton
                                font.weight: weightBold
                            }

                            Rectangle {
                                radius: 10
                                color: isDark ? "#18FFFFFF" : "#12000000"
                                implicitWidth: badgeText.implicitWidth + 12
                                implicitHeight: badgeText.implicitHeight + 6

                                Text {
                                    id: badgeText
                                    anchors.centerIn: parent
                                    text: modelData.is_empty
                                          ? tr("空", "Empty")
                                          : tr(String(modelData.fact_count || 0) + " 条事实", String(modelData.fact_count || 0) + " facts")
                                    color: textSecondary
                                    font.pixelSize: typeCaption
                                    font.weight: weightDemiBold
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.preview || tr("还没有内容，适合在这里保存稳定偏好或项目背景。", "No content yet — use this space for durable preferences or project context.")
                            color: modelData.is_empty ? textSecondary : textPrimary
                            font.pixelSize: typeLabel
                            wrapMode: Text.WordWrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }

                        Item { Layout.fillHeight: true }

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                Layout.fillWidth: true
                                text: modelData.updated_label ? tr("更新于 " + modelData.updated_label, "Updated " + modelData.updated_label) : tr("尚未写入", "Not written yet")
                                color: textSecondary
                                font.pixelSize: typeMeta
                            }

                            IconCircleButton {
                                buttonSize: 28
                                glyphText: "→"
                                glyphSize: typeMeta
                                fillColor: "transparent"
                                hoverFillColor: bgCardHover
                                outlineColor: borderSubtle
                                glyphColor: textSecondary
                                onClicked: root.selectMemory(modelData.category)
                            }
                        }
                    }

                    MouseArea {
                        id: cardMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.selectMemory(modelData.category)
                    }
                }

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }

            Item {
                anchors.fill: parent
                visible: root.filteredMemoryCategories.length === 0

                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 40, 280)
                    spacing: 10

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        implicitWidth: 56
                        implicitHeight: 56
                        radius: 28
                        color: isDark ? "#1D1613" : "#FFF4EA"
                        border.width: 1
                        border.color: borderSubtle

                        Text {
                            anchors.centerIn: parent
                            text: "◌"
                            color: accent
                            font.pixelSize: 24
                            font.weight: weightBold
                        }
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: root.tr("没有匹配的记忆分类", "No matching memory categories")
                        color: textPrimary
                        font.pixelSize: typeButton
                        font.weight: weightBold
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: root.tr("换一个关键词，或者直接在右侧编辑当前分类内容。", "Try another keyword, or edit the current category on the right.")
                        color: textSecondary
                        font.pixelSize: typeLabel
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }

    Component {
        id: experienceListComponent

        Item {
            ListView {
                anchors.fill: parent
                model: hasMemoryService ? (memoryService.experienceItems || []) : []
                spacing: 10
                clip: true

                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: 156
                    radius: radiusLg
                    color: String(root.selectedExperience.key || "") === String(modelData.key || "")
                           ? sessionRowActiveBg
                           : (expMouse.containsMouse ? bgCardHover : (isDark ? "#1A1411" : "#FFFFFF"))
                    border.width: 1
                    border.color: String(root.selectedExperience.key || "") === String(modelData.key || "") ? "#D8A23C" : borderSubtle
                    scale: String(root.selectedExperience.key || "") === String(modelData.key || "") ? motionSelectionScaleActive : (expMouse.containsMouse ? motionSelectionScaleHover : 1.0)

                    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                Layout.fillWidth: true
                                text: modelData.task || tr("未命名经验", "Untitled experience")
                                color: textPrimary
                                font.pixelSize: typeButton
                                font.weight: weightBold
                                elide: Text.ElideRight
                            }

                            Rectangle {
                                radius: 10
                                color: modelData.deprecated ? (isDark ? "#24F05A5A" : "#14F05A5A") : (isDark ? "#1CFFFFFF" : "#12000000")
                                implicitWidth: stateBadge.implicitWidth + 12
                                implicitHeight: stateBadge.implicitHeight + 6

                                Text {
                                    id: stateBadge
                                    anchors.centerIn: parent
                                    text: modelData.deprecated ? tr("已停用", "Deprecated") : (modelData.outcome || tr("成功", "success"))
                                    color: modelData.deprecated ? statusError : textSecondary
                                    font.pixelSize: typeCaption
                                    font.weight: weightDemiBold
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.preview || modelData.lessons || ""
                            color: textPrimary
                            font.pixelSize: typeLabel
                            wrapMode: Text.WordWrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Rectangle {
                                radius: 9
                                color: isDark ? "#18FFFFFF" : "#12000000"
                                implicitWidth: qualityText.implicitWidth + 12
                                implicitHeight: qualityText.implicitHeight + 6

                                Text {
                                    id: qualityText
                                    anchors.centerIn: parent
                                    text: tr("质量 " + Number(modelData.quality || 0), "Q " + Number(modelData.quality || 0))
                                    color: textSecondary
                                    font.pixelSize: typeCaption
                                    font.weight: weightDemiBold
                                }
                            }

                            Rectangle {
                                radius: 9
                                color: isDark ? "#18FFFFFF" : "#12000000"
                                implicitWidth: reuseText.implicitWidth + 12
                                implicitHeight: reuseText.implicitHeight + 6

                                Text {
                                    id: reuseText
                                    anchors.centerIn: parent
                                    text: tr("复用 " + Number(modelData.uses || 0), "Reuse " + Number(modelData.uses || 0))
                                    color: textSecondary
                                    font.pixelSize: typeCaption
                                    font.weight: weightDemiBold
                                }
                            }

                            Item { Layout.fillWidth: true }

                            Text {
                                text: modelData.updated_label || ""
                                color: textSecondary
                                font.pixelSize: typeMeta
                            }
                        }
                    }

                    MouseArea {
                        id: expMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: memoryService.selectExperience(modelData.key)
                    }
                }

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }

            Item {
                anchors.fill: parent
                visible: root.hasMemoryService && (memoryService.experienceItems || []).length === 0

                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 40, 300)
                    spacing: 10

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        implicitWidth: 56
                        implicitHeight: 56
                        radius: 28
                        color: isDark ? "#1D1613" : "#FFF4EA"
                        border.width: 1
                        border.color: borderSubtle

                        Text {
                            anchors.centerIn: parent
                            text: "✦"
                            color: "#D8A23C"
                            font.pixelSize: 24
                            font.weight: weightBold
                        }
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: root.tr("当前筛选下没有经验", "No experiences for this filter")
                        color: textPrimary
                        font.pixelSize: typeButton
                        font.weight: weightBold
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: root.tr("试试放宽筛选，或继续使用 Bao，新的经验会在这里慢慢积累。", "Relax the filters or keep using Bao — new experiences will accumulate here over time.")
                        color: textSecondary
                        font.pixelSize: typeLabel
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }

    Component {
        id: memoryDetailComponent

        Item {
            visible: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 12
                visible: root.hasSelectedMemory()

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Rectangle {
                        implicitWidth: 34
                        implicitHeight: 34
                        radius: 17
                        color: isDark ? "#1D1713" : "#F3E7DA"
                        border.width: 1
                        border.color: borderSubtle

                        Image {
                            anchors.centerIn: parent
                            width: 18
                            height: 18
                            source: root.detailIconSource
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                            Layout.fillWidth: true
                            text: root.memoryCategoryTitle(selectedMemoryCategory.category)
                            color: textPrimary
                            font.pixelSize: typeTitle - 3
                            font.weight: weightBold
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.memoryCategoryMeta(selectedMemoryCategory)
                            color: textSecondary
                            font.pixelSize: typeMeta
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: radiusLg
                    color: bgInput
                    border.width: 1
                    border.color: editor.activeFocus ? borderFocus : borderSubtle

                    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

                    ScrollView {
                        anchors.fill: parent
                        clip: true

                        TextArea {
                            id: editor
                            text: root.editorText
                            color: textPrimary
                            placeholderText: tr("把值得长期保留的内容写在这里。每一行都会被视为一个稳定记忆片段。", "Write durable information here. Each line is treated as a stable memory fragment.")
                            placeholderTextColor: textPlaceholder
                            wrapMode: TextArea.Wrap
                            selectByMouse: true
                            selectionColor: textSelectionBg
                            selectedTextColor: textSelectionFg
                            background: null
                            padding: 14
                            onTextChanged: {
                                root.editorText = text
                                root.editorDirty = text !== String(selectedMemoryCategory.content || "")
                            }
                        }
                    }
                }

                        Text {
                            text: tr("补充一条记忆", "Add one memory")
                            color: textSecondary
                            font.pixelSize: typeMeta
                            font.weight: weightBold
                }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 92
                    radius: radiusMd
                    color: bgBase
                    border.width: 1
                    border.color: borderSubtle

                    TextArea {
                        id: appendEditor
                        anchors.fill: parent
                        text: root.appendText
                        color: textPrimary
                        placeholderText: tr("写下要补充到当前分类的一条记忆", "Write one memory to add to this category")
                        placeholderTextColor: textPlaceholder
                        wrapMode: TextArea.Wrap
                        selectByMouse: true
                        selectionColor: textSelectionBg
                        selectedTextColor: textSelectionFg
                        background: null
                        padding: 12
                        onTextChanged: root.appendText = text
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    AsyncActionButton {
                        Layout.fillWidth: true
                        text: tr("保存当前分类", "Save current category")
                        busy: hasMemoryService && memoryService.blockingBusy
                        iconSource: root.saveIconSource
                        fillColor: isDark ? "#2A1B11" : "#E7D5C7"
                        hoverFillColor: isDark ? "#342116" : "#DDC7B6"
                        textColor: textPrimary
                        spinnerColor: textPrimary
                        spinnerSecondaryColor: isDark ? "#A0F7EFE7" : "#886B5649"
                        spinnerHaloColor: isDark ? "#24FFFFFF" : "#186B5649"
                        buttonEnabled: root.canMutate && !!selectedMemoryCategory.category
                        minHeight: 36
                        onClicked: memoryService.saveMemoryCategory(selectedMemoryCategory.category, root.editorText)
                    }

                    Flow {
                        Layout.fillWidth: true
                        width: parent.width
                        spacing: 8

                        PillActionButton {
                            text: tr("加入到当前分类", "Add to this category")
                            iconSource: root.appendIconSource
                            buttonEnabled: root.canMutate
                                           && !!selectedMemoryCategory.category
                                           && root.appendText.trim().length > 0
                            onClicked: memoryService.appendMemoryCategory(selectedMemoryCategory.category, root.appendText)
                        }

                        PillActionButton {
                            text: tr("清空当前分类", "Clear")
                            iconSource: root.removeIconSource
                            outlined: true
                            fillColor: "transparent"
                            hoverFillColor: isDark ? "#2A1614" : "#FFF1EE"
                            outlineColor: statusError
                            textColor: statusError
                            buttonEnabled: root.canMutate
                                           && !!selectedMemoryCategory.category
                                           && String(selectedMemoryCategory.content || "").trim().length > 0
                            onClicked: root.openDestructiveModal("clearMemory", "", selectedMemoryCategory.category)
                        }
                    }
                }
            }

            Item {
                anchors.fill: parent
                visible: !root.hasSelectedMemory()

                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 48, 300)
                    spacing: 12

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        implicitWidth: 60
                        implicitHeight: 60
                        radius: 30
                        color: isDark ? "#1B1512" : "#FFF5EB"
                        border.width: 1
                        border.color: borderSubtle

                        Text {
                            anchors.centerIn: parent
                            text: "▣"
                            color: accent
                            font.pixelSize: 22
                            font.weight: weightBold
                        }
                    }

                    Text {
                        width: parent.width
                        text: root.tr("选择一个分类开始管理", "Choose a category to manage")
                        color: textPrimary
                        font.pixelSize: typeButton + 1
                        font.weight: weightBold
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: root.tr("长期记忆适合存放稳定偏好、项目上下文和值得长期保留的做法。", "Long-term memory is ideal for stable preferences, project context, and durable practices.")
                        color: textSecondary
                        font.pixelSize: typeLabel
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }

    Component {
        id: experienceDetailComponent

        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 12
                visible: root.hasSelectedExperience()

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Rectangle {
                        implicitWidth: 34
                        implicitHeight: 34
                        radius: 17
                        color: isDark ? "#1D1713" : "#F3E7DA"
                        border.width: 1
                        border.color: borderSubtle

                        Image {
                            anchors.centerIn: parent
                            width: 18
                            height: 18
                            source: root.experienceIconSource
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: selectedExperience.task || tr("选择一条经验", "Choose an experience")
                        color: textPrimary
                        font.pixelSize: typeTitle - 3
                        font.weight: weightBold
                        wrapMode: Text.WordWrap
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Rectangle {
                        radius: 10
                        color: selectedExperience.deprecated ? (isDark ? "#24F05A5A" : "#14F05A5A") : (isDark ? "#18FFFFFF" : "#12000000")
                        implicitWidth: outcomeText.implicitWidth + 12
                        implicitHeight: outcomeText.implicitHeight + 6

                        Text {
                            id: outcomeText
                            anchors.centerIn: parent
                            text: selectedExperience.deprecated ? tr("已停用", "Deprecated") : (selectedExperience.outcome || tr("成功", "Success"))
                            color: selectedExperience.deprecated ? statusError : textSecondary
                            font.pixelSize: typeCaption
                            font.weight: weightDemiBold
                        }
                    }

                    Rectangle {
                        radius: 10
                        color: isDark ? "#18FFFFFF" : "#12000000"
                        implicitWidth: qualityMeta.implicitWidth + 12
                        implicitHeight: qualityMeta.implicitHeight + 6

                        Text {
                            id: qualityMeta
                            anchors.centerIn: parent
                            text: tr("质量 " + Number(selectedExperience.quality || 0), "Q " + Number(selectedExperience.quality || 0))
                            color: textSecondary
                            font.pixelSize: typeCaption
                            font.weight: weightDemiBold
                        }
                    }

                    Rectangle {
                        radius: 10
                        color: isDark ? "#18FFFFFF" : "#12000000"
                        implicitWidth: successMeta.implicitWidth + 12
                        implicitHeight: successMeta.implicitHeight + 6

                        Text {
                            id: successMeta
                            anchors.centerIn: parent
                            text: tr("成功率 " + Number(selectedExperience.success_rate || 0) + "%", "Rate " + Number(selectedExperience.success_rate || 0) + "%")
                            color: textSecondary
                            font.pixelSize: typeCaption
                            font.weight: weightDemiBold
                        }
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth

                    Column {
                        width: parent.width
                        spacing: 16

                        Text {
                            width: parent.width
                            text: tr("经验内容", "Lesson")
                            color: textSecondary
                            font.pixelSize: typeMeta
                            font.weight: weightBold
                        }

                        Text {
                            width: parent.width
                            text: selectedExperience.lessons || tr("暂无详细内容", "No lesson text")
                            color: textPrimary
                            wrapMode: Text.WordWrap
                            font.pixelSize: typeBody
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: borderSubtle
                            opacity: 0.9
                        }

                        Text {
                            width: parent.width
                            text: tr("判断信息", "Signals")
                            color: textSecondary
                            font.pixelSize: typeMeta
                            font.weight: weightBold
                        }

                        Column {
                            width: parent.width
                            spacing: 8

                            Text { text: tr("分类：", "Category: ") + String(selectedExperience.category || tr("无", "none")); color: textPrimary; font.pixelSize: typeLabel }
                            Text { text: tr("复用次数：", "Reuse: ") + Number(selectedExperience.uses || 0); color: textPrimary; font.pixelSize: typeLabel }
                            Text { text: tr("成功次数：", "Successes: ") + Number(selectedExperience.successes || 0); color: textPrimary; font.pixelSize: typeLabel }
                            Text { text: tr("最近更新：", "Updated: ") + String(selectedExperience.updated_label || tr("无", "none")); color: textPrimary; font.pixelSize: typeLabel }
                            Text { visible: !!selectedExperience.keywords; text: tr("关键词：", "Keywords: ") + String(selectedExperience.keywords || ""); color: textPrimary; font.pixelSize: typeLabel; wrapMode: Text.WordWrap; width: parent.width }
                            Text { visible: !!selectedExperience.trace; text: tr("轨迹：", "Trace: ") + String(selectedExperience.trace || ""); color: textSecondary; font.pixelSize: typeMeta; wrapMode: Text.WordWrap; width: parent.width }
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: borderSubtle
                            opacity: 0.9
                        }

                        Text {
                            width: parent.width
                            text: tr("提升为长期记忆", "Promote to memory")
                            color: textSecondary
                            font.pixelSize: typeMeta
                            font.weight: weightBold
                        }

                        Flow {
                            id: promoteRow
                            width: parent.width
                            spacing: 8

                            Repeater {
                                model: ["preference", "personal", "project", "general"]

                                delegate: PillActionButton {
                                    required property var modelData
                                    text: modelData === "preference" ? tr("偏好", "Preference")
                                          : modelData === "personal" ? tr("个人", "Personal")
                                          : modelData === "project" ? tr("项目", "Project")
                                          : tr("通用", "General")
                                    fillColor: root.promoteCategory === modelData ? accentMuted : "transparent"
                                    hoverFillColor: root.promoteCategory === modelData ? accentMuted : bgCardHover
                                    outlineColor: root.promoteCategory === modelData ? accent : borderSubtle
                                    textColor: textPrimary
                                    outlined: true
                                    onClicked: root.promoteCategory = modelData
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    AsyncActionButton {
                        Layout.fillWidth: true
                        text: tr("提升为长期记忆", "Promote to memory")
                        busy: hasMemoryService && memoryService.blockingBusy
                        iconSource: root.saveIconSource
                        fillColor: isDark ? "#2A1B11" : "#E7D5C7"
                        hoverFillColor: isDark ? "#342116" : "#DDC7B6"
                        textColor: textPrimary
                        spinnerColor: textPrimary
                        spinnerSecondaryColor: isDark ? "#A0F7EFE7" : "#886B5649"
                        spinnerHaloColor: isDark ? "#24FFFFFF" : "#186B5649"
                        buttonEnabled: root.canMutate && !!selectedExperience.key
                        minHeight: 36
                        onClicked: memoryService.promoteExperienceToMemory(selectedExperience.key, root.promoteCategory)
                    }

                    Flow {
                        Layout.fillWidth: true
                        width: parent.width
                        spacing: 8

                        PillActionButton {
                            text: selectedExperience.deprecated ? tr("恢复启用", "Restore") : tr("停用这条经验", "Deprecate")
                            iconSource: root.deprecateIconSource
                            buttonEnabled: root.canMutate && !!selectedExperience.key
                            outlined: true
                            fillColor: "transparent"
                            hoverFillColor: bgCardHover
                            outlineColor: selectedExperience.deprecated ? accent : statusError
                            textColor: selectedExperience.deprecated ? accent : statusError
                            onClicked: memoryService.setExperienceDeprecated(selectedExperience.key, !selectedExperience.deprecated)
                        }

                        PillActionButton {
                            text: tr("删除这条经验", "Delete")
                            iconSource: root.removeIconSource
                            outlined: true
                            fillColor: "transparent"
                            hoverFillColor: isDark ? "#2A1614" : "#FFF1EE"
                            outlineColor: statusError
                            textColor: statusError
                            buttonEnabled: root.canMutate && !!selectedExperience.key
                            onClicked: root.openDestructiveModal("deleteExperience", selectedExperience.key, "")
                        }
                    }
                }
            }

            Item {
                anchors.fill: parent
                visible: !root.hasSelectedExperience()

                Column {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 48, 320)
                    spacing: 12

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        implicitWidth: 60
                        implicitHeight: 60
                        radius: 30
                        color: isDark ? "#1B1512" : "#FFF5EB"
                        border.width: 1
                        border.color: borderSubtle

                        Text {
                            anchors.centerIn: parent
                            text: "✦"
                            color: "#D8A23C"
                            font.pixelSize: 24
                            font.weight: weightBold
                        }
                    }

                    Text {
                        width: parent.width
                        text: root.tr("选择一条经验查看细节", "Choose an experience to inspect")
                        color: textPrimary
                        font.pixelSize: typeButton + 1
                        font.weight: weightBold
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        text: root.tr("你可以在这里停用噪音经验、删除失效经验，或把高价值经验提升为长期记忆。", "From here you can deprecate noisy experiences, delete stale ones, or promote high-value ones into long-term memory.")
                        color: textSecondary
                        font.pixelSize: typeLabel
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }

    AppModal {
        id: destructiveModal
        title: destructiveAction === "clearMemory"
               ? tr("清空该类记忆？", "Clear this memory category?")
               : tr("删除这条经验？", "Delete this experience?")
        closeText: tr("取消", "Cancel")
        showDefaultCloseAction: true
        maxModalWidth: 460
        maxModalHeight: 280

        Text {
            width: parent.width
            text: destructiveAction === "clearMemory"
                  ? tr("这会清空当前分类下的聚合记忆内容，但不会影响其他分类。", "This clears the aggregated content in the current category without touching other categories.")
                  : tr("删除后这条经验将不再出现在经验工作台中。", "After deletion, this experience will no longer appear in the experience workspace.")
            color: textPrimary
            wrapMode: Text.WordWrap
            font.pixelSize: typeBody
        }

        footer: [
            PillActionButton {
                text: root.tr("确认", "Confirm")
                onClicked: root.confirmDestructiveAction()
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
