import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string channelName: ""
    property string enabledPath: ""
    // Array of {label, dotpath, placeholder, isSecret, inputType, isList}
    property var fields: []
    property var advancedFields: []

    // Expose for saveAll() collection — children expose their own dotpaths
    property string dotpath: ""
    property var currentValue: channelToggle.currentValue

    property bool expanded: false

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight

    ColumnLayout {
        id: col
        width: root.width
        spacing: 0

        // Header row — channel name + expand arrow + toggle
        ExpandHeader {
            id: headerSurface
            Layout.fillWidth: true
            headerHeight: 44
            title: root.channelName
            expanded: root.expanded
            titleColor: textPrimary
            titlePixelSize: typeButton
            titleWeight: weightMedium
            reservedRightMargin: 56
            onClicked: root.expanded = !root.expanded

            ToggleSwitch {
                id: channelToggle
                objectName: "channelToggle"
                property string dotpath: root.enabledPath
                property bool _dirty: false
                property bool _hasInitialValue: false
                property bool _loaded: false
                property var currentValue: (_loaded && (_dirty || _hasInitialValue)) ? checked : undefined

                Component.onCompleted: {
                    if (configService && enabledPath) {
                        var v = configService.getValue(enabledPath)
                        if (v === true || v === false) {
                            checked = v
                            _hasInitialValue = true
                        }
                    }
                    _loaded = true
                }

                onToggled: function(nextChecked) {
                    checked = nextChecked
                    _dirty = true
                }
            }
        }

        // Expanded fields area — independent of enabled state
        ExpandReveal {
            expanded: root.expanded
            Layout.fillWidth: true
            bottomPadding: spacingMd + 8
            slideAxis: Qt.Vertical
            slideSign: 1
            slideDistance: 14

            Item {
                width: parent.width
                implicitHeight: contentCol.implicitHeight + 8

                Column {
                    id: contentCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 16
                    anchors.top: parent.top
                    anchors.topMargin: 8
                    spacing: spacingMd

                    Repeater {
                        model: root.fields
                        delegate: Loader {
                            width: parent.width
                            sourceComponent: (modelData.isList === true) ? listComp : fieldComp
                            property var fieldData: modelData
                        }
                    }

                    SettingsCollapsible {
                        visible: root.advancedFields.length > 0
                        width: parent.width
                        title: isZh ? "高级选项" : "Advanced"

                        ColumnLayout {
                            width: parent.width
                            spacing: spacingMd

                            Repeater {
                                model: root.advancedFields
                                delegate: Loader {
                                    Layout.fillWidth: true
                                    sourceComponent: (modelData.isList === true) ? listComp : fieldComp
                                    property var fieldData: modelData
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: fieldComp
        SettingsField {
            label: fieldData.label || ""
            placeholder: fieldData.placeholder || ""
            dotpath: fieldData.dotpath || ""
            isSecret: fieldData.isSecret || false
            inputType: fieldData.inputType || "text"
        }
    }

    Component {
        id: listComp
        SettingsListField {
            label: fieldData.label || ""
            placeholder: fieldData.placeholder || ""
            dotpath: fieldData.dotpath || ""
        }
    }
}
