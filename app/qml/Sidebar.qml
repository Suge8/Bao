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

    function rebuildGroupModel() {
        if (!sessionService) return
        var sm = sessionService.sessionsModel
        if (!sm) return

        var groups = {}
        var order = []
        for (var i = 0; i < sm.rowCount(); i++) {
            var idx = sm.index(i, 0)
            var key     = sm.data(idx, Qt.UserRole + 1) || ""
            var title   = sm.data(idx, Qt.UserRole + 2) || key
            var channel = sm.data(idx, Qt.UserRole + 5) || "other"
            var unread  = sm.data(idx, Qt.UserRole + 6) || false
            if (!groups[channel]) { groups[channel] = []; order.push(channel) }
            groups[channel].push({ key: key, title: title, channel: channel, hasUnread: unread })
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
            groupModel.append({ isHeader: true,  channel: grp, expanded: exp,
                                 itemKey: "", itemTitle: "", itemVisible: true, itemHasUnread: false })
            var items = groups[grp]
            for (var si = 0; si < items.length; si++) {
                var s = items[si]
                groupModel.append({ isHeader: false, channel: grp, expanded: false,
                                     itemKey: s.key, itemTitle: s.title,
                                     itemVisible: exp, itemHasUnread: s.hasUnread })
            }
        }

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
        root.expandedGroups[activeChannel] = true
        for (var j = 0; j < groupModel.count; j++) {
            var row = groupModel.get(j)
            if (row.channel !== activeChannel)
                continue
            if (row.isHeader)
                groupModel.setProperty(j, "expanded", true)
            else
                groupModel.setProperty(j, "itemVisible", true)
        }
    }

    onActiveSessionKeyChanged: ensureGroupExpandedFor(activeSessionKey)

    function toggleGroup(channel) {
        var newExp = !(root.expandedGroups[channel] === true)
        root.expandedGroups[channel] = newExp
        for (var i = 0; i < groupModel.count; i++) {
            var item = groupModel.get(i)
            if (item.channel === channel) {
                if (item.isHeader)
                    groupModel.setProperty(i, "expanded", newExp)
                else
                    groupModel.setProperty(i, "itemVisible", newExp)
            }
        }
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

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Gateway status capsule ────────────────────────────────────
        Rectangle {
            id: gwCapsule
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 16
            Layout.topMargin: 16; Layout.bottomMargin: 2
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

            function resetVisualState() {
                gwCapsule.actionPulse = 0.0
                gwCapsule.iconLift = 0.0
                gwCapsule.iconPulse = 0.0
                gwCapsule.iconTurn = 0.0
                gwDot.opacity = 1.0
                gwDot.scale = 1.0
            }
            onCurrentStateChanged: resetVisualState()

            color: gwCapsule.surfaceColor
            border.width: 0
            scale: gwHover.pressed ? 0.985 : (gwCapsule.isHovered ? motionHoverScaleSubtle : 1.0)

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
                        running: gwCapsule.isStarting
                        loops: Animation.Infinite
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.10; duration: motionAmbient; easing.type: easeSoft }
                        NumberAnimation { target: gwCapsule; property: "iconPulse"; to: 0.0; duration: motionAmbient; easing.type: easeSoft }
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
                    if (!chatService) return
                    if (gwCapsule.isStarting) return
                    if (gwCapsule.isRunning) chatService.stop()
                    else chatService.start()
                }
            }
        }

        // ── Sessions header ───────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.rightMargin: 12
            Layout.topMargin: 14
            Layout.bottomMargin: 10
            spacing: 0

            Text {
                text: strings.sidebar_sessions
                color: textSecondary
                font.pixelSize: typeBody
                font.weight: Font.DemiBold
                font.letterSpacing: 0.5
                textFormat: Text.PlainText
                Layout.fillWidth: true
            }

            Rectangle {
                implicitWidth: sizeControlHeight - 6
                implicitHeight: sizeControlHeight - 6
                radius: 18
                color: newSessionHover.containsMouse ? accent : accentMuted
                border.width: 1
                border.color: newSessionHover.containsMouse ? accent : borderSubtle
                scale: newSessionHover.containsMouse ? motionHoverScaleMedium : 1.0
                Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                Text {
                    anchors.centerIn: parent
                    text: "+"
                    color: textPrimary
                    font.pixelSize: typeTitle
                    font.weight: weightDemiBold
                }

                MouseArea {
                    id: newSessionHover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.newSessionRequested()
                }
            }
        }

        // ── Session list ──────────────────────────────────────────────────
        ListView {
            id: sessionList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: groupModel
            spacing: 0
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                width: sessionList.width
                height: model.isHeader ? sizeSidebarHeader : sessionRow.height

                // ── Group header row ──────────────────────────────────────
                Rectangle {
                    visible: model.isHeader
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    height: sizeSidebarHeader
                    color: "transparent"

                    RowLayout {
                        anchors { fill: parent; leftMargin: 14; rightMargin: 10 }
                        spacing: 6

                        Text {
                            text: model.expanded ? "▾" : "▸"
                            color: textPrimary
                            font.pixelSize: typeBody
                            font.weight: weightDemiBold
                        }
                        Text {
                            text: strings["channel_" + (model.channel || "other")] || model.channel || "other"
                            color: textPrimary
                            font.pixelSize: typeBody
                            font.weight: weightDemiBold
                            font.letterSpacing: letterTight
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                        }
                    }

                    MouseArea {
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
                    height: model.itemVisible ? (inner.height + 4) : 0
                    clip: true
                    Behavior on height { NumberAnimation { duration: motionUi; easing.type: easeStandard } }

                    SessionItem {
                        id: inner
                        width: parent.width - 20
                        x: 10
                        opacity: model.itemVisible ? 1.0 : 0.0
                        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                        sessionKey:   model.itemKey   ?? ""
                        sessionTitle: model.itemTitle ?? model.itemKey ?? ""
                        isActive:     root.showChatSelection && sessionKey === root.activeSessionKey
                        dimmed:       root.gatewayIdle
                        hasUnread:    model.itemHasUnread ?? false
                        onSelected:       root.sessionSelected(sessionKey)
                        onDeleteRequested: root.sessionDeleteRequested(sessionKey)
                    }
                }
            }

            // Empty state
            Text {
                anchors.centerIn: parent
                visible: groupModel.count === 0
                text: strings.sidebar_no_sessions
                color: textTertiary
                font.pixelSize: typeLabel
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
