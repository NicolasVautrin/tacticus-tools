"""#576 -- confront LIVE de `1175 BloodChalice` (`bloodSanguinary`, UNIQUE porteur).

FOYER UNIQUE de la mesure : le montage ET les criteres vivent ici ; `tests/engine/runner/
test_576_blood_chalice_live.py` appelle `mesure()` et ne duplique rien.

CE QUE CE PROBE CHERCHE A CASSER. L'audit classe 1175 en `HEAL` et le volet 1 n'est PAS un soin :
c'est `ChangeStat(..., mode 0 = SetAbsolute, ...)`. La signature qui separe SET de HEAL n'est
visible que sur une cible **AU-DESSUS** du seuil -- un soin la laisserait tranquille, un SET la fait
DESCENDRE. Un montage qui n'aurait que des blesses rendrait le MEME verdict pour les deux lectures :
c'est le regime degenere, et il est explicitement evite ici.

⚠ L'ETAGE VOISIN QUI A FAILLI FAIRE FITTER UN SCALAIRE, et pourquoi la mesure est construite ainsi.
Le porteur possede le PASSIF `SanguinaryPriest` (`TriggeredAbilityType` 1296), qui est **NON PORTE**
cote Python. Son
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateBehaviour` est

    Heal( Owner@DSLSelectors+0x30,
          AdjacentFriends(Owner, unique, 3) op_Subtraction MechanicalUnits(.),
          RandomAmount( GetVariableForLevel(0x20 hpToHeal), GetVariableForLevel(0x47 maxHpToHeal) ),
          HealBehaviourOptions.**ForRegenerate** )

-- c'est-a-dire un soin ALEATOIRE sur EXACTEMENT le meme ensemble que `BloodChalice.GetTargets()`.
Mesure : le live rend `hp_apres = floor(hp_max * healthPct/100) + 2049`, et le `2049` n'est PAS du
1175. Un critere sur la valeur ABSOLUE aurait donc soit rougi a tort, soit ete « ajuste » de 2049 --
un fit de scalaire. La mesure ISOLE l'etage a la place : `hp_max` VARIE sur trois runners, et c'est
l'ECART `hp_apres - floor(hp_max * healthPct/100)` qui doit rester CONSTANT. Un `healthPct` faux,
une base fausse (courant au lieu de MAXIMUM) ou un arrondi faux le feraient VARIER avec `hp_max`.

CINQ ETAGES :

  E1 SET ISOLE   trois `hp_max` distincts -> l'ecart au `floor(hp_max*healthPct/100)` PORTE est
                 CONSTANT, et il tombe dans la plage `[hpToHeal, maxHpToHeal]` du passif, DERIVEE du
                 gameconfig. C'est l'etage qui etablit la base MAXIMUM, le pct et l'arrondi.
  E2 SET vs HEAL allie adjacent non-mecanique **PLEIN** -> il DESCEND. Refute la lecture « HEAL ».
  E3 EXCLUSION   allie adjacent **MECANIQUE** et allie non-mecanique **HORS PORTEE** : intacts,
                 aucun effet. Regime ou le natif REFUSE, monte a cote d'un regime ou il accepte.
  E4 EFFETS      1368 `BloodChalice_HealOnAttack` pose sur les cibles ; 1369
                 `BloodChalice_ExtraPiercing` **ABSENT** de `decisionView` -- c'est un RESULTAT, pas
                 un echec : `readEffectsByUnit` DROPPE les entrees `IsActive == 0`, et la
                 `CreateActiveCondition = IsCharging(Owner, Target)` de 1369 est FAUSSE hors charge.
                 C'est la CONFIRMATION LIVE du residu #576-r1 (le port sur-accorde sur ce terme).
  E5 ARRONDI     `roundingRule = 2` = Floor. Le departage exige `hp_max = 3 (mod 4)` : alors
                 `hp_max/2` tombe sur un demi dont l'entier PAIR est au-dessus, donc Floor et
                 half-to-even different d'exactement 1. L'etage compare la DIFFERENCE de deux
                 `hp_apres` (le soin passif s'annule dans la difference -- mesure : il est identique
                 a seed fixe sur les trois runners).

⚠ NON CONFRONTE, et nomme plutot que tu : le troisieme filtre de `GetTargets`,
`UnitsWithoutTrait(0x19 = UnitTrait.Immune)`. **AUCUNE** des 99 unites du pool ne porte ce trait
(mesure), donc aucun montage ne peut le faire mordre. Le terme est porte parce que le decompile
l'ecrit ; il n'est pas confronte.

Usage :
    python probe_576_blood_chalice_live.py --keep
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gameconfig as GC                                                    # noqa: E402
import probe_112_darkangels as PR                                          # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402

LOGS = HERE.parents[1] / "logs"
BC = int(ActiveAbilityType.BloodChalice)                # 1175
EF_HEAL = int(EffectType.BloodChalice_HealOnAttack)     # 0x558 = 1368
EF_PIERCE = int(EffectType.BloodChalice_ExtraPiercing)  # 0x559 = 1369

PORTEUR = "bloodSanguinary"     # UNIQUE porteur de 1175
HAUT = "bloodDeathCompany"      # allie ADJACENT non-mecanique, PLEIN -> E1/E2/E5
MECA = "necroSpyder"            # allie ADJACENT **MECANIQUE**        -> E3 (exclu)
LOIN = "bloodMephiston"         # allie non-mecanique HORS PORTEE     -> E3 (exclu)
ENNEMI = "necroWarden"

#: `hp_max` des trois runners d'E1. Le TROISIEME vaut `3 (mod 4)` : c'est la SEULE classe de reste
#: qui separe Floor de half-to-even a `healthPct = 50` (mod 1 et mod 2 rendent la meme valeur), et
#: c'est ce qui rend E5 discriminant. Les deux autres bornent la droite de regression d'E1.
HP_MAX = (20001, 30001, 20003)

#: ⚠ `bloodIntercessor` a ete ECARTE du montage apres MESURE : il porte le trait `TeleportStrike`,
#: donc il arrive en bataille avec `TeleportStrike_TeleportingIn` (1035) et `unitFlags [17]` -- il
#: n'est pas encore POSE, aucune ability ne le voit. Le montage rendait alors « 1 seule cible » et
#: se lisait comme un bug de `GetTargets`. Ce n'en etait pas un.


def _r(sid, m, b, t=90):
    return PR.rpc(sid, m, b, t)


def _run(args) -> int:
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False).returncode


def _uid(dv, visual):
    for u in (dv.get("units") or []):
        if u.get("visualId") == visual:
            return u.get("id")
    return None


def _hp(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return None if u is None else u.get("hp")


def _hp_max(sid, rid):
    """`healthMax` PAR UNITE : il vit dans `combatSnapshot`, PAS dans `decisionView` (qui ne publie
    que le `hp` COURANT). Deux canaux, deux appels -- on lit chacun la ou il est."""
    sn = _r(sid, "combatSnapshot", {"runnerId": rid}, 150)
    return {u.get("entityId"): u.get("healthMax") for u in (sn.get("units") or [])}


def _carriers(dv, effect_type):
    """Ids portant `effect_type` -- `decisionView.effects` est le GROUND TRUTH (#100). ⚠ Ce canal
    DROPPE les entrees `IsActive == 0` : une absence peut vouloir dire « pose mais INERTE »."""
    return sorted(u["id"] for u in (dv.get("units") or [])
                  if any(e.get("effectType") == effect_type for e in (u.get("effects") or [])))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="#576 : confront live de 1175 BloodChalice")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=576576)
    ap.add_argument("--state-file", default="rs_576_blood_chalice.json")
    #: Le porteur au centre, deux allies sur des voisins hex REELS de sa tuile
    #: (`hexgeo.neighbors(3,3) = [(3,4),(3,2),(4,3),(4,2),(2,3),(2,2)]`) et un allie au loin. Les
    #: positions sont FORCEES : on ne subit jamais la geometrie de spawn.
    ap.add_argument("--porteur", default="3,3")
    ap.add_argument("--haut", default="4,3")
    ap.add_argument("--meca", default="2,3")
    ap.add_argument("--loin", default="0,0")
    ap.add_argument("--ennemi", default="6,6")
    ap.add_argument("--keep", action="store_true")
    return ap


def seuil_pct() -> int:
    """`ConfigConst(0x4f) = AbilityConstantType.healthPct` -- DERIVE du gameconfig, jamais fige."""
    return int(((GC.ability("BloodChalice") or {}).get("constants") or {})["healthPct"])


def attendu_set(hp_max: int) -> int:
    """CE QUE LE PORT CALCULE : `PercentageOf(StatAmount(It, HEALTH, MAXIMUM),
    ConfigConst(healthPct), **2 = Floor**)`. Le critere est couple a CETTE valeur, pas au seul
    oracle natif -- si le port change d'arrondi, de base ou de pct, E1 et E5 rougissent."""
    import math
    return math.floor(Fraction(int(hp_max) * seuil_pct(), 100))


def attendu_set_half_even(hp_max: int) -> int:
    """CONTRE-VALEUR d'E5 : ce que rendrait `roundingRule = 0` (l'arrondi de `BlackRage`)."""
    return round(Fraction(int(hp_max) * seuil_pct(), 100))


def plage_regen_passif(multiplier_pct: int) -> "tuple[int, int]":
    """Plage du `RandomAmount(GetVariableForLevel(0x20 hpToHeal), GetVariableForLevel(0x47
    maxHpToHeal))` de `SanguinaryPriestAbility$$CreateBehaviour` -- l'ETAGE VOISIN non porte.
    DERIVEE du gameconfig au niveau 50 et du multiplier de rarete LU sur l'unite. Sert de BORNE a
    E1 : l'ecart residuel doit y tomber, sinon ce n'est pas le passif qu'on observe."""
    from engine.entities.effects.magnitude import ability_var
    lo = ability_var("SanguinaryPriest", "hpToHeal", 50, multiplier_pct=multiplier_pct)
    hi = ability_var("SanguinaryPriest", "maxHpToHeal", 50, multiplier_pct=multiplier_pct)
    return (int(lo), int(hi))


def _mesure_set(a, hp_max: int, suffixe: str) -> "tuple[int, int, int] | None":
    """UN runner LEGER (porteur + une cible PLEINE) : rend `(hp_max_live, hp_avant, hp_apres)` de la
    cible apres le cast. C'est la brique d'E1/E5 : on la rejoue a `hp_max` variable."""
    p = LOGS / ("rs_576_set_%s.json" % suffixe)
    LOGS.mkdir(parents=True, exist_ok=True)
    _run(["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
          "--p-units", ",".join([PORTEUR, HAUT]), "--a-units", ENNEMI,
          "--place", "%s:%s" % (PORTEUR, a.porteur),
          "--place", "%s:%s" % (HAUT, a.haut),
          "--a-place", "%s:%s" % (ENNEMI, a.ennemi),
          "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (HAUT, hp_max, hp_max),
          "--state-file", str(p)])
    if not p.exists():
        return None
    rid = int(json.loads(p.read_text(encoding="utf-8"))["runnerId"])
    sid = INV._session_id()
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        cid, tid = _uid(dv, PORTEUR), _uid(dv, HAUT)
        if cid is None or tid is None:
            return None
        hm = _hp_max(sid, rid).get(tid)
        avant = _hp(dv, tid)
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": cid, "abilityType": BC}}, 150)
        dv2 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        return (hm, avant, _hp(dv2, tid))
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def mesure(a) -> "dict | None":
    """Monte les runners, joue les cinq etages, rend `{libelle: bool}` -- ou `None` si le MONTAGE
    n'aboutit pas. `None` = PAS MESURE, ce qui n'est PAS un verdict sur le port."""
    verdicts = {}
    pct = seuil_pct()
    print("[576] healthPct (ConfigConst 0x4f, DERIVE du gameconfig) = %d" % pct)

    # ---------------- E1 + E5 : le SET, ISOLE par variation de `hp_max` ----------------------
    obs = {}
    for i, hm_demande in enumerate(HP_MAX):
        r = _mesure_set(a, hm_demande, "%d" % i)
        if r is None:
            print("[576] PAS MESURE : build KO pour hp_max=%d" % hm_demande)
            return None
        hm, avant, apres = r
        if hm is None or apres is None:
            print("[576] PAS MESURE : hp/healthMax non publies pour hp_max=%d" % hm_demande)
            return None
        obs[int(hm)] = (int(avant), int(apres))
        print("[576] hp_max=%-6d avant=%-6d apres=%-6d | SET porte=%-6d | ecart=%d"
              % (hm, avant, apres, attendu_set(hm), apres - attendu_set(hm)))

    ecarts = {hm: v[1] - attendu_set(hm) for hm, v in obs.items()}
    ecart_constant = len(set(ecarts.values())) == 1
    lo, hi = plage_regen_passif(180)          # multiplier LU sur l'unite (cf. `unitConfig`)
    dans_plage = all(lo <= e <= hi for e in ecarts.values())
    print("[576] E1 ecarts=%r constant=%s | plage RandomAmount du passif SanguinaryPriest=[%d,%d]"
          % (ecarts, ecart_constant, lo, hi))
    verdicts["E1 set isole : l'ecart au SET porte est CONSTANT sur 3 hp_max, et dans la plage "
             "du passif"] = bool(ecart_constant and dans_plage and len(obs) == len(HP_MAX))

    # E5 -- la DIFFERENCE de deux `hp_apres` annule le soin passif (constant a seed fixe) et ne
    # laisse que la difference des SET. Floor et half-to-even ne s'y separent que si `hp_max` est
    # `3 (mod 4)` ; l'etage DIT quand il n'est pas discriminant plutot que de rendre un faux vert.
    ref, alt = HP_MAX[0], HP_MAX[2]
    hm_ref = next((h for h in obs if abs(h - ref) <= 1), None)
    hm_alt = next((h for h in obs if abs(h - alt) <= 1), None)
    if hm_ref is None or hm_alt is None or hm_ref == hm_alt:
        print("[576] E5 NON DISCRIMINANT : les deux runners n'ont pas des hp_max distincts")
        verdicts["E5 arrondi : le live suit Floor (roundingRule 2), pas le half-to-even"] = False
    else:
        d_live = obs[hm_alt][1] - obs[hm_ref][1]
        d_floor = attendu_set(hm_alt) - attendu_set(hm_ref)
        d_half = attendu_set_half_even(hm_alt) - attendu_set_half_even(hm_ref)
        disc = d_floor != d_half
        print("[576] E5 : d_live=%d d_floor=%d d_half-to-even=%d (discriminant=%s)"
              % (d_live, d_floor, d_half, disc))
        if not disc:
            print("[576] E5 NON DISCRIMINANT : hp_max=%d ne separe pas les deux arrondis -- "
                  "l'etage ne prouve RIEN dans ce regime" % hm_alt)
        verdicts["E5 arrondi : le live suit Floor (roundingRule 2), pas le half-to-even"] = bool(
            disc and d_live == d_floor)

    # ---------------- E2 + E3 + E4 : un montage COMPLET, un seul cast -------------------------
    state_file = LOGS / a.state_file
    rc = _run(["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
               "--p-units", ",".join([PORTEUR, HAUT, MECA, LOIN]), "--a-units", ENNEMI,
               "--place", "%s:%s" % (PORTEUR, a.porteur),
               "--place", "%s:%s" % (HAUT, a.haut),
               "--place", "%s:%s" % (MECA, a.meca),
               "--place", "%s:%s" % (LOIN, a.loin),
               "--a-place", "%s:%s" % (ENNEMI, a.ennemi),
               # HAUT est PLEIN : c'est le regime qui separe SET de HEAL. MECA et LOIN sont
               # BLESSES : un SET les remonterait, un refus les laisse -- l'ecart est visible.
               "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (HAUT, HP_MAX[0], HP_MAX[0]),
               "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (MECA, HP_MAX[0],
                                                                   HP_MAX[0] // 4),
               "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (LOIN, HP_MAX[0],
                                                                   HP_MAX[0] // 4),
               "--state-file", str(state_file)])
    if not state_file.exists():
        print("[576] PAS MESURE : build KO du montage complet (rc=%d)" % rc)
        return None
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    sid = INV._session_id()
    try:
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ids = {k: _uid(dv0, k) for k in (PORTEUR, HAUT, MECA, LOIN)}
        if any(v is None for v in ids.values()):
            print("[576] PAS MESURE : unite(s) absente(s) -> %r" % (ids,))
            return None
        hm = _hp_max(sid, rid)
        avant = {k: _hp(dv0, v) for k, v in ids.items()}
        res = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ids[PORTEUR], "targetId": ids[PORTEUR],
            "abilityType": BC}}, 150)
        if not (res or {}).get("ok", True):
            print("[576] PAS MESURE : cast refuse -> %r" % (res,))
            return None
        dv1 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        apres = {k: _hp(dv1, v) for k, v in ids.items()}
        print("[576] avant=%r" % (avant,))
        print("[576] apres=%r" % (apres,))

        # E2 -- LE DISCRIMINANT : la cible PLEINE doit DESCENDRE, et atterrir AU-DESSUS du SET
        # porte (le passif la remonte un peu). Un HEAL, lui, ne la ferait pas bouger du tout.
        set_porte = attendu_set(hm.get(ids[HAUT]) or 0)
        descendu = (apres[HAUT] is not None and avant[HAUT] is not None
                    and int(apres[HAUT]) < int(avant[HAUT]))
        verdicts["E2 set-haut : allie adjacent PLEIN DESCEND (mode 0 SetAbsolute, PAS un heal)"] = (
            bool(descendu and set_porte and int(apres[HAUT]) >= set_porte))
        print("[576] E2 : %s -> %s (SET porte=%s, descendu=%s)"
              % (avant[HAUT], apres[HAUT], set_porte, descendu))

        # E3 -- REGIME OU LE NATIF REFUSE. ⚠ Le passif `SanguinaryPriest` vise le MEME ensemble
        # (`AdjacentFriends - MechanicalUnits`) : le MECANIQUE en est exclu comme ici, et le LOIN
        # aussi. Les deux doivent donc etre STRICTEMENT intacts, PV compris.
        intacts = all(apres[k] == avant[k] for k in (MECA, LOIN))
        sans_effet = all(ids[k] not in _carriers(dv1, EF_HEAL)
                         and ids[k] not in _carriers(dv1, EF_PIERCE) for k in (MECA, LOIN))
        verdicts["E3 exclusion : mecanique adjacent et non-mecanique hors portee INTACTS"] = (
            bool(intacts and sans_effet))
        print("[576] E3 : meca %s->%s | loin %s->%s | sans_effet=%s"
              % (avant[MECA], apres[MECA], avant[LOIN], apres[LOIN], sans_effet))

        # E4 -- 1368 sur les cibles ; 1369 ABSENT (inactif hors charge).
        heal_c, pierce_c = _carriers(dv1, EF_HEAL), _carriers(dv1, EF_PIERCE)
        print("[576] E4 : porteurs 1368=%r | 1369=%r (attendu 1369 VIDE hors charge)"
              % (heal_c, pierce_c))
        verdicts["E4 effets : 1368 pose sur la cible eligible et sur elle SEULE"] = (
            heal_c == [ids[HAUT]])
        # ⚠ CRITERE COUPLE AU RESIDU #576-r1, pas a une constante : `1369` est pose par le port
        # (feuille `AddStaticStatModifierEffect`) mais le NATIF le rend INACTIF hors charge
        # (`CreateActiveCondition = IsCharging`), et `readEffectsByUnit` droppe les inactifs. Si un
        # jour 1369 APPARAIT ici sans charge, c'est la lecture d'`IsCharging` qui serait fausse.
        verdicts["E4bis 1369 : ABSENT du canal actif hors charge (confirme IsCharging, #576-r1)"] = (
            pierce_c == [])
    finally:
        if not a.keep:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            except Exception:
                pass
    return verdicts


def main() -> int:
    a = _parser().parse_args()
    v = mesure(a)
    if v is None:
        return 99                                      # PAS MESURE (ni echec ni feu vert)
    for k, ok in v.items():
        print("[576] %-78s %s" % (k, "OK" if ok else "ECHEC"))
    return 0 if all(v.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
