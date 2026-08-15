"""#894-r2 -- confrontation LIVE de la PHASE 2 de `SolarAtomizer` : natif contre port.

MONTAGE, ET C'EST LUI LE FAIT NEUF. La fiche declarait ce residu bloque en `seeding` : le porteur
`admecBossBelisarius` spawnait avec UNE tuile et le natif refusait le cast
(`CasterHas3Tiles`). La cause n'etait ni l'unite ni le board -- c'est que le harnais ne demandait
jamais l'empreinte. `IdunBattle.Operations.SetupGameOperation$$AddBossUnit` est le SEUL chemin qui
pose une unite sur PLUSIEURS tuiles (il lit `BC.BossUnit` et la `BossPlatform` du board), et
`BC.BossUnit` vaut `null` dans le seed partage. Ecrit, le porteur arrive a `feet = 3` et le gate
rend `ValidRequest` -- mesure et contre-epreuve dans `probe_10016_bossunit_footprint.py`.

CE QUE CE PROBE MESURE :

  1. **phase 1 NATIVE** : le cast pose `1371 SolarAtomizer_PendingAttack` sur le caster et
     `1372 SolarAtomizer_PendingTarget` sur les tuiles de la ligne ;
  2. **phase 2 NATIVE** : au tour suivant, l'attaque differee part -- N coups `[AUTO:StartTurn]` ;
  3. **phase 2 PORTEE**, sur la capture prise APRES le cast et AVANT le changement de tour :
     `delayed_attack_triggers(state, player)` doit declencher le MEME rail
     (`PENDING_ATTACK_EFFECTS[1371]` -> `TRIGGERED_ABILITY_BEHAVIOURS[1297]`), avec le meme
     CARDINAL de coups et la meme cible ;
  4. **CONTRE-EPREUVE** : `1371` retire de `PENDING_ATTACK_EFFECTS` -> le port ne doit RIEN
     declencher. Sans elle, un port qui frapperait par un autre chemin passerait pour juste.

Usage :
    python probe_10017_solar_atomizer_phase2_live.py [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from rl_collect_batch import _resolve_session, _rpc, PLAYER_ID_HUMAN  # noqa: E402

PORTEUR = "admecBossBelisarius:4"      #: palier npc 4 -- le boss doit SURVIVRE au tour adverse
VISUAL_PORTEUR = "GuildBoss10Boss1AdmecBelisarius"
BOUCHE_TROU = "admecMarshall"          #: `initAndStart` exige des `playerUnits`
ENNEMIS = "admecDestroyer,admecRuststalker"
BOARD = "GB_Belisarius_01"
SOLAR_ATOMIZER = 1174                  #: `ActiveAbilityType.SolarAtomizer`
PENDING_ATTACK = 1371                  #: `EffectType.SolarAtomizer_PendingAttack`
PENDING_TARGET = 1372                  #: `EffectType.SolarAtomizer_PendingTarget`
CIBLE_TUILE = (1, 7)                   #: une tuile legale du cast, LUE au RPC `abilityTargets`


class MontageError(RuntimeError):
    pass


def _r(sid, method, body, t=120):
    return (_rpc(sid, method, [body], timeout=t) or {}).get("result") or {}


def stage(seed: int):
    """Ecrit le seed BC augmente de `BC.BossUnit` puis monte le runner. N'ecrit JAMAIS le seed
    partage -- la copie vit dans `logs/`, jamais dans `data/`."""
    tag = uuid.uuid4().hex[:8]
    dossier = REPO / "logs" / "runners"
    dossier.mkdir(parents=True, exist_ok=True)
    sf, bcf = dossier / ("sa10017-%s.json" % tag), dossier / ("sa10017-%s-bc.json" % tag)
    bc = json.loads((REPO / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    # Les CINQ champs d'`IdunBattle.Configuration.PredefinedBossUnit`, MESURES par le RPC
    # `classFields` (56 octets) : Id@0x10 PlayerId, UnitId@0x18 String, Health@0x20 Nullable<int>,
    # RemainingHealth@0x28 Nullable<int>, Modifiers@0x30 List<UnitModifier>.
    bc["BossUnit"] = {"Id": PLAYER_ID_HUMAN, "UnitId": PORTEUR,
                      "Health": None, "RemainingHealth": None, "Modifiers": []}
    bcf.write_text(json.dumps(bc), encoding="utf-8")
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
           "--state-file", str(sf), "--seed-bc", str(bcf),
           "--explicit-stats", PORTEUR,
           "--p-units", BOUCHE_TROU, "--a-units", ENNEMIS,
           # L'adversaire doit etre INOFFENSIF et INDESTRUCTIBLE : le boss doit atteindre le tour
           # suivant (sinon pas de phase 2) et ses cibles doivent survivre a la salve (sinon la
           # comparaison porte sur une mort, pas sur des coups).
           "--dmg-target", "1", "--hp-target", "500000"]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise MontageError("build KO (rc=%d) : %s" % (p.returncode, (p.stderr or "")[-700:]))
    return int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"]), sf


def _porteur_id(sid, rid) -> int:
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    for u in (dv.get("units") or []):
        if str(u.get("visualId") or "") == VISUAL_PORTEUR and len(u.get("feet") or []) == 3:
            return int(u["id"])
    raise MontageError("porteur a 3 tuiles introuvable -- `BC.BossUnit` n'a pas mordu")


def _coups(res) -> list[dict]:
    """Les coups publies par le flux d'events, avec leur cible et leur montant."""
    out = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if td.get("Amount") is not None and td.get("Target_Id") is not None:
                out.append({"target": td.get("Target_Id"), "amount": td.get("Amount"),
                            "ability": td.get("Active_Ability_Type")})
    return out


def mesure_native(sid, rid, boss: int, state_file):
    """Cast (phase 1), capture, puis passage de tour (phase 2)."""
    cast = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": boss, "abilityType": SOLAR_ATOMIZER,
        "to": {"col": CIBLE_TUILE[0], "row": CIBLE_TUILE[1]}}}, 150)
    a0 = (cast.get("actions") or [{}])[0]
    if not (cast.get("ok") and a0.get("ok")):
        raise MontageError("cast phase 1 REFUSE : %s" % str(cast)[:300])
    # CAPTURE APRES LE CAST : c'est l'etat que le port doit rejouer.
    dv1 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob1 = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    snap1 = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    rng1 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    # ⚠ `decisionView.effects` est AVEUGLE aux effets de TUILE (`case-92` SS357) : les marques
    # `1372` vivent sur des TUILES, donc c'est `tileMeta` qui les porte -- et c'est ce canal
    # qu'il faut passer a `load_state(tiles=...)`, sans quoi le port rejoue sur un plateau VIERGE
    # et sa phase 2 ne trouve AUCUNE cible.
    tiles1 = _r(sid, "tileMeta", {"runnerId": rid}, 90)
    effets_unites = {}
    for u in (dv1.get("units") or []):
        ids = [int(e["effectType"]) for e in (u.get("effects") or [])
               if e.get("effectType") is not None]
        if PENDING_ATTACK in ids or PENDING_TARGET in ids:
            effets_unites[int(u["id"])] = ids
    marquees = [(t.get("col"), t.get("row"))
                for t in (tiles1.get("tiles") or [])
                if any(int(e.get("effectType", -1)) == PENDING_TARGET
                       for e in (t.get("effects") or []) if isinstance(e, dict))]
    # PHASE 2 NATIVE : on rend la main, l'adversaire joue, et le tour du boss redemarre. On passe
    # par le CLI (`act endturn` + `aiturn`), la voie deja eprouvee du harnais.
    hp_avant = {int(u["squadId"] if "squadId" in u else u["id"]): u.get("hp")
                for u in (ob1.get("units") or []) if u.get("hp") is not None}
    for sous in (["act", "endturn"], ["aiturn"]):
        subprocess.run([sys.executable, "rl_duel.py"] + sous + ["--state-file", str(state_file)],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    ob2 = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    hp_apres = {int(u["squadId"] if "squadId" in u else u["id"]): u.get("hp")
                for u in (ob2.get("units") or []) if u.get("hp") is not None}
    deltas = {k: hp_avant[k] - hp_apres[k] for k in hp_avant
              if k in hp_apres and hp_avant[k] != hp_apres[k]}
    return {"dv1": dv1, "ob1": ob1, "snap1": snap1, "rng1": rng1, "tiles1": tiles1,
            "effets_apres_cast": effets_unites, "tuiles_marquees": marquees,
            "deltas_phase2": deltas}


def mesure_port(nat, boss: int, board, sans_rail: bool = False):
    """Rejoue la PHASE 2 sur la capture POST-CAST avec le moteur porte."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import HealthComponent, OwnerComponent
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers
    import engine.runner.operations.triggers.pending_attack as PA

    st = load_state(nat["dv1"], nat["ob1"], nat["snap1"], board=board,
                    tiles=nat.get("tiles1"))
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(nat["rng1"]["mt"]), nat["rng1"]["mti"]
    rng.call_count = 0
    st.rng = rng
    sauve = None
    if sans_rail:
        sauve = PA.PENDING_ATTACK_EFFECTS.pop(PENDING_ATTACK, None)
    try:
        e = st.get_entity(int(boss))
        oc = e.get_component(OwnerComponent) if e is not None else None
        joueur = None if oc is None else int(oc.player)
        pv_avant = {uid: (ent.get_component(HealthComponent).hp
                          if ent.get_component(HealthComponent) is not None else None)
                    for uid, ent in st.entities.items()}
        # DECOMPOSITION PAR ETAGE -- on ne compare pas un scalaire : chaque maillon du chemin
        # `tuiles marquees -> occupants -> ennemis` est mesure SEPAREMENT, pour que l'etage ou le
        # port decroche soit LU et non devine.
        from engine.entities.selectors.geometry import Cache, EntitiesWithAnyEffect
        from engine.entities.selectors.tiles import AllTiles
        from engine.entities.selectors.units import Enemies, Units
        from engine.runner.abilities.behaviours.context import entities_from_state
        ent_diag = entities_from_state(st, int(boss), int(boss))
        marquees = EntitiesWithAnyEffect(AllTiles(), [PENDING_TARGET]).evaluate(ent_diag)
        cache = Cache(EntitiesWithAnyEffect(AllTiles(), [PENDING_TARGET]))
        occupants = Units(cache, selection_type=3).evaluate(ent_diag)
        ennemis = Enemies(Units(cache, selection_type=3), selection_type=3).evaluate(ent_diag)
        etages = {
            "tuiles_1372_seedees": sum(
                1 for k, v in (st.effects.by_unit or {}).items()
                for e in v if int(getattr(e, "effect_type", -1)) == PENDING_TARGET),
            "EntitiesWithAnyEffect": len(marquees or []),
            "Units": len(occupants or []),
            "Enemies": len(ennemis or []),
        }
        res = delayed_attack_triggers(st, joueur) if joueur is not None else []
        pv_apres = {uid: (ent.get_component(HealthComponent).hp
                          if ent.get_component(HealthComponent) is not None else None)
                    for uid, ent in st.entities.items()}
        deltas = {uid: (pv_avant[uid] - pv_apres[uid]) for uid in pv_avant
                  if pv_avant[uid] is not None and pv_apres[uid] is not None
                  and pv_avant[uid] != pv_apres[uid]}
        phases = [r for r in res if isinstance(r, dict)]
        return {"joueur": joueur, "declenchements": len(phases), "deltas": deltas,
                "etages": etages, "detail": phases,
                "effets_port": sorted(int(x.effect_type)
                                      for x in (st.effects.by_unit.get(int(boss)) or ())
                                      if getattr(x, "effect_type", None) is not None)}
    finally:
        if sauve is not None:
            PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK] = sauve


def _coups_du_port(detail) -> list:
    """Les coups que la PHASE 2 portee publie, quelle que soit la profondeur ou le rail les range."""
    out = []
    pile = list(detail)
    while pile:
        r = pile.pop()
        if isinstance(r, dict):
            if isinstance(r.get("damage"), list):
                out.extend(r["damage"])
            pile.extend(v for v in r.values() if isinstance(v, (dict, list)))
        elif isinstance(r, list):
            pile.extend(r)
    return out


def run(seed: int = 777, verbose: bool = True) -> dict:
    from engine.entities.pathfinding.board import Board
    sid = _resolve_session()
    rid, sf = stage(seed)
    out = {"rid": rid, "seed": seed}
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        boss = _porteur_id(sid, rid)
        out["boss"] = boss
        nat = mesure_native(sid, rid, boss, sf)
        out["natif"] = {k: v for k, v in nat.items()
                        if k not in ("dv1", "ob1", "snap1", "rng1")}
        out["port"] = mesure_port(nat, boss, board)
        out["port_sans_rail"] = mesure_port(nat, boss, board, sans_rail=True)
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(sf)],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    if verbose:
        _imprimer(out)
    return out


def _imprimer(out: dict) -> None:
    n, p, sr = out.get("natif") or {}, out.get("port") or {}, out.get("port_sans_rail") or {}
    print("=== #894-r2 SolarAtomizer phase 2 -- natif contre port (runner %s, boss u%s) ==="
          % (out.get("rid"), out.get("boss")))
    print("")
    print("-- NATIF --")
    print("  effets APRES le cast (phase 1) : %r" % (n.get("effets_apres_cast"),))
    print("  tuiles MARQUEES (1372)         : %r" % (n.get("tuiles_marquees"),))
    print("  deltas de PV de la phase 2     : %r" % (n.get("deltas_phase2"),))
    print("")
    print("-- PORT (capture POST-CAST, meme MT) --")
    print("  joueur du boss                 : %s" % p.get("joueur"))
    print("  declenchements du rail         : %s" % p.get("declenchements"))
    print("  ETAGES du selecteur            : %r" % (p.get("etages"),))
    print("  deltas de PV                   : %r" % (p.get("deltas"),))
    print("  coups publies                  : %r" % (_coups_du_port(p.get("detail") or []),))
    print("  detail brut                    : %s" % str(p.get("detail"))[:700])
    print("")
    print("-- CONTRE-EPREUVE : 1371 hors de PENDING_ATTACK_EFFECTS --")
    print("  declenchements                 : %s (doit valoir 0)" % sr.get("declenchements"))
    print("  deltas de PV                   : %r (doit etre vide)" % (sr.get("deltas"),))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()
    run(a.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
