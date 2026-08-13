"""CLIQUET #996 (volet LIVE) -- confrontation port/natif des trois no-op silencieuses portees.

Rejoue `probe_996_no_op_silencieuses.py` pour 1185, 1133 et 1010. `rc == 0` = les TROIS bras du
probe sont OK pour l'ability :

  A. le NATIF a REELLEMENT execute le cast (`actionConsumed` / `mutated`, pas le seul `ok: True` --
     un cast REFUSE rend `ok: True`, `mutated: False`, `changes: []`, et ouvre quand meme un
     evenement `group` portant le nom de l'ability) ;
  B. la face CIBLAGE du port ACCEPTE ce que le natif a execute (un masque trop strict rougirait
     ici -- la degradation inverse, permissive, est celle du port d'avant) ;
  C. la face EXECUTION du port, rejouee sur l'etat d'AVANT le cast, rend le MEME resultat que le
     natif : memes effets sur les memes unites (1185, 1133) ; deux attaques emises la ou le natif
     inflige des degats (1010).

**C'EST LE BRAS C QUI EST LE POINT DE LA TRANCHE.** Avant ce port, les trois abilities etaient
ABSENTES d'`ABILITY_CLASSES` : `AbilityHandler.visit_ActiveAbilityMessage` repondait
`ported: False`, 0 degat, 0 effet, AUCUNE erreur. Le bras A, lui, a toujours ete vert. C'est ce qui
rend ce mode de panne invisible en replay et en self-play.

CE QUI N'EST PAS COUVERT, ET IL FAUT LE LIRE :
  * 1010 -- le MONTANT des degats du port n'est pas confronte. `UseActiveAbility` rend
    `skipped: "rng_non_cale"` sur un etat RECHARGE (le flux `state.rng` n'est pas rejouable depuis
    un `load_state`), donc le bras C garde la STRUCTURE (deux attaques, bonne cible) et le fait que
    le natif, lui, inflige bien des degats. Le montant releve des tests de damage, pas d'ici.
  * la MECANIQUE des effets poses par 1133 (`WarConstruct_CounterAttack`,
    `IgnoreUsedAbilityInOverwatch`) et la MAGNITUDE de `ForwardObservers_DamageReduction` : elles
    vivent dans les classes d'EFFET natives, hors de ces trois `ExecuteBehaviour`. Les effets sont
    POSES et INERTES -- residu nomme dans `docs/rl/case-996-...`.

ASCII only (cp1252).
"""
from __future__ import annotations

#: LARGE, ET C'EST UN RESULTAT. Un cast confronte LIVE traverse le moteur Python ENTIER (arbre DSL,
#: selecteurs, `snapshot.load_state`, operations d'effet et d'attaque, gate de ciblage, geometrie
#: hex) PLUS son montage (`rl_duel`, `rl_collect_batch`, le probe). Un declencheur qui enumererait
#: la chaine attendue fabriquerait un FAUX VERT : le fichier ne serait pas rejoue alors que son
#: gisement vient de se rouvrir.
#: ⚠ LES DEUX GLOBS SONT NECESSAIRES : `scripts/python/**/*.py` exige un SEGMENT apres `**/` et rate
#: donc `scripts/python/rl_duel.py`, `scripts/python/hexgeo.py` et le probe lui-meme.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/*.py",
        "scripts/python/**/*.py",
        "data/seed-bc.json", "data/boards/**",
    ),
    # Le verdict compare le PORT au JEU : les stats/armes des trois porteurs npc viennent de
    # `units.npc[id].stats[]` du gameconfig (voie `--explicit-stats`), hors arbre -- un changement
    # de build peut basculer le verdict sans qu'un seul fichier du depot bouge.
    "build": True,
    "toujours": False,
    "raison": "Trois casts d'ability confrontes LIVE : le perimetre reellement lu est le moteur "
              "Python entier plus le montage (`rl_duel build --explicit-stats`, `rl_collect_batch`, "
              "`hexgeo`), d'ou les deux globs. `build: True` parce que le discriminant repose sur "
              "des donnees du JEU : les stats npc des porteurs et la geometrie du board MC1_67.",
}

import os

import pytest

import probe_996_no_op_silencieuses as P


@pytest.mark.parametrize("ability,attendu", [
    (1133, "WarConstruct -- cast SELF, deux AddEffect a TurnsFromRounds(1)"),
    (1185, "ForwardObservers -- Markerlight sur la CIBLE (2 rounds) + DamageReduction sur SOI (1)"),
    (1010, "StormOfFlensingBlades -- DEUX attaques normales, aucun effet"),
])
def test_confrontation_live(tmp_path, ability, attendu):
    """`rc == 0` = bras A, B et C OK. `rc == 4` = accord sur un REFUS (le montage n'a pas produit
    de cast accepte) : ce n'est PAS un vert -- la face EXECUTION n'aurait alors ete confrontee par
    rien, et c'est precisement ce que cette tranche repare."""
    sf = str(tmp_path / ("p996_%d_%d.json" % (ability, os.getpid())))
    rc = P.main(["--ability", str(ability), "--max-tours", "10", "--state-file", sf])
    assert rc == 0, "probe #996 ability=%d rc=%s (%s)" % (ability, rc, attendu)
