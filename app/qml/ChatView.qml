import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    color: "transparent"

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
            cacheBuffer: 400
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
                _modelJustChanged = true
                // Skip positioning during history loading - let onHistoryLoadingChanged handle it
                if (historyLoading) return
                // Immediately position at end if autoFollow is true, no delay
                if (autoFollow && count > 0) {
                    animateProgrammaticScroll = false
                    positionViewAtEnd()
                    contentY = maxContentY()
                }
            }

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            // ── Smart follow / anti-flicker state ──────────────────────
            property real followThresholdPx: 40
            property bool autoFollow: true
            property bool userInteracting: dragging || flicking
            property bool historyLoading: chatService ? chatService.historyLoading : false
            property bool gatewayRunning: chatService ? chatService.state === "running" : false
            property bool animateProgrammaticScroll: false
            property bool _modelJustChanged: false
            property bool batchReloading: false
            property real savedDistanceToEnd: 0
            property bool savedWasFollowing: true

            property bool pendingFollow: false
            property bool pendingFollowAnimated: false
            property bool emptyBurstWatching: false

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
                if (!animated) animateProgrammaticScroll = false
                if (!userInteracting) {
                    clampContentY()
                    if (!atYEnd) contentY = maxContentY()
                }
                animateProgrammaticScroll = false
            }

            function beginBatchReload() {
                batchReloading = true
                suspendEntranceAnimations = true
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
                    if (messageList.batchReloading) {
                        messageList.finishBatchReload()
                        return
                    }
                    if (messageList.pendingFollow && messageList.autoFollow && !messageList.userInteracting) {
                        messageList.applyScrollToEnd(messageList.pendingFollowAnimated)
                    }
                    messageList.pendingFollow = false
                    messageList.pendingFollowAnimated = false
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
            }

            onContentYChanged: {
                // Empty - no longer tracking reading position
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

            }

            onContentHeightChanged: {
                if (historyLoading) return
                if (batchReloading) {
                    settleTimer.restart()
                    return
                }
                // If model just changed and autoFollow is true, ensure we're at the end
                if (_modelJustChanged && autoFollow && count > 0) {
                    animateProgrammaticScroll = false
                    contentY = maxContentY()
                    _modelJustChanged = false
                    return
                }
                if (!userInteracting) clampContentY()
            }

            onHeightChanged: {
                if (historyLoading) return
                if (batchReloading) {
                    settleTimer.restart()
                    return
                }
                if (!userInteracting) clampContentY()
            }

            Connections {
                target: chatService
                function onHistoryLoadingChanged(loading) {
                    if (loading) {
                        messageList.suspendEntranceAnimations = true
                        messageList.emptyBurstWatching = false
                        emptyBurstTimer.stop()
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
                    if (messageList.savedWasFollowing) {
                        messageList.autoFollow = true
                        // Only reposition if not already at end
                        if (messageList.count > 0 && !messageList.atYEnd) {
                            messageList.animateProgrammaticScroll = false
                            messageList.contentY = messageList.maxContentY()
                        }
                    } else {
                        messageList.autoFollow = false
                        var targetY = messageList.maxContentY() - messageList.savedDistanceToEnd
                        // Only reposition if position actually changed
                        if (Math.abs(messageList.contentY - targetY) > 1) {
                            messageList.contentY = targetY
                            messageList.clampContentY()
                        }
                }
            }
            }

            Connections {
                target: sessionService
                function onActiveKeyChanged(_key) {
                    // Session switch will trigger onModelChanged, which handles positioning
                }
            }


            delegate: MessageBubble {
                width: messageList.width
                role: model.role ?? "assistant"
                content: model.content ?? ""
                format: model.format ?? "plain"
                status: model.status ?? "done"
                messageId: model.id ?? -1
                messageRow: index
                entranceStyle: model.entranceStyle ?? "none"
                entrancePending: model.entrancePending ?? false
                entranceConsumed: model.entranceConsumed ?? true
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
