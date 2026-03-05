import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root

    property string sessionKey: ""
    property string sessionTitle: ""
    property bool isActive: false
    property bool dimmed: false
    property bool hasUnread: false
    signal selected()
    signal deleteRequested()

    height: 38
    radius: radiusSm
    color: isActive
           ? (isDark ? "#4AFF951F" : "#30FF951F")
           : (hoverArea.containsMouse ? (isDark ? "#08FFFFFF" : "#06000000") : "transparent")
    border.width: isActive ? 1 : 0
    border.color: isActive ? (isDark ? "#A0FF951F" : "#85FF951F") : "transparent"
    opacity: dimmed ? (isActive ? 0.9 : 0.6) : 1.0

    Behavior on color { ColorAnimation { duration: 150 } }
    Behavior on opacity { NumberAnimation { duration: 150 } }

    HoverHandler { id: rowHover }

    Row {
        anchors {
            verticalCenter: parent.verticalCenter
            left: parent.left
            right: deleteBtn.left
            leftMargin: 12
            rightMargin: 10
        }
        spacing: 8

        Rectangle {
            id: leadingIcon
            width: 20
            height: 20
            radius: 10
            color: root.isActive ? (isDark ? "#5AFF951F" : "#3DFF951F") : (isDark ? "#10FFFFFF" : "#12000000")
            border.width: 1
            border.color: root.isActive ? accentGlow : borderSubtle
            anchors.verticalCenter: parent.verticalCenter

            Image {
                anchors.centerIn: parent
                source: "../resources/icons/chat.svg"
                sourceSize: Qt.size(12, 12)
                width: 12
                height: 12
                opacity: root.isActive ? 1.0 : 0.85
            }
        }

        Text {
            text: root.sessionTitle
            color: root.isActive ? textPrimary : textSecondary
            font.pixelSize: 13
            font.weight: root.isActive ? Font.Medium : Font.Normal
            elide: Text.ElideRight
            width: Math.max(0, parent.width - leadingIcon.width - 12)
            anchors.verticalCenter: parent.verticalCenter

            Behavior on color { ColorAnimation { duration: 150 } }
        }
    }

    Rectangle {
        id: deleteBtn
        z: 2
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: 8
        width: 30
        height: 30
        radius: 9
        color: deleteHover.containsMouse ? (isDark ? "#28F87171" : "#22F87171") : (isDark ? "#14FFFFFF" : "#10000000")
        border.width: 1
        border.color: deleteHover.containsMouse ? "#66F87171" : (isDark ? "#2AFFFFFF" : "#23000000")
        scale: deleteHover.containsMouse ? 1.04 : 1.0
        visible: rowHover.hovered || deleteHover.containsMouse
        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on scale { NumberAnimation { duration: 120 } }

        Text {
            anchors.centerIn: parent
            text: "✕"
            color: isDark ? "#F87171" : "#DC2626"
            font.pixelSize: 12
            font.weight: Font.Medium
        }

        MouseArea {
            id: deleteHover
            anchors.fill: parent
            hoverEnabled: true
            enabled: deleteBtn.visible
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.PointingHandCursor
            onClicked: function(mouse) {
                mouse.accepted = true
                root.deleteRequested()
            }
        }
    }

    // Unread indicator dot
    Rectangle {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: 14
        width: 7; height: 7; radius: 3.5
        color: isDark ? "#F87171" : "#DC2626"
        opacity: (root.hasUnread && !root.isActive && !hoverArea.containsMouse) ? 1.0 : 0.0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }

    MouseArea {
        id: hoverArea
        z: 1
        anchors {
            left: parent.left
            top: parent.top
            bottom: parent.bottom
            right: deleteBtn.visible ? deleteBtn.left : parent.right
            leftMargin: -2
            topMargin: -2
            bottomMargin: -2
            rightMargin: deleteBtn.visible ? 4 : -2
        }
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.selected()
    }
}
