#!/usr/bin/env python
"""probe #911-r1 -- CONFRONTATION de `DaemonicPatrons_Finale` (triggered 0x5c1 = 1473).

CRITERE BINAIRE, pose avant toute methode :

    << Quand `emperFlawlessBlade` (<< Hascule >>) ACHEVE un ennemi TAUNTE alors qu'il porte encore
       `DaemonicPatrons_ExtraDamage` (1464), le natif re-arme-t-il son actif `DaemonicPatrons`
       (1203) -- et le PORT rend-il le MEME verdict, a partir du meme etat et du meme flux PRNG ? >>

L'observable est l'ETAT D'UTILISATION de l'actif du TUEUR : `usable` / `cooldown` cote
`decisionView.units[].abilities` (natif), `ActiveAbilitiesComponent` cote port -- les deux champs
qu'ecrit `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute`.

## CE QUE CE PROBE ETABLIT, ET QUI ETAIT LE BLOCAGE DU RESIDU

`#911-r1` portait `BLOCAGE: seeding` sur l'enonce << 1473 n'est ni dans `activeAbilities` ni dans
`passiveAbilities` du kit d'`emperFlawlessBlade`, donc le canal d'inscription n'est pas etabli >>.
Le canal EST etabli (`GetDerivedTriggeredAbilities[0x4b3] = [0x5c1]`, cf. l'en-tete de
`engine/runner/operations/triggers/loki/daemonic_patrons.py`). Ce probe le CONFRONTE : si le natif
re-arme, c'est que 1473 est bien monte sur Hascule sans aucune entree de kit.

## LE MONTAGE, et pourquoi chaque piece y est

  * `emperFlawlessBlade` est HORS POOL et HORS seed BC -> `catalog_inject.write_augmented_seed_bc`
    (meme voie que `probe_911_daemonic_patrons.py`). Ce n'est PAS un refus : aucun
    `data/unspawnable_rank*.json` ne le nomme.
  * L'actif 1203 doit etre CONSOMME avant le kill, sinon le gate natif
    `IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` rend FAUX et
    `ResetActiveAbility` est un no-op : rien ne discriminerait. Il l'est PAR CONSTRUCTION -- c'est
    le cast de 1203 lui-meme qui pose le taunt 27 sur la victime ET les buffs 1464/1465 sur Hascule.
    Le probe VERIFIE que l'actif est non-utilisable juste avant le kill, et REFUSE (rc 2) sinon.
  * Le cast TERMINE le tour (mesure #911) -> il faut un cycle de tour complet entre le cast et le
    kill. Le buff 1464 dure `Sum(TurnsFromRounds(1), Const(1))` = 3 tours a la pose, donc il est
    encore la au tour suivant : le probe le VERIFIE plutot que de le supposer.
  * `--crit 0,0` / `--block-target 0,0` : aucun canal aleatoire ne decide de la mort.

## LES DEUX BRAS, et pourquoi il en faut DEUX

  * `TAUNTE` (defaut) -- Hascule acheve la victime QU'IL A TAUNTEE. Les quatre conjoints du
    `CreateTrigger` sont vrais, le natif DOIT re-armer. La contre-epreuve `NOPORT` (l'entree
    `"DaemonicPatrons"` retiree d'`ACTIVE_ABILITY_TRIGGERS`, c.-a-d. la vue d'AVANT ce port) doit
    CHANGER l'observable : sans elle, << ca concorde >> ne prouverait rien.
  * `--non-taunte` -- Hascule acheve l'AUTRE ennemi, celui qu'il n'a jamais taunte. Le MEME kill,
    la MEME attaque normale, le MEME buff 1464 sur lui. Seul le conjoint
    `HasEffect(Target@<DSLSelectors+0x60>, 0x1b = 27, onlyActive 0, 6)` change, et il doit MORDRE :
    le natif ne DOIT PAS re-armer. C'est le seul bras qui exerce ce noeud -- sans lui, un port qui
    re-armerait sur TOUT kill concorderait quand meme sur le bras positif.

Le temoin n'est donc PAS degenere : les deux bras different par UN SEUL predicat, et le natif y
rend DEUX verdicts opposes.

## CE QUE CE PROBE NE COUVRE PAS (dit explicitement)

  * La face FAIL (`DaemonicPatrons_FinaleFailAbility`, `On(0x40 = EffectRemoved)` -> perte de
    `hpPct` % des PV COURANTS). Elle exige d'attendre l'EXPIRATION de l'effet 1465, soit 3 tours du
    porteur sans kill taunte. Volet non joue ici -- il reste NON CONFRONTE LIVE, et c'est dit.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_911r1_daemonic_patrons_finale_live.py
    python probe_911r1_daemonic_patrons_finale_live.py --non-taunte
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

CARRIER = "emperFlawlessBlade"     # << Hascule >>, seul porteur LINEUP de l'actif 1203
ALLY = "blackHaarken"              # 2e unite de mon camp : elle n'agit pas
ABILITY_TYPE = 1203                # `ActiveAbilityType.DaemonicPatrons` = 0x4b3
FINALE_TRIGGERED = 1473            # `TriggeredAbilityType.DaemonicPatrons_Finale` = 0x5c1
DP_TAUNTED = 27                    # `EffectType.Taunted_OnlySpecificTargets` = 0x1b
DP_EXTRA_DAMAGE = 1464             # `EffectType.DaemonicPatrons_ExtraDamage` = 0x5b8
REGISTRY_KEY = "DaemonicPatrons"   # cle d'`ACTIVE_ABILITY_TRIGGERS`


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _pos_of(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def seed_bc_avec_hascule() -> str:
    import catalog_inject
    fd, out = tempfile.mkstemp(prefix="probe_911r1_bc_", suffix=".json")
    os.close(fd)
    catalog_inject.write_augmented_seed_bc(out, [CARRIER])
    return out


def build(a, seed_bc):
    fd, sf = tempfile.mkstemp(prefix="probe_911r1_", suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--seed-bc", seed_bc,
            "--p-units", "%s,%s" % (CARRIER, ALLY),
            "--a-units", "%s,%s,%s" % (a.target_unit, a.other_unit, a.third_unit),
            "--hp-target", str(a.hp_target), "--hp-player", "900000",
            "--unit-stat", "%s:Damage=%d" % (CARRIER, a.dmg),
            "--no-ai", "--crit", "0,0", "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("build KO : %s" % ((p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _active_state_live(dv, unit_id):
    """`usable` / `cooldown` de l'actif 1203 dans le `decisionView` -- l'oracle NATIF des deux champs
    qu'ecrit `ResetActiveAbilityOperation$$Execute`."""
    for u in (dv.get("units") or []):
        if u.get("id") == unit_id:
            for ab in (u.get("abilities") or []):
                if ab.get("id") == ABILITY_TYPE:
                    return {"usable": ab.get("usable"), "cooldown": ab.get("cooldown")}
    return None


def _active_state_port(st, unit_id):
    """Le pendant PORT : `ActiveAbilitiesComponent` (mirror d'`ActiveAbilityComponent`)."""
    from engine.runner.components import ActiveAbilitiesComponent
    e = st.get_entity(int(unit_id))
    comp = e.get_component(ActiveAbilitiesComponent) if e is not None else None
    if comp is None:
        return None
    for ab in comp.abilities:
        if int(ab.ability_type) == ABILITY_TYPE:
            return {"usable": bool(ab.can_still_be_used), "cooldown": ab.remaining_cooldown}
    return None


def _effets(dv, unit_id):
    for u in (dv.get("units") or []):
        if u.get("id") == unit_id:
            return {int(e.get("effectType")): e.get("remainingTurns")
                    for e in (u.get("effects") or []) if isinstance(e, dict)}
    return {}


def stage(h, a):
    """Monte le regime et rend `(rec, raison)`. `raison is None` == regime ATTEINT.

    ETAPES : placements (victime ET temoin ADJACENTS a Hascule) -> cycle de tour -> CAST de 1203 sur
    la VICTIME (taunt 27 sur elle, buffs 1464/1465 sur Hascule, actif consomme, tour termine) ->
    cycle de tour -> verification du regime -> snapshot (le kill est porte hors d'ici).
    """
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "porteur %s absent du deploiement" % CARRIER
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < 3:
        return None, ("il faut 3 ennemis (le TAUNTE, le NON TAUNTE, et un SURVIVANT) -- %d trouve(s)"
                      % len(ens))
    victime_taunt, victime_plain, survivant = ens[0], ens[1], ens[2]

    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]
    occupe = {p for p in (_pos_of(u) for u in h.alive(dv)) if p is not None}
    libres = [c for c in marchables if c not in occupe]

    def _n_voisins(c):
        return sum(1 for s in marchables if hexgeo.distance(s, c) == 1)

    # ⚠ GEOMETRIE CONTRAINTE PAR UNE MESURE, pas par confort. L'attaque normale de Hascule
    # ECLABOUSSE : un premier montage placant les DEUX victimes au contact les a tuees TOUTES LES
    # DEUX d'un seul coup -- la bataille se terminait, `decisionView` rendait `units: []`, et le
    # bras NON TAUNTE aurait de toute facon vu mourir la victime TAUNTEE dans le meme coup (donc le
    # trigger aurait fire, et le bras negatif n'aurait rien discrimine).
    # D'ou : le TAUNTE au CONTACT (le masque de 1203 est `RANGE_ADJACENT`), le NON TAUNTE LOIN
    # (on ira le chercher), et un TROISIEME ennemi encore plus loin pour que la bataille SURVIVE
    # au kill -- sans lui, plus aucun canal ne publie l'etat d'actif.
    plan = None
    for anchor in sorted(libres, key=lambda c: (-_n_voisins(c), c)):
        if _n_voisins(anchor) < 4:
            break
        contacts = [s for s in libres if hexgeo.distance(s, anchor) == 1]
        loin = [s for s in libres if hexgeo.distance(s, anchor) >= 5]
        if len(contacts) >= 1 and len(loin) >= 2:
            # le NON TAUNTE et le SURVIVANT doivent aussi etre loin l'un de l'autre : le kill du
            # bras negatif ne doit eclabousser personne.
            paires = [(x, y) for x in loin for y in loin if hexgeo.distance(x, y) >= 4]
            if paires:
                plan = (anchor, contacts, paires[0])
                break
    if plan is None:
        return None, "geometrie non realisable (contact + 2 postes eloignes et disjoints)"
    anchor, contacts, (poste_plain, poste_surv) = plan

    if not h.place(me["id"], anchor):
        return None, "placement de Hascule refuse"
    if not h.place(victime_taunt["id"], contacts[0]):
        return None, "placement de la victime TAUNTEE refuse"
    if not h.place(victime_plain["id"], poste_plain):
        return None, "placement de la victime NON TAUNTEE refuse"
    if not h.place(survivant["id"], poste_surv):
        return None, "placement du SURVIVANT refuse"
    # L'allie n'est PAS deplace : il n'agit pas, et toute tuile qu'on lui donnerait serait une tuile
    # de moins pour la geometrie contrainte ci-dessus.

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint (avant le cast)"

    # --- CONSOMMATION de l'actif : le VRAI cast de 1203 sur la victime TAUNTEE -----------------
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": me["id"], "targetId": victime_taunt["id"],
        "abilityType": ABILITY_TYPE}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "cast de 1203 refuse : %s" % str(res)[:300]
    dv = h.dview()
    apres_cast = _active_state_live(dv, me["id"])
    if apres_cast is None or apres_cast.get("usable"):
        return None, ("l'actif est encore utilisable APRES le cast (%s) -- rien a re-armer"
                      % apres_cast)

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint (avant le kill)"

    # --- LE REGIME, verifie piece par piece plutot que suppose --------------------------------
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "Hascule a disparu apres le cycle de tour"
    eff_moi = _effets(dv, me["id"])
    if DP_EXTRA_DAMAGE not in eff_moi:
        return None, ("le buff 1464 a EXPIRE avant le kill (effets = %s) -- le conjoint "
                      "`HasEffect(Actor, 1464)` ne serait plus exerce" % sorted(eff_moi))
    cible = victime_plain if a.non_taunte else victime_taunt
    autre = victime_taunt if a.non_taunte else victime_plain
    vic = next((u for u in h.alive(dv) if u["id"] == cible["id"]), None)
    if vic is None:
        return None, "la cible du kill est deja morte"
    eff_vic = _effets(dv, cible["id"])
    eff_taunt = _effets(dv, victime_taunt["id"])
    if DP_TAUNTED not in eff_taunt:
        return None, ("le taunt 27 n'est PAS sur la victime tauntee (effets = %s) -- le cast n'a pas "
                      "produit le regime" % sorted(eff_taunt))
    if a.non_taunte and DP_TAUNTED in eff_vic:
        return None, "la cible du bras NON TAUNTE porte le taunt 27 -- le bras ne discrimine rien"

    # Le kill se porte au CONTACT : on verifie l'adjacence plutot que de la subir.
    if hexgeo.distance(_pos_of(me), _pos_of(vic)) != 1:
        occ = {p for p in (_pos_of(u) for u in h.alive(dv)) if p is not None} - {_pos_of(me)}
        dest = next((c for c in marchables
                     if hexgeo.distance(c, _pos_of(vic)) == 1 and c not in occ), None)
        if dest is None or not h.place(me["id"], dest):
            return None, "impossible de ramener Hascule au contact de la cible"
        dv = h.dview()
        me = h.by_visual(CARRIER, dv)

    avant = _active_state_live(dv, me["id"])
    if avant is None:
        return None, "actif 1203 absent du decisionView"
    if avant.get("usable"):
        return None, ("l'actif s'est re-arme TOUT SEUL avant le kill (%s) -- le regime ne "
                      "discrimine plus rien" % avant)

    nat = h.normal_attack_type(me["id"], dv)
    if nat is None:
        return None, "attaque normale introuvable pour Hascule"
    rec = {"caster": me["id"], "target": cible["id"], "autre": autre["id"], "step_to": None,
           "ability_type": nat, "avant": avant, "eff_moi": eff_moi, "eff_cible": eff_vic}
    rec["snapshot"] = h.snapshot()
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    if a.verbose:
        print("    Hascule %s, cible %s (effets %s), mes effets %s, attaque normale %s"
              % (_pos_of(me), _pos_of(vic), sorted(eff_vic), sorted(eff_moi), nat))
    return rec, None


def kill_live(h, rec):
    """L'ATTAQUE NORMALE native. Rend `(observables, raison)`."""
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "attaque normale refusee : %s" % str(res)[:300]
    ob = h.rpc("observeBattle", {"runnerId": h.rid}, 40) or {}
    rows = [u for u in (ob.get("units") or []) if u.get("id") == rec["target"]]
    mort = (not rows) or bool(rows[0].get("isDead"))
    apres, voie = _lire_actif_natif(h, rec["caster"])
    return {"mort": bool(mort), "apres": apres, "voie": voie}, None


def _lire_actif_natif(h, unit_id):
    """Lecture de l'etat d'actif NATIF, avec le canal EFFECTIVEMENT utilise rendu avec la valeur.

    ⚠ MESURE (2026-08-14) : juste apres l'attaque qui TERMINE le tour du porteur, `decisionView`
    rend `units: []` -- il n'y a plus d'unite a activer, donc plus de vue de decision. Un lecteur
    qui s'arrete la rend `None` et se lit comme << l'actif n'est pas re-arme >>, alors que c'est
    << NON MESURE >>. On rouvre donc un tour AVANT de conclure.

    Le cycle de tour est-il lui-meme capable de re-armer l'actif ? C'est precisement ce que le bras
    `--non-taunte` controle : il joue le MEME cycle et doit rendre `usable=False`. Si le cycle
    re-armait, les deux bras seraient d'accord et le probe le DIRAIT (le bras negatif rendrait
    << le NATIF ne fait pas ce que le bras attend >>)."""
    st = _active_state_live(h.dview(), unit_id)
    if st is not None:
        return st, "direct"
    if h.reach_my_turn(force_cycle=True) is None:
        ob = h.rpc("observeBattle", {"runnerId": h.rid}, 40) or {}
        vivants = [(u.get("id"), u.get("visualId"), u.get("team"), u.get("isDead"))
                   for u in (ob.get("units") or [])]
        return None, ("tour non rouvert -- observeBattle: active=%r winner=%r units=%s"
                      % (ob.get("isBattleActive"), ob.get("winner"), vivants))
    return _active_state_live(h.dview(), unit_id), "apres cycle de tour"


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque normale, RNG cale sur le dump pris juste avant.

    MUTATION `NOPORT` : l'entree `"DaemonicPatrons"` retiree d'`ACTIVE_ABILITY_TRIGGERS` -- c'est le
    registre qui materialise la triggered derivee, donc son retrait rend la vue d'AVANT ce port
    (aucun `DaemonicPatronsFinaleSuccessAbility` instancie). Restauree en `finally`."""
    from engine.runner.components import UnitComponent
    from engine.runner.operations.triggers.dispatch.registry import ACTIVE_ABILITY_TRIGGERS
    saved = ACTIVE_ABILITY_TRIGGERS.get(REGISTRY_KEY)
    espion = _armer_espion() if mutate == "DIAG" else None
    try:
        if mutate == "NOPORT":
            ACTIVE_ABILITY_TRIGGERS.pop(REGISTRY_KEY, None)
        res = h.replay_offline(rec)
        st = res["state"]
        e = st.get_entity(rec["target"])
        uc = e.get_component(UnitComponent) if e is not None else None
        return {"mort": bool(uc is not None and not uc.alive),
                "apres": _active_state_port(st, rec["caster"]),
                "per_hit": res.get("per_hit") or [],
                "espion": (espion or {}).get("traces")}
    finally:
        if saved is not None:
            ACTIVE_ABILITY_TRIGGERS[REGISTRY_KEY] = saved
        if espion is not None:
            espion["restaurer"]()


def _armer_espion():
    """DIAGNOSTIC : instrumente `matches` de la face SUCCESS pour dire QUEL conjoint tombe.

    Un port qui ne fire pas rend le meme observable qu'un port absent -- il faut donc regarder
    DANS le predicat, conjoint par conjoint, plutot que de deviner lequel a mordu."""
    from engine.runner.operations.triggers.loki import daemonic_patrons as DP
    cls, traces = DP.DaemonicPatronsFinaleSuccessAbility, []
    original = cls.matches

    def espionne(self, state, ev):
        v = ev.dying_id if ev.dying_id is not None else ev.target_id
        traces.append({
            "killer_id": ev.killer_id, "actor_id": ev.actor_id, "target_id": ev.target_id,
            "dying_id": ev.dying_id, "owner": int(self.owner_id),
            "owner_is_actor": ev.killer_id is not None and int(ev.killer_id) == int(self.owner_id),
            "taunt_sur_victime": DP._has_effect(state, v, DP.DP_TAUNTED),
            "buff_sur_tueur": DP._has_effect(state, ev.killer_id, DP.DP_EXTRA_DAMAGE),
            "verdict": original(self, state, ev)})
        return traces[-1]["verdict"]

    cls.matches = espionne
    return {"traces": traces, "restaurer": lambda: setattr(cls, "matches", original)}


def mesurer(a, rpc, Board, Harness, rid) -> dict:
    """LA MESURE, sur un runner DEJA construit -- sans impression ni verdict.

    Rend `{ok, why, bras, attendu, avant, live, offline, noport}`. C'est le point d'entree du
    PORTAGE PYTEST (`tests/engine/runner/test_911r1_daemonic_patrons_finale_live.py`) : le probe
    MESURE, le test ASSERTE, et aucun montage n'est duplique entre les deux (#911-r1).

    `ok: False` = le REGIME n'a pas ete atteint (montage), jamais un verdict de fidelite -- le
    consommateur doit le distinguer d'un desaccord port/natif, sinon un montage rate se lirait
    comme un accord."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    bras = "NON TAUNTE" if a.non_taunte else "TAUNTE"
    rec, why = stage(h, a)
    if rec is None:
        return {"ok": False, "why": "montage : %s" % why, "bras": bras}
    live, why = kill_live(h, rec)
    if live is None:
        return {"ok": False, "why": "kill live : %s" % why, "bras": bras}
    off = replay(h, rec)
    mut = replay(h, rec, mutate="NOPORT")
    return {"ok": True, "why": None, "bras": bras,
            # Le re-armement n'est attendu QUE sur la victime tauntee : c'est ce qui fait des deux
            # bras un temoin NON degenere (ils different par UN conjoint et rendent DEUX verdicts).
            "attendu": (not a.non_taunte),
            "avant": rec["avant"], "live": live, "offline": off, "noport": mut,
            "_h": h, "_rec": rec}


def run(a, rpc, Board, Harness, seed_bc) -> int:
    rid, sf = build(a, seed_bc)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        m = mesurer(a, rpc, Board, Harness, rid)
        if not m.get("ok"):
            print("REFUS (%s)" % m.get("why"))
            return 2
        h, rec = m["_h"], m["_rec"]
        live, off, mut = m["live"], m["offline"], m["noport"]
        if a.verbose:
            dg = replay(h, rec, mutate="DIAG")
            for t in (dg.get("espion") or []):
                print("    [espion] %s" % t)

        bras, attendu = m["bras"], m["attendu"]
        print("[%s] avant   : %s" % (bras, rec["avant"]))
        print("[%s] LIVE    : mort=%s actif=%s (voie: %s)"
              % (bras, live["mort"], live["apres"], live["voie"]))
        print("[%s] OFFLINE : mort=%s actif=%s (per_hit=%s)"
              % (bras, off["mort"], off["apres"], off["per_hit"][:4]))
        print("[%s] NOPORT  : actif=%s" % (bras, mut["apres"]))

        rc = 0
        if not live["mort"]:
            print("REFUS : la cible n'est PAS morte du coup -- augmenter --dmg / baisser --hp-target")
            return 2
        if not off["mort"]:
            print("REFUS : la cible n'est pas morte OFFLINE -- les deux cotes ne jouent pas le meme "
                  "coup, l'accord sur l'actif ne prouverait rien")
            return 2
        nat_usable = (live["apres"] or {}).get("usable")
        port_usable = (off["apres"] or {}).get("usable")
        if nat_usable is None or port_usable is None:
            print("REFUS : etat d'actif NON MESURE (natif=%s port=%s)" % (nat_usable, port_usable))
            return 2
        if bool(nat_usable) != bool(attendu):
            print("REFUS : le NATIF ne fait pas ce que le bras attend (usable=%s, attendu=%s) -- "
                  "le regime ne discrimine pas" % (nat_usable, attendu))
            return 2
        if bool(port_usable) != bool(nat_usable):
            print("FAUTE : port usable=%s != natif usable=%s" % (port_usable, nat_usable))
            _nommer_l_etage(h, rec)
            rc |= 1
        # ⚠ LA CONTRE-EPREUVE SE COMPARE AU PORT, PAS A UNE CONSTANTE. Ecrite d'abord comme
        # `mut.usable is False`, elle rendait `mord: True` alors que le port NE FIRAIT PAS -- donc
        # elle << mordait >> sur un port et un mutant STRICTEMENT IDENTIQUES : un faux vert. Ce qui
        # prouve quelque chose, c'est que retirer l'entree du registre CHANGE l'observable.
        if not a.non_taunte:
            mord = (mut["apres"] or {}).get("usable") != (off["apres"] or {}).get("usable")
            print("[%s] mord   : %s (port=%s vs NOPORT=%s)"
                  % (bras, mord, (off["apres"] or {}).get("usable"),
                     (mut["apres"] or {}).get("usable")))
            if not mord:
                print("FAUTE : NOPORT rend le MEME observable que le port -- l'accord ne prouve rien")
                rc |= 1
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def _nommer_l_etage(h, rec):
    """Quand le port diverge, DIRE quel conjoint tombe -- pas laisser re-diagnostiquer."""
    dg = replay(h, rec, mutate="DIAG")
    for t in (dg.get("espion") or []):
        if t.get("verdict"):
            continue
        manquants = [k for k in ("owner_is_actor", "taunt_sur_victime", "buff_sur_tueur")
                     if not t.get(k)]
        print("    [etage] conjoint(s) FAUX cote port : %s -- trace %s" % (manquants, t))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--target-unit", default="necroWarden")
    ap.add_argument("--other-unit", default="necroOverlord")
    ap.add_argument("--third-unit", default="necroSpyder",
                    help="le SURVIVANT : il ne fait rien, il empeche seulement la bataille de se "
                         "TERMINER au kill (sans lui, `decisionView` rend `units: []` et l'etat "
                         "d'actif n'est plus publie par aucun canal).")
    ap.add_argument("--hp-target", type=int, default=20000)
    ap.add_argument("--dmg", type=int, default=400000,
                    help="stat Damage de Hascule (--unit-stat) : ses coups d'arme doivent TUER "
                         "un ennemi a --hp-target PV en UNE attaque normale.")
    ap.add_argument("--non-taunte", action="store_true", dest="non_taunte",
                    help="BRAS NEGATIF : le kill porte sur l'ennemi JAMAIS taunte -- le conjoint "
                         "`HasEffect(Target, 27)` doit REFUSER le re-armement, des deux cotes.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    print("== #911-r1 DaemonicPatrons_Finale (triggered %d) -- board %s seed %s%s"
          % (FINALE_TRIGGERED, a.board, a.seed, " [NON TAUNTE]" if a.non_taunte else ""))

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    seed_bc = seed_bc_avec_hascule()
    try:
        rc = run(a, rpc, Board, ChargeRegimeHarness, seed_bc)
    finally:
        Path(seed_bc).unlink(missing_ok=True)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

