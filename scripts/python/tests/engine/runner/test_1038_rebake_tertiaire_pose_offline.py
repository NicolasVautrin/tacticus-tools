"""#1038 -- CLIQUET du re-bake TERTIAIRE des effets poses SUR AUTRUI, 100 % OFFLINE.

CE QUE CE FICHIER GARDE, ET POURQUOI IL EXISTE
------------------------------------------------
`_rebake_tertiary_owner_effects` (#1009) est clee par PORTEUR : elle visite
`state.effects.by_unit[<l'unite qui porte la tertiaire>]`. Une ability tertiaire dont le behaviour
pose AILLEURS lui est donc structurellement invisible --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MastersOfManoeuvreAbility$$CreateBehaviour` =
`AddEffect(0x5e6, get_AbilityStateReference(this), source = Owner@<DSLSelectors+0x30>,
targets = **Actor@<DSLSelectors+0x40>**, ...)`.

MESURE qui a ouvert le residu (live, `darkaStormSpeeder` + `--equip-mythic ...:1`, board `MC1_67`) :
l'instance captee sur l'ami arrivait avec `ability_level = None` / `mult = 160` (le repli sur le
PORTEUR, `effects_state.baked_ability_state`), donc `ConfigVar(0x46)` ne trouvait aucun
`AbilityState` et la classe rendait `None` -- la reduction etait **entierement INERTE**.

LES QUATRE ETAGES sont des COUPLES : le bras qui MORD doit mordre (sinon un bras negatif vert ne
prouverait rien -- il pourrait passer parce qu'un AUTRE gate refuse), le bras qui NE MORD PAS doit
laisser l'instance intacte. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/loki/masters_of_manoeuvre.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("Le re-bake vit dans `snapshot.py`, sa table de portee dans `factory.py`, et le "
               "verdict de magnitude dans la classe d'effet + `magnitude.ability_var`. Aucun "
               "artefact de `data/symbols` n'est lu (les valeurs viennent du gameconfig vivant, "
               "et les assertions portent sur des RAPPORTS, pas sur des paliers en dur)."),
}

import hexgeo                                                              # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects.factory import (EffectFactory,                # noqa: E402
                                             EFFECT_CLASSES,
                                             TERTIARY_ABILITY_POSED_EFFECTS)
from engine.entities.effects.loki.masters_of_manoeuvre import (            # noqa: E402
    ABILITY_ID, MastersOfManoeuvreEffect, VAR_DMG_REDUCTION_PCT)
from engine.entities.effects.magnitude import ability_var                  # noqa: E402
from engine.entities.unit_context import UnitContext                       # noqa: E402
from engine.runner.components import StatsComponent                        # noqa: E402
from engine.runner.snapshot import _rebake_tertiary_posed_effects          # noqa: E402

COLS, ROWS = 5, 5
SOURCE_ID, PORTEUR_ID = 10, 20            # la MoW (source) et l'ami qui porte l'effet
#: Le couple TERTIAIRE que `UnitFactory$$Build` fabrique depuis `config+0xc0 TertiaryAbilityLevel`.
TERT_LVL, TERT_MULT = 1, 100
#: Le couple des PASSIFS du MEME porteur en runner normalise -- ce que le port lisait AVANT.
PASSIF_LVL, PASSIF_MULT = 50, 160


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _state():
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    decision = {"currentPlayer": 1, "units": [
        {"id": SOURCE_ID, "visualId": "darkaStormSpeeder", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 2}, "effects": []},
        {"id": PORTEUR_ID, "visualId": "worldKharn", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 3, "row": 2}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 50000, "hpMax": 50000}
                         for u in decision["units"]]}
    return load_state(decision, observe, board=Board(tiles, adjacency="evenq"))


def _monte(*, tertiaire: "str | None" = ABILITY_ID, niveau: int = TERT_LVL,
           nom_effet: str = "MastersOfManoeuvre"):
    """LE MONTAGE, NOMME ET REUTILISABLE : une SOURCE porteuse (ou non) d'une tertiaire, et un
    PORTEUR distinct sur qui l'instance a ete posee avec le repli PASSIF (l'etat que la capture
    live produit -- `baked_ability_state` se replie sur le porteur quand la source n'a pas
    d'`ability_level`)."""
    st = _state()
    ent = st.get_entity(SOURCE_ID)
    sc = ent.get_component(StatsComponent)
    if sc is None or getattr(sc, "ctx", None) is None:
        # Sans `combatSnapshot`, `load_state` ne pose aucun `StatsComponent` : on POSE celui que le
        # canal `unitAbilityStates` ecrirait (`snapshot._load_tertiary_abilities`). Ces trois
        # champs sont la SEULE entree que le re-bake lit, donc le montage reste fidele a ce qu'il
        # visite -- il ne fabrique pas un etat que la capture ne produirait pas.
        sc = StatsComponent(UnitContext(entity_id=SOURCE_ID, visual_id="darkaStormSpeeder"))
        ent.add_component(sc)
    ctx = sc.ctx
    ctx.tertiary_ability = tertiaire
    ctx.tertiary_ability_level = niveau
    ctx.tertiary_ability_variables_multiplier = TERT_MULT
    if st.effects is None:
        from engine.entities.effects_state import EffectsState
        st.effects = EffectsState.seed({})
    inst = EffectFactory.create({"name": nom_effet,
                                 "effectType": int(EffectType.MastersOfManoeuvre),
                                 "active": True, "source": SOURCE_ID})
    inst.ability_level = PASSIF_LVL                 # <- le repli sur le PORTEUR
    inst.ability_variables_multiplier = PASSIF_MULT
    st.effects.by_unit.setdefault(PORTEUR_ID, []).append(inst)
    return st, inst


# ══ Etage 0 -- la population EXISTE (sinon les etages suivants seraient des verts vides) ════════

def test_etage0_le_registre_et_la_table_sont_peuples():
    """Un cliquet qui ne visite rien rend vert pour rien : on assertionne le non-vide D'ABORD.
    Les deux entrees sont POSEES PAR LA MEME TRANCHE, donc un rollback partiel les separerait."""
    assert EFFECT_CLASSES.get("MastersOfManoeuvre") is MastersOfManoeuvreEffect, (
        "1510 n'est pas (ou plus) apparie a `MastersOfManoeuvreEffect` dans EFFECT_CLASSES -- "
        "l'instance retomberait sur un `BaseEffect` nu, et la degradation est SILENCIEUSE")
    assert ABILITY_ID in TERTIARY_ABILITY_POSED_EFFECTS, (
        "`%s` a disparu de TERTIARY_ABILITY_POSED_EFFECTS : le re-bake ne visiterait plus rien "
        "et les trois etages suivants seraient des verts vides" % ABILITY_ID)
    assert "MastersOfManoeuvre" in TERTIARY_ABILITY_POSED_EFFECTS[ABILITY_ID]


# ══ Etage 1 -- le re-bake MORD, et il ecrit le couple TERTIAIRE ═════════════════════════════════

def test_etage1_le_rebake_ecrit_le_couple_tertiaire():
    """MIRROR de `AddEffectBehaviour$$DefaultEffectBuilder` : l'`AbilityStateReference` BAKEE dans
    `EffectComponent+0x18` est celle de l'ability QUI POSE -- ici la TERTIAIRE de la SOURCE."""
    st, inst = _monte()
    n = _rebake_tertiary_posed_effects(st)
    assert n == 1, "le re-bake n'a visite aucune instance (n=%d)" % n
    assert inst.ability_level == TERT_LVL, (
        "niveau non re-bake : %r (attendu %d, le TertiaryAbilityLevel de la source)"
        % (inst.ability_level, TERT_LVL))
    assert inst.ability_variables_multiplier == TERT_MULT


def test_etage1b_le_niveau_change_la_magnitude_le_regime_est_separant():
    """LE CRAN QUI COMPTE. Le re-bake ne vaut que s'il DEPLACE la magnitude : si `dmgReductionPct`
    rendait la meme valeur au palier tertiaire et au palier passif clampe, ce cliquet serait vert
    pour un port FAUX. On l'assertionne au lieu de le supposer.

    MESURE NATIVE de reference (`aiPredict`, meme tuile finale, meme tireur) : niveau 1 -> x0.8997,
    niveau 4 -> x0.8000, contre-bras sans effet -> x1. Trois bras DISTINCTS."""
    v_tert = ability_var(ABILITY_ID, VAR_DMG_REDUCTION_PCT, TERT_LVL, multiplier_pct=TERT_MULT)
    v_passif = ability_var(ABILITY_ID, VAR_DMG_REDUCTION_PCT, PASSIF_LVL,
                           multiplier_pct=PASSIF_MULT)
    assert v_tert and v_passif, (
        "gameconfig muet sur %s.%s -- le test ne mesure rien" % (ABILITY_ID, VAR_DMG_REDUCTION_PCT))
    assert int(v_tert) != int(v_passif), (
        "REGIME DEGENERE : le palier tertiaire (%s) et le palier passif clampe (%s) donnent la "
        "MEME valeur -- ce fichier ne peut alors rien prouver du re-bake" % (v_tert, v_passif))


# ══ Etage 2 -- les CONTRE-EPREUVES : le re-bake ne mord QUE la ou il doit ═══════════════════════

def test_etage2_source_sans_tertiaire_rien_nest_reecrit():
    """PORTEE STRICTE : une source qui ne porte AUCUNE tertiaire n'est pas visitee. Sans ce cran,
    un effet homonyme pose par un passif se ferait reecrire le niveau."""
    st, inst = _monte(tertiaire=None)
    assert _rebake_tertiary_posed_effects(st) == 0
    assert inst.ability_level == PASSIF_LVL and inst.ability_variables_multiplier == PASSIF_MULT


def test_etage2b_tertiaire_verrouillee_niveau_zero_rien_nest_reecrit():
    """`0` = VERROUILLE (`Idun.Shared.Level$$CreateValidOrLockedLevel`), et
    `AbilityConfiguration$$TryGetVariableArrayForLevel` LEVE dessus via `ToZeroBasedIndex`.
    Re-baker un `0` transformerait un effet inerte en exception."""
    st, inst = _monte(niveau=0)
    assert _rebake_tertiary_posed_effects(st) == 0
    assert inst.ability_level == PASSIF_LVL


def test_etage2c_effet_hors_table_rien_nest_reecrit():
    """Le nom de l'effet doit figurer dans `TERTIARY_ABILITY_POSED_EFFECTS[<tertiaire>]`. Un effet
    quelconque pose par la MEME source (une aura, un marqueur) garde son propre `AbilityState`."""
    st, inst = _monte(nom_effet="UnEffetQuiNestPasDeCetteAbility")
    assert _rebake_tertiary_posed_effects(st) == 0
    assert inst.ability_level == PASSIF_LVL


# ══ Etage 3 -- le VERDICT de la classe d'effet, gate par gate ═══════════════════════════════════

def _verdict(st, is_melee):
    inst = [e for e in st.effects.by_unit[PORTEUR_ID]
            if int(getattr(e, "effect_type", -1) or -1) == int(EffectType.MastersOfManoeuvre)][0]
    return inst.create_effect_damage_malus_for_defense(is_melee=is_melee)


def test_etage3_ranged_prouve_rend_le_percent_decrease_du_palier_tertiaire():
    """`ForPercentDecrease( get_OwnerIsTarget & IsRangedAttack(), ConfigVar(0x46) )` -- le bras qui
    MORD. C'est lui qui rend probants les deux bras negatifs qui suivent."""
    st, _i = _monte()
    _rebake_tertiary_posed_effects(st)
    eb = _verdict(st, is_melee=False)
    attendu = int(ability_var(ABILITY_ID, VAR_DMG_REDUCTION_PCT, TERT_LVL,
                              multiplier_pct=TERT_MULT))
    assert eb is not None and eb.kind == "PercentDecrease", (
        "le canal defenseur ne rend pas de PercentDecrease : %r" % (eb,))
    assert eb.value == attendu, "pct %r au lieu du palier tertiaire %d" % (eb.value, attendu)
    assert eb.owner_is_caster is False, "l'effet vit sur le DEFENSEUR (get_OwnerIsTarget)"


def test_etage3b_melee_prouvee_est_muette():
    """`IsRangedAttack()` est un conjoint du trigger : en melee le natif ne verse RIEN. C'est le
    contraste ENTIER avec `ContemptuousDisregard_DamageReduction`, qui n'a aucun gate de nature."""
    st, _i = _monte()
    _rebake_tertiary_posed_effects(st)
    assert _verdict(st, is_melee=True) is None


def test_etage3c_nature_inconnue_est_muette():
    """Tri-etat : `None` = nature du coup NON declaree -> le gate se TAIT (<< present != applique
    >>). Degradation RESTRICTIVE, jamais une valeur devinee."""
    st, _i = _monte()
    _rebake_tertiary_posed_effects(st)
    assert _verdict(st, is_melee=None) is None


def test_etage3d_sans_rebake_leffet_est_inerte_et_cest_le_bug_repare():
    """LE ROUGE D'AVANT, GARDE EN TEST. Sans le re-bake, la capture live donne `ability_level =
    None` (repli sur un porteur qui n'a pas d'`ability_level` d'ability tertiaire) et la classe
    rend `None` : materialisee, et pourtant INERTE."""
    st, inst = _monte()
    inst.ability_level = None                      # l'etat EXACT mesure avant #1038
    assert _verdict(st, is_melee=False) is None, (
        "sans AbilityState, `ConfigVar(0x46)` doit rester muet -- rendre une valeur ici serait un "
        "palier DEVINE")
