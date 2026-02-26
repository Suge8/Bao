import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    color: "transparent"

    // Signal to request switching to settings page
    signal openSettings()
    signal messageCopied()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── Message list ─────────────────────────────────────────────────
        ListView {
            id: messageList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 14
            topMargin: 20
            bottomMargin: 12
            boundsBehavior: Flickable.StopAtBounds
            cacheBuffer: 1400
            reuseItems: false
            highlightFollowsCurrentItem: false
            highlightRangeMode: ListView.NoHighlightRange
            verticalLayoutDirection: ListView.TopToBottom

            model: chatService ? chatService.messages : null

            onModelChanged: {
                _prevCount = count
                batchReloading = false
                suspendEntranceAnimations = historyLoading
                pendingFollow = false
                pendingFollowAnimated = false
                emptyBurstWatching = false
                emptyBurstTimer.stop()
                autoFollow = true
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            // ── Smart follow / anti-flicker state ──────────────────────
            property real followThresholdPx: 40
            property bool autoFollow: true
            property bool userInteracting: dragging || flicking
            property bool historyLoading: chatService ? chatService.historyLoading : false
            property bool gatewayRunning: chatService ? chatService.state === "running" : false
            property bool animateProgrammaticScroll: false
            property bool forceFollowAfterSwitch: false

            property bool batchReloading: false
            property real savedReadingContentY: 0
            property real savedDistanceToEnd: 0
            property bool savedWasFollowing: true

            property bool pendingFollow: false
            property bool pendingFollowAnimated: false
            property bool emptyBurstWatching: false
            property int followRetryLeft: 0

            property bool suspendEntranceAnimations: false
            property int _prevCount: 0

            opacity: historyLoading ? 0.92 : 1.0
            Behavior on opacity {
                NumberAnimation {
                    duration: 130
                    easing.type: Easing.OutCubic
                }
            }

            function maxContentY() {
                // ListView uses a shifted content coordinate system (originY can be negative).
                // Use originY-based bounds to avoid landing in a blank overscroll region.
                return originY + contentHeight - height + bottomMargin
            }

            function minContentY() {
                return originY - topMargin
            }

            function clampContentY() {
                var minY = minContentY()
                var maxY = maxContentY()
                if (contentY < minY) contentY = minY
                else if (contentY > maxY) contentY = maxY
            }

            function isNearEnd() {
                return contentY >= (maxContentY() - followThresholdPx)
            }

            function recomputeAutoFollow() {
                autoFollow = atYEnd || isNearEnd()
            }

            function requestFollow(animated, restart) {
                pendingFollow = true
                pendingFollowAnimated = pendingFollowAnimated || animated
                if (restart) settleTimer.restart()
                else if (!settleTimer.running) settleTimer.start()
            }

            function applyScrollToEnd(animated) {
                if (count <= 0) return
                animateProgrammaticScroll = !!animated
                contentY = maxContentY()
                Qt.callLater(function () {
                    animateProgrammaticScroll = false
                    if (messageList.userInteracting) return
                    clampContentY()
                    if (!atYEnd) contentY = maxContentY()
                })
                if (!animated) animateProgrammaticScroll = false
            }

            function beginBatchReload() {
                batchReloading = true
                suspendEntranceAnimations = true
                savedReadingContentY = contentY
                savedDistanceToEnd = Math.max(0, maxContentY() - contentY)
            }

            function finishBatchReload() {
                batchReloading = false
                suspendEntranceAnimations = false
                pendingFollow = false
                pendingFollowAnimated = false
                autoFollow = savedWasFollowing
                if (savedWasFollowing) {
                    applyScrollToEnd(false)
                    return
                }
                contentY = maxContentY() - savedDistanceToEnd
                clampContentY()
            }

            Timer {
                id: settleTimer
                interval: 16
                repeat: false
                onTriggered: {
                    Qt.callLater(function () {
                        // While switching sessions we do a progressive follow loop.
                        // Any instant jump here can land in a "no delegates created" region.
                        if (messageList.forceFollowAfterSwitch) {
                            messageList.pendingFollow = false
                            messageList.pendingFollowAnimated = false
                            return
                        }
                        if (messageList.batchReloading) {
                            messageList.finishBatchReload()
                            return
                        }
                        if (messageList.pendingFollow && messageList.autoFollow && !messageList.userInteracting) {
                            messageList.applyScrollToEnd(messageList.pendingFollowAnimated)
                        }
                        messageList.pendingFollow = false
                        messageList.pendingFollowAnimated = false
                    })
                }
            }

            Timer {
                id: emptyBurstTimer
                interval: 60
                repeat: false
                onTriggered: {
                    messageList.emptyBurstWatching = false
                    if (!messageList.batchReloading) messageList.suspendEntranceAnimations = false
                }
            }

            Timer {
                id: followRetryTimer
                interval: 16
                repeat: false
                onTriggered: {
                    if (messageList.userInteracting) {
                        messageList.followRetryLeft = 0
                        return
                    }
                    if (messageList.count <= 0) {
                        if (messageList.followRetryLeft > 0) {
                            messageList.followRetryLeft -= 1
                            followRetryTimer.restart()
                        } else {
                            messageList.forceFollowAfterSwitch = false
                        }
                        return
                    }

                    // If the view has not created any delegates yet, a direct jump to the
                    // target scroll position can land in a blank region. Force a populate
                    // pass first, then progress toward the end.
                    var hasDelegates = messageList.contentItem
                                      && messageList.contentItem.childrenRect.height > 1
                    if (!hasDelegates) {
                        messageList.positionViewAtEnd()
                        if (messageList.followRetryLeft > 0) {
                            messageList.followRetryLeft -= 1
                            followRetryTimer.restart()
                        }
                        return
                    }

                    var target = messageList.maxContentY()
                    var delta = target - messageList.contentY
                    if (Math.abs(delta) <= 1.5 || messageList.atYEnd || messageList.isNearEnd()) {
                        messageList.contentY = target
                        messageList.clampContentY()
                        messageList.followRetryLeft = 0
                        messageList.forceFollowAfterSwitch = false
                        return
                    }

                    // Jump directly to bottom to avoid progressive scrolling,
                    // but keep retrying in case new delegates adjust the contentHeight.
                    messageList.animateProgrammaticScroll = false
                    messageList.positionViewAtEnd()
                    messageList.contentY = messageList.maxContentY()
                    messageList.clampContentY()

                    if (messageList.followRetryLeft > 0) {
                        messageList.followRetryLeft -= 1
                        followRetryTimer.restart()
                    }
                }
            }

            Behavior on contentY {
                enabled: messageList.animateProgrammaticScroll && !messageList.moving && !messageList.dragging
                SmoothedAnimation {
                    velocity: 5200
                }
            }

            onMovementEnded: {
                recomputeAutoFollow()
                if (!gatewayRunning) return
                if (autoFollow) requestFollow(false, false)
                else savedReadingContentY = contentY
            }

            onContentYChanged: {
                if (!autoFollow && !batchReloading) {
                    savedReadingContentY = contentY
                }
            }

            onCountChanged: {
                var oldCount = _prevCount
                _prevCount = count
                if (historyLoading) {
                    suspendEntranceAnimations = true
                    if (!settleTimer.running) settleTimer.start()
                    return
                }
                if (count === 0 && oldCount > 0) {
                    savedWasFollowing = autoFollow
                    beginBatchReload()
                    if (!settleTimer.running) settleTimer.start()
                    return
                }
                if (batchReloading) {
                    requestFollow(false, true)
                    return
                }

                if (oldCount === 0 && count === 1) {
                    emptyBurstWatching = true
                    emptyBurstTimer.restart()
                } else if (emptyBurstWatching && count > 1) {
                    suspendEntranceAnimations = true
                    emptyBurstTimer.restart()
                    settleTimer.restart()
                }

                if (autoFollow && !userInteracting) {
                    if (!forceFollowAfterSwitch) requestFollow(true, false)
                }

                if (forceFollowAfterSwitch && !historyLoading && count > 0 && followRetryLeft <= 0) {
                    followRetryLeft = 8
                    followRetryTimer.restart()
                }
            }

            onContentHeightChanged: {
                if (historyLoading) return
                if (batchReloading) {
                    settleTimer.restart()
                    return
                }
                if (!userInteracting) clampContentY()
                if (!gatewayRunning) return
                if (autoFollow && !userInteracting) {
                    if (!forceFollowAfterSwitch) requestFollow(false, false)
                }
                if (forceFollowAfterSwitch && !historyLoading && followRetryLeft <= 0) {
                    followRetryLeft = 60
                    followRetryTimer.restart()
                }
            }

            onHeightChanged: {
                if (historyLoading) return
                if (batchReloading) {
                    settleTimer.restart()
                    return
                }
                if (!userInteracting) clampContentY()
                if (!gatewayRunning) return
                if (autoFollow && !userInteracting) {
                    if (!forceFollowAfterSwitch) requestFollow(false, true)
                }
            }

            Connections {
                target: chatService
                function onHistoryLoadingChanged(loading) {
                    if (loading) {
                        messageList.suspendEntranceAnimations = true
                        messageList.emptyBurstWatching = false
                        emptyBurstTimer.stop()
                        followRetryTimer.stop()
                        messageList.followRetryLeft = 0
                        messageList.pendingFollow = false
                        messageList.pendingFollowAnimated = false
                        messageList.savedWasFollowing = messageList.autoFollow
                        messageList.savedDistanceToEnd = Math.max(
                            0,
                            messageList.maxContentY() - messageList.contentY
                        )
                        return
                    }

                    messageList.suspendEntranceAnimations = false
                    if (messageList.forceFollowAfterSwitch) {
                        messageList.autoFollow = true
                        messageList.followRetryLeft = 60
                        followRetryTimer.restart()
                    } else if (messageList.savedWasFollowing) {
                        messageList.autoFollow = true
                        messageList.requestFollow(false, true)
                    } else {
                        messageList.autoFollow = false
                        messageList.contentY = messageList.maxContentY() - messageList.savedDistanceToEnd
                        messageList.clampContentY()
                    }
                }
            }

            Connections {
                target: sessionService
                function onActiveKeyChanged(_key) {
                    messageList.forceFollowAfterSwitch = true
                    messageList.followRetryLeft = 0
                    followRetryTimer.stop()
                }
            }


            delegate: MessageBubble {
                width: messageList.width
                role: model.role ?? "user"
                content: model.content ?? ""
                status: model.status ?? "done"
                toastFunc: function() { root.messageCopied() }
            }

            // ── Empty state — multi-state onboarding cards ──────────
            Item {
                anchors.centerIn: parent
                width: Math.min(360, messageList.width - 80)
                height: emptyCol.implicitHeight
                visible: messageList.count === 0
                         && !messageList.batchReloading
                         && !messageList.historyLoading
                         && !messageList.forceFollowAfterSwitch

                Column {
                    id: emptyCol
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width
                    spacing: 16

                    // ── State 1: Needs setup (no config) ──
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: configService && configService.needsSetup
                        spacing: 14
                        width: parent.width

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 72; height: 72; radius: 36
                            color: isDark ? "#10FFFFFF" : "#08000000"
                            Image {
                                anchors.centerIn: parent
                                source: "../resources/icons/settings.svg"
                                sourceSize: Qt.size(32, 32)
                                width: 32; height: 32
                                opacity: 0.6
                            }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.empty_setup_title
                            color: textPrimary
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.3
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.empty_setup_hint
                            color: textTertiary
                            font.pixelSize: 14
                            horizontalAlignment: Text.AlignHCenter
                            width: parent.width
                            wrapMode: Text.WordWrap
                        }
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 140; height: 40; radius: radiusMd
                            color: setupBtnHover.containsMouse ? accentHover : accent
                            Behavior on color { ColorAnimation { duration: 150 } }
                            Text {
                                anchors.centerIn: parent
                                text: strings.empty_setup_btn
                                color: "#FFFFFF"
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            MouseArea {
                                id: setupBtnHover
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.openSettings()
                            }
                        }
                    }

                    // ── State 2: Gateway starting ──
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: chatService && chatService.state === "starting"
                                 && !(configService && configService.needsSetup)
                        spacing: 14

                        BusyIndicator {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 48; height: 48
                            running: visible
                            palette.dark: accent
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.empty_starting_hint
                            color: textTertiary
                            font.pixelSize: 15
                            font.weight: Font.Medium
                        }
                    }

                    // ── State 3: Gateway error ──
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: chatService && chatService.state === "error"
                                 && !(configService && configService.needsSetup)
                        spacing: 14
                        width: parent.width

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 72; height: 72; radius: 36
                            color: isDark ? "#18F87171" : "#10F87171"
                            Text {
                                anchors.centerIn: parent
                                text: "!"
                                color: statusError
                                font.pixelSize: 28
                                font.weight: Font.Bold
                            }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.empty_error_hint
                            color: textPrimary
                            font.pixelSize: 18
                            font.weight: Font.DemiBold
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: chatService ? (chatService.lastError || "") : ""
                            color: textTertiary
                            font.pixelSize: 13
                            horizontalAlignment: Text.AlignHCenter
                            width: parent.width
                            wrapMode: Text.WordWrap
                            visible: text !== ""
                        }
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 120; height: 38; radius: radiusMd
                            color: retryBtnHover.containsMouse ? accentHover : accent
                            Behavior on color { ColorAnimation { duration: 150 } }
                            Text {
                                anchors.centerIn: parent
                                text: strings.empty_error_btn
                                color: "#FFFFFF"
                                font.pixelSize: 14
                                font.weight: Font.DemiBold
                            }
                            MouseArea {
                                id: retryBtnHover
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: if (chatService) chatService.start()
                            }
                        }
                    }

                    // ── State 4: Ready (running, no messages yet) ──
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: chatService && chatService.state === "running"
                        spacing: 14

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 72; height: 72; radius: 36
                            color: isDark ? "#10FFFFFF" : "#08000000"
                            Image {
                                anchors.centerIn: parent
                                source: "../resources/icons/chat.svg"
                                sourceSize: Qt.size(32, 32)
                                width: 32; height: 32
                                opacity: 0.6
                            }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.empty_chat_title
                            color: textPrimary
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.3
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.empty_chat_hint
                            color: textTertiary
                            font.pixelSize: 14
                        }
                    }
                    // ── State 5: Idle/Stopped (gateway not started) ──
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: {
                            if (!chatService) return true
                            var s = chatService.state
                            return (s === "idle" || s === "stopped")
                                   && !(configService && configService.needsSetup)
                        }
                        spacing: 14
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 72; height: 72; radius: 36
                            color: isDark ? "#10FFFFFF" : "#08000000"
                            Image {
                                anchors.centerIn: parent
                                source: "../resources/icons/zap.svg"
                                sourceSize: Qt.size(32, 32)
                                width: 32; height: 32
                                opacity: 0.5
                            }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
            text: strings.empty_idle_title
                            color: textPrimary
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.3
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
            text: strings.empty_idle_hint
                            color: textTertiary
                            font.pixelSize: 14
                    }
                }
            }
        }
        }
        // ── Input bar ────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            visible: chatService && chatService.state === "running"
            height: inputRow.implicitHeight + 24
            color: bgSidebar
            radius: 20
            antialiasing: true

            Rectangle {
                anchors { top: parent.top; left: parent.left; right: parent.right }
                height: parent.radius
                color: parent.color
            }

            RowLayout {
                id: inputRow
                anchors {
                    left: parent.left; right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: 20; rightMargin: 16
                }
                spacing: 10

                Rectangle {
                    Layout.fillWidth: true
                    height: Math.min(messageInput.implicitHeight + 20, 140)
                    radius: radiusMd
                    color: bgInput
                    border.color: messageInput.activeFocus ? borderFocus : borderSubtle
                    border.width: messageInput.activeFocus ? 1.5 : 1
                    Behavior on border.color { ColorAnimation { duration: 150 } }

                    // Click anywhere in input box → focus TextArea
                    MouseArea {
                        anchors.fill: parent
                        onPressed: function(mouse) {
                            messageInput.forceActiveFocus()
                            mouse.accepted = false
                        }
                        cursorShape: Qt.IBeamCursor
                    }

                    ScrollView {
                        anchors { fill: parent; topMargin: 6; bottomMargin: 6; leftMargin: 4; rightMargin: 4 }
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded
                        TextArea {
                            id: messageInput
                            placeholderText: strings.chat_placeholder
                            placeholderTextColor: textPlaceholder
                            color: textPrimary
                            background: null
                            wrapMode: TextArea.Wrap
                            font.pixelSize: 15
                            Keys.onReturnPressed: function(event) {
                                if (event.modifiers & Qt.ShiftModifier) {
                                    event.accepted = false
                                } else {
                                    event.accepted = true
                                    sendMessage()
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    width: 40; height: 40; radius: radiusMd
                    property bool canSend: messageInput.text.trim().length > 0
                                          && chatService
                                          && chatService.state === "running"
                    color: sendHover.containsMouse && canSend
                           ? accentHover
                           : (canSend ? accent : (isDark ? "#1A1A26" : "#E5E7EB"))
                    Behavior on color { ColorAnimation { duration: 150 } }

                    Image {
                        anchors.centerIn: parent
                        source: "../resources/icons/send.svg"
                        width: 18; height: 18
                        sourceSize: Qt.size(18, 18)
                        opacity: parent.canSend ? 1.0 : 0.3
                        Behavior on opacity { NumberAnimation { duration: 150 } }
                    }

                    MouseArea {
                        id: sendHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: parent.canSend ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: if (parent.canSend) sendMessage()
                    }
                }
            }
        }
    }


    function sendMessage() {
        var text = messageInput.text.trim()
        if (!text || !chatService) return
        messageList.autoFollow = true
        messageList.requestFollow(true, false)
        chatService.sendMessage(text)
        messageInput.text = ""
    }
}
