"""Probe #1073 -- confronter LIVE le canal COUPS du passif `SynapticInsight`
(`TriggeredAbilityType 0x4a9 = 1193`, effet `EffectType 0x4cf = 1231
SynapticInsight_ExtraHits`), porte par le summon `tyranSmnBarbgaunt` et ses jumeaux npc.

Ce que le natif fait, et que ce probe MESURE plutot que de le supposer :

    SynapticInsightAbility$$CreateTrigger   = <DSLTriggers+0x30>
                                            = On(0x21 = AbilityInit, ownerNeedsToBeAlive: false)
                                              & get_OwnerIsActor
    SynapticInsightAbility$$CreateBehaviour = AddEffect(0x4cf, AbilityStateReference,
                                                        targets = Owner@<Sel+0x30>, turns = null)

    SynapticInsight_ExtraHitsEffect$$CreateEffectHitsBonusForAttack =
        EffectBonus.ForAddition(
            get_OwnerIsCaster & IsRangedAttack()
            & (   Any( AdjacentFriends(unit = Owner@<Sel+0x30>, unitTile = Target@<Sel+0x60>,
                                       unique: true),
                       HasFaction(ActiveTarget@<Sel+0x68>, UnitFaction.Tyranids = 0xc, 3) )
                | IsInTeamSynapseRange( Target@<Sel+0x60>, Owner@<Sel+0x30> ) ),
            ConfigConst(0x2b = extraHit) )                                   # = 2 sur ce build

=================================================================================================
LE PORTEUR, ET POURQUOI L'AUDIT LE RENDAIT `S?`
=================================================================================================

`unit_map find --ability SynapticInsight` rend TROIS unites : le summon `tyranSmnBarbgaunt` et les
npc `tyranNpc5Barbgaunt` / `tyranNpc5BarbgauntSurv`. Le graphe de summon de
`audit_passive_ability_coverage` ne balaie que les abilities DES UNITES, et l'unique invocateur de
`tyranSmnBarbgaunt` est `EnvFactionSummons:Tyranids` -- une ability d'ENVIRONNEMENT de live-event,
portee par AUCUNE unite (balayage EXHAUSTIF du gameconfig : toute chaine de l'arbre, pas seulement
`constants.unitId*`). D'ou `S?`, faute de pouvoir trancher -- PAS parce que le porteur serait
inatteignable.

Le chemin retenu est le **jumeau npc** : `tyranSmnBarbgaunt.visualId == "tyranNpc5Barbgaunt"`, donc
`--explicit-stats tyranNpc5Barbgaunt:45` amene un MIRROR du summon, avec SES stats (table
`units.npc[].stats[]`, 45 paliers), SES traits et SON arme. Meme recette que #1052.

⚠ Le palier n'est pas cosmetique ici NON PLUS, mais pour une autre raison qu'en #1052 : la
magnitude est une CONSTANTE (`ConfigConst`), donc elle ne depend pas du niveau -- ce qui depend du
palier, c'est la survie du porteur et de sa cible pendant la mesure. Corollaire : le defaut de
harnais `#1049-r1` (l'`AbilityState` annonce par un porteur `--explicit-stats`) ne peut PAS fausser
ce port, qui ne lit aucune variable par niveau.

=================================================================================================
LES TROIS REGIMES -- et c'est le NATIF qui doit les separer
=================================================================================================

Le temoin est le NOMBRE DE COUPS de l'attaque normale RANGED du porteur (arme `Bio`, portee 3).
Les deux disjoints sont armes SEPAREMENT, par la GEOMETRIE :

  * `temoin`   : personne pres de la cible                       -> attendu : base
  * `adjacent` : un SECOND `tyranNpc5Barbgaunt:45` (Tyranide, AUCUN trait `Synapse`) colle a la
                 CIBLE                                            -> `Any(AdjacentFriends(...))`
  * `synapse`  : `tyranParasite` (Tyranide `Synapse`) a distance **2** de la cible, donc PAS
                 adjacent                                         -> `IsInTeamSynapseRange` seul

⚠ **UN ACCORD EN REGIME DEGENERE NE PROUVE RIEN.** Le probe EXIGE que le NATIF separe lui-meme
`temoin` de `adjacent`/`synapse` (`natif_separe`) : si les trois regimes rendent le meme nombre de
coups cote natif, le montage est faux et le verdict est `indisponible`, jamais `EGAL`.

⚠ Le porteur est place a distance 3 de sa cible : s'il etait ADJACENT, il armerait le premier
disjoint TOUT SEUL (le natif ne soustrait que `unitTile`, donc le porteur reste dans
`AdjacentFriends` -- il est ami de lui-meme et Tyranide), et le temoin serait detruit.

⚠ Aucune unite du montage ne porte `BigTarget` : son aura `-1 coup aux attaques RANGED des amis
adjacents` tombe sur le MEME axe que la mesure (residu `#1052-r3`). `tyranTyrantGuard`, seul autre
Tyranide sans `Synapse` du pool, en porte un -- d'ou le second Barbgaunt.

MUTANTS (`--mutate <nom>`) -- chacun doit MORDRE sur `adjacent` et `synapse`, et chacun EST un etat
reel du depot :
  * `effet`     : retire `EFFECT_CLASSES["SynapticInsight_ExtraHits"]` -> l'effet est materialise
                  mais INERTE (etat d'avant cette tranche) ;
  * `ctxAdj`    : efface la cle `synaptic_insight_adjacent_tyranid` du board de coups -> le PREMIER
                  disjoint se ferme (mord sur `adjacent` SEUL) ;
  * `ctxSynapse`: efface `team_synapse_positions` -> le SECOND disjoint se ferme (mord sur
                  `synapse` SEUL). Ces deux-la sont le cliquet du CABLAGE : sans eux, un port qui
                  lit les mauvaises cles rendrait juste par accident sur un seul regime.
  * `seed`      : retire `ABILITY_INIT_OWNER_EFFECTS["SynapticInsight"]` -> mesure si le seed est
                  un FILET (l'effet etant `CreateActiveCondition = <DSLTriggers+0x40>` = constante
                  VRAIE, il devrait etre capte par `decisionView.effects`) ou le SEUL chemin.

CLI (depuis scripts/python) :
  python probe_1073_synaptic_insight.py
  python probe_1073_synaptic_insight.py --mutate effet
  python probe_1073_synaptic_insight.py --regime adjacent --verbose

ASCII only dans les sorties (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from probe_r6_round_materialize import _mkrpc                    # noqa: E402

BOARD = "MC1_67"
SEED = "4321"
#: le jumeau NPC du summon `tyranSmnBarbgaunt` -- MEME `visualId`, donc MEME kit, MEMES traits.
#: Palier 45 (`units.npc[].stats[]`), forme exigee VERBATIM par `--explicit-stats`, `--p-units` et
#: `--place` (le parseur coupe au DERNIER `:`, cf. `rl_duel._parse_place_specs`).
CARRIER = "tyranNpc5Barbgaunt:45"
#: le SECOND Barbgaunt, colle a la cible : Tyranide, AUCUN `Synapse`, AUCUN `BigTarget`.
ADJ_TYRANID = "tyranNpc5Barbgaunt:45"
#: `tyranParasite` -- Tyranide porteur du trait `Synapse` (l'emetteur de la bulle, cf.
#: `SynapseEffect$$GetTrait` = `return 0x7e8`). Son passif `BarbedOvipositor` est un SUMMON-sur-kill
#: (aucune interaction avec l'axe COUPS).
SYNAPSE_ALLY = "tyranParasite"
#: la CIBLE : `orksNob`. Son passif `SmashaEad` est un bonus de DEGAT conditionne a SON deplacement
#: -- aucun gate de coups, ni en attaque ni en defense.
TARGET = "orksNob"
#: `EffectType.SynapticInsight_ExtraHits` = `0x4cf` = 1231.
SI_EFFECT = 1231
#: tuiles LUES sur `MC1_67` (`board.py`) : cible au centre (3,4), anneau
#: [(2,3) (2,4) (3,3) (3,5) (4,3) (4,4)], couronne 2 dont (5,5), et (6,4) a distance 3.
T_POS = (3, 4)
CARRIER_POS = (6, 4)          # distance 3 -> dans la portee de l'arme, JAMAIS adjacent
ADJ_POS = (4, 4)              # anneau de la cible
SYNAPSE_POS = (5, 5)          # distance 2 de la cible, PAS adjacent


def _build(regime, seed, board, extra_dbg=None):
    """Monte le regime demande. `--no-ai` : on pilote nous-memes, l'IA ne joue jamais."""
    sf = ROOT / "logs" / "runners" / ("p1073-%s-%s.json" % (regime, uuid.uuid4().hex[:8]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    p_units = [CARRIER]
    places = ["--place", "%s:%d,%d" % (CARRIER, *CARRIER_POS)]
    explicit = ["--explicit-stats", CARRIER]
    if regime == "adjacent":
        p_units.append(ADJ_TYRANID)
        places += ["--place", "%s:%d,%d" % (ADJ_TYRANID, *ADJ_POS)]
    elif regime == "synapse":
        p_units.append(SYNAPSE_ALLY)
        places += ["--place", "%s:%d,%d" % (SYNAPSE_ALLY, *SYNAPSE_POS)]
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
           "--board", board, "--rank", "17",
           "--p-units", ",".join(p_units), "--a-units", TARGET,
           "--a-place", "%s:%d,%d" % (TARGET, *T_POS),
           *places, *explicit,
           # crit et block ZEROES des DEUX cotes : le nombre de coups est la mesure, pas leur degat.
           "--crit", "0,0", "--crit-target", "0,0",
           "--block-target", "0,0", "--block-player", "0,0",
           # PV eleves : la cible doit SURVIVRE aux 5 coups, sinon la cascade s'arrete tot et le
           # compte de coups mesure la MORT, pas la formule.
           "--hp-target", "400000", "--hp-player", "400000", "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if extra_dbg:
        print((proc.stdout or "")[-2500:])
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-900:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _units_by_vis(dv, vis):
    """TOUTES les unites de ce `visualId` -- le regime `adjacent` en porte DEUX."""
    return [u for u in (dv.get("units") or []) if u.get("visualId") == vis]


def _normal_attack_id(dv, uid):
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _attack(rpc, rid, cid, tid, ab):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ab)}, "captureEvents": True}, 150)
    hits = []
    for act in (res.get("actions") or []):
        for ev in (act.get("events") or []):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and int(td.get("Target_Id", td.get("TargetId", tid)) or tid) == int(tid):
                hits.append(int(td["Amount"]))
    return res, hits


def _replay(cap, board, att_id, tgt_id, mutate=None):
    """Rejoue l'attaque normale du porteur depuis la capture, avec le MEME flux RNG."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.entities.effects.factory import EFFECT_CLASSES, ABILITY_INIT_OWNER_EFFECTS
    from engine.entities.effects.loki import synaptic_insight as SI
    from engine.entities.effects.loki import norn_crown as NC
    import engine.runner.damage_model as DM

    # ⚠ Les mutants de REGISTRE sont poses AVANT `load_state` : `EFFECT_CLASSES` n'est lu qu'a la
    # CREATION des instances d'effet, donc un `pop` d'apres arriverait trop tard pour un effet deja
    # present au seed (lecon de `probe_932`).
    saved_eff = saved_seed = saved_board = None
    if mutate == "effet":
        saved_eff = EFFECT_CLASSES.pop("SynapticInsight_ExtraHits", None)
        assert saved_eff is not None, \
            "MUTANT INOPERANT : EFFECT_CLASSES['SynapticInsight_ExtraHits'] absent"
    elif mutate == "seed":
        saved_seed = ABILITY_INIT_OWNER_EFFECTS.pop("SynapticInsight", None)
        assert saved_seed is not None, \
            "MUTANT INOPERANT : ABILITY_INIT_OWNER_EFFECTS['SynapticInsight'] absent"
    elif mutate in ("ctxAdj", "ctxSynapse"):
        # Le board de COUPS est bati par `build_hits_board` : on l'enveloppe pour EFFACER la cle
        # visee, ce qui simule EXACTEMENT << substrat non mesure >> (tri-etat).
        #
        # ⚠ **ON PATCHE LE BINDING DU CONSOMMATEUR, PAS CELUI DU MODULE SOURCE**, et c'est MESURE :
        # `damage_ops/normal.py` et `damage_ops/ability.py` font `from ...damage_model import
        # build_hits_board` (**forme A**), donc le nom est LIE chez eux -- substituer
        # `damage_model.build_hits_board` NE MORD PAS. Premier jet de ce probe : les deux mutants
        # `ctx*` rendaient `EGAL` sur les trois regimes, un FAUX VERT parfaitement silencieux
        # (l'`assert cle in board_` ne levait pas... parce que le wrapper n'etait jamais appele).
        # C'est exactement la mesure du CLAUDE.md sur les 28 rouges de #484.
        cle = SI.CTX_ADJACENT_TYRANID if mutate == "ctxAdj" else NC.CTX_TEAM_SYNAPSE_POSITIONS
        from engine.runner.operations.damage_ops import normal as _DN
        from engine.runner.operations.damage_ops import ability as _DA
        saved_board = [(_DN, _DN.build_hits_board), (_DA, _DA.build_hits_board),
                       (DM, DM.build_hits_board)]
        vrai = DM.build_hits_board
        appels = [0]

        def _sans_cle(*a, **kw):
            board_, aura, tgt_eff = vrai(*a, **kw)
            assert cle in board_, "MUTANT INOPERANT : la cle %r n'est pas dans le board" % cle
            appels[0] += 1
            board_ = {k: v for k, v in board_.items() if k != cle}
            return board_, aura, tgt_eff
        for mod, _old in saved_board:
            mod.build_hits_board = _sans_cle
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(int(att_id), int(tgt_id)))
        last = runner.damage_handler.last or {}
        eff = getattr(st, "effects", None)
        niveau = None
        if eff is not None:
            for e in eff.by_unit.get(int(att_id), []):
                if e.effect_type == SI_EFFECT and not e.consumed:
                    niveau = int(e.level or 0)
        out = {"per_hit": last.get("per_hit"), "total": last.get("total"),
               "hits": len(last.get("per_hit") or []), "effet_present": niveau is not None}
        if saved_board is not None:
            # << la mutation a-t-elle MORDU ? >> -- un mutant qui n'est jamais appele rend un
            # EGAL qui ne prouve rien. On PUBLIE le compte au lieu de l'esperer.
            out["mutant_appels"] = appels[0]
            assert appels[0] > 0, ("MUTANT INOPERANT : `build_hits_board` n'a jamais ete traverse "
                                   "-- le binding patche n'est pas celui que le runner lit")
        return out
    finally:
        if saved_eff is not None:
            EFFECT_CLASSES["SynapticInsight_ExtraHits"] = saved_eff
        if saved_seed is not None:
            ABILITY_INIT_OWNER_EFFECTS["SynapticInsight"] = saved_seed
        if saved_board is not None:
            for mod, old in saved_board:
                mod.build_hits_board = old


def _regime(rpc, regime, seed, board_id, mutate, verbose, dbg=False):
    from engine.entities.pathfinding.board import Board

    rid, err = _build(regime, seed, board_id, extra_dbg=dbg)
    if rid is None:
        return {"regime": regime, "verdict": "indisponible", "cause": "build KO : %s" % err}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _view(rpc, rid, inactive=True)
        if dbg:
            for u in (dv.get("units") or []):
                print("   [dbg] id=%-4s vis=%-26s team=%-3s pos=%s eff=%s"
                      % (u.get("id"), u.get("visualId"), u.get("team"), u.get("pos"),
                         [(e.get("effectType"), e.get("name")) for e in (u.get("effects") or [])]))
        # le PORTEUR est celui pose a `CARRIER_POS` (le regime `adjacent` a deux unites du meme
        # `visualId` -- les departager par la POSITION, jamais par l'ordre du view).
        cands = _units_by_vis(dv, CARRIER.split(":")[0]) or _units_by_vis(dv, CARRIER)
        porteur = next((u for u in cands
                        if u.get("pos") and (int(u["pos"]["col"]), int(u["pos"]["row"]))
                        == CARRIER_POS), None)
        cible = next((u for u in (dv.get("units") or [])
                      if u.get("pos") and (int(u["pos"]["col"]), int(u["pos"]["row"])) == T_POS
                      and u.get("team") != (porteur or {}).get("team")), None)
        if porteur is None or cible is None:
            return {"regime": regime, "verdict": "indisponible",
                    "cause": "porteur ou cible introuvable a la position voulue (cands=%d)"
                             % len(cands)}
        pid, tid = int(porteur["id"]), int(cible["id"])
        # L'effet doit EXISTER sur le porteur, sinon on mesure une absence de montage, pas le port.
        eff_live = [e for e in (porteur.get("effects") or [])
                    if e.get("effectType") is not None and int(e["effectType"]) == SI_EFFECT]
        na = _normal_attack_id(dv, pid)
        if na is None:
            return {"regime": regime, "verdict": "indisponible",
                    "cause": "attaque normale du porteur introuvable"}
        cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
               "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
        _r, hits = _attack(rpc, rid, pid, tid, na)
        if not hits:
            return {"regime": regime, "verdict": "indisponible",
                    "cause": "cascade VIDE -> l'attaque n'a pas eu lieu (ok=%s)" % _r.get("ok")}
        port = _replay(cap, board, pid, tid, mutate=mutate)
        out = {"regime": regime, "porteur": pid, "cible": tid,
               "effet_live_sur_porteur": bool(eff_live),
               "natif_hits": len(hits), "natif_total": sum(hits), "natif_per_hit": hits,
               "port_hits": port["hits"], "port_total": port["total"],
               "port_per_hit": port["per_hit"], "port_effet_present": port["effet_present"],
               "mutant_appels": port.get("mutant_appels")}
        out["verdict"] = ("EGAL" if (out["natif_hits"] == out["port_hits"]
                                     and out["natif_total"] == out["port_total"]) else "DIVERGE")
        if verbose:
            print("[1073] regime=%-9s natif=%d coups (%s) port=%s coups (%s) -> %s"
                  % (regime, out["natif_hits"], out["natif_total"], out["port_hits"],
                     out["port_total"], out["verdict"]))
        return out
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", default="tous",
                    choices=("temoin", "adjacent", "synapse", "tous"))
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--mutate", default=None,
                    choices=("effet", "ctxAdj", "ctxSynapse", "seed"))
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rpc = _mkrpc()
    regimes = ("temoin", "adjacent", "synapse") if a.regime == "tous" else (a.regime,)
    res = {r: _regime(rpc, r, a.seed, a.board, a.mutate, a.verbose or not a.json, a.debug)
           for r in regimes}
    # ⚠ LE CONTROLE DE NON-DEGENERESCENCE : c'est le NATIF qui doit separer les regimes. Un accord
    # port/natif sur trois regimes qui rendent tous le meme nombre de coups ne prouve RIEN.
    if len(regimes) == 3 and all(r.get("verdict") != "indisponible" for r in res.values()):
        base = res["temoin"]["natif_hits"]
        separe = all(res[r]["natif_hits"] > base for r in ("adjacent", "synapse"))
        res["_controle"] = {"natif_separe": separe, "natif_base": base,
                            "natif_adjacent": res["adjacent"]["natif_hits"],
                            "natif_synapse": res["synapse"]["natif_hits"]}
        if not separe:
            print("[1073] ⚠ REGIME DEGENERE : le natif ne separe pas les trois montages "
                  "(%d / %d / %d coups) -- le montage est faux, pas le port."
                  % (base, res["adjacent"]["natif_hits"], res["synapse"]["natif_hits"]))
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        for r, v in res.items():
            if r.startswith("_"):
                print("[1073] %s : %s" % (r, v))
                continue
            print("[1073] %-9s %-12s natif=%s coups tot=%s | port=%s coups tot=%s | effet_live=%s"
                  % (r, v.get("verdict"), v.get("natif_hits"), v.get("natif_total"),
                     v.get("port_hits"), v.get("port_total"), v.get("effet_live_sur_porteur")))
            if v.get("cause"):
                print("           cause: %s" % v["cause"])
    return 0 if all(v.get("verdict") == "EGAL" for k, v in res.items()
                    if not k.startswith("_")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
