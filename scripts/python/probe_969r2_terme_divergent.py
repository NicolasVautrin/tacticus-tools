#!/usr/bin/env python3
"""#969-r2 -- QUEL TERME de l'utilite de `DeathFromAbovePlaybook` diverge ?

Le residu est mesure : le natif caste `1003` sur `u77`, le port sur `u114`. La question n'est PAS
<< le port est-il faux >> (on le sait) mais **lequel des etages du scoring**. Ce probe les separe,
il ne fitte aucun scalaire.

L'utilite est `GetNumPossibleSpawnTilesForTarget(cible)`, et l'arbre natif est LU (relu VERBATIM
sur `rnca9r7q6c`) :

    `IdunBattle.AI.Playbook.Loki.DeathFromAbovePlaybook$$EvaluateNonComparable` :
        foreach (e in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile))
            bucket.AddAction(GenerateAction(pos, e.Target, Fix64(GetNumPossibleSpawnTilesForTarget)))

    `...$$GetNumPossibleSpawnTilesForTarget` -> le corps que Ghidra nomme
    `SpawnTermagantsAbility$$u003CExecuteBehaviouru003Eb__1_0` (fusion ICF) :
        CanAddUnit( AdjacentTiles( Entity(target) ) )          puis slot `Count`

    `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` appelle, PAR TUILE,
    `IdunBattle.Entities.TileExtensions$$CanAddUnitFromAbility(tile, state, parent, allowSteppable)`
      -> `IsFreeTile(tile, state, allowSteppable, allowTemporaryTile: 0, allowAnyUnit: 0)`
         && !`IsTileReservedForOtherUnit(tile, parent)`
         && !`IsTilePendingDrafting(tile, state)`

    et `IdunBattle.Entities.TileExtensions$$IsFreeTile` decide l'OCCUPATION par
    **`IdunBattle.Entities.Components.TileContentComponent$$IsEmpty(tile+0x38)`** -- le contenu de
    LA TUILE. Ce n'est donc PAS une liste de positions d'unites : toute tuile sous N'IMPORTE QUEL
    pied est occupee. Le port, lui, construit `occupied = set(ctx.epos) | set(ctx.fpos) | {origin}`,
    et `engine/ai/context.py` ne met dans ces deux listes que la **MAIN TILE** de chaque unite.

QUATRE ETAGES, mesures separement -- l'appariement tranche SEUL :

  E0  MULTI-HEX PRESENT ?   `dv.units[].feet` de longueur > 1. Si AUCUNE unite multi-hex n'est en
                            jeu, le mecanisme ci-dessus n'explique PAS cet ecart-la, et le dire est
                            le resultat (piege #925-r1 : reproduire le symptome ne valide pas la
                            cause).
  E1  ENSEMBLE DE CIBLES    cardinal du port (`_targets.eligible_units`), rendu TEL QUEL.
                            ⚠ **`actionCount` NE MESURE PAS le cardinal natif, et le croire est un
                            FAUX POSITIF que ce probe a d'abord produit** : `countActions`
                            (`frida/hooks/ai-toolkit/bucket-decode.ts`) somme le champ `best` de la
                            racine et de chaque sous-bucket, or `Bucket$$AddAction` ECRASE `best`
                            (remplacement sur `>` STRICT). `DeathFromAbovePlaybook` n'ouvre AUCUN
                            sous-bucket -> `actionCount` vaut **1 des qu'une seule action est
                            admise**, quel que soit le nombre de cibles. Il est affiche comme
                            CONTEXTE, jamais comme cardinal.
  E2  COMPTE PAR CIBLE      `util` natif (= le compte de la cible GAGNANTE, l'utilite de 1003 ETANT
                            ce compte) confronte aux comptes du port, cible par cible. C'est le
                            SEUL appariement disponible, et il exige un montage NON DEGENERE (des
                            comptes DISTINCTS), sans quoi `util` ne designe aucune cible.
  E3  ORDRE / ARGMAX        `util` natif EGAL au max du port mais correspondant a une AUTRE cible
                            => ENSEMBLE ou ORDRE ; `port_max > util_natif` => SUR-COMPTE ou cible
                            invisible du natif.
  E4  CONTRE-EPREUVE        le meme compte, mais avec l'occupation derivee de l'EMPREINTE
                            (`dv.units[].feet`). Si E2 accusait un sur-compte et que E4 le
                            resorbe, la cause est etablie ; sinon elle est ailleurs.
  E5  FILTRE MANQUANT       `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`
                            applique, APRES le slot `0x42` d'`IAttackQuery` et AVANT la boucle, un
                            `ListExtensions.Remove(targets, t => !this.ShouldEvaluateTarget(t))`
                            (slot VIRTUEL `0x248`, lambda
                            `...BasePlaybook$$u003CGetEligibleTargetsEntitiesu003Eb__58_0`). Le
                            corps de base est
                            `!(IsUnit(t) && CurrentOwnerIsEnvironment(t, state)) && !IsIrrelevantObject(t)`.
                            Le port n'a AUCUN homologue : `fromHere` est la sortie du slot, SANS ce
                            `Remove`. Cet etage compte les cibles que le filtre RETIRERAIT.

⚠ REGIME DEGENERE : un montage ou toutes les cibles ont le MEME compte, ou dont le bucket ne porte
qu'UNE action, ne DISCRIMINE RIEN -- les deux hypotheses y rendent le meme resultat. Le probe le
DIT (`DEGENERE`) au lieu de rendre un accord.

Sortie ASCII stricte. Monte UN runner, le dispose.

Usage :
    python probe_969r2_terme_divergent.py [--seed 777] [--board MC1_67] [--steps 8]
                                          [--state-file <absolu>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

ABILITY = 1003          # `ActiveAbilityType.DeathFromAbove`, argument du ctor natif (0x3eb)


def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc
    return _resolve_session, _rpc


def _build(seed, board, state_file, p_units=None, a_units=None, place=(), a_place=()):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board]
    if p_units:
        cmd += ["--p-units", p_units]
    if a_units:
        cmd += ["--a-units", a_units]
    for p in place:
        cmd += ["--place", p]
    for p in a_place:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return json.loads(Path(state_file).read_text())


def _feet_of(u) -> list:
    """Empreinte publiee par `decisionView` (`projection.ts` : `feet = readEntityFeet(e, state)`,
    mirror d'`IdunBattle.Entities.EntityExtensions$$GetTiles`). TRI-ETAT : `None` = pas mesure."""
    f = u.get("feet")
    if not isinstance(f, list):
        return []
    return [(t.get("col"), t.get("row")) for t in f
            if isinstance(t, dict) and t.get("col") is not None]


def _occupied_par_pied(dv, uid) -> set:
    """CONTRE-EPREUVE E4 : l'occupation telle que `TileContentComponent$$IsEmpty` la voit --
    TOUTES les tuiles sous un pied, de TOUTE unite vivante, self compris (le natif ne fait aucune
    exception pour le caster : sa propre tuile porte son contenu)."""
    occ = set()
    for u in (dv.get("units") or []):
        if u.get("alive") is False:
            continue
        for p in _feet_of(u):
            occ.add(p)
        pos = u.get("pos") or {}
        if pos.get("col") is not None:
            occ.add((pos["col"], pos["row"]))
    return occ


def _sonde(etat, r, sid, rid):
    """Sonde par-etage, branchee sur `engine_validate.run_agreement` (appelee AVANT `applyAction`,
    donc sur l'etat de DECISION -- le meme que le natif a lu)."""
    from engine.playbook import noncomparable as PB
    from engine.playbook.noncomparable import _targets as T
    from engine import battle_query as bq

    def probe(step, uid, dv, mov_by_unit, nat, eng, predictor):
        na = (nat or {}).get("ability") or {}
        eb = (eng or {}) if isinstance(eng, dict) else {}
        # DECLENCHEUR = le PORTEUR, pas ce que le natif a RETENU. `ShouldEvaluate` finit par un
        # TIRAGE RNG (`this.<+0x30>.<slot 4>(prob)`), donc exiger que le natif ait caste 1003
        # rendrait la mesure dependante d'un tirage -- et un pas ou il ne tire pas se lirait comme
        # << pas de regime >>. `ncEvaluate` invoque le playbook DIRECTEMENT : le bucket existe que
        # le natif ait retenu l'ability ou non.
        row = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        porte = any(a.get("id") == ABILITY for a in ((row or {}).get("abilities") or []))
        interesse = porte or (na.get("ability") == ABILITY) or (eb.get("ability") == ABILITY)
        if not interesse:
            return
        pb = PB.playbook_for(ABILITY)
        if pb is None:
            etat["lignes"].append({"step": step, "erreur": "1003 hors registre PLAYBOOKS"})
            return
        nc = etat["ctx"](uid)

        # --- E0 : multi-hex en jeu ? -------------------------------------------------------
        multi = []
        feet_mesure = 0
        for u in (dv.get("units") or []):
            if u.get("alive") is False:
                continue
            f = _feet_of(u)
            if u.get("feet") is not None:
                feet_mesure += 1
            if len(f) > 1:
                multi.append({"id": u.get("id"), "visualId": u.get("visualId"),
                              "feet": f, "ctrl": bool(u.get("ctrl"))})

        # --- E1 / E2 / E3 : cote PORT ------------------------------------------------------
        cibles = [(tid, p) for (tid, p) in T.eligible_units(nc, ABILITY) if p is not None]
        comptes = [(tid, p, int(pb._spawn_tiles(nc, tuple(p)))) for (tid, p) in cibles]
        port_max = max([c for (_t, _p, c) in comptes], default=None)
        port_argmax = next((t for (t, _p, c) in comptes if c == port_max), None)

        # --- E4 : le MEME compte, occupation derivee de l'EMPREINTE -------------------------
        occ_pied = _occupied_par_pied(dv, uid)
        comptes_pied = [(tid, p,
                         bq.adjacent_addable_count(tuple(p), nc.neigh_by_pos,
                                                   nc.walkable_by_pos, occ_pied, nc.elev_by_pos))
                        for (tid, p) in cibles]
        pied_max = max([c for (_t, _p, c) in comptes_pied], default=None)
        pied_argmax = next((t for (t, _p, c) in comptes_pied if c == pied_max), None)

        # --- E5 : le filtre `ShouldEvaluateTarget`, et ce que le port peut en SAVOIR -------
        row_by_id = {u.get("id"): u for u in (dv.get("units") or [])}
        e5 = []
        for (tid, p) in cibles:
            u = row_by_id.get(tid) or {}
            e5.append({"id": tid, "visualId": u.get("visualId"),
                       # SUBSTRAT ABSENT : ni `CurrentOwnerIsEnvironment` ni `IsIrrelevantObject`
                       # n'ont de canal publie par unite. On le DIT, on n'invente pas un verdict.
                       "environment": u.get("isEnvironment", "NON MESURE"),
                       "irrelevant": u.get("isIrrelevantObject", "NON MESURE"),
                       "retiree": None})

        # --- voisinage NATIF de chaque cible, pour PILOTER le montage vers un regime non
        #     degenere (c'est le seul moyen de faire varier le compte a dessein) -------------
        occ_main = set(nc.epos or ()) | set(nc.fpos or ())
        if nc.origin is not None:
            occ_main.add(nc.origin)
        voisinage = []
        for (tid, p) in cibles:
            vs = (nc.neigh_by_pos or {}).get((p[0], p[1])) or []
            voisinage.append({"id": tid, "pos": list(p), "voisins": [
                {"p": list(v), "walkable": bool((nc.walkable_by_pos or {}).get((v[0], v[1]))),
                 "occupee": (v[0], v[1]) in occ_main} for v in vs]})

        # --- cote NATIF : `ncEvaluate` (util / targetLow / actionCount PAR POSITION) --------
        nat_eval = r(sid, "ncEvaluate",
                     {"runnerId": rid, "unitId": uid, "abilityType": ABILITY, "sweep": True}, 300)
        positions = (nat_eval or {}).get("positions") or []
        # L'ORIGINE est en tete du sweep (`GetCurrentAndMovablePositionsFor` seede la position
        # courante) : c'est la position que compare `EvaluateNonComparable` a l'origine, et la
        # seule dont le port produit un homologue (`fromHere`).
        p0 = positions[0] if positions else {}
        etat["lignes"].append({
            "step": step, "uid": uid,
            "nat_ability": na.get("ability"), "nat_target": na.get("target"),
            "port_ability": eb.get("ability"), "port_target": eb.get("target"),
            "E0_multi_hex": multi, "E0_feet_mesure": feet_mesure,
            "E0_units_vivantes": len([u for u in (dv.get("units") or [])
                                      if u.get("alive") is not False]),
            "E1_port_cardinal": len(cibles),
            "E1_nat_actionCount": p0.get("actionCount"),
            "E2_port_max": port_max, "E2_nat_util": p0.get("util"),
            "E3_port_argmax": port_argmax, "E3_nat_targetLow": (p0.get("action") or {}).get("targetLow"),
            "comptes_port": [(t, list(p), c) for (t, p, c) in comptes],
            "E4_comptes_pied": [(t, list(p), c) for (t, p, c) in comptes_pied],
            "E4_pied_max": pied_max, "E4_pied_argmax": pied_argmax,
            "E5": e5, "voisinage": voisinage,
            "nat_pos0": list(p0.get("pos") or []), "port_origin": list(nc.origin or []),
            "nat_positions": len(positions),
        })
    return probe


def _afficher(lignes) -> int:
    if not lignes:
        print("AUCUN pas n'a mis 1003 en jeu -- ni le natif ni le port ne l'ont proposee.")
        print("Ce n'est PAS une mesure de l'ecart : le montage n'a pas atteint le regime vise.")
        return 3
    rc = 0
    for L in lignes:
        if "erreur" in L:
            print("pas %s : ERREUR %s" % (L.get("step"), L["erreur"]))
            rc = 2
            continue
        print("=" * 88)
        print("PAS %s  caster u%s   natif(ab=%s,tgt=%s)   port(ab=%s,tgt=%s)"
              % (L["step"], L["uid"], L["nat_ability"], L["nat_target"],
                 L["port_ability"], L["port_target"]))
        print("-" * 88)
        print("E0  unites vivantes %d, dont `feet` mesure sur %d ; MULTI-HEX : %d"
              % (L["E0_units_vivantes"], L["E0_feet_mesure"], len(L["E0_multi_hex"])))
        for m in L["E0_multi_hex"]:
            print("      u%-4s %-22s pieds=%s ctrl=%s"
                  % (m["id"], m["visualId"], m["feet"], m["ctrl"]))
        if not L["E0_multi_hex"]:
            print("      AUCUNE -- le mecanisme MULTI-HEX n'explique PAS cet ecart-la.")
        print("E1  cardinal des cibles   port=%s        (natif : NON OBSERVABLE ici -- "
              "actionCount=%s ne compte que les `best` de l'arbre, cf. l'en-tete)"
              % (L["E1_port_cardinal"], L["E1_nat_actionCount"]))
        print("E2  utilite max           port=%s   natif(util)=%s   position natif=%s "
              "(origine port=%s)"
              % (L["E2_port_max"], L["E2_nat_util"], L.get("nat_pos0"), L.get("port_origin")))
        print("E3  argmax                port=u%s  natif(targetLow)=%s (pointeur, non traduit)"
              % (L["E3_port_argmax"], L["E3_nat_targetLow"]))
        print("    comptes PORT par cible (occupation = main tiles) :")
        for (t, p, c) in L["comptes_port"]:
            print("      u%-4s @%-9s -> %d" % (t, tuple(p), c))
        vals = sorted({c for (_t, _p, c) in L["comptes_port"]})
        if len(vals) <= 1:
            print("    ⚠ DEGENERE : toutes les cibles ont le MEME compte %s -- `util` natif ne "
                  "DESIGNE aucune cible, ce pas ne discrimine RIEN." % (vals or "aucune"))
        else:
            u = L["E2_nat_util"]
            cands = [t for (t, _p, c) in L["comptes_port"] if u is not None and abs(c - u) < 1e-9]
            print("    NON DEGENERE : comptes distincts %s ; `util` natif %s <-> cible(s) port %s"
                  % (vals, u, cands or "AUCUNE (le natif compte autre chose)"))
        print("E5  filtre `ShouldEvaluateTarget` (slot 0x248) -- cibles que le natif RETIRERAIT :")
        for row in L.get("E5", []):
            print("      u%-4s %-22s environment=%s irrelevant=%s -> %s"
                  % (row["id"], row["visualId"], row["environment"], row["irrelevant"],
                     "RETIREE" if row["retiree"] else "gardee"))
        if not L.get("E5"):
            print("      (aucune cible)")
        print("VOISINAGE NATIF des cibles (pour PILOTER le montage vers un regime non degenere) :")
        for v in L.get("voisinage", []):
            libres = [tuple(x["p"]) for x in v["voisins"] if x["walkable"] and not x["occupee"]]
            print("      u%-4s @%-9s %d voisins, LIBRES %d : %s"
                  % (v["id"], tuple(v["pos"]), len(v["voisins"]), len(libres), libres))
        print("E4  comptes avec occupation PAR PIED (`TileContentComponent.IsEmpty`) :")
        for (t, p, c) in L["E4_comptes_pied"]:
            print("      u%-4s @%-9s -> %d" % (t, tuple(p), c))
        print("    max=%s argmax=u%s   (port main-tile : max=%s argmax=u%s)"
              % (L["E4_pied_max"], L["E4_pied_argmax"], L["E2_port_max"], L["E3_port_argmax"]))
        if L["E4_pied_argmax"] != L["E3_port_argmax"]:
            print("    -> L'OCCUPATION PAR PIED CHANGE L'ARGMAX : u%s -> u%s"
                  % (L["E3_port_argmax"], L["E4_pied_argmax"]))
        else:
            print("    -> occupation par pied SANS EFFET sur l'argmax a ce pas.")
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--p-units", default=None)
    ap.add_argument("--a-units", default=None)
    ap.add_argument("--place", action="append", default=[])
    ap.add_argument("--a-place", action="append", default=[])
    args = ap.parse_args()

    resolve, rpc = _rpc_mod()
    sid = resolve()

    def r(_sid, m, b, t=120):
        return (rpc(_sid, m, [b], timeout=t).get("result") or {})

    sf = Path(args.state_file or (ROOT / "logs" / "runners" /
                                  ("p969r2-%s.json" % uuid.uuid4().hex[:8])))
    sf.parent.mkdir(parents=True, exist_ok=True)
    st = _build(args.seed, args.board, sf, args.p_units, args.a_units,
                args.place, args.a_place)
    rid = int(st["runnerId"])
    print("MONTAGE : runner %d, board %s, seed %d, steps %d, p=%s a=%s"
          % (rid, args.board, args.seed, args.steps, args.p_units or "(defaut)",
             args.a_units or "(defaut)"))

    etat = {"lignes": []}

    def _ctx(uid):
        from engine.ai import context as _ai_ctx
        from engine.playbook import noncomparable as PB
        from engine import weights
        from engine.playbook import scene as _scene
        from engine.runner import snapshot as _snapshot
        dv = r(sid, "decisionView",
               _snapshot.decision_view_seed_body(rid, allAbilities=True, maxRank=32), 180)
        mov = r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        predictor = _scene.build_predictor(lambda m, b, t: r(sid, m, b, t), rid)
        c = _ai_ctx.build(lambda m, b, t: r(sid, m, b, t), rid, dv, mov_by_unit, uid,
                          weights.load(), predictor)
        return PB.NCContext(
            uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
            enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
            plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
            elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
            is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
            obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
            active_levels=c.active_ability_levels, ability_config=c.heal_config,
            units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)

    etat["ctx"] = _ctx

    rc = 0
    try:
        import engine_validate as EV
        from engine import weights
        EV.run_agreement(sid, rid, args.steps, weights.load(),
                         log=lambda s: print("  " + str(s)),
                         probe=_sonde(etat, r, sid, rid))
        print()
        rc = _afficher(etat["lignes"])
    finally:
        try:
            r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
        try:
            sf.unlink()
        except OSError:
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
