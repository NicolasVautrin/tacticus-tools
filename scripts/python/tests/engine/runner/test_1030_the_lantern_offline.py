"""`1094 TheLantern` (`deathBossMortarion`) -- la GARDE du port des DEUX phases. #1030.

Ce fichier ne mesure rien : il FIGE ce que la RE a lu, et chaque etage porte sa CONTRE-EPREUVE
(la mutation qui doit le faire rougir). Le decompile est cite dans `runner/abilities/deathguard.py`
(phase 1), `runner/operations/triggers/loki/the_lantern_attack.py` (phase 2) et
`playbook/noncomparable/the_lantern.py` (face DECISION).

Board SYNTHETIQUE et plat : la geometrie de la zone est le sujet, pas le terrain. ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/hexgeo.py",
        # PRIS LARGE, et non feuille a feuille : le cast passe par le visiteur de message, donc par
        # le registre d'abilities, le vocabulaire DSL (selecteurs de tuiles ET d'unites), la pose
        # d'effet, le dispatch de trigger et le modele de degat. Une liste choisie ne pourrait pas
        # montrer le module qu'elle a oublie.
        "scripts/python/engine/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE du port de `1094 TheLantern` : zone, trois poses, attaquant de la "
              "phase 2, relecture de la marque au TIR, et face DECISION. Aucun runner, aucun RPC.",
}

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import hexgeo                                                            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType        # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects_state import EffectsState                   # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.messages import ActiveAbilityMessage                  # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

TL = int(ActiveAbilityType.TheLantern)                        # 1094
PENDING_TARGET = int(EffectType.TheLantern_PendingTarget)     # 1195
PINNED = int(EffectType.Pinned)                               # 1065
PENDING_ATTACK = int(EffectType.TheLantern_PendingAttack)     # 1194
TL_ATTACK = int(TriggeredAbilityType.TheLantern_Attack)       # 1167

#: BOARD 13x13, CASTER AU CENTRE -- et les deux chiffres sont CONTRAINTS, pas confortables
#: (#10023). Le montage d'origine (9x9, caster en (2,4)) est ne AVANT que #895-r2 ne porte le gate
#: `CasterHas7Tiles` et AVANT que #1030-r1 ne porte la regle dynamique ; ni l'un ni l'autre ne
#: pouvait alors le contraindre. Les deux le contraignent maintenant :
#:   * l'empreinte SEPT HEX doit tenir dans le plateau (`_empreinte_7`) ;
#:   * `...TheLanternAbility$$GetDynamicInvalidTargetReason` n'accepte que les SIX tuiles a
#:     distance 3 du centre (`|adj(casterFeet) inter adj(target)| == 1`). Mesure sur l'ancien
#:     montage : le bord en tronquait DEUX, et la cible a distance 2 etait REFUSEE
#:     (`invalid_target = 0x2` = `TargetMatchesDynamicRule`) -- donc plus un seul effet pose.
#: A 13x13 centre sur (6,6), les six directions existent TOUTES et aucun anneau n'est tronque.
COLS = ROWS = 13
CASTER, PLAYER_MOI, PLAYER_ADV = 10, 3, 4
CASTER_POS = (6, 6)
#: L'une des SIX directions, a distance 3 du centre de l'empreinte -- donc a distance 2 du pied le
#: plus proche, ce que la portee `CustomRange(2)` du masque exige. `test_e0_le_montage_est_dans_le
#: _regime_qu_il_documente` la RE-DERIVE du gate : elle n'est pas choisie a la main.
TARGET_POS = (6, 3)


def _empreinte_7(centre=CASTER_POS) -> list:
    """LES SEPT TUILES DE MORTARION -- centre en TETE, puis sa couronne.

    ⚠ CE MONTAGE MANQUAIT, ET SON ABSENCE A REND CE FICHIER ROUGE (#10023). Le masque de `1094`
    porte `CasterHas7Tiles` (bit 37, `int(TR.CasterHas7Tiles) == 0x2000000000`) ; depuis que
    #895-r2 a porte les trois filtres de `GetFeetCount` dans
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, un caster MONO-HEX se voit
    REFUSER le cast -- `invalid_target = 0x2000000000`, aucun effet pose, aucune erreur. Les cinq
    tests qui lisaient les effets tombaient donc en `IndexError` sur une liste vide, et les deux
    de l'etage 5 sur un `Triggered()` qui n'avait rien a declencher.

    Le gate a RAISON : c'est le montage qui mentait. `deathBossMortarion` est un boss SEPT HEX, et
    la source de cette empreinte n'est pas l'unite mais la PLATEFORME du board --
    `data/boards/global/GB_Mortarion_05.json` porte `board.BossPlatforms = [{"Size": 7, "Tiles":
    [(4,8), (3,9), (4,9), (5,9), (5,8), (4,7), (3,8)]}]`, soit le CENTRE `(4,8)` EN TETE suivi de
    ses six voisins. `IdunBattle.Operations.SetupGameOperation$$AddBossUnit` passe cette liste au
    spawn ; aucun champ de gameconfig ne porte la taille d'une unite.

    Meme ecriture que le fichier soeur `test_1030r1_the_lantern_dynamic_target_offline.py`, qui
    posait deja ses sept pieds -- c'est ce qui l'a garde VERT quand celui-ci est tombe."""
    return [centre] + list(hexgeo.neighbors(*centre))


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


def _state(foes: dict = None, caster_pos=CASTER_POS):
    """Etat runner minimal : le caster (joueur `PLAYER_MOI`) et `foes` = {uid: (col,row)}."""
    units = [{"id": CASTER, "visualId": "deathBossMortarion", "alive": True, "team": 1,
              "owner": PLAYER_MOI, "pos": {"col": caster_pos[0], "row": caster_pos[1]},
              "effects": []}]
    for uid, p in sorted((foes or {}).items()):
        units.append({"id": uid, "visualId": "necroWarden", "alive": True, "team": 2,
                      "owner": PLAYER_ADV, "pos": {"col": p[0], "row": p[1]}, "effects": []})
    decision = {"currentPlayer": PLAYER_MOI, "units": units}
    observe = {"units": [{"squadId": u["id"], "hp": 500000, "hpMax": 500000} for u in units]}
    # `combatSnapshot` MINIMAL : sans lui aucune unite n'a de `StatsComponent`, donc le niveau
    # d'ability de la phase 2 serait lu sur un repli et l'armure resterait indefinie.
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 500000, "movement": 3, "armour": 0,
                                     "turnsStarted": 0},
                           "healthMax": 500000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in units]}
    st = load_state(decision, observe, snapshot,
                    board=Board(_tiles(), adjacency="evenq"), ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    # LE CANAL `unitAbilityStates`, POSE A LA MAIN -- et il est INDISPENSABLE. Le noeud
    # `TriggerAbility` porte le gate `GetAbilityState` de
    # `IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` : l'unite declenchee
    # doit PORTER l'ability triggered. `1167 TheLantern_Attack` est une ability DERIVEE
    # (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`, dictionnaire peuple au
    # RUNTIME), donc INVISIBLE du kit gameconfig : sans ce seed, le trigger fire et le noeud rend
    # `dispatched: True, notCarrying: [caster]` -- zero degat, aucune erreur. C'est exactement le
    # regime que le champ `notCarrying` a rendu visible sur 1069 (#513 Sec.5).
    from engine.runner.components import StatsComponent, set_unit_feet
    sc = st.get_entity(CASTER).get_component(StatsComponent)
    if sc is not None and getattr(sc, "ctx", None) is not None:
        sc.ctx.triggered_abilities = [TL_ATTACK]
    # L'EMPREINTE SEPT HEX du caster -- sans elle le gate `CasterHas7Tiles` refuse tout cast
    # (cf. `_empreinte_7`). `set_unit_feet` recale la `PositionComponent` sur `feet[0]`, donc la
    # main tile reste `caster_pos`.
    set_unit_feet(st, CASTER, _empreinte_7(caster_pos))
    return st


def _zone_attendue(caster_pos=CASTER_POS, target=TARGET_POS) -> set:
    """La zone RE-DERIVEE a la main depuis le decompile, en positions -- volontairement ecrite
    autrement que le port (ensembles Python purs, aucun noeud DSL), pour qu'une faute du port ne
    puisse pas se recopier dans son oracle.

    ⚠ `cring1 = SurroundingTiles(CasterTiles, includeCenter = 0, range = 1)` porte l'EMPREINTE, pas
    la main tile (#10023). `IdunBattle.Core.Services.BattleQuery.u003CIterateSurroundingTilesu003Ed__117$$MoveNext`
    ouvre par `foreach (tile in EntityExtensions.IterateTiles(center, state))` : le disque d'une
    origine MULTI-HEX est l'UNION des disques de TOUS ses pieds. Et `includeCenter == 0` retranche
    `Tiles(origin)` = `GetMainTile` PAR ENTITE -- l'origine etant ici une liste de sept
    entites-TUILE, chacune est sa propre main tile, donc les SEPT sortent de l'anneau.

    L'oracle changeait donc en meme temps que le montage : ecrit pour un caster mono-hex, il
    n'aurait plus decrit la meme zone une fois les sept pieds poses."""
    d = hexgeo.distance
    feet = set(_empreinte_7(caster_pos))
    ring1 = {p for p in hexgeo.disk(target[0], target[1], 1) if p != target}
    ring2 = {p for p in hexgeo.disk(target[0], target[1], 2) if p != target}
    cring = {p for f in feet for p in hexgeo.disk(f[0], f[1], 1)} - feet
    dans = lambda s: {p for p in s if 0 <= p[0] < COLS and 0 <= p[1] < ROWS}   # noqa: E731
    assert d(caster_pos, target) == 3, "le montage n'a plus la distance qu'il documente"
    return dans({target} | ring1 | (ring2 & cring))


#: Une tuile LOIN de tout : ni dans la zone, ni sur un pied du caster. `test_e0_...` le verifie --
#: un montage qui la placerait par megarde DANS la zone rendrait les etages 3 et 5 muets (l'ennemi
#: << hors zone >> ne discriminerait plus rien).
DEHORS = (12, 12)


# =================================================================================================
# ETAGE 0 -- LE MONTAGE EST DANS LE REGIME QU'IL DOCUMENTE
# =================================================================================================

def test_e0_le_montage_est_dans_le_regime_qu_il_documente():
    """⚠ L'ETAGE QUI MANQUAIT, ET SON ABSENCE A COUTE SEPT ROUGES (#10023).

    Ce fichier figeait `CASTER_POS`/`TARGET_POS` comme des coordonnees confortables. Deux gates
    portes APRES son ecriture les ont rendues INVALIDES, et il n'existait aucun cran pour le dire :
    le cast partait en refus silencieux (`invalid_target`), zero effet pose, et les cinq tests qui
    lisaient les effets tombaient en `IndexError` -- un mode d'echec qui accuse la LECTURE alors
    que la faute est au MONTAGE.

      * `CasterHas7Tiles` (#895-r2) -- `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`
        refuse tout caster dont `GetFeetCount != 7` ;
      * `...TheLanternAbility$$GetDynamicInvalidTargetReason` (#1030-r1) -- n'accepte que les tuiles
        ou `|adj(casterFeet) inter adj(target)| == 1`.

    Ce test les RE-DERIVE au lieu de les croire : il balaye le plateau, exige que le gate accepte
    EXACTEMENT les SIX directions de l'i2, et que `TARGET_POS` en soit une. Les constantes du
    module deviennent ainsi verifiees, pas decretees -- au prochain gate porte, c'est ICI que ça
    rougira, en NOMMANT le refus."""
    from engine.runner.abilities.targeting import get_invalid_caster_reason
    st = _state()
    ab = ABILITY_CLASSES[TL]()
    assert get_invalid_caster_reason(st, ab, CASTER) == 0, (
        "le CASTER est refuse : l'empreinte du montage ne satisfait plus le masque")
    acceptees = sorted((c, r) for c in range(COLS) for r in range(ROWS)
                       if st.board.id_at(c, r) is not None
                       and ab.get_dynamic_invalid_target_reason(st, CASTER,
                                                                st.board.id_at(c, r)) == 0)
    assert len(acceptees) == 6, (
        "l'i2 dit SIX directions ; ce montage en offre %d (%r) -- un bord tronque le voisinage, "
        "et un ensemble tronque ne prouve pas la geometrie qu'il pretend exercer"
        % (len(acceptees), acceptees))
    assert {hexgeo.distance(p, CASTER_POS) for p in acceptees} == {3}, acceptees
    assert TARGET_POS in acceptees, (
        "TARGET_POS %r n'est plus une direction acceptee : %r" % (TARGET_POS, acceptees))
    # ... et les deux reperes que les etages 3 et 5 utilisent comme discriminants.
    zone = _zone_attendue()
    assert DEHORS not in zone and DEHORS not in set(_empreinte_7()), DEHORS
    assert len(zone) >= 7, "la zone ne passe pas le gate `|zone| >= 7` qu'exerce l'etage 6"
    assert set(_empreinte_7()).isdisjoint({TARGET_POS}), "la cible est SOUS le caster"


# =================================================================================================
# ETAGE 1 -- LES TROIS REGISTRES, DANS LE MEME COMMIT
# =================================================================================================

def test_e1_registre_masque_et_attack_type():
    """`ABILITY_CLASSES` + `TARGETING_OPTIONS` + `ABILITY_ATTACK_TYPE` : la regle de
    non-regression du CLAUDE.md, verifiee sur CETTE entree.

    Les quatre bits sont ceux du litteral `0x2000100042` du
    `IdunBattle.Core.Services.TargetingOptions$$.ctor` a 6 parametres, et leur SOMME doit RENDRE le
    litteral : un test qui ne verifierait que la presence de chaque bit passerait sur un masque
    portant en plus un cinquieme."""
    assert TL in ABILITY_CLASSES, "1094 absente d'ABILITY_CLASSES -> NO-OP SILENCIEUX"
    opts = ABILITY_CLASSES[TL].TARGETING_OPTIONS
    attendu = int(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.AllowSteppableUnit
                  | TR.CasterHas7Tiles)
    assert int(opts.rules) == attendu == 0x2000100042, hex(int(opts.rules))
    assert opts.self_cast is False
    # `CustomRange(2)` -- surcharge INT (XREF entrante) et litteral relu aux octets du call-site.
    assert opts.range.override_range == 2, opts.range
    assert opts.range.use_whole_board is False and opts.range.use_range_from_config is False
    assert ABILITY_ATTACK_TYPE[ActiveAbilityType.TheLantern] == AbilityAttackType.Others == 2


# =================================================================================================
# ETAGE 2 -- LA ZONE, ET LA MUTATION QUI LA CASSE
# =================================================================================================

def test_e2_zone_est_le_disque_plus_le_pont():
    """`Unique((Target + SurroundingTiles(Target,1)) + (SurroundingTiles(Target,2) &
    SurroundingTiles(CasterTiles,1)))`.

    L'oracle est RE-DERIVE (`_zone_attendue`), pas recopie du port. On assertionne aussi que le
    « pont » est NON VIDE et STRICTEMENT inclus dans `ring2` : sans ces deux crans, un port qui
    rendrait `ring2` entier -- ou rien -- passerait le test d'egalite sur un montage degenere."""
    from engine.runner.abilities.deathguard import the_lantern_area_selector
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = _state()
    sel = the_lantern_area_selector(_tid(*TARGET_POS))
    ids = set(sel.evaluate(entities_from_state(st, CASTER, _tid(*TARGET_POS))))
    got = {st.board.coord(t) for t in ids}
    attendu = _zone_attendue()
    assert got == attendu, "zone port %s != zone re-derivee %s" % (sorted(got), sorted(attendu))
    pont = attendu - ({TARGET_POS} | {p for p in hexgeo.disk(*TARGET_POS, 1)})
    ring2 = {p for p in hexgeo.disk(*TARGET_POS, 2) if p != TARGET_POS}
    assert pont, "le PONT est vide -- ce montage ne discrimine pas l'intersection"
    assert pont < ring2, "le pont vaut TOUT ring2 -- l'intersection ne mord pas ici"


def test_e2_contre_epreuve_union_au_lieu_d_intersection():
    """CONTRE-EPREUVE : l'`op_BitwiseAnd` du decompile remplace par un `op_Addition`.

    Vu ROUGE : la zone mutee est STRICTEMENT plus grande. Sans ce cran, l'egalite de l'etage
    ci-dessus ne prouverait pas que c'est bien une INTERSECTION qui est portee."""
    from engine.entities.selectors.accessors import FixedTileIds, SurroundingTiles, CasterTile
    from engine.entities.selectors.tiles import TileUnion, TileUnique
    from engine.dsl.base import Const
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = _state()
    tgt = FixedTileIds([_tid(*TARGET_POS)])
    r1 = SurroundingTiles(tgt, Const(1), include_center=False, include_non_walkable=False)
    r2 = SurroundingTiles(tgt, Const(2), include_center=False, include_non_walkable=False)
    cr = SurroundingTiles(CasterTile(as_ids=True), Const(1),
                          include_center=False, include_non_walkable=False)
    mute = TileUnique(TileUnion(TileUnion(tgt, r1), TileUnion(r2, cr)))       # `&` -> `+`
    ids = set(mute.evaluate(entities_from_state(st, CASTER, _tid(*TARGET_POS))))
    got = {st.board.coord(t) for t in ids}
    assert got != _zone_attendue(), "la mutation `&` -> `+` ne change RIEN : l'etage 2 est inerte"
    assert got > _zone_attendue()


# =================================================================================================
# ETAGE 3 -- LA PHASE 1 : TROIS POSES, ZERO DEGAT
# =================================================================================================

def _cast(st, target_tile):
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=CASTER, target_id=int(target_tile),
                                      ability_type=TL))
    return runner.ability_handler.last or {}


def test_e3_trois_poses_et_aucun_degat():
    """La marque sur TOUTE la zone, `Pinned` sur les seuls ENNEMIS qui s'y trouvent, l'armement sur
    le CASTER -- et pas un point de degat au cast.

    Le montage place UN ennemi DANS la zone et UN HORS zone : sans le second, un port qui poserait
    `Pinned` sur tous les ennemis du plateau passerait."""
    zone = _zone_attendue()
    dedans = sorted(zone - {TARGET_POS})[0]
    dehors = DEHORS
    assert dehors not in zone
    st = _state({20: dedans, 21: dehors})
    last = _cast(st, _tid(*TARGET_POS))
    #: ⚠ LE CANAL A CHANGE, ET C'EST UN CHANGEMENT DE HARNAIS, PAS DU MOTEUR (#10023).
    #: `AbilityHandler.last` publiait `{"dsl": True, "ability": "TheLantern"}` ; il publie
    #: desormais `{"ability_type": <id>, "ported": True, ...}` -- l'ability_type NUMERIQUE et un
    #: booleen de portage, la ou l'ancien couple melangeait << l'arbre est un DSL >> et
    #: << l'identifiant textuel >>. Lire le nouveau canal est la reparation ; toucher au moteur en
    #: serait une fausse.
    assert last.get("ported") is True and last.get("ability_type") == TL, last
    assert not last.get("invalid_target"), (
        "le cast a ete REFUSE (0x%x) : aucun effet ne sera pose, et les assertions qui suivent "
        "accuseraient la lecture au lieu du montage" % (last.get("invalid_target") or 0))
    marquees = {st.board.coord(t) for t in st.effects.by_unit
                if any(not e.consumed and int(e.effect_type) == PENDING_TARGET
                       for e in st.effects.by_unit[t]) and t in st.board.by_id}
    assert marquees == zone, "marque %s != zone %s" % (sorted(marquees), sorted(zone))
    pinned = {u for u in (20, 21)
              if any(not e.consumed and int(e.effect_type) == PINNED
                     for e in st.effects.by_unit.get(u, []))}
    assert pinned == {20}, "Pinned pose sur %s (attendu : le seul ennemi DANS la zone)" % pinned
    assert any(not e.consumed and int(e.effect_type) == PENDING_ATTACK
               for e in st.effects.by_unit.get(CASTER, [])), "1194 absent du CASTER"
    # ZERO DEGAT au cast : c'est tout l'enjeu du patron 2-phases.
    from engine.runner.components import HealthComponent
    for u in (20, 21):
        assert st.get_entity(u).get_component(HealthComponent).hp == 500000


def test_e3_contre_epreuve_enemies_sans_resolution_de_tuile():
    """CONTRE-EPREUVE de la reparation d'`Enemies` : sans la resolution
    `IdunBattle.Entities.UnitExtensions$$GetUnitOrMachine(entity, state)` que
    `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` applique a CHAQUE entite
    iteree, le `Pinned` ne se pose sur PERSONNE.

    Vu ROUGE avant la reparation. C'est la faute qui rendait le port MUET sur ce volet : `[]`, sans
    erreur.

    ⚠ **LE DOMAINE DE RETOUR EST L'ACTEUR RESOLU, et il a fallu DEUX passes pour le lire (#1030-r5).**
    `CountOrAdd` fait bien `System.Collections.Generic.List<T>.Add(result, entity)` avec l'entite
    ITEREE -- mais ce qu'il itere est le **slot 5 d'`ITargetsSelector`** = `SelectAllActors` (grille
    `metadata/interface_slots.tsv`), et `IdunBattle.DSL.TargetsSelector$$SelectAllActors` a DEJA
    resolu chaque element par `IdunBattle.DSL.TargetsSelector$$SelectUnit`
    (`IsUnitFoot || IsTile -> GetUnit`). Lire l'`Add` sans cet etage fait conclure << entite
    source >> et rend des ids de TUILE : c'est ce qu'avait fait la 1re passe, en s'alignant sur
    `master` -- qui portait la meme lecture tronquee. Recoupements (fonction soeur `$$SelectAllUnits`
    au slot 20, et `NormalUnits(Enemies(<TUILES>))` de `...NovaChargeAbility$$GetAdditionalMarkedTiles`)
    dans la docstring d'`Enemies`."""
    from engine.entities.selectors import units as U
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    ancien = U.unit_or_machine
    try:
        # Le comportement d'AVANT : aucune resolution -- une entite-TUILE (id `int`) ne rendait
        # aucune unite, donc l'ensemble sortait VIDE, sans erreur.
        U.unit_or_machine = lambda e, ctx: (e if isinstance(e, dict) else None)
        st2 = _state({20: sorted(zone - {TARGET_POS})[0]})
        _cast(st2, _tid(*TARGET_POS))
        pinned_mute = [e for e in st2.effects.by_unit.get(20, [])
                       if not e.consumed and int(e.effect_type) == PINNED]
    finally:
        U.unit_or_machine = ancien
    _cast(st, _tid(*TARGET_POS))
    pinned_ok = [e for e in st.effects.by_unit.get(20, [])
                 if not e.consumed and int(e.effect_type) == PINNED]
    assert not pinned_mute, "la mutation ne mord pas -- l'etage 3 ne prouve rien de la reparation"
    assert pinned_ok, "avec la reparation, `Pinned` doit etre pose"


def test_e3_contre_epreuve_le_domaine_de_retour_est_l_ACTEUR_pas_la_TUILE():
    """CONTRE-EPREUVE du DOMAINE DE RETOUR -- l'axe qui a OSCILLE DEUX FOIS (#1030-r5).

    La faute gardee ici n'est PAS l'absence de resolution (c'est la contre-epreuve precedente) :
    c'est `result.Add(entity)` relu comme << l'entite SOURCE >>. La resolution a bien lieu, le test
    de camp est juste, et le noeud rend quand meme des ids de TUILE. En aval, `AddEffect` pose alors
    sur un `int` : `Pinned` sur PERSONNE, **sans une seule erreur**.

    C'est exactement la forme que portait `master`, et qu'une premiere passe de #1030 avait
    recopiee en s'y << alignant >>. Aucune garde ne la voyait : sur les call-sites unit-domain,
    `GetUnitOrMachine(unit) == unit` rend les deux lectures IDENTIQUES. Il faut une source
    tile-domain -- la zone de `1094` en est une.

    Ce que le decompile oppose a cette lecture : `CountOrAdd` itere le SLOT 5 d'`ITargetsSelector`
    (`SelectAllActors`), qui a deja resolu par `IdunBattle.DSL.TargetsSelector$$SelectUnit`. Donc
    l'element ajoute EST l'acteur. Recoupe trois fois -- fonction soeur `$$SelectAllUnits` au slot
    20 contre `$$SelectAllActors` au slot 21 ; `NormalUnits(Enemies(<TUILES>))` de
    `...NovaChargeAbility$$GetAdditionalMarkedTiles` ; et
    `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select`, qui appelle le slot 3
    `SelectAllUnits` avant son `GetMainTile` (un selecteur nomme << UnitsMainTiles >> qui demande
    << SelectAllUnits >> : la grille de slots est la bonne)."""
    from engine.entities.selectors import units as U
    zone = _zone_attendue()
    dedans = sorted(zone - {TARGET_POS})[0]

    ancien = U.Enemies.select
    try:
        def _select_rend_l_entite_source(self, ctx):
            """LA FORME DE `master` AVANT #1030-r5 : identique au mirror, sauf le dernier mot."""
            ref = (U.resolve_unit(self.reference, ctx)
                   if self.reference is not None else ctx.caster)
            ct = (ref or {}).get("team")
            out = []
            for e in U._entities_of(self.inner, ctx):
                u = U.unit_or_machine(e, ctx)
                if u is None or u.get("team") == ct:
                    continue
                out.append(e)                     # <- l'ENTITE SOURCE, la lecture REFUTEE
            return out
        U.Enemies.select = _select_rend_l_entite_source
        st_mut = _state({20: dedans})
        _cast(st_mut, _tid(*TARGET_POS))
        pinned_mut = [e for e in st_mut.effects.by_unit.get(20, [])
                      if not e.consumed and int(e.effect_type) == PINNED]
    finally:
        U.Enemies.select = ancien

    st = _state({20: dedans})
    _cast(st, _tid(*TARGET_POS))
    pinned_ok = [e for e in st.effects.by_unit.get(20, [])
                 if not e.consumed and int(e.effect_type) == PINNED]

    assert not pinned_mut, (
        "la mutation ne mord pas : rendre l'entite SOURCE laisse `Pinned` pose -- cette garde ne "
        "protege alors RIEN de l'oscillation qu'elle vise")
    assert pinned_ok, "avec le domaine corrige, `Pinned` doit etre pose sur l'occupant"


# =================================================================================================
# ETAGE 4 -- L'ATTAQUANT DE LA PHASE 2 : `EffectSource`, PAS `BondedEntity`
# =================================================================================================

def _turn_start(st, player_id):
    from engine.runner.operations.triggers.dispatch.turn import delayed_attack_triggers
    return delayed_attack_triggers(st, int(player_id))


def test_e4_attaquant_est_la_source_de_l_effet():
    """`<klass+0x758> GetAttackingUnitSelector` SURCHARGEE en `DSLSelectors$$EffectSource(Effect)`.

    L'effet 1194 est pose par `AddEffect`, donc SANS composant de bond : la table doit le declarer
    `ATTACKER_EFFECT_SOURCE`, et l'instance posee doit effectivement porter `bonded is None` (sans
    quoi ce test ne mesurerait pas ce qu'il croit)."""
    from engine.runner.operations.triggers import pending_attack as PA
    spec = PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK]
    assert spec.attacker == PA.ATTACKER_EFFECT_SOURCE
    assert spec.triggered_ability == TL_ATTACK
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    _cast(st, _tid(*TARGET_POS))
    inst = [e for e in st.effects.by_unit.get(CASTER, [])
            if not e.consumed and int(e.effect_type) == PENDING_ATTACK][0]
    assert getattr(inst, "bonded", None) is None, (
        "l'instance porte un bond : le regime que ce test discrimine n'existe plus")
    assert int(inst.source) == CASTER
    assert PA._attacking_unit(inst) == CASTER


def test_e4_contre_epreuve_lecture_bonded():
    """CONTRE-EPREUVE : la table declaree `ATTACKER_BONDED` (le corps HERITE) -- l'attaquant devient
    introuvable et la phase 2 ne part JAMAIS.

    Vu ROUGE : c'est exactement le regime silencieux qu'aurait produit un port qui aurait recopie
    le corps que `ghidra/functions.tsv` attribue a `ValkyrieStrikeEffect`."""
    from engine.runner.operations.triggers import pending_attack as PA
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    _cast(st, _tid(*TARGET_POS))
    inst = [e for e in st.effects.by_unit.get(CASTER, [])
            if not e.consumed and int(e.effect_type) == PENDING_ATTACK][0]
    vrai = PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK]
    try:
        PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK] = vrai._replace(
            attacker=PA.ATTACKER_BONDED)
        assert PA._attacking_unit(inst) is None, (
            "la mutation ne mord pas -- l'etage 4 ne prouve rien")
    finally:
        PA.PENDING_ATTACK_EFFECTS[PENDING_ATTACK] = vrai


# =================================================================================================
# ETAGE 5 -- LA MARQUE EST RELUE AU TIR (le volet qui exige DEUX tours)
# =================================================================================================

def test_e5_le_tir_frappe_les_occupants_courants():
    """La zone marquee vit sur des TUILES : l'unite qui SORT y echappe, celle qui ENTRE la prend.

    Le montage bouge DEUX unites entre le cast et le tir -- une dans chaque sens -- sur un etat par
    ailleurs identique. Un port qui figerait la liste des cibles AU CAST frapperait exactement
    l'inverse."""
    from engine.runner.components import HealthComponent, PositionComponent
    zone = _zone_attendue()
    dedans = sorted(zone - {TARGET_POS})[0]
    dehors = DEHORS
    st = _state({20: dedans, 21: dehors})
    _cast(st, _tid(*TARGET_POS))
    # 20 SORT de la zone, 21 y ENTRE -- apres le cast, avant le tir.
    st.get_entity(20).get_component(PositionComponent).col = dehors[0]
    st.get_entity(20).get_component(PositionComponent).row = dehors[1]
    st.get_entity(21).get_component(PositionComponent).col = dedans[0]
    st.get_entity(21).get_component(PositionComponent).row = dedans[1]
    hp0 = {u: st.get_entity(u).get_component(HealthComponent).hp for u in (20, 21)}
    fired = _turn_start(st, PLAYER_MOI)
    assert fired, "le `Triggered()` d'APendingAttackEffect n'a pas fire au tour du caster"
    hp1 = {u: st.get_entity(u).get_component(HealthComponent).hp for u in (20, 21)}
    assert hp1[20] == hp0[20], "l'unite SORTIE de la zone a ete frappee"
    assert hp1[21] < hp0[21], "l'unite ENTREE dans la zone n'a PAS ete frappee"
    # La marque est retiree par le meme arbre (`RemoveEffect(cache, 1195)`), et l'armement 1194 par
    # le `RemoveEffect(Effect)` du `Triggered()` de la base.
    restant = [t for t in st.effects.by_unit
               if any(not e.consumed and int(e.effect_type) == PENDING_TARGET
                      for e in st.effects.by_unit[t])]
    assert not restant, "la marque 1195 survit au tir : %s" % restant
    assert not [e for e in st.effects.by_unit.get(CASTER, [])
                if not e.consumed and int(e.effect_type) == PENDING_ATTACK]


def test_e5_ne_fire_pas_au_tour_adverse():
    """TEMOIN NEGATIF : `IsTurnOf(GetAttackingUnitSelector())`. Au tour de l'ADVERSE, rien ne part
    et la marque reste. Sans ce cran, l'etage 5 ne distinguerait pas « fire au bon tour » de
    « fire a tous les tours »."""
    from engine.runner.components import HealthComponent
    zone = _zone_attendue()
    st = _state({20: sorted(zone - {TARGET_POS})[0]})
    _cast(st, _tid(*TARGET_POS))
    hp0 = st.get_entity(20).get_component(HealthComponent).hp
    _turn_start(st, PLAYER_ADV)
    assert st.get_entity(20).get_component(HealthComponent).hp == hp0
    assert any(not e.consumed and int(e.effect_type) == PENDING_ATTACK
               for e in st.effects.by_unit.get(CASTER, []))


# =================================================================================================
# ETAGE 6 -- LA FACE DECISION
# =================================================================================================

def test_e6_utilite_poids_et_gate_de_sept_tuiles():
    """`n1 * 1 + n2 * 0,1` sous le gate `|zone| >= 7`, avec `n2` compte sur les ENNEMIS DEJA
    filtres (l'ordre des deux `FilterInPlace` est load-bearing).

    Le montage met dans la zone : un ennemi ordinaire, un ennemi PSYKER, et un ALLIE psyker. Le
    troisieme est le discriminant : un port qui compterait les psykers de la zone (et non les
    ennemis psykers) rendrait `2 + 0,2` au lieu de `2 + 0,1`."""
    from engine.playbook.noncomparable.the_lantern import TheLanternPlaybook
    zone = sorted(_zone_attendue() - {TARGET_POS})
    pb = TheLanternPlaybook()

    class _Ctx:
        uid = CASTER
        origin = CASTER_POS
        #: UNE LIGNE PAR PIED pour le caster (#10023) -- c'est le canal que lit
        #: `TheLanternPlaybook._measured_feet`, et il rend `[]` des qu'il n'y en a qu'une (donc
        #: `_caster_footprint` retombe sur `[position]`). Avec une seule ligne, la face DECISION
        #: calculait la zone d'un caster MONO-HEX pendant que la face COMBAT en calculait une de
        #: SEPT : les deux ne pouvaient plus coincider, et c'est ce que ce test compare.
        obs_units = [
            {"id": CASTER, "teamId": 1, "visualId": "deathBossMortarion",
             "pos": {"col": f[0], "row": f[1]}} for f in _empreinte_7()
        ] + [
            {"id": 20, "teamId": 2, "visualId": "necroWarden",
             "pos": {"col": zone[0][0], "row": zone[0][1]}},
            {"id": 21, "teamId": 2, "visualId": "eldarFarseer",
             "pos": {"col": zone[1][0], "row": zone[1][1]}},
            {"id": 22, "teamId": 1, "visualId": "eldarFarseer",
             "pos": {"col": zone[2][0], "row": zone[2][1]}},
        ]
        elev_by_pos = {(c, r): 0 for c in range(COLS) for r in range(ROWS)}
        is_wall_by_pos = {}
        walkable_by_pos = {}
        scene = None

    from engine.entities.traits.unit_trait import entity_trait_names, has_any_trait
    psyker = has_any_trait(entity_trait_names(None, "eldarFarseer"), ("Psyker",))
    if not psyker:
        pytest.skip("`eldarFarseer` n'est plus Psyker au gameconfig -- montage a refaire")
    area = pb.target_area(_Ctx(), CASTER_POS, TARGET_POS)
    assert area == _zone_attendue(), "la zone de la face DECISION diverge de celle du COMBAT"
    assert len(area) >= 7, "le montage ne passe pas le gate qu'il pretend exercer"
    u = pb._enemies_hit_utility(_Ctx(), area)
    assert abs(u - (2 * 1.0 + 1 * 0.1)) < 1e-9, u


def test_e6_gate_sept_tuiles_mord():
    """Le gate `|zone| >= 7` : sur une zone TRONQUEE (cible dans un coin du board), l'ability n'est
    pas proposee. TEMOIN : la meme mesure au centre la propose."""
    from engine.playbook.noncomparable.the_lantern import TheLanternPlaybook, _MIN_TILES_HIT
    pb = TheLanternPlaybook()

    class _Ctx:
        uid = CASTER
        origin = (0, 0)
        obs_units = [{"id": CASTER, "teamId": 1, "visualId": "deathBossMortarion",
                      "pos": {"col": 0, "row": 0}}]
        elev_by_pos = {(c, r): 0 for c in range(COLS) for r in range(ROWS)}
        is_wall_by_pos = {}
        walkable_by_pos = {}
        scene = None

    coin = pb.target_area(_Ctx(), (0, 0), (0, 0))
    centre = pb.target_area(_Ctx(), (4, 4), (4, 4))
    assert len(coin) < _MIN_TILES_HIT <= len(centre), (len(coin), len(centre))


if os.environ.get("TACTICUS_1030_SELFTEST"):        # pragma: no cover - aide au diagnostic
    print("zone:", sorted(_zone_attendue()))
