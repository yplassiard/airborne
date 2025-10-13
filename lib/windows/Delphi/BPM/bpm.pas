{========================================================================
 bpm.pas - Copyright (c) 2003-2013 (: JOBnik! :) [Arthur Aminov, ISRAEL]
                                                 [http://www.jobnik.org]
                                                 [bass_fx @ jobnik .org]

 * BPM Callbacks working by: DJ-Chris

 BASS_FX bpm with tempo & samplerate changers
 * Requires: BASS 2.4 (available @ www.un4seen.com)
========================================================================}

unit bpm;

interface

uses
	Windows, Messages, SysUtils, Classes, Graphics, Controls, Forms, Dialogs,
	StdCtrls, ComCtrls,  MMSystem, BASS, BASS_FX;

type
	TfrmBPM = class(TForm)
		GroupBox: TGroupBox;
		lblTempo: TLabel;
		lblSamplerate: TLabel;
		lblPosition: TLabel;
		lblVolume: TLabel;
		tbTempo: TTrackBar;
		tbSamplerate: TTrackBar;
		tbVolume: TTrackBar;
		hsPosition: TScrollBar;
		btnOpen: TButton;
		od: TOpenDialog;
		lblBPM: TLabel;
		chkBPMCallback: TCheckBox;
		ebPeriod: TEdit;
		lblProgress: TLabel;
		pbProgress: TProgressBar;
		lblBeat: TLabel;
		chkBeat: TCheckBox;
		procedure FormCreate(Sender: TObject);
		procedure Error(msg: string);
		procedure FormDestroy(Sender: TObject);
		procedure btnOpenClick(Sender: TObject);
		procedure UpdatePositionLabel();
		function GetNewBPM(bpm: Single): Single;
		procedure DecodingBPM(newStream: Boolean; startSec, endSec: DOUBLE);
		procedure tbTempoChange(Sender: TObject);
		procedure tbSamplerateChange(Sender: TObject);
		procedure tbVolumeChange(Sender: TObject);
		procedure hsPositionChange(Sender: TObject);
		procedure hsPositionScroll(Sender: TObject; ScrollCode: TScrollCode; var ScrollPos: Integer);
		procedure lblTempoClick(Sender: TObject);
		procedure lblSamplerateClick(Sender: TObject);
		procedure chkBPMCallbackClick(Sender: TObject);
		procedure chkBeatClick(Sender: TObject);
		private
			{ Private declarations }
		public
			{ Public declarations }
			chan: DWORD;               // tempo channel handle
			bpmChan: DWORD;            // decoding channel handle for BPM detection
			bpmValue: Single;           // bpm value returned by BASS_FX_BPM_DecodeGet/GetBPM_Callback functions
			info: BASS_CHANNELINFO;
	end;

var
	frmBPM: TfrmBPM;

implementation

{$R *.DFM}

{====================
  CALLBACK FUNCTIONS
 ====================}

// get bpm value after period of time (called by BASS_FX_BPM_CallbackSet function)
procedure GetBPM_Callback(handle: DWORD; bpm: Single; user: Pointer); stdcall;
begin
	frmBPM.bpmValue := bpm;
	if (bpm > 0) then frmBPM.lblBPM.Caption := 'BPM: ' + FormatFloat('###.##', frmBPM.GetNewBPM(bpm));	// update the bpm view
end;

// get bpm detection progress in percents (called by BASS_FX_BPM_DecodeGet function)
procedure GetBPM_ProgressCallback(chan: DWORD; percent: Single; user: Pointer); stdcall;
begin
	frmBPM.pbProgress.position := round(percent);	// update the progress bar
end;

// beat timer proc (called by timeSetEvent function)
procedure beatTimerProc(uTimerID, uMsg: Uint; dwUser, dw1, dw2: DWORD); stdcall;
var
	beatpos: Single;
begin
	if (BASS_FX_TempoGetRateRatio(dwUser) > 0) then begin
		beatpos := BASS_ChannelBytes2Seconds(dwUser, BASS_ChannelGetPosition(dwUser, BASS_POS_BYTE)) / BASS_FX_TempoGetRateRatio(dwUser);
		frmBPM.lblBeat.Caption := 'Beat pos: ' + FormatFloat('###.##', beatpos);
	end;
	timeKillEvent(uTimerID);
end;

// get beat position in seconds (called by BASS_FX_BPM_BeatCallbackSet function)
procedure GetBeatPos_Callback(handle: DWORD; beatpos: DOUBLE; user: Pointer); stdcall;
var
	curpos: DOUBLE;
begin
	curpos := BASS_ChannelBytes2Seconds(handle, BASS_ChannelGetPosition(handle, BASS_POS_BYTE));
	timeSetEvent(round((beatpos - curpos) * 1000), 0, @beatTimerProc, handle, TIME_ONESHOT);
end;

{========================
  END CALLBACK FUNCTIONS
 ========================}

// display error dialogs
procedure TFrmBPM.Error(msg: string);
var
	s: string;
begin
	s := msg + #13#10 + #13#10 + '(error code: ' + IntToStr(BASS_ErrorGetCode) + ')';
	MessageBox(handle, PChar(s), 'Error', MB_ICONEXCLAMATION);
end;

// show the approximate position in MM:SS format according to Tempo change
procedure TfrmBPM.UpdatePositionLabel();
var
	totalsec, posec: Single;
begin
	if (BASS_FX_TempoGetRateRatio(chan) > 0) then begin
		totalsec := hsPosition.max / BASS_FX_TempoGetRateRatio(chan);
		posec := hsPosition.position / BASS_FX_TempoGetRateRatio(chan);

		lblPosition.Caption := 'Playing position: ' +
								format('%2.2d:%2.2d', [trunc(posec) div 60, trunc(posec) mod 60]) + ' / ' +
								format('%2.2d:%2.2d', [trunc(totalsec) div 60, trunc(totalsec) mod 60]);
	end;
end;

// calculate approximate bpm value according to Tempo change
function TfrmBPM.GetNewBPM(bpm: Single): Single;
begin
	Result := bpm * BASS_FX_TempoGetRateRatio(chan);
end;

procedure TfrmBPM.DecodingBPM(newStream: Boolean; startSec, endSec: DOUBLE);
begin
	if (newStream) then begin
		// open the same file as played but for bpm decoding detection
		bpmChan := BASS_StreamCreateFile(FALSE, PChar(od.FileName), 0, 0, BASS_STREAM_DECODE {$IFDEF UNICODE} or BASS_UNICODE {$ENDIF});
		if (bpmChan = 0) then bpmChan := BASS_MusicLoad(FALSE, PChar(od.FileName), 0, 0, BASS_MUSIC_DECODE Or BASS_MUSIC_PRESCAN {$IFDEF UNICODE} or BASS_UNICODE {$ENDIF}, 0);
	end;

	// detect bpm in background and return progress in GetBPM_ProgressCallback function
	if (bpmChan > 0) then bpmValue := BASS_FX_BPM_DecodeGet(bpmChan, startSec, endSec, 0, BASS_FX_BPM_BKGRND Or BASS_FX_BPM_MULT2 Or BASS_FX_FREESOURCE, @GetBPM_ProgressCallback, 0);

	// update the bpm view
	if (bpmValue > 0) then lblBPM.Caption := 'BPM: ' + FormatFloat('###.##', GetNewBPM(bpmValue));
end;

procedure TfrmBPM.FormCreate(Sender: TObject);
begin
	// check the correct BASS was loaded
	If (HiWord(BASS_GetVersion()) <> BASSVERSION) then begin
		application.MessageBox('An incorrect version of BASS.DLL was loaded (2.4 is required)', 'Incorrect BASS.DLL', MB_ICONERROR or MB_OK);
		application.Terminate;
	end;

	// check the correct BASS_FX was loaded
	If (HiWord(BASS_FX_GetVersion()) <> BASSVERSION) then begin
		application.MessageBox('An incorrect version of BASS_FX.DLL was loaded (2.4 is required)', 'Incorrect BASS_FX.DLL', MB_ICONERROR or MB_OK);
		application.Terminate;
	end;

	// setup output - default device, 44100hz, stereo, 16 bits
	If (BASS_Init(-1, 44100, 0, frmBPM.handle, Nil) = false) then begin
		Error('Can''t initialize device');
		application.Terminate;
	end;
end;

procedure TfrmBPM.FormDestroy(Sender: TObject);
begin
	BASS_Free;    // free BASS & BASS_FX
end;

procedure TfrmBPM.btnOpenClick(Sender: TObject);
var
    pos, maxpos, period, endSec: DOUBLE;
begin
	od.Filename := '';
	od.Filter :=  'Playable files|*.mo3;*.xm;*.mod;*.s3m;*.it;*.mtm;*.mp3;*.mp2;*.mp1;*.ogg;*.wav;*.aif|All files|*.*';
	If od.Execute = false then exit;

	// free decode bpm stream and resources
	BASS_FX_BPM_Free(bpmChan);

	// free tempo, stream, music & bpm/beat callbacks
	BASS_StreamFree(chan);

	// create decode channel
	chan := BASS_StreamCreateFile(FALSE, pChar(od.filename), 0, 0, BASS_STREAM_DECODE {$IFDEF UNICODE} or BASS_UNICODE {$ENDIF});
	If (chan = 0) Then chan := BASS_MusicLoad(FALSE, pChar(od.filename), 0, 0, BASS_MUSIC_RAMP or BASS_MUSIC_PRESCAN or BASS_MUSIC_DECODE {$IFDEF UNICODE} or BASS_UNICODE {$ENDIF}, 0);

	If (chan = 0) then begin
		btnOpen.Caption := 'click here to open a file && play it...';
		Error('Selected file couldnt be loaded!');
		Exit;
	end;

	// get channel info
	BASS_ChannelGetInfo(chan, info);

	// set max length to hsPosition scroller
	hsPosition.max := round(BASS_ChannelBytes2Seconds(chan, BASS_ChannelGetLength(chan, BASS_POS_BYTE)));
	hsPosition.position := 0;

	// create a new stream - decoded & resampled :)
	chan := BASS_FX_TempoCreate(chan, BASS_SAMPLE_LOOP Or BASS_FX_FREESOURCE);

	If (chan = 0) Then begin
		btnOpen.Caption := 'click here to open a file && play it...';
		Error('Couldn''t create a resampled stream!');
		BASS_StreamFree(chan);
		BASS_MusicFree(chan);
		Exit;
	End;

	// update the button to show the loaded file name
	btnOpen.Caption := ExtractFileName(pChar(od.Filename));

	// set Volume
	tbVolume.OnChange(Self);

	// set rate min/max values according to current frequency
	With tbSamplerate do begin
		min := 0;								// to avoid min > max
		max := 1;								// to avoid max < min
		max := round(info.freq * 1.3);			// by +30%
		min := round(info.freq * 0.7);			// by -30%
		pagesize := round(info.freq * 0.01);	// by 1%
	End;

	// update the Rate label hint
	lblSamplerate.hint := 'click to set Samplerate to ' + IntToStr(info.freq) + 'Hz';

	// set tempo/rate to normal
	lblTempo.OnClick(Self);
	lblSamplerate.OnClick(Self);

	// update the approximate time in seconds view
	UpdatePositionLabel;

	// set the callback bpm and beat
	chkBPMCallback.OnClick(Self);
	chkBeat.OnClick(Self);

	// play new created stream
	BASS_ChannelPlay(chan, FALSE);

  	// create bpmChan stream and get bpm value for txtPeriod seconds from current position
    pos := hsPosition.Position;
    period := StrToInt(ebPeriod.Text);
    maxpos := hsPosition.max;
    if (pos + period >= maxpos) then
        endSec := maxpos - 1
    else
        endSec := pos + period;

	DecodingBPM(TRUE, pos, endSec);
end;

procedure TfrmBPM.tbTempoChange(Sender: TObject);
begin
	If (BASS_ChannelIsActive(chan) = 0) then exit;

	// set new tempo
	BASS_ChannelSetAttribute(chan, BASS_ATTRIB_TEMPO, tbTempo.position);
	lblTempo.Caption := 'Tempo = ' + IntToStr(tbTempo.position) + '%';

	// update the bpm view
	lblBPM.Caption := 'BPM: ' + FormatFloat('###.##', GetNewBPM(bpmValue));

	// update the approximate time in seconds view
	UpdatePositionLabel;
end;

procedure TfrmBPM.tbSamplerateChange(Sender: TObject);
begin
	If (BASS_ChannelIsActive(chan) = 0) then exit;

	// set new sample rate
	BASS_ChannelSetAttribute(chan, BASS_ATTRIB_TEMPO_FREQ, tbSamplerate.position);
	lblSamplerate.Caption := 'Samplerate = ' + IntToStr(tbSamplerate.position) + 'Hz';

	// update the bpm view
	lblBPM.Caption := 'BPM: ' + FormatFloat('###.##', GetNewBPM(bpmValue));

	// update the approximate time in seconds view
	UpdatePositionLabel;
end;

procedure TfrmBPM.tbVolumeChange(Sender: TObject);
begin
	BASS_ChannelSetAttribute(chan, BASS_ATTRIB_VOL, (100 - tbVolume.position) / 100);
end;

procedure TfrmBPM.hsPositionChange(Sender: TObject);
begin
	If (BASS_ChannelIsActive(chan) = 0) then exit;

	// update the approximate time in seconds view
	UpdatePositionLabel;
end;

procedure TfrmBPM.hsPositionScroll(Sender: TObject; ScrollCode: TScrollCode; var ScrollPos: Integer);
var
    pos, maxpos, period, endSec: DOUBLE;
begin
	If (BASS_ChannelIsActive(chan) = 0) then exit;

	if (ScrollCode = scEndScroll) then begin
		BASS_ChannelSetPosition(chan, BASS_ChannelSeconds2Bytes(chan, hsPosition.position), BASS_POS_BYTE);

		// get bpm value for txtPeriod seconds from current position
        pos := hsPosition.Position;
        period := StrToInt(ebPeriod.Text);
        maxpos := hsPosition.max;
        if (pos + period >= maxpos) then
            endSec := maxpos - 1
        else
            endSec := pos + period;

    	DecodingBPM(FALSE, pos, endSec);
	end;
	// update the approximate time in seconds view
	UpdatePositionLabel;
end;

procedure TfrmBPM.lblTempoClick(Sender: TObject);
begin
	tbTempo.position := 0;
	tbTempo.OnChange(Self);
end;

procedure TfrmBPM.lblSamplerateClick(Sender: TObject);
begin
	if (info.freq > 0) then
		tbSamplerate.position := info.freq
	else
		tbSamplerate.position := 44100;

	tbSamplerate.OnChange(Self);
end;

procedure TfrmBPM.chkBPMCallbackClick(Sender: TObject);
begin
	if (chkBPMCallback.Checked) then
		BASS_FX_BPM_CallbackSet(chan, @GetBPM_Callback, StrToFloat(ebPeriod.Text), 0, BASS_FX_BPM_MULT2, 0)
	else
		BASS_FX_BPM_Free(chan);
end;

procedure TfrmBPM.chkBeatClick(Sender: TObject);
begin
	if (chkBeat.Checked) then
		BASS_FX_BPM_BeatCallbackSet(chan, @GetBeatPos_Callback, 0)
	else
		BASS_FX_BPM_BeatFree(chan);
end;

end.
