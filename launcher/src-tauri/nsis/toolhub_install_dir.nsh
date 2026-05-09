!macro NSIS_HOOK_PREINSTALL
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\ToolHub"
  ; Tauri inserts this hook after an initial SetOutPath, so reset it too.
  SetOutPath $INSTDIR
!macroend
