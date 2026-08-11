#!/usr/bin/env python
"""probe #911 -- `DaemonicPatrons` (1203, `emperFlawlessBlade` « Hascule ») vs le natif.

CE QUI EST MESURE
-----------------
Avant #911 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc le cast
partait, l'`AbilityHandler` rendait `ported=False` et RIEN ne se passait -- 0 taunt, 0 buff, AUCUNE
erreur. Le probe monte UN regime deterministe (positions FORCEES par `--place`), et confronte
CINQ etages -- jamais un scalaire :

  E0  `ported`        -- l'observable qui distingue le port du no-op ;
  E1  LA POSE et LA DUREE des TROIS effets de l'arbre : `Taunted_OnlySpecificTargets` (27) sur la
      CIBLE, `DaemonicPatrons_ExtraDamage` (1464) et `DaemonicPatrons_DmgReduction` (1465) sur le
      CASTER, tous a `Sum(TurnsFromRounds(nrOfRounds), Const(1))` TOURS -- natif
      (`decisionView.units[].effects[].remainingTurns`) vs port (`EffectsState`) ;
  E2  LE COMPTEUR `n` = `GetNumAdjacentTauntedEnemies()`, et c'est le coeur du cas. Le montage pose
      **DEUX ennemis ADJACENTS au caster, dont UN SEUL sera taunte** : un port qui collapserait le
      `Filter(..., HasEffect(It, 27))` rendrait **2** au lieu de **1**, donc DOUBLERAIT les deux
      magnitudes. Le temoin DISCRIMINE ce collapse -- c'est ce qu'un montage a un seul ennemi ne
      pourrait pas faire ;
  E3  LE CANAL EXTRA-DAMAGE (`+extraDmg x n`, face ATTAQUANT). Le caster frappe la cible TAUNTEE,
      d'abord SANS le buff (bras temoin) puis AVEC (bras buff). Le probe confronte les montants
      NATIFS coup par coup au rejeu HORS LIGNE du moteur (`Runner.apply` sur la capture, MT cale
      par `dumpRng`), DANS LES DEUX BRAS -- et exige que le DELTA soit non nul (sans quoi l'accord
      serait obtenu en regime DEGENERE et ne prouverait rien) ;
  E4  LE CANAL REDUCTION (`-Min(100, dmgReductionPct x n) %`, face DEFENSEUR). L'ennemi NON taunte
      frappe le caster buffe ; meme confrontation natif/port, meme exigence de non-degenerescence.

MONTAGE (board `MC1_67`) -- les positions sont FORCEES, jamais subies
---------------------------------------------------------------------
    emperFlawlessBlade (3,4)  le caster. HERO `lineup` HORS pool ET HORS seed BC -> `catalog_inject`
                              (`docs/rl/case-92-catalog-injection.md` §6). `--list-pool` ne le rend
                              PAS, et ce n'est PAS un refus : aucun `data/unspawnable_rank*.json`.
    tauCrisis          (3,5)  la CIBLE du cast -- adjacente (le masque est `RANGE_ADJACENT`).
                              C'est elle qui recoit le bond `Taunted_OnlySpecificTargets`.
    tauCrisis          (2,4)  le SECOND adjacent, **jamais taunte**. C'est lui qui rend E2
                              discriminant, et c'est lui qui frappe le caster en E4.

CE QUE LE TEMOIN NE DISCRIMINE PAS (dit explicitement)
------------------------------------------------------
  * `n >= 2` : le cast ne taunte qu'UNE cible, donc ce montage ne peut pas exercer le produit
    au-dela de `n = 1`. Un facteur `x n` FAUX (ex. `x 1` en dur) passerait ce probe. L'etage E2b le
    couvre HORS LIGNE en poussant un second taunt dans l'`EffectsState` de la capture.
  * Le CAP `Min(100, pct x n)` : avec `dmgReductionPct = 30`, il faudrait `n >= 4`. Non atteignable
    en live sur ce montage -- couvert HORS LIGNE par E2b (`n = 4` force).

Usage (depuis `scripts/python`, ASCII only) :
    python probe_911_daemonic_patrons.py
    python probe_911_daemonic_patrons.py --keep      # ne dispose PAS le runner
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import uuid

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PYDIR)

DAEMONIC_PATRONS = 1203                    # `ActiveAbilityType.DaemonicPatrons`
DP_TAUNTED = 27                            # `EffectType.Taunted_OnlySpecificTargets` = 0x1b
DP_EXTRA_DAMAGE = 1464                     # `EffectType.DaemonicPatrons_ExtraDamage` = 0x5b8
DP_DMG_REDUCTION = 1465                    # `EffectType.DaemonicPatrons_DmgReduction` = 0x5b9
DP_REDUCTION_CAP = 100                     # `Min(Const(100)@DSLFormulas+0x30, ...)`

CASTER = "emperFlawlessBlade"              # « Hascule », seul porteur LINEUP de 1203
FOE_TAUNT = "tauCrisis"                    # la CIBLE du cast (sera tauntee)
FOE_PLAIN = "tauCrisis"                    # le SECOND adjacent, JAMAIS taunte

BOARD = "MC1_67"
SEED = 911
CASTER_TILE = "3,4"
TAUNT_TILE = "3,5"
PLAIN_TILE = "2,4"
#: crit/block FORCES a 0 des deux cotes : le canal mesure est l'ADDITIF et le POURCENT, pas le crit.
#: Sans ca un crit natif non reproduit offline masquerait l'etage sous une divergence de tirage.
CRIT = "0,100"
#: PV eleves des DEUX cotes : personne ne doit mourir avant la fin de la sequence (une cible MORTE
#: sature l'observable -- l'accord y serait obtenu sur un zero).
HP = 900000

RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attack_DidCrit=(\d).*?Attacker_Id=(\d+) Target_Id=(\d+) "
    r"Amount=(-?\d+) DamageProfileType=(\d+) Active_Ability_Type=(\d+)")
#: La DUREE **POSEE** se lit dans les events du cast, jamais dans `decisionView` : ce dernier est
#: capture APRES le `[EndTurn]` que le cast declenche, et son `remaining` a DEJA ete decremente par
#: l'`Effect_Refresh` de fin de tour (MESURE : pose a 3, publie a 2). Comparer le `remaining` de
#: `decisionView` au `remaining_turns` du port -- qui, lui, n'a pas joue le EndTurn -- ferait rougir
#: un port JUSTE, et le « corriger » d'un `+1` serait un fit.
#: ⚠ Le nom est encadre de guillemets FRANCAIS que la console Windows rend en MOJIBAKE
#: (`Â«...Â»` : de l'UTF-8 relu en cp1252). `Â` est un caractere WORD en Unicode, donc un motif
#: `\W*(\w+)\W*` ECHOUE en silence -- mesure du 2026-08-11, il rendait `[]` et E1 accusait le port.
#: On capture donc le contenu BRUT et on en extrait l'identifiant ASCII.
RE_REFRESH = re.compile(r"\[Effect_Refresh e=(\d+)\s+(\S.*?)\]")
RE_NOM = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
RE_RECEIVE = re.compile(r"ReceiveEffect e=(\d+).*?Effect_RemainingTurns=(\d+)")


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=600):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ montage

def build(state_file: str, seed_bc: str):
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--seed-bc", seed_bc,
            "--crit", CRIT, "--crit-target", CRIT,
            "--hp-player", str(HP), "--hp-target", str(HP),
            "--p-units", CASTER, "--a-units", "%s,%s" % (FOE_TAUNT, FOE_PLAIN),
            "--place", "%s:%s" % (CASTER, CASTER_TILE),
            "--a-place", "%s:%s" % (FOE_TAUNT, TAUNT_TILE),
            "--a-place", "%s:%s" % (FOE_PLAIN, PLAIN_TILE),
            "--state-file", state_file]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-2500:], p.stderr[-1500:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    """Index par ID d'unite (les deux ennemis partagent leur `visualId` : on ne peut PAS indexer
    par visualId ici, ce serait perdre un des deux -- c'est le piege de ce montage)."""
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[int(u.get("id"))] = {
            "vis": u.get("visualId"), "pos": (p.get("col"), p.get("row")),
            "hp": u.get("hp"), "alive": not u.get("isDead"), "team": u.get("team"),
            "abilities": u.get("abilities") or [],
            "effects": {int(e.get("effectType")): e.get("remainingTurns")
                        for e in (u.get("effects") or []) if isinstance(e, dict)}}
    return out


def capture(sid, rid):
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "ab": _rpc(sid, "unitAbilityStates", {"runnerId": rid}, 90),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


def etat_offline(cap):
    """Le substrat du rejeu porte, MT cale sur `dumpRng` -- sans lui le degat offline est un faux 0."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=Board(cap["tiles"], adjacency="evenq"),
                    ability_states=cap["ab"])
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    return st


def montants_natifs(sortie, attaquant=None):
    """SEQUENCE coup par coup du NATIF : (attaquant, cible, montant, crit).

    Elle se lit dans le STDOUT de `rl_duel act` (les events formates), PAS dans la reponse RPC
    brute d'`applyAction` : cette derniere ne porte pas le texte des tags."""
    out = []
    for m in RE_DMG.finditer(sortie or ""):
        _e, crit, att, tgt, amount, _prof, _at = m.groups()
        if attaquant is not None and int(att) != int(attaquant):
            continue
        out.append({"att": int(att), "tgt": int(tgt), "amount": int(amount), "crit": crit == "1"})
    return out


# ------------------------------------------------------------------ etages

def hp_port(st, uid):
    from engine.runner.components import HealthComponent
    e = st.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else int(hc.hp)


def hp_natif(cap_ou_ob, uid):
    ob = cap_ou_ob.get("ob") if "ob" in cap_ou_ob else cap_ou_ob
    for u in (ob.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            return int(u.get("hp") or u.get("health") or 0)
    return None


def rejeu_attaque(cap, att_id, tgt_id):
    """Rejeu HORS LIGNE de l'ATTAQUE NORMALE, par le CHEMIN COMPLET du moteur.

    ⚠ `install_default_handlers(20)` est OBLIGATOIRE : sans lui `Runner.apply` ne traite RIEN et
    rend un delta de 0 -- un faux accord silencieux si l'autre cote rendait 0 aussi. Mesure du
    2026-08-11 : la premiere version de ce probe l'omettait et rendait `port=[]` sur les CINQ
    etages."""
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    st = etat_offline(cap)
    hp0 = hp_port(st, tgt_id)
    Runner(st).install_default_handlers(20).apply(AttackUnitMessage(int(att_id), int(tgt_id)))
    hp1 = hp_port(st, tgt_id)
    return st, (None if hp0 is None or hp1 is None else hp0 - hp1)


def poses_natives(sortie):
    """{nom d'effet -> (unite receveuse, duree POSEE)} lu dans les events du cast."""
    out, nom = {}, None
    for ligne in (sortie or "").splitlines():
        m = RE_REFRESH.search(ligne)
        if m:
            ident = RE_NOM.search(m.group(2))
            nom = ident.group(0) if ident else None
            continue
        r = RE_RECEIVE.search(ligne)
        if r and nom:
            out[nom] = (int(r.group(1)), int(r.group(2)))
    return out


def compteur_offline(st, uid):
    """`GetNumAdjacentTauntedEnemies()` cote PORT, par le foyer unique."""
    from engine.runner.components import adjacent_taunted_enemies_count
    return adjacent_taunted_enemies_count(st, int(uid))


# ------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()

    import catalog_inject
    tmp = tempfile.gettempdir()
    tag = uuid.uuid4().hex[:8]
    seed_bc = os.path.join(tmp, "seedbc-911-%s.json" % tag)
    catalog_inject.write_augmented_seed_bc(seed_bc, [CASTER])
    sf = a.state_file or os.path.join(tmp, "rs-911-%s.json" % tag)
    sf2 = os.path.join(tmp, "rs-911-t2-%s.json" % tag)

    sid = _sid()
    rid = build(sf, seed_bc)
    if rid is None:
        print("[911] BUILD KO")
        return 2
    print("[911] runner=%s board=%s seed=%s" % (rid, BOARD, SEED))
    ok = True
    try:
        u0 = unites(sid, rid)
        caster = next((i for i, v in u0.items() if v["vis"] == CASTER), None)
        foes = sorted(i for i, v in u0.items() if v["vis"] != CASTER and v["team"] != u0[caster]["team"])
        by_pos = {v["pos"]: i for i, v in u0.items()}
        tgt = by_pos.get(tuple(int(x) for x in TAUNT_TILE.split(",")))
        plain = by_pos.get(tuple(int(x) for x in PLAIN_TILE.split(",")))
        print("[montage] caster=%s cible=%s second=%s (adjacents=%s)"
              % (caster, tgt, plain, len(foes)))
        if caster is None or tgt is None or plain is None:
            print("[911] MONTAGE KO -- une unite manque au plateau")
            return 2

        # ---- E0 : le registre -------------------------------------------------
        from engine.runner.abilities.handler import ABILITY_CLASSES
        e0 = DAEMONIC_PATRONS in ABILITY_CLASSES
        print("[E0] 1203 dans ABILITY_CLASSES : %s" % e0)
        ok &= e0

        # `{"id": 69, "name": "Loki_NormalAttack", "kind": "normal"}` -- l'attaque normale est un id
        # d'ability CONCRET, per-unit (`NormalAttackType@0x28`), jamais une constante du probe.
        na = next((int(x.get("id")) for x in (u0[caster]["abilities"] or [])
                   if x.get("kind") == "normal"), None)
        na_foe = next((int(x.get("id")) for x in (u0[plain]["abilities"] or [])
                       if x.get("kind") == "normal"), None)

        # ---- BRAS TEMOIN : personne n'est buffe --------------------------------
        cap_t = capture(sid, rid)
        n_t = compteur_offline(etat_offline(cap_t), caster)
        p = _duel(["act", "ability", "--caster", str(caster), "--target", str(tgt),
                   "--ability", str(na), "--state-file", sf])
        nat_t = sum(h["amount"] for h in montants_natifs(p.stdout, attaquant=caster))
        _st, port_t = rejeu_attaque(cap_t, caster, tgt)
        acc_t = (nat_t == port_t and port_t)
        print("[temoin] n=%s  natif=%s  port=%s  accord=%s" % (n_t, nat_t, port_t, acc_t))
        ok &= bool(acc_t) and n_t == 0

        # le second ennemi (JAMAIS taunte) frappe le caster NON buffe -> base de E4
        _duel(["attach", "--team", "2", "--from", sf, "--state-file", sf2])
        cap_td = capture(sid, rid)
        p = _duel(["act", "ability", "--caster", str(plain), "--target", str(caster),
                   "--ability", str(na_foe), "--state-file", sf2])
        nat_td = sum(h["amount"] for h in montants_natifs(p.stdout, attaquant=plain))
        _st, port_td = rejeu_attaque(cap_td, plain, caster)
        acc_td = (nat_td == port_td and port_td)
        print("[temoin-def] natif=%s port=%s accord=%s" % (nat_td, port_td, acc_td))
        ok &= bool(acc_td)
        _duel(["dispose", "--state-file", sf])

        # ---- BRAS BUFF : meme montage, le caster caste 1203 d'abord ------------
        rid = build(sf, seed_bc)
        if rid is None:
            print("[911] BUILD (bras buff) KO")
            return 2
        u1 = unites(sid, rid)
        by_pos = {v["pos"]: i for i, v in u1.items()}
        caster = by_pos[tuple(int(x) for x in CASTER_TILE.split(","))]
        tgt = by_pos[tuple(int(x) for x in TAUNT_TILE.split(","))]
        plain = by_pos[tuple(int(x) for x in PLAIN_TILE.split(","))]
        cap_c = capture(sid, rid)
        p = _duel(["act", "ability", "--caster", str(caster), "--target", str(tgt),
                   "--ability", str(DAEMONIC_PATRONS), "--state-file", sf])

        # ---- E1 : LA POSE et LA DUREE, natif vs port ---------------------------
        pn = poses_natives(p.stdout)
        nat_pose = {"taunt": pn.get("Taunted_OnlySpecificTargets"),
                    "extra": pn.get("DaemonicPatrons_ExtraDamage"),
                    "reduc": pn.get("DaemonicPatrons_DmgReduction")}
        from engine.runner.runner import Runner
        from engine.runner.messages import ActiveAbilityMessage
        st_c = etat_offline(cap_c)
        Runner(st_c).install_default_handlers(20).apply(
            ActiveAbilityMessage(caster_id=int(caster), target_id=int(tgt),
                                 ability_type=DAEMONIC_PATRONS))
        def _rt(uid, et):
            for e in (st_c.effects.by_unit.get(int(uid)) or []):
                if int(getattr(e, "effect_type", -1)) == int(et):
                    return (int(uid), getattr(e, "remaining_turns", None))
            return None
        port_pose = {"taunt": _rt(tgt, DP_TAUNTED), "extra": _rt(caster, DP_EXTRA_DAMAGE),
                     "reduc": _rt(caster, DP_DMG_REDUCTION)}
        # LE SECOND ENNEMI N'EST PAS TAUNTE -- des DEUX cotes. C'est ce qui rend E2 legitime.
        nat_plain = any(u == plain for u, _t in pn.values())
        port_plain = _rt(plain, DP_TAUNTED) is not None
        e1 = (nat_pose == port_pose and all(v is not None for v in nat_pose.values())
              and not nat_plain and not port_plain)
        print("[E1] natif=%s  port=%s  second-taunte natif/port=%s/%s  accord=%s"
              % (nat_pose, port_pose, nat_plain, port_plain, e1))
        ok &= e1

        # ---- E2 : LE COMPTEUR, et ce qu'il DISCRIMINE --------------------------
        n_port = compteur_offline(st_c, caster)
        from engine.runner.components import adjacent_enemies_count
        n_sans_filtre = adjacent_enemies_count(st_c, caster)
        e2 = (n_port == 1 and n_sans_filtre == 2)
        print("[E2] adjacents_TAUNTES=%s  adjacents_TOUS=%s  (le Filter DISCRIMINE : %s)"
              % (n_port, n_sans_filtre, e2))
        ok &= e2

        # ---- E2b : LE PRODUIT `x n` ET LE CAP, HORS LIGNE ----------------------
        # Le live ne peut pas depasser `n = 1` (le cast ne taunte qu'UNE cible), donc un facteur
        # `x n` FAUX -- `x 1` en dur, ou un `n` capte a la pose -- passerait E1/E2/E3/E4 sans
        # broncher. On interroge donc les DEUX hooks sur les INSTANCES REELLES (elles portent les
        # vrais niveaux/multiplicateurs bakes par l'`AddEffect`) avec un `n` FORCE.
        inst = {int(getattr(e, "effect_type", -1)): e
                for e in (st_c.effects.by_unit.get(int(caster)) or [])}
        ex, rd = inst.get(DP_EXTRA_DAMAGE), inst.get(DP_DMG_REDUCTION)
        serie_x, serie_r = {}, {}
        for n in (0, 1, 2, 4):
            ctx = {"adjacent_taunted_enemies": n}
            bx = ex.create_effect_damage_bonus_for_attack(att_ctx=ctx) if ex else None
            br = rd.create_effect_damage_malus_for_defense(attacker_ctx=ctx) if rd else None
            serie_x[n] = None if bx is None else int(bx.value)
            serie_r[n] = None if br is None else int(br.value)
        v1 = serie_x.get(1)
        # `Multiply(ConfigVar(extraDmg), n)` : STRICTEMENT lineaire, et NUL a n = 0.
        lin = (v1 is not None and serie_x[0] is None and serie_x[2] == 2 * v1
               and serie_x[4] == 4 * v1)
        # `Multiply(Const(-1), Min(Const(100), Multiply(ConfigVar(dmgReductionPct), n)))` :
        # NEGATIF, lineaire, et CAPE a -100 des que `pct x n >= 100`.
        p1 = serie_r.get(1)
        cap = (p1 is not None and p1 < 0 and serie_r[0] is None and serie_r[2] == 2 * p1
               and serie_r[4] == -DP_REDUCTION_CAP and 2 * p1 > -DP_REDUCTION_CAP)
        print("[E2b] extraDmg par n : %s -> lineaire=%s" % (serie_x, lin))
        print("[E2b] reduction par n : %s -> negatif+cape(-%d)=%s"
              % (serie_r, DP_REDUCTION_CAP, cap))
        ok &= lin and cap

        # ---- E4 : la REDUCTION -- le second ennemi frappe le caster BUFFE ------
        _duel(["attach", "--team", "2", "--from", sf, "--state-file", sf2])
        cap_d = capture(sid, rid)
        p = _duel(["act", "ability", "--caster", str(plain), "--target", str(caster),
                   "--ability", str(na_foe), "--state-file", sf2])
        nat_d = sum(h["amount"] for h in montants_natifs(p.stdout, attaquant=plain))
        _st, port_d = rejeu_attaque(cap_d, plain, caster)
        acc_d = (nat_d == port_d and port_d)
        deg_d = (nat_d != nat_td)                 # la reduction DOIT changer le montant
        print("[E4] natif=%s port=%s accord=%s | temoin=%s -> NON DEGENERE=%s"
              % (nat_d, port_d, acc_d, nat_td, deg_d))
        ok &= bool(acc_d) and deg_d
        _duel(["act", "endturn", "--state-file", sf2])

        # ---- E3 : l'EXTRA-DAMAGE -- le caster BUFFE frappe la cible TAUNTEE ----
        cap_a = capture(sid, rid)
        p = _duel(["act", "ability", "--caster", str(caster), "--target", str(tgt),
                   "--ability", str(na), "--state-file", sf])
        nat_a = sum(h["amount"] for h in montants_natifs(p.stdout, attaquant=caster))
        _st, port_a = rejeu_attaque(cap_a, caster, tgt)
        acc_a = (nat_a == port_a and port_a)
        deg_a = (nat_a != nat_t)                  # le +extraDmg DOIT changer le montant
        print("[E3] natif=%s port=%s accord=%s | temoin=%s -> NON DEGENERE=%s"
              % (nat_a, port_a, acc_a, nat_t, deg_a))
        ok &= bool(acc_a) and deg_a
    finally:
        if not a.keep:
            _duel(["dispose", "--state-file", sf])
            for f in (sf, sf2, seed_bc):
                try:
                    os.remove(f)
                except OSError:
                    pass
    print("[911] %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
