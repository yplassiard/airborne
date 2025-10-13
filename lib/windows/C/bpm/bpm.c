/***************************************************************************
 bpm.c/h/rc - Copyright (c) 2003-2013 (: JOBnik! :) [Arthur Aminov, ISRAEL]
                                                    [http://www.jobnik.org]
                                                    [bass_fx @ jobnik .org]
 BASS_FX bpm with tempo & samplerate changers
 * Imports: bass.lib, bass_fx.lib
            kernel32.lib, user32.lib, comdlg32.lib, gdi32.lib, winmm.lib
***************************************************************************/

#include <windows.h>
#include <commctrl.h>
#include <stdio.h>
#include "bass.h"
#include "bass_fx.h"
#include "bpm.h"

HWND win=NULL;
HINSTANCE inst;

HFONT Font;				// bpm static text font

DWORD chan;				// tempo channel handle
DWORD bpmChan;			// decoding channel handle for BPM detection
float bpmValue;			// bpm value returned by BASS_FX_BPM_DecodeGet/GetBPM_Callback functions
BASS_CHANNELINFO info;

#define MESS(id,m,w,l) SendDlgItemMessage(win,id,m,(WPARAM)w,(LPARAM)l)

OPENFILENAME ofn;
char path[MAX_PATH];

// display error dialogs
void Error(const char *es)
{
	char mes[200];
	sprintf(mes,"%s\n\n(error code: %d)",es,BASS_ErrorGetCode());
	MessageBox(win,mes,"Error",MB_ICONEXCLAMATION);
}

// show the approximate position in MM:SS format according to Tempo change
void UpdatePositionLabel()
{
	if(!BASS_FX_TempoGetRateRatio(chan)) return;
	{
		char c[30];
		float totalsec=(float)MESS(IDC_POS,TBM_GETRANGEMAX,0,0)/BASS_FX_TempoGetRateRatio(chan);
		float posec=(float)MESS(IDC_POS,TBM_GETPOS,0,0)/BASS_FX_TempoGetRateRatio(chan);
		sprintf(c,"Playing position: %02d:%02d / %02d:%02d", (int)posec/60,(int)posec%60,(int)totalsec/60,(int)totalsec%60);
		MESS(IDC_SPOS,WM_SETTEXT,0,c);
	}
}

// calculate approximate bpm value according to Tempo change
float GetNewBPM(float bpm)
{
	return bpm * BASS_FX_TempoGetRateRatio(chan);
}

// get bpm value after period of time (called by BASS_FX_BPM_CallbackSet function)
void CALLBACK GetBPM_Callback(DWORD handle, float bpm, void *user)
{
	bpmValue = bpm;
	if (bpm) {
		// update the bpm view
		char c[30];
		sprintf(c,"BPM: %0.2f", GetNewBPM(bpm));
		MESS(IDC_SBPM,WM_SETTEXT,0,c);
	}
}

// beat timer proc (called by timeSetEvent function)
void CALLBACK beatTimerProc(UINT uTimerID, UINT uMsg, DWORD dwUser, DWORD dw1, DWORD dw2)
{
    if (BASS_FX_TempoGetRateRatio(dwUser)) {
		double beatpos;
		char c[30];

		beatpos = BASS_ChannelBytes2Seconds(dwUser, BASS_ChannelGetPosition(dwUser, BASS_POS_BYTE)) / BASS_FX_TempoGetRateRatio(dwUser);
		sprintf(c,"Beat pos: %0.2f", beatpos);
		MESS(IDC_SBEAT,WM_SETTEXT,0,c);
	}
	timeKillEvent(uTimerID);
}

// get beat position in seconds (called by BASS_FX_BPM_BeatCallbackSet function)
void CALLBACK GetBeatPos_Callback(DWORD handle, double beatpos, void *user)
{
	double curpos;
    curpos = BASS_ChannelBytes2Seconds(handle, BASS_ChannelGetPosition(handle, BASS_POS_BYTE));
    timeSetEvent((UINT)((beatpos - curpos) * 1000.0f), 0, (LPTIMECALLBACK)beatTimerProc, handle, TIME_ONESHOT);
}

// get bpm detection progress in percents (called by BASS_FX_BPM_DecodeGet function)
void CALLBACK GetBPM_ProgressCallback(DWORD chan, float percent, void *user)
{
	MESS(IDC_PRGRSBPM,PBM_SETPOS,(int)percent,0);	// update the progress bar
}

void DecodingBPM(BOOL newStream, double startSec, double endSec, const char *fp)
{
	char c[30];

	if (newStream) {
		// open the same file as played but for bpm decoding detection
		bpmChan = BASS_StreamCreateFile(FALSE, fp, 0, 0, BASS_STREAM_DECODE);
		if (!bpmChan) bpmChan = BASS_MusicLoad(FALSE, fp, 0, 0, BASS_MUSIC_DECODE|BASS_MUSIC_PRESCAN, 0);
	}

	// detect bpm in background and return progress in GetBPM_ProgressCallback function
	if (bpmChan) bpmValue = BASS_FX_BPM_DecodeGet(bpmChan, startSec, endSec, 0, BASS_FX_BPM_BKGRND|BASS_FX_BPM_MULT2|BASS_FX_FREESOURCE, (BPMPROGRESSPROC*)GetBPM_ProgressCallback, 0);

	// update the bpm view
	if (bpmValue) {
		sprintf(c,"BPM: %0.2f", GetNewBPM(bpmValue));
		MESS(IDC_SBPM,WM_SETTEXT,0,c);
	}
}

// get the file name from the file path
char *GetFileName(const char *fp)
{
	unsigned char slash_location;
	fp = strrev(fp);
	slash_location = strchr(fp, '\\') - fp;
	return (strrev(fp) + strlen(fp) - slash_location);
}

BOOL CALLBACK dialogproc(HWND h,UINT m,WPARAM w,LPARAM l)
{
	DWORD p=0;
	char c[30];

	switch (m) {
		case WM_COMMAND:
			switch (LOWORD(w)) {
				case ID_OPEN:
					{
						char file[MAX_PATH]="";
						ofn.lpstrFilter="playable files\0*.mo3;*.xm;*.mod;*.s3m;*.it;*.mtm;*.mp3;*.mp2;*.mp1;*.ogg;*.wav;*.aif\0All files\0*.*\0\0";
						ofn.lpstrFile=file;
						if (GetOpenFileName(&ofn)) {
							memcpy(path,file,ofn.nFileOffset);
							path[ofn.nFileOffset-1]=0;

							// free decode bpm stream and resources
							BASS_FX_BPM_Free(bpmChan);

							// free tempo, stream, music & bpm/beat callbacks
							BASS_StreamFree(chan);

							// create decode channel
							chan = BASS_StreamCreateFile(FALSE, file, 0, 0, BASS_STREAM_DECODE);
							if (!chan) chan = BASS_MusicLoad(FALSE, file, 0, 0, BASS_MUSIC_RAMP|BASS_MUSIC_PRESCAN|BASS_MUSIC_DECODE, 0);

							if (!chan) {
								// not a WAV/MP3 or MOD
								MESS(ID_OPEN,WM_SETTEXT,0,"click here to open a file && play it...");
								Error("Selected file couldn't be loaded!");
								break;
							}

							// get channel info
							BASS_ChannelGetInfo(chan, &info);

							// set max length to position slider
							p = (DWORD)BASS_ChannelBytes2Seconds(chan, BASS_ChannelGetLength(chan, BASS_POS_BYTE));
							MESS(IDC_POS,TBM_SETRANGEMAX,0,p);
							MESS(IDC_POS,TBM_SETPOS,TRUE,0);

							// create a new stream - decoded & resampled :)
							if (!(chan=BASS_FX_TempoCreate(chan, BASS_SAMPLE_LOOP|BASS_FX_FREESOURCE))) {
								MESS(ID_OPEN,WM_SETTEXT,0,"click here to open a file && play it...");
								Error("Couldn't create a resampled stream!");
								BASS_StreamFree(chan);
								BASS_MusicFree(chan);
								break;
							}

							// update the button to show the loaded file name (without path)
							MESS(ID_OPEN,WM_SETTEXT,0,GetFileName(file));

							// set Volume
							p = MESS(IDC_VOL,TBM_GETPOS,0,0);
							BASS_ChannelSetAttribute(chan, BASS_ATTRIB_VOL, (float)(100 - p)/100.0f);

							// set rate min/max values according to current frequency
							MESS(IDC_RATE,TBM_SETRANGEMAX,0,(long)((float)info.freq * 1.3f));	// by +30%
							MESS(IDC_RATE,TBM_SETRANGEMIN,0,(long)((float)info.freq * 0.7f));	// by -30%
							MESS(IDC_RATE,TBM_SETPOS,TRUE,(long)info.freq);
							MESS(IDC_RATE,TBM_SETPAGESIZE,0,(long)((float)info.freq * 0.01f));	// by 1%

							// update rate view
							sprintf(c,"Samplerate = %dHz", (long)info.freq);
							MESS(IDC_SRATE,WM_SETTEXT,0,c);

							// update tempo slider & view
							MESS(IDC_TEMPO,TBM_SETPOS,TRUE,0);
							MESS(IDC_STEMPO,WM_SETTEXT,0,"Tempo = 0%");

							// update the approximate time in seconds view
							UpdatePositionLabel();

							// set the callback bpm and beat
							SendMessage(win,WM_COMMAND,IDC_CHKPERIOD,l);
							SendMessage(win,WM_COMMAND,IDC_CHKBEAT,l);

							// play new created stream
							BASS_ChannelPlay(chan,FALSE);

							// create bpmChan stream and get bpm value for IDC_EPBPM seconds from current position
							GetDlgItemText(win, IDC_EPBPM, c, 5);
							{
								double pos=(double)MESS(IDC_POS,TBM_GETPOS,0,0);
								double maxpos=(double)MESS(IDC_POS,TBM_GETRANGEMAX,0,0);
								double period=atof(c);
								DecodingBPM(TRUE, pos, (pos+period)>=maxpos?maxpos-1:pos+period,file);
							}
						}
					}
				return 1;

				case IDC_CHKPERIOD:
					if(MESS(IDC_CHKPERIOD,BM_GETCHECK,0,0)){
						GetDlgItemText(win, IDC_EPBPM, c, 5);
						BASS_FX_BPM_CallbackSet(chan, (BPMPROC*)GetBPM_Callback, (double)atof(c), 0, BASS_FX_BPM_MULT2, 0);
					}else
						BASS_FX_BPM_Free(chan);
				return 1;

				case IDC_CHKBEAT:
					if(MESS(IDC_CHKBEAT,BM_GETCHECK,0,0)){
						BASS_FX_BPM_BeatCallbackSet(chan, (BPMBEATPROC*)GetBeatPos_Callback, 0);
					}else
						BASS_FX_BPM_BeatFree(chan);
				return 1;
			}
			break;

		case WM_VSCROLL:
			if(GetDlgCtrlID((HWND)l) == IDC_VOL)
				BASS_ChannelSetAttribute(chan, BASS_ATTRIB_VOL, (float)(100 - MESS(IDC_VOL,TBM_GETPOS,0,0))/100.0f);
		break;

		case WM_HSCROLL:
			{
				if(!BASS_ChannelIsActive(chan)) break;

				switch (GetDlgCtrlID((HWND)l)) {
					case IDC_TEMPO:
						// set new tempo
						p = MESS(IDC_TEMPO, TBM_GETPOS, 0, 0);
						BASS_ChannelSetAttribute(chan, BASS_ATTRIB_TEMPO, (float)(signed)p);

						// update tempo static text
						sprintf(c,"Tempo = %d%%", p);
						MESS(IDC_STEMPO,WM_SETTEXT,0,c);
					case IDC_RATE:
						// set new samplerate
						p = MESS(IDC_RATE, TBM_GETPOS, 0, 0);
						BASS_ChannelSetAttribute(chan, BASS_ATTRIB_TEMPO_FREQ, (float)p);

						sprintf(c,"Samplerate = %dHz", p);
						MESS(IDC_SRATE,WM_SETTEXT,0,c);

						// update the bpm view
						sprintf(c,"BPM: %0.2f", GetNewBPM(bpmValue));
						MESS(IDC_SBPM,WM_SETTEXT,0,c);

						// update the approximate time in seconds view
						UpdatePositionLabel();
					break;
					case IDC_POS:
						// change the position
						if (LOWORD(w) == SB_ENDSCROLL) { // seek to new pos
							p = MESS(IDC_POS,TBM_GETPOS,0,0);
							BASS_ChannelSetPosition(chan, (QWORD)BASS_ChannelSeconds2Bytes(chan, (double)p), BASS_POS_BYTE);

							// get bpm value for IDC_EPBPM seconds from current position
							GetDlgItemText(win, IDC_EPBPM, c, 5);
							{
								double pos=(double)MESS(IDC_POS,TBM_GETPOS,0,0);
								double maxpos=(double)MESS(IDC_POS,TBM_GETRANGEMAX,0,0);
								double period=atof(c);
								DecodingBPM(FALSE, pos, (pos+period)>=maxpos?maxpos-1:pos+period,"");
							}
						}
						// update the approximate time in seconds view
						UpdatePositionLabel();
					break;
				}
			}
			return 1;

		case WM_CLOSE:
			EndDialog(h, 0);
			return 1;
		break;

		case WM_INITDIALOG:
			win=h;
			GetCurrentDirectory(MAX_PATH,path);
			memset(&ofn,0,sizeof(ofn));
			ofn.lStructSize=sizeof(ofn);
			ofn.hwndOwner=h;
			ofn.hInstance=inst;
			ofn.nMaxFile=MAX_PATH;
			ofn.Flags=OFN_HIDEREADONLY|OFN_EXPLORER;

			// setup output - default device, 44100hz, stereo, 16 bits
			if (!BASS_Init(-1,44100,0,win,NULL)) {
				Error("Can't initialize device");
				DestroyWindow(win);
				return 1;
			}
    
			// volume
			MESS(IDC_VOL,TBM_SETRANGEMAX,0,100);
			MESS(IDC_VOL,TBM_SETPOS,TRUE,50);
			MESS(IDC_VOL,TBM_SETPAGESIZE,0,5);

			// tempo
			MESS(IDC_TEMPO,TBM_SETRANGEMAX,TRUE,30);
			MESS(IDC_TEMPO,TBM_SETRANGEMIN,TRUE,-30);
			MESS(IDC_TEMPO,TBM_SETPOS,TRUE,0);
			MESS(IDC_TEMPO,TBM_SETPAGESIZE,0,1);

			// rate
			MESS(IDC_RATE,TBM_SETRANGEMAX,0,(long)(44100.0f * 1.3f));
			MESS(IDC_RATE,TBM_SETRANGEMIN,0,(long)(44100.0f * 0.7f));
			MESS(IDC_RATE,TBM_SETPOS,TRUE,44100);
			MESS(IDC_RATE,TBM_SETPAGESIZE,0,(long)(44100.0f * 0.01f));	// by 1%

			// bpm detection progress
			MESS(IDC_PRGRSBPM,PBM_SETRANGE32,0,100);

			// set the bpm period edit box, as a default of 30 seconds
			MESS(IDC_EPBPM,WM_SETTEXT,0,"30");

			// set the bpm static text font
			Font = CreateFont(-12,0,0,0,FW_BOLD,0,0,0,0,0,0,0,0,"Tahoma");
			MESS(IDC_SBPM, WM_SETFONT, Font, TRUE);
			MESS(IDC_SBEAT, WM_SETFONT, Font, TRUE);

			return 1;
	}

	return 0;
}

int PASCAL WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,LPSTR lpCmdLine, int nCmdShow)
{
	inst=hInstance;

	// check the correct BASS was loaded
	if (HIWORD(BASS_GetVersion())!=BASSVERSION) {
		MessageBox(0,"An incorrect version of BASS.DLL was loaded (2.4 is required)","Incorrect BASS.DLL",MB_ICONERROR);
		return 1;
	}

	// check the correct BASS_FX was loaded
	if (HIWORD(BASS_FX_GetVersion())!=BASSVERSION) {
		MessageBox(0,"An incorrect version of BASS_FX.DLL was loaded (2.4 is required)","Incorrect BASS_FX.DLL",MB_ICONERROR);
		return 1;
	}

	DialogBox(inst,(char*)1000,0,&dialogproc);

	BASS_Free();

	DeleteObject(Font);

	return 0;
}