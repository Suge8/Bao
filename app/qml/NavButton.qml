import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root

    property string icon: ""
    property string label: ""
    property bool active: false
    signal clicked()

    height: 40
    radius: radiusSm
    color: active
           ? accentMuted
           : (hoverArea.containsMouse ? (isDark ? "#08FFFFFF" : "#06000000") : "transparent")

    Behavior on color { ColorAnimation { duration: 150 } }

    Row {
        anchors { verticalCenter: parent.verticalCenter; left: parent.left; leftMargin: 14 }
        spacing: 10

        Text {
            text: root.icon
            font.pixelSize: 15
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: root.label
            color: root.active ? textPrimary : textSecondary
            font.pixelSize: 14
            font.weight: root.active ? Font.DemiBold : Font.Normal
            font.letterSpacing: 0.2
            anchors.verticalCenter: parent.verticalCenter

            Behavior on color { ColorAnimation { duration: 150 } }
        }
    }

    // Active indicator bar
    Rectangle {
        anchors { left: parent.left; verticalCenter: parent.verticalCenter }
        width: 3
        height: 18
        radius: 2
        color: accent
        visible: root.active
        opacity: root.active ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
