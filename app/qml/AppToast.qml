import QtQuick 2.15

Item {
    id: root

    property string message: ""
    property bool success: true
    property int duration: toastDuration
    property color successBg: "#1F7A4D"
    property color errorBg: "#B63A3A"
    property color textColor: "#FFFFFF"

    readonly property bool shown: message !== ""

    implicitWidth: bubble.implicitWidth
    implicitHeight: bubble.implicitHeight + 6

    function show(msg, ok) {
        message = msg || ""
        success = ok === true
        if (message === "") return
        hideTimer.restart()
    }

    Rectangle {
        id: shadow
        anchors.fill: bubble
        anchors.topMargin: 2
        anchors.leftMargin: 1
        anchors.rightMargin: -1
        anchors.bottomMargin: -2
        radius: bubble.radius + 2
        color: "#60000000"
        opacity: root.shown ? opacityShadowSoft : 0
        visible: opacity > 0.01
        Behavior on opacity { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
    }

    Rectangle {
        id: bubble
        radius: 11
        color: root.success ? root.successBg : root.errorBg
        opacity: root.shown ? 1 : 0
        scale: root.shown ? 1.0 : motionToastHiddenScale
        property real lift: root.shown ? 0 : -12
        transform: Translate { y: bubble.lift }
        implicitWidth: contentRow.implicitWidth + 22
        implicitHeight: 38

        Behavior on opacity { NumberAnimation { duration: motionUi; easing.type: easeStandard } }
        Behavior on scale { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }
        Behavior on lift { NumberAnimation { duration: motionPanel; easing.type: easeEmphasis } }

        Row {
            id: contentRow
            anchors.centerIn: parent
            spacing: 8

            Rectangle {
                width: 18
                height: 18
                radius: 9
                color: "#26FFFFFF"

                Text {
                    anchors.centerIn: parent
                    text: root.success ? "✓" : "!"
                    color: root.textColor
                    font.pixelSize: typeMeta
                    font.weight: weightBold
                }
            }

            Text {
                text: root.message
                color: root.textColor
                font.pixelSize: typeMeta
                font.weight: weightDemiBold
            }
        }
    }

    Timer {
        id: hideTimer
        interval: root.duration
        onTriggered: root.message = ""
    }
}
