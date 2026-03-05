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

    height: sizeSessionRow
    radius: radiusSm
    color: isActive
           ? sessionRowActiveBg
           : (hoverArea.containsMouse ? sessionRowHoverBg : "transparent")
    border.width: isActive ? 1 : 0
    border.color: isActive ? sessionRowActiveBorder : "transparent"
    opacity: dimmed ? (isActive ? opacityDimmedActive : opacityDimmedIdle) : 1.0

    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

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
            color: root.isActive ? sessionLeadingActiveBg : sessionLeadingIdleBg
            border.width: 1
            border.color: root.isActive ? accentGlow : borderSubtle
            anchors.verticalCenter: parent.verticalCenter

            Image {
                anchors.centerIn: parent
                source: "../resources/icons/chat.svg"
                sourceSize: Qt.size(12, 12)
                width: 12
                height: 12
                opacity: root.isActive ? 1.0 : opacityInactive
            }
        }

        Text {
            text: root.sessionTitle
            color: root.isActive ? textPrimary : textSecondary
            font.pixelSize: typeLabel
            font.weight: root.isActive ? weightMedium : weightRegular
            elide: Text.ElideRight
            width: Math.max(0, parent.width - leadingIcon.width - 12)
            anchors.verticalCenter: parent.verticalCenter

            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
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
        color: deleteHover.containsMouse ? sessionDeleteHoverBg : sessionDeleteIdleBg
        border.width: 1
        border.color: deleteHover.containsMouse ? sessionDeleteHoverBorder : sessionDeleteIdleBorder
        scale: deleteHover.containsMouse ? motionHoverScaleSubtle : 1.0
        visible: rowHover.hovered || deleteHover.containsMouse
        Behavior on color { ColorAnimation { duration: motionMicro; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: motionMicro; easing.type: easeStandard } }

        Text {
            anchors.centerIn: parent
            text: "✕"
            color: sessionDeleteIcon
            font.pixelSize: typeMeta
            font.weight: weightMedium
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
        color: sessionUnreadDot
        opacity: (root.hasUnread && !root.isActive && !hoverArea.containsMouse) ? 1.0 : 0.0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
    }

    MouseArea {
        id: hoverArea
        z: 1
        anchors {
            left: parent.left
            top: parent.top
            bottom: parent.bottom
            right: parent.right
            leftMargin: -2
            topMargin: -2
            bottomMargin: -2
            rightMargin: -2
        }
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.selected()
    }
}
