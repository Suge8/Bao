import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string title: ""
    property bool expanded: false
    property real reveal: expanded ? 1 : 0
    default property alias content: contentArea.data

    Layout.fillWidth: true
    clip: true
    implicitHeight: header.height + contentArea.height
    Behavior on reveal { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }

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

            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                spacing: 8

                Text {
                    text: root.expanded ? "▾" : "▸"
                    color: textTertiary
                    font.pixelSize: typeMeta
                }

                Text {
                    text: root.title
                    color: textSecondary
                    font.pixelSize: typeLabel
                    font.weight: weightMedium
                    font.letterSpacing: letterTight
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
            visible: height > 0.5
            height: (childrenRect.height + spacingSm) * root.reveal
            opacity: root.reveal
            scale: 0.985 + (0.015 * root.reveal)
            transformOrigin: Item.Top
        }
    }
}
