# setup-agent-worktree.ps1 -- VERIFIE qu'un worktree agent est runnable.
#
# CE SCRIPT NE CREE PLUS DE JONCTION (2026-07-26). Il ne reste que par compatibilite,
# pour qu'un brief d'agent pas encore mis a jour recoive un message clair au lieu d'un
# "fichier introuvable". Il ne modifie RIEN : il constate et rend un code de sortie.
#
# POURQUOI LA JONCTION A DISPARU
# Elle joignait <worktree>\data -> <arbre principal>\data parce que les entrees dont
# dependent gameconfig.py / rl_duel.py / les probes etaient gitignorees. data/ etait donc
# PHYSIQUEMENT PARTAGE entre tous les agents, avec trois consequences :
#   a) le script SUPPRIMAIT le data\symbols que git venait de materialiser dans le worktree
#      pour le remplacer par celui de l'arbre principal -> la table de symboles d'un agent
#      n'etait PAS celle de SON commit ; un checkout detache de l'arbre principal a deja
#      prive TOUS les agents de leur table d'un coup ;
#   b) les N agents ecrivaient leurs state-files dans le MEME repertoire -> d'ou la
#      discipline "un nom unique par agent", et 355 fichiers d'etat retrouves le
#      2026-07-26 qui avaient SURVECU aux worktrees les ayant produits ;
#   c) `git worktree remove --force` sur la jonction DETRUISAIT le data/ partage
#      (arrive le 2026-07-22).
#
# CE QUI L'A REMPLACEE : les quatre ENTREES sont VERSIONNEES (symbols/, boards/,
# seed-bc.json, i2_en.json -- ~1,1 Mo compresse, cf. .gitignore). Un worktree frais les
# tient donc de SON PROPRE commit. Et les SORTIES (state-files de probe, rl-state/...)
# sont ecrites dans le data/ local du worktree, gitignore : elles MEURENT avec lui.
#
# Usage :
#   powershell -File C:\Users\nicolasv\tacticus-tools\scripts\setup-agent-worktree.ps1 [-WorktreePath <chemin>]

param([string]$WorktreePath = (Get-Location).Path)

$REQUIRED = @(
    @{ Path = "data\symbols";      Kind = "table de symboles du build" },
    @{ Path = "data\boards";       Kind = "779 dumps de plateau (rl_duel --board)" },
    @{ Path = "data\seed-bc.json"; Kind = "seed BC template des runners isoles" },
    @{ Path = "data\i2_en.json";   Kind = "localisation i2 (texte de regles)" }
)

if (-not (Test-Path (Join-Path $WorktreePath ".git"))) {
    Write-Error "Pas un worktree git : $WorktreePath"
    exit 1
}

# Une jonction heritee d'avant le 2026-07-26 est un PIEGE : le worktree lirait les entrees
# de l'arbre principal et non de son commit, et un `worktree remove --force` detruirait le
# data/ partage. On la signale sans y toucher (la supprimer sans passer par `rmdir` sur le
# lien LUI-MEME suit le lien et efface la cible).
$link = Join-Path $WorktreePath "data"
if (Test-Path $link) {
    $item = Get-Item $link -Force
    if ($item.LinkType) {
        Write-Error ("data/ est un $($item.LinkType) vers $($item.Target) -- heritage d'avant " +
            "la suppression de la jonction. A retirer avec `rmdir data` (JAMAIS Remove-Item " +
            "-Recurse, qui suivrait le lien et effacerait la cible), puis " +
            "`git checkout -- data` pour materialiser les entrees versionnees.")
        exit 1
    }
}

$missing = @()
foreach ($r in $REQUIRED) {
    if (-not (Test-Path (Join-Path $WorktreePath $r.Path))) { $missing += $r }
}
if ($missing.Count -gt 0) {
    foreach ($m in $missing) { Write-Output "MANQUE $($m.Path) -- $($m.Kind)" }
    Write-Error ("Entrees absentes du checkout. Elles sont VERSIONNEES : " +
        "`git checkout -- data` devrait suffire. Si le commit du worktree est anterieur " +
        "au 2026-07-26, il precede leur versionnement -> rebaser sur origin/master.")
    exit 1
}

Write-Output "OK: worktree runnable par son seul checkout (aucune jonction requise)."
foreach ($r in $REQUIRED) { Write-Output "   $($r.Path)" }
exit 0
