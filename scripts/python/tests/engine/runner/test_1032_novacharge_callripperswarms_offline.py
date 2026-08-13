"""#1032 -- GARDE des deux no-op silencieux fermes : `1052 CallRipperSwarms` et `1193 NovaCharge`.

Ce fichier ne re-decrit pas les deux arbres (leurs docstrings le font, avec le decompile) : il
garde les QUATRE choses qu'un port de ce genre perd en silence.

  1. Les deux ids sont au registre COMBAT et portent leurs DEUX donnees obligatoires -- le
     `TARGETING_OPTIONS` a sa VALEUR EXACTE (les masques `0x8004` et `0x2000000042` LUS au
     decompile, pas seulement « non None ») et l'`ABILITY_ATTACK_TYPE` a `Others`.
  2. Le cast fait ce que le natif fait ET RIEN DE PLUS : des effets poses, ZERO degat, ZERO spawn.
     C'est le coeur du sujet -- l'audit classait `1193` en `DAMAGE(Particle)` d'apres le kit, et
     un port qui aurait invente le degat au cast serait passe pour vert partout ailleurs.
  3. Les QUATRE reparations de noeuds PARTAGES faites par la meme tranche -- `direction_to` qui
     NORMALISE, `Enemies` qui resout `GetUnitOrMachine`, `Tiles`/`Unique` en domaine TUILE. Chacune
     est gardee par une propriete que l'ANCIEN comportement VIOLAIT, jamais par un simple appel.
  4. Le gate dynamique de `1193` (le bit `TargetMatchesDynamicRule` est POSE, donc il MORD) et son
     accord avec `direction_to` : l'ensemble des tuiles qu'il accepte est EXACTEMENT celui sur
     lequel la direction normalise.

CE QUI N'EST PAS COUVERT ICI, et c'est dit : la face DECISION des deux abilities (residu
`#1032-r1`, inscrit au registre de dette de `probe_1021_face_decision_au_registre`), la PHASE 2
(les triggered `1324 NovaCharge_Attack` et `1099 CallRipperSwarms_Spawn`), et la confrontation
LIVE sur les deux boss npc.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

#: Ce que ce fichier LIT -- s'il bouge, la garde doit se rejouer. Meme contrat que les cliquets de
#: la banque (`declencheur_cliquet.py`). Volontairement LARGE : les quatre noeuds partages repares
#: sont lus par tout l'arbre DSL, donc un declencheur reduit aux deux modules d'ability serait un
#: FAUX VERT (le vice que `probe_486r15` nomme).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/tau.py",
        "scripts/python/engine/runner/abilities/tyranids.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/hexgeo.py",
    ),
    "raison": ("garde le port COMBAT de 1052/1193 ET les quatre noeuds partages que la meme "
               "tranche a repares (direction_to, Enemies, Tiles, Unique)"),
}

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.formulas import AVERAGE_DISTANCE_EMPTY                # noqa: E402
from engine.entities.selectors.geometry import direction_to                # noqa: E402
from engine.runner.abilities.attack_type import (AbilityAttackType,        # noqa: E402
                                                 ABILITY_ATTACK_TYPE)
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402

import hexgeo                                                              # noqa: E402


# ================================================================================================
# ETAGE 1 -- le registre : les deux ids, leurs DEUX donnees obligatoires, aux VALEURS lues
# ================================================================================================

#: Les masques `TargetingOptions+0x28` LUS au decompile. `1052` : preset statique
#: `<TargetingOptions statics>+0x280` (le MEME qu'`ExemplarOfTheMontka`), `+0x28 = 0x8004`.
#: `1193` : forme FLAGS DIRECTS, `mov rax, 0x2000000042` recopie sur la pile avant le ctor.
MASQUES = {
    int(ActiveAbilityType.CallRipperSwarms): 0x8004,
    int(ActiveAbilityType.NovaCharge): 0x2000000042,
}


def test_etage1_les_deux_ids_au_registre_avec_leurs_deux_donnees():
    for aid, masque in MASQUES.items():
        klass = ABILITY_CLASSES.get(aid)
        assert klass is not None, (
            "l'ability %d n'est PAS dans ABILITY_CLASSES -- c'est le no-op SILENCIEUX que #1032 "
            "ferme : ported:False, 0 degat, 0 effet, AUCUNE erreur" % aid)
        opts = getattr(klass, "TARGETING_OPTIONS", None)
        assert opts is not None, (
            "%s entre au registre SANS TARGETING_OPTIONS : `get_invalid_target_reason` rend 0 "
            "immediatement, donc AUCUN gate -- degradation PERMISSIVE et muette" % klass.__name__)
        assert int(opts.rules) == masque, (
            "masque de %s : %#x attendu (LU au decompile), %#x pose"
            % (klass.__name__, masque, int(opts.rules)))
        assert ABILITY_ATTACK_TYPE.get(ActiveAbilityType(aid)) == AbilityAttackType.Others, (
            "le 3e argument d'`AActiveAbility..ctor` vaut 2 = Others pour %d -- il se TRANSCRIT, "
            "il ne se deduit ni du nom ni du damageProfile du kit" % aid)


def test_etage1_masques_decomposes_sans_bit_residuel():
    """Chaque masque se decompose ENTIEREMENT en membres nommes : un bit qui resterait serait une
    regle NON LUE, donc un gate absent que personne ne verrait."""
    attendu = {
        int(ActiveAbilityType.CallRipperSwarms):
            TR.CasterMatchesDynamicRule | TR.CasterIsPossibleTarget,
        int(ActiveAbilityType.NovaCharge):
            TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.CasterHas7Tiles,
    }
    for aid, bits in attendu.items():
        assert int(bits) == MASQUES[aid], (
            "la decomposition nommee de %d ne redonne pas le masque lu (%#x vs %#x) -- un bit "
            "manque ou est en trop" % (aid, int(bits), MASQUES[aid]))


# ================================================================================================
# ETAGE 2 -- `direction_to` NORMALISE (la reparation la plus load-bearing de la tranche)
# ================================================================================================

def test_etage2_direction_to_normalise_hors_adjacence():
    """MIRROR d'`IdunBattle.Utils.Hex.AxialCoordinate$$DirectionTo`. L'ANCIEN port rendait `None`
    des que les deux tuiles n'etaient pas ADJACENTES (`_CUBE_DIRECTIONS.index(delta)`), ce qui
    aurait rendu `NovaChargeAbility$$GetLineTiles` VIDE -- le centre d'un caster a sept tuiles est
    a distance 2 de sa cible. On garde donc le regime NON adjacent, celui que l'ancien violait."""
    origine = (5, 5)
    for d in range(6):
        pas1 = hexgeo.from_cube(*_cube_plus(origine, d, 1))
        assert direction_to(origine, pas1) == d, (
            "pas UNITAIRE dans la direction %d : le regime deja couvert avant #1032 doit etre "
            "INCHANGE" % d)
        for k in (2, 3, 5):
            loin = hexgeo.from_cube(*_cube_plus(origine, d, k))
            assert direction_to(origine, loin) == d, (
                "distance %d dans la direction %d : le natif NORMALISE, il ne se limite pas a "
                "l'adjacence -- c'est ce que l'ancien port rendait `None`" % (k, d))


def test_etage2_direction_to_vide_sur_une_diagonale():
    """L'AUTRE face de la meme lecture, et elle est CONTRE-INTUITIVE donc gardee : quand aucune
    composante cube n'est STRICTEMENT la plus petite (ex. delta `(2,-1,-1)`), le natif n'annule
    rien, les trois signes survivent, `CubeDirections$$EdgeToNeighbor` ne reconnait pas le code et
    rend un `Nullable` VIDE. Un port qui « arrondirait au plus proche » fabriquerait une direction
    la ou le natif abandonne."""
    origine = (5, 5)
    x, _y, z = hexgeo.to_cube(origine[0], origine[1])
    diag = hexgeo.from_cube(x + 2, z - 1)          # cube delta (2,-1,-1)
    assert direction_to(origine, diag) is None, (
        "delta cube (2,-1,-1) : aucune composante n'est strictement la plus petite -> le natif "
        "rend VIDE. Rendre une direction ici ferait viser une ligne que le jeu ne trace pas.")
    assert direction_to(origine, origine) is None, (
        "a == b -> `len == 0` : le natif diviserait par zero ; le port DIT qu'il ne resout pas")


def _cube_plus(pos, direction, k):
    """`pos` avance de `k` pas dans la direction hex `direction` -- en cube, pour ne dependre
    d'aucune convention de parite."""
    from engine.entities.selectors.geometry import _CUBE_DIRECTIONS
    dx, dz = _CUBE_DIRECTIONS[direction]
    x, _y, z = hexgeo.to_cube(int(pos[0]), int(pos[1]))
    return (x + dx * k, z + dz * k)


# ================================================================================================
# ETAGE 3 -- les noeuds de domaine TUILE (`Enemies` / `Tiles` / `Unique`) et `AverageDistance`
# ================================================================================================

def test_etage3_enemies_resout_la_tuile_en_son_occupant():
    """`IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` applique
    `UnitExtensions$$GetUnitOrMachine` a CHAQUE element puis ajoute l'ENTITE SOURCE. Sur un domaine
    TUILE, le noeud rend donc les TUILES a occupant ennemi -- l'ancien port rendait `[]`, ce qui
    vidait silencieusement deux des trois strates de `GetAdditionalMarkedTiles`."""
    from engine.entities.selectors.units import Enemies
    from engine.entities.selectors.geometry import Nothing
    ctx = _ctx_deux_equipes()
    tuiles = _Fixe([ctx.board.id_at(1, 1), ctx.board.id_at(2, 2), ctx.board.id_at(3, 3)])
    out = Enemies(tuiles).evaluate(ctx)
    assert out == [ctx.board.id_at(2, 2)], (
        "seule la tuile (2,2) porte un ennemi du caster -- rendu %r" % (out,))
    assert Nothing is not None       # le module de geometrie est bien celui qu'on croit


def test_etage3_tiles_et_unique_en_domaine_tuile():
    """`Tiles` = `GetMainTile` PAR ENTITE, et c'est l'IDENTITE sur une tuile ; `Unique` = LINQ
    `Distinct` sur l'identite d'entite. Les deux levaient ou vidaient sur des ids de tuile."""
    from engine.entities.selectors.units import Tiles, Unique
    ctx = _ctx_deux_equipes()
    t11, t22 = ctx.board.id_at(1, 1), ctx.board.id_at(2, 2)
    assert Tiles(_Fixe([t11, t22]), as_ids=True).evaluate(ctx) == [t11, t22]
    assert Unique(_Fixe([t11, t22, t11])).evaluate(ctx) == [t11, t22]


def test_etage3_average_distance_defaut_et_division_entiere():
    """`BattleQuery$$GetAverageDistance` : division ENTIERE, et `defaultValue` = **10000** quand
    aucune paire n'est mesurable (LU a l'immediat du call de slot 112). Ni 0 ni `int.MaxValue` --
    les deux feraient basculer le tri de `CallRipperSwarms` du mauvais cote."""
    from engine.entities.formulas import AverageDistance
    ctx = _ctx_deux_equipes()
    vide = AverageDistance(_Fixe([ctx.board.id_at(0, 0)]), _Fixe([]))
    assert vide.evaluate(ctx) == AVERAGE_DISTANCE_EMPTY == 10000
    # (0,0) est a distance 2 de (1,1) et a distance 4 de (3,3) -> moyenne ENTIERE de 2 et 4
    deux = AverageDistance(_Fixe([ctx.board.id_at(0, 0)]),
                           _Fixe([ctx.board.id_at(1, 1), ctx.board.id_at(2, 2)]))
    d1 = hexgeo.distance((0, 0), (1, 1))
    d2 = hexgeo.distance((0, 0), (2, 2))
    assert deux.evaluate(ctx) == (d1 + d2) // 2


# ================================================================================================
# ETAGE 4 -- le cast POSE des effets et NE FRAPPE PAS
# ================================================================================================

EFFETS_ATTENDUS = {
    int(ActiveAbilityType.CallRipperSwarms): {int(EffectType.CallRipperSwarms_PendingSummon)},
    int(ActiveAbilityType.NovaCharge): {int(EffectType.NovaCharge_PendingAttack),
                                        int(EffectType.NovaCharge_PendingTarget_Line),
                                        int(EffectType.NovaCharge_PendingTarget_Single)},
}


def test_etage4_aucun_noeud_d_attaque_ni_de_spawn_dans_les_deux_arbres():
    """L'audit classe `1193` en `DAMAGE(Particle)` d'apres le `damageProfile` du KIT, et `1052` en
    `SUMMON`. Les deux `ExecuteBehaviour` LUS ne portent NI `AttackWith*` NI `Spawn` : le degat et
    le spawn appartiennent aux TRIGGERED de phase 2. On garde l'ABSENCE, parce que c'est
    exactement l'erreur qu'un brief « porte cette attaque » induit."""
    from engine.runner.abilities.tau import nova_charge_tree
    from engine.runner.abilities.tyranids import call_ripper_swarms_tree
    interdits = ("AttackWithAttackDamage", "Spawn", "SpawnSummon", "SpawnReplica",
                 "ChainLeftOverHitsAttackDamage", "Kill")
    for nom, arbre in (("NovaCharge", nova_charge_tree()),
                       ("CallRipperSwarms", call_ripper_swarms_tree())):
        vus = _noms_de_noeuds(arbre)
        assert vus, "l'arbre de %s est vide -- la garde ne prouverait rien" % nom
        for interdit in interdits:
            assert interdit not in vus, (
                "l'arbre de %s porte un noeud %r : le cast ne frappe PAS et ne spawne PAS, "
                "noeuds vus = %s" % (nom, interdit, sorted(vus)))
        assert "AddBondEffect" in vus, (
            "%s pose un effet-BOND (`AddBondEffect`) -- noeuds vus = %s" % (nom, sorted(vus)))


def _noms_de_noeuds(n, vus=None):
    """Parcours de l'arbre par ses CHAMPS -- `__dict__` ET `__slots__` : les feuilles a effet
    declarent `__slots__` (donc `__dict__` est VIDE), et un parcours qui les oublierait rendrait
    `{'Seq'}` sur n'importe quel arbre, c'est-a-dire un VERT qui ne prouve rien."""
    vus = set() if vus is None else vus
    vus.add(type(n).__name__)
    champs = list(getattr(n, "__dict__", {}).values())
    for klass in type(n).__mro__:
        for nom in getattr(klass, "__slots__", ()):
            if hasattr(n, nom):
                champs.append(getattr(n, nom))
    for v in champs:
        if isinstance(v, (str, bytes, int, float, bool, type(None))):
            continue
        if isinstance(v, (list, tuple, set)):
            for x in v:
                if not isinstance(x, (str, bytes, int, float, bool, type(None))):
                    _noms_de_noeuds(x, vus)
        else:
            _noms_de_noeuds(v, vus)
    return vus


def test_etage4_les_effets_poses_sont_ceux_du_decompile():
    """Les ids d'effet sont ceux que le decompile passe a `AddEffect`/`AddBondEffect` -- ce sont
    eux que la PHASE 2 relit (`EntitiesWithAnyEffect(AllTiles, 0x584)` de
    `NovaCharge_AttackAbility$$CreateBehaviour`). Un id faux casserait la chaine EN SILENCE."""
    from engine.runner.abilities import tau, tyranids
    assert {tau.NOVA_CHARGE_PENDING_ATTACK, tau.NOVA_CHARGE_PENDING_TARGET_LINE,
            tau.NOVA_CHARGE_PENDING_TARGET_SINGLE} == \
        EFFETS_ATTENDUS[int(ActiveAbilityType.NovaCharge)]
    assert {tyranids.CALL_RIPPER_SWARMS_PENDING_SUMMON} == \
        EFFETS_ATTENDUS[int(ActiveAbilityType.CallRipperSwarms)]
    assert tau.NOVA_CHARGE_PENDING_ATTACK == 0x583
    assert tau.NOVA_CHARGE_PENDING_TARGET_LINE == 0x584
    assert tau.NOVA_CHARGE_PENDING_TARGET_SINGLE == 0x585
    assert tyranids.CALL_RIPPER_SWARMS_PENDING_SUMMON == 0x446


# ================================================================================================
# ETAGE 5 -- le gate dynamique de 1193, et son ACCORD avec `direction_to`
# ================================================================================================

def test_etage5_gate_dynamique_ne_laisse_que_les_tuiles_alignees():
    """`...NovaChargeAbility$$GetDynamicInvalidTargetReason` : la tuile visee doit toucher
    EXACTEMENT UNE tuile du caster. Sur une empreinte hexagonale de 7 tuiles, cela ne laisse que
    les SIX tuiles du ring 2 ALIGNEES sur un axe du centre -- les six « milieux d'arete » en
    touchent DEUX.

    ⚠ ET LA PROPRIETE QUI COMPTE EST UNE INCLUSION, PAS UNE EGALITE -- c'est ce test qui l'a
    ETABLI, contre l'hypothese initiale de la tranche. `direction_to` normalise sur **10 des 12**
    tuiles du ring 2, pas 6 : seules les deux dont le delta cube a la forme `(+-2, -+1, -+1)`
    rendent vide (aucune composante n'y est strictement la plus petite ET le tie-break ne s'y
    applique pas, `|dx|` valant 2 quand les deux autres valent 1). Les quatre autres diagonales
    -- `(-1,2,-1)`, `(-1,-1,2)`, `(1,-2,1)`, `(1,1,-2)` -- passent par le tie-break `x1,01` sur x
    et rendent bien une arete. L'egalite serait donc FAUSSE ; ce qui est vrai, et suffisant, c'est
    que TOUTE tuile acceptee par le gate porte une direction, donc que `GetLineTiles` n'est JAMAIS
    vide sur une cible legale."""
    from engine.runner.abilities.tau import NovaChargeAbility
    centre = (6, 6)
    feet = [centre] + list(hexgeo.neighbors(centre[0], centre[1]))     # 7 tuiles
    state, board = _state_caster_multi_hex(feet)
    ab = NovaChargeAbility()
    acceptees, avec_direction = set(), set()
    for col in range(board.cols):
        for row in range(board.rows):
            p = (col, row)
            if p in feet:
                continue
            tid = board.id_at(col, row)
            if tid is None:
                continue
            if ab.get_dynamic_invalid_target_reason(state, 1, tid) == 0:
                acceptees.add(p)
            if direction_to(centre, p) is not None and hexgeo.distance(centre, p) == 2:
                avec_direction.add(p)
    assert len(acceptees) == 6, (
        "un caster a SEPT tuiles n'a que six tuiles de depart de ligne legales (les six du ring 2 "
        "alignees sur un axe) -- %d acceptees : %s" % (len(acceptees), sorted(acceptees)))
    assert acceptees <= avec_direction, (
        "une tuile ACCEPTEE par le gate sur laquelle `direction_to` rend VIDE : le port tracerait "
        "une ligne VIDE sur une cible que le natif juge legale. gate=%s sans direction=%s"
        % (sorted(acceptees), sorted(acceptees - avec_direction)))
    assert len(avec_direction) == 10, (
        "le ring 2 porte 12 tuiles, dont 10 normalisent -- si ce compte bouge, la lecture de "
        "`AxialCoordinate$$DirectionTo` a change (mesure : %d)" % len(avec_direction))


def test_etage5_gate_dynamique_refuse_avec_le_code_natif():
    """Le refus rend le `TargetingRule` BRUT `0x2` (`TargetMatchesDynamicRule`), comme tous les
    gates dynamiques du port -- pas un booleen, pas un 1."""
    from engine.runner.abilities.tau import NovaChargeAbility
    centre = (6, 6)
    feet = [centre] + list(hexgeo.neighbors(centre[0], centre[1]))
    state, board = _state_caster_multi_hex(feet)
    ab = NovaChargeAbility()
    # une tuile ADJACENTE a deux tuiles du caster : un « milieu d'arete » du ring 2
    refusee = None
    for col in range(board.cols):
        for row in range(board.rows):
            p = (col, row)
            if p in feet or hexgeo.distance(centre, p) != 2:
                continue
            if direction_to(centre, p) is None:
                refusee = p
                break
        if refusee:
            break
    assert refusee is not None, "le montage ne produit aucune tuile diagonale -- il ne prouve rien"
    assert ab.get_dynamic_invalid_target_reason(state, 1, board.id_at(*refusee)) == \
        int(TR.TargetMatchesDynamicRule)


# ================================================================================================
# MONTAGES NOMMES ET REUTILISABLES
# ================================================================================================

class _Fixe:
    """Selecteur constant : rend la liste donnee, telle quelle. Le vehicule minimal pour exercer
    un noeud sur un domaine choisi sans monter une bataille."""
    def __init__(self, items):
        self.items = items

    def evaluate(self, ctx):
        return list(self.items)


class _Board:
    """Plateau rectangulaire minimal -- la SEULE surface de `ctx.board` que les noeuds de cette
    tranche touchent (`id_at`, `coord`, `by_id`, `walkable`)."""
    def __init__(self, cols=10, rows=10):
        self.cols, self.rows = cols, rows
        self.by_id = {}
        self._pos = {}
        for c in range(cols):
            for r in range(rows):
                tid = 1000 + c * rows + r
                self.by_id[tid] = (c, r)
                self._pos[(c, r)] = tid

    def id_at(self, col, row):
        return self._pos.get((int(col), int(row)))

    def coord(self, tid):
        return self.by_id[tid]

    def walkable(self, tid):
        return tid in self.by_id

    def elevation(self, tid):
        return 0


class _Ctx:
    """Contexte DSL minimal : ce que lisent `Enemies`, `Tiles`, `Unique`, `AverageDistance`."""
    def __init__(self, board, units, caster):
        self.board, self.units, self.caster = board, units, caster
        self.target = None
        self.subject = None
        self.active_target = None


def _ctx_deux_equipes():
    """Un caster d'equipe 0 en (0,0), un ALLIE en (1,1), un ENNEMI en (2,2), rien en (3,3).
    Non-degenere PAR CONSTRUCTION : les trois tuiles interrogees ont trois statuts DIFFERENTS,
    donc un noeud qui rendrait tout ou rien ne peut pas passer."""
    board = _Board()
    caster = _u(1, 0, (0, 0))
    allie = _u(2, 0, (1, 1))
    ennemi = _u(3, 1, (2, 2))
    return _Ctx(board, [caster, allie, ennemi], caster)


def _u(uid, team, pos):
    """Dict d'unite au format que LISENT les noeuds (`_pos` -> `u["pos"]["col"/"row"]`,
    `_feet` -> `u["feet"]` sinon la main tile). Ecrire `col`/`row` a plat rendrait `_pos` NUL et
    tous les noeuds geometriques vides -- un montage qui ne prouve rien."""
    return {"id": uid, "team": team, "alive": True, "hp": 100,
            "pos": {"col": pos[0], "row": pos[1]}, "feet": [pos]}


class _UnitComp:
    """La seule lecture que fait `components.get_unit_feet` : `UnitComponent.feet` (liste de
    positions), materialise pour une unite MULTI-HEX."""
    def __init__(self, feet):
        self.feet = list(feet)


class _Entity:
    """Entite ECS minimale : `get_component(UnitComponent)` seul. Le gate dynamique de `1193` ne
    lit rien d'autre du caster."""
    def __init__(self, feet):
        self._uc = _UnitComp(feet)

    def get_component(self, klass):
        from engine.runner.components import UnitComponent
        return self._uc if klass is UnitComponent else None


class _State:
    def __init__(self, board, entities):
        self.board, self._e = board, entities

    def get_entity(self, eid):
        return self._e.get(eid)


def _state_caster_multi_hex(feet):
    """Un `State` dont l'entite 1 occupe l'empreinte `feet` -- le montage du gate dynamique de
    `1193`, qui lit `get_unit_feet(caster)` et `board`. `get_unit_feet` accepte un objet portant
    `feet` ; on ne monte donc pas de composant ECS pour une lecture de geometrie."""
    board = _Board(14, 14)
    return _State(board, {1: _Entity(feet)}), board


if __name__ == "__main__":                                    # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
