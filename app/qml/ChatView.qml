import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    color: "transparent"

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

            model: chatService ? chatService.messages : null

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            onCountChanged: Qt.callLater(scrollToBottom)
            function scrollToBottom() {
                if (count > 0) positionViewAtEnd()
            }

            delegate: MessageBubble {
                width: messageList.width
                role: model.role ?? "user"
                content: model.content ?? ""
                status: model.status ?? "done"
            }

            // Empty state
            Column {
                anchors.centerIn: parent
                visible: messageList.count === 0
                spacing: 16

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "🤖"
                    font.pixelSize: 48
                    opacity: 0.6
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: strings.chat_empty_title
                    color: textSecondary
                    font.pixelSize: 18
                    font.weight: Font.Medium
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: {
                        if (chatService && chatService.state !== "running") {
                            switch (chatService.state) {
                                case "starting": return strings.gateway_starting
                                case "error":    return chatService.lastError || strings.gateway_error
                                default:         return strings.gateway_idle
                            }
                        }
                        return strings.chat_empty_hint
                    }
                    color: textTertiary
                    font.pixelSize: 13
                }
            }
        }

        // ── Gateway status bar ──────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 48
            visible: !chatService || chatService.state !== "running"
            color: bgSidebar

            Row {
                anchors.centerIn: parent
                spacing: 14

                Rectangle {
                    width: 8; height: 8; radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: {
                        if (!chatService) return textTertiary
                        switch (chatService.state) {
                            case "running":  return statusSuccess
                            case "starting": return statusWarning
                            case "error":    return statusError
                            default:         return textTertiary
                        }
                    }
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: {
                        if (!chatService) return strings.gateway_idle
                        switch (chatService.state) {
                            case "starting": return strings.gateway_starting
                            case "error":    return chatService.lastError || strings.gateway_error
                            default:         return strings.gateway_idle
                        }
                    }
                    color: textSecondary
                    font.pixelSize: 13
                }
                Rectangle {
                    width: gwBtnText.implicitWidth + 28
                    height: 34; radius: radiusSm
                    visible: !chatService || chatService.state !== "starting"
                    color: gwBtnHover.containsMouse ? accentHover : accent
                    Behavior on color { ColorAnimation { duration: 150 } }
                    Text {
                        id: gwBtnText
                        anchors.centerIn: parent
                        text: chatService && chatService.state === "running"
                              ? strings.button_restart : strings.button_start_gateway
                        color: "#FFFFFF"
                        font.pixelSize: 13
                        font.weight: Font.Medium
                    }
                    MouseArea {
                        id: gwBtnHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (chatService) {
                                if (chatService.state === "running")
                                    chatService.restart()
                                else
                                    chatService.start()
                            }
                        }
                    }
                }
            }
        }
        // ── Input bar ────────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
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
                    ScrollView {
                        anchors { fill: parent; margins: 10 }
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
                // Send button
                Rectangle {
                    width: 40; height: 40; radius: radiusMd
                    color: sendHover.containsMouse && canSend
                           ? accentHover
                           : (canSend ? accent : (isDark ? "#1A1A26" : "#E5E7EB"))
                    property bool canSend: messageInput.text.trim().length > 0
                                          && chatService
                                          && chatService.state === "running"
                    Behavior on color { ColorAnimation { duration: 150 } }
                    Text {
                        anchors.centerIn: parent
                        text: "↑"
                        color: parent.canSend ? "#FFFFFF" : textTertiary
                        font.pixelSize: 20
                        font.weight: Font.Bold
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
        messageInput.text = ""
    }
}
