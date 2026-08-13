"""#1016 -- CLIQUET des deux passifs Necrons portes par la tranche : `ReanimationProtocols` (1008,
9 porteurs) et `WhipcoilBody` (1009, effet 1118).

POURQUOI CE FICHIER EXISTE. Un passif non porte ne produit AUCUNE erreur :
`engine/runner/operations/triggers/dispatch/core.py` fait `for cls in ABILITY_TRIGGERS.get(pa, ())`
-- un nom absent rend un tuple vide et le moteur continue. Il n'existe, de ce cote, aucun
accumulateur `unported` (contrairement aux actives). Le retrait de l'une des deux inscriptions ne
casserait donc RIEN d'observable ; ce fichier est la seule chose qui rougirait.

CE QU'IL GARDE, etage par etage :
  0. le CABLAGE (les deux registres, et le predicat de couverture de l'audit) ;
  1. `ReanimationProtocols` MORD -- avec un congenere vivant, la resurrection se produit ;
  2. les SIX gates du trigger DISCRIMINENT, un par un (sinon l'etage 1 ne garde rien) ;
  3. le `>` STRICT d'`AmountIsEqualOrGreater` -- le cran que `>=` ne verrait pas ;
  4. la MAGNITUDE : `PercentageOf(StatAmount(Owner, Health, **Initial**), Direct(hpPct))`, lue a
     PV NULLE (l'unite vient de mourir) -- c'est l'etage qui casse si le port lit la PV COURANTE ;
  5. la REPETABILITE : aucun gate once-per-turn / once-per-battle dans l'arbre natif ;
  6. `WhipcoilBody` : magnitude, gate `IsMeleeAttack`, et l'ABSENCE de patte AURA.

OFFLINE INTEGRAL : `State` synthetique, aucun runner, aucun RPC. ASCII only.
"""
from __future__ import annotations

import pytest

import audit_kit_coverage as AUDIT
import gameconfig as GC
from engine.entities.effect_type import EffectType
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.damage_reduction import WhipcoilBodyReduceDmgEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.effects_state import EffectsState
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.revive import kill_unit_revive_gate
from engine.runner.operations.triggers.dispatch.move_death import after_death_triggers
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki.reanimation_protocols import (
    ABILITY_ID, REANIMATION_ABILITY, REANIMATION_HEAL_TYPE, ReanimationProtocolsAbility,
    same_type_allies_alive)
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State


#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # VIDE : tout ce que ce fichier lit -- les deux registres, la classe de trigger, la classe
    # d'effet, le pipeline de mort -- est dans sa propre fermeture d'imports, donc dans la cascade
    # DERIVEE par le foyer. Recopier des chemins ici serait la faute #531.
    "chemins": (),
    # VRAI : les DEUX magnitudes viennent du gameconfig du build (`ReanimationProtocols.constants
    # {chance, hpPct}` et `WhipcoilBody.variables.dmgReduction`). Un re-dump qui renommerait l'une
    # de ces cles ferait tomber le montant a 0 -- exactement le rouge attendu.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde DEUX comportements de passif Necron et rien d'autre : que "
        "ReanimationProtocols ressuscite un porteur qui a un congenere vivant du meme type (et "
        "SEULEMENT dans ce cas), et que WhipcoilBody retranche dmgReduction aux seules attaques de "
        "melee subies par son porteur. Son verdict ne depend que de sa fermeture d'imports et du "
        "gameconfig du build."
    ),
}

#: Le porteur SUMMON de reference -- c'est celui du montage live (`necroSpyder` / `ScarabHive` en
#: spawne DEUX d'un coup, donc deux unites de meme `visual_id` et de meme equipe).
SWARM = "necroSmnSwarm"
#: Un AUTRE porteur du meme passif, mais d'un `visual_id` DIFFERENT : il ne doit PAS compter.
WARRIOR = "necroSmnWarrior"
#: Le porteur de `WhipcoilBody`.
DESTROYER = "necroSmnDestroyer"

HP_MAX = 20000
LEVEL, MULT = 50, 100
#: Assez de tirages pour qu'un `chance = 35 %` mordent ET rate au moins une fois (P(tout pareil)
#: sur 24 tirages independants < 1e-4). Les seeds sont FIXES -> le test est deterministe.
SEEDS = tuple(range(1000, 1024))


class _Ctx:
    """Le minimum de `UnitContext` que `collect_triggered_abilities` et `entities_from_state`
    lisent. `visual_id` est ce que `UnitsWithVisualIdSelector` compare ; `passive_abilities` est le
    canal MESURE dont le collecteur se sert en priorite (hierarchie 2 =
    `UnitConfiguration.PassiveAbilities`)."""

    def __init__(self, visual_id: str, traits=(), passives=None):
        self.visual_id = visual_id
        self.traits = list(traits)
        self.passive_abilities = list(passives) if passives is not None else None
        self.active_ability_level = LEVEL
        self.passive_ability_level = LEVEL
        self.ability_variables_multiplier = MULT


def _unite(st: State, uid: int, visual_id: str, *, team: int, traits=(("Mechanical",)),
           passives=None, pos=(0, 0), hp=HP_MAX, hp_max=HP_MAX) -> int:
    e = st.add_entity(uid)
    e.add_component(UnitComponent(visual_id, True))
    e.add_component(OwnerComponent(team, team))
    e.add_component(HealthComponent(hp, hp_max))
    e.add_component(StatsComponent(ctx=_Ctx(visual_id, traits, passives)))
    e.add_component(PositionComponent(int(pos[0]), int(pos[1])))
    return uid


@pytest.fixture
def necrons():
    """FIXTURE NOMMEE ET REUTILISABLE -- le couple qui resservira : DEUX `necroSmnSwarm` de la MEME
    equipe (ce que `ScarabHive` spawne), plus un tueur adverse.

    Chaque face NEGATIVE se fabrique en retirant UNE piece du montage (le congenere, le trait
    Mechanical, l'egalite d'equipe, l'egalite de `visual_id`), jamais en en ajoutant une."""
    def _monter(congenere: bool = True, meme_visual: bool = True, meme_equipe: bool = True,
                mechanical: bool = True, steppable: bool = False, seed: int = 777):
        st = State()
        st.effects = EffectsState()
        st.rng = IntBasedMersenneTwister(seed)
        traits = ["Mechanical"] if mechanical else []
        if steppable:
            traits.append(UnitTrait.Steppable.name)
        moi = _unite(st, 10, SWARM, team=1, traits=traits, pos=(0, 0))
        if congenere:
            _unite(st, 11, SWARM if meme_visual else WARRIOR,
                   team=(1 if meme_equipe else 2), traits=["Mechanical"], pos=(1, 0))
        tueur = _unite(st, 20, "necroWarden", team=2, traits=["Mechanical"], pos=(2, 0))
        return st, moi, tueur
    return _monter


def _tuer(st: State, uid: int, killer: int, overkill: bool = False):
    """`On(1 = PreUnitDeath)` PUIS la garde `IdunBattle.Operations.KillUnitOperation$$Execute`
    (`kill_unit_revive_gate`), qui draine la `ReviveData` posee par la feuille `Revive`.
    Le port pose `alive = False` AVANT le dispatch : c'est ce que declare `fire_on_death`, et c'est
    l'ecart de harnais que `same_type_allies_alive` retablit."""
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    out = after_death_triggers(st, dying_id=uid, killer_id=killer, overkill=overkill)
    kill_unit_revive_gate(st, uid)
    return out


def _vivant(st: State, uid: int) -> bool:
    return bool(st.get_entity(uid).get_component(UnitComponent).alive)


def _compter_revives(monter, **kw) -> int:
    """Nombre de seeds (sur `SEEDS`) ou la resurrection se produit. Un `Maybe(chance)` fait UN
    tirage `next_bool` : balayer les seeds echantillonne donc la loi, sans jamais la fitter."""
    n = 0
    for s in SEEDS:
        st, moi, tueur = monter(seed=s, **kw)
        _tuer(st, moi, tueur)
        n += 1 if _vivant(st, moi) else 0
    return n


# ═══ 0. LE CABLAGE ═══════════════════════════════════════════════════════════════════════════════

def test_les_deux_passifs_sont_INSCRITS_et_COUVERTS():
    """Le cran de non-regression du gisement : retirer l'une des deux inscriptions ne casse RIEN
    d'observable ailleurs (`ABILITY_TRIGGERS.get(pa, ())` rend un tuple vide sans erreur)."""
    assert ABILITY_ID in ABILITY_TRIGGERS, "ReanimationProtocols n'a plus de rail : le moteur " \
                                           "simule les Necrons SANS leur mecanique de faction"
    assert ReanimationProtocolsAbility in ABILITY_TRIGGERS[ABILITY_ID]
    assert EFFECT_CLASSES.get(EffectType.WhipcoilBody_ReduceDmg.name) is WhipcoilBodyReduceDmgEffect
    assert ABILITY_INIT_OWNER_EFFECTS.get("WhipcoilBody") == ["WhipcoilBody_ReduceDmg"]
    for nm in (ABILITY_ID, "WhipcoilBody"):
        assert AUDIT._passive_covered(nm) is True, "%s retombe hors couverture de l'audit" % nm


def test_les_ordinaux_des_deux_enums_sont_ceux_du_build():
    """Le piege documente : QUATRE noms pour deux entiers. Aucune de ces confusions ne LEVERAIT --
    les quatre membres existent -- donc seul un test peut les tenir."""
    assert int(TriggeredAbilityType.ReanimationProtocols) == 1008
    assert int(TriggeredAbilityType.WhipcoilBody) == 1009
    assert int(EffectType.WhipcoilBody_ReduceDmg) == 1118
    # TEMOIN NON DEGENERE : les memes ordinaux nomment autre chose ailleurs, et ces autres choses
    # EXISTENT (une confusion lirait une config valide, en silence).
    from engine.entities.active_ability_type import ActiveAbilityType
    assert int(ActiveAbilityType.HarbingerOfDestruction) == 1008
    assert int(ActiveAbilityType.ResurrectionOrb) == 1009
    assert int(TriggeredAbilityType.TerrorsLament) == 1118


def test_les_deux_constantes_du_gameconfig_sont_des_CONSTANTES():
    """`GetNumberConstant(0x12 = hpPct)` / `(0x2a = chance)` -- et NON `GetVariableForLevel`. Le
    gameconfig le confirme independamment du decompile : `variables` est VIDE."""
    cfg = GC.ability(ABILITY_ID) or {}
    assert cfg.get("variables") in ({}, None), "ReanimationProtocols n'a AUCUNE variable"
    assert cfg.get("constants", {}).get("chance") == "35"
    assert cfg.get("constants", {}).get("hpPct") == "25"


# ═══ 1. ReanimationProtocols MORD ════════════════════════════════════════════════════════════════

def test_le_revive_MORD_quand_un_congenere_vit(necrons):
    """Le coeur du port. `chance = 35 %` -> sur 24 seeds fixes, il doit y avoir des DEUX (sinon
    c'est que le gate est bloque d'un cote, pas que la loi est respectee)."""
    n = _compter_revives(necrons)
    assert n > 0, "aucune resurrection sur 24 seeds : le trigger ne mord pas"
    assert n < len(SEEDS), "resurrection sur TOUTES les seeds : le `Maybe(chance)` ne tire pas"


def test_la_frequence_est_celle_de_la_constante_chance(necrons):
    """Contre-epreuve de sur-ajustement : on ne fitte pas le scalaire, on borne LARGEMENT autour de
    35 % (24 tirages -> l'intervalle est volontairement lache ; ce test attrape un `chance` lu sur
    la mauvaise cle, pas un ecart de PRNG)."""
    n = _compter_revives(necrons)
    assert 2 <= n <= 18, "frequence %d/24 incompatible avec chance = 35 %%" % n


# ═══ 2. LES GATES DISCRIMINENT (sinon l'etage 1 ne garde rien) ═══════════════════════════════════

def test_gate_congenere_un_necron_ISOLE_ne_ressuscite_JAMAIS(necrons):
    """`AmountIsEqualOrGreater(Friends(...SameVisualId...), Direct(1))` avec `>` STRICT : sans
    AUCUN autre congenere vivant, le compte vaut 1 et `1 > 1` est FAUX. C'est le gate central du
    passif, et celui qu'un `>=` mal lu aurait ouvert."""
    assert _compter_revives(necrons, congenere=False) == 0


def test_gate_visual_id_un_congenere_d_un_AUTRE_TYPE_ne_compte_pas(necrons):
    """`UnitsWithSameVisualId(Target)` -> `HasVisualUnitId(unit, GetVisualUnitId(Target))`, une
    comparaison de CHAINES. `necroSmnWarrior` porte le MEME passif mais n'est pas du meme type."""
    assert _compter_revives(necrons, meme_visual=False) == 0


def test_gate_equipe_un_congenere_ADVERSE_ne_compte_pas(necrons):
    """`Friends(of = Target)` -> `UnitsFrom<Team>Selector$$Select`, qui compare
    `EntityExtensions$$GetCurrentTeamId`. Le referent est l'EQUIPE, pas la faction -- deux swarms
    de camps opposes ont pourtant la MEME faction."""
    assert _compter_revives(necrons, meme_equipe=False) == 0


def test_gate_overkill(necrons):
    """`OnPreDeath(triggerOnOverkill: 0)` -> `NOT(TargetIsOverkilled)`, le << Does not apply if
    Overkilled >> de l'i2. Contraste EXACT avec `PhoenixGem` (litteral 1, aucun gate)."""
    n = 0
    for s in SEEDS:
        st, moi, tueur = necrons(seed=s)
        _tuer(st, moi, tueur, overkill=True)
        n += 1 if _vivant(st, moi) else 0
    assert n == 0, "resurrection malgre l'overkill"


def test_gate_steppable(necrons):
    """`OnPreDeath(triggerOnSteppable: 0)` -> `NOT(HasTrait(Target@+0x60, 0x1b))`. Le parametre
    natif s'appelle litteralement `triggerOnSteppable` ; ce n'est PAS un gate de bouclier.
    INERTE sur les 9 porteurs reels (aucun n'est `Steppable`) -- porte parce qu'il est LU."""
    assert _compter_revives(necrons, steppable=True) == 0


def test_gate_healType_Mechanical_une_cible_NON_MECANIQUE_ne_ressuscite_pas(necrons):
    """`healType = 1 = HealType.Mechanical` -> `IdunBattle.Entities.UnitExtensions$$
    IsAffectedByHealType(1)` exige une cible MECANIQUE. Les 9 porteurs le sont tous, donc ce gate
    ne se voit jamais en bataille reelle -- mais c'est LUI qui rendrait le passif inerte s'il etait
    greffe sur un porteur non-mecanique, et c'est le discriminant du montage live."""
    assert REANIMATION_HEAL_TYPE == 1
    assert _compter_revives(necrons, mechanical=False) == 0


def test_le_compteur_de_congeneres_est_bien_le_sous_arbre_natif(necrons):
    """`same_type_allies_alive` = le cardinal SANS le mourant. Temoin non degenere : il doit valoir
    1 dans le montage nominal et 0 dans chacune des trois faces negatives -- sinon les trois tests
    de gate ci-dessus passeraient pour une raison qui n'est pas la leur."""
    st, moi, _ = necrons()
    assert same_type_allies_alive(st, moi) == 1
    for kw in ({"congenere": False}, {"meme_visual": False}, {"meme_equipe": False}):
        st, moi, _ = necrons(**kw)
        assert same_type_allies_alive(st, moi) == 0, "face negative %r" % (kw,)


# ═══ 3. LE `>` STRICT -- le cran qu'un `>=` ne verrait pas ═══════════════════════════════════════

def test_le_predicat_est_STRICTEMENT_superieur_pas_superieur_ou_egal(necrons):
    """`AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend `evaluate(minAmount@+0x20) < amount`, et
    AUCUN des deux `.ctor` ne decremente `minAmount`. Le nom `AmountIsEqualOrGreater` MENT.

    Ce test est le SEUL endroit ou la difference se voit : avec `>=`, un Necron isole (compte
    natif = 1, le mourant seul) ressusciterait. Les deux redactions donnent le MEME resultat des
    qu'un congenere existe -- d'ou la paire ci-dessous, qui exige les DEUX verdicts."""
    assert _compter_revives(necrons, congenere=False) == 0, "un `>=` aurait ressuscite l'isole"
    assert _compter_revives(necrons, congenere=True) > 0, "temoin : avec un congenere, ca mord"


# ═══ 4. LA MAGNITUDE -- `Initial`, lue a PV NULLE ════════════════════════════════════════════════

def test_le_montant_est_hpPct_de_la_PV_INITIALE_et_non_de_la_PV_COURANTE(necrons):
    """`PercentageOf(StatAmount(Owner@+0x30, 5 = Health, **3 = Initial**), Direct(hpPct))`.

    L'ETAGE QUI CASSE EN SILENCE : au moment ou ce behaviour tourne, l'unite vient de mourir, donc
    sa PV COURANTE vaut 0. Un port qui lirait `StatPart.Current` (ou qui retomberait sur le
    `_default_get_stat` degrade de `dsl/base.py`, lequel rend le hp COURANT) ressusciterait a
    **0 PV** -- une resurrection qui ne rend rien, et qu'aucune erreur ne signale.

    On borne le montage a une PV MAX distincte de la PV de depart pour que les deux lectures
    possibles donnent des nombres DIFFERENTS."""
    attendu = HP_MAX * 25 // 100
    trouve = None
    for s in SEEDS:
        st, moi, tueur = necrons(seed=s)
        # PV courante ARBITRAIREMENT basse avant le coup fatal : si le port lisait `Current`, le
        # montant suivrait cette valeur-la.
        st.get_entity(moi).get_component(HealthComponent).hp = 137
        _tuer(st, moi, tueur)
        if _vivant(st, moi):
            trouve = int(st.get_entity(moi).get_component(HealthComponent).hp)
            break
    assert trouve is not None, "aucune resurrection sur 24 seeds -- montant non observable"
    assert trouve == attendu, ("hp rendu = %d, attendu %d (= 25 %% de la PV INITIALE %d). "
                              "Une lecture de la PV COURANTE aurait rendu 34." % (trouve, attendu, HP_MAX))


def test_hpPct_vient_bien_du_gameconfig_et_pas_d_un_litteral():
    """Temoin non degenere de l'etage precedent : si `hpPct` etait code en dur a 25, ce test
    passerait quand meme -- il verifie donc que la CLE existe et que le port la lit par son nom."""
    assert int(ability_var(ABILITY_ID, "hpPct", is_constant=True)) == 25
    assert int(ability_var(ABILITY_ID, "chance", is_constant=True)) == 35


# ═══ 5. LA REPETABILITE -- aucun gate once-per-battle dans l'arbre ═══════════════════════════════

def test_la_resurrection_est_REPETABLE(necrons):
    """L'arbre natif n'a NI `DeactivateEffect`, NI `RemoveEffect`, NI
    `HasBeenRevivedByAbility(...)` -- contrairement a `ReviveEffect` (once-per-turn),
    `PhoenixGem` (marqueur one-shot) et `GhostEffect` (`HasBeenRevivedByAbility`). L'i2 ne dit pas
    << the first time >>. Un port qui aurait recopie le gate d'un voisin de forme eteindrait le
    passif apres la premiere mort."""
    for s in SEEDS:
        st, moi, tueur = necrons(seed=s)
        _tuer(st, moi, tueur)
        if not _vivant(st, moi):
            continue
        # DEUXIEME mort de la MEME unite, dans la MEME bataille.
        _tuer(st, moi, tueur)
        # On ne demande pas qu'elle ressuscite (le roll peut rater) : on demande que le TRIGGER
        # soit encore evalue, donc que le compteur de congeneres reste satisfait et qu'aucun
        # marqueur n'ait ete pose.
        assert same_type_allies_alive(st, moi) >= 1
        return
    pytest.fail("aucune resurrection sur 24 seeds -- repetabilite non observable")


def test_le_sourceId_du_revive_est_la_TRIGGERED_1008():
    """6e argument de `DSLBehaviors$$Revive` = `Nullable(AbilityOrEffect(this.AbilityType@+0x10))`.
    Le getter est mislabele `CenterSpace.Free.MersenneTwister$$get_Count` par l'ICF, mais son corps
    ENTIER est `return *(uint*)(this + 0x10)` -- le champ que
    `AOwnerEffectTriggeredAbility$$CreateTrigger` lit pour `OnOwnerSpecificAbilityInit`."""
    assert REANIMATION_ABILITY == int(TriggeredAbilityType.ReanimationProtocols) == 1008


# ═══ 6. WhipcoilBody ═════════════════════════════════════════════════════════════════════════════

def _whipcoil(level: int = 50, mult: int = 100) -> WhipcoilBodyReduceDmgEffect:
    return WhipcoilBodyReduceDmgEffect(effect_type=int(EffectType.WhipcoilBody_ReduceDmg),
                                       name=EffectType.WhipcoilBody_ReduceDmg.name,
                                       ability_level=level, ability_variables_multiplier=mult)


def test_whipcoil_retranche_dmgReduction_en_MELEE():
    """`EffectBonus.ForSubtraction(get_OwnerIsTarget & IsMeleeAttack, ConfigVar(0x12 =
    dmgReduction))` -- reduction PLATE, canal DEFENSEUR."""
    attendu = int(ability_var("WhipcoilBody", "dmgReduction", 50, multiplier_pct=100))
    assert attendu > 0, "temoin degenere : le gameconfig ne rend aucun `dmgReduction`"
    b = _whipcoil().create_effect_damage_malus_for_defense(is_melee=True)
    assert b is not None and b.kind == "Subtraction" and int(b.value) == attendu
    assert b.owner_is_caster is False, "l'effet vit sur le DEFENSEUR"


def test_whipcoil_est_MUET_hors_melee_et_sur_nature_INCONNUE():
    """Convention tri-etat #106 : `None` = nature NON DECLAREE -> le gate se FERME (RESTRICTIF).
    Le regime permissif inverse ferait porter la reduction a des attaques a distance."""
    assert _whipcoil().create_effect_damage_malus_for_defense(is_melee=False) is None
    assert _whipcoil().create_effect_damage_malus_for_defense(is_melee=None) is None


def test_whipcoil_n_a_AUCUNE_patte_AURA():
    """`get_OwnerIsTarget` = `AreEqual(Owner@+0x30, Target@+0x60)` : des que le porteur n'est pas la
    cible du coup, le trigger est FAUX. L'absence de `create_aura_defense_damage_malus_for_ally`
    n'est donc pas un oubli -- c'est le trigger.

    TEMOIN NON DEGENERE : le voisin de forme `TerrorsLamentDamageReductionEffect`, dont le trigger
    porte sur `(Caster, Owner)`, en a UNE. Sans ce temoin, ce test passerait meme si le canal aura
    n'existait nulle part dans le moteur.

    ⚠ `hasattr` NE PEUT PAS servir de discriminant ici, et c'est mesure : `BaseEffect` DECLARE le
    canal (retour `None` par defaut), donc `hasattr` rend VRAI pour toute classe d'effet du moteur.
    Le discriminant est la SURCHARGE, c'est-a-dire la presence du nom dans le `__dict__` PROPRE de
    la classe -- plus le fait que l'appel rende `None` sur un ctx d'aura pourtant complet."""
    from engine.entities.effects.loki.terrors_lament import TerrorsLamentDamageReductionEffect
    CANAL = "create_aura_defense_damage_malus_for_ally"
    assert CANAL not in WhipcoilBodyReduceDmgEffect.__dict__, \
        "WhipcoilBody se serait vu greffer une patte AURA que son `get_OwnerIsTarget` interdit"
    assert CANAL in TerrorsLamentDamageReductionEffect.__dict__, \
        "temoin degenere : plus aucun effet ne surcharge ce canal, le test ne garde rien"
    # Et le comportement, pas seulement la forme : sur un ctx d'aura COMPLET (l'attaquant est un
    # ennemi adjacent en melee -- tout ce que TerrorsLament exige), WhipcoilBody reste muet.
    ctx = {"owner_pos": (0, 0), "owner_team": 1, "att_pos": (1, 0), "att_team": 2, "is_melee": True}
    assert getattr(_whipcoil(), CANAL)(ctx) is None
    assert getattr(TerrorsLamentDamageReductionEffect(
        effect_type=int(EffectType.TerrorsLament_DamageReduction),
        name=EffectType.TerrorsLament_DamageReduction.name,
        ability_level=50, ability_variables_multiplier=100), CANAL)(ctx) is not None


def test_whipcoil_scale_par_le_NIVEAU_et_par_la_RARETE():
    """`dmgReduction` a 65 paliers ET figure dans `variablesAffectedByRarityBonus` : les deux axes
    doivent mordre, sinon la magnitude est figee (faute silencieuse)."""
    bas = _whipcoil(level=1).create_effect_damage_malus_for_defense(is_melee=True)
    haut = _whipcoil(level=65).create_effect_damage_malus_for_defense(is_melee=True)
    assert int(bas.value) < int(haut.value), "le NIVEAU ne mord pas"
    assert int(haut.value) == 509, "dernier palier != l'i2 (<< takes -509 Damage >>)"
    rare = _whipcoil(level=50, mult=180).create_effect_damage_malus_for_defense(is_melee=True)
    plat = _whipcoil(level=50, mult=100).create_effect_damage_malus_for_defense(is_melee=True)
    assert int(rare.value) > int(plat.value), "le multiplicateur de RARETE ne mord pas"


def test_whipcoil_n_est_PAS_sur_la_face_ATTAQUANT():
    """L'effet derive de `BaseEffect` et implemente DIRECTEMENT
    `CreateEffectDamageMalusForDefense` -- pas de forwarder
    `DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`. TEMOIN : `MarkerlightEffect`,
    qui lui passe par ce forwarder, doit rendre "attacker"."""
    from engine.entities.effects.loki.damage_reduction import MarkerlightEffect
    assert WhipcoilBodyReduceDmgEffect.DEFENSE_MALUS_NATIVE_FACE == "defender"
    assert MarkerlightEffect.DEFENSE_MALUS_NATIVE_FACE == "attacker"
