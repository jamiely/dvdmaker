<#
.SYNOPSIS
Converts one or more video files to DVD-compatible MPEG-2 program streams.

.DESCRIPTION
Creates a constant-frame-rate DVD MPEG-2 video with 48 kHz AC-3 audio. Video
and audio timestamps are normalized during conversion to prevent progressive
audio/video drift. By default, output is written to a "converted" directory
beside each input file.

.EXAMPLE
.\Convert-ToDvdMpeg2.ps1 -Path 'C:\Videos\movie.mp4'

.EXAMPLE
.\Convert-ToDvdMpeg2.ps1 -Path 'C:\Videos\one.mp4', 'C:\Videos\two.mkv' -Overwrite

.EXAMPLE
.\Convert-ToDvdMpeg2.ps1 -Path 'C:\Videos\movie.mp4' -Standard PAL -AspectRatio '4:3'
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [Alias('FullName')]
    [ValidateNotNullOrEmpty()]
    [string[]] $Path,

    # If omitted, each file goes into a "converted" folder beside the input.
    [string] $OutputDirectory,

    [ValidateSet('NTSC', 'PAL')]
    [string] $Standard = 'NTSC',

    [ValidateSet('Auto', '16:9', '4:3')]
    [string] $AspectRatio = 'Auto',

    # 0 calculates a bitrate from TargetSizeMB and the source duration.
    [ValidateRange(0, 9000)]
    [int] $VideoBitrateKbps = 0,

    # Leaves useful headroom on a 4.7 GB single-layer DVD for authoring overhead.
    [ValidateRange(500, 4480)]
    [int] $TargetSizeMB = 4300,

    [switch] $Overwrite,

    # Optional directory containing ffmpeg.exe and ffprobe.exe.
    [string] $FfmpegDirectory
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

    function Find-FFmpegProgram {
        param(
            [Parameter(Mandatory = $true)] [string] $ProgramName,
            [string] $PreferredDirectory
        )

        $executableName = "$ProgramName.exe"
        $candidates = [System.Collections.Generic.List[string]]::new()

        if ($PreferredDirectory) {
            $candidates.Add((Join-Path $PreferredDirectory $executableName))
        }

        $command = Get-Command $ProgramName -CommandType Application -ErrorAction SilentlyContinue
        if ($command) {
            $candidates.Add($command.Source)
        }

        $candidates.Add((Join-Path $env:ProgramData "chocolatey\bin\$executableName"))
        $candidates.Add((Join-Path $env:ProgramData "chocolatey\lib\ffmpeg\tools\ffmpeg\bin\$executableName"))
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\$executableName"))
        $candidates.Add((Join-Path $env:USERPROFILE "scoop\apps\ffmpeg\current\bin\$executableName"))
        $candidates.Add("C:\ffmpeg\bin\$executableName")
        $candidates.Add("C:\Program Files\ffmpeg\bin\$executableName")
        $candidates.Add("C:\Program Files\DownloadHelper CoApp\$executableName")

        foreach ($candidate in $candidates) {
            if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                return (Get-Item -LiteralPath $candidate).FullName
            }
        }

        throw "$executableName was not found. Install FFmpeg or supply -FfmpegDirectory."
    }

    function Convert-RatioToDouble {
        param([string] $Ratio)

        if (-not $Ratio -or $Ratio -eq 'N/A' -or $Ratio -eq '0:1') {
            return 0.0
        }

        $parts = $Ratio -split '[:/]'
        if ($parts.Count -eq 2) {
            $numerator = [double]::Parse($parts[0], [Globalization.CultureInfo]::InvariantCulture)
            $denominator = [double]::Parse($parts[1], [Globalization.CultureInfo]::InvariantCulture)
            if ($denominator -ne 0) {
                return $numerator / $denominator
            }
        }

        return 0.0
    }

$ffmpegPath = Find-FFmpegProgram -ProgramName 'ffmpeg' -PreferredDirectory $FfmpegDirectory
$ffprobePath = Find-FFmpegProgram -ProgramName 'ffprobe' -PreferredDirectory $FfmpegDirectory
$invariantCulture = [Globalization.CultureInfo]::InvariantCulture

foreach ($inputPath in $Path) {
        $resolvedInput = (Resolve-Path -LiteralPath $inputPath).Path
        $inputItem = Get-Item -LiteralPath $resolvedInput
        if ($inputItem.PSIsContainer) {
            throw "Input must be a file: $resolvedInput"
        }

        $probeText = & $ffprobePath -v error `
            -show_entries 'format=duration:stream=index,codec_type,width,height,display_aspect_ratio' `
            -of json -- $resolvedInput
        if ($LASTEXITCODE -ne 0) {
            throw "ffprobe could not inspect: $resolvedInput"
        }

        $probe = $probeText | ConvertFrom-Json
        $videoStream = $probe.streams | Where-Object { $_.codec_type -eq 'video' } | Select-Object -First 1
        $audioStream = $probe.streams | Where-Object { $_.codec_type -eq 'audio' } | Select-Object -First 1
        if (-not $videoStream) { throw "No video stream was found in: $resolvedInput" }
        if (-not $audioStream) { throw "No audio stream was found in: $resolvedInput" }

        $durationSeconds = [double]::Parse([string] $probe.format.duration, $invariantCulture)
        if ($durationSeconds -le 0) { throw "The duration could not be determined for: $resolvedInput" }

        $selectedAspectRatio = $AspectRatio
        if ($selectedAspectRatio -eq 'Auto') {
            $displayAspectRatio = 0.0
            $displayAspectProperty = $videoStream.PSObject.Properties['display_aspect_ratio']
            if ($displayAspectProperty) {
                $displayAspectRatio = Convert-RatioToDouble ([string] $displayAspectProperty.Value)
            }
            if ($displayAspectRatio -le 0 -and $videoStream.height -gt 0) {
                $displayAspectRatio = [double] $videoStream.width / [double] $videoStream.height
            }
            if ($displayAspectRatio -ge 1.55) {
                $selectedAspectRatio = '16:9'
            }
            else {
                $selectedAspectRatio = '4:3'
            }
        }

        if ($Standard -eq 'NTSC') {
            $target = 'ntsc-dvd'
            $outputWidth = 720
            $outputHeight = 480
            $frameRate = '30000/1001'
            $gopSize = 18
            if ($selectedAspectRatio -eq '16:9') {
                $canvasWidth = 960
                $canvasHeight = 540
                $sampleAspectRatio = '32/27'
            }
            else {
                $canvasWidth = 720
                $canvasHeight = 540
                $sampleAspectRatio = '8/9'
            }
        }
        else {
            $target = 'pal-dvd'
            $outputWidth = 720
            $outputHeight = 576
            $frameRate = '25'
            $gopSize = 15
            if ($selectedAspectRatio -eq '16:9') {
                $canvasWidth = 1024
                $canvasHeight = 576
                $sampleAspectRatio = '64/45'
            }
            else {
                $canvasWidth = 768
                $canvasHeight = 576
                $sampleAspectRatio = '16/15'
            }
        }

        $audioBitrateKbps = 192
        if ($VideoBitrateKbps -gt 0) {
            $selectedVideoBitrateKbps = $VideoBitrateKbps
        }
        else {
            # Reserve three percent for MPEG program-stream overhead.
            $totalKbps = (($TargetSizeMB * 1000000.0 * 8.0) / $durationSeconds / 1000.0) * 0.97
            $selectedVideoBitrateKbps = [math]::Floor($totalKbps - $audioBitrateKbps)
            $selectedVideoBitrateKbps = [math]::Min(8000, $selectedVideoBitrateKbps)
            if ($selectedVideoBitrateKbps -lt 1800) {
                throw "The calculated video bitrate is only $selectedVideoBitrateKbps kb/s. Use a larger -TargetSizeMB, split the video, or set -VideoBitrateKbps explicitly."
            }
        }

        if ($OutputDirectory) {
            if ([IO.Path]::IsPathRooted($OutputDirectory)) {
                $destinationDirectory = [IO.Path]::GetFullPath($OutputDirectory)
            }
            else {
                $destinationDirectory = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
            }
        }
        else {
            $destinationDirectory = Join-Path $inputItem.DirectoryName 'converted'
        }
        $null = New-Item -ItemType Directory -Path $destinationDirectory -Force

        $outputPath = Join-Path $destinationDirectory ($inputItem.BaseName + '.mpg')
        if ((Test-Path -LiteralPath $outputPath) -and -not $Overwrite) {
            throw "Output already exists: $outputPath (use -Overwrite to replace it)"
        }

        $temporaryOutputPath = Join-Path $destinationDirectory ('.{0}.{1}.partial.mpg' -f $inputItem.BaseName, $PID)
        if (Test-Path -LiteralPath $temporaryOutputPath) {
            Remove-Item -LiteralPath $temporaryOutputPath -Force
        }

        $videoFilter = 'settb=AVTB,scale={0}:{1}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1,pad={0}:{1}:(ow-iw)/2:(oh-ih)/2:color=black,scale={2}:{3}:flags=lanczos,setsar={4},fps={5}:start_time=0:round=near' -f `
            $canvasWidth, $canvasHeight, $outputWidth, $outputHeight, $sampleAspectRatio, $frameRate
        $audioFilter = 'aresample=48000:async=1000:first_pts=0'

        $ffmpegArguments = @(
            '-hide_banner',
            '-stats_period', '10',
            '-fflags', '+genpts+discardcorrupt',
            '-i', $resolvedInput,
            '-map', '0:v:0',
            '-map', '0:a:0',
            '-sn',
            '-dn',
            '-vf', $videoFilter,
            '-af', $audioFilter,
            '-target', $target,
            '-aspect', $selectedAspectRatio,
            '-b:v', "${selectedVideoBitrateKbps}k",
            '-maxrate:v', '9000k',
            '-minrate:v', '0',
            '-bufsize:v', '1835008',
            '-g', [string] $gopSize,
            '-b:a', "${audioBitrateKbps}k",
            '-ac', '2',
            '-max_muxing_queue_size', '4096',
            '-avoid_negative_ts', 'make_zero',
            '-shortest',
            '-y',
            $temporaryOutputPath
        )

        Write-Host "Input:   $resolvedInput"
        Write-Host "Output:  $outputPath"
        Write-Host "Format:  $Standard DVD, $selectedAspectRatio, $selectedVideoBitrateKbps kb/s video, $audioBitrateKbps kb/s AC-3"

        try {
            & $ffmpegPath @ffmpegArguments
            if ($LASTEXITCODE -ne 0) {
                throw "ffmpeg exited with code $LASTEXITCODE"
            }

            if ((Test-Path -LiteralPath $outputPath) -and $Overwrite) {
                Remove-Item -LiteralPath $outputPath -Force
            }
            Move-Item -LiteralPath $temporaryOutputPath -Destination $outputPath
            Get-Item -LiteralPath $outputPath
        }
        finally {
            if (Test-Path -LiteralPath $temporaryOutputPath) {
                Remove-Item -LiteralPath $temporaryOutputPath -Force
            }
        }
}
