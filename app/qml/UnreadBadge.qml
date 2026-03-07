import QtQuick 2.15

Item {
    id: root

    property bool active: false
    property int count: 0
    property string mode: "dot" // dot | count
    property color fillColor: accent
    property color textColor: "#FFFFFFFF"
    property color borderColor: "transparent"
    property real haloOpacity: mode === "dot" ? 0.24 : 0.0
    property real visualScale: 1.0
    property string badgeObjectName: ""
    property string textObjectName: ""

    readonly property bool showingCount: mode === "count"
    readonly property int clampedCount: Math.max(0, count)
    readonly property string countText: clampedCount > 99 ? "99+" : String(clampedCount)
    readonly property bool visibleState: active && (showingCount ? clampedCount > 0 : true)

    objectName: badgeObjectName
    visible: visibleState
    implicitWidth: showingCount ? Math.max(18, badgeLabel.implicitWidth + 12) : 10
    implicitHeight: showingCount ? 18 : 10
    width: implicitWidth
    height: implicitHeight
    opacity: visibleState ? 1.0 : 0.0
    scale: visibleState ? visualScale : visualScale * 0.88

    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

    Rectangle {
        anchors.centerIn: parent
        width: parent.width + 6
        height: parent.height + 6
        radius: height / 2
        color: root.fillColor
        opacity: root.haloOpacity
        visible: !root.showingCount
    }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.fillColor
        border.width: root.borderColor === "transparent" ? 0 : 1
        border.color: root.borderColor
    }

    Text {
        id: badgeLabel
        objectName: root.textObjectName
        anchors.centerIn: parent
        visible: root.showingCount
        text: root.countText
        color: root.textColor
        font.pixelSize: typeCaption
        font.weight: weightDemiBold
        textFormat: Text.PlainText
    }
}
