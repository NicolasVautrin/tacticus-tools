# Hook Stop -- l'ETAT DE LA BOUCLE, a chaque fin de tour, sans avoir a y penser (#465).
#
# POURQUOI UN HOOK, et pas une checklist : une checklist qu'il faut PENSER a lancer est
# elle-meme oubliable. Mesure du 2026-08-04 -- un tour termine a 1 agent sur un plafond de 5
# apres que quatre solveurs avaient rendu, 30 commits d'avance non pousses, 4 worktrees livres
# non nettoyes. Rien ne l'a signale ; l'utilisateur a du demander << t'oublies rien ? >>.
#
# POURQUOI CE WRAPPER PLUTOT QUE `python <script> --hook` EN DIRECT. Un hook `Stop` qui rend
# **exactement 2** est traite par Claude Code comme un BLOCAGE, stderr renvoye au modele. Or
# `python: can't open file` rend precisement 2. Le jour ou le depot est deplace ou le script
# renomme, la commande nue ne se contenterait pas d'etre inerte : elle bloquerait chaque fin de
# tour avec une trace Python. Ce script garantit `exit 0` quoi qu'il arrive -- un garde-fou ne
# doit jamais devenir un maillon du chemin critique.
#
# `$repo` se DERIVE de l'emplacement du script (comme `session-start.ps1`), il ne se code pas en
# dur : le hook suit le depot si on le deplace.
#
# ASCII STRICT : PowerShell 5.1 lit ce fichier en ANSI ; un accent y casse la chaine.

$ErrorActionPreference = 'SilentlyContinue'

# Le JSON du hook (cwd, stop_hook_active, session_id) est RETRANSMIS tel quel : c'est
# `loop_status --hook` qui decide de se taire, et c'est cette decision-la que garde probe_465.
$evt = [Console]::In.ReadToEnd()

# SANS CETTE LIGNE, PowerShell 5.1 prefixe d'un BOM UTF-8 tout ce qu'il pipe vers un
# executable natif. `json.loads` levait cote Python, la charge du hook retombait a vide, et le
# rappel se declenchait MEME quand Claude etait deja en train de continuer a cause de lui --
# c'est-a-dire la boucle qu'il est cense eviter. `loop_status` sait desormais avaler ce BOM,
# mais on ne l'emet plus : deux gardes valent mieux qu'un sur un chemin qu'on ne relit jamais.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$script = Join-Path $repo 'scripts\python\loop_status.py'
if (Test-Path $script) {
    $sortie = $evt | & python $script --hook 2>$null
    if ($sortie) { Write-Output ($sortie -join "`n") }
}

exit 0
