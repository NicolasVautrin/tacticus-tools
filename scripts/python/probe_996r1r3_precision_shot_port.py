"""#996-r1-r3 -- `1015 PrecisionShot` + `1012 PrecisionShot_Aim` : CONFRONTATION du port.

Le residu annoncait un couple INDIVISIBLE : la regle dynamique de caster de 1015 ne se pose que
sur la CLASSE, donc l'inscrire a `ABILITY_CLASSES` arme aussi son `execute_behaviour`, qui
dispatche `1012` -- un `activeAbilityType` NON-NORMAL, chemin que la feuille `UseActiveAbility`
n'avait pas.

Ce probe MESURE, volet par volet :

  [A] REACHABILITY -- le kit ACTIF que la bataille monte, et `abilityReason` des trois soeurs
      AVANT toute visee (re-mesure de `probe_996r1_precision_shot.py`, pour partir d'un fait et
      non d'une citation).
  [B] GATE -- le port rend-il la MEME raison que l'oracle natif pour 1015 / 1012 / 1013 ? C'est le
      trou PERMISSIF que la tranche ferme (avant : le port rendait 0 la ou le natif rend 0x2).
  [C] VISEE -- cast LIVE de 1012, puis REJEU OFFLINE du meme cast depuis l'etat capture :
      l'effet `1015 EffectType.PrecisionShot_Aim` est-il pose des DEUX cotes, avec la meme duree,
      et la charge de `1015 ActiveAbilityType.PrecisionShot` est-elle consommee des DEUX cotes ?
  [D] DISPATCH -- au tour suivant (le caster PORTE l'effet), `abilityReason` des trois, puis cast
      LIVE de 1015 et rejeu OFFLINE : le sous-cast 1012 traverse-t-il ses propres gates, et le
      port dit-il la MEME chose que le natif ?

Usage : python probe_996r1r3_precision_shot_port.py --state-file <ABSOLU propre>
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType

PYDIR = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:8765"

PORTEUR_VIS = "necroNpc3Deathmark"
PORTEUR = PORTEUR_VIS + ":45"
ALLIE = "ultraTitus"
ENNEMIS = ("eldarRanger", "astraBullgryn", "darkaCompanion")
BOARD = "MC1_67"
SEED = "999"

AIM_ID = int(ActiveAbilityType.PrecisionShot_Aim)          # 1012
ATTACK_ID = int(ActiveAbilityType.PrecisionShot_Attack)    # 1013
SHOT_ID = int(ActiveAbilityType.PrecisionShot)             # 1015
AIM_EFFECT = int(EffectType.PrecisionShot_Aim)             # 1015 (EffectType, homonyme)


def _sid():
    return requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post("%s/api/scripts/%s/rpc" % (HOST, sid),
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(sid, state_file: str) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
           "--state-file", state_file, "--explicit-stats", PORTEUR,
           "--p-units", "%s,%s" % (PORTEUR, ALLIE), "--a-units", ",".join(ENNEMIS),
           "--hp-target", "400000", "--hp-player", "400000"]
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0 or not Path(state_file).exists():
        raise RuntimeError("build KO rc=%d : %s" % (p.returncode, (p.stderr or p.stdout)[-1500:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def _hexi(h):
    try:
        return int(str(h), 16) if h else 0
    except ValueError:
        return 0


class H:
    """Pilotage minimal du runner (meme forme que `probe_1012_dw02_burst_cannon.py`)."""

    def __init__(self, sid, rid):
        self.sid, self.rid, self.mine = sid, rid, None

    def rpc(self, m, b=None, t=180):
        return _rpc(self.sid, m, b, t)

    def dview(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "maxRank": 1,
                                         "allAbilities": True}, 150)

    def capture(self):
        """Le triplet que `load_state` exige, + le RNG (pris JUSTE avant un cast)."""
        from engine.entities.pathfinding.board import Board
        bg = self.rpc("boardGraph", {"runnerId": self.rid}, 60)
        return {"dv": self.dview(),
                "ob": self.rpc("observeBattle", {"runnerId": self.rid}, 60),
                "snap": self.rpc("combatSnapshot", {"runnerId": self.rid}, 90),
                "board": Board(bg["tiles"], adjacency="native_sym"),
                "rng": self.rpc("dumpRng", {"runnerId": self.rid}, 30)}

    def by_visual(self, vis, dv=None):
        dv = dv if dv is not None else self.dview()
        return next((u for u in (dv.get("units") or [])
                     if u.get("alive") and u.get("visualId") == vis), None)

    def reason(self, caster, target, ability):
        r = self.rpc("abilityReason", {"runnerId": self.rid, "casterId": int(caster),
                                       "abilityType": int(ability),
                                       "targetId": int(target)}, 60) or {}
        return (_hexi((r.get("casterReason") or {}).get("hex")),
                _hexi((r.get("targetReason") or {}).get("hex")), r)

    def cast(self, caster, target, ability):
        r = self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": int(ability)}}, 240)
        return (r.get("actions") or [{}])[0] or {}, r

    def endturn(self):
        self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 60)

    def my_turn(self, max_end=12):
        for _ in range(max_end):
            dv = self.dview()
            if dv.get("currentPlayer") == self.mine:
                return dv
            self.endturn()
        return None

    def effects_of(self, uid, dv=None):
        """Les effets de l'unite tels que `decisionView` les publie (ACTIF-ONLY, GROUND TRUTH)."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if int(u.get("id", -1)) == int(uid):
                return [(e.get("type"), e.get("name"), e.get("remaining"))
                        for e in (u.get("effects") or [])]
        return []

    def ability_usable(self, uid, ability, dv=None):
        """`ActiveAbility.CanStillBeUsed@0x28` = le champ que le canal nomme `usable`. TRI-ETAT :
        `None` = l'entree n'est pas publiee (jamais un `False` fabrique)."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if int(u.get("id", -1)) != int(uid):
                continue
            for a in (u.get("abilities") or []):
                if int(a.get("id", -1)) == int(ability):
                    return a.get("usable")
        return None

    def dispose(self):
        try:
            self.rpc("disposeRunner", {"runnerId": int(self.rid)}, 60)
        except Exception:
            pass


# ------------------------------------------------------------------ rejeu OFFLINE du meme cast --

def _offline(cap, caster_id, target_id, ability):
    """Rejoue le cast dans le PORT depuis l'etat capture (meme MT), et rend
    `(diag, effets_du_caster, usable_1015)`."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.components import ActiveAbilitiesComponent
    from tests.engine.runner._ringed_cast import seed_rng
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=cap["board"])
    st.rng = seed_rng(cap["rng"])
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=int(ability)))
    diag = runner.ability_handler.last or {}
    # ⚠ `EffectsState.by_unit` GARDE les entrees CONSOMMEES / EXPIREES / DESACTIVEES : le lire brut
    # comparerait une liste ACTIF-ONLY (le canal natif `decisionView.effects`, GROUND TRUTH #100) a
    # une liste qui n'a rien oublie. Mesure du 2026-08-14 sur ce probe : l'effet TIERS
    # `InspiredToGreatness_OverrideLevel` (1180) -- que le port RETIRE bien, sur `On(0xc) &
    # OwnerIsCaster` (registre `ITG_OVERRIDE_LEVEL`) -- restait dans `by_unit` et se lisait comme un
    # DESACCORD sur un accord parfait. On passe donc par `active_effects`, l'accesseur ACTIF-ONLY.
    eff = []
    rows = st.effects.active_effects(int(caster_id)) if getattr(st, "effects", None) else []
    for e in rows:
        eff.append((getattr(e, "effect_type", None), getattr(e, "name", None),
                    getattr(e, "remaining_turns", None)))
    ent = st.get_entity(int(caster_id))
    comp = ent.get_component(ActiveAbilitiesComponent) if ent is not None else None
    entry = comp.get(SHOT_ID) if comp is not None else None
    usable = None if entry is None else bool(entry.can_still_be_used)
    return diag, eff, usable


def _port_reason(cap, caster_id, target_id, ability):
    """Le verdict du port au MEME rang que l'oracle natif : `is_invalid_target` (volet CASTER
    inclus), tel que `ActiveAbilityOperation$$ExecuteInternal` l'applique."""
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import is_invalid_target
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=cap["board"])
    klass = ABILITY_CLASSES.get(int(ability))
    return int(is_invalid_target(st, int(caster_id), int(target_id),
                                 klass() if klass is not None else None) or 0)


def _volet_gate(h, cap, cid, tag) -> int:
    """Confronte l'oracle natif `abilityReason` au verdict du port, pour les TROIS soeurs.

    ⚠ DEUX FONCTIONS NATIVES DIFFERENTES, et il faut le dire (#287-r6) : le RPC passe par
    `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`, qui place DEUX etages EN AMONT
    de la cascade (disponibilite de l'ability, `IsDamagedMachine`), tous deux rendant
    `TargetingRule.ValidRequest` (0x1). Le port, lui, mirror
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`, qui n'a AUCUN de ces etages.
    Confronter les deux quand l'etage amont MORD compare deux choses differentes -> le cran est
    `oracle_targeting.oracle_court_circuite`, et le couple sort NON MESURE, jamais DESACCORD.

    `1013 PrecisionShot_Attack` n'est PAS au registre (residu de la tranche) : son verdict de port
    est `0` par construction (`is_invalid_target(ability=None)`), ce qui est le trou PERMISSIF
    documente -- il est IMPRIME mais ne compte pas comme desaccord de ce port."""
    import oracle_targeting as O
    rc = 0
    for name, aid, porte in (("1015 PrecisionShot", SHOT_ID, True),
                             ("1012 Aim", AIM_ID, True),
                             ("1013 Attack", ATTACK_ID, False)):
        cr, tr, rep = h.reason(cid, cid, aid)
        pr = _port_reason(cap, cid, cid, aid)
        if O.oracle_court_circuite(rep):
            print("[%s] %-18s natif casterReason=%s (ORACLE COURT-CIRCUITE, cause=%s) | port=%s"
                  "  NON MESURE" % (tag, name, hex(cr), O.cause_du_court_circuit(rep), hex(pr)))
            continue
        ok = (cr == pr)
        print("[%s] %-18s natif casterReason=%s targetReason=%s | port=%s  %s%s"
              % (tag, name, hex(cr), hex(tr), hex(pr),
                 "ACCORD" if ok else "DESACCORD", "" if porte else "  (1013 NON PORTEE -- attendu)"))
        if not ok and porte:
            rc = 1
    return rc


# ------------------------------------------------------------------------------------- volets --

def volet_e(sid, state_file) -> int:
    """[E] LA FACE EXECUTION DE 1015, ATTEINTE POUR DE VRAI -- scenario CRAFTE.

    Les volets [A]-[D] etablissent que 1015 n'est jamais exécutable dans son regime NATUREL : hors
    visee sa regle dynamique la refuse, et le seul cast qui pose la visee (`1012`) CONSOMME sa
    charge dans le meme arbre (`SetActiveAbilityUsed(Owner, 1015)`). Sa `ExecuteBehaviour` -- donc
    tout le dispatch que cette tranche porte -- resterait NON CONFRONTEE.

    Le levier existe, et il est dans le jeu : `1204 InspiredToGreatness` (`tauAunShi`, DANS le pool)
    porte `ResetActiveAbility`, qui re-arme les charges (`CanStillBeUsed = true`) SANS toucher aux
    effets. On monte donc : Deathmark vise (1012) -> Aun'Shi le RESET -> tour suivant, 1015 est en
    visee ET rechargee -> son `ExecuteBehaviour` est ATTEINT.

    Ce que ca CONFRONTE : le natif exécute alors l'arbre de 1015, dont le sous-cast 1012 est refuse
    par SA propre regle dynamique. Le port doit dire la MEME chose -- `actionConsumed` egal, et
    aucun effet neuf des deux cotes."""
    from engine.entities.active_ability_type import ActiveAbilityType as AAT
    INSPIRE = int(AAT.InspiredToGreatness)                        # 1204
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
           "--state-file", state_file, "--explicit-stats", PORTEUR,
           "--p-units", "%s,%s" % (PORTEUR, "tauAunShi"), "--a-units", ",".join(ENNEMIS),
           "--hp-target", "400000", "--hp-player", "400000"]
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0 or not Path(state_file).exists():
        print("[E] MONTAGE : build KO rc=%d : %s" % (p.returncode, (p.stderr or p.stdout)[-600:]))
        return 2
    rid = int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])
    h = H(sid, rid)
    rc = 0
    try:
        dv = h.dview()
        dm = h.by_visual(PORTEUR_VIS, dv)
        aun = h.by_visual("tauAunShi", dv)
        if dm is None or aun is None:
            print("[E] MONTAGE : deathmark=%r aunshi=%r -- volet NON MESURE"
                  % (dm is not None, aun is not None))
            return 2
        cid, aid = int(dm["id"]), int(aun["id"])
        h.mine = dm.get("owner")
        a0, _ = h.cast(cid, cid, AIM_ID)
        print("[E] visee 1012 -> actionConsumed=%r ; usable(1015)=%r"
              % (a0.get("actionConsumed"), h.ability_usable(cid, SHOT_ID)))
        cr, tr, rep = h.reason(aid, cid, INSPIRE)
        print("[E] abilityReason 1204 (AunShi -> Deathmark) casterReason=%s targetReason=%s"
              % (hex(cr), hex(tr)))
        a1, _ = h.cast(aid, cid, INSPIRE)
        print("[E] reset 1204 -> ok=%r actionConsumed=%r ; usable(1015)=%r usable(1012)=%r"
              % (a1.get("ok"), a1.get("actionConsumed"), h.ability_usable(cid, SHOT_ID),
                 h.ability_usable(cid, AIM_ID)))
        if h.ability_usable(cid, SHOT_ID) is not True:
            print("[E] MONTAGE : la charge de 1015 n'est PAS re-armee -- le regime vise n'est pas "
                  "atteint, volet NON MESURE (jamais rabattu sur un vert)")
            return 2
        dvt = h.my_turn()
        if dvt is None:
            print("[E] MONTAGE : tour du caster inatteignable -- volet NON MESURE")
            return 2
        cap = h.capture()
        print("[E] effets au tour suivant : %r" % (h.effects_of(cid, cap["dv"]),))
        print("[E] usable(1015)=%r usable(1012)=%r"
              % (h.ability_usable(cid, SHOT_ID, cap["dv"]),
                 h.ability_usable(cid, AIM_ID, cap["dv"])))
        rc = max(rc, _volet_gate(h, cap, cid, "E"))
        eff_av = sorted(n for _t, n, _r in h.effects_of(cid, cap["dv"]) if n)
        a2, _ = h.cast(cid, cid, SHOT_ID)
        dv2 = h.dview()
        eff_ap = sorted(n for _t, n, _r in h.effects_of(cid, dv2) if n)
        print("[E] applyAction 1015 (EN VISEE + RECHARGEE) -> ok=%r actionConsumed=%r n_changes=%s"
              % (a2.get("ok"), a2.get("actionConsumed"), len(a2.get("changes") or [])))
        print("[E] natif effets avant=%r apres=%r usable(1015)=%r"
              % (eff_av, eff_ap, h.ability_usable(cid, SHOT_ID, dv2)))
        diag, eff_port, us_port = _offline(cap, cid, cid, SHOT_ID)
        port_names = sorted(n for _t, n, _r in eff_port if n)
        print("[E] port  ported=%r effets apres=%r usable(1015)=%r"
              % (diag.get("ported"), port_names, us_port))
        print("[E] port  diag : %s" % json.dumps(diag, default=str)[:600])
        if eff_ap != port_names:
            print("[E] DESACCORD effets natif=%r port=%r" % (eff_ap, port_names))
            rc = 1
        us_nat = h.ability_usable(cid, SHOT_ID, dv2)
        if us_nat != us_port:
            # ECART NOMME, HORS PERIMETRE ET PRE-EXISTANT : `ActiveAbilityOperation$$ExecuteInternal`
            # REECRIT l'entree d'ability du caster a chaque cast qui aboutit -- compteurs `+0x10` /
            # `+0x14` incrementes, `+0x18`/`+0x20` = tour courant, `+0x2c` (cooldown) et
            # `CanStillBeUsed@0x28` reecrits depuis un appel d'interface. Le port ne porte AUCUNE de
            # ces ecritures (`add_flags_after_ability_execution` ne pose que le FLAG D'UNITE
            # `ActiveAbilityUsed`, ce qui est le mirror exact d'`AddFlagsAfterAbilityExecution`).
            # L'ecart vaut donc pour TOUTE ability du registre, pas pour 1015 -> residu.
            # ⚠ Et il n'y a AUCUN gate de disponibilite dans `ExecuteInternal` : `CanCurrentlyBeUsed`,
            # `HasUnusedAbility` et `CanStillBeUsed` y ont 0 occurrence (relecture integrale du
            # decompile). Le refus mesure au volet [D] vient d'un etage AMONT du visiteur.
            print("[E] ECART NOMME (hors perimetre, pre-existant) usable(1015) natif=%r port=%r : "
                  "`ExecuteInternal` reecrit l'entree d'ability a chaque cast, le port ne le fait "
                  "pas" % (us_nat, us_port))
        sub = ((diag.get("dispatched") or [{}])[0] or {}).get("sub_cast") or {}
        print("[E] sous-cast 1012 cote port : ported=%r invalid_target=%r"
              % (sub.get("ported"), sub.get("invalid_target")))
        if not sub.get("invalid_target"):
            print("[E] DESACCORD : le port a laisse passer le sous-cast 1012 alors que sa regle "
                  "dynamique le REFUSE en visee")
            rc = 1
    finally:
        h.dispose()
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--volet", default="abcd", choices=("abcd", "e"))
    a = ap.parse_args()
    sid = _sid()
    if a.volet == "e":
        rc = volet_e(sid, a.state_file)
        print("PROBE OK" if rc == 0 else "PROBE : rc=%d" % rc)
        return rc
    rid = _build(sid, a.state_file)
    h = H(sid, rid)
    rc = 0
    try:
        dv = h.dview()
        caster = h.by_visual(PORTEUR_VIS, dv)
        if caster is None:
            print("[MONTAGE] porteur %s absent du decisionView" % PORTEUR_VIS)
            return 2
        cid = int(caster["id"])
        h.mine = caster.get("owner")
        kit = [(x.get("id"), x.get("name")) for x in (caster.get("abilities") or [])]
        print("[A] caster id=%s pos=%s" % (cid, caster.get("pos")))
        print("[A] KIT ACTIF monte par la bataille : %r" % (kit,))
        ids = {int(x.get("id")) for x in (caster.get("abilities") or []) if x.get("id") is not None}
        for name, aid in (("1015 PrecisionShot", SHOT_ID), ("1012 Aim", AIM_ID),
                          ("1013 Attack", ATTACK_ID)):
            print("[A] %-20s monte=%s" % (name, aid in ids))

        cap0 = h.capture()
        print("[B] --- GATE avant visee : oracle natif vs port (cible = le caster) ---")
        rc = max(rc, _volet_gate(h, cap0, cid, "B"))

        print("[C] --- VISEE : cast LIVE de 1012, puis rejeu OFFLINE ---")
        eff_avant = h.effects_of(cid, cap0["dv"])
        us_avant = h.ability_usable(cid, SHOT_ID, cap0["dv"])
        print("[C] avant : effets=%r usable(1015)=%r" % (eff_avant, us_avant))
        a0, _res = h.cast(cid, cid, AIM_ID)
        print("[C] applyAction 1012 -> ok=%r mutated=%r actionConsumed=%r n_changes=%s"
              % (a0.get("ok"), a0.get("mutated"), a0.get("actionConsumed"),
                 len(a0.get("changes") or [])))
        dv1 = h.dview()
        eff_natif = h.effects_of(cid, dv1)
        us_natif = h.ability_usable(cid, SHOT_ID, dv1)
        print("[C] natif apres : effets=%r usable(1015)=%r" % (eff_natif, us_natif))
        diag, eff_port, us_port = _offline(cap0, cid, cid, AIM_ID)
        print("[C] port  apres : ported=%r effets=%r usable(1015)=%r"
              % (diag.get("ported"), eff_port, us_port))
        print("[C] port  diag  : %s" % json.dumps(diag, default=str)[:500])
        # ⚠ COMPARER PAR NOM, PAS PAR TYPE : `decisionView.effects` ne publie PAS de champ `type`
        # (il vaut `None` sur toutes les lignes) -- une comparaison par ordinal rendrait donc un
        # ensemble natif VIDE face a un ensemble port plein, et se lirait DESACCORD sur un accord
        # parfait. Mesure du 2026-08-14, sur ce probe meme.
        nat_names = sorted(n for _t, n, _r in eff_natif if n)
        port_names = sorted(n for _t, n, _r in eff_port if n)
        print("[C] NOMS d'effet natif=%r port=%r %s"
              % (nat_names, port_names, "ACCORD" if nat_names == port_names else "DESACCORD"))
        if nat_names != port_names:
            rc = 1
        # La DUREE des deux effets de visee (`AddSubEffectWithSameTurns` -> le sous-effet doit
        # porter la MEME que son parent).
        nat_dur = {n: r for _t, n, r in eff_natif if n and n.startswith("PrecisionShot")}
        port_dur = {n: r for _t, n, r in eff_port if n and n.startswith("PrecisionShot")}
        print("[C] DUREES natif=%r port=%r %s"
              % (nat_dur, port_dur, "ACCORD" if nat_dur == port_dur else "DESACCORD"))
        if nat_dur != port_dur:
            rc = 1
        if us_natif != us_port:
            print("[C] DESACCORD usable(1015) natif=%r port=%r" % (us_natif, us_port))
            rc = 1

        print("[D] --- APRES VISEE : le caster PORTE l'effet ---")
        dvt = h.my_turn()
        if dvt is None:
            print("[D] MONTAGE : le tour du caster est inatteignable -- volet NON MESURE")
            return max(rc, 2)
        cap1 = h.capture()
        eff_now = h.effects_of(cid, cap1["dv"])
        print("[D] effets du caster au retour de son tour : %r" % (eff_now,))
        rc = max(rc, _volet_gate(h, cap1, cid, "D"))
        us_before = h.ability_usable(cid, SHOT_ID, cap1["dv"])
        print("[D] usable(1015) AVANT le cast de 1015 : %r" % (us_before,))
        a1, res1 = h.cast(cid, cid, SHOT_ID)
        print("[D] applyAction 1015 -> ok=%r mutated=%r actionConsumed=%r n_changes=%s"
              % (a1.get("ok"), a1.get("mutated"), a1.get("actionConsumed"),
                 len(a1.get("changes") or [])))
        if us_before is False:
            # RESULTAT DE RE, pas un accident de montage : `SetActiveAbilityUsed(Owner, 1015)` est
            # DANS l'arbre de 1012, donc le seul cast qui rend 1015 legale (il pose l'effet de
            # visee) CONSOMME sa charge dans le meme souffle. Les deux regimes de 1015 sont donc
            # refuses par le natif, pour deux causes DIFFERENTES : hors visee ->
            # `casterReason 0x2` (regle dynamique, PORTEE) ; en visee -> etage AMONT
            # `CanCurrentlyBeUsed` (charge consommee), que le port ne porte pas -> il execute la
            # behaviour la ou le natif ne l'atteint jamais. Ecart NOMME, hors perimetre de la
            # tranche (il vaut pour TOUTE ability du registre, pas pour 1015).
            print("[D] REGIME : 1015 est en visee MAIS sa charge est consommee -> le natif refuse "
                  "EN AMONT (actionConsumed=%r). Le port, lui, n'a pas cet etage : son "
                  "`execute_behaviour` s'execute et son sous-cast 1012 est refuse par la regle "
                  "dynamique (`invalid_target: 2`). ECART NOMME, pre-existant."
                  % (a1.get("actionConsumed"),))
        dv2 = h.dview()
        print("[D] natif apres 1015 : effets=%r usable(1015)=%r"
              % (h.effects_of(cid, dv2), h.ability_usable(cid, SHOT_ID, dv2)))
        diag2, eff_port2, us_port2 = _offline(cap1, cid, cid, SHOT_ID)
        print("[D] port  apres 1015 : ported=%r effets=%r usable(1015)=%r"
              % (diag2.get("ported"), eff_port2, us_port2))
        print("[D] port  diag  : %s" % json.dumps(diag2, default=str)[:700])
    finally:
        h.dispose()
    print("PROBE OK" if rc == 0 else "PROBE : %d desaccord(s)" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
