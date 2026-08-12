"""GARDE #955-r2 (OFFLINE PURE) -- `FreeTilesOrAdjacentFreeTiles` a DEUX surcharges, et elles ne
passent PAS le meme trigger. Le port est JUSTE sur les quatre consommateurs : ne pas << harmoniser >>.

CE FICHIER EXISTE PARCE QUE LE RESIDU QUI L'A OUVERT ETAIT FAUX, et faux d'UN BIT.

`#955-r2` annoncait : << QUATRE consommateurs, UN SEUL porte `allowSteppable` ; les trois collapses
imperatifs sont RESTRICTIFS >>. Il avait lu la surcharge a DEUX arguments -- qui prend son trigger
dans son PROPRE corps, a `<DSLTriggers>+0x48` -- et lui avait attribue les call-sites de la surcharge
a TROIS arguments, ou le trigger est passe PAR L'APPELANT. Mesure (etage 2) : les trois passent
`<DSLTriggers>+0x40`, pas `+0x48`.

LES DEUX SLOTS SONT ADJACENTS ET L'UN EST LA NEGATION DE L'AUTRE -- c'est ce qui rend la confusion
muette. `IdunBattleLogic.Entities.DSLTriggers$$.ctor`, LU :

    +0x40 = new <trigger sans champ>(0)                      // le trigger NU
    +0x48 = IdunBattle.DSL.AbilityTrigger$$op_LogicalNot( new <le meme type>(0) )
    +0x70 = new <le meme type>(0)                            // deja nomme `YesTrigger` par le port

et `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` **INVERSE** ce qu'il recoit :

    allowSteppable = !( <+0x28>.ShouldTrigger(entities, 0x20) )

donc, le trigger nu rendant TOUJOURS vrai :

    isSteppable = <DSLTriggers>+0x40  ->  ShouldTrigger VRAI  ->  allowSteppable **FAUX**
    isSteppable = <DSLTriggers>+0x48  ->  ShouldTrigger FAUX  ->  allowSteppable **VRAI**

VERDICT : les trois collapses imperatifs (`triggers/genestealer.py::_free_tile_or_adjacent`, ses
DEUX call-sites, et `loki/cosmic_horror.py::_decoy_tile_for_kill`) tiennent une tuile occupee par un
`Steppable` pour OCCUPEE -- et c'est **FIDELE**. Seul `loki/possession.py::possession_spawn_tree`,
qui passe par la surcharge a DEUX arguments, porte `allow_steppable=True` -- et c'est fidele aussi.
Ajouter `allowSteppable` aux trois serait un ecart PERMISSIF : le summon/decoy se poserait sur un
mur, un decor ou un token, la ou le natif refuse.

ASCII only. Aucune VA en dur (tout est resolu par `data/symbols/<build>/ghidra/functions.tsv`).
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.operations.triggers import genestealer as GS
from engine.runner.operations.triggers.loki import cosmic_horror as CH
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        # les trois collapses que ce fichier FIGE, et le quatrieme consommateur (l'arbre deplie)
        "scripts/python/engine/runner/operations/triggers/genestealer.py",
        "scripts/python/engine/runner/operations/triggers/loki/cosmic_horror.py",
        "scripts/python/engine/runner/operations/triggers/loki/possession.py",
        # le foyer du noeud, dont la branche `allow_steppable` est l'objet du verdict
        "scripts/python/engine/entities/selectors/tiles.py",
        # le mirror d'enum dont ce fichier FIGE l'ordinal (`Steppable`)
        "scripts/python/engine/entities/traits/unit_trait.py",
        # la cascade que `load_state` tire
        "scripts/python/engine/runner/snapshot.py",
    ),
    # Etages 1-3 : ils LISENT `GameAssembly.dll`, HORS de l'arbre.
    "build": True,
    "toujours": False,
    "raison": "Il grave l'appariement surcharge <-> slot de trigger (`+0x40` nu vs `+0x48` nie), "
              "c'est-a-dire la SEULE chose qui distingue les quatre consommateurs. La confusion "
              "vaut UN BIT, elle n'a aucun symptome, et elle a deja produit un residu FAUX qui "
              "demandait de rendre les trois collapses PERMISSIFS.",
}

ROOT = Path(__file__).resolve().parents[4].parent          # racine du depot
IMAGE_BASE = 0x180000000                                   # base de l'image PE de GameAssembly.dll

#: Le slot que la surcharge a TROIS arguments recoit de ses appelants -- trigger NU, donc
#: `allowSteppable` FAUX apres l'inversion de `CanAddUnitTileSelector$$Select`.
SLOT_TRIGGER_NU = 0x40
#: Le slot que la surcharge a DEUX arguments lit dans son propre corps -- `op_LogicalNot(<nu>)`,
#: donc `allowSteppable` VRAI.
SLOT_TRIGGER_NIE = 0x48

FREE_TILES = "IdunBattleLogic.Entities.DSLSelectors$$FreeTilesOrAdjacentFreeTiles"
OP_NOT = "IdunBattle.DSL.AbilityTrigger$$op_LogicalNot"
DSL_TRIGGERS_CTOR = "IdunBattleLogic.Entities.DSLTriggers$$.ctor"

#: Les TROIS consommateurs que le port collapse imperativement -- ils passent le trigger NU.
LES_TROIS_COLLAPSES = (
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility$$GetSummonBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
    "HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour",
)
#: Le QUATRIEME -- celui que le port deplie en arbre, avec `allow_steppable=True`.
LE_QUATRIEME = "IdunBattleLogic.Entities.Abilities.Active.Loki.PossessionAbility$$CreateBehaviour"

COLS, ROWS = 7, 7
MUR, VICTIME, TEMOIN = 10, 20, 30


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
    """Traduction VA -> offset fichier par les SECTIONS du PE. La RVA est calculee EN CODE."""
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


def _disp8_du_3e_argument(blob: bytes, offset_du_call: int) -> list:
    """Les deplacements des `mov r8, [reg+disp8]` qui precedent le call.

    `r8` est le TROISIEME argument de la convention x64 Microsoft, donc `isSteppable`. Le motif est
    `REX.WR|REX.WRB` (`4C`/`4D`) + `8B` + modrm `mod=01, reg=000` (`0x40`..`0x47`) + disp8."""
    fenetre = blob[max(0, offset_du_call - 40):offset_du_call]
    return [fenetre[j + 3] for j in range(len(fenetre) - 3)
            if fenetre[j] in (0x4C, 0x4D) and fenetre[j + 1] == 0x8B
            and 0x40 <= fenetre[j + 2] <= 0x47]


@pytest.fixture(scope="module")
def pe():
    build = _build_hash()
    if build is None:
        pytest.skip("aucun build avec table `ghidra/functions.tsv` ET GameAssembly.dll installee")
    dll = Path(os.environ.get("LOCALAPPDATA") or "") / "tacticus" / "games" / build / "GameAssembly.dll"
    return build, dll, _symbols(build)


# ---------------------------------------------------------------- etage 1 : le ctor de DSLTriggers

def test_le_slot_0x48_est_la_NEGATION_du_slot_0x40(pe):
    """`DSLTriggers$$.ctor` n'appelle `op_LogicalNot` qu'UNE FOIS, et range son resultat en `+0x48`.

    C'est CE fait qui donne leur sens opposé aux deux slots. S'il basculait, tous les verdicts
    `allowSteppable` du port s'inverseraient EN SILENCE : la branche n'a ni erreur ni trace, elle
    change seulement la tuile ou le summon se pose."""
    build, dll, sym = pe
    ctor = sym.get(DSL_TRIGGERS_CTOR)
    op_not = sym.get(OP_NOT)
    assert ctor and op_not, f"symboles absents de la table du build {build}"
    blob = _read_at_va(dll, ctor[0], 0x300)
    assert blob, "lecture PE vide"
    calls = _calls_vers(blob, ctor[0], set(op_not))
    assert len(calls) == 1, (
        f"{len(calls)} appels a `op_LogicalNot` dans `DSLTriggers$$.ctor` (attendu 1) -- "
        "l'appariement slot <-> negation est a re-lire")
    # `mov [reg+disp8], rax` juste apres le call : `48 89 <modrm 0x40..0x47> <disp8>`
    apres = blob[calls[0] + 5:calls[0] + 9]
    assert apres[0] == 0x48 and apres[1] == 0x89 and 0x40 <= apres[2] <= 0x47, (
        f"forme de stockage inattendue apres `op_LogicalNot` : {apres.hex()}")
    assert apres[3] == SLOT_TRIGGER_NIE, (
        f"le resultat d'`op_LogicalNot` est range en +{apres[3]:#x}, pas en "
        f"+{SLOT_TRIGGER_NIE:#x} -- les deux slots ont echange leur sens")


# ------------------------------------------------- etages 2 et 3 : QUEL slot chaque call-site passe

def test_les_TROIS_collapses_passent_le_trigger_NU(pe):
    """Ils appellent la surcharge a TROIS arguments et lui passent `<DSLTriggers>+0x40`.

    ⇒ `ShouldTrigger` VRAI ⇒ `allowSteppable` **FAUX** ⇒ une tuile occupee par un `Steppable` est
    OCCUPEE. Les collapses du port sont fideles ; leur ajouter la branche serait PERMISSIF."""
    build, dll, sym = pe
    ft = sym.get(FREE_TILES)
    assert ft and len(ft) == 2, (
        f"attendu DEUX surcharges de `{FREE_TILES}`, trouve {len(ft or [])}")
    # La surcharge a 3 arguments est celle que les call-sites appellent avec un `r8` charge : on la
    # DERIVE, on ne la choisit pas -- c'est celle qu'atteignent les trois symboles ci-dessous.
    vues = set()
    for nom in LES_TROIS_COLLAPSES:
        va = sym.get(nom)
        assert va, f"symbole absent de la table du build {build} : {nom}"
        blob = _read_at_va(dll, va[0], 0x1200)
        calls = _calls_vers(blob, va[0], set(ft))
        assert len(calls) == 1, (
            f"{nom} : {len(calls)} appels a `FreeTilesOrAdjacentFreeTiles` (attendu 1)")
        rel = struct.unpack_from("<i", blob, calls[0] + 1)[0]
        vues.add(va[0] + calls[0] + 5 + rel)
        disps = _disp8_du_3e_argument(blob, calls[0])
        assert disps, f"{nom} : aucun `mov r8, [reg+disp8]` avant le call -- forme a re-lire"
        assert disps[-1] == SLOT_TRIGGER_NU, (
            f"{nom} passe `isSteppable = <DSLTriggers>+{disps[-1]:#x}` et non "
            f"+{SLOT_TRIGGER_NU:#x} : `allowSteppable` a CHANGE DE SENS a ce call-site")
    assert len(vues) == 1, "les trois collapses n'appellent pas la MEME surcharge"


def test_le_QUATRIEME_appelle_l_AUTRE_surcharge_sans_charger_r8(pe):
    """`PossessionAbility$$CreateBehaviour` appelle la surcharge a DEUX arguments, qui prend son
    trigger dans son PROPRE corps (`<dsl>.<+0x88>.<+0x48>`) -- d'ou aucun `mov r8` au call-site.

    C'est le seul des quatre pour lequel `allow_steppable=True` est fidele. Ce test est ce qui
    interdit de LUI retirer la branche en croyant << uniformiser >>."""
    build, dll, sym = pe
    ft = sym.get(FREE_TILES)
    va = sym.get(LE_QUATRIEME)
    assert ft and va, f"symboles absents de la table du build {build}"
    blob = _read_at_va(dll, va[0], 0x1200)
    calls = _calls_vers(blob, va[0], set(ft))
    assert len(calls) == 1, f"{LE_QUATRIEME} : {len(calls)} appels (attendu 1)"
    assert _disp8_du_3e_argument(blob, calls[0]) == [], (
        "PossessionAbility charge un 3e argument -- il n'appelle donc plus la surcharge a DEUX "
        "arguments, et son `allow_steppable=True` est a re-deriver")
    # ... et ce n'est PAS la surcharge des trois autres.
    rel = struct.unpack_from("<i", blob, calls[0] + 1)[0]
    cible = va[0] + calls[0] + 5 + rel
    autres = set()
    for nom in LES_TROIS_COLLAPSES:
        b2 = _read_at_va(dll, sym[nom][0], 0x1200)
        c2 = _calls_vers(b2, sym[nom][0], set(ft))
        r2 = struct.unpack_from("<i", b2, c2[0] + 1)[0]
        autres.add(sym[nom][0] + c2[0] + 5 + r2)
    assert cible not in autres, (
        "PossessionAbility appelle desormais la MEME surcharge que les trois collapses -- "
        "l'asymetrie que ce fichier garde a disparu")


# ------------------------------------------------------------------ etage 4 : le port, des DEUX cotes

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
    """`MUR` est un occupant VIVANT portant le trait `Steppable`, en (3,3). `VICTIME` et `TEMOIN`
    sont ailleurs et servent d'ancres."""
    board = Board(_tiles(), adjacency="evenq")
    pos = {MUR: (3, 3), VICTIME: (5, 5), TEMOIN: (0, 0)}
    decision = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "ultraTitus", "alive": True, "team": 1 if uid != TEMOIN else 2,
         "owner": 1 if uid != TEMOIN else 2,
         "pos": {"col": pos[uid][0], "row": pos[uid][1]}, "effects": []}
        for uid in (MUR, VICTIME, TEMOIN)]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000,
                           # canal `combatSnapshot.units[].traits` = des IDS natifs, que
                           # `trait_names_from_ids` nomme -- jamais des noms.
                           "traits": ([int(UnitTrait.Steppable)] if u["id"] == MUR else []),
                           "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    return load_state(decision, observe, snapshot, board=board, ability_states=False)


def test_le_temoin_du_montage_porte_bien_le_trait(state):
    """CONTROLE DE NON-DEGENERESCENCE : si `MUR` n'etait pas `Steppable`, les deux etages suivants
    rendraient le meme resultat pour une raison qui n'a rien a voir, et passeraient pour verts."""
    from engine.runner.components import StatsComponent
    from engine.entities.traits.unit_trait import has_trait
    sc = state.get_entity(MUR).get_component(StatsComponent)
    assert has_trait(getattr(sc.ctx, "traits", None) or [], UnitTrait.Steppable)


@pytest.mark.parametrize("fn,label", [
    (lambda st: GS._free_tile_or_adjacent(st, (3, 3)), "genestealer::_free_tile_or_adjacent"),
    (lambda st: CH._decoy_tile_for_kill(st, MUR, VICTIME), "cosmic_horror::_decoy_tile_for_kill"),
])
def test_un_occupant_STEPPABLE_bloque_bien_la_tuile_des_trois_collapses(state, fn, label):
    """LE VERDICT. `allowSteppable` FAUX a ces call-sites (etage 2) : la tuile du `Steppable` est
    OCCUPEE, donc le collapse retombe sur une ADJACENTE.

    Un futur lecteur qui << corrigerait >> ces trois-la en `allow_steppable=True` verrait ce test
    rougir -- c'est exactement ce que le residu #955-r2 demandait de faire, sur une premisse fausse."""
    centre = _tid(3, 3)
    got = fn(state)
    assert got is not None, f"{label} : aucune tuile rendue -- montage a re-verifier"
    assert got != centre, (
        f"{label} rend la tuile du `Steppable` ({got}) : la branche `allowSteppable` a ete ajoutee "
        "a un call-site qui passe le trigger NU (`<DSLTriggers>+0x40`) -- ecart PERMISSIF")


def test_le_QUATRIEME_canal_lui_ACCEPTE_la_tuile_du_steppable(state):
    """CONTRE-EPREUVE MORDANTE, et elle porte sur le MEME etat : le noeud que `possession_spawn_tree`
    assemble (`CanAddUnit(., allow_steppable=True)`) rend la tuile que les trois collapses refusent.

    Sans elle, l'etage precedent serait indiscernable d'un montage ou RIEN n'occupe la tuile."""
    from engine.entities.selectors.tiles import CanAddUnit
    from engine.entities.selectors.geometry import Const
    from engine.runner.abilities.behaviours.context import entities_from_state
    centre = _tid(3, 3)
    ctx = entities_from_state(state, caster_id=VICTIME, target_id=MUR)
    refuse = CanAddUnit(Const([centre]), allow_steppable=False).evaluate(ctx)
    accepte = CanAddUnit(Const([centre]), allow_steppable=True).evaluate(ctx)
    assert refuse == [], "la branche `allowSteppable=False` n'a PAS mordu -- montage degenere"
    assert accepte == [centre], (
        "la branche `allowSteppable=True` ne rend pas la tuile du `Steppable` : le foyer "
        "`selectors/tiles.py::CanAddUnit` a perdu sa branche, et `PossessionAbility` avec elle")
