import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string label: ""
    property string dotpath: ""
    property bool toggleOn: false
    property bool _dirty: false
    property bool _hasInitialValue: false

    // For collectFields(): only emit when loaded and user changed or key existed
    property var currentValue: (_loaded && (_dirty || _hasInitialValue)) ? toggleOn : undefined
    property bool _loaded: false

    Layout.fillWidth: true
    implicitHeight: 42

    Component.onCompleted: {
        if (configService && dotpath) {
            var v = configService.getValue(dotpath)
            if (v === true || v === false) {
                toggleOn = v
                _hasInitialValue = true
            }
        }
        _loaded = true
    }

    RowLayout {
        anchors.fill: parent
        spacing: 12

        Text {
            text: root.label
            color: textSecondary
            font.pixelSize: typeLabel
            font.weight: weightMedium
            font.letterSpacing: letterTight
            Layout.fillWidth: true
        }

        Rectangle {
            id: toggle
            width: 44; height: 24; radius: 12
            color: root.toggleOn ? accent : (isDark ? "#252538" : "#D1D5DB")
            scale: root.toggleOn ? motionHoverScaleSubtle : 1.0
            Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

            Rectangle {
                width: 18; height: 18; radius: 9
                color: "#FFFFFF"
                anchors.verticalCenter: parent.verticalCenter
                x: root.toggleOn ? parent.width - width - 3 : 3
                Behavior on x { SmoothedAnimation { velocity: motionTrackVelocity; duration: motionUi } }
            }

            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                scrollGestureEnabled: false
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    root.toggleOn = !root.toggleOn
                    root._dirty = true
                }
            }
        }
    }
}
