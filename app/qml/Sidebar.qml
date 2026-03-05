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
            var savedY = sessionList.contentY
            root.rebuildGroupModel()
            var maxY = Math.max(0, sessionList.contentHeight - sessionList.height)
            sessionList.contentY = Math.min(savedY, maxY)
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
            height: 48
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
                    if (isRunning) return isDark ? "#5222C55E" : "#3A22C55E"
                    if (isError)   return isDark ? "#28F05A5A" : "#18F05A5A"
                    if (isStarting) return isDark ? "#52F59E0B" : "#3AF59E0B"
                    // idle hover — stronger purple
                    return isDark ? "#32FF951F" : "#20FF951F"
                }
                if (isRunning)  return isDark ? "#3A22C55E" : "#2822C55E"
                if (isError)    return isDark ? "#1CF05A5A" : "#14F05A5A"
                if (isStarting) return isDark ? "#34F59E0B" : "#24F59E0B"
                // idle — soft purple tint as CTA invitation
                return isDark ? "#24FF951F" : "#16FF951F"
            }
            border.width: 1
            border.color: {
                if (isRunning)  return isDark ? "#7A22C55E" : "#6022C55E"
                if (isError)    return isDark ? "#30F05A5A" : "#24F05A5A"
                if (isStarting) return isDark ? "#68F59E0B" : "#54F59E0B"
                if (gwHover.containsMouse) return isDark ? "#4AFF951F" : "#35FF951F"
                // idle — visible purple border
                return isDark ? "#30FF951F" : "#1EFF951F"
            }

            // ── State transition animations ──────────────────────────
            Behavior on color { ColorAnimation { duration: 280; easing.type: Easing.OutCubic } }
            Behavior on border.color { ColorAnimation { duration: 280; easing.type: Easing.OutCubic } }

            // Scale bounce on state change
            property string _prevState: chatService ? chatService.state : "idle"
            scale: 1.0
            Behavior on scale { NumberAnimation { duration: 300; easing.type: Easing.OutBack } }
            Connections {
                target: chatService
                function onStateChanged() {
                    if (!chatService) return
                    var s = chatService.state
                    if (s !== gwCapsule._prevState) {
                        gwCapsule._prevState = s
                        gwCapsule.scale = 0.96
                        scaleBounceTimer.restart()
                    }
                }
            }
            Timer {
                id: scaleBounceTimer
                interval: 80; repeat: false
                onTriggered: gwCapsule.scale = 1.0
            }

            // Starting pulse animation
            SequentialAnimation {
                id: startingPulse
                running: gwCapsule.isStarting
                loops: Animation.Infinite
                NumberAnimation { target: gwCapsule; property: "opacity"; from: 1.0; to: 0.78; duration: 800; easing.type: Easing.InOutSine }
                NumberAnimation { target: gwCapsule; property: "opacity"; from: 0.78; to: 1.0; duration: 800; easing.type: Easing.InOutSine }
            }
            // Error subtle pulse
            SequentialAnimation {
                id: errorPulse
                running: gwCapsule.isError
                loops: Animation.Infinite
                NumberAnimation { target: gwCapsule; property: "opacity"; from: 1.0; to: 0.7; duration: 1200; easing.type: Easing.InOutSine }
                NumberAnimation { target: gwCapsule; property: "opacity"; from: 0.7; to: 1.0; duration: 1200; easing.type: Easing.InOutSine }
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
                border.color: gwCapsule.isRunning ? (isDark ? "#8A22C55E" : "#6A22C55E") : "transparent"
                opacity: 0
                visible: gwCapsule.isRunning
                Behavior on border.color { ColorAnimation { duration: 300 } }
                SequentialAnimation {
                    running: gwCapsule.isRunning
                    loops: Animation.Infinite
                    NumberAnimation { target: gwGlow; property: "opacity"; from: 0; to: 0.8; duration: 1200; easing.type: Easing.InOutSine }
                    NumberAnimation { target: gwGlow; property: "opacity"; from: 0.8; to: 0; duration: 1200; easing.type: Easing.InOutSine }
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
                        Behavior on color { ColorAnimation { duration: 250 } }

                        // Running: breathing scale
                        SequentialAnimation on scale {
                            running: gwCapsule.isRunning
                            loops: Animation.Infinite
                            NumberAnimation { to: 1.4; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                        }

                        // Starting: rotation spin
                        SequentialAnimation on rotation {
                            running: gwCapsule.isStarting
                            loops: Animation.Infinite
                            NumberAnimation { from: 0; to: 360; duration: 1600; easing.type: Easing.Linear }
                        }

                        // Error: opacity pulse
                        SequentialAnimation {
                            running: gwCapsule.isError
                            loops: Animation.Infinite
                            NumberAnimation { target: gwDot; property: "opacity"; from: 1.0; to: 0.3; duration: 600; easing.type: Easing.InOutSine }
                            NumberAnimation { target: gwDot; property: "opacity"; from: 0.3; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
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
                        if (gwCapsule.isRunning)  return isDark ? "#A8EAC3" : "#177C43"
                        if (gwCapsule.isError)    return statusError
                        if (gwCapsule.isStarting) return isDark ? "#FFD484" : "#B56800"
                        // idle — purple accent text
                        return isDark ? "#FFC58A" : "#B86A12"
                    }
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    font.letterSpacing: 0.3
                    Behavior on color { ColorAnimation { duration: 250 } }
                }

                // Action icon
                Image {
                    Layout.alignment: Qt.AlignVCenter
                    source: gwCapsule.isRunning
                            ? "../resources/icons/stop.svg"
                            : "../resources/icons/power.svg"
                    sourceSize: Qt.size(16, 16)
                    width: 16; height: 16
                    opacity: gwHover.containsMouse ? 0.95 : 0.65
                    Behavior on opacity { NumberAnimation { duration: 150 } }
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
                font.pixelSize: 15
                font.weight: Font.DemiBold
                font.letterSpacing: 0.5
                textFormat: Text.PlainText
                Layout.fillWidth: true
            }

            Rectangle {
                width: 36
                height: 36
                radius: 18
                color: newSessionHover.containsMouse ? accent : accentMuted
                border.width: 1
                border.color: newSessionHover.containsMouse ? accent : borderSubtle
                scale: newSessionHover.containsMouse ? 1.04 : 1.0
                Behavior on color { ColorAnimation { duration: 140 } }
                Behavior on scale { NumberAnimation { duration: 140 } }

                Text {
                    anchors.centerIn: parent
                    text: "+"
                    color: "#FFFFFF"
                    font.pixelSize: 22
                    font.weight: Font.DemiBold
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
                height: model.isHeader ? 38 : sessionRow.height

                // ── Group header row ──────────────────────────────────────
                Rectangle {
                    visible: model.isHeader
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    height: 38
                    color: "transparent"

                    RowLayout {
                        anchors { fill: parent; leftMargin: 14; rightMargin: 10 }
                        spacing: 6

                        Text {
                            text: model.expanded ? "▾" : "▸"
                            color: textPrimary
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: strings["channel_" + (model.channel || "other")] || model.channel || "other"
                            color: textPrimary
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.4
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
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

                    SessionItem {
                        id: inner
                        width: parent.width - 20
                        x: 10
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
                font.pixelSize: 13
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
                width: appIconBtn.width + 14; height: appIconBtn.height + 14
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
                        from: 0; to: 0.35; duration: 2400
                        easing.type: Easing.InOutSine
                    }
                    NumberAnimation {
                        target: glowRing; property: "opacity"
                        from: 0.35; to: 0; duration: 2400
                        easing.type: Easing.InOutSine
                    }
                }

                states: State {
                    name: "hovered"; when: appIconArea.containsMouse
                    PropertyChanges { target: glowRing; opacity: 0.6 }
                }
                transitions: Transition {
                    NumberAnimation {
                        property: "opacity"; duration: 280
                        easing.type: Easing.OutCubic
                    }
                }
            }

            // Second subtle ring (depth layer)
            Rectangle {
                id: glowRingOuter
                anchors.centerIn: appIconBtn
                width: appIconBtn.width + 24; height: appIconBtn.height + 24
                radius: width / 2
                color: "transparent"
                border.width: 1
                border.color: accent
                opacity: appIconArea.containsMouse ? 0.25 : 0
                antialiasing: true
                scale: appIconBtn.scale
                rotation: appIconBtn.rotation
                Behavior on opacity {
                    NumberAnimation { duration: 400; easing.type: Easing.OutCubic }
                }
            }

            // Icon body
            Rectangle {
                id: appIconBtn
                width: 44; height: 44; radius: 22
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
                    NumberAnimation { from: 0; to: -2.5; duration: 1800; easing.type: Easing.InOutQuad }
                    NumberAnimation { from: -2.5; to: 0; duration: 1800; easing.type: Easing.InOutQuad }
                }
                transform: Translate { y: appIconBtn.floatY }

                scale: appIconArea.pressed ? 0.90
                       : (appIconArea.containsMouse ? 1.12 : 1.0)
                rotation: appIconArea.containsMouse ? -10 : 0

                Behavior on scale {
                    NumberAnimation { duration: 240; easing.type: Easing.OutBack }
                }
                Behavior on border.color {
                    ColorAnimation { duration: 200 }
                }
                Behavior on rotation {
                    NumberAnimation { duration: 350; easing.type: Easing.OutBack }
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
                radius: 12
                color: isDark ? "#2A1A11" : "#FFFFFF"
                border.width: 1
                border.color: isDark ? "#4A2A1A" : "#F0DED1"

                opacity: 0
                scale: 0.8
                transformOrigin: Item.Left
                visible: opacity > 0

                Behavior on opacity {
                    NumberAnimation { duration: 220; easing.type: Easing.OutCubic }
                }
                Behavior on scale {
                    NumberAnimation { duration: 220; easing.type: Easing.OutBack }
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
                        ctx.fillStyle = isDark ? "#2A1A11" : "#FFFFFF"
                        ctx.fill()
                    }
                }

                // Bubble text
                Text {
                    id: bubbleText
                    anchors.centerIn: parent
                    font.pixelSize: 12
                    font.weight: Font.Medium
                    color: isDark ? "#EBCDB3" : "#5D4738"
                    text: ""
                }
            }
        }
    }
}
