# Instantane FACTUEL de l'etat de travail — ecrit par le hook PostCompact, relu par SessionStart.
#
# POURQUOI. Le resume de compactage est une RECONSTITUTION : il perd systematiquement les memes
# choses (sha courant, agents en vol, gestes en attente) et peut affirmer des faits perimes.
# Ce fichier ne contient que du MESURE au moment du compactage — donc invérifiable-faux.
#
# Ne fait aucune hypothese : chaque bloc est independant et degrade proprement si sa source est
# absente (host eteint, gh non installe, pas de session). ASCII only (console cp1252).

$ErrorActionPreference = 'SilentlyContinue'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $repo

$out = New-Object System.Collections.Generic.List[string]
$out.Add("# Etat au dernier compactage")
$out.Add("")
$out.Add("Genere par le hook PostCompact. FAITS MESURES, pas un resume.")
$out.Add("")

# --- git -------------------------------------------------------------------
$out.Add("## Git")
$head = git log --oneline -1 2>$null
$branch = git rev-parse --abbrev-ref HEAD 2>$null
$dirty = @(git status --porcelain 2>$null)
$ahead = git rev-list --count origin/$branch..HEAD 2>$null
$out.Add("- branche  : $branch")
$out.Add("- HEAD     : $head")
if ($ahead -and $ahead -ne '0') { $out.Add("- NON POUSSE : $ahead commit(s) d'avance sur origin/$branch") }
if ($dirty.Count -gt 0) {
    $out.Add("- ARBRE SALE : $($dirty.Count) fichier(s)")
    $dirty | Select-Object -First 12 | ForEach-Object { $out.Add("    $_") }
    if ($dirty.Count -gt 12) { $out.Add("    ... et $($dirty.Count - 12) autres") }
} else {
    $out.Add("- arbre propre")
}
$out.Add("")

# --- PR ouvertes -----------------------------------------------------------
$prs = gh pr list --state open --json number,title,headRefName 2>$null | ConvertFrom-Json
if ($prs) {
    $out.Add("## PR ouvertes (a relire / merger)")
    foreach ($p in $prs) { $out.Add("- #$($p.number) $($p.title)") }
    $out.Add("")
}

# --- session Frida ---------------------------------------------------------
$out.Add("## Session Frida")
$st = try { Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/admin/status' -TimeoutSec 3 } catch { $null }
if (-not $st) {
    $out.Add("- host INJOIGNABLE sur 127.0.0.1:8765 (non demarre, ou jeu ferme)")
} elseif (-not $st.session) {
    $out.Add("- aucune session (`.session` est null) -> inject + warmup requis avant tout RPC")
} else {
    $s = $st.session
    $out.Add("- session $($s.id) pid $($s.pid) statut $($s.status) depuis $($s.startedAt)")
    # DERIVE, pas suppose : hooks rebuildes APRES le demarrage de la session => reinject du.
    $js = Get-Item "$repo\frida\dist\hooks.js" -ErrorAction SilentlyContinue
    if ($js -and $s.startedAt) {
        $started = [datetime]::Parse($s.startedAt).ToUniversalTime()
        if ($js.LastWriteTimeUtc -gt $started) {
            $out.Add("- ATTENTION : dist/hooks.js est plus recent que la session")
            $out.Add("  (build $($js.LastWriteTimeUtc.ToString('HH:mm:ss')) UTC > session $($started.ToString('HH:mm:ss')) UTC)")
            $out.Add("  => la session tourne avec des hooks PERIMES : un reinject est DU.")
            $out.Add("  => mais NE PAS reinjecter tant qu'un agent tourne (ca casse son harnais).")
        }
    }
}
$out.Add("")

# --- coherence build <-> symboles -----------------------------------------
# Le dossier du build est celui qui contient l'exe — pas le premier venu : il traine des
# repertoires de travail (`.temp`, …) qui feraient crier au faux positif.
$installed = (Get-ChildItem 'C:\Users\nicolasv\AppData\Local\tacticus\games' -Directory -EA SilentlyContinue |
              Where-Object { Test-Path (Join-Path $_.FullName 'Tacticus.exe') } |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
$tables = (Get-ChildItem "$repo\data\symbols" -Directory -EA SilentlyContinue).Name
if ($installed -and $tables) {
    if ($tables -notcontains $installed) {
        $out.Add("## ALERTE build")
        $out.Add("- jeu installe : $installed")
        $out.Add("- tables       : $($tables -join ', ')")
        $out.Add("- DESYNCHRONISE -> suivre la procedure de MAJ (skill tacticus-orchestration).")
        $out.Add("")
    }
}

# --- notes non derivables -------------------------------------------------
# Le script ne sait mesurer que des FAITS. Ce qui est en cours (decisions ouvertes, agents en
# vol, intention de la tranche) n'est nulle part sur le disque : on le tient a la main dans
# `.claude/compact-notes.md`, incorpore ici pour qu'il SURVIVE a chaque regeneration.
$notes = Join-Path $repo '.claude\compact-notes.md'
if (Test-Path $notes) {
    $body = (Get-Content $notes -Raw).Trim()
    if ($body) {
        $out.Add("## En cours (tenu a la main, non derivable)")
        $out.Add("")
        $out.Add($body)
        $out.Add("")
    }
}

$dest = Join-Path $repo '.claude\last-compact-state.md'
$out -join "`n" | Set-Content $dest -Encoding UTF8
