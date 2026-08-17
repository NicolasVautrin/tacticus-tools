"""GARDE #550-r4 + #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r3 (OFFLINE PURE) -- les DEUX arguments que
`IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` passe a
`IdunBattle.Entities.TileExtensions$$CanAddUnitFromAbility`, et les DEUX gates propres d'
`IdunBattle.Operations.SetUnitPositionOperation$$Execute`.

POURQUOI CE FICHIER
-------------------
`CanAddUnitFromAbility(tile, state, parent, allowSteppable)` a TROIS gates, dont le port n'en jouait
qu'UN :

    if (!IsFreeTile(tile, state, allowSteppable, 0, 0))   return false;   <- porte
    if (IsTileReservedForOtherUnit(tile, parent))         return false;   <- #550-r4
    if (IsTilePendingDrafting(tile, state, 0))            return false;   <- NON PORTE (nomme)

et les deux qu'il jouait etaient FAUX de sens :

  * `parent` etait ABSENT du port. Il ne vaut pas << rien >> : les surcharges a UN et DEUX arguments
    de `IdunBattleLogic.Entities.DSLSelectors$$CanAddUnit` allouent `new EntitySelector(state, null)`
    -- le corps est IDENTIQUE a celui de `DSLSelectors$$None()` -- donc `parent` est NUL, donc
    `IsTileReservedForOtherUnit` prend sa branche `allowedUnit == null` = `HasValue` = << reservee
    par QUICONQUE >>. Avec un `parent` NON nul (le seul call-site est `ItItchesAbility`), la polarite
    S'INVERSE : `!(HasValue && Value == parent.Id)` refuse toute tuile NON reservee pour lui.
  * `allowSteppable` avait pour defaut `False`, alors que **123 des 147 call-sites natifs** passent
    `<DSLTriggers+0x48>` = `op_LogicalNot(<trigger nu>)` -> `ShouldTrigger` FAUX -> `allowSteppable`
    **VRAI**. Seuls **14** call-sites passent `<DSLTriggers+0x40>` (le trigger NU) -> FAUX.

LES DEUX OMISSIONS SE COMPENSAIENT, et c'est ce qui rendait le residu dangereux a fermer a moitie :
ajouter le gate de reservation SANS le modele ferait spawner ZERO unite sur `1121 ItItches`.

ASCII only. Aucune VA en dur : les adresses sont resolues par
`data/symbols/<build>/ghidra/functions.tsv` et la RVA est calculee EN CODE.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

import hexgeo
from engine.dsl.base import DslContext
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.geometry import Const
from engine.entities.selectors.accessors import Owner
from engine.entities.selectors.tiles import CanAddUnit
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.components import UnitComponent
from engine.runner.events import EventBus
from engine.runner.operations import tile_reservation
from engine.runner.operations.movement import MoveUnitOperation
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        # le foyer du noeud -- les DEUX branches sont ici
        "scripts/python/engine/entities/selectors/tiles.py",
        # le modele de reservation que le gate consomme
        "scripts/python/engine/runner/operations/tile_reservation.py",
        # l'accesseur qui l'expose au DSL
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/dsl/base.py",
        # les deux gates de `SetUnitPositionOperation` et leurs quatre stand-ins
        "scripts/python/engine/runner/operations/movement.py",
        "scripts/python/engine/runner/operations/displace.py",
        # les TROIS sites portes qui posent `allow_steppable=False`
        "scripts/python/engine/runner/operations/triggers/loki/haywire_mine.py",
        "scripts/python/engine/runner/abilities/orks.py",
        # le call-site `parent` non nul
        "scripts/python/engine/runner/abilities/tyranids.py",
        # les sites qui laissent le DEFAUT -- il vient de changer de sens
        "scripts/python/engine/entities/selectors/composites.py",
    ),
    # Les etages 1-2 LISENT `GameAssembly.dll`, HORS de l'arbre.
    "build": True,
    "toujours": False,
    "raison": "Il grave (a) que le defaut d'`allow_steppable` est celui de la surcharge a UN "
              "argument -- 123 xrefs, trigger NIE en dur -- et non l'inverse, et (b) les DEUX "
              "polarites du gate de reservation, qui n'ont AUCUN symptome et se compensaient.",
}

ROOT = Path(__file__).resolve().parents[4].parent          # racine du depot
IMAGE_BASE = 0x180000000                                   # base de l'image PE de GameAssembly.dll

#: `DSLTriggers+0x40` = le trigger NU (`ShouldTrigger` VRAI) -> `allowSteppable` **FAUX**.
SLOT_TRIGGER_NU = 0x40
#: `DSLTriggers+0x48` = `op_LogicalNot(<nu>)` (`ShouldTrigger` FAUX) -> `allowSteppable` **VRAI**.
SLOT_TRIGGER_NIE = 0x48
#: `<DSLFactory>+0x88` = l'instance `DSLTriggers` (LU dans `DSLFactory$$.ctor`).
SLOT_DSLTRIGGERS = 0x88

CAN_ADD_UNIT = "IdunBattleLogic.Entities.DSLSelectors$$CanAddUnit"

#: Les call-sites natifs des sites PORTES qui posent `allow_steppable=False`. Ils prennent la
#: surcharge a DEUX arguments et lui passent le trigger NU.
CALL_SITES_TRIGGER_NU = (
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Active.Loki.SquigMineAbility$$ExecuteBehaviour",
)

COLS, ROWS = 7, 7
MARCHEUR, VICTIME, TEMOIN = 10, 20, 30


# ============================================================================== lecture du PE

def _build_hash() -> "str | None":
    d = ROOT / "data" / "symbols"
    local = os.environ.get("LOCALAPPDATA")
    for p in sorted(d.iterdir()) if d.exists() else []:
        if not ((p / "ghidra" / "functions.tsv").exists() and (p / "BUILD").exists()):
            continue
        if (Path(local or "") / "tacticus" / "games" / p.name / "GameAssembly.dll").exists():
            return p.name
    return None


def _symbols(build: str) -> dict:
    tsv = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    out: dict = {}
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        va, name = line.split("\t", 1)
        out.setdefault(name.strip(), []).append(int(va, 16))
    return out


def _read_at_va(dll: Path, va: int, size: int) -> bytes:
    """Traduction VA -> offset fichier par les SECTIONS du PE. La RVA est calculee EN CODE.

    ⚠ On balaie TOUTES les sections, pas seulement `.text` : sur un binaire IL2CPP, une partie du
    code vit hors de la premiere section de code."""
    rva = va - IMAGE_BASE
    with dll.open("rb") as f:
        head = f.read(0x400)
        e_lfanew = struct.unpack_from("<I", head, 0x3C)[0]
        nsec = struct.unpack_from("<H", head, e_lfanew + 6)[0]
        opt_size = struct.unpack_from("<H", head, e_lfanew + 20)[0]
        f.seek(e_lfanew + 24 + opt_size)
        secs = f.read(40 * nsec)
        for i in range(nsec):
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", secs, 40 * i + 8)
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                f.seek(rawptr + (rva - vaddr))
                return f.read(size)
    return b""


def _calls_vers(blob: bytes, va: int, cibles) -> list:
    """Offsets des `call rel32` (`E8`) du blob dont la cible est dans `cibles`."""
    out = []
    for i in range(len(blob) - 5):
        if blob[i] == 0xE8:
            rel = struct.unpack_from("<i", blob, i + 1)[0]
            if va + i + 5 + rel in cibles:
                out.append(i)
    return out


def _charges_disp8(blob: bytes) -> set:
    """Les `mov <reg64>, [<reg>+disp8]` du blob, quel que soit le registre DESTINATION.

    Motif : REX.W (`48`/`4C`/`49`/`4D`) + `8B` + modrm `mod=01` (`0x40`..`0x7F`) + disp8. Le champ
    `reg` du modrm designe la destination et VARIE d'un build a l'autre (allocation de registres) --
    le figer ferait rendre un ensemble VIDE, donc un test VACANT. `rm == 100` = SIB, ecarte."""
    out = set()
    for j in range(len(blob) - 3):
        if blob[j] in (0x48, 0x49, 0x4C, 0x4D) and blob[j + 1] == 0x8B \
                and 0x40 <= blob[j + 2] <= 0x7F and (blob[j + 2] & 0x07) != 0x04:
            out.add(blob[j + 3])
    return out


def _charge_disp32(blob: bytes, disp: int) -> bool:
    """Vrai si le blob contient un `mov <reg64>, [<reg>+disp32]` de deplacement `disp`.

    Meme remarque que ci-dessus sur le champ `reg` : `mod=10` = `0x80`..`0xBF`."""
    for j in range(len(blob) - 7):
        if blob[j] in (0x48, 0x49, 0x4C, 0x4D) and blob[j + 1] == 0x8B \
                and 0x80 <= blob[j + 2] <= 0xBF and (blob[j + 2] & 0x07) != 0x04 \
                and struct.unpack_from("<I", blob, j + 3)[0] == disp:
            return True
    return False


def _disp8_du_3e_argument(blob: bytes, offset_du_call: int) -> list:
    """Les deplacements des `mov r8, [reg+disp8]` qui precedent le call.

    `r8` est le TROISIEME argument de la convention x64 Microsoft. Sur la surcharge a DEUX arguments
    de `CanAddUnit` (`this, tiles, isSteppable`), c'est donc `isSteppable`."""
    fenetre = blob[max(0, offset_du_call - 40):offset_du_call]
    return [fenetre[j + 3] for j in range(len(fenetre) - 3)
            if fenetre[j] in (0x4C, 0x4D) and fenetre[j + 1] == 0x8B
            and 0x40 <= fenetre[j + 2] <= 0x47]


def _bornes(sym: dict) -> list:
    """Toutes les adresses de fonction de la table, TRIEES -- la borne haute d'un corps est le
    debut de la fonction suivante.

    ⚠ Sans elle, un blob de taille fixe DEBORDE sur la fonction voisine : les trois surcharges de
    `CanAddUnit` sont contigues (moins de 0x100 octets d'ecart), et lire 0x200 depuis la premiere
    ramassait le corps de la troisieme -- deux << surcharges >> repondaient alors au meme critere."""
    return sorted({va for vas in sym.values() for va in vas})


def _corps(dll: Path, sym: dict, va: int, plafond: int = 0x2000) -> bytes:
    """Le corps d'UNE fonction, borne par le debut de la suivante."""
    bornes = _bornes(sym)
    import bisect
    i = bisect.bisect_right(bornes, va)
    fin = bornes[i] if i < len(bornes) else va + plafond
    return _read_at_va(dll, va, min(plafond, max(0, fin - va)))


@pytest.fixture(scope="module")
def pe():
    build = _build_hash()
    if build is None:
        pytest.skip("aucun build avec table `ghidra/functions.tsv` ET GameAssembly.dll installee")
    dll = Path(os.environ.get("LOCALAPPDATA") or "") / "tacticus" / "games" / build / "GameAssembly.dll"
    return build, dll, _symbols(build)


# ============ etage 1 : la surcharge a UN argument code le trigger NIE -- d'ou le defaut `True`

def test_la_surcharge_a_UN_argument_code_le_trigger_NIE_en_dur(pe):
    """C'EST L'ETAGE QUI RENVERSE LE DEFAUT.

    `DSLSelectors$$CanAddUnit(tiles)` -- la surcharge la plus appelee du binaire, et celle que
    represente `CanAddUnit(source)` sans annotation cote port -- ne recoit AUCUN trigger : elle le
    prend dans le contexte partage, par `mov <reg>,[<reg>+0x88]` (l'instance `DSLTriggers`, cf.
    `IdunBattleLogic.Entities.DSLFactory$$.ctor` : `this+0x88 = new DSLTriggers(this)`) puis
    `mov <reg>,[<reg>+0x48]` -- le slot NIE.

    Le port codait la branche inverse. La dégradation est SILENCIEUSE : elle ne change que la tuile
    ou un summon se pose quand un `Steppable` (decoy, mine, spore, token) l'occupe."""
    build, dll, sym = pe
    vas = sym.get(CAN_ADD_UNIT)
    assert vas and len(vas) == 3, (
        f"attendu TROIS surcharges de `{CAN_ADD_UNIT}`, trouve {len(vas or [])} sur {build}")
    # On DERIVE la surcharge a un argument : c'est la SEULE des trois dont le corps contient a la
    # fois un `mov <reg>,[<reg>+0x88]` et un `mov <reg>,[<reg>+0x48]`. On ne la choisit pas par son
    # adresse (qui change a chaque build) ni par son rang dans la table.
    trouvees = []
    for va in vas:
        blob = _corps(dll, sym, va)
        assert blob, f"lecture PE vide a {va:#x}"
        if _charge_disp32(blob, SLOT_DSLTRIGGERS) and SLOT_TRIGGER_NIE in _charges_disp8(blob):
            trouvees.append(va)
    assert len(trouvees) == 1, (
        f"{len(trouvees)} surcharge(s) de `CanAddUnit` chargent `<DSLTriggers>+"
        f"{SLOT_TRIGGER_NIE:#x}` depuis le contexte partage (attendu 1) -- l'appariement "
        "surcharge <-> slot a bouge, le DEFAUT du port est a re-deriver")
    blob = _corps(dll, sym, trouvees[0])
    assert SLOT_TRIGGER_NU not in _charges_disp8(blob), (
        "la surcharge a UN argument charge AUSSI le slot NU : les deux triggers coexistent dans "
        "son corps, la lecture qui fonde le defaut `True` n'est plus univoque")


def test_les_call_sites_qui_posent_FALSE_passent_bien_le_trigger_NU(pe):
    """LA CONTRE-EPREUVE DE L'ETAGE PRECEDENT, sur les deux natifs que le port annote `False`.

    Sans elle, l'etage 1 serait indiscernable d'un binaire ou TOUS les call-sites passeraient le
    meme slot -- et le parametre `allow_steppable` n'aurait aucune raison d'exister."""
    build, dll, sym = pe
    cibles = set(sym.get(CAN_ADD_UNIT) or [])
    assert cibles, f"symbole absent de la table du build {build}"
    for nom in CALL_SITES_TRIGGER_NU:
        va = sym.get(nom)
        assert va, f"symbole absent de la table du build {build} : {nom}"
        blob = _read_at_va(dll, va[0], 0x2000)
        calls = _calls_vers(blob, va[0], cibles)
        assert calls, f"{nom} : aucun appel a `CanAddUnit` -- l'arbre natif a change"
        for off in calls:
            disps = _disp8_du_3e_argument(blob, off)
            assert disps and disps[-1] == SLOT_TRIGGER_NU, (
                f"{nom} : le 3e argument du call a {va[0] + off:#x} est "
                f"<DSLTriggers>+{(disps[-1] if disps else -1):#x} et non +{SLOT_TRIGGER_NU:#x} -- "
                "`allowSteppable` a CHANGE DE SENS a ce call-site, le port doit suivre")


# ============================================ etage 3 : le port, cote DEFAUT et cote ANNOTATION

def test_le_defaut_du_noeud_est_TRUE():
    """Le defaut du port EST le defaut du natif. Un lecteur qui le remettrait a `False` rendrait le
    port RESTRICTIF sur 123 call-sites d'un coup, sans aucun symptome."""
    assert CanAddUnit(Const([])).allow_steppable is True, (
        "le defaut d'`allow_steppable` n'est plus `True` -- cf. l'etage 1 : la surcharge a UN "
        "argument code `<DSLTriggers+0x48>` en dur, donc `allowSteppable` VRAI")


def test_les_trois_sites_portes_qui_posent_FALSE_le_font_toujours():
    """Les SEULS sites du port dont le call-site natif passe le trigger NU. Les laisser au defaut
    les rendrait PERMISSIFS (une mine posee sur un `Steppable` que le natif tient pour occupant)."""
    from engine.runner.abilities.orks import squig_mine_pool_tree
    from engine.runner.operations.triggers.loki.haywire_mine import haywire_mine_tiles

    pool = squig_mine_pool_tree(1, 2)
    assert pool.source.allow_steppable is False, (
        "`squig_mine_pool_tree` mirroite `...SquigMineAbility$$ExecuteBehaviour`, qui passe "
        "`<DSLTriggers+0x40>` (etage 2)")
    # `haywire_mine_tiles` rend `Cache(SelectIf(garde, CanAddUnit(prev), <adjacentes>))` :
    # on ne fouille pas l'arbre a la main, on collecte TOUS les `CanAddUnit` par recurrence sur les
    # attributs -- un arbre qui change de forme ne doit pas rendre le test VACANT.
    noeuds = _tous_les_can_add_unit(haywire_mine_tiles())
    assert len(noeuds) == 2, (
        f"{len(noeuds)} noeud(s) `CanAddUnit` dans l'arbre de `HaywireMineAbility` (attendu 2, "
        "les deux call-sites natifs releves a l'etage 2)")
    assert all(n.allow_steppable is False for n in noeuds), (
        "un `CanAddUnit` de `HaywireMineAbility` a repris le defaut `True` : le natif y passe "
        "`<DSLTriggers+0x40>` aux DEUX call-sites")


def _attributs(node) -> list:
    """Les noms d'attributs d'un objet, TOUTES formes de stockage confondues.

    ⚠ **`__slots__` ET `__dict__` COEXISTENT, et un objet peut n'avoir NI l'un NI l'autre.** La
    version d'avant faisait `getattr(node, "__slots__", None) or vars(node)` : elle levait
    `TypeError: vars() argument must have __dict__ attribute` des qu'un arbre contenait un objet
    sans `__dict__` et sans `__slots__` PROPRE -- ce qui est arrive au REBASE, sur du code merge
    entre-temps. Elle aurait aussi RATE les attributs `__dict__` d'une classe a `__slots__`
    partiel, donc rendu le test VACANT en silence.

    On balaie la MRO (chaque classe peut declarer ses propres `__slots__`) et on ajoute `__dict__`
    quand il existe. Un objet sans aucun des deux rend `[]` -- c'est une FEUILLE, pas une erreur."""
    noms = []
    for cls in type(node).__mro__:
        s = cls.__dict__.get("__slots__")
        if isinstance(s, str):
            noms.append(s)
        elif s:
            noms.extend(s)
    d = getattr(node, "__dict__", None)
    if isinstance(d, dict):
        noms.extend(d.keys())
    return noms


def _tous_les_can_add_unit(node, vus=None) -> list:
    """Parcours GENERIQUE d'un arbre DSL : tout attribut qui est un noeud, ou un conteneur de
    noeuds, est visite. Ecrit ainsi pour qu'un changement de FORME de l'arbre ne rende pas le test
    vacant (il rougirait sur le COMPTE, au lieu de ne rien trouver)."""
    vus = vus if vus is not None else set()
    if id(node) in vus or node is None or isinstance(node, (str, bytes, int, float, bool)):
        return []
    vus.add(id(node))
    out = [node] if isinstance(node, CanAddUnit) else []
    if isinstance(node, (list, tuple, set, frozenset)):
        enfants = list(node)
    elif isinstance(node, dict):
        enfants = list(node.values())
    else:
        enfants = [getattr(node, nom, None) for nom in _attributs(node)]
    for e in enfants:
        out += _tous_les_can_add_unit(e, vus)
    return out


# ================================================================== le montage OFFLINE partage

def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


@pytest.fixture
def state():
    """`MARCHEUR` porte `Steppable` en (3,3) ; `VICTIME` (5,5) et `TEMOIN` (0,0) sont des ancres."""
    board = Board(_tiles(), adjacency="evenq")
    pos = {MARCHEUR: (3, 3), VICTIME: (5, 5), TEMOIN: (0, 0)}
    decision = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "ultraTitus", "alive": True, "team": 1 if uid != TEMOIN else 2,
         "owner": 1 if uid != TEMOIN else 2,
         "pos": {"col": pos[uid][0], "row": pos[uid][1]}, "effects": []}
        for uid in (MARCHEUR, VICTIME, TEMOIN)]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000,
                           "traits": ([int(UnitTrait.Steppable)] if u["id"] == MARCHEUR else []),
                           "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    return load_state(decision, observe, snapshot, board=board, ability_states=False)


# ==================================== etage 4 : les DEUX branches d'`allowSteppable`, cote port

def test_le_defaut_rend_LIBRE_la_tuile_du_steppable_et_False_la_refuse(state):
    """CONTROLE POSITIF ET CONTRE-EPREUVE dans le MEME etat -- sans les deux, un montage ou rien
    n'occupe la tuile passerait pour vert."""
    centre = _tid(3, 3)
    ctx = entities_from_state(state, caster_id=VICTIME, target_id=TEMOIN)
    assert CanAddUnit(Const([centre])).evaluate(ctx) == [centre], (
        "le DEFAUT ne rend pas la tuile du `Steppable` : la branche `allowSteppable == 1` a ete "
        "perdue, ou le defaut est retombe a `False`")
    assert CanAddUnit(Const([centre]), allow_steppable=False).evaluate(ctx) == [], (
        "la branche `allowSteppable == 0` n'a PAS mordu -- le montage est degenere (le `MARCHEUR` "
        "ne porte peut-etre plus `Steppable`)")


# ========================= etages 5-7 : le gate de RESERVATION, ses DEUX polarites (#550-r4)

def test_parent_NUL_refuse_une_tuile_reservee_par_quiconque(state):
    """Branche `allowedUnit == null` de `TileExtensions$$IsTileReservedForOtherUnit` = `HasValue`.

    C'est la polarite des 146 call-sites sur 147 -- ceux dont le `parent` est le selecteur que rend
    `DSLSelectors$$None()` (`EntitySelector` vide)."""
    libre, reservee = _tid(1, 1), _tid(2, 2)
    ctx = entities_from_state(state, caster_id=VICTIME, target_id=TEMOIN)
    assert CanAddUnit(Const([libre, reservee])).evaluate(ctx) == [libre, reservee], (
        "controle positif : sans reservation, les deux tuiles passent")
    tile_reservation.reserve_for_unit(state, (2, 2), TEMOIN)
    ctx = entities_from_state(state, caster_id=VICTIME, target_id=TEMOIN)
    assert CanAddUnit(Const([libre, reservee])).evaluate(ctx) == [libre], (
        "une tuile RESERVEE reste acceptee : le 2e gate de `CanAddUnitFromAbility` n'est pas joue")


def test_parent_NON_NUL_INVERSE_la_polarite(state):
    """Branche `allowedUnit != null` : `!(HasValue && Value == allowedUnit.Id)`.

    ⚠ **CE N'EST PAS UNE COQUILLE DU DECOMPILE**, et c'est ce que ce test interdit de << corriger >> :
    sur une tuile NON reservee, `TileExtensions$$IsTileReservedForOtherUnit` rend **VRAI** (son
    raccourci `if (!HasValue) return true` CONFIRME la formule), la ou son homonyme
    `BattleQuery$$IsTileReservedForAnotherUnit` rend FAUX. C'est cette polarite qui rend le
    `Reserve(Owner, targetTiles)` d'`ItItches` LOAD-BEARING."""
    a, b, c = _tid(1, 1), _tid(2, 2), _tid(4, 4)
    ctx = entities_from_state(state, caster_id=VICTIME, target_id=TEMOIN, owner_id=VICTIME)
    assert CanAddUnit(Const([a, b, c]), parent_sel=Owner()).evaluate(ctx) == [], (
        "AUCUNE reservation posee et pourtant des tuiles passent : la branche `allowedUnit != null` "
        "a ete rabattue sur la polarite de `BattleQuery$$IsTileReservedForAnotherUnit`")
    tile_reservation.reserve_for_unit(state, (2, 2), VICTIME)      # reservee POUR le parent
    tile_reservation.reserve_for_unit(state, (4, 4), TEMOIN)       # reservee pour un AUTRE
    ctx = entities_from_state(state, caster_id=VICTIME, target_id=TEMOIN, owner_id=VICTIME)
    assert CanAddUnit(Const([a, b, c]), parent_sel=Owner()).evaluate(ctx) == [b], (
        "seule la tuile reservee POUR le parent doit passer -- `Value == allowedUnit.Id`")


def test_substrat_ABSENT_ne_joue_PAS_le_gate():
    """`ctx.tile_reserved_for_other_unit` absent = NON MESURE, pas << aucune reservation >>.

    Le rabattre sur une table vide ferait rendre un ensemble VIDE a tout `CanAddUnit(..., parent)`
    non nul -- donc casserait tout contexte de prediction, qui n'a pas de table de reservation."""
    board = Board(_tiles(), adjacency="evenq")
    ctx = DslContext(units=[], board=board)
    assert getattr(ctx, "tile_reserved_for_other_unit", None) is None
    assert CanAddUnit(Const([_tid(1, 1)]), parent_sel=Owner()).evaluate(ctx) == [_tid(1, 1)], (
        "sans substrat, le gate mord quand meme : la degradation nommee a disparu")


def test_it_itches_pose_bien_son_parent_et_son_Reserve_amont():
    """L'arbre de `1121 ItItches` porte les DEUX moities du couple. Les separer casse le cast :
    `parent` sans `Reserve` -> ZERO spawn ; `Reserve` sans `parent` -> le noeud est decoratif."""
    from engine.runner.abilities.tyranids import it_itches_tree
    _atomic, _reset, group = it_itches_tree(_tid(3, 3), 0)
    noeuds = _tous_les_can_add_unit(group)
    assert len(noeuds) == 1, f"{len(noeuds)} `CanAddUnit` dans le bloc SUMMON d'ItItches (attendu 1)"
    assert noeuds[0].parent_sel is not None, (
        "le `CanAddUnit` d'`ItItches` a perdu son `parent_sel` -- le call-site natif est la SEULE "
        "occurrence de la surcharge a TROIS arguments du binaire, et il y passe `Owner@+0x30`")
    assert noeuds[0].allow_steppable is True, (
        "`ItItchesAbility$$ExecuteBehaviour` passe `<DSLTriggers+0x48>` -> `allowSteppable` VRAI")


# ============== etages 8-9 : les deux gates propres de `SetUnitPositionOperation$$Execute`

def test_S2_refuse_de_deplacer_un_CADAVRE_et_NOMME_sa_raison(state):
    """`if (UnitExtensions.HasFlag(unit, 6 = Dead)) { log; return; }`.

    ⚠ **S2 N'EST PLUS DOUBLE (#550-r4-r1), ET CETTE DOCSTRING A ETE MISE A JOUR PARCE QUE LE TEST
    L'A DEMANDE LUI-MEME** (son dernier message d'assertion disait : << le gate (c) du bloc override
    a change -- S2 n'est donc PLUS double, et c'est desormais LUI qui porte le refus. Mettre a jour
    cette docstring. >>). Le gate (c) du bloc override d'
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (`if (!ovr.HasValue || IsDead(unit))
    { RemoveReservation; return; }`) appartient a `MoveUnitOperation` et **PAS** a
    `SetUnitPositionOperation` : il est desormais ETEINT sous `set_unit_position_gates`, avec la
    reservation et le vecteur `On(PreUnitMove)` du meme bloc. S2 est donc SEUL a porter le refus
    pour les stand-ins, et le second volet de ce test le verifie encore -- mais sur l'autre face :
    hors stand-in, c'est bien le gate (c) qui refuse, et il NOMME desormais sa raison."""
    e = state.get_entity(VICTIME)
    e.get_component(UnitComponent).alive = False
    dest = (5, 4)
    op = MoveUnitOperation(VICTIME, dest, emit_after_move=False, enforce_native_gates=False,
                           set_unit_position_gates=True)
    op.execute(state, EventBus())
    assert op.last_abandoned == "set-position-unit-dead", (
        f"abandon '{op.last_abandoned}' au lieu de S2 -- le gate `HasFlag(unit, 6)` d'"
        "`IdunBattle.Operations.SetUnitPositionOperation$$Execute` n'est pas joue, ou un gate "
        "AMONT le devance (verifier lequel : c'est le proprietaire du refus qui est en jeu)")
    from engine.runner.components import PositionComponent
    pc = e.get_component(PositionComponent)
    assert (pc.col, pc.row) == (5, 5), "le cadavre a bouge malgre l'abandon"
    # L'AUTRE FACE (#550-r4-r1) : HORS stand-in, le bloc override est joue et c'est son gate (c)
    # qui refuse -- avec, depuis cette tranche, une RAISON. Les deux refus existent donc toujours,
    # mais chacun chez son proprietaire, et ils ne se recouvrent plus.
    op2 = MoveUnitOperation(VICTIME, dest, emit_after_move=False, enforce_native_gates=False)
    op2.execute(state, EventBus())
    pc = e.get_component(PositionComponent)
    assert (pc.col, pc.row) == (5, 5) and op2.last_abandoned == "override-unit-dead", (
        f"hors stand-in le port a bouge le cadavre (pos={(pc.col, pc.row)}, "
        f"abandon={op2.last_abandoned!r}) : le gate (c) du bloc override d'"
        "`MoveUnitOperation$$Execute` ne refuse plus -- or c'est LUI le proprietaire de ce "
        "refus-la, S2 ne couvre que les stand-ins de `SetUnitPositionOperation`")


def test_S1_refuse_une_empreinte_de_CARDINALITE_differente(state):
    """`if (feet.Count != position.Count) { log; return; }`.

    ⚠ Ce gate n'a PAS le bras `Count == 0 -> true` de son cousin `MoveUnitOperation$$
    TilesMatchUnitFeetCount` (G4) : une `UnitPosition` VIDE y est REFUSEE des que l'unite a un pied.
    C'est le seul regime que le collapse mono-hex du port laisse atteignable."""
    op = MoveUnitOperation(TEMOIN, None, emit_after_move=False, enforce_native_gates=False,
                           allow_null_target_position=True, set_unit_position_gates=True)
    op.execute(state, EventBus())
    assert op.last_abandoned == "set-position-feet-count-mismatch", (
        f"abandon '{op.last_abandoned}' au lieu de S1 -- une `UnitPosition` VIDE passe alors que "
        "`SetUnitPositionOperation` la refuse (il n'a pas le bras lift-off de G4)")


def test_les_stand_ins_de_displace_arment_TOUS_le_flag():
    """Le gate ne vaut que s'il est POSE. Ce cliquet lit l'AST de `displace.py` -- un stand-in
    ajoute sans le flag serait invisible autrement.

    ⚠ AST et pas `str.count` : les commentaires citent `set_unit_position_gates=True` plusieurs fois
    pour l'expliquer, et un comptage textuel rendait 9 pour 5 sites. Un cliquet qui compte des
    COMMENTAIRES ne garde rien."""
    import ast
    import inspect
    from engine.runner.operations import displace as D
    arbre = ast.parse(inspect.getsource(D))
    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "MoveUnitOperation"]
    assert len(appels) == 5, (
        f"{len(appels)} `MoveUnitOperation(...)` dans `displace.py` (attendu 5 : push, pull, "
        "switch x2, Direct). Un stand-in a ete ajoute ou retire : verifier qu'il mirroite bien "
        "`IdunBattle.Operations.SetUnitPositionOperation$$Execute` avant de l'armer")
    manquants = [a.lineno for a in appels
                 if not any(k.arg == "set_unit_position_gates"
                            and isinstance(k.value, ast.Constant) and k.value.value is True
                            for k in a.keywords)]
    assert manquants == [], (
        f"les stand-ins des lignes {manquants} de `displace.py` n'arment pas "
        "`set_unit_position_gates` -- ils ecrivent une position que "
        "`SetUnitPositionOperation$$Execute` refuserait d'ecrire")
