!macro NSIS_HOOK_PREINSTALL
  SetShellVarContext current
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\ToolHub"
!macroend
