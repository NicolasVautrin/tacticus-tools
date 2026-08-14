"""#1038-r1 / #1042-r1 -- les DEUX auras de REDUCTION de degat des mythiques de MACHINE OF WAR :
`ContemptuousDisregard_DamageReduction` (1443) et `WisdomOfTheAncients_DamageReduction` (1445).

Elles partagent la MEME face DEGAT (`ForPercentDecrease(get_OwnerIsTarget, ConfigVar(0x46 =
dmgReductionPct))`) et le MEME canal (`create_aura_defense_damage_malus_for_ally`) ; seul leur
`$$CreateTargetSelector` differe. Ce fichier garde ce qui separe -- jamais un scalaire.

⚠ LE PIEGE QUE CE FICHIER EXISTE POUR EVITER. `rl_duel build` impose `targetRarity = 5` a toute
unite normalisee : dans le regime par defaut du harnais, TOUT gate `UnitsWithRarity(Mythic)` est
uniformement VRAI, et un port qui l'oublierait serait faussement d'accord partout. Chaque etage de
rarete ci-dessous exhibe donc son TEMOIN NON NUL -- une entree PRISE et une entree ECARTEE.

HUIT ETAGES :
  A. les deux effets sont au REGISTRE, routes par la FABRIQUE, sur le canal AURA -- et leur canal
     PORTEUR reste le no-op de `BaseEffect` (l'inscrire la donnerait la reduction a la MoW) ;
  B. 1443 -- les TROIS etages du selecteur SEPARENT (equipe, rarete, status de tuile), plus le
     contre-bras `LightCover` qui n'est PAS un status de tuile ;
  C. 1443 -- la magnitude est `dmgReductionPct[niveau] x multiplicateur`, relue au gameconfig ;
  D. 1445 -- le resolveur COMBAT separe les TROIS etages du selecteur sur un etat REEL ;
  E. 1445 -- le resolveur PREDICTION rend EXACTEMENT le meme set (pas de fork de substrat) ;
  F. 1445 -- `A` est VIDE quand le porteur n'a pas de position : c'est ce qui rend le
     `ConditionalSelector(IsMachine(Owner), ...)` non porte EQUIVALENT, et non raccourci ;
  G. les DEUX facades POSENT la cle `wisdom_of_the_ancients_target_ids_of` ;
  H. la FACE NATIVE des deux contributions est DEFENSEUR (slot `CreateEffectDamageMalusForDefense`
     implemente EN PROPRE, pas le forwarder de `DamageModifierAbilityEffect`).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]            # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                        # noqa: E402
from engine.entities.effect_type import EffectType                                   # noqa: E402
from engine.entities.rarity import Rarity                                            # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                              # noqa: E402
from engine.runner import damage_model as DM                                         # noqa: E402
from engine.runner.snapshot import load_state                                        # noqa: E402
from engine.entities.pathfinding.board import Board                                  # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/damage_reduction.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/services/static_battle_rules.py",
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "L'etage C lit le GAMECONFIG (`ContemptuousDisregard.dmgReductionPct`), qui se perime "
              "SEPAREMENT du build ; le fichier fige des ORDINAUX ECRITS au site (1443, 1445, "
              "`Rarity.Mythic = 5`, `UnitTrait.Hero = 0x10`) qu'un renumerotage rendrait faux sans "
              "toucher aucun des chemins ci-dessus ; et l'etage F garde une ABSENCE (aucune "
              "position pour une MoW), donc une reparation n'importe ou dans le seed le concerne.",
}

CD = EffectType.ContemptuousDisregard_DamageReduction        # 0x5a3 = 1443
WOTA = EffectType.WisdomOfTheAncients_DamageReduction        # 0x5a5 = 1445
#: Gameconfig des DEUX mythiques : `dmgReductionPct = [10, 13, 16, 20]` (voie TERTIAIRE, 4 paliers).
PALIERS = [10, 13, 16, 20]
#: `StaticBattleRules.Effect$$IsTileStatusEffect` -- un membre du set, et un NON-membre.
STATUS = "Fire"
NON_STATUS = "LightCover"

COLS, ROWS = 8, 8
ENTITY_TYPE_UNIT = 1
#: Le porteur (la MoW, hors plateau) et les cinq unites du montage de `probe_1042_...`.
MOW_ID = 90
P1, P2, P3 = 11, 12, 13        # chaine adjacente : P1 - P2 - P3
H, X = 21, 22                  # paire isolee ; `H` est le Hero, `X` son voisin
FOE = 31                       # equipe adverse


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


# ============================================================ A -- le REGISTRE et le CANAL

def _instance(effect_type: EffectType, source: int = MOW_ID, level: int = 4, mult: int = 100):
    """L'instance QUE LA FABRIQUE PRODUIT -- jamais la classe instanciee a la main : `EffectFactory
    .create` rend un `BaseEffect` nu pour tout nom inconnu, et un `BaseEffect` nu a TOUS ses canaux
    muets. Passer par la fabrique exerce donc le routage du registre en plus de la classe."""
    from engine.entities.effects.factory import EffectFactory, EFFECT_CLASSES
    inst = EffectFactory.create({"name": effect_type.name, "effectType": int(effect_type),
                                 "source": source, "active": True}, mult, level)
    assert type(inst) is EFFECT_CLASSES[effect_type.name], (
        f"la fabrique ne route plus {effect_type.name} vers sa classe portee -- tous ses canaux "
        f"seraient muets, et chaque bras VRAI de ce fichier deviendrait un faux rouge")
    return inst


@pytest.mark.parametrize("et", (CD, WOTA), ids=("1443", "1445"))
def test_effet_au_registre_sur_le_canal_aura(et):
    """Les deux effets exposent `create_aura_defense_damage_malus_for_ally` et **PAS**
    `create_effect_damage_malus_for_defense`.

    Ce n'est pas un detail de style : les deux ont un `$$CreateTargetSelector`, donc
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` les
    evalue sur les CIBLES de leur selecteur. Les inscrire sur le canal du PORTEUR donnerait la
    reduction a la MoW elle-meme -- que le natif n'en fait beneficier dans aucun des deux cas."""
    from engine.entities.effects.base import BaseEffect

    inst = _instance(et)
    cls = type(inst)
    assert cls.create_aura_defense_damage_malus_for_ally \
        is not BaseEffect.create_aura_defense_damage_malus_for_ally, (
        f"{et.name} n'implemente pas le canal AURA -- il serait INERTE, sans erreur")
    assert cls.create_effect_damage_malus_for_defense \
        is BaseEffect.create_effect_damage_malus_for_defense, (
        f"{et.name} implemente le canal du PORTEUR : la MoW se donnerait a elle-meme une reduction "
        f"que le natif ne lui accorde JAMAIS (terme PERMISSIF)")
    # Les ordinaux ECRITS aux sites (ctor de l'effet, `GetEffectType` de l'ability).
    assert int(CD) == 0x5A3 and int(WOTA) == 0x5A5


# ================================================= B -- 1443 : les TROIS etages SEPARENT

def _ctx_1443(owner_team=1, tgt_team=1, tgt_rarity=Rarity.Mythic, tile_names=(STATUS,),
              t_pos=(2, 2)):
    """Le contexte que `aura_defense_damage_malus_from_units` construit, cle par cle.

    Ce sont EXACTEMENT les cles que les deux facades posent deja (`tgt_rarity` depuis #999-r3-r1,
    `tile_effects_by_pos` depuis #366-r1) : ce fichier n'en introduit AUCUNE pour 1443."""
    return {"owner_id": MOW_ID, "owner_team": owner_team, "owner_pos": None,
            "tgt_id": P1, "tgt_team": tgt_team, "tgt_rarity": tgt_rarity,
            "t_pos": t_pos, "tile_effects_by_pos": {t_pos: list(tile_names)}}


def test_1443_bras_vrai():
    """Ami MYTHIQUE sur une tuile portant un STATUS -> reduction. C'est le TEMOIN NON NUL sans
    lequel tous les contre-bras ci-dessous ne prouveraient rien."""
    eb = _instance(CD).create_aura_defense_damage_malus_for_ally(_ctx_1443())
    assert eb is not None, "le bras VRAI ne contribue rien -- les contre-bras ne separent alors RIEN"
    assert eb.kind == "PercentDecrease" and eb.value == PALIERS[3]


@pytest.mark.parametrize("mut,quoi", (
    ({"tgt_team": 2}, "`Friends(Owner, AllUnits(), 3)` : la cible n'est pas une ALLIEE"),
    ({"owner_team": None}, "equipe du porteur NON MESUREE -> gate FERME (tri-etat)"),
    ({"tgt_rarity": Rarity.Legendary}, "`UnitsWithRarity(., Mythic = 5, 3)` : rarete VOISINE"),
    ({"tgt_rarity": None}, "rarete NON MESUREE -> gate FERME, jamais permissif"),
    ({"tile_names": ()}, "`HasTileStatusEffect(Tiles(candidat))` : tuile NUE"),
    ({"tile_names": (NON_STATUS,)},
     "`LightCover` n'est PAS dans `StaticBattleRules.Effect$$IsTileStatusEffect`"),
    ({"tile_effects_absent": True}, "canal de tuile NON THREADE -> gate FERME"),
), ids=("equipe", "equipe-non-mesuree", "rarete-voisine", "rarete-non-mesuree",
        "tuile-nue", "tuile-non-status", "canal-tuile-absent"))
def test_1443_contre_bras(mut, quoi):
    ctx = _ctx_1443(**{k: v for k, v in mut.items() if k != "tile_effects_absent"})
    if mut.get("tile_effects_absent"):
        ctx["tile_effects_by_pos"] = None
    assert _instance(CD).create_aura_defense_damage_malus_for_ally(ctx) is None, quoi


def test_1443_la_rarete_voisine_est_bien_un_temoin():
    """Le contre-bras `rarete-voisine` ne vaut que si `Legendary != Mythic` ET que les DEUX sont des
    membres REELS du mirror -- sinon on aurait ecrit une comparaison qui ne peut pas echouer."""
    assert Rarity.Legendary != Rarity.Mythic
    assert int(Rarity.Mythic) == 5, "l'ordinal ECRIT au site du decompile est 5"


# ============================================================== C -- 1443 : la MAGNITUDE

@pytest.mark.parametrize("niveau,mult,attendu", (
    (1, 100, PALIERS[0]),
    (4, 100, PALIERS[3]),
    (4, 180, (PALIERS[3] * 180) // 100),
), ids=("L1", "L4", "L4-mult180"))
def test_1443_magnitude_suit_le_palier_et_le_multiplicateur(niveau, mult, attendu):
    """`ConfigVar(0x46 = dmgReductionPct, GetAbilityState(effet))`, `dmgReductionPct` etant DANS
    `variablesAffectedByRarityBonus` -- le multiplicateur MORD. Aucun scalaire fitte : le palier est
    relu au gameconfig par l'etage suivant."""
    eb = _instance(CD, level=niveau, mult=mult).create_aura_defense_damage_malus_for_ally(_ctx_1443())
    assert eb is not None and eb.value == attendu


@pytest.mark.parametrize("ability", ("ContemptuousDisregard", "WisdomOfTheAncients"))
def test_les_paliers_lus_ici_sont_ceux_du_gameconfig(ability):
    """Le tableau `PALIERS` de ce fichier n'est pas une valeur INVENTEE : il doit rester celui du
    gameconfig, sinon les etages B/C mesurent le test au lieu du port."""
    import gameconfig

    cfg = gameconfig.ability(ability) or {}
    variables = cfg.get("variables") or {}
    assert variables, f"aucune variable pour {ability} -- rien n'est mesure ici"
    assert list(variables.get("dmgReductionPct") or []) == PALIERS
    assert "dmgReductionPct" in (cfg.get("variablesAffectedByRarityBonus") or []), (
        "`dmgReductionPct` sort de `variablesAffectedByRarityBonus` : le multiplicateur cesserait "
        "de mordre, et l'etage C ci-dessus mentirait")


# ================================================ D -- 1445 : le resolveur COMBAT SEPARE

def _state_1445(rarity_by_id=None, hero_ids=(H,)):
    """Le montage de `probe_1042_wisdom_of_the_ancients_live.py`, transpose OFFLINE :

        equipe 1   P1 (1,1) - P2 (2,1) - P3 (3,1)     chaine adjacente
                   H  (5,7) - X  (6,7)                paire isolee, loin de la chaine
        equipe 2   FOE (0,7)                          contre-bras d'equipe

    `H` porte `UnitTrait.Hero`, les autres NON : c'est ce qui fait de `X` le temoin du noeud
    `UnitsWithTrait(., Hero)`, et de la chaine le temoin de l'adjacence.
    ⚠ Le PORTEUR (`MOW_ID`) n'a PAS de position -- c'est une MACHINE OF WAR."""
    rarity_by_id = dict(rarity_by_id or {})
    pos = {P1: (1, 1), P2: (2, 1), P3: (3, 1), H: (5, 7), X: (6, 7), FOE: (0, 7)}
    team = {P1: 1, P2: 1, P3: 1, H: 1, X: 1, FOE: 2}
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": f"u{uid}", "alive": True, "team": team[uid], "owner": team[uid],
         "pos": {"col": pos[uid][0], "row": pos[uid][1]}, "effects": []}
        for uid in pos]}
    ob = {"units": [{"squadId": uid, "hp": 9000, "hpMax": 9000} for uid in pos]}
    snap = {"rarityEnum": "idun.meta.Rarity", "units": [
        {"entityId": uid, "visualId": f"u{uid}", "entityType": ENTITY_TYPE_UNIT,
         "rarity": int(rarity_by_id.get(uid, Rarity.Mythic)),
         "traits": ([int(UnitTrait.Hero)] if uid in hero_ids else [])}
        for uid in pos]}
    st = load_state(dv, ob, snap, board=_board())
    # Le PORTEUR : une entite d'equipe 1 SANS `PositionComponent`, comme toute MACHINE OF WAR.
    # C'est CE FAIT (aucune position) que l'etage F transforme en equivalence du
    # `ConditionalSelector(IsMachine(Owner), ...)` -- il est donc pose ici EXPLICITEMENT.
    from engine.runner.components import OwnerComponent, PositionComponent
    ent = st.add_entity(MOW_ID)
    ent.add_component(OwnerComponent(team=1))
    assert ent.get_component(PositionComponent) is None, (
        "le porteur du montage a une position : ce n'est plus une MoW, et l'etage F ne mesure rien")
    return st


def test_1445_combat_bras_vrai_et_temoin_ecarte():
    """Chaine `P1-P2-P3` : chacun a un voisin MYTHIQUE... mais aucun n'est `Hero`. `H`/`X` : `X` a
    pour voisin `H`, MYTHIQUE **et** `Hero` -> `X` est PRIS, et `H` ne l'est pas (son seul voisin
    `X` n'est pas `Hero`). Un ensemble qui contiendrait TOUT LE MONDE ne separerait rien."""
    st = _state_1445()
    vus = DM.wisdom_of_the_ancients_target_ids(st, MOW_ID)
    assert vus is not None, "resolveur MUET : le montage ne mesure rien"
    assert X in vus, "le bras VRAI est vide -- les contre-bras ci-dessous ne prouveraient rien"
    assert H not in vus, "`H` n'a aucun voisin `Hero` : `UnitsWithTrait(., Hero)` ne separe pas"
    assert P1 not in vus and P2 not in vus and P3 not in vus, (
        "la chaine entre sans porteur de `Hero` : le noeud `UnitsWithTrait` est inerte")
    assert FOE not in vus, "`Friends(Owner, AllUnits(), 3)` ne separe pas les equipes"


def test_1445_combat_etage_rarete_exterieur():
    """`B = ValidCharacter(Friends(Owner, AllUnits(), 3))` -- la rarete du BENEFICIAIRE.
    `X` non-Mythique sort du set, alors que sa geometrie n'a pas bouge."""
    st = _state_1445(rarity_by_id={X: Rarity.Legendary})
    vus = DM.wisdom_of_the_ancients_target_ids(st, MOW_ID)
    assert X not in vus, "l'etage de rarete EXTERIEUR (sur B) n'est pas porte"


def test_1445_combat_etage_rarete_interieur():
    """`F = Filter(B, AmountIsGreaterThanZero(UnitsWithTrait(ValidCharacter(AdjacentFriends(
    <candidat>)), Hero)))` -- la rarete du VOISIN. `H` non-Mythique ne compte plus, donc `X` sort,
    alors que `X` lui-meme est reste Mythique ET que `H` est reste `Hero`.

    C'est le contre-bras qui distingue les DEUX etages de rarete : sans lui, un port qui n'aurait
    porte que l'exterieur passerait le test precedent."""
    st = _state_1445(rarity_by_id={H: Rarity.Legendary})
    vus = DM.wisdom_of_the_ancients_target_ids(st, MOW_ID)
    assert X not in vus, "l'etage de rarete INTERIEUR (sous le Filter) n'est pas porte"


def test_1445_combat_etage_trait_hero():
    """Le MEME montage sans aucun `Hero` : le set est VIDE. Temoin du noeud
    `UnitsWithTrait(., UnitTrait.Hero = 0x10, 3)`."""
    st = _state_1445(hero_ids=())
    assert DM.wisdom_of_the_ancients_target_ids(st, MOW_ID) == frozenset()


def test_1445_combat_adjacence_du_voisin_hero():
    """`H` deplace loin de `X` : `X` n'a plus de voisin, donc il sort. Temoin du noeud
    `AdjacentFriends(<candidat>)` -- la geometrie, isolee de la rarete et du trait."""
    from engine.runner.components import PositionComponent
    st = _state_1445()
    pc = st.get_entity(H).get_component(PositionComponent)
    pc.col, pc.row = 0, 0
    assert X not in DM.wisdom_of_the_ancients_target_ids(st, MOW_ID)


def test_1445_combat_tri_etat_du_resolveur():
    """Porteur inconnu / sans equipe -> `None` = NON MESURE, jamais un `frozenset()` qui se lirait
    << mesure, et personne >> (le lecteur FERME son gate sur `None` comme sur un set vide, mais la
    distinction est ce qui rend une panne de montage visible)."""
    st = _state_1445()
    assert DM.wisdom_of_the_ancients_target_ids(st, 999999) is None
    assert DM.wisdom_of_the_ancients_target_ids(st, None) is None


# ================================ E -- 1445 : la PREDICTION rend le MEME set (pas de fork)

class _StubScene:
    """Scene MINIMALE portant EXACTEMENT ce que le resolveur PREDICTION consomme.

    Ecrite en dur (et non derivee de `Scene`) pour la meme raison que le stub de
    `test_999r3r1_canal_rarete_aura_offline.py` : un stub qui herite du foyer ne peut plus montrer
    qu'un appelant a change de contrat."""

    def __init__(self, board, rarity_by_id=None, hero_ids=(H,), owner_pos=None):
        from engine.entities.unit_context import UnitContext
        rarity_by_id = dict(rarity_by_id or {})
        self.board = board
        self.pos_by_id = {P1: (1, 1), P2: (2, 1), P3: (3, 1), H: (5, 7), X: (6, 7), FOE: (0, 7)}
        if owner_pos is not None:
            self.pos_by_id[MOW_ID] = owner_pos
        self.team_by_id = {P1: 1, P2: 1, P3: 1, H: 1, X: 1, FOE: 2, MOW_ID: 1}
        self.hp_by_id = {uid: 9000 for uid in self.team_by_id}
        self.ctx_by_id = {
            uid: UnitContext(entity_id=uid, visual_id=f"u{uid}",
                             rarity=rarity_by_id.get(uid, Rarity.Mythic),
                             traits=([UnitTrait.Hero.name] if uid in hero_ids else []),
                             traits_measured=True)
            for uid in self.team_by_id}
        self.tile_effects_by_pos = {}
        self.vis_by_id = {uid: f"u{uid}" for uid in self.team_by_id}

    def ctx(self, uid):
        return self.ctx_by_id.get(uid)

    def pos(self, uid):
        return self.pos_by_id.get(uid)

    def team(self, uid):
        return self.team_by_id.get(uid)

    def hp(self, uid):
        return self.hp_by_id.get(uid)

    def effects(self, uid):
        return []


@pytest.mark.parametrize("mut", ({}, {"rarity_by_id": {X: Rarity.Legendary}},
                                 {"rarity_by_id": {H: Rarity.Legendary}}, {"hero_ids": ()}),
                         ids=("vrai", "rarete-exterieure", "rarete-interieure", "sans-hero"))
def test_1445_les_deux_faces_rendent_le_meme_set(mut):
    """UN noeud natif, DEUX substrats -- et ils doivent coincider bras par bras. Threader un seul
    cote laisserait l'autre INERTE EN SILENCE (la lecon de #999-r3-r1)."""
    from engine.playbook.prediction import _shared as SH

    combat = DM.wisdom_of_the_ancients_target_ids(_state_1445(**mut), MOW_ID)
    pred = SH.wisdom_of_the_ancients_target_ids(_StubScene(_board(), **mut), MOW_ID)
    assert combat is not None and pred is not None
    assert combat == pred, f"FORK de substrat : combat={sorted(combat)} prediction={sorted(pred)}"


def test_1445_le_bras_vrai_de_la_prediction_est_non_vide():
    """Assertionner son propre NON-VIDE : quatre ensembles vides seraient egaux, et l'etage E
    passerait pour vert sans rien mesurer."""
    from engine.playbook.prediction import _shared as SH

    assert SH.wisdom_of_the_ancients_target_ids(_StubScene(_board()), MOW_ID) == frozenset({X})


# ========== F -- 1445 : `A` VIDE sans position de porteur (le `ConditionalSelector` equivalent)

def test_1445_branche_A_vide_quand_le_porteur_n_a_pas_de_position():
    """LE GARDE DE L'EQUIVALENCE. Le port n'evalue PAS `ConditionalSelector(IsMachine(Owner), F,
    Unique(A + F))` : il rend `Unique(A + F)` inconditionnellement, ce qui n'est EXACT que parce
    que `IsMachine(Owner)` implique `EntityType.Machine`, donc aucune tuile, donc `A = {}`.

    Cet etage mesure les deux moities de l'implication :
      1. sans position, `A` est vide -- donc `Unique(A + F) == F` et les deux branches coincident ;
      2. AVEC une position (porteur ON-BOARD, cas de la GREFFE `--allow-unlisted-mythic`),
         `A` est NON VIDE -- donc la branche `ifFalse` est bien la seule observable, et le port la
         rend. Sans ce second bras, l'etage 1 pourrait etre vert sur un `A` toujours vide.

    Si un jour une entite pouvait etre MACHINE **et** positionnee, ce test ne rougirait pas seul --
    mais l'ecart deviendrait reel, et c'est ce que dit la docstring de
    `WisdomOfTheAncientsDamageReductionEffect`."""
    from engine.playbook.prediction import _shared as SH
    from engine.entities.pathfinding import board as _pf

    bd = _board()
    elev, neigh = _pf.elevations_by_pos(bd), _pf.adjacent_neigh_by_pos(bd)
    # 1. porteur SANS position (une MoW) -> A vide.
    sc = _StubScene(bd)
    assert SH._wisdom_valid_adjacent_friends(sc, MOW_ID, elev, neigh) == frozenset(), (
        "`AdjacentFriends(Owner)` n'est PAS vide sur un porteur sans tuile : l'equivalence qui "
        "justifie de ne pas porter le `ConditionalSelector` tombe")
    # 2. porteur ON-BOARD adjacent a la chaine -> A non vide, et son contenu ENTRE dans le set.
    sc2 = _StubScene(bd, owner_pos=(2, 2))
    a = SH._wisdom_valid_adjacent_friends(sc2, MOW_ID, elev, neigh)
    assert a, "le bras temoin de `A` est vide : l'etage 1 ci-dessus ne prouverait rien"
    assert a <= SH.wisdom_of_the_ancients_target_ids(sc2, MOW_ID), (
        "`Unique(A + F)` ne contient pas `A` : la branche `ifFalse` n'est pas portee")


# ================================ G -- les DEUX facades POSENT la cle du resolveur

def test_les_deux_facades_posent_la_cle_du_resolveur(monkeypatch):
    """Une cle non posee rend 1445 INERTE, sans erreur ni trace -- exactement le profil de panne
    que #999-r3-r1 a mesure sur `att_rarity`. On capture le ctx REELLEMENT construit par chaque
    facade, jamais un dict ecrit ici."""
    from engine.entities.effects.loki.damage_reduction import CTX_WISDOM_TARGET_IDS_OF
    from engine.playbook.prediction import _shared as SH
    from engine.entities.effects import DamageModifiers

    # --- face COMBAT
    vus = []
    reel = DM.aura_defense_damage_malus_from_units

    def _spy(carriers, ctx):
        vus.append(ctx)
        return reel(carriers, ctx)

    monkeypatch.setattr(DM, "aura_defense_damage_malus_from_units", _spy)
    st = _state_1445()
    # Un PORTEUR d'effet est necessaire pour que la boucle construise son ctx (`if carriers`) --
    # une VRAIE instance de la fabrique, pas un stub : un objet sans le contrat de `BaseEffect`
    # ferait echouer le montage AVANT la construction du ctx, et le test accuserait le port.
    st.effects.by_unit.setdefault(P3, []).append(_instance(WOTA, source=P3))
    DM.defender_modifiers(st, X, 9000, is_melee=True, attacker_id=FOE)
    assert vus, "l'agregateur d'aura DEFENSE (combat) n'a pas ete appele -- montage muet"
    assert CTX_WISDOM_TARGET_IDS_OF in vus[0], (
        "cle ABSENTE cote COMBAT : 1445 serait INERTE en combat, sans erreur")
    assert callable(vus[0][CTX_WISDOM_TARGET_IDS_OF])

    # --- face PREDICTION : la cle est posee au MEME nom, par le MEME foyer de nommage.
    src = Path(SH.__file__).read_text(encoding="utf-8", errors="replace")
    assert "_WOTA_CTX_TARGET_IDS:" in src, (
        "la face PREDICTION ne pose plus la cle : la face DECISION serait inerte")
    assert "CTX_WISDOM_TARGET_IDS_OF as _WOTA_CTX_TARGET_IDS" in src, (
        "la face PREDICTION a FORKE le nom de la cle au lieu de l'importer du foyer")
    assert DamageModifiers is not None      # l'import ci-dessus garde le contrat du module


# ==================================================== H -- la FACE NATIVE des contributions

# =============== I -- `GetAbilityState(effet)` : d'ou vient le NIVEAU, et d'ou il ne vient PAS

@pytest.mark.parametrize("et", (CD, WOTA), ids=("1443", "1445"))
def test_aucun_repli_sur_le_niveau_de_stack(et):
    """LE BUG QUE LA MESURE LIVE A TROUVE, FIGE ICI (#1042-r1).

    Le port lisait `self.ability_level if ... else self.level`. Or `level` est le niveau de **STACK**
    de l'effet (`decisionView.effects[].level`), pas un niveau d'ability -- et il vaut justement
    `1` sur ces deux instances. MESURE LIVE (runner `mow`, `WisdomOfTheAncients:4`, board MC1_67) :
    ce repli lisait `dmgReductionPct[1] = 10` et rendait `x0.90` contre `x0.80` natif, soit une
    DEMI-reduction -- un nombre plausible et FAUX, que rien d'offline ne montrait.

    L'arbitrage retenu est celui de `MastersOfManoeuvreEffect` (meme famille, meme variable, meme
    fabrique) : `AbilityState` non mesure -> `None`, l'effet est INERTE. Une sous-prediction NOMMEE
    vaut mieux qu'une magnitude devinee."""
    from engine.entities.effects.factory import EffectFactory

    # Instance telle que la capture LIVE la produit : `level` (stack) = 1, AUCUN `ability_level`.
    inst = EffectFactory.create({"name": et.name, "effectType": int(et), "source": MOW_ID,
                                 "active": True, "level": 1}, 180, None)
    assert inst.ability_level is None, "le montage ne mesure rien : l'instance porte deja un niveau"
    assert inst.level == 1, "le niveau de STACK n'est pas celui que la capture live publie"
    ctx = (_ctx_1443() if et is CD
           else {"owner_id": MOW_ID, "tgt_id": P1,
                 "wisdom_of_the_ancients_target_ids_of": lambda _oid: frozenset({P1})})
    assert inst.create_aura_defense_damage_malus_for_ally(ctx) is None, (
        f"{et.name} contribue SANS `AbilityState` : le repli sur le niveau de STACK est revenu, et "
        f"il lit `dmgReductionPct[1]` la ou le natif lit le palier TERTIAIRE reel")


@pytest.mark.parametrize("et,ability", ((CD, "ContemptuousDisregard"),
                                        (WOTA, "WisdomOfTheAncients")),
                         ids=("1443", "1445"))
def test_le_callable_d_etat_d_ability_prime_sur_l_instance(et, ability):
    """`GetAbilityState(effet)` interroge la SOURCE par le foyer #357, et ce canal PRIME sur le
    couple bake de l'instance -- il porte l'etat TERTIAIRE (`1..4 / 100`), l'instance peut porter
    celui des PASSIFS (`50 / 180`) quand aucun re-bake n'a eu lieu."""
    from engine.entities.effects.factory import EffectFactory
    from engine.entities.effects.loki.damage_reduction import CTX_TERTIARY_ABILITY_STATE_OF

    vus = []

    def _etat(oid, nom):
        vus.append((oid, nom))
        return (4, 100)

    inst = EffectFactory.create({"name": et.name, "effectType": int(et), "source": MOW_ID,
                                 "active": True, "level": 1}, 180, 50)   # PASSIFS : 50 / 180
    ctx = (_ctx_1443() if et is CD
           else {"owner_id": MOW_ID, "tgt_id": P1,
                 "wisdom_of_the_ancients_target_ids_of": lambda _oid: frozenset({P1})})
    ctx[CTX_TERTIARY_ABILITY_STATE_OF] = _etat
    eb = inst.create_aura_defense_damage_malus_for_ally(ctx)
    assert vus == [(MOW_ID, ability)], (
        f"le callable n'est pas interroge avec (SOURCE, {ability!r}) : vus={vus}")
    assert eb is not None and eb.value == PALIERS[3], (
        f"le couple TERTIAIRE (4/100) n'a pas prime : value={getattr(eb, 'value', None)} "
        f"(attendu {PALIERS[3]}, le palier 4 -- 50/180 aurait donne {PALIERS[3] * 180 // 100})")


def test_scene_expose_l_etat_par_triggered_et_est_tri_etat():
    """`Scene.triggered_ability_state` -- face DECISION du foyer #357, substrat
    `unitAbilityStates`. C'est ce qui manquait : `Scene.ability_state` ne porte que les ACTIVES
    (son capteur `combatSnapshot.abilityStates` publie `kind: active`), donc les deux auras etaient
    INERTES cote DECISION."""
    from engine.playbook.scene import Scene
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.snapshot import triggered_ability_states_by_unit

    # Le PARSING, sur la forme EXACTE du capteur (`raw[0]` = l'ordinal, `level` / `mult` a plat).
    payload = {"units": [{"entityId": MOW_ID, "triggered": [
        {"level": 4, "mult": 100, "raw": [int(TriggeredAbilityType.WisdomOfTheAncients), 0, 0, 0]},
        {"level": 50, "mult": 180, "raw": [1257, 0, 0, 0]},
        {"level": None, "mult": 100, "raw": [1258, 0, 0, 0]},      # niveau NON MESURE -> ecarte
    ]}]}
    par_unit = triggered_ability_states_by_unit(payload)
    assert par_unit[MOW_ID][int(TriggeredAbilityType.WisdomOfTheAncients)] == (4, 100)
    assert par_unit[MOW_ID][1257] == (50, 180), "les PASSIFS restent lisibles, sous leur propre id"
    assert 1258 not in par_unit[MOW_ID], "un niveau NON MESURE ne doit poser AUCUNE entree"

    def _scene_nue(**kw):
        """`Scene` MINIMALE -- toutes les tables vides sauf celle qu'on mesure. On passe par le
        vrai constructeur (et non un stub) parce que c'est l'ACCESSEUR de `Scene` qui est teste."""
        return Scene(units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, ctx_by_id={},
                     armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                     vis_by_id={}, eff_state=None, **kw)

    sc = _scene_nue(trigstate_by_id=par_unit)
    assert sc.triggered_ability_state(MOW_ID, "WisdomOfTheAncients") == (4, 100)
    assert sc.triggered_ability_state(MOW_ID, "ContemptuousDisregard") == (None, None), \
        "ability non montee -> NON MESURE, jamais un couple devine"
    assert sc.triggered_ability_state(999, "WisdomOfTheAncients") == (None, None)
    assert sc.triggered_ability_state(MOW_ID, "PasUnMembreDeLEnum") == (None, None), \
        "nom hors du mirror -> NON MESURE (la resolution passe par le mirror, pas par un ordinal)"
    assert _scene_nue().triggered_ability_state(MOW_ID, "WisdomOfTheAncients") == (None, None), \
        "canal muet -> NON MESURE ; le lecteur retombe alors sur le couple bake de l'instance"


# ==================================================== H -- la FACE NATIVE des contributions

@pytest.mark.parametrize("et", (CD, WOTA), ids=("1443", "1445"))
def test_face_native_defenseur(et):
    """Les deux classes derivent de `IdunBattle.Entities.Effects.BaseEffect` et implementent
    `CreateEffectDamageMalusForDefense` EN PROPRE -- pas le forwarder
    `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`,
    que seul `CalculateAttackerModifiersForPrediction` invoque. La face est donc DEFENSEUR, et le
    routage de `add_modifier` en depend (#437-r1-r1-r1)."""
    assert type(_instance(et)).AURA_DEFENSE_MALUS_NATIVE_FACE == "defender"
