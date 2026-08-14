"""#1046 -- CLIQUET de la chaine des Horreurs Thousand Sons : `Split` (1156) et `FlamesOfMutation`
(1160), les deux passifs de SUMMON portes par la tranche.

POURQUOI CE FICHIER EXISTE. Un passif non porte ne produit AUCUNE erreur :
`triggers/dispatch/core.py` fait `for cls in ABILITY_TRIGGERS.get(pa, ())` -- un nom absent rend un
tuple vide et le moteur continue, sans accumulateur `unported` (contrairement aux actives). Retirer
l'une des deux inscriptions ne casserait donc RIEN d'observable ; ce fichier est la seule chose qui
rougirait. Meme raison d'etre que `test_1016_passifs_necrons_offline.py`.

CE QU'IL GARDE, etage par etage :
  0. le CABLAGE (les deux registres) et les DEUX ordinaux d'enum ;
  1. `Split` MORD -- 2 Blue Horrors sur des tuiles ADJACENTES au mourant, `thousSmnBlueHorror` LU
     dans `abilities.Split.constants.unitId`, equipe + `parent_id` du porteur ;
  2. le gate OVERKILL discrimine, sur les DEUX abilities -- c'est le meme corps de `CreateTrigger`
     cote natif (fold ICF), donc un seul gate a garder deux fois ;
  3. le gate STEPPABLE discrimine (inerte sur les porteurs actuels, mirrore quand meme) ;
  4. `OwnerIsTarget` -- une AUTRE unite qui meurt ne declenche rien ;
  5. `If(IsTurnOf(Owner))` DISCRIMINE : l'attaque immediate n'a lieu QUE pendant le tour du porteur.
     C'est le seul etage qui distingue les deux branches du `If` -- sans lui, porter la branche
     `else` a l'identique passerait ;
  6. le COMPTE : `PickRandomly(..., 2, ...)` est un LITTERAL, borne par les tuiles posables ;
  7. `FlamesOfMutation` : `EffectType.Fire` sur la MAIN TILE, la tuile est sa PROPRE SOURCE (le
     selecteur source natif est `0`), duree = `DefaultAmountOfRounds(5)` CONVERTIE en tours ;
  8. la CHAINE : Pink meurt -> 2 Blue -> une Blue meurt -> sa tuile brule ;
  9. GROUND TRUTH LIVE (runner 446, board MC1_67) : sous multiplier 180, les Blue Horrors sortent a
     **2093 PV / 1795 Attack** et le Fire a **4 tours** -- les trois chiffres du stream natif ;
 10. `abilities.FlamesOfMutation.constants.chance` reste NON LU -- garde contre un `Maybe(50)`
     INVENTE (aucune des quatre methodes de la classe native ne lit cette constante).

OFFLINE INTEGRAL : `State` synthetique, aucun runner, aucun RPC. ASCII only.
"""
from __future__ import annotations

import gameconfig as GC
import pytest

import probe_1046_horrors_chain as P
from engine.entities.effect_type import EffectType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.effects import default_amount_of_rounds
from engine.runner.operations.triggers.dispatch.move_death import pre_unit_death_2_triggers
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki.horrors import (
    FLAMES_OF_MUTATION_ABILITY, FLAMES_OF_MUTATION_FIRE, FLAMES_OF_MUTATION_KEY,
    SPLIT_ABILITY, SPLIT_KEY, SPLIT_SPAWN_COUNT, FlamesOfMutationAbility, SplitAbility)


#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # Le foyer (`triggers/loki/horrors.py`) et le registre sont dans la fermeture d'imports, donc
    # DERIVES. Ce qui ne l'est PAS : le probe, dont ce fichier importe le montage (board synthetique,
    # `UnitContext`, emission de `On(PreUnitDeath_2)`) -- une modification du montage change ce que
    # ce fichier mesure sans toucher a un seul module `engine.*`. Le nommer ici est exactement la
    # parade au « declencheur trop ETROIT ».
    "chemins": ("scripts/python/probe_1046_horrors_chain.py",),
    # VRAI : le port lit le gameconfig du build pour `Split.constants.unitId` (le summon pose) et
    # pour `summonHp`/`summonDmg` (ses stats). Un re-dump qui renommerait l'une de ces cles ferait
    # tomber le spawn ou ses stats -- exactement le rouge attendu.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde DEUX comportements de passif de summon Thousand Sons et rien d'autre : "
        "qu'une Pink Horror non overkillee se scinde en 2 Blue Horrors adjacentes (qui n'attaquent "
        "aussitot que pendant le tour de leur porteuse), et qu'une Blue Horror non overkillee mette "
        "sa propre tuile en feu. Son verdict ne depend que de sa fermeture d'imports, du montage du "
        "probe et du gameconfig du build."
    ),
}

BLUE_HORROR = "thousSmnBlueHorror"
PINK = "thousSmnPinkHorror"
BLUE = "thousSmnBlueHorror"


#: `P.jouer(st, ...)` -> `(payload, ids des unites NEUVES)`. On passe TOUJOURS par lui : le snapshot
#: des ids connus doit etre pris AVANT l'emission. Une liste d'exclusion ecrite a la main
#: (`{PORTEUR, ENNEMI}`) sous-compte des que le montage n'a pas d'ennemi -- l'allocateur reutilise
#: alors l'id `ENNEMI` pour le premier summon, et le test rendait 1 au lieu de 2 (faute mesuree au
#: premier jeu de ce fichier).
jouer = P.jouer


# --- 0. CABLAGE ------------------------------------------------------------------------------
def test_cablage_registre_et_ordinaux():
    """Les deux passifs sont INSCRITS, et sous le NOM que porte `units.<id>.passiveAbilities`."""
    assert ABILITY_TRIGGERS.get(SPLIT_KEY) == [SplitAbility]
    assert ABILITY_TRIGGERS.get(FLAMES_OF_MUTATION_KEY) == [FlamesOfMutationAbility]
    # Les ordinaux, FIGES au site (le mirror seul redeviendrait vert apres un renumerotage).
    assert (SPLIT_ABILITY, FLAMES_OF_MUTATION_ABILITY) == (1156, 1160)
    assert int(TriggeredAbilityType.Split) == SPLIT_ABILITY
    assert int(TriggeredAbilityType.FlamesOfMutation) == FLAMES_OF_MUTATION_ABILITY
    # Les DEUX classes portent leur `TRIGGERED_ABILITY_ID` (lu par `CurrentAbilityIs` cote natif).
    assert SplitAbility.TRIGGERED_ABILITY_ID == SPLIT_ABILITY
    assert FlamesOfMutationAbility.TRIGGERED_ABILITY_ID == FLAMES_OF_MUTATION_ABILITY


def test_les_quatre_porteurs_du_registre_des_summons():
    """Les porteurs sont ceux de `docs/rl/summons-registry.tsv`, LUS dans le gameconfig -- pas une
    liste recopiee. Ce test rougit si un re-dump retire l'un des quatre passifs de son kit."""
    attendus = {"thousSmnPinkHorror": SPLIT_KEY, "thousSmnPinkHorrorHSE": SPLIT_KEY,
                "thousSmnBlueHorror": FLAMES_OF_MUTATION_KEY,
                "thousSmnBlueHorrorHSE": FLAMES_OF_MUTATION_KEY}
    for uid, passif in attendus.items():
        u = GC.unit(uid) or {}
        assert passif in (u.get("passiveAbilities") or []), uid


# --- 1. Split MORD ----------------------------------------------------------------------------
def test_split_pose_deux_blue_horrors_adjacentes():
    st = P.monter(PINK, SPLIT_KEY, owner_turn=True)
    out, neuves = jouer(st)
    assert len(neuves) == SPLIT_SPAWN_COUNT == 2, out
    porteur = st.get_entity(P.PORTEUR).get_component(PositionComponent)
    import hexgeo
    voisines = {(c, r) for (c, r) in hexgeo.neighbors(porteur.col, porteur.row)}
    for nid in neuves:
        uc = st.get_entity(nid).get_component(UnitComponent)
        pc = st.get_entity(nid).get_component(PositionComponent)
        oc = st.get_entity(nid).get_component(OwnerComponent)
        # `GetStringConstant(config, 0 = unitId)` -- LU en gameconfig, jamais code en dur ici.
        assert uc.visual_id == (GC.ability(SPLIT_KEY) or {})["constants"]["unitId"] == BLUE_HORROR
        assert (pc.col, pc.row) in voisines             # AdjacentTiles(Owner@+0x30)
        assert uc.parent_id == P.PORTEUR                 # `Spawn(parentSelector = Owner, ...)`
        assert oc.team == 0                              # equipe du porteur (owner du spawn)
    # payload structure : l'appelant doit pouvoir distinguer un no-op d'un spawn.
    assert out and out[0]["ability"] == SPLIT_KEY and len(out[0]["spawned"]) == 2


# --- 2 & 3 & 4. les GATES du trigger PARTAGE ---------------------------------------------------
@pytest.mark.parametrize("visual,passif", [(PINK, SPLIT_KEY), (BLUE, FLAMES_OF_MUTATION_KEY)])
def test_gate_overkill_discrimine_sur_les_deux(visual, passif):
    """`OnPreDeath2(triggerOnOverkill: FALSE, ...)` -> `NOT TargetIsOverkilled`. Les DEUX abilities
    partagent LE MEME corps de `CreateTrigger` cote natif (fold ICF), donc le meme gate.

    GROUND TRUTH LIVE (runner 446) : `Attack_WasOverkill=1` -> `RemoveUnit Unit_WasOverkilled=1` et
    **zero** `AddUnit` / zero effet de tuile ; `Attack_WasOverkill=0` -> les deux se produisent."""
    st = P.monter(visual, passif, owner_turn=True)
    out, neuves = jouer(st, overkill=True)
    assert out == [] and neuves == [] and P.effets(st) == {}
    # contre-bras : le MEME montage sans overkill produit quelque chose (sinon le test ne garde rien)
    st2 = P.monter(visual, passif, owner_turn=True)
    assert jouer(st2)[0] != []


@pytest.mark.parametrize("visual,passif", [(PINK, SPLIT_KEY), (BLUE, FLAMES_OF_MUTATION_KEY)])
def test_gate_steppable_discrimine_sur_les_deux(visual, passif):
    """`OnPreDeath2(..., triggerOnSteppable: FALSE)` -> `NOT HasTrait(Target, 0x1b = Steppable)`.
    INERTE sur les quatre porteurs actuels (aucune Horreur n'est Steppable) -- garde le mirror."""
    st = P.monter(visual, passif, traits=(UnitTrait.Steppable.name,), owner_turn=True)
    out, neuves = jouer(st)
    assert out == [] and neuves == [] and P.effets(st) == {}


@pytest.mark.parametrize("visual,passif", [(PINK, SPLIT_KEY), (BLUE, FLAMES_OF_MUTATION_KEY)])
def test_owner_is_target_une_autre_mort_ne_declenche_rien(visual, passif):
    """`get_OwnerIsTarget` : le porteur ne reagit qu'a SA PROPRE mort."""
    st = P.monter(visual, passif, ennemi_adjacent=True, owner_turn=True)
    out, neuves = jouer(st, dying=P.ENNEMI, killer=P.PORTEUR)
    assert out == [] and neuves == [] and P.effets(st) == {}


# --- 5. If(IsTurnOf(Owner)) --------------------------------------------------------------------
def test_if_is_turn_of_owner_discrimine_l_attaque_immediate():
    """`SplitAbility$$CreateBehaviour` = `If(IsTurnOf(Owner@+0x30), <spawn autoAttack:true>,
    <spawn autoAttack:false>)`. Les DEUX branches spawnent ; seule l'attaque on-appearance differe
    (`PerformAIAttackFromCurrentPosition(ActiveTarget@+0x68)`).

    C'est le SEUL etage qui separe les deux branches : sans lui, porter la branche `else` a
    l'identique passerait tous les autres."""
    dedans = P.monter(PINK, SPLIT_KEY, ennemi_adjacent=True, owner_turn=True)
    a, _ = jouer(dedans)
    dehors = P.monter(PINK, SPLIT_KEY, ennemi_adjacent=True, owner_turn=False)
    b, _ = jouer(dehors)
    # meme nombre de summons des deux cotes -- c'est l'ATTAQUE qui distingue, pas le spawn
    assert len(a[0]["spawned"]) == len(b[0]["spawned"]) == 2
    assert a[0]["attacks"], "tour de l'owner -> les summons attaquent aussitot"
    assert b[0]["attacks"] == [], "hors tour de l'owner -> aucune attaque immediate"


# --- 6. le COMPTE -------------------------------------------------------------------------------
def test_compte_borne_par_les_tuiles_posables():
    """`PickRandomly(CanAddUnit(AdjacentTiles(Owner)), 2, ...)` : le `2` est un LITTERAL du
    decompile (le gameconfig de `Split` n'a AUCUNE variable de compte), et il est borne par le
    nombre de tuiles ou une unite PEUT etre ajoutee."""
    import hexgeo
    voisines = [p for p in hexgeo.neighbors(2, 2) if P.dans_board(p)]
    assert len(voisines) > 2, "montage : il faut plus de 2 voisines pour que le bornage soit visible"
    st = P.monter(PINK, SPLIT_KEY, owner_turn=True, bloquees=voisines[1:])
    assert len(jouer(st)[1]) == 1
    # et le regime PLEIN rend bien 2 (sinon le bornage ci-dessus ne prouverait rien)
    st2 = P.monter(PINK, SPLIT_KEY, owner_turn=True)
    assert len(jouer(st2)[1]) == 2


# --- 7. FlamesOfMutation ------------------------------------------------------------------------
def test_flames_of_mutation_pose_le_feu_sur_sa_main_tile():
    """`AddEffect(5 = EffectType.Fire, AbilityStateReference, <source 0>, Tiles(Owner@+0x30), null)`.

    Les TROIS champs sont gardes, et chacun a son ecart possible :
      * la CIBLE est la MAIN TILE du mourant (`UnitsMainTilesSelector`), pas son empreinte ni le
        caster ;
      * la SOURCE est la TUILE elle-meme -- le ctor `AddEffectBehaviour..ctor` recoit `0` en
        selecteur source, donc le fallback natif « source absente => la source EST la cible ». La
        confondre avec le caster passerait inapercu offline (le caster est mort) mais divergerait
        de la mesure live `Effect_SourceId=<la tuile>` ;
      * la DUREE vient de `DefaultAmountOfRounds(5)` CONVERTIE en tours par
        `ConvertRoundsToTurns` (facteur = nb de joueurs). GROUND TRUTH LIVE : 4 tours."""
    st = P.monter(BLUE, FLAMES_OF_MUTATION_KEY, owner_turn=True)
    out, neuves = jouer(st)
    assert out and out[0]["ability"] == FLAMES_OF_MUTATION_KEY
    main = P.tid(2, 2)                                   # la main tile du porteur (monte en (2,2))
    assert P.effets(st).keys() == {main}, "l'effet est sur la MAIN TILE, et sur elle seule"
    (etype, turns, source), = P.effets(st)[main]
    assert etype == FLAMES_OF_MUTATION_FIRE == int(EffectType.Fire) == 5
    assert source == main, "la TUILE est sa propre source (selecteur source natif = 0)"
    # `DefaultAmountOfRounds(Fire) = 2` rounds, x2 joueurs = 4 tours (mesure live : 4).
    assert default_amount_of_rounds(int(EffectType.Fire)) == 2
    assert turns == 2 * st.turn_order_player_count == 4
    # AUCUNE unite n'est posee : ce passif ne spawne rien.
    assert neuves == []


# --- 8. LA CHAINE -------------------------------------------------------------------------------
def test_la_chaine_pink_puis_blue():
    """Pink meurt -> 2 Blue Horrors -> une Blue meurt -> SA tuile brule. C'est ce qui APPARIE les
    deux items : le summon pose par `Split` porte `FlamesOfMutation` par son kit gameconfig."""
    st = P.monter(PINK, SPLIT_KEY, owner_turn=True)
    _, neuves = jouer(st)
    assert len(neuves) == 2
    cible = neuves[0]
    st.get_entity(cible).get_component(UnitComponent).alive = False
    st.get_entity(cible).get_component(HealthComponent).hp = 0
    out2, _ = jouer(st, dying=cible)
    assert out2 and out2[0]["ability"] == FLAMES_OF_MUTATION_KEY
    pc = st.get_entity(cible).get_component(PositionComponent)
    assert P.tid(pc.col, pc.row) in P.effets(st)


# --- 9. GROUND TRUTH LIVE -----------------------------------------------------------------------
def test_stats_des_blue_horrors_sous_multiplier_180():
    """GROUND TRUTH LIVE (runner 446, board MC1_67, Abraxas `thousInfernalMaster` -> Pink Horror
    tuee sans overkill) : le stream natif rend `UnitStats_MaxHealth=2093 UnitStats_Attack=1795`
    pour les deux Blue Horrors, sous `VariableMultiplierPercentage=180`.

    C'est l'etage `WithStatsFromConfig(config, abilityState)` : les stats du summon viennent de
    l'`AbilityState` du PASSIF du porteur, pas de son canal d'active -- et `summonHp`/`summonDmg`
    sont dans `variablesAffectedByRarityBonus`, donc SCALES par le multiplier. Sans le
    `ability_state=` de la feuille, elles se liraient a l'index 0 (mode de panne #174)."""
    st = P.monter(PINK, SPLIT_KEY, owner_turn=True, mult=180)
    _, neuves = jouer(st)
    assert len(neuves) == 2
    for nid in neuves:
        ctx = st.get_entity(nid).get_component(StatsComponent).ctx
        assert (ctx.health, ctx.attack) == (2093, 1795), nid
        assert st.get_entity(nid).get_component(HealthComponent).hp_max == 2093
    # la chaine des DEUX magnitudes, re-derivee du gameconfig (aucun chiffre recopie)
    v = (GC.ability(SPLIT_KEY) or {})["variables"]
    assert round(v["summonHp"][49] * 180 / 100) == 2093
    assert round(v["summonDmg"][49] * 180 / 100) == 1795


# --- 10. la constante NON LUE -------------------------------------------------------------------
def test_flames_of_mutation_chance_reste_non_lue():
    """`abilities.FlamesOfMutation.constants.chance = "50"` EXISTE en gameconfig et n'est lue par
    AUCUNE des quatre methodes de la classe native (`get_AllowForDeadOwner`, `CreateTrigger` -- le
    corps PARTAGE avec `Split`, qui n'a pas de `chance` --, `CreateBehaviour`, `.ctor`), et aucun
    gate de chance generique n'existe dans `BaseTriggeredAbility$$ShouldTrigger`/`$$Execute`.

    Ce test garde le RESULTAT « constante non lue » : il rougirait si quelqu'un ajoutait un
    `Maybe(50)` au port -- le gate INVENTE de l'anti-pattern §2.1. Il assertionne d'abord que la
    constante EXISTE, faute de quoi il serait vert sans rien garder."""
    cfg = GC.ability(FLAMES_OF_MUTATION_KEY) or {}
    assert (cfg.get("constants") or {}).get("chance") == "50", "premisse : la constante existe"
    assert not (cfg.get("variables") or {}), "FlamesOfMutation n'a AUCUNE variable de niveau"
    # 200 poses sur 200 montages non-overkill : le feu tombe A CHAQUE FOIS (aucun jet de 50 %).
    poses = 0
    for seed in range(1000, 1200):
        st = P.monter(BLUE, FLAMES_OF_MUTATION_KEY, owner_turn=True, seed=seed)
        out, _ = jouer(st)
        poses += 1 if (out and out[0]["tiles"][0]["placed"]) else 0
    assert poses == 200, "un gate de chance a ete introduit : %d/200" % poses
