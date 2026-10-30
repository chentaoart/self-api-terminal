# 打包：
#   默认   -> dist\自用API终端\（目录版：运行时不需要临时目录，最稳）
#   -OneFile -> dist\自用API终端.exe（单文件：启动时要解包到 %TEMP%）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -OneFile
param([switch]$OneFile)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root '.venv\Scripts\python.exe'
$name = 'HermesTerminalNative'   # 生成后再由 rename_dist.py 改成中文名

if (-not (Test-Path $py)) { throw "missing venv: $py" }

$common = @(
  '--noconfirm', '--clean', '--windowed',
  '--name', $name,
  '--icon', (Join-Path $root 'icon.ico'),
  '--add-data', 'icon.ico;.',
  # WebEngine 现在是按需 import，显式声明一下，别被分析漏掉
  '--hidden-import', 'PySide6.QtWebEngineWidgets',
  '--hidden-import', 'PySide6.QtWebEngineCore',
  '--hidden-import', 'PySide6.QtTextToSpeech',
  # 没用到的大件（QtWebEngine/Qml/Multimedia 要用，不能排）
  '--exclude-module', 'PySide6.Qt3DCore',
  '--exclude-module', 'PySide6.Qt3DRender',
  '--exclude-module', 'PySide6.Qt3DInput',
  '--exclude-module', 'PySide6.Qt3DLogic',
  '--exclude-module', 'PySide6.Qt3DAnimation',
  '--exclude-module', 'PySide6.Qt3DExtras',
  '--exclude-module', 'PySide6.QtCharts',
  '--exclude-module', 'PySide6.QtDataVisualization',
  '--exclude-module', 'PySide6.QtGraphs',
  '--exclude-module', 'PySide6.QtBluetooth',
  '--exclude-module', 'PySide6.QtNfc',
  '--exclude-module', 'PySide6.QtSql',
  '--exclude-module', 'PySide6.QtTest',
  '--exclude-module', 'PySide6.QtDesigner',
  '--exclude-module', 'PySide6.QtHelp',
  '--exclude-module', 'PySide6.QtUiTools',
  '--exclude-module', 'PySide6.QtRemoteObjects',
  '--exclude-module', 'PySide6.QtScxml',
  '--exclude-module', 'PySide6.QtSensors',
  '--exclude-module', 'PySide6.QtSerialBus',
  '--exclude-module', 'PySide6.QtSerialPort',
  '--exclude-module', 'PySide6.QtSpatialAudio',
  '--exclude-module', 'PySide6.QtStateMachine',
  '--exclude-module', 'PySide6.QtPdf',
  '--exclude-module', 'tkinter'
)

Push-Location $root
try {
  Remove-Item -Recurse -Force (Join-Path $root 'dist') -ErrorAction SilentlyContinue
  if ($OneFile) {
    & $py -m PyInstaller @common --onefile app.py
  } else {
    & $py -m PyInstaller @common --onedir app.py
  }
  if ($LASTEXITCODE -ne 0) { throw 'pyinstaller failed' }

  & $py (Join-Path $root 'rename_dist.py')
  if ($LASTEXITCODE -ne 0) { throw 'rename failed' }

  Get-ChildItem (Join-Path $root 'dist') -Recurse -Filter *.exe | ForEach-Object {
    Write-Host ("done: {0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB))
  }
} finally {
  Pop-Location
}
