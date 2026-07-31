#!/usr/bin/env python
"""probe #382 -- l'`AbilityState` d'un effet vient de sa SOURCE, pas de son PORTEUR.

CRITERION BINAIRE : « quand porteur != source, le port indexe-t-il les variables de l'effet sur
l'etat d'ability de la SOURCE, comme le natif ? », mesure dans un montage ou les deux etats sont
DISSOCIES -- c.-a-d. ou repondre « porteur » et repondre « source » ne donnent pas le meme nombre.

CE QUE LE NATIF FAIT, relu au desassemblage (le natif *bake*, il ne lit pas le porteur) :

    IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)
        -> IdunBattle.Entities.Blueprints$$Effect(id)                 # cree l'entite-effet
        -> EffectComponent[+0x18 .. +0x38] = *abilityState            # COPIE 0x24 octets = le BAKE
    IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference  # relit ce MEME +0x18
    IdunBattle.DSL.AbilityStateFromEffectSelector$$Select             # idem, cote DSL

L'`abilityState` recu est celui du noeud DSL `AddEffect(<type>, <abilityStateReference>, source,
targets, turns)`, evalue sur l'ability QUI POSE
(`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$get_AbilityStateReference` ->
`IdunBattleLogic.Entities.DSLSelectors$$AbilityState(entities, owner, abilityType)`) -- donc sur le
CASTER. L'effet ne consulte JAMAIS son porteur.

MONTAGE (le seul connu qui DISSOCIE les deux etats) : `SagaOfTheWarriorBorn_OtherSpaceWolves` (1224).
Ragnar (`spaceBlackmane`, SOURCE) execute un Hero ennemi -> le natif pose 1224 sur les Space Wolves
AMIS ; Ulf (`spaceWulfen`, PORTEUR) charge. `--unit-stat spaceBlackmane:PassiveAbilityLevel=1`
descend le niveau de la SOURCE a 1 en laissant le porteur a 50.

  * niveau SOURCE  = 1  -> `extraHits[1]`  = 1 -> salve de 4 coups (3 d'arme + 1)
  * niveau PORTEUR = 50 -> `extraHits[50]` = 3 -> salve de 6 coups

⚠ `buildNormalizedBC` MASQUE la moitie de l'ecart : il ecrit le MEME `targetAbilityLevel` dans
`ActiveAbilityLevel` et `PassiveAbilityLevel` de TOUTES les unites (`normalize-bc/json-build.ts`).
Sans `--unit-stat`, la garde serait VERTE ET VIDE. Le probe REFUSE de mesurer si la dissociation
n'est pas etablie -- un vert degrade vaudrait moins que rien.

Le MULTIPLICATEUR de rarete, lui, reste per-unite meme normalise (mesure : source 200, porteur 180)
-> il est verifie separement, et c'est lui qui porte la face CRIT (`extraCritDmg` est la seule
variable de l'ability listee dans `variablesAffectedByRarityBonus`).

Usage (depuis scripts/python, session warmee) :
    python probe_382_effect_source_ability_state.py                 # montage live (2 couples)
    python probe_382_effect_source_ability_state.py --scan          # recensement OFFLINE, sans jeu

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

#: PORTEUR de 1224 -- Space Wolf du pool, 3 coups d'arme (base discrete).
ALLY = "spaceWulfen"
#: SOURCE -- seul porteur de l'ability `SagaOfTheWarriorBorn`.
RAGNAR = "spaceBlackmane"
VICTIM = "necroOverlord"          # Hero ennemi (trait 0x10) execute par Ragnar
SURVIVOR = "necroWarden"          # encaisseur de la charge de l'allie
EFFECT_NAME = "SagaOfTheWarriorBorn_OtherSpaceWolves"
EFFECT_TYPE = 1224
#: Niveau force sur la SOURCE. 1 est le plancher natif (`Idun.Shared.Level$$ToZeroBasedIndex` LEVE
#: sur <= 0), et `extraHits[1]` = 1 contre `extraHits[50]` = 3 -> l'ecart le plus large.
SOURCE_LEVEL = 1

#: Les trois champs du canal `AbilityState` cote port (`BaseEffect`).
CHANNEL_FIELDS = ("ability_variables_multiplier", "active_ability_level", "ability_level")
_CHANNEL_RE = re.compile(r"ability_variables_multiplier|active_ability_level|ability_level"
                         r"|multiplier_pct")


# ───────────────────────────────── recensement OFFLINE (sans jeu) ─────────────────────────────────

def _source_of(obj) -> str:
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return ""


def _expand_module_helpers(src: str, mod, depth: int = 2) -> str:
    """Ajoute a `src` le corps des fonctions de MODULE qu'il appelle (profondeur `depth`).

    Une classe d'effet delegue souvent son indexation a un helper du meme module (ex.
    `hits.py::_effect_level(eff)`, `unbreakable_duty.py::_level(eff)`) : sans cette expansion, le
    balayage textuel rendrait un faux negatif. LIMITE ASSUMEE, dite ici plutot que masquee : seules
    les fonctions du MEME module sont suivies, et sur `depth` niveaux."""
    seen: set = set()
    out = [src]
    frontier = [src]
    for _ in range(max(0, depth)):
        nxt = []
        for chunk in frontier:
            for name in set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", chunk)):
                if name in seen:
                    continue
                seen.add(name)
                fn = getattr(mod, name, None)
                if inspect.isfunction(fn) and getattr(fn, "__module__", None) == mod.__name__:
                    s = _source_of(fn)
                    if s:
                        out.append(s)
                        nxt.append(s)
        frontier = nxt
    return "\n".join(out)


def scan_registry() -> dict:
    """Recensement OFFLINE des entrees d'`EFFECT_CLASSES` SENSIBLES au canal `AbilityState`.

    Une entree est SENSIBLE si sa classe (corps propre + bases jusqu'a `BaseEffect` exclu + helpers
    de module appeles, cf. `_expand_module_helpers`) MENTIONNE l'un des trois champs du canal. C'est
    la condition NECESSAIRE pour que lire l'etat de la SOURCE plutot que celui du PORTEUR change un
    nombre : une classe qui n'y touche pas est indifferente au correctif, quel que soit l'ecart
    porteur/source.

    Rend `{"total", "sensitive", "insensitive", "by_class"}`. Ce que ce balayage NE dit PAS : si le
    porteur PEUT differer de la source pour cette entree (c'est une propriete du noeud `AddEffect`
    de l'ability qui pose, cote natif -- non balayee ici)."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.base import BaseEffect

    by_class: dict = {}
    for name, klass in EFFECT_CLASSES.items():
        key = "%s.%s" % (klass.__module__, klass.__qualname__)
        if key not in by_class:
            mod = importlib.import_module(klass.__module__)
            chunks = []
            for k in klass.__mro__:
                if k is BaseEffect or k is object:
                    break
                chunks.append(_source_of(k))
            src = _expand_module_helpers("\n".join(chunks), mod)
            by_class[key] = {"sensitive": bool(_CHANNEL_RE.search(src)), "names": []}
        by_class[key]["names"].append(name)
    names_sensitive = sorted(n for v in by_class.values() if v["sensitive"] for n in v["names"])
    names_insensitive = sorted(n for v in by_class.values() if not v["sensitive"]
                               for n in v["names"])
    return {"total": len(EFFECT_CLASSES), "sensitive": names_sensitive,
            "insensitive": names_insensitive, "by_class": by_class}


# ───────────────────────────────── montage LIVE (regime dissocie) ─────────────────────────────────

def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _effect_names(u):
    return [e.get("name") for e in (u.get("effects") or []) if isinstance(e, dict)]


def _ability_state_rows(snap: dict) -> dict:
    """`{entityId: (mult, passiveLevel, activeLevel)}` LU du `combatSnapshot` -- l'oracle
    INDEPENDANT du port pour l'etat d'ability de chaque unite."""
    from engine.runner.snapshot import _ability_state_from_config
    return {int(u["entityId"]): _ability_state_from_config(u.get("unitConfig"))
            for u in (snap.get("units") or []) if u.get("entityId") is not None}


def cross_unit_effects(rec, state) -> list:
    """Toutes les instances materialisees dont la SOURCE differe du PORTEUR, avec l'etat qu'elles
    portent et celui que le `combatSnapshot` attribue a leur source.

    Invariant transverse (il ne parle PAS que de 1224) : pour toute instance dont la source est
    RESOLVABLE et differente, le triplet porte doit etre celui de la SOURCE."""
    rows = _ability_state_rows(rec["snapshot"]["snap"])
    out = []
    for carrier, effs in (state.effects.by_unit or {}).items():
        for e in effs:
            src = getattr(e, "source", None)
            if src is None or int(src) == int(carrier) or int(src) not in rows:
                continue
            out.append({
                "carrier": int(carrier), "source": int(src), "name": e.name,
                "effectType": e.effect_type,
                "carried": (int(e.ability_variables_multiplier or 100),
                            e.ability_level, e.active_ability_level),
                "expected_source": rows[int(src)],
                "carrier_state": rows.get(int(carrier)),
            })
    return out


def run(seed: str = "777", board: str = "MC1_67", verbose: bool = True,
        source_level: int = SOURCE_LEVEL) -> dict:
    """Monte le regime DISSOCIE et rend le dict de mesure.

    `why` non nul = montage NON INSTALLE (l'appelant doit ECHOUER, jamais skipper : un skip vert
    mentirait sur une garde qui n'a rien garde)."""
    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import CHARGE, ChargeRegimeHarness
    from probe_366_r1_saga_other_space_wolves import execute_hero

    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "warmupGameSingletons", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        return {"ok": False, "why": "warmup KO : %s" % str(w)[:200]}

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    fd, state_file = tempfile.mkstemp(prefix="p382_%s_%s_" % (board, seed), suffix=".json")
    os.close(fd)
    Path(state_file).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", state_file, "--board", board,
            "--p-units", "%s,%s" % (RAGNAR, ALLY),
            "--a-units", "%s,%s" % (VICTIM, SURVIVOR),
            "--hp-target", "120000", "--hp-player", "120000", "--no-ai",
            "--unit-stat", "%s:Health=400,RemainingHealth=400" % VICTIM,
            # DISSOCIATION -- applique au MEME endroit que --hp-target, donc APRES la normalisation
            # (qui, elle, pose 50 partout). L'inverser rendrait la garde verte et vide.
            "--unit-stat", "%s:PassiveAbilityLevel=%d" % (RAGNAR, int(source_level))]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        Path(state_file).unlink(missing_ok=True)
        return {"ok": False, "why": "build KO : %s" % (p.stderr or p.stdout or "")[-400:]}
    rid = json.loads(Path(state_file).read_text())["runnerId"]
    Path(state_file).unlink(missing_ok=True)
    if verbose:
        print("[p382] runner %s (board %s seed %s, %s.PassiveAbilityLevel=%d)"
              % (rid, board, seed, RAGNAR, source_level))

    res: dict = {"ok": False, "runner": rid, "board": board, "seed": str(seed)}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        dv = h.dview()
        ally, ragnar, victim = (h.by_visual(ALLY, dv), h.by_visual(RAGNAR, dv),
                                h.by_visual(VICTIM, dv))
        if ally is None or ragnar is None or victim is None:
            res["why"] = ("roster incomplet (ally=%s ragnar=%s victim=%s)"
                          % (ally is not None, ragnar is not None, victim is not None))
            return res
        res["ally_id"], res["source_id"] = int(ally["id"]), int(ragnar["id"])

        # --- GARDE DE DISSOCIATION, AVANT toute mesure ------------------------------------------
        rows = _ability_state_rows(rpc("combatSnapshot", {"runnerId": rid}, 60))
        res["carrier_state"] = rows.get(int(ally["id"]))
        res["source_state"] = rows.get(int(ragnar["id"]))
        if res["carrier_state"] is None or res["source_state"] is None:
            res["why"] = "unitConfig absent (carrier=%s source=%s)" % (res["carrier_state"],
                                                                      res["source_state"])
            return res
        if res["source_state"][1] == res["carrier_state"][1]:
            res["why"] = ("regime NON DISSOCIE : niveau source == niveau porteur (%s) -- la mesure "
                          "serait verte et vide" % (res["source_state"][1],))
            return res

        if not execute_hero(h, RAGNAR, victim["id"]):
            res["why"] = "Ragnar n'a pas execute %s -- trigger OnDeath non exerce" % VICTIM
            return res
        names = _effect_names(h.by_visual(ALLY))
        if EFFECT_NAME not in names:
            res["why"] = "%s absent de l'allie apres le kill (vus : %s)" % (EFFECT_NAME, names)
            return res

        rec = h.run(caster_visual=ALLY, regime=CHARGE)
        if rec is None:
            res["why"] = "geometrie CHARGE non realisable"
            return res
        if not rec["live_ok"] or not rec["live_per_hit"]:
            res["why"] = "attaque live refusee/vide"
            return res
        if not any(u.get("id") == rec["target"] for u in h.alive()):
            res["why"] = "cible u%s morte pendant la salve -- n live tronque" % rec["target"]
            return res
        off = h.replay_offline(rec)
        if rec["target"] not in off["charged"]:
            res["why"] = ("la cible n'entre pas dans ChargedUnitIds (charged=%s target=%s) -- le "
                          "gate IsCharging n'est pas exerce" % (off["charged"], rec["target"]))
            return res

        carried = [e for e in (off["state"].effects.by_unit.get(rec["caster"]) or [])
                   if e.effect_type == EFFECT_TYPE or e.name == EFFECT_NAME]
        if not carried:
            res["why"] = "1224 non materialise offline sur l'allie -- rien a confronter"
            return res
        e = carried[0]
        res.update({
            "ok": True,
            "live_per_hit": rec["live_per_hit"], "off_per_hit": off["per_hit"],
            "effect_ability_level": e.ability_level,
            "effect_multiplier": int(e.ability_variables_multiplier or 100),
            "cross_unit": cross_unit_effects(rec, off["state"]),
        })
        if verbose:
            print("[p382] source u%s state=%s | porteur u%s state=%s"
                  % (res["source_id"], res["source_state"], res["ally_id"], res["carrier_state"]))
            print("[p382] instance 1224 : ability_level=%s multiplier=%s"
                  % (res["effect_ability_level"], res["effect_multiplier"]))
            print("[p382] LIVE    n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"]))
            print("[p382] OFFLINE n=%d %s" % (len(off["per_hit"]), off["per_hit"]))
            print("[p382] VERDICT %s" % ("OK" if off["per_hit"] == rec["live_per_hit"]
                                         else "DIVERGE"))
        return res
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true", help="recensement OFFLINE seul (sans jeu)")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--source-level", type=int, default=SOURCE_LEVEL)
    a = ap.parse_args()

    if a.scan:
        s = scan_registry()
        print("[scan] EFFECT_CLASSES = %d entrees, %d classes distinctes"
              % (s["total"], len(s["by_class"])))
        print("[scan] SENSIBLES au canal AbilityState : %d entrees" % len(s["sensitive"]))
        print("[scan] INDIFFERENTES                   : %d entrees" % len(s["insensitive"]))
        print("[scan] indifferentes : %s" % ", ".join(s["insensitive"]))
        return 0

    r = run(seed=a.seed, board=a.board, source_level=a.source_level)
    if not r.get("ok"):
        print("[p382] REFUS : %s" % r.get("why"))
        return 2
    for row in r["cross_unit"]:
        print("[p382] cross-unit u%s <- u%s %s : porte %s, source %s"
              % (row["carrier"], row["source"], row["name"], row["carried"],
                 row["expected_source"]))
    return 0 if r["off_per_hit"] == r["live_per_hit"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
