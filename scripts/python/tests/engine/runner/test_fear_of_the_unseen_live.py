"""FearOfTheUnseen (1115, `tyranDeathleaper` << Deathleaper >>, Tyranids) -- confront LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1 -- cf. `engine/runner/abilities/tyranids.py::fear_of_the_unseen_tree`) :

    enemies = Enemies(Self@0x148,
                      NonSteppableOrObjectUnits(
                          SurroundingUnits(Self@0x148, GetNumberConstant(0x16 = range),
                                           unique=1, includeCenter=1, sel=3), 3), 3)
    Execute( ( If( NOT HasFlag(Self@0x148, 0 = Moved),
                   AddEffect(0x429 = Pinned, stateRef, caster@0x160, enemies, options=default)
                   op_Addition TriggerAbility(enemies, 0x401 = BattleFatigue, ...) )
               op_Addition AddEffect(0x4d6 = 1238 TeleportingIn, stateRef, Self@0x148, turns) )
             op_Addition AddEffect(0x4d7 = 1239 ExtraDamage, stateRef, Self@0x148, turns) )
    avec turns = Sum(TurnsFromRounds(1), Direct(1))

LE CAST NE FAIT AUCUN DEGAT : c'est un POSEUR D'EFFETS. Le DirectDamage annonce par la config 1115
vit dans la PHASE 2 -- l'effet 1239, qui declare `nrOfHits` coups additionnels [minDmg,maxDmg]
DirectDamage sur les attaques MELEE du porteur (`IdunBattle.Entities.Effects.Loki.
FearOfTheUnseen_ExtraDamageEffect$$CreateAdditionalHits` -> `EffectAdditionalHits$$Create`, trigger
`OwnerIsCaster & IsMeleeAttack`).

CE QUE CES TESTS PROUVENT -- DEUX CAS DISCRIMINANTS (ils ne rendent PAS le meme nombre) :
  (A) 2 ennemis dans le disque rayon-`range` -> 2 `Pinned` poses ;
  (B) 1 seul ennemi dedans (l'autre repousse a `range`+1) -> 1 SEUL `Pinned`.
  Dans les deux cas, l'ENSEMBLE des unites affectees LIVE == OFFLINE, et les DEUX effets self
  (1238 / 1239) sont poses sur le Deathleaper des deux cotes.

  (C) GATE `!Moved` (offline, discriminant) : le Deathleaper qui a BOUGE ce tour ne pose NI Pinned NI
      BattleFatigue -- mais pose QUAND MEME les deux effets self (ils sont HORS du `If` natif). C'est
      le point ou une lecture << tout est sous le gate >> se verrait.

  (D) PHASE 2 -- LE DEGAT : l'effet 1239 present ajoute `nrOfHits` coups DirectDamage a l'attaque
      MELEE du porteur. Cas discriminant : MEME attaque, MEME MT, avec vs sans l'effet -> le nombre
      de coups et le total different, et les coups bonus tombent dans la plage config-scalee.

Drive les positions des DEUX camps. Montage via la fixture NOMMEE `ability_cast_harness`
(`_ability_cast_replay.py`). Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _ability_cast_replay import ability_cast_harness   # noqa: E402,F401  (fixture)

import hexgeo                                            # noqa: E402
import gameconfig as GC                                  # noqa: E402
from engine.runner.runner import Runner                  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage   # noqa: E402
from engine.runner.components import (HealthComponent, PositionComponent,    # noqa: E402
                                      UnitComponent, UnitFlagsComponent)
from engine.entities.effect_type import EffectType       # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

DEATHLEAPER = "tyranDeathleaper"
ABILITY = 1115
ENEMIES = "orksNob,tyranTyrantGuard,templAggressor"
BUILD = ["--hp-target", "500000", "--crit", "0,0", "--block-target", "0,0"]

PINNED = int(EffectType.Pinned)                                  # 1065
TELEPORTING_IN = int(EffectType.FearOfTheUnseen_TeleportingIn)   # 1238
EXTRA_DAMAGE = int(EffectType.FearOfTheUnseen_ExtraDamage)       # 1239


# ------------------------------------------------------------------ helpers offline

def _find_vis(state, vis):
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _eff_types(state, uid):
    """Types d'effets ACTIFS portes par `uid` dans l'etat OFFLINE."""
    if state.effects is None:
        return set()
    return {e.effect_type for e in state.effects.by_unit.get(uid, []) if not e.consumed}


def _pos(state, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _offline_cast(state, caster):
    runner = Runner(state).install_default_handlers(20)
    # self-cast : la cible EST le caster (`isSelfCasting = 1` du ctor natif).
    runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=caster, ability_type=ABILITY))
    return runner.ability_handler.last or {}


def _setup(h, distances):
    """Place le Deathleaper sur une tuile D et chaque ennemi a la distance hex demandee.

    `distances` = liste de distances (une par ennemi consomme). Rend `(dl_id, {uid: dist})` ou None
    si la geometrie n'est pas montable. Placements D'ABORD, `reach_my_turn()` ENSUITE (cf.
    `AbilityCastHarness.place`)."""
    dv = h.dview()
    dl = h.by_visual(DEATHLEAPER, dv)
    if dl is None:
        return None
    h.my_player = dl.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < len(distances):
        return None

    for tid in sorted(h.board.by_id):
        D = h.board.coord(tid)
        if not h.board.walkable(tid):
            continue
        slots, ok = [], True
        used = {D}
        for dist in distances:
            cand = [c for c in h.free_neighbours(D, dist, exclude=[u["id"] for u in h.alive()])
                    if c not in used]
            if not cand:
                ok = False
                break
            slots.append(cand[0])
            used.add(cand[0])
        if not ok:
            continue
        # ecarter les ennemis non utilises TRES loin (hors du disque, quel que soit `range`)
        extra = [e["id"] for e in ens[len(distances):]]
        far = [h.board.coord(x) for x in sorted(h.board.by_id)
               if h.board.walkable(x) and hexgeo.distance(h.board.coord(x), D) > 5]
        if len(far) < len(extra):
            continue
        for uid, c in zip(extra, far):
            h.place(uid, c)
        if not h.place(dl["id"], D):
            continue
        placed = {}
        for e, c, dist in zip(ens, slots, distances):
            if not h.place(e["id"], c):
                ok = False
                break
            placed[e["id"]] = dist
        if not ok:
            continue
        if h.reach_my_turn() is None:
            return None
        return dl["id"], placed
    return None


def _cfg_damage_profile():
    """`GetDamageProfile(config, 0)` = `constants.damageProfile` (ORACLE config)."""
    p = ((GC.ability("FearOfTheUnseen") or {}).get("constants") or {}).get("damageProfile")
    assert p, "oracle introuvable : constants.damageProfile de FearOfTheUnseen"
    return str(p)


def _cfg_range():
    """`GetNumberConstant(config, 0x16)` = `constants.range` (ORACLE config, jamais un litteral)."""
    r = ((GC.ability("FearOfTheUnseen") or {}).get("constants") or {}).get("range")
    assert r is not None, "oracle introuvable : constants.range de FearOfTheUnseen"
    return int(r)


# ------------------------------------------------------------------ (A)/(B) les 2 discriminants

@pytest.mark.parametrize("n_in,label", [(2, "2 ennemis dans le rayon"), (1, "1 seul dans le rayon")])
def test_fear_of_the_unseen_live_effects(ability_cast_harness, n_in, label):
    """DISCRIMINANT LIVE : le cast pose `Pinned` sur EXACTEMENT les ennemis du disque rayon-`range`,
    et les DEUX effets self sur le Deathleaper. Les deux parametrages ne posent PAS le meme nombre
    d'effets -- un port qui poserait << sur tout le monde >> ou << sur personne >> echouerait l'un des
    deux."""
    rng_val = _cfg_range()
    h = ability_cast_harness(p_units=DEATHLEAPER, a_units=ENEMIES, extra=BUILD)
    # n_in ennemis DANS le disque (distance 1..range), les autres a range+1 (juste dehors)
    dists = [1 + (i % rng_val) for i in range(n_in)] + [rng_val + 1]
    geom = _setup(h, dists)
    if geom is None:
        pytest.skip("geometrie non montable (%s)" % label)
    dl, placed = geom
    inside = {uid for uid, d in placed.items() if d <= rng_val}
    outside = {uid for uid, d in placed.items() if d > rng_val}
    assert len(inside) == n_in, "setup : %d ennemis dans le rayon != %d" % (len(inside), n_in)

    snap = h.snapshot()
    live = h.cast_live(dl, dl, ABILITY)
    if not live["ok"]:
        pytest.skip("cast live refuse: %s" % str(live["raw"])[:200])
    dv_after = h.dview()
    live_pinned = {uid for uid in placed if "Pinned" in h.effects_of(uid, dv_after)}
    live_self = set(h.effects_of(dl, dv_after))

    st = h.offline_state(snap)
    last = _offline_cast(st, dl)
    assert last.get("ported") is True, "1115 non routee par le handler: %s" % last
    off_pinned = {uid for uid in placed if PINNED in _eff_types(st, uid)}
    off_self = _eff_types(st, dl)

    print("\n[FU %s] range=%d dl=u%d placed=%s" % (label, rng_val, dl, placed))
    print("[FU %s] live pinned=%s self=%s" % (label, sorted(live_pinned), sorted(live_self)))
    print("[FU %s] off  pinned=%s self=%s" % (label, sorted(off_pinned), sorted(off_self)))

    # (1) AUCUN DEGAT au cast (poseur d'effets pur)
    assert not live["damage_by_target"], \
        "le cast ne doit infliger AUCUN degat, live a rendu %s" % live["damage_by_target"]

    # (2) ENSEMBLE des Pinned : live == offline == les ennemis du disque
    assert live_pinned == inside, \
        "live Pinned %s != ennemis du disque %s" % (sorted(live_pinned), sorted(inside))
    assert off_pinned == inside, \
        "offline Pinned %s != ennemis du disque %s" % (sorted(off_pinned), sorted(inside))
    for uid in outside:
        assert uid not in live_pinned and uid not in off_pinned, \
            "u%d est a distance %d > range=%d : il ne doit PAS etre Suppressed" % (uid, placed[uid], rng_val)

    # (3) EFFETS SELF : 1238 et 1239 poses sur le caster, des DEUX cotes.
    assert TELEPORTING_IN in off_self and EXTRA_DAMAGE in off_self, \
        "offline : effets self attendus 1238+1239, obtenu %s" % sorted(off_self)
    assert "FearOfTheUnseen_TeleportingIn" in live_self and "FearOfTheUnseen_ExtraDamage" in live_self, \
        "live : effets self attendus TeleportingIn+ExtraDamage, obtenu %s" % sorted(live_self)


# ------------------------------------------------------------------ (C) gate !Moved

def test_fear_of_the_unseen_moved_gate_refuses_the_whole_cast(ability_cast_harness):
    """DISCRIMINANT << CASTER AYANT BOUGE >> (offline) -- et la MESURE qui a corrige ma lecture.

    Il y a DEUX gardes distinctes sur << le Deathleaper n'a pas bouge >>, et elles ne vivent pas au
    meme etage :
      * le masque de ciblage porte `CasterHasNotMoved` (0x10) -> `IdunBattle.Core.Services.
        TargetingQuery$$GetInvalidCasterReason` REFUSE le cast ENTIER, en amont de toute behaviour
        (`ActiveAbilityOperation$$ExecuteInternal` sort avant le 1er `Execute`) ;
      * l'ExecuteBehaviour porte EN PLUS un `If(NOT HasFlag(Self, Moved), ...)` autour du seul volet
        ENNEMIS.

    MESURE (2026-07-28) : avec le flag `Moved` pose, le port ne materialise AUCUN effet -- ni Pinned,
    ni les deux effets self. C'est le PREMIER gate qui parle, et il est NATIF : le `If` interne est
    donc du code defensif sur ce chemin (il ne peut etre faux que si l'ability est atteinte par une
    voie qui contourne le filtre de ciblage). Le test fige les DEUX faits :
      (1) sans `Moved` -> le cast passe et pose Pinned + les deux effets self ;
      (2) avec `Moved` -> refus complet, avec la RAISON `CasterHasNotMoved`.
    Un port qui aurait oublie le masque (le trou que le cliquet du registre traque) passerait (1)
    mais echouerait (2) : il poserait les effets self."""
    rng_val = _cfg_range()
    h = ability_cast_harness(p_units=DEATHLEAPER, a_units=ENEMIES, extra=BUILD)
    geom = _setup(h, [1, rng_val + 1])
    if geom is None:
        pytest.skip("geometrie non montable")
    dl, placed = geom
    inside = {uid for uid, d in placed.items() if d <= rng_val}
    snap = h.snapshot()

    # --- sans le flag Moved : le volet ennemis s'applique
    st = h.offline_state(snap)
    _offline_cast(st, dl)
    pinned_no_move = {uid for uid in placed if PINNED in _eff_types(st, uid)}
    self_no_move = _eff_types(st, dl)

    # --- avec le flag Moved pose (mirror `IdunBattle.Entities.UnitExtensions$$SetMovedFlag`)
    st2 = h.offline_state(snap)
    e = st2.get_entity(dl)
    fl = e.get_component(UnitFlagsComponent) or e.add_component(UnitFlagsComponent())
    fl.add(UnitFlagsComponent.MOVED)
    last_moved = _offline_cast(st2, dl)
    pinned_moved = {uid for uid in placed if PINNED in _eff_types(st2, uid)}
    self_moved = _eff_types(st2, dl)

    print("\n[FU gate] inside=%s | sans-Moved pinned=%s self=%s | avec-Moved pinned=%s self=%s"
          % (sorted(inside), sorted(pinned_no_move), sorted(self_no_move),
             sorted(pinned_moved), sorted(self_moved)))
    print("[FU gate] verdict du gate avec Moved = %s" % {k: v for k, v in last_moved.items()
                                                        if k in ("ported", "invalid_target")})
    # (1) sans Moved : le cast passe entierement
    assert pinned_no_move == inside, "sans Moved : Pinned attendu sur %s" % sorted(inside)
    assert TELEPORTING_IN in self_no_move and EXTRA_DAMAGE in self_no_move, \
        "sans Moved : les deux effets self doivent etre poses (obtenu %s)" % sorted(self_no_move)
    # (2) avec Moved : REFUS COMPLET, et la raison est bien `CasterHasNotMoved` (0x10)
    assert last_moved.get("invalid_target") == int(TR.CasterHasNotMoved), \
        ("avec Moved, le cast doit etre REFUSE avec la raison CasterHasNotMoved (0x10) -- obtenu %s. "
         "Une raison nulle signifie que le masque `TARGETING_OPTIONS` est absent ou faux."
         % last_moved.get("invalid_target"))
    assert not pinned_moved, "avec Moved : refus complet, aucun Pinned attendu"
    assert TELEPORTING_IN not in self_moved and EXTRA_DAMAGE not in self_moved, \
        ("avec Moved : refus complet -> AUCUN effet self non plus (obtenu %s). En voir un signifierait "
         "que la behaviour s'est executee malgre le gate de ciblage." % sorted(self_moved))


# ------------------------------------------------------------------ (D) PHASE 2 : le DirectDamage

def test_fear_of_the_unseen_extra_damage_adds_melee_hits(ability_cast_harness):
    """PHASE 2 -- LE DEGAT de l'ability. L'effet 1239 declare `nrOfHits` coups additionnels
    [minDmg,maxDmg] DirectDamage sur les attaques MELEE du porteur (canal #179). Discriminant : la
    MEME attaque normale, depuis le MEME etat et le MEME MT, AVEC vs SANS l'effet -- le nombre de
    coups et le total different, et le surplus tombe dans la plage config-scalee."""
    rng_val = _cfg_range()
    h = ability_cast_harness(p_units=DEATHLEAPER, a_units=ENEMIES, extra=BUILD)
    geom = _setup(h, [1, rng_val + 1])
    if geom is None:
        pytest.skip("geometrie non montable")
    dl, placed = geom
    victim = min(uid for uid, d in placed.items() if d == 1)     # adjacent -> attaque MELEE
    snap = h.snapshot()

    # --- SANS l'effet : attaque normale de reference
    st_ref = h.offline_state(snap)
    r_ref = Runner(st_ref).install_default_handlers(20)
    r_ref.apply(AttackUnitMessage(attacker_id=dl, target_id=victim))
    ref = r_ref.damage_handler.last or {}
    ref_hits = list((ref.get("per_hit") or []))

    # --- AVEC l'effet : on caste 1115 d'abord (il se pose sur le caster), puis LA MEME attaque
    st_eff = h.offline_state(snap)
    _offline_cast(st_eff, dl)
    assert EXTRA_DAMAGE in _eff_types(st_eff, dl), "l'effet 1239 n'a pas ete pose par le cast"
    # DECOMPOSITION PAR ETAGE : ce que le canal #179 VOIT reellement (si la liste est vide alors que
    # l'effet est present, le probleme est dans l'enumeration/le gate, pas dans l'effet).
    from engine.runner.operations.additional_hits import collect_additional_hit_groups
    from engine.runner.components import HealthComponent as _HC
    _hc = st_eff.get_entity(dl).get_component(_HC)
    _act = (st_eff.effects.active_effects(dl, {"hp": _hc.hp if _hc else None})
            if st_eff.effects is not None else [])
    _grp = collect_additional_hit_groups(st_eff, dl, victim, _act, True, [])
    print("[FU dmg] effets actifs du porteur = %s" % [e.name for e in _act])
    print("[FU dmg] groupes vus par le canal #179 (is_melee=True) = %s" % _grp)
    # on re-cale le MT sur le meme etat pre-attaque que la reference pour ne comparer QUE le canal
    st_eff.rng = h.offline_state(snap).rng
    r_eff = Runner(st_eff).install_default_handlers(20)
    r_eff.apply(AttackUnitMessage(attacker_id=dl, target_id=victim))
    got = r_eff.damage_handler.last or {}
    got_hits = list((got.get("per_hit") or []))

    cst = (GC.ability("FearOfTheUnseen") or {}).get("constants") or {}
    n_bonus = int(cst["nrOfHits"])
    # OU MESURER : les coups du canal #179 sont des SOUS-OPERATIONS de degat (mirror
    # `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`), executees
    # APRES les coups d'arme et au profil PROPRE du groupe -> ils ne figurent PAS dans le `per_hit` de
    # l'arme. Ils vivent dans la cle `additional_hits` du resultat, et se voient sur les PV de la cible.
    ah_ref = ref.get("additional_hits")
    ah_got = got.get("additional_hits")
    print("\n[FU dmg] victime=u%d | arme sans effet %s | arme avec effet %s | nrOfHits=%d"
          % (victim, ref_hits, got_hits, n_bonus))
    print("[FU dmg] canal #179 : sans effet=%s | avec effet=%s" % (ah_ref, ah_got))

    assert ref_hits, "l'attaque de reference n'a inflige aucun coup (setup a revoir)"
    # (1) les coups d'ARME sont INCHANGES : le canal est une sous-operation SEPAREE, pas un
    #     gonflement du volet arme (un port qui aurait fondu les deux casserait ici).
    assert got_hits == ref_hits, \
        "les coups d'ARME ont bouge (%s -> %s) : le canal #179 ne doit pas les modifier" % (ref_hits, got_hits)
    # (2) SANS l'effet, aucun groupe ; AVEC, exactement `constants.nrOfHits` coups au profil du groupe.
    assert ah_ref is None, "aucun coup additionnel attendu sans l'effet 1239, obtenu %s" % ah_ref
    assert ah_got is not None, "le canal #179 n'a produit AUCUNE sous-operation avec l'effet 1239"
    assert ah_got["groups"] == 1 and ah_got["hits"] == n_bonus, \
        ("canal #179 : %d groupe(s) / %d coups != 1 groupe / constants.nrOfHits=%d"
         % (ah_got["groups"], ah_got["hits"], n_bonus))
    assert ah_got["profiles"] == [_cfg_damage_profile()], \
        "profil des coups bonus %s != constants.damageProfile" % ah_got["profiles"]
    assert ah_got["total"] > 0 and len(ah_got["per_hit"]) == n_bonus, \
        "coups bonus attendus : %d valeurs > 0, obtenu %s" % (n_bonus, ah_got["per_hit"])
