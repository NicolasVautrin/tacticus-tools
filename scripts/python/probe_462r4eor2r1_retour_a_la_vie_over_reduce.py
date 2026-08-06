"""#462-r4e-o-r2-r1 -- CONFRONTATION LIVE du regime « retour a la vie NATIF puis attaque NATIVE ».

#462-r4e-o-r2 a tranche au DECOMPILE que l'accumulateur de sur-reduction
`IdunBattle.Entities.Components.FillUpStatComponent+0x24` (`HealthComponent.over_reduce` cote port)
est PURGE par `IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` -- appele par
`IdunBattle.Operations.HealUnitOperation$$Execute`, `IdunBattle.Operations.RepairUnitOperation$$Execute`
et `IdunBattle.Operations.ResurrectUnitOperation$$SetHealth` -- mais PAS par le REVIVE
(`IdunBattle.Operations.ReviveUnitOperation$$SetHealth` pose les PV par un modificateur de stat,
relu ici : ni `FillUp` ni `Initialize`). RIEN n'avait jamais ete joue LIVE.

DEUX QUESTIONS BINAIRES, un OBSERVABLE COMMUN : la CARDINALITE des events `Amount` de l'attaque
qui suit le retour a la vie.

  (a) REVIVE (`TaintedNarthecium`, `deathRotbone` + allie Chaos adjacent, 75 %, even-if-Overkilled)
      -- l'accumulateur SURVIT => `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` est VRAI
      DES LE PREMIER coup, a pleine vie ; le SITE (A) d'
      `IdunBattle.Operations.ApplyDamageOperation$$Execute` supprime alors tous les suivants
      => **UN SEUL** event. S'il avait ete purge : cardinalite PLEINE.
  (b) RESURRECT (trait `Ambush`, `genesPrimus` -- `EnvAmbushResurrectAbility` sur `On(TurnStart)`
      au tour SUIVANT) -- `FillUp` purge => cardinalite PLEINE.

POURQUOI UN PROBE DEDIE (aucun harnais existant ne le monte) : `replay_normal_attack` ne compose
qu'UNE attaque, et les trois tests de revive/resurrect capturent l'etat live puis SIMULENT la mort
offline. Il faut une sequence LIVE de bout en bout -- SUR-TUER, laisser le NATIF ramener l'unite,
RE-ATTAQUER -- et la rejouer INTEGRALEMENT cote port depuis l'etat d'AVANT la sur-tuerie : c'est la
seule facon de faire vivre l'accumulateur cote port, `engine/runner/snapshot.py` ne le transportant
PAS (il reconstruit `HealthComponent(hp, hp_max)`, donc `over_reduce = 0`).

LE REGIME EST STRUCTURELLEMENT ETROIT : `Reduce` n'accumule que ce qu'il n'a PAS pu retirer, donc
`over_reduce > 0` implique `hp == 0`, donc une unite MORTE. Le seul etat ou un porteur VIVANT a un
accumulateur non nul est « mort en sur-reduction PUIS retour a la vie ».

LE REGIME EST AUTO-VERIFIANT : le probe calcule AUSSI la cardinalite de l'HYPOTHESE ADVERSE (meme
port, meme etat live post-retour, mais `over_reduce` remis a la valeur OBSERVEE juste avant la purge
-- cf. `_EspionDePurge`) et REFUSE de conclure si elle egale celle du port nominal. Un regime ou les
deux hypotheses rendent la meme reponse ne prouve rien, et opposer le port a `0` deviendrait une
TAUTOLOGIE des lors que le port purge.

RESULTAT (2026-08-06, ce probe) : le RE offline de `#462-r4e-o-r2` etait FAUX sur (a). Le REVIVE
purge lui aussi, par un QUATRIEME ecrivain du zero que sa table avait manque --
`IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` `case 0`, atteint depuis
`ReviveUnitOperation$$SetHealth` via `IdunBattle.Entities.UnitExtensions$$ApplyStatModifier`.

Usage :
    python scripts/python/probe_462r4eor2r1_retour_a_la_vie_over_reduce.py
        [--volet revive|resurrect|tous] [--state-file <ABSOLU>] [--seeds 777,31337,...]
        [--mutate revive-purge|fillup-sans-purge|resurrect-flags-partiels]

ASCII only. Dispose ses runners.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "tests", "engine", "runner"))
import rl_collect_batch as R                                          # noqa: E402

from engine.runner.snapshot import load_state                         # noqa: E402
from engine.runner.runner import Runner                               # noqa: E402
from engine.runner.messages import AttackUnitMessage                  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                # noqa: E402
from engine.runner.components import (HealthComponent, UnitComponent,  # noqa: E402
                                      UnitFlagsComponent, PositionComponent)
from engine.entities.pathfinding.board import Board                   # noqa: E402

_SID = R._resolve_session()
_created = []

# ----------------------------------------------------------------- montages

BOARD = "MC1_67"

# (a) REVIVE -- `TaintedNarthecium` : `deathRotbone` revive un allie Chaos ADJACENT vaincu.
#     Victime `worldExecutions` : Chaos (BlessingsOfKhorne), et le SEUL des Chaos du pool dont les
#     traits n'ajoutent aucun etage au chemin de degat (pas de `Resilient` -> pas de
#     `denied_damage`, pas de `Terrifying`, pas de `ThrillSeekers`, pas de `FinalJustice`).
MONTAGE_REVIVE = {
    "p_units": "astraBullgryn,tauAunShi",
    "a_units": "deathRotbone,worldExecutions",
    "att1": "astraBullgryn",     # 4 coups Physical -- le SUR-TUEUR
    "att2": "tauAunShi",         # 5 coups Power    -- l'attaque qui MESURE
    "victime": "worldExecutions",
    "temoin": "deathRotbone",    # doit rester VIVANT et ADJACENT (porteur du passif)
}

# (b) RESURRECT -- trait `Ambush` : `genesPrimus` meurt, un `genesSmnDecoy` est pose sur sa tuile,
#     et `EnvAmbushResurrectAbility` le ressuscite au tour SUIVANT de son joueur (delta == 1).
MONTAGE_RESURRECT = {
    "p_units": "astraBullgryn,tauAunShi",
    "a_units": "genesPrimus,necroWarden",
    "att1": "astraBullgryn",
    "att2": "tauAunShi",
    "victime": "genesPrimus",
    "temoin": None,
}

# Le SUR-TUEUR frappe assez fort pour gaspiller un accumulateur enorme ; l'attaque qui MESURE frappe
# assez FAIBLE pour que, SANS accumulateur, aucun de ses coups n'atteigne le seuil d'overkill
# (`dmg >= 2 x PV`). Les deux conditions sont VERIFIEES a posteriori, pas supposees.
DMG_SURTUEUR = 60000
DMG_MESUREUR = 250

# ⚠ LA MARGE DU REGIME EST UNE MESURE, PAS UN CONFORT. Sans `--hp-victime`, le seuil d'overkill de
# l'attaque 2 vaut `2 x PV_apres_retour` (4887 revive-HP -> 9774) et le PLANCHER d'accumulateur
# qu'impose la sur-tuerie vaut `2 x PV_avant - PV_avant = PV_avant` (9537) : les deux sont a 2,5 %
# l'un de l'autre, donc un natif « 5 events » exclut `over_reduce >= 9561` mais NE SEPARE PAS
# « 0 » de « 9537 ». `--hp-victime N` ECRASE `Health`/`RemainingHealth` de la victime : le retour a
# la vie clampe alors a N (`Min(reviveHP, maxHP)`), le seuil tombe a `2N` et la marge s'ouvre.
# N = 2000 -> seuil 4000, plancher d'accumulateur ~59 800 : facteur 15.
HP_VICTIME_RESSERRE = 2000


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(method, body=None, timeout=60):
    return _unwrap(R._rpc(_SID, method, [body] if body is not None else [], timeout=timeout))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _build(state_file, seed, montage, hp_victime=None, cap_wait_s=900, poll_s=20):
    """Build d'un runner cale sur `BOARD`. ATTEND le cap MAX_RUNNERS / une fenetre DRAIN."""
    champs_vic = "Armor=0,FixedArmor=0,BlockChance=0"
    if hp_victime:
        champs_vic += f",Health={int(hp_victime)},RemainingHealth={int(hp_victime)}"
    extra = [
        "--roster", "1",
        "--p-units", montage["p_units"],
        "--a-units", montage["a_units"],
        "--unit-stat", f"{montage['att1']}:Damage={DMG_SURTUEUR},CritChance=0",
        "--unit-stat", f"{montage['att2']}:Damage={DMG_MESUREUR},CritChance=0",
        "--unit-stat", f"{montage['victime']}:{champs_vic}",
    ]
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", state_file, "--board", BOARD, *extra]
    waited = 0.0
    while True:
        try:
            os.unlink(state_file)
        except OSError:
            pass
        p = subprocess.run(args, cwd=_HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if os.path.exists(state_file):
            rid = json.loads(open(state_file).read())["runnerId"]
            _created.append(rid)
            return rid
        out = (p.stderr or p.stdout or "")
        if ("runner cap reached" not in out and "runner creation paused" not in out) \
                or waited >= cap_wait_s:
            raise RuntimeError(f"build KO: {out[-800:]}")
        print(f"  cap/drain, attente {poll_s}s ({waited:.0f}/{cap_wait_s})")
        time.sleep(poll_s)
        waited += poll_s


# ----------------------------------------------------------------- live helpers

def _dv(rid):
    return _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _unit(dv, vis=None, uid=None, alive=None):
    for u in (dv.get("units") or []):
        if vis is not None and u.get("visualId") != vis:
            continue
        if uid is not None and u.get("id") != uid:
            continue
        if alive is not None and bool(u.get("alive")) != alive:
            continue
        return u
    return None


def _move(rid, uid, col, row):
    return _rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 60)


def _endturn(rid):
    return _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def _normal_ability_id(dv, uid):
    u = _unit(dv, uid=uid)
    for ab in ((u or {}).get("abilities") or []):
        if ab.get("kind") == "normal":
            return ab.get("id")
    return None


def _attaque_live(rid, att, tgt, ability_id):
    """Joue l'attaque normale live et rend (per_hit, hp_apres_cible, res)."""
    res = _rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tgt, "abilityType": ability_id}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not (_ok(res) and a0.get("ok")):
        return None, None, res
    per_hit = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tgt and "Amount" in td \
                and td.get("Active_Ability_Type") == ability_id:
            per_hit.append(td.get("Amount"))
    hp = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tgt), None)
    return per_hit, hp, res


def _capture(rid, board):
    dv = _dv(rid)
    ob = _rpc("observeBattle", {"runnerId": rid}, 60)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None
    return {"dv": dv, "ob": ob, "snap": snap,
            "state": load_state(dv, ob, snap, board=board)}


def _seed_rng(state, s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    state.rng = rng


# ----------------------------------------------------------------- placement

def _occupees(board, dv):
    """Tuiles portant une unite VIVANTE. Une tuile occupee fait echouer le move EN SILENCE
    (`ok: True`, `mutated: False`) -- mesure du 2026-08-06, c'est ce qui rendait le placement muet."""
    out = set()
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        p = u.get("pos") or {}
        t = board.id_at(p.get("col"), p.get("row"))
        if t is not None:
            out.add(t)
    return out


def _cluster(board, besoin, occupees=frozenset()):
    """Rend (T, [voisins...]) : une tuile marchable LIBRE avec au moins `besoin` voisins marchables
    LIBRES eux aussi. Parcours TRIE par id -> deterministe."""
    for t in sorted(board.by_id):
        if not board.walkable(t) or t in occupees:
            continue
        nb = [n for n in sorted(board.neighbours(t))
              if board.walkable(n) and n not in occupees]
        if len(nb) >= besoin:
            return t, nb[:besoin]
    return None, None


def _placer(rid, board, plan):
    """`plan` = [(unitId, tile_id), ...]. DEPLACE (jamais « bloque par la geometrie de spawn »)."""
    rep = []
    for uid, tid in plan:
        col, row = board.coord(tid)
        rep.append((uid, tid, str(_move(rid, uid, col, row))[:160]))
    dv = _dv(rid)
    for uid, tid in plan:
        u = _unit(dv, uid=uid)
        p = (u or {}).get("pos") or {}
        if board.id_at(p.get("col"), p.get("row")) != tid:
            print("  [placer] ECHEC", uid, "voulu", tid, board.coord(tid),
                  "obtenu", p, "| reponses:", rep)
            return False, dv
    return True, dv


def _mon_tour(rid, mon_player, max_iter=8):
    for _ in range(max_iter):
        dv = _dv(rid)
        if dv.get("currentPlayer") == mon_player:
            return dv
        _endturn(rid)
    return None


# ----------------------------------------------------------------- port helpers

def _hc(state, uid):
    e = state.get_entity(uid)
    return e.get_component(HealthComponent) if e is not None else None


def _uc(state, uid):
    e = state.get_entity(uid)
    return e.get_component(UnitComponent) if e is not None else None


def _flags(state, uid):
    e = state.get_entity(uid)
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return sorted(fl.flags) if fl is not None else []


def _attaque_port(state, att, tgt):
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tgt))
    rr = runner.damage_handler.last
    return (rr or {}).get("per_hit")


class _EspionDePurge:
    """OBSERVE (ne mute pas) la valeur d'`over_reduce` juste AVANT chaque purge portee, sur les DEUX
    foyers : `HealthComponent.fill_up` (soin / reparation / RESURRECT) et
    `HealthComponent.apply_modifier_set_current` (REVIVE). Sert a construire l'hypothese ADVERSE --
    « l'accumulateur est TRANSPORTE au-dela du retour a la vie » -- sans laquelle le regime ne
    discrimine plus rien une fois le port corrige (la 1re redaction opposait le port a `0`, ce qui
    devient une TAUTOLOGIE des que le port purge)."""

    def __init__(self):
        self.max_avant_purge = 0
        self._orig = {}

    def __enter__(self):
        espion = self

        for nom in ("fill_up", "apply_modifier_set_current"):
            orig = getattr(HealthComponent, nom)
            self._orig[nom] = orig

            def _fait(self_hc, *a, _orig=orig, **kw):
                espion.max_avant_purge = max(espion.max_avant_purge,
                                             int(getattr(self_hc, "over_reduce", 0) or 0))
                return _orig(self_hc, *a, **kw)
            setattr(HealthComponent, nom, _fait)
        return self

    def __exit__(self, *exc):
        for nom, orig in self._orig.items():
            setattr(HealthComponent, nom, orig)
        return False


# ----------------------------------------------------------------- mutations

def _mutation(nom):
    """Contre-epreuves. Chacune DOIT faire diverger le volet qu'elle vise ; `a_mordu` est mesure
    SEPAREMENT du verdict (une mutation NON EXERCEE se declare, elle ne compte pas verte)."""
    if nom == "fillup-sans-purge":
        # FOYER : `HealthComponent.fill_up` sans sa queue `this[0x24] = 0`. Vise le volet (b).
        def _fill_up(self, amount):
            if self.hp is None or self.hp_max is None:
                return 0
            filled = min(int(amount), int(self.hp_max) - int(self.hp))
            self.hp = int(self.hp) + filled
            return filled                                     # <- purge RETIREE
        HealthComponent.fill_up = _fill_up
        return "HealthComponent.fill_up ne purge plus `over_reduce` (queue de FillUp retiree)"
    if nom == "revive-purge":
        # Vise le volet (a) : le revive PURGERAIT (le « correctif » que le quirk natif interdit).
        from engine.runner.operations import revive as _rev
        _orig = _rev.ReviveUnitOperation.execute

        def _exec(state, unit_id):
            out = _orig(state, unit_id)
            hc = _hc(state, unit_id)
            if hc is not None:
                hc.over_reduce = 0                            # <- purge AJOUTEE
            return out
        _rev.ReviveUnitOperation.execute = staticmethod(_exec)
        return "ReviveUnitOperation purge `over_reduce` (le quirk natif serait « corrige »)"
    if nom == "resurrect-flags-partiels":
        # Vise le volet (b) : la rafale de flags AVANT #462-r4e-o-r2-r1 (seul `Remove(0x1a)`).
        from engine.runner.operations import resurrect as _res
        _res.update_flags_on_resurrect = lambda fl: fl.remove(UnitFlagsComponent.REMOVED)
        return ("ResurrectUnitOperation ne retire plus que `Remove(0x1a)` "
                "(rafale d'avant #462-r4e-o-r2-r1)")
    raise SystemExit(f"mutation inconnue: {nom}")


# ----------------------------------------------------------------- volet (a)

def _volet_revive(state_file, seed, hp_victime=None):
    """SUR-TUER un allie Chaos adjacent a `deathRotbone` -> REVIVE natif -> RE-ATTAQUER."""
    m = MONTAGE_REVIVE
    rid = _build(state_file, seed, m, hp_victime=hp_victime)
    bg = _rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"ok": False, "raison": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = _dv(rid)
    if not _ok(dv):
        return {"ok": False, "raison": "decisionView KO"}
    ids = {k: (_unit(dv, vis=m[k]) or {}).get("id")
           for k in ("att1", "att2", "victime", "temoin")}
    if any(v is None for v in ids.values()):
        return {"ok": False, "raison": f"roster incomplet: {ids}"}
    mon_player = _unit(dv, uid=ids["att1"]).get("owner")

    T, nb = _cluster(board, 3, _occupees(board, dv))
    if T is None:
        return {"ok": False, "raison": "aucune tuile a 3 voisins marchables"}
    place_ok, dv = _placer(rid, board, [(ids["victime"], T), (ids["temoin"], nb[0]),
                                        (ids["att1"], nb[1]), (ids["att2"], nb[2])])
    if not place_ok:
        return {"ok": False, "raison": "placement refuse (tuiles occupees ?)"}
    dv = _mon_tour(rid, mon_player)
    if dv is None:
        return {"ok": False, "raison": "tour du joueur non atteint"}
    return _sequence(rid, board, ids, mon_player, avance_de_tour=False)


# ----------------------------------------------------------------- volet (b)

def _volet_resurrect(state_file, seed, hp_victime=None):
    """SUR-TUER un porteur `Ambush` -> decoy -> RESURRECT natif au tour SUIVANT -> RE-ATTAQUER."""
    m = MONTAGE_RESURRECT
    rid = _build(state_file, seed, m, hp_victime=hp_victime)
    bg = _rpc("boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"ok": False, "raison": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = _dv(rid)
    if not _ok(dv):
        return {"ok": False, "raison": "decisionView KO"}
    ids = {k: (_unit(dv, vis=m[k]) or {}).get("id") for k in ("att1", "att2", "victime")}
    if any(v is None for v in ids.values()):
        return {"ok": False, "raison": f"roster incomplet: {ids}"}
    ids["temoin"] = None
    mon_player = _unit(dv, uid=ids["att1"]).get("owner")

    T, nb = _cluster(board, 3, _occupees(board, dv))
    if T is None:
        return {"ok": False, "raison": "aucune tuile a 3 voisins marchables"}
    # La victime au CENTRE : le decoy prend SA tuile, donc les deux attaquants restent adjacents
    # a l'unite ressuscitee (qui reapparait sur la tuile du decoy).
    place_ok, dv = _placer(rid, board, [(ids["victime"], T),
                                        (ids["att1"], nb[0]), (ids["att2"], nb[1])])
    if not place_ok:
        return {"ok": False, "raison": "placement refuse (tuiles occupees ?)"}
    dv = _mon_tour(rid, mon_player)
    if dv is None:
        return {"ok": False, "raison": "tour du joueur non atteint"}
    return _sequence(rid, board, ids, mon_player, avance_de_tour=True)


# ----------------------------------------------------------------- sequence commune

def _sequence(rid, board, ids, mon_player, *, avance_de_tour):
    """LIVE et PORT jouent la MEME sequence. `avance_de_tour` = le retour a la vie n'a lieu qu'au
    tour SUIVANT du joueur de la victime (volet RESURRECT) au lieu de la mort meme (volet REVIVE)."""
    att1, att2, vic = ids["att1"], ids["att2"], ids["victime"]

    cap0 = _capture(rid, board)
    if cap0 is None:
        return {"ok": False, "raison": "capture S0 KO"}
    st = cap0["state"]
    rng0 = _rpc("dumpRng", {"runnerId": rid}, 40)
    if not _ok(rng0):
        return {"ok": False, "raison": "dumpRng S0 KO"}
    _seed_rng(st, rng0)
    hc = _hc(st, vic)
    if hc is None or hc.hp is None:
        return {"ok": False, "raison": "victime sans HealthComponent offline"}
    hp0, hpmax = int(hc.hp), int(hc.hp_max)

    ab1 = _normal_ability_id(cap0["dv"], att1)
    if ab1 is None:
        return {"ok": False, "raison": "att1 sans attaque normale"}

    # --- ATTAQUE 1 : la SUR-TUERIE ---------------------------------------------------
    ph1_live, hp1_live, res1 = _attaque_live(rid, att1, vic, ab1)
    if ph1_live is None:
        return {"ok": False, "raison": f"attaque 1 live KO: {str(res1)[:200]}"}
    espion = _EspionDePurge()
    with espion:                      # couvre l'attaque 1 ET le retour a la vie PORTE
        ph1_port = _attaque_port(st, att1, vic)

        # --- RETOUR A LA VIE ---------------------------------------------------------
        if avance_de_tour:
            # LIVE : fin de mon tour -> le tour du joueur de la victime demarre -> `On(TurnStart)`.
            _endturn(rid)
            dv_adv = _dv(rid)
            joueur_vic = (_unit(dv_adv, uid=vic) or {}).get("owner")
            _endturn(rid)
            _mon_tour(rid, mon_player)
            # PORT : mirror de `StartTurnOperation` (cf. `test_ambush_migration_live`) -- le
            # compteur de tours du joueur de la victime avance de 1, puis `On(TurnStart = 22)`.
            from engine.runner.operations.triggers import start_turn_triggers
            e_vic = st.get_entity(vic)
            from engine.runner.components import OwnerComponent
            oc = e_vic.get_component(OwnerComponent) if e_vic is not None else None
            pj = oc.player if oc is not None else joueur_vic
            st.turn_counts[pj] = st.turn_counts.get(pj, 0) + 1
            start_turn_triggers(st, pj)

    cap1 = _capture(rid, board)
    if cap1 is None:
        return {"ok": False, "raison": "capture S1 KO"}
    u_vic = _unit(cap1["dv"], uid=vic)
    vivante_live = bool((u_vic or {}).get("alive"))
    hp1b_live = next((h for h in [_hp_live(cap1["ob"], vic)] if True), None)
    uc = _uc(st, vic)
    vivante_port = bool(uc.alive) if uc is not None else None
    hp_port = int(_hc(st, vic).hp) if _hc(st, vic) is not None else None
    over_port = int(_hc(st, vic).over_reduce) if _hc(st, vic) is not None else None
    flags_port = _flags(st, vic)
    flags_live = _flags_live(cap1["snap"], vic)

    base = {"ok": True, "hp0": hp0, "hp_max": hpmax,
            "ph1_live": ph1_live, "ph1_port": ph1_port,
            "vivante_live": vivante_live, "vivante_port": vivante_port,
            "hp_apres_retour_live": hp1b_live, "hp_apres_retour_port": hp_port,
            "over_reduce_port": over_port,
            "flags_port": flags_port, "flags_live": flags_live}
    if not vivante_live:
        base.update({"ok": False, "raison": "PAS de retour a la vie LIVE (tirage 75 % ? gate ?)"})
        return base

    # --- ATTAQUE 2 : celle qui MESURE ------------------------------------------------
    ab2 = _normal_ability_id(cap1["dv"], att2)
    if ab2 is None:
        base.update({"ok": False, "raison": "att2 sans attaque normale"})
        return base
    rng1 = _rpc("dumpRng", {"runnerId": rid}, 40)
    if not _ok(rng1):
        base.update({"ok": False, "raison": "dumpRng S1 KO"})
        return base
    # Le MT est RE-CALE ici : une eventuelle desynchro de tirages a l'etape 1 ne doit pas polluer
    # la mesure de l'etape 2 (on mesure la CARDINALITE, pas le bit-exact de l'attaque 1).
    _seed_rng(st, rng1)

    # HYPOTHESE ADVERSE (« l'accumulateur est TRANSPORTE au-dela du retour a la vie ») : le MEME
    # port, sur le MEME etat live post-retour, mais avec `over_reduce` REMIS a la valeur qu'il avait
    # juste AVANT la purge -- valeur OBSERVEE (pas supposee) par `_EspionDePurge` pendant le rejeu
    # de l'attaque 1. C'est elle, et non `0`, qui doit servir de contrefactuel : opposer le port a
    # `0` devient une TAUTOLOGIE des que le port purge.
    st_alt = _clone_hypothese(cap1, board, rng1, vic, espion.max_avant_purge)
    ph2_alt = _attaque_port(st_alt, att2, vic) if st_alt is not None else None

    ph2_live, hp2_live, res2 = _attaque_live(rid, att2, vic, ab2)
    if ph2_live is None:
        base.update({"ok": False, "raison": f"attaque 2 live KO: {str(res2)[:200]}"})
        return base
    ph2_port = _attaque_port(st, att2, vic)
    hp2_port = int(_hc(st, vic).hp) if _hc(st, vic) is not None else None

    base.update({"ph2_live": ph2_live, "ph2_port": ph2_port, "ph2_hypothese_transport": ph2_alt,
                 "over_reduce_avant_purge": espion.max_avant_purge,
                 "hp_final_live": hp2_live, "hp_final_port": hp2_port})
    return base


def _clone_hypothese(cap1, board, rng1, vic, over_reduce):
    """Recharge l'etat LIVE post-retour-a-la-vie (`load_state` ne transporte PAS `+0x24`, donc
    `over_reduce = 0`), y REPOSE la valeur `over_reduce` demandee et cale le meme MT."""
    st = load_state(cap1["dv"], cap1["ob"], cap1["snap"], board=board)
    hc = _hc(st, vic)
    if hc is None:
        return None
    hc.over_reduce = int(over_reduce or 0)
    _seed_rng(st, rng1)
    return st


def _hp_live(ob, uid):
    for u in (ob.get("units") or []):
        if (u.get("squadId") or u.get("id")) == uid:
            return u.get("hp")
    return None


def _flags_live(snap, uid):
    for u in (snap.get("units") or []) + (snap.get("unitsNotAlive") or []):
        if u.get("entityId") == uid:
            return sorted(u.get("unitFlags") or [])
    return None


# ----------------------------------------------------------------- verdict

def _verdict(volet, r, mutate):
    """Rend (ok, ligne).

    LE DISCRIMINANT OPPOSE LES DEUX HYPOTHESES ENTRE ELLES, JAMAIS L'UNE AU NATIF. Le regime ne vaut
    que si `port` (le port tel qu'il est) et `hypothese_transport` (le MEME port avec `over_reduce`
    remis a sa valeur d'avant la purge) rendent des reponses DIFFERENTES.
    DEUX redactions fautives ont ete corrigees par la mesure, et elles sont symetriques :
      * comparer l'hypothese au NATIF declarait « non discriminant » le cas ou le natif s'ALIGNE sur
        elle -- c'est-a-dire exactement le resultat cherche ;
      * opposer le port a `over_reduce = 0` devient une TAUTOLOGIE des que le port purge (les deux
        branches deviennent le meme calcul) -- le probe se serait tu apres le correctif.

    Le VERDICT, lui, est l'accord `port == live`. Sous mutation il s'INVERSE (la mutation doit
    MORDRE), et `a_mordu` est rapporte separement."""
    if not r.get("ok"):
        return None, f"NON CONCLUANT -- {r.get('raison')}"
    live, port, cf = r["ph2_live"], r["ph2_port"], r.get("ph2_hypothese_transport")
    if cf is None:
        return None, "NON CONCLUANT -- hypothese adverse non calculee"
    if not r.get("over_reduce_avant_purge"):
        return None, ("REGIME VACU : `over_reduce` observe AVANT le retour a la vie vaut 0 -- "
                      "la sur-tuerie n'a rien gaspille, les deux hypotheses coincident")
    if cf == port:
        return None, (f"REGIME NON DISCRIMINANT : les deux hypotheses rendent la MEME reponse "
                      f"(port={port} == transport={cf}, over_reduce avant purge = "
                      f"{r.get('over_reduce_avant_purge')}) -- resserrer par --hp-victime")
    diag = (f"live={live} port={port} hypothese_transport(over_reduce="
            f"{r.get('over_reduce_avant_purge')})={cf}")
    # Ce que DIT le natif : sur quelle des deux hypotheses il tombe.
    if live == port and live != cf:
        sens = "le NATIF s'aligne sur le PORT"
    elif live == cf:
        sens = "le NATIF s'aligne sur `over_reduce TRANSPORTE` (le port purge a tort)"
    else:
        sens = "le NATIF ne s'aligne sur AUCUNE des deux hypotheses"
    accord = (port == live)
    if mutate is None:
        return accord, (("OK -- " if accord else "DIVERGENCE DU PORT -- ") + diag + " ; " + sens)
    if accord:
        return False, f"IDENTIQUE SOUS MUTATION -- la mutation n'a PAS mordu : {diag}"
    return True, f"DIVERGE (attendu sous mutation) : {diag}"


def _dump(volet, r):
    print(f"\n[{volet}]")
    if not r.get("ok") and "hp0" not in r:
        print("  KO:", r.get("raison"))
        return
    print(f"  PV cible au depart      : {r.get('hp0')} / max {r.get('hp_max')}")
    print(f"  attaque 1 (sur-tuerie)  : live={r.get('ph1_live')} port={r.get('ph1_port')}")
    print(f"  retour a la vie         : live_alive={r.get('vivante_live')} "
          f"port_alive={r.get('vivante_port')} "
          f"hp live={r.get('hp_apres_retour_live')} port={r.get('hp_apres_retour_port')}")
    print(f"  over_reduce PORTE       : {r.get('over_reduce_port')}")
    print(f"  flags cible             : live={r.get('flags_live')} port={r.get('flags_port')}")
    if "ph2_live" in r:
        print(f"  attaque 2 (LA MESURE)   : live={r.get('ph2_live')} "
              f"(cardinalite {len(r.get('ph2_live') or [])})")
        print(f"                            port={r.get('ph2_port')} "
              f"(cardinalite {len(r.get('ph2_port') or [])})")
        print(f"                            hypothese_transport={r.get('ph2_hypothese_transport')}")
        print(f"  PV final                : live={r.get('hp_final_live')} port={r.get('hp_final_port')}")
    if not r.get("ok"):
        print("  KO:", r.get("raison"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=["revive", "resurrect", "tous"], default="tous")
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU du state-file de build (defaut : logs/runners/<uuid>)")
    ap.add_argument("--seeds", default="777,31337,4242,90210,1234",
                    help="seeds essayes tant que le retour a la vie NATIF n'a pas eu lieu "
                         "(le revive TaintedNarthecium est un tirage a 75 %%)")
    ap.add_argument("--mutate", default=None,
                    choices=["revive-purge", "fillup-sans-purge", "resurrect-flags-partiels"])
    ap.add_argument("--hp-victime", type=int, default=HP_VICTIME_RESSERRE,
                    help="ECRASE Health/RemainingHealth de la victime -> le retour a la vie clampe "
                         "a cette valeur et le seuil d'overkill de l'attaque 2 tombe a 2 x N. "
                         "0 = PV natifs (marge etroite, cf. HP_VICTIME_RESSERRE)")
    a = ap.parse_args()

    state_file = a.state_file or os.path.abspath(os.path.join(
        _HERE, "..", "..", "logs", "runners",
        f"_probe462r4eor2r1_{uuid.uuid4().hex[:8]}_state.json"))
    os.makedirs(os.path.dirname(state_file), exist_ok=True)

    if a.mutate:
        print("MUTATION:", _mutation(a.mutate))

    w = _unwrap(R._rpc(_SID, "warmupGameSingletons", [{}], timeout=240))
    print("warmup ok=", isinstance(w, dict) and w.get("ok"),
          (w or {}).get("skipped") or "")

    seeds = [s.strip() for s in a.seeds.split(",") if s.strip()]
    volets = ["revive", "resurrect"] if a.volet == "tous" else [a.volet]
    resultats = {}
    try:
        for volet in volets:
            fn = _volet_revive if volet == "revive" else _volet_resurrect
            r = None
            for seed in seeds:
                r = fn(state_file, seed, hp_victime=(a.hp_victime or None))
                _dump(f"{volet} seed={seed}", r)
                if r.get("ok") or "PAS de retour a la vie" not in str(r.get("raison")):
                    break
                print("  -> pas de retour a la vie, seed suivant")
            resultats[volet] = r
    finally:
        for rid in list(_created):
            try:
                _rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception:
                pass

    print("\n--- VERDICT ---")
    bad = 0
    for volet, r in resultats.items():
        ok, ligne = _verdict(volet, r or {"ok": False, "raison": "non joue"}, a.mutate)
        print(f"  {volet}: {ligne}")
        if ok is not True:
            bad += 1
    print(f"VERDICT: {'PASS' if bad == 0 else 'FAIL'} ({bad} anomalie(s))")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
