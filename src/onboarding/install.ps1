$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

$ProjectRoot = (Get-Location).Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$ProductName = "SayClip"
$ProductTagline = "Local OBS voice clip rename setup"
$TotalSetupSteps = 6
$ModelCatalog = @(
    [ordered]@{
        Id = "tiny"
        Name = "Fastest"
        Repo = "Systran/faster-whisper-tiny"
        Url = "https://huggingface.co/Systran/faster-whisper-tiny"
        Path = Join-Path $ProjectRoot "models\faster-whisper-tiny"
        Description = "downloads Tiny on the next step; lowest CPU load, good enough for short titles"
    },
    [ordered]@{
        Id = "small"
        Name = "Balanced"
        Repo = "Systran/faster-whisper-small"
        Url = "https://huggingface.co/Systran/faster-whisper-small"
        Path = Join-Path $ProjectRoot "models\faster-whisper-small"
        Description = "downloads Small on the next step; better recognition, larger download, a bit more CPU work"
    }
)
$ConfigPath = Join-Path $ProjectRoot "config.toml"
$ConfigExamplePath = Join-Path $ProjectRoot "config.example.toml"
$InstallerMutexName = "Local\SayClipInstaller"
$script:InstallerMutex = $null

function Write-BrandBanner {
    Show-SetupHeader 0 "Welcome"
}

function Write-Title($Text) {
    Write-Host ""
    Write-Host "== $Text ==" -ForegroundColor Cyan
}

function Write-Step($Text) {
    Write-Host $Text -ForegroundColor Yellow
}

function Write-Option($Number, $Text) {
    Write-Host "[$Number] " -NoNewline -ForegroundColor Green
    Write-Host $Text
}

function Write-Muted($Text) {
    Write-Host $Text -ForegroundColor DarkGray
}

function New-ProgressBar($Step) {
    $width = 18
    if ($Step -le 0) {
        return ("-" * $width)
    }
    $filled = [int][Math]::Min($width, [Math]::Max(1, [Math]::Round(($Step / $TotalSetupSteps) * $width)))
    return ("#" * $filled) + ("-" * ($width - $filled))
}

function Show-SetupHeader($Step, $Title, $Status = "") {
    Clear-Host
    Write-Host $ProductName -ForegroundColor Cyan
    Write-Muted $ProductTagline
    Write-Host ""
    if ($Step -gt 0) {
        Write-Host "Step $Step of $TotalSetupSteps  [" -NoNewline -ForegroundColor DarkGray
        Write-Host (New-ProgressBar $Step) -NoNewline -ForegroundColor Green
        Write-Host "]  $Title" -ForegroundColor DarkGray
    } else {
        Write-Host $Title -ForegroundColor DarkGray
    }
    if ($Status) {
        Write-Host $Status -ForegroundColor Yellow
    }
    Write-Host ""
}

function Read-Choice($Prompt, [string[]] $Allowed) {
    while ($true) {
        $value = (Read-Host $Prompt).Trim()
        if ($Allowed -contains $value) {
            return $value
        }
        Write-Host "Please choose one of: $($Allowed -join ', ')" -ForegroundColor Yellow
    }
}

function Find-Python {
    $candidates = @()
    foreach ($command in @("py", "python")) {
        $path = Get-Command $command -ErrorAction SilentlyContinue
        if ($path) {
            $candidates += $path.Source
        }
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        try {
            $version = & $candidate --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $version -match "Python\s+(\d+)\.(\d+)") {
                $major = [int]$Matches[1]
                $minor = [int]$Matches[2]
                if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
                    $executable = (& $candidate -c "import sys; print(sys.executable)" 2>$null).ToString().Trim()
                    if (-not $executable) {
                        $executable = $candidate
                    }
                    return @{ Path = $executable; Version = $version.ToString().Trim() }
                }
            }
        } catch {
        }
    }
    return $null
}

function Read-Dependencies {
    $pyproject = Join-Path $ProjectRoot "pyproject.toml"
    $lines = Get-Content $pyproject
    $inside = $false
    $deps = @()
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "dependencies = [") {
            $inside = $true
            continue
        }
        if ($inside -and $trimmed -eq "]") {
            break
        }
        if ($inside -and $trimmed -match '^\s*"([^"]+)"') {
            $deps += $Matches[1]
        }
    }
    return $deps
}

function Test-DependenciesInstalled {
    if (-not (Test-Path $VenvPython)) {
        return $false
    }
    & $VenvPython -c "import PySide6, faster_whisper, sounddevice, soundfile" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Invoke-Checked($Description, [scriptblock] $Command) {
    Write-Host ""
    Write-Step $Description
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed."
    }
}

function Start-BackendUi {
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    $backendPython = Join-Path $VenvPath "Scripts\pythonw.exe"
    if (-not (Test-Path $backendPython -PathType Leaf)) {
        $backendPython = $VenvPython
    }
    Start-Process `
        -FilePath $backendPython `
        -ArgumentList @("-m", "instant_easy_rename_server", "--ui") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden
}

function Ensure-ConfigFile {
    if (Test-Path $ConfigPath -PathType Leaf) {
        return
    }
    if (-not (Test-Path $ConfigExamplePath -PathType Leaf)) {
        throw "config.toml is missing and config.example.toml was not found."
    }
    Copy-Item -Path $ConfigExamplePath -Destination $ConfigPath
    Write-Host ""
    Write-Host "Created config.toml from config.example.toml." -ForegroundColor Green
}

function Enter-InstallerMutex {
    $createdNew = $false
    $mutex = New-Object System.Threading.Mutex($true, $InstallerMutexName, [ref]$createdNew)
    if (-not $createdNew) {
        Write-Host ""
        Write-Host "Setup is already running in another window." -ForegroundColor Yellow
        Write-Host "Finish that setup window, or close it and run install.bat again."
        Write-Host ""
        Read-Host "Press Enter to close this window"
        exit 0
    }
    $script:InstallerMutex = $mutex
}

function Release-InstallerMutex {
    if ($script:InstallerMutex) {
        try {
            $script:InstallerMutex.ReleaseMutex()
            $script:InstallerMutex.Dispose()
        } catch {
        }
        $script:InstallerMutex = $null
    }
}

trap {
    Write-Host ""
    Write-Host "Setup failed."
    Write-Host ""
    Write-Host $_
    Write-Host ""
    Write-Host "Nothing else will be changed. You can fix the issue and run setup again."
    Release-InstallerMutex
    Read-Host "Press Enter to close this window"
    exit 1
}

function Get-AudioDevices {
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    $json = & $VenvPython -c "import json; from instant_easy_rename_server.audio_devices import list_user_audio_input_device_names; print(json.dumps(list_user_audio_input_device_names()))" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) {
        return @("default")
    }
    return @($json | ConvertFrom-Json)
}

function Select-Microphone {
    Show-SetupHeader 4 "Voice and file names" "Microphone"
    Write-Host "The backend can run headless, so let's choose the voice settings now."
    Write-Host "If voice capture does not work later, open Settings from the main UI/menu and change these values."
    Write-Host ""

    $devices = Get-AudioDevices
    if (-not $devices -or $devices.Count -eq 0) {
        $devices = @("default")
    }

    Write-Host "Available microphone inputs:"
    for ($index = 0; $index -lt $devices.Count; $index++) {
        Write-Host "[$($index + 1)] $($devices[$index])"
    }
    Write-Host "[$($devices.Count + 1)] Type another device name"

    while ($true) {
        $choice = Read-Host "Choose the microphone $ProductName should listen to"
        $number = 0
        if ([int]::TryParse($choice, [ref]$number)) {
            if ($number -ge 1 -and $number -le $devices.Count) {
                return [string]$devices[$number - 1]
            }
            if ($number -eq ($devices.Count + 1)) {
                $manual = (Read-Host "Type the microphone device name").Trim()
                if ($manual) {
                    return $manual
                }
            }
        }
        Write-Host "Please choose a listed number."
    }
}

function Select-Language {
    Show-SetupHeader 4 "Voice and file names" "Speech language"
    Write-Host "What language will the speaker use for voice titles?"
    Write-Host "[1] Russian (ru)"
    Write-Host "[2] English (en)"
    Write-Host "[3] Type another language code"
    $choice = Read-Choice "Choose language" @("1", "2", "3")
    if ($choice -eq "1") { return "ru" }
    if ($choice -eq "2") { return "en" }
    while ($true) {
        $language = (Read-Host "Type a Faster Whisper language code, for example ru, en, uk, de").Trim()
        if ($language -match "^[A-Za-z][A-Za-z0-9_-]{0,15}$") {
            return $language.ToLowerInvariant()
        }
        Write-Host "Please enter a short language code."
    }
}

function Select-ModelFromCatalog($Prompt) {
    Write-Host ""
    Write-Host $Prompt
    for ($index = 0; $index -lt $ModelCatalog.Count; $index++) {
        $model = $ModelCatalog[$index]
        Write-Option ($index + 1) "$($model.Name) - $($model.Description)"
        Write-Muted "    $($model.Repo)"
    }
    $allowed = @()
    for ($index = 1; $index -le $ModelCatalog.Count; $index++) {
        $allowed += [string]$index
    }
    $choice = Read-Choice "Choose model" $allowed
    return $ModelCatalog[[int]$choice - 1]
}

function Select-DownloadedModel($DownloadedModels) {
    Write-Host ""
    Write-Host "Downloaded models found:"
    for ($index = 0; $index -lt $DownloadedModels.Count; $index++) {
        $model = $DownloadedModels[$index]
        Write-Option ($index + 1) "$($model.Name) at $($model.Path)"
    }
    $allowed = @()
    for ($index = 1; $index -le $DownloadedModels.Count; $index++) {
        $allowed += [string]$index
    }
    $choice = Read-Choice "Use which downloaded model" $allowed
    return $DownloadedModels[[int]$choice - 1]
}

function Select-FilenameFormat {
    Show-SetupHeader 4 "Voice and file names" "Rename format"
    Write-Host "Choose what the renamed file should include."
    Write-Muted "Examples use source Forza Horizon 6, clip type moment, and spoken title clean overtake."
    Write-Host ""
    Write-Option 1 "Spoken title only"
    Write-Muted "    clean-overtake"
    Write-Option 2 "Time + spoken title"
    Write-Muted "    2026-05-27_22-10-44__clean-overtake"
    Write-Option 3 "Source + time + spoken title"
    Write-Muted "    forza-horizon-6__2026-05-27_22-10-44__clean-overtake"
    Write-Option 4 "Source + clip type + time + spoken title"
    Write-Muted "    forza-horizon-6__mom__2026-05-27_22-10-44__clean-overtake"
    Write-Option 5 "Custom format"
    $choice = Read-Choice "Choose format" @("1", "2", "3", "4", "5")
    if ($choice -eq "1") { return "{title}" }
    if ($choice -eq "2") { return "{datetime}__{title}" }
    if ($choice -eq "3") { return "{source}__{datetime}__{title}" }
    if ($choice -eq "4") { return "{source}__{job_type}__{datetime}__{title}" }
    Write-Muted "Available tokens: {source}, {job_type}, {datetime}, {title}. Legacy {game} still works as an alias."
    while ($true) {
        $format = (Read-Host "Enter format").Trim()
        if ($format -match "\{title\}") {
            return $format
        }
        Write-Host "Please include at least {title}, otherwise voice naming has nowhere to go." -ForegroundColor Yellow
    }
}

function Test-FasterWhisperModelFolder($Path) {
    if (-not (Test-Path $Path -PathType Container)) {
        return $false
    }
    $required = @("config.json", "model.bin")
    foreach ($name in $required) {
        if (-not (Test-Path (Join-Path $Path $name) -PathType Leaf)) {
            return $false
        }
    }
    $tokenizer = (Test-Path (Join-Path $Path "tokenizer.json") -PathType Leaf) -or (Test-Path (Join-Path $Path "vocabulary.txt") -PathType Leaf)
    return $tokenizer
}

function Update-AppConfig($ModelPath, $AudioDevice, $Language, $FilenameFormat, $PythonPath, $DependenciesInstalled, $SetupCompleted) {
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    $env:IER_PROJECT_ROOT = $ProjectRoot
    $env:IER_MODEL_PATH = $ModelPath
    $env:IER_AUDIO_DEVICE = $AudioDevice
    $env:IER_LANGUAGE = $Language
    $env:IER_FILENAME_FORMAT = $FilenameFormat
    $env:IER_SETUP_PYTHON_PATH = $PythonPath
    $env:IER_SETUP_VENV_PATH = $VenvPath
    $env:IER_SETUP_DEPENDENCIES_INSTALLED = if ($DependenciesInstalled) { "true" } else { "false" }
    $env:IER_SETUP_COMPLETED = if ($SetupCompleted) { "true" } else { "false" }
    $env:IER_SETUP_COMPLETED_AT = if ($SetupCompleted) { (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") } else { "" }
    $runner = $PythonPath
    if (Test-Path $VenvPython -PathType Leaf) {
        $runner = $VenvPython
    }
    & $runner -m instant_easy_rename_server.onboarding_config
    if ($LASTEXITCODE -ne 0) {
        throw "Could not update config.toml."
    }
}

Enter-InstallerMutex
Write-BrandBanner
Write-Host "Don't worry: this installer uses the console only to show clear steps." -ForegroundColor White
Write-Host "Nothing will be changed without your confirmation."
Write-Host ""
Write-Step "This setup will:"
Write-Option 1 "Check Python"
Write-Option 2 "Create a local environment inside this project folder"
Write-Option 3 "Install required dependencies locally"
Write-Option 4 "Configure voice input, speech language, and rename format"
Write-Option 5 "Choose and configure the Faster Whisper model"
Write-Option 6 "Start the backend"

Ensure-ConfigFile

Show-SetupHeader 1 "Python check"
$python = Find-Python
if (-not $python) {
    Write-Host "Python was not found."
    Write-Host ""
    Write-Host "Please install Python 3.11+ from:"
    Write-Host "https://www.python.org/downloads/windows/"
    Write-Host ""
    Write-Host "Then run install.bat again."
    exit 1
}

Write-Host "Python found:"
Write-Host $python.Path
Write-Host "Version: $($python.Version)"
Write-Host ""
Write-Host "Use this Python?"
Write-Option 1 "Yes"
Write-Option 2 "Choose another Python path"
Write-Option 3 "Cancel setup"
$choice = Read-Choice "Choose" @("1", "2", "3")
if ($choice -eq "3") { exit 1 }
if ($choice -eq "2") {
    $manualPython = (Read-Host "Paste the full path to python.exe").Trim('" ')
    if (-not (Test-Path $manualPython -PathType Leaf)) {
        throw "Python path does not exist: $manualPython"
    }
    $python = @{
        Path = (& $manualPython -c "import sys; print(sys.executable)" 2>$null).ToString().Trim()
        Version = (& $manualPython --version 2>&1).ToString().Trim()
    }
}

Update-AppConfig "" "default" "ru" "{source}__{datetime}__{title}" $python.Path $false $false

Show-SetupHeader 2 "Local environment"
Write-Host "Setup will create a local environment here:"
Write-Host $VenvPath
Write-Host ""
Write-Host "Your system Python will not be modified."
Write-Host "Dependencies will be installed only inside this project folder."
Write-Host ""
$dependencies = Read-Dependencies
Write-Host "Dependencies from pyproject.toml:"
foreach ($dependency in $dependencies) {
    Write-Host "- $dependency"
}

$dependenciesInstalled = Test-DependenciesInstalled
$installDependenciesRequested = $false
if ((Test-Path $VenvPath) -and $dependenciesInstalled) {
    Write-Host ""
    Write-Host "Local environment already exists."
    Write-Host "Dependencies look installed."
    Write-Host "Continuing to voice setup."
} else {
    Write-Host ""
    Write-Host "Install these dependencies locally?"
    Write-Option 1 "Yes, install"
    Write-Option 2 "No, I will install them myself"
    Write-Option 3 "Cancel setup"
    $depChoice = Read-Choice "Choose" @("1", "2", "3")
    if ($depChoice -eq "3") { exit 1 }
    if ($depChoice -eq "2") {
        $dependenciesInstalled = Test-DependenciesInstalled
    } else {
        $dependenciesInstalled = $false
        $installDependenciesRequested = $true
    }
}

if (-not (Test-Path $VenvPython)) {
    Invoke-Checked "Creating local virtual environment" { & $python.Path -m venv $VenvPath }
}

if ((-not $dependenciesInstalled) -and (-not $installDependenciesRequested)) {
    Write-Host ""
    Write-Host "Dependencies are not installed yet."
    Write-Host "Install them into this local environment, then run install.bat again:"
    Write-Host $VenvPath
    exit 1
}

if (-not $dependenciesInstalled) {
    Show-SetupHeader 3 "Dependencies" "Installing local packages"
    Invoke-Checked "Upgrading local pip" { & $VenvPython -m pip install --upgrade pip }
    Invoke-Checked "Installing local dependencies" { & $VenvPython -m pip install -e ".[dev]" }
    $dependenciesInstalled = Test-DependenciesInstalled
}

$audioDevice = Select-Microphone
Update-AppConfig "" $audioDevice "ru" "{source}__{datetime}__{title}" $python.Path $dependenciesInstalled $false
$language = Select-Language
$filenameFormat = Select-FilenameFormat
Update-AppConfig "" $audioDevice $language $filenameFormat $python.Path $dependenciesInstalled $false

Show-SetupHeader 5 "Speech model"
Write-Host "Faster Whisper needs a speech recognition model."
Write-Host ""
$downloadedModels = @($ModelCatalog | Where-Object { Test-FasterWhisperModelFolder $_.Path })
if ($downloadedModels.Count -gt 0) {
    Write-Host "A Faster Whisper model already exists in this project."
    Write-Host ""
    Write-Option 1 "Use a downloaded model"
    Write-Option 2 "Proceed to download"
    Write-Option 3 "Use a different model folder"
    Write-Option 4 "Skip for now"
    Write-Option 5 "Cancel setup"
    $modelChoice = Read-Choice "Choose" @("1", "2", "3", "4", "5")
    if ($modelChoice -eq "1") {
        $selectedModel = Select-DownloadedModel $downloadedModels
        $modelPath = $selectedModel.Path
    } elseif ($modelChoice -eq "2") {
        $modelChoice = "download"
    } elseif ($modelChoice -eq "3") {
        $modelChoice = "manual"
    } elseif ($modelChoice -eq "4") {
        $modelChoice = "skip"
    } else {
        exit 1
    }
} else {
    Write-Host "You have these options:"
    Write-Option 1 "Proceed to download"
    Write-Option 2 "Use a model folder I already have"
    Write-Option 3 "Skip for now"
    Write-Option 4 "Cancel setup"
    $modelChoice = Read-Choice "Choose" @("1", "2", "3", "4")
    if ($modelChoice -eq "1") {
        $modelChoice = "download"
    } elseif ($modelChoice -eq "2") {
        $modelChoice = "manual"
    } elseif ($modelChoice -eq "3") {
        $modelChoice = "skip"
    } else {
        exit 1
    }
}

if (-not (Get-Variable -Name modelPath -ErrorAction SilentlyContinue)) {
    $modelPath = ""
}
if ($modelChoice -eq "download") {
    $selectedModel = Select-ModelFromCatalog "Which speed/quality profile should be downloaded?"
    Write-Host ""
    Write-Host "The model will be downloaded from:"
    Write-Host $selectedModel.Url -ForegroundColor Cyan
    Write-Host ""
    Write-Host "It will be saved to:"
    Write-Host $selectedModel.Path
    Write-Host ""
    Write-Host "This is an external source. Please review the link before continuing."
    Write-Host "$ProductName does not control third-party files or hosting."
    Write-Host ""
    Write-Host "Download this model now?"
    Write-Option 1 "Yes"
    Write-Option 2 "No"
    $downloadChoice = Read-Choice "Choose" @("1", "2")
    if ($downloadChoice -eq "1") {
        New-Item -ItemType Directory -Force -Path $selectedModel.Path | Out-Null
        $downloadScript = "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$($selectedModel.Repo)', local_dir=r'$($selectedModel.Path)', local_dir_use_symlinks=False)"
        Invoke-Checked "Downloading Faster Whisper model" { & $VenvPython -c $downloadScript }
        if (-not (Test-FasterWhisperModelFolder $selectedModel.Path)) {
            throw "Downloaded folder does not look like a Faster Whisper model folder."
        }
        $modelPath = $selectedModel.Path
    }
} elseif ($modelChoice -eq "manual") {
    while ($true) {
        $manualModel = (Read-Host "Paste the full path to your Faster Whisper model folder").Trim('" ')
        if (Test-FasterWhisperModelFolder $manualModel) {
            $modelPath = $manualModel
            break
        }
        Write-Host "That folder does not look like a Faster Whisper model folder."
        Write-Host "Expected at least config.json, model.bin, and tokenizer.json or vocabulary.txt."
    }
}

if (-not $modelPath) {
    Write-Host "Model setup skipped. Backend will start, but voice jobs will be blocked until the model is configured in Settings." -ForegroundColor Yellow
}

Update-AppConfig $modelPath $audioDevice $language $filenameFormat $python.Path $dependenciesInstalled $true

Show-SetupHeader 6 "Finish"
Write-Host "Setup completed." -ForegroundColor Green
Write-Host ""
Write-Host "Backend can now start automatically."
Write-Host "You can open the backend UI from OBS Scripts if needed."
Write-Host ""
Write-Host "Setup settings written to:"
Write-Host $ConfigPath
Write-Host ""
Write-Host "OBS dock panel:"
Write-Host "In OBS, open Docks -> Custom Browser Docks."
Write-Host "Name: $ProductName"
Write-Host "URL:  http://127.0.0.1:17891/dock"
Write-Host ""
Write-Host "Starting backend..."

Start-BackendUi
Release-InstallerMutex
exit 0
