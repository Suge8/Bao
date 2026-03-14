import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root

    property var chatService: null
    property var sessionService: null
    property string activeSessionKey: ""
    property bool showSelection: true
    property bool gatewayIdle: {
        if (!hasChatService)
            return true
        if (typeof chatService.gatewayState === "string" && chatService.gatewayState !== "")
            return chatService.gatewayState === "idle"
        if (typeof chatService.state === "string" && chatService.state !== "")
            return chatService.state === "idle"
        return true
    }
    property bool projectionMotionEnabled: false
    property real activeHighlightX: 0.0
    property real activeHighlightY: 0.0
    property real activeHighlightWidth: 0.0
    property real activeHighlightHeight: 0.0
    property real activeHighlightOpacity: 0.0

    readonly property bool hasChatService: chatService !== null
    readonly property bool hasSessionService: sessionService !== null

    signal newSessionRequested()
    signal sessionSelected(string key)
    signal sessionDeleteRequested(string key)

    function requestNewSession() {
        root.newSessionRequested()
    }

    function finishProjectionMotion() {
        root.projectionMotionEnabled = false
        root.updateActiveHighlight()
    }

    function syncViewportHighlight(clampContentY) {
        if (clampContentY && sessionList)
            sessionList.contentY = root.clampListContentY(sessionList.contentY)
        if (!root.projectionMotionEnabled)
            root.updateActiveHighlight()
    }

    function findActiveSessionDelegate() {
        if (!sessionList || !sessionList.contentItem)
            return null
        var children = sessionList.contentItem.children
        for (var i = 0; i < children.length; i++) {
            var child = children[i]
            if (!child || child.anchorReady !== true)
                continue
            if (child.anchorIsHeader)
                continue
            if ((child.anchorKey || "") !== root.activeSessionKey)
                continue
            return child
        }
        return null
    }

    function updateActiveHighlight() {
        var target = root.findActiveSessionDelegate()
        if (!target) {
            root.activeHighlightOpacity = 0.0
            return
        }
        root.activeHighlightX = target.highlightContentX
        root.activeHighlightY = target.highlightContentY - sessionList.contentY
        root.activeHighlightWidth = target.highlightContentWidth
        root.activeHighlightHeight = target.highlightContentHeight
        root.activeHighlightOpacity = root.showSelection ? 1.0 : 0.0
    }

    function channelVisualSource(channel, filled) {
        switch (channel) {
        case "telegram":
            return "../resources/icons/channel-telegram.svg"
        case "discord":
            return "../resources/icons/channel-discord.svg"
        case "whatsapp":
            return "../resources/icons/channel-whatsapp.svg"
        case "feishu":
            return "../resources/icons/channel-feishu.svg"
        case "slack":
            return "../resources/icons/channel-slack.svg"
        case "qq":
            return "../resources/icons/channel-qq.svg"
        case "dingtalk":
            return "../resources/icons/channel-dingtalk.svg"
        case "imessage":
            return "../resources/icons/channel-imessage.svg"
        case "desktop":
            if (filled)
                return isDark
                       ? "../resources/icons/sidebar-monitor-solid-dark.svg"
                       : "../resources/icons/sidebar-monitor-solid.svg"
            return isDark ? "../resources/icons/sidebar-monitor-dark.svg" : "../resources/icons/sidebar-monitor.svg"
        case "subagent":
            return filled ? "../resources/icons/sidebar-subagent-solid.svg" : "../resources/icons/sidebar-subagent.svg"
        case "system":
            return filled ? "../resources/icons/sidebar-system-solid.svg" : "../resources/icons/sidebar-system.svg"
        case "heartbeat":
            return filled ? "../resources/icons/sidebar-heartbeat-solid.svg" : "../resources/icons/sidebar-heartbeat.svg"
        case "cron":
            return filled ? "../resources/icons/sidebar-cron-solid.svg" : "../resources/icons/sidebar-cron.svg"
        case "email":
            return filled ? "../resources/icons/sidebar-mail-solid.svg" : "../resources/icons/sidebar-mail.svg"
        default:
            return filled ? "../resources/icons/sidebar-chat-solid.svg" : "../resources/icons/sidebar-chat.svg"
        }
    }

    function channelIconSource(channel) {
        return channelVisualSource(channel, false)
    }

    function channelFilledIconSource(channel) {
        return channelVisualSource(channel, true)
    }

    function channelUsesTint(channel) {
        switch (channel) {
        case "telegram":
        case "discord":
        case "whatsapp":
        case "feishu":
        case "slack":
        case "qq":
        case "dingtalk":
        case "imessage":
            return true
        default:
            return false
        }
    }

    function channelAccent(channel) {
        switch (channel) {
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
        case "desktop":
            return isDark ? Qt.rgba(1.0, 0.78, 0.29, 1.0) : Qt.rgba(0.97, 0.63, 0.05, 1.0)
        case "subagent":
            return isDark ? Qt.rgba(1.0, 0.72, 0.24, 1.0) : Qt.rgba(0.96, 0.57, 0.00, 1.0)
        case "system":
            return isDark ? Qt.rgba(0.53, 0.82, 1.0, 1.0) : Qt.rgba(0.18, 0.67, 0.98, 1.0)
        case "heartbeat":
            return isDark ? Qt.rgba(0.20, 0.90, 0.56, 1.0) : Qt.rgba(0.00, 0.82, 0.40, 1.0)
        case "cron":
            return isDark ? Qt.rgba(1.0, 0.66, 0.18, 1.0) : Qt.rgba(0.99, 0.58, 0.00, 1.0)
        case "email":
            return isDark ? Qt.rgba(0.46, 0.69, 1.0, 1.0) : Qt.rgba(0.16, 0.56, 0.95, 1.0)
        default:
            return isDark ? Qt.rgba(0.79, 0.55, 1.0, 1.0) : Qt.rgba(0.52, 0.27, 0.84, 1.0)
        }
    }

    function listContentYBounds() {
        var minY = sessionList ? sessionList.originY : 0
        var maxY = minY
        if (sessionList)
            maxY = minY + Math.max(0, sessionList.contentHeight - sessionList.height)
        return { minY: minY, maxY: maxY }
    }

    function clampListContentY(y) {
        var bounds = root.listContentYBounds()
        return Math.max(bounds.minY, Math.min(y, bounds.maxY))
    }

    function visibleDelegates() {
        if (!sessionList || !sessionList.contentItem)
            return []
        var delegates = []
        var children = sessionList.contentItem.children
        var minY = sessionList.contentY - sizeSidebarHeader
        var maxY = sessionList.contentY + sessionList.height + sizeSidebarHeader
        for (var i = 0; i < children.length; i++) {
            var child = children[i]
            if (!child || child.anchorReady !== true)
                continue
            var childTop = child.y
            var childBottom = child.y + child.height
            if (childBottom < minY || childTop > maxY)
                continue
            delegates.push(child)
        }
        delegates.sort(function(a, b) { return a.y - b.y })
        return delegates
    }

    function findVisibleAnchorDelegate(targetY) {
        var delegates = root.visibleDelegates()
        for (var i = 0; i < delegates.length; i++) {
            var delegate = delegates[i]
            if (delegate.height <= 0)
                continue
            if (delegate.y + delegate.height > targetY)
                return delegate
        }
        return null
    }

    function findVisibleDelegateByAnchor(anchor) {
        if (!anchor)
            return null
        var delegates = root.visibleDelegates()
        for (var i = 0; i < delegates.length; i++) {
            var delegate = delegates[i]
            if (anchor.isHeader) {
                if (delegate.anchorIsHeader && delegate.anchorChannel === anchor.channel)
                    return delegate
                continue
            }
            if (!delegate.anchorIsHeader && delegate.anchorKey === anchor.key)
                return delegate
        }
        return null
    }

    function captureScrollAnchor() {
        if (!sessionList || sessionList.count === 0)
            return { contentY: sessionList ? sessionList.contentY : 0, key: "", channel: "", isHeader: false, offset: 0 }
        var targetY = sessionList.contentY
        var anchorDelegate = root.findVisibleAnchorDelegate(targetY)
        if (anchorDelegate) {
            if (!anchorDelegate.anchorIsHeader && anchorDelegate.anchorKey === (root.activeSessionKey || ""))
                return { contentY: targetY, key: "", channel: "", isHeader: false, offset: 0 }
            return {
                contentY: targetY,
                key: anchorDelegate.anchorIsHeader ? "" : (anchorDelegate.anchorKey || ""),
                channel: anchorDelegate.anchorChannel || "",
                isHeader: anchorDelegate.anchorIsHeader === true,
                offset: targetY - anchorDelegate.y,
            }
        }
        return { contentY: targetY, key: "", channel: "", isHeader: false, offset: 0 }
    }

    function restoreScrollAnchor(anchor) {
        if (!sessionList)
            return
        var targetY = anchor && anchor.contentY !== undefined ? anchor.contentY : sessionList.contentY
        var anchorDelegate = root.findVisibleDelegateByAnchor(anchor)
        if (anchorDelegate)
            targetY = anchorDelegate.y + (anchor.offset || 0)
        sessionList.contentY = root.clampListContentY(targetY)
    }

    function toggleGroup(channel) {
        if (!hasSessionService)
            return
        root.projectionMotionEnabled = true
        projectionMotionSettler.restart()
        sessionService.toggleSidebarGroup(channel)
    }

    Connections {
        target: hasSessionService ? sessionService : null
        property var pendingAnchor: null

        function onSidebarProjectionWillChange() {
            if (root.projectionMotionEnabled) {
                pendingAnchor = null
                return
            }
            pendingAnchor = root.captureScrollAnchor()
        }

        function onSidebarProjectionChanged() {
            if (root.projectionMotionEnabled)
                return
            if (!pendingAnchor) {
                root.finishProjectionMotion()
                return
            }
            var anchor = pendingAnchor
            pendingAnchor = null
            sessionList.forceLayout()
            root.restoreScrollAnchor(anchor)
            root.finishProjectionMotion()
        }
    }

    Component.onCompleted: {
        Qt.callLater(function() {
            root.updateActiveHighlight()
        })
    }

    onActiveSessionKeyChanged: Qt.callLater(function() { root.updateActiveHighlight() })
    onShowSelectionChanged: root.updateActiveHighlight()

    Rectangle {
        anchors.fill: parent
        radius: 28
        color: sidebarListPanelBg
        border.width: 1
        border.color: sidebarListPanelBorder

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: sidebarListPanelOverlay
            opacity: 0.9
        }
    }

    Item {
        id: sessionsHeaderBar
        objectName: "sessionsHeaderBar"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 16
        anchors.rightMargin: 14
        anchors.topMargin: 12
        height: 34

        Item {
            anchors.left: parent.left
            anchors.right: newSessionButton.left
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            height: parent.height

            Row {
                id: sessionsHeaderContent
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                AppIcon {
                    objectName: "sidebarSessionsTitleIcon"
                    width: 22
                    height: 22
                    anchors.verticalCenter: parent.verticalCenter
                    y: 1
                    source: themedIconSource("sidebar-sessions-title")
                    sourceSize: Qt.size(22, 22)
                    opacity: 0.98
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: strings.sidebar_sessions
                    color: textPrimary
                    font.pixelSize: typeBody + 2
                    font.weight: weightBold
                    font.letterSpacing: 0.35
                    textFormat: Text.PlainText
                    opacity: 0.96
                }

                UnreadBadge {
                    id: unreadBadge
                    badgeObjectName: "sessionsHeaderUnreadBadge"
                    textObjectName: "sessionsHeaderUnreadText"
                    anchors.verticalCenter: parent.verticalCenter
                    active: hasSessionService && (sessionService.sidebarUnreadCount || 0) > 0
                    count: hasSessionService ? (sessionService.sidebarUnreadCount || 0) : 0
                    mode: "count"
                    fillColor: sidebarHeaderBadgeBg
                    textColor: sidebarHeaderBadgeText
                }
            }
        }

        IconCircleButton {
            id: newSessionButton
            objectName: "newSessionButton"
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            buttonSize: sizeControlHeight - 6
            glyphText: "+"
            glyphSize: 18
            fillColor: isDark ? "#12FFFFFF" : "#16000000"
            hoverFillColor: accent
            outlineColor: newSessionButton.hovered ? accent : "transparent"
            glyphColor: newSessionButton.hovered ? "#FFFFFFFF" : textPrimary
            hoverScale: motionHoverScaleMedium
            onClicked: root.requestNewSession()
        }
    }

    ListView {
        id: sessionList
        objectName: "sidebarSessionList"
        z: 2
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: sessionsHeaderBar.y + sessionsHeaderBar.height + 8
        anchors.bottomMargin: 0
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        boundsMovement: Flickable.StopAtBounds
        model: hasSessionService ? sessionService.sidebarModel : null
        spacing: 0

        onContentHeightChanged: root.syncViewportHighlight(true)
        onHeightChanged: root.syncViewportHighlight(true)
        onContentYChanged: root.syncViewportHighlight(false)

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            width: 4
            background: Item {}
            contentItem: Rectangle {
                implicitWidth: 4
                radius: 2
                color: sidebarScrollbarThumb
                opacity: 0.72
            }
        }

        footer: Item {
            width: sessionList.width
            height: 0
        }

        add: Transition {
            enabled: root.projectionMotionEnabled

            NumberAnimation {
                property: "opacity"
                from: 0.0
                to: 1.0
                duration: motionFast
                easing.type: easeStandard
            }
        }

        remove: Transition {
            enabled: root.projectionMotionEnabled

            NumberAnimation {
                property: "opacity"
                to: 0.0
                duration: motionFast
                easing.type: easeStandard
            }
        }

        addDisplaced: Transition {
            enabled: root.projectionMotionEnabled

            NumberAnimation {
                properties: "y"
                duration: motionUi
                easing.type: easeStandard
            }
        }

        removeDisplaced: Transition {
            enabled: root.projectionMotionEnabled

            NumberAnimation {
                properties: "y"
                duration: motionUi
                easing.type: easeStandard
            }
        }

        delegate: Item {
            z: 2
            property bool anchorReady: true
            property bool anchorIsHeader: model.isHeader === true
            property string anchorKey: model.itemKey || ""
            property string anchorChannel: model.channel || ""
            readonly property real sessionTopGap: model.isFirstInGroup ? sizeSidebarHeaderToRowGap : 0
            readonly property real sessionBottomGap: model.isLastInGroup ? sizeSidebarGroupGap : sizeSidebarGroupInnerGap
            readonly property real highlightContentX: sessionRow.x + inner.x
            readonly property real highlightContentY: y + sessionRow.y
            readonly property real highlightContentWidth: inner.width
            readonly property real highlightContentHeight: inner.height
            width: sessionList.width
            height: model.isHeader
                    ? (sizeSidebarHeader + (!model.expanded ? sizeSidebarGroupGap : 0))
                    : (sizeSessionRow + sessionTopGap + sessionBottomGap)
            opacity: model.isHeader ? 1.0 : (sessionRow.visible ? 1.0 : 0.0)

            SidebarGroupHeader {
                id: groupHeaderCard
                visible: model.isHeader
                anchors { left: parent.left; right: parent.right; top: parent.top }
                height: sizeSidebarHeader
                channel: model.channel || "other"
                expanded: model.expanded ?? false
                itemCount: model.itemCount || 0
                unreadCount: model.groupUnreadCount || 0
                groupHasRunning: model.groupHasRunning ?? false
                iconSource: root.channelIconSource(model.channel)
                chevronObjectName: "sidebarGroupChevronIcon_" + (model.channel || "other")
                unreadBadgeObjectName: "sidebarGroupUnreadBadge_" + (model.channel || "other")
                unreadTextObjectName: "sidebarGroupUnreadText_" + (model.channel || "other")
                onClicked: root.toggleGroup(model.channel)
            }

            Item {
                id: sessionRow
                visible: !model.isHeader
                anchors { left: parent.left; right: parent.right; top: parent.top }
                y: sessionTopGap
                height: sizeSessionRow + sessionBottomGap
                clip: true

                SessionItem {
                    id: inner
                    width: parent.width - 16 - ((model.isChildSession ?? false) ? 12 : 0)
                    x: 8 + ((model.isChildSession ?? false) ? 12 : 0)
                    sessionKey: model.itemKey ?? ""
                    sessionTitle: model.itemTitle ?? model.itemKey ?? ""
                    sessionRelativeTime: model.itemUpdatedText ?? ""
                    filledIconSource: (model.isChildSession ?? false)
                                      ? "../resources/icons/sidebar-subagent.svg"
                                      : root.channelFilledIconSource(model.visualChannel ?? model.channel)
                    iconTintColor: root.channelAccent(model.visualChannel ?? model.channel)
                    useIconTint: (model.isChildSession ?? false)
                                 ? false
                                 : root.channelUsesTint(model.visualChannel ?? model.channel)
                    isRunning: model.isRunning ?? false
                    childIndent: (model.isChildSession ?? false) ? 2 : 0
                    isActive: root.showSelection && sessionKey === root.activeSessionKey
                    useExternalActiveHighlight: true
                    dimmed: root.gatewayIdle
                    hasUnread: model.itemHasUnread ?? false
                    readOnlySession: model.isReadOnly ?? false
                    onSelected: root.sessionSelected(sessionKey)
                    onDeleteRequested: root.sessionDeleteRequested(sessionKey)
                }
            }
        }

        Item {
            id: loadingStateWrap
            objectName: "sidebarLoadingState"
            anchors.top: parent.top
            anchors.topMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(sessionList.width - 20, 216)
            height: loadingStateCard.implicitHeight
            visible: sessionList.count === 0 && hasSessionService && sessionService.sessionsLoading

            Rectangle {
                id: loadingStateCard
                width: parent.width
                implicitHeight: loadingStateContent.implicitHeight + 24
                radius: 18
                color: isDark ? "#18FFFFFF" : "#0B000000"
                border.width: 1
                border.color: isDark ? "#32FFFFFF" : "#26000000"

                Column {
                    id: loadingStateContent
                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: 2
                    width: parent.width - 24
                    spacing: 10

                    Rectangle {
                        width: 46
                        height: 46
                        radius: 23
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: isDark ? "#16FFFFFF" : "#10FFB33D"
                        border.width: 1
                        border.color: isDark ? "#22FFFFFF" : borderSubtle

                        LoadingOrbit {
                            anchors.centerIn: parent
                            width: 28
                            height: 28
                            running: loadingStateWrap.visible
                            haloOpacity: 0.16
                        }
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: strings.sidebar_loading_title
                        color: isDark ? "#FFF1E1" : "#4B2D12"
                        font.pixelSize: typeBody + 1
                        font.weight: weightBold
                        wrapMode: Text.WordWrap
                        lineHeight: 1.12
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: strings.sidebar_loading_hint
                        color: isDark ? "#DCC5A8" : "#74512F"
                        font.pixelSize: typeMeta
                        wrapMode: Text.WordWrap
                        lineHeight: 1.18
                    }
                }
            }
        }

        Item {
            id: emptyStateWrap
            anchors.top: parent.top
            anchors.topMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(sessionList.width - 28, 196)
            height: emptyStateCard.implicitHeight
            visible: sessionList.count === 0 && !(hasSessionService && sessionService.sessionsLoading)

            Rectangle {
                id: emptyStateCard
                objectName: "sidebarEmptyState"
                width: parent.width
                implicitHeight: emptyStateContent.implicitHeight + 24
                radius: 18
                color: emptyStateHover.containsMouse ? (isDark ? "#22FFFFFF" : "#14000000") : (isDark ? "#18FFFFFF" : "#0B000000")
                border.width: 1
                border.color: emptyStateHover.containsMouse ? sessionRowActiveBorder : (isDark ? "#46FFFFFF" : "#26000000")
                scale: emptyStateHover.pressed ? 0.988 : (emptyStateHover.containsMouse ? motionHoverScaleMedium : 1.0)

                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                Column {
                    id: emptyStateContent
                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: 4
                    width: parent.width - 28
                    spacing: 11

                    Item {
                        width: 50
                        height: 50
                        anchors.horizontalCenter: parent.horizontalCenter

                        Rectangle {
                            width: 46
                            height: 46
                            radius: 23
                            anchors.centerIn: parent
                            color: emptyStateHover.containsMouse ? (isDark ? "#18FFFFFF" : "#10000000") : chatEmptyIconBg
                            border.width: 1
                            border.color: emptyStateHover.containsMouse ? sessionRowActiveBorder : (isDark ? "#38FFFFFF" : chatEmptyIconBorder)

                            AppIcon {
                                objectName: "sidebarEmptyChatIcon"
                                width: 18
                                height: 18
                                anchors.centerIn: parent
                                source: themedIconSource("chat")
                                sourceSize: Qt.size(18, 18)
                                opacity: 0.96
                            }
                        }

                        Rectangle {
                            width: 16
                            height: 16
                            radius: 8
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.rightMargin: 4
                            anchors.topMargin: 4
                            color: emptyStateHover.containsMouse ? accent : accentGlow

                            PlusGlyph {
                                glyphSize: 7
                                barThickness: 1.8
                                glyphColor: bgSidebar
                                anchors.centerIn: parent
                            }
                        }
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: strings.sidebar_empty_title
                        color: isDark ? "#FFF1E1" : "#4B2D12"
                        font.pixelSize: typeBody + 1
                        font.weight: weightBold
                        wrapMode: Text.WordWrap
                    }

                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        text: strings.sidebar_empty_hint
                        color: isDark ? "#DCC5A8" : "#74512F"
                        font.pixelSize: typeMeta
                        wrapMode: Text.WordWrap
                    }

                    PillActionButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.sidebar_empty_cta
                        leadingText: "+"
                        minHeight: 28
                        horizontalPadding: 18
                        fillColor: emptyStateHover.containsMouse ? accent : accentGlow
                        hoverFillColor: emptyStateHover.containsMouse ? accent : accentGlow
                        outlineColor: emptyStateHover.containsMouse ? accent : sessionRowActiveBorder
                        hoverOutlineColor: emptyStateHover.containsMouse ? accent : sessionRowActiveBorder
                        textColor: bgSidebar
                    }
                }

                MouseArea {
                    id: emptyStateHover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.requestNewSession()
                }
            }
        }
    }

    Item {
        id: sessionHighlightViewport
        objectName: "sessionHighlightViewport"
        parent: sessionList.parent
        z: 1
        x: sessionList.x
        y: sessionList.y
        width: sessionList.width
        height: sessionList.height
        clip: true

        Rectangle {
            id: activeSessionHighlight
            objectName: "activeSessionHighlight"
            z: 1
            x: root.activeHighlightX
            y: root.activeHighlightY
            width: root.activeHighlightWidth
            height: root.activeHighlightHeight
            radius: 12
            color: isDark ? "#251B14" : "#F5EADF"
            border.width: 1
            border.color: isDark ? "#3A2A20" : "#E8D5C0"
            opacity: root.activeHighlightOpacity
            visible: opacity > 0.01

            Behavior on x { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on y { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on width { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on height { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

            Rectangle {
                width: 3
                height: parent.height - 12
                radius: 1
                anchors.left: parent.left
                anchors.leftMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                color: accent
                opacity: 0.9
            }

            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: parent.radius - 1
                color: isDark ? "#08FFFFFF" : "#10FFFFFF"
                opacity: 0.72
            }
        }
    }

    SequentialAnimation {
        id: projectionMotionSettler
        PauseAnimation {
            duration: motionUi
        }
        ScriptAction {
            script: root.finishProjectionMotion()
        }
    }
}
