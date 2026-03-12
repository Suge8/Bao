import QtQuick 2.15
import QtQuick.Layouts 1.15

Item {
    id: root

    property bool active: false
    readonly property bool hasSessionService: typeof sessionService !== "undefined" && sessionService !== null
    property real railOpacity: 1.0
    property real railShift: 0.0
    property real railScale: 1.0
    property real stageOpacity: 1.0
    property real stageShift: 0.0
    property real stageScale: 1.0

    function playWorkspaceReveal() {
        railOpacity = 0.72
        railScale = motionPageRevealStartScale
        railShift = -motionPageShiftSubtle
        stageOpacity = motionPageRevealStartOpacity
        stageScale = motionPageRevealStartScale
        stageShift = motionPageShiftSubtle + 4
        workspaceRevealAnimation.restart()
    }

    function playStageReveal() {
        stageOpacity = motionPageRevealStartOpacity
        stageScale = motionPageRevealStartScale
        stageShift = motionPageShiftSubtle
        stageRevealAnimation.restart()
    }

    onActiveChanged: {
        if (active)
            playWorkspaceReveal()
    }

    function createSession() {
        if (root.hasSessionService)
            sessionService.newSession("")
    }

    function selectSession(sessionKey) {
        if (root.hasSessionService)
            sessionService.selectSession(sessionKey)
    }

    function deleteSession(sessionKey) {
        if (root.hasSessionService)
            sessionService.deleteSession(sessionKey)
    }

    Connections {
        target: root.hasSessionService ? sessionService : null

        function onActiveKeyChanged(_key) {
            if (root.active)
                root.playStageReveal()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 16

        Item {
            objectName: "sessionRailStage"
            Layout.preferredWidth: 272
            Layout.minimumWidth: 256
            Layout.maximumWidth: 288
            Layout.fillHeight: true
            opacity: root.railOpacity
            scale: root.railScale
            transform: Translate { x: root.railShift }

            SessionBrowser {
                id: browser
                anchors.fill: parent
                activeSessionKey: root.hasSessionService ? sessionService.activeKey : ""
                showSelection: true
                onNewSessionRequested: root.createSession()
                onSessionSelected: function(key) { root.selectSession(key) }
                onSessionDeleteRequested: function(key) { root.deleteSession(key) }
            }
        }

        Item {
            objectName: "chatDetailStage"
            Layout.fillWidth: true
            Layout.fillHeight: true
            opacity: root.stageOpacity
            scale: root.stageScale
            transform: Translate { x: root.stageShift }

            Rectangle {
                anchors.fill: parent
                radius: 30
                color: bgCard
                border.width: 1
                border.color: isDark ? "#24FFFFFF" : "#1A6E4B2A"

                Rectangle {
                    anchors.fill: parent
                    radius: parent.radius
                    color: isDark ? "#08FFFFFF" : "#12FFF7EF"
                }

                ChatView {
                    anchors.fill: parent
                    onMessageCopied: globalToast.show(strings.copied_ok, true)
                }
            }
        }
    }

    SequentialAnimation {
        id: workspaceRevealAnimation

        ParallelAnimation {
            NumberAnimation { target: root; property: "railOpacity"; to: 1.0; duration: motionUi; easing.type: easeStandard }
            NumberAnimation { target: root; property: "railScale"; to: 1.0; duration: motionPanel; easing.type: easeEmphasis }
            NumberAnimation { target: root; property: "railShift"; to: 0.0; duration: motionPanel; easing.type: easeEmphasis }
            NumberAnimation { target: root; property: "stageOpacity"; to: 1.0; duration: motionUi; easing.type: easeStandard }
            NumberAnimation { target: root; property: "stageScale"; to: 1.0; duration: motionPanel; easing.type: easeEmphasis }
            NumberAnimation { target: root; property: "stageShift"; to: 0.0; duration: motionPanel; easing.type: easeEmphasis }
        }
    }

    SequentialAnimation {
        id: stageRevealAnimation

        ParallelAnimation {
            NumberAnimation { target: root; property: "stageOpacity"; to: 1.0; duration: motionUi; easing.type: easeStandard }
            NumberAnimation { target: root; property: "stageScale"; to: 1.0; duration: motionPanel; easing.type: easeEmphasis }
            NumberAnimation { target: root; property: "stageShift"; to: 0.0; duration: motionPanel; easing.type: easeEmphasis }
        }
    }
}
