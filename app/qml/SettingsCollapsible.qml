import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string title: ""
    property bool expanded: false
    default property alias content: contentArea.data

    Layout.fillWidth: true
    clip: true
    implicitHeight: header.height + contentArea.height

    Column {
        id: col
        width: parent.width
        spacing: 0

        // Header row — clickable to toggle
        Rectangle {
            id: header
            width: parent.width
            height: 36
            radius: radiusSm
            color: headerHover.containsMouse ? (isDark ? "#0AFFFFFF" : "#08000000") : "transparent"

            Behavior on color { ColorAnimation { duration: 150 } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                spacing: 8

                Text {
                    text: root.expanded ? "▾" : "▸"
                    color: textTertiary
                    font.pixelSize: 12
                }

                Text {
                    text: root.title
                    color: textSecondary
                    font.pixelSize: 13
                    font.weight: Font.Medium
                    font.letterSpacing: 0.2
                    Layout.fillWidth: true
                }
            }

            MouseArea {
                id: headerHover
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton
                scrollGestureEnabled: false
                cursorShape: Qt.PointingHandCursor
                onClicked: root.expanded = !root.expanded
            }
        }

        // Content area — only visible when expanded
        Item {
            id: contentArea
            width: parent.width
            visible: root.expanded
            height: root.expanded ? childrenRect.height + 8 : 0
        }
    }
}
