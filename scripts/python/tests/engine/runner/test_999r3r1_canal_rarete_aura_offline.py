"""#999-r3-r1 -- CLIQUET du FOYER de rarete des canaux de degat, 100 % OFFLINE.

Ce que ces etages verrouillent, et pourquoi ils existent SEPAREMENT de `test_999r3_canal_rarete_*`
(#999-r3, qui garde le CANAL : `UnitContext.rarity`, `HasRarity`, `UnitsWithRarity`) : le canal peut
repondre et le CONTEXTE du coup ne pas le porter. C'est exactement l'etat qu'a mesure #999-r3-r1 --
`combatSnapshot.units[].rarity` etait consomme depuis #999-r3, et les quatre `ctx` des canaux de
degat n'avaient AUCUNE cle de rarete, donc tout gate `HasRarity` monte dans un effet aurait ete
inevaluable, ou pire, PERMISSIF si on l'avait omis.

Etage 1 -- les DEUX foyers de lecture (COMBAT / PREDICTION) sont TRI-ETAT et lisent le MEME champ.
Etage 2 -- les ctx du COMBAT portent leur cle : aura ATTAQUE `att_rarity`, aura DEFENSE
           `tgt_rarity`, self DEFENSEUR `rarity`. MESURE en interceptant le consommateur, pas en
           relisant le source.
Etage 3 -- le ctx de la face PREDICTION (aura ATTAQUE) porte `att_rarity`, meme cle, meme valeur.
Etage 4 -- `HyperCorrosiveAcid_ExtraDamagePct` (1448) : UN bras VRAI et QUATRE contre-bras, dont
           chacun eteint UN conjoint. Un bras vrai seul ne prouverait rien (le gate pourrait etre
           ferme pour une autre raison) ; un contre-bras seul non plus (il pourrait etre eteint par
           le mauvais conjoint).
Etage 5 -- le blocage RESIDUEL (`#999-r3-r1-r1`) est FIGE : une MoW porteuse d'aura n'entre dans
           l'univers de porteurs d'AUCUN des deux agregateurs. Sans ce cran, un lecteur croirait le
           threading suffisant pour les six effets, alors qu'il n'en debloque qu'UN.
Etage 6 -- la MAIN TILE de l'ATTAQUANT est dans `tile_effects_by_pos` du ctx d'aura ATTAQUE
           (`UnitsOnTilesWithEffect` lit la tuile de l'element du selecteur, pas celle de la cible).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest                                                                   # noqa: E402

import hexgeo                                                                   # noqa: E402
from engine.entities.pathfinding.board import Board                             # noqa: E402
from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.rarity import Rarity                                       # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                         # noqa: E402
from engine.runner import damage_model as DM                                    # noqa: E402
from engine.runner.snapshot import load_state                                   # noqa: E402
from engine.runner.components import StatsComponent                             # noqa: E402

DECLENCHEUR = {
    "chemins": (
        # Les DEUX foyers de lecture de la rarete et les QUATRE ctx qu'ils alimentent.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        # Le canal en amont : mirror d'enum, tri-etat, seed du `UnitContext`.
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/runner/snapshot.py",
        # Le registre et la classe portee (1448), plus les agregateurs eux-memes.
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/loki/extra_damage.py",
        # Le substrat des deux autres conjoints de 1448 (traits, equipes).
        "scripts/python/engine/entities/traits/unit_trait.py",
        # Le blocage RESIDUEL que l'etage 5 fige, et sa mesure.
        "scripts/python/probe_999r3r1_porteurs_aura_mow.py",
        "scripts/python/engine/playbook/scene.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "L'etage 4 lit le GAMECONFIG (`HyperCorrosiveAcid.extraDmgPct`, quatre paliers), qui "
              "se perime SEPAREMENT du build ; le fichier fige des ORDINAUX au site (1448, 1122, "
              "`Rarity.Mythic = 5`, `UnitTrait.Hero = 0x10`), qu'un renumerotage rendrait faux sans "
              "toucher aucun des chemins ci-dessus ; et l'etage 5 garde une ABSENCE (les MoW hors "
              "de l'univers de porteurs d'aura), donc une reparation n'importe ou dans le seed ou "
              "dans les agregateurs peut le concerner.",
}

COLS, ROWS = 6, 6
ATT_ID, TGT_ID, ALLY_ID = 10, 20, 30
#: `EffectType` 0x5a8 = 1448 -- l'effet pose par la mythique `HyperCorrosiveAcid` sur l'ENNEMI.
ACID = EffectType.HyperCorrosiveAcid_ExtraDamagePct
#: `AbilityVariableType` 0xa = extraDmgPct ; gameconfig `HyperCorrosiveAcid` = [10, 13, 16, 20].
PALIERS = [10, 13, 16, 20]
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


#: Effet BENIN pose sur l'ALLIE de l'attaquant. Il ne sert qu'a UNE chose : faire de cet allie un
#: PORTEUR, sans quoi `_apply_ally_attack_damage_auras` sort AVANT de construire son `ctx`
#: (`if not carriers: return`) et le test mesurerait un contexte qui n'existe pas. `Markerlight`
#: (1122) est choisi parce que son unique canal de degat est gate `HasFaction(actor, 9 = T'au)` et
#: `IsRangedAttack` : sur un attaquant Imperial en melee il ne contribue RIEN, donc il ne peut pas
#: fabriquer un nombre. C'est un TEMOIN de presence, pas un terme.
EFFET_TEMOIN = EffectType.Markerlight


def _state(att_rarity=Rarity.Mythic, tgt_rarity=Rarity.Mythic):
    """Etat OFFLINE : un attaquant (equipe 1), une cible (equipe 2), un allie PORTEUR (equipe 1)."""
    dv = {"currentPlayer": 1, "units": [
        {"id": ATT_ID, "visualId": "ultraMarneus", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": TGT_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 2, "row": 1}, "effects": []},
        {"id": ALLY_ID, "visualId": "orksKillaKan", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 4, "row": 4},
         "effects": [{"id": 7200, "name": EFFET_TEMOIN.name, "effectType": int(EFFET_TEMOIN),
                      "source": ALLY_ID, "active": True}]},
    ], "effects": [
        {"id": 7200, "name": EFFET_TEMOIN.name, "effectType": int(EFFET_TEMOIN),
         "ownerId": ALLY_ID, "source": ALLY_ID, "active": True, "targetIds": []},
    ]}
    ob = {"units": [{"squadId": u["id"], "hp": 9000, "hpMax": 9000} for u in dv["units"]]}
    snap = {"rarityEnum": "idun.meta.Rarity", "units": [
        {"entityId": ATT_ID, "visualId": "ultraMarneus", "entityType": ENTITY_TYPE_UNIT,
         **({"rarity": int(att_rarity)} if att_rarity is not None else {})},
        {"entityId": TGT_ID, "visualId": "necroWarden", "entityType": ENTITY_TYPE_UNIT,
         **({"rarity": int(tgt_rarity)} if tgt_rarity is not None else {})},
        {"entityId": ALLY_ID, "visualId": "orksKillaKan", "entityType": ENTITY_TYPE_UNIT,
         "rarity": int(Rarity.Mythic)},
    ]}
    return load_state(dv, ob, snap, board=_board())


# =============================== Etage 1 -- les DEUX foyers de lecture ==========================

def test_foyer_combat_lit_le_champ_et_est_tri_etat():
    """`damage_model._unit_rarity` -- MEME substrat que la cle `rarity` du dict d'unite DSL."""
    st = _state(att_rarity=Rarity.Epic, tgt_rarity=Rarity.Mythic)
    assert DM._unit_rarity(st, ATT_ID) == Rarity.Epic
    assert DM._unit_rarity(st, TGT_ID) == Rarity.Mythic
    assert DM._unit_rarity(st, None) is None, "uid absent -> NON MESURE"
    assert DM._unit_rarity(st, 9999) is None, "entite inexistante -> NON MESURE"
    # Une entite SANS `StatsComponent` (un cadavre : `combatSnapshot` filtre les morts) : `None`,
    # jamais `Rarity.Common` -- un repli sur `Common` ferait passer un gate `HasRarity(Common)`.
    st.get_entity(ALLY_ID)._components.pop(StatsComponent, None)
    assert DM._unit_rarity(st, ALLY_ID) is None
    assert DM._unit_rarity(st, ALLY_ID) is not Rarity.Common


def test_foyer_prediction_est_le_pendant_exact():
    """`playbook/prediction/_shared._entity_rarity` -- meme tri-etat, meme lecture (`ctx.rarity`)."""
    from engine.playbook.prediction._shared import _entity_rarity
    from engine.entities.unit_context import UnitContext

    class _Sc:
        def __init__(self, table):
            self._t = table

        def ctx(self, uid):
            return self._t.get(uid)

    sc = _Sc({ATT_ID: UnitContext(entity_id=ATT_ID, rarity=Rarity.Epic),
              TGT_ID: UnitContext(entity_id=TGT_ID)})
    assert _entity_rarity(sc, ATT_ID) == Rarity.Epic
    assert _entity_rarity(sc, TGT_ID) is None, "ctx sans rarete -> NON MESURE"
    assert _entity_rarity(sc, 9999) is None, "uid hors des tables -> NON MESURE"
    assert _entity_rarity(sc, None) is None


# ================= Etage 2 -- les TROIS ctx du COMBAT portent leur cle de rarete ================

def _capture(monkeypatch, nom):
    """Intercepte un consommateur de `damage_model` et rend la liste des ctx recus.

    ⚠ FORME B DE MORSURE : `damage_model` importe ces symboles au niveau module
    (`from ..entities.effects import ...`), donc le call-site lit un GLOBAL du module -- patcher
    l'attribut de `engine.runner.damage_model` mord. Patcher `engine.entities.effects.<nom>` ne
    mordrait PAS (le binding est deja gele)."""
    vus = []
    reel = getattr(DM, nom)

    def _spy(*a, **kw):
        # aura_*: (carriers, ctx) ; build_defender_modifiers_from_effects: kwarg `attacker_ctx`
        vus.append(a[1] if len(a) > 1 and isinstance(a[1], dict) else kw.get("attacker_ctx"))
        return reel(*a, **kw)

    monkeypatch.setattr(DM, nom, _spy)
    return vus


def test_ctx_aura_attaque_porte_att_rarity(monkeypatch):
    """`create_aura_attack_damage_bonus_for_ally` -- le BENEFICIAIRE est l'ATTAQUANT, donc un etage
    `UnitsWithRarity(...)` du `$$CreateTargetSelector` se lit sur `att_id`."""
    st = _state(att_rarity=Rarity.Epic, tgt_rarity=Rarity.Mythic)
    vus = _capture(monkeypatch, "aura_attack_damage_bonus_from_allies")
    DM.attacker_modifiers(st, ATT_ID, 9000, is_ranged=False, target_id=TGT_ID)
    assert vus, "l'agregateur d'aura ATTAQUE n'a pas ete appele -- le montage ne mesure rien"
    ctx = vus[0]
    assert "att_rarity" in ctx, "cle ABSENTE : tout gate `HasRarity(Caster, ...)` d'aura est muet"
    assert ctx["att_rarity"] == Rarity.Epic


def test_ctx_aura_defense_porte_tgt_rarity(monkeypatch):
    """`create_aura_defense_damage_malus_for_ally` -- le BENEFICIAIRE est la CIBLE."""
    st = _state(att_rarity=Rarity.Mythic, tgt_rarity=Rarity.Epic)
    vus = _capture(monkeypatch, "aura_defense_damage_malus_from_units")
    DM.defender_modifiers(st, TGT_ID, 9000, is_melee=True, attacker_id=ATT_ID)
    assert vus, "l'agregateur d'aura DEFENSE n'a pas ete appele -- le montage ne mesure rien"
    ctx = vus[0]
    assert "tgt_rarity" in ctx, "cle ABSENTE : tout gate `UnitsWithRarity` d'aura defense est muet"
    assert ctx["tgt_rarity"] == Rarity.Epic


def test_attacker_ctx_du_canal_defenseur_porte_rarity(monkeypatch):
    """`create_effect_damage_malus_for_defense` -- `HasRarity(Caster@+0x48, ...)`, donc la rarete de
    l'ATTAQUANT, sous la cle SANS prefixe (convention de ce ctx : `team`/`traits`/`faction`)."""
    st = _state(att_rarity=Rarity.Epic, tgt_rarity=Rarity.Mythic)
    vus = _capture(monkeypatch, "build_defender_modifiers_from_effects")
    DM.defender_modifiers(st, TGT_ID, 9000, is_melee=True, attacker_id=ATT_ID)
    assert vus and vus[0] is not None, "montage muet : aucun `attacker_ctx` capture"
    assert "rarity" in vus[0], "cle ABSENTE : le gate `HasRarity` de 1448 serait PERMISSIF"
    assert vus[0]["rarity"] == Rarity.Epic


# ================= Etage 3 -- la face PREDICTION porte la MEME cle, MEME valeur =================

class _StubScene:
    """Scene MINIMALE : exactement les accesseurs que `_apply_ally_attack_dmg_bonus` consomme.

    Un stub et non une vraie `Scene` parce que la mesure porte sur le CONTEXTE construit, pas sur
    l'hydratation -- et qu'une `Scene` reelle exige un `predictor` complet, donc un montage qui
    pourrait masquer l'absence de la cle sous une autre panne."""

    def __init__(self, rarity_by_id, board):
        from engine.entities.unit_context import UnitContext
        self.board = board
        self.pos_by_id = {ATT_ID: (1, 1), TGT_ID: (2, 1), ALLY_ID: (4, 4)}
        self.team_by_id = {ATT_ID: 1, TGT_ID: 2, ALLY_ID: 1}
        self.hp_by_id = {ATT_ID: 9000, TGT_ID: 9000, ALLY_ID: 9000}
        self.vis_by_id = {ATT_ID: "ultraMarneus", TGT_ID: "necroWarden", ALLY_ID: "orksKillaKan"}
        self.ctx_by_id = {uid: UnitContext(entity_id=uid, visual_id=self.vis_by_id[uid],
                                           rarity=rarity_by_id.get(uid))
                          for uid in self.vis_by_id}
        self.tile_effects_by_pos = {}

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

    def effect_carrier_ids(self, exclude=None):
        """#999-r3-r1-r1 -- l'UNIVERS de porteurs que consomment desormais les trois boucles
        d'aura (au lieu de `pos_by_id`), parce que le natif itere l'ETAT BOARD-WIDE et n'ecarte
        AUCUN porteur par sa position. Ce stub n'a aucune entite hors-plateau : il rend donc
        exactement ce que rendait `pos_by_id`, et ce qui est mesure ici reste le CONTEXTE.
        ⚠ Il est ecrit EN DUR plutot que delegue a `Scene` : un stub qui herite du foyer ne peut
        plus montrer qu'un appelant a change de contrat -- or c'est exactement ce qu'il a montre
        (AttributeError) quand le foyer a bouge."""
        return [uid for uid in self.pos_by_id if uid != exclude]

    def total_attacks_made(self, uid):
        return 0

    def adjacent_enemy_ids(self, uid):
        return ()

    def is_machine(self, uid):
        """#1036-r2 -- `IsMachine(Owner)` du `ConditionalSelector` de
        `CabalOfSorcerers_ExtraDamagePctEffect`, que `_apply_ally_attack_dmg_bonus` publie
        desormais dans son ctx. C'est EXACTEMENT le mecanisme que le commentaire d'
        `effect_carrier_ids` ci-dessus decrit : le stub a montre le changement de contrat par un
        `AttributeError`, il ne l'a pas absorbe en silence.

        Aucune entite de ce stub n'est une Machine -> `False` MESURE (jamais `None`, qui dirait
        << je n'ai pas regarde >> et ouvrirait la branche `ifFalse` du selecteur)."""
        return False


def test_ctx_aura_attaque_prediction_porte_att_rarity(monkeypatch):
    """Pendant exact de l'etage 2 sur l'autre face : threader un seul bout laisserait l'autre INERTE
    EN SILENCE (c'est le ⚠ explicite de `#999-r3-r1`)."""
    from engine.playbook.prediction import _shared as SH
    from engine.entities.effects import DamageModifiers
    vus = []
    reel = SH.aura_attack_damage_bonus_from_allies

    def _spy(carriers, ctx):
        vus.append(ctx)
        return reel(carriers, ctx)

    monkeypatch.setattr(SH, "aura_attack_damage_bonus_from_allies", _spy)
    sc = _StubScene({ATT_ID: Rarity.Epic, TGT_ID: Rarity.Mythic, ALLY_ID: Rarity.Mythic}, _board())
    SH._apply_ally_attack_dmg_bonus(DamageModifiers(), sc, ATT_ID, (1, 1), True, None,
                                    tgt_id=TGT_ID)
    assert vus, "l'agregateur d'aura ATTAQUE (prediction) n'a pas ete appele"
    assert "att_rarity" in vus[0], "cle ABSENTE cote PREDICTION : la face DECISION serait inerte"
    assert vus[0]["att_rarity"] == Rarity.Epic


# ================ Etage 4 -- 1448 : un bras VRAI et QUATRE contre-bras ==========================

def _acid(source: int, level: int = 1):
    """Instance de 1448 telle que la FABRIQUE la produit -- c'est ce qui exerce le routage du
    registre en plus de la classe (`EffectFactory.create` rend un `BaseEffect` nu pour tout nom
    inconnu, et un `BaseEffect` nu a TOUS ses canaux muets : le bras vrai le verrait).

    `source` = `EffectComponent.SourceUnit @+0x10` = le POSEUR (la MoW Biovore en live) ;
    `level` = l'`AbilityState` BAKE a la pose (`EffectComponent+0x18`, #382/#1038), pour une
    TERTIAIRE `1..4`."""
    from engine.entities.effects.factory import EffectFactory, EFFECT_CLASSES
    inst = EffectFactory.create({"name": ACID.name, "effectType": int(ACID),
                                 "source": source, "active": True}, 100, level)
    assert type(inst) is EFFECT_CLASSES[ACID.name], (
        "la fabrique ne route plus 1448 vers sa classe portee -- tous ses canaux seraient muets")
    return inst


def _attacker_ctx(monkeypatch, st, traits):
    """L'`attacker_ctx` QUE LE FOYER CONSTRUIT (capture par interception), jamais un dict fabrique
    ici : un ctx ecrit a la main mesurerait le test et pas le port.

    `traits` est ecrit dans le `UnitContext` de l'attaquant -- la SEULE source que lit
    `target_trait_names` -- et non dans le ctx."""
    vus = _capture(monkeypatch, "build_defender_modifiers_from_effects")
    sc = st.get_entity(ATT_ID).get_component(StatsComponent)
    sc.ctx.traits = tuple(traits)
    sc.ctx.traits_measured = True
    DM.defender_modifiers(st, TGT_ID, 9000, is_melee=True, attacker_id=ATT_ID)
    assert vus and vus[0] is not None
    return vus[0]


def test_1448_bras_vrai(monkeypatch):
    """Attaquant MYTHIC + HERO + allie de la SOURCE de l'effet -> `+extraDmgPct %` sur le degat RECU."""
    st = _state(att_rarity=Rarity.Mythic)
    ctx = _attacker_ctx(monkeypatch, st, [UnitTrait.Hero.name])
    eb = _acid(ALLY_ID, 1).create_effect_damage_malus_for_defense(True, None, ctx)
    assert eb is not None, "bras VRAI muet : le gate refuse pour une raison qui n'est pas mesuree"
    assert eb.kind == "PercentIncrease"
    assert eb.owner_is_caster is False, "owner = le DEFENSEUR (l'effet vit sur la cible)"
    assert int(eb.value) == PALIERS[0], (
        "palier TERTIAIRE 1 attendu (`ConfigVar(extraDmgPct)` indexe par l'`AbilityState` BAKE)")
    # Le palier SUIT le niveau bake : une magnitude figee passerait le bras vrai sans rien prouver.
    eb4 = _acid(ALLY_ID, 4).create_effect_damage_malus_for_defense(True, None, ctx)
    assert int(eb4.value) == PALIERS[3]
    # `ConfigVar` sans `AbilityState` -> AUCUNE contribution (<< present != applique >>).
    assert _acid(ALLY_ID, None).create_effect_damage_malus_for_defense(True, None, ctx) is None


@pytest.mark.parametrize("rarete", [Rarity.Epic, Rarity.Legendary, None])
def test_1448_contre_bras_rarete(monkeypatch, rarete):
    """`HasRarity(Caster, Mythic)` -- une rarete AUTRE, ou NON MESUREE, eteint le bonus.

    Le troisieme cas (`None`) est le plus important : c'est la degradation RESTRICTIVE NOMMEE. Un
    port qui rabattrait le non-mesure sur `Rarity.Common` puis testerait `!= Mythic` passerait ce
    cas ; un port qui OMETTRAIT le gate accorderait le bonus a TOUT Hero ami de la source."""
    st = _state(att_rarity=rarete)
    ctx = _attacker_ctx(monkeypatch, st, [UnitTrait.Hero.name])
    assert ctx.get("rarity") == rarete, "le foyer n'a pas propage la rarete du montage"
    assert _acid(ALLY_ID, 1).create_effect_damage_malus_for_defense(True, None, ctx) is None


def test_1448_contre_bras_pas_hero(monkeypatch):
    """`HasTrait(Caster, 0x10 = UnitTrait.Hero)` -- un attaquant Mythic SANS le trait ne l'a pas."""
    st = _state(att_rarity=Rarity.Mythic)
    ctx = _attacker_ctx(monkeypatch, st, [UnitTrait.Psyker.name])
    assert _acid(ALLY_ID, 1).create_effect_damage_malus_for_defense(True, None, ctx) is None


def test_1448_contre_bras_attaquant_ennemi_de_la_source(monkeypatch):
    """`AreFriends(Caster, EffectSource(Effect))` -- l'attaquant doit etre allie du BIOVORE.

    Ici la source de l'effet est la CIBLE elle-meme (equipe 2), donc l'attaquant (equipe 1) n'en est
    pas l'allie. Sans ce conjoint, l'effet bonifierait n'importe quel Mythic Hero, y compris les
    allies de la victime."""
    st = _state(att_rarity=Rarity.Mythic)
    ctx = _attacker_ctx(monkeypatch, st, [UnitTrait.Hero.name])
    assert _acid(TGT_ID, 1).create_effect_damage_malus_for_defense(True, None, ctx) is None
    # Source INCONNUE du ctx (`team_by_id` muet) -> gate FERME, jamais accorde par defaut.
    assert _acid(9999, 1).create_effect_damage_malus_for_defense(True, None, ctx) is None
    assert _acid(None, 1).create_effect_damage_malus_for_defense(True, None, ctx) is None


def test_1448_face_native_est_attaquant():
    """`...HyperCorrosiveAcid_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` = slot 0x16 ->
    accumulateur ATTAQUANT, malgre le trigger `get_OwnerIsTarget` et le canal PORT defenseur.
    Canal POURCENT, donc l'attribution a une consequence arithmetique (un `Fix64.Round` par
    accumulateur non nul)."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    assert EFFECT_CLASSES[ACID.name].DEFENSE_MALUS_NATIVE_FACE == "attacker"


# ============ Etage 5 -- les porteurs MoW ENTRENT, sur les DEUX faces (#999-r3-r1-r1) ==========

def test_une_mow_porteuse_d_aura_entre_dans_l_univers_des_porteurs():
    """REQUALIFIE -- ce cran a ROUGI, et il a eu RAISON.

    Etat d'AVANT : il figeait le blocage `#999-r3-r1-r1` (<< une MoW n'entre dans l'univers de
    porteurs d'AUCUN des deux agregateurs, sur AUCUNE des deux faces >>), pour que la fermeture de
    `#999-r3-r1` ne se lise pas comme << les six effets sont debloques >> alors qu'un seul l'etait.
    Il etait ecrit pour rougir le jour de la reparation. Il a rougi ce jour-la.

    Etat d'AUJOURD'HUI. La cause etait un ARTEFACT du port, sur QUATRE sites :
      * COMBAT   -- `damage_model._apply_ally_attack_damage_auras` et `defender_modifiers`
        exigeaient un `PositionComponent` du PORTEUR (`if oc is None or pc is None: continue`),
        que `snapshot._load_machines` ne pose JAMAIS ;
      * DECISION -- `scene.step_context` seedait son `EffectsState` depuis `dv["units"]` seulement
        (le canal `dv["mows"][].effects` EXISTE pourtant : `rpc-decision.ts` l'assemble par
        `effectsByUnit.get(m.casterId)`), et les trois boucles de porteurs iteraient
        `scene.pos_by_id`, ou une MoW n'entre jamais.
    Le natif, lui, itere une `List<KeyValuePair<entite, List<effet>>>` de l'ETAT, BOARD-WIDE
    (`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` et son
    jumeau ATTAQUE) : il ne lit AUCUNE position pour decider qui entre.

    Ce que ce cran garde maintenant : les DEUX faces, ENSEMBLE. Reparer une seule aurait cree le
    fork prediction/combat que #197 et #950-r2 ont deja paye -- c'est pourquoi les quatre
    assertions sont dans le MEME test : aucune ne peut passer seule."""
    import probe_999r3r1_porteurs_aura_mow as P
    _st, f = P.mesurer()
    assert f["mow_entite"] and f["mow_porte_l_aura"], "montage degenere : rien n'est mesure"
    assert f["mow_rarete_mesuree"], "la rarete d'une MoW EST mesuree (canal #1039, cf. case-1039 S4)"
    # TEMOINS DE NON-DEGENERESCENCE : les deux agregateurs TOURNENT dans ce montage. Sans eux,
    # << la MoW EST porteuse >> ne pourrait meme pas etre evalue.
    assert f["aura_attaque_appelee"] and f["aura_defense_appelee"], (
        "agregateur non appele : le montage ne mesure plus rien (porteurs att=%r def=%r)"
        % (f["att_porteurs"], f["def_porteurs"]))
    assert f["mow_porteur_aura_attaque"], (
        "une MoW porteuse d'aura est de nouveau ECARTEE de l'aura ATTAQUE : le filtre positionnel "
        "de `damage_model._apply_ally_attack_damage_auras` est revenu. Le natif n'ecarte AUCUN "
        "porteur par sa position -- relire docs/rl/case-999r3r1-contrat-de-rarete.md Sec.4.")
    assert f["mow_porteur_aura_defense"], (
        "une MoW porteuse d'aura est de nouveau ECARTEE de l'aura DEFENSE : le filtre positionnel "
        "de `damage_model.defender_modifiers` est revenu.")
    p = P.mesurer_prediction()
    assert p["mow_dans_eff_state"], (
        "la face PREDICTION ne seede plus les effets de `dv['mows']` : le second volet est reouvert, "
        "et le port repart en FORK prediction/combat (la face COMBAT, elle, les voit).")
    assert p["mow_dans_team_by_id"], "temoin #360 : les tables PAR ID couvrent bien les MoW"
    # ⚠ RESTE FAUX, ET C'EST FIDELE : une MoW n'a PAS de position, cote natif non plus. Ce n'est pas
    # `pos_by_id` qu'il fallait elargir (ce serait INVENTER une tuile) mais l'UNIVERS DES PORTEURS,
    # qui est desormais `Scene.effect_carrier_ids`. Le distinguer est ce qui empeche la
    # << reparation >> par fabrication de donnee.
    assert not p["mow_dans_pos_by_id"], (
        "une MoW a recu une POSITION : elle est hors-plateau par construction. Une aura "
        "positionnelle deviendrait evaluable sur une tuile INVENTEE -- pire qu'un gate muet.")


def test_l_univers_des_porteurs_de_la_face_decision_contient_la_mow():
    """Le pendant DECISION de l'assertion COMBAT ci-dessus, au NIVEAU DU FOYER.

    `mow_dans_eff_state` dit que l'effet est SEEDE ; il ne dit pas que la boucle de porteurs le
    VOIT. Les deux sont distincts, et c'est precisement l'ecart qui rendait la reparation partielle
    invisible : `Scene.effect_carrier_ids` est ce qui les relie."""
    import probe_999r3r1_porteurs_aura_mow as P
    sc = P.scene_prediction()
    ids = sc.effect_carrier_ids()
    assert P.MOW_ID in ids, (
        "la MoW porteuse n'entre pas dans `Scene.effect_carrier_ids` : les trois boucles d'aura de "
        "la face DECISION la rateront, alors que la face COMBAT la voit -- FORK.")
    # NON-DEGENERESCENCE : l'univers n'est pas << tout le monde >>. Il reste borne aux porteurs
    # reels, donc un etat sans MoW porteuse rend exactement ce que rendait `pos_by_id`.
    assert set(sc.pos_by_id) <= set(ids), "l'univers a RETRECI : des unites du plateau sont perdues"
    assert P.MOW_ID not in sc.pos_by_id, "temoin : la MoW n'a bien aucune position"
    assert P.MOW_ID not in sc.effect_carrier_ids(exclude=P.MOW_ID), "`exclude` ne mord pas"


# ================ Etage 6 -- la MAIN TILE de l'ATTAQUANT est dans le ctx d'aura =================

def test_ctx_aura_attaque_porte_la_tuile_de_l_attaquant(monkeypatch):
    """`UnitsOnTilesWithEffect(<les allies Mythiques>, Contaminated)` de 1442 lit la tuile de
    l'ELEMENT du selecteur -- l'attaquant --, pas celle de la cible. Le ctx ne portait que la tuile
    de la CIBLE : le gate aurait ete evalue sur la mauvaise tuile, ce qui est PIRE qu'absent."""
    st = _state()
    vus = _capture(monkeypatch, "aura_attack_damage_bonus_from_allies")
    DM.attacker_modifiers(st, ATT_ID, 9000, is_ranged=False, target_id=TGT_ID)
    assert vus
    tiles = vus[0].get("tile_effects_by_pos")
    assert tiles is not None
    assert (1, 1) in tiles, "MAIN TILE de l'ATTAQUANT absente du ctx d'aura ATTAQUE"
    assert (2, 1) in tiles, "MAIN TILE de la CIBLE perdue : la cle a ete REMPLACEE, pas elargie"
