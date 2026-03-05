import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property string currentView: "chat"
    signal viewRequested(string view)
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
            var active  = sm.data(idx, Qt.UserRole + 3) || false
            var channel = sm.data(idx, Qt.UserRole + 5) || "other"
            var unread  = sm.data(idx, Qt.UserRole + 6) || false
            if (!groups[channel]) { groups[channel] = []; order.push(channel) }
            groups[channel].push({ key: key, title: title, isActive: active, channel: channel, hasUnread: unread })
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
                                 itemKey: "", itemTitle: "", isActive: false, itemVisible: true, itemHasUnread: false })
            var items = groups[grp]
            for (var si = 0; si < items.length; si++) {
                var s = items[si]
                groupModel.append({ isHeader: false, channel: grp, expanded: false,
                                     itemKey: s.key, itemTitle: s.title, isActive: s.isActive,
                                     itemVisible: exp, itemHasUnread: s.hasUnread })
            }
        }

    }

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
                var maxY = Math.max(0, sessionList.contentHeight - sessionList.height)
                sessionList.contentY = Math.min(savedY, maxY)
            })
        }
        function onActiveKeyChanged(key) {
            var activeChannel = ""
            for (var i = 0; i < groupModel.count; i++) {
                var item = groupModel.get(i)
                if (!item.isHeader) {
                    var isNowActive = item.itemKey === key
                    if (isNowActive)
                        activeChannel = item.channel
                    groupModel.setProperty(i, "isActive", isNowActive)
                }
            }
            if (!activeChannel)
                return
            if (root.expandedGroups[activeChannel] === true)
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
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Gateway status capsule ────────────────────────────────────
        Rectangle {
            id: gwCapsule
            Layout.fillWidth: true
            Layout.leftMargin: 10; Layout.rightMargin: 10
            Layout.topMargin: 16; Layout.bottomMargin: 2
            height: sizeCapsuleHeight
            radius: height / 2
            visible: chatService !== null

            property bool isRunning: chatService && chatService.state === "running"
            property bool isStarting: chatService && chatService.state === "starting"
            property bool isError: chatService && chatService.state === "error"
            property bool isStopped: {
                if (!chatService) return true
                var s = chatService.state
                return s === "idle" || s === "stopped"
            }

            // ── State colors ──────────────────────────────────────────
            color: {
                if (gwHover.containsMouse) {
                    if (isRunning) return gatewayBgRunningHover
                    if (isError)   return gatewayBgErrorHover
                    if (isStarting) return gatewayBgStartingHover
                    return gatewayBgIdleHover
                }
                if (isRunning)  return gatewayBgRunning
                if (isError)    return gatewayBgError
                if (isStarting) return gatewayBgStarting
                return gatewayBgIdle
            }
            border.width: 1
            border.color: {
                if (isRunning)  return gatewayBorderRunning
                if (isError)    return gatewayBorderError
                if (isStarting) return gatewayBorderStarting
                if (gwHover.containsMouse) return gatewayBorderIdleHover
                return gatewayBorderIdle
            }

            // ── State transition animations ──────────────────────────
            Behavior on color { ColorAnimation { duration: motionPanel; easing.type: easeStandard } }
            Behavior on border.color { ColorAnimation { duration: motionPanel; easing.type: easeStandard } }

            // Scale bounce on state change
            property string _prevState: chatService ? chatService.state : "idle"
            scale: 1.0
            Behavior on scale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
            Connections {
                target: chatService
                function onStateChanged() {
                    if (!chatService) return
                    var s = chatService.state
                    if (s !== gwCapsule._prevState) {
                        gwCapsule._prevState = s
                        gwCapsule.scale = 0.93
                        scaleBounceTimer.restart()
                    }
                }
            }
            Timer {
                id: scaleBounceTimer
                interval: motionStagger; repeat: false
                onTriggered: gwCapsule.scale = 1.0
            }

            // Starting pulse animation
            SequentialAnimation {
                id: startingPulse
                running: gwCapsule.isStarting
                loops: Animation.Infinite
                NumberAnimation { target: gwCapsule; property: "opacity"; from: 1.0; to: motionStatusMinOpacityStarting; duration: motionAmbient; easing.type: easeSoft }
                NumberAnimation { target: gwCapsule; property: "opacity"; from: motionStatusMinOpacityStarting; to: 1.0; duration: motionAmbient; easing.type: easeSoft }
            }
            // Error subtle pulse
            SequentialAnimation {
                id: errorPulse
                running: gwCapsule.isError
                loops: Animation.Infinite
                NumberAnimation { target: gwCapsule; property: "opacity"; from: 1.0; to: motionStatusMinOpacityError; duration: motionBreath; easing.type: easeSoft }
                NumberAnimation { target: gwCapsule; property: "opacity"; from: motionStatusMinOpacityError; to: 1.0; duration: motionBreath; easing.type: easeSoft }
            }
            // Reset opacity when not animating
            onIsStartingChanged: if (!isStarting && !isError) opacity = 1.0
            onIsErrorChanged: if (!isError && !isStarting) opacity = 1.0

            // ── Running border glow (breathing) ──────────────────────
            Rectangle {
                id: gwGlow
                anchors.fill: parent
                anchors.margins: -1.5
                radius: parent.radius + 1.5
                color: "transparent"
                border.width: 1.5
                border.color: gwCapsule.isRunning ? gatewayGlowRunning : "transparent"
                opacity: 0
                visible: gwCapsule.isRunning
                Behavior on border.color { ColorAnimation { duration: motionPanel; easing.type: easeStandard } }
                SequentialAnimation {
                    running: gwCapsule.isRunning
                    loops: Animation.Infinite
                    NumberAnimation { target: gwGlow; property: "opacity"; from: 0; to: motionGlowPeakOpacity; duration: motionBreath; easing.type: easeSoft }
                    NumberAnimation { target: gwGlow; property: "opacity"; from: motionGlowPeakOpacity; to: 0; duration: motionBreath; easing.type: easeSoft }
                }
            }

            // ── Content row ───────────────────────────────────────────
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14; anchors.rightMargin: 12
                spacing: 10

                // Status dot
                Item {
                    Layout.alignment: Qt.AlignVCenter
                    width: 10; height: 10
                    Rectangle {
                        id: gwDot
                        anchors.centerIn: parent
                        width: 8; height: 8; radius: 4
                        color: {
                            if (!chatService) return textTertiary
                            switch (chatService.state) {
                                case "running":  return statusSuccess
                                case "starting": return statusWarning
                                case "error":    return statusError
                                default:         return accent
                            }
                        }
                        Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

                        // Running: breathing scale
                        SequentialAnimation on scale {
                            running: gwCapsule.isRunning
                            loops: Animation.Infinite
                            NumberAnimation { to: motionDotPulseScaleMax; duration: motionBreath - motionFast; easing.type: easeSoft }
                            NumberAnimation { to: 1.0; duration: motionBreath - motionFast; easing.type: easeSoft }
                        }

                        // Starting: rotation spin
                        SequentialAnimation on rotation {
                            running: gwCapsule.isStarting
                            loops: Animation.Infinite
                            NumberAnimation { from: 0; to: 360; duration: motionFloat - motionUi; easing.type: easeLinear }
                        }

                        // Error: opacity pulse
                        SequentialAnimation {
                            running: gwCapsule.isError
                            loops: Animation.Infinite
                            NumberAnimation { target: gwDot; property: "opacity"; from: 1.0; to: motionDotPulseMinOpacity; duration: motionStatusPulse; easing.type: easeSoft }
                            NumberAnimation { target: gwDot; property: "opacity"; from: motionDotPulseMinOpacity; to: 1.0; duration: motionStatusPulse; easing.type: easeSoft }
                        }
                    }
                }

                // Status text
                Text {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    text: {
                        if (!chatService) return strings.gateway_idle
                        switch (chatService.state) {
                            case "running":  return strings.gateway_running
                            case "starting": return strings.gateway_starting
                            case "error":    return strings.gateway_error
                            default:         return strings.button_start_gateway
                        }
                    }
                    color: {
                        if (gwCapsule.isRunning)  return gatewayTextRunning
                        if (gwCapsule.isError)    return statusError
                        if (gwCapsule.isStarting) return gatewayTextStarting
                        return gatewayTextIdle
                    }
                    font.pixelSize: typeButton
                    font.weight: weightDemiBold
                    font.letterSpacing: letterTight
                    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                }

                // Action icon
                Image {
                    Layout.alignment: Qt.AlignVCenter
                    source: gwCapsule.isRunning
                            ? "../resources/icons/stop.svg"
                            : "../resources/icons/power.svg"
                    sourceSize: Qt.size(16, 16)
                    width: 16; height: 16
                    opacity: gwHover.containsMouse ? opacityInteractionHover : opacityInteractionIdle
                    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                }
            }

            // Click handler
            MouseArea {
                id: gwHover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: gwCapsule.isStarting ? Qt.ArrowCursor : Qt.PointingHandCursor
                onClicked: {
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
                width: sizeControlHeight - 6
                height: sizeControlHeight - 6
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
                        isActive:     model.isActive  ?? false
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
                        if (root.currentView !== "settings") {
                            root.currentView = "settings"
                            root.viewRequested("settings")
                        }
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
