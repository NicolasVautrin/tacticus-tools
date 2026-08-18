"""#895-r5 -- CLIQUET : `1082 InspiredToGreatness` indexe l'`AbilityState` PER-ABILITY.

`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$ExecuteBehaviour(this,
abilityState, entities)`, LU verbatim sur `t6dpr4k06g` -- ce sont les DEUX premieres instructions
du corps, et elles se repetent a l'identique avant chaque lecture de variable :

    local_1c8 = *(void **)abilityState;                 // recopie du 2e ARGUMENT
    local_1c0 = *(undefined4 *)(abilityState + 8);
    hpToHeal   = AbilityConfiguration$$GetVariableForLevel(config@this+0x60, 0x20, &local_1c8, 0);
    local_1c0 = *(undefined4 *)(abilityState + 8);
    local_1c8 = *(void **)abilityState;
    hpToHeal_2 = AbilityConfiguration$$GetVariableForLevel(config@this+0x60, 0x22, &local_1c8, 0);

Le port lisait `UnitContext.active_ability_level` / `ability_variables_multiplier` : le canal
GLOBAL. C'est la MEME faute que celle corrigee pour `1194 NovaShield` par #895 -- et le remede y
existait deja, sous un nom qui le declarait faussement specifique (`_nova_ability_scaling`, un seul
appelant, `ability_type` en parametre depuis le debut). Il est renomme `_ability_scaling`.

POURQUOI CA NE SE VOIT PAS SUR UN HEROS : les deux canaux COINCIDENT. Le global ne decroche que
sur un porteur dont `combatSnapshot.unitConfig` vaut `{"error": "config null"}` -- un npc. Mesure
#895 sur `tauBossRiptide` : `level=0, mult=100` contre `level=55, multiplier=200`, soit un facteur
**137** sur la variable lue. `1082` n'ayant aujourd'hui que des porteurs `lineup`, l'ecart est
LATENT : il devient reel des qu'un npc porte l'ability (greffe, injection catalogue). Ce fichier
le rend donc VISIBLE en montant les deux canaux DIVERGENTS -- c'est le seul regime ou la faute
s'observe, et le monter est ce qui fait de ce cliquet autre chose qu'un accord degenere.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PYDIR = Path(__file__).resolve().parents[3]                  # scripts/python
sys.path.insert(0, str(PYDIR))

import engine.runner.abilities.tau as TAU                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType            # noqa: E402
from engine.runner.components import (ActiveAbilitiesComponent, ActiveAbility,   # noqa: E402
                                      PositionComponent, StatsComponent)
from engine.runner.state import State                                        # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/tau.py",),
    "build": True,
    "toujours": False,
    "raison": "Le foyer `_ability_scaling` et ses deux consommateurs (`1194 NovaShield`, "
              "`1082 InspiredToGreatness`) vivent tous dans `tau.py`. `build: True` : les valeurs "
              "attendues sortent d'`ability_var` sur le gameconfig du build.",
}

ITG = int(ActiveAbilityType.InspiredToGreatness)              # 1082
NOVA = int(ActiveAbilityType.NovaShield)                      # 1194

#: Le regime qui SEPARE les deux canaux : per-ability renseigne, global a la valeur qu'un npc
#: rend quand `combatSnapshot.unitConfig` est en erreur (`0 / 100`).
PER_ABILITY = (55, 200)
GLOBAL_NPC = (0, 100)


def _ctx(level, mult):
    return SimpleNamespace(visual_id="tauBossRiptide", normal_hits=None, traits=(),
                           extra_pierce=0, extra_pierce_melee=0, extra_pierce_ranged=0,
                           passive_abilities=[], active_abilities=[],
                           config_active_abilities=None,
                           active_ability_level=level, ability_variables_multiplier=mult)


def _state(per_ability=None, global_canal=GLOBAL_NPC, ability_id=ITG) -> State:
    """Un caster dont les DEUX canaux DIVERGENT : c'est le seul montage discriminant."""
    st = State()
    e = st.add_entity(1)
    e.add_component(StatsComponent(_ctx(*global_canal)))
    e.add_component(PositionComponent(0, 0))
    if per_ability is not None:
        e.add_component(ActiveAbilitiesComponent([
            ActiveAbility(int(ability_id), level=per_ability[0], multiplier=per_ability[1])]))
    return st


# --------------------------------------------------------------------------------------------
# ETAGE 0 -- le montage SEPARE bien les deux canaux. Sans ca, tout le reste est un accord vide.
# --------------------------------------------------------------------------------------------
def test_etage0_le_montage_est_discriminant():
    st = _state(per_ability=PER_ABILITY)
    assert TAU._ability_scaling(st, 1, ITG) == PER_ABILITY
    sc = st.get_entity(1).get_component(StatsComponent)
    assert (sc.ctx.active_ability_level, sc.ctx.ability_variables_multiplier) == GLOBAL_NPC, (
        "le canal GLOBAL ne porte plus la valeur npc : les deux canaux coincident et le montage "
        "ne discrimine RIEN")
    assert PER_ABILITY != GLOBAL_NPC


def test_etage0bis_le_foyer_est_generique_et_partage():
    """Le remede de `1194` et celui de `1082` doivent etre LA MEME fonction : deux montages du
    meme etage derivent, c'est un bug silencieux par construction."""
    assert hasattr(TAU, "_ability_scaling"), (
        "`_ability_scaling` a disparu : le foyer partage n'existe plus")
    assert not hasattr(TAU, "_nova_ability_scaling"), (
        "l'ancien nom SPECIFIQUE subsiste -- c'est lui qui avait fait re-ecrire la lecture "
        "globale au lieu d'appeler le foyer")
    st = _state(per_ability=(7, 150), ability_id=NOVA)
    assert TAU._ability_scaling(st, 1, NOVA) == (7, 150), (
        "le foyer ne sert plus `NovaShield` : le renommage a casse son consommateur d'origine")


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- LE FIX : `_itg_heal_amounts` suit le canal PER-ABILITY.
# --------------------------------------------------------------------------------------------
def _attendu(level, mult):
    from engine.entities.effects.magnitude import ability_var                # noqa: PLC0415
    return (int(ability_var("InspiredToGreatness", "hpToHeal", level, multiplier_pct=mult) or 0),
            int(ability_var("InspiredToGreatness", "hpToHeal_2", level, multiplier_pct=mult) or 0))


def test_etage1_les_deux_montants_suivent_le_canal_per_ability():
    st = _state(per_ability=PER_ABILITY)
    attendu = _attendu(*PER_ABILITY)
    assert any(attendu), "les deux montants sont nuls : le gameconfig ne porte plus ces variables"
    assert TAU._itg_heal_amounts(st, 1) == attendu


def test_etage1bis_la_divergence_avec_le_canal_global_est_REELLE():
    """CONTRE-EPREUVE : le regime d'AVANT (canal global) doit rendre AUTRE CHOSE. S'il rendait la
    meme valeur, ce fichier serait vert sous les deux ecritures et ne mesurerait rien."""
    avant = _attendu(*GLOBAL_NPC)
    apres = _attendu(*PER_ABILITY)
    assert avant != apres, (
        "les deux canaux rendent le MEME couple (%s) : le montage n'est pas discriminant" % (avant,))
    st = _state(per_ability=PER_ABILITY)
    assert TAU._itg_heal_amounts(st, 1) == apres
    assert TAU._itg_heal_amounts(st, 1) != avant


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- LE REPLI reste le canal GLOBAL quand le composant per-ability n'est pas seede.
# C'est une degradation NOMMEE, pas un oubli : le canal exige `allAbilities: true`.
# --------------------------------------------------------------------------------------------
def test_etage2_sans_composant_per_ability_on_replie_sur_le_global():
    st = _state(per_ability=None, global_canal=(12, 130))
    assert TAU._ability_scaling(st, 1, ITG) == (12, 130)
    assert TAU._itg_heal_amounts(st, 1) == _attendu(12, 130)


def test_etage2bis_caster_inconnu_rend_le_defaut_neutre():
    assert TAU._ability_scaling(State(), 99, ITG) == (0, 100)


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- l'INDEXATION est PAR ABILITY : l'etat d'une AUTRE ability ne doit pas etre lu.
# C'est ce que « per-ability » veut dire, et aucun etage ci-dessus ne le garde.
# --------------------------------------------------------------------------------------------
def test_etage3_l_etat_d_une_autre_ability_n_est_pas_lu():
    st = _state(per_ability=PER_ABILITY, ability_id=NOVA)      # seed pose sur 1194, PAS sur 1082
    assert TAU._ability_scaling(st, 1, NOVA) == PER_ABILITY
    assert TAU._ability_scaling(st, 1, ITG) == GLOBAL_NPC, (
        "l'etat de `NovaShield` a ete lu pour `InspiredToGreatness` : l'indexation n'est pas "
        "PAR ABILITY, et c'est exactement la confusion que cette tranche repare")
    assert TAU._itg_heal_amounts(st, 1) == _attendu(*GLOBAL_NPC)
