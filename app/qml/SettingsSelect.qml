import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string label: ""
    property string dotpath: ""
    property string description: ""

    // Array of { label: string, value: any }
    property var options: []

    // For SettingsView.collectFields()
    property var currentValue: _loaded ? valueForIndex(combo.currentIndex) : undefined
    property bool _loaded: false
    property int popupMaxHeight: 240

    signal valueChanged(var value)

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight

    function valueForIndex(i) {
        if (!options) return undefined
        if (i < 0 || i >= options.length) return undefined
        return options[i].value
    }

    function indexForValue(v) {
        if (!options) return -1
        for (var i = 0; i < options.length; i++) {
            if (options[i].value === v) return i
        }
        return -1
    }

    function presetValue(v) {
        var idx = indexForValue(v)
        if (idx < 0) return
        combo.currentIndex = idx
    }

    Component.onCompleted: {
        if (configService && dotpath) {
            var v = configService.getValue(dotpath)
            presetValue(v)
        }
        _loaded = true
    }

    Column {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 6

        Text {
            text: root.label
            color: textSecondary
            font.pixelSize: 13
            font.weight: Font.Medium
            font.letterSpacing: 0.2
        }
        Text {
            visible: root.description !== ""
            text: root.description
            color: textTertiary
            font.pixelSize: 11
            font.italic: true
            wrapMode: Text.Wrap
            width: parent.width
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
                hoverEnabled: true

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
                    rotation: combo.popup.visible ? 180 : 0

                    Behavior on rotation { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                }

                delegate: ItemDelegate {
                    id: optionDelegate
                    width: ListView.view ? ListView.view.width : combo.width
                    height: 34
                    highlighted: combo.highlightedIndex === index

                    contentItem: Text {
                        text: modelData
                        color: optionDelegate.highlighted ? textPrimary : textSecondary
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }

                    background: Rectangle {
                        radius: radiusSm
                        color: optionDelegate.highlighted
                        ? (isDark ? "#2AFF951F" : "#1AFF951F")
                               : (optionDelegate.hovered
                                  ? (isDark ? "#10FFFFFF" : "#08000000")
                                  : "transparent")

                        Behavior on color { ColorAnimation { duration: 120 } }
                    }
                }

                popup: Popup {
                    y: combo.height + 6
                    width: combo.width
                    padding: 6

                    implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, root.popupMaxHeight)

                    contentItem: ListView {
                        clip: true
                        model: combo.popup.visible ? combo.delegateModel : null
                        currentIndex: combo.highlightedIndex
                        boundsBehavior: Flickable.StopAtBounds
                        implicitHeight: contentHeight

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                        }
                    }

                    background: Rectangle {
                        radius: radiusSm
                        color: bgInput
                        border.color: borderSubtle
                        border.width: 1
                    }
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
                scrollGestureEnabled: false
                cursorShape: Qt.PointingHandCursor
                acceptedButtons: Qt.NoButton
            }
        }
    }
}
