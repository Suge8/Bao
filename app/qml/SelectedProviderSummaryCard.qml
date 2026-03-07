import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property string title: ""
    property string description: ""
    property string typeText: ""
    property bool highlighted: false
    property real glowPhase: 0.0
    readonly property color panelFillColor: root.highlighted ? (isDark ? "#10FFB33D" : "#0DFFB33D") : (isDark ? "#0DFFFFFF" : "#08000000")
    readonly property color panelBorderColor: root.highlighted ? accent : borderSubtle
    readonly property real panelGlowOpacity: root.highlighted ? (0.02 + root.glowPhase * 0.04) : 0.0
    default property alias content: contentColumn.data

    Layout.fillWidth: true
    radius: radiusMd
    color: root.panelFillColor
    border.color: root.panelBorderColor
    border.width: root.highlighted ? 1.2 : 1
    implicitHeight: contentColumn.implicitHeight + 24

    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

    SequentialAnimation on glowPhase {
        running: root.highlighted
        loops: Animation.Infinite
        NumberAnimation { from: 0.0; to: 1.0; duration: motionAmbient + motionMicro; easing.type: easeSoft }
        NumberAnimation { from: 1.0; to: 0.0; duration: motionAmbient + motionMicro; easing.type: easeSoft }
    }

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: accent
        opacity: root.panelGlowOpacity
        visible: opacity > 0.001
        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
    }

    ColumnLayout {
        id: contentColumn
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 12
        spacing: spacingMd

        RowLayout {
            Layout.fillWidth: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    Layout.fillWidth: true
                    text: root.title
                    color: textPrimary
                    font.pixelSize: typeBody
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: root.description
                    color: textSecondary
                    font.pixelSize: typeMeta
                    wrapMode: Text.WordWrap
                }
            }

            Rectangle {
                implicitWidth: typeChipLabel.implicitWidth + 16
                implicitHeight: 26
                radius: 13
                color: isDark ? "#14FFFFFF" : "#10FFFFFF"
                visible: root.typeText !== ""

                Text {
                    id: typeChipLabel
                    anchors.centerIn: parent
                    text: root.typeText
                    color: accent
                    font.pixelSize: typeCaption
                    font.weight: Font.DemiBold
                }
            }
        }
    }
}
