import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string label: ""
    property string dotpath: ""

    // Array of { label: string, value: any }
    property var options: []

    // For SettingsView.collectFields()
    property var currentValue: _loaded ? valueForIndex(combo.currentIndex) : undefined
    property bool _loaded: false

    signal valueChanged(var value)

    Layout.fillWidth: true
    implicitHeight: 66

    function valueForIndex(i) {
        if (!options || options.length === undefined) return undefined
        if (i < 0 || i >= options.length) return undefined
        return options[i].value
    }

    function indexForValue(v) {
        if (!options || options.length === undefined) return -1
        for (var i = 0; i < options.length; i++) {
            if (options[i].value === v) return i
        }
        return -1
    }

    function presetValue(v) {
        var idx = indexForValue(v)
        if (idx >= 0) combo.currentIndex = idx
    }

    Component.onCompleted: {
        if (configService && dotpath) {
            var v = configService.getValue(dotpath)
            presetValue(v)
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
            color: combo.activeFocus
                   ? bgInputFocus
                   : (hover.containsMouse ? bgInputHover : bgInput)
            border.color: combo.activeFocus ? borderFocus : borderSubtle
            border.width: combo.activeFocus ? 1.5 : 1

            Behavior on border.color { ColorAnimation { duration: 180 } }
            Behavior on color { ColorAnimation { duration: 180 } }

            ComboBox {
                id: combo
                anchors.fill: parent
                leftPadding: 14
                rightPadding: 32
                font.pixelSize: 14

                model: {
                    var labels = []
                    for (var i = 0; i < root.options.length; i++) labels.push(root.options[i].label)
                    return labels
                }

                background: null

                contentItem: Text {
                    text: combo.displayText
                    color: textPrimary
                    font.pixelSize: 14
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                indicator: Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: "▾"
                    color: textTertiary
                    font.pixelSize: 14
                }

                onActivated: function(index) {
                    if (!root._loaded) return
                    root.valueChanged(root.valueForIndex(index))
                }
            }

            MouseArea {
                id: hover
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                acceptedButtons: Qt.NoButton
            }
        }
    }
}
