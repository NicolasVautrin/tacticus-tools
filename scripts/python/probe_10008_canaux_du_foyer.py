"""probe #10008 -- le VOLET LIVE des canaux du foyer `frida/hooks/features/ai-step/rpc-snapshot.ts`.

Trois volets, chacun lisible tout seul, chacun avec son CRITERE pose AVANT la methode.

  V1 (#545-r1 + #287-r5-r2) -- LE REGIME DISCRIMINANT, celui que les deux fiches declarent NON
      ATTEINT (<< la marche d'approche a cale sur la geometrie et les deux cotes rendaient 0/0,
      un accord DEGENERE >>). Les deux compteurs PER-TOUR d'`ActorStatisticsComponent` --
      `TotalAttacksMadeThisTurn` (`+0x24`, EMISES) et `NumAttacksReceivedThisTurn` (`+0x38`,
      RECUES) -- sont EN VOL depuis la fenetre du 2026-08-15. Ce qui manquait n'etait pas le
      capteur mais un etat ou ils soient NON NULS.

      Le montage tient en une ligne, et c'est le point : `--place` / `--a-place` posent
      l'attaquant et sa cible sur DEUX TUILES ADJACENTES, donc l'attaque part SANS deplacement --
      la geometrie de spawn est CONTOURNEE, pas subie. Deux unites de mon cote (une seule ferait
      finir le tour automatiquement, et `StartTurnOperation$$ResetUnit` remettrait les compteurs
      a zero avant qu'on les lise -- mesure, pas hypothese : c'est ce qu'a rendu le premier
      montage a une unite).

      CRITERE :
        (a) NATIF -- apres le cast et AVANT la fin de tour : `made == 1` sur l'ATTAQUANT SEUL,
            `recv == 1` sur la CIBLE SEULE, `0` partout ailleurs. Un montage ou les deux valeurs
            seraient egales, ou porteesa par la meme entite, ne discriminerait pas un echange de
            champs ; celui-ci le fait.
        (b) PORT -- un `State` RECHARGE de cette capture doit rendre les MEMES valeurs sur
            `attacks_made_this_turn` et `times_attacked_this_turn`.
        (c) CONTREFACTUEL -- le meme `load_state` SANS le canal (`actor_stats=None`) doit
            RE-DIVERGER vers `0/0`. Sans ce bras, un vert ne prouverait rien : il pourrait venir
            d'un compteur que le moteur repose lui-meme.

  V2 (#1039-r1) -- LE QUATRIEME BRAS de la confrontation du canal `rarity`, le seul que
      `#999-r3` laisse ouvert : `unitsNotAlive[].rarity` sur une unite ayant FUI. Les trois
      premiers (layout, regime non degenere, MoW) sont VERTS depuis la session 89. Une unite
      qui a FUI garde ses PV PLEINS mais sort d'`IsAlive` : elle n'existe que dans ce bloc-la.
      Le montage de fuite n'est pas refait -- il est IMPORTE de
      `probe_429r1r3r1_message_gate_perimeter.py`, qui l'a etabli.

  V3 (#487-r2 + #419) -- LES DEUX CANAUX NEUFS, qui attendent une FENETRE DE REINJECT. Ce volet
      rend `PAS EN VOL` tant que le bundle courant ne les publie pas, et devient la mesure de
      recette une fois la fenetre passee. Il DISTINGUE explicitement << pas en vol >> (le champ
      est absent : rien a conclure) de << en vol et FAUX >> (le champ est la et le contrat n'est
      pas tenu) -- confondre les deux ferait lire une non-mesure comme un vert.

Lancement (depuis `scripts/python`) :
    python probe_10008_canaux_du_foyer.py --state-file <ABS> [--volet v1|v2|v3]

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rl_collect_batch import _rpc, _resolve_session                       # noqa: E402
from engine.entities.pathfinding.board import Board                       # noqa: E402
from engine.runner.components import UnitComponent                        # noqa: E402
from engine.runner.snapshot import load_state                             # noqa: E402

BOARD = "MC1_67"
SEED = "777"

#: DEUX unites de MON cote -- une seule ferait finir le tour tout seul apres le cast, et le
#: turn-start du joueur entrant remettrait les compteurs a zero AVANT la lecture. Mesure.
P_UNITS = "custoVexilusPraetor,templChampion"
A_UNITS = "orksKillaKan"
#: Adjacentes en `evenq` : (0,0) et (1,0) sont voisines, donc l'attaque part SANS deplacement.
PLACES = ("--place", "custoVexilusPraetor:0,0", "--place", "templChampion:0,1",
          "--a-place", "orksKillaKan:1,0")
#: L'active du Custodes, offensive et PRETE au tour 1 (`ActiveAbilityType.VexillaMagnifica`).
ABILITY = "1183"


def _run(argv, timeout=600):
    return subprocess.run(argv, cwd=str(HERE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _build(state_file: str, extra=()) -> dict:
    """Monte le runner. EXIGE un runner NEUF : `rl_duel build` peut refuser SANS lever, et on
    relirait paisiblement l'ANCIEN runner du meme `--state-file` (piege #322 SS5)."""
    avant = None
    p = Path(state_file)
    if p.exists():
        try:
            avant = int(json.loads(p.read_text(encoding="utf-8"))["runnerId"])
        except Exception:                                          # noqa: BLE001
            avant = None
    p.unlink(missing_ok=True)
    out = _run([sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
                "--state-file", state_file, "--p-units", P_UNITS, "--a-units", A_UNITS,
                *PLACES, *extra])
    if not p.exists():
        raise RuntimeError("BUILD refuse rc=%d\n%s\n%s"
                           % (out.returncode, out.stdout[-800:], out.stderr[-800:]))
    st = json.loads(p.read_text(encoding="utf-8"))
    if avant is not None and int(st["runnerId"]) == avant:
        raise RuntimeError("BUILD refuse (runner inchange : %d) -- on mesurerait le PRECEDENT"
                           % avant)
    return st


def _dispose(state_file: str, rid: int) -> None:
    _run([sys.executable, "rl_duel.py", "dispose", "--runner", str(rid),
          "--state-file", state_file], timeout=180)


def _stats_par_id(payload) -> dict:
    return {u.get("entityId"): u for u in ((payload or {}).get("units") or [])}


# =================================================================================================
# V1 -- LE REGIME DISCRIMINANT DES DEUX COMPTEURS PER-TOUR
# =================================================================================================

def volet_v1(state_file: str) -> dict:
    res = {"volet": "v1", "items": ["#545-r1", "#287-r5-r2"]}
    sid = _resolve_session()
    st = _build(state_file)
    rid = int(st["runnerId"])
    res["runnerId"] = rid
    try:
        dv = _rpc(sid, "decisionView", [{"runnerId": rid}], 60).get("result") or {}
        vis = {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}
        att = vis.get("custoVexilusPraetor")
        cible = vis.get("orksKillaKan")
        if att is None or cible is None:
            raise RuntimeError("montage NON INSTALLE : attaquant=%s cible=%s (vis=%s)"
                               % (att, cible, sorted(vis)))
        res["attaquant"], res["cible"] = att, cible

        avant = _stats_par_id(_rpc(sid, "actorStats", [{"runnerId": rid}], 60).get("result"))
        res["avant"] = {u: (avant[u].get("attacksMadeThisTurn"),
                            avant[u].get("attacksReceivedThisTurn")) for u in sorted(avant)}

        out = _run([sys.executable, "rl_duel.py", "act", "ability", "--caster", str(att),
                    "--target", str(cible), "--ability", ABILITY, "--runner", str(rid),
                    "--state-file", state_file])
        res["cast_rc"] = out.returncode

        # --- (a) LE NATIF, apres le cast et AVANT la fin de tour --------------------------
        brut = _rpc(sid, "actorStats", [{"runnerId": rid}], 60).get("result") or {}
        apres = _stats_par_id(brut)
        res["apres"] = {u: (apres[u].get("attacksMadeThisTurn"),
                            apres[u].get("attacksReceivedThisTurn")) for u in sorted(apres)}
        made = {u: apres[u].get("attacksMadeThisTurn") for u in apres}
        recv = {u: apres[u].get("attacksReceivedThisTurn") for u in apres}
        res["natif_ok"] = (made.get(att) == 1 and recv.get(cible) == 1
                           and all(v == 0 for u, v in made.items() if u != att)
                           and all(v == 0 for u, v in recv.items() if u != cible))
        # ANTI-DEGENERESCENCE : les deux compteurs doivent etre portes par des entites
        # DIFFERENTES, sinon un echange de champs serait invisible.
        res["non_degenere"] = att != cible and made.get(att) == 1 and recv.get(att) == 0

        # --- (b) LE PORT, sur un etat RECHARGE --------------------------------------------
        ob = _rpc(sid, "observeBattle", [{"runnerId": rid}], 60).get("result") or {}
        snap = _rpc(sid, "combatSnapshot", [{"runnerId": rid}], 90).get("result") or {}
        bg = _rpc(sid, "boardGraph", [{"runnerId": rid}], 60).get("result") or {}
        board = Board(bg["tiles"], adjacency="native_sym") if bg.get("tiles") else None
        seede = load_state(dv, ob, snap, board=board, actor_stats=brut)
        # --- (c) LE CONTREFACTUEL : le MEME chargement SANS le canal ----------------------
        nu = load_state(dv, ob, snap, board=board)

        def _lit(state, uid):
            e = state.get_entity(uid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is None:
                return None
            return (uc.attacks_made_this_turn, uc.times_attacked_this_turn)

        res["port_seede"] = {"attaquant": _lit(seede, att), "cible": _lit(seede, cible)}
        res["port_nu"] = {"attaquant": _lit(nu, att), "cible": _lit(nu, cible)}
        res["port_ok"] = (res["port_seede"]["attaquant"] == (1, 0)
                          and res["port_seede"]["cible"] == (0, 1))
        res["contrefactuel_ok"] = (res["port_nu"]["attaquant"] == (0, 0)
                                   and res["port_nu"]["cible"] == (0, 0))
        res["ok"] = bool(res["natif_ok"] and res["non_degenere"]
                         and res["port_ok"] and res["contrefactuel_ok"])
    finally:
        _dispose(state_file, rid)
    return res


# =================================================================================================
# V2 -- LA RARETE D'UNE UNITE AYANT FUI
# =================================================================================================

def volet_v2(state_file: str) -> dict:
    """Le 4e bras de #1039-r1. Le montage de FUITE n'est PAS refait : il est importe de
    `probe_429r1r3r1_message_gate_perimeter.py`, qui l'a etabli et le maintient."""
    res = {"volet": "v2", "items": ["#1039-r1"]}
    import probe_429r1r3r1_message_gate_perimeter as FLED                 # noqa: N812
    sid = _resolve_session()
    st = FLED.build_fled(state_file, SEED, BOARD)
    rid = int(st["runnerId"])
    res["runnerId"] = rid
    try:
        bg = _rpc(sid, "boardGraph", [{"runnerId": rid}], 60).get("result") or {}
        board = Board(bg["tiles"], adjacency="native_sym") if bg.get("tiles") else None
        pose = {}
        FLED.installer_regime_fled(sid, rid, board, 12, pose)
        res["installation"] = {k: v for k, v in pose.items()
                               if k in ("fled_uid", "ok", "why", "essais")}
        snap = _rpc(sid, "combatSnapshot", [{"runnerId": rid}], 90).get("result") or {}
        na = snap.get("unitsNotAlive")
        res["canal_units_not_alive"] = FLED.canal_units_not_alive(snap)
        if not isinstance(na, list):
            res["ok"] = False
            res["why"] = ("`unitsNotAlive` n'est pas une liste (%s) -- canal NON MESURE, "
                          "rien a conclure" % type(na).__name__)
            return res
        res["nb_non_vivantes"] = len(na)
        lignes = [{"entityId": u.get("entityId"), "rarity": u.get("rarity"),
                   "unitFlags": u.get("unitFlags")} for u in na]
        res["lignes"] = lignes
        # `UnitFlag.Fled` = 9 (`IdunBattle.Operations.FleeOperation$$Execute`, seul ecrivain).
        enfuies = [l for l in lignes if isinstance(l["unitFlags"], list) and 9 in l["unitFlags"]]
        res["enfuies"] = enfuies
        if not enfuies:
            # PORTEUR manquant, PAS un echec du canal : on le NOMME, et surtout on ne rend pas
            # un vert sur un ensemble vide.
            res["ok"] = False
            res["why"] = ("PORTEUR MANQUANT : aucune ligne `unitsNotAlive` ne porte `UnitFlag."
                          "Fled` (9). Le tirage `BattleFatigue` n'a pas mordu -- ce n'est PAS "
                          "un verdict sur le canal.")
            return res
        # `rarity` doit etre un ordinal MESURE. `rl_duel build` impose `targetRarity = 5` a toute
        # unite normalisee : la valeur attendue est donc 5, et c'est un regime DEGENERE qu'on
        # DECLARE au lieu de le taire.
        res["raretes"] = [l["rarity"] for l in enfuies]
        res["degenere_targetRarity"] = all(l["rarity"] == 5 for l in enfuies)
        res["ok"] = all(isinstance(l["rarity"], int) for l in enfuies)
        if res["ok"] and res["degenere_targetRarity"]:
            res["why"] = ("MESURE, mais en regime DEGENERE : `rl_duel build` impose "
                          "`targetRarity = 5`. Le bras prouve que le canal PUBLIE la rarete "
                          "d'une unite ayant FUI (ce qu'aucun autre canal ne fait), pas qu'il "
                          "discrimine -- la discrimination est le bras (2), deja VERT.")
    finally:
        _dispose(state_file, rid)
    return res


# =================================================================================================
# V3 -- LES DEUX CANAUX NEUFS (recette de la fenetre de reinject)
# =================================================================================================

def volet_v3(state_file: str) -> dict:
    """`PAS EN VOL` aujourd'hui ; mesure de RECETTE une fois la fenetre passee.

    ⚠ Il DISTINGUE << absent >> (rien a conclure) de << present et FAUX >> (contrat non tenu).
    Les confondre ferait lire une non-mesure comme un vert -- c'est exactement le vice que le
    tri-etat combat cote capteur."""
    res = {"volet": "v3", "items": ["#487-r2", "#419-r1-tr14-r5-r2-r1-r2-r1-r2"]}
    sid = _resolve_session()
    st = _build(state_file)
    rid = int(st["runnerId"])
    res["runnerId"] = rid
    try:
        stats = _rpc(sid, "actorStats", [{"runnerId": rid}], 60).get("result") or {}
        snap = _rpc(sid, "combatSnapshot", [{"runnerId": rid}], 90).get("result") or {}

        # --- #487-r2 : `receiveDamageTypeThisTurn` sur `actorStats` -----------------------
        u0 = ((stats.get("units") or [None])[0]) or {}
        en_vol_rdt = "receiveDamageTypeThisTurn" in u0
        res["rdt_en_vol"] = en_vol_rdt
        if not en_vol_rdt:
            res["rdt"] = "PAS EN VOL -- le bundle courant ne publie pas ce champ"
        else:
            lay = stats.get("receiveDamageLayout") or {}
            champs = [u.get("receiveDamageTypeThisTurn") for u in (stats.get("units") or [])]
            res["rdt_layout"] = lay
            res["rdt_enum"] = stats.get("receiveDamageEnum")
            res["rdt_echantillon"] = champs[:3]
            res["rdt_ok"] = bool(
                lay.get("channelResolved") is True
                and not lay.get("errors")
                and stats.get("receiveDamageEnum")
                == "IdunBattle.Entities.Enum.DamageProfileType"
                # Au deploiement, aucune unite n'a encore recu de degat -> `{}` PARTOUT, et
                # c'est la MESURE attendue. Ce qui serait FAUX, c'est `null`.
                and all(isinstance(c, dict) and isinstance(c.get("profiles"), dict)
                        for c in champs))

        # --- #419 : `weapons` sur `combatSnapshot` ----------------------------------------
        s0 = ((snap.get("units") or [None])[0]) or {}
        en_vol_wpn = "weapons" in s0
        res["weapons_en_vol"] = en_vol_wpn
        if not en_vol_wpn:
            res["weapons"] = "PAS EN VOL -- le bundle courant ne publie pas ce champ"
        else:
            lay = snap.get("weaponsLayout") or {}
            res["weapons_layout"] = lay
            res["weapons_enum"] = snap.get("weaponProfileEnum")
            lignes = [(u.get("entityId"), u.get("configId"), u.get("weapons"))
                      for u in (snap.get("units") or [])]
            res["weapons_echantillon"] = lignes[:3]
            portees = [w for (_, _, wp) in lignes
                       if isinstance(wp, dict) and isinstance(wp.get("weapons"), list)
                       for w in wp["weapons"]]
            res["nb_armes_lues"] = len(portees)
            res["weapons_ok"] = bool(
                lay.get("channelResolved") is True and not lay.get("errors")
                and snap.get("weaponProfileEnum")
                == "IdunBattle.Entities.Enum.DamageProfileType"
                and portees
                # `IsMelee` doit etre COHERENT avec la portee LUE -- c'est le seul controle qui
                # confronte le calcul du capteur a son propre brut.
                and all(w["isMelee"] == (not w["rangeHasValue"] or w["range"] < 2)
                        for w in portees))
            # CONFRONTATION DES DEUX SUBSTRATS (le coeur du residu #419) : l'ECS contre le
            # gameconfig, `IsMelee` par `IsMelee`.
            res["ecart_ecs_gameconfig"] = _confronter_gameconfig(lignes)

        res["ok"] = bool(res.get("rdt_ok") and res.get("weapons_ok"))
        if not en_vol_rdt or not en_vol_wpn:
            res["ok"] = None                     # NI vrai NI faux : la mesure n'a pas eu lieu
    finally:
        _dispose(state_file, rid)
    return res


def _confronter_gameconfig(lignes) -> list:
    """L'ECART que le residu #419 existe pour rendre MESURABLE : le natif itere le
    `WeaponsComponent`, le port lit `GC.unit(visualId).weapons`. Rend la liste des divergences
    (vide = les deux substrats concordent sur ce montage)."""
    import gameconfig as GC
    ecarts = []
    for eid, cid, wp in lignes:
        if not (isinstance(wp, dict) and isinstance(wp.get("weapons"), list) and cid):
            continue
        kit = ((GC.unit(cid) or {}).get("weapons")) or []
        ecs = sorted((w["damageProfileType"], w["hits"], w["isMelee"]) for w in wp["weapons"])
        cfg = sorted((_profil(w), int(w.get("hits") or 0),
                      (w.get("Range") is None or int(w["Range"]) < 2)) for w in kit)
        if ecs != cfg:
            ecarts.append({"entityId": eid, "configId": cid, "ecs": ecs, "gameconfig": cfg})
    return ecarts


def _profil(w) -> int:
    """`DamageProfile` du gameconfig -> ordinal `IdunBattle.Entities.Enum.DamageProfileType`."""
    from engine.entities.damage_profile_type import DamageProfileType
    nom = w.get("DamageProfile")
    try:
        return int(getattr(DamageProfileType, str(nom)))
    except Exception:                                                     # noqa: BLE001
        return -999                                     # jamais un ordinal valide -> l'ecart SORT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--volet", default="tous", choices=["tous", "v1", "v2", "v3"])
    a = ap.parse_args()
    if os.path.normpath(a.state_file).replace("\\", "/").find("/data/") >= 0:
        print("[10008] REFUS : un `--state-file` sous `data/` ecrirait une SORTIE dans les "
              "ENTREES versionnees (#349).")
        return 2
    volets = {"v1": volet_v1, "v2": volet_v2, "v3": volet_v3}
    choisis = list(volets) if a.volet == "tous" else [a.volet]
    tout = {}
    for nom in choisis:
        try:
            tout[nom] = volets[nom](a.state_file)
        except Exception as exc:                                          # noqa: BLE001
            # Un echec de MONTAGE n'est pas un verdict : il est RENDU, jamais avale.
            tout[nom] = {"volet": nom, "ok": None, "erreur": "%s: %s"
                         % (type(exc).__name__, exc)}
        print(json.dumps(tout[nom], ensure_ascii=True, indent=2, default=str))
    verdicts = {k: v.get("ok") for k, v in tout.items()}
    print("[10008] verdicts : %s" % json.dumps(verdicts, ensure_ascii=True))
    # `None` = PAS MESURE -> ni vert ni rouge. Seul un `False` explicite fait rougir.
    return 1 if any(v is False for v in verdicts.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
