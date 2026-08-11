"""CLIQUET 1210 `ExemplarOfTheMontka` (volet OFFLINE) -- registre, STRUCTURE de l'arbre, effet 1498.

`tauFarsight` << Commander Farsight >>. Ce volet garde ce qui se verifie SANS runner ; le volet
LIVE (`test_1210_exemplar_of_the_montka_live.py`) garde la MESURE (accord port/natif sur les
cibles buffees et sur le trait pose).

Ce que ce fichier fige, et pourquoi chaque cran existe :

  * l'ability est au registre AVEC ses deux donnees obligatoires (`TARGETING_OPTIONS` = 0x8004,
    `ABILITY_ATTACK_TYPE` = `Others`) et hors de `TARGETING_OPTIONS_UNPORTED` (contrat de
    DISJONCTION -- une ability a UNE source de masque, jamais deux) ;
  * **le CASTER entre par le FILTRE, pas par une exception** : l'arbre ne porte NI `op_Subtraction`
    NI `op_Addition`, contrairement au jumeau de forme `WarHowl` (1106). C'est la difference qu'un
    port recopie-du-voisin effacerait, et elle est OBSERVABLE (un porteur sans `Hero` ou sans arme
    `Range >= 2` ne se bufferait PAS) ;
  * le `selectionType = 3` du natif est REELLEMENT cable sur les DEUX noeuds qui l'acceptent.
    Garde STRUCTURELLE par NECESSITE : en live, seul un montage ou une unite porte
    `UnitFlag.Untargetable` (deep strike) l'exerce ;
  * l'effet 1498 DECLARE son trait (`AddTrait(0x412 = Unstoppable, isTemporary: 1)`) -- sans quoi
    le canal de pose est un no-op SILENCIEUX ;
  * **l'absence de gate de nature de coup** sur `CreateEffectDamageBonusForAttack` : melee ET
    distance recoivent le bonus. C'est l'ecart de fond avec 1222 (`IsMeleeAttack`), et l'ecrire
    comme un cran est ce qui empeche de le "corriger" par imitation ;
  * l'ORDRE des deux branches du `If(HasTrait(Target, BigTarget), extraDmg_2, extraDmg)` -- les
    inverser est value-preserving en STRUCTURE et FAUX en VALEUR ;
  * la face DECISION : le playbook NonComparable est au registre avec son `MIN_UTILITY`.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre ETROIT et DERIVE : les fichiers dont un changement peut RENDRE FAUX ce que ce cliquet
#: fige. Pas de glob `scripts/python/**` (ce serait un `toujours: True` deguise).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/tau.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/loki/exemplar_of_the_montka.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/playbook/noncomparable/__init__.py",
        "scripts/python/engine/playbook/noncomparable/exemplar_of_the_montka.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Perimetre ETROIT : ce volet ne lit ni le binaire ni les tables du build -- il fige "
              "des valeurs du PORT (masque de ciblage, AbilityAttackType, declaration de trait, "
              "structure du selecteur, cablage du selectionType, registre de playbook). Le seul "
              "axe qui les perime est une edition de ces fichiers-la. `build: False` parce "
              "qu'aucune grandeur ici n'est derivee d'une adresse ou d'un dump : les litteraux "
              "natifs sont RECOPIES dans le port, et c'est le port que ce cliquet garde.",
}

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.selectors.units import (Friends, UnitsWithRangedWeapons, UnitsWithTrait)
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.tau import (ExemplarOfTheMontkaAbility,
                                         exemplar_of_the_montka_buff_targets,
                                         exemplar_of_the_montka_tree)
from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
from engine.runner.abilities.targeting_rule import TargetingRule as TR

_MONTKA = int(ActiveAbilityType.ExemplarOfTheMontka)          # 0x4ba = 1210
_MONTKA_EFFECT = int(EffectType.ExemplarOfTheMontka)          # 0x5da = 1498


def _effect(level: int = 50):
    from engine.entities.effects.factory import EFFECT_CLASSES
    klass = EFFECT_CLASSES.get("ExemplarOfTheMontka")
    assert klass is not None, "1498 absent d'EFFECT_CLASSES -- le canal degat est un no-op muet"
    eff = klass(effect_type=_MONTKA_EFFECT, name="ExemplarOfTheMontka")
    eff.active_ability_level = level
    return eff


def test_registre_1210():
    """`ExemplarOfTheMontkaAbility` est au registre avec ses DEUX donnees obligatoires, et son
    masque n'est declare qu'UNE fois (`probe_181` verifie qu'un masque EXISTE, jamais qu'il est
    unique -- c'est ce cran-la qui a rendu `master` rouge trois commits durant sur une autre
    ability)."""
    assert ABILITY_CLASSES.get(_MONTKA) is ExemplarOfTheMontkaAbility
    assert _MONTKA not in {int(k) for k in TARGETING_OPTIONS_UNPORTED}
    opts = ExemplarOfTheMontkaAbility.TARGETING_OPTIONS
    assert opts is not None
    # STATIC-COPY du preset `<TargetingOptions statics>+0x280` : `rules` = `<preset>+0x28` = 0x8004,
    # SANS les `additionalRules = 0x10` de 1216/1192 -> PAS de `CasterHasNotMoved`.
    assert int(opts.rules) == (int(TR.CasterMatchesDynamicRule)
                               | int(TR.CasterIsPossibleTarget)) == 0x8004
    assert int(opts.rules) & int(TR.CasterHasNotMoved) == 0
    assert bool(opts.self_cast) is True                       # `<preset>+0x00` = 1
    assert opts.range is not None and int(opts.range.override_range) == 0   # RANGE_SELF
    # 3e argument d'`AActiveAbility..ctor` = litteral `2` = `Others`. TRANSCRIT, pas deduit du fait
    # que le cast ne frappe personne (sur cet axe, `WallOfMirrors` et `StormOfWrath` se contredisent).
    assert ABILITY_ATTACK_TYPE.get(_MONTKA) == AbilityAttackType.Others


def test_le_caster_entre_par_le_filtre_pas_par_une_exception():
    """LE cran qui separe 1210 de son jumeau de forme 1106.

    1106 fait `op_Addition(Owner, UnitsWithoutTrait(UnitsWithoutRangedWeapons(Friends(of=Owner,
    entities = AllAliveUnits - Owner))))` : le caster est buffe QUOI QU'IL ARRIVE.
    1210 fait `UnitsWithRangedWeapons(UnitsWithTrait(Friends(of=Caster, entities=AllAliveUnits)))` :
    NI soustraction NI addition -- le caster n'est buffe que parce qu'il passe les DEUX filtres.

    Recopier la forme du voisin aurait produit un `Union(...)` : structurellement plausible,
    OBSERVABLEMENT faux des qu'un porteur perd `Hero` ou son arme distante."""
    sel = exemplar_of_the_montka_buff_targets()
    assert isinstance(sel, UnitsWithRangedWeapons)
    with_trait = sel.source
    assert isinstance(with_trait, UnitsWithTrait)
    friends = with_trait.source
    assert isinstance(friends, Friends)
    # Le pool passe a `Friends` est le champ PARTAGE `<DSLSelectors+0x20>` = `AllAliveUnits`, NU :
    # aucun `Sub`/`op_Subtraction` ne l'enveloppe.
    from engine.entities.selectors.tiles import AllAliveUnits
    assert isinstance(friends.inner, AllAliveUnits)


def test_selection_type_est_dans_l_arbre():
    """Le `selectionType = 3` que le natif passe a `Friends` ET a `UnitsWithTrait` est cable.
    `UnitsWithRangedWeapons`, lui, n'en prend PAS cote natif (son `Select` code en dur
    `SelectUniqueUnits(..., 1 = OnlyAlive)`) -- lui en passer un serait une invention."""
    sel = exemplar_of_the_montka_buff_targets()
    with_trait = sel.source
    assert int(with_trait.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)
    assert int(with_trait.trait) == int(UnitTrait.Hero) == 0x10
    friends = with_trait.source
    assert int(friends.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)
    assert not hasattr(sel, "selection_type")


def test_les_deux_filtres_mordent_sur_un_contexte_synthetique():
    """LE cran qui rend MORDANTS les mutants `retirer UnitsWithTrait(Hero)` et `retirer
    UnitsWithRangedWeapons` -- et il est OFFLINE **par necessite mesuree**, pas par confort.

    Le bras live (`probe_1210_exemplar_of_the_montka.py`) exerce le filtre RANGED (`tauAunShi`,
    Hero a arme melee seule, n'est PAS buffe : mesure 2026-08-11, runner MC1_67/777) mais PAS le
    filtre `Hero` : balayage du pool, **0** unite `lineup` des 97 spawnables n'est non-Hero, et
    les 8 MoW n'ont AUCUNE arme au gameconfig (elles echouent au filtre RANGED, donc ne
    discriminent pas le HERO). Le seul porteur naturel est un SUMMON (`tauSmnDroneSniper` :
    Summon/Flying/Mechanical/RangedSpecialist, `Piercing` R4) et son montage n'a pas abouti
    (l'ability du summoner rend `mutated: False` sur ce board) -- residu NOMME dans la fiche.

    Ce test evalue donc l'arbre REEL sur un contexte SYNTHETIQUE ou les quatre combinaisons
    existent. Un contexte fabrique n'est pas un oracle du NATIF -- mais l'arbre, lui, est le vrai,
    et c'est exactement ce que les deux mutants cassent."""
    from engine.dsl.base import DslContext
    # `hp` est REQUIS : `selection_ok_from_ctx` derive `IsAlive` du couple `alive`/`hp`, et le
    # `selectionType = 3` des deux noeuds ecarte sinon TOUT le monde -- un `[]` qui se lirait
    # comme << le filtre marche >> alors qu'il n'aurait rien filtre du tout.
    caster = {"id": 1, "team": 0, "visualId": "hero_ranged", "alive": True, "hp": 100}
    units = [caster,
             {"id": 2, "team": 0, "visualId": "hero_melee", "alive": True, "hp": 100},
             {"id": 3, "team": 0, "visualId": "drone_ranged", "alive": True, "hp": 100},  # non-Hero
             {"id": 4, "team": 1, "visualId": "foe_hero_ranged", "alive": True, "hp": 100}]  # ENNEMI
    heroes = {1, 2, 4}
    ranged = {1, 3, 4}
    ctx = DslContext(units=units, caster=caster)
    ctx.has_trait = lambda u, t: int(t) == int(UnitTrait.Hero) and u.get("id") in heroes
    ctx.has_ranged_weapon = lambda u: u.get("id") in ranged
    got = sorted(int(u["id"]) for u in exemplar_of_the_montka_buff_targets().evaluate(ctx))
    # 1 = Hero + ranged (le CASTER, entre par le FILTRE) ; 2 tombe sur le filtre RANGED ;
    # 3 tombe sur le filtre HERO ; 4 tombe sur `Friends`.
    assert got == [1], got


def test_arbre_une_seule_feuille_addeffect():
    """`Execute(AddEffect(1498, get_AbilityStateReference, source=Caster@+0x48, targets, turns))`.

    `turns` = `<DSLFormulas+0x20>`, le champ que `DSLFormulas$$.ctor` initialise a la constante
    **1** (`+0x18 <- 0`, `+0x20 <- 1`, `+0x28 <- 2`, `+0x30 <- 100`, `+0x38 <- -1`). Il arrive tel
    quel dans `AddEffectOperation$$Execute`, qui ne le convertit pas -> 1 TOUR, pas 1 round."""
    tree = exemplar_of_the_montka_tree()
    assert tree.effect_type == _MONTKA_EFFECT
    assert tree.duration_turns == 1
    assert tree.duration_rounds in (1, None)      # court-circuite par `duration_turns`
    # `AbilityStateReference` = l'etat d'ability du CASTER : les DEUX variables du kit sont dans
    # `variablesAffectedByRarityBonus`, donc lire le scaling sur le BUFFE serait un ecart NUMERIQUE
    # et SILENCIEUX (mesure #585 : multiplicateurs 200 contre 180).
    assert tree.scale_from_source is True
    assert tree.source_ref is not None            # 4e argument natif `<DSLSelectors+0x48>`
    assert tree.source_from_target is False       # la surcharge 6-args passe une source EXPLICITE


def test_effet_1498_declare_son_trait():
    """La part TRAIT d'`ApplyInternal`/`RevertInternal` est DATA sur la classe d'effet :
    `AddTrait(0x412 = UnitTrait.Unstoppable, isTemporary: 1)`."""
    assert _effect().applied_traits() == [(UnitTrait.Unstoppable, True)]


def test_bonus_degat_sans_gate_de_nature():
    """`ForAddition(get_OwnerIsCaster & IsNormalAttack, If(...))` -- DEUX noeuds, et AUCUN
    `IsMeleeAttack`/`IsRangedAttack`. C'est l'ecart de fond avec 1222, dont le trigger porte
    `IsMeleeAttack` : ajouter ce gate ici par imitation SUPPRIMERAIT le buff sur les attaques
    distantes, que l'i2 accorde explicitement (« all their normal attacks »)."""
    eff = _effect()
    melee = eff.create_effect_damage_bonus_for_attack(is_ranged=False)
    ranged = eff.create_effect_damage_bonus_for_attack(is_ranged=True)
    unknown = eff.create_effect_damage_bonus_for_attack(is_ranged=None)
    assert melee is not None and ranged is not None and unknown is not None
    assert melee.kind == "Addition"                # `EffectBonus$$ForAddition`
    assert melee.value == ranged.value == unknown.value
    # `IsNormalAttack`, lui, EST un noeud du trigger.
    assert eff.create_effect_damage_bonus_for_attack(is_normal_attack=False) is None


def test_if_big_target_ordre_des_branches():
    """`If(HasTrait(Target@+0x60, 0x3f9 = BigTarget), ConfigVar(0x09 = extraDmg_2),
    ConfigVar(0x08 = extraDmg))` -- l'ORDRE est LU (le `ifAmount` de `DSLFormulas$$If` recoit
    `ConfigVar(9)`), et l'inverser est value-preserving en structure, FAUX en valeur.

    Les deux magnitudes sont figees au niveau 50 (`extraDmg[49] = 333`, `extraDmg_2[49] = 721`,
    mesure sur le kit gameconfig) : c'est ce qui garde l'appariement cle -> variable, qu'un
    renommage de cle rendrait muet."""
    eff = _effect(level=50)
    big = eff.create_effect_damage_bonus_for_attack(target_traits=frozenset({UnitTrait.BigTarget.name}))
    small = eff.create_effect_damage_bonus_for_attack(target_traits=frozenset())
    assert big.value == 721 and small.value == 333
    assert big.value > small.value
    # `target_traits is None` = cible NON MESUREE -> branche `else`, degradation MINIMALE : le
    # natif accorde TOUJOURS une contribution (son `If` a deux branches non nulles), donc rendre
    # `None` la supprimerait ; accorder `extraDmg_2` l'inventerait.
    assert eff.create_effect_damage_bonus_for_attack(target_traits=None).value == 333


def test_playbook_1210_au_registre():
    """Face DECISION : `...ExemplarOfTheMontkaPlaybook` est un **NonComparable** (base LUE par la
    methode surchargee `EvaluateNonComparable`, JAMAIS par le nom du `.ctor`, que Ghidra rend
    `ComparablePlaybook<...>$$.ctor` -- corps trivial DEDUPLIQUE, meme piege que #487-r1).

    `MIN_UTILITY` = l'utilite CONSTANTE = `Fix64(1)` du `.cctor`."""
    from engine.playbook.noncomparable import is_noncomp, playbook_for
    pb = playbook_for(_MONTKA)
    assert pb is not None and is_noncomp(_MONTKA)
    assert pb.ABILITY_ID == _MONTKA
    assert pb.MIN_UTILITY == 1.0
    assert pb.PRIORITY == 0                       # hors `NATIVE_PRIORITY` (sweep #170)


def test_playbook_gate_ne_refuse_pas_a_l_aveugle():
    """`ShouldEvaluate = HasNormalAttackTarget` -- et la NON-MESURE ne doit jamais fabriquer un
    refus : sans RPC `abilityTargets`, le port rend `True` (comportement d'avant ce module, ou
    1210 n'avait aucune entree NonComparable). Un `False` invente RETIRERAIT un cast que le natif
    fait."""
    from engine.playbook.noncomparable import playbook_for
    from engine.playbook.noncomparable._base import NCContext
    pb = playbook_for(_MONTKA)
    ctx = NCContext(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                    hp_cur_by_id={}, ability_targets=None)
    assert pb.should_evaluate(ctx) is True
    assert pb.generate_candidates(ctx) == []
    # RPC PRESENT mais l'unite n'a AUCUNE attaque normale -> la boucle native est vide -> False.
    # C'est une MESURE, pas une non-mesure : le gate refuse.
    ctx2 = NCContext(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                     hp_cur_by_id={}, ability_targets=lambda *_a, **_k: {},
                     units=[{"id": 1, "abilities": []}])
    assert pb.should_evaluate(ctx2) is False
