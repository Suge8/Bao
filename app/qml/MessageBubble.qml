import QtQuick 2.15

Item {
    id: root

    property string role: "user"
    property string content: ""
    property string status: "done"

    // Toast callback — set by parent (ChatView)
    property var toastFunc: null

    property bool isUser: role === "user"
    property bool isSystem: role === "system"

    height: isSystem ? systemText.height + 16 : bubble.height + 10
    width: parent ? parent.width : 600

    // ── System message (centered, no bubble) ──────────────────────
    Text {
        id: systemText
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top; anchors.topMargin: 8
        width: root.width * 0.85
        visible: isSystem
        text: root.content
        color: root.status === "error" ? statusError : textTertiary
        font.pixelSize: 13
        font.italic: true
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        lineHeight: 1.4
    }

    // ── Hidden metrics text (no anchors to bubble → breaks binding loop) ──
    Text {
        id: contentMetrics
        text: root.content
        font.pixelSize: 15
        textFormat: Text.MarkdownText
        visible: false
    }

    // ── Chat bubble (user / assistant) ────────────────────────────
    Rectangle {
        id: bubble
        visible: !isSystem
        anchors {
            right: isUser ? parent.right : undefined
            left: isUser ? undefined : parent.left
            rightMargin: isUser ? 20 : 0
            leftMargin: isUser ? 0 : 20
            top: parent.top
            topMargin: 5
        }
        property bool isTyping: root.status === "typing" && root.content === ""
        width: isTyping ? 72 : Math.min(contentMetrics.implicitWidth + 32, root.width * 0.75)
        height: isTyping ? 42 : contentText.contentHeight + 28
        radius: 18
        scale: 1.0
        transformOrigin: Item.Center

        color: {
            if (isUser) return hoverHandler.hovered ? accentHover : accent
            return hoverHandler.hovered ? bgCardHover : bgCard
        }

        border.color: isUser ? "transparent" : borderSubtle
        border.width: isUser ? 0 : 1

        Behavior on color { ColorAnimation { duration: 150 } }

        // ── Hover detection (non-blocking) ───────────────────────
        HoverHandler {
            id: hoverHandler
        }

        // ── Padding click area (behind TextEdit — only receives clicks on margins) ──
        MouseArea {
            id: paddingClickArea
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            hoverEnabled: true
            onClicked: {
                if (bubble.isTyping || root.content === "") return
                clipHelper.text = root.content
                clipHelper.selectAll()
                clipHelper.copy()
                clipHelper.deselect()
                clickAnim.start()
                if (root.toastFunc) root.toastFunc()
            }
        }

        // Hidden TextEdit for clipboard access
        TextEdit {
            id: clipHelper
            visible: false
        }

        // ── Click animation — subtle scale pulse ─────────────────
        SequentialAnimation {
            id: clickAnim
            NumberAnimation {
                target: bubble; property: "scale"
                to: 0.97; duration: 80
                easing.type: Easing.OutQuad
            }
            NumberAnimation {
                target: bubble; property: "scale"
                to: 1.0; duration: 200
                easing.type: Easing.OutBack
            }
        }

        // ── Typing indicator — elastic pulse dots ──────────────────
        Row {
            anchors.centerIn: parent
            spacing: 5
            visible: bubble.isTyping

            Repeater {
                model: 3
                delegate: Rectangle {
                    id: dot
                    width: 6; height: 6; radius: 3
                    color: isDark ? "#8A8AA0" : "#9CA3AF"
                    opacity: 0.45
                    scale: 1.0
                    transformOrigin: Item.Center

                    SequentialAnimation on scale {
                        running: bubble.isTyping
                        loops: Animation.Infinite
                        PauseAnimation { duration: index * 160 }
                        NumberAnimation { to: 1.5; duration: 320; easing.type: Easing.OutBack }
                        NumberAnimation { to: 1.0; duration: 280; easing.type: Easing.InOutQuad }
                        PauseAnimation { duration: (2 - index) * 160 + 400 }
                    }

                    SequentialAnimation on opacity {
                        running: bubble.isTyping
                        loops: Animation.Infinite
                        PauseAnimation { duration: index * 160 }
                        NumberAnimation { to: 1.0; duration: 320; easing.type: Easing.OutCubic }
                        NumberAnimation { to: 0.45; duration: 280; easing.type: Easing.InCubic }
                        PauseAnimation { duration: (2 - index) * 160 + 400 }
                    }
                }
            }
        }

        // ── Message text (selectable + clickable links) ──────────
        TextEdit {
            id: contentText
            anchors {
                top: parent.top; topMargin: 14
                left: parent.left; leftMargin: 16
                right: parent.right; rightMargin: 16
            }
            text: root.content
            visible: root.content !== ""
            color: root.isUser ? "#FFFFFF" : textPrimary
            selectedTextColor: root.isUser ? accent : "#FFFFFF"
            selectionColor: root.isUser ? "#FFFFFF" : accent
            font.pixelSize: 15
            wrapMode: TextEdit.Wrap
            textFormat: TextEdit.MarkdownText
            readOnly: true
            selectByMouse: true
            activeFocusOnPress: true

            onLinkActivated: function(link) {
                Qt.openUrlExternally(link)
            }

        }

        // Error tint
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: "#15F87171"
            visible: root.status === "error"
        }
    }
}
