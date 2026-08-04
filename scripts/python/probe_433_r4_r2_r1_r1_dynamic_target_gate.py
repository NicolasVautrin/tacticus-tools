"""probe #433-r4-r2-r1-r1 -- ce qui SEPARE deux abilities au MEME preset de ciblage.

LE FAIT A EXPLIQUER. `LightOfSanguinius` (1177) et `LeadingTheCharge` (1204) partagent le MEME
preset (`IdunBattle.Core.Services.TargetingOptions$$.cctor`, statique `+0x240`), donc le meme
`TargetingRange` (`UseWholeBoard`) ET le meme masque `Rules = 0x102004032` -- et rendent pourtant des
zones DIFFERENTES. Le discriminant est donc EN AVAL du `TargetingRange`.

LA CHAINE, LUE. `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` ne se contente pas de recopier
les 0x40 octets du preset dans `this.<TargetingOptions @+0x70>` : il ECRASE ensuite DEUX champs par
des delegues lies a des methodes VIRTUELLES de l'instance --

    this.TargetingOptions.<+0x30> = new TargetingOptions.DynamicTargetingRule(this, <klass+0x470>)
    this.TargetingOptions.<+0x38> = new TargetingOptions.DynamicTargetingTargetRule(this, <klass+0x480>)

`klass+0x470` / `klass+0x480` sont les champs `MethodInfo*` (a `+8` du debut de slot) des slots de
vtable commencant a `klass+0x468` / `klass+0x478` -- la vtable IL2CPP demarrant a `klass+0x138` avec
un pas de 0x10, ce sont les index 51 et 52. RESOLUS AU RUNTIME (`resolveVtableSlot`), ce sont
`GetDynamicInvalidCasterReason` et `GetDynamicInvalidTargetReason`.

Le champ `+0x38` est EXACTEMENT celui qu'invoque le troisieme predicat de
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` (la lambda
`u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2`, appliquee en
`RemoveAll` quand `Rules & 2`) : la tuile est RETIREE de la zone quand le delegue rend une raison non
nulle. C'est donc `GetDynamicInvalidTargetReason` -- et lui seul -- qui donne sa FORME a la zone
au-dela du `TargetingRange`.

CE QUE LE PROBE MESURE :

  * `--step gate` : pour CHAQUE classe derivant (transitivement) de `AActiveAbility`, l'adresse du
    slot `+0x478` resolue AU RUNTIME. Les classes dont l'adresse EGALE celle d'`AActiveAbility`
    n'ont pas de gate ; les autres surchargent. C'est la seule facon de conclure : les corps
    triviaux etant DEDUPLIQUES par IL2CPP, l'absence d'un `<X>$$GetDynamicInvalidTargetReason` dans
    les tables ne prouve RIEN. Croise avec l'inventaire des abilities `UseWholeBoard` du port.

  * `--step sweep` : la ZONE mesuree, natif contre port, sur un sweep de positions. Le terme
    s'isole par `bonus = util + 10 * sum_E d(P,E)` (branche A pure d'`EarlyWarningOverridePlaybook`)
    -- `0` = en portee, `50` = hors portee -- et la partition n'est attribuable qu'a UN ennemi
    vivant. Deux kits, choisis pour que le modele porte les SEPARE :
      - `bloodDante` : arme MELEE + `LightOfSanguinius` (whole-board, `constants.range = 5`)
        -> zone d'ability != portee d'arme, c'est le cas DISCRIMINANT ;
      - `astraDreir` : arme MELEE + `LeadingTheCharge` (whole-board, gate de MOUVEMENT).

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step gate
  python probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step sweep
  python probe_433_r4_r2_r1_r1_dynamic_target_gate.py --step all
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                     # noqa: E402
from rl_collect_batch import _resolve_session, _rpc               # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASTER = "tauCrisis"          # HERO du pool ; seul porteur `lineup` de 1077 EarlyWarningOverride
ABILITY = 1077                # ActiveAbilityType.EarlyWarningOverride
BOARD = "MC1_67"
SEED = "777"

AACTIVE_NS = "IdunBattle.Entities.Abilities"
AACTIVE_CLS = "AActiveAbility"
SLOT_DYNAMIC_TARGET = 0x478   # index 52 de la vtable (klass+0x138 + 52*0x10)
SLOT_DYNAMIC_CASTER = 0x468   # index 51


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# ------------------------------------------------------------------------------------------------
# --step gate : QUI surcharge `GetDynamicInvalidTargetReason` ?
# ------------------------------------------------------------------------------------------------
def _active_ability_classes():
    """Toutes les classes dont la chaine de parents atteint `AActiveAbility`, lues dans la table
    de symboles VERSIONNEE (`data/symbols/<build>/frida/classes.tsv`, colonnes
    `fullName \\t size \\t parent \\t ...`)."""
    build = (ROOT / "data" / "symbols").glob("*/frida/classes.tsv")
    parents: dict[str, str] = {}
    for path in build:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#!"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) >= 3 and cols[0] and "<" not in cols[0]:
                    parents[cols[0]] = cols[2]
    base = AACTIVE_NS + "." + AACTIVE_CLS
    out = []
    for name in parents:
        seen, cur = 0, name
        while cur and seen < 12:
            cur = parents.get(cur)
            seen += 1
            if cur == base:
                out.append(name)
                break
    return sorted(out)


def _split(full):
    i = full.rfind(".")
    return (full[:i], full[i + 1:]) if i > 0 else ("", full)


def _slot_addr(sid, ns, cls, off):
    try:
        res = _r(sid, "resolveVtableSlot", {"ns": ns, "cls": cls, "start": off, "end": off}, 30)
    except Exception as exc:                                      # pragma: no cover - diagnostic
        return None, str(exc)[:80]
    if not res.get("ok"):
        return None, (res.get("error") or "?")[:80]
    slots = res.get("slots") or []
    # `resolveVtableSlot` rend une chaine VIDE quand la lecture du slot echoue (classe jamais
    # initialisee -> vtable non materialisee). La traiter comme une adresse la ferait passer pour
    # une SURCHARGE (elle differe de la base) : c'est un « non resolu », pas un verdict.
    addr = (slots[0].get("ghidraVA") if slots else None) or None
    return addr, (None if addr else "slot non materialise (classe non initialisee)")


def step_gate(sid):
    # 2e source du volet PORTEE depuis `#433-r4-r2-r1-r2-r2-r1-r1` : le `range` vit avec les trois
    # autres champs du meme ctor, `ability_range.TARGETING_RANGE_BY_ABILITY` ayant ete supprimee.
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    from engine.runner.abilities.handler import ABILITY_CLASSES

    whole = set()
    for aid, cls in ABILITY_CLASSES.items():
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        rng = getattr(opts, "range", None) if opts is not None else None
        if rng is not None and getattr(rng, "use_whole_board", False):
            whole.add(getattr(cls, "__name__", ""))
    for aid, opts in TARGETING_OPTIONS_UNPORTED.items():
        if getattr(opts.range, "use_whole_board", False):
            from engine.entities.active_ability_type import ActiveAbilityType
            try:
                whole.add(ActiveAbilityType(aid).name + "Ability")
            except ValueError:
                pass

    base_addr, err = _slot_addr(sid, AACTIVE_NS, AACTIVE_CLS, SLOT_DYNAMIC_TARGET)
    print("base AActiveAbility.GetDynamicInvalidTargetReason = %s (%s)" % (base_addr, err))
    if base_addr is None:
        return 1

    names = _active_ability_classes()
    print("classes derivant de AActiveAbility (classes.tsv) : %d" % len(names))
    overriders, missing = [], []
    for full in names:
        ns, cls = _split(full)
        addr, err = _slot_addr(sid, ns, cls, SLOT_DYNAMIC_TARGET)
        if addr is None:
            missing.append((full, err))
            continue
        if addr != base_addr:
            overriders.append((full, cls, addr, cls in whole))
    print("")
    print("SURCHARGES de GetDynamicInvalidTargetReason : %d / %d" % (len(overriders), len(names)))
    for full, cls, addr, is_whole in sorted(overriders):
        print("  %-4s %-72s %s" % ("WB" if is_whole else "", full, addr))
    print("")
    hit = sorted(c for _, c, _, w in overriders if w)
    print("dont WHOLE_BOARD : %d / %d  -> %s" % (len(hit), len(whole), ", ".join(hit)))
    no_gate = sorted(w for w in whole if w not in {c for _, c, _, _ in overriders})
    print("WHOLE_BOARD SANS gate (zone = tout le plateau) : %d -> %s"
          % (len(no_gate), ", ".join(no_gate)))
    if missing:
        print("non resolues : %d (ex. %s)" % (len(missing), missing[:3]))
    return 0


# ------------------------------------------------------------------------------------------------
# --step sweep : la ZONE, natif contre port
#
# Le MONTAGE n'est pas redefini ici : il est DELEGUE a
# `probe_433_r4_r2_r1_ability_range.step_seam`, qui porte deja le verrou « exactement UN ennemi
# vivant » (sans lui la partition n'est attribuable a aucun kit) et le sweep `ncEvaluate`. Ce
# probe-ci ne rajoute que la VENTILATION PAR DISTANCE, seule lecture qui distingue un rayon `r`
# d'un rayon `r + 1` -- et donc le `+1` de `GetFreeAdjacentTiles`.
# ------------------------------------------------------------------------------------------------
def step_sweep(sid, enemy, dist=8, movement=6):
    from probe_433_r4_r2_r1_ability_range import step_seam
    from engine.services import ability_range as ar

    res = step_seam(verbose=False, enemy=enemy, want=dist, movement=movement)
    if "error" in res:
        print("REFUS (%s) : %s" % (enemy, res["error"]))
        return 1
    vid = res["enemy_visual"]
    Y = tuple(res["Y"])
    in_range = {tuple(p) for p in res["natif_in_range"]}
    out_range = {tuple(p) for p in res["natif_out_range"]}
    sweep = sorted(in_range | out_range)
    reach = ar.unit_threat_reach(vid)
    elev = res.get("elev") or None
    modeled = {P for P in sweep
               if ar.is_tile_in_range_of_any_ability(Y, P, vid, elev_by_pos=elev)}

    by_d = {}
    for P in sweep:
        by_d.setdefault(hexgeo.distance(P, Y), []).append(P in in_range)
    print("kit=%-20s sweep=%-3d  port reach=%d" % (vid, len(sweep), reach))
    for d in sorted(by_d):
        v = by_d[d]
        print("  d=%-2d natif in=%2d/%-2d   port in=%s"
              % (d, sum(1 for x in v if x), len(v), "OUI" if d <= reach else "non"))
    fp = sorted(modeled - in_range)
    fn = sorted(in_range - modeled)
    print("  FP=%d  FN=%d  -> %s" % (len(fp), len(fn), "EXACT" if not fp and not fn else "DIVERGE"))
    if fp:
        print("  faux positifs : %r" % (fp[:12],))
        _explain_false_positives(sid, Y, fp, in_range, ar, enemy)
    if fn:
        print("  faux negatifs : %r" % (fn[:12],))
    return 0 if not fp and not fn else 1


def _explain_false_positives(sid, Y, fp, in_range, ar, enemy):
    """ATTRIBUER les faux positifs residuels, au lieu de les supposer.

    Le gate `GATE_FREE_ADJACENT_IN_CONFIG_RANGE` porte sur les tuiles LIBRES adjacentes a la cible
    (`<IBattleQuery slot 0x53>` = `GetFreeAdjacentTiles`) : le port n'en garde que la consequence de
    DISTANCE (`config.range + 1`) et ignore le mot « LIBRES ». Si une tuile a `d = range + 1` n'a
    AUCUNE voisine walkable a `d <= range`, le natif l'exclut et le port la garde. On le VERIFIE en
    lisant le plateau plutot qu'en l'affirmant."""
    from probe_433_r4_r2_r1_ability_range import _board_maps, _build as _seam_build

    rid, err = _seam_build()
    if rid is None:
        print("  (attribution impossible : build KO -- %s)" % (err,))
        return
    try:
        elev, walk = _board_maps(sid, rid)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    reach = ar.unit_threat_reach(enemy)
    inner = reach - 1                       # `config.range` : ce que `GetDistance(t, casterTiles)` borne

    def _line(P, tag):
        nbrs = [N for N in hexgeo.neighbors(P[0], P[1]) if tuple(N) in walk]
        close = [N for N in nbrs if hexgeo.distance(N, Y) <= inner]
        print("    %-11s %r d=%d elev=%s : voisines walkable=%d dont a d<=%d : %d %r"
              % (tag, P, hexgeo.distance(P, Y), elev.get(P), len(nbrs), inner,
                 len(close), [(N, elev.get(tuple(N))) for N in close]))

    print("    tuile de l'ennemi Y=%r elev=%s" % (Y, elev.get(Y)))
    for P in fp:
        _line(P, "FAUX POSITIF")
    # Contre-epreuve : les tuiles de MEME distance que le natif ACCEPTE.
    for P in sorted(P for P in in_range if hexgeo.distance(P, Y) == reach)[:4]:
        _line(P, "(natif OK)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["gate", "sweep", "all"])
    ap.add_argument("--enemy", action="append", default=None)
    args = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    if args.step in ("gate", "all"):
        rc |= step_gate(sid)
    if args.step in ("sweep", "all"):
        for enemy in (args.enemy or ["bloodDante", "astraDreir"]):
            print("")
            rc |= step_sweep(sid, enemy)
    return rc


if __name__ == "__main__":
    sys.exit(main())
