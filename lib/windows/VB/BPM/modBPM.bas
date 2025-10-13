Attribute VB_Name = "modBPM"
'============================================================================
' modBPM.bas - Copyright (c) 2003-2013 (: JOBnik! :) [Arthur Aminov, ISRAEL]
'                                                    [http://www.jobnik.org]
'                                                    [bass_fx @ jobnik .org]
' Other source: frmBPM.frm
'
' BASS_FX bpm with tempo & samplerate changers
' * Requires: BASS 2.4 (available @ www.un4seen.com)
'============================================================================

Option Explicit

' Declare the multimedia timer API
Public uTimerID As Long             ' The identifier of the timer. The identifier is returned by the timeSetEvent function
Public Const TIME_ONESHOT = 0       ' Event occurs once, after uDelay milliseconds
Public Declare Function timeSetEvent Lib "winmm.dll" (ByVal uDelay As Long, ByVal uResolution As Long, ByVal lpFunction As Long, ByVal dwUser As Long, ByVal uFlags As Long) As Long
Public Declare Function timeKillEvent Lib "winmm.dll" (ByVal uID As Long) As Long

Public chan As Long                 ' tempo channel handle
Public bpmChan As Long              ' decoding channel handle for BPM detection
Public bpmValue As Single           ' bpm value returned by BASS_FX_BPM_DecodeGet/GetBPM_Callback functions

' show the approximate position in MM:SS format according to Tempo change
Public Sub UpdatePositionLabel()
    If (BASS_FX_TempoGetRateRatio(chan)) Then
        Dim totalsec As Single, posec As Single

        With frmBPM
            totalsec = .sldPosition.max / BASS_FX_TempoGetRateRatio(chan)
            posec = .sldPosition.value / BASS_FX_TempoGetRateRatio(chan)
    
            .sldPosition.Text = Format(Int(posec) \ 60, "00") & ":" & Format(Int(posec) Mod 60, "00") & " / " & _
                                Format(Int(totalsec) \ 60, "00") & ":" & Format(Int(totalsec) Mod 60, "00")
            .lblPos.Caption = "Playing position: " & .sldPosition.Text
        End With
    End If
End Sub

' calculate approximate bpm value according to Tempo change
Public Function GetNewBPM(ByVal bpm As Single) As Single
    GetNewBPM = bpm * BASS_FX_TempoGetRateRatio(chan)
End Function

Public Sub DecodingBPM(ByVal newStream As Boolean, ByVal startSec As Double, ByVal endSec As Double)
    If (newStream) Then
        ' open the same file as played but for bpm decoding detection
        bpmChan = BASS_StreamCreateFile(BASSFALSE, StrPtr(frmBPM.CMD.filename), 0, 0, BASS_STREAM_DECODE)
        If (bpmChan = 0) Then bpmChan = BASS_MusicLoad(BASSFALSE, StrPtr(frmBPM.CMD.filename), 0, 0, BASS_MUSIC_DECODE Or BASS_MUSIC_PRESCAN, 0)
    End If

    ' detect bpm in background and return progress in GetBPM_ProgressCallback function
    If (bpmChan) Then bpmValue = BASS_FX_BPM_DecodeGet(bpmChan, startSec, endSec, 0, BASS_FX_BPM_BKGRND Or BASS_FX_BPM_MULT2 Or BASS_FX_FREESOURCE, AddressOf GetBPM_ProgressCallback, 0)

    ' update the bpm view
    If (bpmValue) Then frmBPM.lblBPM.Caption = "BPM: " & Format(GetNewBPM(bpmValue), "0.00")
End Sub

'====================
' CALLBACK FUNCTIONS
'====================

' get bpm value after period of time (called by BASS_FX_BPM_CallbackSet function)
Public Sub GetBPM_Callback(ByVal handle As Long, ByVal bpm As Single, ByVal user As Long)
    bpmValue = bpm
    If (bpm) Then frmBPM.lblBPM.Caption = "BPM: " & Format(GetNewBPM(bpm), "0.00")  ' update the bpm view
End Sub

' get bpm detection progress in percents (called by BASS_FX_BPM_DecodeGet function)
Public Sub GetBPM_ProgressCallback(ByVal chan As Long, ByVal percent As Single, ByVal user As Long)
    frmBPM.pbProgress.value = percent   ' update the progress bar
End Sub

' get beat position in seconds (called by BASS_FX_BPM_BeatCallbackSet function)
Public Sub GetBeatPos_Callback(ByVal handle As Long, ByVal beatpos As Double, ByVal user As Long)
    Dim curpos As Double
    curpos = BASS_ChannelBytes2Seconds(handle, BASS_ChannelGetPosition(handle, BASS_POS_BYTE))
    uTimerID = timeSetEvent((beatpos - curpos) * 1000, 0, AddressOf beatTimerProc, handle, TIME_ONESHOT)
End Sub

' beat timer proc (called by timeSetEvent function)
Public Sub beatTimerProc(ByVal uTimerID As Long, ByVal uMsg As Long, ByVal dwUser As Long, ByVal dw1 As Long, ByVal dw2 As Long)
    If (BASS_FX_TempoGetRateRatio(dwUser)) Then
        frmBPM.lblBeat.Caption = "Beat pos: " & Format(BASS_ChannelBytes2Seconds(dwUser, BASS_ChannelGetPosition(dwUser, BASS_POS_BYTE)) / BASS_FX_TempoGetRateRatio(dwUser), "0.00")
    End If
    Call timeKillEvent(uTimerID)
End Sub
