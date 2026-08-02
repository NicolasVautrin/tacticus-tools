"""#425 -- OU se perd la marque de tuile, entre le capteur `readEffectsByTile` et le
consommateur `load_state` ?

#448-r1 a mesure, sur le montage `StormboyzStrike`/`orksNob` : entites `EntityType.Effect`
17 -> 18 apres le `finish`, et AUCUNE tuile marquee dans `tileMeta` (meme sous
`includeInactive: true`). Il a laisse le point NON TRANCHE, faute de canal nominatif : le
+1 d'entite n'etait pas identifie, donc « la tuile ne possede pas l'effet » et « le capteur
le filtre » restaient indiscernables.

CE PROBE TRANCHE PAR LA VALEUR DE RETOUR, pas par le silence (cf. l'absence d'un evenement
ne prouve rien) : `effectAbilityStates` (rpc-snapshot.ts) balaie TOUTES les entites
`EntityType.Effect` et publie, pour chacune, `{effectId, effectType, name, source, active}`
-- sans AUCUN filtre d'appartenance (ni owner, ni tuile, ni unite). Le diff des ids
avant/apres NOMME donc l'entite creee.

Etages confrontes, un par un :
  E1  NATIF        -- l'entite Effect creee porte-t-elle bien `effectType == 1179` ?
                      (`effectAbilityStates`, canal sans filtre)
  E2  DECODEUR     -- la tuile publie-t-elle cet effet (`tileMeta`, `readEffectsByTile`) ?
  E3  AUTRE PORTEUR-- l'effet apparait-il sur une UNITE (`decisionView.units[].effects`,
                      `readEffectsByUnit`, MEME decodeur, MEME liste `ActiveEffectIds`) ?
  E4  MONTAGE      -- le regime joue marque-t-il seulement une tuile ? (pos du porteur
                      avant/apres, entite-tuile d'atterrissage via `boardGraph`)

E2 et E3 partagent le decodeur ET la structure lue (`EffectsOwnedComponent.ActiveEffectIds`,
`Blueprints$$Tile` l'attache a TOUTE tuile, slot `TileEntity+0x58`) : si l'effet sort en E3
et pas en E2, le decodeur est hors de cause et c'est l'OWNER qui n'est pas une tuile.

Reproduction :
    python probe_425_tile_effect_channel.py --live
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

ABILITY = "StormboyzStrike"
TELEPORTING_IN = 0x474            # 1140 EffectType.StormboyzStrike_TeleportingIn
ALREADY_USED_TILE = 0x49B         # 1179 EffectType.StormboyzStrike_AlreadyUsedTile


def _effects_index(rows) -> dict:
    """`effectAbilityStates.effects[]` -> {effectId: row}. Canal SANS filtre d'appartenance."""
    out = {}
    for e in (rows or []):
        if isinstance(e, dict) and e.get("effectId") is not None:
            out[int(e["effectId"])] = e
    return out


def volet_live(board: str, seed: int, graft: str, foes: list,
               allies: list = None, tag: str = "") -> dict:
    import catalog_inject as CI
    from rl_collect_batch import _resolve_session, _rpc

    def rpc(sid, m, args, t=120):
        r = _rpc(sid, m, [args], timeout=t)
        return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}

    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    suffix = ("_" + tag) if tag else ""
    state_file = logs / ("p425_tile_channel_state%s.json" % suffix)
    bc_path = logs / ("p425_tile_channel_bc%s.json" % suffix)

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    rep = CI.graft_passive_ability(bc, graft, ABILITY)
    bc_path.write_text(json.dumps(bc), encoding="utf-8")
    print("== #425 live -- greffe %s sur %s : %s" % (ABILITY, graft, rep))

    # ROSTER ALLIE -- discriminant du bras « fin de tour d'EQUIPE ». Avec le seul porteur,
    # son `finish` CLOT le tour de son equipe : tout effet pose a `turns: 1` PENDANT ce
    # meme `applyAction` voit sa duree decrementer aussitot. Un allie qui n'a pas fini
    # garde le tour d'equipe ouvert.
    p_units = [graft] + [a for a in (allies or []) if a]

    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", ",".join(p_units),
           "--a-units", ",".join(foes), "--no-ai",
           "--seed-bc", str(bc_path), "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        sys.stdout.write((p.stdout or "")[-2000:])
        sys.stdout.write((p.stderr or "")[-2000:])
        raise SystemExit("build KO")
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    sid = _resolve_session()
    print("   runner %s (session %s)" % (rid, sid))
    out = {"runner": rid, "graft": graft, "board": board, "seed": seed}
    try:
        def snapshot(tag):
            # CANAL SANS FILTRE : toutes les entites EntityType.Effect, quel que soit leur owner.
            eas = rpc(sid, "effectAbilityStates", {"runnerId": rid}, 120)
            idx = _effects_index(eas.get("effects"))
            tm = rpc(sid, "tileMeta", {"runnerId": rid, "includeInactive": True}, 90)
            tiles = tm.get("tiles") if isinstance(tm, dict) else None
            if tiles is None and isinstance(tm, list):
                tiles = tm
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                           "allAbilities": True, "includeInactive": True}, 150)
            # Tous les ids d'effet publies PAR PORTEUR (unites + mows) = la voie
            # `readEffectsByUnit`, MEME decodeur, MEME `EffectsOwnedComponent.ActiveEffectIds`.
            by_unit = {}
            for u in (dv.get("units") or []) + (dv.get("mows") or []):
                for e in (u.get("effects") or []):
                    if e.get("effectId") is not None:
                        by_unit[int(e["effectId"])] = (u.get("id"), e.get("effectType"),
                                                       e.get("name"), e.get("active"))
            by_tile = {}
            tile_rows = []
            for t in (tiles or []):
                effs = t.get("effects") or []
                if effs:
                    tile_rows.append({"col": t.get("col"), "row": t.get("row"),
                                      "eff": [(e.get("effectType"), e.get("name"),
                                               e.get("remaining"), e.get("active"))
                                              for e in effs]})
                for e in effs:
                    if e.get("effectType") is not None:
                        by_tile.setdefault(int(e["effectType"]), []).append(
                            (t.get("col"), t.get("row")))
            me = None
            for u in (dv.get("units") or []):
                if out.get("uid") is not None and u.get("id") == out["uid"]:
                    me = u
                    break
            if me is None:
                cand = [u for u in (dv.get("units") or []) if u.get("pos") is None]
                if len(cand) == 1:
                    me = cand[0]
                else:
                    for u in (dv.get("units") or []):
                        if (u.get("visualId") or u.get("unitId")) == graft:
                            me = u
                            break
            print("   [%s] entites Effect (effectAbilityStates) = %d" % (tag, len(idx)))
            print("        porteur=%s" % ({k: (me or {}).get(k)
                                           for k in ("id", "visualId", "pos", "alive")},))
            print("        effets du porteur=%s"
                  % ([(e.get("effectId"), e.get("effectType"), e.get("name"))
                      for e in ((me or {}).get("effects") or [])],))
            print("        tuiles a effet (tileMeta): %s" % (tile_rows or "AUCUNE"))
            return {"idx": idx, "by_unit": by_unit, "by_tile": by_tile,
                    "tile_rows": tile_rows, "me": me, "n_tiles": len(tiles or [])}

        b1 = snapshot("avant")
        out["uid"] = (b1.get("me") or {}).get("id")
        uid = out["uid"]
        print("   -> applyAction finish sur le porteur %s (emet On(0x28 UnitFinishedTurn))" % uid)
        fin = rpc(sid, "applyAction",
                  {"runnerId": rid, "action": {"kind": "finish", "unitId": uid}}, 120)
        print("      applyAction -> %s" % ({k: fin.get(k) for k in ("mutated", "error")
                                            if k in fin},))
        b2 = snapshot("apres")

        # ---- E1 : NOMMER l'entite creee (diff du canal sans filtre) --------------
        new_ids = sorted(set(b2["idx"]) - set(b1["idx"]))
        gone_ids = sorted(set(b1["idx"]) - set(b2["idx"]))
        print("\n   == E1 -- entites Effect NEUVES (canal effectAbilityStates) ==")
        for i in new_ids:
            r = b2["idx"][i]
            print("      +id=%s type=%s name=%s source=%s active=%s"
                  % (i, r.get("effectType"), r.get("name"), r.get("source"), r.get("active")))
        for i in gone_ids:
            r = b1["idx"][i]
            print("      -id=%s type=%s name=%s" % (i, r.get("effectType"), r.get("name")))
        if not new_ids:
            print("      AUCUNE entite neuve")
        out["new"] = [{"id": i, **{k: b2["idx"][i].get(k)
                                   for k in ("effectType", "name", "source", "active")}}
                      for i in new_ids]
        out["gone"] = [{"id": i, "effectType": b1["idx"][i].get("effectType"),
                        "name": b1["idx"][i].get("name")} for i in gone_ids]

        marked = [i for i in new_ids
                  if int(b2["idx"][i].get("effectType") or -1) == ALREADY_USED_TILE]
        # Le 1179 peut aussi avoir ete pose avant le finish (regime a exclure explicitement).
        all_1179 = [i for i, r in b2["idx"].items()
                    if int(r.get("effectType") or -1) == ALREADY_USED_TILE]
        out["e1_1179_entities"] = all_1179
        print("   E1 verdict : entites d'effectType 1179 dans l'etat APRES = %s"
              % (all_1179 or "AUCUNE"))

        # ---- E2 / E3 : ou l'entite 1179 est-elle PUBLIEE ? -----------------------
        print("\n   == E2/E3 -- appartenance publiee de chaque entite 1179 ==")
        for i in all_1179:
            on_tile = ALREADY_USED_TILE in b2["by_tile"]
            on_unit = b2["by_unit"].get(i)
            print("      effet %s : tileMeta=%s | decisionView(porteur)=%s"
                  % (i, b2["by_tile"].get(ALREADY_USED_TILE) if on_tile else "ABSENT",
                     on_unit or "ABSENT"))
        out["e2_tile"] = b2["by_tile"].get(ALREADY_USED_TILE)
        out["e3_unit"] = {i: b2["by_unit"].get(i) for i in all_1179}

        # ---- E4 : le MONTAGE a-t-il seulement produit le regime ? ----------------
        landed = ((b2.get("me") or {}).get("pos")) or {}
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        bg_tiles = {int(t["id"]): (t.get("col"), t.get("row"))
                    for t in (bg.get("tiles") or []) if t.get("id") is not None}
        tile_entity = None
        for tid, cr in bg_tiles.items():
            if cr == (landed.get("col"), landed.get("row")):
                tile_entity = tid
                break
        print("\n   == E4 -- montage ==")
        print("      pos porteur : %s -> %s"
              % ((b1.get("me") or {}).get("pos"), (b2.get("me") or {}).get("pos")))
        print("      entite-tuile d'atterrissage (%s,%s) = %s"
              % (landed.get("col"), landed.get("row"), tile_entity))
        print("      tuiles a effet identiques avant/apres ? %s"
              % (b1["tile_rows"] == b2["tile_rows"]))
        print("      tuiles : boardGraph=%d | tileMeta=%d"
              % (len(bg_tiles), b2["n_tiles"]))
        out["e4"] = {"pos_before": (b1.get("me") or {}).get("pos"),
                     "pos_after": (b2.get("me") or {}).get("pos"),
                     "tile_entity": tile_entity,
                     "tiles_same": b1["tile_rows"] == b2["tile_rows"],
                     "n_boardgraph_tiles": len(bg_tiles), "n_tilemeta_tiles": b2["n_tiles"]}

        # ---- E5 : QUI est l'owner ? -------------------------------------------
        # `DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)` passe
        # `source = NULL` au ctor d'`AddEffectBehaviour` ; `$$Execute` retombe alors
        # litteralement sur la CIBLE (`pvVar16 = unit; if (sourceSelectionne != 0)
        # pvVar16 = <source>`), donc `SourceUnitId == OwnerId` pour cet effet.
        # `dumpEntityComponents` rend le TYPE d'entite + la liste des composants :
        # c'est ce qui separe « l'owner n'est pas une tuile » de « le capteur filtre ».
        print("\n   == E5 -- identite de l'owner de chaque entite 1179 ==")
        owners = {}
        for i in all_1179:
            oid = b2["idx"][i].get("source")
            if oid is None:
                continue
            dmp = rpc(sid, "dumpEntityComponents",
                      {"runnerId": rid, "entityId": int(oid), "withFields": False}, 90)
            comps = [c.get("cls") for c in (dmp.get("components") or [])]
            owners[i] = {"ownerId": int(oid), "entityType": dmp.get("type"),
                         "components": comps,
                         "boardGraphPos": bg_tiles.get(int(oid)),
                         "inTileMeta": None}
            print("      effet %s -> owner %s : EntityType=%s boardGraph=%s"
                  % (i, oid, dmp.get("type"), bg_tiles.get(int(oid))))
            print("         composants : %s" % comps)
        out["e5_owners"] = owners

        # ---- E6 : le GATE `includeInactive`, mesure du residu nomme ------------
        # `IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
        # itere `EffectsOwnedComponent.ActiveEffectIds` de la MainTile et fait
        # `Enum.ToString(EffectComponent+0x58)` -> `HasUtilityValue` -> `GetUtilityValue` SANS
        # AUCUN gate sur `IsActive` ni `Removed`. Or `engine/ai/context.py::build` demande
        # `tileMeta` SANS `includeInactive`, donc `readEffectsByTile` filtre `!active`. Un effet de
        # tuile POSE-mais-INACTIF serait compte par le natif et pas par le port. Ce bloc CHIFFRE le
        # gisement au lieu de le supposer : la difference entre les deux appels EST le residu.
        tm_def = rpc(sid, "tileMeta", {"runnerId": rid}, 90)
        tm_inc = rpc(sid, "tileMeta", {"runnerId": rid, "includeInactive": True}, 90)

        def _names(tm):
            out2 = {}
            for t in (tm.get("tiles") or []):
                names = sorted(e.get("name") for e in (t.get("effects") or []) if e.get("name"))
                if names:
                    out2[(t.get("col"), t.get("row"))] = names
            return out2

        d_def, d_inc = _names(tm_def), _names(tm_inc)
        only_inc = {k: v for k, v in d_inc.items()
                    if k not in d_def or d_def[k] != v}
        print("\n   == E6 -- effets de tuile visibles SEULEMENT sous includeInactive ==")
        print("      %s" % (only_inc or "AUCUN (le gate `!active` ne retire rien ici)"))
        out["e6_inactive_only"] = {str(k): v for k, v in only_inc.items()}

        # Croisement complementaire : TOUS les ids d'effet publies par un porteur
        # (tuile OU unite) vs le canal sans filtre -> les ORPHELINS de publication.
        published = set(b2["by_unit"])
        orphans = sorted(set(b2["idx"]) - published)
        print("\n   == croisement -- entites Effect NON publiees par decisionView ==")
        for i in orphans:
            r = b2["idx"][i]
            print("      id=%s type=%s name=%s source=%s active=%s"
                  % (i, r.get("effectType"), r.get("name"), r.get("source"), r.get("active")))
        out["orphans"] = [{"id": i, **{k: b2["idx"][i].get(k)
                                       for k in ("effectType", "name", "source", "active")}}
                          for i in orphans]
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
            print("   runner %s dispose" % rid)
        except Exception as exc:                                        # noqa: BLE001
            print("   dispose KO: %s" % exc)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--graft", default="orksNob")
    ap.add_argument("--foes", default="ultraTitus")
    ap.add_argument("--allies", default="",
                    help="allies EN PLUS du porteur (bras « tour d'equipe encore ouvert »)")
    ap.add_argument("--tag", default="", help="suffixe des fichiers de travail (isolation)")
    ap.add_argument("--json", default=None, help="chemin ou ecrire le rapport JSON")
    a = ap.parse_args()
    if not a.live:
        print("probe #425 : rien a faire hors --live (la mesure est un diff de canal live)")
        return 0
    allies = [x for x in a.allies.split(",") if x]
    res = volet_live(a.board, a.seed, a.graft, a.foes.split(","), allies, a.tag)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
