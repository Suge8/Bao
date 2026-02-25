import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property string channelName: ""
    property string enabledPath: ""
    // Array of {label, dotpath, placeholder, isSecret, inputType}
    property var fields: []

    // Expose for saveAll() collection — children expose their own dotpaths
    property string dotpath: ""
    property var currentValue: undefined

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight

    ColumnLayout {
        id: col
        width: root.width
        spacing: 10

        // Enable toggle row
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Text {
                text: root.channelName
                color: textPrimary
                font.pixelSize: 14
                font.weight: Font.Medium
                Layout.fillWidth: true
            }

            // Toggle switch
            Rectangle {
                id: toggle
                width: 44; height: 24; radius: 12
                color: toggleOn ? accent : (isDark ? "#252538" : "#D1D5DB")
                Behavior on color { ColorAnimation { duration: 200 } }

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
                    Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: toggle.toggleOn = !toggle.toggleOn
                }
            }
        }

        // Dynamic fields — only shown when enabled
        Repeater {
            model: toggle.toggleOn ? root.fields : []
            delegate: SettingsField {
                Layout.fillWidth: true
                label: modelData.label || ""
                placeholder: modelData.placeholder || ""
                dotpath: modelData.dotpath || ""
                isSecret: modelData.isSecret || false
                inputType: modelData.inputType || "text"
            }
        }
    }
}
