#!/usr/bin/env python
"""probe_447_bit51_native -- la voie du BIT 51 de `TargetIsNotSteppable`, CONFRONTEE AU NATIF.

CE QUE CE PROBE AJOUTE A #442
-----------------------------
`docs/rl/case-442-target-is-not-steppable.md` a confronte la regle `TargetIsNotSteppable` par son
armement IMPLICITE -- `get_IsUnitTargeting` sans `AllowSteppableUnit`, 82 abilities + l'attaque
normale, accord 18/18. Son SECOND armement, le BIT 51 pose explicitement au masque, n'y etait
confronte qu'OFFLINE (etage D). Ce probe le confronte AU NATIF.

    IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason (surcharge 7 arguments) :

        if ((rules >> 0x33 & 1) == 0) {                      // bit 51 NON pose
            if (TargetingOptions.get_IsUnitTargeting(options)) {
                if ((rules & 0x100000) == 0) goto TEST;      // !AllowSteppableUnit (bit 20)
            }
        } else {
        TEST:
            if (TileExtensions.HasSteppableUnit(puVar12, state)) -> broken(0x8000000000000);
        }

CE QUE LA VOIE UNIT-TARGETING NE PEUT PAS MONTRER, et que ce montage EXHIBE
--------------------------------------------------------------------------
L'unique porteur du bit, `1011 TunnelingHorror`, est **TILE-targeting** (bit 6) : son
`get_IsUnitTargeting` est donc FAUX, et la voie implicite de #442 ne l'arme PAS. Chez lui la regle
n'est armee QUE par le bit 51 -- c'est la branche `else` du natif, celle qui saute directement au
predicat sans passer par le test d'`AllowSteppableUnit`.

Et 1011 porte AUSSI le bit 12 `TargetTileIsFree`, dont l'appel natif est
`IsFreeTile(tile, state, allowSteppable: 1, allowTemporaryTile: 0, allowAnyUnit: 0)` --
`IdunBattle.Entities.TileExtensions$$IsFreeTile` rend VRAI (« libre ») sur une tuile portee par une
unite `Steppable` (branche `allowSteppable != 0` : `IsEmpty()` faux -> `GetUnit` -> `HasTrait(0x1b)`
-> return true). LE PARTAGE DES DEUX REGLES EST DONC MESURABLE, et c'est le coeur de ce probe :

    tuile d'un DECOY, ability 1011 (bit 51 + bit 12)  ->  0x8000000000000  (refus par 51)
    tuile d'un DECOY, ability 1166 (bit 12 SANS 51)   ->  0x0              (12 ACCEPTE la tuile)

La seconde ligne est ce qui fait de la premiere une mesure DISCRIMINANTE : sans elle, 51 et 12
pourraient rendre le meme verdict sur la meme entree et l'accord ne prouverait rien. Les deux
masques ne different, sur ce point, que par le bit 51 :

    1011 TunnelingHorror   0x8000000001042 = bits 1 (dynamique) | 6 (tuile) | 12 | 51
    1166 AberrantHypermorph        0x1040  = bits            6 (tuile) | 12

LE MONTAGE, ET POURQUOI CELUI-LA (les deux montages nommes par #442 ont ete instruits)
-------------------------------------------------------------------------------------
Porteurs de 1011 : les npc `necroNpc4Destroyer*` et le summon `necroSmnDestroyer`, summon
d'ENVIRONNEMENT (`EnvFactionSummons:Necrons`) pose par le BOARD, sans summoner d'unite.

  MONTAGE 1 (`write_augmented_seed_bc` sur `necroSmnDestroyer`) -- MESURE, et il ECHOUE, mais pas
  la ou #442 le supposait : l'entree `necroSmnDestroyer` est DEJA au catalogue du seed BC (175
  entrees, stats a 0) et sa config `TunnelingHorror` est DEJA dans `BC.Abilities.ActiveAbilities`.
  `augment` n'a donc RIEN a ajouter (`added=[] abilities=[]`). Le refus vient de l'etage 2, celui
  qu'aucun enrichissement du catalogue ne leve (`case-92` §5bis) : `buildNormalizedBC` ->
  `IStatsFormula.StatsUsingProgressionIndexFor` ne couvre pas les summons, l'unite reste hors
  `normalized`, et `rl_duel build --a-units necroSmnDestroyer` sort en
  `hors pool / non spawnables au rank 17`.

  MONTAGE 3 -- GREFFE DE L'ACTIVE sur une unite du pool, recours 3 de `case-92` §5bis. C'est le
  montage joue ici (`catalog_inject.graft_active_ability`, ecrit par cette tranche : la recette
  ACTIVE etait DECRITE mais pas OUTILLEE, seul le volet passif l'etait). Greffon `necroWarden` --
  meme faction que le vrai porteur, au pool.

  ELLE EST NECESSAIRE, et le natif le dit : `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`
  commence par `ActiveAbilityComponent$$GetOrNull(unit, abilityType)` et rend
  `broken(ValidRequest)` quand l'unite ne possede pas l'ability -- on ne peut pas interroger le
  natif sur une ability qu'on n'a pas montee.

  ELLE EST EXACTE POUR CETTE MESURE : les `TargetingOptions` sont un champ de l'objet
  `AActiveAbility` resolu PAR TYPE, jamais lu sur l'unite -- le masque exerce est celui du ctor de
  `TunnelingHorrorAbility`. La limite habituelle de la greffe (« ni stats ni traits ni armes du vrai
  porteur ») ne mord sur aucune des quatre regles armees par 1011 (bits 1, 6, 12, 51), et la portee
  ne mord pas non plus : son `TargetingRange` est `useWholeBoard`.

LE SUBSTRAT : les unites `Steppable` sont des `genesSmnDecoy` poses par `CultDemagogue` (1179) de
`genesPrimus` -- exactement le montage de #442, dont ce probe reprend la geometrie.

TROIS ETAGES, mesures separement
--------------------------------
  A. SUBSTRAT -- l'etat rechargé porte-t-il `Steppable` sur les decoys ? (sinon la regle serait
     VERTE ET VIDE).
  B. LA VOIE DU BIT 51 (natif) -- 1011 castee par le greffon, tuile par tuile : decoys, unites
     non-Steppable, tuiles libres. Accord natif/port par ligne.
  C. LE PARTAGE 51 / 12 (natif) -- 1166 sur les MEMES tuiles, depuis un caster amene au contact.
     C'est la ligne qui interdit de confondre les deux regles.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_447_bit51_native.py
    python probe_447_bit51_native.py --seed 31337 --board C4_09 --graft necroImmortal

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
import catalog_inject as CI                                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc, bind_ambient_rpc   # noqa: E402

import probe_247_splash_targeting as P247                            # noqa: E402
import probe_436_taunt_targeting as P436                             # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait              # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (                      # noqa: E402
    _unit_traits, get_invalid_target_reason, has_steppable_unit)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

TUNNELING_HORROR = 1011      # SEUL porteur du bit 51 au registre ; TILE-targeting
ABERRANT_HYPERMORPH = 1166   # bit 12 SANS bit 51, TILE-targeting, RANGE_ADJACENT
CULT_DEMAGOGUE = 1179        # pose les `genesSmnDecoy`
DECOY_VIS = "genesSmnDecoy"
GRAFT_DEFAUT = "necroWarden"           # greffon du bit 51 -- Necron, au pool
DISCRIM_VIS = "genesBiophagus"         # porteur NATIF de 1166 (au pool)
P_UNITS_DEFAUT = "genesPrimus,genesBiophagus"
STEPPABLE_RULE = int(TR.TargetIsNotSteppable)
TILE_FREE_RULE = int(TR.TargetTileIsFree)


def _build(sid, seed, board, p_units, a_units, seed_bc):
    """`rl_duel build --seed-bc <greffe>` avec state-file PROPRE sous `logs/`. Meme mecanique
    d'attente sur le cap de runners que `probe_436._build`, qui ne sait pas passer `--seed-bc`."""
    import subprocess
    import time
    state = P247.ROOT / "logs" / ("_probe447-%d-%d.json" % (os.getpid(), next(P247._seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--seed-bc", str(seed_bc),
            "--p-units", ",".join(p_units), "--a-units", a_units]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(P247.PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-800:])
        time.sleep(10)


def _capture(sid, rid):
    dv = P247._dv(sid, rid)
    ob = P247._r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = P247._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = P247._r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    return dv, (dv, ob, snap, bg), bg


def _mk_state(payloads):
    dv, ob, snap, bg = payloads
    return load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))


def _tile_id(bg, pos):
    """id d'ENTITE de la tuile (col,row) -- le meme espace d'ids que `abilityReason.targetId` :
    `boardGraph` et `abilityReason` peuplent tous deux leur table par `forEachEntity`."""
    for t in bg["tiles"]:
        if t.get("col") == pos[0] and t.get("row") == pos[1]:
            return int(t["id"])
    return None


def _variant(klass, *, add=None, drop=None):
    """La classe du registre avec SON masque, un bit ajoute ou retire -- contrefactuel du CHAMP,
    jamais du code : une ligne que ce seul bit fait basculer prouve que c'est bien lui qui agit."""
    from dataclasses import replace as _replace
    base = klass.TARGETING_OPTIONS
    rules = int(base.rules)
    if add is not None:
        rules |= int(add)
    if drop is not None:
        rules &= ~int(drop)

    class _V(klass):                                                  # type: ignore[misc, valid-type]
        __slots__ = ()
        TARGETING_OPTIONS = _replace(base, rules=rules)
    return _V()


def _row(sid, rid, caster_id, aid, tile_id, st, port_ability):
    """UNE ligne de mesure : natif et port sur la MEME tuile, la MEME ability, le MEME caster."""
    nat = P247._nat(sid, rid, caster_id, aid, tile_id)
    tr = (nat or {}).get("targetReason") or {}
    nv = P247._hexval(tr)
    pv = int(get_invalid_target_reason(st, caster_id, tile_id, port_ability))
    return nv, pv, ",".join(tr.get("reasons") or []) or "-"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--graft", default=GRAFT_DEFAUT,
                    help="unite DU POOL qui recoit l'ACTIVE 1011 (greffe #92 §5bis)")
    ap.add_argument("--p-units", default=P_UNITS_DEFAUT)
    ap.add_argument("--free-tiles", type=int, default=3,
                    help="nombre de tuiles LIBRES a mesurer (non-degenerescence)")
    ap.add_argument("--sans-canal", action="store_true",
                    help="CONTRE-EPREUVE : rejoue le regime d'AVANT #448-r3-r1-r1 -- canal "
                         "`unitAbilityStates` muet ET registre de greffes purge (donc pas de "
                         "refus). C'est ce que ce probe mesurait, port AMPUTE compris.")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    p_units = [x for x in a.p_units.split(",") if x]

    # ⚠ LE CANAL, SANS QUOI CE PROBE MESURE UN PORT AMPUTE (#448-r3-r1-r1). Ce montage GREFFE une
    # ACTIVE (`TunnelingHorror` sur `necroWarden`) : `BC.Units[<greffon>].ActiveAbilities` la porte,
    # `gameconfig.unit("necroWarden").activeAbilities` NON. Sans le canal `unitAbilityStates`,
    # `snapshot._load_active_abilities` / `_load_config_active_abilities` / `_load_triggered_
    # abilities` ne posent RIEN et le port derive le kit du gameconfig -- il ne connait pas
    # l'ability qu'on mesure. `--sans-canal` reproduit ce regime pour la contre-epreuve : le foyer
    # (`snapshot._refuse_if_grafted`) LEVE alors au lieu de se degrader en silence, ce qui est tout
    # l'objet de la tranche.
    if not a.sans_canal:
        bind_ambient_rpc(sid)
        print("[canal] `unitAbilityStates` LIE en ambiant (bind_live_rpc)")
    else:
        print("[canal] MUET (--sans-canal) -- regime d'AVANT, port AMPUTE, refus neutralise")

    # ------------------------------------------------------------------ LE MONTAGE
    grafted = P247.ROOT / "logs" / ("_probe447-bc-%d.json" % os.getpid())
    bc_path, reports = CI.write_grafted_seed_bc(
        grafted, ["%s:TunnelingHorror" % a.graft], kind="active")
    print("[greffe] %s <- TunnelingHorror : %s" % (a.graft, json.dumps(reports[0])))
    if a.sans_canal:
        CI.clear_declared_grafts()      # neutralise le refus : on veut le VERDICT d'avant

    a_units = ",".join([a.graft] * 4)
    rid, state_file = _build(sid, a.seed, a.board, p_units, a_units, bc_path)
    print("[build] runner=%d board=%s seed=%s p=%s a=%s"
          % (rid, a.board, a.seed, ",".join(p_units), a_units))
    try:
        for _ in range(P247.TOURS_DE_CHAUFFE):
            P247._act(sid, rid, {"kind": "endturn"}, 60)

        victim_id = P436._make_adjacent(sid, rid, "genesPrimus", only_vis=a.graft)
        if victim_id is None:
            print("[FAIL] impossible d'amener genesPrimus au contact d'un %s" % a.graft)
            return 2
        P247._give_turn_to(sid, rid, "genesPrimus")
        dv_pre, _pre, _bg0 = _capture(sid, rid)
        primus = P247._by_vis(dv_pre, "genesPrimus")
        if primus is None:
            print("[FAIL] genesPrimus absent")
            return 2
        cid = int(primus["id"])
        act = {"kind": "ability", "casterId": cid, "abilityType": CULT_DEMAGOGUE,
               "targetId": victim_id}
        r = P247._act(sid, rid, act, 120)
        acts = ((r or {}).get("actions") or [{}])[0]
        print("[cast natif] CultDemagogue u%d -> u%d : mutated=%s"
              % (cid, victim_id, acts.get("mutated")))
        if not acts.get("mutated"):
            print("[FAIL] le cast natif n'a pas mute l'etat -> pas de decoy")
            return 2

        dv, payloads, bg = _capture(sid, rid)
        st = _mk_state(payloads)

        # -------------------------------------------------------- ETAGE A : le SUBSTRAT
        print("\n=== ETAGE A -- SUBSTRAT")
        decoys, others = [], []
        for u in dv["units"]:
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            tr = _unit_traits(st, tid) or ()
            if UnitTrait.Steppable.name in tr:
                decoys.append(tid)
            else:
                others.append(tid)
        print("  entites `Steppable` vivantes : %d %s" % (len(decoys), decoys))
        print("  dont visualId=%s : %s"
              % (DECOY_VIS, [int(u["id"]) for u in dv["units"]
                             if u.get("alive") and u.get("visualId") == DECOY_VIS]))
        okA = bool(decoys) and all(has_steppable_unit(st, t) for t in decoys)
        print("  [A] %s" % ("PASS" if okA else "FAIL"))
        if not okA:
            return 2

        # -------------------------------------------------------- ETAGE B : la voie du BIT 51
        pos_by_id = {int(u["id"]): P247._pos(u) for u in dv["units"] if u.get("alive")}
        occupied = set()
        for u in dv["units"]:
            if u.get("alive"):
                occupied.add(P247._pos(u))
        # le caster du bit 51 : un greffon VIVANT (ils portent tous l'active greffee)
        casters = [int(u["id"]) for u in dv["units"]
                   if u.get("alive") and u.get("visualId") == a.graft]
        if not casters:
            print("[FAIL] aucun %s vivant pour porter 1011" % a.graft)
            return 2
        bit_caster = casters[0]
        st_nat = P247._nat(sid, rid, bit_caster, TUNNELING_HORROR, None)
        print("\n=== ETAGE B -- la voie du BIT 51 (natif, ability %d de u%d %s)"
              % (TUNNELING_HORROR, bit_caster, a.graft))
        print("  [possession] abilityState=%s casterReason=%s"
              % (json.dumps((st_nat or {}).get("abilityState")),
                 json.dumps((st_nat or {}).get("casterReason"))))
        port_1011 = ABILITY_CLASSES[TUNNELING_HORROR]()

        libres = []
        for t in bg["tiles"]:
            pos = (t.get("col"), t.get("row"))
            if pos in occupied or not t.get("walkable", True):
                continue
            libres.append(int(t["id"]))
            if len(libres) >= a.free_tiles:
                break

        lignes = []
        for tid in decoys:
            lignes.append(("DECOY u%d" % tid, _tile_id(bg, pos_by_id[tid]), STEPPABLE_RULE))
        for tid in others:
            lignes.append(("unite u%d" % tid, _tile_id(bg, pos_by_id[tid]), TILE_FREE_RULE))
        for t in libres:
            lignes.append(("tuile LIBRE", t, 0))

        print("  %-16s %-7s %-18s %-26s %-18s %s"
              % ("cible", "tile", "natif", "regle natif", "port", "verdict"))
        nB = okB = 0
        n_51 = n_12 = n_ok = 0
        rows_b = []
        for label, tile_id, attendu in lignes:
            if tile_id is None:
                continue
            nv, pv, reasons = _row(sid, rid, bit_caster, TUNNELING_HORROR, tile_id, st, port_1011)
            nB += 1
            agree = (nv == pv)
            conforme = (nv == attendu)
            okB += 1 if (agree and conforme) else 0
            n_51 += 1 if nv == STEPPABLE_RULE else 0
            n_12 += 1 if nv == TILE_FREE_RULE else 0
            n_ok += 1 if nv == 0 else 0
            print("  %-16s t%-6s %-18s %-26s %-18s %s"
                  % (label, tile_id, "-" if nv is None else hex(nv), reasons[:26], hex(pv),
                     ("OK" if agree else "MISMATCH")
                     + ("" if conforme else " /ATTENDU %s" % hex(attendu))))
            rows_b.append({"label": label, "tile": tile_id, "nat": nv, "port": pv,
                           "attendu": attendu})
        passB = (okB == nB and nB > 0 and n_51 > 0 and n_12 > 0 and n_ok > 0)
        print("  [bilan B] %d/%d lignes natif==port ET conformes ; refus 51 : %d ; refus 12 : %d ; "
              "acceptees : %d" % (okB, nB, n_51, n_12, n_ok))
        print("  [B] %s" % ("PASS" if passB else "FAIL"))

        # -------------------------------------------------------- ETAGE C : le PARTAGE 51 / 12
        #
        # 1166 est `RANGE_ADJACENT` : on AMENE le caster au contact de CHAQUE decoy tour a tour --
        # la geometrie n'est jamais une excuse. `_bring_within` mesure la distance ATTEINTE.
        #
        # ⚠ NE PAS ATTENDRE `0x0` SUR TOUTE TUILE A d=1. L'adjacence native
        # (`MovementUtil$$AreTilesAdjacent`) est GATEE EN ELEVATION (`|dElev| < 2`) : une tuile
        # voisine en hex mais separee de 2 niveaux rend `TargetIsInRange`. MESURE au premier jet
        # (t24, seed 777 / MC1_67) -- natif ET port rendaient `0x8000000` d'accord. L'attendu ci-
        # dessous accepte donc `TargetIsInRange` partout ou la portee peut mordre, et la
        # NON-DEGENERESCENCE est portee par des compteurs explicites, pas par un attendu rigide.
        print("\n=== ETAGE C -- le PARTAGE 51 / 12 (natif, ability %d = bit 12 SANS bit 51)"
              % ABERRANT_HYPERMORPH)
        if P247._by_vis(dv, DISCRIM_VIS) is None:
            print("  [C] FAIL -- %s absent du roster" % DISCRIM_VIS)
            return 2
        port_1166 = ABILITY_CLASSES[ABERRANT_HYPERMORPH]()
        in_range = int(TR.TargetIsInRange)
        print("  %-16s %-7s %-18s %-26s %-18s %-18s %s"
              % ("cible", "tile", "natif 1166", "regle natif", "port 1166", "natif 1011",
                 "verdict"))
        nC = okC = n_disc = n_c_refus = n_c_accept = 0
        rows_c = []

        def _mesure_c(label, tile_id, attendus, st_c, bio_id):
            nonlocal nC, okC, n_disc, n_c_refus, n_c_accept
            if tile_id is None:
                return
            nv, pv, reasons = _row(sid, rid, bio_id, ABERRANT_HYPERMORPH, tile_id, st_c, port_1166)
            # la MEME tuile vue par 1011 (bit 51), depuis le greffon -- c'est LA comparaison
            nv11, pv11, _r11 = _row(sid, rid, bit_caster, TUNNELING_HORROR, tile_id, st_c,
                                    port_1011)
            nC += 1
            agree = (nv == pv) and (nv11 == pv11)
            conforme = nv in attendus
            okC += 1 if (agree and conforme) else 0
            if label.startswith("DECOY") and nv == 0 and nv11 == STEPPABLE_RULE:
                n_disc += 1
            n_c_refus += 1 if nv == TILE_FREE_RULE else 0
            n_c_accept += 1 if nv == 0 else 0
            print("  %-16s t%-6s %-18s %-26s %-18s %-18s %s"
                  % (label, tile_id, "-" if nv is None else hex(nv), reasons[:26], hex(pv),
                     "-" if nv11 is None else hex(nv11),
                     ("OK" if agree else "MISMATCH")
                     + ("" if conforme else " /ATTENDU %s" % [hex(x) for x in attendus])))
            rows_c.append({"label": label, "tile": tile_id, "nat1166": nv, "port1166": pv,
                           "nat1011": nv11, "port1011": pv11})

        for dec in decoys:
            got = P436._bring_within(sid, rid, DISCRIM_VIS, dec, 1)
            dv, payloads, bg = _capture(sid, rid)
            st = _mk_state(payloads)
            bio = P247._by_vis(dv, DISCRIM_VIS)
            if bio is None:
                print("  [contact] %s introuvable -- decoy u%d NON MESURE" % (DISCRIM_VIS, dec))
                continue
            bio_id, bio_pos = int(bio["id"]), P247._pos(bio)
            pos_by_id = {int(u["id"]): P247._pos(u) for u in dv["units"] if u.get("alive")}
            if dec not in pos_by_id:
                print("  [contact] decoy u%d disparu -- NON MESURE" % dec)
                continue
            print("  [contact] %s@%s a d=%s du decoy u%d" % (DISCRIM_VIS, bio_pos, got, dec))
            _mesure_c("DECOY u%d" % dec, _tile_id(bg, pos_by_id[dec]), (0, in_range), st, bio_id)
            # CONTEXTE de non-degenerescence, pris dans le MEME etat : une unite normale voisine
            # (1166 doit REFUSER par 12) et une tuile libre voisine (1166 doit ACCEPTER).
            occupied = set(pos_by_id.values())
            for tid2, pos2 in pos_by_id.items():
                if tid2 in decoys or hexgeo.distance(bio_pos, pos2) != 1:
                    continue
                _mesure_c("unite u%d" % tid2, _tile_id(bg, pos2), (TILE_FREE_RULE, in_range),
                          st, bio_id)
                break
            for t in bg["tiles"]:
                pos2 = (t.get("col"), t.get("row"))
                if pos2 in occupied or not t.get("walkable", True):
                    continue
                if hexgeo.distance(bio_pos, pos2) == 1:
                    _mesure_c("tuile LIBRE", int(t["id"]), (0, in_range), st, bio_id)
                    break

        passC = (okC == nC and nC > 0 and n_disc > 0 and n_c_refus > 0 and n_c_accept > 0)
        print("  [bilan C] %d/%d lignes conformes ET natif==port sur les DEUX abilities ; "
              "lignes DISCRIMINANTES (1011 refuse 51, 1166 ACCEPTE la meme tuile) : %d ; "
              "1166 refuse par 12 : %d ; 1166 accepte : %d"
              % (okC, nC, n_disc, n_c_refus, n_c_accept))
        print("  [C] %s -- une tuile qu'un decoy occupe est REFUSEE par 51 et NON par 12 "
              "(`IsFreeTile(..., allowSteppable: 1, ...)`)" % ("PASS" if passC else "FAIL"))

        # -------------------------------------------------------- ETAGE D : ce que le BIT est SEUL
        # a faire (offline sur les VRAIES classes du registre -- contrefactuel du CHAMP, pas du code)
        print("\n=== ETAGE D -- l'armement du bit 51 chez 1011 (offline, classes du registre)")
        dv, payloads, bg = _capture(sid, rid)
        st = _mk_state(payloads)
        pos_by_id = {int(u["id"]): P247._pos(u) for u in dv["units"] if u.get("alive")}
        o11 = ABILITY_CLASSES[TUNNELING_HORROR].TARGETING_OPTIONS
        o66 = ABILITY_CLASSES[ABERRANT_HYPERMORPH].TARGETING_OPTIONS
        print("  1011 rules=%s is_unit_targeting=%s has(bit51)=%s"
              % (hex(int(o11.rules)), o11.is_unit_targeting, o11.has(TR.TargetIsNotSteppable)))
        print("  1166 rules=%s is_unit_targeting=%s has(bit51)=%s"
              % (hex(int(o66.rules)), o66.is_unit_targeting, o66.has(TR.TargetIsNotSteppable)))
        okD1 = (not o11.is_unit_targeting) and o11.has(TR.TargetIsNotSteppable)
        print("  [D1] %s -- chez 1011 la voie IMPLICITE (`get_IsUnitTargeting`) est FERMEE : "
              "l'armement mesure a l'etage B ne peut venir QUE du bit 51" % ("PASS" if okD1 else "FAIL"))
        # bit 20 sur le masque de 1011 : le natif branche `else: goto TEST` AVANT de le tester.
        sans51 = _variant(ABILITY_CLASSES[TUNNELING_HORROR], drop=TR.TargetIsNotSteppable)
        avec20 = _variant(ABILITY_CLASSES[TUNNELING_HORROR], add=TR.AllowSteppableUnit)
        d_sans = [int(get_invalid_target_reason(st, bit_caster, _tile_id(bg, pos_by_id[d]), sans51))
                  for d in decoys if d in pos_by_id]
        d_avec = [int(get_invalid_target_reason(st, bit_caster, _tile_id(bg, pos_by_id[d]), avec20))
                  for d in decoys if d in pos_by_id]
        okD2 = bool(d_sans) and all(v != STEPPABLE_RULE for v in d_sans)
        okD3 = bool(d_avec) and all(v == STEPPABLE_RULE for v in d_avec)
        print("  [D2] %s -- 1011 PRIVEE du bit 51 n'oppose plus le refus : %s"
              % ("PASS" if okD2 else "FAIL", [hex(v) for v in d_sans]))
        print("  [D3] %s -- 1011 AVEC `AllowSteppableUnit` (bit 20) refuse QUAND MEME : %s   "
              "(NON CONFRONTE au natif : 0 porteur du bit 20 au registre)"
              % ("PASS" if okD3 else "FAIL", [hex(v) for v in d_avec]))
        passD = okD1 and okD2 and okD3

        allok = okA and passB and passC and passD
        print("\n[VERDICT] %s" % ("PASS" if allok else "FAIL"))
        print("[RAW] " + json.dumps({"graft": a.graft, "bitCaster": bit_caster,
                                     "decoys": decoys, "B": rows_b, "C": rows_c,
                                     "D": {"sans51": d_sans, "avec20": d_avec}}))
        return 0 if allok else 1
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            bc_path.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
