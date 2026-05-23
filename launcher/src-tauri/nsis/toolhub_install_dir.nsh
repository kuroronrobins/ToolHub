!macro NSIS_HOOK_PREINSTALL
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\ToolHub"
  ; Tauri inserts this hook after an initial SetOutPath, so reset it too.
  SetOutPath $INSTDIR
  ; Keep user data under $LOCALAPPDATA\ToolHub, but replace managed payload
  ; directories so removed apps do not remain visible after reinstall/update.
  RMDir /r "$INSTDIR\apps"
  RMDir /r "$INSTDIR\runner"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\config.default"
  RMDir /r "$INSTDIR\release"
  RMDir /r "$INSTDIR\tools"
  RMDir /r "$INSTDIR\updater"
  RMDir /r "$INSTDIR\installer"
  Delete "$INSTDIR\README.md"
!macroend
