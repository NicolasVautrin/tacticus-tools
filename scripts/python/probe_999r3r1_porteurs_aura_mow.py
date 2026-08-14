"""#999-r3-r1-r1 -- MESURE : une MACHINE OF WAR porteuse d'un effet-AURA entre-t-elle dans
l'univers de porteurs des deux agregateurs d'aura, sur les DEUX faces ?

⚠ CE PROBE A CHANGE DE SENS, ET C'EST SON TRAVAIL. Il a ete ecrit pour MONTRER le trou (rc 0 =
<< le trou est bien la >>) et pour rendre `rc 1` le jour ou l'etat changerait. Ce jour est arrive :
le trou est REPARE, il a rendu `rc 1`, et son verdict est desormais inverse -- `rc 0` = la
reparation TIENT sur les deux faces. Le montage, lui, n'a pas bouge d'une ligne : c'est le meme
etat synthetique, la meme interception du foyer REEL.

POURQUOI CE PROBE EXISTE. `#999-r3-r1` annonce que le threading de la rarete (`att_rarity` /
`tgt_rarity` / `rarity`) debloque SIX effets. Il en debloque **un** : les cinq autres
(1442 `BlightedLand`, 1443 `ContemptuousDisregard`, 1445 `WisdomOfTheAncients`,
1449 `MoreGitzOverEre`, 1494 `CabalOfSorcerers`, 1548 `GuardianConstruct`) vivent sur des MACHINES
OF WAR, et un SECOND blocage -- independant de la rarete -- les tient hors de portee.

CE QUE LE NATIF FAIT. `IdunBattle.Core.Services.DamageCalculations$$
CalculateDefenderModifiersForPrediction` (et son jumeau `...CalculateAttackerModifiersForPrediction`)
iterent une `List<KeyValuePair<entite, List<effet>>>` de l'ETAT : la boucle est BOARD-WIDE et ne lit
AUCUNE position pour decider qui entre. Une MoW porteuse d'un `EffectWithTarget` y est donc, comme
n'importe quelle unite.

CE QUE LE PORT FAISAIT, ET QUI EST CORRIGE. Les deux agregateurs construisaient leur liste de
porteurs en EXIGEANT un `PositionComponent` :

    runner/damage_model.py::_apply_ally_attack_damage_auras   `if oc is None or pc is None ...`
    runner/damage_model.py::defender_modifiers                `if oc is None or pc is None: continue`

Or `runner/snapshot.py::_load_machines` ne pose NI `PositionComponent` NI `HealthComponent` sur une
Machine (elle est HORS-PLATEAU : le natif n'en a pas non plus). Le filtre etait donc un ARTEFACT du
port, et il ecartait structurellement toute MoW. Il est LEVE : le porteur entre avec
`owner_pos = None`, et les auras POSITIONNELLES se taisent d'elles-memes chez leurs lecteurs
(`op, ap = c.get("owner_pos"), c.get("att_pos")` puis `if not op or not ap: return None`).

Face PREDICTION, le blocage etait DOUBLE : `playbook/scene.py::step_context` seedait son
`EffectsState` depuis `dv["units"]` SEULEMENT -- alors que le canal `dv["mows"][].effects` EXISTE
(`frida/hooks/features/ai-step/rpc-decision.ts` l'assemble par `effectsByUnit.get(m.casterId)`,
meme `readEffectsByUnit` que pour les units ; ⚠ `projectMowsFull` seul ne porte AUCUN champ
`effects`, le rattachement se fait au site d'ASSEMBLAGE du RPC) -- et les TROIS boucles de porteurs
(`prediction/_shared.py` x2, `prediction/normal_attack.py` x1) iteraient `scene.pos_by_id`, ou une
MoW n'entre jamais. Les deux volets sont corriges : le seed prend les MoW, et les boucles passent
par le foyer `Scene.effect_carrier_ids`.

⚠ `pos_by_id` n'a PAS ete elargi, et c'est deliberé : une MoW n'a pas de position cote natif non
plus. Y inventer une tuile rendrait evaluable une aura positionnelle qui doit se taire -- pire
qu'un gate muet.

VERDICT ATTENDU (rc 0) : la reparation TIENT sur les DEUX faces. `rc != 0` = le trou est reouvert
(par un cote ou par les deux), ou le montage ne mesure plus rien.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import hexgeo                                                                   # noqa: E402
from engine.entities.pathfinding.board import Board                             # noqa: E402
from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.rarity import Rarity                                       # noqa: E402
from engine.runner.snapshot import load_state                                   # noqa: E402
from engine.runner.components import PositionComponent, StatsComponent          # noqa: E402
from engine.runner import damage_model as DM                                    # noqa: E402
from engine.runner.damage_model import unit_state_for_effects                   # noqa: E402

COLS, ROWS = 5, 5
#: `ATT_ID` = l'ATTAQUANT ; `ALLY_ID` = un allie PORTEUR-temoin (l'aura ATTAQUE exclut le
#: beneficiaire lui-meme, donc l'attaquant ne peut pas etre son propre temoin) ; `MOW_ID` = la
#: Machine of War alliee, porteuse de l'aura mesuree.
MOW_ID, ATT_ID, ALLY_ID, FOE_ID = 90, 11, 10, 20
#: `EffectType` 0x5a2 = 1442 -- l'owner-effect AURA de la mythique `BlightedLand` (MoW `deathCrawler`).
AURA_EFFECT = EffectType.BlightedLand_ExtraDamagePct
#: TEMOIN de presence, pose sur l'ALLIE : sans AU MOINS un porteur retenu, les deux agregateurs ne
#: sont meme pas APPELES (`if not carriers: return`), et l'absence de la MoW ne se distinguerait plus
#: de l'absence de toute mesure. `Markerlight` (1122) est inerte ici (gate `HasFaction(actor, T'au)`
#: + `IsRangedAttack`, et l'attaquant est un Ork en melee) : il ne fabrique aucun nombre.
EFFET_TEMOIN = EffectType.Markerlight
#: `EntityType.Machine` = 6 (`combatSnapshot.units[].entityType`), cf. `snapshot._ENTITY_TYPE_MACHINE`.
ENTITY_TYPE_MACHINE = 6
ENTITY_TYPE_UNIT = 1


def _tid(c: int, r: int) -> int:
    return c * ROWS + r + 1


def _board() -> Board:
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def decision_view() -> dict:
    """`decisionView` MINIMAL : deux unites + une MoW alliee porteuse de l'aura 1442.

    La MoW est publiee comme le fait le capteur -- canal `.mows` SEPARE, `pos = null` -- et son
    effet apparait a la FOIS dans `mows[].effects` et dans `effects[]` (les deux canaux que
    `load_state` consomme)."""
    return {
        "currentPlayer": 1,
        "units": [
            {"id": ATT_ID, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 2, "row": 1}, "effects": []},
            {"id": ALLY_ID, "visualId": "orksKillaKan", "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 1, "row": 1},
             "effects": [{"id": 7002, "name": EFFET_TEMOIN.name,
                          "effectType": int(EFFET_TEMOIN), "source": ALLY_ID, "active": True}]},
            {"id": FOE_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
             "pos": {"col": 3, "row": 1}, "effects": []},
        ],
        "mows": [
            {"casterId": MOW_ID, "visualId": "deathCrawler", "alive": True, "team": 1, "owner": 1,
             "pos": None, "slot": 1,
             "effects": [{"id": 7001, "name": AURA_EFFECT.name, "effectType": int(AURA_EFFECT),
                          "sourceId": MOW_ID, "active": True, "targetIds": []}]},
        ],
        "effects": [
            {"id": 7001, "name": AURA_EFFECT.name, "effectType": int(AURA_EFFECT),
             "ownerId": MOW_ID, "source": MOW_ID, "active": True, "targetIds": []},
            {"id": 7002, "name": EFFET_TEMOIN.name, "effectType": int(EFFET_TEMOIN),
             "ownerId": ALLY_ID, "source": ALLY_ID, "active": True, "targetIds": []},
        ],
    }


def observe() -> dict:
    return {"units": [{"squadId": ATT_ID, "hp": 5000, "hpMax": 5000},
                      {"squadId": ALLY_ID, "hp": 5000, "hpMax": 5000},
                      {"squadId": FOE_ID, "hp": 5000, "hpMax": 5000}]}


def combat_snapshot() -> dict:
    """`combatSnapshot` MINIMAL portant le canal `rarity` (#1039) -- l'allie en `Epic`, la MoW et
    l'ennemi en `Mythic`. C'est un regime SEPARANT en miniature : le gate de rarete y a un verdict
    different selon l'unite, contrairement au regime par defaut du harnais (`targetRarity = 5`)."""
    return {"rarityEnum": "idun.meta.Rarity",
            "units": [
                {"entityId": ATT_ID, "visualId": "orksNob",
                 "entityType": ENTITY_TYPE_UNIT, "rarity": int(Rarity.Epic)},
                {"entityId": ALLY_ID, "visualId": "orksKillaKan",
                 "entityType": ENTITY_TYPE_UNIT, "rarity": int(Rarity.Epic)},
                {"entityId": FOE_ID, "visualId": "necroWarden",
                 "entityType": ENTITY_TYPE_UNIT, "rarity": int(Rarity.Mythic)},
                {"entityId": MOW_ID, "visualId": "deathCrawler",
                 "entityType": ENTITY_TYPE_MACHINE, "rarity": int(Rarity.Mythic)},
            ]}


def _porteurs_captes(nom_agregateur: str, appel):
    """Liste des ids de PORTEURS que le foyer REEL a retenus, captee en INTERCEPTANT l'agregateur.

    ⚠ ON N'EN RECOPIE PAS LA BOUCLE. Un mirror de la collecte serait un artefact du probe : mesure
    (#999-r3-r1, contre-epreuve M10) -- avec un mirror, une mutation qui ADMET les MoW dans le vrai
    foyer laissait le cliquet VERT, donc le controle mesurait son propre code. L'interception, elle,
    lit l'argument que le foyer PASSE.

    ⚠ FORME B DE MORSURE : `damage_model` lie ces symboles au niveau module, donc le call-site lit
    un GLOBAL du module -- remplacer l'attribut de `damage_model` mord. Remplacer
    `engine.entities.effects.<nom>` ne mordrait PAS.

    Rend `None` si l'agregateur n'a PAS ete appele (aucun porteur retenu du tout) : un `[]` s'y
    confondrait avec << appele, MoW absente >>."""
    vus = []
    reel = getattr(DM, nom_agregateur)

    def _spy(carriers, ctx):
        vus.append([c[0] for c in (carriers or [])])
        return reel(carriers, ctx)

    setattr(DM, nom_agregateur, _spy)
    try:
        appel()
    finally:
        setattr(DM, nom_agregateur, reel)
    return vus[0] if vus else None


def mesurer():
    """Rend `(state, faits)` -- `faits` = dict de booleens MESURES, consomme par le cliquet."""
    st = load_state(decision_view(), observe(), combat_snapshot(), board=_board())
    mow = st.get_entity(MOW_ID)
    sc = mow.get_component(StatsComponent) if mow is not None else None
    porte = [getattr(e, "name", None)
             for e in st.effects.active_effects(MOW_ID, unit_state_for_effects(st, MOW_ID))]
    att = _porteurs_captes(
        "aura_attack_damage_bonus_from_allies",
        lambda: DM.attacker_modifiers(st, ATT_ID, 5000, is_ranged=False, target_id=FOE_ID))
    dfe = _porteurs_captes(
        "aura_defense_damage_malus_from_units",
        lambda: DM.defender_modifiers(st, FOE_ID, 5000, is_melee=True, attacker_id=ALLY_ID))
    faits = {
        "mow_entite": mow is not None,
        "mow_sans_position": (mow is not None
                              and mow.get_component(PositionComponent) is None),
        "mow_rarete_mesuree": getattr(getattr(sc, "ctx", None), "rarity", None) == Rarity.Mythic,
        "mow_porte_l_aura": AURA_EFFECT.name in porte,
        "aura_attaque_appelee": att is not None,
        "aura_defense_appelee": dfe is not None,
        "mow_porteur_aura_attaque": bool(att) and MOW_ID in att,
        "mow_porteur_aura_defense": bool(dfe) and MOW_ID in dfe,
        "att_porteurs": att,
        "def_porteurs": dfe,
    }
    return st, faits


def mesurer_prediction():
    """Face DECISION : `playbook/scene.py::step_context` voit-il l'effet de la MoW ?

    Le `predictor` minimal porte les trois tables que la fonction consomme. `mult_by_id` /
    `ablvl_by_id` / `ctx_by_id` n'ont AUCUNE entree pour la MoW -- c'est deja le regime reel
    (`_effect_source_ability_states` l'ecarte explicitement)."""
    from engine.playbook.scene import step_context                              # noqa: PLC0415
    dv = decision_view()
    predictor = {"mult_by_id": {ALLY_ID: 100, FOE_ID: 100},
                 "ablvl_by_id": {ALLY_ID: 50, FOE_ID: 50},
                 "ctx_by_id": {}}
    sc = step_context(predictor, dv)
    eff = sc["eff_state"]
    return {
        "mow_dans_eff_state": MOW_ID in (eff.by_unit or {}),
        "mow_dans_pos_by_id": MOW_ID in (sc["pos_by_id"] or {}),
        "mow_dans_team_by_id": MOW_ID in (sc["team_by_id"] or {}),
        "mow_dans_univers_porteurs": MOW_ID in scene_prediction(sc).effect_carrier_ids(),
    }


def scene_prediction(sctx=None):
    """La `Scene` de la face DECISION, montee sur le MEME `step_context` que `mesurer_prediction`.

    Exposee separement parce que `mow_dans_eff_state` et << la boucle de porteurs la VOIT >> sont
    DEUX faits distincts : le premier dit que l'effet est SEEDE, le second que l'agregateur
    l'atteint. Le foyer qui les relie est `Scene.effect_carrier_ids` (#999-r3-r1-r1), et c'est LUI
    que les trois boucles d'aura de la face DECISION consomment desormais -- pas `pos_by_id`."""
    from engine.playbook.scene import Scene, step_context                       # noqa: PLC0415
    if sctx is None:
        dv = decision_view()
        predictor = {"mult_by_id": {ALLY_ID: 100, FOE_ID: 100},
                     "ablvl_by_id": {ALLY_ID: 50, FOE_ID: 50},
                     "ctx_by_id": {}}
        sctx = step_context(predictor, dv)
    return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                 vis_by_id={}, units=sctx.get("units") or [],
                 hp_by_id=sctx.get("hp_by_id") or {}, pos_by_id=sctx.get("pos_by_id") or {},
                 team_by_id=sctx.get("team_by_id") or {}, eff_state=sctx["eff_state"])


def main() -> int:
    print("=== #999-r3-r1-r1 : une MoW porteuse d'aura entre-t-elle dans l'univers de porteurs ? ===")
    st, f = mesurer()
    print("-- face COMBAT (runner/damage_model.py)")
    print("   MoW materialisee comme entite            : %s" % f["mow_entite"])
    print("   MoW SANS PositionComponent (hors-plateau): %s" % f["mow_sans_position"])
    print("   rarete de la MoW MESUREE (canal #1039)   : %s" % f["mow_rarete_mesuree"])
    print("   MoW porte bien l'aura %-4d actif         : %s"
          % (int(AURA_EFFECT), f["mow_porte_l_aura"]))
    print("   agregateur ATTAQUE appele (temoin)       : %s   (porteurs : %s)"
          % (f["aura_attaque_appelee"], f["att_porteurs"]))
    print("   MoW retenue comme porteur (ATTAQUE)      : %s" % f["mow_porteur_aura_attaque"])
    print("   agregateur DEFENSE appele (temoin)       : %s   (porteurs : %s)"
          % (f["aura_defense_appelee"], f["def_porteurs"]))
    print("   MoW retenue comme porteur (DEFENSE)      : %s" % f["mow_porteur_aura_defense"])
    p = mesurer_prediction()
    print("-- face PREDICTION (playbook/scene.py::step_context)")
    print("   MoW dans EffectsState.by_unit            : %s" % p["mow_dans_eff_state"])
    print("   MoW dans l'univers des porteurs          : %s" % p["mow_dans_univers_porteurs"])
    print("   MoW dans pos_by_id (doit rester False)   : %s" % p["mow_dans_pos_by_id"])
    print("   MoW dans team_by_id (temoin, #360)       : %s" % p["mow_dans_team_by_id"])

    attendu = (f["mow_entite"] and f["mow_sans_position"] and f["mow_rarete_mesuree"]
               and f["mow_porte_l_aura"]
               # TEMOINS DE NON-DEGENERESCENCE : sans eux, << la MoW EST porteuse >> ne pourrait
               # meme pas etre evalue le jour ou les agregateurs ne tourneraient plus du tout.
               and f["aura_attaque_appelee"] and f["aura_defense_appelee"]
               and f["mow_porteur_aura_attaque"] and f["mow_porteur_aura_defense"]
               and p["mow_dans_eff_state"] and p["mow_dans_univers_porteurs"]
               # RESTE FAUX, ET C'EST FIDELE : une MoW n'a pas de position, cote natif non plus.
               # Ce qu'il fallait elargir est l'UNIVERS DES PORTEURS, pas `pos_by_id` -- l'elargir
               # aurait INVENTE une tuile, et rendu evaluable une aura positionnelle qui doit se
               # taire.
               and not p["mow_dans_pos_by_id"]
               and p["mow_dans_team_by_id"])
    print()
    if attendu:
        print("VERDICT: le trou est REPARE sur les DEUX faces (#999-r3-r1-r1). La MoW porteuse est")
        print("         retenue par les deux agregateurs COMBAT, ses effets sont seedes cote")
        print("         DECISION, et elle entre dans `Scene.effect_carrier_ids` -- sans avoir recu")
        print("         de position. Ce qui reste a faire pour 1442/1443/1445/1449/1494/1548 est")
        print("         le PORT de chaque effet, plus sa confrontation en regime SEPARANT.")
        return 0
    print("VERDICT: L'ETAT A CHANGE -- cette fiche (#999-r3-r1-r1) est PERIMEE, re-lire le foyer.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
