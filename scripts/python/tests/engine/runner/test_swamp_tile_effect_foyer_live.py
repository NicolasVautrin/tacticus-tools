"""case-155 -- GARDE du FOYER UNIQUE « terrain statique -> noms sommes par la feuille TileEffects(9) ».

CRITERE TRANCHE (decompile = verite). `IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
a DEUX boucles, deux SOURCES, deux espaces de NOMS :
  Loop1 -- `GetComponent<EffectsOwnedComponent>(mainTile)`, nom = `((EffectType)EffectComponent+0x58)
           .ToString()`, poids `Default.TileEffects.<EffectType>` (multiplie par
           `IdunBattle.AI.Utilities.TileEffectsUtility$$GetStatusEffectMultiplier` SEULEMENT si
           `StaticBattleRules.Effect$$IsTileStatusEffect`) ;
  Loop2 -- abilities HEBERGEES, nom = `Unit.get_Id` -> `ActiveAbilityType.ToString()`, sans multiplicateur.

Le `-25` d'une Swamp est un effet POSE SUR LA TUILE par l'ability de terrain
(`IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` =
`AddBlockEnteringUnitsEffect(0) & AddStaticStatModifierEffectToOwner(0xb, 3, Direct(const 0x14))`),
donc **Loop1**. Aucune cle BC `SwampBlockMovement`/`ThornsBlockMovement` n'existe dans
`Default.TileEffects` -> Loop2 ne rend RIEN sur une Swamp. Le `+9` d'une DryBush, lui, est **Loop2**
(`LightCoverAbility$$CreateBehaviour` = `AddEffect(0x3f5, ., UnitsThatNeedEffect())` : l'effet est pose
sur les UNITES, la TUILE n'en porte aucun -- une DryBush VIDE rend quand meme +9).

CE QUE CES TESTS GARDENT :
  (1) OFFLINE -- `terrain_tile_effects` n'ajoute le repli Loop1 que si le canal DYNAMIQUE ne le porte
      pas deja. C'est ce qui rend le repli inoffensif : sans cette regle, un etat hydrate compterait
      le -25 DEUX fois (-50). Rougit si quelqu'un re-concatene les deux tables sans deduplication.
  (2) OFFLINE -- aucune SECONDE table terrain->effets ne reapparait hors du foyer (anti-refork).
  (3) LIVE -- sur la geometrie qui a IMPOSE le -25 (case-130 SS5, caster force sur t15 de MC1_67),
      les regimes HYDRATE (`load_state(tiles=tileMeta)`) et NON HYDRATE CONVERGENT : meme tri, meme
      tuile, et tous deux egaux au live. C'est LA garde anti-fork : les deux canaux se recouvrent au
      lieu de s'additionner.
  (4) LIVE, ANTI-TAUTOLOGIE -- repli neutralise, le port place sur la SWAMP alors que le live place
      ailleurs. Sans ce volet, (3) passerait meme si le -25 ne decidait de rien.

Scenario live = `probe_155_swamp_tile_effect_fork.py` (probe versionne) : le test l'IMPORTE. Le runner
est dispose des la mesure capturee. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_155_swamp_tile_effect_fork as P155
import probe_130_placement_sort_rng as P
from engine.utilities.tile import (TERRAIN_HOSTED_ABILITIES, TERRAIN_TILE_OWNED_EFFECTS,
                                   terrain_tile_effects)

SEED = "777"
BOARD = "MC1_67"
CASTER_TILE = 15


# --------------------------------------------------------------- offline : la REGLE du foyer

def test_swamp_fallback_only_when_dynamic_channel_is_silent():
    """Repli Loop1 : present sur un etat NON hydrate, ABSENT des que le canal dynamique le porte."""
    assert terrain_tile_effects("Swamp") == ["Thorns_DefenseReduction"]
    assert terrain_tile_effects("Swamp", []) == ["Thorns_DefenseReduction"]
    # canal dynamique hydrate (ce que `tileMeta` rend reellement sur une Swamp, case-102) -> 0 repli
    assert terrain_tile_effects(
        "Swamp", ["BlockEnteringUnits", "Thorns_DefenseReduction"]) == []


def test_hosted_ability_is_never_deduplicated_against_the_dynamic_channel():
    """Loop2 n'est PAS un repli : une DryBush rend +9 meme quand la tuile porte des effets dynamiques
    (le natif somme les deux boucles). Rougit si on dedupliquait Loop2 comme Loop1."""
    assert terrain_tile_effects("DryBush") == ["LightCover"]
    assert terrain_tile_effects("DryBush", ["Fire"]) == ["LightCover"]
    assert terrain_tile_effects("DryBush", ["LightCover"]) == ["LightCover"]


@pytest.mark.parametrize("terrain", ["Grass", "Block", "Water", "Bridge", "", None])
def test_terrains_without_hosted_ability_contribute_nothing(terrain):
    assert terrain_tile_effects(terrain) == []
    assert terrain_tile_effects(terrain, ["Fire"]) == []


def test_the_two_tables_are_the_only_terrain_effect_source():
    """ANTI-REFORK : le savoir terrain->effets vit dans CES deux tables, chacune rattachee a SA boucle
    native. Rougit si une troisieme table apparait (c'est exactement le defaut ferme ici) ou si les
    deux se melangent."""
    assert TERRAIN_HOSTED_ABILITIES == {"DryBush": ("LightCover",)}, (
        "Loop2 (abilities HEBERGEES) : toute entree ajoutee doit etre lue au `CreateBehaviour` de "
        "l'ability de tuile ET avoir un poids `Default.TileEffects.<ActiveAbilityType>`.")
    assert TERRAIN_TILE_OWNED_EFFECTS == {"Swamp": ("Thorns_DefenseReduction",)}, (
        "Loop1 (repli) : n'y mettre QUE des noms d'EffectType qu'une ability de terrain pose sur la "
        "tuile elle-meme (`AddStaticStatModifierEffectToOwner`), et qui ont un poids BC.")
    assert not set(TERRAIN_HOSTED_ABILITIES) & set(TERRAIN_TILE_OWNED_EFFECTS), (
        "un terrain ne doit pas alimenter les deux tables sans RE explicite des deux boucles")


# --------------------------------------------------------------- live : convergence des deux regimes

@pytest.fixture(scope="module")
def measured(live_session, rpc):
    """Geometrie de case-130 SS5 (caster force sur t15), mesuree dans les TROIS regimes. Le runner est
    dispose des la capture (ne pas affamer les autres agents)."""
    P.BOARD = BOARD
    reg = P.run_case(rpc, SEED, "controledict", discriminate=True,
                     force_caster_tile=CASTER_TILE)
    if reg is None or "rng_after" not in reg:
        pytest.skip("scenario live indisponible (setup a re-crafter, pas un verdict)")
    try:
        tm = rpc("tileMeta", {"runnerId": reg["rid"]}, 60)
        pool, order_dry, st_dry = P155._pool_utilities(reg)
        _, tiles_dry = P155._replay(reg)
        pool_h, order_h, st_h = P155._pool_utilities(reg, tiles=tm)
        _, tiles_h = P155._replay(reg, tiles=tm)
        _, order_no, _ = P155._pool_utilities(reg, owned_effects={})
        _, tiles_no = P155._replay(reg, owned_effects={})
        out = {
            "live": reg["live_spawn_tiles"], "pool": pool,
            "swamps": [t for t in pool if reg["board"].tile_def_id(t) == "Swamp"],
            "dry": {"order": order_dry, "tiles": tiles_dry,
                    "eff": {t: P155._tile_effect_names(st_dry, t) for t in pool}},
            "hyd": {"order": order_h, "tiles": tiles_h,
                    "eff": {t: P155._tile_effect_names(st_h, t) for t in pool_h}},
            "no_fallback": {"order": order_no, "tiles": tiles_no},
        }
    finally:
        try:
            rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
        except Exception:
            pass
        try:
            reg["state_file"].unlink()
        except Exception:
            pass
    assert out["live"], "aucun spawn live observe -- geometrie a re-crafter, pas un verdict"
    assert out["swamps"], (
        "le pool de placement ne contient AUCUNE Swamp -- le scenario ne teste pas le -25 "
        "(re-crafter la geometrie, pas un verdict)")
    return out


def test_dynamic_channel_really_carries_the_thorns_effect_live(measured):
    """PRE-REQUIS du volet anti-double : le canal dynamique (tileMeta) porte bien, LIVE, ce que
    `ThornsBlockMovementAbility$$CreateBehaviour` pose sur la tuile. Si ce n'etait pas le cas, la
    convergence testee ensuite serait vide de sens."""
    for t in measured["swamps"]:
        assert "Thorns_DefenseReduction" in measured["hyd"]["eff"].get(t, []), (
            f"tuile {t} (Swamp) ne porte pas Thorns_DefenseReduction dans tileMeta : "
            f"{measured['hyd']['eff'].get(t)}")
        assert measured["dry"]["eff"].get(t) == [], (
            f"tuile {t} : l'etat NON hydrate ne devrait porter aucun effet de tuile")


def test_both_regimes_agree_with_live_and_with_each_other(measured):
    """LE CRITERE DU CAS : hydrate et non hydrate rendent le MEME tri et la MEME tuile, tous deux
    egaux au live. Rougit si le repli s'ADDITIONNE au canal dynamique (-50 au lieu de -25) ou si le
    site de placement cesse de compter le -25."""
    m = measured
    assert m["dry"]["tiles"] == m["live"], (
        f"regime NON hydrate : port {m['dry']['tiles']} vs live {m['live']}")
    assert m["hyd"]["tiles"] == m["live"], (
        f"regime HYDRATE : port {m['hyd']['tiles']} vs live {m['live']} -- le canal dynamique et le "
        f"repli se cumulent (fork rouvert) ou le canal n'est pas lu")
    assert m["hyd"]["order"] == m["dry"]["order"], (
        f"tri hydrate {m['hyd']['order']} != tri non hydrate {m['dry']['order']} : les deux canaux "
        f"ne se recouvrent plus -- c'est la signature exacte du fork de port")


def test_without_the_minus_25_the_port_places_on_the_swamp(measured):
    """ANTI-TAUTOLOGIE : repli neutralise, le port place sur la Swamp -- donc les tests ci-dessus
    mesurent bien le -25 et pas la geometrie. S'ils coincidaient, la garde ne garderait rien."""
    m = measured
    assert m["no_fallback"]["tiles"] != m["live"], (
        f"sans le -25 le port place encore en {m['no_fallback']['tiles']} (= live) : la geometrie "
        f"n'est plus discriminante, re-crafter (pas un verdict)")
    assert set(m["no_fallback"]["tiles"]) & set(m["swamps"]), (
        f"sans le -25 le port devrait choisir une Swamp du pool {m['swamps']}, il a pris "
        f"{m['no_fallback']['tiles']}")
