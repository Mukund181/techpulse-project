$ErrorActionPreference = 'Stop'
$projectCode = $PSScriptRoot
$submissionRoot = Split-Path $projectCode -Parent
$projectRoot = Split-Path $submissionRoot -Parent
$runtimeRoot = Join-Path $projectRoot 'runtime'
$pythonRoot = Join-Path $runtimeRoot 'python'
$llamaRoot = Join-Path $runtimeRoot 'llama'
$downloadRoot = Join-Path $runtimeRoot 'downloads'
New-Item -ItemType Directory -Force -Path $pythonRoot,$llamaRoot,$downloadRoot,(Join-Path $runtimeRoot 'logs') | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$manifest = Get-Content -Raw -LiteralPath (Join-Path $submissionRoot 'Model_Prompts_Config\download_manifest.json') | ConvertFrom-Json
$pythonExe = Join-Path $pythonRoot 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonArchive = Join-Path $downloadRoot 'python.zip'
    Invoke-WebRequest -Uri $manifest.python_url -OutFile $pythonArchive
    Expand-Archive -LiteralPath $pythonArchive -DestinationPath $pythonRoot -Force
    "python312.zip`n.`nLib/site-packages`nimport site`n" | Set-Content -Encoding ascii -LiteralPath (Join-Path $pythonRoot 'python312._pth')
}
if (-not (Test-Path -LiteralPath (Join-Path $llamaRoot 'llama-server.exe'))) {
    $llamaArchive = Join-Path $downloadRoot 'llama.zip'
    Invoke-WebRequest -Uri $manifest.llama_url -OutFile $llamaArchive
    Expand-Archive -LiteralPath $llamaArchive -DestinationPath $llamaRoot -Force
}
$pipScript = Join-Path $downloadRoot 'get-pip.py'
if (-not (Test-Path -LiteralPath $pipScript)) { Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $pipScript }
& $pythonExe $pipScript --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed.' }
& $pythonExe -m pip install -r (Join-Path $projectCode 'requirements-lock.txt') --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
$modelFile = Join-Path $submissionRoot ('Model_Prompts_Config\models\' + $manifest.model_file)
if (-not (Test-Path -LiteralPath $modelFile)) { throw 'Model weights are missing. Restore Model_Prompts_Config\models from the submission package.' }
if ((Get-FileHash -LiteralPath $modelFile -Algorithm SHA256).Hash.ToLower() -ne $manifest.model_sha256) { throw 'Model checksum did not match the recorded download.' }
Write-Host 'Setup complete. Start Code\START_PROJECT.bat.'
