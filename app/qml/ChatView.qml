import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    color: "transparent"

    readonly property int composerMinHeight: 44
    readonly property int composerMaxHeight: 140
    readonly property int composerScrollInset: 12
    readonly property int composerBottomSafeGap: 4
    readonly property real composerFieldRadius: composerMinHeight / 2
    readonly property int chatTopSafeInset: windowContentInsetTop
    readonly property int chatTopContentGap: spacingMd
    readonly property int chatSideInset: windowContentInsetSide + spacingSm
    readonly property int chatIdleBottomGap: windowContentInsetBottom
    readonly property int composerBottomMargin: Math.max(spacingXs, windowContentInsetBottom - spacingSm)
    readonly property int composerDockGap: windowContentInsetBottom
    readonly property int composerEdgeInset: spacingSm
    readonly property bool hasSessionService: typeof sessionService !== "undefined" && sessionService !== null
    readonly property bool activeSessionReadOnly: hasSessionService ? sessionService.activeSessionReadOnly : false
    signal messageCopied()

    // Message list and composer share one inset source so content never gets
    // visually clipped by the window edge or by the floating composer itself.
    ListView {
        id: messageList
        objectName: "chatMessageList"
        anchors.fill: parent
        anchors.leftMargin: root.chatSideInset
        anchors.rightMargin: root.chatSideInset
        anchors.bottomMargin: composerBar.listBottomInset
        clip: true
        spacing: spacingLg
        topMargin: root.chatTopSafeInset + root.chatTopContentGap
        bottomMargin: 0
        focus: root.visible
        activeFocusOnTab: true
        boundsBehavior: Flickable.StopAtBounds
        cacheBuffer: 20000
        reuseItems: false
        highlightFollowsCurrentItem: false
        highlightRangeMode: ListView.NoHighlightRange
        verticalLayoutDirection: ListView.TopToBottom

        model: chatService ? chatService.messages : null

        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        // ── Smart follow / anti-flicker state ──────────────────────
        property bool historyLoading: chatService ? chatService.historyLoading : false
        readonly property string activeSessionKey: sessionService ? sessionService.activeKey : ""
        property string renderedSessionKey: activeSessionKey
        readonly property bool sessionReady: chatService ? chatService.activeSessionReady : false
        readonly property bool sessionHasMessages: chatService ? chatService.activeSessionHasMessages : false
        readonly property real keyboardLineStep: Math.max(48, Math.round(height * 0.08))
        readonly property real keyboardPageStep: Math.max(keyboardLineStep, Math.round(height * 0.9))
        property real pendingRestoreContentY: -1
        property bool pendingRestoreAtEnd: false

        function positionAfterLayout() {
            if (count <= 0) return
            forceLayout()
            positionViewAtEnd()
        }

        function maxContentY() {
            return Math.max(originY, originY + contentHeight - height)
        }

        function minContentY() {
            return originY
        }

        function isNearEnd() {
            return maxContentY() - contentY <= Math.max(24, keyboardLineStep)
        }

        function scrollBy(delta) {
            if (count <= 0) return
            var minY = minContentY()
            var maxY = maxContentY()
            var nextY = contentY + delta
            if (nextY <= minY) {
                positionViewAtBeginning()
                return
            }
            if (nextY >= maxY) {
                positionAfterLayout()
                return
            }
            contentY = Math.max(minY, Math.min(maxY, nextY))
        }

        function handleNavigationKey(event) {
            if (!event || messageInput.activeFocus || count <= 0) return false

            switch (event.key) {
            case Qt.Key_Up:
                scrollBy(-keyboardLineStep)
                return true
            case Qt.Key_Down:
                scrollBy(keyboardLineStep)
                return true
            case Qt.Key_PageUp:
                scrollBy(-keyboardPageStep)
                return true
            case Qt.Key_PageDown:
                scrollBy(keyboardPageStep)
                return true
            case Qt.Key_Home:
                positionViewAtBeginning()
                return true
            case Qt.Key_End:
                positionAfterLayout()
                return true
            default:
                return false
            }
        }

        function captureViewportBeforeReset() {
            pendingRestoreAtEnd = isNearEnd()
            pendingRestoreContentY = contentY
        }

        function clearPendingViewportRestore() {
            pendingRestoreContentY = -1
            pendingRestoreAtEnd = false
        }

        function restoreViewportAfterReset() {
            if (pendingRestoreContentY < 0 && !pendingRestoreAtEnd) return

            Qt.callLater(function() {
                if (messageList.count <= 0) {
                    messageList.clearPendingViewportRestore()
                    return
                }

                messageList.forceLayout()
                if (messageList.pendingRestoreAtEnd) {
                    messageList.positionViewAtEnd()
                } else {
                    messageList.contentY = Math.max(
                        messageList.minContentY(),
                        Math.min(messageList.maxContentY(), messageList.pendingRestoreContentY)
                    )
                }
                messageList.clearPendingViewportRestore()
            })
        }

        function messageMetaAt(row) {
            if (row < 0 || !model) return null
            var idx = model.index(row, 0)
            return {
                role: model.data(idx, Qt.UserRole + 2) || "",
                status: model.data(idx, Qt.UserRole + 5) || ""
            }
        }

        function applyScrollToEnd() {
            positionAfterLayout()
            Qt.callLater(function() {
                if (messageList.historyLoading) return
                messageList.positionAfterLayout()
            })
        }

        function forceFollowToEnd() {
            if (historyLoading || count <= 0) return
            applyScrollToEnd()
        }

        function shouldFollowOnAppend(row) {
            var message = messageMetaAt(row)
            if (!message) return false

            return message.role === "user"
                || message.role === "assistant"
                || message.role === "system"
                || message.status === "typing"
        }

        function shouldFollowOnStatusUpdate(row, status) {
            if (status !== "done" && status !== "error") return false
            var message = messageMetaAt(row)
            if (!message) return false
            return message.role === "assistant" || message.role === "system"
        }

        Connections {
            target: chatService
            function onHistoryLoadingChanged(loading) {
                if (loading) {
                    messageList.cancelFlick()
                    return
                }

                messageList.forceFollowToEnd()
            }

            function onMessageAppended(_row) {
                if (messageList.shouldFollowOnAppend(_row)) {
                    messageList.forceFollowToEnd()
                }
            }

            function onStatusUpdated(_row, _status) {
                if (messageList.shouldFollowOnStatusUpdate(_row, _status)) {
                    messageList.forceFollowToEnd()
                }
            }
        }

        Connections {
            target: messageList.model
            ignoreUnknownSignals: true

            function onModelAboutToBeReset() {
                if (messageList.activeSessionKey === messageList.renderedSessionKey) {
                    messageList.captureViewportBeforeReset()
                } else {
                    messageList.clearPendingViewportRestore()
                }
            }

            function onModelReset() {
                var switchedSession = messageList.activeSessionKey !== messageList.renderedSessionKey
                messageList.renderedSessionKey = messageList.activeSessionKey
                if (switchedSession) {
                    Qt.callLater(function() {
                        messageList.forceFollowToEnd()
                    })
                    return
                }
                messageList.restoreViewportAfterReset()
            }
        }

        Connections {
            target: chatService
            ignoreUnknownSignals: true

            function onSessionViewApplied(key) {
                Qt.callLater(function() {
                    messageList.renderedSessionKey = key || messageList.activeSessionKey
                    messageList.forceActiveFocus()
                    messageList.forceFollowToEnd()
                })
            }
        }

        Keys.onPressed: function(event) {
            if (messageList.handleNavigationKey(event))
                event.accepted = true
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
                showDateDivider: (model.dividerText ?? "") !== ""
                dateDividerText: model.dividerText ?? ""
                toastFunc: function() { root.messageCopied() }
            }

        // ── Empty state — multi-state onboarding cards ──────────
        Item {
            id: historyLoadingState
            anchors.centerIn: parent
            width: Math.min(320, messageList.width - 80)
            height: loadingCol.implicitHeight
            visible: messageList.count === 0 && messageList.historyLoading

            Column {
                id: loadingCol
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 12

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 68
                    height: 68
                    radius: 34
                    color: isDark ? "#16FFFFFF" : "#10FFB33D"
                    border.color: isDark ? "#22FFFFFF" : borderSubtle

                    LoadingOrbit {
                        anchors.centerIn: parent
                        width: 38
                        height: 38
                        running: historyLoadingState.visible
                        haloOpacity: 0.16
                    }
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: strings.chat_loading_history
                    color: textTertiary
                    font.pixelSize: typeMeta
                    font.weight: weightDemiBold
                    font.letterSpacing: letterWide
                }
            }
        }

        Item {
            anchors.centerIn: parent
            width: Math.min(360, messageList.width - 80)
            height: emptyCol.implicitHeight
            visible: messageList.count === 0
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
                        color: chatEmptyIconBg
                        border.width: isDark ? 0 : 1
                        border.color: chatEmptyIconBorder
                        Image {
                            objectName: "chatEmptySetupIcon"
                            anchors.centerIn: parent
                            source: themedIconSource("settings")
                            sourceSize: Qt.size(34, 34)
                            width: 34; height: 34
                            opacity: isDark ? 0.72 : 0.96
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_setup_title
                        color: textPrimary
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                        font.letterSpacing: 0.3
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_setup_hint
                        color: textTertiary
                        font.pixelSize: typeButton
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width
                        wrapMode: Text.WordWrap
                    }
                }

                // ── State 2: Gateway starting ──
                Column {
                    id: gatewayStartingState
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: chatService && chatService.state === "starting"
                             && !(configService && configService.needsSetup)
                    spacing: 14

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 74
                        height: 74
                        radius: 37
                        color: isDark ? "#16FFFFFF" : "#10FFB33D"
                        border.color: isDark ? "#22FFFFFF" : borderSubtle

                        LoadingOrbit {
                            anchors.centerIn: parent
                            width: 42
                            height: 42
                            running: gatewayStartingState.visible
                            color: statusWarning
                            secondaryColor: Qt.lighter(statusWarning, 1.16)
                            haloColor: accentGlow
                            haloOpacity: 0.18
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_starting_hint
                        color: textTertiary
                        font.pixelSize: typeMeta
                        font.weight: weightMedium
                        font.letterSpacing: letterWide
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
                        color: chatErrorBadgeBg
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
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: chatService ? (chatService.lastError || "") : ""
                        color: textTertiary
                        font.pixelSize: typeLabel
                        horizontalAlignment: Text.AlignHCenter
                        width: parent.width
                        wrapMode: Text.WordWrap
                        visible: text !== ""
                    }
                    PillActionButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 120
                        minHeight: 38
                        text: strings.empty_error_btn
                        onClicked: if (chatService) chatService.start()
                    }
                }

                // ── State 4: Ready (running, no messages yet) ──
                Column {
                    id: readyEmptyState
                    objectName: "chatEmptyReadyState"
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: chatService && messageList.sessionReady
                             && !messageList.sessionHasMessages
                             && chatService.state !== "starting"
                             && chatService.state !== "error"
                    spacing: 14

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 72; height: 72; radius: 36
                        color: chatEmptyIconBg
                        border.width: isDark ? 0 : 1
                        border.color: chatEmptyIconBorder
                        Image {
                            objectName: "chatEmptyReadyIcon"
                            anchors.centerIn: parent
                            source: themedIconSource("chat")
                            sourceSize: Qt.size(34, 34)
                            width: 34; height: 34
                            opacity: isDark ? 0.68 : 0.94
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_chat_title
                        color: textPrimary
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                        font.letterSpacing: 0.3
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: chatService && chatService.state === "running"
                              ? strings.empty_chat_hint
                              : strings.empty_chat_idle_hint
                        color: textTertiary
                        font.pixelSize: typeButton
                    }
                }

                // ── State 5: Idle/Stopped (gateway not started) ──
                Column {
                    id: idleEmptyState
                    objectName: "chatEmptyIdleState"
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: {
                        if (!chatService) return true
                        var s = chatService.state
                        return (s === "idle" || s === "stopped")
                               && !messageList.sessionReady
                               && !(configService && configService.needsSetup)
                    }
                    spacing: 14

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 72; height: 72; radius: 36
                        color: chatEmptyIconBg
                        border.width: isDark ? 0 : 1
                        border.color: chatEmptyIconBorder
                        Image {
                            objectName: "chatEmptyIdleIcon"
                            anchors.centerIn: parent
                            source: themedIconSource("zap")
                            sourceSize: Qt.size(34, 34)
                            width: 34; height: 34
                            opacity: isDark ? 0.7 : 0.96
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_idle_title
                        color: textPrimary
                        font.pixelSize: typeTitle
                        font.weight: weightDemiBold
                        font.letterSpacing: 0.3
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.empty_idle_hint
                        color: textTertiary
                        font.pixelSize: typeButton
                    }
                }
            }
        }
    }

    // ── Input bar ────────────────────────────────────────────────────
    Item {
        id: composerBar
        readonly property bool active: chatService && chatService.state === "running" && !root.activeSessionReadOnly
        readonly property real visibleHeight: inputRow.implicitHeight + 24
        readonly property real listBottomInset: active
                                             ? visibleHeight + root.composerBottomMargin + root.composerDockGap
                                             : root.chatIdleBottomGap

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: root.chatSideInset + root.composerEdgeInset
        anchors.rightMargin: root.chatSideInset + root.composerEdgeInset
        anchors.bottomMargin: root.composerBottomMargin
        height: visibleHeight
        enabled: active
        opacity: active ? 1.0 : 0.0
        scale: active ? 1.0 : 0.992
        transform: Translate {
            y: composerBar.active ? 0 : 22
            Behavior on y { NumberAnimation { duration: motionPanel; easing.type: easeStandard } }
        }

        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

        RowLayout {
            id: inputRow
            anchors {
                left: parent.left; right: parent.right
                verticalCenter: parent.verticalCenter
                leftMargin: 18; rightMargin: 18
            }
            spacing: 0

            Rectangle {
                id: composerField
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                readonly property bool focused: messageInput.activeFocus
                readonly property bool hovered: messageInput.hovered
                readonly property color fillColor: focused ? bgInputFocus : (hovered ? bgInputHover : bgInput)
                readonly property color strokeColor: focused ? borderFocus : (hovered ? borderDefault : borderSubtle)
                readonly property real strokeWidth: focused ? 1.35 : 1.0
                readonly property real fieldScale: focused ? 1.006 : (hovered ? 1.003 : 1.0)
                Layout.preferredHeight: Math.min(
                                          Math.max(
                                              messageInput.contentHeight
                                              + messageInput.topPadding
                                              + messageInput.bottomPadding
                                              + root.composerScrollInset,
                                              root.composerMinHeight
                                          ),
                                          root.composerMaxHeight
                                      )
                radius: root.composerFieldRadius
                color: fillColor
                border.color: strokeColor
                border.width: strokeWidth
                clip: true
                scale: fieldScale
                Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                Behavior on border.width { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                Rectangle {
                    id: innerSendButton
                    width: sizeButton
                    height: sizeButton
                    radius: width / 2
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    property bool canSend: messageInput.text.trim().length > 0
                                          && chatService
                                          && chatService.state === "running"
                    color: sendHover.containsMouse && canSend
                           ? accentHover
                           : (canSend ? accent : chatComposerSendDisabled)
                    border.width: canSend ? 0 : 1
                    border.color: canSend ? "transparent" : borderSubtle
                    scale: sendHover.pressed && canSend
                           ? motionPressScaleStrong
                           : (sendHover.containsMouse && canSend ? motionHoverScaleSubtle : 1.0)
                    antialiasing: true
                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: chatComposerSendHighlight }
                            GradientStop { position: 1.0; color: "#00FFFFFF" }
                        }
                        opacity: parent.canSend ? (sendHover.containsMouse ? 0.82 : 0.66) : 0.0
                        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    }

                    Image {
                        anchors.centerIn: parent
                        source: "../resources/icons/send.svg"
                        width: 20
                        height: 20
                        sourceSize: Qt.size(20, 20)
                        opacity: parent.canSend ? 1.0 : 0.3
                        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    }

                    MouseArea {
                        id: sendHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: parent.canSend ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: if (parent.canSend) sendMessage()
                    }
                }

                ScrollView {
                    id: inputScroll
                    anchors.left: parent.left
                    anchors.right: innerSendButton.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.rightMargin: 8
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded

                    TextArea {
                        id: messageInput
                        objectName: "chatMessageInput"
                        property bool baoClickAwayEditor: true
                        hoverEnabled: true
                        placeholderText: strings.chat_placeholder
                        placeholderTextColor: textPlaceholder
                        color: textPrimary
                        background: null
                        wrapMode: TextArea.Wrap
                        leftPadding: sizeFieldPaddingX
                        rightPadding: sizeFieldPaddingX
                        topPadding: 15
                        bottomPadding: 5
                        font.pixelSize: typeBody
                        selectionColor: textSelectionBg
                        selectedTextColor: textSelectionFg

                        onCursorPositionChanged: {
                            if (!activeFocus || cursorPosition !== length) return
                            var flick = inputScroll.contentItem
                            if (!flick) return
                            if (flick.contentHeight > flick.height)
                                flick.contentY = flick.contentHeight - flick.height + root.composerBottomSafeGap
                        }

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

        }
    }

    function sendMessage() {
        var text = messageInput.text.trim()
        if (!text || !chatService) return
        chatService.sendMessage(text)
        messageInput.text = ""
    }
}
