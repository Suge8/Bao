import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string label: ""
    property string placeholder: ""
    property string dotpath: ""
    property bool isSecret: false
    property string inputType: "text"

    property var currentValue: _loaded ? fieldValue() : undefined
    property bool _loaded: false

    Layout.fillWidth: true
    implicitHeight: 66

    function fieldValue() {
        var t = field.text.trim()
        if (t === "") return undefined
        if (inputType === "number") {
            var n = parseFloat(t)
            return isNaN(n) ? undefined : n
        }
        return t
    }

    function presetText(val) {
        if (val !== undefined && val !== null && String(val) !== "") {
            field.text = String(val)
        }
    }

    Component.onCompleted: {
        if (configService && dotpath) {
            var v = configService.getValue(dotpath)
            if (v !== undefined && v !== null) {
                field.text = String(v)
            }
        }
        _loaded = true
    }

    Column {
        anchors.fill: parent
        spacing: 6

        Text {
            text: root.label
            color: textSecondary
            font.pixelSize: 13
            font.weight: Font.Medium
            font.letterSpacing: 0.2
        }

        Rectangle {
            width: parent.width
            height: 42
            radius: radiusSm
            color: field.activeFocus
                   ? bgInputFocus
                   : (fieldHover.containsMouse ? bgInputHover : bgInput)
            border.color: field.activeFocus ? borderFocus : borderSubtle
            border.width: field.activeFocus ? 1.5 : 1

            Behavior on border.color { ColorAnimation { duration: 180 } }
            Behavior on color { ColorAnimation { duration: 180 } }

            TextField {
                id: field
                anchors.fill: parent
                leftPadding: 14
                rightPadding: 14
                topPadding: 0
                bottomPadding: 0
                placeholderText: root.placeholder
                placeholderTextColor: textPlaceholder
                color: textPrimary
                background: null
                font.pixelSize: 14
                echoMode: root.isSecret ? TextInput.Password : TextInput.Normal
                verticalAlignment: TextInput.AlignVCenter
            }

            MouseArea {
                id: fieldHover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.IBeamCursor
                acceptedButtons: Qt.NoButton
            }
        }
    }
}
