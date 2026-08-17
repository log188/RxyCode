; RxyCode Desktop installer customizations (electron-builder NSIS include).
;
; Requirements:
;   - Default install directory: %USERPROFILE%\.rxycode\desktop
;     (the same location `rxycode gui` searches at runtime).
;   - Assisted (non-oneClick) wizard so the user can pick a custom
;     directory via the standard "Browse..." button.
;   - Desktop shortcut created by default but cancelable via the wizard
;     checkbox (createDesktopShortcut: always renders it checked).
;   - Installer UI language follows the OS: Chinese on Chinese systems,
;     English everywhere else.

; --- Default install directory -------------------------------------------------
; electron-builder's assisted installer normally defaults to
; %LOCALAPPDATA%\Programs\${productName}. Override it so first-run matches the
; runtime search path used by `rxycode gui` (~/.rxycode/desktop).
!define DEFAULT_INSTALL_DIR "$PROFILE\.rxycode\desktop"

!macro customInstall
  ; Nothing extra: the stock assistant macro installs the app files and
  ; creates shortcuts according to createDesktopShortcut.
!macroend

!macro customUnInstall
!macroend

; --- Wizard language ------------------------------------------------------------------
; installerLanguages: [en_US, zh_CN] makes NSIS auto-detect the system UI
; language; en_US is the fallback for any non-Chinese locale.
;
; The stock electron-builder assistant already ships localized strings for
; the directory page and the "Create a desktop shortcut" checkbox for the
; languages listed in installerLanguages, so no extra LangString work is
; required here.

; --- Directory page: prefill default install dir on first run -------------------------
; Runs right after the standard Init. Honor silent `/D=` and a user-chosen
; path: only replace electron-builder's stock LOCALAPPDATA\Programs location
; (or an empty INSTDIR) with ~/.rxycode/desktop. Do not overwrite /D=.
!macro customInit
  StrCmp "$INSTDIR" "" rxy_use_default
  StrCmp "$INSTDIR" "$LOCALAPPDATA\Programs\RxyCode Desktop" rxy_use_default
  StrCmp "$INSTDIR" "$LOCALAPPDATA\Programs\rxycode-desktop" rxy_use_default
  Goto rxy_keep_instdir
  rxy_use_default:
    StrCpy $INSTDIR "${DEFAULT_INSTALL_DIR}"
  rxy_keep_instdir:
!macroend