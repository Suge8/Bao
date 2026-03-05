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
    property var currentValue: undefined

    property bool expanded: false

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight

    ColumnLayout {
        id: col
        width: root.width
        spacing: 0

        // Header row — channel name + expand arrow + toggle
        Rectangle {
            Layout.fillWidth: true
            height: 44
            radius: radiusSm
            color: headerHover.containsMouse ? (isDark ? "#0AFFFFFF" : "#08000000") : "transparent"
            Behavior on color { ColorAnimation { duration: motionFast; easing.type: easeStandard } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                spacing: 8

                // Expand arrow
                Text {
                    text: root.expanded ? "▾" : "▸"
                    color: textTertiary
                    font.pixelSize: typeMeta
                }

                Text {
                    text: root.channelName
                    color: textPrimary
                    font.pixelSize: typeButton
                    font.weight: weightMedium
                    Layout.fillWidth: true
                }

                // Toggle switch
                Rectangle {
                    id: toggle
                    width: 44; height: 24; radius: 12
                    color: toggleOn ? accent : (isDark ? "#252538" : "#D1D5DB")
                    scale: toggleOn ? motionHoverScaleSubtle : 1.0
                    Behavior on color { ColorAnimation { duration: motionUi; easing.type: easeStandard } }
                    Behavior on scale { NumberAnimation { duration: motionUi; easing.type: easeEmphasis } }

                    property bool toggleOn: false

                    Component.onCompleted: {
                        if (configService && enabledPath) {
                            var v = configService.getValue(enabledPath)
                            toggleOn = v === true
                        }
                    }

                    // Expose for saveAll
                    property string dotpath: root.enabledPath
                    property var currentValue: toggleOn

                    Rectangle {
                        width: 18; height: 18; radius: 9
                        color: "#FFFFFF"
                        anchors.verticalCenter: parent.verticalCenter
                        x: parent.toggleOn ? parent.width - width - 3 : 3
                        Behavior on x { SmoothedAnimation { velocity: motionTrackVelocity; duration: motionUi } }
                    }

                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton
                        scrollGestureEnabled: false
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            toggle.toggleOn = !toggle.toggleOn
                            // Don't propagate to header click
                        }
                    }
                }
            }

            MouseArea {
                id: headerHover
                anchors.fill: parent
                anchors.rightMargin: 56  // Don't overlap toggle
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton
                scrollGestureEnabled: false
                cursorShape: Qt.PointingHandCursor
                onClicked: root.expanded = !root.expanded
            }
        }

        // Expanded fields area — independent of enabled state
        ColumnLayout {
            visible: root.expanded
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.topMargin: 8
            spacing: spacingMd

            Repeater {
                model: root.expanded ? root.fields : []
                delegate: Loader {
                    Layout.fillWidth: true
                    sourceComponent: (modelData.isList === true) ? listComp : fieldComp
                    property var fieldData: modelData
                }
            }

            // Advanced fields — collapsible
            SettingsCollapsible {
                visible: root.advancedFields.length > 0
                Layout.fillWidth: true
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
