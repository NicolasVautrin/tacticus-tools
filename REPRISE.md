# Reprise -- agent `#462-r4d-r3` (deux canaux du MEME cote)

Arrete par l'UTILISATEUR le 2026-08-04, alors qu'il en etait a la lecture des docs (aucune edition).
Ce fichier n'a qu'un role : rendre le worktree SALE pour qu'il survive. Un worktree propre est
auto-supprime, et la reprise repartirait dans l'ARBRE PRINCIPAL, ou l'agent editerait `master`.
Le supprimer de l'index (`git rm --cached REPRISE.md`) avant d'ouvrir une PR.

## Tache

`#462-r4d-r3` -- le regime **deux canaux du MEME cote** n'a jamais ete exerce : un `EffectBonus %`
ET un stat-mod DEFENSE sur la MEME cible, **en combat**. Ce n'est pas le « deux faces » de #462-r4a.

Blocage concret connu : le montage est ECRIT mais `--thorns` **ne s'installe pas** sur `MC1_67`.
Changer de board, ou trouver l'autre producteur de stat-mod DEFENSE.

Canal nomme : transposer `probe_446_r2_base_min_residual.both_faces` (flag `--both-faces`,
fonction ligne 261) vers melee / combat.

## A lire en premier

* `docs/rl/case-462-r4d-arrondi-inter-faces-combat.md` (residu en §7)
* `scripts/python/probe_462d_nightshroud_stage_diff.py` -- contient `solve_bounds`, qui inverse les
  bornes natives a etat PRNG connu, SANS inference. C'est l'outil qui tranche quand l'ecart n'est
  pas constant ; ne pas se rabattre sur une soustraction.
* `scripts/python/tests/engine/runner/test_462_r4d_nightshroud_cells_offline.py` -- le cran offline
  APPELLE `AttackDamageOperation._apply_defender_flat_reductions` au lieu de le simuler. Sa premiere
  version simulait et rendait 109 au lieu de 108 : une garde de fiction. Ne pas refaire l'erreur.

## Rappels

RE d'abord (decompile = verite), citation par SYMBOLE jamais par VA, jamais fitter un scalaire.
⚠ Un accord obtenu la ou deux modeles COINCIDENT ne prouve rien -- sur la branche ARMURE le plancher
est affine de pente 1, donc les deux placements coincident. L'assertionner comme BORNE.
Aucune (re)injection Frida ni redemarrage de host. Tests cibles, 4 max en parallele. Banque
`-Since origin/master` verte + attestation `probe_462` avant la PR. Livraison PAR PULL REQUEST.
