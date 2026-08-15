"""#590-r6 -- la branche MOBILE de `AttemptedPossessionAbility$$GetPreferredAttackTarget`.

Ce que ce fichier garde, et pourquoi chacun des points est un piege REEL, rencontre pendant la RE :

  1. **LE MIRROR MORD, ET IL FAIT BASCULER UN VERDICT.** Un summon mobile sans cible a portee sans
     bouger rendait `None` (donc AUCUNE contrainte de cible, degradation PERMISSIVE) ; il rend
     desormais la cible preferee. Le test le mesure dans les DEUX sens sur un board REEL.
  2. **LA GARDE `canMove && isSummon` EST BILATERALE.** Le natif ne prend la branche mobile que
     sous ces deux conditions ; sans le trait `Summon`, le verdict d'avant doit etre rendu a
     l'identique -- sinon le port aurait ELARGI le domaine legal de toute unite possedee.
  3. **`casterTiles` TRAVERSE QUATRE ETAGES, ET LE QUATRIEME EST LA REGLE DYNAMIQUE.** C'est le
     point qui a failli faire livrer un mirror INERTE : portee et ligne de vue passaient deja, et
     le delegue `options+0x38` refusait quand meme parce qu'il mesurait l'adjacence depuis la tuile
     REELLE. Le site d'invocation natif passe pourtant
     `d.Invoke(caster, casterTiles, cibleResolue, targetTiles)`.
  4. **LE THREADING EST VALUE-PRESERVANT PAR SIGNATURE.** `caster_tiles=None` doit rendre, sur
     CHAQUE etage, exactement ce que rendait le port d'avant ; et les regles dynamiques qui ne
     declarent pas le parametre ne doivent RIEN recevoir (un appel a l'aveugle leverait
     `TypeError` sur les ~35 porteurs du registre).
  5. **`GetValidTargetsInSteps` EST UNE UNION, PAS UN REMPLACEMENT.** L'iterateur natif accumule
     par `ValidTargets$$Merge` sur un `OrderedSet` : premiere apparition d'abord, doublons ignores,
     et la position COURANTE fait partie des positions interrogees (le natif l'AJOUTE
     explicitement). Un mirror qui ne garderait que la meilleure position perdrait des cibles.

Aucune valeur de gameplay n'est ecrite en dur : les positions sont derivees du board VERSIONNE et
les verdicts sont des BASCULES relatives, pas des scalaires. ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier importe `load_state` (donc tout le substrat runner),
    # le registre d'abilities via `attempted_possession`, et le foyer `targeting`. Declarer etroit
    # produirait un FAUX VERT. Les DEUX formes de glob sont necessaires (`**/` exige un SEGMENT).
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/boards/global/MC1_67.json"),
    # `build: False` -- aucune valeur n'est figee depuis le binaire. Ce qui est fige, ce sont les
    # STRUCTURES lues au decompile (les quatre etages consommateurs de `casterTiles`).
    "build": False,
    # `toujours: True` : offline, aucun runner, ~3 s.
    "toujours": True,
    "raison": "Branche MOBILE de GetPreferredAttackTarget (#590-r6) : la bascule du verdict sur un "
              "board reel, la garde bilaterale canMove/isSummon, le threading de `casterTiles` a "
              "travers les QUATRE etages consommateurs (dont la regle dynamique, le seul qui "
              "faisait la difference), et la value-preservation du regime `caster_tiles=None`.",
}

import json
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from board import _effective_elevation                                           # noqa: E402
from engine.entities.pathfinding.board import Board                              # noqa: E402
from engine.runner.snapshot import load_state                                    # noqa: E402
import engine.runner.abilities.targeting as T                                    # noqa: E402
from engine.runner.abilities.loki import attempted_possession as AP              # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR           # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                          # noqa: E402

#: `MC1_67` -- board VERSIONNE, 63 tuiles, CINQ niveaux d'elevation. Un board PLAT serait vert pour
#: la mauvaise raison : ici les portes d'elevation (`CanMeleeAttackOverElevationDifference`,
#: `AreTilesAdjacent`) mordent sur des coordonnees reelles.
BOARD_ID = "MC1_67"

#: L'ordinal `UnitTrait.Summon`, tel que le canal `combatSnapshot.units[].traits` le publie -- le
#: NOM y serait refuse par `trait_names_from_ids`.
SUMMON = int(UnitTrait.Summon)


def _board(board_id: str = BOARD_ID, pool: str = "global") -> Board:
    """`Board` bati depuis une entree VERSIONNEE (`data/boards/<pool>/<id>.json`, forme BC).
    L'elevation passe par `board._effective_elevation` (Trench = champ BC - 1, #195), le MEME calcul
    que ce que le `boardGraph` live baked."""
    p = PYDIR.parents[1] / "data" / "boards" / pool / (board_id + ".json")
    raw = json.loads(p.read_text(encoding="utf-8"))
    b = raw.get("board") or raw.get("Board") or {}
    cells = {}
    for c, col in enumerate(b.get("Tiles") or []):
        for r, t in enumerate((col or {}).get("Tile") or []):
            if t is None or bool(t.get("ForceUnplayable")):
                continue
            cells[(c, r)] = _effective_elevation(t.get("TileId"), t.get("Elevation", 0))
    ids = {q: i + 1 for i, q in enumerate(sorted(cells))}
    tiles = [{"id": ids[q], "col": q[0], "row": q[1], "elevation": e, "walkable": True,
              "isWall": False,
              "neighbours": [ids[n] for n in hexgeo.neighbors(q[0], q[1]) if n in ids]}
             for q, e in cells.items()]
    return Board(tiles)


def _u(uid, team, pos, vid="astarLysander", traits=(), mv=3):
    return {"id": uid, "team": team, "pos": {"col": pos[0], "row": pos[1]}, "vid": vid,
            "traits": list(traits), "mv": mv}


def _state(board, units):
    """`load_state` sur un substrat minimal. `statTypes` est OBLIGATOIRE : sans lui, `seed_unit_stats`
    n'a aucun appariement nom -> `StatType` et `get_stat(MOVEMENT)` rend **0** -- le pathfinding
    serait alors vide et le test passerait pour la mauvaise raison (piege joue)."""
    decision = {"currentPlayer": 1, "units": [
        {"id": u["id"], "visualId": u["vid"], "alive": True, "team": u["team"],
         "owner": u["team"], "pos": u["pos"], "effects": []} for u in units]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000} for u in units]}
    snapshot = {"statTypes": {"movement": 1, "range": 2, "health": 5},
                "units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": u["mv"], "turnsStarted": 1},
                           "healthMax": 1000, "traits": u["traits"], "unitFlags": [],
                           "unitConfig": {"visualId": u["vid"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in units]}
    return load_state(decision, observe, snapshot, board=board, ability_states=False)


# Le montage DISCRIMINANT, derive et non suppose (cf. `test_le_montage_est_bien_DISCRIMINANT`) :
# le caster Thousand Sons en (0,0), le summon ennemi en (2,0) avec 4 de MOVEMENT, et sa proie --
# un ancien allie, donc un ENNEMI une fois le swap d'owner applique -- en (6,0), a distance 4.
CASTER, SUMMON_POS, PROIE = (0, 0), (2, 0), (6, 0)


def _montage(avec_trait_summon: bool = True, mv: int = 4):
    board = _board()
    traits = [SUMMON] if avec_trait_summon else []
    units = [_u(1, 1, CASTER, "thousSorcerer"),
             _u(2, 2, SUMMON_POS, "astarLysander", traits, mv),
             _u(3, 2, PROIE, "astarLysander")]
    return board, _state(board, units)


# ================================================================= 0. LE MONTAGE EST DISCRIMINANT

def test_le_montage_est_bien_DISCRIMINANT():
    """Un test dont le montage ne SEPARE pas les deux branches serait vert pour la mauvaise raison.
    Les trois conditions sont MESUREES ici, pas supposees : la proie est hors de portee sans bouger,
    elle est atteignable en bougeant, et le summon a bien de quoi le faire."""
    board, st = _montage()
    assert hexgeo.distance(SUMMON_POS, PROIE) == 4, "la proie doit etre HORS de portee de melee"
    assert hexgeo.distance((5, 0), PROIE) == 1, "une tuile de mouvement doit etre AU CONTACT"
    from engine.entities.stats import StatType
    from engine.runner.components import StatsComponent
    sc = st.get_entity(2).get_component(StatsComponent)
    assert int(sc.ctx.get_stat(int(StatType.MOVEMENT))) == 4, \
        "MOVEMENT non seede => stop-set VIDE => le test passerait sans rien mesurer"
    assert UnitTrait.Summon.name in (T._unit_traits(st, 2) or ()), "le trait doit etre porte"


# ==================================================== 1. LA BASCULE (piege 1) -- board REEL

def test_la_branche_mobile_fait_BASCULER_le_verdict():
    """`AttemptedPossessionAbility.<>c__DisplayClass5_0$$<GetPreferredAttackTarget>b__0` :

        if (canMove && isSummon)
            res = <IBattleQuery 69 GetAllValidTargetsFromAllPossibleMovementTiles>(unit, ..., 1)
        else
            res = <IBattleQuery 66 GetValidTargets>(unit, GetUnitPosition(unit), ...)

    La branche STATIQUE ne trouve rien (la proie est a 4, l'attaque normale de ce caster est de
    melee) ; la branche MOBILE la trouve. Avant #590-r6 le port rendait `None` -- donc
    `GetAttackCustomUtility` rendait `null`, donc AUCUNE contrainte de cible n'etait posee."""
    board, st = _montage()
    from engine.runner.operations.change_unit_owner import (ChangeUnitOwnerOperation,
                                                            ResetUnitOwnerOperation)
    # Le Func natif est evalue SOUS SIMULATION de l'effet `0x4b9` : les << ennemis >> du possede
    # sont ceux de son NOUVEAU proprietaire. Sans le swap, la proie est son ALLIEE.
    assert ChangeUnitOwnerOperation.execute(st, 2, 1) is True
    try:
        assert T.valid_normal_attack_targets(st, 2) == [], \
            "branche STATIQUE : aucune cible sans bouger -- c'est ce qui rend le test discriminant"
        assert T.all_valid_targets_from_all_possible_movement_tiles(st, 2) == [3], \
            "branche MOBILE : la proie devient atteignable depuis une tuile de mouvement"
    finally:
        ResetUnitOwnerOperation.execute(st, 2)

    assert AP.attempted_possession_preferred_target(st, 1, 2) == 3, \
        "le corps complet doit rendre la proie (il rendait None avant #590-r6)"


def test_la_garde_canMove_ET_isSummon_est_BILATERALE(monkeypatch):
    """`if (canMove && isSummon)` : les DEUX termes. Retirer l'un ou l'autre doit rendre le verdict
    d'avant -- sinon le port aurait elargi le domaine legal de toute unite possedee."""
    _, sans_trait = _montage(avec_trait_summon=False)
    assert AP.attempted_possession_preferred_target(sans_trait, 1, 2) is None, \
        "sans le trait Summon, la branche STATIQUE s'applique -- verdict d'avant, a l'identique"

    _, st = _montage()
    # `canMove` FAUX -> branche statique, meme si le trait est la. On substitue le FOYER
    # (`turnflow._can_move`), par le chemin PLEIN : c'est ce que la forme C du differe rend possible.
    monkeypatch.setattr("engine.runner.operations.turnflow._can_move",
                        lambda state, unit_id: False)
    assert AP.attempted_possession_preferred_target(st, 1, 2) is None, \
        "canMove faux => branche STATIQUE, quel que soit le trait"


def test_le_tri_etat_de_canMove_ne_bascule_que_sur_un_True_MESURE(monkeypatch):
    """`turnflow._can_move` rend `None` quand le substrat n'est pas lisible. Rabattre ce `None` sur
    `True` prendrait la branche la plus PERMISSIVE (plus de cibles) sur une NON-MESURE."""
    _, st = _montage()
    monkeypatch.setattr("engine.runner.operations.turnflow._can_move",
                        lambda state, unit_id: None)
    assert AP.attempted_possession_preferred_target(st, 1, 2) is None


# ============================ 2. `casterTiles` TRAVERSE QUATRE ETAGES (piege 3) -- dont la DYNAMIQUE

def _probe(st, uid):
    return T._NormalAttackTargeting(T.normal_attack_targeting_options(st, uid))


def test_la_REGLE_DYNAMIQUE_lit_casterTiles_et_c_est_elle_qui_tranche():
    """LE PIEGE CENTRAL de la tranche. Le site d'invocation natif est

        rule = options.<+0x38>.Invoke(caster, casterTiles, <cible RESOLUE>, targetTiles);

    -- QUATRE arguments, `casterTiles` en DEUXIEME. La regle de l'attaque normale
    (`ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`) mesure l'ADJACENCE
    `casterTile x targetTiles` pour choisir l'arme ; depuis la tuile REELLE elle refuse, depuis la
    tuile CANDIDATE elle accepte. Sans ce threading, portee et ligne de vue passaient deja et le
    mirror etait livre INERTE (mesure : `[]` sur les 25 positions candidates)."""
    board, st = _montage()
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    ChangeUnitOwnerOperation.execute(st, 2, 1)
    depuis_candidate = [(5, 0)]

    # Les trois AUTRES etages passent DEJA depuis la position candidate : ce n'est donc pas eux qui
    # faisaient la difference.
    opts = T.normal_attack_targeting_options(st, 2)
    assert T.get_range_broken_rule(st, 2, 3, opts, depuis_candidate) == 0
    assert T.get_tiles_obscuring_terrain(st, 2, 3, opts, depuis_candidate) == set()

    # Le QUATRIEME, lui, bascule -- et c'est le verdict complet qui suit.
    assert T.normal_attack_dynamic_invalid_target_reason(st, 2, 3) == int(
        TR.TargetMatchesDynamicRule), "depuis la tuile REELLE, le delegue refuse"
    assert T.normal_attack_dynamic_invalid_target_reason(st, 2, 3, depuis_candidate) == 0, \
        "depuis la tuile CANDIDATE, il accepte -- c'est ce que `casterTiles` porte"

    assert T.get_invalid_target_reason(st, 2, 3, _probe(st, 2), apply_self_cast_switch=False) != 0
    assert T.get_invalid_target_reason(st, 2, 3, _probe(st, 2), apply_self_cast_switch=False,
                                       caster_tiles=depuis_candidate) == 0


def test_les_QUATRE_etages_RECOIVENT_bien_casterTiles(monkeypatch):
    """⚠ CE TEST EXISTE PARCE QUE LA COUVERTURE FONCTIONNELLE EST INCOMPLETE, ET C'EST MESURE :
    muter le site d'appel de la LIGNE DE VUE pour qu'il passe `None` laisse les quinze autres items
    VERTS -- `MC1_67` ne porte, pour les couples de ce montage, **aucune** position candidate ou la
    ligne de vue bascule (balayage des 63 tuiles : 0 bascule). Un montage qui la ferait basculer
    exigerait un caster A DISTANCE, donc un autre type d'attaque normale, donc un autre gisement.

    Plutot que de fabriquer ce montage, on garde la LIGNE : chaque etage est espionne et doit
    RECEVOIR la position interrogee. C'est un cran STRUCTUREL, il ne remplace pas la mesure
    fonctionnelle des trois autres etages -- il la complete la ou elle est aveugle."""
    _, st = _montage()
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    # SANS le swap, la cascade sort des `TargetIsEnemy` (le summon et sa proie sont allies) et
    # n'atteint JAMAIS les etages espionnes -- le test serait vert sur un dict vide.
    ChangeUnitOwnerOperation.execute(st, 2, 1)
    probe = _probe(st, 2)
    interrogee = [(5, 0)]
    vus: dict = {}

    def _espion(nom, vrai, rang):
        def _f(*a, **k):
            vus[nom] = a[rang] if len(a) > rang else k.get("caster_tiles")
            return vrai(*a, **k)
        return _f

    for nom, rang in (("get_range_broken_rule", 4), ("get_tiles_obscuring_terrain", 4)):
        monkeypatch.setattr(T, nom, _espion(nom, getattr(T, nom), rang))
    monkeypatch.setattr(T, "_invoque_regle_dynamique",
                        _espion("_invoque_regle_dynamique", T._invoque_regle_dynamique, 4))
    monkeypatch.setattr(T, "caster_tiles_of",
                        _espion("caster_tiles_of", T.caster_tiles_of, 2))

    T.get_invalid_target_reason(st, 2, 3, probe, apply_self_cast_switch=False,
                                caster_tiles=interrogee)
    assert vus.get("get_range_broken_rule") == interrogee, "le volet PORTEE ne recoit pas casterTiles"
    assert vus.get("get_tiles_obscuring_terrain") == interrogee, \
        "la LIGNE DE VUE ne recoit pas casterTiles"
    assert vus.get("_invoque_regle_dynamique") == interrogee, \
        "la REGLE DYNAMIQUE ne recoit pas casterTiles"


def test_TargetIsNotAdjacent_mesure_l_adjacence_depuis_casterTiles():
    """`if ((rules >> 0x20) & 1) { if (<IBattleQuery 0x62>(targetTiles, casterTiles)) -> broken }`
    -- le slot recoit `casterTiles` en SECONDE liste. Le masque de l'attaque normale ne pose PAS ce
    bit, donc les items ci-dessus lui sont aveugles (mesure : muter ce site les laisse tous verts) ;
    on l'exerce ici sur un masque qui ne pose QUE lui (`range=None` desarme le volet portee, qui
    sortirait avant)."""
    _, st = _montage()
    opts = T.TargetingOptions(rules=int(TR.TargetIsNotAdjacent), self_cast=False, range=None,
                              force_melee_target=T.RANGED_BOOL_FALSE)
    probe = T._NormalAttackTargeting(opts)
    assert T.get_invalid_target_reason(st, 2, 3, probe, apply_self_cast_switch=False) == 0, \
        "depuis (2,0) la proie (6,0) n'est PAS adjacente -- aucun refus"
    assert T.get_invalid_target_reason(st, 2, 3, probe, apply_self_cast_switch=False,
                                       caster_tiles=[(5, 0)]) == int(TR.TargetIsNotAdjacent), \
        "depuis (5,0) elle l'est -- le refus doit suivre la position INTERROGEE"


def test_le_clamp_MELEE_se_mesure_depuis_casterTiles():
    """`GetRange` : `if (IsTrue(options.ForceMeleeTarget, caster)
    && attackQuery.<slot 21 ShouldApplyRangedInMelee>(caster, casterTiles, true))
    { v = Min(1, v); onlyAdjacent = true; }`. Le 2e argument du slot est `casterTiles` -- un summon
    qui s'approche entre en melee, et sa portee doit se rabattre. Le masque de l'attaque normale
    porte `force_melee_target = IfRangedCaster` (faux pour ce caster de melee), donc ce site n'est
    jamais atteint par les items ci-dessus : on l'arme explicitement."""
    from dataclasses import replace as _replace
    _, st = _montage()
    base = T.normal_attack_targeting_options(st, 2)
    opts = _replace(base, force_melee_target=T.RANGED_BOOL_TRUE,
                    range=_replace(base.range, only_adjacent=T.RANGED_BOOL_FALSE,
                                   override_range=4))
    # L'ennemi du summon (le caster, id 1, en (0,0)) est a distance 2 de sa position REELLE.
    assert T.should_apply_ranged_in_melee(st, 2, None) is False
    assert T.get_range(st, 2, opts, None).value == 4
    # Depuis (1, 0), il est AU CONTACT : le clamp doit tomber, et forcer `only_adjacent`.
    assert T.should_apply_ranged_in_melee(st, 2, [(1, 0)]) is True
    rr = T.get_range(st, 2, opts, [(1, 0)])
    assert rr.value == 1 and rr.only_adjacent is True

    # ⚠ ET LE CLAMP DOIT REMONTER JUSQU'AU VERDICT : sans cette moitie, muter `get_range_broken_rule`
    # pour qu'elle appelle `get_range(..., None)` laisse tout vert (mesure) -- elle mesure la
    # DISTANCE depuis la bonne position, mais perd le clamp. Cible a 3 de (1,0) : acceptee a portee
    # 4, refusee des que le clamp force l'adjacence.
    board = _board()
    units = [_u(1, 1, CASTER, "thousSorcerer"),
             _u(2, 2, SUMMON_POS, "astarLysander", [SUMMON], 4),
             _u(3, 2, PROIE, "astarLysander"),
             _u(5, 1, (4, 0), "astarLysander")]
    st2 = _state(board, units)
    o2 = _replace(opts, rules=int(TR.TargetIsEnemy))     # ni regle dynamique ni autre gate
    p2 = T._NormalAttackTargeting(o2)
    assert hexgeo.distance((1, 0), (4, 0)) == 3
    assert T.get_range_broken_rule(st2, 2, 5, o2, None) == 0, "portee 4, cible a 2 : acceptee"
    assert T.get_range_broken_rule(st2, 2, 5, o2, [(1, 0)]) == int(TR.TargetIsInRange), \
        "depuis (1,0) le clamp melee force l'adjacence : la cible a 3 doit etre REFUSEE"
    assert T.get_invalid_target_reason(st2, 2, 5, p2, apply_self_cast_switch=False,
                                       caster_tiles=[(1, 0)]) == int(TR.TargetIsInRange)


def _board_plat(elev=None):
    """Board synthetique : `MC1_67` ne fait basculer la LIGNE DE VUE sur AUCUNE de ses 63 tuiles pour
    les couples de ce fichier (balayage). Un relief CHOISI est donc le seul moyen de l'exercer."""
    elev = elev or {}
    n = 9
    cells = {(c, r): int(elev.get((c, r), 0)) for c in range(n) for r in range(n)}
    ids = {q: i + 1 for i, q in enumerate(sorted(cells))}
    tiles = [{"id": ids[q], "col": q[0], "row": q[1], "elevation": e, "walkable": True,
              "isWall": False,
              "neighbours": [ids[x] for x in hexgeo.neighbors(q[0], q[1]) if x in ids]}
             for q, e in cells.items()]
    return Board(tiles)


def test_la_LIGNE_DE_VUE_se_mesure_DEPUIS_casterTiles():
    """⚠ LE CRAN STRUCTUREL CI-DESSUS NE SUFFIT PAS, et c'est mesure : il verifie que la fonction
    RECOIT le parametre, pas qu'elle l'UTILISE -- muter son corps pour qu'il reparte de
    `entity_tiles(caster)` le laissait VERT. Ici on mesure la VALEUR, sur un relief bloquant choisi.

    `GetTilesObscuringTerrain(caster, casterTiles, cible, options)` : le premier argument du slot
    `IMovementQuery 15` EST `casterTiles`. Depuis la position reelle la ligne passe ; depuis la
    candidate elle bute sur le bloc haut. Les DEUX sens sont assertes -- un seul ne prouverait pas
    que le terme mord."""
    board = _board_plat({(c, 4): 5 for c in (2, 3, 4)})
    units = [_u(1, 1, (0, 4), "astarCyrus"), _u(2, 2, (6, 4), "astarLysander")]
    st = _state(board, units)
    opts = T.normal_attack_targeting_options(st, 1)
    assert T.get_tiles_obscuring_terrain(st, 1, 2, opts, None) == set(), \
        "depuis la position REELLE, la ligne passe"
    obstruee = T.get_tiles_obscuring_terrain(st, 1, 2, opts, [(1, 4)])
    assert obstruee, "depuis (1,4) le bloc haut obscurcit -- c'est ce que `casterTiles` porte"
    assert (2, 4) in obstruee


def test_la_clause_TUILE_NULLE_porte_sur_la_position_INTERROGEE():
    """`if ((rules & AllowNullCasterTile) == 0 && (rules & CasterHasNoTile) == 0
    && CollectionExtensions.IsNullOrEmpty(casterTiles)) -> broken(AllowNullCasterTile)`.

    Le predicat porte sur `casterTiles`, PAS sur `GetTiles(caster)` : une position interrogee VIDE
    rompt la regle meme quand l'unite est bien posee sur le plateau. Sans ce test, muter le repli
    pour qu'il reparte toujours de `get_unit_feet` restait vert (mesure)."""
    _, st = _montage()
    probe = _probe(st, 2)
    assert T.get_invalid_caster_reason(st, 2, probe, None) == 0, "l'unite EST sur le plateau"
    assert T.get_invalid_caster_reason(st, 2, probe, []) == int(TR.AllowNullCasterTile), \
        "position interrogee VIDE -> le natif rompt, quelle que soit la position reelle"


def test_le_threading_ne_passe_le_parametre_QU_AUX_porteurs_qui_le_DECLARENT():
    """Les ~35 regles dynamiques du registre gardent le contrat `(state, caster_id, target_id)`.
    Un appel a l'aveugle leverait `TypeError` sur chacune ; le threading teste donc la SIGNATURE,
    comme `PerformAIAbility._accepte_utility_entity` (#590-r4)."""
    vus = []

    class _SansParametre:
        TARGETING_OPTIONS = T.NORMAL_ATTACK_TARGETING_OPTIONS
        ABILITY_ID = None

        def get_dynamic_invalid_target_reason(self, state, caster_id, target_id):
            vus.append("sans")
            return 0

    class _AvecParametre:
        TARGETING_OPTIONS = T.NORMAL_ATTACK_TARGETING_OPTIONS
        ABILITY_ID = None

        def get_dynamic_invalid_target_reason(self, state, caster_id, target_id,
                                              caster_tiles=None):
            vus.append(("avec", caster_tiles))
            return 0

    _, st = _montage()
    assert T._invoque_regle_dynamique(_SansParametre(), st, 1, 3, [(5, 0)]) == 0
    assert T._invoque_regle_dynamique(_AvecParametre(), st, 1, 3, [(5, 0)]) == 0
    assert vus == ["sans", ("avec", [(5, 0)])]

    # `caster_tiles is None` -> personne ne recoit rien, meme un porteur qui declare le parametre.
    vus.clear()
    assert T._invoque_regle_dynamique(_AvecParametre(), st, 1, 3, None) == 0
    assert vus == [("avec", None)]

    # Une signature ILLISIBLE est un refus, jamais une tentative d'appel a quatre arguments.
    assert T._accepte_caster_tiles(len) is False


# ================================================ 3. VALUE-PRESERVATION du regime `None` (piege 4)

@pytest.mark.parametrize("uid", [1, 2, 3])
def test_caster_tiles_None_rend_EXACTEMENT_la_position_reelle(uid):
    """`caster_tiles_of` est le FOYER unique du repli. `None` doit rendre `EntityExtensions$$GetTiles`
    -- si ce n'etait pas le cas, les ~200 appelants historiques changeraient de verdict en silence."""
    _, st = _montage()
    assert T.caster_tiles_of(st, uid, None) == T.entity_tiles(st, uid)
    assert T.caster_tiles_of(st, uid, [(1, 1)]) == [(1, 1)]


def test_les_quatre_etages_sont_INCHANGES_quand_le_parametre_vaut_None():
    """Chaque etage touche par le threading doit rendre, sous `caster_tiles=None`, ce que rend son
    appel a la position reelle explicite. C'est l'invariant qui borne le rayon du changement."""
    _, st = _montage()
    opts = T.normal_attack_targeting_options(st, 2)
    reelle = T.entity_tiles(st, 2)
    probe = _probe(st, 2)
    assert T.get_range(st, 2, opts, None) == T.get_range(st, 2, opts, reelle)
    assert (T.get_range_broken_rule(st, 2, 3, opts, None)
            == T.get_range_broken_rule(st, 2, 3, opts, reelle))
    assert (T.get_tiles_obscuring_terrain(st, 2, 3, opts, None)
            == T.get_tiles_obscuring_terrain(st, 2, 3, opts, reelle))
    assert (T.should_apply_ranged_in_melee(st, 2, None)
            == T.should_apply_ranged_in_melee(st, 2, reelle))
    assert T.get_invalid_caster_reason(st, 2, probe, None) == T.get_invalid_caster_reason(
        st, 2, probe, reelle)
    assert T.valid_normal_attack_targets(st, 2) == T.valid_normal_attack_targets(
        st, 2, caster_tiles=reelle)


def test_CasterHasNotMoved_refuse_une_position_HYPOTHETIQUE():
    """`if (!DidMove(caster) && GetTiles(caster).IsEquivalentTo(casterTiles)) -> ok` : la 2e clause
    REFUSE une position de cast hypothetique. Elle est INERTE sur l'attaque normale (preset `0x4002`,
    pas de bit `0x10`) -- ce test l'exerce donc sur un porteur qui pose le bit, sans quoi l'ecriture
    du mirror ne serait gardee par rien.

    ⚠ LE SUJET EST L'UNITE **1**, PAS LE SUMMON : la clause est prefixee par
    `<IBattleQuery 0x35 IsTurnOfUnit>(caster)` (#287-r11-r1-r1-r2), et le natif SAUTE la clause
    entiere quand ce n'est pas le tour du proprietaire d'ORIGINE. Monter le test sur l'unite 2
    (team 2, `currentPlayer = 1`) le rendait vert pour la mauvaise raison -- piege joue."""
    from dataclasses import replace as _replace
    from engine.runner.components import is_turn_of_unit
    _, st = _montage()
    assert is_turn_of_unit(st, 1) is True, "sans ce prefixe, la clause est SAUTEE et rien n'est teste"
    opts = _replace(T.NORMAL_ATTACK_TARGETING_OPTIONS,
                    rules=int(T.NORMAL_ATTACK_TARGETING_OPTIONS.rules) | int(TR.CasterHasNotMoved))
    probe = T._NormalAttackTargeting(opts)
    reelle = T.entity_tiles(st, 1)
    assert T.get_invalid_caster_reason(st, 1, probe, None) == 0
    assert T.get_invalid_caster_reason(st, 1, probe, reelle) == 0, \
        "la position reelle passee EXPLICITEMENT est equivalente -- pas de faux refus"
    assert T.get_invalid_caster_reason(st, 1, probe, [(5, 0)]) == int(TR.CasterHasNotMoved)


# ============================================== 4. `GetValidTargetsInSteps` EST UNE UNION (piege 5)

def test_get_valid_targets_in_steps_UNIT_et_dedoublonne_dans_l_ordre():
    """`ValidTargets$$Merge` accumule dans un `OrderedSet` : premiere apparition d'abord, doublons
    ignores. Un mirror qui garderait la MEILLEURE position au lieu de l'UNION perdrait des cibles."""
    _, st = _montage()
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    ChangeUnitOwnerOperation.execute(st, 2, 1)
    depuis, sterile = [(5, 0)], T.entity_tiles(st, 2)
    assert T.valid_normal_attack_targets(st, 2, caster_tiles=depuis) == [3]
    assert T.valid_normal_attack_targets(st, 2, caster_tiles=sterile) == [], \
        "la position courante ne donne RIEN : c'est ce qui rend l'union observable"
    # La MEME position deux fois ne doit pas dupliquer.
    assert T.get_valid_targets_in_steps(st, 2, [depuis, depuis]) == [3]
    assert T.get_valid_targets_in_steps(st, 2, []) == []
    # ⚠ LES DEUX ORDRES, ET C'EST CE QUI ATTRAPE LE MUTANT << garder la derniere position >> :
    # avec la seule seconde position, `[depuis, sterile]` rendrait `[]`. Mesure : sans ces deux
    # lignes, un mirror qui ECRASE au lieu d'UNIR laissait les quinze items verts.
    assert T.get_valid_targets_in_steps(st, 2, [sterile, depuis]) == [3]
    assert T.get_valid_targets_in_steps(st, 2, [depuis, sterile]) == [3]

    # UNION SUR DEUX CIBLES DISTINCTES, dans l'ordre de PREMIERE APPARITION (`OrderedSet.Add`).
    # Montage propre : une SECONDE proie (team 2, donc ennemie une fois le swap applique), loin de
    # la premiere. Les deux positions d'interrogation sont DERIVEES, jamais supposees.
    board = _board()
    units = [_u(1, 1, CASTER, "thousSorcerer"),
             _u(2, 2, SUMMON_POS, "astarLysander", [SUMMON], 4),
             _u(3, 2, PROIE, "astarLysander"),
             _u(4, 2, (2, 6), "astarLysander")]
    st2 = _state(board, units)
    ChangeUnitOwnerOperation.execute(st2, 2, 1)
    toutes = [[(c, r)] for c in range(7) for r in range(9)]
    p3 = next(p for p in toutes if T.valid_normal_attack_targets(st2, 2, caster_tiles=p) == [3])
    p4 = next(p for p in toutes if T.valid_normal_attack_targets(st2, 2, caster_tiles=p) == [4])
    assert T.get_valid_targets_in_steps(st2, 2, [p3, p4]) == [3, 4]
    assert T.get_valid_targets_in_steps(st2, 2, [p4, p3]) == [4, 3]


def test_la_position_COURANTE_fait_partie_des_positions_interrogees():
    """`tiles.Add(EntityExtensions.GetUnitPosition(attacker, state))` -- l'iterateur natif l'AJOUTE
    explicitement. Une cible deja a portee sans bouger doit donc rester dans le resultat MOBILE."""
    board = _board()
    units = [_u(1, 1, CASTER, "thousSorcerer"),
             _u(2, 2, SUMMON_POS, "astarLysander", [SUMMON], 0),   # MOVEMENT 0 : aucune tuile
             _u(3, 2, (3, 0), "astarLysander")]                    # ADJACENTE au summon
    st = _state(board, units)
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    ChangeUnitOwnerOperation.execute(st, 2, 1)
    assert T.valid_normal_attack_targets(st, 2) == [3]
    assert T.all_valid_targets_from_all_possible_movement_tiles(st, 2) == [3], \
        "MOVEMENT 0 => seule la position COURANTE est interrogee, et elle DOIT l'etre"


def test_l_AJOUT_EXPLICITE_de_la_position_courante_est_ECRIT_et_non_domine(monkeypatch):
    """⚠ CE TEST EXISTE PARCE QUE LE PRECEDENT EST **DOMINE**, et c'est une MESURE, pas une crainte :
    muter la ligne d'ajout explicite en no-op laisse les treize autres items VERTS. La cause est que
    `MovementQuery$$GetMovablePositionsFor` fait DEJA `movable.AddRange(IterateTiles(unit, state))`
    en interne -- sur une unite a 1 pied les deux se recouvrent, donc aucun montage a un pied ne peut
    separer les deux ecritures.

    Le seul regime ou l'`Add` du natif MORD est le multi-hex, ou `GetMovablePositionsFromTiles`
    recombine les tuiles en positions a N pieds et n'est pas tenu de reproduire l'empreinte exacte.
    Plutot que de monter une unite multi-hex (substrat lourd, et le port n'en a pas de summon), on
    ISOLE la ligne : on substitue l'etage AMONT pour qu'il ne rende PAS l'empreinte courante, et on
    exige que le mirror la remette. C'est exactement ce que fait la ligne native."""
    board = _board()
    units = [_u(1, 1, CASTER, "thousSorcerer"),
             _u(2, 2, SUMMON_POS, "astarLysander", [SUMMON], 0),
             _u(3, 2, (3, 0), "astarLysander")]
    st = _state(board, units)
    from engine.runner.operations.change_unit_owner import ChangeUnitOwnerOperation
    ChangeUnitOwnerOperation.execute(st, 2, 1)

    # CONTRE-EPREUVE DE LA SUBSTITUTION (#feedback_verify_the_mutation_applied) : sans elle, l'etage
    # amont rend BIEN l'empreinte -- donc le stub ci-dessous change reellement quelque chose.
    import engine.services.movement_query as MQ
    avant = MQ.get_movable_positions_for(board, st, 2, [])
    assert [list(p) for p in avant] == [[SUMMON_POS]], \
        "l'etage amont rend l'empreinte courante : c'est CE recouvrement qui domine l'autre test"

    monkeypatch.setattr("engine.services.movement_query.get_movable_positions_for",
                        lambda *a, **k: [])
    assert MQ.get_movable_positions_for(board, st, 2, []) == [], "la substitution doit MORDRE"
    assert T.all_valid_targets_from_all_possible_movement_tiles(st, 2) == [3], \
        "l'etage amont ne rend RIEN : c'est l'AJOUT EXPLICITE qui doit sauver la position courante"


def test_substrat_absent_rend_une_liste_VIDE_sans_rien_inventer():
    """Pas de board, pas de position : le mirror ne fabrique NI cible NI refus."""
    _, st = _montage()
    st.board = None
    assert T.all_valid_targets_from_all_possible_movement_tiles(st, 2) == []
