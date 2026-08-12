"""#951 -- garde OFFLINE des deux passifs de la tranche.

`TrophyTaker` (`worldExecutions` << Tarvakh >>) est un PORT NEUF ; `FireOfAbsolution`
(`adeptRetributor` << Vindicta >>) etait DEJA porte -- ce fichier garde donc, pour le premier, ce
que le decompile dit, et pour le second les TROIS ecarts que l'audit de cette tranche a trouves.

Chaque etage cite le symbole natif dont il garde la lecture. Le dernier etage porte les
CONTRE-EPREUVES PAR MUTATION : chaque garde y est re-jouee contre une version FAUSSE du port, et
doit ROUGIR. Un garde qui reste vert sous mutation est inerte -- il ne mesure rien.
"""
from __future__ import annotations

import pytest

import gameconfig as GC

from engine.dsl.base import Const
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki import trophy_taker as TT
from engine.entities.formulas import Count, Multiply
from engine.entities.selectors.units import NormalUnits, UnitsDefeatedBy
from engine.entities.stats import StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki import fire as FIRE
from engine.runner.operations.triggers.loki import trophy_taker as TTT


DECLENCHEUR = {
    "chemins": (
        # Le port de `TrophyTaker` -- ses deux faces et leur cablage.
        "scripts/python/engine/entities/effects/loki/trophy_taker.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/loki/trophy_taker.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # L'etage natif que la tranche a ajoute (registre des victimes + selecteur qui le lit) et
        # les deux foyers d'ou il est ecrit/lu.
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/__init__.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        # Les mirrors d'enum et les foyers de magnitude/arrondi que les gardes citent.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/dsl/base.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/services/effect_bonus.py",
        "scripts/python/engine/entities/stats.py",
        # Le second item de la tranche : les trois ecarts corriges sur `FireOfAbsolution`.
        "scripts/python/engine/runner/operations/triggers/loki/fire.py",
        "scripts/python/engine/runner/operations/triggers/loki/__init__.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        # Les entrees LUES : le gameconfig (magnitudes, `variablesAffectedByRarityBonus`) et la
        # table de symboles (l'etage qui verifie que `FireOfAbsolutionAbility$$CreateTrigger` a un
        # corps PROPRE, donc que la prose corrigee dit vrai).
        "scripts/python/gameconfig.py",
        # (`data/symbols/**` -- dont `CURRENT` et `frida/methods.tsv` -- est ajoute par
        #  `declencheur_cliquet` DU FAIT de `build: True` ci-dessous. Le hash ECRIT ici figeait le
        #  perimetre au build du jour : au suivant, le garde serait devenu muet. cf. #431 / #962)
    ),
    "build": True,
    "toujours": False,
    "raison": "Test OFFLINE : il n'ouvre aucun runner. Son perimetre est la chaine du passif "
              "`TrophyTaker` (effet 1289, trigger du stat-mod 1288, selecteur `UnitsDefeatedBy` et "
              "le registre de victimes qui l'alimente), plus les trois ecarts corriges sur "
              "`FireOfAbsolution`. Il LIT le gameconfig et la table de symboles du build : les deux "
              "sont donc dans le declencheur, faute de quoi un changement de build laisserait le "
              "garde muet.",
}


class _Ctx:
    """`AbilityEntities` minimal pour executer un SELECTEUR hors runner : `units` (l'univers) et
    `caster` (le slot `Owner@DSLSelectors+0x30` d'un `BaseTriggeredAbility`, owner == caster)."""

    def __init__(self, units, caster=None, has_trait=None):
        self.units = units
        self.caster = caster
        self.target = None
        self.actor = None
        self.board = None
        self.has_trait = has_trait
        self.caster_pos = None
        self.subject = None
        self.has_unit_flag = None


def _effet(niveau):
    """L'effet 1289 monte au niveau d'ability `niveau` -- `None` = pas d'`AbilityState`, ce qui
    rend le `ConfigVar` natif INERTE (et non nul)."""
    e = TT.TrophyTakerExtraCritDamageEffect(name="TrophyTaker_ExtraCritDamage")
    e.ability_level = niveau
    return e


def _u(uid, defeated=(), traits=()):
    return {"id": uid, "team": 0, "player": 0, "pos": {"col": uid, "row": 0}, "alive": True,
            "hp": 10, "hpMax": 10, "visualId": None, "feet": [(uid, 0)],
            "defeatedUnits": list(defeated), "_traits": set(traits)}


# ==================================================================================================
# [1] REGISTRES -- le canal de port, qui decide si le passif se pose UN JOUR
# ==================================================================================================

def test_registre_effet_trophy_taker():
    """`TrophyTaker_ExtraCritDamage` (0x509) est la SEULE classe d'effet du passif : le 0x508 est un
    stat-modifier pose par la factory `AddOrUpdateStaticStatModifierEffect`, sans comportement
    propre -- il n'a AUCUNE classe native (`methodPointers` : rien sous ce nom)."""
    assert EFFECT_CLASSES["TrophyTaker_ExtraCritDamage"] is TT.TrophyTakerExtraCritDamageEffect
    assert "TrophyTaker_ExtraCritChance" not in EFFECT_CLASSES


def test_registre_trigger_trophy_taker():
    """`...TrophyTakerAbility$$CreateTrigger` = `<DSLTriggers+0x30> | (On(UnitDefeated) &
    get_OwnerIsActor)`. SEUL le second bras entre dans `ABILITY_TRIGGERS` -- le premier
    (`On(AbilityInit) & <+0x70> & OwnerIsActor`) pose l'effet 1289, canal servi par
    `decisionView.effects`."""
    assert ABILITY_TRIGGERS["TrophyTaker"] == [TTT.TrophyTakerOnUnitDefeatedAbility]
    assert int(TTT.TrophyTakerOnUnitDefeatedAbility.event_id) == int(EventTriggerType.UnitDefeated)
    assert int(EventTriggerType.UnitDefeated) == 0x36 == 54


def test_pas_dentree_de_seed_pour_trophy_taker():
    """L'effet 1289 n'a NI `CreateActiveCondition` NI `ApplyInternal` -> il est ACTIF des sa pose,
    donc present dans `decisionView.effects`. L'inscrire en `ABILITY_INIT_OWNER_EFFECTS` le
    materialiserait UNE SECONDE FOIS."""
    assert "TrophyTaker" not in ABILITY_INIT_OWNER_EFFECTS


def test_litteraux_denum_figes_au_site():
    """Les ordinaux ECRITS AUX SITES, figes a la conversion. `probe_313` garde le MIRROR contre le
    build ; ce test garde le fait que le SITE designe bien CE membre-la -- il redeviendrait vert
    apres un renumerotage si on ne le figeait pas ici."""
    assert int(EffectType.TrophyTaker_ExtraCritChance) == 0x508 == 1288
    assert int(EffectType.TrophyTaker_ExtraCritDamage) == 0x509 == 1289
    # le `TriggeredAbilityType` que `TrophyTaker_ExtraCritDamageEffect$$.ctor` passe a
    # `AbilityOrEffect$$op_Implicit` -- LU AUX OCTETS (`mov edx, 0x4cd`), et qualifie par la
    # signature de la surcharge (`triggeredAbility:TriggeredAbilityType`), pas par l'ordinal.
    assert int(TriggeredAbilityType.TrophyTaker) == 0x4cd == 1229
    assert int(AbilityVariableType.extraDmg) == 0x8
    assert int(AbilityVariableType.extraCritChance) == 0x41
    assert int(AbilityVariableType.extraCritDmg) == 0x42
    assert int(AbilityConstantType.hpPct) == 0x12
    assert int(AbilityConstantType.chance) == 0x2a
    assert int(AbilityConstantType.nrOfHits) == 0x2f
    assert int(StatType.CRIT_CHANCE) == 9        # `AddOrUpdateStaticStatModifierEffect(statType: 9)`
    assert int(UnitTrait.Object) == 0xd          # les deux traits d'`UnitExtensions$$IsNormalUnit`
    assert int(UnitTrait.Steppable) == 0x1b


# ==================================================================================================
# [2] `HealthLowerThanPct` -- le gate STRICT, et son arrondi
# ==================================================================================================

def test_health_current_pct_est_un_arrondi_demi_vers_le_pair():
    """`FillUpStatComponent$$GetStatPart` case 1 = `Round(Max(0, current/maximum) * 100, mode 0)`.
    Mode 0 = `AAmountFormula$$RoundFix64Result` demi-vers-le-PAIR, PAS une troncature -- et les
    deux divergent sur les demis, qui sont exactement les cas ou le seuil bascule."""
    assert TT.health_current_pct(50, 100) == 50
    assert TT.health_current_pct(1, 3) == 33               # 33.33 -> 33
    assert TT.health_current_pct(2, 3) == 67               # 66.67 -> 67 (une troncature rendrait 66)
    assert TT.health_current_pct(1, 8) == 12               # 12.5 -> 12 (demi vers le PAIR)
    assert TT.health_current_pct(3, 8) == 38               # 37.5 -> 38 (demi vers le PAIR)
    assert TT.health_current_pct(-5, 100) == 0             # `Fix64.Max(0, .)`


def test_health_current_pct_tri_etat():
    """`None` = PAS MESURE. Un `0` invente ferait passer pour << mourante >> une cible dont on
    ignore la vie -- le gate deviendrait PERMISSIF, exactement l'inverse de la doctrine."""
    assert TT.health_current_pct(None, 100) is None
    assert TT.health_current_pct(50, None) is None
    assert TT.health_current_pct(50, 0) is None            # le natif y diviserait par zero


def test_gate_hp_est_strict():
    """`NOT AmountIsEqualOrGreater(pct, hpPct)` == `pct < hpPct`. Le mislabel guette : la classe
    voisine `AmountIsGreater` aurait donne `pct <= hpPct`, donc le bonus sur une cible a EXACTEMENT
    50 % -- le cas le plus frequent d'une cible entamee de moitie."""
    seuil = int(GC.ability("TrophyTaker")["constants"]["hpPct"])
    assert seuil == 50
    ok = {"tgt_hp": 49, "tgt_hp_max": 100, "owner_id": 7, "att_id": 7}
    pile = {"tgt_hp": 50, "tgt_hp_max": 100, "owner_id": 7, "att_id": 7}
    assert TT.health_lower_than_pct(ok) is True
    assert TT.health_lower_than_pct(pile) is False
    assert TT.health_lower_than_pct({}) is False           # mesure absente -> le gate se TAIT


def test_le_gate_est_le_meme_corps_pour_les_deux_canaux():
    """`CreateEffectDamageBonusForAttack` et `CreateCritDamageBonus` appellent le MEME
    `HealthLowerThanPct` natif (meme `call`, meme adresse). Les deux faces du port ne peuvent donc
    pas diverger sur le seuil -- et si le canal CRIT n'avait pas ses cles, la divergence serait
    SILENCIEUSE. Ce test la rendrait visible."""
    e = _effet(50)
    dur = {"tgt_hp": 20, "tgt_hp_max": 100, "owner_id": 7, "att_id": 7}
    assert e.create_effect_damage_bonus_for_attack(att_ctx=dur) is not None
    assert e.create_effect_crit_damage_bonus_for_attack(att_ctx=dur) is not None
    sain = {"tgt_hp": 90, "tgt_hp_max": 100, "owner_id": 7, "att_id": 7}
    assert e.create_effect_damage_bonus_for_attack(att_ctx=sain) is None
    assert e.create_effect_crit_damage_bonus_for_attack(att_ctx=sain) is None


def test_owner_is_caster_nest_exige_que_du_canal_board_wide():
    """Le canal DEGAT (`_attacker_effect_bonuses`) ne recoit QUE les effets de l'attaquant et ne
    thread PAS `owner_id` ; le canal CRIT balaie le BOARD et le thread par porteur. Exiger
    `get_OwnerIsCaster` des deux cotes effacerait le bonus de DEGAT en silence."""
    e = _effet(50)
    sans_owner = {"tgt_hp": 20, "tgt_hp_max": 100}          # ce que thread le canal DEGAT
    assert e.create_effect_damage_bonus_for_attack(att_ctx=sans_owner) is not None
    assert e.create_effect_crit_damage_bonus_for_attack(att_ctx=sans_owner) is None
    autrui = {"tgt_hp": 20, "tgt_hp_max": 100, "owner_id": 7, "att_id": 8}
    assert e.create_effect_crit_damage_bonus_for_attack(att_ctx=autrui) is None


def test_magnitudes_et_rarete():
    """`variablesAffectedByRarityBonus == ["extraDmg", "extraCritDmg"]` -- `extraCritChance` n'y est
    PAS. Ce fait ne se lit QUE dans le gameconfig, et il est ASYMETRIQUE entre les trois variables
    du meme passif."""
    cfg = GC.ability("TrophyTaker")
    assert set(cfg["variablesAffectedByRarityBonus"]) == {"extraDmg", "extraCritDmg"}
    assert set(cfg["variables"]) == {"extraCritChance", "extraDmg", "extraCritDmg"}
    e = _effet(1)
    dur = {"tgt_hp": 1, "tgt_hp_max": 100, "owner_id": 7, "att_id": 7}
    b = e.create_effect_damage_bonus_for_attack(att_ctx=dur)
    assert b is not None and b.kind == "Addition" and b.value == cfg["variables"]["extraDmg"][0]
    assert e.create_effect_crit_damage_bonus_for_attack(att_ctx=dur) == \
        cfg["variables"]["extraCritDmg"][0]


def test_sans_ability_level_les_deux_canaux_se_taisent():
    """`ConfigVar` sans `AbilityState` = noeud INERTE cote natif. Rendre `0` serait un `EffectBonus`
    nul de plus dans la somme -- pas faux arithmetiquement, mais il masquerait l'absence."""
    e = _effet(None)
    dur = {"tgt_hp": 1, "tgt_hp_max": 100, "owner_id": 7, "att_id": 7}
    assert e.create_effect_damage_bonus_for_attack(att_ctx=dur) is None
    assert e.create_effect_crit_damage_bonus_for_attack(att_ctx=dur) is None


# ==================================================================================================
# [3] `UnitsDefeatedBy` + `NormalUnits` -- l'etage natif qui MANQUAIT au port
# ==================================================================================================

def test_units_defeated_by_prend_l_union_et_dedoublonne():
    """`UnitsDefeatedBySelector$$Select` appelle `AddUnits` sur les DEUX listes (@+0xa8 melee,
    @+0xb0 le reste) et accumule dans un `OrderedSet` -- union, ordre d'inscription, sans doublon.
    Un id qui ne resout pas en entite est IGNORE (`if (u != null)`), il ne devient pas un trou."""
    porteur = _u(1, defeated=[2, 3, 2, 99])                # 99 : id qui ne resout pas
    univers = [porteur, _u(2), _u(3)]
    ctx = _Ctx(univers, caster=porteur)
    from engine.entities.selectors.tiles import Caster as _C
    sel = UnitsDefeatedBy(_C())
    ids = [u["id"] for u in sel.evaluate(ctx)]
    assert ids == [2, 3]


def test_normal_units_exclut_object_et_steppable():
    """`UnitExtensions$$IsNormalUnit` = `!HasTrait(Object = 0xd) && !HasTrait(Steppable = 0x1b)`.
    C'est le SEUL filtre du compteur : ni camp, ni `Hero`, ni liveness."""
    porteur = _u(1, defeated=[2, 3, 4])
    univers = [porteur, _u(2), _u(3, traits=("Steppable",)), _u(4, traits=("Object",))]
    traits = {u["id"]: u["_traits"] for u in univers}
    ctx = _Ctx(univers, caster=porteur,
               has_trait=lambda u, t: UnitTrait(t).name in traits.get(u.get("id"), ()))
    from engine.entities.selectors.tiles import Caster as _C
    n = Count(NormalUnits(UnitsDefeatedBy(_C()), int(UnitSelectionType.Any))).evaluate(ctx)
    assert n == 1                                          # seul l'id 2 est une unite NORMALE


def test_l_arbre_du_multiplicateur_est_celui_du_decompile():
    """`...TrophyTakerAbility$$GetCritChanceMultiplier` = `Count(NormalUnits(UnitsDefeatedBy(
    Owner@+0x30), UnitSelectionType.Any = 0))` -- la STRUCTURE, pas seulement le resultat : c'est
    elle qui garantit que le filtre EMERGE du noeud `NormalUnits` au lieu d'etre recable a la main."""
    t = TTT.trophy_taker_crit_chance_multiplier_tree()
    assert isinstance(t, Count)
    assert isinstance(t.selector, NormalUnits)
    assert int(t.selector.selection_type) == int(UnitSelectionType.Any) == 0
    assert isinstance(t.selector.entities, UnitsDefeatedBy)


def test_le_multiplicateur_est_multiplie_pas_additionne():
    """`Multiply(ConfigVar(extraCritChance), GetCritChanceMultiplier())` -- et la factory
    `AddOrUpdateStaticStatModifierEffect` RE-ECRIT (`If(NOT AmountIsEqual(amount, CurrentStatModifier
    Amount(...)), RemoveEffect & AddStaticStatModifierEffect)`). Un port qui accumulerait
    `+= extraCritChance` a chaque mort rendrait `N(N+1)/2` au lieu de `N`."""
    arbre = TTT.trophy_taker_crit_chance_tree(8)
    trouve = []

    def _visite(n, prof=0):
        if prof > 12 or n is None:
            return
        if isinstance(n, Multiply):
            trouve.append(n)
        for a in ("a", "b", "child", "behaviour", "amount", "then", "otherwise", "cond",
                  "condition", "left", "right"):
            v = getattr(n, a, None)
            if v is not None and not isinstance(v, (int, str, bool)):
                _visite(v, prof + 1)

    _visite(arbre)
    assert trouve, "aucun `Multiply` dans l'arbre : la magnitude n'est pas un PRODUIT"
    m = trouve[0]
    assert isinstance(m.a, Const) and int(m.a.value) == 8
    assert isinstance(m.b, Count)


# ==================================================================================================
# [4] FireOfAbsolution -- les ecarts que l'audit de cette tranche a trouves
# ==================================================================================================

def test_chance_est_lue_du_gameconfig_pas_codee_en_dur():
    """`GetNumberConstant(AbilityConstantType.chance)`. Le port la figeait a `30`. Le test lit la
    MEME source que le port, donc il ne garde pas la valeur -- il garde le CANAL : si la config
    disparait, les deux tombent a 0 ensemble, et c'est le natif."""
    attendu = int(GC.ability("FireOfAbsolution")["constants"]["chance"])
    assert FIRE.fire_of_absolution_ignite_chance() == attendu
    assert not hasattr(FIRE, "FIRE_OF_ABSOLUTION_IGNITE_CHANCE"), \
        "la constante figee doit avoir DISPARU, sinon un lecteur peut encore la prendre"


def test_selection_type_de_l_adjacence_est_porte():
    """`AdjacentUnits(origin, unique: false, selectionType: 3 = OnlyAliveAndTargetable)` -- le 4e
    argument NATIF, lu aux octets (`xor r8d,r8d` / `mov r9d,3`). Le port l'avalait et compensait
    par un wrapper `Alive(...)` : le volet TARGETABLE manquait."""
    from engine.entities.selectors.units import AdjacentUnits, Sub
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    arbre = FIRE.fire_of_absolution_tree(30, int(EffectType.Fire))
    trouve = []

    def _visite(n, prof=0):
        if prof > 14 or n is None:
            return
        if isinstance(n, AdjacentUnits):
            trouve.append(n)
        for a in ("a", "b", "child", "behaviour", "left", "right", "source", "center",
                  "target_sel", "entities", "selector"):
            v = getattr(n, a, None)
            if v is not None and not isinstance(v, (int, str, bool)):
                _visite(v, prof + 1)

    _visite(arbre)
    assert len(trouve) == 1, "un seul `AdjacentUnits` dans l'arbre natif"
    assert trouve[0].selection_type is not None, "le `selectionType` natif est AVALE"
    assert int(trouve[0].selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable) == 3


def test_le_create_trigger_de_fire_of_absolution_existe():
    """La docstring du port affirmait << pas de `CreateTrigger` distinct dumpe pour ce passif >>.
    C'est FAUX : `...FireOfAbsolutionAbility$$CreateTrigger` a un corps PROPRE dans
    `frida/methods.tsv`. Ce test garde la CORRECTION, pas le code -- une prose fausse survit a tous
    les tests fonctionnels."""
    import io
    from pathlib import Path
    racine = Path(__file__).resolve().parents[4]      # tests/engine/<f> -> scripts/python -> RACINE
    build = (racine / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    p = racine / "data" / "symbols" / build / "frida" / "methods.tsv"
    noms = set()
    for ligne in io.open(p, encoding="utf-8"):
        f = ligne.rstrip("\n").split("\t")
        if len(f) > 1 and "FireOfAbsolutionAbility" in f[1]:
            noms.add(f[1].rsplit(".", 1)[-1])
    assert "CreateTrigger" in noms, "le CreateTrigger de FireOfAbsolution a un corps PROPRE"
    src = (racine / "scripts" / "python" / "engine" / "runner" / "operations" / "triggers"
           / "loki" / "fire.py").read_text(encoding="utf-8")
    # Critere par PRESENCE du symbole, pas par absence de la phrase fausse : l'absence rougirait sur
    # la CORRECTION elle-meme (qui doit citer la phrase pour la refuter) -- mesure faite, le test
    # est tombe dessus. Ce qui est exigible, c'est que le module NOMME le trigger natif.
    assert "FireOfAbsolutionAbility$$CreateTrigger" in src, \
        "le module doit CITER le trigger natif, dont le corps est propre dans les tables"
    assert "AttackInAtomicGroup" in src and "IsRangedAttack()" in src


# ==================================================================================================
# [5] CONTRE-EPREUVES PAR MUTATION -- un garde vert sous mutation est INERTE
# ==================================================================================================

def _rougit(fn) -> bool:
    try:
        fn()
    except AssertionError:
        return True
    return False


def test_mutation_gate_hp_non_strict(monkeypatch):
    """Mutant : `AmountIsGreater` a la place d'`AmountIsEqualOrGreater` (`pct <= hpPct`). C'est le
    mislabel ICF exact que le brief signale, et il ne change QUE le cas << pile au seuil >>."""
    vrai = TT.health_lower_than_pct
    monkeypatch.setattr(TT, "health_lower_than_pct",
                        lambda c: (TT.health_current_pct((c or {}).get("tgt_hp"),
                                                         (c or {}).get("tgt_hp_max")) or 999)
                        <= int(GC.ability("TrophyTaker")["constants"]["hpPct"]))
    assert _rougit(test_gate_hp_est_strict), "le garde du seuil STRICT ne mord pas"
    monkeypatch.setattr(TT, "health_lower_than_pct", vrai)


def test_mutation_pct_tronque_au_lieu_darrondi(monkeypatch):
    """Mutant : troncature a la place du demi-vers-le-pair. Divergence sur 2/3 (66 vs 67) et sur
    3/8 (37 vs 38) -- deux points ou le seuil peut basculer."""
    monkeypatch.setattr(TT, "health_current_pct",
                        lambda hp, mx: None if not hp or not mx or int(mx) <= 0
                        else (int(hp) * 100) // int(mx))
    assert _rougit(test_health_current_pct_est_un_arrondi_demi_vers_le_pair), \
        "le garde de l'arrondi ne mord pas"


def test_mutation_union_reduite_a_la_melee(monkeypatch):
    """Mutant : `UnitsDefeatedBy` ne lirait qu'UNE des deux listes. Ici, le port n'ayant qu'UNE
    liste (equivalence mesuree), la mutation la VIDE de moitie -- meme observable."""
    vrai = UnitsDefeatedBy.select
    monkeypatch.setattr(UnitsDefeatedBy, "select", lambda self, ctx: vrai(self, ctx)[:1])
    assert _rougit(test_units_defeated_by_prend_l_union_et_dedoublonne), \
        "le garde de l'union ne mord pas"
    monkeypatch.setattr(UnitsDefeatedBy, "select", vrai)


def test_mutation_normal_units_absent(monkeypatch):
    """Mutant : le compteur oublie `NormalUnits` -- un decoy `Steppable` ecrase compterait. C'est
    exactement le genre d'ecart qui gonfle une chance de crit sans jamais lever d'erreur."""
    from engine.entities.selectors.tiles import Caster as _C
    monkeypatch.setattr(TTT, "trophy_taker_crit_chance_multiplier_tree",
                        lambda: Count(UnitsDefeatedBy(_C())))
    assert _rougit(test_l_arbre_du_multiplicateur_est_celui_du_decompile), \
        "le garde de la structure de l'arbre ne mord pas"


def test_mutation_owner_is_caster_exige_des_deux_cotes(monkeypatch):
    """Mutant : le canal DEGAT exige lui aussi `get_OwnerIsCaster`. Il ne recoit pas `owner_id` ->
    le bonus de degat DISPARAIT partout, en silence. Degradation RESTRICTIVE, la plus dure a voir."""
    vrai = TT.TrophyTakerExtraCritDamageEffect._gate
    monkeypatch.setattr(TT.TrophyTakerExtraCritDamageEffect, "_gate",
                        lambda self, c, balayage_board: vrai(self, c, True))
    assert _rougit(test_owner_is_caster_nest_exige_que_du_canal_board_wide), \
        "le garde de l'asymetrie des deux canaux ne mord pas"
    monkeypatch.setattr(TT.TrophyTakerExtraCritDamageEffect, "_gate", vrai)


def test_mutation_chance_figee(monkeypatch):
    """Mutant : la chance de FireOfAbsolution redevient un litteral. Le garde doit rougir MEME si
    la valeur figee est la bonne aujourd'hui -- c'est le CANAL qu'il garde, pas le nombre."""
    monkeypatch.setattr(FIRE, "fire_of_absolution_ignite_chance", lambda: 31)
    assert _rougit(test_chance_est_lue_du_gameconfig_pas_codee_en_dur), \
        "le garde du canal de config ne mord pas"


def test_mutation_selection_type_avale(monkeypatch):
    """Mutant : le port ravale le `selectionType` d'`AdjacentUnits`, comme avant #951."""
    vrai = FIRE.fire_of_absolution_tree

    def _sans(chance, eff):
        from engine.entities.selectors.units import AdjacentUnits
        vrai_init = AdjacentUnits.__init__

        def _init(self, center, radius=None, selection_type=None):
            vrai_init(self, center, radius, None)
        monkeypatch.setattr(AdjacentUnits, "__init__", _init)
        try:
            return vrai(chance, eff)
        finally:
            monkeypatch.setattr(AdjacentUnits, "__init__", vrai_init)

    monkeypatch.setattr(FIRE, "fire_of_absolution_tree", _sans)
    assert _rougit(test_selection_type_de_l_adjacence_est_porte), \
        "le garde du selectionType ne mord pas"


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
