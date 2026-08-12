"""#950 -- CONFRONTATION LIVE des deux passifs portes : `TerrorsLament` (`eldarJainZar`) et
`ToughToKill` (`astraDreir`).

CE QUE CE PROBE MESURE, ET POURQUOI LA GEOMETRIE EST CALCULEE PLUTOT QUE SUBIE
-----------------------------------------------------------------------------
`TerrorsLament` pose DEUX owner-effects PERMANENTS sur Jain Zar (1119 degat / 1120 coups) dont le
trigger ne porte NI sur la cible du coup NI sur un `CreateTargetSelector` : il lit l'ATTAQUANT
(`IsAdjacent(Caster, Owner, 3) & AreEnemies(Owner, Caster, 0) & IsMeleeAttack`, plus
`NOT HasTrait(Caster, Immune)` pour la seule moitie COUPS). Le port doit donc mordre dans DEUX
regimes de population, et le seul discriminant honnete est **la position de Jain Zar, tout le reste
egal** :

    TILE_V      (0,0)  victime
    TILE_A      (0,1)  attaquant, ADJACENT a la victime
    TILE_J_NEAR (0,2)  Jain Zar ADJACENTE A L'ATTAQUANT et a DISTANCE 2 de la victime
    TILE_J_FAR  (0,4)  Jain Zar a DISTANCE 3 de l'attaquant -- le TEMOIN

Les quatre tuiles sont `Grass` a l'elevation 3 sur `MC1_67` (verifie offline ET assertionne live
contre le `boardGraph` du runner) : aucun terme d'elevation, de cover ni de terrain ne separe les
bras. `TILE_J_NEAR` etant a 2 hex de la victime, un port qui lirait l'adjacence a la CIBLE au lieu
de l'adjacence a l'ATTAQUANT rendrait un bras `aura` identique au temoin.

LES BRAS
--------
  `tl_aura` : Jain Zar en `J_NEAR`, l'attaquant frappe la VICTIME  -> les deux reductions doivent
              s'appliquer alors que Jain Zar n'est ni l'attaquant ni la cible (patte AURA) ;
  `tl_away` : Jain Zar en `J_FAR`, meme attaque                    -> TEMOIN, aucune reduction ;
  `tl_self` : Jain Zar EST la cible, l'attaquant lui est adjacent  -> patte SELF ;
  `ttk`     : `astraDreir` est la cible, l'attaquant a `--crit 100,700` -> les deux canaux CRIT ;
  `ttk_ctl` : meme attaque contre une cible SANS `ToughToKill`     -> TEMOIN du bras precedent.

Chaque bras capture l'etat (`decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`) AVANT
l'attaque, joue l'attaque NATIVE (ledger par coup), puis REJOUE la meme attaque OFFLINE sur le meme
`State` et le meme flux RNG. Le verdict fort est **port == natif A L'UNITE, par coup**, dans TOUS
les bras -- pas un ecart fitte.

MUTATION (contre-epreuve). `--mutate` RETIRE du registre les entrees `EFFECT_CLASSES` des trois
effets portes (1119, 1120, 1472) : c'est EXACTEMENT l'etat d'`origin/master`. Le rejeu doit alors
DIVERGER du natif dans les bras porteurs et rester EGAL dans les temoins. Un bras mutant VERT est le
resultat suspect (mutation qui ne mord pas), pas une bonne nouvelle -- le verdict le dit.

REGEN (`ToughToKill_HealAbility`). Bras `ttk` : apres l'attaque on rend la main, et on lit le PV de
Dreir au debut de SON tour. Cote port, `turn_start_other_triggers(state, <son joueur>)` est appele
sur le `State` capte APRES l'attaque -- meme vecteur natif (`On(0x13 = TurnStart_Other)`), meme
foyer que `LivingMetal` et `TimeFlux`.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import hexgeo                                                     # noqa: E402
from probe_r6_round_materialize import _mkrpc                     # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait           # noqa: E402

BOARD = "MC1_67"
SEED = "777"
#: 6 coups MELEE ; son passif `DestroyTheWitch` est gate `HasTrait(target, Psyker)` -- ni `orksNob`
#: ni `eldarJainZar` ni `astraDreir` ne le portent, donc il est INERTE dans tous les bras.
ATT = "templHelbrecht"
#: cible neutre : son passif `SmashaEad` est un bonus crit OFFENSIF (elle ne l'exerce jamais ici,
#: elle ne fait qu'encaisser), et elle ne projette RIEN sur ses allies.
VICTIM = "orksNob"
JZ = "eldarJainZar"
DREIR = "astraDreir"
#: SPECTATEUR de MON camp, place a l'autre bout du plateau et qui n'agit JAMAIS. Il n'existe que
#: pour empecher la CLOTURE AUTOMATIQUE de mon tour apres l'attaque mesuree : sans lui le natif
#: enchaine EndTurn/ChangeTurn/StartTurn DANS la meme cascade, la regen de `ToughToKill` tombe au
#: milieu du ledger d'attaque, et la capture d'apres montre un porteur DEJA soigne (mesure vide).
#: `CamoCloak` est une reduction de degat SUR LUI-MEME : il n'attaque pas, il n'est pas attaque.
FILLER = "ultraEliminatorSgt"
#: ATTAQUANT `Immune` du bras `tl_immune` (#987, residu #950-r1). `darkaBossLion` est le SEUL des
#: six porteurs `Immune` a arme de melee dont le profil est PUREMENT melee (`4hmp40`) : les cinq
#: autres portent aussi une arme a distance (`deathBossMortarion` 7hmp20/3hR2p100,
#: `tyranBossHiveTyrantLeviathan` 5hmp30/2hR2p100, `tauBossRiptide` 3hmp1/3hR3p15) ou ne montent
#: pas (`admecBossBelisarius` -> `ShroudPsalm inconnu du build`, refus mesure). Palier `:4` (le
#: vrai boss) et non `:1` : la reduction vaut `dmgReduction[50] x 180 % = 797` par coup, qui doit
#: rester LISIBLE devant le degat de base.
BOSS_IMMUNE = "darkaBossLion:4"

TILE_V = (0, 0)
TILE_A = (0, 1)
TILE_J_NEAR = (0, 2)
TILE_J_FAR = (0, 4)
TILE_F = (3, 8)

TL_DMG = 1119          # EffectType TerrorsLament_DamageReduction
TL_HITS = 1120         # EffectType TerrorsLament_HitReduction
TTK = 1472             # EffectType ToughToKill

#: les bras : qui est en face, ou, et qui prend le coup.
ARMS = {
    "tl_aura": {"carrier": JZ, "carrier_tile": TILE_J_NEAR, "victim": VICTIM,
                "victim_tile": TILE_V, "target": "victim", "crit": "0,0"},
    "tl_away": {"carrier": JZ, "carrier_tile": TILE_J_FAR, "victim": VICTIM,
                "victim_tile": TILE_V, "target": "victim", "crit": "0,0"},
    "tl_self": {"carrier": JZ, "carrier_tile": TILE_V, "victim": VICTIM,
                "victim_tile": TILE_J_FAR, "target": "carrier", "crit": "0,0"},
    "ttk": {"carrier": DREIR, "carrier_tile": TILE_V, "victim": VICTIM,
            "victim_tile": TILE_J_FAR, "target": "carrier", "crit": "100,700"},
    "ttk_ctl": {"carrier": DREIR, "carrier_tile": TILE_J_FAR, "victim": VICTIM,
                "victim_tile": TILE_V, "target": "victim", "crit": "100,700"},
    # --- #987 : le conjoint `NOT HasTrait(Caster, 0x19 = Immune)`, PROPRE a la moitie COUPS -------
    # Attendu : le degat reste reduit (1119 n'a PAS ce conjoint) et le nombre de coups NE l'est PAS.
    # Voie RETENUE : le trait est GREFFE sur l'attaquant des bras `tl_aura` / `tl_away`. Meme unite,
    # meme geometrie, meme cible -- SEUL le trait change, donc l'ecart mesure ne peut venir que de
    # lui. `tl_immune` se compare a `tl_aura` (5 coups) et `tl_immune_away` a `tl_away` (6 coups).
    "tl_immune": {"carrier": JZ, "carrier_tile": TILE_J_NEAR, "victim": VICTIM,
                  "victim_tile": TILE_V, "target": "victim", "crit": "0,0",
                  "graft_trait": "%s:%s" % (ATT, UnitTrait.Immune.name)},
    "tl_immune_away": {"carrier": JZ, "carrier_tile": TILE_J_FAR, "victim": VICTIM,
                       "victim_tile": TILE_V, "target": "victim", "crit": "0,0",
                       "graft_trait": "%s:%s" % (ATT, UnitTrait.Immune.name)},
    # Voie CORROBORANTE, NATIF SEUL (`native_only`) : un vrai porteur `Immune` du build. Son rejeu
    # offline est STRUCTURELLEMENT impossible -- `combatSnapshot.unitConfig` rend
    # `{"error": "config null"}` pour une unite montee par `--explicit-stats` (elle n'a aucune
    # `UnitConfiguration` cote natif, exactement comme une unite INVOQUEE), donc `UnitContext.
    # from_snapshot` lit `weapons = []` et le port rend ZERO coup. Residu #987-r1.
    "tl_immune_boss": {"carrier": JZ, "carrier_tile": TILE_J_NEAR, "victim": VICTIM,
                       "victim_tile": TILE_V, "target": "victim", "crit": "0,0",
                       "att": BOSS_IMMUNE, "native_only": True},
    "tl_immune_boss_away": {"carrier": JZ, "carrier_tile": TILE_J_FAR, "victim": VICTIM,
                            "victim_tile": TILE_V, "target": "victim", "crit": "0,0",
                            "att": BOSS_IMMUNE, "native_only": True},
}


# --------------------------------------------------------------------------- montage live


def _build(arm_spec, seed=SEED, board=BOARD, rank=17, hp=400000):
    sf = ROOT / "logs" / "runners" / ("p950-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cv, ct = arm_spec["carrier"], arm_spec["carrier_tile"]
    vv, vt = arm_spec["victim"], arm_spec["victim_tile"]
    att = arm_spec.get("att", ATT)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", str(rank),
           "--p-units", "%s,%s" % (att, FILLER), "--a-units", "%s,%s" % (cv, vv),
           "--place", "%s:%d,%d" % (att, TILE_A[0], TILE_A[1]),
           "--place", "%s:%d,%d" % (FILLER, TILE_F[0], TILE_F[1]),
           "--a-place", "%s:%d,%d" % (cv, ct[0], ct[1]),
           "--a-place", "%s:%d,%d" % (vv, vt[0], vt[1]),
           "--hp-target", str(hp), "--crit", arm_spec["crit"],
           "--block-target", "0,0", "--block-player", "0,0", "--no-ai"]
    env = dict(os.environ)
    if arm_spec.get("graft_trait"):
        # `catalog_inject.add_unit_trait` ECRIT `BC.Units[].Traits` -- le canal que
        # `IdunBattle.Entities.Factories.UnitFactory$$Build` lit reellement (et NON le kit
        # gameconfig, que le port ne reconstruit plus depuis #264). `replace=False` : on AJOUTE au
        # jeu de traits existant, sans vider les autres.
        import catalog_inject as CI
        bcp = sf.with_name(sf.stem + "-bc.json")
        _p, reports = CI.write_trait_seed_bc(bcp, [arm_spec["graft_trait"]])
        for r in reports:
            print("[950] greffe de trait : %s -> %s (avant=%s)"
                  % (r["unitId"], r["traitsAfter"], r["traitsBefore"]))
        cmd += ["--seed-bc", str(bcp)]
    if ":" in att:
        # Un ATTAQUANT `unitId:palier` est une entree `units.npc` : `--explicit-stats` cable la
        # formule `UnitProgression$$GetNpcStats` (la formule HEROS la refuserait). Le garde de
        # roster rend alors un FAUX ROUGE -- le jeu publie le boss sous un id REMAPPE
        # (`darkaBossLion` -> `GuildBoss12Boss1DarkaLion`), et le garde compare les deux chaines.
        cmd += ["--explicit-stats", att]
        env["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-1200:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _resolve_remapped_attacker(dv, spec):
    """L'ATTAQUANT quand son `visualId` a ete REMAPPE par le jeu (cas BOSS).

    Le montage ne place que TROIS unites : l'attaquant et le `FILLER` dans MON camp, le porteur et
    la victime en face. On resout donc par ELIMINATION sur la tuile de l'attaquant (`TILE_A`), qui
    est fixee par `--place` : c'est un critere de POSITION, pas de nom, donc insensible au
    remappage. Rendre `None` plutot que deviner si la tuile ne porte personne."""
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        if p.get("col") is None:
            continue
        if (int(p["col"]), int(p["row"])) != TILE_A:
            continue
        if u.get("visualId") in (FILLER, spec["carrier"], spec["victim"]):
            continue
        return u
    return None


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _pos(dv, uid):
    u = _unit(dv, uid)
    return None if u is None else (int(u["pos"]["col"]), int(u["pos"]["row"]))


def _hp(dv, uid):
    u = _unit(dv, uid)
    return None if u is None else int(u.get("hp", 0))


def _effect_types(dv, uid):
    return sorted({int(e["effectType"]) for e in ((_unit(dv, uid) or {}).get("effects") or [])
                   if e.get("effectType") is not None})


def _normal_attack_id(dv, uid):
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _attack(rpc, rid, cid, tid, ab):
    """Attaque NORMALE live + ledger par coup.

    ⚠ Le discriminant est `Attacker_Id`, PAS la seule presence d'`Amount` : un event de SOIN porte
    lui aussi une cle `Amount` (mesure : la regen de `ToughToKill` = `{Amount: 2659, Caster_Id: …,
    UnitStats_WasWoundedBeforeHeal: 1}`, SANS `Attacker_Id` ni `Target_Id`). Un filtre par `Amount`
    seul comptait le soin comme un 7e coup."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ab)}, "captureEvents": True}, 150)
    hits, heals = [], []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" not in td:
                continue
            if "Attacker_Id" in td:
                if int(td.get("Target_Id", -1)) == int(tid):
                    hits.append(int(td["Amount"]))
            else:
                heals.append({"amount": int(td["Amount"]), "caster": td.get("Caster_Id")})
    return res, hits, heals


# --------------------------------------------------------------------------- rejeu offline


def _replay(cap, board_id, att_id, tgt_id, mutate=False, mutate_immune=False):
    """Rejoue l'attaque OFFLINE sur le `State` capte et le flux RNG capte.

    `mutate=True` RETIRE les trois entrees `EFFECT_CLASSES` du registre AVANT `load_state` : les
    effets captes ne sont alors plus materialises par leur classe portee mais par le `BaseEffect`
    no-op -- c'est EXACTEMENT l'etat d'`origin/master`, ou aucune des trois classes n'existait.

    `mutate_immune=True` est la contre-epreuve CIBLEE de #987 : elle neutralise le SEUL conjoint
    que la moitie COUPS ajoute (`NOT HasTrait(Caster, 0x19 = Immune)`), en laissant tout le reste
    intact. Sur le bras `tl_immune` le port doit alors retomber a 5 coups (le regime SANS le
    trait) ; s'il rend encore 6, c'est que le gate n'est pas LU et le bras vert ne prouve rien."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.loki import terrors_lament as TL
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.entities.pathfinding.board import Board as _BoardCls  # noqa: F401

    saved = {}
    saved_immune = None
    if mutate:
        for name in ("TerrorsLament_DamageReduction", "TerrorsLament_HitReduction", "ToughToKill"):
            saved[name] = EFFECT_CLASSES.get(name)
            EFFECT_CLASSES[name] = BaseEffect
    if mutate_immune:
        # Le module resout `_caster_is_immune` dans SON propre espace de noms global a chaque
        # appel : substituer l'attribut du module MORD (contrairement a une liaison `from X import`
        # posee dans un module TIERS).
        saved_immune = TL._caster_is_immune
        TL._caster_is_immune = lambda _traits: False
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        hc = st.get_entity(int(tgt_id)).get_component(HealthComponent)
        hp0 = int(hc.hp)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(int(att_id), int(tgt_id)))
        last = runner.damage_handler.last or {}
        return {"hp_delta": hp0 - int(hc.hp), "total": last.get("total"),
                "per_hit": list(last.get("per_hit") or []), "state": st}
    finally:
        for name, cls in saved.items():
            if cls is None:
                EFFECT_CLASSES.pop(name, None)
            else:
                EFFECT_CLASSES[name] = cls
        if saved_immune is not None:
            TL._caster_is_immune = saved_immune


def _replay_regen(cap, board_id, carrier_id, mutate=False):
    """Rejoue le vecteur `On(0x13 = TurnStart_Other)` OFFLINE pour le joueur du porteur.

    `mutate=True` RETIRE l'entree `ABILITY_TRIGGERS["ToughToKill"]` -- l'etat d'`origin/master`."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import HealthComponent, OwnerComponent
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.dispatch.turn import turn_start_other_triggers

    saved = None
    had = "ToughToKill" in ABILITY_TRIGGERS
    if mutate:
        saved = ABILITY_TRIGGERS.pop("ToughToKill", None)
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board_id)
        e = st.get_entity(int(carrier_id))
        hc, oc = e.get_component(HealthComponent), e.get_component(OwnerComponent)
        hp0 = int(hc.hp)
        out = turn_start_other_triggers(st, int(oc.player))
        return {"hp_delta": int(hc.hp) - hp0, "hp_before": hp0, "hp_after": int(hc.hp),
                "events": [d for d in (out or []) if d.get("type") == "tough_to_kill_regen"]}
    finally:
        if had and saved is not None:
            ABILITY_TRIGGERS["ToughToKill"] = saved


# --------------------------------------------------------------------------- pilote


def run(arm: str, mutate: bool = False, verbose: bool = True, seed=SEED, board=BOARD,
        mutate_immune: bool = False) -> dict:
    spec = ARMS[arm]
    rid, err = _build(spec, seed=seed, board=board)
    if rid is None:
        return {"error": "build KO (%s) : %s" % (arm, err)}
    rpc = _mkrpc()
    try:
        return _measure(rpc, rid, arm, spec, mutate, verbose, board, mutate_immune)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _measure(rpc, rid, arm, spec, mutate, verbose, board_id, mutate_immune=False):
    from engine.entities.pathfinding.board import Board

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = _view(rpc, rid, inactive=True)
    att_vis = spec.get("att", ATT)
    ids = {}
    for v in (att_vis, spec["carrier"], spec["victim"]):
        u = _by_vis(dv, v)
        if u is None and v == att_vis:
            # Un BOSS est publie sous un id REMAPPE (`darkaBossLion` -> `GuildBoss12Boss1DarkaLion`) :
            # on le retrouve par ELIMINATION dans MON camp -- la seule unite qui n'est ni le FILLER
            # ni une a-unit. C'est la meme cause que le faux rouge du garde de roster.
            u = _resolve_remapped_attacker(dv, spec)
        if u is None:
            return {"error": "unite absente du build : %s" % v}
        ids[v] = int(u["id"])
    att_id = ids[att_vis]
    carrier_id = ids[spec["carrier"]]
    tgt_id = carrier_id if spec["target"] == "carrier" else ids[spec["victim"]]

    # --- GEOMETRIE : elle est ASSERTIONNEE, pas supposee ---------------------------------------
    geo = {"att": _pos(dv, att_id), "carrier": _pos(dv, carrier_id),
           "victim": _pos(dv, ids[spec["victim"]])}
    geo["d_att_carrier"] = (None if None in (geo["att"], geo["carrier"])
                            else hexgeo.distance(geo["att"], geo["carrier"]))
    geo["d_att_target"] = (None if geo["att"] is None
                           else hexgeo.distance(geo["att"], _pos(dv, tgt_id)))
    geo["elevations"] = {}
    for t in (bg.get("tiles") or []):
        key = (int(t["col"]), int(t["row"]))
        if key in (geo["att"], geo["carrier"], geo["victim"]):
            geo["elevations"][str(key)] = t.get("elevation")

    na = _normal_attack_id(dv, att_id)
    if na is None:
        return {"error": "id d'attaque normale introuvable pour %s" % att_vis}

    carrier_effects = _effect_types(dv, carrier_id)

    cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
           "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
           "rng": rpc("dumpRng", {"runnerId": rid}, 30)}

    _res, hits, heals_in_attack = _attack(rpc, rid, att_id, tgt_id, na)
    port = _replay(cap, board, att_id, tgt_id, mutate=mutate, mutate_immune=mutate_immune)

    out = {"arm": arm, "mutate": bool(mutate), "mutate_immune": bool(mutate_immune),
           "runner": rid, "ids": ids, "geo": geo,
           "carrier_effects": carrier_effects, "target": tgt_id,
           "heals_in_attack": heals_in_attack,
           "native": {"hits": hits, "n": len(hits), "total": sum(hits)},
           "port": {"per_hit": port["per_hit"], "n": len(port["per_hit"]),
                    "total": port["total"], "hp_delta": port["hp_delta"]}}

    # --- REGEN : seulement la ou le porteur est `astraDreir` -------------------------------------
    # La capture est prise APRES l'attaque et AVANT le `endturn` : Dreir y est BLESSE et PAS ENCORE
    # soigne, sans quoi le rejeu offline et la mesure native ne partiraient pas du meme PV.
    if spec["carrier"] == DREIR:
        cap2 = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
                "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        hp_before = _hp(_view(rpc, rid), carrier_id)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        d_after = _view(rpc, rid)
        out["regen"] = {"native_hp_before": hp_before,
                        "native_hp_after": _hp(d_after, carrier_id),
                        "current_player": d_after.get("currentPlayer")}
        out["regen"]["native_delta"] = (None if None in (hp_before, out["regen"]["native_hp_after"])
                                        else out["regen"]["native_hp_after"] - hp_before)
        rp = _replay_regen(cap2, board, carrier_id, mutate=mutate)
        out["regen"]["port_delta"] = rp["hp_delta"]
        out["regen"]["port_events"] = rp["events"]

    if verbose:
        _report(out)
    return out


def _report(r):
    print("[950] arm=%-8s mutate=%-5s runner=%s ids=%s"
          % (r["arm"], r["mutate"], r["runner"], r["ids"]))
    g = r["geo"]
    print("       geo att=%s carrier=%s victim=%s | d(att,carrier)=%s d(att,cible)=%s elev=%s"
          % (g["att"], g["carrier"], g["victim"], g["d_att_carrier"], g["d_att_target"],
             g["elevations"]))
    print("       effets du porteur (EffectType) : %s" % r["carrier_effects"])
    print("       NATIF  n=%d total=%-8d hits=%s" % (r["native"]["n"], r["native"]["total"],
                                                     r["native"]["hits"]))
    print("       PORT   n=%d total=%-8s hits=%s" % (r["port"]["n"], r["port"]["total"],
                                                     r["port"]["per_hit"]))
    if r.get("heals_in_attack"):
        print("       [!] soins DANS la cascade d'attaque : %s" % r["heals_in_attack"])
    if "regen" in r:
        rg = r["regen"]
        print("       REGEN  natif %s -> %s (delta=%s) | port delta=%s events=%s"
              % (rg["native_hp_before"], rg["native_hp_after"], rg["native_delta"],
                 rg["port_delta"], rg["port_events"]))


# --------------------------------------------------------------------------- verdicts


def verdict_geometry(res: dict) -> list:
    """La geometrie EST le discriminant : si elle n'est pas celle qu'on a demandee, tout verdict
    d'aval est vide. Elle est donc verifiee AVANT tout, bras par bras."""
    f, g, arm = [], res["geo"], res["arm"]
    if g["att"] != TILE_A:
        f.append("[geo] %s : attaquant en %s, attendu %s" % (arm, g["att"], TILE_A))
    want = ARMS[arm]["carrier_tile"]
    if g["carrier"] != want:
        f.append("[geo] %s : porteur en %s, attendu %s" % (arm, g["carrier"], want))
    if g["victim"] != ARMS[arm]["victim_tile"]:
        f.append("[geo] %s : victime en %s, attendu %s"
                 % (arm, g["victim"], ARMS[arm]["victim_tile"]))
    if g["d_att_target"] != 1:
        f.append("[geo] %s : l'attaquant n'est pas AU CONTACT de sa cible (d=%s)"
                 % (arm, g["d_att_target"]))
    if arm in ("tl_aura",) and g["d_att_carrier"] != 1:
        f.append("[geo] tl_aura : Jain Zar doit etre ADJACENTE a l'attaquant (d=%s)"
                 % g["d_att_carrier"])
    if arm in ("tl_away",) and (g["d_att_carrier"] or 0) < 2:
        f.append("[geo] tl_away : Jain Zar doit etre HORS contact de l'attaquant (d=%s)"
                 % g["d_att_carrier"])
    if arm == "tl_aura":
        d_cv = hexgeo.distance(g["carrier"], g["victim"])
        if d_cv < 2:
            f.append("[geo] tl_aura : Jain Zar doit etre a >= 2 de la VICTIME (d=%s) -- sinon le "
                     "bras ne distingue pas « adjacent a l'attaquant » de « adjacent a la cible »"
                     % d_cv)
    elev = set(v for v in g["elevations"].values() if v is not None)
    if len(elev) > 1:
        f.append("[geo] %s : les trois tuiles n'ont PAS la meme elevation (%s) -- un terme "
                 "d'elevation separerait les bras" % (arm, g["elevations"]))
    return f


def verdict_carrier_effects(res: dict) -> list:
    """Le porteur DOIT porter ses effets : sans eux la mesure d'aval est vide (un zero de canal ne
    se distinguerait pas d'un zero de pose)."""
    f, arm = [], res["arm"]
    want = ([TL_DMG, TL_HITS] if ARMS[arm]["carrier"] == JZ else [TTK])
    have = set(res["carrier_effects"])
    for et in want:
        if et not in have:
            f.append("[pose] %s : l'effet %d n'est PAS sur le porteur (effets = %s)"
                     % (arm, et, res["carrier_effects"]))
    return f


def verdict_port_matches_native(res: dict) -> list:
    """Le verdict FORT : le rejeu offline egale le natif A L'UNITE, coup par coup."""
    f, arm = [], res["arm"]
    if res["native"]["n"] == 0:
        f.append("[port] %s : le natif n'a porte AUCUN coup -- mesure VIDE" % arm)
        return f
    if res["port"]["n"] != res["native"]["n"]:
        f.append("[port] %s : nb de coups port=%d natif=%d"
                 % (arm, res["port"]["n"], res["native"]["n"]))
    if res["port"]["per_hit"] != res["native"]["hits"]:
        f.append("[port] %s : ledger par coup port=%s natif=%s"
                 % (arm, res["port"]["per_hit"], res["native"]["hits"]))
    return f


def verdict_terrors_lament(aura: dict, away: dict) -> list:
    """Le DISCRIMINANT natif : Jain Zar adjacente a l'attaquant retire UN coup et REDUIT le degat,
    a geometrie d'attaque IDENTIQUE. Les deux bras ne different QUE par sa tuile."""
    f = []
    na, nw = aura["native"], away["native"]
    if nw["n"] == 0 or na["n"] == 0:
        return ["[natif] TerrorsLament : un des deux bras n'a porte aucun coup (aura=%d away=%d)"
                % (na["n"], nw["n"])]
    if na["n"] != nw["n"] - 1:
        f.append("[natif] TerrorsLament COUPS : aura=%d attendu %d (= temoin %d - hitsReduction 1)"
                 % (na["n"], nw["n"] - 1, nw["n"]))
    if not na["hits"] or not nw["hits"]:
        f.append("[natif] TerrorsLament : ledger vide")
    elif not (max(na["hits"]) < max(nw["hits"])):
        f.append("[natif] TerrorsLament DEGAT : le coup MAX du bras aura (%d) n'est pas STRICTEMENT "
                 "inferieur a celui du temoin (%d) -- la reduction plate ne mord pas"
                 % (max(na["hits"]), max(nw["hits"])))
    return f


def verdict_tough_to_kill(ttk: dict, ctl: dict) -> list:
    """Le DISCRIMINANT natif de l'axe CRIT : a `--crit 100,700`, la cible SANS `ToughToKill` prend
    des coups strictement plus lourds que le porteur, toutes choses egales par ailleurs."""
    f = []
    if not ttk["native"]["hits"] or not ctl["native"]["hits"]:
        return ["[natif] ToughToKill : un des deux bras n'a porte aucun coup"]
    if max(ttk["native"]["hits"]) >= max(ctl["native"]["hits"]):
        f.append("[natif] ToughToKill CRIT : coup MAX sur Dreir (%d) >= coup MAX sur le temoin "
                 "(%d) -- ni la chance ni le degat de crit ne sont reduits"
                 % (max(ttk["native"]["hits"]), max(ctl["native"]["hits"])))
    return f


def verdict_regen(res: dict) -> list:
    """`ToughToKill_HealAbility` : le PV de Dreir remonte au debut de SON tour, et le port rend la
    MEME valeur par le MEME vecteur (`On(0x13 = TurnStart_Other)`)."""
    f = []
    rg = res.get("regen")
    if rg is None:
        return ["[regen] bras sans mesure de regen"]
    if not rg.get("native_delta"):
        f.append("[regen] natif : delta de PV NUL au debut du tour de Dreir (%s -> %s) -- "
                 "la mesure est vide" % (rg.get("native_hp_before"), rg.get("native_hp_after")))
        return f
    if rg.get("port_delta") != rg.get("native_delta"):
        f.append("[regen] port=%s natif=%s" % (rg.get("port_delta"), rg.get("native_delta")))
    if not rg.get("port_events"):
        f.append("[regen] le port n'a emis AUCUN event `tough_to_kill_regen`")
    return f


def verdict_mutation(base: dict, mut: dict, porteur: bool) -> list:
    """CONTRE-EPREUVE. `porteur=True` : la mutation DOIT faire diverger le rejeu du natif.
    `porteur=False` (temoin) : elle ne doit RIEN changer.

    Le premier verdict verifie que les DEUX bras ont la MEME mesure NATIVE -- sans lui, un ecart
    port/natif ne serait pas attribuable a la seule mutation."""
    f = []
    if base["native"]["hits"] != mut["native"]["hits"]:
        return ["[mutation] les deux bras n'ont pas la MEME mesure NATIVE (%s vs %s) : l'A/B n'est "
                "pas attribuable" % (base["native"]["hits"], mut["native"]["hits"])]
    same = (mut["port"]["per_hit"] == mut["native"]["hits"])
    if porteur and same:
        f.append("[mutation] %s : le registre NEUTRALISE, le rejeu egale TOUJOURS le natif (%s) -- "
                 "la mutation NE MORD PAS, donc le vert du bras normal ne prouve rien"
                 % (base["arm"], mut["port"]["per_hit"]))
    if (not porteur) and not same:
        f.append("[mutation] %s (temoin) : le registre neutralise change le rejeu (%s vs %s) -- "
                 "un effet non concerne a bouge" % (base["arm"], mut["port"]["per_hit"],
                                                    mut["native"]["hits"]))
    return f


# --------------------------------------------------------------------------- CLI


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", default="all", choices=sorted(ARMS) + ["all"])
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutate-immune", action="store_true",
                    help="contre-epreuve CIBLEE #987 : neutralise NOT HasTrait(Caster, Immune)")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args()
    arms = sorted(ARMS) if a.arm == "all" else [a.arm]
    rc = 0
    for arm in arms:
        r = run(arm, mutate=a.mutate, seed=a.seed, board=a.board,
                mutate_immune=a.mutate_immune)
        if "error" in r:
            print("[950] %s : %s" % (arm, r["error"]))
            rc = 1
            continue
        for v in (verdict_geometry(r) + verdict_carrier_effects(r)
                  + verdict_port_matches_native(r)):
            print("  " + v)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
