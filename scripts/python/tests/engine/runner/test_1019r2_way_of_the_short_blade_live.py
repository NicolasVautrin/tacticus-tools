"""GARDE LIVE de `WayOfTheShortBlade_AttackAbility` (#1019-r2) -- la SECONDE attaque normale, et
surtout le fait qu'elle est a DISTANCE alors que le caster est AU CONTACT.

GROUND TRUTH MESURE LE 2026-08-15 (build `t6dpr4k06g`, board `MC1_67`, seed 777, `tauFarsight`
injecte au catalogue et pose a `(2,2)`, `ultraTitus` a `(2,3)` ; Farsight bouge en `(3,3)` puis
lance son attaque normale sur Titus). La cascade native, VERBATIM :

    [Ability_Power e=77 «Loki_NormalAttack»]
      Info  Attack_Weapon_DamageProfile=14  Attack_Weapon_IsMelee=1        <- 4 coups, profil Power
      ... 4 x [Damage e=81] DamageProfileType=14 ...
      [Ability_Power e=77 «WayOfTheShortBlade»]                            <- LE TRIGGER FIRE
        [Ability_Power e=77 «Loki_NormalAttack»]
          Info  Attack_Weapon_DamageProfile=7  Attack_Weapon_IsMelee=0     <- 2 coups, profil Plasma
          ... 2 x [Damage e=81] DamageProfileType=7 ...

TROIS FAITS que cette cascade etablit, et qu'aucune lecture seule ne donnait :

  1. **Farsight declenche sur SA PROPRE attaque** -> la branche `op_Addition Owner@<DSLSelectors
     +0x30>` du `CreateTargetSelector` de l'effet `1500` est REELLE (le jumeau `1499` ne l'a pas,
     et recopier l'un sur l'autre aurait donne le mauvais ensemble) ;
  2. **la seconde attaque est `Attack_Weapon_IsMelee=0` ALORS QUE le caster est ADJACENT** -> c'est
     le `AddFlag(Caster, 0x15 = UnitFlag.ForceRangedAttack)` du behaviour, et donc le second
     conjoint `!HasFlag(attacker, 0x15)` de `IdunBattle.Core.Services.BattleQuery$$
     GetAttackWeaponForDefaultNormalAttack`. C'est litteralement le << even if they are adjacent to
     it >> de l'i2 ;
  3. **il n'y a PAS de troisieme attaque** -> le garde-fou de re-entrance tient : la sous-attaque
     etant RANGED, le `IsMeleeAttack()` du `CreateTrigger` est FAUX pour elle.

CE QUE CE FICHIER CONFRONTE. Le point 2 est l'etage que la tranche a porte, et il se confronte
DIRECTEMENT et sans runner : le natif a choisi `DamageProfile=14 = Power` (4 coups) puis
`DamageProfile=7 = Plasma` (2 coups) pour la MEME unite a la MEME distance ; le port doit rendre
EXACTEMENT le meme couple selon la valeur du drapeau. Le temoin est NON DEGENERE par construction
(`Power != Plasma`, `4 != 2`) et le test l'ASSERTIONNE avant de conclure.

⚠ POURQUOI `tauFarsight` ET PAS `tauAunShi`. La fiche `#1019-r2` proposait `tauAunShi` comme
porteur confrontable. C'est un temoin DEGENERE : mesure sur le gameconfig, `tauAunShi` n'a
**AUCUNE arme de portee** (`melee=[Power]`, `ranged=[]`). Le natif y prend donc la branche
`FindRangedWeapon -> null` et `ALoki_NormalAttackAbility$$ExecuteBehaviour` retourne sans rien
faire (`if (weapon == null) return;`) -- l'attaque supplementaire est un NO-OP, des deux cotes, et
le test aurait ete vert sans rien mesurer. `tauFarsight` porte les DEUX armes (`Power` en melee,
`Plasma` portee 2) et il est dans son propre marqueur : c'est LUI le temoin.
"""
from __future__ import annotations

import os
import sys

import pytest

_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

import gameconfig as GC                                                    # noqa: E402
from engine.entities.damage_profile_type import DamageProfileType          # noqa: E402
from engine.services import battle_query as BQ                             # noqa: E402

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # L'ETAGE confronte et son foyer PARTAGE.
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        # LE MIRROR de l'ability et son registre.
        "scripts/python/engine/runner/operations/triggers/loki/way_of_the_short_blade.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # LES DEUX FEUILLES DSL du behaviour.
        "scripts/python/engine/runner/abilities/behaviours/flags.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        # LA GEOMETRIE de cibles de l'effet 1500 (le gate du trigger).
        "scripts/python/engine/entities/effect_targets.py",
        "scripts/python/engine/entities/effects/loki/way_of_the_short_blade.py",
        "scripts/python/engine/entities/unit_flag.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Le verdict compare le couple (profil, nombre de coups) que le PORT choisit selon "
        "`force_ranged_attack` au couple que le NATIF a choisi dans la cascade mesuree. Il depend "
        "donc du service de selection d'arme et de ses deux appelants, du mirror de l'ability et "
        "de son registre, des deux feuilles `AddFlag`/`RemoveFlag`, et de la geometrie de cibles "
        "de l'effet 1500 -- plus du BUILD, puisque les armes viennent du gameconfig."),
}

#: Le couple MESURE dans la cascade native (cf. l'en-tete). `DamageProfileType` 14 = `Power`,
#: 7 = `Plasma` -- noms LUS dans le mirror, jamais recopies d'un ordinal nu.
NATIF_MELEE_PROFIL = DamageProfileType.Power.name         # `Attack_Weapon_DamageProfile=14`
NATIF_MELEE_COUPS = 4                                     # 4 blocs `[Damage]` sous le 1er atomique
NATIF_RANGED_PROFIL = DamageProfileType.Plasma.name       # `Attack_Weapon_DamageProfile=7`
NATIF_RANGED_COUPS = 2                                    # 2 blocs `[Damage]` sous le 2e atomique
PORTEUR = "tauFarsight"


def test_le_temoin_est_non_degenere():
    """`tauFarsight` doit porter les DEUX armes, et elles doivent DIFFERER -- sinon la confrontation
    ne separe rien. C'est aussi ce qui disqualifie `tauAunShi` (cf. l'en-tete)."""
    armes = (GC.unit(PORTEUR) or {}).get("weapons") or []
    melee = [w for w in armes if BQ.weapon_is_melee(w)]
    ranged = [w for w in armes if not BQ.weapon_is_melee(w)]
    assert melee, "%s n'a plus d'arme de melee : temoin degenere" % PORTEUR
    assert ranged, "%s n'a plus d'arme de portee : temoin degenere" % PORTEUR
    assert NATIF_MELEE_PROFIL != NATIF_RANGED_PROFIL
    assert NATIF_MELEE_COUPS != NATIF_RANGED_COUPS


def test_le_port_choisit_le_meme_couple_que_le_natif_selon_le_drapeau():
    """CONFRONTATION -- meme unite, meme distance (1, le CONTACT), seul le drapeau change.

    Sans drapeau, le natif a pris `Power` en 4 coups ; avec, `Plasma` en 2. Le port doit rendre
    exactement ces deux couples, et rien d'autre."""
    w_off, ranged_off = BQ.get_attack_weapon_for_default_normal_attack(
        PORTEUR, is_adjacent=True, dist=1, force_ranged_attack=False)
    w_on, ranged_on = BQ.get_attack_weapon_for_default_normal_attack(
        PORTEUR, is_adjacent=True, dist=1, force_ranged_attack=True)

    assert w_off is not None and w_on is not None, "le montage doit rendre une arme des deux cotes"
    # -- ATTAQUE 1 : la MELEE nominale.
    assert w_off.get("DamageProfile") == NATIF_MELEE_PROFIL
    assert int(w_off.get("hits") or 0) == NATIF_MELEE_COUPS
    assert ranged_off is False, "`Attack_Weapon_IsMelee=1` cote natif"
    # -- ATTAQUE 2 : celle de `WayOfTheShortBlade`, AU CONTACT et pourtant A DISTANCE.
    assert w_on.get("DamageProfile") == NATIF_RANGED_PROFIL
    assert int(w_on.get("hits") or 0) == NATIF_RANGED_COUPS
    assert ranged_on is True, "`Attack_Weapon_IsMelee=0` cote natif, alors que dist == 1"


@pytest.mark.parametrize("adjacent,dist", [(True, 1), (False, 2), (False, 3)])
def test_le_drapeau_ne_change_rien_sur_un_porteur_sans_arme_de_portee(adjacent, dist):
    """`tauAunShi` : le natif prend `FindRangedWeapon -> null` et `ExecuteBehaviour` RETOURNE.

    Le port doit rendre `None` -- pas une arme de melee de repli. C'est ce qui garantit que
    l'attaque supplementaire est un NO-OP sur ce porteur, DONC qu'aucune boucle ne se forme (une
    attaque de repli en MELEE re-satisferait `IsMeleeAttack()` et re-declencherait le trigger)."""
    w, _ = BQ.get_attack_weapon_for_default_normal_attack(
        "tauAunShi", is_adjacent=adjacent, dist=dist, force_ranged_attack=True)
    assert w is None, "aucun repli croise : un porteur sans arme de portee ne tire pas"
