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
    property bool _entrancePlayed: false

    height: isSystem ? systemText.height + 16 : bubble.height + 10
    width: parent ? parent.width : 600

    function playEntranceIfAllowed() {
        if (_entrancePlayed) return
        var view = ListView.view
        if (isSystem) return
        if (!view) return
        if (view.suspendEntranceAnimations) return
        if (!view.autoFollow) return
        if (view.dragging || view.flicking || view.moving) return
        if (typeof index === "number" && index !== view.count - 1) return
        _entrancePlayed = true
        bubble.opacity = 0.0
        enterTranslate.y = 10
        entranceAnim.start()
    }

    Component.onCompleted: Qt.callLater(playEntranceIfAllowed)

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
        opacity: 1.0
        transform: Translate { id: enterTranslate; y: 0 }

        color: {
            if (isUser) return hoverHandler.hovered ? accentHover : accent
            return hoverHandler.hovered ? bgCardHover : bgCard
        }

        border.color: isUser ? "transparent" : borderSubtle
        border.width: isUser ? 0 : 1

        Behavior on color { ColorAnimation { duration: 150 } }

        // ── Hover + pointer cursor ───────────────────────
        HoverHandler {
            id: hoverHandler
            cursorShape: Qt.PointingHandCursor
        }

        // ── Hidden TextEdit for clipboard (pure QML, no Python call) ──
        TextEdit {
            id: clipHelper
            visible: false
        }
        // ── Click to copy (z:10 covers Text to block MarkdownText press) ──
        MouseArea {
            id: clickArea
            anchors.fill: parent
            z: 10
            preventStealing: true
            cursorShape: Qt.PointingHandCursor
            onClicked: function(mouse) {
                if (bubble.isTyping || root.content === "") return
                // Check if click hit a link
                var localPt = clickArea.mapToItem(contentText, mouse.x, mouse.y)
                var link = contentText.linkAt(localPt.x, localPt.y)
                if (link) {
                    Qt.openUrlExternally(link)
                    return
                }
                // Copy content via hidden TextEdit
                clipHelper.text = root.content
                clipHelper.selectAll()
                clipHelper.copy()
                clipHelper.deselect()
                copyFlash.opacity = 0.0
                copyFlashAnim.restart()
                if (root.toastFunc) root.toastFunc()
            }
        }

        // ── Copy animation — non-geometric flash (no layout shift) ─────
        Rectangle {
            id: copyFlash
            anchors.fill: parent
            radius: parent.radius
            z: 1
            color: root.isUser ? "#40FFFFFF" : accentGlow
            opacity: 0.0
        }

        SequentialAnimation {
            id: copyFlashAnim
            NumberAnimation {
                target: copyFlash
                property: "opacity"
                from: 0.0
                to: 0.32
                duration: 90
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: copyFlash
                property: "opacity"
                to: 0.0
                duration: 180
                easing.type: Easing.OutCubic
            }
        }
        // ── Entrance animation — fade + slight slide up ────────
        ParallelAnimation {
            id: entranceAnim
            NumberAnimation {
                target: bubble
                property: "opacity"
                to: 1.0
                duration: 160
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: enterTranslate
                property: "y"
                to: 0
                duration: 220
                easing.type: Easing.OutCubic
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

        // ── Message text (read-only display, no mouse handling) ──
        Text {
            id: contentText
            anchors {
                top: parent.top; topMargin: 14
                left: parent.left; leftMargin: 16
                right: parent.right; rightMargin: 16
            }
            text: root.content
            visible: root.content !== ""
            color: root.isUser ? "#FFFFFF" : textPrimary
            font.pixelSize: 15
            wrapMode: Text.Wrap
            textFormat: Text.MarkdownText
            lineHeight: 1.4
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
