"""CLIQUET #585 (volet OFFLINE) -- le REGISTRE de `WarHowl` (1106) et la STRUCTURE de son arbre.

Volet jumeau de `test_war_howl_pose_live.py`, qui garde la MESURE (accord port/natif sur les
cibles, et la face PORT du trait). Celui-ci garde ce qui se verifie SANS runner :

  * l'ability est au registre AVEC ses deux donnees obligatoires (`TARGETING_OPTIONS` = 0x8014,
    `ABILITY_ATTACK_TYPE` = `Others`) et SORTIE de `TARGETING_OPTIONS_UNPORTED` (contrat de
    DISJONCTION -- c'est ce cran-la qui a rendu `master` rouge trois commits durant sur une autre
    ability, cf. `test_targeting_options_sources`) ;
  * l'effet 1222 DECLARE son trait (`AddTrait(0x412 = Unstoppable, isTemporary: 1)`) -- sans quoi
    le canal de pose est un no-op SILENCIEUX ;
  * le `selectionType = 3` du natif est REELLEMENT cable dans l'arbre. Cette derniere garde est
    STRUCTURELLE **par necessite** : en live, seul un montage ou une unite porte
    `UnitFlag.Untargetable` (deep strike) l'exerce -- un board sans deep strike rendrait le bras
    live muet sans que rien ne proteste.

⚠ CE FICHIER EST OFFLINE ET IL EST NOMME COMME TEL. Trois tests offline heberges dans un
`*_live.py` sont invisibles des DEUX gardes de selection (`probe_457` / `probe_486r15`), qui
excluent les `_live.py` par choix -- le probe 547 le dit dans sa section de portee.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre ETROIT et DERIVE : les fichiers dont un changement peut RENDRE FAUX ce que ce cliquet
#: fige. Pas de glob `scripts/python/**` (ce serait un `toujours: True` deguise).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/spacewolves.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/loki/war_howl.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Perimetre ETROIT : ce volet ne lit ni le binaire ni les tables du build -- il fige "
              "des valeurs du PORT (masque de ciblage, AbilityAttackType, declaration de trait, "
              "cablage du selectionType). Le seul axe qui les perime est une edition de ces "
              "fichiers-la. `build: False` parce qu'aucune grandeur ici n'est derivee d'une "
              "adresse ou d'un dump : les litteraux natifs sont RECOPIES dans le port, et c'est "
              "le port que ce cliquet garde.",
}

from engine.entities.effect_type import EffectType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.spacewolves import WarHowlAbility, war_howl_buff_targets
from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
from engine.runner.abilities.targeting_rule import TargetingRule as TR

_WAR_HOWL = 1106


def test_registre_1106():
    """`WarHowlAbility` est au registre avec ses deux donnees obligatoires, et son masque n'est
    declare qu'UNE fois (`probe_181` verifie qu'un masque EXISTE, jamais qu'il est unique)."""
    assert ABILITY_CLASSES.get(_WAR_HOWL) is WarHowlAbility
    assert _WAR_HOWL not in {int(k) for k in TARGETING_OPTIONS_UNPORTED}
    opts = WarHowlAbility.TARGETING_OPTIONS
    assert opts is not None
    # `.ctor` : preset `<TargetingOptions statics>+0x280` (`rules = 0x8004`) puis
    # `.ctor(&opts, &preset, 0x10)` -> `rules = additionalRules | template.rules` = 0x8014.
    assert int(opts.rules) == (int(TR.CasterMatchesDynamicRule) | int(TR.CasterHasNotMoved)
                               | int(TR.CasterIsPossibleTarget)) == 0x8014
    assert bool(opts.self_cast) is True
    # 3e argument d'`AActiveAbility..ctor` = litteral `2` = `Others`. TRANSCRIT, pas deduit du
    # comportement -- le lot voisin porte les deux contre-exemples (1121 / 1038).
    assert ABILITY_ATTACK_TYPE.get(_WAR_HOWL) == AbilityAttackType.Others


def test_effet_1222_declare_son_trait():
    """La part TRAIT d'`ApplyInternal` est DATA sur la classe d'effet :
    `AddTrait(0x412 = UnitTrait.Unstoppable, isTemporary: 1)`. Mutation M3 de la fiche."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    klass = EFFECT_CLASSES.get("WarHowl_ExtraDamage_Unstoppable")
    assert klass is not None
    eff = klass(effect_type=int(EffectType.WarHowl_ExtraDamage_Unstoppable),
                name="WarHowl_ExtraDamage_Unstoppable")
    assert eff.applied_traits() == [(UnitTrait.Unstoppable, True)]


def test_selection_type_est_dans_l_arbre():
    """Le `selectionType = 3` que le natif passe a `Friends` ET a `UnitsWithoutTrait` est cable.
    Mutation M1 de la fiche (`-> Any` : le port sur-buffe une unite en deep strike)."""
    sel = war_howl_buff_targets()
    # `Union(Owner(), UnitsWithoutTrait(UnitsWithoutRangedWeapons(Friends(...)), Summon, 3))`
    without_trait = sel.b                       # `op_Addition` : operande DROITE
    assert int(without_trait.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)
    friends = without_trait.source.source       # -> UnitsWithoutRangedWeapons -> Friends
    assert int(friends.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)
