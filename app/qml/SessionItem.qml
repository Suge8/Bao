import QtQuick 2.15

Rectangle {
    id: root
    z: 1
    objectName: "sessionItem"

    property string sessionKey: ""
    property string sessionTitle: ""
    property string sessionRelativeTime: ""
    property string filledIconSource: "../resources/icons/sidebar-chat-solid.svg"
    property color iconTintColor: textSecondary
    property bool useIconTint: false
    property bool isActive: false
    property bool dimmed: false
    property bool hasUnread: false
    property bool readOnlySession: false
    property bool isRunning: false
    property int childIndent: 0
    property bool useExternalActiveHighlight: false
    readonly property real deleteHitZoneWidth: deleteBtn.width + deleteBtn.anchors.rightMargin
    readonly property string deleteIconSource: isDark
                                               ? "../resources/icons/sidebar-close.svg"
                                               : "../resources/icons/sidebar-close-light.svg"
    signal selected()
    signal deleteRequested()

    height: sizeSessionRow
    radius: 12
    scale: useExternalActiveHighlight
           ? (hoverArea.pressed ? motionPressScaleStrong : (hoverArea.containsMouse && !isActive ? motionHoverScaleSubtle : 1.0))
           : (isActive ? motionSelectionScaleActive : (hoverArea.containsMouse ? motionSelectionScaleHover : 1.0))
    color: isActive && useExternalActiveHighlight
           ? "transparent"
           : useExternalActiveHighlight && hoverArea.containsMouse
           ? (isDark ? "#11FFFFFF" : "#12000000")
           : useExternalActiveHighlight
           ? "transparent"
           : isActive && !useExternalActiveHighlight
           ? sessionRowActiveBg
           : (hoverArea.containsMouse ? sessionRowHoverBg : sessionRowIdleBg)
    border.width: 0
    border.color: useExternalActiveHighlight
                  ? "transparent"
                  : (isActive ? sessionRowActiveBorder : (hoverArea.containsMouse ? sessionRowHoverBorder : sessionRowIdleBorder))
    opacity: dimmed ? (isActive ? opacityDimmedActive : opacityDimmedIdle) : 1.0

    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
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
            leftMargin: 11 + root.childIndent
            rightMargin: 10
        }
        height: parent.height

        Item {
            id: leadingIcon
            width: 16
            height: 16
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            scale: 1.0

            AppIcon {
                id: iconImage
                anchors.centerIn: parent
                source: root.filledIconSource
                sourceSize: Qt.size(14, 14)
                width: 14
                height: 14
                opacity: root.isActive ? 1.0 : (hoverArea.containsMouse ? 0.92 : 0.72)
                visible: !root.useIconTint

                Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            }

            AppIcon {
                anchors.centerIn: parent
                width: iconImage.width
                height: iconImage.height
                source: root.filledIconSource
                sourceSize: Qt.size(iconImage.width, iconImage.height)
                opacity: root.isActive ? 1.0 : (hoverArea.containsMouse ? 0.92 : 0.72)
                visible: root.useIconTint

                Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
            }

            Rectangle {
                id: runningBadge
                visible: root.isRunning
                width: 8
                height: 8
                radius: 4
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                color: statusSuccess
                border.width: 1
                border.color: isDark ? "#CCFFFFFF" : "#F7FFFB"
                opacity: 0.65
                scale: 0.92

                SequentialAnimation on opacity {
                    running: root.isRunning
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.46; to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
                    NumberAnimation { from: 1.0; to: 0.46; duration: 900; easing.type: Easing.InOutQuad }
                }

                SequentialAnimation on scale {
                    running: root.isRunning
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.88; to: 1.14; duration: 900; easing.type: Easing.InOutQuad }
                    NumberAnimation { from: 1.14; to: 0.88; duration: 900; easing.type: Easing.InOutQuad }
                }
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
        visible: !root.readOnlySession && opacity > 0.01
        Behavior on color { ColorAnimation { duration: motionMicro; easing.type: easeStandard } }
        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: motionMicro; easing.type: easeStandard } }

        AppIcon {
            objectName: "sessionDeleteIcon"
            anchors.centerIn: parent
            source: root.deleteIconSource
            sourceSize: Qt.size(12, 12)
            width: 12
            height: 12
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
            rightMargin: root.deleteHitZoneWidth - 2
        }
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.selected()
    }
}
