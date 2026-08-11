"""#925 -- l'INVENTAIRE DES FACES de `Boltstorm` (triggered 1090, passif de `templAggressor`), grave.

`Boltstorm` n'a PAS de `CreateTrigger` ni de `CreateBehaviour` : la classe
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility` (base
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`) n'expose que DEUX methodes,
`$$GetAdditionalTargets` et `$$GetAllTargets` -- deux ARBRES DE CIBLAGE. Le passif agit en
SUBSTITUANT l'attaque normale (`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`
-> `ActiveAbilityType.Boltstorm_NormalAttack` 1128), et c'est cette attaque-la qui porte le corps.

Il n'entre donc NI dans `ABILITY_TRIGGERS`, NI dans `ABILITY_INIT_OWNER_EFFECTS`, NI dans
`EFFECT_CLASSES` -- les trois registres que `audit_kit_coverage.py` interroge. C'est la CAUSE de son
faux `manque 1` dans `docs/rl/kit-coverage.md`, et la 4e voie (`custom_normal_attack`) est desormais
lue par l'audit ; ce fichier garde que les faces, elles, sont bien la ou la RE les place.

LES QUATRE FACES, et leur verdict :

| face | artefact natif | verdict |
|---|---|---|
| DECISION owner ATTACK | `IdunBattle.AI.Playbook.Loki.BoltstormPlaybook$$CalculateAttackUtilityInStepsInternal` | PORTEE (#446) |
| DECISION owner MOVE | `BoltstormPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` | **DEAD** -- `yield Fix64.op_Implicit(0)` |
| DECISION prediction | `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction` | PORTEE (#446-r1) |
| COMBAT | `...Boltstorm_NormalAttackAbility$$ExecuteBoltstorm` (CLEAVE) + `$$GetCustomNormalAttackBehaviour` (FOLD) | PORTEE (#478, #419-r3, #925) |

ASCII only. Purement OFFLINE (aucun runner, aucun RPC).
"""
from __future__ import annotations

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.behaviours import AtomicGroup, Foreach
from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
from engine.runner.abilities.loki import additional_targets as AT

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/loki/additional_targets.py",
        "scripts/python/engine/playbook/boltstorm.py",
        "scripts/python/engine/playbook/psyker.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py"),
    "build": True,
    "toujours": False,
    "raison": "Il grave l'inventaire des faces de `Boltstorm` : les deux registres de DECISION, "
              "la table de dispatch du CLEAVE et les deux drapeaux de ses volets. `build: True` "
              "parce que les deux ordinaux (1090 / 1128) sont lus dans les mirrors d'enum, qui se "
              "re-derivent du dump.",
}

_BOLTSTORM = int(TriggeredAbilityType.Boltstorm)                    # 1090
_NORMAL = int(ActiveAbilityType.Boltstorm_NormalAttack)             # 1128


def test_la_face_move_est_dead_et_le_registre_est_temoin():
    """`BoltstormPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` a un corps
    TRIVIAL -- `Fix64.op_Implicit(0)` puis `return` : un ZERO CONSTANT, aucune lecture d'etat.
    L'absence du registre EST donc le comportement natif, pas un trou.

    ⚠ Le cran qui rend cette assertion NON VIDE : le registre doit etre PEUPLE. Un
    `TRIGGERED_MOVE_PLAYBOOKS` vide (import casse, renommage) ferait passer un `not in` sans rien
    prouver -- c'est exactement la forme de faux vert que #270-r1-r1-r3 a documentee."""
    assert TRIGGERED_MOVE_PLAYBOOKS, (
        "`TRIGGERED_MOVE_PLAYBOOKS` est VIDE : le `not in` ci-dessous passerait sans rien prouver")
    assert _BOLTSTORM not in TRIGGERED_MOVE_PLAYBOOKS, (
        f"`Boltstorm` ({_BOLTSTORM}) est entre au registre des playbooks de MOUVEMENT, alors que "
        f"son corps natif est un `yield Fix64.op_Implicit(0)` constant -- le porter lui donnerait "
        f"un terme d'utilite que le natif n'a pas")


def test_la_face_attack_est_portee():
    """La SEULE face de playbook qui ait un corps : `$$CalculateAttackUtilityInStepsInternal`
    (poids `BOLTSTORM_AdjacentEnemies` x cardinal de `$$GetAllTargets`, #446)."""
    assert _BOLTSTORM in TRIGGERED_ATTACK_PLAYBOOKS, (
        f"`Boltstorm` ({_BOLTSTORM}) est sorti du registre des playbooks d'ATTAQUE -- sa face "
        f"DECISION owner n'est plus portee")


def test_la_face_combat_porte_les_deux_gates_lues():
    """La table de dispatch du CLEAVE. Les TROIS champs de `Boltstorm` sont INVERSES ou uniques par
    rapport a ses trois voisins de famille, et c'est ce qui interdit de les porter par analogie :

      * `cleaves_when_melee = False` -- `...Boltstorm_NormalAttackAbility$$ExecuteBehaviour` route
        vers `$$ExecuteBoltstorm` sur `IsMelee == 0` (les trois autres cleavent en MELEE) ;
      * `primary_fold_when_melee_position = False` -- son `$$GetCustomNormalAttackBehaviour` gate
        sur `IdunBattleLogic.Entities.DSLTriggers$$IsRangedPosition` (`RighteousRepugnance` gate
        `IsMeleePosition` ; `Fealty` et `TalonOfHorus` n'ont PAS ce symbole -> `None`) ;
      * `needs_weapon_range = True` -- SEUL son arbre consomme `Direct(attackWeapon.Range.Value)`."""
    e = AT.NORMAL_ATTACK_CLEAVES["Boltstorm"]
    assert e.cleaves_when_melee is False
    assert e.primary_fold_when_melee_position is False
    assert e.needs_weapon_range is True
    # le CONTRASTE, dans le meme test : sans lui, trois booleens justes ne diraient pas qu'ils sont
    # DISTINCTIFS. `None` (pas de fold du tout) et `False` (fold a distance) sont deux etats.
    assert AT.NORMAL_ATTACK_CLEAVES["RighteousRepugnance"].primary_fold_when_melee_position is True
    assert AT.NORMAL_ATTACK_CLEAVES["Fealty"].primary_fold_when_melee_position is None
    assert AT.NORMAL_ATTACK_CLEAVES["TalonOfHorus"].primary_fold_when_melee_position is None
    assert all(AT.NORMAL_ATTACK_CLEAVES[n].cleaves_when_melee is True
               for n in ("Fealty", "TalonOfHorus", "RighteousRepugnance"))


def test_l_attaque_normale_substituee_est_bien_1128():
    """La cascade `UnitFactory$$AddNormalAttackAbility` monte `Boltstorm_NormalAttack` (1128) pour
    un porteur du passif : c'est la CLE de la face COMBAT (le port lit la config au SLOT PASSIF).

    Le registre est keye par NOM des DEUX cotes -- on confronte donc le nom, PUIS l'ordinal qu'il
    designe dans le mirror d'enum : c'est l'appariement nom -> ordinal qui peut glisser au
    changement de build, pas le nom seul."""
    from engine.services.custom_normal_attack import CUSTOM_NORMAL_ATTACK_BY_PASSIVE
    nom = CUSTOM_NORMAL_ATTACK_BY_PASSIVE["Boltstorm"]
    assert nom == ActiveAbilityType.Boltstorm_NormalAttack.name
    assert int(ActiveAbilityType[nom]) == _NORMAL


@pytest.mark.parametrize("melee", [True, False])
def test_le_fold_est_une_feuille_NUE_et_le_cleave_ne_l_est_pas(melee):
    """#925 -- LE DRAPEAU, lu sur les arbres REELLEMENT construits (pas sur la constante).

    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
    monte UN SEUL `IdunBattleLogic.Entities.DSLBehaviors$$Attack` autour de `coups d'ARME & FOLD &
    ExecuteAdditionalHitsWithDamageProfileType` : le FOLD n'ouvre donc AUCUNE attaque, donc ne pousse
    pas `StartAttack`, donc n'emet pas `On(PreAttack = 5)`.

    Le CLEAVE, lui, passe par `$$GetAdditionalTargetsAttackBehavior`, qui appelle
    `IdunBattleLogic.Entities.DSLBehaviors$$Attack` autour de la MEME feuille -> il l'emet, par
    cible additionnelle.

    Le parametre `melee` balaie les deux natures d'arme : le drapeau ne doit PAS en dependre."""
    e = AT.NORMAL_ATTACK_CLEAVES["Boltstorm"]
    fold = AT.primary_fold_tree(e, is_melee=melee)
    assert fold.is_outside_attack is False, (
        "le FOLD primaire ouvre une attaque cote port : il emettrait un `On(PreAttack = 5)` que le "
        "natif n'emet pas (mesure #925 : 4 emissions contre 3)")
    grp = AT.cleave_tree(e, is_melee=melee, weapon_range=2)
    assert isinstance(grp, AtomicGroup) and isinstance(grp.child, Foreach)
    assert grp.child.body.is_outside_attack is True, (
        "le CLEAVE n'ouvre PAS d'attaque cote port : chaque cible additionnelle est pourtant "
        "enveloppee dans son propre `DSLBehaviors$$Attack` par "
        "`$$GetAdditionalTargetsAttackBehavior`")


def test_le_point_de_mutation_rend_le_natif():
    """`fold_emits_pre_attack` est le point de MUTATION des contre-epreuves (meme role que
    `fold_inherits_attack_state` pour #419-r3). Sa valeur PAR DEFAUT doit etre celle du NATIF --
    une contre-epreuve laissee armee inverserait silencieusement le port."""
    assert AT.fold_emits_pre_attack() is False
