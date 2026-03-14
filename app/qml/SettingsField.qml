import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    readonly property var configService: (typeof appServices !== "undefined" && appServices !== null)
                                      ? appServices.configService
                                      : null
    property string label: ""
    property string placeholder: ""
    property string dotpath: ""
    property bool isSecret: false
    property string inputType: "text"
    property string description: ""
    property bool showLabel: label !== ""
    property bool showDescription: description !== ""
    property int fieldHeight: sizeControlHeight
    property int fieldFontPixelSize: typeButton
    property alias text: field.text
    readonly property alias inputItem: field

    property var currentValue: _loaded ? fieldValue() : undefined
    property bool _loaded: false
    property bool _dirty: false
    signal accepted()
    signal textEdited(string text)

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight

    function fieldValue() {
        var t = field.text.trim()
        if (inputType === "bool") {
            if (t === "") return _dirty ? false : undefined
            var lowered = t.toLowerCase()
            if (lowered === "true" || lowered === "1" || lowered === "yes" || lowered === "on") return true
            if (lowered === "false" || lowered === "0" || lowered === "no" || lowered === "off") return false
            return undefined
        }
        if (t === "") return _dirty ? "" : undefined
        if (inputType === "number") {
            var n = parseFloat(t)
            return isNaN(n) ? undefined : n
        }
        return t
    }

    function _writeText(val, markDirty) {
        field.text = (val !== undefined && val !== null) ? String(val) : ""
        if (markDirty)
            _dirty = true
    }

    function presetText(val) {
        if (val !== undefined && val !== null && String(val) !== "")
            _writeText(val, false)
    }

    function setCurrentText(val) {
        _writeText(val, true)
    }

    function forceActiveFocus() {
        field.forceActiveFocus()
    }

    function selectAll() {
        field.selectAll()
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
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: (root.showLabel || root.showDescription) ? spacingSm : 0

        Text {
            visible: root.showLabel
            text: root.label
            color: textSecondary
            font.pixelSize: typeLabel
            font.weight: weightMedium
            font.letterSpacing: letterTight
        }
        Text {
            visible: root.showDescription
            text: root.description
            color: textTertiary
            font.pixelSize: typeCaption
            font.italic: true
            wrapMode: Text.Wrap
            width: parent.width
        }

        Rectangle {
            width: parent.width
            height: root.fieldHeight
            radius: radiusSm
            color: field.activeFocus
                   ? bgInputFocus
                   : (field.hovered ? bgInputHover : bgInput)
            border.color: field.activeFocus ? borderFocus : borderSubtle
            border.width: field.activeFocus ? 1.5 : 1

            Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

            TextField {
                id: field
                property bool baoClickAwayEditor: true
                anchors.fill: parent
                hoverEnabled: true
                leftPadding: sizeFieldPaddingX
                rightPadding: sizeFieldPaddingX
                topPadding: 0
                bottomPadding: 0
                placeholderText: root.placeholder
                placeholderTextColor: textPlaceholder
                color: textPrimary
                background: null
                font.pixelSize: root.fieldFontPixelSize
                selectionColor: textSelectionBg
                selectedTextColor: textSelectionFg
                echoMode: root.isSecret ? TextInput.Password : TextInput.Normal
                verticalAlignment: TextInput.AlignVCenter
                onTextEdited: {
                    root._dirty = true
                    root.textEdited(text)
                }
                onAccepted: root.accepted()
            }
        }
    }
}
