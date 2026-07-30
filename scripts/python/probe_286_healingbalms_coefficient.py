#!/usr/bin/env python
"""Probe #286 -- DISCRIMINER le coefficient du terme custom de 1212 `HealingBalms_Heal`.

Le decompile tranche la FORME sans ambiguite :

    `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$CalculateCustomUtility`
      = `Fix64$$FastMul( Sum(Playbook<T>$$CalculateUtilityFromHealEvent), Fix64.<statics+0x30> )`
    gate par `EntityExtensions$$HasEffect(target, state, 0x5df = HealingBalms_ExtraCritDamage, 0)`

et `Fix64.<statics+0x30>` = `op_Division(One, Fix64(2))` = **Half**, ecrit par `FixMath.NET.Fix64$$.cctor`.
Comme `ComparablePlaybook<T>$$CalculateActionUtility` fait `u = custom + CalculateUtilityFromPredictions`,
l'utilite d'ACTION vaut `(1 + c) x U_heal` sur une cible NON buffee et `1.0 x U_heal` sur une cible
buffee, avec `c` = le coefficient a discriminer (`Half` au decompile).

CE QUE CE PROBE AJOUTE (residu #27-4d) : l'A/B causal retenu par la tranche 4d opposait deux cibles
d'ecart d'utilite de soin NUL -- n'importe quelle constante positive y aurait fait basculer le natif.
Ce probe monte le **deuxieme cas discriminant** : huit bras a ecart NON NUL, sur deux axes.

  bras | niveau | ratio r | cible A (BUFFEE) | cible B (non buffee) | choix natif attendu
  -----|--------|---------|------------------|----------------------|--------------------
   1   | haut   | 1.40    | u_A = U_A        | u_B = (1+c) U_B      | B  <=> c > r-1 = 0.40
   2   | haut   | 1.60    | u_A = U_A        | u_B = (1+c) U_B      | A  <=> c < r-1 = 0.60
   3   | bas    | 1.40    | idem, U divise par 4                    | B  <=> c > 0.40
   4   | bas    | 1.60    | idem, U divise par 4                    | A  <=> c < 0.60
   5-6 | haut   | 1.49 / 1.51     | idem                            | B / A
   7-8 | haut   | 1.4999 / 1.5001 | idem                            | B / A

  * les bras PINCES (7, 8) MESURENT le coefficient : `0.499894 < c < 0.500094`. Les marges d'utilite
    y valent ~0.0025 point contre un arrondi Fix64 de ~1e-8 -- serre, pas bruite ;
  * les bras 1-4 montrent la PROPORTIONNALITE : meme encadrement `0.40 < c < 0.60` a deux niveaux
    d'utilite separes d'un facteur 4, ce qu'un terme non proportionnel a `U` ne peut pas rendre ;
  * les bras 1 et 4 sont CONTRADICTOIRES pour un terme ADDITIF constant `k` : le bras 1 exige
    `k > 10.714` au niveau HAUT, le bras 4 exige `k < 3.516` au niveau BAS -> la forme "constante"
    est REFUTEE par la mesure, plus seulement par la lecture.

LEVIER DE PILOTAGE -- pourquoi il echappe aux deux pieges mesures par la tranche 4d :

  `U_heal` = `HealUtility` = `min(healAmount, missing) / (hpMax + 1) x 100`. En regime NON SATURE
  (`missing > healAmount`) le numerateur est CONSTANT : `U` ne depend plus que de **hpMax**. On pilote
  donc les deux niveaux et les deux ratios par les `Health` du seed BC (per-unit, exactement comme
  `rl_duel --hp-player` le fait globalement), en gardant TOUTES les cibles loin de la saturation.
  Consequence directe :
    - piege 1 ("piloter `missing` par les DEGATS est trop grossier") : `missing` n'entre plus dans
      `U`. Le soin RETARDE de l'effet `HealingBalms` (~4986) et les coups adverses ne DEPLACENT PLUS
      la mesure -- ils ne font que consommer de la marge de non-saturation, dimensionnee ici a >= 1x
      `healAmount` apres le cast qui pose le buff.
    - piege 2 (`pairUtility` peut rendre du CACHE perime) : chaque lecture est RECOUPEE avec l'etat de
      PV du meme instant (`observeBattle`) via l'identite `min(amt, missing)/(hpMax+1) x 100` ; toute
      valeur qui ne s'explique pas par l'etat lu est REJETEE (pas de re-lecture opportuniste).

Le buff `HealingBalms_ExtraCritDamage` n'a qu'un seul poseur (le cast de 1212 lui-meme) : le bras se
deroule donc en deux tours -- cast au tour N sur A, observation du CHOIX au tour N+1. Le caster est
FIGE (`Movement = 0`), ce qui ne lui laisse qu'UNE tuile candidate et fige le terme de tuile a une
constante commune aux deux options ; les cibles, elles, sont AMENEES au contact (`place_targets`).

Usage :
  python probe_286_healingbalms_coefficient.py --recon            # build + etat, aucune conclusion
  python probe_286_healingbalms_coefficient.py --arm 1            # un bras
  python probe_286_healingbalms_coefficient.py --all --json out.json
  python probe_286_healingbalms_coefficient.py --arm 7 --targets spaceStormcaller,spaceBlackmane \
      --board MC1_63 --seed 909 --tag _g1                         # controle de generalisation

ASCII only.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

import requests

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

HOST = "http://127.0.0.1:8765"
ABILITY = 1212                      # ActiveAbilityType.HealingBalms_Heal
GATE_EFFECT = "HealingBalms_ExtraCritDamage"        # EffectType 0x5df
CASTER_VIS = "spaceWolfPriest"      # Baldr -- seul porteur hero du passif HealingBalms
A_VIS = "spaceBlackmane"            # cible A : celle qu'on BUFFE
B_VIS = "spaceHound"                # cible B : jamais buffee
# Adversaire : `blackAbaddon` SEUL, et surtout PAS `blackTerminator` -- son `TeleportStrike` le fait
# apparaitre au contact quel que soit son `Movement`, ce qui rouvre des plans d'attaque pour le caster
# (mesure : au tour 2 le natif proposait `Move + NormalAttack(69)` au lieu du soin).
FOE_VIS = "blackAbaddon"
BOARD = "MC1_67"

# Stat `Damage` forcee du caster -> `HealAbility$$HealAmount` = attack x hits(3) = HEAL_AMOUNT.
# Choisie GRANDE pour que les PV max des cibles (qui portent le ratio) laissent une marge de
# non-saturation superieure a un soin complet + le soin retarde du passif.
CASTER_DAMAGE = 10000
CASTER_HITS = 3
HEAL_AMOUNT = CASTER_DAMAGE * CASTER_HITS           # 30000, verifie live contre `combatSnapshot`

# hpMax des cibles par bras : A fixe le NIVEAU, B fixe le RATIO r = (hpMaxB+1)/(hpMaxA+1).
# niveau haut : U_A = 100 x 30000 / 80001  = 37.4996...
# niveau bas  : U_A = 100 x 30000 / 320001 =  9.3750...
ARMS = {
    1: {"level": "haut", "r": 1.40, "hpA": 80000, "hpB": 112000, "expect": "B"},
    2: {"level": "haut", "r": 1.60, "hpA": 80000, "hpB": 128000, "expect": "A"},
    3: {"level": "bas", "r": 1.40, "hpA": 320000, "hpB": 448000, "expect": "B"},
    4: {"level": "bas", "r": 1.60, "hpA": 320000, "hpB": 512000, "expect": "A"},
    # Bras SERRES : ratios encadrant 1.5 d'a peine +-1 %. Ils resserrent l'encadrement a
    # 0.49 < c < 0.51 -- plus aucune valeur ronde autre que `Half` n'y survit. Les marges
    # d'utilite tombent a ~0.25 point, ce qui reste sept ordres de grandeur au-dessus de
    # l'arrondi Fix64 mesure (~1e-8) : le regime est serre, pas bruite.
    5: {"level": "haut", "r": 1.49, "hpA": 80000, "hpB": 119200, "expect": "B"},
    6: {"level": "haut", "r": 1.51, "hpA": 80000, "hpB": 120801, "expect": "A"},
    # Bras PINCE : le ratio ne s'ecarte plus de 1.5 que de ~1e-4. Marges d'utilite ~0.0025 point,
    # soit cinq ordres de grandeur au-dessus de l'arrondi Fix64 -- ce n'est plus une exclusion de
    # valeurs rondes, c'est une DETERMINATION de `c` a 1e-4 pres.
    7: {"level": "haut", "r": 1.49991, "hpA": 80000, "hpB": 119992, "expect": "B"},
    8: {"level": "haut", "r": 1.50011, "hpA": 80000, "hpB": 120008, "expect": "A"},
}
HP_START = 1000                     # PV courants des cibles : loin de la saturation
CASTER_HP = 200000                  # caster a PV PLEINS -> son propre soin vaut 0 (MaxFillUp)
FOE_DAMAGE = 1                      # frappe adverse rendue inoffensive (le bruit ne doit rien porter)
# PV adverses ENORMES : l'utilite de degat est un ratio `degat / (hpMax + 1)`, donc un adversaire a
# 10^8 PV rend toute attaque negligeable (~0.03) devant les utilites de soin mesurees ici (5 a 40).
# C'est la CEINTURE ; la BRETELLE est `Movement = 0` des deux cotes -- caster FIGE (une seule tuile
# candidate, donc terme de tuile rigoureusement COMMUN aux deux options) et adversaire FIGE (le tour
# adverse ne rapproche personne, donc aucun plan d'attaque n'apparait entre les deux tours).
FOE_HP = 100000000


def _session() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=20).json()["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 15).json()
    if "error" in r and "result" not in r:
        raise RuntimeError(f"{method}: {r['error']}")
    return r.get("result", r)


def base_seed_bc(out: Path) -> Path:
    """Seed BC augmente du porteur (`spaceWolfPriest` est hors catalogue capture)."""
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", CASTER_VIS,
                        "--out", str(out)], cwd=str(PYDIR), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if not out.exists():
        raise RuntimeError(f"catalog_inject KO: {p.stdout}\n{p.stderr}")
    return out


def unit_stat_spec(hp_a: int, hp_b: int) -> str:
    """Patch PER-UNIT (`rl_duel --unit-stat`) du BC **normalise** -- la normalisation
    (`buildNormalizedBC`) RECALCULE `Health`/`Damage` au rank cible, donc patcher le seed BC en
    amont ne sert a rien (mesure : PV du seed ecrases, 9035/9035 au lieu de 200000).

    * caster : `Damage` fixe (magnitude du soin = attack x hits), PV PLEINS (sa propre utilite de
      soin est alors nulle -- `FillUpStatComponent$$MaxFillUp` = 0 -> `ShouldExecute` refuse, donc
      le self-cast ne concurrence pas les deux cibles) et `ActiveAbilities` VIDE (retire
      `RitesOfMorkai` ; 1212 est GRANTED par le passif `HealingBalms`, donc conserve) ;
    * cibles : `Health` = LE levier de la mesure, `RemainingHealth` bas = regime non sature ;
    * adverses : `Damage` = 1 -- le tour adverse ne deplace alors rien de mesurable.
    """
    caster = (f"{CASTER_VIS}:Damage={CASTER_DAMAGE},Health={CASTER_HP},"
              f"RemainingHealth={CASTER_HP},ActiveAbilities=[],Movement=0")
    a = f"{A_VIS}:Health={hp_a},RemainingHealth={HP_START}"
    b = f"{B_VIS}:Health={hp_b},RemainingHealth={HP_START}"
    foes = ";".join(f"{v}:Damage={FOE_DAMAGE},Health={FOE_HP},RemainingHealth={FOE_HP},Movement=0"
                    for v in FOE_VIS.split(","))
    return ";".join([caster, a, b, foes])


def build(state_file: Path, seed_bc: Path, hp_a: int, hp_b: int, seed: str = "4242",
          board: str = BOARD) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed,
           "--seed-bc", str(seed_bc), "--board", board,
           "--p-units", f"{CASTER_VIS},{A_VIS},{B_VIS}", "--a-units", FOE_VIS,
           "--unit-stat", unit_stat_spec(hp_a, hp_b),
           "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(p.stdout[-2500:])
    if p.returncode != 0:
        print(p.stderr[-2500:], file=sys.stderr)
        raise RuntimeError("build KO")
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def snapshot(sid: int, rid: int) -> dict:
    obs = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    by_vis = {}
    for u in (obs.get("units") or []):
        by_vis.setdefault(u.get("visualId"), u)
    return {"obs": obs, "byVis": by_vis}


def heal_utility_of(hp: int, hp_max: int) -> float:
    """`IdunBattle.AI.Utilities.HealUtility` sur la seule branche exercee ici :
    `MaxFillUp = min(healAmount, missing)` puis `fill / (hpMax + 1) x W(100)`, `friendSign = +1`
    (cibles alliees), `bossMod` inerte (`BossUnit` nul en arene)."""
    return 100.0 * min(HEAL_AMOUNT, max(0, hp_max - hp)) / (hp_max + 1)


def pair_utility_checked(sid: int, rid: int, caster: int, target: int, ob: dict) -> float:
    """`pairUtility` RECOUPE avec l'etat de PV du MEME instant.

    Piege #27-4d (mesure) : `CachedDamagePredictionQuery` peut rendre une valeur PERIMEE juste apres
    une mutation (37.678 rendu sur une cible a PV pleins, 0 en re-mesure). La parade n'est pas de
    re-lire au hasard : c'est de REJETER toute valeur qui ne s'explique pas par l'etat lu."""
    pu = rpc(sid, "pairUtility", {"runnerId": rid, "unitId": caster,
                                  "targetId": target, "abilityType": ABILITY}, 60)
    got = float(pu.get("utility"))
    want = heal_utility_of(int(ob.get("hp") or 0), int(ob.get("hpMax") or 0))
    # Tolerance 1e-6 : le natif calcule en Fix64 (virgule fixe 32.32), donc `fill/(hpMax+1) x 100`
    # arrondit (mesure : 37.499531265348196 natif contre 37.499531255859375 exact, ecart 9.5e-9).
    # C'est trois ordres de grandeur SOUS ce que le piege du cache produit (37.678 rendu sur une
    # cible a PV pleins, soit un ecart de 37.7) : la garde reste discriminante.
    if abs(got - want) > 1e-6:
        raise RuntimeError(
            "pairUtility %s->%s = %.12f INCOHERENT avec l'etat du meme instant (%s/%s -> %.12f) : "
            "lecture de cache perimee, mesure REJETEE"
            % (caster, target, got, ob.get("hp"), ob.get("hpMax"), want))
    if pu.get("playbookClass") != "HealingBalms_HealPlaybook":
        raise RuntimeError("playbook natif inattendu: %s" % pu.get("playbookClass"))
    return got


def native_choice(sid: int, rid: int, caster: int) -> dict:
    """Action proposee par le NATIF pour le caster (`aiDryRunAllUnits`, read-only)."""
    dry = rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 300)
    for u in (dry.get("units") or []):
        if u.get("unitId") != caster:
            continue
        out = {"raw": u.get("proposed"), "ability": None, "target": None, "moved": False}
        for m in (u.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                out["ability"], out["target"] = m.get("abilityType"), m.get("targetId")
            elif m.get("cls") == "MoveUnitMessage":
                out["moved"] = True
        return out
    return {"raw": None, "ability": None, "target": None, "moved": False}


def engine_choice(sid: int, rid: int, caster: int, coef) -> dict:
    """Decision du MOTEUR sur le MEME etat, avec le terme custom de 1212 remplace par `coef`.

    `coef(heal_term, gated) -> float` : `None` = le port tel quel (`Half`). Sert a montrer que le
    bras est SENSIBLE au coefficient -- un bras que toutes les formes passent ne mesure rien."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook.common import HEALING_BALMS_HEAL_PLAYBOOK as PB

    _rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = _rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(_rpc, rid)
    cls = type(PB)
    orig = cls.calculate_custom_utility_from_heal
    if coef is not None:
        cls.calculate_custom_utility_from_heal = (
            lambda self, heal_term, target_has_balms: coef(heal_term, target_has_balms))
    try:
        d = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        cls.calculate_custom_utility_from_heal = orig
    return {"kind": d.get("kind"), "ability": d.get("ability"), "target": d.get("target"),
            "to": d.get("to")}


# Formes CONCURRENTES du terme custom, confrontees dans CHAQUE bras. `half` = ce que le decompile
# dit (`Fix64$$FastMul(x, Fix64.<statics+0x30>)`) ; les autres sont les hypotheses que l'A/B de la
# tranche 4d ne pouvait PAS ecarter (son ecart d'utilite entre les deux cibles etait nul).
#   K_CONST : calibree pour PASSER les deux bras du niveau HAUT (10.71 < k < 14.06) -- elle doit donc
#   ECHOUER au niveau BAS, ou l'ecart a franchir n'est plus que ~3.5. C'est cette contradiction qui
#   refute la forme additive.
K_CONST = 12.0
FORMS = {
    "half (decompile)": None,
    "zero": lambda t, g: 0.0,
    "one": lambda t, g: 0.0 if g else 1.0 * t,
    "quarter": lambda t, g: 0.0 if g else 0.25 * t,
    "const %.1f" % K_CONST: lambda t, g: 0.0 if g else K_CONST,
}


def _ids(sid: int, rid: int) -> dict:
    ids = {v: u.get("squadId") for v, u in snapshot(sid, rid)["byVis"].items()}
    missing = [v for v in (CASTER_VIS, A_VIS, B_VIS) if ids.get(v) is None]
    if missing:
        raise RuntimeError("unites absentes du build: %s" % missing)
    return ids


def _obs_by_id(sid: int, rid: int) -> dict:
    return {u.get("squadId"): u
            for u in (rpc(sid, "observeBattle", {"runnerId": rid}, 40).get("units") or [])}


def _from_here(sid: int, rid: int, caster: int) -> set:
    """Cibles de 1212 castables SANS bouger depuis la tuile du caster (`abilityTargets.fromHere`).
    C'est l'ensemble des options que le natif met REELLEMENT en concurrence : une cible qui n'y est
    pas ne participe a aucune comparaison, et un bras monte sur elle ne mesure RIEN."""
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "abilityType": ABILITY}, 60)
    for u in (at.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") == ABILITY:
                return {t.get("targetId") for t in (a.get("fromHere") or [])
                        if t.get("kind") == "unit" and t.get("targetId") is not None}
    return set()


def place_targets(sid: int, rid: int, caster: int, tids: list) -> set:
    """Amene les cibles AU CONTACT du caster (lui est FIGE, `Movement = 0`).

    Doctrine "on pilote les positions, on ne se plaint pas de la geometrie de spawn" : selon le
    board, les spawns ne mettent pas les deux cibles a portee de cast, et le bras rendrait alors un
    verdict qui ne parle pas du terme custom. MESURE (board MC1_63, seed 909) : sans ce placement,
    `spaceBlackmane` n'etait pas dans `fromHere` et le natif retenait l'autre cible quelle que soit
    la forme du terme -- y compris `One`, qui ailleurs bascule.
    """
    fh = _from_here(sid, rid, caster)
    missing = [t for t in tids if t not in fh]
    if not missing:
        return fh
    tiles = (rpc(sid, "boardGraph", {"runnerId": rid}, 90).get("tiles") or [])
    id2pos = {t.get("id"): (t.get("col"), t.get("row")) for t in tiles}
    by_pos = {(t.get("col"), t.get("row")): t for t in tiles}
    ob = _obs_by_id(sid, rid)
    cpos = (ob[caster].get("col"), ob[caster].get("row"))
    ring = [id2pos[n] for n in ((by_pos.get(cpos) or {}).get("neighbours") or []) if n in id2pos]
    occupied = {(u.get("col"), u.get("row")) for u in ob.values() if not u.get("isDead")}
    mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    reach = {u.get("unitId"): {(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])}
             for u in (mov.get("units") or [])}
    for tid in missing:
        cands = [p for p in ring if p not in occupied
                 and (by_pos.get(p) or {}).get("walkable") and p in (reach.get(tid) or set())]
        if not cands:
            raise RuntimeError("cible u%s n'atteint aucune tuile LIBRE au contact du caster "
                               "(ring-1 = %s) : montage impossible sur ce board" % (tid, ring))
        to = cands[0]
        rpc(sid, "applyAction", {"runnerId": rid,
                                 "action": {"kind": "move", "unitId": tid,
                                            "to": {"col": to[0], "row": to[1]}}}, 90)
        occupied.add(to)
    fh = _from_here(sid, rid, caster)
    still = [t for t in tids if t not in fh]
    if still:
        raise RuntimeError("apres placement, u%s hors de `fromHere` de 1212" % still)
    return fh


def _effects_by_id(sid: int, rid: int) -> dict:
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 240)
    return {u.get("id"): [e.get("name") for e in (u.get("effects") or [])]
            for u in (dv.get("units") or [])}


def run_arm(sid: int, n: int, base: Path, logs: Path, keep: bool = False,
            seed: str = "4242", board: str = BOARD, tag: str = "") -> dict:
    """UN bras : monte l'etat, POSE le buff sur A, puis lit le CHOIX natif entre A (gate FERME) et
    B (gate OUVERT) a utilites de soin DIFFERENTES. Chaque controle qui echoue LEVE -- un montage qui
    ne tient pas doit se voir comme un abandon, jamais se degrader en verdict."""
    arm = ARMS[n]
    print("\n=== BRAS %d%s -- niveau %s, ratio vise r=%.5f (hpA=%d hpB=%d) A=%s B=%s seed=%s board=%s ==="
          % (n, tag, arm["level"], arm["r"], arm["hpA"], arm["hpB"], A_VIS, B_VIS, seed, board))
    rid = build(logs / ("rs_286_arm%d%s.json" % (n, tag)), base, arm["hpA"], arm["hpB"],
                seed=seed, board=board)
    try:
        ids = _ids(sid, rid)
        cid, a_id, b_id = ids[CASTER_VIS], ids[A_VIS], ids[B_VIS]

        # -- controle d'entree 1 : la MAGNITUDE du soin est bien celle qu'on a commandee.
        cs = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        sn = next((u for u in (cs.get("units") or []) if u.get("entityId") == cid), {}) or {}
        attack = int(((sn.get("stats") or {}).get("attack")) or 0)
        hits = int((sn.get("normalAttack") or {}).get("hits") or 1)
        if attack * max(hits, 1) != HEAL_AMOUNT:
            raise RuntimeError("magnitude ARME %d x %d != %d commande (--unit-stat non applique ?)"
                               % (attack, hits, HEAL_AMOUNT))

        # -- controle d'entree 2 : le caster est FIGE (Movement=0) -> UNE seule tuile candidate, donc
        #    le terme de tuile de `CalculateActionUtility` est rigoureusement COMMUN aux deux options
        #    et ne peut pas porter la bascule.
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mv = next((u for u in (mov.get("units") or []) if u.get("unitId") == cid), None)
        if mv is None:
            raise RuntimeError("caster absent d'aiMovableTiles : l'immobilite n'est pas MESUREE "
                               "(une absence n'est pas une preuve de 0 tuile)")
        n_tiles = len(mv.get("tiles") or [])
        if n_tiles:
            raise RuntimeError("caster NON fige : %d tuiles atteignables (terme de tuile non commun)"
                               % n_tiles)

        # -- controle d'entree 3 : les DEUX cibles doivent etre en concurrence reelle, c'est-a-dire
        #    castables depuis la tuile (unique) du caster. On les y AMENE au besoin.
        place_targets(sid, rid, cid, [a_id, b_id])

        ob = _obs_by_id(sid, rid)
        hp_a, hp_b = ob[a_id], ob[b_id]
        if int(hp_a.get("hpMax")) != arm["hpA"] or int(hp_b.get("hpMax")) != arm["hpB"]:
            raise RuntimeError("hpMax non conformes: A=%s B=%s" % (hp_a.get("hpMax"), hp_b.get("hpMax")))
        u_a = pair_utility_checked(sid, rid, cid, a_id, hp_a)
        u_b = pair_utility_checked(sid, rid, cid, b_id, hp_b)
        ratio = u_a / u_b
        print("  entree : A u%d %s/%s U=%.9f | B u%d %s/%s U=%.9f | ratio=%.6f"
              % (a_id, hp_a.get("hp"), hp_a.get("hpMax"), u_a,
                 b_id, hp_b.get("hp"), hp_b.get("hpMax"), u_b, ratio))

        # -- temoin AVANT buff : aucune des deux cibles n'est gatee, donc le natif doit prendre la
        #    plus haute utilite (A) QUELLE QUE SOIT la forme du terme -- c'est le controle que le
        #    montage emet bien une action 1212, et non que le coefficient vaut quelque chose.
        pre = native_choice(sid, rid, cid)
        if pre["ability"] != ABILITY:
            raise RuntimeError("temoin: le natif ne propose pas 1212 mais %s" % pre["raw"])
        if pre["target"] != a_id:
            raise RuntimeError("temoin: cible %s au lieu de A(%s) alors qu'aucune n'est buffee"
                               % (pre["target"], a_id))

        # -- pose du buff : le SEUL poseur de `HealingBalms_ExtraCritDamage` est le cast de 1212.
        rpc(sid, "applyAction", {"runnerId": rid,
                                 "action": {"kind": "ability", "casterId": cid,
                                            "targetId": a_id, "abilityType": ABILITY}}, 90)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        rpc(sid, "autoPlayRunner", {"runnerId": rid, "maxTurns": 1}, 300)

        # -- controles de sortie : gate pose du bon cote, et TOUJOURS hors saturation (c'est cette
        #    seconde propriete qui rend la mesure insensible au soin RETARDE du passif et aux coups
        #    adverses -- en regime non sature, U ne depend plus que de hpMax).
        eff = _effects_by_id(sid, rid)
        if GATE_EFFECT not in (eff.get(a_id) or []):
            raise RuntimeError("A ne porte pas %s apres le cast : %s" % (GATE_EFFECT, eff.get(a_id)))
        if GATE_EFFECT in (eff.get(b_id) or []):
            raise RuntimeError("B porte %s : le gate n'est plus discriminant" % GATE_EFFECT)
        ob2 = _obs_by_id(sid, rid)
        for who, oid in (("A", a_id), ("B", b_id)):
            miss = int(ob2[oid].get("hpMax")) - int(ob2[oid].get("hp"))
            if miss <= HEAL_AMOUNT:
                raise RuntimeError("%s SATURE (missing=%d <= healAmount=%d) : U ne vaut plus "
                                   "100 x amt/(hpMax+1), le bras ne mesure plus le ratio voulu"
                                   % (who, miss, HEAL_AMOUNT))
        fh2 = _from_here(sid, rid, cid)
        if a_id not in fh2 or b_id not in fh2:
            raise RuntimeError("au tour d'observation, les deux cibles ne sont plus toutes deux "
                               "castables sans bouger (fromHere = %s) : le natif n'a pas le CHOIX, "
                               "sa preference ne mesure rien" % sorted(fh2))
        u_a2 = pair_utility_checked(sid, rid, cid, a_id, ob2[a_id])
        u_b2 = pair_utility_checked(sid, rid, cid, b_id, ob2[b_id])
        if abs(u_a2 - u_a) > 1e-9 or abs(u_b2 - u_b) > 1e-9:
            raise RuntimeError("les utilites ont bouge entre les deux tours (%.9f/%.9f -> %.9f/%.9f)"
                               % (u_a, u_b, u_a2, u_b2))
        print("  apres buff : A u%d %s/%s [gate FERME] | B u%d %s/%s [gate OUVERT] | U inchangees"
              % (a_id, ob2[a_id].get("hp"), ob2[a_id].get("hpMax"),
                 b_id, ob2[b_id].get("hp"), ob2[b_id].get("hpMax")))

        post = native_choice(sid, rid, cid)
        if post["ability"] != ABILITY:
            raise RuntimeError("le natif ne propose plus 1212 mais %s" % post["raw"])
        role = "A" if post["target"] == a_id else ("B" if post["target"] == b_id else
                                                   "u%s" % post["target"])
        print("  CHOIX NATIF : %s (u%s)%s" % (role, post["target"],
                                              " + MOVE (inattendu)" if post["moved"] else ""))

        # -- bornes deduites du seul choix : u_A = U_A (gate ferme), u_B = (1 + c) U_B.
        c_lo = c_hi = k_lo = k_hi = None
        if role == "B":
            c_lo, k_lo = ratio - 1.0, u_a - u_b
            bound_c, bound_k = "c > %.6f" % c_lo, "k > %.6f" % k_lo
        elif role == "A":
            c_hi, k_hi = ratio - 1.0, u_a - u_b
            bound_c, bound_k = "c < %.6f" % c_hi, "k < %.6f" % k_hi
        else:
            bound_c = bound_k = "(cible hors A/B)"

        # -- contre-epreuve MOTEUR, forme par forme : le bras doit SEPARER les hypotheses.
        forms = {}
        for label, coef in FORMS.items():
            d = engine_choice(sid, rid, cid, coef)
            if d.get("kind") != "ability" or d.get("ability") != ABILITY:
                forms[label] = "%s" % d.get("kind")
                continue
            forms[label] = ("A" if d.get("target") == a_id else
                            ("B" if d.get("target") == b_id else "u%s" % d.get("target")))
        print("  moteur : " + ", ".join("%s -> %s" % (k, v) for k, v in forms.items())
              + "   (natif = %s)" % role)

        return {"arm": n, "runner": rid, "level": arm["level"], "ratio": ratio,
                "U_A": u_a, "U_B": u_b, "native_target_role": role,
                "native_raw": post["raw"], "c_lo": c_lo, "c_hi": c_hi,
                "k_lo": k_lo, "k_hi": k_hi, "bound_c": bound_c, "bound_k": bound_k,
                "forms": forms, "attack": attack, "hits": hits}
    finally:
        if not keep:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            except Exception:  # noqa: BLE001
                pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recon", action="store_true")
    ap.add_argument("--arm", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", type=str, default=None)
    ap.add_argument("--keep", action="store_true", help="ne dispose pas le runner en fin de passe")
    ap.add_argument("--targets", type=str, default=None,
                    help="couple de cibles 'A,B' (defaut spaceBlackmane,spaceHound) -- "
                         "controle de generalisation : le verdict ne doit pas dependre de leur identite")
    ap.add_argument("--seed", type=str, default="4242")
    ap.add_argument("--board", type=str, default=BOARD)
    ap.add_argument("--tag", type=str, default="", help="suffixe de state-file (montages paralleles)")
    args = ap.parse_args(argv)

    if args.targets:
        global A_VIS, B_VIS
        A_VIS, B_VIS = (x.strip() for x in args.targets.split(","))

    sid = _session()
    logs = ROOT / "logs"
    base = base_seed_bc(logs / "bc_286_base.json")

    if args.recon:
        arm = ARMS[1]
        rid = build(logs / "rs_286_recon.json", base, arm["hpA"], arm["hpB"])
        snap = snapshot(sid, rid)
        ids = {}
        for vis, u in snap["byVis"].items():
            ids[vis] = u.get("squadId")
            print("  %-20s id=%-4s team=%s pos=(%s,%s) hp=%s/%s"
                  % (vis, u.get("squadId"), u.get("teamId"), u.get("col"), u.get("row"),
                     u.get("hp"), u.get("hpMax")))
        cid = ids.get(CASTER_VIS)
        cs = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        for u in (cs.get("units") or []):
            if u.get("entityId") == cid:
                print("  caster: attack=%s hits=%s cfg=%s"
                      % ((u.get("stats") or {}).get("attack"),
                         (u.get("normalAttack") or {}).get("hits"),
                         json.dumps(u.get("unitConfig"))))
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 180)
        for u in (dv.get("units") or []):
            if u.get("id") == cid:
                print("  caster abilities:", json.dumps(u.get("abilities")))
        at = rpc(sid, "abilityTargets", {"runnerId": rid, "abilityType": ABILITY}, 60)
        print("  abilityTargets(1212):", json.dumps(at)[:1200])
        print("  runner=%d (state-file conserve)" % rid)
        return 0

    arms = sorted(ARMS) if args.all else ([args.arm] if args.arm else [])
    if not arms:
        print("rien a faire : passer --recon, --arm N ou --all")
        return 2

    out, rc = [], 0
    for n in arms:
        try:
            out.append(run_arm(sid, n, base, logs, keep=args.keep, seed=args.seed,
                               board=args.board, tag=args.tag))
        except RuntimeError as e:
            print("[bras %d] ABANDON : %s" % (n, e))
            out.append({"arm": n, "aborted": str(e)})
            rc = 1
    print("")
    print("=== SYNTHESE #286 -- encadrement du coefficient du terme custom de 1212 ===")
    c_los, c_his, k_los, k_his = [], [], [], []
    for r in out:
        if r.get("aborted"):
            print(" bras %d : ABANDON (%s)" % (r["arm"], r["aborted"][:110]))
            continue
        a = ARMS[r["arm"]]
        ok = "OK" if r["native_target_role"] == a["expect"] else "INATTENDU"
        print(" bras %d (niveau %s, ratio mesure %.6f) : U_A=%.9f U_B=%.9f -> natif %s [%s attendu] %s"
              % (r["arm"], a["level"], r["ratio"], r["U_A"], r["U_B"],
                 r["native_target_role"], a["expect"], ok))
        print("        coefficient : %s | constante additive : %s" % (r["bound_c"], r["bound_k"]))
        print("        moteur : %s"
              % ", ".join("%s -> %s" % (k, v) for k, v in r["forms"].items()))
        if r["native_target_role"] != a["expect"]:
            rc = 1
        for val, acc in ((r["c_lo"], c_los), (r["c_hi"], c_his),
                         (r["k_lo"], k_los), (r["k_hi"], k_his)):
            if val is not None:
                acc.append(val)
    if c_los and c_his:
        lo, hi = max(c_los), min(c_his)
        print(" ENCADREMENT MULTIPLICATIF : %.6f < c < %.6f  -> Half (0.5) est %s"
              % (lo, hi, "DEDANS" if lo < 0.5 < hi else "DEHORS"))
        if not lo < 0.5 < hi:
            rc = 1
    else:
        print(" ENCADREMENT MULTIPLICATIF : incomplet (il faut au moins un bras 'B' et un bras 'A')")
        rc = 1
    if k_los and k_his:
        klo, khi = max(k_los), min(k_his)
        print(" FORME ADDITIVE (constante k) : exigee > %.6f ET < %.6f -> %s"
              % (klo, khi, "CONTRADICTOIRE, forme REFUTEE" if klo >= khi else "NON refutee"))
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
