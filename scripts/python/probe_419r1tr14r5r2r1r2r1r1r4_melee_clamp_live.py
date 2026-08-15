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
from rl_collect_batch import _resolve_session, bind_ambient_rpc      # noqa: E402

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
    """BASELINE B2 -- « les deux clamps de melee n'ARMENT PAS `onlyAdjacent` ».

    On rejoue le SEUL terme que les deux clamps forcent : `onlyAdjacent`, ramene a sa valeur de BASE
    (`IsTrue(options.Range.OnlyAdjacent, caster)`, la 1re des trois ecritures natives). Aucune
    duplication du corps de `get_range` : c'est une SOUSTRACTION exacte.

    ⚠ **CETTE BASELINE ETAIT GARDEE PAR `rr.value is None`, ET CETTE GARDE L'A RENDUE VACANTE**
    (#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1). Elle ne soustrayait le clamp que dans le regime « valeur
    inconnue » ; or `get_range` lit desormais `GetStat(caster, StatType.Range = 2)` sur un caster
    sans arme, donc la valeur y vaut `0` et non `None` -- B2 rendait alors le `Range` INTACT, se
    confondait avec le port, et le cran D1 tombait en REGIME DEGENERE. La question de la tranche
    n'a pourtant pas change : « le clamp arme-t-il `onlyAdjacent` ? ». On la pose donc directement,
    sans passer par un etat du tri-etat qui n'en est qu'un symptome."""
    rr = _VRAI_GET_RANGE(state, caster_id, options)
    if rr is None:
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

#: BRAS 2 -- l'ACTIVE dont la cascade `UnitFactory$$AddNormalAttackAbility` derive l'attaque normale
#: `1126 RogalDorn_NormalAttack`, dont le ctor pose `forceMeleeTarget = 1 = RangedBool.False`
#: (litteral LU) et le masque `0x4000` (SANS `TargetMatchesDynamicRule`). Ces deux proprietes en font
#: la SONDE de `GetStat(Range)` : le clamp ne s'arme JAMAIS, et rien ne rattrape le volet portee en
#: aval -- le verdict natif a `d = 1` lit donc directement la valeur.
GRAFT_ACTIVE = P587.GRAFT_ACTIVE          # `PoundThemToDust`
GRAFT_TYPE = P587.GRAFT_TYPE              # 1126


def _seed_bc_avec_trait(greffe: bool = False) -> tuple[Path, dict]:
    """Le seed BC du montage : `genesSmnDecoy` recoit le trait `Ranged` -- et, pour le bras 2,
    l'active `PoundThemToDust` (qui substitue l'attaque normale `1126`)."""
    import catalog_inject
    bc = catalog_inject._load_seed(None)
    rep = catalog_inject.add_unit_trait(bc, CASTER_VIS, TRAIT)
    if greffe:
        rep = dict(rep, **catalog_inject.graft_active_ability(bc, CASTER_VIS, GRAFT_ACTIVE,
                                                              replace=True))
    out = Path(tempfile.mkdtemp()) / ("seed-trait%s.json" % ("-graft" if greffe else ""))
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out, rep


def _traits_natifs(snap, uid: int):
    """Les traits que le NATIF publie pour cette entite -- `combatSnapshot.units[].traits`, que
    `readUnitTraits` obtient en invoquant `IdunBattle.Entities.UnitExtensions$$HasTrait` une fois
    par valeur d'enum. C'est la preuve que l'injection a mordu COTE NATIF, et pas une relecture de
    ce qu'on a ecrit.

    TRI-ETAT, comme le capteur : `None` = PAS MESURE (ligne absente, ou champ `null`), `[]` = mesure
    « aucun trait ». Les confondre ferait passer un capteur muet pour une unite sans trait.
    ⚠ La cle est `entityId` (PAS `id`), et les valeurs sont des IDS d'enum -- on les nomme."""
    from engine.entities.traits.unit_trait import trait_names_from_ids
    for u in (snap.get("units") or []):
        if u.get("entityId") is not None and int(u["entityId"]) == int(uid):
            t = u.get("traits")
            return None if not isinstance(t, list) else sorted(trait_names_from_ids(t))
    return None


def _rows(sid, rid, st, dv, caster_u, aid: int = GENERIC_TYPE) -> list:
    """Une ligne par cible ENNEMIE vivante : natif, port, B1, B2."""
    cid = int(caster_u["id"])
    ab = _NormalAttackTargeting(OPTS[aid])
    out = []
    for u in (dv.get("units") or []):
        if not u.get("alive") or int(u["id"]) == cid or u.get("owner") == caster_u.get("owner"):
            continue
        tid = int(u["id"])
        tr = (P247._nat(sid, rid, cid, aid, tid) or {}).get("targetReason") or {}
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


def forcer_contact(sid, rid, vis: str = CASTER_VIS, rounds: int = 8) -> bool:
    """PILOTE la geometrie au lieu de la subir : amene un ENNEMI au contact d'un summon `vis`.

    Le clamp `(c)` exige `ShouldApplyRangedInMelee`, donc un ennemi adjacent au CASTER. Sur un
    board/seed ou les summons apparaissent loin de tout ennemi -- c'est le cas du montage NOMINAL
    lui-meme, `MC1_67`/`4192`, ou les trois `genesSmnDecoy` tombent a `d = 2`, `3` et `9` --, la
    geometrie de spawn n'est PAS une excuse : on DEPLACE.

    DELEGUE au foyer commun `P583.forcer_contact`, qui porte les trois faits mesures. L'implantation
    LOCALE qui vivait ici NE POUVAIT PAS ABOUTIR, et sa propre trace le disait sans le nommer : elle
    refusait tout `endturn` (« les decoys sont EPHEMERES et n'y survivent pas ») et ne bougeait donc
    l'ennemi que pendant NOTRE tour -- or `aiMovableTiles` ne publie alors AUCUNE unite adverse, si
    bien qu'elle sortait systematiquement sur « u%d n'est pas activable sans consommer un tour ».
    Le fait qui la fondait est vrai a l'envers : c'est le retour de la main a NOTRE camp qui detruit
    la geometrie (`PlayAutomaticUnits`), pas le passage a l'adversaire. Rendre la main a l'ennemi et
    y RESTER est donc a la fois necessaire et sans danger -- mesure : les trois decoys sont intacts
    apres le passage, et `abilityReason` y repond normalement."""
    rep = P583.forcer_contact(sid, rid, vis_list=(vis,), rounds=rounds)
    print("  [contact] distance minimale atteinte : %s" % rep)
    return rep.get(vis) == 1


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
        forcer_contact(sid, rid)
        dv, payloads = P436._capture(sid, rid)
        st = P436._mk_state(payloads)
        snap = payloads[2]
        vivants = P583._live(dv, CASTER_VIS)
        if not vivants:
            raise MontageError("aucun `%s` vivant -> montage non pose" % CASTER_VIS)
        # (1) LE TRAIT A-T-IL MORDU COTE NATIF ? -- `combatSnapshot` lit l'entite native.
        for u in vivants:
            tn = _traits_natifs(snap, int(u["id"]))
            tp = T._unit_traits(st, int(u["id"]))
            print("  u%-4s %-18s traits NATIFS = %s" % (u["id"], u.get("visualId"), tn))
            print("        traits vus par le PORT = %s" % (list(tp),))
            if tn is None:
                raise MontageError("traits NON MESURES sur u%s -- capteur muet, pas une mesure"
                                   % u["id"])
            if TRAIT not in tn:
                raise MontageError("le trait `%s` n'est PAS publie par le natif sur u%s -- "
                                   "l'injection n'a pas mordu" % (TRAIT, u["id"]))
            if TRAIT not in tp:
                raise MontageError("le trait `%s` n'atteint pas le PORT sur u%s -- les deux "
                                   "modeles ne liraient pas le meme caster" % (TRAIT, u["id"]))
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


def run_sonde(sid, seed: str = "4192", board: str = "MC1_67") -> dict:
    """BRAS 2 -- LA SONDE DE `GetStat(caster, StatType.Range = 2)`, et pourquoi elle est necessaire.

    Le bras 1 ne donne qu'une BORNE : ses temoins n'ont, par construction, aucune cible a `d = 1`
    (c'est ce qui les rend temoins), donc le plus petit refus observe vaut 2 et n'etablit que
    `Value <= 1`. Or `D2` n'est probant que si `Value == 0` : avec `Value == 1`,
    `min(1, Value) == Value` et « gate d'adjacence » et « branche distance » rendent le MEME verdict
    partout -- un accord DEGENERE, qui ne prouverait rien.

    On leve l'ambiguite avec une ability dont le clamp ne peut PAS s'armer : `1126`
    (`forceMeleeTarget = RangedBool.False`, litteral lu au ctor) et masque `0x4000`, donc sans
    `TargetMatchesDynamicRule` pour masquer le volet portee. Sur un caster ADJACENT :

        natif `TargetIsInRange` a `d = 1`  <=>  `Value == 0`     (`d > 0`)
        natif `0x0`            a `d = 1`  <=>  `Value >= 1`

    ⚠ Le PORT diverge ici, et c'est ATTENDU : `value = None` -> aucun refus de DISTANCE. C'est le
    prix CONNU du tri-etat (#419-r1-tr14-r5-r2-r1-r2-r1-r1) ; sur ce masque il devient un ecart de
    VERDICT, la ou le bras 1 ne le laissait voir que sur le CODE. On le CHIFFRE, on ne le tait pas.
    Ce regime n'existe que parce qu'on a POSE le trait : sans lui, `only_adjacent` est vrai par la
    base et le gate d'adjacence couvre. Ce n'est donc pas un gisement reel."""
    seed_bc, rep = _seed_bc_avec_trait(greffe=True)
    print("\n=== BRAS 2 (sonde `GetStat(Range)`) : %s.Traits=%s ActiveAbilities=[%s]"
          % (CASTER_VIS, rep["traitsAfter"], GRAFT_ACTIVE))
    rid, state = P587._build_bc(sid, seed, board, str(seed_bc))
    try:
        for _ in range(P247.WARMUP_ENDTURNS):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
        P583._drive_and_summon(sid, rid)
        forcer_contact(sid, rid)
        dv, payloads = P436._capture(sid, rid)
        st = P436._mk_state(payloads)
        u = P583._pick_adjacent(dv, CASTER_VIS)
        if u is None:
            raise MontageError("bras 2 : aucun `%s` vivant ADJACENT -> sonde non posee"
                               % CASTER_VIS)
        got = P583._normal_attack_id(u)
        print("  u%-4s attaque normale NATIVE = %s (attendu %d) -> %s"
              % (u["id"], got, GRAFT_TYPE, "MORD" if got == GRAFT_TYPE else "N'A PAS MORDU"))
        if got != GRAFT_TYPE:
            raise MontageError("la greffe n'a pas substitue l'attaque normale (%s != %d)"
                               % (got, GRAFT_TYPE))
        rows = _rows(sid, rid, st, dv, u, aid=GRAFT_TYPE)
        _print_rows("SONDE  u%s (type %d, masque 0x4000, forceMeleeTarget=False)"
                    % (u["id"], GRAFT_TYPE), rows)
        return {"sonde": rows}
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state)],
                       cwd=str(PYDIR), capture_output=True, text=True)


def get_stat_range_mesure(res: dict):
    """`GetStat(caster, StatType.Range = 2)` -- `(valeur, borne_sup, source)`, tri-etat.

    Deux lectures, et seule la seconde donne la VALEUR :
      * les TEMOINS du bras 1 (clamp non arme, masque `0x4002`) -> le plus petit `d` refuse en
        `TargetIsInRange` vaut `Value + 1` : une BORNE SUPERIEURE ;
      * la SONDE du bras 2 (`d = 1`, masque `0x4000`) -> `TargetIsInRange` <=> `Value == 0`.
    `(None, ..., ...)` = NON MESURE (jamais rabattu sur 0)."""
    borne = None
    for t in res.get("temoins") or []:
        refus = [r["d"] for r in t["rows"] if r["nat"] == int(TR.TargetIsInRange)]
        if refus:
            b = min(refus) - 1
            borne = b if borne is None else min(borne, b)
    valeur, source = None, "non mesure"
    a1 = [r for r in (res.get("sonde") or []) if r["d"] == 1 and r["nat"] is not None]
    if a1:
        valeur = 0 if all(r["nat"] == int(TR.TargetIsInRange) for r in a1) else None
        source = "sonde bras 2 (d=1, type %d)" % GRAFT_TYPE
        if valeur is None and all(r["nat"] == 0 for r in a1):
            valeur, source = ">= 1", source
    return valeur, borne, source


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


def verdict_sature(res: dict) -> bool:
    """L'axe VERDICT est-il SATURE sur le caster clampe ? -- fait MESURE, pas excuse.

    Le seul jeu d'options qui combine « clamp armable » et « portee non observable » est le preset
    `statics+0x00` (type `69` et ses freres), dont le masque `0x4002` porte
    `TargetMatchesDynamicRule`. Or `ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason` refuse
    TOUTE cible d'un caster sans arme (`GetAttackWeaponForDefaultNormalAttack` rend null des deux
    cotes de son `AreTilesAdjacent`). Le natif refuse donc partout : aucune baseline ne peut etre
    departagee sur « refuse / accepte », et seul le CODE (la CAUSE) discrimine."""
    rows = [r for c in (res.get("clampes") or []) for r in c["rows"] if r["nat"] is not None]
    return bool(rows) and all(r["nat"] != 0 for r in rows)


def d2_probant(res: dict, valeur) -> tuple:
    """D2 -- « la valeur clampee est-elle CONSOMMEE ? ». Rend `(probant, ok, detail)`.

    Probant SEULEMENT si `GetStat(Range) == 0` : alors `min(1, 0) = 0`, et la branche DISTANCE
    refuserait TOUTE cible (`d >= 1 > 0`). Observer le natif ACCEPTER le volet portee a `d = 1` sur
    le caster CLAMPE prouve donc que c'est la branche `OnlyAdjacent` qui a repondu, et que la valeur
    clampee n'a pas ete lue. Avec `Value >= 1`, les deux branches coincident -> DEGENERE, et on le
    DIT au lieu de compter l'accord."""
    a1 = [r for c in (res.get("clampes") or []) for r in c["rows"]
          if r["d"] == 1 and r["nat"] is not None]
    if valeur != 0:
        return False, None, ("GetStat(Range) = %s -> min(1, Value) = Value : gate d'adjacence et "
                             "branche distance coincident, D2 DEGENERE" % valeur)
    if not a1:
        return False, None, "aucune ligne a d = 1 sur le caster clampe"
    ok = all(r["nat"] != int(TR.TargetIsInRange) for r in a1)
    return True, ok, ("le natif %s le volet portee a d = 1 alors que min(1, 0) = 0"
                      % ("ACCEPTE" if ok else "REFUSE"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4192")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--offline", action="store_true", help="crans hors ligne seuls (pas de runner)")
    ap.add_argument("--no-sonde", action="store_true",
                    help="ne joue que le bras 1 (economise un runner ; PERD le discriminant D2)")
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
    # #448-r3-r1-r1 : ce montage GREFFE (`graft_active_ability` + `add_unit_trait`). Sans le canal
    # `unitAbilityStates`, `services.custom_normal_attack` derive le type d'attaque normale du KIT
    # gameconfig, qui ne connait pas la greffe -- port AMPUTE, assertions negatives a vide. Mesure
    # sur le montage voisin (`..._r1_r1_only_adjacent_live.py`) : voie implicite `69` sans canal,
    # `1126` avec. Le foyer (`snapshot._refuse_if_grafted`) LEVE sans cette ligne.
    bind_ambient_rpc(sid)
    print("[canal] `unitAbilityStates` LIE en ambiant (bind_live_rpc)")
    try:
        res = run(sid, a.seed, a.board)
        if not a.no_sonde:
            res.update(run_sonde(sid, a.seed, a.board))
    except MontageError as e:
        print("\n[FAIL] MONTAGE : %s" % e)
        return 2

    valeur, borne, source = get_stat_range_mesure(res)
    print("\n=== `GetStat(caster, StatType.Range = 2)` : valeur = %s (%s) ; borne sup du bras 1 = %s"
          % (valeur, source, borne))
    t = tally(res)
    print("=== BILAN sur %d lignes du/des caster(s) CLAMPE(s)" % t["tot"])
    print("  CODE    : port %d | B1 %d | B2 %d | gagnees/B2 %d | PERDUES/B2 %d"
          % (t["port"], t["b1"], t["b2"], t["gain_b2"], t["perte_b2"]))
    print("  VERDICT : port %d | B2 %d | gagnees/B2 %d | PERDUES %d"
          % (t["v_port"], t["v_b2"], t["v_gain_b2"], t["v_perte"]))
    sat = verdict_sature(res)
    print("  axe VERDICT %s sur le caster clampe (masque 0x4002 + regle dynamique)"
          % ("SATURE -- seul le CODE discrimine" if sat else "NON sature"))
    probant, ok, detail = d2_probant(res, valeur)
    print("  D2 (valeur clampee consommee ?) : %s -- %s"
          % ("PROBANT" if probant else "NON PROBANT", detail))

    if t["tot"] == 0:
        print("[FAIL] aucune ligne mesuree")
        rc = 1
    if t["v_port"] != t["tot"]:
        print("[FAIL] %d ligne(s) ou le port et le natif divergent SUR LE VERDICT (D1)"
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
    if not a.no_sonde:
        if not probant:
            print("[FAIL] D2 NON PROBANT : la sonde n'a pas etabli `GetStat(Range) == 0`, donc "
                  "l'accord a d = 1 ne separe PAS « gate d'adjacence » de « branche distance »")
            rc = 1
        elif not ok:
            print("[FAIL] D2 REFUTE : le natif a lu la valeur CLAMPEE -- propager `None` est FAUX")
            rc = 1
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
