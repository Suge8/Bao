import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "sidebarRoot"

    property bool showingSettings: false
    property string activeSessionKey: ""
    property bool showChatSelection: true
    signal settingsRequested()
    signal newSessionRequested()
    signal sessionSelected(string key)
    signal sessionDeleteRequested(string key)

    color: "transparent"

    Rectangle {
        anchors.fill: parent
        radius: 20
        color: bgSidebar
        antialiasing: true

        Rectangle {
            anchors { top: parent.top; left: parent.left; right: parent.right }
            height: parent.radius
            color: parent.color
        }
        Rectangle {
            anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
            width: parent.radius
            color: parent.color
        }
    }

    ListModel { id: groupModel }

    property var expandedGroups: ({})
    property bool gatewayIdle: !chatService || chatService.state === "idle" || chatService.state === "stopped"
    property int sessionsUnreadCount: 0
    property string unreadFingerprint: ""
    property real headerPulseScale: 0.0
    property real headerBadgeScale: 0.0

    function requestNewSession() {
        root.newSessionRequested()
    }

    function channelIconSource(channel) {
        switch (channel) {
        case "desktop":
            return "../resources/icons/sidebar-monitor.svg"
        case "system":
            return "../resources/icons/sidebar-settings.svg"
        case "heartbeat":
            return "../resources/icons/sidebar-pulse.svg"
        case "cron":
            return "../resources/icons/sidebar-zap.svg"
        case "email":
            return "../resources/icons/sidebar-mail.svg"
        default:
            return "../resources/icons/sidebar-chat.svg"
        }
    }

    function channelFilledIconSource(channel) {
        switch (channel) {
        case "desktop":
            return "../resources/icons/sidebar-monitor-solid.svg"
        case "system":
            return "../resources/icons/sidebar-settings-solid.svg"
        case "heartbeat":
            return "../resources/icons/sidebar-pulse-solid.svg"
        case "cron":
            return "../resources/icons/sidebar-zap-solid.svg"
        case "email":
            return "../resources/icons/sidebar-mail-solid.svg"
        default:
            return "../resources/icons/sidebar-chat-solid.svg"
        }
    }

    function channelAccent(channel) {
        switch (channel) {
        case "desktop":
            return isDark ? Qt.rgba(1.0, 0.78, 0.29, 1.0) : Qt.rgba(0.90, 0.58, 0.08, 1.0)
        case "system":
            return isDark ? Qt.rgba(0.53, 0.82, 1.0, 1.0) : Qt.rgba(0.20, 0.55, 0.85, 1.0)
        case "heartbeat":
            return isDark ? Qt.rgba(0.20, 0.90, 0.56, 1.0) : Qt.rgba(0.05, 0.70, 0.38, 1.0)
        case "cron":
            return isDark ? Qt.rgba(1.0, 0.66, 0.18, 1.0) : Qt.rgba(0.92, 0.52, 0.05, 1.0)
        case "email":
            return isDark ? Qt.rgba(0.46, 0.69, 1.0, 1.0) : Qt.rgba(0.22, 0.46, 0.88, 1.0)
        default:
            return isDark ? Qt.rgba(0.79, 0.55, 1.0, 1.0) : Qt.rgba(0.52, 0.27, 0.84, 1.0)
        }
    }

    function channelSurface(channel, expanded, hovered) {
        return expanded ? sidebarGroupExpandedBg : (hovered ? sidebarGroupHoverBg : sidebarGroupBg)
    }

    function applyGroupExpanded(channel, expanded) {
        root.expandedGroups[channel] = expanded
        for (var i = 0; i < groupModel.count; i++) {
            var item = groupModel.get(i)
            if (item.channel !== channel)
                continue
            if (item.isHeader)
                groupModel.setProperty(i, "expanded", expanded)
            else
                groupModel.setProperty(i, "itemVisible", expanded)
        }
    }

    function updateUnreadState(unreadCount, unreadFingerprintParts) {
        var nextUnreadFingerprint = unreadFingerprintParts.join("|")
        if (root.unreadFingerprint !== "" && nextUnreadFingerprint !== root.unreadFingerprint && unreadCount > 0)
            sessionsHeaderPulse.restart()
        root.sessionsUnreadCount = unreadCount
        root.unreadFingerprint = nextUnreadFingerprint
    }

    function rebuildGroupModel() {
        if (!sessionService) return
        var sm = sessionService.sessionsModel
        if (!sm) return

        var groups = {}
        var order = []
        var unreadCount = 0
        var unreadFingerprintParts = []
        for (var i = 0; i < sm.rowCount(); i++) {
            var idx = sm.index(i, 0)
            var key     = sm.data(idx, Qt.UserRole + 1) || ""
            var title   = sm.data(idx, Qt.UserRole + 2) || key
            var updated = sm.data(idx, Qt.UserRole + 4) || ""
            var channel = sm.data(idx, Qt.UserRole + 5) || "other"
            var unread  = sm.data(idx, Qt.UserRole + 6) || false
            var updatedText = sm.data(idx, Qt.UserRole + 7) || ""
            if (!groups[channel]) { groups[channel] = []; order.push(channel) }
            groups[channel].push({ key: key, title: title, channel: channel, hasUnread: unread, updatedText: updatedText })
            if (unread) {
                unreadCount += 1
                unreadFingerprintParts.push(String(key) + ":" + String(updated))
            }
        }

        order.sort(function(a, b) {
            if (a === b) return 0
            if (a === "desktop") return -1
            if (b === "desktop") return 1
            if (a === "heartbeat") return 1
            if (b === "heartbeat") return -1
            return a < b ? -1 : 1
        })

        for (var ci = 0; ci < order.length; ci++) {
            var ch = order[ci]
            if (!(ch in root.expandedGroups))
                root.expandedGroups[ch] = (ch === "desktop")
        }

        groupModel.clear()
        for (var gi = 0; gi < order.length; gi++) {
            var grp = order[gi]
            var exp = root.expandedGroups[grp] === true
            var items = groups[grp]
            groupModel.append({ isHeader: true,  channel: grp, expanded: exp,
                                 itemKey: "", itemTitle: "", itemUpdatedText: "", itemVisible: true, itemHasUnread: false,
                                 itemCount: items.length, isLastInGroup: false, isFirstInGroup: false })
            for (var si = 0; si < items.length; si++) {
                var s = items[si]
                groupModel.append({ isHeader: false, channel: grp, expanded: false,
                                     itemKey: s.key, itemTitle: s.title, itemUpdatedText: s.updatedText,
                                     itemVisible: exp, itemHasUnread: s.hasUnread, itemCount: 0,
                                     isLastInGroup: si === items.length - 1,
                                     isFirstInGroup: si === 0 })
            }
        }
        updateUnreadState(unreadCount, unreadFingerprintParts)
    }

    function ensureGroupExpandedFor(key) {
        if (!key)
            return
        var activeChannel = ""
        for (var i = 0; i < groupModel.count; i++) {
            var item = groupModel.get(i)
            if (!item.isHeader && item.itemKey === key) {
                activeChannel = item.channel
                break
            }
        }
        if (!activeChannel || root.expandedGroups[activeChannel] === true)
            return
        applyGroupExpanded(activeChannel, true)
    }

    onActiveSessionKeyChanged: ensureGroupExpandedFor(activeSessionKey)

    function toggleGroup(channel) {
        var newExp = !(root.expandedGroups[channel] === true)
        applyGroupExpanded(channel, newExp)
    }

    Connections {
        target: sessionService
        function onSessionsChanged() {
            Qt.callLater(function() {
                var savedY = sessionList.contentY
                root.rebuildGroupModel()
                root.ensureGroupExpandedFor(root.activeSessionKey)
                var maxY = Math.max(0, sessionList.contentHeight - sessionList.height)
                sessionList.contentY = Math.min(savedY, maxY)
            })
        }
    }

    Component.onCompleted: {
        Qt.callLater(function() {
            root.rebuildGroupModel()
            root.ensureGroupExpandedFor(root.activeSessionKey)
        })
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Gateway status capsule ────────────────────────────────────
        Rectangle {
            id: gwCapsule
            objectName: "gatewayCapsule"
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            Layout.topMargin: 16; Layout.bottomMargin: 0
            implicitHeight: sizeCapsuleHeight
            radius: height / 2
            visible: chatService !== null

            property string currentState: chatService ? chatService.state : "idle"
            property bool isRunning: chatService && chatService.state === "running"
            property bool isStarting: chatService && chatService.state === "starting"
            property bool isError: chatService && chatService.state === "error"
            property bool isIdleVisual: !isRunning && !isStarting && !isError
            property bool isHovered: gwHover.containsMouse
            property real actionPulse: 0.0
            property real iconLift: 0.0
            property real iconPulse: 0.0
            property real iconTurn: 0.0

            function stateValue(runningValue, errorValue, startingValue, idleValue) {
                switch (currentState) {
                    case "running":
                        return runningValue
                    case "error":
                        return errorValue
                    case "starting":
                        return startingValue
                    default:
                        return idleValue
                }
            }

            property var stateSpec: stateValue(
                                       {
                                           surfaceColor: gatewaySurfaceRunningTop,
                                           statusColor: gatewayTextRunning,
                                           actionColor: statusSuccess,
                                           dotColor: statusSuccess,
                                           primaryLabel: strings.gateway_running,
                                           actionIconSource: "../resources/icons/gateway-running.svg"
                                       },
                                       {
                                           surfaceColor: gatewaySurfaceErrorTop,
                                           statusColor: statusError,
                                           actionColor: statusError,
                                           dotColor: statusError,
                                           primaryLabel: strings.gateway_error,
                                           actionIconSource: "../resources/icons/gateway-error.svg"
                                       },
                                       {
                                           surfaceColor: gatewaySurfaceStartingTop,
                                           statusColor: gatewayTextStarting,
                                           actionColor: statusWarning,
                                           dotColor: statusWarning,
                                           primaryLabel: strings.gateway_starting,
                                           actionIconSource: "../resources/icons/gateway-starting.svg"
                                       },
                                       {
                                           surfaceColor: gatewaySurfaceIdleTop,
                                           statusColor: gatewayTextIdle,
                                           actionColor: accent,
                                           dotColor: accent,
                                           primaryLabel: strings.button_start_gateway,
                                           actionIconSource: "../resources/icons/gateway-idle.svg"
                                       })
            property color surfaceColor: stateSpec.surfaceColor
            property color statusColor: stateSpec.statusColor
            property color actionColor: stateSpec.actionColor
            property color dotColor: stateSpec.dotColor
            property string primaryLabel: stateSpec.primaryLabel
            property string actionIconSource: stateSpec.actionIconSource
            property string detailText: chatService ? (chatService.gatewayDetail || "") : ""
            property bool hasErrorDetail: chatService ? Boolean(chatService.gatewayDetailIsError) : false
            property bool showDetailBubble: hasErrorDetail || (detailText !== "" && (gwHover.containsMouse || gwDetailHover.containsMouse || activeFocus))
            property real detailAnchorCenterX: gwAction.x + gwAction.width / 2
            z: 6

            function resetVisualState() {
                gwCapsule.actionPulse = 0.0
                gwCapsule.iconLift = 0.0
                gwCapsule.iconPulse = 0.0
                gwCapsule.iconTurn = 0.0
                gwDot.opacity = 1.0
                gwDot.scale = 1.0
            }
            function triggerGatewayAction() {
                if (!chatService || gwCapsule.isStarting)
                    return
                if (gwCapsule.isRunning)
                    chatService.stop()
                else
                    chatService.start()
            }
            onCurrentStateChanged: resetVisualState()
            activeFocusOnTab: true
            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    gwCapsule.triggerGatewayAction()
                    event.accepted = true
                }
            }
            color: gwCapsule.surfaceColor
            border.width: activeFocus ? 1.5 : 0
            border.color: activeFocus ? borderFocus : "transparent"
            scale: gwHover.pressed ? 0.985 : (gwCapsule.isHovered ? motionHoverScaleSubtle : 1.0)

            Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
            Item {
                anchors.fill: parent

                Rectangle {
                    id: gwAction
                    anchors.right: parent.right
                    anchors.rightMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    width: sizeGatewayAction
                    height: sizeGatewayAction
                    radius: width / 2
                    antialiasing: true
                    color: Qt.darker(gwCapsule.actionColor, isDark ? 1.22 : 1.14)
                    border.width: 0
                    scale: (gwHover.pressed ? 0.97 : (gwCapsule.isHovered ? motionHoverScaleSubtle : 1.0)) + gwCapsule.actionPulse * 0.025
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                    Rectangle {
                        id: gwActionFace
                        width: parent.width - 2
                        height: width
                        radius: width / 2
                        anchors.centerIn: parent
                        color: gwCapsule.actionColor
                    }

                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.03; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isStarting
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.10; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isError
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.06; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "actionPulse"; to: 0.0; duration: motionStatusPulse; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: -0.8; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.06; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isIdleVisual
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 6; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconTurn"; to: 0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isStarting
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.10; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
                    }
                    NumberAnimation {
                        target: gwCapsule
                        property: "iconTurn"
                        from: 0
                        to: 360
                        duration: motionFloat
                        loops: Animation.Infinite
                        easing.type: easeLinear
                        running: gwCapsule.isStarting
                    }
                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: -0.6; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconLift"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isRunning
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.08; duration: motionBreath; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionBreath; easing.type: easeSoft }
                    }
                    SequentialAnimation {
                        running: gwCapsule.isError
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.05; duration: motionStatusPulse; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionStatusPulse; easing.type: easeSoft }
                    }

                    Item {
                        width: sizeGatewayActionIcon
                        height: sizeGatewayActionIcon
                        anchors.centerIn: gwActionFace
                        y: gwCapsule.iconLift
                        scale: 1.0 + gwCapsule.iconPulse
                        rotation: gwCapsule.iconTurn

                        Image {
                            anchors.fill: parent
                            source: gwCapsule.actionIconSource
                            sourceSize: Qt.size(sizeGatewayActionIcon, sizeGatewayActionIcon)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            mipmap: true
                            opacity: gwCapsule.isHovered ? 1.0 : 0.92
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                        }
                    }
                }

                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: 22
                    anchors.right: gwAction.left
                    anchors.rightMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1

                    Row {
                        spacing: 7

                        Rectangle {
                            id: gwDot
                            width: 6
                            height: 6
                            radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: gwCapsule.dotColor
                            Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

                            SequentialAnimation on scale {
                                running: gwCapsule.isRunning
                                loops: Animation.Infinite
                                NumberAnimation { to: motionDotPulseScaleMax; duration: motionBreath - motionFast; easing.type: easeSoft }
                                NumberAnimation { to: 1.0; duration: motionBreath - motionFast; easing.type: easeSoft }
                            }
                            SequentialAnimation {
                                running: gwCapsule.isStarting
                                loops: Animation.Infinite
                                NumberAnimation { target: gwDot; property: "opacity"; from: 1.0; to: 0.42; duration: motionAmbient; easing.type: easeSoft }
                                NumberAnimation { target: gwDot; property: "opacity"; from: 0.42; to: 1.0; duration: motionAmbient; easing.type: easeSoft }
                            }
                            SequentialAnimation {
                                running: gwCapsule.isError
                                loops: Animation.Infinite
                                NumberAnimation { target: gwDot; property: "opacity"; from: 1.0; to: motionDotPulseMinOpacity; duration: motionStatusPulse; easing.type: easeSoft }
                                NumberAnimation { target: gwDot; property: "opacity"; from: motionDotPulseMinOpacity; to: 1.0; duration: motionStatusPulse; easing.type: easeSoft }
                            }
                        }

                        Text {
                            text: strings.chat_gateway
                            color: gwCapsule.statusColor
                            font.pixelSize: typeCaption
                            font.weight: weightDemiBold
                            font.letterSpacing: letterWide
                            opacity: 0.72
                        }
                    }

                    Text {
                        text: gwCapsule.primaryLabel
                        color: gwCapsule.statusColor
                        font.pixelSize: typeButton + 1
                        font.weight: weightBold
                        font.letterSpacing: letterTight
                        Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    }
                }
            }

            MouseArea {
                id: gwHover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: gwCapsule.isStarting ? Qt.ArrowCursor : Qt.PointingHandCursor
                onClicked: {
                    gwCapsule.forceActiveFocus()
                    gwCapsule.triggerGatewayAction()
                }
            }

            Rectangle {
                id: gatewayDetailBubble
                objectName: "gatewayDetailBubble"
                z: 20
                property real maxContentHeight: 116
                width: Math.min(gwCapsule.width - 8, 320)
                x: Math.max(0, Math.min(gwCapsule.width - width, gwCapsule.detailAnchorCenterX - width / 2))
                y: gwCapsule.height
                visible: gwCapsule.showDetailBubble
                color: gwCapsule.hasErrorDetail ? (isDark ? "#FF472122" : "#FFF9E1E1") : (isDark ? "#FF2A241F" : "#FFF8F1E7")
                radius: 16
                border.width: 1
                border.color: gwCapsule.hasErrorDetail ? (isDark ? "#55F07A7A" : "#22DC2626") : (isDark ? "#22FFFFFF" : "#16000000")
                opacity: visible ? 1.0 : 0.0
                implicitHeight: Math.min(maxContentHeight, gatewayDetailText.implicitHeight) + 18
                clip: true

                Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                Canvas {
                    anchors.bottom: parent.top
                    width: 12
                    height: 8
                    x: Math.max(0, Math.min(parent.width - width, gwCapsule.detailAnchorCenterX - gatewayDetailBubble.x - width / 2))
                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.beginPath()
                        ctx.moveTo(width / 2, 0)
                        ctx.lineTo(0, height)
                        ctx.lineTo(width, height)
                        ctx.closePath()
                        ctx.fillStyle = gatewayDetailBubble.color
                        ctx.fill()
                    }
                }

                Flickable {
                    id: gatewayDetailViewport
                    objectName: "gatewayDetailViewport"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 9
                    anchors.bottomMargin: 9
                    clip: true
                    contentWidth: width
                    contentHeight: gatewayDetailText.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height

                    Text {
                        id: gatewayDetailText
                        objectName: "gatewayDetailText"
                        width: gatewayDetailViewport.width
                        text: gwCapsule.detailText
                        color: gwCapsule.hasErrorDetail ? statusError : textSecondary
                        font.pixelSize: typeCaption
                        font.weight: weightMedium
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                    }
                }

                MouseArea {
                    id: gwDetailHover
                    anchors.fill: parent
                    anchors.topMargin: -8
                    acceptedButtons: Qt.NoButton
                    hoverEnabled: true
                }
            }
        }

        // ── Session list ──────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: 14
            Layout.bottomMargin: 8
            radius: 22
            color: sidebarListPanelBg
            border.width: 1
            border.color: sidebarListPanelBorder

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: sidebarListPanelOverlay
                opacity: 0.9
            }

            Item {
                id: sessionsHeaderBar
                objectName: "sessionsHeaderBar"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.leftMargin: 14
                anchors.rightMargin: 12
                anchors.topMargin: 8
                height: 30
                scale: 1.0 + headerPulseScale

                Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                Item {
                    anchors.left: parent.left
                    anchors.right: newSessionButton.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    height: parent.height

                    Row {
                        id: sessionsHeaderContent
                        anchors.centerIn: parent
                        spacing: 8

                        Image {
                            width: 22
                            height: 22
                            anchors.verticalCenter: parent.verticalCenter
                            y: 1
                            source: "../resources/icons/sidebar-sessions-title.svg"
                            sourceSize: Qt.size(22, 22)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            mipmap: true
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

                        Rectangle {
                            objectName: "sessionsHeaderUnreadBadge"
                            visible: root.sessionsUnreadCount > 0
                            width: unreadBadgeText.implicitWidth + 12
                            height: 18
                            radius: 9
                            anchors.verticalCenter: parent.verticalCenter
                            color: sidebarHeaderBadgeBg
                            scale: 1.0 + headerBadgeScale

                            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                            Text {
                                id: unreadBadgeText
                                objectName: "sessionsHeaderUnreadText"
                                anchors.centerIn: parent
                                text: root.sessionsUnreadCount
                                color: sidebarHeaderBadgeText
                                font.pixelSize: typeCaption
                                font.weight: weightDemiBold
                            }
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

                SequentialAnimation {
                    id: sessionsHeaderPulse
                    running: false
                    ParallelAnimation {
                        NumberAnimation { target: root; property: "headerPulseScale"; from: 0.0; to: 0.03; duration: motionFast; easing.type: easeStandard }
                        NumberAnimation { target: root; property: "headerBadgeScale"; from: 0.0; to: 0.12; duration: motionFast; easing.type: easeEmphasis }
                    }
                    PauseAnimation { duration: motionMicro }
                    ParallelAnimation {
                        NumberAnimation { target: root; property: "headerPulseScale"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
                        NumberAnimation { target: root; property: "headerBadgeScale"; to: 0.0; duration: motionPanel; easing.type: easeSoft }
                    }
                }
            }

            ListView {
                id: sessionList
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                anchors.topMargin: sessionsHeaderBar.y + sessionsHeaderBar.height + 6
                anchors.bottomMargin: 8
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: groupModel
                spacing: 0
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

                delegate: Item {
                    width: sessionList.width
                    height: model.isHeader
                            ? (sizeSidebarHeader + (!model.expanded ? sizeSidebarGroupGap : 0))
                            : sessionRow.height

                    // ── Group header row ──────────────────────────────────────
                    Rectangle {
                        id: groupHeaderCard
                        visible: model.isHeader
                        anchors { left: parent.left; right: parent.right; top: parent.top }
                        height: sizeSidebarHeader
                        radius: 14
                        color: groupHeaderArea.pressed
                               ? sidebarGroupExpandedBg
                               : (groupHeaderArea.containsMouse
                                  ? sidebarGroupHoverBg
                                  : (model.expanded ? sidebarGroupExpandedBg : sidebarGroupBg))
                        border.width: 0
                        border.color: model.expanded ? sidebarGroupExpandedBorder : sidebarGroupBorder
                        scale: groupHeaderArea.pressed ? 0.992 : 1.0

                        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                        Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                        Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            color: root.channelSurface(model.channel, model.expanded, groupHeaderArea.containsMouse)
                            opacity: 1.0
                        }

                        RowLayout {
                            anchors { fill: parent; leftMargin: 10; rightMargin: 8 }
                            spacing: 7

                            Item {
                                Layout.preferredWidth: 20
                                Layout.preferredHeight: 20

                                Image {
                                    width: 16
                                    height: 16
                                    anchors.centerIn: parent
                                    source: root.channelIconSource(model.channel)
                                    sourceSize: Qt.size(16, 16)
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                    mipmap: true
                                    opacity: model.expanded ? 1.0 : 0.92
                                }
                            }

                            Text {
                                text: strings["channel_" + (model.channel || "other")] || model.channel || "other"
                                color: textPrimary
                                font.pixelSize: typeLabel + 1
                                font.weight: weightDemiBold
                                font.letterSpacing: 0.2
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                verticalAlignment: Text.AlignVCenter
                                opacity: model.expanded ? 0.99 : 0.94
                            }

                            Rectangle {
                                visible: (model.itemCount || 0) > 0
                                Layout.preferredWidth: countText.implicitWidth + 12
                                Layout.preferredHeight: 22
                                radius: 11
                                color: sidebarGroupCountBg
                                border.width: 1
                                border.color: sidebarGroupChevronBorder

                                Text {
                                    id: countText
                                    anchors.centerIn: parent
                                    text: model.itemCount || 0
                                    color: sidebarGroupCountText
                                    font.pixelSize: typeCaption
                                    font.weight: weightDemiBold
                                }
                            }

                            Rectangle {
                                Layout.preferredWidth: 22
                                Layout.preferredHeight: 22
                                radius: 11
                                color: sidebarGroupChevronBg
                                border.width: 1
                                border.color: sidebarGroupChevronBorder

                                Image {
                                    anchors.centerIn: parent
                                    width: 12
                                    height: 12
                                    source: "../resources/icons/sidebar-chevron.svg"
                                    sourceSize: Qt.size(12, 12)
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                    mipmap: true
                                    rotation: model.expanded ? 0 : -90
                                    opacity: groupHeaderArea.containsMouse ? 1.0 : 0.86

                                    Behavior on rotation { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
                                    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                                }
                            }
                        }

                        MouseArea {
                            id: groupHeaderArea
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton
                            preventStealing: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.toggleGroup(model.channel)
                        }
                    }

                    // ── Session item row ──────────────────────────────────────
                    Item {
                        id: sessionRow
                        visible: !model.isHeader
                        anchors { left: parent.left; right: parent.right; top: parent.top }
                        y: model.isFirstInGroup ? sizeSidebarHeaderToRowGap : 0
                        height: model.itemVisible
                                ? (inner.height
                                   + (model.isFirstInGroup ? sizeSidebarHeaderToRowGap : 0)
                                   + (model.isLastInGroup ? sizeSidebarGroupGap : sizeSidebarGroupInnerGap))
                                : 0
                        clip: true
                        Behavior on height { NumberAnimation { duration: motionUi; easing.type: easeStandard } }

                        SessionItem {
                            id: inner
                            width: parent.width - 16
                            x: 8
                            opacity: model.itemVisible ? 1.0 : 0.0
                            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                            sessionKey:   model.itemKey   ?? ""
                            sessionTitle: model.itemTitle ?? model.itemKey ?? ""
                            sessionRelativeTime: model.itemUpdatedText ?? ""
                            filledIconSource: root.channelFilledIconSource(model.channel)
                            isActive:     root.showChatSelection && sessionKey === root.activeSessionKey
                            dimmed:       root.gatewayIdle
                            hasUnread:    model.itemHasUnread ?? false
                            onSelected:       root.sessionSelected(sessionKey)
                            onDeleteRequested: root.sessionDeleteRequested(sessionKey)
                        }
                    }
                }


                // Empty state
                Item {
                    id: emptyStateWrap
                    objectName: "sidebarEmptyStateWrap"
                    anchors.top: parent.top
                    anchors.topMargin: 18
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(sessionList.width - 28, 196)
                    height: emptyStateCard.implicitHeight
                    visible: groupModel.count === 0

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
                                border.color: emptyStateHover.containsMouse ? sessionRowActiveBorder : (isDark ? "#38FFFFFF" : "#1A000000")

                                Image {
                                    width: 24
                                    height: 24
                                    anchors.centerIn: parent
                                    source: "../resources/icons/chat.svg"
                                    sourceSize: Qt.size(24, 24)
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                    mipmap: true
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
        }

        // ── App icon (bottom) ────────────────────────────────────────
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            Layout.bottomMargin: 14

            // Outer glow ring (sibling — never clipped)
            Rectangle {
                id: glowRing
                anchors.centerIn: appIconBtn
                width: appIconBtn.width + spacingMd + 2; height: appIconBtn.height + spacingMd + 2
                radius: width / 2
                color: "transparent"
                border.width: 1.5
                border.color: accent
                opacity: 0
                antialiasing: true
                scale: appIconBtn.scale
                rotation: appIconBtn.rotation

                SequentialAnimation {
                    id: breatheAnim
                    running: !appIconArea.containsMouse
                    loops: Animation.Infinite
                    NumberAnimation {
                        target: glowRing; property: "opacity"
                        from: 0; to: motionRingIdlePeakOpacity; duration: motionFloat + motionPanel
                        easing.type: easeSoft
                    }
                    NumberAnimation {
                        target: glowRing; property: "opacity"
                        from: motionRingIdlePeakOpacity; to: 0; duration: motionFloat + motionPanel
                        easing.type: easeSoft
                    }
                }

                states: State {
                    name: "hovered"; when: appIconArea.containsMouse
                    PropertyChanges { target: glowRing; opacity: motionRingHoverOpacity }
                }
                transitions: Transition {
                    NumberAnimation {
                        property: "opacity"; duration: motionPanel
                        easing.type: easeStandard
                    }
                }
            }

            // Second subtle ring (depth layer)
            Rectangle {
                id: glowRingOuter
                anchors.centerIn: appIconBtn
                width: appIconBtn.width + spacingXl; height: appIconBtn.height + spacingXl
                radius: width / 2
                color: "transparent"
                border.width: 1
                border.color: accent
                opacity: appIconArea.containsMouse ? 0.25 : 0
                antialiasing: true
                scale: appIconBtn.scale
                rotation: appIconBtn.rotation
                Behavior on opacity {
                    NumberAnimation { duration: motionAmbient; easing.type: easeStandard }
                }
            }

            // Icon body
            Rectangle {
                id: appIconBtn
                width: sizeAppIcon; height: sizeAppIcon; radius: sizeAppIcon / 2
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                color: "transparent"
                border.width: 1.5
                border.color: appIconArea.containsMouse ? accent : borderSubtle
                antialiasing: true

                // Idle float
                property real floatY: 0
                SequentialAnimation on floatY {
                    loops: Animation.Infinite
                    NumberAnimation { from: 0; to: -motionFloatOffset; duration: motionFloat; easing.type: easeSoft }
                    NumberAnimation { from: -motionFloatOffset; to: 0; duration: motionFloat; easing.type: easeSoft }
                }
                transform: Translate { y: appIconBtn.floatY }

                scale: appIconArea.pressed ? motionPressScaleStrong
                       : (appIconArea.containsMouse ? motionHoverScaleStrong : 1.0)
                rotation: appIconArea.containsMouse ? -10 : 0

                Behavior on scale {
                    NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
                }
                Behavior on border.color {
                    ColorAnimation { duration: motionUi; easing.type: easeStandard }
                }
                Behavior on rotation {
                    NumberAnimation { duration: motionPanel; easing.type: easeEmphasis }
                }

                // Circular logo (pre-clipped PNG)
                Image {
                    anchors.fill: parent
                    source: "../resources/logo-circle.png"
                    sourceSize: Qt.size(88, 88)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }

                MouseArea {
                    id: appIconArea
                    anchors.fill: parent
                    anchors.margins: -8
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: {
                        var idx = Math.floor(Math.random() * 5)
                        bubbleText.text = strings["bubble_" + idx] || ""
                        speechBubble.show = true
                    }
                    onExited: {
                        speechBubble.show = false
                    }
                    onClicked: {
                        if (!root.showingSettings)
                            root.settingsRequested()
                    }
                }
            }

            // ── Speech bubble (hover tooltip) ──────────────────────────
            Rectangle {
                id: speechBubble
                property bool show: false

                anchors.left: appIconBtn.right
                anchors.leftMargin: 14
                anchors.verticalCenter: appIconBtn.verticalCenter

                width: bubbleText.implicitWidth + 24
                height: bubbleText.implicitHeight + 16
                radius: radiusMd
                color: bgElevated
                border.width: 1
                border.color: borderDefault

                opacity: 0
                scale: motionBubbleHiddenScale
                transformOrigin: Item.Left
                visible: opacity > 0

                Behavior on opacity {
                    NumberAnimation { duration: motionUi; easing.type: easeStandard }
                }
                Behavior on scale {
                    NumberAnimation { duration: motionUi; easing.type: easeEmphasis }
                }

                states: State {
                    name: "visible"; when: speechBubble.show
                    PropertyChanges { target: speechBubble; opacity: 1.0; scale: 1.0 }
                }

                // Pointer triangle (points left toward icon)
                Canvas {
                    anchors.right: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: 8; height: 12
                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.beginPath()
                        ctx.moveTo(width, 0)
                        ctx.lineTo(0, height / 2)
                        ctx.lineTo(width, height)
                        ctx.closePath()
                        ctx.fillStyle = bgElevated
                        ctx.fill()
                    }
                }

                // Bubble text
                Text {
                    id: bubbleText
                    anchors.centerIn: parent
                    font.pixelSize: typeMeta
                    font.weight: weightMedium
                    color: textSecondary
                    text: ""
                }
            }
        }
    }
}
