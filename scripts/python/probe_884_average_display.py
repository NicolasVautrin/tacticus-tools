#!/usr/bin/env python
"""Probe #884 -- le canal DISPLAY `Average` des QUATRE descripteurs `EffectAdditionalHits`
qui publiaient `min`/`max` SANS `amount`.

## L'artefact natif, LU (build rnca9r7q6c)

`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, isPrediction, minVar, maxVar)` :

    minNode = DSLFormulas.ConfigVar(minVar, AbilityStateFromEffect(...), config)
    maxNode = DSLFormulas.ConfigVar(maxVar, AbilityStateFromEffect(...), config)
    isPrediction == 0 -> DSLFormulas.RandomAmount(minNode, maxNode)     # noeud ROLL
    isPrediction != 0 -> DSLFormulas.Average(minNode, maxNode)          # noeud DISPLAY

`GetMinMaxDamage(this, p)` (2-arg) = `GetMinMaxDamage(this, p, 0xc = minDmg, 0xd = maxDmg)` ;
`GetMinMaxDamage2(this, p)` = `GetMinMaxDamage(this, p, 0x36 = minDmg_2, 0x37 = maxDmg_2)`.

`IdunBattle.Entities.Effects.EffectAdditionalHits$$Create(out, trigger, roll, type, profile,
hits, forceOverkill, display)` pose `out+0x08 = roll` puis `out+0x10 = display if display else
roll` ; `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` lit
`min = max = <+0x10>.Calculate()` quand `useDisplay`, sinon `<+0x08>.CalculateMin()` /
`.CalculateMax()`. `DSLFormulas$$Average(a, b)` = `DivideAmount(SumAmount(a, b), Direct(2),
rule = null)` -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` ->
`IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `FixMath.NET Fix64.Round`
demi-vers-le-PAIR -- donc un ENTIER, jamais un `.5`.

## Les QUATRE descripteurs et leur porteur

  * `SquigHound_AdditionalHitsEffect`      (1292) -- `orksRuntherd`      , ability 1082
  * `CordClaw_AdditionalHitsEffect`        (1250) -- `admecRuststalker`  , ability 1122
  * `SorcerousFacade_AdditionalHitsEffect` (1204) -- `thousTzaangor`     , ability 1100
  * `FearOfTheUnseen_ExtraDamageEffect`    (1239) -- `tyranDeathleaper`  , ability 1115

Les quatre abilities POSEUSES sont au registre `ABILITY_CLASSES` et les quatre porteurs sont dans
`rl_duel build --list-pool` : confrontables sans injection catalogue.

## Ce que ce probe MESURE

Oracle = canal `ranked` natif (`decisionView.attackPlans[].evals[].ranked[]` : `dmgMin`/`dmgMax`
par tuile candidate), confronte a `playbook.prediction.make_normal_attack_predictions`. Une seule
CAPTURE live, puis un REPLAY offline par VARIANTE de modele du noeud DISPLAY :

  * `port`       -- `Fix64.Round((min + max) / 2)` demi-vers-le-pair (le port livre) ;
  * `predefined` -- l'ANCIEN modele : pas d'`amount`, la prediction lit `[min, max]` ;
  * `float`      -- `(min + max) / 2` SANS arrondi (le mutant que le montage #419-r1-tr11-r5 ne
                    pouvait PAS separer : sa somme etait PAIRE) ;
  * `floor`      -- `Fix64.Floor` au lieu de `Fix64.Round`.

Le regime servi (rank 17 -> `AbilityVariablesMultiplierPercentage` 180, ability_level 50) donne des
sommes IMPAIRES sur `SorcerousFacade` [997, 1996], `FearOfTheUnseen` [1197, 1496] et `SquigHound`
[2394, 3589] : `float` y publie un `.5` que `port` n'a pas. Et `floor` diverge de `port` des que la
partie entiere de la moyenne est IMPAIRE (`SquigHound` : 2991 contre 2992).

ASCII only. Usage :
    python probe_884_average_display.py [--seed 88401] [--state-file <abs>] [--keep]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc            # noqa: E402
from engine.dsl.base import _round_fix64                       # noqa: E402
from engine.entities.effects.magnitude import ability_var      # noqa: E402
from engine.playbook import scene as SC                        # noqa: E402
from engine.playbook import prediction                         # noqa: E402
from engine.playbook.scene import Scene                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BOARD = "MC1_67"

#: (visualId du porteur, ability POSEUSE, nom d'effet publie par le decisionView, cle min, cle max,
#: cle gameconfig de l'ability qui porte les variables)
CARRIERS = [
    ("thousTzaangor",    1100, "SorcerousFacade_AdditionalHits", "minDmg",   "maxDmg",   "SorcerousFacade"),
    ("tyranDeathleaper", 1115, "FearOfTheUnseen_ExtraDamage",    "minDmg",   "maxDmg",   "FearOfTheUnseen"),
    ("orksRuntherd",     1082, "SquigHound_AdditionalHits",      "minDmg",   "maxDmg",   "SquigHound"),
    ("admecRuststalker", 1122, "CordClaw_AdditionHits",          "minDmg_2", "maxDmg_2", "CordClaw"),
]
ALLY_VIS = "thousSorcerer"          # l'ALLIE PSYKER : seule cible que 1100 accepte
P_UNITS = ",".join(c[0] for c in CARRIERS) + "," + ALLY_VIS
A_UNITS = "necroWarden,necroWarden,necroWarden"

VARIANTS = ("port", "predefined", "float", "floor")


# ---------------------------------------------------------------- modeles du noeud DISPLAY

def display_value(mn: int, mx: int, variant: str):
    """La valeur du noeud DISPLAY selon la VARIANTE de modele. `None` = pas de cle `amount`."""
    if variant == "predefined":
        return None
    if variant == "float":
        return (int(mn) + int(mx)) / 2
    if variant == "floor":
        return _round_fix64(Fraction(int(mn) + int(mx), 2), 2)      # RoundFix64Result mode 2
    return _round_fix64(Fraction(int(mn) + int(mx), 2), 0)          # mode 0 = Fix64.Round


def patch_variant(variant: str):
    """Reecrit `additional_hit_groups` des QUATRE classes d'effet pour la variante demandee.
    Rend un callable de restauration."""
    from engine.entities.effects import loki
    from engine.entities.effects.loki import hits as H

    targets = [H.SorcerousFacadeAdditionalHitsEffect, H.FearOfTheUnseenExtraDamageEffect,
               H.SquigHoundAdditionalHitsEffect, H.CordClawAdditionalHitsEffect]
    saved = [(cls, cls.additional_hit_groups) for cls in targets]

    def make(orig):
        def wrapper(self, ctx=None):
            grps = orig(self, ctx)
            if not grps:
                return grps
            out = []
            for g in grps:
                g = dict(g)
                v = display_value(g["min"], g["max"], variant)
                if v is None:
                    g.pop("amount", None)
                else:
                    g["amount"] = v
                out.append(g)
            return out
        return wrapper

    for cls, orig in saved:
        cls.additional_hit_groups = make(orig)

    def restore():
        for cls, orig in saved:
            cls.additional_hit_groups = orig
    _ = loki                                    # garde l'import explicite (pas de faux "unused")
    return restore


# ---------------------------------------------------------------- montage

def separating_multiplier(cfg: str, kmin: str, kmax: str, lvl: int = 50):
    """Le multiplicateur de rarete qui SEPARE `Fix64.Round` de `Fix64.Floor` sur ce descripteur.

    `Average` rend `Round((mn + mx) / 2)` demi-vers-le-PAIR. `round != floor` exige que la moyenne
    soit `k + 0.5` avec `k` IMPAIR -- c'est-a-dire `mn + mx == 3 (mod 4)`. Un `k` PAIR fait
    COINCIDER les deux (`floor(1346.5) = 1346 = round(1346.5)`), et c'est le cas du regime servi
    par le seed BC sur trois des quatre porteurs.

    Le mult est DERIVE de la table `units.heroProgressionSteps` du gameconfig, jamais saisi."""
    import gameconfig as _G
    mults = sorted({s["abilityStatMultiplierPct"]
                    for s in _G._cfg()["units"]["heroProgressionSteps"]})
    for m in mults:
        mn = ability_var(cfg, kmin, lvl, multiplier_pct=m)
        mx = ability_var(cfg, kmax, lvl, multiplier_pct=m)
        if mn is None or mx is None:
            continue
        if (int(mn) + int(mx)) % 4 == 3:
            return m
    return None


def seed_bc_multipliers() -> dict:
    """`AbilityVariablesMultiplierPercentage` que le seed BC porte pour chaque porteur.

    ⚠ Ce champ n'est PAS recalcule par `buildNormalizedBC` : le `--rank 17` de `rl_duel build` ne
    le touche pas. Le regime servi n'est donc PAS deductible du rank -- mesure : `orksRuntherd` et
    `admecRuststalker` sont a **200**, `thousTzaangor` et `tyranDeathleaper` a **180**. Un probe
    qui suppose 180 partout imprime un regime FAUX et conclut de travers sur la discriminance."""
    src = Path(__file__).resolve().parents[2] / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    out = {}
    for u in (bc.get("Units") or []):
        vis = u.get("VisualId") or u.get("UnitId") or u.get("Id")
        if vis:
            out[vis] = u.get("AbilityVariablesMultiplierPercentage")
    return out


def write_patched_seed_bc(out: Path, mult_by_vis: dict) -> Path:
    """Copie `data/seed-bc.json` en forcant `AbilityVariablesMultiplierPercentage` par porteur.

    ⚠ Ce n'est PAS un patch INVISIBLE DU PORT (motif `#366-r1-bcpatch-invisible`) : le
    multiplicateur est LU par le port depuis l'etat du runner (`ability_variables_multiplier`),
    donc les deux cotes voient le meme regime. Ce qu'il change, c'est la COURBE servie -- et c'est
    exactement l'objet de la manoeuvre. `buildNormalizedBC` ne recalcule PAS ce champ."""
    src = Path(__file__).resolve().parents[2] / "data" / "seed-bc.json"
    bc = json.loads(src.read_text(encoding="utf-8"))
    touched = {}
    for u in (bc.get("Units") or []):
        vis = u.get("VisualId") or u.get("UnitId") or u.get("Id")
        if vis in mult_by_vis and mult_by_vis[vis] is not None:
            touched[vis] = (u.get("AbilityVariablesMultiplierPercentage"), mult_by_vis[vis])
            u["AbilityVariablesMultiplierPercentage"] = int(mult_by_vis[vis])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    for vis, (was, now) in sorted(touched.items()):
        print("  [seed-bc] %-20s AbilityVariablesMultiplierPercentage %s -> %s"
              % (vis, was, now))
    return out


def build(seed: int, state_file: Path, armor: "int | None" = None,
          seed_bc: "Path | None" = None) -> int:
    """⚠ `--armor-target` est LE levier de discrimination de l'ARRONDI : la reduction d'armure
    COMPRIME l'ecart. Un `amount` a +/-1 (port 2992 / floor 2991) rend la MEME prediction finale
    des que l'armure est haute -- c'est ce qui a fait rendre << float et floor non separes >> au
    premier run. Armure BASSE = passthrough, l'ecart d'entree survit en sortie."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD,
           "--p-units", P_UNITS, "--a-units", A_UNITS,
           "--hp-target", "400000", "--hp-player", "400000"]
    if armor is not None:
        cmd += ["--armor-target", str(armor)]
    if seed_bc is not None:
        cmd += ["--seed-bc", str(seed_bc)]
    proc = subprocess.run(cmd,
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[884] build KO: %s" % ((proc.stderr or proc.stdout or "")[-500:]), file=sys.stderr)
        sys.exit(2)
    return json.loads(state_file.read_text())["runnerId"]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(dec):
    return {u.get("visualId"): u for u in (dec.get("units") or []) if u.get("alive")}


def _rich(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 150)


def _advance_to_my_turn(rpc, rid, owner, max_iter=10):
    for _ in range(max_iter):
        dec = rpc("decisionView", {"runnerId": rid}, 150)
        if not isinstance(dec, dict) or not dec.get("ok"):
            return None
        if dec.get("currentPlayer") == owner:
            return _rich(rpc, rid)
        rpc("aiPlayTurn", {"runnerId": rid}, 240)
        dec2 = rpc("decisionView", {"runnerId": rid}, 150)
        if isinstance(dec2, dict) and dec2.get("ok") and dec2.get("currentPlayer") != owner:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def _end_round(rpc, rid, owner) -> None:
    for _ in range(4):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dec = rpc("decisionView", {"runnerId": rid}, 90)
        if isinstance(dec, dict) and dec.get("ok") and dec.get("currentPlayer") != owner:
            rpc("aiPlayTurn", {"runnerId": rid}, 300)
            return


def _effect_names(dec, uid):
    for u in (dec.get("units") or []):
        if u.get("id") == uid:
            return [e.get("name") for e in (u.get("effects") or [])]
    return []


def _ability_targets(rpc, rid, caster_id, ability_id):
    """(`targets`, `fromHere`) du NATIF pour (caster, ability).

    ⚠ Le RPC `abilityTargets` est GLOBAL (`{runnerId, allAbilities}`) et rend un arbre
    `units[].abilities[]` -- il n'accepte NI `casterId` NI `abilityType`. Appele avec ces cles,
    il repond `ok: true` et une liste VIDE : un refus qui se lit comme une mesure."""
    a = rpc("abilityTargets", {"runnerId": rid, "allAbilities": True}, 120)
    for u in ((a or {}).get("units") or []):
        if u.get("unitId") != caster_id:
            continue
        for ab in (u.get("abilities") or []):
            if ab.get("abilityId") == ability_id:
                return (ab.get("targets") or []), (ab.get("fromHere") or []), ab
    return [], [], None


def _cast(rpc, rid, caster_id, ability_id, target_id):
    """L'action de `rl_duel act ability` : `{kind, casterId, targetId, abilityType}` -- la cle
    est `casterId`, PAS `unitId` (un `unitId` est ignore EN SILENCE, `ok: true` inclus)."""
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": ability_id,
        "targetId": target_id}}, 180)
    return bool(isinstance(r, dict) and r.get("ok") and not r.get("error"))


def _step_toward(rpc, rid, dec, u, goal):
    """Un pas greedy vers `goal` (disque 4, tuiles libres). Rend True si un move a mordu."""
    upos = _pos(u)
    free = _free_tiles(dec, rpc, rid)
    cands = [t for t in hexgeo.disk(upos[0], upos[1], 4) if t in free and t != tuple(upos)]
    cands.sort(key=lambda t: hexgeo.distance(t, tuple(goal)))
    for t in cands[:8]:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": t[0], "row": t[1]}}}, 90)
        if isinstance(r, dict) and r.get("ok") and not r.get("error"):
            return True
    return False


_BOARD_TILES = None


def _board_tiles(rpc, rid):
    """Les tuiles REELLES du board, lues une fois.

    ⚠ Un rectangle DEVINE (`range(9) x range(11)`) produit des destinations HORS BOARD : tous les
    moves candidats sont refuses et l'unite ne bouge plus -- c'est ce qui a laisse `thousTzaangor`
    fige a 3 hexes de l'ennemi pendant huit rounds, et fait rendre << NON CONFRONTE >> a un montage
    qui n'avait simplement pas avance."""
    global _BOARD_TILES
    if _BOARD_TILES is None:
        b = SC.build_board(rpc, rid)
        _BOARD_TILES = {(t["col"], t["row"]) for t in (b.by_id.values() if b else ())}
    return _BOARD_TILES


def _free_tiles(dec, rpc=None, rid=None):
    occ = {tuple(_pos(u)) for u in (dec.get("units") or []) if u.get("alive")}
    tiles = _board_tiles(rpc, rid) if rpc is not None else (_BOARD_TILES or set())
    return tiles - occ


def _approach(rpc, rid, dec, u, enemies):
    """Rapproche `u` de l'ennemi le plus proche (greedy, disque 4). Rend True si un move a mordu.

    DOCTRINE : on DEPLACE les unites pour forcer la configuration -- << bloque par la geometrie
    de spawn >> n'est pas un resultat."""
    upos = _pos(u)
    if not enemies:
        return False
    goal = min((_pos(e) for e in enemies), key=lambda p: hexgeo.distance(upos, p))
    free = _free_tiles(dec, rpc, rid)
    cands = [t for t in hexgeo.disk(upos[0], upos[1], 4) if t in free and t != tuple(upos)]
    cands.sort(key=lambda t: hexgeo.distance(t, goal))
    for t in cands[:8]:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": t[0], "row": t[1]}}}, 90)
        if isinstance(r, dict) and r.get("ok") and not r.get("error"):
            return True
    return False


def _has_plan(dec, uid) -> bool:
    """VRAI seulement si au moins une tuile CLASSEE existe.

    ⚠ Un `attackPlan` existe pour toute unite et toute cible, meme hors de portee : ses `evals`
    sont alors presents avec `rankCount = 0` et `ranked = []`. Tester `evals` non vide rendait
    donc VRAI au spawn -- et le probe castait a 8 hexes de l'ennemi, en pure perte."""
    return any(p.get("unitId") == uid and any((e.get("ranked") or [])
                                              for e in (p.get("evals") or []))
               for p in (dec.get("attackPlans") or []))


# ---------------------------------------------------------------- mesure

def capture_rows(rpc, rid, dec, att_id):
    """Les lignes NATIVES (`ranked`) de l'attaque NORMALE de `att_id` : tuile, cible, dmgMin/dmgMax.
    Une seule capture -- le replay offline par variante se fait ensuite sur ces memes lignes."""
    rows = []
    norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == att_id
                for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
    for ap in (dec.get("attackPlans") or []):
        if ap.get("unitId") != att_id:
            continue
        for ev in (ap.get("evals") or []):
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("col") is None:
                    continue
                rows.append({"tile": (rk["col"], rk["row"]), "tgt": ev.get("targetId"),
                             "nat": (rk.get("dmgMin"), rk.get("dmgMax"))})
    return rows


def replay_offline(rpc, rid, dec, att_id, rows, variant):
    """Recalcule l'offline sur les MEMES lignes, sous la variante donnee."""
    restore = patch_variant(variant)
    try:
        predictor = SC.build_predictor(rpc, rid)
        if predictor is None:
            return None
        sctx = SC.step_context(predictor, dec)
        scene = Scene.from_predictor_sctx(predictor, sctx, None)
        out = []
        for r in rows:
            res = prediction.make_normal_attack_predictions(scene, att_id, r["tgt"], r["tile"],
                                                            meta=True)
            if not res:
                out.append(None)
                continue
            acc = res[0].prediction.accurate_health_damage
            out.append((acc.min, acc.max))
        return out
    finally:
        restore()


def find_bearer(dec, owner, fx):
    """La 1re unite ALLIEE qui porte `fx` ET a une tuile classee.

    ⚠ Ce n'est pas forcement le CASTER : `SorcerousFacadeAbility$$ExecuteBehaviour` pose 1204 sur
    le caster ET sur l'allie Psyker vise, PUIS fait attaquer le caster et ECHANGE leurs positions
    -- apres le cast, le caster a agi et se retrouve au spawn de l'allie. Le porteur confrontable
    est l'ALLIE, et dans le MEME TOUR : la duree est `TurnsFromRounds(1)`.

    ⚠ Et on PREFERE un porteur qui n'a PAS encore agi (`toActivate`). Mesure : sur le CASTER, dans
    le tour meme du cast, `SorcerousFacadeAbility$$ExecuteBehaviour` a AUSSI pose
    `RealityUnbound_ExtraMaxDamage` (1207, stat `EXTRA_MAX_DAMAGE`) -- et le port ne propage pas
    `extra_max` aux groupes du canal #179 (`get_multi_hit_attack_prediction` ne passe PAS
    `extra_max=` a `predict_attack_raw` dans sa boucle `extra_groups`). Le caster rendait donc
    natif `(4601, 7233)` contre port `(4601, 6901)` -- borne MIN exacte, borne MAX a `998` au lieu
    de `1330 = 998 + 332`. C'est un AUTRE gisement, pas le canal DISPLAY : sur l'allie, qui ne
    porte pas 1207, le port est EXACT sur les cinq lignes."""
    cands = [x for x in (dec.get("units") or [])
             if x.get("alive") and x.get("owner") == owner
             and fx in _effect_names(dec, x.get("id"))
             and _has_plan(dec, x.get("id"))]
    active = set(dec.get("toActivate") or ())
    cands.sort(key=lambda x: (x.get("id") not in active, len(_effect_names(dec, x.get("id")))))
    return cands[0] if cands else None


def do_measure(rpc, rid, dec, u, vis, verdicts, measured):
    """Confronte les QUATRE variantes au natif sur les lignes `ranked` de `u`. Rend True si mesure."""
    rows = capture_rows(rpc, rid, dec, u["id"])
    if not rows:
        return False
    res = {}
    for v in VARIANTS:
        off = replay_offline(rpc, rid, dec, u["id"], rows, v)
        if off is None:
            continue
        ok = sum(1 for r, o in zip(rows, off) if o == r["nat"])
        worst = max((max(abs((o or (0, 0))[0] - r["nat"][0]), abs((o or (0, 0))[1] - r["nat"][1]))
                     for r, o in zip(rows, off)), default=None)
        res[v] = (ok, len(rows), worst, tuple(off))
    print("  [MESURE] %-20s sur %s, %d lignes" % (vis, u.get("visualId"), len(rows)))
    for v in VARIANTS:
        if v in res:
            ok, n, worst, _ = res[v]
            print("      %-11s %2d/%2d en accord, |ecart| max %s" % (v, ok, n, worst))
    same = [v for v in res if v != "port" and res[v][3] == res.get("port", (0, 0, 0, None))[3]]
    print("      variantes NON separees ici : %s"
          % (same if same else "aucune -- les 4 modeles divergent"))
    verdicts[vis] = (res, same)
    measured.add(vis)
    return True


def main(argv, return_verdicts: bool = False):
    """`return_verdicts` : rend le dict `{visualId: (res, variantes_non_separees)}` au lieu du rc,
    pour que le test live assertionne sur les MEMES mesures que celles imprimees ici."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=88401)
    ap.add_argument("--state-file", default=str(ROOT / "logs" / "runners" / "_884avg_state.json"))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--max-rounds", type=int, default=6)
    ap.add_argument("--armor-target", type=int, default=None,
                    help="armure des cibles ; BASSE = l'ecart d'arrondi survit a la reduction")
    ap.add_argument("--separating-mult", action="store_true",
                    help="force, par porteur, le multiplicateur qui SEPARE Fix64.Round de Floor")
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args(argv)

    sid = _resolve_session()
    rpc = lambda m, b, t=90: (_rpc(sid, m, [b], timeout=t).get("result") or {})   # noqa: E731

    # 0. le REGIME que ce montage va SERVIR, offline -- c'est ce qui dit si le montage discrimine
    #    AVANT toute mesure live. Sans `--separating-mult`, le multiplicateur est celui du seed BC.
    seed_bc_path = None
    mult_by_vis = {}
    if args.separating_mult:
        for vis, _ab, _fx, kmin, kmax, cfg in CARRIERS:
            mult_by_vis[vis] = separating_multiplier(cfg, kmin, kmax)
        seed_bc_path = write_patched_seed_bc(
            Path(args.state_file).with_name("_884avg_seedbc.json"), mult_by_vis)
    else:
        mult_by_vis = seed_bc_multipliers()
    print("[884] regime servi (ability_level 50) :")
    for _vis, _ab, _fx, kmin, kmax, cfg in CARRIERS:
        m = mult_by_vis.get(_vis)
        if m is None:
            print("  %-20s multiplicateur INCONNU (porteur absent du seed BC)" % cfg)
            continue
        mn = ability_var(cfg, kmin, 50, multiplier_pct=m)
        mx = ability_var(cfg, kmax, 50, multiplier_pct=m)
        if mn is None or mx is None:
            print("  %-20s BORNES ABSENTES au gameconfig" % cfg)
            continue
        s = int(mn) + int(mx)
        vals = {v: display_value(mn, mx, v) for v in VARIANTS}
        print("  %-20s mult=%3d [%5d,%5d] somme=%6d (mod4=%d) ratio=%.4f  port=%s float=%s "
              "floor=%s  -> arrondi %s"
              % (cfg, m, mn, mx, s, s % 4, float(mx) / float(mn),
                 vals["port"], vals["float"], vals["floor"],
                 "SEPARABLE" if vals["port"] != vals["floor"] else "NON separable (round==floor)"))

    rid = args.runner if args.runner is not None \
        else build(args.seed, Path(args.state_file), args.armor_target, seed_bc_path)
    print("[884] seed=%d runner=%s board=%s armor_target=%s seed_bc=%s"
          % (args.seed, rid, BOARD, args.armor_target, seed_bc_path))
    verdicts = {}
    try:
        dec = _rich(rpc, rid)
        if not (isinstance(dec, dict) and dec.get("ok")):
            print("[884] decisionView KO", file=sys.stderr)
            return 2
        owner = (_by_vis(dec).get(CARRIERS[0][0]) or {}).get("owner")
        dec = _advance_to_my_turn(rpc, rid, owner) or dec

        casted, measured = {}, set()
        for rnd in range(args.max_rounds):
            byvis = _by_vis(dec)
            enemies = [u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != owner]
            print("[884] round %d" % rnd)
            for vis, ab, fx, *_ in CARRIERS:
                if vis in measured:
                    continue
                u = byvis.get(vis)
                if u is None:
                    print("  %-20s ABSENT (mort ?)" % vis)
                    continue
                names = _effect_names(dec, u["id"])
                has_fx, has_rows = fx in names, _has_plan(dec, u["id"])

                # (a) l'effet est POSE et une unite alliee qui le porte a des tuiles classees
                bearer = find_bearer(dec, owner, fx)
                if bearer is not None:
                    if bearer.get("visualId") != vis:
                        print("  [porteur] %-20s effet %s confronte sur %s"
                              % (vis, fx, bearer.get("visualId")))
                    if do_measure(rpc, rid, dec, bearer, vis, verdicts, measured):
                        continue

                # (b) pas encore caste, et une tuile classee existe -> TEMOIN puis CAST
                #     ⚠ On ne caste QUE si le porteur a deja un plan : sinon il pose un effet a
                #     DUREE COURTE ("this turn and the next") a huit hexes de l'ennemi, et l'effet
                #     a expire quand il arrive enfin a portee -- mesure du run precedent, ou
                #     `tyranDeathleaper` a bien pose 1239 puis n'a JAMAIS eu de tuile classee.
                if not has_fx and vis not in casted and has_rows:
                    rows = capture_rows(rpc, rid, dec, u["id"])
                    off = replay_offline(rpc, rid, dec, u["id"], rows, "port")
                    ok = sum(1 for r, o in zip(rows, off or []) if o == r["nat"])
                    print("  [temoin] %-20s %d/%d lignes en accord SANS l'effet" % (vis, ok, len(rows)))
                    verdicts.setdefault("temoin:" + vis, (ok, len(rows)))
                    tgts, fh, meta = _ability_targets(rpc, rid, u["id"], ab)
                    if not fh and tgts:
                        gp = tgts[0].get("pos") or {}
                        if gp.get("col") is not None:
                            _step_toward(rpc, rid, dec, u, (gp["col"], gp["row"]))
                        dec = _rich(rpc, rid)
                        byvis = _by_vis(dec)
                        u = byvis.get(vis) or u
                        tgts, fh, meta = _ability_targets(rpc, rid, u["id"], ab)
                    pool = [t.get("targetId") for t in (fh or tgts)
                            if t.get("targetId") is not None]
                    pool.append(u["id"])       # abilities self-only : le natif ne rend aucune cible
                    hit = next((t for t in pool if _cast(rpc, rid, u["id"], ab, t)), None)
                    dec = _rich(rpc, rid)
                    byvis = _by_vis(dec)
                    after = _effect_names(dec, u["id"])
                    if fx in after:
                        casted[vis] = hit           # marque SEULEMENT si l'effet est LA
                    print("  [cast]   %-20s ability %d -> %s ; effet %s %s (natif targets=%s "
                          "fromHere=%s usable=%s)"
                          % (vis, ab, hit, fx, "POSE" if fx in after else "ABSENT",
                             [t.get("targetId") for t in tgts],
                             [t.get("targetId") for t in fh], (meta or {}).get("usable")))
                    if fx in after or find_bearer(dec, owner, fx) is not None:
                        # MESURER DANS LE MEME TOUR : les durees sont courtes
                        # (`TurnsFromRounds(1)`), et 1204 expire avant mon tour suivant.
                        b2 = find_bearer(dec, owner, fx)
                        if b2 is not None:
                            if b2.get("visualId") != vis:
                                print("  [porteur] %-20s effet %s confronte sur %s"
                                      % (vis, fx, b2.get("visualId")))
                            do_measure(rpc, rid, dec, b2, vis, verdicts, measured)
                        continue

                # (c) pas de tuile classee (ou cast refuse faute de cible) -> SE RAPPROCHER.
                #     Vaut AUSSI quand l'effet est deja pose : un porteur qui le porte sans plan
                #     ne confronte rien.
                _approach(rpc, rid, dec, u, enemies)
                dec = _rich(rpc, rid)
                byvis = _by_vis(dec)

            # L'ALLIE PSYKER (cible unique du cast 1100) doit lui aussi arriver a portee : il n'est
            # pas dans CARRIERS, donc rien ne le fait avancer -- et un `thousSorcerer` laisse au
            # spawn rend `targets = []` a `SorcerousFacade` pour toute la partie.
            ally = _by_vis(dec).get(ALLY_VIS)
            tza = _by_vis(dec).get(CARRIERS[0][0])
            if ally is not None and tza is not None and CARRIERS[0][0] not in measured:
                _step_toward(rpc, rid, dec, ally, _pos(tza))
                dec = _rich(rpc, rid)

            if len(measured) == len(CARRIERS):
                break
            _end_round(rpc, rid, owner)
            dec = _advance_to_my_turn(rpc, rid, owner)
            if dec is None:
                print("[884] impossible de revenir a mon tour", file=sys.stderr)
                break

        print("[884] --- BILAN ---")
        for vis, _ab, fx, *_ in CARRIERS:
            if vis in verdicts:
                res, same = verdicts[vis]
                print("  %-20s CONFRONTE : port %d/%d, predefined %d/%d (|ecart| max %s) ; "
                      "arrondi %s"
                      % (vis, res["port"][0], res["port"][1],
                         res["predefined"][0], res["predefined"][1], res["predefined"][2],
                         "SEPARE" if "floor" not in same else "NON separe"))
            else:
                print("  %-20s NON CONFRONTE (effet jamais pose ou aucune tuile classee)" % vis)
    finally:
        if not args.keep and args.runner is None:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--runner", str(rid)],
                           cwd=str(PYDIR), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
    return verdicts if return_verdicts else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
