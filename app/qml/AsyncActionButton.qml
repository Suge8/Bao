import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root

    property string text: ""
    property bool busy: false
    property bool buttonEnabled: true
    property color fillColor: accent
    property color hoverFillColor: accentHover
    property color textColor: "#FFFFFFFF"
    property color spinnerColor: "#FFFFFFFF"
    property color spinnerSecondaryColor: "#AAFFFFFF"
    property color spinnerHaloColor: "#44FFFFFF"
    property real spinnerHaloOpacity: 0.12
    property real horizontalPadding: 28
    property real minHeight: 30
    readonly property bool interactive: root.buttonEnabled && !root.busy
    readonly property color currentFillColor: buttonArea.containsMouse ? root.hoverFillColor : root.fillColor
    readonly property real currentOpacity: root.busy ? 0.72 : 1.0
    readonly property real currentScale: buttonArea.pressed ? 0.988 : (buttonArea.containsMouse ? motionHoverScaleSubtle : 1.0)
    signal clicked()

    implicitWidth: contentRow.implicitWidth + root.horizontalPadding
    implicitHeight: root.minHeight
    radius: implicitHeight / 2
    color: root.currentFillColor
    opacity: root.currentOpacity
    scale: root.currentScale

    Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    Behavior on scale { NumberAnimation { duration: motionFast; easing.type: easeStandard } }

    Row {
        id: contentRow
        anchors.centerIn: parent
        spacing: 7

        LoadingOrbit {
            width: 14
            height: 14
            anchors.verticalCenter: parent.verticalCenter
            running: root.busy
            color: root.spinnerColor
            secondaryColor: root.spinnerSecondaryColor
            haloColor: root.spinnerHaloColor
            haloOpacity: root.spinnerHaloOpacity
            showCore: false
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            color: root.textColor
            font.pixelSize: typeLabel
            font.weight: Font.DemiBold
        }
    }

    MouseArea {
        id: buttonArea
        anchors.fill: parent
        enabled: root.interactive
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        scrollGestureEnabled: false
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}
