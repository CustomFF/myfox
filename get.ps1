# MyFox for Windows, in PowerShell:
#   irm https://raw.githubusercontent.com/CustomFF/myfox/master/get.ps1 | iex
# With arguments:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/CustomFF/myfox/master/get.ps1))) -y
# Puts the Python MyFox runs on into %LOCALAPPDATA%\myfox\python (python.org's
# embeddable build, nothing installed system-wide), then fetches bootstrap.py
# and runs it; all the logic lives there.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    # Windows PowerShell 5.1 may still offer only TLS 1.0, which GitHub refuses.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor
        [Net.SecurityProtocolType]::Tls12

    $version = '3.14.10'
    $sha256 = @{
        'amd64' = '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
        'arm64' = 'bbe116bb1248820359cbf25127ac5c7794ea161869d83686cfbc9a45203ff836'
    }
    $bootstrap = if ($env:MYFOX_BOOTSTRAP_URL) { $env:MYFOX_BOOTSTRAP_URL }
                 else { 'https://raw.githubusercontent.com/CustomFF/myfox/master/bootstrap.py' }

    $arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    $arch = @{ 'AMD64' = 'amd64'; 'ARM64' = 'arm64' }[$arch]
    if (-not $arch) {
        Write-Error "MyFox needs 64-bit Windows (x64 or ARM64)."
        return
    }

    $root = Join-Path $env:LOCALAPPDATA 'myfox'
    $python = Join-Path $root 'python'
    $marker = Join-Path $python '.myfox-python'
    if (-not ((Test-Path $marker) -and (Test-Path (Join-Path $python 'python.exe')) -and
              ((Get-Content $marker -Raw).Trim() -eq "$version-$arch"))) {
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ("myfox-" + [Guid]::NewGuid())
        New-Item -ItemType Directory $tmp | Out-Null
        try {
            $zip = Join-Path $tmp 'python.zip'
            Invoke-WebRequest -UseBasicParsing -OutFile $zip `
                "https://www.python.org/ftp/python/$version/python-$version-embed-$arch.zip"
            if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne $sha256[$arch]) {
                Write-Error "The Python download is damaged (checksum mismatch)."
                return
            }
            Expand-Archive $zip (Join-Path $tmp 'python')
            # Without its ._pth the embeddable Python reads PYTHONPATH, as
            # MyFox's launcher needs.
            Remove-Item (Join-Path $tmp 'python\*._pth')
            Set-Content (Join-Path $tmp 'python\.myfox-python') "$version-$arch"
            New-Item -ItemType Directory -Force $root | Out-Null
            if (Test-Path $python) { Remove-Item -Recurse -Force $python }
            Move-Item (Join-Path $tmp 'python') $python
        } finally {
            Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
        }
    }

    # Windows fetches a root certificate the first time its own checks need
    # it, and Python sees only those already fetched: have it check GitHub's.
    try { Invoke-WebRequest -UseBasicParsing -Method Head 'https://github.com' | Out-Null } catch { }

    $script = Join-Path ([IO.Path]::GetTempPath()) ("myfox-bootstrap-" + [Guid]::NewGuid() + '.py')
    try {
        if ($bootstrap -match '^[a-z]+://') {
            Invoke-WebRequest -UseBasicParsing -OutFile $script $bootstrap
        } else {
            Copy-Item $bootstrap $script
        }
        & (Join-Path $python 'python.exe') $script @args
    } finally {
        Remove-Item $script -ErrorAction SilentlyContinue
    }
} @args
