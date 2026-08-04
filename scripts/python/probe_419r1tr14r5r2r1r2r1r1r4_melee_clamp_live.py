"""probe #419-r1-tr14-r5-r2-r1-r2-r1-r1-r4 -- les CLAMPS DE MELEE sur une portee NON OBSERVABLE.

QUESTION BINAIRE
    Quand la portee NUMERIQUE n'est pas observable, un clamp de melee de
    `IdunBattle.Core.Services.TargetingQuery$$GetRange` arme-t-il quand meme son `onlyAdjacent` ?
    Et la valeur qu'il clampe est-elle consommee quelque part ?

  Le port fait `value = None if value is None else min(1, value)` + `only_adjacent = True`.
  L'argument qui rend ce `None` inoffensif etait une LECTURE (les deux `Math.Min(1, v)` cohabitent
  avec `onlyAdjacent = 1` dans le MEME bloc, et le consommateur teste `range._4_1_` en premier).
  Ce probe la CONFRONTE.

LES DEUX BRAS SONT DISTINCTS -- CELUI-CI EST `ForceMeleeTarget`

    (b) `if (HasEffect(caster, 0x529 ForcedInMelee))            { v = Math.Min(1,v); onlyAdj = 1; }`
    (c) `if (IsTrue(options.ForceMeleeTarget, caster)
             && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true))
                                                                { v = Math.Min(1,v); onlyAdj = 1; }`

  Ce probe monte **(c)**. Le bras (b) est NON CONFRONTE, et c'est une impossibilite MESUREE, pas un
  abandon -- cf. `impossibilite_du_bras_forced_in_melee()` plus bas.

POURQUOI LE REGIME N'AVAIT JAMAIS ETE ATTEINT, ET COMMENT ON L'OUVRE

  `value is None` exige un caster SANS ARME au gameconfig. Or le clamp (c) de l'attaque normale
  generique `69` teste `ForceMeleeTarget = IfRangedCaster`, c.-a-d.
  `IdunBattle.Entities.UnitExtensions$$IsRanged` = `HasTrait(caster, 0xb Ranged) ||
  HasRangedWeapon(caster)`. Sans arme, le 2e terme est faux -- et le 1er l'est aussi, puisque le
  trait `Ranged` n'est porte par AUCUNE des 683 unites du gameconfig (constat #161). Les deux
  conditions s'excluaient donc par la seule structure du catalogue.

  ON LES DISSOCIE en POSANT le trait : `catalog_inject.add_unit_trait(bc, 'genesSmnDecoy', 'Ranged')`
  ecrit `BC.Units[].Traits`, que `buildNormalizedBC` LIT (detection MoW) mais n'ECRIT jamais. Le
  NATIF le lit par `HasTrait` sur l'entite, le PORT par `combatSnapshot.units[].traits` -- lu sur
  cette MEME entite native. Substrat UNIQUE : aucune divergence de substrat possible.

  EFFET DE BORD **VOULU**, et c'est lui qui rend le regime discriminant : le `TargetingRange` de
  `69` est `RANGE_ADJACENT_IF_MELEE_CASTER` (`onlyAdjacent = IfNotRangedCaster`), qui devient FAUX
  avec le trait. Le gate d'adjacence n'est donc plus arme par la BASE -- il ne peut l'etre que par
  le CLAMP. C'est la sortie du regime degenere de la tranche precedente, ou `onlyAdjacent` etait
  deja vrai avant tout clamp.

CE QUI ME FERAIT CONCLURE QUE LE PORT DIVERGE -- ENONCE AVANT LE MONTAGE

  D1  CLAMP QUI NE S'ARME PAS. Sur un caster clampe (un ennemi ADJACENT, donc
      `ShouldApplyRangedInMelee` vrai), le natif ACCEPTE une cible a d >= 2 la ou le port rend
      `TargetIsInRange` -> le natif desarmerait son gate faute de valeur ; le port serait
      RESTRICTIF a tort.
  D2  VALEUR CLAMPEE CONSOMMEE. Sur ce meme caster, le natif rend `TargetIsInRange` sur une cible
      ADJACENTE (d = 1) -> la branche DISTANCE aurait ete prise avec `Value = min(1, GetStat(Range))`
      -> propager `None` serait FAUX et il faudrait modeliser `GetStat(StatType.Range = 2)`.
      ⚠ D2 n'est probant que si `GetStat(Range) == 0` (sinon `min(1, v) = 1` accepterait d = 1 de
      toute facon) : c'est le TEMOIN NON CLAMPE qui le mesure, cf. ci-dessous.
  D3  DECLENCHEMENT DIVERGENT. Le port et le natif desaccordent sur `ShouldApplyRangedInMelee` --
      visible en comparant le caster CLAMPE au TEMOIN NON CLAMPE (meme visualId, meme trait, meme
      arme, meme attaque normale ; SEULE difference : un ennemi a d = 1).

LE TEMOIN NON CLAMPE -- L'ETAGE QUI REND D2 PROBANT
  Un `genesSmnDecoy` du MEME cast qui n'a AUCUN ennemi a d = 1. Chez lui le clamp ne s'arme pas,
  donc le natif retombe sur la branche DISTANCE avec `Value = GetStat(Range)` : le plus petit `d`
  qu'il refuse vaut `GetStat(Range) + 1`. C'est ainsi qu'on MESURE une valeur que le port declare
  non observable, au lieu de la supposer.
  ⚠ DIVERGENCE ATTENDUE ET ASSUMEE sur ce temoin : le port ne modelise pas `GetStat(Range)` et ne
  pose aucun refus de DISTANCE. C'est le prix CONNU du tri-etat (#419-r1-tr14-r5-r2-r1-r2-r1-r1),
  pas une regression de cette tranche -- on le CHIFFRE au lieu de le taire.

LES BASELINES (deux, et elles ne disent pas la meme chose)
  B1  le port d'AVANT #587 : `return None` global des que la valeur manque -> aucun gate.
  B2  **la baseline propre a CETTE tranche** : « le clamp ABANDONNE quand la valeur est inconnue »
      (ni `min`, ni forcage de `onlyAdjacent`). C'est la seule alternative qui isole EXACTEMENT le
      comportement mis en cause par le residu.
  B3  « le clamp pose `value = 1` » : INDISTINGUABLE du port sur le seul consommateur porte, et
      c'est un RESULTAT, pas un trou -- il se demontre hors ligne (`b3_indistinguable()`), pas par
      un accord live qui ne prouverait rien.

VERDICT
  rc 0 si (a) le montage a mordu (trait vu par le NATIF, attaque normale `69`, un caster clampe),
  (b) le port est en accord TOTAL avec le natif sur le caster CLAMPE (code ET verdict),
  (c) B2 diverge sur au moins une ligne -- sinon regime DEGENERE --, et (d) B3 est bien
  indistinguable (sinon il faudrait le confronter, pas le raisonner).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session                            # noqa: E402

import probe_247_splash_targeting as P247                                # noqa: E402
import probe_436_taunt_targeting as P436                                 # noqa: E402
import probe_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule as P583      # noqa: E402
import probe_419r1tr14r5r2r1r2r1r1_only_adjacent_live as P587            # noqa: E402

from engine.runner.abilities import targeting as T                       # noqa: E402
from engine.runner.abilities.targeting import (                          # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE as OPTS,
    _NormalAttackTargeting, get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

GENERIC_TYPE = P583.GENERIC_TYPE
MontageError = P583.MontageError

#: Le trait a POSER, et son unite. `Ranged` = `UnitTrait` 0xb, 1er terme de `IsRanged`.
TRAIT = "Ranged"
CASTER_VIS = P583.NOWEAPON_VIS            # `genesSmnDecoy` : `weapons = []` au kit ET dans BC.Units

#: La VRAIE fonction, capturee A L'IMPORT (les baselines la substituent).
_VRAI_GET_RANGE = T.get_range


def _b1(state, caster_id, options):
    """BASELINE B1 -- le port d'AVANT #587 : `None` global des que la portee manque."""
    rr = _VRAI_GET_RANGE(state, caster_id, options)
    return None if rr is None or rr.value is None else rr


def _b2(state, caster_id, options):
    """BASELINE B2 -- « le clamp de melee ABANDONNE quand la valeur est inconnue ».

    On rejoue le SEUL terme que les deux clamps auraient force : `onlyAdjacent`. Dans le regime
    `value is None` on le ramene a sa valeur de BASE (`IsTrue(options.Range.OnlyAdjacent, caster)`,
    la 1re des trois ecritures natives) ; partout ailleurs on rend le `Range` tel quel. Aucune
    duplication du corps de `get_range` : c'est une SOUSTRACTION exacte."""
    rr = _VRAI_GET_RANGE(state, caster_id, options)
    if rr is None or rr.value is not None:
        return rr
    rng = getattr(options, "range", None)
    base = T.ranged_bool_is_true(rng.only_adjacent, state, caster_id) if rng is not None else False
    return replace(rr, only_adjacent=bool(base))


class _Substitue:
    """Substitue `targeting.get_range` le temps d'une mesure. Restauration GARANTIE."""

    def __init__(self, fn):
        self._fn = fn

    def __enter__(self):
        T.get_range = self._fn
        return self

    def __exit__(self, *exc):
        T.get_range = _VRAI_GET_RANGE
        return False


# ------------------------------------------------------------------- crans OFFLINE, sans runner

def b3_indistinguable(verbose: bool = True) -> dict:
    """B3 -- « le clamp pose `value = 1` » : le DEMONTRER indistinguable, ne pas l'esperer.

    `get_range_broken_rule` est le SEUL appelant Python de `get_range`. On lui donne les deux
    `Range` concurrents (`Range(None, True)` et `Range(1, True)`) sur un balayage de geometries et
    de masques, et on exige l'egalite BIT A BIT. Si un jour elle tombe, c'est que la valeur est
    devenue consommable sous `only_adjacent` -> il faudra CONFRONTER le choix, plus le raisonner."""
    from engine.runner.abilities.targeting import Range
    st, cid = _etat_synthetique(CASTER_VIS)
    tid = _ajoute_cible(st, col=3, row=3)
    ecarts, verifies, ecarts_hors_adj = [], 0, 0
    codes = set()
    for masque in (int(TR.TargetIsEnemy), int(TR.TargetIsEnemy) | int(TR.TargetMatchesDynamicRule),
                   int(TR.TargetIsEnemy) | int(TR.TargetIsAtRange)):
        opts = replace(OPTS[GENERIC_TYPE], rules=masque)
        for col in range(1, 9):
            for row in range(1, 9):
                _place(st, tid, col, row)
                for adj in (True, False):
                    a = _rule_avec(st, cid, tid, opts, Range(value=None, only_adjacent=adj))
                    b = _rule_avec(st, cid, tid, opts, Range(value=1, only_adjacent=adj))
                    verifies += 1
                    if adj:
                        codes.add(a)
                        if a != b:
                            ecarts.append((masque, col, row, hex(a), hex(b)))
                    elif a != b:
                        ecarts_hors_adj += 1
    if verbose:
        print("=== B3 (offline) : `Range(None, True)` contre `Range(1, True)` sur %d couples"
              % verifies)
        print("    codes distincts rendus sous `only_adjacent` : %s"
              % sorted(hex(c) for c in codes))
        print("    ecarts sous `only_adjacent`      : %d -> %s"
              % (len(ecarts), "INDISTINGUABLE" if not ecarts else ecarts[:3]))
        print("    ecarts HORS `only_adjacent`      : %d  (le CONTRE-CRAN : la, la valeur EST lue)"
              % ecarts_hors_adj)
    return {"verifies": verifies, "ecarts": ecarts, "codes": sorted(codes),
            "ecarts_hors_adj": ecarts_hors_adj}


def _rule_avec(state, cid, tid, opts, rr) -> int:
    """`get_range_broken_rule` avec un `Range` IMPOSE."""
    with _Substitue(lambda *_a, **_k: rr):
        return int(T.get_range_broken_rule(state, cid, tid, opts))


def _etat_synthetique(visual_id: str, taille: int = 10):
    """Un `State` MINIMAL : une unite de `visual_id` sur une grille `evenq` plate.

    Le BOARD est indispensable ici (contrairement au cran offline de la tranche precedente) :
    `get_range_broken_rule` sort en `return 0` sans lui, ce qui rendrait le balayage B3 DEGENERE --
    egalite triviale au lieu d'une egalite mesuree."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.state import State
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    st = State()
    tiles = [{"id": c * taille + r, "col": c, "row": r, "elevation": 0}
             for c in range(taille) for r in range(taille)]
    st.board = Board(tiles, adjacency="evenq")
    ent = st.add_entity()
    ent.add_component(UnitComponent(visual_id=visual_id, alive=True))
    ent.add_component(PositionComponent(col=5, row=5))
    ent.add_component(OwnerComponent(team=0))
    cid = int(next(k for k, v in st.entities.items() if v is ent))
    return st, cid


def _ajoute_cible(st, col: int, row: int) -> int:
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    ent = st.add_entity()
    ent.add_component(UnitComponent(visual_id="tauCrisis", alive=True))
    ent.add_component(PositionComponent(col=col, row=row))
    ent.add_component(OwnerComponent(team=1))
    return int(next(k for k, v in st.entities.items() if v is ent))


def _place(st, uid: int, col: int, row: int) -> None:
    from engine.runner.components import PositionComponent
    pc = st.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = col, row


def impossibilite_du_bras_forced_in_melee(verbose: bool = True) -> dict:
    """LE BRAS (b) `ForcedInMelee` -- pourquoi il reste NON CONFRONTE, chiffre.

    Poseur LU au decompile :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour`
    = `If(HasFaction(unit, 0xe BloodAngels), AddEffect(0x529, ...) & ... & RemoveEffect(unit, 0x529))`.
    TROIS verrous INDEPENDANTS, dont deux se mesurent sur le catalogue :

      1. GATE DE FACTION -- l'effet ne se pose que sur une unite `BloodAngels`. Or **0** des unites
         SANS ARME du gameconfig est `BloodAngels` : le regime « effet pose ET portee non
         observable » est VIDE dans la population.
      2. GATE `Attackable` DU SWAP -- l'unite ECHANGEE (le seul autre porteur possible) est filtree
         par `UnitsWithoutTrait(0x1b Steppable)`. Le porteur sans arme le plus proche du montage
         (`genesSmnDecoy`) porte precisement `Steppable`.
      3. FENETRE ATOMIQUE -- `AddEffect` et `RemoveEffect` vivent dans la MEME chaine
         `op_BitwiseAnd`, donc l'effet naît et meurt dans un seul `AbilityBehaviour`. Aucun oracle
         SYNCHRONE (`abilityReason`) ne peut l'observer entre les deux.

    ⚠ RESERVE HONNETE : je ne peux PAS affirmer l'UNICITE du poseur. La recherche par litteral de
    l'index ghidra est demontree incomplete ici -- interrogee sur `0x529` elle rend `GetRange`
    (le LECTEUR) et RATE `GetTriggerAttackBehaviour`, que j'ai pourtant decompile. L'argument porte
    sur le poseur LU, pas sur un balayage exhaustif."""
    import gameconfig as G
    idx = G.all_unit_ids()
    ids = sorted({u for k in ("lineup", "npc", "summons") for u in (idx.get(k) or [])})
    sans_arme = [u for u in ids if not ((G.unit(u) or {}).get("weapons") or [])]
    ba = [u for u in sans_arme if (G.unit(u) or {}).get("FactionId") == "BloodAngels"]
    steppables = [u for u in sans_arme if "Steppable" in ((G.unit(u) or {}).get("traits") or [])]
    if verbose:
        print("=== BRAS (b) `ForcedInMelee` -- preuve d'IMPOSSIBILITE")
        print("  unites du catalogue                        : %d" % len(ids))
        print("  dont SANS ARME (portee non observable)     : %d" % len(sans_arme))
        print("  dont `BloodAngels` (gate du seul poseur LU): %d  <- verrou 1" % len(ba))
        print("  dont `Steppable` (exclues du swap)         : %d" % len(steppables))
        print("  -> NON CONFRONTE, et le regime est VIDE dans la population.")
    return {"catalogue": len(ids), "sans_arme": len(sans_arme), "sans_arme_bloodangels": ba,
            "sans_arme_steppable": steppables}


# ------------------------------------------------------------------------------- montage LIVE

def _seed_bc_avec_trait() -> tuple[Path, dict]:
    """Le seed BC du montage : `genesSmnDecoy` recoit le trait `Ranged`."""
    import catalog_inject
    out = Path(tempfile.mkdtemp()) / "seed-trait-ranged.json"
    p, reports = catalog_inject.write_trait_seed_bc(out, ["%s:%s" % (CASTER_VIS, TRAIT)])
    return p, reports[0]


def _traits_natifs(snap, uid: int) -> list:
    """Les traits que le NATIF publie pour cette entite (`combatSnapshot.units[].traits`, lus par
    `readUnitTraits` sur l'entite). C'est la preuve que l'injection a mordu COTE NATIF."""
    for u in (snap.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            return list(u.get("traits") or [])
    return []


def _rows(sid, rid, st, dv, caster_u) -> list:
    """Une ligne par cible ENNEMIE vivante : natif, port, B1, B2."""
    cid = int(caster_u["id"])
    ab = _NormalAttackTargeting(OPTS[GENERIC_TYPE])
    out = []
    for u in (dv.get("units") or []):
        if not u.get("alive") or int(u["id"]) == cid or u.get("owner") == caster_u.get("owner"):
            continue
        tid = int(u["id"])
        tr = (P247._nat(sid, rid, cid, GENERIC_TYPE, tid) or {}).get("targetReason") or {}
        port = int(get_invalid_target_reason(st, cid, tid, ab))
        with _Substitue(_b1):
            b1 = int(get_invalid_target_reason(st, cid, tid, ab))
        with _Substitue(_b2):
            b2 = int(get_invalid_target_reason(st, cid, tid, ab))
        out.append({"tid": tid, "vis": u.get("visualId"),
                    "d": hexgeo.distance(P247._pos(caster_u), P247._pos(u)),
                    "nat": P247._hexval(tr), "port": port, "b1": b1, "b2": b2})
    return sorted(out, key=lambda r: (r["d"], r["tid"]))


def _print_rows(label, rows):
    print("\n  --- CASTER %s" % label)
    print("      %-5s %-16s %-3s %-12s %-12s %-12s %-12s"
          % ("id", "cible", "d", "natif", "port", "B1", "B2"))
    for r in rows:
        mark = "   <- B2 DISCRIMINANT" if r["port"] != r["b2"] else ""
        print("      %-5d %-16s %-3d %-12s %-12s %-12s %-12s%s"
              % (r["tid"], r["vis"], r["d"], "?" if r["nat"] is None else hex(r["nat"]),
                 hex(r["port"]), hex(r["b1"]), hex(r["b2"]), mark))


def _clampe(st, dv, u) -> bool:
    """Le clamp (c) est-il arme pour ce caster ? = `IsTrue(ForceMeleeTarget, caster) &&
    ShouldApplyRangedInMelee(caster, casterTiles, true)`, evalue par le PORT sur l'etat mesure."""
    cid = int(u["id"])
    return bool(T.ranged_bool_is_true(OPTS[GENERIC_TYPE].force_melee_target, st, cid)
                and T.should_apply_ranged_in_melee(st, cid))


def run(sid, seed: str = "4192", board: str = "MC1_67") -> dict:
    """La MESURE, sans verdict. Leve `MontageError` si le montage n'a pas mordu."""
    seed_bc, rep = _seed_bc_avec_trait()
    print("=== montage : %s.Traits %s -> %s" % (CASTER_VIS, rep["traitsBefore"],
                                                rep["traitsAfter"]))
    rid, state = P587._build_bc(sid, seed, board, str(seed_bc))
    print("    runner %d ; %s -> `CultDemagogue` -> %s" % (rid, P583.ANCHOR_VIS, CASTER_VIS))
    try:
        for _ in range(P247.WARMUP_ENDTURNS):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
        P583._drive_and_summon(sid, rid)
        dv, payloads = P436._capture(sid, rid)
        st = P436._mk_state(payloads)
        snap = payloads[2]
        vivants = P583._live(dv, CASTER_VIS)
        if not vivants:
            raise MontageError("aucun `%s` vivant -> montage non pose" % CASTER_VIS)
        # (1) LE TRAIT A-T-IL MORDU COTE NATIF ? -- `combatSnapshot` lit l'entite native.
        for u in vivants:
            tn = _traits_natifs(snap, int(u["id"]))
            print("  u%-4s %-18s traits NATIFS = %s" % (u["id"], u.get("visualId"), tn))
            if TRAIT not in tn:
                raise MontageError("le trait `%s` n'est PAS publie par le natif sur u%s -- "
                                   "l'injection n'a pas mordu" % (TRAIT, u["id"]))
            got = P583._normal_attack_id(u)
            if got != GENERIC_TYPE:
                raise MontageError("u%s ne porte pas l'attaque normale generique (%s)"
                                   % (u["id"], got))
        # (2) VENTILATION : clampe (un ennemi a d = 1) contre TEMOIN non clampe.
        clampes = [u for u in vivants if _clampe(st, dv, u)]
        temoins = [u for u in vivants if not _clampe(st, dv, u)]
        print("  ventilation : %d caster(s) CLAMPE(s), %d TEMOIN(s) non clampe(s)"
              % (len(clampes), len(temoins)))
        if not clampes:
            raise MontageError("aucun `%s` sous clamp de melee -> le regime n'est pas monte"
                               % CASTER_VIS)
        res = {"clampes": [], "temoins": []}
        for u in clampes:
            rows = _rows(sid, rid, st, dv, u)
            _print_rows("CLAMPE  u%s %s (trait %s)" % (u["id"], CASTER_VIS, TRAIT), rows)
            res["clampes"].append({"uid": int(u["id"]), "rows": rows})
        for u in temoins:
            rows = _rows(sid, rid, st, dv, u)
            _print_rows("TEMOIN NON CLAMPE  u%s %s" % (u["id"], CASTER_VIS), rows)
            res["temoins"].append({"uid": int(u["id"]), "rows": rows})
        return res
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state)],
                       cwd=str(PYDIR), capture_output=True, text=True)


def get_stat_range_mesure(res: dict):
    """`GetStat(caster, StatType.Range = 2)` DEDUIT du temoin non clampe : le natif y prend la
    branche DISTANCE (`d > Value` -> `TargetIsInRange`), donc le plus petit `d` refuse pour cette
    raison vaut `Value + 1`. `None` = pas de temoin, ou aucune ligne concluante."""
    seuils = []
    for t in res.get("temoins") or []:
        refus = [r["d"] for r in t["rows"] if r["nat"] == int(TR.TargetIsInRange)]
        if refus:
            seuils.append(min(refus) - 1)
    return min(seuils) if seuils else None


def tally(res: dict) -> dict:
    """Bilan du caster CLAMPE, sur les deux axes (CODE exact, VERDICT binaire)."""
    out = {"tot": 0, "port": 0, "b1": 0, "b2": 0, "gain_b2": 0, "perte_b2": 0,
           "v_port": 0, "v_b2": 0, "v_gain_b2": 0, "v_perte": 0}
    for c in res.get("clampes") or []:
        rows = [r for r in c["rows"] if r["nat"] is not None]
        out["tot"] += len(rows)
        out["port"] += sum(1 for r in rows if r["port"] == r["nat"])
        out["b1"] += sum(1 for r in rows if r["b1"] == r["nat"])
        out["b2"] += sum(1 for r in rows if r["b2"] == r["nat"])
        out["gain_b2"] += sum(1 for r in rows if r["port"] == r["nat"] and r["b2"] != r["nat"])
        out["perte_b2"] += sum(1 for r in rows if r["port"] != r["nat"] and r["b2"] == r["nat"])
        for r in rows:
            nat, p, b2 = bool(r["nat"]), bool(r["port"]), bool(r["b2"])
            out["v_port"] += int(p == nat)
            out["v_b2"] += int(b2 == nat)
            out["v_gain_b2"] += int(p == nat and b2 != nat)
            out["v_perte"] += int(p != nat and b2 == nat)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4192")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--offline", action="store_true", help="crans hors ligne seuls (pas de runner)")
    a = ap.parse_args(argv)

    rc = 0
    b3 = b3_indistinguable()
    if b3["ecarts"]:
        print("[FAIL] B3 (`value = 1`) n'est PAS indistinguable -- il doit etre CONFRONTE")
        rc = 1
    if len(b3["codes"]) < 2:
        print("[FAIL] BALAYAGE B3 DEGENERE : un seul code rendu sous `only_adjacent` (%s) -- "
              "l'egalite ne prouve rien" % b3["codes"])
        rc = 1
    if b3["ecarts_hors_adj"] == 0:
        print("[FAIL] CONTRE-CRAN B3 MUET : hors `only_adjacent` la valeur devrait etre LUE et les "
              "deux `Range` devraient differer -- le balayage ne discrimine rien")
        rc = 1
    impossibilite_du_bras_forced_in_melee()
    if a.offline:
        print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
        return rc

    sid = _resolve_session()
    try:
        res = run(sid, a.seed, a.board)
    except MontageError as e:
        print("\n[FAIL] MONTAGE : %s" % e)
        return 2

    gs = get_stat_range_mesure(res)
    print("\n=== `GetStat(caster, StatType.Range = 2)` mesure sur le temoin : %s"
          % ("NON MESURE (pas de temoin concluant)" if gs is None else gs))
    t = tally(res)
    print("=== BILAN sur %d lignes du/des caster(s) CLAMPE(s)" % t["tot"])
    print("  CODE    : port %d | B1 %d | B2 %d | gagnees/B2 %d | PERDUES/B2 %d"
          % (t["port"], t["b1"], t["b2"], t["gain_b2"], t["perte_b2"]))
    print("  VERDICT : port %d | B2 %d | gagnees/B2 %d | PERDUES %d"
          % (t["v_port"], t["v_b2"], t["v_gain_b2"], t["v_perte"]))
    if t["tot"] == 0:
        print("[FAIL] aucune ligne mesuree")
        rc = 1
    if t["v_port"] != t["tot"]:
        print("[FAIL] %d ligne(s) ou le port et le natif divergent SUR LE VERDICT (D1/D2)"
              % (t["tot"] - t["v_port"]))
        rc = 1
    if t["port"] != t["tot"]:
        print("[FAIL] %d ligne(s) ou le port et le natif divergent SUR LE CODE"
              % (t["tot"] - t["port"]))
        rc = 1
    if t["gain_b2"] == 0:
        print("[FAIL] REGIME DEGENERE : B2 (le clamp abandonne sur `None`) nomme la MEME regle "
              "partout -- la mesure ne prouve rien, meme si l'accord est parfait")
        rc = 1
    if t["perte_b2"]:
        print("[FAIL] %d ligne(s) PERDUE(S) contre B2" % t["perte_b2"])
        rc = 1
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
