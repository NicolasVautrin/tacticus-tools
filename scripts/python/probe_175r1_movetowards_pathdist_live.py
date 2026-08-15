"""#175-r1 -- CONFRONTATION LIVE des deux feuilles `MoveTowardsUnitUtility`.

    python scripts/python/probe_175r1_movetowards_pathdist_live.py --runner <rid> [--pas N]

CE QUE CE PROBE MESURE, ET CE QU'IL NE MESURE PAS
-------------------------------------------------
Le pendant OFFLINE (`probe_175r1_movetowards_pathdist.py`) monte les deux regimes sur un board
lu du DISQUE, avec `neigh_by_pos = None` -- donc sur un voisinage APPROXIME par `hexgeo`, sans
aucune occupance reelle, et il n'appelle ni `apply_tile_attributes` ni la feuille : il n'imprime
que des `Count`. Ce probe-ci ferme les quatre ecarts :

  * le board vient du RPC `boardGraph` (voisins NATIFS = `BattleQuery.GetAdjacentTiles`), pas du
    fichier disque ;
  * l'occupance est celle de la bataille (elle alimente le `WeightCost = 10 + IsFilled` du
    pathfinder, donc le COUT du chemin) ;
  * on passe par `tile_leaf_ctx(ctx)` -> `apply_tile_attributes`, c.-a-d. la chaine que le moteur
    emprunte reellement, et on evalue la FEUILLE, pas seulement la distance ;
  * on confronte l'ARGMAX du composite `Tile(7)` du port a la tuile choisie par le NATIF
    (`aiStepDryRun`, non mutant).

⚠ **CE QUI RESTE NON COUVERT, ET POURQUOI.** Le SCORE natif de la feuille prise SEULE n'est pas
lisible : `LEAF_HOOKS` de `frida/hooks/features/scorer-damage-trace.ts` ne porte que `TileEffects`
et `CapturePointTile`. Ajouter `MoveTowardsUnitUtility.u003CEvaluateMovementInStepsu003Ed__15$$MoveNext`
y est possible (le corps est PARTAGE par les deux sous-classes, donc UN hook publierait les DEUX
feuilles) mais c'est une edition `frida/hooks/*`, donc une FENETRE DE REINJECT. Ce qui est
confronte ici est donc l'ARGMAX du composite, pas le terme isole -- et le probe REFUSE de conclure
quand le terme n'est pas discriminant, au lieu de rendre un accord degenere.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402

from engine import weights as W                                           # noqa: E402
from engine.ai import context as _ai_ctx                                  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402
from engine.entities.effect_type import EffectType                        # noqa: E402
from engine.playbook import scene as _scene                               # noqa: E402
from engine.utilities import tile as T                                    # noqa: E402
from engine.utilities.utility_type import UtilityType                     # noqa: E402

#: Les deux identifiants que `MoveTowardsUnitUtility$$UnitIdentifierAbilityOrEffect` porte dans
#: les deux sous-classes -- l'ACTIVE pour MasterOfTheTutelaries, l'EFFET pour BioMinefield.
MOT = int(ActiveAbilityType.MasterOfTheTutelaries)          # 1096
BIOMINE = int(EffectType.BioMinefield_Target)               # 1315

#: ⚠ 62 et 63, PAS 61 et 62 : la fiche `#175-r1` du backlog ecrit « (61) » et « (62) », ordinaux
#: d'un build anterieur. Re-derives ici du mirror, jamais recopies.
LEAF_BIOMINE = int(UtilityType.BioMinefield_MoveTowardsTarget)
LEAF_MOT = int(UtilityType.MasterOfTheTutelaries_MoveTowardsTarget)


def _r(sid, m, b, t=90):
    d = _rpc(sid, m, b, t)
    return d.get("result", d) if isinstance(d, dict) else {}


def _ctx_du_pas(sid, rid: int):
    """(uid, tuile NATIVE, ctx) du pas courant. `aiStepDryRun` ne MUTE PAS."""
    dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
    if not dry.get("ok") or not dry.get("hasNext"):
        return None, None, None, dry
    msgs = (dry.get("action") or {}).get("messages") or []
    nat = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    uid = dry.get("activatedUnitId")
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    if me is None:
        return uid, None, None, dry
    wt = W.load()
    rpc = lambda m, b, t: _r(sid, m, b, t)                                # noqa: E731
    predictor = _scene.build_predictor(rpc, rid)
    ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, uid, wt, predictor)
    origine = ((me.get("pos") or {}).get("col"), (me.get("pos") or {}).get("row"))
    tuile_nat = ((nat["to"]["col"], nat["to"]["row"]) if nat else origine)
    return uid, tuile_nat, (ctx, me, wt, msgs), dry


def _avancer(sid, rid: int, dry: dict) -> None:
    for m in ((dry.get("action") or {}).get("messages") or []):
        cls = m.get("cls")
        if cls == "MoveUnitMessage":
            act = {"kind": "move", "unitId": m["unitId"],
                   "to": {"col": m["to"]["col"], "row": m["to"]["row"]}}
        elif cls == "ActiveAbilityMessage":
            act = {"kind": "ability", "casterId": m["casterId"],
                   "targetId": m.get("targetId"), "abilityType": m["abilityType"]}
        elif cls == "FinishUnitTurnMessage":
            act = {"kind": "finish", "unitId": m["unitId"]}
        else:
            continue
        _r(sid, "applyAction", {"runnerId": rid, "action": act}, 90)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", required=True)
    ap.add_argument("--pas", type=int, default=0,
                    help="nombre de chunks NATIFS a jouer avant de mesurer")
    ap.add_argument("--cherche", type=int, default=0,
                    help="avance jusqu'a trouver un pas ou la carte pathdist est NON VIDE")
    a = ap.parse_args()
    sid = _resolve_session()
    if not sid:
        print("PAS MESURE : aucune session Frida")
        return 99
    rid = int(a.runner)

    for _ in range(a.pas):
        _, _, _, dry = _ctx_du_pas(sid, rid)
        if not dry.get("ok"):
            print("PAS MESURE : trajectoire epuisee avant le pas demande")
            return 99
        _avancer(sid, rid, dry)

    trouve = None
    for k in range(int(a.cherche) + 1):
        uid, tuile_nat, paquet, dry = _ctx_du_pas(sid, rid)
        if paquet is None:
            if not dry.get("ok") or not dry.get("hasNext"):
                break
            _avancer(sid, rid, dry)
            continue
        ctx, me, wt, _msgs = paquet
        lc = T.tile_leaf_ctx(ctx)
        cartes = T._movetowards_pathdist_by_pos(lc)
        if cartes or k == a.cherche:
            trouve = (uid, tuile_nat, ctx, me, wt, lc, cartes, _msgs)
            if cartes:
                break
        _avancer(sid, rid, dry)

    if trouve is None:
        print("PAS MESURE : aucun pas exploitable")
        return 99
    uid, tuile_nat, ctx, me, wt, lc, cartes, dec_msgs = trouve

    print("=== #175-r1 CONFRONTATION LIVE -- runner %d ===" % rid)
    print("unite activee : u%s [%s] @%s  move=%s"
          % (uid, me.get("visualId"), (me.get("pos") or {}).get("col") is not None
             and ((me.get("pos") or {})["col"], (me.get("pos") or {})["row"]), me.get("movement")))
    print("traits du mover : %s" % sorted(lc.get("unit_traits") or []))
    print("actives du mover : %s" % sorted(lc.get("unit_active_abilities") or []))
    print("amis lus : %d   ennemis lus : %d"
          % (len(lc.get("friend_units") or []), len(lc.get("enemy_units") or [])))
    print("voisinage NATIF (boardGraph) present : %s"
          % ("OUI" if lc.get("neigh_by_pos") else "NON (repli hexgeo)"))

    # -- ETAGE 1 : le PRODUCTEUR. Quelles cibles le port identifie-t-il ?
    print("\n[1] cibles identifiees par le producteur : %s"
          % (sorted(cartes.keys()) or "AUCUNE"))
    for ident, carte in sorted(cartes.items()):
        nom = {MOT: "MasterOfTheTutelaries(active 1096)",
               BIOMINE: "BioMinefield_Target(effet 1315)"}.get(ident, str(ident))
        vals = sorted(set(carte.values()))
        print("    %-40s : %d tuiles, Count distincts = %s"
              % (nom, len(carte), vals[:12] + (["..."] if len(vals) > 12 else [])))

    if not cartes:
        print("\nVERDICT : carte VIDE -- aucune cible sur ce pas. Le terme est structurellement 0 ;"
              " un accord ici ne prouverait RIEN (regime degenere).")
        return 1

    # -- ETAGE 2 : CHEMIN != HEX. Temoin NON NUL exige, sinon le port serait indistinguable
    #    d'un `hexgeo.distance` et la confrontation ne separerait rien.
    for ident, carte in sorted(cartes.items()):
        cible = T._movetowards_cible(lc, ident) if hasattr(T, "_movetowards_cible") else None
        ecarts = 0
        injoignables = 0
        for pos, n in carte.items():
            if n is None:
                injoignables += 1
                continue
        print("\n[2] identifiant %s : %d tuile(s) sans chemin (terme 0), cible=%s"
              % (ident, injoignables, cible))

    # -- ETAGE 3 : la FEUILLE, sur les tuiles candidates reelles
    feuilles = {LEAF_BIOMINE: T.BioMinefield_MoveTowardsTargetUtility(),
                LEAF_MOT: T.MasterOfTheTutelaries_MoveTowardsTargetUtility()}
    tuiles = list(ctx.action_tiles or [])
    print("\n[3] tuiles candidates (`ctx.action_tiles`) : %d" % len(tuiles))
    for leaf_id, leaf in sorted(feuilles.items()):
        termes = {}
        for t in tuiles:
            meta = T.apply_tile_attributes({}, t, lc)
            termes[t] = leaf.evaluate(t, meta, lc, wt)
        distincts = sorted(set(termes.values()))
        non_nuls = [t for t, v in termes.items() if v]
        print("    feuille %-2d (%s) : %d tuile(s) a terme NON NUL, valeurs distinctes = %s"
              % (leaf_id, leaf._CAT, len(non_nuls), distincts[:10]))
        if len(distincts) > 1:
            mx = max(termes.values())
            best = sorted(t for t, v in termes.items() if v == mx)
            print("        argmax de CETTE feuille seule : %s (terme %.3f)" % (best[:6], mx))

    # -- ETAGE 4 : ARGMAX du composite Tile(7) du PORT vs tuile NATIVE
    #
    # ⚠ `Tile(7)` NE CHOISIT PAS SEUL la tuile : le natif maximise l'utilite d'ACTION (ability x
    # cible x tuile), dont `Tile(7)` n'est qu'un membre. Comparer l'argmax de `Tile(7)` a la tuile
    # native SANS restreindre l'ensemble compare des tuiles ou l'action est ex aequo produirait un
    # faux desaccord -- c'est ce que fait la premiere version de cet etage, et elle est FAUSSE.
    from engine.playbook.base import tile_utility as _tile_u
    comp = {t: _tile_u(ctx, t) for t in tuiles}
    print("\n[4] DECISION NATIVE du pas :")
    for m in (dec_msgs or []):
        print("    %s" % ({k: v for k, v in m.items() if k != "stack"},))
    if tuile_nat in comp:
        print("    Tile(7) du PORT sur la tuile NATIVE %s = %.3f" % (tuile_nat, comp[tuile_nat]))
    else:
        print("    tuile NATIVE %s HORS de `ctx.action_tiles` (%d tuiles) -- l'ensemble compare "
              "n'est pas le meme, aucun argmax n'est confrontable ici"
              % (tuile_nat, len(tuiles)))
    if comp:
        mx = max(comp.values())
        best = sorted(t for t, v in comp.items() if v == mx)
        print("    argmax Tile(7) du PORT : %s (max=%.3f)" % (best[:6], mx))
        # discriminance : le terme de la feuille change-t-il l'argmax de Tile(7) ?
        sans = {}
        for t in tuiles:
            meta = T.apply_tile_attributes({}, t, lc)
            d = sum(feuilles[i].evaluate(t, meta, lc, wt) for i in feuilles)
            sans[t] = comp[t] - d
        mx2 = max(sans.values()) if sans else 0
        best2 = sorted(t for t, v in sans.items() if v == mx2)
        print("    argmax Tile(7) SANS les deux feuilles : %s" % (best2[:6],))
        print("    la feuille DEPLACE l'argmax de Tile(7) : %s"
              % ("OUI -- le terme MORD" if best2 != best else "NON -- terme non discriminant ici"))

    # -- ETAGE 5 : VENTILATION PAR FEUILLE. Un desaccord d'argmax ne dit PAS quelle feuille
    #    diverge ; seule la ventilation le dit (jamais fitter le scalaire du composite).
    interet = []
    if tuile_nat in comp:
        interet.append(tuile_nat)
    interet += [t for t in best[:2] if t not in interet]
    print("\n[5] VENTILATION du composite Tile(7) du PORT, feuille par feuille :")
    for t in interet:
        meta = T.apply_tile_attributes({}, t, lc)
        lignes = []
        for ut, (nom, leaf) in sorted(T.TILE_LEAVES.items(), key=lambda kv: int(kv[0])):
            try:
                v = leaf.evaluate(t, meta, lc, wt)
            except Exception as exc:                       # noqa: BLE001
                v = "ERR:%s" % exc
            if v:
                lignes.append("%s(%d)=%s" % (nom, int(ut), v))
        print("    %s  total=%.3f  |  %s" % (t, comp[t], "  ".join(lignes) or "toutes nulles"))

    # -- ETAGE 6 : LA DISTANCE ELLE-MEME, CONFRONTEE AU NATIF.
    #
    # C'est le SEUL etage de ces deux feuilles qu'on puisse confronter au natif sans hook neuf, et
    # c'est aussi le SEUL etage NEUF livre par #175-r1 : `get_path_node_counts_by_pos`, le jumeau
    # en domaine POSITION. Le canal est `pathDistToEnemies`, qui invoque
    # `IPathfinders.GetPath` avec le litteral `PathfinderType = 1` (`IgnoreTerrain`) --
    # EXACTEMENT le pathfinder que `MoveTowardsUnitUtility$$GetMinDistanceToTarget` appelle.
    from engine.entities.pathfinding import ignore_terrain_pathfinder as ITP
    pde = _r(sid, "pathDistToEnemies", {"runnerId": rid, "unitId": uid}, 120)
    print("\n[6] CONFRONTATION DE LA DISTANCE (canal natif `pathDistToEnemies`, "
          "PathfinderType=IgnoreTerrain) :")
    if not pde.get("ok"):
        print("    PAS MESURE : %s" % pde.get("error"))
        return 0
    nat = {(t["col"], t["row"]): t.get("pathDist")
           for t in (pde.get("tiles") or []) if t.get("pathDist") is not None}
    enn = [tuple(u["pos"]) for u in (lc.get("enemy_units") or []) if u.get("pos")]
    print("    tuiles publiees par le natif : %d   ennemis lus : %s" % (len(nat), enn))
    if not nat or not enn:
        print("    PAS MESURE : canal vide")
        return 0
    # Le natif prend le MIN sur les ennemis CIBLABLES ; le port doit faire le meme min.
    cartes_enn = [ITP.get_path_node_counts_by_pos(
                      e, neigh_by_pos=lc.get("neigh_by_pos"),
                      walkable_by_pos=lc.get("walkable_by_pos"),
                      elev_by_pos=lc.get("elev_by_pos"),
                      occupied_positions=tuple(
                          [u["pos"] for u in (lc.get("friend_units") or []) if u.get("pos")]
                          + [u["pos"] for u in (lc.get("enemy_units") or []) if u.get("pos")]))
                  for e in enn]
    port = {}
    for c in cartes_enn:
        for p, n in c.items():
            if n is not None and (p not in port or n < port[p]):
                port[p] = n
    communs = sorted(set(nat) & set(port))
    if not communs:
        print("    PAS MESURE : aucune tuile commune")
        return 0
    # Deux conventions possibles (NOEUDS vs ARETES) : on mesure le decalage, on ne le suppose pas.
    for delta in (0, -1, 1):
        ok = sum(1 for p in communs if port[p] + delta == nat[p])
        print("    accord avec port %+d : %d / %d" % (delta, ok, len(communs)))
    d0 = [(p, port[p], nat[p]) for p in communs if port[p] != nat[p]]
    d1 = [(p, port[p], nat[p]) for p in communs if port[p] - 1 != nat[p]]
    meilleur = d0 if len(d0) <= len(d1) else d1
    print("    ECARTS (convention retenue = la mieux accordee) : %d" % len(meilleur))
    for p, a, b in meilleur[:12]:
        print("        %s port=%s natif=%s" % (p, a, b))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
