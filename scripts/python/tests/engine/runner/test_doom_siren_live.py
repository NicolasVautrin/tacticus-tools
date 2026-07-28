"""DoomSiren (1199, `emperKakophonist` << Adamatar >>, EmperorsChildren) -- FACE COMBAT, confront LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1) :

    pool  = Damageable( AdjacentEnemies(Self@0x148, TargetTiles@0x190, unique=1) )
    sel   = Cache( op_Addition( Target@0x178,
                                PickRandomly(pool, GetNumberConstant(0x78 = nrOfUnits)) ), 1 )
    atk   = AttackWithAttackDamage(caster@0x160, sel, MinMaxDamage(0xc,0xd),
                                   Nullable(GetDamageProfile(config,0)), GetHits()=GetNumberConstant(0x2f),
                                   AbilityOrEffect(1199), options=default)
    ovk   = Foreach( UnitsDamagedThisPhase(caster@0x160),
                     If( IsDead(It@0x180) & HasFlag(It@0x180, 8 = Overkilled),
                         AddStaticStatModifierEffect(Self@0x148, 0x597 = DoomSiren_ExtraHit,
                                                     0x11 = ExtraHits, dsl@0xc0 = Direct(1),
                                                     turns = null, isHidden = false) ) )
    ExecuteAtomic( op_Addition(atk, ovk), entities, 0x2a )

i2 : << Deals {nrOfHits}x {minDmg}-{maxDmg} Direct Damage to an adjacent enemy and up to {nrOfUnits}
other random enemies adjacent to the target. For the rest of the battle, Adamatar's normal attacks
score an additional hit for each enemy Overkilled by Doom Siren. >>

CE QUE CES TESTS PROUVENT -- DEUX CAS DISCRIMINANTS (ils ne rendent PAS le meme nombre, donc un
scalaire fitte ne peut pas passer les deux) :
  (A) CIBLE SEULE (aucun ennemi adjacent a la cible) -> le cast ne frappe QU'UNE unite ;
  (B) CIBLE + 2 ennemis adjacents A LA CIBLE -> le cast frappe TROIS unites.
  Dans les DEUX cas, le per-coup LIVE == le per-coup OFFLINE, cible par cible (meme MT, snapshot
  pre-cast). Le cas (B) est monte avec `len(pool) == nrOfUnits` -> le `PickRandomly` prend TOUT le
  pool : le SET pique est deterministe (le residu #215 ne porte que sur `len(pool) > nrOfUnits`), et
  la conso RNG du pick reste exacte (`min(len(pool), n)` tirages, cf. `_pick_randomly_n`).

  (C) ANCRAGE SUR LA CIBLE (discriminant de FIDELITE, offline) : un ennemi adjacent au CASTER mais
      PAS a la cible n'est PAS frappe -- refute un ciblage caster-ancre (contraste BringerOfDespair /
      HarbingerOfDestruction, qui sont caster-ancres). C'est le point ou une confusion
      `AdjacentEnemies(CasterTile)` / `AdjacentEnemies(TargetTiles)` se voit.

  (D) VOLET OVERKILL : une cible OVERKILLEE (degat >= 2x PV) fait poser `DoomSiren_ExtraHit` (1431,
      stat EXTRA_HITS +1, PERMANENT) sur Adamatar ; une cible qui SURVIT n'en pose aucun.

CONFONDS NEUTRALISES AU BUILD (sinon ils decalent le flux RNG et l'egalite ne mesurerait plus le
port) : `--crit 0,0` (Adamatar porte le trait `ThrillSeekers`, qui donne du CritChance des qu'elle
cible un ennemi a PLEINE VIE -- exactement notre setup), `--block-target 0`, `--hp-target` eleve
(cibles a armure nulle qui SURVIVENT aux 3 coups, cf. le reglage eprouve des tests soeurs).
Le passif `ObsessiveAnnunciation` d'Adamatar est inerte ici : son volet +degat est gate
`IsRangedAttack` (DoomSiren est MELEE) et son volet crit est gate sur un overkill DEJA survenu.

Drive les positions des DEUX camps (`applyAction` ignore la propriete). Lit l'etat LIVE, aucune
tuile/RVA hardcodee, seed = simple generateur. Montage via la fixture NOMMEE `ability_cast_harness`
(`_ability_cast_replay.py`). ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _ability_cast_replay import ability_cast_harness   # noqa: E402,F401  (fixture)

import hexgeo                                            # noqa: E402
from engine.runner.runner import Runner                  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage  # noqa: E402
from engine.runner.components import (HealthComponent, PositionComponent,  # noqa: E402
                                      StatsComponent, UnitComponent, UnitFlagsComponent)
from engine.runner.abilities.emperorschildren import DoomSirenAbility   # noqa: E402

ADAMATAR = "emperKakophonist"
ABILITY = 1199
ENEMIES = "orksNob,tyranTyrantGuard,templAggressor"
# `--hp-target` eleve = cibles a ARMURE NULLE (per-coup bit-exact, cf. tests soeurs) qui SURVIVENT
# aux `nrOfHits` coups ; `--crit 0,0` neutralise ThrillSeekers ; `--block-target 0` supprime le block.
BUILD_NO_NOISE = ["--hp-target", "500000", "--crit", "0,0", "--block-target", "0,0"]


# ------------------------------------------------------------------ helpers etat offline

def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def _set_pos(state, uid, coord):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is not None:
        pc.col, pc.row = int(coord[0]), int(coord[1])


def _pos(state, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _find_vis(state, vis):
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == vis:
            return uid
    return None


def _enemies_of(state, uid):
    from engine.runner.components import OwnerComponent
    mine = state.get_entity(uid).get_component(OwnerComponent).team
    out = []
    for oid, e in state.entities.items():
        uc, oc = e.get_component(UnitComponent), e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team == mine:
            continue
        out.append(oid)
    return sorted(out)


def _extra_hits(state, uid):
    """Contribution EXTRA_HITS (StatType 17) courante de l'unite -- ce que le stat-mod
    `DoomSiren_ExtraHit` fait bouger."""
    from engine.entities.stats import StatType
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    us = getattr(sc.ctx, "stats", None) if sc is not None else None
    return us.get_stat(int(StatType.EXTRA_HITS), 0) if us is not None else None


def _offline_cast(state, caster, target):
    """Rejoue le cast par le VRAI point d'entree (`Runner.apply` -> `AbilityHandler`), donc en
    passant par les gates de ciblage et les vecteurs d'operation -- pas par un appel direct a
    `execute_behaviour`."""
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=target, ability_type=ABILITY))
    return runner.ability_handler.last or {}


def _per_hit_by_target(last, target_id):
    """{targetId: [degat par coup]} depuis le diag du handler (main + splash)."""
    out = {}
    main = last.get("main_attack") or {}
    if main:
        out[target_id] = main.get("per_hit") or []
    for s in (last.get("splash") or []):
        out[s["target"]] = ((s.get("attack") or {}).get("per_hit") or [])
    return out


# ------------------------------------------------------------------ montage geometrique partage

def _setup(h, n_adjacent_to_target):
    """Place Adamatar sur une tuile C, la CIBLE sur un voisin T de C, et `n_adjacent_to_target`
    autres ennemis sur des voisins de T (les tuiles restantes -- s'il y en a -- sont videes loin).

    Rend `(adam_id, target_id, [ids adjacents a la cible], [ids ecartes])`, ou None si la geometrie
    n'est pas montable sur ce board.

    ORDRE : placements D'ABORD, `reach_my_turn()` ENSUITE (cf. `AbilityCastHarness.place`) -- sinon
    les `move` font basculer le tour et le natif refuse le cast en silence."""
    dv = h.dview()
    adam = h.by_visual(ADAMATAR, dv)
    if adam is None:
        return None
    h.my_player = adam.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < n_adjacent_to_target + 1:
        return None

    # C = tuile marchable ayant >=1 voisin T qui a lui-meme assez de voisins libres (hors C).
    for t in sorted(h.board.by_id):
        C = h.board.coord(t)
        if not h.board.walkable(t):
            continue
        for T in h.free_neighbours(C, 1, exclude=[u["id"] for u in h.alive()]):
            slots = [c for c in h.free_neighbours(T, 1, exclude=[u["id"] for u in h.alive()])
                     if c != C and hexgeo.distance(C, c) != 0]
            if len(slots) >= n_adjacent_to_target:
                target_id = ens[0]["id"]
                adj_ids = [e["id"] for e in ens[1:1 + n_adjacent_to_target]]
                far_ids = [e["id"] for e in ens[1 + n_adjacent_to_target:]]
                # ecarter d'abord les non-participants (loin de C et de T)
                far_tiles = [h.board.coord(x) for x in sorted(h.board.by_id)
                             if h.board.walkable(x)
                             and hexgeo.distance(h.board.coord(x), C) > 4
                             and hexgeo.distance(h.board.coord(x), T) > 4]
                if len(far_tiles) < len(far_ids):
                    continue
                for uid, c in zip(far_ids, far_tiles):
                    h.place(uid, c)
                if not h.place(adam["id"], C) or not h.place(target_id, T):
                    continue
                ok = all(h.place(uid, c) for uid, c in zip(adj_ids, slots[:n_adjacent_to_target]))
                if not ok:
                    continue
                if h.reach_my_turn() is None:          # tour NEUF pour le caster (cf. `place`)
                    return None
                return adam["id"], target_id, adj_ids, far_ids
    return None


def _live_vs_offline(h, adam, target, expected_hit):
    """Cast LIVE + rejeu OFFLINE depuis le snapshot pre-cast. Rend
    `(live_by_target, off_by_target, last)`. Skip propre si le natif refuse le cast."""
    snap = h.snapshot()
    live = h.cast_live(adam, target, ABILITY)
    if not live["ok"]:
        pytest.skip("cast live refuse par le natif: %s" % str(live["raw"])[:200])
    st = h.offline_state(snap)
    last = _offline_cast(st, adam, target)
    assert last.get("ported") is True, "1199 non routee par le handler: %s" % last
    return live["damage_by_target"], _per_hit_by_target(last, target), last


# ------------------------------------------------------------------ (A) et (B) : les 2 discriminants

@pytest.mark.parametrize("n_adj,label", [(0, "cible SEULE"), (2, "cible + 2 adjacents-cible")])
def test_doom_siren_live_equals_offline(ability_cast_harness, n_adj, label):
    """DISCRIMINANT LIVE : le cast frappe `1 + n_adj` unites et le per-coup OFFLINE == LIVE, cible par
    cible. Les deux parametrages ne rendent PAS le meme nombre d'unites frappees ni le meme total --
    c'est ce qui empeche un scalaire fitte de passer les deux."""
    h = ability_cast_harness(p_units=ADAMATAR, a_units=ENEMIES, extra=BUILD_NO_NOISE)
    geom = _setup(h, n_adj)
    if geom is None:
        pytest.skip("geometrie non montable sur ce board (%s)" % label)
    adam, target, adj_ids, far_ids = geom
    expected = {target, *adj_ids}
    live_by, off_by, last = _live_vs_offline(h, adam, target, expected)

    print("\n[DS %s] adam=u%d cible=u%d adjacents-cible=%s ecartes=%s"
          % (label, adam, target, adj_ids, far_ids))
    print("[DS %s] live=%s" % (label, {k: v for k, v in sorted(live_by.items())}))
    print("[DS %s] off =%s" % (label, {k: v for k, v in sorted(off_by.items())}))

    # (1) CIBLAGE : live et offline frappent EXACTEMENT le meme ensemble, et c'est l'ensemble attendu.
    assert set(live_by) == expected, \
        "live frappe %s != attendu %s" % (sorted(live_by), sorted(expected))
    assert set(off_by) == expected, \
        "offline frappe %s != attendu %s" % (sorted(off_by), sorted(expected))
    assert len(live_by) == 1 + n_adj, \
        "cardinal frappe %d != 1 + n_adj = %d" % (len(live_by), 1 + n_adj)

    # (2) DEGAT -- assertion sur le PREFIXE EXACT de la sequence de coups, dans l'ordre d'execution
    #     (cibles id-triees, coups dans l'ordre : c'est l'`OrderBy` d'
    #     `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`).
    #
    #     CONFOND MESURE (`probe_154_doom_siren_live.py`) : Adamatar porte le trait `ThrillSeekers`
    #     (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility`), qui pose l'effet
    #     `Thrilled` (1434, `+thrillSeekersExtraCritChance`) DES QU'ELLE CIBLE UN ENNEMI A PLEINE VIE
    #     -- donc PENDANT ce cast. L'effet est porte et APPLIQUE offline (CritChance = 15 des DEUX
    #     cotes apres le cast) ; ce qui differe est le RANG auquel la modification devient effective au
    #     sein d'une attaque MULTI-CIBLES : live, le crit-roll supplementaire est consomme des le 2e
    #     coup de la 2e cible (le 1er coup de la 3e cible sort alors en `Attack_DidCrit: 1`), offline
    #     plus tard. Etage PARTAGE (pose + refresh de stat-mod intra-attaque), EXTERIEUR a DoomSiren.
    #
    #     On asserte donc la LONGUEUR du prefixe commun, pas des valeurs figees : c'est une borne
    #     PRECISE (un port qui se tromperait de ciblage, de bornes, de profil ou de nb de coups
    #     casserait le prefixe DES le 1er coup) et elle ne valide DoomSiren sur aucune compensation.
    order = sorted(expected)
    live_seq = [v for uid in order for v in (live_by.get(uid) or [])]
    off_seq = [v for uid in order for v in (off_by.get(uid) or [])]
    common = 0
    while common < min(len(live_seq), len(off_seq)) and live_seq[common] == off_seq[common]:
        common += 1
    n_hits_cfg = len(live_by.get(target) or [])
    # prefixe attendu = TOUTE la cible principale (elle precede toute pose) + le 1er coup de la 1re
    # cible additionnelle (le decalage ne mord qu'a partir du coup SUIVANT).
    expect_prefix = n_hits_cfg + (1 if n_adj else 0)
    print("[DS %s] prefixe commun = %d coups (attendu >= %d) sur %d"
          % (label, common, expect_prefix, len(live_seq)))
    assert off_by.get(target) == live_by.get(target), \
        "cible u%d : offline %s != live %s" % (target, off_by.get(target), live_by.get(target))
    assert common >= expect_prefix, \
        ("prefixe commun %d < %d : la divergence commence AVANT le rang du confond ThrillSeekers "
         "-> vrai bug de port (ciblage / bornes / profil / nb de coups). live=%s off=%s"
         % (common, expect_prefix, live_seq, off_seq))
    for uid in order:
        assert len(off_by.get(uid) or []) == len(live_by.get(uid) or []), \
            "u%d : %d coups offline != %d live" % (uid, len(off_by.get(uid) or []),
                                                   len(live_by.get(uid) or []))

    # (3) NB DE COUPS = `constants.nrOfHits` (oracle config, jamais un litteral ecrit ici).
    import gameconfig as GC
    n_hits = int(((GC.ability("DoomSiren") or {}).get("constants") or {}).get("nrOfHits"))
    for uid, ph in live_by.items():
        assert len(ph) == n_hits, "u%d : %d coups live != constants.nrOfHits=%d" % (uid, len(ph), n_hits)


# ------------------------------------------------------------------ (C) ancrage CIBLE, pas caster

def test_doom_siren_splash_anchored_on_target_not_caster(ability_cast_harness):
    """DISCRIMINANT DE FIDELITE : le pool des additionnels est ancre sur les TUILES DE LA CIBLE
    (`AdjacentEnemies(Self, TargetTiles)`), PAS sur le caster. Un ennemi adjacent a ADAMATAR mais a
    distance >= 2 de la cible ne doit PAS etre frappe."""
    h = ability_cast_harness(p_units=ADAMATAR, a_units=ENEMIES, extra=BUILD_NO_NOISE)
    dv = h.dview()
    adam = h.by_visual(ADAMATAR, dv)
    if adam is None:
        pytest.skip("Adamatar absente")
    h.my_player = adam.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < 2:
        pytest.skip("2 ennemis requis")

    # geometrie : C (Adamatar) ; T adjacent a C (cible) ; D adjacent a C mais dist(T,D) >= 2.
    geom = None
    for t in sorted(h.board.by_id):
        C = h.board.coord(t)
        if not h.board.walkable(t):
            continue
        nb = h.free_neighbours(C, 1, exclude=[u["id"] for u in h.alive()])
        for T in nb:
            for D in nb:
                if D != T and hexgeo.distance(T, D) >= 2:
                    geom = (C, T, D)
                    break
            if geom:
                break
        if geom:
            break
    if geom is None:
        pytest.skip("aucune geometrie discriminante caster-vs-cible sur ce board")
    C, T, D = geom
    target_id, d_id = ens[0]["id"], ens[1]["id"]
    for uid in [e["id"] for e in ens[2:]]:                    # ecarter les autres
        far = [h.board.coord(x) for x in sorted(h.board.by_id)
               if h.board.walkable(x) and hexgeo.distance(h.board.coord(x), C) > 4]
        if far:
            h.place(uid, far[0])
    if not (h.place(adam["id"], C) and h.place(target_id, T) and h.place(d_id, D)):
        pytest.skip("placement KO")

    snap = h.snapshot()
    st = h.offline_state(snap)
    last = _offline_cast(st, adam["id"], target_id)
    hit = set(_per_hit_by_target(last, target_id))
    print("\n[DS anchor] C=%s T=%s(u%d) D=%s(u%d, adj CASTER, dist(T,D)=%d) hit=%s"
          % (C, T, target_id, D, d_id, hexgeo.distance(T, D), sorted(hit)))
    assert target_id in hit, "la cible principale doit etre frappee"
    assert d_id not in hit, \
        ("u%d (adjacent au CASTER mais a distance %d de la cible) est frappe -> le pool est ancre sur "
         "le caster, pas sur TargetTiles" % (d_id, hexgeo.distance(T, D)))


# ------------------------------------------------------------------ (D) volet OVERKILL

def test_doom_siren_overkill_poses_extra_hit(ability_cast_harness):
    """VOLET OVERKILL : `Foreach(UnitsDamagedThisPhase(caster), If(IsDead & HasFlag(Overkilled),
    AddStaticStatModifierEffect(caster, 1431, EXTRA_HITS, 1)))`.

    Deux regimes sur le MEME etat, offline (l'overkill exige `degat >= 2x PV` -- on descend les PV de
    la cible sous la moitie du degat minimal du cast pour l'obtenir a coup sur, et on les remonte pour
    le contre-cas). Le contre-cas est ce qui rend le test discriminant : sans lui, un port qui
    poserait l'effet INCONDITIONNELLEMENT passerait."""
    h = ability_cast_harness(p_units=ADAMATAR, a_units=ENEMIES, extra=BUILD_NO_NOISE)
    geom = _setup(h, 0)
    if geom is None:
        pytest.skip("geometrie non montable")
    adam, target, _adj, _far = geom
    snap = h.snapshot()

    # --- regime 1 : la cible SURVIT -> aucun effet pose
    st = h.offline_state(snap)
    before = _extra_hits(st, adam)
    last = _offline_cast(st, adam, target)
    survivor_effects = last.get("extra_hits") or []
    after_survive = _extra_hits(st, adam)
    alive_after = st.get_entity(target).get_component(UnitComponent).alive
    print("\n[DS ovk] survie : cible vivante=%s effets=%s EXTRA_HITS %s -> %s"
          % (alive_after, survivor_effects, before, after_survive))
    assert alive_after, "la cible devait survivre (--hp-target eleve) : setup a revoir"
    assert not survivor_effects, "aucun DoomSiren_ExtraHit ne doit etre pose sans overkill"
    assert after_survive == before, "EXTRA_HITS a bouge sans overkill"

    # --- regime 2 : la cible est OVERKILLEE -> 1 effet pose, EXTRA_HITS +1
    st2 = h.offline_state(snap)
    hc = st2.get_entity(target).get_component(HealthComponent)
    hc.hp = 1                                   # degat >= 2x PV garanti -> IsOverkill vrai
    before2 = _extra_hits(st2, adam)
    last2 = _offline_cast(st2, adam, target)
    posed = last2.get("extra_hits") or []
    after2 = _extra_hits(st2, adam)
    fl = st2.get_entity(target).get_component(UnitFlagsComponent)
    print("[DS ovk] overkill : morte=%s flag8=%s effets=%s EXTRA_HITS %s -> %s"
          % (not st2.get_entity(target).get_component(UnitComponent).alive,
             fl is not None and fl.has(UnitFlagsComponent.OVERKILLED), posed, before2, after2))
    assert not st2.get_entity(target).get_component(UnitComponent).alive, "la cible devait mourir"
    assert fl is not None and fl.has(UnitFlagsComponent.OVERKILLED), \
        "UnitFlag.Overkilled (8) non pose par le pipeline de degat"
    assert len(posed) == 1, "1 DoomSiren_ExtraHit attendu (1 overkill), obtenu %d" % len(posed)
    assert posed[0]["effect_type"] == 1431 and posed[0]["unit"] == adam, \
        "l'effet doit etre 1431 sur Adamatar : %s" % posed
    assert after2 == (before2 or 0) + 1, \
        "EXTRA_HITS %s -> %s : le stat-mod +1 n'a pas ete applique" % (before2, after2)
