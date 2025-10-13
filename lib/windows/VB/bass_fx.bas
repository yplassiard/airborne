Attribute VB_Name = "BASS_FX"
'=============================================================================
' BASS_FX 2.4 - Copyright (c) 2002-2018 (: JOBnik! :) [Arthur Aminov, ISRAEL]
'                                                     [http://www.jobnik.org]
'
'         bugs/suggestions/questions:
'           forum  : http://www.un4seen.com/forum/?board=1
'                    http://www.jobnik.org/forums
'           e-mail : bass_fx@jobnik.org
'        --------------------------------------------------
'
' NOTE: This module will work only with BASS_FX version 2.4.12
'       Check www.un4seen.com or www.jobnik.org for any later versions.
'
' * Requires BASS 2.4 (available at http://www.un4seen.com)
'=============================================================================

' BASS_CHANNELINFO types
Public Const BASS_CTYPE_STREAM_TEMPO = &H1f200
Public Const BASS_CTYPE_STREAM_REVERSE = &H1f201

' Tempo / Reverse / BPM / Beat flag
Public Const BASS_FX_FREESOURCE = &H10000     ' Free the source handle as well?

' BASS_FX Version
Public Declare Function BASS_FX_GetVersion Lib "bass_fx.dll" () As Long

'=============================================================================
'	DSP (Digital Signal Processing)
'=============================================================================

'	Multi-channel order of each channel is as follows:
'	 3 channels       left-front, right-front, center.
'	 4 channels       left-front, right-front, left-rear/side, right-rear/side.
'	 5 channels       left-front, right-front, center, left-rear/side, right-rear/side.
'	 6 channels (5.1) left-front, right-front, center, LFE, left-rear/side, right-rear/side.
'	 8 channels (7.1) left-front, right-front, center, LFE, left-rear/side, right-rear/side, left-rear center, right-rear center.

' DSP channels flags
Public Const BASS_BFX_CHANALL = -1            ' all channels at once (as by default)
Public Const BASS_BFX_CHANNONE = 0            ' disable an effect for all channels
Public Const BASS_BFX_CHAN1 = 1               ' left-front channel
Public Const BASS_BFX_CHAN2 = 2               ' right-front channel
Public Const BASS_BFX_CHAN3 = 4               ' see above info
Public Const BASS_BFX_CHAN4 = 8               ' see above info
Public Const BASS_BFX_CHAN5 = 16              ' see above info
Public Const BASS_BFX_CHAN6 = 32              ' see above info
Public Const BASS_BFX_CHAN7 = 64              ' see above info
Public Const BASS_BFX_CHAN8 = 128             ' see above info

' if you have more than 8 channels (7.1), use BASS_BFX_CHANNEL_N(n) function below

' DSP effects
Public Enum BFX
    BASS_FX_BFX_ROTATE = &H10000              ' A channels volume ping-pong  / multi-channel
    BASS_FX_BFX_ECHO                          ' Echo                         / 2 channels max   (deprecated)
    BASS_FX_BFX_FLANGER                       ' Flanger                      / multi channel    (deprecated)
    BASS_FX_BFX_VOLUME                        ' Volume                       / multi channel
    BASS_FX_BFX_PEAKEQ                        ' Peaking Equalizer            / multi channel
    BASS_FX_BFX_REVERB                        ' Reverb                       / 2 channels max   (deprecated)
    BASS_FX_BFX_LPF                           ' Low Pass Filter 24dB         / multi channel    (deprecated)
    BASS_FX_BFX_MIX                           ' Swap, remap and mix channels / multi channel
    BASS_FX_BFX_DAMP                          ' Dynamic Amplification        / multi channel
    BASS_FX_BFX_AUTOWAH                       ' Auto Wah                     / multi channel
    BASS_FX_BFX_ECHO2                         ' Echo 2                       / multi channel    (deprecated)
    BASS_FX_BFX_PHASER                        ' Phaser                       / multi channel
    BASS_FX_BFX_ECHO3                         ' Echo 3                       / multi channel    (deprecated)
    BASS_FX_BFX_CHORUS                        ' Chorus/Flanger               / multi channel
    BASS_FX_BFX_APF                           ' All Pass Filter              / multi channel    (deprecated)
    BASS_FX_BFX_COMPRESSOR                    ' Compressor                   / multi channel    (deprecated)
    BASS_FX_BFX_DISTORTION                    ' Distortion                   / multi channel
    BASS_FX_BFX_COMPRESSOR2                   ' Compressor 2                 / multi channel
    BASS_FX_BFX_VOLUME_ENV                    ' Volume envelope              / multi channel
    BASS_FX_BFX_BQF                           ' BiQuad filters               / multi channel
    BASS_FX_BFX_ECHO4                         ' Echo 4                       / multi channel
    BASS_FX_BFX_PITCHSHIFT                    ' Pitch shift using FFT        / multi channel    (not available on mobile)
    BASS_FX_BFX_FREEVERB                      ' Reverb using "Freeverb" algo / multi channel
End Enum

' Deprecated effects in 2.4.10 version:
' ------------------------------------
' BASS_FX_BFX_ECHO        -> use BASS_FX_BFX_ECHO4
' BASS_FX_BFX_ECHO2       -> use BASS_FX_BFX_ECHO4
' BASS_FX_BFX_ECHO3       -> use BASS_FX_BFX_ECHO4
' BASS_FX_BFX_REVERB      -> use BASS_FX_BFX_FREEVERB
' BASS_FX_BFX_FLANGER     -> use BASS_FX_BFX_CHORUS
' BASS_FX_BFX_COMPRESSOR  -> use BASS_FX_BFX_COMPRESSOR2
' BASS_FX_BFX_APF         -> use BASS_FX_BFX_BQF with BASS_BFX_BQF_ALLPASS filter
' BASS_FX_BFX_LPF         -> use 2x BASS_FX_BFX_BQF with BASS_BFX_BQF_LOWPASS filter and appropriate fQ values

' Rotate
Public Type BASS_BFX_ROTATE
    fRate As Single                           ' rotation rate/speed in Hz (A negative rate can be used for reverse direction)
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s (supported only even number of channels)
End Type

' Echo (deprecated)
Public Type BASS_BFX_ECHO
    fLevel As Single                          ' [0....1....n] linear
    lDelay As Long                            ' [1200..30000]
End Type

' Flanger (deprecated)
Public Type BASS_BFX_FLANGER
    fWetDry As Single                         ' [0....1....n] linear
    fSpeed As Single                          ' [0......0.09]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Volume
Public Type BASS_BFX_VOLUME
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s or 0 for global volume control
    fVolume As Single                         ' [0....1....n] linear
End Type

' Peaking Equalizer
Public Type BASS_BFX_PEAKEQ
    lBand As Long                             ' [0...............n] more bands means more memory & cpu usage
    fBandwidth As Single                      ' [0.1...........<10] in octaves - fQ is not in use (Bandwidth has a priority over fQ)
    fQ As Single                              ' [0...............1] the EE kinda definition (linear) (if Bandwidth is not in use)
    fCenter As Single                         ' [1Hz..<info.freq/2] in Hz
    fGain As Single                           ' [-15dB...0...+15dB] in dB (can be above/below these limits)
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Reverb (deprecated)
Public Type BASS_BFX_REVERB
    fLevel As Single                          ' [0....1....n] linear
    lDelay As Long                            ' [1200..10000]
End Type

' Low Pass Filter (deprecated)
Public Type BASS_BFX_LPF
    fResonance As Single                      ' [0.01............10]
    fCutOffFreq As Single                     ' [1Hz....info.freq/2] cutoff frequency
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Swap, remap and mix
Public Type BASS_BFX_MIX
    lChannel As Long                          ' a pointer to an array of channels to mix using BASS_BFX_CHANxxx flag/s (lChannel[0] is left channel...)
End Type

' Dynamic Amplification
Public Type BASS_BFX_DAMP
    fTarget As Single                         ' target volume level                      [0<......1] linear
    fQuiet As Single                          ' quiet  volume level                      [0.......1] linear
    fRate As Single                           ' amp adjustment rate                      [0.......1] linear
    fGain As Single                           ' amplification level                      [0...1...n] linear
    fDelay As Single                          ' delay in seconds before increasing level [0.......n] linear
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Auto Wah
Public Type BASS_BFX_AUTOWAH
    fDryMix As Single                         ' dry (unaffected) signal mix              [-2......2]
    fWetMix As Single                         ' wet (affected) signal mix                [-2......2]
    fFeedback As Single                       ' output signal to feed back into input	 [-1......1]
    fRate As Single                           ' rate of sweep in cycles per second       [0<....<10]
    fRange As Single                          ' sweep range in octaves                   [0<....<10]
    fFreq As Single                           ' base frequency of sweep Hz               [0<...1000]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Echo 2 (deprecated)
Public Type BASS_BFX_ECHO2
    fDryMix As Single                         ' dry (unaffected) signal mix              [-2......2]
    fWetMix As Single                         ' wet (affected) signal mix                [-2......2]
    fFeedback As Single                       ' output signal to feed back into input	 [-1......1]
    fDelay As Single                          ' delay sec                                [0<......n]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Phaser
Public Type BASS_BFX_PHASER
    fDryMix As Single                         ' dry (unaffected) signal mix              [-2......2]
    fWetMix As Single                         ' wet (affected) signal mix                [-2......2]
    fFeedback As Single                       ' output signal to feed back into input	 [-1......1]
    fRate As Single                           ' rate of sweep in cycles per second       [0<....<10]
    fRange As Single                          ' sweep range in octaves                   [0<....<10]
    fFreq As Single                           ' base frequency of sweep                  [0<...1000]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Echo 3 (deprecated)
Public Type BASS_BFX_ECHO3
    fDryMix As Single                         ' dry (unaffected) signal mix              [-2......2]
    fWetMix As Single                         ' wet (affected) signal mix                [-2......2]
    fDelay As Single                          ' delay sec                                [0<......n]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Chorus/Flanger
Public Type BASS_BFX_CHORUS
    fDryMix As Single                         ' dry (unaffected) signal mix              [-2......2]
    fWetMix As Single                         ' wet (affected) signal mix                [-2......2]
    fFeedback As Single                       ' output signal to feed back into input	 [-1......1]
    fMinSweep As Single                       ' minimal delay ms                         [0<..<6000]
    fMaxSweep As Single                       ' maximum delay ms                         [0<..<6000]
    fRate As Single                           ' rate ms/s                                [0<...1000]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' All Pass Filter (deprecated)
Public Type BASS_BFX_APF
    fGain As Single                           ' reverberation time                       [-1=<..<=1]
    fDelay As Single                          ' delay sec                                [0<....<=n]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Compressor (deprecated)
Public Type BASS_BFX_COMPRESSOR
    fThreshold As Single                      ' compressor threshold                     [0<=...<=1]
    fAttacktime As Single                     ' attack time ms                           [0<.<=1000]
    fReleasetime As Single                    ' release time ms                          [0<.<=5000]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Distortion
Public Type BASS_BFX_DISTORTION
    fDrive As Single                          ' distortion drive                         [0<=...<=5]
    fDryMix As Single                         ' dry (unaffected) signal mix              [-5<=..<=5]
    fWetMix As Single                         ' wet (affected) signal mix                [-5<=..<=5]
    fFeedback As Single                       ' output signal to feed back into input	 [-1<=..<=1]
    fVolume As Single                         ' distortion volume                        [0=<...<=2]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Compressor 2
Public Type BASS_BFX_COMPRESSOR2
    fGain As Single                           ' output gain of signal after compression  [-60....60] in dB
    fThreshold As Single                      ' point at which compression begins        [-60.....0] in dB
    fRatio As Single                          ' compression ratio                        [1.......n]
    fAttack As Single                         ' attack time in ms                        [0.01.1000]
    fRelease As Single                        ' release time in ms                       [0.01.5000]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Volume envelope
Public Type BASS_BFX_ENV_NODE
    pos As Double                             ' node position in seconds (1st envelope node must be at position 0)
    val_ As Single                            ' node value
End Type

Public Type BASS_BFX_VOLUME_ENV
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
    lNodeCount As Long                        ' number of nodes
    pNodes As Long                            ' the nodes. Pointer to nodes of BASS_BFX_ENV_NODE
    bFollow As Long                           ' follow source position
End Type

' BiQuad Filters
Public Enum BQF
    BASS_BFX_BQF_LOWPASS
    BASS_BFX_BQF_HIGHPASS
    BASS_BFX_BQF_BANDPASS                     ' constant 0 dB peak gain
    BASS_BFX_BQF_BANDPASS_Q                   ' constant skirt gain, peak gain = Q
    BASS_BFX_BQF_NOTCH
    BASS_BFX_BQF_ALLPASS
    BASS_BFX_BQF_PEAKINGEQ
    BASS_BFX_BQF_LOWSHELF
    BASS_BFX_BQF_HIGHSHELF
End Enum

Public Type BASS_BFX_BQF
    lFilter As Integer                        ' BASS_BFX_BQF_xxx filter types
    fCenter As Single                         ' [1Hz..<info.freq/2] Cutoff (central) frequency in Hz
    fGain As Single                           ' [-15dB...0...+15dB] Used only for PEAKINGEQ and Shelving filters in dB (can be above/below these limits)
    fBandwidth As Single                      ' [0.1...........<10] Bandwidth in octaves (fQ is not in use (fBandwidth has a priority over fQ))
                                              '                     (between -3 dB frequencies for BANDPASS and NOTCH or between midpoint
                                              '                     (fGgain/2) gain frequencies for PEAKINGEQ)
    fQ As Single                              ' [0.1.............1] The EE kinda definition (linear) (if fBandwidth is not in use)
    fS As Single                              ' [0.1.............1] A "shelf slope" parameter (linear) (used only with Shelving filters)
                                              '                     when fS = 1, the shelf slope is as steep as you can get it and remain monotonically
                                              '                     increasing or decreasing gain with frequency.
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Echo 4
Public Type BASS_BFX_ECHO4
    fDryMix As Single                         ' dry (unaffected) signal mix              [-2.......2]
    fWetMix As Single                         ' wet (affected) signal mix                [-2.......2]
    fFeedback As Single                       ' output signal to feed back into input    [-1.......1]
    fDelay As Single                          ' delay sec                                [0<.......n]
    bStereo As Long                           ' echo adjoining channels to each other    [TRUE/FALSE]
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Pitch shift (not available on mobile)
Public Type BASS_BFX_PITCHSHIFT
    fPitchShift As Single                     ' A factor value which is between 0.5 (one octave down) and 2 (one octave up) (1 won't change the pitch) [1 default]
                                              ' (fSemitones is not in use, fPitchShift has a priority over fSemitones)
    fSemitones As Single                      ' Semitones (0 won't change the pitch) [0 default]
    lFFTsize As Long                          ' Defines the FFT frame size used for the processing. Typical values are 1024, 2048 and 4096 [2048 default]
                                              ' It may be any value <= 8192 but it MUST be a power of 2
    lOsamp As Long                            ' Is the STFT oversampling factor which also determines the overlap between adjacent STFT frames [8 default]
                                              ' It should at least be4 for moderate scaling ratios. A value of 32 is recommended for best quality (better quality = higher CPU usage)
    lChannel As Long                          ' BASS_BFX_CHANxxx flag/s
End Type

' Freeverb
Public Const BASS_BFX_FREEVERB_MODE_FREEZE = 1

Public Type BASS_BFX_FREEVERB
    fDryMix As Single                          ' dry (unaffected) signal mix            [0........1], def. 0
    fWetMix As Single                          ' wet (affected) signal mix              [0........3], def. 1.0f
    fRoomSize As Single                        ' room size                              [0........1], def. 0.5f
    fDamp As Single                            ' damping                                [0........1], def. 0.5f
    fWidth As Single                           ' stereo width                           [0........1], def. 1
    lMode As Long                              ' 0 or BASS_BFX_FREEVERB_MODE_FREEZE, def. 0 (no freeze)
    lChannel As Long                           ' BASS_BFX_CHANxxx flag/s
End Type
'=============================================================================
'   set dsp fx          - BASS_ChannelSetFX
'   remove dsp fx       - BASS_ChannelRemoveFX
'   set parameters      - BASS_FXSetParameters
'   retrieve parameters - BASS_FXGetParameters
'   reset the state     - BASS_FXReset
'=============================================================================

'=============================================================================
'   Tempo, Pitch scaling and Sample rate changers
'=============================================================================

' NOTE: Enable Tempo supported flags in BASS_FX_TempoCreate and the others to source handle.

' tempo attributes (BASS_ChannelSet/GetAttribute)
Public Enum TempoAttribs
    BASS_ATTRIB_TEMPO = &H10000
    BASS_ATTRIB_TEMPO_PITCH
    BASS_ATTRIB_TEMPO_FREQ
End Enum

' tempo attributes options
Public Enum TempoAttribsOptions
    BASS_ATTRIB_TEMPO_OPTION_USE_AA_FILTER = &H10010    ' TRUE (default) / FALSE (default for multi-channel on mobile devices for lower CPU usage)
    BASS_ATTRIB_TEMPO_OPTION_AA_FILTER_LENGTH           ' 32 default (8 .. 128 taps)
    BASS_ATTRIB_TEMPO_OPTION_USE_QUICKALGO              ' TRUE (default on mobile devices for lower CPU usage) / FALSE (default)
    BASS_ATTRIB_TEMPO_OPTION_SEQUENCE_MS                ' 82 default, 0 = automatic
    BASS_ATTRIB_TEMPO_OPTION_SEEKWINDOW_MS              ' 28 default, 0 = automatic
    BASS_ATTRIB_TEMPO_OPTION_OVERLAP_MS                 ' 8  default
    BASS_ATTRIB_TEMPO_OPTION_PREVENT_CLICK              ' TRUE / FALSE (default)
End Enum

' tempo algorithm flags
Public Const BASS_FX_TEMPO_ALGO_LINEAR = &H200
Public Const BASS_FX_TEMPO_ALGO_CUBIC = &H400           ' default
Public Const BASS_FX_TEMPO_ALGO_SHANNON = &H800

Public Declare Function BASS_FX_TempoCreate Lib "bass_fx.dll" (ByVal chan As Long, ByVal flags As Long) As Long
Public Declare Function BASS_FX_TempoGetSource Lib "bass_fx.dll" (ByVal chan As Long) As Long
Public Declare Function BASS_FX_TempoGetRateRatio Lib "bass_fx.dll" (ByVal chan As Long) As Single

'=============================================================================
'   Reverse playback
'=============================================================================

' NOTE: 1. MODs won't load without BASS_MUSIC_PRESCAN flag.
'       2. Enable Reverse supported flags in BASS_FX_ReverseCreate and the others to source handle.

' reverse attribute (BASS_ChannelSet/GetAttribute)
Public Const BASS_ATTRIB_REVERSE_DIR = &H11000

' playback directions
Public Const BASS_FX_RVS_REVERSE = -1
Public Const BASS_FX_RVS_FORWARD = 1

Public Declare Function BASS_FX_ReverseCreate Lib "bass_fx.dll" (ByVal chan As Long, ByVal dec_block As Single, ByVal flags As Long) As Long
Public Declare Function BASS_FX_ReverseGetSource Lib "bass_fx.dll" (ByVal chan As Long) As Long

'=============================================================================
'   BPM (Beats Per Minute)
'=============================================================================

' bpm flags
Public Const BASS_FX_BPM_BKGRND = 1   ' if in use, then you can do other processing while detection's in progress. Available only in Windows platforms (BPM/Beat)
Public Const BASS_FX_BPM_MULT2 = 2    ' if in use, then will auto multiply bpm by 2 (if BPM < minBPM*2)

' translation options (deprecated)
Public Enum bpmTranslation
    BASS_FX_BPM_TRAN_X2         ' multiply the original BPM value by 2 (may be called only once & will change the original BPM as well!)
    BASS_FX_BPM_TRAN_2FREQ      ' BPM value to Frequency
    BASS_FX_BPM_TRAN_FREQ2      ' Frequency to BPM value
    BASS_FX_BPM_TRAN_2PERCENT   ' BPM value to Percents
    BASS_FX_BPM_TRAN_PERCENT2   ' Percents to BPM value
End Enum

Public Declare Function BASS_FX_BPM_DecodeGet Lib "bass_fx.dll" (ByVal chan As Long, ByVal startSec As Double, ByVal endSec As Double, ByVal minMaxBPM As Long, ByVal flags As Long, ByVal proc As Long, ByVal user As Long) As Single
Public Declare Function BASS_FX_BPM_CallbackSet Lib "bass_fx.dll" (ByVal handle As Long, ByVal proc As Long, ByVal period As Double, ByVal minMaxBPM As Long, ByVal flags As Long, ByVal user As Long) As Long
Public Declare Function BASS_FX_BPM_CallbackReset Lib "bass_fx.dll" (ByVal handle As Long) As Long
Public Declare Function BASS_FX_BPM_Translate Lib "bass_fx.dll" (ByVal handle As Long, ByVal val2tran As Single, ByVal trans As Long) As Single ' deprecated
Public Declare Sub BASS_FX_BPM_Free Lib "bass_fx.dll" (ByVal handle As Long)

'=============================================================================
'   Beat position trigger
'=============================================================================

Public Declare Function BASS_FX_BPM_BeatCallbackSet Lib "bass_fx.dll" (ByVal handle As Long, ByVal proc As Long, ByVal user As Long) As Long
Public Declare Function BASS_FX_BPM_BeatCallbackReset Lib "bass_fx.dll" (ByVal handle As Long) As Long
Public Declare Function BASS_FX_BPM_BeatDecodeGet Lib "bass_fx.dll" (ByVal handle As Long, ByVal startSec As Double, ByVal endSec As Double, ByVal flags As Long, ByVal proc As Long, ByVal user As Long) As Long
Public Declare Function BASS_FX_BPM_BeatSetParameters Lib "bass_fx.dll" (ByVal handle As Long, ByVal bandwidth As Single, ByVal centerfreq As Single, ByVal beat_rtime As Single) As Long
Public Declare Function BASS_FX_BPM_BeatGetParameters Lib "bass_fx.dll" (ByVal handle As Long, ByRef bandwidth As Single, ByRef centerfreq As Single, ByRef beat_rtime As Single) As Long
Public Declare Sub BASS_FX_BPM_BeatFree Lib "bass_fx.dll" (ByVal handle As Long)

'=============================================================================
'   Callback functions
'=============================================================================

Public Sub BPMPROC(ByVal chan As Long, ByVal bpm As Single, ByVal user As Long)
End Sub

Public Sub BPMPROGRESSPROC(ByVal chan As Long, ByVal percent As Single, ByVal user As Long)
End Sub

Public Sub BPMBEATPROC(ByVal chan As Long, ByVal beatpos As Double, ByVal user As Long)
End Sub

'=============================================================================
'   Macros
'=============================================================================

' If you have more than 8 channels (7.1), use this function
Public Function BASS_BFX_CHANNEL_N(ByVal n As Long) As Long
    BASS_BFX_CHANNEL_N = 2 ^ (n - 1)
End Function

' translate linear level to logarithmic dB
Public Function BASS_BFX_Linear2dB(ByVal level As Double) As Double
    BASS_BFX_Linear2dB = 20 * (Math.Log(level) / 2.30258509299405)   ' base 10 logarithm
End Function

' translate logarithmic dB level to linear
Public Function BASS_BFX_dB2Linear(ByVal dB As Double) As Double
    BASS_BFX_dB2Linear = 10 ^ (dB / 20)
End Function
