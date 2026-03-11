import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string label: ""
    property string dotpath: ""
    property string description: ""
    property var initialValue: undefined
    readonly property bool popupOpen: combo.popup.visible

    // Array of { label: string, value: any }
    property var options: []

    // For SettingsView.collectFields(): only emit when config had a real value or user changed it.
    property var currentValue: (_loaded && (_dirty || _hasInitialValue)) ? valueForIndex(combo.currentIndex) : undefined
    property bool _loaded: false
    property bool _dirty: false
    property bool _hasInitialValue: false
    property int popupMaxHeight: sizeDropdownMaxHeight

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
        return syncValue(v)
    }

    function readConfigValue() {
        if (initialValue !== undefined)
            return {"exists": true, "value": initialValue}
        if (!configService || !dotpath)
            return {"exists": false, "value": undefined}
        var parts = dotpath.split(".")
        if (parts.length === 0)
            return {"exists": false, "value": undefined}
        var key = parts[parts.length - 1]
        var parentPath = parts.slice(0, parts.length - 1).join(".")
        var parentValue = parentPath !== "" ? configService.getValue(parentPath) : undefined
        if (!parentValue || typeof parentValue !== "object" || Array.isArray(parentValue) || !parentValue.hasOwnProperty(key))
            return {"exists": false, "value": undefined}
        return {"exists": true, "value": parentValue[key]}
    }

    function syncValue(value) {
        var idx = indexForValue(value)
        if (idx < 0)
            return false
        combo.currentIndex = idx
        return true
    }

    function openPopup() {
        combo.forceActiveFocus()
        setPopupVisible(true)
    }

    function setPopupVisible(visible) {
        if (combo.popup.visible === visible)
            return
        if (visible) {
            combo.popup.open()
            return
        }
        combo.popup.visible = false
    }

    Component.onCompleted: {
        var state = readConfigValue()
        if (state.exists && syncValue(state.value))
            _hasInitialValue = true
        _loaded = true
    }

    onInitialValueChanged: {
        if (!_loaded || initialValue === undefined)
            return
        if (syncValue(initialValue))
            _hasInitialValue = true
    }

    Column {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
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
            color: combo.activeFocus
                   ? bgInputFocus
                   : (comboArea.containsMouse ? bgInputHover : bgInput)
            border.color: combo.activeFocus ? borderFocus : borderSubtle
            border.width: combo.activeFocus ? 1.5 : 1

            Behavior on border.color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
            Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }

            ComboBox {
                id: combo
                anchors.fill: parent
                leftPadding: sizeFieldPaddingX
                rightPadding: 32
                font.pixelSize: typeButton
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
                    font.pixelSize: typeButton
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                indicator: Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: "▾"
                    color: textTertiary
                    font.pixelSize: typeButton
                    rotation: combo.popup.visible ? 180 : 0

                    Behavior on rotation { NumberAnimation { duration: motionFast; easing.type: easeStandard } }
                }

                delegate: ItemDelegate {
                    id: optionDelegate
                    width: ListView.view ? ListView.view.width : combo.width
                    height: sizeOptionHeight
                    highlighted: combo.highlightedIndex === index

                    contentItem: Text {
                        text: modelData
                        color: optionDelegate.highlighted ? textPrimary : textSecondary
                        font.pixelSize: typeLabel
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

                        Behavior on color { ColorAnimation { duration: motionMicro; easing.type: easeStandard } }
                    }
                }

                popup: Popup {
                    y: combo.height + 6
                    width: combo.width
                    padding: 6
                    transformOrigin: Item.Top
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside | Popup.CloseOnPressOutsideParent

                    enter: Transition {
                        ParallelAnimation {
                            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: motionFast; easing.type: easeStandard }
                            NumberAnimation { property: "scale"; from: 0.98; to: 1.0; duration: motionFast; easing.type: easeEmphasis }
                        }
                    }

                    exit: Transition {
                        ParallelAnimation {
                            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: motionMicro; easing.type: easeStandard }
                            NumberAnimation { property: "scale"; from: 1.0; to: 0.985; duration: motionMicro; easing.type: easeStandard }
                        }
                    }

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
                    root._dirty = true
                    root.valueChanged(root.valueForIndex(index))
                }
            }

            MouseArea {
                id: comboArea
                objectName: "settingsSelectHitArea"
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton
                scrollGestureEnabled: false
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    combo.forceActiveFocus()
                    setPopupVisible(!combo.popup.visible)
                }
            }
        }
    }
}
