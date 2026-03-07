import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    objectName: ""
    property string title: ""
    property string typeText: ""
    property bool expanded: false
    property bool removable: false
    property real contentPadding: spacingMd
    default property alias content: contentColumn.data
    signal removeClicked()

    Layout.fillWidth: true
    radius: radiusMd
    color: isDark ? "#0DFFFFFF" : "#08000000"
    border.color: root.expanded ? accent : borderSubtle
    border.width: root.expanded ? 1.2 : 1
    implicitHeight: cardCol.implicitHeight + 24

    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on border.width { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

    ColumnLayout {
        id: cardCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.contentPadding
        spacing: spacingMd

        ExpandHeader {
            id: providerHeader
            Layout.fillWidth: true
            headerHeight: 32
            expanded: root.expanded
            title: root.title
            titleColor: textPrimary
            titlePixelSize: 14
            titleWeight: Font.Medium
            reservedRightMargin: 36
            onClicked: root.expanded = !root.expanded

            Rectangle {
                radius: radiusSm
                color: isDark ? "#14FFFFFF" : "#10000000"
                implicitHeight: 24
                implicitWidth: typeChipLabel.implicitWidth + 14
                visible: root.typeText !== ""

                Text {
                    id: typeChipLabel
                    anchors.centerIn: parent
                    text: root.typeText
                    color: textSecondary
                    font.pixelSize: 12
                }
            }

            IconCircleButton {
                visible: root.removable
                buttonSize: 28
                glyphText: "\u2715"
                glyphSize: 13
                fillColor: "transparent"
                hoverFillColor: isDark ? "#30F87171" : "#20F87171"
                outlineColor: "transparent"
                glyphColor: textTertiary
                onClicked: root.removeClicked()
            }
        }

        ExpandReveal {
            expanded: root.expanded
            Layout.fillWidth: true
            bottomPadding: spacingMd
            slideAxis: Qt.Vertical
            slideSign: 1
            slideDistance: 14

            ColumnLayout {
                id: contentColumn
                width: parent.width
                spacing: spacingMd
            }
        }
    }
}
