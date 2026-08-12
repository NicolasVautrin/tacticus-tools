"""#963 -- garde OFFLINE des deux passifs de kit portes par la tranche :
`RedRampage` (`bloodTerminator`) et `GeminaeSuperia` (`adeptCelestine`).

Ce fichier ne monte AUCUN runner : il garde ce qu'un test live ne voit pas -- l'existence de
l'EMETTEUR, la forme des arbres, et les ordinaux MESURES a la conversion.

SEPT etages, et chacun a une raison d'exister qui a ete MESUREE pendant la tranche :

  1. les deux passifs sont au registre `ABILITY_TRIGGERS`, avec le bon nombre de classes ;
  2. `On(0x39 = PreDamageTaken)` a un EMETTEUR -- c'etait le NON du critere de lot : au moment de
     l'ouverture, `engine/**` construisait 40 types d'evenement et celui-ci n'en faisait pas
     partie. `GeminaeSuperiaAbility` y serait entre *registered-but-dead* ;
  3. le pipeline de degat APPELLE reellement ce vecteur (l'etage 2 ne garde que la fonction, pas
     son cablage -- un vecteur declare et jamais appele est le MEME angle mort) ;
  4. `IsFirstDamagingHitInSeries` n'est PAS `IsFirstHitInSeries` : trois champs voisins
     (`AbilityEntities` +0x108 / +0x110 / +0x118), et deux citations d'offset du depot etaient
     FAUSSES avant cette tranche ;
  5. les ordinaux d'enum ecrits aux sites, FIGES a la valeur mesuree (le registre `probe_313`
     compare le mirror au build, pas la valeur ECRITE) ;
  6. les constantes lues du GAMECONFIG (`nrOfHits`, `extraMovement`, `unitId`, `damageProfile`) ;
  7. le cap de `GeminaeSuperia` compte les summons MORTS COMPRIS -- confronte LIVE (2e attaque sur
     Celestine apres la mort des deux Geminae : AUCUN nouveau spawn).
"""
from __future__ import annotations

import ast
import io
import os

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.effect_type import EffectType
from engine.entities.stats import StatType
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_selection_type import UnitSelectionType
from engine.runner.operations.triggers.dispatch import registry as REG
from engine.runner.operations.triggers.loki import geminae_superia as GEM
from engine.runner.operations.triggers.loki import red_rampage as RR


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- les deux passifs sont INSCRITS, avec le bon nombre de classes natives
# --------------------------------------------------------------------------------------------
def test_registre_porte_les_deux_passifs():
    """`RedRampage` a DEUX classes natives (`_AttackAbility`, `_BuffAbility`) pour UN id de kit,
    `GeminaeSuperia` une seule -- comptes etablis par la colonne << classe declarante >> de
    `frida/methods.tsv`, jamais par grep de nom."""
    rr = REG.ABILITY_TRIGGERS.get("RedRampage")
    gem = REG.ABILITY_TRIGGERS.get("GeminaeSuperia")
    assert rr is not None, "RedRampage absent d'ABILITY_TRIGGERS"
    assert gem is not None, "GeminaeSuperia absent d'ABILITY_TRIGGERS"
    assert [c.__name__ for c in rr] == ["RedRampageAttackAbility", "RedRampageBuffAbility"]
    assert [c.__name__ for c in gem] == ["GeminaeSuperiaAbility"]
    # Les DEUX classes de RedRampage partagent l'id de kit 1551, et ecoutent des events DIFFERENTS.
    assert {c.TRIGGERED_ABILITY_ID for c in rr} == {int(TriggeredAbilityType.RedRampage)}
    assert rr[0].event_id == int(EventTriggerType.ArrivedAtFinalTile)
    assert rr[1].event_id == int(EventTriggerType.UnitDefeated)
    assert gem[0].event_id == int(EventTriggerType.PreDamageTaken)
    assert gem[0].TRIGGERED_ABILITY_ID == int(TriggeredAbilityType.GeminaeSuperia)


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- l'EMETTEUR existe (le NON du critere de lot)
# --------------------------------------------------------------------------------------------
def _types_emis() -> dict:
    """Recense les emetteurs comme la tranche l'a fait : tout `TriggerEvent(EventTriggerType.X, ...)`
    construit dans `engine/**`. C'est la MESURE qui a montre le trou (40 types, `PreDamageTaken`
    absent des 40) -- on la rejoue, on ne la cite pas."""
    root = os.path.join(os.path.dirname(__file__), "..", "..", "..", "engine")
    out: dict = {}
    for dp, _dirs, fs in os.walk(os.path.abspath(root)):
        for f in fs:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f)
            try:
                tree = ast.parse(io.open(p, encoding="utf-8").read())
            except (OSError, SyntaxError):
                continue
            for n in ast.walk(tree):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id == "TriggerEvent" and n.args
                        and isinstance(n.args[0], ast.Attribute)):
                    out.setdefault(n.args[0].attr, []).append(f"{p}:{n.lineno}")
    return out


def test_pre_damage_taken_a_un_emetteur():
    """LE CRITERE DE LOT. Sans cet etage, `GeminaeSuperiaAbility` serait *registered-but-dead* :
    inscrite au registre (etage 1 VERT) et jamais declenchee, sans erreur ni crash."""
    emis = _types_emis()
    assert len(emis) > 30, f"recenseur casse : {len(emis)} types seulement"
    sites = emis.get("PreDamageTaken")
    assert sites, ("On(0x39 = PreDamageTaken) n'a AUCUN emetteur -> GeminaeSuperia entre MORTE. "
                   f"types emis = {sorted(emis)}")
    # Les deux events de RedRampage aussi (ils en avaient deja un AVANT la tranche).
    assert emis.get("ArrivedAtFinalTile"), "On(0x1c) sans emetteur"
    assert emis.get("UnitDefeated"), "On(0x36) sans emetteur"


def test_le_pipeline_de_degat_appelle_le_vecteur():
    """Un vecteur DECLARE mais jamais CABLE est le meme angle mort qu'un vecteur absent : l'etage 2
    passerait au vert sur une fonction morte.

    ⚠ CE TEST A ETE ECRIT DEUX FOIS. La premiere version cherchait la CHAINE
    `pre_damage_taken_triggers(` dans le source -- et la contre-epreuve l'a REFUTE : remplacer
    l'appel par `None and attack_dispatch.pre_damage_taken_triggers(...)` (donc le desarmer
    completement) la laissait VERTE, la chaine etant toujours la. Un garde de PRESENCE TEXTUELLE
    ne peut pas voir un appel neutralise. On confronte donc l'AST : l'appel doit etre une
    INSTRUCTION NUE (`ast.Expr` dont la valeur EST le `Call`), pas un operande de `and`/`or`, pas
    une valeur jetee."""
    p = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                     "engine", "runner", "operations", "damage.py")
    src = io.open(os.path.abspath(p), encoding="utf-8").read()
    tree = ast.parse(src)

    def _nom(call):
        f = call.func
        return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)

    appels_nus = {}          # nom -> lineno de l'appel joue comme INSTRUCTION
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            nom = _nom(n.value)
            if nom:
                appels_nus.setdefault(nom, n.lineno)

    assert "pre_damage_taken_triggers" in appels_nus, (
        "operations/damage.py n'APPELLE pas pre_damage_taken_triggers en instruction nue "
        f"(appels nus vus : {sorted(appels_nus)})")

    # PLACE : l'appel doit PRECEDER la mutation de PV -- c'est ce qui fait que la victime est encore
    # a pleine vie quand la Geminae apparait (lu aux octets dans `ApplyDamageOperation$$Execute`).
    i_pre = appels_nus["pre_damage_taken_triggers"]
    lignes = src.splitlines()
    i_reduce = next(i for i, l in enumerate(lignes, 1) if "applied = thc.reduce(total)" in l)
    assert i_pre < i_reduce, "On(0x39) doit etre emis AVANT la mutation de PV"
    # ORDRE des trois events de la MEME operation native : 0x39 -> 0xf -> 0x10.
    assert i_pre < appels_nus["damage_taken_triggers"] < appels_nus["damage_dealt_triggers"], \
        "ordre natif 0x39 -> 0xf -> 0x10 non respecte"


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- les TROIS champs voisins ne sont pas le meme
# --------------------------------------------------------------------------------------------
def test_is_first_damaging_hit_est_un_champ_distinct():
    """`IsFirstDamagingHitInSeriesTrigger$$ShouldTrigger` lit `AbilityEntities+0x118` DIRECTEMENT ;
    `IsFirstHitInSeriesTrigger` passe par `get_IsFirstHit` (+0x108) et
    `IsFirstHitGroupInAttackTrigger` par `get_IsFirstHitGroup` (+0x110). Les confondre ferait
    spawner la Geminae sur un coup entierement bloque."""
    from engine.entities.triggers import IsFirstDamagingHitInSeries, IsFirstHitInSeries
    assert IsFirstDamagingHitInSeries is not IsFirstHitInSeries

    class _Ctx:
        is_first_hit = True
        is_first_damaging_hit = None

    ctx = _Ctx()
    # Meme contexte, verdicts OPPOSES : c'est la preuve que les deux noeuds lisent deux canaux.
    assert IsFirstHitInSeries().should_trigger(ctx) is True
    assert IsFirstDamagingHitInSeries().should_trigger(ctx) is False
    ctx.is_first_damaging_hit = True
    assert IsFirstDamagingHitInSeries().should_trigger(ctx) is True

    # Le champ existe sur le porteur d'evenement, en TRI-ETAT.
    from engine.runner.operations.triggers.base import TriggerEvent
    ev = TriggerEvent(EventTriggerType.PreDamageTaken, 1, 2, ranged=False, profile=None)
    assert ev.is_first_damaging_hit is None                  # `Nullable` vide -> le trigger dit false


# --------------------------------------------------------------------------------------------
# ETAGE 5 -- les ordinaux ECRITS aux sites, figes a la valeur MESUREE
# --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("membre,attendu", [
    (TriggeredAbilityType.RedRampage, 1551),            # 0x60f
    (TriggeredAbilityType.GeminaeSuperia, 1048),        # 0x418
    (TriggeredAbilityType.Lifewards, 1049),             # 0x419
    (EffectType.RedRampage_ExtraMovement, 1570),        # 0x622
    (EffectType.GeminaeSuperia_JustSummonedEffect, 1061),   # 0x425
    (EventTriggerType.PreDamageTaken, 57),              # 0x39
    (EventTriggerType.ArrivedAtFinalTile, 28),          # 0x1c
    (EventTriggerType.UnitDefeated, 54),                # 0x36
    (StatType.MOVEMENT, 1),                             # `AddStaticStatModifierEffect(..., 1, ...)`
    (AbilityConstantType.extraMovement, 14),            # `GetNumberConstant(0xe)`
    (AbilityConstantType.unitId, 0),                    # `GetStringConstant(0)`
    (UnitSelectionType.OnlyAliveAndTargetable, 3),      # `AdjacentEnemies(..., 3)`
    (UnitSelectionType.Any, 0),                         # `UnitsWithId(..., 0)` du cap
])
def test_ordinaux_mesures(membre, attendu):
    """`probe_313` compare le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror apres
    un renumerotage, alors que la valeur ECRITE au site, elle, a change. Cet etage garde l'ordinal
    tel qu'il a ete MESURE pendant la tranche."""
    assert int(membre) == attendu, f"{membre!r} : {int(membre)} != {attendu} (build rnca9r7q6c)"


def test_les_ordinaux_ne_sont_pas_interchangeables():
    """Contre-epreuve du precedent : un ordinal juste dans UN enum peut nommer autre chose dans un
    autre. Le cap de GeminaeSuperia (`UnitSelectionType.Any = 0`) et la constante `unitId = 0`
    partagent l'ordinal 0 sans designer la meme chose."""
    assert int(UnitSelectionType.Any) == int(AbilityConstantType.unitId) == 0
    assert UnitSelectionType.Any.name != AbilityConstantType.unitId.name


# --------------------------------------------------------------------------------------------
# ETAGE 6 -- les constantes viennent du GAMECONFIG, pas d'un litteral recopie
# --------------------------------------------------------------------------------------------
def test_constantes_du_gameconfig():
    import gameconfig as GC
    rr = (GC.ability("RedRampage") or {}).get("constants") or {}
    assert rr.get("damageProfile") == RR.DAMAGE_PROFILE == "Power"
    assert int(rr.get("nrOfHits")) == 2
    assert RR.extra_movement_amount() == int(rr.get("extraMovement")) == 1
    gem = (GC.ability("GeminaeSuperia") or {}).get("constants") or {}
    assert GEM._summon_unit_id() == gem.get("unitId") == "adeptSmnGeminaeSuperia"
    # Le porteur du summon declare bien `Lifewards` -- c'est ce que `TriggerAbility` va viser.
    smn = GC.unit("adeptSmnGeminaeSuperia") or {}
    passifs = smn.get("passiveAbilities") or []
    assert "Lifewards" in passifs, f"le summon ne porte pas Lifewards : {passifs}"


def test_cap_geminae_est_un_litteral_de_l_ability():
    """`DSLFormulas.Get(2)` : le 2 est ECRIT dans `GeminaeSuperiaAbility$$SummonLimit`, il n'existe
    AUCUNE variable ni constante de config qui le porte. Un lecteur qui irait le chercher dans le
    gameconfig ne trouverait rien et poserait un cap de 0 (ou infini)."""
    import gameconfig as GC
    cfg = GC.ability("GeminaeSuperia") or {}
    consts = cfg.get("constants") or {}
    variables = cfg.get("variables") or {}
    assert GEM.SUMMON_LIMIT == 2
    assert not any("limit" in k.lower() or "max" in k.lower()
                   for k in list(consts) + list(variables)), \
        f"une cle de config porte peut-etre le cap : consts={list(consts)} vars={list(variables)}"


# --------------------------------------------------------------------------------------------
# ETAGE 7 -- le cap compte les summons MORTS COMPRIS (confronte live)
# --------------------------------------------------------------------------------------------
def test_le_cap_ne_filtre_pas_les_morts():
    """`UnitsWithId(Children(Owner), unitId, UnitSelectionType.Any = 0)` et
    `IdunBattleLogic.Entities.DSLSelectors$$Children` SANS filtre `alive`.

    GROUND TRUTH LIVE (#963, board MC1_67, seed 777, `adeptCelestine` injectee au catalogue) :
    tour 1 -- Celestine attaquee, elle reste a PLEINE VIE (6025/6025) et DEUX unites de son camp
    meurent alors qu'une SEULE avait ete deployee (les deux Geminae, qui encaissent via Lifewards) ;
    tour 2 -- Celestine attaquee a nouveau, AUCUN nouveau spawn, elle encaisse (1566 dmg). Si le cap
    comptait les VIVANTES, une 3e Geminae serait apparue.

    Le garde executable : l'arbre du cap ne doit porter AUCUN noeud `Alive`/`Damageable`."""
    from engine.entities.selectors.geometry import UnitsWithId
    tree = GEM.geminae_summoned_units()
    assert isinstance(tree, UnitsWithId)
    assert int(GEM.SUMMON_COUNT_SELECTION) == int(UnitSelectionType.Any)
    # Le source du selecteur est `ChildrenOf` (DSLSelectors$$Children, AVEC argument), et non
    # l'accumulateur `Children()` du cast courant -- les confondre (#590) rendrait le cap TOUJOURS
    # nul, donc un spawn a chaque coup recu.
    from engine.entities.selectors.tiles import Children, ChildrenOf
    src = getattr(tree, "source", None)
    assert isinstance(src, ChildrenOf), f"source du cap = {type(src).__name__}, attendu ChildrenOf"
    assert not isinstance(src, Children)


def test_red_rampage_frappe_tout_le_pool_sans_tirage():
    """`RedRampage_AttackAbility$$CreateBehaviour` passe le selecteur NU, contrairement a son voisin
    de forme `ChampionOfTheFeast` (`Cache(Otherwise(PickRandomly, PickRandomly))`, UNE cible).

    GROUND TRUTH LIVE (#963, board MC1_67, seed 777) : Cezare arrive en (4,4) au contact de DEUX
    ennemis -> `[Ability_Power e=77 <<RedRampage>>]` frappe les DEUX, 2 coups chacun
    (`Passive_Ability_Type=1551`, `DamageProfileType=14`).

    Garde executable : l'arbre ne porte AUCUN `PickRandomly`/`Cache` (sinon le port ne frapperait
    qu'une cible ET consommerait un tirage PRNG que le natif ne consomme pas)."""
    import engine.entities.selectors.geometry as G
    behaviour = RR.red_rampage_attack_behaviour_tree()
    assert behaviour.multi is True, "le pool ENTIER doit etre frappe"
    assert behaviour.pick_n is None, "aucun PickRandomly dans cet arbre"
    tgt = behaviour.target_sel
    assert not isinstance(tgt, (G.PickRandomly, G.Cache)), \
        f"selecteur enveloppe ({type(tgt).__name__}) : c'est le voisin de forme, pas RedRampage"
    assert type(tgt).__name__ == "AdjacentEnemies"


def test_red_rampage_buff_re_time_et_ne_cumule_pas():
    """`If(HasEffect(...), ChangeEffectTurns(..., ChangeType.Set = 1), AddStaticStatModifierEffect)`.

    `ChangeType.Set`, pas `Add` : deux kills dans le meme tour donnent +1 Movement, jamais +2.

    GROUND TRUTH LIVE : apres un kill par Cezare, il porte `RedRampage_ExtraMovement` (effet 1570)
    -- lu dans la vue du runner."""
    tree = RR.red_rampage_buff_behaviour_tree(turns=3, amount=1)
    assert type(tree).__name__ == "If"
    assert type(tree.then).__name__ == "ChangeEffectTurns"
    assert tree.then.change_type == 1, "ChangeType.Set attendu (1), pas Add (0)"
    assert type(tree.otherwise).__name__ == "AddStaticStatModifierEffect"
    assert tree.otherwise.stat_type == int(StatType.MOVEMENT)
    assert tree.otherwise.effect_type == int(EffectType.RedRampage_ExtraMovement)
    # Les DEUX branches visent le MEME effet et la MEME duree.
    assert tree.then.effect_type == tree.otherwise.effect_type
    assert tree.then.turns == tree.otherwise.duration_turns == 3
