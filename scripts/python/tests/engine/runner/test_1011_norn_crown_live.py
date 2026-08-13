"""#1011 -- `NornCrown` (relique de `tyranNeurothrope`), montee LIVE par `rl_duel build
--equip-relic` (#237, etat 2 des trois), et son AURA de degat confrontee au natif.

CE QUE CE FICHIER GARDE, ET POURQUOI CHAQUE GARDE EXISTE
--------------------------------------------------------
* l'effet 1492 se materialise en `NornCrownEffect` -- sans l'entree `EFFECT_CLASSES`,
  `EffectFactory` retombe SILENCIEUSEMENT sur `BaseEffect` et l'aura disparait sans une erreur ;
* le bonus est GATE par `HasEffect(Target, Neuroparasite)` : AVANT la pose du parasite il vaut
  ZERO. C'est la contre-epreuve SANS LE RAIL -- sans elle, un port qui accorderait le bonus a
  toute attaque passerait pour juste (l'ecart mesure serait le meme APRES) ;
* le beneficiaire doit etre AMI, `Psyker` ou `Summon`, et dans la bulle SYNAPSE de l'equipe du
  porteur ;
* la magnitude vient de l'etat **TERTIAIRE** (#357), pas de l'instance : au niveau 1 le natif sert
  `extraDmg[1] = 880`, l'instance porterait `ability_level = 50` donc `extraDmg[10] = 1308`
  (+49 %). C'est le REGIME SEPARANT -- au niveau 10 les deux modeles coincident, donc un montage
  a 10 aurait rendu VERT le port FAUX.

Le niveau **1** est choisi DELIBEREMENT, pour cette derniere raison.

MESURE NATIVE DE REFERENCE (probe `probe_1011_norn_crown.py`, A/B de relique, `--hp-target`
200000 pour sortir du regime SATURE ou `aiPredict` clampe ses bornes aux PV restants) :

    allie `astraPrimarisPsy` AVANT parasite : A - B = (0, 0)          <- le gate mord
    allie `astraPrimarisPsy` APRES parasite : A - B = (+880, +880)    <- extraDmg[1]
    porteur, SEUL emetteur Synapse          : A - B = (0, 0)
    porteur, un SECOND emetteur a 1 hex     : A - B = (+1170, +1170)

Les deux dernieres lignes ETABLISSENT `GetSurroundingUnits(..., includeCenter: FALSE)` : une unite
`Synapse` seule n'est PAS dans sa propre bulle.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.components import UnitComponent
from engine.runner.damage_model import (attacker_modifiers, target_trait_names,
                                        _team_synapse_positions, _target_effect_names)
from engine.entities.pathfinding.board import Board
from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS
from engine.entities.effects.loki.norn_crown import (NornCrownEffect, SYNAPSE_RANGE, SYNAPSE_TRAIT,
                                                     NORN_CROWN_ABILITY)
from engine.entities.effects.magnitude import ability_var
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.operations.triggers.base import triggered_ability_state

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, et c'est une MESURE : ce fichier importe `load_state`, la factory d'effets
    # et `damage_model` -- leur fermeture d'import atteint la quasi-totalite de `scripts/python`.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    # Le NATIF est l'oracle : la POSE de l'effet 1492, le niveau tertiaire publie par
    # `unitAbilityStates`, les paliers `extraDmg` du gameconfig et la bulle Synapse viennent tous
    # du build installe.
    "build": True,
    "toujours": False,
    "raison": ("Lit l'etat live d'un runner monte avec --equip-relic (effet 1492, niveau "
               "TERTIAIRE) et les registres du port (EFFECT_CLASSES, ABILITY_INIT_OWNER_EFFECTS) ; "
               "tous vivent sous scripts/python, le reste sous data/."),
}

#: Niveau de relique du montage. **1 = REGIME SEPARANT** (cf. l'en-tete). `extraDmg` a 10 paliers.
RELIC_LEVEL = 1
NEURO, ALLY = "tyranNeurothrope", "astraPrimarisPsy"
SECOND_SYNAPSE = "tyranParasite"
TARGET, FAR = "orksNob", "orksRuntherd"

#: LE MONTAGE, NOMME ET REUTILISABLE -- roster, tuiles DRIVEES, board, PV de la cible, niveau de
#: relique. Chaque terme porte sa raison :
#:  * les tuiles sont EXPLICITES (`--place` / `--a-place`) : le porteur a 1 hex de l'allie (bulle
#:    Synapse = 2), l'allie a 1 hex de la cible (son arme ranged porte a 2), le porteur a 2 hex de
#:    la cible (son arme ranged porte a 3) -- rien n'est laisse aux SpawnPoints ;
#:  * `tyranParasite` est le SECOND emetteur `Synapse` : sans lui, le porteur n'est pas dans sa
#:    propre bulle (`includeCenter: false`) et la patte SELF est structurellement eteinte ;
#:  * `--hp-target` sort du regime SATURE : sans lui `aiPredict` clampe ses bornes aux PV restants
#:    de la cible et l'ecart A-B tombe a zero pour une raison etrangere a la relique ;
#:  * `--no-ai` fige la geometrie entre les deux mesures.
MONTAGE = ["--p-units", "%s,%s,%s" % (NEURO, ALLY, SECOND_SYNAPSE),
           "--a-units", "%s,%s" % (TARGET, FAR),
           "--rank", "17", "--board", "MC1_67", "--hp-target", "200000", "--no-ai",
           "--place", "%s:3,2" % NEURO, "--place", "%s:3,3" % ALLY,
           "--place", "%s:2,2" % SECOND_SYNAPSE,
           "--a-place", "%s:3,4" % TARGET, "--a-place", "%s:0,5" % FAR,
           "--equip-relic", "%s:%s:%d" % (NEURO, NORN_CROWN_ABILITY, RELIC_LEVEL)]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _capture(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap) and isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("capture live KO")
    return dv, ob, snap, Board(bg["tiles"], adjacency="evenq")


def _dv_id(dv, visual_id):
    for u in (dv.get("units") or []):
        if u.get("visualId") == visual_id:
            return int(u["id"])
    pytest.skip("unite %s absente de la vue" % visual_id)


def _normal_attack(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    return int(ab["id"])
    pytest.skip("attaque normale introuvable pour %s" % uid)


@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
    """LE MONTAGE, joue une fois : build + pose du Neuroparasite par l'attaque normale PSYCHIQUE du
    Neurothrope. Rend la capture AVANT et la capture APRES -- les deux regimes dont l'ecart isole
    le gate `HasEffect(Target, Neuroparasite)`."""
    rid = build_runner("777", extra=MONTAGE)["rid"]
    dv0, ob0, snap0, board = _capture(rpc, rid)
    neuro, tgt = _dv_id(dv0, NEURO), _dv_id(dv0, TARGET)
    at = _normal_attack(dv0, neuro)
    # `NeuroparasiteAbility$$CreateTrigger` = `On(9 Attack) & get_OwnerIsCaster & NOT HasEffect(
    # Target, 0x4c2) & IsUnit(Target) & CurrentAttackDamageProfilesContain(0xd Psychic)` : l'arme
    # ranged du Neurothrope est Psychic, donc son attaque normale POSE le parasite.
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": neuro, "targetId": tgt, "abilityType": at}}, 90)
    if not _ok(res):
        pytest.skip("pose du Neuroparasite refusee : %r" % (res,))
    dv1, ob1, snap1, _b = _capture(rpc, rid)
    return {"rid": rid, "board": board, "rpc": rpc,
            "avant": (dv0, ob0, snap0), "apres": (dv1, ob1, snap1)}


def _state(env, quand):
    dv, ob, snap = env[quand]
    return load_state(dv, ob, snap, board=env["board"])


def _unit(st, visual_id):
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == visual_id:
            return int(uid)
    pytest.skip("unite %s absente du runner" % visual_id)


def _additive(st, att_vid, tgt_vid):
    """L'additif ATTAQUANT que le port pose pour `att_vid` frappant `tgt_vid` -- le canal exact ou
    `NornCrownEffect` verse son `ForAddition` (`mods.additive`)."""
    a, t = _unit(st, att_vid), _unit(st, tgt_vid)
    mods, _active = attacker_modifiers(st, a, None, is_ranged=True,
                                       target_traits=target_trait_names(st, t),
                                       target_id=t, damage_profile="Psychic")
    return int(mods.additive or 0)


# ----------------------------------------------------------------- 1. la POSE de l'owner-effect
def test_relique_montee_leffet_1492_est_pose_sur_le_porteur(env):
    """MESURE FONDATRICE. `AOwnerEffectTriggeredAbility$$CreateBehaviour` pose `GetEffectType()`
    (`return 0x5d4` = 1492) sur l'Owner a l'init, options VIDES donc PERMANENT."""
    st = _state(env, "avant")
    n = _unit(st, NEURO)
    insts = [e for e in (st.effects.by_unit.get(n) or [])
             if int(getattr(e, "effect_type", -1) or -1) == int(EffectType.NornCrown)
             and not e.consumed]
    assert insts, "l'effet 1492 NornCrown n'est pas pose sur le porteur"
    assert isinstance(insts[0], NornCrownEffect), (
        "1492 retombe sur %s : l'entree EFFECT_CLASSES manque, et la degradation est SILENCIEUSE"
        % type(insts[0]).__name__)
    # Le registre de POSE existe aussi (filet offline : sur un runner live l'effet est de toute
    # facon capte, sa `CreateActiveCondition` etant celle de la base).
    assert ABILITY_INIT_OWNER_EFFECTS.get(NORN_CROWN_ABILITY) == [EffectType.NornCrown.name]


def test_le_niveau_lu_est_le_TERTIAIRE_pas_le_passif(env):
    """#357. `GetAbilityState(effect)` rend l'etat TERTIAIRE de la relique EQUIPEE. Lire l'instance
    rendrait le niveau PASSIF (50 sur tout runner normalise), donc le DERNIER palier."""
    st = _state(env, "avant")
    n = _unit(st, NEURO)
    lvl, mult = triggered_ability_state(st, n, NORN_CROWN_ABILITY)
    assert lvl == RELIC_LEVEL, (
        "niveau tertiaire lu %r au lieu de %d -- le canal `unitAbilityStates` (#357) est muet, et "
        "la magnitude clamperait au dernier palier" % (lvl, RELIC_LEVEL))
    bas = ability_var(NORN_CROWN_ABILITY, "extraDmg", RELIC_LEVEL, multiplier_pct=mult)
    haut = ability_var(NORN_CROWN_ABILITY, "extraDmg", 50, multiplier_pct=mult)
    assert bas != haut, ("regime NON SEPARANT : extraDmg[%d] == extraDmg[50] -- ce montage ne "
                         "pourrait pas distinguer les deux lectures" % RELIC_LEVEL)


# --------------------------------------------------------- 2. le GATE `HasEffect(Neuroparasite)`
def test_sans_parasite_laura_est_MUETTE(env):
    """CONTRE-EPREUVE SANS LE RAIL. `HasEffect(Target@+0x60, 0x4c2, onlyActive: false, 6)` est un
    conjoint du trigger : pas de parasite, pas de bonus. Natif mesure : A - B = 0."""
    st = _state(env, "avant")
    t = _unit(st, TARGET)
    assert EffectType.Neuroparasite.name not in (_target_effect_names(st, t) or ()), \
        "la cible porte deja le parasite AVANT la pose : le montage ne separe rien"
    assert _additive(st, ALLY, TARGET) == 0, \
        "le port accorde l'aura SANS parasite sur la cible -- le gate HasEffect ne mord pas"


def test_avec_parasite_laura_vaut_extraDmg_du_niveau_de_relique(env):
    """LA MESURE. Natif : allie APRES, A - B = +880 = `extraDmg[1]`, sur min ET max."""
    st = _state(env, "apres")
    t = _unit(st, TARGET)
    assert EffectType.Neuroparasite.name in (_target_effect_names(st, t) or ()), \
        "le parasite n'a pas ete pose : la mesure d'APRES ne vaut rien"
    n = _unit(st, NEURO)
    _lvl, mult = triggered_ability_state(st, n, NORN_CROWN_ABILITY)
    attendu = int(ability_var(NORN_CROWN_ABILITY, "extraDmg", RELIC_LEVEL, multiplier_pct=mult))
    assert attendu == 880, "palier de reference change (build ?) : extraDmg[1] = %d" % attendu
    assert _additive(st, ALLY, TARGET) == attendu, (
        "aura portee = %d, natif mesure = %d" % (_additive(st, ALLY, TARGET), attendu))


# ------------------------------------------------------------------- 3. le SELECTEUR, terme a terme
def test_le_beneficiaire_doit_etre_Psyker_ou_Summon(env):
    """`HasTrait(It@+0x68, 0x3ea = Psyker) | HasTrait(It@+0x68, 0x2 = Summon)`. Contre-epreuve par
    RETRAIT du trait sur le substrat d'ENTITE que lit le gate."""
    st = _state(env, "apres")
    a = _unit(st, ALLY)
    traits = target_trait_names(st, a)
    assert UnitTrait.Psyker.name in traits, "le montage a perdu son beneficiaire Psyker"
    from engine.runner.components import StatsComponent
    sc = st.get_entity(a).get_component(StatsComponent)
    garde = list(getattr(sc.ctx, "traits", []) or [])
    try:
        sc.ctx.traits = [x for x in garde
                         if x not in (UnitTrait.Psyker.name, UnitTrait.Summon.name)]
        assert _additive(st, ALLY, TARGET) == 0, \
            "l'aura s'applique a un beneficiaire NI Psyker NI Summon"
    finally:
        sc.ctx.traits = garde


def test_la_bulle_synapse_EXCLUT_le_sujet_lui_meme(env):
    """`BattleQuery$$GetInRangeAuraAmount` balaye `GetSurroundingUnits(target, range, null,
    includeCenter: FALSE)` : le sujet n'est jamais son propre emetteur. MESURE : sans second
    porteur, la patte SELF du Neurothrope vaut 0 ; avec, elle s'allume."""
    st = _state(env, "apres")
    n, a = _unit(st, NEURO), _unit(st, ALLY)
    by_team = _team_synapse_positions(st)
    from engine.runner.components import OwnerComponent, PositionComponent
    team = st.get_entity(n).get_component(OwnerComponent).team
    emetteurs = by_team.get(team) or ()
    assert len(emetteurs) >= 2, (
        "le montage doit porter DEUX emetteurs Synapse (%s + %s) pour que la patte SELF soit "
        "evaluable ; lus : %r" % (NEURO, SECOND_SYNAPSE, emetteurs))
    import hexgeo
    npos = st.get_entity(n).get_component(PositionComponent)
    apos = st.get_entity(a).get_component(PositionComponent)
    npos, apos = (npos.col, npos.row), (apos.col, apos.row)
    autres = [p for p in emetteurs if p != npos]
    assert any(0 < hexgeo.distance(p, npos) <= SYNAPSE_RANGE for p in autres), \
        "aucun emetteur Synapse AUTRE que le porteur a portee : la patte SELF resterait eteinte"
    assert any(0 < hexgeo.distance(p, apos) <= SYNAPSE_RANGE for p in emetteurs), \
        "le beneficiaire n'est pas dans la bulle : le montage ne mesure pas l'aura"
    assert SYNAPSE_TRAIT == UnitTrait.Synapse.name


def test_hors_bulle_synapse_laura_est_MUETTE(env):
    """Contre-epreuve GEOMETRIQUE : on VIDE la table des emetteurs (equivalent a un beneficiaire
    hors de toute bulle) -- le bonus doit disparaitre."""
    st = _state(env, "apres")
    a, t = _unit(st, ALLY), _unit(st, TARGET)
    from engine.entities.effects import aura_attack_damage_bonus_from_allies
    from engine.runner.components import OwnerComponent, PositionComponent
    n = _unit(st, NEURO)
    ent = st.get_entity(n)
    pos = ent.get_component(PositionComponent)
    team = ent.get_component(OwnerComponent).team
    effs = [e for e in (st.effects.by_unit.get(n) or []) if not e.consumed]
    ctx_plein = {"att_id": a, "att_team": team,
                 "att_pos": (st.get_entity(a).get_component(PositionComponent).col,
                             st.get_entity(a).get_component(PositionComponent).row),
                 "att_traits": target_trait_names(st, a),
                 "tgt_effect_names": _target_effect_names(st, t),
                 "team_synapse_positions": _team_synapse_positions(st),
                 "tertiary_ability_state_of":
                     lambda oid, ab: triggered_ability_state(st, int(oid), ab)}
    carriers = [(n, (pos.col, pos.row), team, effs)]
    assert [int(eb.value) for eb in aura_attack_damage_bonus_from_allies(carriers, ctx_plein)
            if isinstance(eb.value, (int, float))], "le montage de reference ne produit rien"
    ctx_vide = dict(ctx_plein, team_synapse_positions={})
    assert not aura_attack_damage_bonus_from_allies(carriers, ctx_vide), \
        "l'aura s'applique HORS de toute bulle Synapse"
    # TRI-ETAT : canal ABSENT != canal mesure et vide -- le gate doit se TAIRE, pas conclure.
    ctx_absent = {k: v for k, v in ctx_plein.items() if k != "team_synapse_positions"}
    assert not aura_attack_damage_bonus_from_allies(carriers, ctx_absent), \
        "canal synapse NON MESURE : le gate doit se taire (jamais permissif)"


def test_effet_1492_hors_registre_retomberait_sur_BaseEffect(env):
    """Garde de NON-REGRESSION du registre : `BaseEffect` n'a AUCUNE des deux pattes -- si l'entree
    disparait, l'aura s'eteint sans une erreur."""
    assert not hasattr(BaseEffect, "_amount")
    assert BaseEffect().create_aura_attack_damage_bonus_for_ally({}) is None
