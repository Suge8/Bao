import QtQuick 2.15

Rectangle {
    id: root

    property string sessionKey: ""
    property string sessionTitle: ""
    property string sessionRelativeTime: ""
    property string filledIconSource: "../resources/icons/sidebar-chat-solid.svg"
    property color iconTintColor: textSecondary
    property bool useIconTint: false
    property bool isActive: false
    property bool dimmed: false
    property bool hasUnread: false
    readonly property string deleteIconSource: isDark
                                               ? "../resources/icons/sidebar-close.svg"
                                               : "../resources/icons/sidebar-close-light.svg"
    signal selected()
    signal deleteRequested()

    height: sizeSessionRow
    radius: 12
    scale: isActive ? motionSelectionScaleActive : (hoverArea.containsMouse ? motionSelectionScaleHover : 1.0)
    color: isActive
           ? sessionRowActiveBg
           : (hoverArea.containsMouse ? sessionRowHoverBg : sessionRowIdleBg)
    border.width: 0
    border.color: isActive ? sessionRowActiveBorder : (hoverArea.containsMouse ? sessionRowHoverBorder : sessionRowIdleBorder)
    opacity: dimmed ? (isActive ? opacityDimmedActive : opacityDimmedIdle) : 1.0

    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on border.width { NumberAnimation { duration: motionMicro; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

    Item {
        id: contentRow
        anchors {
            verticalCenter: parent.verticalCenter
            left: parent.left
            right: deleteBtn.left
            leftMargin: 11
            rightMargin: 10
        }
        height: parent.height

        Item {
            id: leadingIcon
            width: 16
            height: 16
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            scale: root.isActive ? motionHoverScaleSubtle : (hoverArea.containsMouse ? 1.03 : 1.0)

            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

            Image {
                id: iconImage
                anchors.centerIn: parent
                source: root.filledIconSource
                sourceSize: Qt.size(root.isActive ? 16 : 14, root.isActive ? 16 : 14)
                width: root.isActive ? 16 : 14
                height: root.isActive ? 16 : 14
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
                opacity: root.isActive ? 1.0 : 0.94
                scale: root.isActive ? 1.05 : 1.0
                visible: !root.useIconTint

                Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
            }

            Image {
                anchors.centerIn: parent
                width: iconImage.width
                height: iconImage.height
                source: root.filledIconSource
                sourceSize: Qt.size(iconImage.width, iconImage.height)
                fillMode: Image.PreserveAspectFit
                smooth: true
                mipmap: true
                opacity: root.isActive ? 1.0 : 0.94
                visible: root.useIconTint
                scale: root.isActive ? 1.05 : 1.0

                Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
                Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
            }
        }

        Text {
            id: timeText
            objectName: "sessionRelativeTime"
            visible: root.sessionRelativeTime !== ""
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.sessionRelativeTime
            color: root.isActive ? textSecondary : textTertiary
            font.pixelSize: typeMeta
            font.weight: weightMedium
            renderType: Text.NativeRendering
            opacity: visible && !hoverArea.containsMouse && !deleteHover.containsMouse ? 0.9 : 0.0

            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
            Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
        }

        Text {
            id: titleText
            text: root.sessionTitle
            anchors.left: leadingIcon.right
            anchors.leftMargin: 7
            anchors.right: timeText.visible ? timeText.left : parent.right
            anchors.rightMargin: timeText.visible ? 10 : 0
            color: root.isActive ? textPrimary : (hoverArea.containsMouse ? textPrimary : textSecondary)
            font.pixelSize: typeLabel
            font.weight: root.isActive ? weightDemiBold : weightMedium
            elide: Text.ElideRight
            anchors.verticalCenter: parent.verticalCenter
            renderType: Text.NativeRendering

            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
        }
    }

    Rectangle {
        id: deleteBtn
        z: 2
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: 8
        width: 24
        height: 24
        radius: 12
        color: deleteHover.containsMouse ? sessionDeleteHoverBg : sessionDeleteIdleBg
        border.width: 0
        border.color: deleteHover.containsMouse ? sessionDeleteHoverBorder : sessionDeleteIdleBorder
        scale: deleteHover.containsMouse ? motionHoverScaleSubtle : (hoverArea.containsMouse ? 1.0 : motionDeleteHiddenScale)
        opacity: hoverArea.containsMouse || deleteHover.containsMouse ? 1.0 : 0.0
        visible: opacity > 0.01
        Behavior on color { ColorAnimation { duration: motionMicro; easing.type: easeStandard } }
        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: motionMicro; easing.type: easeStandard } }

        Image {
            objectName: "sessionDeleteIcon"
            anchors.centerIn: parent
            source: root.deleteIconSource
            sourceSize: Qt.size(12, 12)
            width: 12
            height: 12
            fillMode: Image.PreserveAspectFit
            smooth: true
            mipmap: true
            opacity: deleteHover.containsMouse ? 1.0 : 0.92
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

    UnreadBadge {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: 12
        active: root.hasUnread && !root.isActive && !hoverArea.containsMouse
        mode: "dot"
        fillColor: sessionUnreadDot
        haloOpacity: isActive ? 0.0 : 0.28
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
            rightMargin: deleteBtn.visible ? deleteBtn.width + deleteBtn.anchors.rightMargin : -2
        }
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.selected()
    }
}
