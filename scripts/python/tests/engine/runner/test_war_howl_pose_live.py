"""CLIQUET #585 -- la POSE de `WarHowl` (1106) : QUI recoit 1222, et le TRAIT suit-il ?

Pendant du cliquet #366-r1 (`test_war_howl_extra_damage_live.py`), qui garde la LECTURE de l'effet
`WarHowl_ExtraDamage_Unstoppable` (1222) quand le NATIF l'a pose. Celui-ci garde la POSE elle-meme,
c.-a-d. la face que le residu 6.3 de `docs/rl/case-366-r1-war-howl-extra-damage.md` laissait
ouverte : `IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$ExecuteBehaviour`.

CE QUE LE MONTAGE DISCRIMINE (trois valeurs distinctes sur la MEME equipe, pas un accord global) :

    P : spaceBlackmane (Ragnar, le CASTER)  -- entre par le `op_Addition(Owner, ...)`
        spaceRockfist  (Arjac)              -- ami MELEE PUR    -> BUFFE (une fois ATTERRI)
        spaceStormcaller                    -- arme `Range = 2` -> JAMAIS buffe
    A : deux necrons                        -- ecartes par `Friends`

Un port qui n'ajouterait pas le caster, un port sans `UnitsWithoutRangedWeapons` et un port sans le
`selectionType` rendent TROIS resultats differents -- c'est ce qui fait de ce montage une garde et
non un constat.

DEUX REGIMES, et le second n'est PAS un doublon du premier :
  * `--land-turns 0` : `spaceRockfist` est en DEEP STRIKE (`TeleportStrike_TeleportingIn`), donc il
    porte `UnitFlag.Untargetable` -> le natif ne le buffe PAS. C'est le SEUL bras qui exerce le
    `selectionType = 3` (`UnitSelectionType.OnlyAliveAndTargetable`, lu par
    `IdunBattle.DSL.TargetsSelector$$SelectUnit` -> `UnitExtensions$$MatchesUnitSelectionType`).
  * `--land-turns 2` : il a atterri -> le natif le buffe. C'est le bras qui exerce
    `UnitsWithoutRangedWeapons` (sans lui, `spaceStormcaller` entrerait aussi).

⚠ L'annotation « (armes a distance) » de `case-366-r1` §2 a propos de `spaceRockfist` est REFUTEE
par ce montage : Arjac n'a qu'une arme, MELEE, au gameconfig comme dans `data/seed-bc.json`. Ce qui
l'ecartait ce jour-la etait le camp (le montage de `probe_366_r1` ne met que deux unites cote
joueur), pas ses armes.

VUES ROUGES MESUREES (mutations adversariales, fiche `docs/rl/case-585-war-howl-pose.md` §4) :
  * `selectionType` -> `Any`            : regime 0, PORT `[81, 83]` vs LIVE `[81]`      -> DIVERGE
  * `UnitsWithoutRangedWeapons` retire  : regime 2, PORT `[81, 83, 85]` vs LIVE `[81, 83]` -> DIVERGE
  * `applied_traits` -> `[]`            : face PORT `[]` vs natif `[81]`                -> DIVERGE
    (les DEUX autres bras restent VERTS sous cette mutation : c'est ce qui rend le bras face-PORT
     obligatoire -- une garde qui ne lit que l'oracle natif ne voit pas un canal de port eteint.)

⚠ Le volet OFFLINE (registre, declaration de trait, cablage du `selectionType`) vit dans
`test_585_war_howl_pose_offline.py` -- et il y vit parce que trois tests offline heberges dans un
`*_live.py` sont INVISIBLES des deux gardes de selection, qui excluent les `_live.py` par choix.

ASCII only.
"""
from __future__ import annotations

#: LARGE, ET C'EST UN RESULTAT (le doute se resout TOUJOURS du cote large). Un cast confronte LIVE
#: traverse le moteur Python ENTIER -- l'arbre DSL, les selecteurs, le chargement d'etat, les
#: operations d'effet et de trait, le tick de fin de tour -- plus son montage (`probe_576`,
#: `rl_duel`, `rl_collect_batch`). Un declencheur qui enumererait la chaine attendue fabriquerait
#: un FAUX VERT : le fichier ne serait pas rejoue alors que son gisement vient de se rouvrir.
#: ⚠ LES DEUX GLOBS SONT NECESSAIRES : `scripts/python/**/*.py` exige un SEGMENT apres `**/` et
#: rate donc `scripts/python/rl_duel.py` et le probe lui-meme.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/*.py",
        "scripts/python/**/*.py",
        # Entrees VERSIONNEES du montage : le seed BC (armes et traits de depart des trois Space
        # Wolves) et le board `MC1_67`.
        "data/seed-bc.json", "data/boards/**",
    ),
    # Le verdict compare le PORT au JEU : les armes lues par `UnitsWithoutRangedWeapons` viennent
    # du gameconfig/BC du JEU, hors arbre -- un changement de build peut basculer le verdict sans
    # qu'un seul fichier du depot bouge.
    "build": True,
    "toujours": False,
    "raison": "Cast d'ability confronte LIVE : le perimetre reellement lu est le moteur Python "
              "entier (arbre DSL + selecteurs + `snapshot.load_state` + `AddEffectOperation` + "
              "`operations/traits` + `EndTurnOperation`) plus le montage (`probe_576`, `rl_duel`, "
              "`rl_collect_batch`), d'ou les deux globs. `build: True` parce que le discriminant "
              "repose sur des donnees du JEU : les armes de `spaceRockfist`/`spaceStormcaller` et "
              "le trait `TeleportStrike` qui met Arjac en deep strike au tour 1.",
}

import os

import pytest

import probe_585_war_howl_pose as P


# ------------------------------------------------------------------ LIVE : les deux regimes
@pytest.mark.parametrize("land_turns,attendu", [
    (0, "DEEP STRIKE : Arjac porte Untargetable -> le natif ne le buffe PAS"),
    (2, "ATTERRI : Arjac est un ami MELEE -> le natif le buffe"),
])
def test_pose_live(tmp_path, land_turns, attendu):
    """Rejoue le probe #585 : accord PORT/LIVE sur l'ensemble des cibles, PLUS la face PORT du
    trait (ajout puis retrait). `rc == 0` = les QUATRE verdicts sont OK."""
    sf = str(tmp_path / ("war_howl_pose_%s_%s.json" % (land_turns, os.getpid())))
    rc = P.main(["--state-file", sf, "--land-turns", str(land_turns)])
    assert rc == 0, "probe #585 rc=%s (%s)" % (rc, attendu)
