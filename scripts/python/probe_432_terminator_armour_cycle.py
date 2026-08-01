"""#432 -- le CYCLE d'armement de `1147 TerminatorArmour_ReduceDmg`, CONFRONTE au NATIF.

QUESTION (binaire) : la reduction de -75 % de l'armure Terminator s'applique-t-elle a TOUTE attaque
recue (ce que faisait le port), ou seulement a la PREMIERE de chaque tour (ce que dit l'i2
`Traits/TerminatorArmour_Description` et ce que dit le decompile) ?

Et, sous-question qui decide le MONTAGE : la consommation est-elle par COUP ou par ATTAQUE ?
`IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger` ecoute
`On(9 = Attack)`, emis par `IdunBattle.Operations.FinishAttackOperation$$Execute` **une seule fois
par attaque, a sa CLOTURE** -> tous les coups de la 1re attaque sont reduits. Le regime MONO-COUP
est donc DEGENERE (les deux lectures y coincident) : le discriminant est **deux attaques dans le
MEME tour**, et le LEDGER PAR COUP tranche « premier coup » contre « premiere attaque ».

MONTAGE (aucune geometrie subie -- les trois unites sont DRIVEES a leur place) :

  * porteur / defenseur : `spaceStormcaller` (Njal). C'est le SEUL porteur `lineup` de
    `TerminatorArmour` qui n'a NI `TeleportStrike` (il serait hors plateau 2 tours) NI `Resilient`
    (un plafond per-coup qui masquerait le facteur 4). Ses traits : Hero, Psyker, TerminatorArmour,
    Unstoppable ; son passif `LordOfTempests` ne modifie QUE ses propres attaques.
  * attaquant A : `tauAunShi` -- **5 coups** de melee, profil `Power` (non exclu), seul trait `Hero`.
    C'est LUI qui porte le ledger par coup.
  * attaquant B : `astraBullgryn` -- 4 coups de melee, profil `Physical`. Son role est uniquement de
    CONSOMMER l'armure : sa magnitude n'entre dans aucune assertion.

  Les deux attaquants sont poses sur l'anneau de Njal AVANT la premiere attaque et n'en bougent
  plus : leur etat (`Moved`, adjacence) est donc IDENTIQUE aux deux tours mesures.

SEQUENCE (l'IA adverse est neutralisee, `--no-ai` ; `endturn` ne la fait pas jouer) :

  tour 1 : A frappe (1re attaque du tour -> REDUITE)   puis B frappe (2e -> NON reduite)
  endturn x2
  tour 2 : B frappe (1re -> REDUITE)                   puis A frappe (2e -> NON reduite)

  => **A est mesure DANS LES DEUX REGIMES, a position et cible identiques.** Le rapport
  `total(A, tour 2) / total(A, tour 1)` doit valoir ~4 (a la dispersion +/-20 % pres). Un port qui
  reduit TOUJOURS rendrait ~1.

CE QUE LE PROBE MESURE, aux trois etages :

  1. ETAT NATIF de l'effet -- `decisionView({includeInactive:true})` expose le flag
     `EffectComponent.IsActive @+0x5c` de CHAQUE instance. On le lit avant/apres chaque attaque et
     apres le boundary de tour : c'est un observable BINAIRE, sans arithmetique.
  2. LEDGER PAR COUP natif -- les evenements du cast portent l'`Amount` de chaque coup. On compte
     combien de coups de l'attaque #1 sont dans le regime REDUIT (compare a la moyenne per-coup de
     la MEME unite dans son attaque NON reduite). « premier coup seulement » predirait 1/5 ;
     « premiere attaque » predit 5/5.
  3. PORT -- l'etat capte AVANT la 1re attaque est rejoue OFFLINE, les deux attaques ENCHAINEES sur
     le MEME `State` et le MEME flux RNG (`AttackUnitMessage`). Le port doit reproduire le meme
     classement de regime (reduit / non reduit) attaque par attaque, et son propre flag `e.active`
     doit suivre la meme trajectoire que le natif.

CONTRE-EPREUVE (`--mutate`) : l'entree `EFFECT_TRIGGERS[1147]` est RETIREE du registre -- c'est
EXACTEMENT l'etat d'`origin/master` (les quatre classes n'existaient pas, et les deux canaux d'event
neufs n'ont aucun autre consommateur), pas une caricature. Le port doit alors reduire les DEUX
attaques -> la garde ROUGIT. Et la mutation est VERIFIEE avoir MORDU avant qu'on lise le verdict :
le flag `e.active` ne doit plus tomber. Sur une contre-epreuve, VERT est le resultat SUSPECT.

Discipline runner : state-file ABSOLU sous `logs/`, `--board` explicite, dispose en sortie.
ASCII only (cp1252).

CLI (depuis scripts/python) :
  python probe_432_terminator_armour_cycle.py
  python probe_432_terminator_armour_cycle.py --mutate
  python probe_432_terminator_armour_cycle.py --seed 4321 --board C3_01
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
CARRIER = "spaceStormcaller"     # Njal -- TerminatorArmour, sans TeleportStrike ni Resilient
ATT_A = "tauAunShi"              # 5 coups melee, profil Power -- porte le ledger par coup
ATT_B = "astraBullgryn"          # 4 coups melee, profil Physical -- consomme l'armure
ATT_PSY = "astraPrimarisPsy"     # Sibyll -- attaque normale PSYCHIQUE = profil EXCLU (bras `psychic`)
TERMINATOR_REDUCE = 1147
TERMINATOR_VISUAL = 1375


# --------------------------------------------------------------------------- montage live


def _build(seed, board, p_units, hp=400000, rank=17):
    sf = ROOT / "logs" / "runners" / ("p432-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", board, "--rank", str(rank),
         "--p-units", ",".join(p_units), "--a-units", CARRIER,
         "--hp-target", str(hp), "--crit", "0,0", "--block-target", "0,0", "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-800:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _view(rpc, rid, inactive=False):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": bool(inactive)}, 180)


def _by_vis(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _unit(dv, uid):
    return next((x for x in (dv.get("units") or []) if int(x.get("id", -1)) == int(uid)), None)


def _effects_of(dv, uid):
    """Les entrees d'effet portees par `uid` dans un `decisionView` : elles vivent sur l'unite
    (`units[].effects`), chacune avec son flag `active` = `EffectComponent.IsActive @+0x5c`."""
    return (_unit(dv, uid) or {}).get("effects") or []


def _armour_state(dv, uid, effect_type=TERMINATOR_REDUCE):
    """(present, active) de l'instance `effect_type` sur `uid`, lu du canal `includeInactive`.
    `active` = le flag natif `EffectComponent.IsActive @+0x5c`."""
    for e in _effects_of(dv, uid):
        et = e.get("effectType")
        if et is not None and int(et) == int(effect_type):
            a = e.get("active")
            return True, (None if a is None else bool(a))
    return False, None


def _normal_attack_id(dv, uid):
    """Id CONCRET de l'attaque normale (`kind == "normal"`), PER-UNITE -- jamais le 17 generique."""
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _move(rpc, rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _hp(dv, uid):
    u = _unit(dv, uid)
    return None if u is None else int(u.get("hp", 0))


def _attack(rpc, rid, cid, tid, ab):
    """Attaque NORMALE live + extraction du ledger par coup (`Amount` des evenements)."""
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


# --------------------------------------------------------------------------- rejeu offline


def _replay_two_attacks(cap, board, att_ids, tgt_id, mutate=False):
    """Rejoue les DEUX attaques du tour 1, ENCHAINEES sur le MEME `State` et le MEME flux RNG.

    C'est l'enchainement qui compte : le cycle du port n'est exerce que si l'attaque #2 voit l'etat
    laisse par l'attaque #1. Un rejeu attaque-par-attaque depuis une capture FRAICHE serait
    tautologique -- `decisionView` par defaut ne publie que les effets ACTIFS, donc l'armure
    consommee y est deja absente et le port « aurait raison » sans porter le cycle.

    `mutate=True` RETIRE l'entree `EFFECT_TRIGGERS[1147]` du registre. Ce n'est pas « une » mutation
    parmi d'autres : c'est EXACTEMENT l'etat d'avant #432 (les quatre classes n'existaient pas, et
    les deux canaux d'event neufs -- `health_damage` / `was_block` -- n'ont aucun autre
    consommateur). Le bras mutant EST donc le port de `origin/master`, pas une caricature."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS

    st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
    tgt = st.get_entity(int(tgt_id))
    hc = tgt.get_component(HealthComponent)
    hp_before = int(hc.hp)

    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng

    saved = None
    if mutate:
        saved = EFFECT_TRIGGERS.pop(TERMINATOR_REDUCE, None)
    try:
        runner = Runner(st).install_default_handlers(20)
        out = []
        for att in att_ids:
            h0 = int(hc.hp)
            runner.apply(AttackUnitMessage(int(att), int(tgt_id)))
            last = runner.damage_handler.last or {}
            out.append({"attacker": int(att), "hp_delta": h0 - int(hc.hp),
                        "total": last.get("total"), "per_hit": last.get("per_hit"),
                        "armour_active": _port_armour_active(st, int(tgt_id))})
    finally:
        if saved is not None:
            EFFECT_TRIGGERS[TERMINATOR_REDUCE] = saved
    return {"hp_before": hp_before, "attacks": out,
            "armour_active_end": _port_armour_active(st, int(tgt_id))}


def _port_armour_active(state, uid):
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(uid), []):
        if e.effect_type == TERMINATOR_REDUCE and not e.consumed:
            return bool(e.active)
    return None


# --------------------------------------------------------------------------- pilote


#: Les BRAS du probe. Chaque bras nomme ses attaquants et l'ORDRE d'attaque de chaque tour.
#: `base`    -- le discriminant central : A est mesure DANS LES DEUX REGIMES (1re et 2e attaque).
#: `psychic` -- le gate `CurrentAttackDamageProfilesContainOtherThan(Psychic,DirectDamage)` : la 1re
#:              attaque est PSYCHIQUE, donc elle ne consomme PAS l'armure et n'est pas reduite ; la
#:              2e (profil Power) doit donc etre REDUITE alors qu'elle est la DEUXIEME du tour.
ARMS = {
    "base": {"p_units": [ATT_A, ATT_B], "t1": [ATT_A, ATT_B], "t2": [ATT_B, ATT_A]},
    # ⚠ Le 3e attaquant du bras `psychic` n'attaque JAMAIS : il est la pour que la 2e attaque ne
    #   soit pas la DERNIERE du tour. Sans lui, le tour se cloturerait tout seul juste apres, et la
    #   lecture du flag natif « apres » porterait deja le `On(0x12)` de re-armement du tour suivant
    #   -- un artefact de MONTAGE qu'on lirait comme « l'armure n'a pas ete consommee ».
    "psychic": {"p_units": [ATT_PSY, ATT_A, ATT_B], "t1": [ATT_PSY, ATT_A], "t2": None},
}


def run(seed=SEED, board=BOARD, mutate=False, arm="base", verbose=True) -> dict:
    spec = ARMS[arm]
    rid, sf, err = _build(seed, board, p_units=spec["p_units"])
    if rid is None:
        return {"error": "build KO : %s" % err}
    rpc = _mkrpc()
    try:
        return _measure(rpc, rid, mutate, arm, spec, verbose, board=board, seed=str(seed))
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def _measure(rpc, rid, mutate, arm, spec, verbose, board=None, seed=None):
    from engine.entities.pathfinding.board import Board as _BoardCls
    Board = _BoardCls
    board_id, seed_id = board, seed

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = _view(rpc, rid, inactive=True)
    ids = {}
    for v in [CARRIER] + list(spec["p_units"]):
        u = _by_vis(dv, v)
        if u is None:
            return {"error": "unite absente du build : %s" % v}
        ids[v] = int(u["id"])

    # --- geometrie DRIVEE : le porteur reste sur sa tuile, les attaquants sur son ANNEAU --------
    njal = _unit(dv, ids[CARRIER])
    ctile = board.id_at(int(njal["pos"]["col"]), int(njal["pos"]["row"]))
    ring = [t for t in board.neighbours(ctile)]
    # SEULS les attaquants du tour 1 sont amenes au contact ; les SPECTATEURS (les `p_units` qui ne
    # figurent pas dans un ordre d'attaque) restent a leur spawn -- ils n'existent que pour empecher
    # la cloture AUTOMATIQUE du tour apres la derniere attaque mesuree.
    to_place = list(dict.fromkeys(list(spec["t1"]) + list(spec["t2"] or [])))
    if len(ring) < len(to_place):
        return {"error": "tuile du porteur trop pauvre en voisins (%d pour %d attaquants)"
                         % (len(ring), len(to_place))}
    for i, v in enumerate(to_place):
        _move(rpc, rid, ids[v], *board.coord(ring[i]))

    dv = _view(rpc, rid, inactive=True)
    na = {v: _normal_attack_id(dv, ids[v]) for v in spec["p_units"]}
    if any(x is None for x in na.values()):
        return {"error": "id d'attaque normale introuvable : %s" % na}

    # --- capture AVANT la 1re attaque (etat + flux RNG communs au natif et au rejeu offline) -----
    cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
           "snap": rpc("combatSnapshot", {"runnerId": rid}, 120),
           "rng": rpc("dumpRng", {"runnerId": rid}, 30)}

    steps, native = [], []

    def _snap_state(label):
        d = _view(rpc, rid, inactive=True)
        present, active = _armour_state(d, ids[CARRIER])
        vpresent, vactive = _armour_state(d, ids[CARRIER], TERMINATOR_VISUAL)
        steps.append({"at": label, "present": present, "active": active,
                      "visual_present": vpresent, "visual_active": vactive,
                      "hp": _hp(d, ids[CARRIER]), "player": d.get("currentPlayer")})
        return d, active

    d0, act0 = _snap_state("t1_avant")
    mine = d0.get("currentPlayer")

    def _one(turn, rank, vis, before):
        _res, hits = _attack(rpc, rid, ids[vis], ids[CARRIER], na[vis])
        _d, after = _snap_state("t%d_apres_%s" % (turn, vis))
        native.append({"turn": turn, "rank": rank, "attacker": vis,
                       "hits": hits, "total": sum(hits),
                       "armour_before": before, "armour_after": after})
        return after

    # --- TOUR 1 ---------------------------------------------------------------------------------
    # ⚠ Le tour se termine SEUL des que TOUTES mes unites ont agi (le natif enchaine
    # EndTurn/ChangeTurn/StartTurn) : l'etat lu APRES la derniere attaque du tour porte donc DEJA
    # le `On(0x12)` de re-armement du tour suivant. C'est ce boundary implicite qui avait fait lire
    # « active=True apres la 2e attaque » a la premiere passe.
    cur = act0
    for i, vis in enumerate(spec["t1"]):
        cur = _one(1, i + 1, vis, cur)

    if spec["t2"]:
        # Un SEUL endturn : il clot le tour ADVERSE (l'IA est neutralisee, elle ne joue rien).
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        d2, cur = _snap_state("t2_avant")
        if d2.get("currentPlayer") != mine:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
            d2, cur = _snap_state("t2_avant_bis")
        if d2.get("currentPlayer") != mine:
            return {"error": "le tour n'est pas revenu a moi (player=%s attendu=%s)"
                             % (d2.get("currentPlayer"), mine), "steps": steps}
        for i, vis in enumerate(spec["t2"]):
            cur = _one(2, i + 1, vis, cur)

    port = _replay_two_attacks(cap, board, [ids[v] for v in spec["t1"]], ids[CARRIER],
                               mutate=mutate)

    out = {"runner": rid, "ids": ids, "normal_attack": na, "steps": steps,
           "native": native, "port": port, "mutate": bool(mutate), "arm": arm,
           "board": board_id, "seed": seed_id, "order_t1": list(spec["t1"])}
    if verbose:
        _report(out)
    return out


def _att(r, vis, rank):
    """L'attaque NATIVE de `vis` au rang `rank` de son tour (1 = 1re du tour, 2 = 2e...)."""
    return next((a for a in r["native"] if a["attacker"] == vis and a["rank"] == rank), None)


def _report(r):
    print("[432] arm=%s board=%s seed=%s runner=%s ids=%s"
          % (r.get("arm"), r.get("board"), r.get("seed"), r["runner"], r["ids"]))
    print("[432] --- etat NATIF (decisionView includeInactive) : flag IsActive @+0x5c ---")
    for s in r["steps"]:
        print("       %-16s 1147 act=%-5s | 1375 act=%-5s | hp=%-8s player=%s"
              % (s["at"], s["active"], s["visual_active"], s["hp"], s["player"]))
    print("[432] --- ledger NATIF par coup ---")
    for a in r["native"]:
        print("       tour%d rang%d %-18s total=%-8d coups=%s  (armure avant=%s apres=%s)"
              % (a["turn"], a["rank"], a["attacker"], a["total"], a["hits"],
                 a["armour_before"], a["armour_after"]))
    print("[432] --- PORT (rejeu offline ENCHAINE du tour 1, mutate=%s) ---" % r["mutate"])
    for a in r["port"]["attacks"]:
        print("       attaquant=%-4s total=%-8s hp_delta=%-8d armour_active_apres=%s"
              % (a["attacker"], a["total"], a["hp_delta"], a["armour_active"]))


def verdict(base: dict, mut: dict) -> list:
    """Les echecs (liste de chaines) des DEUX bras du bras `base` : le NATIF, le PORT, la MUTATION.
    Vide = tout tient. Aucun scalaire n'est fitte : les bornes sont derivees de la magnitude LUE
    (`terminatorArmourDmgReduction = -75` -> facteur 4) et de la dispersion de degat (+/-20 %,
    `BattleConfiguration.Damage.DamageSpreadPercentage`), soit un ratio dans [4*0.8/1.2, 4*1.2/0.8]
    = [2.67, 6.0]."""
    f = []
    a1 = _att(base, ATT_A, 1)     # tour 1 : A ATTAQUE EN PREMIER  -> armure ARMEE
    b2 = _att(base, ATT_B, 2)     # tour 1 : B attaque en 2e       -> armure CONSOMMEE
    b1 = _att(base, ATT_B, 1)     # tour 2 : B attaque en premier  -> armure RE-ARMEE
    a2 = _att(base, ATT_A, 2)     # tour 2 : A attaque en 2e       -> armure CONSOMMEE
    if not all((a1, b2, b1, a2)):
        return ["mesure incomplete : %s" % [(x or {}).get("attacker") for x in (a1, b2, b1, a2)]]

    # (1) NATIF -- la trajectoire du flag `EffectComponent.IsActive @+0x5c`.
    if a1["armour_before"] is not True:
        f.append("[natif] l'armure n'etait pas ARMEE avant la 1re attaque du tour 1")
    if a1["armour_after"] is not False:
        f.append("[natif] la 1re attaque du tour 1 n'a PAS desarme l'armure")
    if b1["armour_before"] is not True:
        f.append("[natif] l'armure n'a PAS ete re-armee au boundary de tour")
    if b1["armour_after"] is not False:
        f.append("[natif] la 1re attaque du tour 2 n'a PAS desarme l'armure")
    # `_Visual` (1375) suit le MEME cycle -- il herite les triggers de `_ReduceDmg`.
    if [s["active"] for s in base["steps"]] != [s["visual_active"] for s in base["steps"]]:
        f.append("[natif] 1375 `_Visual` ne suit PAS la meme trajectoire que 1147")

    # (2) NATIF -- le LEDGER PAR COUP : c'est « la premiere ATTAQUE », pas « le premier COUP ».
    for red, non in ((a1, a2), (b1, b2)):
        if len(red["hits"]) != len(non["hits"]):
            f.append("[natif] %s ne porte pas le meme nombre de coups dans les deux regimes (%d/%d)"
                     % (red["attacker"], len(red["hits"]), len(non["hits"])))
            continue
        n_red = sum(1 for h in red["hits"] if h < min(non["hits"]))
        if n_red != len(red["hits"]):
            f.append("[natif] %s : %d/%d coups REDUITS dans l'attaque consommatrice -- « premier "
                     "COUP seulement » predirait 1, « premiere ATTAQUE » predit %d (coups reduits=%s"
                     " / non reduits=%s)" % (red["attacker"], n_red, len(red["hits"]),
                                             len(red["hits"]), red["hits"], non["hits"]))
        ratio = non["total"] / float(red["total"] or 1)
        if not (2.67 <= ratio <= 6.0):
            f.append("[natif] %s : ratio non-reduit/reduit = %.2f hors de l'enveloppe [2.67, 6.0] "
                     "du -75%% a dispersion +/-20%% (%d vs %d)"
                     % (red["attacker"], ratio, non["total"], red["total"]))

    # (3) PORT -- le rejeu ENCHAINE du tour 1 doit egaler le natif, attaque par attaque.
    pa = base["port"]["attacks"]
    if len(pa) != 2:
        f.append("[port] rejeu incomplet (%d attaques)" % len(pa))
    else:
        for got, exp, lbl in ((pa[0], a1, "1re (REDUITE)"), (pa[1], b2, "2e (NON reduite)")):
            if int(got["hp_delta"]) != int(exp["total"]):
                f.append("[port] attaque %s : port=%d natif=%d (ecart %+d)"
                         % (lbl, got["hp_delta"], exp["total"],
                            got["hp_delta"] - exp["total"]))
        if pa[0]["armour_active"] is not False:
            f.append("[port] le flag `e.active` n'est pas tombe apres la 1re attaque")

    # (4) MUTATION -- contre-epreuve. VERT est le resultat SUSPECT : on VERIFIE d'abord qu'elle a
    #     MORDU (le flag ne tombe plus), puis qu'elle CASSE bien la 2e attaque.
    mp = mut["port"]["attacks"]
    if len(mp) != 2:
        f.append("[mutation] rejeu incomplet (%d attaques)" % len(mp))
    else:
        if mp[0]["armour_active"] is not True:
            f.append("[mutation] LA MUTATION N'A PAS MORDU : le flag `e.active` tombe quand meme "
                     "-- le verdict qui suit ne prouverait rien")
        if int(mp[1]["hp_delta"]) >= int(b2["total"]):
            f.append("[mutation] cycle NEUTRALISE, la 2e attaque rend %d (>= natif %d) : la garde "
                     "ne rougirait PAS" % (mp[1]["hp_delta"], b2["total"]))
        if int(mp[0]["hp_delta"]) != int(a1["total"]):
            f.append("[mutation] la 1re attaque a CHANGE (%d vs %d) : la mutation deborde du "
                     "regime qu'elle vise" % (mp[0]["hp_delta"], a1["total"]))
    return f


def verdict_psychic(r: dict) -> list:
    """Le bras `psychic` : la 1re attaque du tour porte un profil EXCLU
    (`terminatorArmourExcludedDmgProfiles = Psychic,DirectDamage`) -> elle ne consomme PAS l'armure,
    donc la 2e attaque du MEME tour (profil `Power`) est REDUITE. C'est le gate
    `CurrentAttackDamageProfilesContainOtherThan` -- le seul regime ou « 2e attaque du tour » et
    « attaque non reduite » se SEPARENT."""
    f = []
    p1 = _att(r, ATT_PSY, 1)
    a2 = _att(r, ATT_A, 2)
    if not (p1 and a2):
        return ["mesure incomplete (bras psychic)"]
    if p1["armour_before"] is not True:
        f.append("[psychic] l'armure n'etait pas ARMEE avant l'attaque psychique")
    if p1["armour_after"] is not True:
        f.append("[psychic] l'attaque PSYCHIQUE a consomme l'armure : le gate "
                 "`CurrentAttackDamageProfilesContainOtherThan` ne mord pas")
    if a2["armour_after"] is not False:
        f.append("[psychic] la 2e attaque (profil Power) n'a PAS consomme l'armure")
    pa = r["port"]["attacks"]
    if len(pa) != 2:
        f.append("[psychic][port] rejeu incomplet (%d attaques)" % len(pa))
    else:
        for got, exp, lbl in ((pa[0], p1, "psychique"), (pa[1], a2, "Power (REDUITE)")):
            if int(got["hp_delta"]) != int(exp["total"]):
                f.append("[psychic][port] attaque %s : port=%d natif=%d (ecart %+d)"
                         % (lbl, got["hp_delta"], exp["total"], got["hp_delta"] - exp["total"]))
        if pa[0]["armour_active"] is not True:
            f.append("[psychic][port] le port a desarme l'armure sur une attaque PSYCHIQUE")
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--arm", default="base", choices=sorted(ARMS))
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--verdict", action="store_true",
                    help="joue les deux bras (normal + mutate) et imprime le verdict")
    a = ap.parse_args()
    if a.verdict:
        base = run(seed=a.seed, board=a.board, arm=a.arm)
        if "error" in base:
            print("[432] ERREUR (base) : %s" % base["error"])
            return 2
        if a.arm == "psychic":
            fails = verdict_psychic(base)
        else:
            mut = run(seed=a.seed, board=a.board, arm=a.arm, mutate=True)
            if "error" in mut:
                print("[432] ERREUR (mutate) : %s" % mut["error"])
                return 2
            fails = verdict(base, mut)
        print("[432] VERDICT : %s" % ("OK" if not fails else "%d echec(s)" % len(fails)))
        for x in fails:
            print("   - %s" % x)
        return 0 if not fails else 1
    r = run(seed=a.seed, board=a.board, arm=a.arm, mutate=a.mutate)
    if "error" in r:
        print("[432] ERREUR : %s" % r["error"])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
