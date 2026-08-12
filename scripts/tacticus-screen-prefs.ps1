<#
.SYNOPSIS
  Reduit le budget de rendu de Tacticus (fenetre 560x800) ou le restaure.

.DESCRIPTION
  POURQUOI. Mesure du 2026-07-28 : Tacticus est le SEUL client de la RTX 4070 et y consommait
  33,7 % en moyenne (43 % en pointe), 20,9 W, SM a 1500 MHz, 62 C -- pour afficher un ecran de
  bataille STATIQUE. La cause n'est pas un rendu couteux mais sa SURFACE : les prefs Unity
  demandaient 3840x2400 (9,2 Mpx, plus qu'un 4K) en plein ecran a 90 Hz, soit ~830 Mpx/s.
  Signature confirmee par `nvidia-smi` : utilization.gpu a 43 % pendant que utilization.memory
  reste a 3 % -- scene triviale, repeinte sur enormement de pixels.

  LA LARGEUR : 560, ET C'EST MESURE. L'UI de Tacticus est mobile-first -- elle rend une COLONNE
  PORTRAIT centree, et tout pixel donne au-dela devient une BANDE NOIRE. Capture du 2026-08-13 a
  900x800 : contenu 557x797, soit ~171 px perdus DE CHAQUE COTE. Le 1280x800 qui vivait ici
  divisait bien la surface, mais il payait encore 56 % de bandes noires -- il est RETIRE, pas
  ajuste. A 560x800 le contenu remplit la fenetre bord a bord :
  9 216 000 px -> 448 000 px, soit une division par 20.

  ⚠ Un chiffre de surface ne dit PAS si les pixels servent : celui-ci a tenu deux semaines
  parce que personne n'avait REGARDE la fenetre. `scripts/python/gamenav/regard.py` capture,
  et les bandes noires se voient immediatement.

  Le jeu sert ici d'hote de calcul IL2CPP pilote par Frida, pas d'objet a regarder : la
  resolution d'affichage n'a aucune incidence sur le harnais.

  PIEGE CENTRAL -- c'est la raison d'etre du garde-fou ci-dessous. Unity REECRIT ces clefs
  quand le joueur se ferme. Appliquer pendant que Tacticus tourne ne sert donc a rien : la
  valeur serait ecrasee a la sortie. Le script refuse de s'executer dans ce cas.

  Les clefs vivent dans HKCU\Software\Snowprint\<produit>, sont des DWORD, et survivent aux
  mises a jour du jeu (elles sont indexees par produit, pas par hash de build).

  LEVIER JUMEAU, A CHAUD -- le RPC `renderBudget` (frida/hooks/features/render-budget.ts) fait la
  meme chose sur le process VIVANT, sans le fermer :
      renderBudget({width:560, height:800, fullScreenMode:3, clampVSync:0, clampFrameRate:60})
  Les deux sont complementaires, pas redondants : ce script regle le DEMARRAGE (persistant), le
  RPC regle la SESSION EN COURS (volatile, perdu au prochain lancement ET a chaque reinject).

  ⛔ NE JAMAIS demander ExclusiveFullScreen (FullScreenMode = 0) sur un process vivant : c'est le
  seul mode qui force un changement de mode d'affichage DXGI, et il a deja tue le jeu une fois
  (`SetFullscreenState failed (887a0022)`, swapchain jamais recupere). Le mode 3 (fenetre) n'a pas
  ce vecteur.

  CE QUI PESE VRAIMENT -- mesure du 2026-07-28. Reduire la SURFACE ne suffit pas : `utilization.gpu`
  est un RAPPORT CYCLIQUE, pas une quantite de travail, et a 90 Hz de vSync le GPU est reveille
  90x/s quel que soit le nombre de pixels. Diviser la surface par 9 a fait tomber la PUISSANCE
  (18,6 W -> 6,6 W) sans bouger le pourcentage. C'est le bridage de CADENCE qui a fait le reste --
  et il exige une INTERCEPTION, pas une ecriture : le jeu reimpose vSync=1 / targetFrameRate=-1 a
  chaque frame (mesure : l'ecriture passe, puis est annulee avant la relecture suivante).
  Resultat cumule, meme ecran meme process : 32,9 % -> 18,6 % d'utilisation, 18,6 W -> 5,3 W,
  64 C -> 56 C, pointe 53 % -> 20 %.

.PARAMETER Restore
  Restaure les valeurs sauvegardees lors du dernier -Apply (fichier de sauvegarde JSON).

.PARAMETER Force
  Passe outre le garde-fou "jeu en cours". A n'utiliser que si l'on sait que le processus ne
  sortira pas proprement (il n'ecrira alors pas ses prefs).

.EXAMPLE
  powershell -File scripts\tacticus-screen-prefs.ps1
  powershell -File scripts\tacticus-screen-prefs.ps1 -Restore
#>
[CmdletBinding()]
param(
  [switch]$Restore,
  [switch]$Force,
  [int]$Width = 560,
  [int]$Height = 800
)

$ErrorActionPreference = 'Stop'

$KeyPath = 'HKCU:\Software\Snowprint\Warhammer 40,000: Tacticus'
$Backup  = Join-Path $PSScriptRoot '..\logs\tacticus-screen-prefs.backup.json'

# Les suffixes _h<hash> font partie du nom : Unity hache le nom de la pref, ils ne sont pas
# decoratifs et ne doivent pas etre reconstruits a la main.
$K = @{
  UseNative    = 'Screenmanager Resolution Use Native_h1405027254'
  Fullscreen   = 'Screenmanager Fullscreen mode_h3630240806'
  Width        = 'Screenmanager Resolution Width_h182942802'
  Height       = 'Screenmanager Resolution Height_h2627697771'
  WindowWidth  = 'Screenmanager Resolution Window Width_h2524650974'
  WindowHeight = 'Screenmanager Resolution Window Height_h1684712807'
}

# FullScreenMode d'Unity : 0=ExclusiveFullScreen, 1=FullScreenWindow, 2=MaximizedWindow, 3=Windowed
$MODE_WINDOWED = 3

function Get-Prefs {
  $out = @{}
  foreach ($e in $K.GetEnumerator()) {
    $out[$e.Key] = (Get-ItemProperty -Path $KeyPath -Name $e.Value -ErrorAction SilentlyContinue).($e.Value)
  }
  $out
}

function Set-Pref($name, $value) {
  Set-ItemProperty -Path $KeyPath -Name $K[$name] -Value $value -Type DWord
}

if (-not (Test-Path $KeyPath)) {
  throw "Clef introuvable : $KeyPath -- le jeu n'a jamais ete lance sur ce profil ?"
}

# --- garde-fou : Unity reecrit ses prefs a la fermeture ---------------------------------
$running = Get-Process -Name 'Tacticus' -ErrorAction SilentlyContinue
if ($running -and -not $Force) {
  Write-Host "REFUS : Tacticus tourne (PID $($running.Id -join ', '))." -ForegroundColor Yellow
  Write-Host "Unity reecrit ces prefs en quittant : la modification serait ecrasee."
  Write-Host "Fermer le jeu, puis relancer ce script. (-Force pour passer outre.)"
  exit 1
}

$before = Get-Prefs
Write-Host "--- avant ---"
$before.GetEnumerator() | Sort-Object Name | ForEach-Object { "  {0,-13} {1}" -f $_.Key, $_.Value }

if ($Restore) {
  if (-not (Test-Path $Backup)) { throw "Aucune sauvegarde : $Backup" }
  $saved = Get-Content $Backup -Raw | ConvertFrom-Json
  foreach ($n in $K.Keys) { if ($null -ne $saved.$n) { Set-Pref $n ([int]$saved.$n) } }
  Write-Host "`nRestaure depuis $Backup"
} else {
  New-Item -ItemType Directory -Force -Path (Split-Path $Backup) | Out-Null
  $before | ConvertTo-Json | Set-Content -Path $Backup -Encoding utf8
  Write-Host "`nSauvegarde -> $Backup"

  Set-Pref UseNative    0
  Set-Pref Fullscreen   $MODE_WINDOWED
  Set-Pref Width        $Width
  Set-Pref Height       $Height
  Set-Pref WindowWidth  $Width
  Set-Pref WindowHeight $Height

  $px  = [double]$Width * $Height
  $old = [double]$before.Width * $before.Height
  if ($old -gt 0) {
    Write-Host ("`nSurface : {0:n0} px -> {1:n0} px  (division par {2:n1})" -f $old, $px, ($old / $px))
  }
}

Write-Host "`n--- apres ---"
(Get-Prefs).GetEnumerator() | Sort-Object Name | ForEach-Object { "  {0,-13} {1}" -f $_.Key, $_.Value }
Write-Host "`nPrend effet au PROCHAIN lancement du jeu."
