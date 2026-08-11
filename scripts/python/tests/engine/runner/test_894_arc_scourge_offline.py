"""GARDES OFFLINE #894 -- `1173 ArcScourge` (`admecBossBelisarius` « Belisarius Cawl »).

CE QUE CE FICHIER GARDE, ET POURQUOI CE TEMOIN-LA. Le point que l'arbre natif impose et qu'on ne
devine pas, c'est que **`AddPersistentData` n'est PAS inconditionnel dans la branche ENNEMIE** :

    perTarget = If( AreEnemies(Caster, ActiveTarget),
                    Attack + If( IsMechanical(ActiveTarget), Stunned + AddPersistentData, 0 ),
                    AddPersistentData + Inform )

Donc un maillon ENNEMI NON MECANIQUE prend les degats et n'incremente RIEN. C'est exactement ce
que la mesure live montre (deux casts consecutifs sur `GB_Belisarius_01`, boss place en (0,2)) :

    cast 1 : 2 maillons x 3 hits (u92 puis u88), DamageProfileType=5, Active_Ability_Type=1173
             -> `Effect_Refresh MachineVengeance` sur le CASTER, `Effect_CurrentLevel=0`
    cast 2 : 3 maillons x 3 hits (u92, u84, u88)
             -> `UpdateEffectLevel e=97 Effect_PreviousLevel=0 Effect_CurrentLevel=0`

⚠ LE TEMOIN DISCRIMINE, et c'est verifiable DANS LE MEME FLUX : au meme instant, un autre effet
porte `Effect_CurrentLevel=1` (`ThrillSeekers` sur u88). Un `0` partout ne prouverait rien -- ici
le champ sait valoir autre chose, donc le `0` de `MachineVengeance` MESURE l'absence d'increment.

CE QUI N'EST PAS COUVERT, et c'est nomme :
  * le regime MECANIQUE (maillon mecanique -> `Stunned` + increment -> `MachineVengeance` de
    niveau non nul) et le regime ALLIE (relais) : aucun des cinq ennemis du roster par defaut de
    ce board n'est mecanique, et monter un roster choisi n'est pas fait ici ;
  * **la garde LIVE elle-meme**. La mesure ci-dessus a ete faite A LA MAIN via `rl_duel act`,
    pas par pytest : sous le harnais, `applyAction` rend une CASCADE de groupes que `rl_duel`
    decode (`_print_apply`) et dont la forme n'a pas ete etablie ici -- un `UnitDamaged` plat
    n'y apparait pas. Ce fichier est donc OFFLINE et ne joue AUCUN runner ; la garde live est un
    residu NOMME (#894-r1), avec le datapoint ci-dessus a rejouer.

ASCII only.

ASCII only.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0].rstrip("\\/"))

from engine.entities.active_ability_type import ActiveAbilityType    # noqa: E402
from engine.entities.effect_type import EffectType                   # noqa: E402
from engine.runner.abilities.admec import (ArcScourgeAbility, AS_MACHINE_VENGEANCE,  # noqa: E402
                                           AS_PD_KEY, AS_STUNNED, _arc_scourge_const)
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402


def test_894_registre_et_masque():
    """Les DEUX donnees du registre, posees dans le meme commit que l'entree."""
    aid = int(ActiveAbilityType.ArcScourge)
    assert ABILITY_CLASSES.get(aid) is ArcScourgeAbility
    opts = ArcScourgeAbility.TARGETING_OPTIONS
    assert opts is not None
    # 0x4006, LU au `ArcScourgeAbility$$.ctor` -- decomposition EXHAUSTIVE, 0 bit residuel.
    attendu = (TR.TargetMatchesDynamicRule | TR.CasterMatchesDynamicRule | TR.TargetIsEnemy)
    assert int(opts.rules) == int(attendu) == 0x4006, hex(int(opts.rules))
    assert int(ABILITY_ATTACK_TYPE[ActiveAbilityType.ArcScourge]) == 2      # Others


def test_894_constantes_du_gameconfig():
    """Les trois `GetNumberConstant` de l'arbre, apparies a leur ordinal `AbilityConstantType`."""
    assert _arc_scourge_const("maxAdjacentTargets") == 3      # 0x75 -- borne des SAUTS
    assert _arc_scourge_const("effectLevel") == 1             # 0x73 -- increment par maillon
    assert _arc_scourge_const("effectLevel_2") == 9           # 0x76 -- plafond de la pile
    assert AS_MACHINE_VENGEANCE == int(EffectType.MachineVengeance) == 1365
    assert AS_STUNNED == int(EffectType.Stunned) == 1162
    assert AS_PD_KEY == "EffectLevel"
