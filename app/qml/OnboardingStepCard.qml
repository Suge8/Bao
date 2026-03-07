import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property int stepNumber: 0
    property string overlineText: ""
    property string title: ""
    property string description: ""
    property string ctaText: ""
    property bool done: false
    property bool current: false
    property bool clickable: true
    property real pulsePhase: 0.0
    readonly property color surfaceColor: root.current
                                         ? (isDark ? "#18FFB33D" : "#14FFB33D")
                                         : (root.done ? (isDark ? "#10FFFFFF" : "#0A000000") : (isDark ? "#0DFFFFFF" : "#05000000"))
    readonly property color outlineColor: root.current ? accent : (root.done ? (isDark ? "#24FFD699" : "#22D0892C") : borderSubtle)
    readonly property real surfaceScale: stepArea.pressed
                                         ? 0.992
                                         : (root.current
                                            ? motionSelectionScaleActive
                                            : (root.done ? motionSelectionScaleHover : (stepArea.containsMouse ? motionHoverScaleSubtle : 1.0)))
    readonly property string statusText: root.done ? tr("已完成", "Done") : (root.current ? tr("现在就做", "Do this now") : tr("接下来", "Up next"))
    readonly property color statusTextColor: root.current ? accent : textTertiary
    readonly property color badgeColor: root.done ? accent : "transparent"
    readonly property color badgeOutlineColor: root.done ? accent : (root.current ? accent : borderSubtle)
    readonly property color badgeTextColor: root.done ? "#FFFFFFFF" : (root.current ? accent : textSecondary)
    readonly property color ctaFillColor: root.current ? accent : (root.done ? (isDark ? "#14FFFFFF" : "#10000000") : "transparent")
    readonly property color ctaTextColor: root.current ? "#FFFFFFFF" : (root.done ? textPrimary : textSecondary)
    signal clicked()

    radius: radiusLg
    color: root.surfaceColor
    border.color: root.outlineColor
    border.width: root.current ? 1.3 : 1
    scale: root.surfaceScale
    implicitHeight: stepCardCol.implicitHeight + 28

    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }

    SequentialAnimation on pulsePhase {
        running: root.current && !root.done
        loops: Animation.Infinite
        NumberAnimation { from: 0.0; to: 1.0; duration: motionStatusPulse; easing.type: easeStandard }
        NumberAnimation { from: 1.0; to: 0.0; duration: motionStatusPulse; easing.type: easeSoft }
    }

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: accent
        opacity: root.current ? (0.03 + root.pulsePhase * 0.03) : (stepArea.containsMouse ? 0.02 : 0.0)
        scale: root.current ? (1.0 + root.pulsePhase * 0.01) : 1.0
        visible: opacity > 0.001
        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }
    }

    Rectangle {
        width: 34
        height: 34
        radius: 17
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 14
        anchors.rightMargin: 14
        color: root.badgeColor
        border.color: root.badgeOutlineColor
        border.width: root.current || !root.done ? 1.2 : 0
        opacity: root.done ? 1.0 : 0.92

        Text {
            anchors.centerIn: parent
            text: root.done ? "OK" : String(root.stepNumber + 1)
            color: root.badgeTextColor
            font.pixelSize: typeLabel
            font.weight: Font.DemiBold
        }
    }

    Rectangle {
        visible: root.current && !root.done
        width: 42
        height: 42
        radius: 21
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 10
        anchors.rightMargin: 10
        color: accent
        opacity: 0.04 + root.pulsePhase * 0.12
        scale: 0.86 + root.pulsePhase * 0.20
    }

    ColumnLayout {
        id: stepCardCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 10

        Text {
            Layout.fillWidth: true
            text: root.overlineText !== "" ? root.overlineText : root.statusText
            color: root.statusTextColor
            font.pixelSize: typeMeta
            font.weight: Font.DemiBold
            font.letterSpacing: letterWide
        }

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
            font.pixelSize: typeLabel
            wrapMode: Text.WordWrap
            lineHeight: 1.2
        }

        Rectangle {
            implicitWidth: stepActionLabel.implicitWidth + 22
            implicitHeight: 32
            radius: 16
            color: root.ctaFillColor
            border.color: root.current ? accent : borderSubtle
            border.width: root.current ? 0 : 1
            scale: stepArea.containsMouse ? motionHoverScaleSubtle : 1.0

            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeEmphasis } }

            Text {
                id: stepActionLabel
                anchors.centerIn: parent
                text: root.ctaText
                color: root.ctaTextColor
                font.pixelSize: typeMeta
                font.weight: Font.DemiBold
            }
        }
    }

    MouseArea {
        id: stepArea
        anchors.fill: parent
        enabled: root.clickable
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        scrollGestureEnabled: false
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}
