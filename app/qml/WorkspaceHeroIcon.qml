import QtQuick 2.15

Item {
    id: root

    property string iconSource: ""
    property color fillColor: typeof isDark !== "undefined" && isDark ? "#1D1713" : "#F3E7DA"
    property color outlineColor: typeof borderSubtle !== "undefined" ? borderSubtle : "#14000000"
    property int iconSize: 18

    implicitWidth: 34
    implicitHeight: 34

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.fillColor
        border.width: 1
        border.color: root.outlineColor

        AppIcon {
            anchors.centerIn: parent
            width: root.iconSize
            height: root.iconSize
            source: root.iconSource
            sourceSize: Qt.size(width, height)
        }
    }
}
