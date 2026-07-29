#!/usr/bin/env python
"""probe_245_valkyrie_targeting -- ARMEMENT du gate de cible de ValkyrieStrike (1018,
`astraSmnVoxcaster` « Cadian Vox-caster »).

CE QUE CE PROBE MESURE
----------------------
`ValkyrieStrikeAbility` entrait dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et
rend 0 immediatement : AUCUN gate. Degradation PERMISSIVE -- ni erreur ni crash.

FORME DE CTOR = **PRESET STATIQUE COPIE** (la 3e des trois formes).
`IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$.ctor` n'appelle AUCUN
`IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du champ STATIQUE de
`TargetingOptions` a l'offset +0x1c0 du bloc `<class>+0xb8`, puis
`AActiveAbility..ctor(this, &opts, 2, 0)` (le `2` = `AbilityAttackType.Others`, deja au registre).
Le masque EFFECTIF est la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a
`<preset>+0x28` = `*(statics+0x1e8)` = 0x6000040 :

    0x40       TargetIsTile                     -> domaine TUILE ; tuile non marchable = refus
    0x2000000  AllowObscuredTargetByElevation   -> leve la ligne de vue (elevation)
    0x4000000  AllowObscuredTargetByWalls       -> leve la ligne de vue (murs)

et le MEME preset porte le volet PORTEE : `TargetingRange` <- `TargetingRange` statique +0x48
(`useWholeBoard`) -> `GetRange` court-circuite, AUCUN test de portee ; `forceMeleeTarget`
(`<preset>+0x20`) = 1 = `RangedBool.False` -> aucun clamp melee. ATTENTION : `ArmoriumCherub` (1014)
a la MEME forme de ctor mais le preset +0x140 (0x4002). Les presets ne sont PAS interchangeables.

POURQUOI LE PORTEUR DOIT ETRE LE VRAI
-------------------------------------
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (surcharge 4 arguments, celle que le
RPC `abilityReason` invoque) commence par
`ActiveAbilityComponent.GetOrNull(<caster>, abilityType)` et rend `GenericBrokenTargetingRule(1)`
(= `ValidRequest`) SANS evaluer la cascade quand le caster ne PORTE PAS l'ability -- ou quand
`ActiveAbility.CanCurrentlyBeUsed` est faux (cooldown initial). Interroger l'oracle avec un caster
arbitraire, ou avant la purge du cooldown, ne mesurerait donc RIEN du masque.

`astraSmnVoxcaster` est un SUMMON (`kind = summons`) : hors `--list-pool`, et ses seuls poseurs
gameconfig sont 4 `EnvFactionSummons:Armageddon*` (summons d'ENVIRONNEMENT) -> pas de summoner de
heros. Il est en revanche DEJA au catalogue `BC.Units` du seed BC, donc spawnable en passant par
`initAndStart(playerUnits=[...])` DIRECTEMENT : le filtre de pool de `rl_duel build` est une
commodite Python, le moteur accepte tout `unitId` present au catalogue -- meme voie que
`tests/engine/runner/test_catalog_inject_live.py`.

DEUX AMENAGEMENTS DE L'ENTREE DE CATALOGUE, ET POURQUOI ILS NE BIAISENT PAS LA MESURE
------------------------------------------------------------------------------------
L'entree du seed BC est reprise telle quelle SAUF deux champs :

  * `Health` 0 -> 5000. L'entree capturee d'un summon porte `Health = 0` (ses PV viennent des
    variables `summonHp` du SUMMONER au moment du spawn natif) ; spawne a la main, le Vox-caster
    naitrait a 1 PV. Aucune regle du filtre statique ne lit les PV.
  * le trait `Summon` est RETIRE (`Imperial` + `BattleFatigue` conserves). MESURE (balayage des 4
    variantes de traits, meme board/seed) : `CanStillBeUsed` vaut `false` SSI le trait `Summon` est
    present, et le court-circuit d'ability ci-dessus rend alors `0x1` pour TOUTES les cibles --
    aucune cascade evaluee, donc rien de mesurable. C'est le gate d'USAGE, pas celui de CIBLAGE :
    la couche `TargetingRule` n'a aucun flag de cooldown/usage (cf. l'en-tete de
    `engine/runner/abilities/targeting.py`).

Le retrait du trait ne peut pas deplacer un verdict de la cascade pour CE masque, et ca se lit sur
le decompile plutot que sur la mesure : les seules regles du filtre statique qui consultent un trait
portent sur la CIBLE (`TargetIsSummon` 0x2000, `TargetIsHero` bit 50, `TargetIsNotAnObject` bit 33)
et AUCUNE n'est dans `0x6000040` ; le trait du CASTER n'entre que par
`RangedBoolExtensions$$IsTrue(IfRangedCaster / IfNotRangedCaster)`, or ce preset pose
`forceMeleeTarget = RangedBool.False` et `onlyAdjacent = RangedBool.False` -- deux constantes, aucun
trait lu -- et `useWholeBoard` fait de toute facon sauter tout le volet portee.

LE PIEGE DU CODE 0x1, ET COMMENT CE PROBE S'EN PROTEGE
------------------------------------------------------
`0x1` (`ValidRequest`) a DEUX causes natives distinctes sur ce chemin : (a) l'ability n'est pas
utilisable (le court-circuit ci-dessus) et (b) la regle `TargetIsTile` sur une tuile NON MARCHABLE
(le natif REUTILISE le litteral 1). Lire (b) alors qu'on mesure (a) serait une fausse validation.
Deux gardes : on n'interroge qu'apres avoir vu `abilityState.usable == true`, et on exige, DANS LE
MEME etat fige, qu'au moins une tuile MARCHABLE rende `0x0` -- ce qui prouve que le court-circuit
(a) ne mord pas et que le `0x1` des tuiles non marchables vient bien de la regle.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF. Le probe rejoue ensuite le gate OFFLINE sur le MEME etat fige, dans DEUX versions :
  * APRES  = l'ability du registre (masque pose par cette tranche) ;
  * AVANT  = la MEME classe avec `TARGETING_OPTIONS = None` -- l'etat de `master` avant la tranche.
Critere : accord natif/APRES sur TOUTES les lignes, et au moins une ligne ou le natif REFUSE alors
qu'AVANT rendait 0 (« refusait de refuser »).

Usage (depuis scripts/python, session Frida chaude) :
    python probe_245_valkyrie_targeting.py
    python probe_245_valkyrie_targeting.py --seed 31337 --board C4_09

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_inject as CI                                          # noqa: E402
import rl_duel as RD                                                 # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import get_invalid_target_reason  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

VALKYRIE_STRIKE = 1018
VOXCASTER = "astraSmnVoxcaster"     # SUMMON -- absent du pool, present au catalogue BC
ENEMY = "necroWarden"
BOARD = "MC1_67"
SEED = 777
RANK = 17
MAX_TILES = 6                       # tuiles echantillonnees par categorie (marchable / non)
# Entree de catalogue : les DEUX seuls champs amenages (cf. l'en-tete pour la justification).
VOX_HEALTH = 5000
VOX_TRAITS = ["Imperial", "BattleFatigue"]      # le trait `Summon` desarme `CanStillBeUsed`


def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: int, board: str):
    """Runner isole ou le VOXCASTER est spawne cote joueur. `owner` = un state-file PROPRE sous
    `logs/` (jamais `data/`, qui est versionne) : c'est la cle de propriete du harnais."""
    state_file = ROOT / "logs" / ("_probe245-%d.json" % os.getpid())
    state_file.parent.mkdir(parents=True, exist_ok=True)
    bc0, added, ab_added, _marker = CI.augment(RD._load_seed_bc(None), [VOXCASTER, ENEMY], rank=RANK)
    dump = RD._load_board_dump(board)
    template, _pool, _pool_mow = RD._normalize_and_extract_pool(sid, bc0, RANK, board_dump=dump)
    bc = copy.deepcopy(template)
    vox_entry = next((u for u in bc["Units"] if u.get("Id") == VOXCASTER), None)
    if vox_entry is None:
        raise RuntimeError("%s absent du catalogue BC.Units" % VOXCASTER)
    vox_entry["Health"] = VOX_HEALTH
    vox_entry["Traits"] = list(VOX_TRAITS)
    RD._patch_predefined_units(bc, [ENEMY, ENEMY])
    spawns = RD._spawn_points_by_twpi(bc)
    pts = spawns.get(0) or []
    if not pts:
        raise RuntimeError("aucun spawn point joueur sur %s" % board)
    pu = [{"unitId": VOXCASTER, "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(pts[0][0]), "row": int(pts[0][1])}]
    resp = _rpc(sid, "initAndStart",
                [{"configJson": json.dumps(bc), "seed": seed, "playerUnits": pu,
                  "owner": str(state_file.resolve())}], timeout=90)
    rid = ((resp or {}).get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % json.dumps(resp)[:400])
    state_file.write_text(json.dumps({"runnerId": int(rid)}), encoding="utf-8")
    return int(rid), added, ab_added, state_file


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)


def _voxcaster(dv):
    for u in (dv.get("units") or []):
        if u.get("visualId") in (VOXCASTER, "astraNpc3Voxcaster"):
            return u
    return None


def _ability_usable(sid, rid, cid) -> bool:
    """`ActiveAbility.CanCurrentlyBeUsed` tel que le RPC l'expose (`abilityState.usable`)."""
    nat = _r(sid, "abilityReason",
             {"runnerId": rid, "casterId": cid, "abilityType": VALKYRIE_STRIKE}, 60)
    st = (nat or {}).get("abilityState") or {}
    return bool(st.get("usable"))


def _to_my_turn(sid, rid, maxit=4):
    """Rend la main au camp du Vox-caster (chaine de `endturn`). Le deploiement peut donner le
    premier tour a l'adversaire selon le board."""
    for _ in range(maxit):
        dv = _dv(sid, rid)
        vox = _voxcaster(dv)
        if vox is None or vox.get("ctrl"):
            return dv, vox
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    dv = _dv(sid, rid)
    return dv, _voxcaster(dv)


def _port_reason(dv, ob, snap, board, caster_id, target_id, variant: str) -> int:
    """Le gate OFFLINE sur un etat FRAIS.

      * `apres`     = l'ability du registre (masque pose par cette tranche) ;
      * `avant`     = la MEME classe, `TARGETING_OPTIONS = None` -> l'etat de `master` ;
      * `sansTile`  = CONTREFACTUEL : le masque prive du seul bit qui mord (`TargetIsTile`).
        Il doit rendre 0 la ou le natif refuse -- preuve que le bit est PORTEUR et pas decoratif.
    """
    from dataclasses import replace as _replace
    st = load_state(dv, ob, snap, board=board)
    klass = ABILITY_CLASSES[VALKYRIE_STRIKE]
    if variant == "apres":
        ability = klass()
    elif variant == "avant":
        class _NoMask(klass):            # meme classe, masque retire -> AUCUN gate
            __slots__ = ()
            TARGETING_OPTIONS = None
        ability = _NoMask()
    else:
        class _NoTile(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(
                klass.TARGETING_OPTIONS,
                rules=int(klass.TARGETING_OPTIONS.rules) & ~int(TR.TargetIsTile))
        ability = _NoTile()
    return int(get_invalid_target_reason(st, int(caster_id), int(target_id), ability))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--tiles", type=int, default=MAX_TILES,
                    help="tuiles echantillonnees par categorie (marchable / non marchable)")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    rid, added, ab_added, state_file = _build(sid, a.seed, a.board)
    print("[build] runner=%d board=%s seed=%d catalog_added=%s abilities_added=%s"
          % (rid, a.board, a.seed, added, ab_added))
    ok = True
    try:
        dv, vox = _to_my_turn(sid, rid)
        if vox is None:
            print("[FAIL] Voxcaster absent du decisionView -> spawn KO")
            return 2
        cid = int(vox["id"])
        usable = _ability_usable(sid, rid, cid)
        print("[state] caster=u%d ctrl=%s pos=%s hp=%s abilities=%s usable=%s"
              % (cid, vox.get("ctrl"), vox.get("pos"), vox.get("hp"),
                 [x.get("id") for x in (vox.get("abilities") or [])], usable))
        if not usable:
            print("[FAIL] 1018 non utilisable -> l'oracle rendrait 0x1 pour la MAUVAISE raison "
                  "(court-circuit d'ability), mesure impossible")
            return 2

        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[FAIL] boardGraph indisponible")
            return 2
        board = Board(bg["tiles"], adjacency="native_sym")
        tiles = list(bg["tiles"])
        allw = [t for t in tiles if t.get("walkable")]
        allnw = [t for t in tiles if not t.get("walkable")]
        # echantillon DISPERSE (pas les N premieres, qui sont toutes dans la meme colonne)
        step_w = max(1, len(allw) // a.tiles)
        step_nw = max(1, len(allnw) // a.tiles)
        walk = allw[::step_w][:a.tiles]
        nowalk = allnw[::step_nw][:a.tiles]
        print("[board] %d tuiles : %d marchables, %d NON marchables (echantillon %d/%d)"
              % (len(tiles), len(allw), len(allnw), len(walk), len(nowalk)))

        cases = []
        for u in (dv.get("units") or []):
            cases.append(("unit  " + str(u.get("visualId")), int(u["id"])))
        for t in walk:
            cases.append(("tile-WALK   (%d,%d)" % (t["col"], t["row"]), int(t["id"])))
        for t in nowalk:
            cases.append(("tile-NOWALK (%d,%d)" % (t["col"], t["row"]), int(t["id"])))

        rows = []
        for label, tid in cases:
            nat = _r(sid, "abilityReason",
                     {"runnerId": rid, "casterId": cid, "targetId": tid,
                      "abilityType": VALKYRIE_STRIKE}, 60)
            tr = (nat or {}).get("targetReason") or {}
            nat_hex = tr.get("hex")
            nat_val = int(nat_hex, 16) if isinstance(nat_hex, str) else None
            if nat_val is None and tr.get("ruleClass") == "NoBrokenTargetingRule":
                nat_val = 0
            rows.append({
                "label": label, "targetId": tid, "nat": nat_val,
                "nat_reasons": tr.get("reasons") or [],
                "nat_class": tr.get("ruleClass"),
                "apres": _port_reason(dv, ob, snap, board, cid, tid, "apres"),
                "avant": _port_reason(dv, ob, snap, board, cid, tid, "avant"),
                "sansTile": _port_reason(dv, ob, snap, board, cid, tid, "sansTile"),
            })

        print("\n[reasons] caster=u%d ability=%d" % (cid, VALKYRIE_STRIKE))
        print("  %-26s %-6s %-10s %-22s %-8s %-8s %-9s %s"
              % ("cible", "id", "natif", "regle", "APRES", "AVANT", "sansTile", "accord"))
        n_agree = n_gain = n_cf = 0
        for r in rows:
            agree = (r["nat"] == r["apres"])
            n_agree += 1 if agree else 0
            gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
            n_gain += 1 if gain else 0
            cf = (r["nat"] not in (None, 0)) and r["sansTile"] == 0
            n_cf += 1 if cf else 0
            print("  %-26s %-6d %-10s %-22s %-8s %-8s %-9s %s%s"
                  % (r["label"], r["targetId"],
                     "-" if r["nat"] is None else hex(r["nat"]),
                     ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                     hex(r["apres"]), hex(r["avant"]), hex(r["sansTile"]),
                     "OK" if agree else "MISMATCH", "  <-GAIN" if gain else ""))

        walk_ok = any(r["nat"] == 0 for r in rows if r["label"].startswith("tile-WALK"))
        print("\n[bilan] accord natif/APRES : %d/%d ; lignes ou le natif REFUSE et AVANT rendait 0 "
              "(casts illegaux que master acceptait) : %d" % (n_agree, len(rows), n_gain))
        print("[garde 0x1] au moins une tuile MARCHABLE rend 0x0 : %s  -> le court-circuit "
              "d'ability ne mord pas, les 0x1 des NON MARCHABLES viennent de `TargetIsTile`"
              % ("OUI" if walk_ok else "NON"))
        print("[contrefactuel] masque prive de `TargetIsTile` -> faux accept sur %d/%d des lignes "
              "REFUSEES par le natif : le bit est PORTEUR" % (n_cf, n_gain))
        ok = (n_agree == len(rows)) and walk_ok and n_gain > 0 and n_cf == n_gain
        print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
        print("[RAW] " + json.dumps(rows))
        return 0 if ok else 1
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
