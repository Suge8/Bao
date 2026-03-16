import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property var configService: null
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

        ToggleSwitch {
            checked: root.toggleOn
            onToggled: function(checked) {
                root.toggleOn = checked
                root._dirty = true
            }
        }
    }
}
