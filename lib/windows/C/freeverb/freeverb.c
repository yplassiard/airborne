/***************************************************************************
 freeverb.c/h/rc - Copyright (c) 2014 (: JOBnik! :) [Arthur Aminov, ISRAEL]
                                                    [http://www.jobnik.org]
                                                    [bass_fx @ jobnik .org]
 
 BASS_FX Freeverb test
 * Imports: bass.lib, bass_fx.lib
            kernel32.lib, user32.lib, comdlg32.lib, gdi32.lib
***************************************************************************/

#include <windows.h>
#include <commctrl.h>
#include <stdio.h>
#include "bass.h"
#include "bass_fx.h"
#include "freeverb.h"

HWND win=NULL;
HINSTANCE inst;
HFONT Font;					// font handle

DWORD chan;					// channel handle
DWORD floatable;			// floating-point channel support?
HFX fxFreeverb=0;			// dsp fx handle
DWORD cn=0;					// channels
BASS_CHANNELINFO info;

#define MESS(id,m,w,l) SendDlgItemMessage(win,id,m,(WPARAM)w,(LPARAM)l)
#define DLGITEM(id) GetDlgItem(win,id)
#define TB_GETPOS(id) MESS(id,TBM_GETPOS,0,0)

OPENFILENAME ofn;
char path[MAX_PATH];

// display error dialogs
void Error(const char *es)
{
	char mes[200];
	sprintf(mes,"%s\n\n(error code: %d)",es,BASS_ErrorGetCode());
	MessageBox(win,mes,"Error",MB_ICONEXCLAMATION);
}

// get the file name from the file path
char *GetFileName(char *filepath)
{
	unsigned char slash_location;
	filepath=strrev(filepath);
	slash_location=strchr(filepath, '\\')-filepath;
	return (strrev(filepath)+strlen(filepath)-slash_location);
}

// update fx
void UpdateFX(int b)
{
	BASS_BFX_FREEVERB frb;

	if (b != IDC_CHKMODE) {
		if (MESS(b,BM_GETCHECK,0,0)) cn|=b;
		else cn&=~b; 
	}

	BASS_FXGetParameters(fxFreeverb, &frb);
		frb.fDryMix=(float)TB_GETPOS(IDC_DRYMIX)/1000.0f;
		frb.fWetMix=(float)TB_GETPOS(IDC_WETMIX)/1000.0f;
		frb.fRoomSize=(float)TB_GETPOS(IDC_ROOMSIZE)/1000.0f;
		frb.fDamp=(float)TB_GETPOS(IDC_DAMP)/1000.0f;
		frb.fWidth=(float)TB_GETPOS(IDC_WIDTH)/1000.0f;
		frb.lMode=MESS(IDC_CHKMODE,BM_GETCHECK,0,0);
		frb.lChannel=cn;
	BASS_FXSetParameters(fxFreeverb, &frb);
}

BOOL CALLBACK dialogproc(HWND h,UINT m,WPARAM w,LPARAM l)
{
	char c[50];
	int i, ci;

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

							// free previous dsp effects & handles
							BASS_StreamFree(chan);	// free stream
							BASS_MusicFree(chan);	// free music

							if(!(chan=BASS_StreamCreateFile(FALSE, file, 0, 0, BASS_SAMPLE_LOOP|floatable))&&
								!(chan=BASS_MusicLoad(FALSE, file, 0, 0, BASS_MUSIC_LOOP|BASS_MUSIC_RAMP|floatable,0))){
								// not a WAV/MP3 or MOD
								MESS(ID_OPEN,WM_SETTEXT,0,"click here to open a file && play it...");
								Error("Selected file couldnt be loaded!");
								break;
							}

							// get channel info
							BASS_ChannelGetInfo(chan, &info);

							// update the button to show the loaded file name
							MESS(ID_OPEN,WM_SETTEXT,0,GetFileName(file));

							// set dsp effect
							SendMessage(win,WM_COMMAND,IDC_CHKFRB,l);

							// set channels
							for (i=IDC_CHKCHAN1,ci=0;i<=IDC_CHKCHAN8;i*=2,ci++) {
								if (ci<info.chans) {	// enable and set available channels
									MESS(i,BM_SETCHECK,1,0);
									EnableWindow(DLGITEM(i),TRUE);
								} else {	// disable and unset unavailable channels
									MESS(i,BM_SETCHECK,0,0);
									EnableWindow(DLGITEM(i),FALSE);
								}
								UpdateFX(i);
							}

							// uncheck freeze mode
							MESS(IDC_CHKMODE,BM_SETCHECK,0,0);

							// play
							BASS_ChannelPlay(chan, FALSE);
						}
					}
					return 1;

				case IDC_CHKFRB:
					if(MESS(IDC_CHKFRB,BM_GETCHECK,0,0)){
						fxFreeverb=BASS_ChannelSetFX(chan, BASS_FX_BFX_FREEVERB,0);
						MESS(IDC_CHKMODE,BM_SETCHECK,0,0);	// uncheck freeze mode
						UpdateFX(0);
					} else {
						BASS_ChannelRemoveFX(chan, fxFreeverb);
						fxFreeverb=0;
					}
				return 1;

				case IDC_CHKCHAN1:
				case IDC_CHKCHAN2:
				case IDC_CHKCHAN3:
				case IDC_CHKCHAN4:
				case IDC_CHKCHAN5:
				case IDC_CHKCHAN6:
				case IDC_CHKCHAN7:
				case IDC_CHKCHAN8:
				case IDC_CHKMODE:
					if (l) UpdateFX(GetDlgCtrlID((HWND)l));
				return 1;
			}
			return 1;

		case WM_HSCROLL:
			switch (GetDlgCtrlID((HWND)l)) {
				case IDC_DRYMIX:
				case IDC_WETMIX:
				case IDC_ROOMSIZE:
				case IDC_DAMP:
				case IDC_WIDTH:
					UpdateFX(0);
			}
			return 1;

		case WM_INITDIALOG:
			win=h;
			GetCurrentDirectory(MAX_PATH,path);
			memset(&ofn,0,sizeof(ofn));
			ofn.lStructSize=sizeof(ofn);
			ofn.hwndOwner=h;
			ofn.hInstance=inst;
			ofn.nMaxFile=MAX_PATH;
			ofn.Flags=OFN_HIDEREADONLY|OFN_EXPLORER;

			// enable floating-point DSP
			BASS_SetConfig(BASS_CONFIG_FLOATDSP, TRUE);

			// setup output - default device, 44100hz, stereo, 16 bits
			if (!BASS_Init(-1,44100,0,win,NULL)) {
				Error("Can't initialize device");
				DestroyWindow(win);
				return 1;
			}

			// check for floating-point capability
			floatable=BASS_StreamCreate(44100, 2, BASS_SAMPLE_FLOAT, 0, 0);
			if (floatable) {
				BASS_StreamFree(floatable);  //woohoo!
				floatable=BASS_SAMPLE_FLOAT;
			}

			// DryMix
			MESS(IDC_DRYMIX,TBM_SETRANGE,0,MAKELONG(0,1000));
			MESS(IDC_DRYMIX,TBM_SETPOS,TRUE,0);

			// WetMix
			MESS(IDC_WETMIX,TBM_SETRANGE,0,MAKELONG(0,3000));
			MESS(IDC_WETMIX,TBM_SETPOS,TRUE,1000);

			// RoomSize
			MESS(IDC_ROOMSIZE,TBM_SETRANGE,0,MAKELONG(0,1000));
			MESS(IDC_ROOMSIZE,TBM_SETPOS,TRUE,500);

			// Damp
			MESS(IDC_DAMP,TBM_SETRANGE,0,MAKELONG(0,1000));
			MESS(IDC_DAMP,TBM_SETPOS,TRUE,500);

			// Width
			MESS(IDC_WIDTH,TBM_SETRANGE,0,MAKELONG(0,1000));
			MESS(IDC_WIDTH,TBM_SETPOS,TRUE,1000);

			// disable all channel checkboxes
			for (i=IDC_CHKCHAN1;i<=IDC_CHKCHAN8;i*=2) {
				MESS(i,BM_SETCHECK,0,0);
				EnableWindow(DLGITEM(i),FALSE);
			}

			Font=CreateFont(-12,0,0,0,FW_BOLD,FALSE,FALSE,FALSE,ANSI_CHARSET,OUT_STRING_PRECIS,
				            CLIP_STROKE_PRECIS,DRAFT_QUALITY,DEFAULT_PITCH | FF_DONTCARE,
							"MS Sans Serif");
			// set the font for the "Freeverb" checkbox
			MESS(IDC_CHKFRB, WM_SETFONT, Font, TRUE);
		return 1;

		case WM_CLOSE:
			EndDialog(h,0);
			return 0;
		break;
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
