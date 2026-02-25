import QtQuick 2.15

Item {
    id: root

    property string role: "user"
    property string content: ""
    property string status: "done"

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
        width: Math.min(contentText.implicitWidth + 32, root.width * 0.75)
        height: contentText.height + 28
        radius: 18

        color: isUser
               ? accent
               : bgCard

        border.color: isUser ? "transparent" : borderSubtle
        border.width: isUser ? 0 : 1

        // Typing indicator dots
        Row {
            anchors.centerIn: parent
            spacing: 6
            visible: root.status === "typing" && root.content === ""

            Repeater {
                model: 3
                delegate: Rectangle {
                    width: 7; height: 7; radius: 4
                    color: accent
                    opacity: 0.4

                    SequentialAnimation on opacity {
                        running: root.status === "typing" && root.content === ""
                        loops: Animation.Infinite
                        PauseAnimation { duration: index * 200 }
                        NumberAnimation { to: 1.0; duration: 350; easing.type: Easing.OutCubic }
                        NumberAnimation { to: 0.3; duration: 350; easing.type: Easing.InCubic }
                        PauseAnimation { duration: (2 - index) * 200 }
                    }
                }
            }
        }

        // Message text
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
            lineHeight: 1.5
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
