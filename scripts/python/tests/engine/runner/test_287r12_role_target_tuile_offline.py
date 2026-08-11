"""#287-r12 -- CLIQUET du role `target` d'une entite TUILE dans l'`AbilityEntities`.

Ce que ce fichier garde, et que les probes ne gardent pas : `probe_287r12_role_target_tuile.py`
MESURE (rayon de souffle, regimes U/T) et `probe_287r12_confront_live.py` CONFRONTE (il lui faut une
session Frida chaude) ; ici on fige, hors ligne, les six proprietes dont la perte serait SILENCIEUSE
-- c'est tout le sujet du cas : un role `target` nul ne leve rien, il fait juste que l'ability ne
fait RIEN.

  [1] LE FOYER MATERIALISE -- `entities_from_state` rend une entite-TUILE sur le role `target` quand
      `target_id` designe une tuile du board, et reste INERTE sur une unite (le regime de tous les
      autres call-sites) comme sur un id qui n'est ni l'un ni l'autre.

  [2] LA FORME DU DICT -- `visualId is None`, `_traits` VIDE, `team`/`player` a `None`. Une valeur
      inventee ferait passer des gates de camp que le natif n'evalue pas ; et `visualId is None` est
      le discriminant par lequel le rayon de souffle reconnait une entite-tuile.

  [3] LE RAYON EFFECTIF EST {1017, 1018, 1057}, ET C'EST UN CLIQUET -- pas un inventaire. Le backlog
      en annoncait CINQ ; la mesure en rendait DEUX (les seules dont l'arbre EVALUE `Target()` en
      regime tuile), et `1057 GrotTank` s'y est AJOUTE avec le port #570. Toute ability qui ENTRE
      dans ce rayon sans avoir ete confrontee doit faire rougir : c'est exactement le gisement que
      notre propre cadence de portage alimente -- et il a mordu, comme prevu, sur cette entree-la.

  [4] LES DEUX SONT CONFRONTEES, et les valeurs figees ici sont celles MESUREES LIVE
      (`probe_287r12_confront_live.py`, board `MC1_67`, seed 777) :
        * `1018` -- le natif inscrit `1022 ValkyrieStrike_Effect` sur l'**ENTITE-TUILE** visee
          (`tileMeta.tiles[].effects`), PAS sur l'unite qui l'occupe (`decisionView.units[].effects`
          reste inchange). Le port d'AVANT ne posait RIEN ;
        * `1017` -- les 12 coups (6 sur la cible + 3 x 2 splash) sont bit-exacts contre le natif en
          regime TUILE ; le port d'AVANT en rendait **zero**.
        * `1057 GrotTank` (#570) -- confrontee par `probe_570_grot_tank.py` etage E1 et par
          `tests/engine/runner/test_grot_tank_live.py::test_grot_tank_spawns_on_the_targeted_tile`
          (board `MC1_67`, seed 777). Son arbre est `Spawn(Caster@0x48, Target@0x60, unitId, opts)`
          : le tile-selecteur EST le role `target`, donc l'entite-tuile en est le SUBSTRAT DIRECT --
          natif et port posent le summon sur la MEME tuile, celle qui a ete ciblee, sur deux runs
          independants. Le TEMOIN du no-op a ete OBSERVE, pas suppose : au premier passage du probe
          le port rendait `spawned=[]` (la feuille iterait les CLES du dict d'entite-tuile) pendant
          que le natif posait `orksNpc3GrotTank` en (1,1) a 7977 PV.
          ⚠ La confrontation n'est PAS passee par `probe_287r12_confront_live.py` : ses deux volets
          sont SPECIALISES (montage `astraBullgryn` / `astraSmnVoxcaster` injecte au catalogue) et
          ne savent pas jouer 1057. C'est la meme QUESTION -- « le natif met-il l'entite-tuile sur
          le role `target` ? » -- tranchee par le meme genre d'observable (une action qui n'a lieu
          QUE si le role est materialise), sur le montage propre a cette ability.

  [5] `main_tile_id` SUIT L'ORDRE NATIF -- unite d'abord, tuile en REPLI.
      `IdunBattle.Entities.EntityExtensions$$GetMainTileId` essaie le composant de PIED, puis
      l'unite multi-pieds (`OrderedSet` @+0x78, element 0, RECURSION), et ne teste
      `EntityExtensions$$IsTile` qu'en dernier. Les deux espaces d'ids du port se CHEVAUCHENT, donc
      l'ordre DECIDE ce que rend un id ambigu -- et `plagueburst_target_tile` avait l'ordre INVERSE.

  [6] IL N'Y A PLUS QU'UN SEUL ENDROIT QUI FABRIQUE CE DICT. La parade a existe en TROIS
      exemplaires (locale dans `tyranids.AlphaWarriorAbility`, locale dans
      `targeting._dynamic_rule_excruciating_frequencies`, puis une fonction specialisee
      `entities_with_tile_target`). Un balayage STATIQUE garde qu'aucune copie ne repousse : c'est
      la faute que ce cas a corrigee, et elle se recree par imitation.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre DECLARE LARGE, et c'est mesure : l'etage [3] charge le REGISTRE ENTIER d'abilities et
#: joue chacune, donc la fermeture d'imports traverse tout `engine/**`. Une liste feuille a feuille
#: rougirait au premier import ajoute. `**/` exige un SEGMENT, d'ou les deux globs ET les conftest
#: ecrits un par un.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
        # ⚠ HORS de `scripts/python/` -- donc AUCUN glob ci-dessus ne les couvre. La cascade
        # d'import du registre LIT ces deux entrees versionnees. Meme omission qu'au merge de
        # #806, mesuree par `probe_486r15` : un declencheur qui ne nomme que du Python est
        # structurellement aveugle a ce que le paquet va chercher ailleurs dans le depot.
        "frida/hooks/data/ability-names.ts", "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le foyer `entities_from_state` est consomme par TOUTES les feuilles du package "
              "`behaviours` ; l'etage [3] balaye `ABILITY_CLASSES` en entier et l'etage [6] fait un "
              "balayage statique de `engine/runner/abilities/**`. `build: False` : rien n'est fige "
              "ici depuis le binaire -- les valeurs [4] viennent d'une CONFRONTATION LIVE, et les "
              "ordinaux d'ability sont deja gardes par `probe_313`.",
}

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import hexgeo                                                              # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.selectors.accessors import Target                     # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

FRAG_BOMB = int(ActiveAbilityType.FragBomb)                 # 1017
VALKYRIE = int(ActiveAbilityType.ValkyrieStrike)            # 1018
BASILISK = int(ActiveAbilityType.BasiliskBarrage)           # 1026
GROT_TANK = int(ActiveAbilityType.GrotTank)                 # 1057
VALK_EFFECT = 1022                                          # EffectType.ValkyrieStrike_Effect

TITANHAMMER = int(ActiveAbilityType.TitanhammerSquad)       # 1231
NOVA_SHIELD = int(ActiveAbilityType.NovaShield)             # 1194

#: Le RAYON EFFECTIF, mesure : les abilities qui portent `TargetIsTile` ET dont l'arbre EVALUE le
#: noeud `Target()` quand `target_id` designe une tuile. Toute entree neuve doit etre CONFRONTEE
#: (cf. l'en-tete [3]) avant d'etre ajoutee ici.
#:
#: `1231 TitanhammerSquad` (#448-r2d-r2) est CONFRONTEE, mais pas par `probe_287r12_confront_live.py`
#: (dont les trois volets sont cables en dur sur 1017/1018/1026) : par
#: `probe_448r2dr2_titanhammer_active.py`, qui compare port et natif TERME A TERME sur trois couples
#: et dont l'assertion porte precisement sur l'ENTITE qui recoit le `1571` -- `tiles_1571` est lu
#: des deux cotes par un balayage des effets de TUILE, ecrit independamment du port. Sa
#: contre-epreuve `--mutate 5` (`tileonunit`) fait viser l'UNITE au lieu de la tuile et rougit :
#: `tiles_1571 : port=[] natif=[(0, 2)]` + `astarLysander effets : port=[1571, 1572, 1573]
#: natif=[1572, 1573]`. C'est exactement le regime que ce rayon garde.
#:
#: `1194 NovaShield` est entree au registre avec #895 et A ETE CONFRONTEE -- son inscription ICI
#: avait seulement ete OUBLIEE, ce qui laissait ce cliquet ROUGE sur `origin/master` (mesure : le
#: meme echec, `Extra items: 1194`, sur un worktree detache a `e702b37e` SANS aucun commit de
#: #448-r2d-r2). Le meme gisement, donc, que celui que 1231 vient d'alimenter : une entree neuve
#: TILE-TARGET qui ne met pas ce rayon a jour. La preuve pour 1194 est l'etage [2] de
#: `probe_895_nova_boss_riptide.py` (ZONE MARQUEE, tuiles portant `1415` port vs natif) : son
#: selecteur EST `GetMarkedTiles = Filter(Target@+0x60 + AdjacentTiles(Target@+0x60), NOT
#: IsTrenchTile(...))`, soit exactement une lecture du role `Target()` en regime TUILE, et le probe
#: assertionne son propre pouvoir discriminant (`marked_avec != marked_sans`).
RAYON_CONFRONTE = {FRAG_BOMB, VALKYRIE, GROT_TANK, TITANHAMMER, NOVA_SHIELD}

COLS = ROWS = 9
POS_CASTER = (4, 1)
POS_CIBLE = (4, 4)
U_CASTER, U_CIBLE, U_ADJ1, U_ADJ2, U_ALLIE = 9001, 9002, 9003, 9004, 9005
SEED_MT = 20260807


def _tid(col: int, row: int) -> int:
    """Ids de tuile VOLONTAIREMENT disjoints des ids d'unite (9001+) : c'est ce qui rend l'etage [5]
    lisible -- un substrat ou les deux espaces collisionnent ne montrerait aucun ordre."""
    return col * 100 + row + 1


def _board() -> Board:
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _substrat(unites, board):
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": p[0], "row": p[1]}, "effects": []}
        for (uid, vid, team, p) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 200000, "hpMax": 200000} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _p) in unites]}
    st = load_state(dv, ob, snap, board=board)
    rng = IntBasedMersenneTwister()
    rng.init_genrand(SEED_MT)
    st.rng = rng
    return st


def _montage(porteur: str, board):
    """Cible ENNEMIE au centre, deux ennemis et un allie sur des tuiles ADJACENTES (voisinage NATIF,
    jamais suppose) -- la geometrie qu'exige un volet splash non vide."""
    voisins = [board.coord(t) for t in board.neighbours_native(_tid(*POS_CIBLE))]
    assert len(voisins) >= 3
    return _substrat([(U_CASTER, porteur, 1, POS_CASTER),
                      (U_CIBLE, "necroWarden", 2, POS_CIBLE),
                      (U_ADJ1, "necroDestroyer", 2, voisins[0]),
                      (U_ADJ2, "orksNob", 2, voisins[1]),
                      (U_ALLIE, "astraCreed", 1, voisins[2])], board)


# ---------------------------------------------------------------- [1] et [2] le foyer materialise

def test_le_foyer_materialise_la_cible_TUILE():
    board = _board()
    st = _montage("astraBullgryn", board)
    tuile = _tid(*POS_CIBLE)
    ents = entities_from_state(st, U_CASTER, tuile)
    assert ents.target is not None, (
        "role `target` nul pour une entite-TUILE : toute feuille qui le lit redevient un no-op "
        "SILENCIEUX (c'est le gisement de #287-r12)")
    assert ents.target["id"] == tuile
    assert ents.target["pos"] == {"col": POS_CIBLE[0], "row": POS_CIBLE[1]}


def test_la_forme_du_dict_n_INVENTE_rien():
    board = _board()
    st = _montage("astraBullgryn", board)
    t = entities_from_state(st, U_CASTER, _tid(*POS_CIBLE)).target
    assert t["visualId"] is None, "le rayon de souffle reconnait une entite-tuile a `visualId` nul"
    assert t["_traits"] == set(), "une tuile n'a AUCUN trait -- en inventer ferait passer des gates"
    assert t["team"] is None and t["player"] is None, (
        "une tuile n'a pas de camp : lui en donner un ferait passer des regles de camp que le natif "
        "n'evalue pas sur ce role")
    assert t["alive"] is True and t["hp"] is None


def test_l_elargissement_est_INERTE_sur_une_cible_UNITE_et_sur_un_id_INCONNU():
    """C'est ce qui le rend sans risque pour les autres entrees du registre : la boucle sur
    `state.entities` sert le role AVANT toute materialisation, et un id qui n'est ni une unite ni
    une tuile ne fabrique RIEN (substrat non mesure)."""
    board = _board()
    st = _montage("astraBullgryn", board)
    u = entities_from_state(st, U_CASTER, U_CIBLE).target
    assert u is not None and u["id"] == U_CIBLE and u["visualId"] == "necroWarden"
    assert entities_from_state(st, U_CASTER, 999999).target is None
    assert entities_from_state(st, U_CASTER, None).target is None


# ---------------------------------------------------------------- [3] le rayon effectif

def _evalue_target_en_regime_tuile(aid, cls, board, tuile) -> bool:
    """L'arbre de `aid` LIT-il l'entite-tuile materialisee ? Le critere porte sur la VALEUR rendue
    (l'entite-tuile de CE cast), pas sur « `Target()` evalue » : ce dernier compte aussi les
    sous-contextes (l'attaque d'un summon a l'apparition, cf. `1096 MasterOfTheTutelaries`, qui
    n'appelle pourtant `entities_from_state` qu'avec le CASTER)."""
    st = _substrat([(U_CASTER, "astraBullgryn", 1, POS_CASTER),
                    (U_CIBLE, "necroWarden", 2, POS_CIBLE)], board)
    vus = []
    orig = Target.select

    def _spy(self, ctx, _o=orig, _v=vus):
        v = _o(self, ctx)
        _v.append(v)
        return v

    Target.select = _spy
    try:
        cls().execute_behaviour(st, U_CASTER, tuile)
    except Exception:                                                   # noqa: BLE001
        return False                       # montage generique inadapte -> jamais compte comme inerte
    finally:
        Target.select = orig
    return any(isinstance(v, dict) and v.get("id") == tuile and v.get("visualId") is None
               for v in vus)


def test_le_rayon_effectif_est_CELUI_QUI_A_ETE_CONFRONTE():
    """CLIQUET, pas inventaire : une ability TILE-TARGET qui se met a lire le role `target` change
    de comportement et doit avoir ete confrontee au natif avant d'entrer dans `RAYON_CONFRONTE`."""
    board = _board()
    tuile = _tid(*POS_CIBLE)
    tile_target = {aid for aid, cls in ABILITY_CLASSES.items()
                   if getattr(cls, "TARGETING_OPTIONS", None) is not None
                   and int(cls.TARGETING_OPTIONS.rules) & int(TR.TargetIsTile)}
    assert len(tile_target) >= 20, (
        f"seulement {len(tile_target)} abilities TargetIsTile : le critere a perdu son objet")
    mesure = {aid for aid in tile_target
              if _evalue_target_en_regime_tuile(aid, ABILITY_CLASSES[aid], board, tuile)}
    assert mesure == RAYON_CONFRONTE, (
        f"rayon MESURE {sorted(mesure)} != rayon CONFRONTE {sorted(RAYON_CONFRONTE)}. Une entree "
        f"neuve doit etre confrontee au natif (probe_287r12_confront_live.py) AVANT d'etre "
        f"ajoutee ; une sortie signifie qu'une ability a CESSE de lire son role `target`.")


# ---------------------------------------------------------------- [4] les deux confrontees

def test_1017_rend_LE_MEME_resultat_en_regime_TUILE_et_en_regime_UNITE():
    """Le natif ne connait qu'UN regime (il transforme lui-meme la cible en entite-tuile) ; le port
    en a deux, selon l'id que l'appelant lui donne. Les deux doivent produire le MEME cast -- et
    c'est ce que la confrontation live a mesure cote coups (12 coups bit-exacts)."""
    board = _board()
    out_u = ABILITY_CLASSES[FRAG_BOMB]().execute_behaviour(_montage("astraBullgryn", board),
                                                           U_CASTER, U_CIBLE)
    out_t = ABILITY_CLASSES[FRAG_BOMB]().execute_behaviour(_montage("astraBullgryn", board),
                                                           U_CASTER, _tid(*POS_CIBLE))
    assert out_u is not None and out_t is not None
    for cle in ("main_attack", "splash", "order"):
        assert out_u[cle] == out_t[cle], f"1017 diverge sur `{cle}` entre regime unite et tuile"
    assert out_t["main_attack"] is not None, (
        "la VENTILATION du diagnostic doit resoudre la cible principale par le selecteur natif "
        "`Units(Target@0x178, 1, 1)`, pas en comparant les cibles emises a `target_id` (qui est une "
        "TUILE en regime tile-target)")
    assert [s["target"] for s in out_t["splash"]] == [U_ADJ1, U_ADJ2, U_ALLIE]


def test_1018_pose_son_effet_sur_la_TUILE_et_c_est_une_MESURE_LIVE():
    """`AddBondEffect(0x3fe, ..., target@0x178, ...)` : le porteur est `finalTarget`, que
    `TargetingQuery$$GetActualTarget` a resolu en `GetMainTile(target)` -- l'ENTITE-TUILE. MESURE
    LIVE (`MC1_67`, seed 777) : le natif publie l'effet 1022 dans `tileMeta.tiles[].effects` de la
    tuile visee, et `decisionView.units[].effects` reste INCHANGE."""
    board = _board()
    tuile = _tid(*POS_CIBLE)
    st = _montage("astraSmnVoxcaster", board)
    ABILITY_CLASSES[VALKYRIE]().execute_behaviour(st, U_CASTER, tuile)
    porteurs = sorted(int(k) for k, v in st.effects.by_unit.items()
                      if any(int(e.effect_type) == VALK_EFFECT for e in v))
    assert porteurs == [tuile], (
        f"1022 doit etre porte par la TUILE {tuile}, pas par {porteurs} -- le natif le publie sur "
        f"l'entite-tuile (mesure live), et un port qui le pose sur l'occupant diverge")


# ---------------------------------------------------------------- [5] l'ordre natif de GetMainTile

def test_main_tile_id_suit_l_ORDRE_NATIF():
    # Import DIFFERE, et la raison n'est PAS un cycle : `main_tile_id` est le seul symbole de ce
    # fichier qui N'EXISTE PAS dans l'arbre d'AVANT la tranche. Au niveau module, il ferait echouer
    # la COLLECTE sur l'arbre temoin -- et un fichier qui n'est pas collecte ne montre AUCUN de ses
    # autres etages. La contre-epreuve « ce cliquet rougit-il avant le fix ? » exige donc qu'il soit
    # local a son test.
    from engine.runner.abilities.behaviours.context import main_tile_id
    board = _board()
    st = _montage("astraOrdnance", board)
    assert main_tile_id(st, U_CIBLE) == _tid(*POS_CIBLE), "une UNITE rend sa main tile"
    assert main_tile_id(st, _tid(*POS_CIBLE)) == _tid(*POS_CIBLE), "une TUILE rend elle-meme"
    assert main_tile_id(st, 999999) is None and main_tile_id(st, None) is None
    # L'ORDRE : sur un id qui est A LA FOIS une unite et une tuile, le natif rend la main tile de
    # l'UNITE (la branche `IsTile` est son DERNIER repli). Substrat FABRIQUE pour l'exercer -- sans
    # collision, aucun ordre n'est observable.
    collision = _tid(0, 0)
    st2 = _substrat([(collision, "necroWarden", 2, POS_CIBLE)], board)
    assert main_tile_id(st2, collision) == _tid(*POS_CIBLE), (
        "id ambigu : le natif essaie le composant de pied AVANT `IsTile` -- la branche TUILE est un "
        "REPLI, et l'ordre inverse rendrait la tuile elle-meme")


def test_1026_n_est_PAS_MUETTE_en_regime_TUILE():
    """Son arbre n'evalue jamais `Target()` (elle est hors du rayon), mais son collapse imperatif
    resolvait la tuile visee par un `get_entity` : `target_id` de TUILE -> `[]` -> **zero obus**."""
    board = _board()
    tuile = _tid(*POS_CIBLE)
    out_u = ABILITY_CLASSES[BASILISK]().execute_behaviour(_montage("astraOrdnance", board),
                                                          U_CASTER, U_CIBLE)
    out_t = ABILITY_CLASSES[BASILISK]().execute_behaviour(_montage("astraOrdnance", board),
                                                          U_CASTER, tuile)
    assert out_t["tiles"], "1026 rend zero tuile d'impact en regime TUILE : le cast est MUET"
    assert out_u["tiles"] == out_t["tiles"], "les deux regimes doivent tirer les MEMES tuiles"
    assert out_u["attacks"] == out_t["attacks"]


# ---------------------------------------------------------------- [6] le foyer est UNIQUE

def test_AUCUNE_copie_du_dict_tuile_minimal_ne_repousse():
    """La parade a existe en TROIS exemplaires avant d'etre absorbee par le foyer. Un balayage
    STATIQUE : hors `behaviours/context.py`, aucun module d'`engine/` ne doit construire un dict
    litteral portant a la fois `_traits` et `visualId` -- la signature de ce dict-la."""
    racine = Path(__file__).resolve().parents[3] / "engine"
    foyer = racine / "runner" / "abilities" / "behaviours" / "context.py"
    coupables = []
    for f in sorted(racine.rglob("*.py")):
        if f == foyer:
            continue
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:                                             # pragma: no cover
            continue
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Dict):
                continue
            cles = {k.value for k in n.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if {"_traits", "visualId"} <= cles:
                coupables.append(f"{f.relative_to(racine)}:{n.lineno}")
    assert not coupables, (
        f"copie(s) du dict-tuile minimal hors du foyer : {coupables}. Ce dict se fabrique dans "
        f"`behaviours/context.py::_tile_entity` et NULLE PART ailleurs -- trois copies ont deja "
        f"existe, et elles se recreent par imitation.")
