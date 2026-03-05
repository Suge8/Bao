import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string label: ""
    property string dotpath: ""
    property string placeholder: ""
    property string description: ""
    property string separator: ","

    // For collectFields() — returns array or undefined
    property var currentValue: _loaded ? _getList() : undefined
    property bool _loaded: false
    property bool _dirty: false

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight

    function _getList() {
        var t = field.text.trim()
        if (t === "") return _dirty ? [] : undefined
        var parts = t.split(separator)
        var result = []
        for (var i = 0; i < parts.length; i++) {
            var s = parts[i].trim()
            if (s !== "") result.push(s)
        }
        return result.length > 0 ? result : undefined
    }

    function presetText(val) {
        if (val !== undefined && val !== null) {
            if (Array.isArray(val)) {
                field.text = val.join(separator + " ")
            } else if (String(val) !== "") {
                field.text = String(val)
            }
        }
    }

    Component.onCompleted: {
        if (configService && dotpath) {
            var v = configService.getValue(dotpath)
            presetText(v)
        }
        _loaded = true
    }

    Column {
        id: col
        anchors { left: parent.left; right: parent.right }
        spacing: spacingSm

        Text {
            text: root.label
            color: textSecondary
            font.pixelSize: typeLabel
            font.weight: weightMedium
            font.letterSpacing: letterTight
        }
        Text {
            visible: root.description !== ""
            text: root.description
            color: textTertiary
            font.pixelSize: typeCaption
            font.italic: true
            wrapMode: Text.Wrap
            width: parent.width
        }

        Rectangle {
            width: parent.width
            height: sizeControlHeight
            radius: radiusSm
            color: field.activeFocus
                   ? bgInputFocus
                   : (fieldHover.containsMouse ? bgInputHover : bgInput)
            border.color: field.activeFocus ? borderFocus : borderSubtle
            border.width: field.activeFocus ? 1.5 : 1

            Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

            TextField {
                id: field
                anchors.fill: parent
                leftPadding: sizeFieldPaddingX; rightPadding: sizeFieldPaddingX
                topPadding: 0; bottomPadding: 0
                placeholderText: root.placeholder
                placeholderTextColor: textPlaceholder
                color: textPrimary
                background: null
                font.pixelSize: typeButton
                selectionColor: textSelectionBg
                selectedTextColor: textSelectionFg
                verticalAlignment: TextInput.AlignVCenter
                onTextEdited: root._dirty = true
            }

            MouseArea {
                id: fieldHover
                anchors.fill: parent
                hoverEnabled: true
                scrollGestureEnabled: false
                cursorShape: Qt.IBeamCursor
                acceptedButtons: Qt.NoButton
            }
        }

        Text {
            text: root.separator === ","
                  ? (isZh ? "多个值用逗号分隔" : "Separate multiple values with commas")
                  : (isZh ? "多个值用 " + root.separator + " 分隔" : "Separate with " + root.separator)
            color: textTertiary
            font.pixelSize: typeCaption
            font.italic: true
            visible: root.placeholder !== ""
        }
    }
}
