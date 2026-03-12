import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    z: 2

    property string label: ""
    property string iconSource: ""
    property bool active: false
    property int badgeCount: 0
    property bool useAccentBadge: false
    property bool useExternalHighlight: false
    signal clicked()

    readonly property bool hovering: hoverArea.containsMouse

    implicitHeight: 50
    radius: 16
    color: active && useExternalHighlight
           ? "transparent"
           : useExternalHighlight && hovering
           ? (isDark ? "#11FFFFFF" : "#12000000")
           : active && !useExternalHighlight
           ? (isDark ? "#241A14" : "#EFE1D1")
           : (hovering ? (isDark ? "#17110D" : "#F6EEE6") : "transparent")
    border.width: active && !useExternalHighlight ? 1 : 0
    border.color: active && !useExternalHighlight ? (isDark ? "#2F241C" : "#E4D0BB") : "transparent"

    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

    scale: useExternalHighlight
           ? (hoverArea.pressed ? motionPressScaleStrong : (hovering && !active ? motionHoverScaleSubtle : 1.0))
           : (hoverArea.pressed ? motionPressScaleStrong : (hovering ? motionHoverScaleSubtle : 1.0))

    Rectangle {
        width: root.active && !root.useExternalHighlight ? 3 : 0
        height: 26
        radius: 1.5
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        color: accent
        visible: width > 0

        Behavior on width { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
    }

    Image {
        id: navIcon
        width: 18
        height: 18
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        source: root.iconSource
        sourceSize: Qt.size(18, 18)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
        opacity: root.active ? 1.0 : (root.hovering ? 0.92 : 0.72)

        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    }

    UnreadBadge {
        id: navBadge
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        active: root.badgeCount > 0
        count: root.badgeCount
        mode: "count"
        fillColor: root.useAccentBadge ? accent : sidebarHeaderBadgeBg
        textColor: root.useAccentBadge ? bgSidebar : sidebarHeaderBadgeText
        borderColor: "transparent"
    }

    Text {
        anchors.left: navIcon.right
        anchors.leftMargin: 10
        anchors.right: navBadge.active ? navBadge.left : parent.right
        anchors.rightMargin: navBadge.active ? 10 : 14
        anchors.verticalCenter: parent.verticalCenter
        text: root.label
        color: root.active ? textPrimary : textSecondary
        font.pixelSize: typeLabel + 1
        font.weight: root.active ? weightDemiBold : weightMedium
        elide: Text.ElideRight
        renderType: Text.NativeRendering

        Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
