import QtQuick 2.15

Item {
    id: root

    implicitWidth: 10
    implicitHeight: 10
    property color markerColor: typeof isDark !== "undefined" && isDark ? "#18FFFFFF" : "#16000000"

    Column {
        anchors.centerIn: parent
        spacing: 6

        Repeater {
            model: 18

            delegate: Rectangle {
                width: 2
                height: 4
                radius: 1
                color: root.markerColor
            }
        }
    }
}
