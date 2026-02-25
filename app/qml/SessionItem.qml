import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root

    property string sessionKey: ""
    property string sessionTitle: ""
    property bool isActive: false
    signal selected()
    signal deleteRequested()

    height: 38
    radius: radiusSm
    color: isActive
           ? accentMuted
           : (hoverArea.containsMouse ? (isDark ? "#08FFFFFF" : "#06000000") : "transparent")

    Behavior on color { ColorAnimation { duration: 150 } }

    Row {
        anchors {
            verticalCenter: parent.verticalCenter
            left: parent.left; right: deleteBtn.left
            leftMargin: 12; rightMargin: 6
        }
        spacing: 8

        Text {
            text: "💬"
            font.pixelSize: 12
            anchors.verticalCenter: parent.verticalCenter
            opacity: root.isActive ? 1.0 : 0.5
        }

        Text {
            text: root.sessionTitle
            color: root.isActive ? textPrimary : textSecondary
            font.pixelSize: 13
            font.weight: root.isActive ? Font.Medium : Font.Normal
            elide: Text.ElideRight
            width: parent.width - 28
            anchors.verticalCenter: parent.verticalCenter

            Behavior on color { ColorAnimation { duration: 150 } }
        }
    }

    // Delete button — only visible on hover
    Rectangle {
        id: deleteBtn
        anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 8 }
        width: 24; height: 24; radius: 6
        color: deleteHover.containsMouse ? "#20F87171" : "transparent"
        visible: hoverArea.containsMouse || deleteHover.containsMouse
        Behavior on color { ColorAnimation { duration: 120 } }

        Text {
            anchors.centerIn: parent
            text: "✕"
            color: isDark ? "#F87171" : "#DC2626"
            font.pixelSize: 10
            font.weight: Font.Medium
        }

        MouseArea {
            id: deleteHover
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: function(mouse) {
                mouse.accepted = true
                root.deleteRequested()
            }
        }
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.selected()
    }
}
