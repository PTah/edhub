# Edited by nc.ai 1.2.12 on Papasha 2026-11-14 21:37:17
#Requires -Version 5
<#
  Уборка утёкших MCP-серверов (node.exe / cmd.exe / conhost.exe от npx).

  Каждая сессия редактора запускает MCP-серверы через npx:
      node(npx-cli) -> cmd.exe /d /s /c <сервер> -> node(<сервер>) (+ conhost)
  Старые цепочки не завершаются и копятся сутками — десятки гигабайт RAM.

  Убиваются только цепочки MCP-серверов; самые свежие (те, что держит текущая
  сессия редактора) остаются. Остальные процессы машины не затрагиваются.

  Использование:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\kill_mcp_leaks.ps1           # dry-run
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\kill_mcp_leaks.ps1 -Apply
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\kill_mcp_leaks.ps1 -Apply -Keep 5
#>
param(
    [switch]$Apply,
    [int]$Keep = 3,          # сколько самых свежих цепочек на каждый сервер оставить
    [switch]$IncludeConhost  # прихватить осиротевшие conhost.exe
)

$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$patterns = @(
    '@shell-mcp/mcp-lite',
    '@mapbox/mcp-server',
    'server-filesystem',
    'server-memory',
    'npx-cli.js',
    '_npx\'
)

function Get-ServerKey([string]$cmd) {
    if ($cmd -match '@shell-mcp/mcp-lite' -or $cmd -match '/c shell-mcp-lite') { return 'shell-mcp-lite' }
    if ($cmd -match '@mapbox/mcp-server'  -or $cmd -match '/c mcp-server')    { return 'mapbox' }
    if ($cmd -match 'server-filesystem')  { return 'filesystem' }
    if ($cmd -match 'server-memory')      { return 'memory' }
    return 'npx-other'
}

$all = Get-CimInstance Win32_Process
$byId = @{}
$children = @{}
foreach ($p in $all) {
    $byId[[int]$p.ProcessId] = $p
    $pp = [int]$p.ParentProcessId
    if (-not $children.ContainsKey($pp)) { $children[$pp] = @() }
    $children[$pp] += [int]$p.ProcessId
}

# прямые матчи по командной строке
$matched = @()
foreach ($p in $all) {
    if ($p.Name -notin @('node.exe', 'cmd.exe')) { continue }
    $cl = [string]$p.CommandLine
    if (-not $cl) { continue }
    foreach ($pat in $patterns) {
        if ($cl.Contains($pat)) { $matched += $p; break }
    }
}

# вниз по дереву: всё потомство цепочки (только node/cmd[/conhost])
function Get-Tree([int]$rootId) {
    $out = New-Object System.Collections.Generic.List[int]
    $stack = New-Object System.Collections.Stack
    $stack.Push($rootId)
    while ($stack.Count -gt 0) {
        $id = [int]$stack.Pop()
        if ($out.Contains($id)) { continue }
        $proc = $byId[$id]
        if (-not $proc) { continue }
        if ($proc.Name -in @('node.exe', 'cmd.exe') -or ($IncludeConhost -and $proc.Name -eq 'conhost.exe')) {
            $out.Add($id)
        }
        if ($children.ContainsKey($id)) { foreach ($c in $children[$id]) { $stack.Push([int]$c) } }
    }
    return $out
}

# группируем совпавшие процессы по серверу, оставляем $Keep самых свежих
$byKey = @{}
foreach ($p in $matched) {
    $k = Get-ServerKey ([string]$p.CommandLine)
    if (-not $byKey.ContainsKey($k)) { $byKey[$k] = @() }
    $byKey[$k] += $p
}

$keepIds = New-Object System.Collections.Generic.HashSet[int]
$killIds = New-Object System.Collections.Generic.HashSet[int]

"SERVER            CHAINS   KEEP_CH  KILL_PROC   KILL_MB"
foreach ($k in ($byKey.Keys | Sort-Object)) {
    $roots = @($byKey[$k] | Sort-Object CreationDate -Descending)
    # корни цепочек: только те, чей родитель сам не совпал (иначе это звено цепочки)
    $rootIds = @($roots | Where-Object {
        $par = $byId[[int]$_.ParentProcessId]
        -not ($par -and ($matched | Where-Object { [int]$_.ProcessId -eq [int]$par.ProcessId }))
    })
    $rootIds = @($rootIds | Sort-Object { $_.CreationDate } -Descending)
    $keepRoots = @($rootIds | Select-Object -First $Keep)
    $dropRoots = @($rootIds | Select-Object -Skip $Keep)

    $kMB = 0
    $kCount = 0
    foreach ($r in $keepRoots) {
        foreach ($id in (Get-Tree ([int]$r.ProcessId))) { [void]$keepIds.Add($id) }
    }
    foreach ($r in $dropRoots) {
        foreach ($id in (Get-Tree ([int]$r.ProcessId))) {
            if ($keepIds.Contains($id)) { continue }
            if ($killIds.Add($id)) {
                $kCount++
                $kMB += [int]($byId[$id].WorkingSetSize / 1MB)
            }
        }
    }
    "{0,-17} {1,6}   {2,6}   {3,9}   {4,8}" -f $k, $roots.Count, $keepRoots.Count, $kCount, $kMB
}

# не трогаем себя и своих предков
$self = [int]$PID
$anc = New-Object System.Collections.Generic.HashSet[int]
$cur = $self
while ($byId.ContainsKey($cur)) { [void]$anc.Add($cur); $cur = [int]$byId[$cur].ParentProcessId }

$final = @($killIds | Where-Object { -not $anc.Contains($_) -and -not $keepIds.Contains($_) })

$totalMB = 0
foreach ($id in $final) { $totalMB += [int]($byId[$id].WorkingSetSize / 1MB) }
""
"TOTAL to kill: {0} processes, ~{1} MB RSS" -f $final.Count, $totalMB

if (-not $Apply) {
    ""
    "dry-run: nothing killed. Re-run with -Apply."
    exit 0
}

$done = 0
foreach ($id in $final) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    if (-not (Get-Process -Id $id -ErrorAction SilentlyContinue)) { $done++ }
}
"killed: {0} of {1}" -f $done, $final.Count

Start-Sleep -Seconds 3
$after = Get-CimInstance Win32_Process
$n = @($after | Where-Object { $_.Name -eq 'node.exe' })
$c = @($after | Where-Object { $_.Name -eq 'cmd.exe' })
$h = @($after | Where-Object { $_.Name -eq 'conhost.exe' })
"after: node={0} ({1} MB), cmd={2}, conhost={3}, total procs={4}" -f `
    $n.Count, [int]((($n | Measure-Object -Property WorkingSetSize -Sum).Sum) / 1MB), $c.Count, $h.Count, @($after).Count
$os = Get-CimInstance Win32_OperatingSystem
"free RAM: {0} MB of {1} MB" -f [int]($os.FreePhysicalMemory / 1KB), [int]($os.TotalVisibleMemorySize / 1KB)
