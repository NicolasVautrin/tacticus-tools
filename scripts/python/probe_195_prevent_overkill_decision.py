#!/usr/bin/env python
"""Probe #195 / R34-b -- `PreventOverkill` sur la face DECISION.

CE QUI EST ETABLI AU DECOMPILE (build gqfc5mff6c, lecture VERBATIM) -- le flag entre par DEUX
portes distinctes, et le port passait `0` EN DUR aux deux :

  ETAGE 1 -- `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`
    (signature `methods.tsv` : ..., defender:IEntity, attacker:IEntity, isCrit, currentHealth,
     currentArmor, initialHealth, previousHitsDeniedDamage, isForcedOverkill, minimumHealth) :

        uVar1 = UnitExtensions.HasFlag(defender, 0x13);
        uVar1 = IsOverkill(initialHealth, accum, isCrit, isForcedOverkill, uVar1,
                           cfg@+0x30, cfg@+0x34, minimumHealth);
        ApplyResilientTraitDamageLimit(min, ..., uVar1);  ApplyResilientTraitDamageLimit(max, ..., uVar1);

    => c'est le `suppress` de `compute_prediction_overkill`. Consequence : le cap Resilient.

  ETAGE 2 -- `DamagePredictionResult$$WillBeOverkill` / `$$MightBeOverkill` :

        IsOverkill(result@+0x00, <borne>, <0 | MightCrit@+0xb1>, ForceOverkill@+0xb2,
                   **result@+0xb3**, HasValue(result@+0xb4), Value(result@+0xb4), null)

    => 5e argument `isPreventOverkill` = `DamagePredictionResult.PreventOverkill@+0xb3`
    (= event+0xBB cote decodeur, expose #190). Consequence : l'utilite `OverkillUnit` (37).

Le poseur du flag est UNIQUE : `FuelledByFury_BlockOverkillEffect$$ApplyInternal` ->
`UnitFlagsComponent.Add(target, 0x13)` (`UnitFlag.PreventOverkill` = 19, `enums.tsv`), retire par
son `$$RevertInternal`. Porteur MESURE (#178) : `ultraTitus`, des le deploiement.

DEUX MESURES, ET LA PREMIERE EST LA PLUS IMPORTANTE :

  A. CANAL (`--part canal`) -- `preventOverkill` prend-il DEUX valeurs ? Un canal qui ne rend
     jamais que son defaut est INDISCERNABLE d'un canal mort, et aucun test d'egalite ne peut
     faire la difference. Meme runner, meme attaquant, DEUX cibles : `ultraTitus` (porteur) et
     `genesPrimus` (temoin). Sans deux valeurs distinctes, tout le reste est sans objet.

  B. UTILITE (`--part utility`) -- le terme vaut-il EXACTEMENT `PossibleOverkill` ? Regime
     LETAL SOUS LE SEUIL avec crit force (`PV <= rawMax < 2 x PV`, `rawMin < PV`) : `MightBeOverkill`
     y renvoie `isCritical` quand `isPreventOverkill` est FAUX, et `false` quand il est VRAI.
     On confronte `pairUtility` NATIF au terme degat du PORT nourri des MEMES events natifs
     (formule ISOLEE : meme feed des deux cotes, donc tout ecart est un gap de LOGIQUE), en
     variante AVEC et SANS la cle -- la variante SANS reproduit le port d'avant #195 sans avoir
     a revenir en arriere dans le code.
     Le temoin `genesPrimus` tourne le MEME montage : le flag y est faux, donc les deux variantes
     doivent coincider ET egaler le natif (garde de non-regression).

Blocage a zero (`--block-target 0,0`) : `ultraTitus` porte `BeastSlayer`, et le scenario de block
`list[0]@0x50` n'est PAS expose par le decodeur (`_fields_from_native_event` le recalcule depuis un
`block_amount` qui vaut 0 par defaut). Sans ca, `killSure` divergerait pour une raison ETRANGERE au
terme mesure.

ASCII only (cp1252). Usage :
  python probe_195_prevent_overkill_decision.py --part canal
  python probe_195_prevent_overkill_decision.py --part utility
  python probe_195_prevent_overkill_decision.py --part all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from engine.weights import load as load_weights                             # noqa: E402
from engine.utilities import damage_composite                               # noqa: E402
from engine.utilities.damage import might_be_overkill, will_be_overkill     # noqa: E402
from engine_agreement_stages import _fields_from_native_event               # noqa: E402
from probe_r34_overkill_decision import (build, view, by_visual, place_ring,  # noqa: E402
                                         playbook_events, native_pair_utility,
                                         _hpmax_by_id, _f, NORMAL_ATTACK)

CARRIER = "ultraTitus"        # porte `FuelledByFury_BlockOverkill` (flag 0x13) des le deploiement
CONTROL = "genesPrimus"       # temoin sans le flag, memes PV tunes
# Attaquant SANS le trait `ThrillSeekers` (1056) : son rider « defeats an enemy with a Crit ->
# always overkilled » forcerait `isForceOverkill` et rendrait l'observation AMBIGUE.
ATTACKER = "ultraInceptorSgt"
FILLER_P = "astraBullgryn"    # 2e unite de mon camp (sans elle l'attaque finit mon tour)
FILLER_A = "necroWarden"      # 2e ennemi : tuer la cible ne doit pas terminer la bataille


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# -- GARDE D'INSTRUMENT (#268) ---------------------------------------------------------------
# Les DEUX mesures de ce probe lisent des champs de `DamagePredictionResult` decodes par
# `frida/hooks/features/ai-step/playbook-predict.ts` a des offsets FIGES sur un build ancien.
# Sur `rnca9r7q6c` ces offsets sont PERIMES et le decodeur rend du GARBAGE : bornes RAW a 0,
# `mightCrit` hors {0,1}, `probability` a 0. Sans cette garde, l'echec accuse le MONTAGE (« regime
# letal-sous-le-seuil inatteignable : bornes [0,0] ») alors que la faute est a l'INSTRUMENT --
# et, pire, il partait en `pytest.skip`, donc en VERT.
_CHANNEL_DEAD = (
    "CANAL MORT (#268) -- le decodeur du struct de prediction "
    "(`frida/hooks/features/ai-step/playbook-predict.ts`) lit des offsets PERIMES sur le build "
    "courant. Offsets re-derives au decompile (`DamagePredictionResult`, taille 176) : "
    "CurrentHealth@0x00, HealthDamage.Min@0x1c / .Max@0x20 (etaient 0x60/0x64), "
    "MightCrit@0x8a (etait 0xb1), ForceOverkill@0x8b (etait 0xb2), PreventOverkill@0x8c "
    "(etait 0xb3). Le fix vit dans les hooks et exige une REINJECTION -- cf. "
    "docs/rl/case-268-decodeur-prediction-perime.md")


def event_channel_health(ev: dict) -> dict:
    """SENTINELLES d'un `ProbableDamageEvent` decode. Trois faits que le natif ne peut PAS produire
    et qui prouvent donc, seuls, que la lecture a derape :
      * `mightCrit` est un `bool` -> toute valeur hors {0,1} est du garbage ;
      * `probability` d'un event rendu par `MakeDamagePredictions` n'est jamais nulle ;
      * une paire au CONTACT ne peut pas annoncer `mightKillDmg == 0` (borne haute de degat).
    Rend `{"alive": bool, "why": str}`."""
    if not ev:
        return {"alive": False, "why": "aucun event natif pour la paire"}
    why = []
    if int(ev.get("mightCrit") or 0) not in (0, 1):
        why.append("mightCrit=%s hors {0,1}" % ev.get("mightCrit"))
    if not (ev.get("probability") or 0):
        why.append("probability=%s (nulle)" % ev.get("probability"))
    if int(ev.get("mightKillDmg") or 0) <= 0:
        why.append("mightKillDmg=%s alors que la paire est au contact" % ev.get("mightKillDmg"))
    return {"alive": not why, "why": " ; ".join(why) or "sentinelles OK"}


def _setup(sid, sf, seed, a_units, hp_target=None, crit_spec="0,0"):
    """Build + GEOMETRIE DRIVEE : l'ATTAQUANT au centre, tout le reste sur son ring 1 -> il
    atteint CHAQUE cible en melee (sinon la prediction rend un degat nul et on compare deux
    choses incomparables)."""
    rid = build(sf, seed, (ATTACKER, FILLER_P), a_units, hp_target=hp_target,
                crit_spec=crit_spec, no_ai=True, block_target="0,0")
    dv = view(sid, rid)
    ids = {}
    for v in (ATTACKER, FILLER_P) + tuple(a_units):
        u = by_visual(dv, v)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        ids[v] = int(u["id"])
    place_ring(sid, rid, ids, ATTACKER, (3, 4))
    return rid, ids


def _main_event(sid, rid, att_id, tgt_id):
    evs = playbook_events(sid, rid, att_id, tgt_id)
    return evs, next((e for e in evs if e.get("targetId") == tgt_id), None)


# --------------------------------------------------------------------------------------------
# A. CANAL -- `preventOverkill` prend-il DEUX valeurs ?
# --------------------------------------------------------------------------------------------

def run_canal(seed: int = 19501, state_file=None, keep=False, verbose=True) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "p195canal.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    out = {}
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed, (CARRIER, CONTROL), hp_target=400)
        for vis in (CARRIER, CONTROL):
            evs, main = _main_event(sid, rid, ids[ATTACKER], ids[vis])
            if main is None:
                out[vis] = {"error": "aucun event natif pour la paire"}
                continue
            health = event_channel_health(main)
            out[vis] = {"preventOverkill": main.get("preventOverkill"),
                        "mightCrit": main.get("mightCrit"),
                        "forceOverkill": main.get("forceOverkill"),
                        "hp": main.get("hpBefore"),
                        "raw_min": main.get("willKillDmg"), "raw_max": main.get("mightKillDmg"),
                        "events": len(evs), "channel": health}
            if verbose:
                print("[195A] %-16s preventOverkill=%r  (mightCrit=%r forceOverkill=%r)"
                      % (vis, out[vis]["preventOverkill"], out[vis]["mightCrit"],
                         out[vis]["forceOverkill"]))
                print("[195A]   canal : %s (%s)" % (health["alive"], health["why"]))
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    a, b = out.get(CARRIER) or {}, out.get(CONTROL) or {}
    vals = {a.get("preventOverkill"), b.get("preventOverkill")}
    out["distinct_values"] = sorted(v for v in vals if v is not None)
    out["ok"] = bool(a.get("preventOverkill") and not b.get("preventOverkill"))
    # Un canal DEROULE (sentinelles KO) ne peut RIEN prouver : il faut le dire AVANT d'accuser
    # le montage ou le port, sinon le rouge designe le mauvais coupable (#268).
    out["channel_alive"] = bool((a.get("channel") or {}).get("alive")
                                and (b.get("channel") or {}).get("alive"))
    out["channel_why"] = "; ".join(
        "%s: %s" % (k, (out.get(k) or {}).get("channel", {}).get("why"))
        for k in (CARRIER, CONTROL))
    if verbose:
        if out["ok"]:
            print("[195A] OK : DEUX valeurs distinctes -- le champ est un fait de la CIBLE,"
                  " vrai sur le porteur du flag 0x13 et faux sur le temoin.")
        elif not out["channel_alive"]:
            print("[195A] ECHEC INSTRUMENT : %s\n[195A]   sentinelles : %s"
                  % (_CHANNEL_DEAD, out["channel_why"]))
        else:
            print("[195A] ECHEC : valeurs vues = %s. Un canal qui ne rend que son defaut est"
                  " indiscernable d'un canal mort." % (out["distinct_values"],))
    return out


# --------------------------------------------------------------------------------------------
# B. UTILITE -- le terme vaut-il EXACTEMENT PossibleOverkill ?
# --------------------------------------------------------------------------------------------

def _port_pair_utility(events, hpmax_by_id, team_by_id, my_team, wt, *, with_prevent: bool):
    """Terme DEGAT du scoreur cote PORT, nourri des events NATIFS -- mirror de
    `CalculateUtilityFromDamageEvent` (`prob1 x prob2 x composite Damage(34)`).
    `with_prevent=False` reproduit EXACTEMENT le port d'AVANT #195 (cle absente ->
    `.get("preventOverkill")` falsy -> `isPreventOverkill = 0`), sans revenir en arriere
    dans le code ; `with_prevent=True` pose la cle depuis l'event natif."""
    u = 0.0
    for ev in events:
        t_id = ev.get("targetId")
        sign = -1.0 if (t_id is not None and team_by_id.get(t_id) == my_team) else 1.0
        prob = (ev.get("probability") or 1.0) * (ev.get("probMult") or 1.0)
        f = _fields_from_native_event(ev)
        if with_prevent:
            f["preventOverkill"] = bool(ev.get("preventOverkill"))
        else:
            f.pop("preventOverkill", None)
        u += sign * prob * damage_composite(f, hpmax_by_id.get(t_id), wt)
    return u


def _measure(sid, rid, ids, wt, victim) -> dict:
    dv = view(sid, rid)
    team_by_id = {int(u["id"]): u.get("team") for u in (dv.get("units") or [])}
    hpmax = _hpmax_by_id(sid, rid)
    evs, main = _main_event(sid, rid, ids[ATTACKER], ids[victim])
    nat = native_pair_utility(sid, rid, ids[ATTACKER], ids[victim])
    my_team = team_by_id.get(ids[ATTACKER])
    with_p = _port_pair_utility(evs, hpmax, team_by_id, my_team, wt, with_prevent=True)
    without = _port_pair_utility(evs, hpmax, team_by_id, my_team, wt, with_prevent=False)
    f_with, f_without = {}, {}
    if main is not None:
        f_with = _fields_from_native_event(main)
        f_with["preventOverkill"] = bool(main.get("preventOverkill"))
        f_without = dict(f_with)
        f_without.pop("preventOverkill", None)
    return {"events": len(evs),
            "hp": (main or {}).get("hpBefore"),
            "raw_min": (main or {}).get("willKillDmg"),
            "raw_max": (main or {}).get("mightKillDmg"),
            "prevent_overkill": bool((main or {}).get("preventOverkill")),
            "might_crit": bool((main or {}).get("mightCrit")),
            "force_overkill": bool((main or {}).get("forceOverkill")),
            "native_utility": nat, "port_with": with_p, "port_without": without,
            "port_might_overkill_with": bool(might_be_overkill(f_with)) if f_with else None,
            "port_might_overkill_without": bool(might_be_overkill(f_without)) if f_without else None,
            "port_will_overkill_with": bool(will_be_overkill(f_with)) if f_with else None}


def run_utility(victim: str, seed: int = 19601, state_file=None, keep=False,
                verbose=True) -> dict:
    """PASSE 1 (PV hauts, crit OFF) : lit les bornes RAW natives -> PV du regime = `rawMax`.
    PASSE 2 : rebuild a ces PV avec crit FORCE, puis confronte natif et port."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "p195util.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    wt = load_weights()
    a_units = (victim, FILLER_A)
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed + 500, a_units, hp_target=200000, crit_spec="0,0")
        _, main = _main_event(sid, rid, ids[ATTACKER], ids[victim])
        if main is None:
            return {"victim": victim, "error": "passe 1 : aucun event natif pour la paire"}
        health = event_channel_health(main)
        raw_min = int(main.get("willKillDmg") or 0)
        raw_max = int(main.get("mightKillDmg") or 0)
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    # L'INSTRUMENT d'abord : des bornes RAW a 0 sur une paire au CONTACT ne disent rien du roster
    # ni de la geometrie -- elles disent que le decodeur ne lit plus le bon champ (#268). Sans ce
    # tri, l'echec accuse le montage (« regime inatteignable »), ce qui envoie re-crafter un roster
    # pour un probleme qui n'est pas la.
    if not health["alive"]:
        return {"victim": victim, "channel": health,
                "error": "%s -- sentinelles : %s (bornes RAW lues [%d,%d])"
                         % (_CHANNEL_DEAD, health["why"], raw_min, raw_max)}
    hp = raw_max
    if not (raw_min < hp <= raw_max < 2 * hp):
        return {"victim": victim, "channel": health,
                "error": "regime letal-sous-le-seuil inatteignable : bornes RAW natives [%d,%d] "
                         "(il faut rawMin < rawMax pour qu'il existe des PV avec rawMin < PV "
                         "<= rawMax < 2 x PV)" % (raw_min, raw_max)}
    if verbose:
        print("[195B] %s : bornes RAW natives [%d,%d] => PV du regime = %d (2 x PV = %d)"
              % (victim, raw_min, raw_max, hp, 2 * hp))
    rid = None
    try:
        rid, ids = _setup(sid, sf, seed, a_units, hp_target=hp, crit_spec="100,1")
        m = _measure(sid, rid, ids, wt, victim)
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    m["victim"] = victim
    m["possible_overkill_weight"] = wt.overkill(definite=False)
    m["lethal_below_threshold"] = bool(
        m["raw_max"] is not None and m["hp"] is not None
        and m["hp"] <= m["raw_max"] < 2 * m["hp"] and m["raw_min"] < m["hp"])
    nat = m["native_utility"]
    m["delta_with"] = None if nat is None else nat - m["port_with"]
    m["delta_without"] = None if nat is None else nat - m["port_without"]
    if verbose:
        print("[195B] %-16s PV=%s raw=[%s,%s] preventOverkill=%s mightCrit=%s regime=%s"
              % (victim, m["hp"], m["raw_min"], m["raw_max"], m["prevent_overkill"],
                 m["might_crit"], m["lethal_below_threshold"]))
        print("[195B]   port MightBeOverkill : avec=%s  sans=%s   (WillBeOverkill avec=%s)"
              % (m["port_might_overkill_with"], m["port_might_overkill_without"],
                 m["port_will_overkill_with"]))
        print("[195B]   utilite NATIVE=%s   port AVEC=%s (ecart %s)   port SANS=%s (ecart %s)"
              % (_f(nat), _f(m["port_with"]), _f(m["delta_with"]),
                 _f(m["port_without"]), _f(m["delta_without"])))
    return m


def _verdict_utility(m: dict, expect_flag: bool, tol: float = 1e-6) -> tuple:
    """Rend (ok, motif). Sur le PORTEUR : le port AVEC doit rejoindre le natif, et le port SANS
    doit s'en ecarter d'EXACTEMENT `PossibleOverkill`. Sur le TEMOIN : les deux variantes
    coincident avec le natif (le fix ne doit rien deplacer la ou le flag est faux)."""
    if m.get("error"):
        return False, m["error"]
    if not m.get("lethal_below_threshold"):
        return False, "regime letal-sous-le-seuil non atteint"
    if bool(m.get("prevent_overkill")) is not expect_flag:
        return False, ("preventOverkill=%s alors que %s etait attendu"
                       % (m.get("prevent_overkill"), expect_flag))
    if m.get("native_utility") is None:
        return False, "pairUtility natif illisible"
    if abs(m["delta_with"]) > tol:
        return False, "port AVEC != natif (ecart %.6f)" % m["delta_with"]
    w = float(m["possible_overkill_weight"])
    if expect_flag:
        if not m.get("might_crit"):
            return False, "crit non force : le terme sous test est quiescent"
        if abs(abs(m["delta_without"]) - w) > 1e-3:
            return False, ("port SANS s'ecarte de %.4f, pas de PossibleOverkill (%.4f)"
                           % (m["delta_without"], w))
        return True, "port AVEC == natif ; port SANS s'ecarte d'exactement %.4f" % w
    if abs(m["delta_without"]) > tol:
        return False, "temoin : le port SANS diverge deja du natif (%.6f)" % m["delta_without"]
    return True, "temoin : les deux variantes egalent le natif (aucun deplacement)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=("all", "canal", "utility"), default="all")
    ap.add_argument("--seed", type=int, default=19501)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    out, ok = {}, True
    if a.part in ("all", "canal"):
        out["canal"] = run_canal(seed=a.seed, state_file=a.state_file, keep=a.keep)
        ok &= bool(out["canal"].get("ok"))
    if a.part in ("all", "utility"):
        for vis, expect in ((CARRIER, True), (CONTROL, False)):
            m = run_utility(vis, seed=a.seed + 100, state_file=a.state_file, keep=a.keep)
            good, why = _verdict_utility(m, expect)
            m["verdict_ok"], m["verdict"] = good, why
            out["utility_" + vis] = m
            ok &= good
            print("[195B] %-16s %s -- %s" % (vis, "OK" if good else "ECHEC", why))
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    print("VERDICT : " + ("OK" if ok else "ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
