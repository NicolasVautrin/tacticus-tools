"""#1020 -- CONFRONTATION LIVE de `SaviorProtocols` : le degat se DEPLACE, PAR COUP.

## Le montage, et pourquoi il est NOMME et REUTILISABLE

`stage()` monte le triangle minimal de la mecanique et le rend en clair :

    ultraTitus  (MOI, melee)  --attaque-->  tauMarksman (ENNEMI, T'au, NE porte PAS 1120)
                                                 ^ ADJACENT
                                            tauNpc2DroneSniper:<palier> (ENNEMI, PORTE 1120)

C'est l'inverse du cas de jeu (les drones protegent d'ordinaire MON camp) et c'est DELIBERE : en
mettant le couple protege/protecteur du cote ADVERSE, l'attaque est jouee par MOI, donc
DETERMINISTE et pilotable a l'action pres -- au lieu de dependre du choix de cible de l'IA.
Le couple `(protecteur, protege)` resservira pour tout consommateur de `On(0x39 =
EventTriggerType.PreDamageTaken)`, d'ou `stage()` autonome.

Le porteur arrive par le **chemin de stats EXPLICITE** (`--explicit-stats <npc>:<palier>`, #419-r1-tr12-r2),
pas par une greffe : `tauNpc2DroneSniper` est le VRAI porteur npc, avec SES stats, SES traits et SES
armes. La gate de confrontabilite est donc franchie sans montage d'ability.

## L'ORACLE, et ce qu'il separe

Le natif tire `Maybe(chance = 50)` PAR COUP. Trois consequences mesurables :

  * **REGIME MIXTE** -- sur une attaque multi-coups, une partie des coups part au drone et l'autre
    reste sur la victime. **Un port PAR GROUPE ne peut PAS produire ce regime** : il transfere tout
    ou rien. C'est le discriminant direct de la granularite, et il ne demande aucune arithmetique.
  * **CONSERVATION** -- ce que la victime ne perd pas, le drone le prend. On mesure LES DEUX cotes :
    deux hypotheses qui rendraient le meme total (bonus vs deplacement) sont separees par le fait
    que `perdu_victime + perdu_drone` reste egal au degat de l'attaque, ET que `perdu_victime`
    DIMINUE quand le drone est present.
  * **CONSOMMATION RNG** -- `dumpRng` avant/apres. Un `Maybe` par coup consomme N `NextBool` la ou
    un `Maybe` par groupe en consomme 1.

## Contre-epreuve SANS LE RAIL

`--sans-rail` desinscrit `SaviorProtocols` du registre de dispatch cote PORT : le port doit alors
appliquer TOUT le degat a la victime et RIEN au drone. Si le verdict ne change pas, c'est que la
mesure ne regarde pas le rail.

ASCII only. Usage : `python probe_1020_savior_protocols_live.py [--seed 777] [--board MC1_67]`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

#: Les sorties du run vont dans le `logs/` de la RACINE, jamais sous `scripts/`, qui ne porte que
#: des sources. `ROOT` reste `scripts/python` -- il sert au `sys.path` et au `cwd` des sous-process.
REPO = ROOT.parents[1]

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402
from engine.entities.pathfinding.board import Board            # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister         # noqa: E402

#: Le protecteur : porteur NPC reel de `SaviorProtocols` (1120). Palier haut = assez de PV pour
#: encaisser plusieurs coups transferes sans mourir (un drone mort arreterait la serie).
DRONE = "tauNpc2DroneSniper:65"
#: La victime : T'au, ami du drone, et NE portant PAS 1120 (gate `!ActorHasTriggeredAbility`).
VICTIME = "tauMarksman"
#: L'attaquant, de MON cote : melee, donc adjacent, donc la geometrie est triviale a piloter.
ATTAQUANT = "ultraTitus"
#: `Loki_NormalAttack` -- l'ability normale generique (id lu au `abilities`, jamais devine).
NORMAL_ATTACK_FALLBACK = 69


class MontageError(RuntimeError):
    pass


def _sid() -> int:
    return _resolve_session()


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t) or {}).get("result") or {}


def stage(seed: int, board_id: str, drone: str = DRONE, victime: str = VICTIME,
          attaquant: str = ATTAQUANT, dmg_attaquant: int | None = None,
          drone_loin: bool = False):
    """Monte le triangle attaquant / victime / protecteur et rend `(runner_id, state_file)`.

    Positions FORCEES (`--place` / `--a-place`), jamais laissees aux SpawnPoints : la mecanique
    exige `IsAdjacent(Owner, Target)` cote drone ET la portee de melee cote attaquant. Les trois
    tuiles choisies sont mutuellement voisines en `evenq` sur `MC1_67`, et `rl_duel` REFUSE le build
    si l'une est injouable -- donc un montage silencieusement faux est impossible.

    `dmg_attaquant` (optionnel) borne le degat de l'attaquant (`--unit-stat`) pour que le drone
    SURVIVE a la serie : un drone mort sortirait du regime mixte par la mauvaise porte."""
    sf = REPO / "logs" / "runners" / ("sp1020-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
           "--state-file", str(sf),
           "--explicit-stats", drone,
           "--p-units", attaquant, "--place", "%s:2,3" % attaquant,
           "--a-units", "%s,%s" % (victime, drone),
           "--a-place", "%s:3,3" % victime,
           # TEMOIN : le MEME montage, drone HORS adjacence -- `IsAdjacent(Owner, Target)` ferme,
           # donc zero transfert et zero `Maybe` consomme. C'est la seule facon de savoir si un
           # ecart de degat total appartient au TRANSFERT ou a un etage EN AMONT (le decalage de
           # flux RNG du chokepoint). Le drone est DEPLACE, pas retire : le roster, les stats et
           # l'ordre d'apparition restent identiques entre les deux bras.
           "--a-place", "%s:%s" % (drone, "6,8" if drone_loin else "3,4")]
    if dmg_attaquant is not None:
        cmd += ["--unit-stat", "%s:Damage=%d" % (attaquant, int(dmg_attaquant))]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise MontageError("build KO (rc=%d) : %s" % (p.returncode, (p.stderr or "")[-500:]))
    st = json.loads(sf.read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    if rid is None:
        raise MontageError("build sans runnerId")
    return int(rid), sf


def _ids(sid, rid):
    """Resout les trois entites par leur `visualId` -- jamais par un ordre d'apparition."""
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        vis = (u.get("visualId") or "")
        if vis.startswith("ultraTitus"):
            out["att"] = u.get("id")
        elif vis.startswith("tauMarksman"):
            out["victime"] = u.get("id")
        elif "Drone" in vis:
            out["drone"] = u.get("id")
    return out, dv


def _hp(sid, rid):
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    return {int(u["id"]): int(u.get("hp") or 0) for u in (ob.get("units") or []) if "id" in u}, ob


def _normal_attack_id(sid, rid, att) -> int:
    ab = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": att}, 90)
    for row in (ab.get("abilities") or []):
        if (row.get("kind") or "") == "normal":
            return int(row.get("abilityType") or NORMAL_ATTACK_FALLBACK)
    return NORMAL_ATTACK_FALLBACK


#: `IdunBattle.Streams.StepType.TransferDamage` = 0x23 = 35 -- le pas de flux qu'emet
#: `IdunBattle.Operations.TransferDamageOperation$$Execute` par cible de transfert, avec les tags
#: `0xb4 Original_Target_Id`, `0xb7 Final_Target_Id`, `Caster_Id`. C'est le TEMOIN NATIF DIRECT du
#: transfert : il ne se deduit d'aucun delta de PV.
STEP_TRANSFER_DAMAGE = 35


def _events_damage(res: dict):
    """Ventile le flux natif : degat PAR COUP (`UnitDamaged`, reconnu par ses tags `Target_Id` +
    `Amount`) et pas de flux `TransferDamage` (`step == 35`).

    Les events du RPC portent leurs tags en CHAINE JSON (`"tags": "{...}"`), pas en dict -- les
    lire comme un dict rendrait un flux vide, donc un faux « aucun transfert »."""
    par_cible, transferts = {}, []

    def tags_of(node):
        t = node.get("tags")
        if isinstance(t, str):
            try:
                return json.loads(t)
            except ValueError:
                return {}
        return t if isinstance(t, dict) else {}

    def walk(node):
        if isinstance(node, dict):
            tg = tags_of(node)
            if "Target_Id" in tg and "Amount" in tg:
                par_cible.setdefault(int(tg["Target_Id"]), []).append(int(tg["Amount"]))
            if int(node.get("step") or -1) == STEP_TRANSFER_DAMAGE and "Final_Target_Id" in tg:
                transferts.append({"caster": tg.get("Caster_Id"),
                                   "original": tg.get("Original_Target_Id"),
                                   "final": tg.get("Final_Target_Id")})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(res)
    return par_cible, transferts


def _events_damage_ventile(res: dict) -> dict:
    """MEME flux que `_events_damage`, mais ventile par `(Target_Id, Attacker_Id)`.

    ⚠ POURQUOI CET AXE EXISTE, et ce que son absence a fait accuser (#1020-r11) : le tag
    `Target_Id` seul REGROUPE tout ce qui frappe une unite pendant l'action -- **y compris ce
    que frappe un AUTRE attaquant**. Sur le montage `orksRuntherd`, l'attaque declenche
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility`, dont le
    `CreateBehaviour` range un noeud
    `IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAttackFromCurrentPosition` dans les
    `SpawnUnitOptions` du `Spawn` : l'unite SUMMONEE attaque toute seule, dans la MEME reponse
    RPC, avec SON `Attacker_Id`, SON profil d'arme et `Attack_Is_First_Hit = 1`. Sommer par
    cible seule compte donc ce coup-la comme un coup DE L'ATTAQUE -- ce qui a fait ecrire, et
    chiffrer, un ecart de port qui n'existe pas.

    Rend `{Target_Id: {Attacker_Id: [Amount, ...]}}`, dans l'ordre du flux."""
    out = {}

    def tags_of(node):
        t = node.get("tags")
        if isinstance(t, str):
            try:
                return json.loads(t)
            except ValueError:
                return {}
        return t if isinstance(t, dict) else {}

    def walk(node):
        if isinstance(node, dict):
            tg = tags_of(node)
            if "Target_Id" in tg and "Amount" in tg:
                att = tg.get("Attacker_Id")
                out.setdefault(int(tg["Target_Id"]), {}).setdefault(
                    None if att is None else int(att), []).append(int(tg["Amount"]))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(res)
    return out


def _deltas(res: dict):
    """Les `hpDelta` que le RPC rend deja ventiles par `squadId` -- canal INDEPENDANT du flux
    d'events (deux canaux qui doivent concorder ; s'ils divergent, la mesure est fausse)."""
    out = {}
    for act in (res.get("actions") or []):
        for ch in (act.get("changes") or []):
            sid_ = ch.get("squadId")
            if sid_ is not None and ch.get("hpDelta") is not None:
                out[int(sid_)] = out.get(int(sid_), 0) + int(ch["hpDelta"])
    return out


def mesure_native(sid, rid, ids, ab_id):
    """Joue l'attaque cote NATIF et rend l'etat AVANT/APRES + le flux ventile."""
    hp0, ob0 = _hp(sid, rid)
    dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    snap0 = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    rng0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ids["att"], "targetId": ids["victime"],
        "abilityType": int(ab_id)}}, 120)
    hp1, _ = _hp(sid, rid)
    rng1 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    coups, transferts = _events_damage(res)
    return {"hp0": hp0, "hp1": hp1, "dv0": dv0, "ob0": ob0, "snap0": snap0,
            "rng0": rng0, "rng1": rng1, "res": res,
            "events": coups, "transferts": transferts, "deltas": _deltas(res),
            "ok": bool(res.get("ok")) and all(a.get("ok") for a in (res.get("actions") or []))}


def mesure_port(nat, ids, board, sans_rail: bool = False):
    """Rejoue LA MEME attaque sur le MEME etat par le moteur porte, avec le MEME etat MT.

    `sans_rail` = la contre-epreuve : `SaviorProtocols` est retire du registre de dispatch, donc
    aucun trigger `On(0x39)` ne peut consommer le pending. Le port doit alors appliquer TOUT a la
    victime -- si le verdict ne bouge pas, la mesure ne regarde pas le rail."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import HealthComponent
    from engine.runner.operations.damage import AttackDamageOperation
    import engine.runner.operations.triggers.dispatch.registry as REG

    st = load_state(nat["dv0"], nat["ob0"], nat["snap0"], board=board)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(nat["rng0"]["mt"]), nat["rng0"]["mti"]
    st.rng = rng
    sauve = None
    if sans_rail:
        sauve = REG.ABILITY_TRIGGERS.pop("SaviorProtocols", None)
    try:
        def hp(uid):
            e = st.get_entity(int(uid))
            c = e.get_component(HealthComponent) if e is not None else None
            return None if c is None else c.hp
        avant = {k: hp(v) for k, v in ids.items()}
        # Compteur de transferts PAR COUP, pris a la source (l'Operation elle-meme) : c'est le seul
        # canal qui distingue « 3 coups sur 4 transferes » de « tout ou rien », et il ne se deduit
        # d'aucun delta de PV.
        import engine.runner.abilities.behaviours.transfer as TR
        vrai = TR.transfer_damage_operation
        vus = []

        def compte(state, caster_id, orig, tgt, hit_index=None, attack_ability=None):
            # `attack_ability` (#1020-r2) = le 5e parametre natif, celui qui descend au slot
            # `64 = DirectDamage`. Le stub DOIT porter le contrat reel, sinon le probe tombe sur
            # son propre echafaudage au lieu de mesurer le port.
            out = vrai(state, caster_id, orig, tgt, hit_index=hit_index,
                       attack_ability=attack_ability)
            if out is not None:
                vus.append(out)
            return out

        TR.transfer_damage_operation = compte
        try:
            r = AttackDamageOperation.execute(st, int(ids["att"]), int(ids["victime"]))
        finally:
            TR.transfer_damage_operation = vrai
        apres = {k: hp(v) for k, v in ids.items()}
        return {"avant": avant, "apres": apres, "attack": r,
                "transferts": vus, "mti": st.rng.mti}
    finally:
        if sauve is not None:
            REG.ABILITY_TRIGGERS["SaviorProtocols"] = sauve


def run(seed: int = 777, board_id: str = "MC1_67", dmg: int | None = 900, verbose: bool = True,
        drone_loin: bool = False):
    sid = _sid()
    rid, sf = stage(seed, board_id, dmg_attaquant=dmg, drone_loin=drone_loin)
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        ids, _dv = _ids(sid, rid)
        if not all(k in ids for k in ("att", "victime", "drone")):
            raise MontageError("entites introuvables : %s" % ids)
        ab_id = _normal_attack_id(sid, rid, ids["att"])
        nat = mesure_native(sid, rid, ids, ab_id)
        if not nat["ok"]:
            raise MontageError("applyAction REFUSEE : %s" % json.dumps(nat["res"])[:400])
        port = mesure_port(nat, ids, board, sans_rail=False)
        port_sr = mesure_port(nat, ids, board, sans_rail=True)
        out = {"seed": seed, "board": board_id, "runner": rid, "ids": ids,
               "ability": ab_id,
               "natif": {
                   "victime_perdu": nat["hp0"].get(ids["victime"], 0) - nat["hp1"].get(ids["victime"], 0),
                   "drone_perdu": nat["hp0"].get(ids["drone"], 0) - nat["hp1"].get(ids["drone"], 0),
                   "coups_victime": nat["events"].get(int(ids["victime"]), []),
                   "coups_drone": nat["events"].get(int(ids["drone"]), []),
                   "transferts": nat["transferts"], "deltas": nat["deltas"],
                   "mti0": nat["rng0"].get("mti"), "mti1": nat["rng1"].get("mti")},
               "port": {
                   "victime_perdu": (port["avant"]["victime"] or 0) - (port["apres"]["victime"] or 0),
                   "drone_perdu": (port["avant"]["drone"] or 0) - (port["apres"]["drone"] or 0),
                   "total": (port["attack"] or {}).get("total"),
                   "coups_transferes": [t.get("requested") for t in port["transferts"]],
                   "coups": ((port["attack"] or {}).get("per_hit_health")
                             or (port["attack"] or {}).get("per_hit")),
                   "mti": port["mti"]},
               "port_sans_rail": {
                   "victime_perdu": (port_sr["avant"]["victime"] or 0) - (port_sr["apres"]["victime"] or 0),
                   "drone_perdu": (port_sr["avant"]["drone"] or 0) - (port_sr["apres"]["drone"] or 0)}}
        if verbose:
            _print(out)
        return out
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(sf)],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=120)


def _print(o):
    n, p, sr = o["natif"], o["port"], o["port_sans_rail"]
    print("=== #1020 SaviorProtocols LIVE -- seed %s board %s runner %s ==="
          % (o["seed"], o["board"], o["runner"]))
    print("  entites : attaquant=%s victime=%s drone=%s" % (o["ids"]["att"], o["ids"]["victime"],
                                                            o["ids"]["drone"]))
    print("  NATIF  : victime -%d  drone -%d   coups victime=%s  coups drone=%s"
          % (n["victime_perdu"], n["drone_perdu"], n["coups_victime"], n["coups_drone"]))
    print("  NATIF  : pas de flux TransferDamage (step 35) = %d -> %s"
          % (len(n["transferts"]), n["transferts"]))
    print("  NATIF  : hpDelta du RPC (canal INDEPENDANT du flux) = %s" % n["deltas"])
    print("  PORT   : victime -%d  drone -%d   total attaque=%s   coups=%s  transferes=%s"
          % (p["victime_perdu"], p["drone_perdu"], p["total"], p["coups"], p["coups_transferes"]))
    mixte_p = bool(p["coups_transferes"]) and len(p["coups_transferes"]) < len(p["coups"] or [])
    print("  REGIME MIXTE port  (%d transferts sur %d coups) : %s"
          % (len(p["coups_transferes"]), len(p["coups"] or []), "OUI" if mixte_p else "non"))
    print("  PORT SANS RAIL : victime -%d  drone -%d  (contre-epreuve : tout doit rester a la victime)"
          % (sr["victime_perdu"], sr["drone_perdu"]))
    mixte_n = bool(n["coups_victime"]) and bool(n["coups_drone"])
    print("  REGIME MIXTE natif (le discriminant PAR COUP) : %s" % ("OUI" if mixte_n else "non"))
    print("  CONSERVATION natif : victime+drone = %d" % (n["victime_perdu"] + n["drone_perdu"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--dmg", type=int, default=900,
                    help="borne le Damage de l'attaquant pour que le drone SURVIVE a la serie")
    ap.add_argument("--temoin", action="store_true",
                    help="bras TEMOIN : drone HORS adjacence -> zero transfert des deux cotes ; "
                         "c'est lui qui dit si un ecart de total appartient au transfert ou a un "
                         "etage EN AMONT")
    a = ap.parse_args()
    try:
        run(seed=a.seed, board_id=a.board, dmg=a.dmg, drone_loin=a.temoin)
    except MontageError as e:
        print("[1020] MONTAGE KO : %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
