import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    default property alias content: contentArea.data
    property color panelColor: isDark ? "#0DFFFFFF" : "#08000000"
    property color panelBorderColor: borderSubtle
    property color overlayColor: "transparent"
    property bool overlayVisible: false
    property color sideGlowColor: "transparent"
    property bool sideGlowVisible: false
    property real sideGlowWidthFactor: 0.28
    property real sideGlowOpacity: 0.55
    property color accentBlobColor: "transparent"
    property bool accentBlobVisible: false
    property real accentBlobWidthFactor: 0.2
    property real padding: 12
    readonly property real fallbackRadius: typeof radiusMd !== "undefined" ? radiusMd : 24

    Layout.fillWidth: true
    implicitHeight: contentArea.childrenRect.height + root.padding * 2
    radius: root.fallbackRadius
    color: root.panelColor
    border.color: root.panelBorderColor
    border.width: 1

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: root.overlayColor
        visible: root.overlayVisible
    }

    Rectangle {
        width: parent.width * root.sideGlowWidthFactor
        height: parent.height * 0.92
        radius: height / 2
        anchors.right: parent.right
        anchors.rightMargin: -height * 0.08
        anchors.verticalCenter: parent.verticalCenter
        color: root.sideGlowColor
        opacity: root.sideGlowOpacity
        visible: root.sideGlowVisible
    }

    Rectangle {
        width: parent.width * root.accentBlobWidthFactor
        height: parent.height * 0.48
        radius: height / 2
        anchors.right: parent.right
        anchors.rightMargin: 18
        anchors.verticalCenter: parent.verticalCenter
        color: root.accentBlobColor
        visible: root.accentBlobVisible
    }

    Item {
        id: contentArea
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.padding
        implicitHeight: childrenRect.height
    }
}
