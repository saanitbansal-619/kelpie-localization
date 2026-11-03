# Laptop-only pinger checks. Does not upload firmware or open a serial port.
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Report = Join-Path $Root "arduino_pinger\HOST_VERIFICATION.md"
$Exe = Join-Path $env:TEMP "test_pinger_logic.exe"
$Obj = Join-Path $env:TEMP "test_pinger_logic.obj"
$CompileLog = Join-Path $env:TEMP "pinger_uno_compile.log"

function Find-ArduinoCli {
  $cmd = Get-Command arduino-cli -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  $bundled = Join-Path $env:LOCALAPPDATA "Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
  if (Test-Path $bundled) {
    return $bundled
  }
  return $null
}

$compiler = "none"
$hostExit = 1
$gpp = Get-Command g++ -ErrorAction SilentlyContinue
if ($gpp) {
  $compiler = "g++"
  & g++ -std=c++11 -Wall -Wextra -I arduino_pinger -o $Exe arduino_pinger\test_pinger_logic.cpp
  if ($LASTEXITCODE -eq 0) {
    $hostExit = 0
  }
} else {
  $vcvars = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
  if (Test-Path $vcvars) {
    $compiler = "MSVC cl /std:c++14 /W4"
    $bat = Join-Path $env:TEMP "build_pinger_test.bat"
    @(
      "@echo off",
      "call `"$vcvars`" >nul",
      "cl /nologo /std:c++14 /W4 /EHsc /I arduino_pinger /Fo:`"$Obj`" /Fe:`"$Exe`" arduino_pinger\test_pinger_logic.cpp",
      "exit /b %ERRORLEVEL%"
    ) | Set-Content -Path $bat -Encoding ASCII
    cmd /c $bat
    if ($LASTEXITCODE -eq 0) {
      $hostExit = 0
    }
  } else {
    Write-Host "NO_HOST_COMPILER"
  }
}

$stamp = "{0} | built with {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss K"), $compiler
if ($hostExit -eq 0) {
  & $Exe $Report $stamp
  $hostExit = $LASTEXITCODE
} elseif (-not (Test-Path $Report)) {
  @(
    "# Pinger host verification",
    "",
    "Run: $stamp",
    "",
    "## Logic results",
    "",
    "| Check | Result | Failures |",
    "| --- | --- | ---: |",
    "| Host test compile | FAIL | 1 |",
    "",
    "The host compiler did not produce test_pinger_logic.exe, so no logic checks ran.",
    "",
    "## Firmware compile",
    "",
    "<!-- BEGIN_COMPILE -->",
    "Result: NOT RUN",
    "<!-- END_COMPILE -->"
  ) | Set-Content -Path $Report -Encoding utf8
}

$cli = Find-ArduinoCli
if (-not $cli) {
  $compileBody = @"
Result: NOT RUN

Arduino CLI was not on PATH, and the Arduino IDE 2 copy was not found at ``%LOCALAPPDATA%\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe``.
This report does not claim a successful firmware build.

From the repository root, after installing Arduino CLI or Arduino IDE 2:

``````
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli compile --warnings all --fqbn arduino:avr:uno arduino_pinger/robosub_pinger
``````
"@
  $compileExit = 0
} else {
  & $cli compile --warnings all --fqbn arduino:avr:uno arduino_pinger/robosub_pinger *> $CompileLog
  $compileExit = $LASTEXITCODE
  $logText = Get-Content -Path $CompileLog -Raw
  $sizeLines = Select-String -Path $CompileLog -Pattern "Sketch uses |Global variables use " | ForEach-Object { $_.Line.Trim() }
  $sketchIssues = Select-String -Path $CompileLog -Pattern "robosub_pinger|pinger_logic\.h" | Where-Object { $_.Line -match "warning:|error:" }
  if ($compileExit -eq 0) {
    $compileBody = "Result: PASS`r`n`r`nCLI: ``$cli```r`n`r`nBoard: ``arduino:avr:uno```r`n`r`n"
    foreach ($line in $sizeLines) {
      $compileBody += "$line`r`n`r`n"
    }
    if ($sketchIssues) {
      $compileBody += "Sketch diagnostics:`r`n`r`n"
      foreach ($issue in $sketchIssues) {
        $compileBody += "- $($issue.Line.Trim())`r`n"
      }
    } else {
      $compileBody += "No warnings or errors were reported in the sketch or ``pinger_logic.h``. The Arduino core may still print its own unused-parameter warnings.`r`n"
    }
  } else {
    $tail = Get-Content -Path $CompileLog -Tail 40
    $compileBody = "Result: FAIL`r`n`r`nCLI: ``$cli```r`n`r`nExit code: $compileExit`r`n`r`n``````r`n$($tail -join "`r`n")`r`n``````r`n"
  }
  if (-not $logText) {
    $compileBody += "`r`nCompiler log was empty.`r`n"
  }
}

$reportText = Get-Content -Path $Report -Raw
$pattern = "(?s)<!-- BEGIN_COMPILE -->.*?<!-- END_COMPILE -->"
$inserted = "<!-- BEGIN_COMPILE -->`r`n$compileBody`r`n<!-- END_COMPILE -->"
$updated = [regex]::Replace($reportText, $pattern, { param($m) $inserted })
if ($updated -eq $reportText) {
  $updated = $reportText.TrimEnd() + "`r`n`r`n## Firmware compile`r`n`r`n$inserted`r`n"
}
Set-Content -Path $Report -Value $updated -Encoding utf8 -NoNewline

if ($hostExit -ne 0 -or $compileExit -ne 0) {
  exit 1
}
exit 0
