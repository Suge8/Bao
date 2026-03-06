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
            spacing: spacingLg
            topMargin: spacingXl - 4
            bottomMargin: 0
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

            function applyScrollToEnd() {
                if (count <= 0) return
                positionViewAtEnd()
                Qt.callLater(function() {
                    if (messageList.count <= 0) return
                    messageList.positionViewAtEnd()
                })
            }

            function forceFollowToEnd() {
                if (historyLoading || count <= 0) return
                applyScrollToEnd()
            }

            function shouldFollowOnAppend(row) {
                if (row < 0 || !messagesModel) return false
                var idx = messagesModel.index(row, 0)
                var role = messagesModel.data(idx, Qt.UserRole + 2) || ""
                var status = messagesModel.data(idx, Qt.UserRole + 5) || ""

                // Only follow on AI/system instantaneous events.
                if (role === "assistant") return true
                if (role === "system") return true
                return status === "typing"
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
                    if (_status === "done" || _status === "error") {
                        messageList.forceFollowToEnd()
                    }
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
                width: Math.min(320, messageList.width - 80)
                height: loadingCol.implicitHeight
                visible: messageList.count === 0 && messageList.historyLoading

                Column {
                    id: loadingCol
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 12

                    BusyIndicator {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 40
                        height: 40
                        running: visible
                        palette.dark: accent
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: strings.chat_loading_history
                        color: textTertiary
                        font.pixelSize: typeButton
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
                            font.pixelSize: typeBody
                            font.weight: weightMedium
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
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 120; height: 38; radius: radiusMd
                            color: retryBtnHover.containsMouse ? accentHover : accent
                            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                            Text {
                                anchors.centerIn: parent
                                text: strings.empty_error_btn
                                color: "#FFFFFF"
                                font.pixelSize: typeButton
                                font.weight: weightDemiBold
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
                            color: chatEmptyIconBg
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
                            font.pixelSize: typeTitle
                            font.weight: weightDemiBold
                            font.letterSpacing: 0.3
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: strings.empty_chat_hint
                            color: textTertiary
                            font.pixelSize: typeButton
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
                            color: chatEmptyIconBg
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
        Rectangle {
            id: composerBar
            Layout.fillWidth: true
            visible: chatService && chatService.state === "running"
            Layout.preferredHeight: inputRow.implicitHeight + 24
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
                    id: composerField
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    readonly property bool focused: messageInput.activeFocus
                    readonly property bool hovered: messageInput.hovered
                    readonly property color fillColor: focused ? bgInputFocus : (hovered ? bgInputHover : bgInput)
                    readonly property color strokeColor: focused ? borderFocus : (hovered ? borderDefault : borderSubtle)
                    readonly property real strokeWidth: focused ? 1.5 : (hovered ? 1.25 : 1)
                    readonly property real fieldScale: focused ? motionSelectionScaleHover : 1.0
                    readonly property real auraOpacity: focused ? motionSelectionAuraOpacity : (hovered ? motionSelectionAuraOpacity * 0.35 : 0.0)
                    readonly property real highlightOpacity: focused ? 0.9 : (hovered ? 0.5 : 0.0)
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
                    radius: radiusMd
                    color: fillColor
                    border.color: strokeColor
                    border.width: strokeWidth
                    scale: fieldScale
                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on border.width { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: -4
                        radius: parent.radius + 4
                        color: accentGlow
                        opacity: composerField.auraOpacity
                        scale: composerField.focused ? 1.0 : motionSelectionAuraHiddenScale
                        z: -1
                        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                        Behavior on scale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
                    }

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: chatComposerSendHighlight }
                            GradientStop { position: 0.5; color: "#10FFFFFF" }
                            GradientStop { position: 1.0; color: "#00FFFFFF" }
                        }
                        opacity: composerField.highlightOpacity
                        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    }

                    ScrollView {
                        id: inputScroll
                        anchors.fill: parent
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AsNeeded
                        TextArea {
                            id: messageInput
                            hoverEnabled: true
                            placeholderText: strings.chat_placeholder
                            placeholderTextColor: textPlaceholder
                            color: textPrimary
                            background: null
                            wrapMode: TextArea.Wrap
                            leftPadding: sizeFieldPaddingX
                            rightPadding: sizeFieldPaddingX
                            topPadding: 13
                            bottomPadding: 7
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

                Rectangle {
                    Layout.alignment: Qt.AlignVCenter
                    implicitWidth: sizeButton
                    implicitHeight: sizeButton
                    radius: implicitWidth / 2
                    property bool canSend: messageInput.text.trim().length > 0
                                          && chatService
                                          && chatService.state === "running"
                    antialiasing: true
                    color: sendHover.containsMouse && canSend
                           ? accentHover
                           : (canSend ? accent : chatComposerSendDisabled)
                    border.width: canSend ? 0 : 1
                    border.color: canSend ? "transparent" : borderSubtle
                    scale: sendHover.pressed && canSend
                           ? motionPressScaleStrong
                           : (sendHover.containsMouse && canSend ? motionHoverScaleSubtle : 1.0)
                    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on border.color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

                    Rectangle {
                        anchors.centerIn: parent
                        width: parent.width + 10
                        height: parent.height + 10
                        radius: width / 2
                        color: chatComposerSendGlow
                        opacity: parent.canSend ? (sendHover.containsMouse ? 0.22 : 0.08) : 0.0
                        z: -1
                        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    }

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: chatComposerSendHighlight }
                            GradientStop { position: 1.0; color: "#00FFFFFF" }
                        }
                        opacity: parent.canSend ? (sendHover.containsMouse ? 1.0 : 0.82) : 0.0
                        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                    }

                    Image {
                        anchors.centerIn: parent
                        source: "../resources/icons/send.svg"
                        width: 20; height: 20
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
            }
        }
    }


    function sendMessage() {
        var text = messageInput.text.trim()
        if (!text || !chatService) return
        chatService.sendMessage(text)
        messageList.forceFollowToEnd()
        messageInput.text = ""
    }
}
