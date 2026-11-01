# Renders social-preview.svg to social-preview.png (1280x640) with headless Chrome/Edge.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$svg = Join-Path $here 'social-preview.svg'
$png = Join-Path $here 'social-preview.png'
$exe = @('C:\Program Files\Google\Chrome\Application\chrome.exe','C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') | Where-Object { Test-Path $_ } | Select-Object -First 1
& $exe --headless --disable-gpu --hide-scrollbars --window-size=1280,640 "--screenshot=$png" ([uri]$svg).AbsoluteUri
