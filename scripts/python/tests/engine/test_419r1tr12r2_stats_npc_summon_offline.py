"""#419-r1-tr12-r2 -- GARDES du chemin de stats explicite npc / summon.

Le probe `probe_419r1tr12r2_stats_npc_summon.py` MESURE ; ce fichier GARDE. Tout est OFFLINE : le
chemin ARME dans `buildNormalizedBC`, lui, exige la session live, et il est garde LA OU IL SERT --
`tests/engine/test_419r1tr12r2_electro_shock_reel_live.py`, dont le montage entier repose sur le
npc amene au pool par ce chemin (12 gardes, cf. `case-419-r1-tr12-r2-stats-npc-summon.md` §11).

Ce qui est garde ici, et pourquoi :

  1. le TEMOIN -- le mirror npc reproduit ce que LE JEU a ecrit dans le seed BC capture, et le
     temoin est assertionne NON VIDE et NON NUL (un accord sur zero entree, ou sur des entrees a
     0, serait un vert de regime degenere) ;
  2. les REGLES d'indexation (`GetStatsForLevel` + `ToZeroBasedIndex` + `GetLevelFromUnitId`)
     chacune par un cas qui la fait MORDRE ;
  3. le fait que le catalogue d'un SUMMON porte 0 cote jeu -- pour qu'on ne prenne jamais le
     montage `summon-spawn` pour un mirror de catalogue ;
  4. les deux chemins rendent des valeurs DISTINCTES et non nulles.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

import catalog_inject as CI          # noqa: E402
import gameconfig as G               # noqa: E402

NPC_ID = "admecNpc3Electropriest"
NPC_LEVEL = 33
SMN_ID = "admecSmnElectropriest"


@pytest.fixture(scope="module")
def seed_bc() -> dict:
    return json.loads(CI.SEED_BC.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- 1. le TEMOIN
def test_temoin_npc_non_vide_et_non_nul(seed_bc):
    """Un temoin vide ou a zero s'accorderait avec n'importe quoi : on l'assertionne d'abord."""
    ents = CI.npc_entries_of(seed_bc)
    assert ents, "aucune entree npc dans le seed BC -- le temoin serait vide"
    hp = [int(u.get("Health") or 0) for u in ents]
    assert min(hp) > 0, f"temoin degenere, Health={hp}"


def test_mirror_npc_reproduit_ce_que_le_jeu_a_ecrit(seed_bc):
    """`catalog_inject.npc_stats` == `BC.Units[]` produit par
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` en bataille reelle."""
    rows, div = CI.npc_witness_diff(seed_bc)
    assert rows, "temoin vide"
    assert div == 0, f"divergences: {[(u, b) for u, b in rows if b]}"


# ------------------------------------------------------------------- 2. les REGLES d'indexation
def test_level_par_defaut_est_1_pas_le_dernier_palier():
    """`idun.shared.UnitNamingConventions$$GetLevelFromUnitId` rend 1 sans suffixe -- pas 0
    (qui ferait lever `ToZeroBasedIndex`) et pas le dernier palier."""
    assert CI.unit_level_from_id(NPC_ID) == 1
    assert CI.unit_level_from_id(f"{NPC_ID}:33") == 33
    # Suffixe non numerique : `Int32.TryParse` echoue -> le natif rend 1.
    assert CI.unit_level_from_id(f"{NPC_ID}:pvp") == 1
    rows = G.unit(NPC_ID)["stats"]
    assert CI.npc_stats(NPC_ID)["Health"] == int(rows[0]["Health"])
    assert CI.npc_stats(NPC_ID)["Health"] != int(rows[-1]["Health"])


def test_clamp_haut_et_refus_du_level_nul():
    """`GetStatsForLevel` clampe au dernier palier (`Math.Min(idx, Count-1)`) ; `ToZeroBasedIndex`
    LEVE sur `level <= 0` -- le mirror doit lever aussi, pas clamper en silence."""
    rows = G.unit(NPC_ID)["stats"]
    haut = CI.npc_stats(f"{NPC_ID}:{len(rows) + 500}")
    assert haut["Health"] == int(rows[-1]["Health"])
    with pytest.raises(ValueError):
        CI.npc_stats(f"{NPC_ID}:0")
    with pytest.raises(ValueError):
        CI.npc_stats(NPC_ID, level=-3)


def test_paliers_voisins_discriminent():
    """Si deux paliers consecutifs rendaient la meme chose, le test du temoin ne prouverait pas
    que l'indexation est la bonne."""
    a = CI.npc_stats(f"{NPC_ID}:{NPC_LEVEL}")["Health"]
    b = CI.npc_stats(f"{NPC_ID}:{NPC_LEVEL - 1}")["Health"]
    assert a != b and a > 0 and b > 0


def test_multiplicateur_indexe_par_progression_index():
    """`GetAbilityVariablesMultiplierPercentageForProgressionIndex` INDEXE la liste, il ne cherche
    pas le premier palier couvrant un rank. Mesure : `necroNpc3Deathmark:7` porte
    ProgressionIndex 4 et 120 -- exactement `heroProgressionSteps[4]`."""
    steps = G._cfg()["units"]["heroProgressionSteps"]
    assert CI.npc_progression_multiplier_pct(4) == steps[4]["abilityStatMultiplierPct"]
    # Deux index qui donnent des valeurs differentes : sans ca l'assertion ci-dessus serait creuse.
    vals = {CI.npc_progression_multiplier_pct(i) for i in range(len(steps))}
    assert len(vals) > 1, "le multiplicateur est constant, l'indexation n'est pas testee"


# --------------------------------------------------------- 3. le catalogue SUMMON porte 0
def test_le_jeu_ecrit_zero_pour_les_summons(seed_bc):
    """65/65 mesure : les stats d'un summon ne viennent PAS du catalogue. C'est ce qui interdit de
    lire le montage `summon-spawn` comme un mirror de `BC.Units[]`."""
    smn = G._cfg()["units"]["summons"]
    ents = [u for u in seed_bc["Units"] if str(u.get("Id", "")).split(":")[0] in smn]
    assert ents, "aucune entree summon -- mesure vide"
    assert [u["Id"] for u in ents if int(u.get("Health") or 0) != 0] == []


def test_aucun_summon_du_gameconfig_ne_porte_de_table_stats():
    smn = G._cfg()["units"]["summons"]
    assert smn
    assert [k for k, v in smn.items() if v.get("stats")] == []


# ------------------------------------------------------------- 4. les deux chemins, distincts
def test_chemin_summon_lit_les_variables_de_l_ability():
    """`GetSummonStats` lit `summonHp`/`summonDmg`/`summonArmor` de l'ability qui declare le
    summon -- ici `EnvFactionSummons:AdeptusMechanicus`, seule a porter
    `constants.unitId == admecSmnElectropriest` (aucune unite ne la porte : c'est un summon
    d'ENVIRONNEMENT, d'ou l'absence d'invocateur a spawner)."""
    decl = CI.summon_declaring_abilities(SMN_ID)
    assert [d[0] for d in decl] == ["EnvFactionSummons:AdeptusMechanicus"]
    assert decl[0][1] == "unitId" and decl[0][2] is True     # regime PRIMARY, pas `_2`
    st = CI.summon_stats(SMN_ID, ability_level=50)
    a = G.ability("EnvFactionSummons:AdeptusMechanicus")
    assert st["Health"] == int(a["variables"]["summonHp"][49])
    assert st["Damage"] == int(a["variables"]["summonDmg"][49])
    assert st["FixedArmor"] == int(a["variables"]["summonArmor"][49])
    # Variables absentes -> champ INCHANGE (0), pas une valeur inventee : `if (var != 0)` natif.
    assert "summonCritChance" not in a["variables"]
    assert st["CritChance"] == 0


def test_declarant_ambigu_refuse_au_lieu_de_choisir():
    """23 des 65 summons sont declares par PLUSIEURS abilities, et leurs profils divergent :
    `necroSmnSwarm` rend 1109 hp par `ScarabHive` et 0 par `ScarabSummon`. Choisir le premier en
    silence poserait des stats fausses sans rien dire."""
    decl = [d[0] for d in CI.summon_declaring_abilities("necroSmnSwarm")]
    assert len(decl) > 1, "cas d'ambiguite disparu du gameconfig -- re-choisir un porteur"
    with pytest.raises(KeyError, match="stats DIFFERENTES"):
        CI.summon_stats("necroSmnSwarm")
    # Nommer l'ability leve l'ambiguite, et les deux reponses different bien.
    a = CI.summon_stats("necroSmnSwarm", "ScarabHive")["Health"]
    b = CI.summon_stats("necroSmnSwarm", "ScarabSummon")["Health"]
    assert a > 0 and b == 0 and a != b


def test_variable_summon_a_zero_donne_zero():
    """`ScarabHive.summonArmor` est un tableau de 65 zeros : le summon a bien 0 d'armure. La
    branche `if (var != 0)` du natif est donc EXERCEE ici -- mais elle est ALGEBRIQUEMENT
    indistinguable d'un ecrasement inconditionnel, parce que la valeur de depart d'un summon est
    elle-meme 0 (sa config n'a pas de `stats[]`). Ce test fige le RESULTAT, pas la branche."""
    a = G.ability("ScarabHive")
    assert all(int(x) == 0 for x in a["variables"]["summonArmor"])
    st = CI.summon_stats("necroSmnSwarm", "ScarabHive", ability_level=50)
    assert st["FixedArmor"] == 0
    assert st["Health"] == int(a["variables"]["summonHp"][49]) > 0


def test_regime_secondaire_reproduit_une_mesure_LIVE_anterieure():
    """SECOND TEMOIN NON NUL, et celui-la est LIVE.

    `GetSummonStats` choisit entre les variables `summon*` et leurs variantes `_2` selon le
    `AbilityConstantType` qui portait l'unitId (`isPrimary = ct in (unitId, unitToSpawn)`).
    `MasterOfTheTutelaries` est le cas discriminant : elle declare `thousSmnPinkHorror` en
    `unitId` (PRIMARY) et `thousSmnScreamer` en `unitId_2` (SECONDAIRE), et elle porte LES DEUX
    jeux de variables -- `summonHp[50] = 1994` et `summonHp_2[50] = 2493`.

    La valeur attendue n'est pas re-derivee du gameconfig : elle vient d'une mesure LIVE
    anterieure et independante, citee dans
    `engine/runner/operations/spawn.py` (#202c, runner 183) -- « Screamer MaxHealth 4487 =
    summonHp_2[50] x 180% ». Un mirror qui resterait en regime PRIMARY rendrait 3589.
    """
    st = CI.summon_stats("thousSmnScreamer", "MasterOfTheTutelaries",
                         ability_level=50, multiplier_pct=180)
    assert st["Health"] == 4487, "regime `_2` non reproduit (mesure live #202c)"
    assert st["_primary"] is False
    a = G.ability("MasterOfTheTutelaries")
    primary_aurait_donne = round(int(a["variables"]["summonHp"][49]) * 180 / 100)
    assert primary_aurait_donne != 4487, "les deux regimes coincident : le test ne discrimine pas"
    # Et le PRIMARY de la MEME ability rend bien l'autre valeur.
    horror = CI.summon_stats("thousSmnPinkHorror", "MasterOfTheTutelaries",
                             ability_level=50, multiplier_pct=180)
    assert horror["_primary"] is True
    assert horror["Health"] == primary_aurait_donne != st["Health"]


def test_multiplicateur_de_rarete_applique_aux_variables_flaggees():
    """Le multiplicateur ne s'applique qu'aux variables listees en
    `variablesAffectedByRarityBonus` (= `VariablesAffectedByUnitRarityMultiplier` cote BC), meme
    regle que `engine.entities.effects.magnitude.ability_var`. Ce que ce test etablit vraiment :
    l'APPLICATION, pas la SELECTION -- voir le test suivant, qui mesure pourquoi."""
    a = G.ability("EnvFactionSummons:AdeptusMechanicus")
    flags = set(a.get("variablesAffectedByRarityBonus") or [])
    assert {"summonHp", "summonDmg", "summonArmor"} <= flags
    x100 = CI.summon_stats(SMN_ID, ability_level=50, multiplier_pct=100)
    x180 = CI.summon_stats(SMN_ID, ability_level=50, multiplier_pct=180)
    for f in ("Health", "Damage", "FixedArmor"):
        assert x180[f] == round(x100[f] * 180 / 100) > x100[f] > 0


def test_le_filtre_du_multiplicateur_est_DISCRIMINANT():
    """CONTRE-EPREUVE du filtre, sur un cas reel : `PhasalSubjugator` (qui declare
    `necroSmnWarrior`) ne porte AUCUN `variablesAffectedByRarityBonus`, donc AUCUNE de ses
    variables `summon*` ne doit bouger avec le multiplicateur -- alors que celles de
    `EnvFactionSummons:AdeptusMechanicus`, toutes flaggees, bougent.

    Le cas est DERIVE du gameconfig, pas choisi a la main : le balayage liste toutes les
    variables `summon*` non nulles et non flaggees, et le test refuse un balayage vide (sans
    cas discriminant, le filtre ne serait pas testable et il faudrait le dire).
    """
    ab = G._cfg()["units"]["abilities"]
    non_flaggees = []
    for uid in G._cfg()["units"]["summons"]:
        for name, _key, prim in CI.summon_declaring_abilities(uid):
            a = ab[name]
            flags = set(a.get("variablesAffectedByRarityBonus") or [])
            variables = a.get("variables") or {}
            for _field, kp, ks in CI.SUMMON_STAT_VARS:
                key = kp if prim else ks
                arr = variables.get(key)
                if arr and int(arr[-1]) > 0 and key not in flags:
                    non_flaggees.append((uid, name, key))
    assert non_flaggees, "aucun cas non flagge : le filtre n'est pas testable, le dire"
    uid, name, _key = non_flaggees[0]
    x100 = CI.summon_stats(uid, name, ability_level=50, multiplier_pct=100)
    x180 = CI.summon_stats(uid, name, ability_level=50, multiplier_pct=180)
    bouge = [f for f in CI.COMBAT_STAT_FIELDS if x100[f] != x180[f]]
    assert bouge == [], f"{name} n'a aucun flag et pourtant {bouge} a bouge"
    assert x100["Health"] > 0, "cas degenere : rien a observer"


def test_declarants_couvrent_les_trois_constantes_du_natif():
    """`GetSummonStats(kind, cfg)` n'interroge QUE `unitToSpawn`(8), `unitId`(0) et `unitId_2`(4).
    On fige cette liste : l'elargir sans relire le decompile inventerait un chemin.

    ⚠ REECRIT par #419-r1-tr12-r2-r1, et RENFORCE. L'ancienne version exigeait le message
    « aucune ability » pour le premier hors-portee venu, ce qui melangeait DEUX causes que le
    decompile separe : le summon ORPHELIN (aucune ability du gameconfig ne le nomme, par aucune
    voie) et celui que seule la voie DYNAMIQUE atteint (`unitId_3` .. `unitId_6` -- ordinal de
    behaviour, autre famille de variables). Le refus doit NOMMER laquelle.
    """
    assert [k for k, _o, _p in CI.SUMMON_ID_CONSTANTS] == \
        ["unitToSpawn", "unitId", "unitId_2"]
    assert [p for _k, _o, p in CI.SUMMON_ID_CONSTANTS] == [True, True, False]
    smn = G._cfg()["units"]["summons"]
    hors_portee = [k for k in smn if not CI.summon_declaring_abilities(k)]
    assert hors_portee, "plus aucun hors-portee -- re-mesurer avant de relacher ce test"
    par_verdict: dict = {}
    for uid in hors_portee:
        par_verdict.setdefault(CI.summon_spawn_regimes(uid)["verdict"], []).append(uid)
    # Les DEUX formes existent sur ce build : sans cela le test ne separerait rien.
    assert sorted(par_verdict) == ["dynamic-only", "orphelin"], par_verdict
    with pytest.raises(KeyError, match="summon ORPHELIN"):
        CI.summon_stats(par_verdict["orphelin"][0])
    with pytest.raises(KeyError, match="voie\\s+DYNAMIQUE"):
        CI.summon_stats(par_verdict["dynamic-only"][0])
    print("\n[419r1tr12r2r1] hors portee des 3 constantes fixes : %d "
          "(orphelins %d, dynamic-only %d)"
          % (len(hors_portee), len(par_verdict["orphelin"]),
             len(par_verdict["dynamic-only"])))


def test_niveau_d_ability_deplace_les_stats_du_summon():
    lo = CI.summon_stats(SMN_ID, ability_level=1)["Health"]
    hi = CI.summon_stats(SMN_ID, ability_level=50)["Health"]
    assert 0 < lo < hi


def test_explicit_stats_nomme_sa_source():
    """Le `source` distingue le MIRROR DE CATALOGUE du MONTAGE post-spawn. Les confondre ferait
    passer une valeur de harnais pour ce que le jeu ecrit."""
    assert CI.explicit_stats(f"{NPC_ID}:{NPC_LEVEL}")["source"] == "npc"
    assert CI.explicit_stats(SMN_ID)["source"] == "summon-spawn"


def test_les_deux_chemins_rendent_des_valeurs_utilisables():
    npc = CI.explicit_stats(f"{NPC_ID}:{NPC_LEVEL}")["fields"]
    smn = CI.explicit_stats(SMN_ID)["fields"]
    for f in ("Health", "Damage", "FixedArmor"):
        assert npc[f] > 0 and smn[f] > 0
    assert npc["Health"] != smn["Health"]
    # Les 8 champs de combat sont TOUS presents des deux cotes : une cle manquante laisserait la
    # valeur precedente du catalogue en place, donc un melange des deux regimes.
    for d in (npc, smn):
        assert set(CI.COMBAT_STAT_FIELDS) <= set(d)


def test_apply_explicit_stats_ecrit_dans_l_entree(seed_bc):
    import copy
    uid = f"{NPC_ID}:{NPC_LEVEL}"
    bc, _added, _ab, _un = CI.augment(copy.deepcopy(seed_bc), [uid], rank=17)
    avant = next(u for u in bc["Units"] if u["Id"] == uid)
    assert int(avant.get("Health") or 0) == 0            # la synthese part bien de 0
    rep = CI.apply_explicit_stats(bc, uid)
    apres = next(u for u in bc["Units"] if u["Id"] == uid)
    assert apres["Health"] == rep["fields"]["Health"] > 0
    assert apres["RemainingHealth"] == apres["Health"]   # spawn a PV pleins
    # Les traits et armes du VRAI porteur sont la : c'est ce que la GREFFE ne couvrait pas.
    assert apres["Weapons"] and apres["Traits"]
    assert "NPC" in apres["Traits"]
    with pytest.raises(KeyError):
        CI.apply_explicit_stats(bc, "cetIdNexistePas:1")


def test_le_porteur_npc_a_bien_le_kit_du_summon():
    """Justification du porteur de substitution : `admecNpc3Electropriest` porte EXACTEMENT les
    memes passifs, la meme arme et le meme Movement que `admecSmnElectropriest`, qui lui n'a
    aucun invocateur a spawner. C'est ce qui rend `1303 ElectroShock` confrontable sur son propre
    porteur plutot que par greffe."""
    npc = G.unit(NPC_ID)
    smn = G.unit(SMN_ID)
    assert npc["passiveAbilities"] == smn["passiveAbilities"] == \
        ["VoltagheistField", "ElectroShock"]
    assert npc["weapons"] == smn["weapons"]
    assert npc["Movement"] == smn["Movement"]
    # La difference EST le trait `Summon` -- et elle est reelle, pas cosmetique.
    assert "Summon" in smn["traits"] and "Summon" not in npc["traits"]


# ==================================================================================================
# #419-r1-tr12-r2-r1 -- LES DEUX ETAGES DE STATS DE SPAWN
#
# Le residu classait 9 summons « hors portee des trois constantes » et proposait d'elargir
# `GetSummonStats`. Le decompile de `t6dpr4k06g` dit que c'est le mauvais axe : la couche META
# (`IdunMetaLogic.UserProgress.UnitProgression$$GetSummonStats`) deduit son regime d'une CONSTANTE
# d'id, la couche BATAILLE (`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig`
# et `$$WithStatsFromConfigSpawn`) recoit un ORDINAL du behaviour et lit une famille de variables
# qui peut etre AUTRE (`spawn*`). Elargir aurait rendu 8 zeros.
# ==================================================================================================

def test_le_nom_dynamique_est_nu_a_l_ordinal_1():
    """Mirror de `IdunBattle.Configuration.AbilityConfiguration$$GetDynamicTypeu003C__Il2CppFullySharedGenericStructTypeu003E` :
    `if (ordinal > 1) name = Concat(name, "_", ordinal)`. Le `> 1` est LU -- un mirror qui
    suffixerait des l'ordinal 1 chercherait `unitId_1`, qui n'existe dans AUCUN des deux enums."""
    assert CI.dynamic_member_name("unitId", 1) == "unitId"
    assert CI.dynamic_member_name("unitId", 0) == "unitId"       # le natif n'en produit pas, mais
    assert CI.dynamic_member_name("unitId", 2) == "unitId_2"     # la borne est `> 1`, pas `>= 1`
    assert CI.dynamic_member_name("summonHp", 3) == "summonHp_3"
    assert CI.dynamic_member_name("spawnHp", 4) == "spawnHp_4"
    # Et les noms construits SONT des membres du build : `Enum.TryParse` LEVE sinon.
    consts = CI.enum_map("IdunBattle.Configuration.AbilityConstantType")
    variables = CI.enum_map("IdunBattle.Configuration.AbilityVariableType")
    assert consts, "table d'enums vide -- rien n'est confronte"
    for o in range(1, CI.DYNAMIC_ID_MAX_ORDINAL + 1):
        assert CI.dynamic_member_name("unitId", o) in consts, o
    assert "unitId_%d" % (CI.DYNAMIC_ID_MAX_ORDINAL + 1) not in consts, \
        "l'enum porte un ordinal de plus -- relire le decompile avant de relever la borne"
    for _f, base_smn, base_spw in CI.SPAWN_STAT_BASES:
        assert base_smn in variables and base_spw in variables


def test_les_deux_familles_de_variables_sont_disjointes_et_completes():
    """`WithStatsFromConfig*` pose les MEMES 7 StatType dans les deux familles -- c'est la BASE qui
    change, pas la liste. Un mirror qui melangerait les deux lirait la mauvaise cle."""
    champs_smn = {f for f, _p, _s in CI.SUMMON_STAT_VARS}
    champs_spawn = {f for f, _a, _b in CI.SPAWN_STAT_BASES}
    assert champs_smn == champs_spawn, (champs_smn, champs_spawn)
    assert len(CI.SPAWN_STAT_BASES) == 7
    bases_smn = {b for _f, b, _s in CI.SPAWN_STAT_BASES}
    bases_spw = {b for _f, _s, b in CI.SPAWN_STAT_BASES}
    assert not (bases_smn & bases_spw)
    assert all(b.startswith("summon") for b in bases_smn)
    assert all(b.startswith("spawn") for b in bases_spw)
    # La voie META lit les MEMES bases `summon*` a l'ordinal 1/2 : c'est le meme jeu de variables,
    # atteint autrement. Une divergence ici voudrait dire que l'un des deux mirrors a derive.
    assert {p for _f, p, _s in CI.SUMMON_STAT_VARS} == bases_smn
    assert {s for _f, _p, s in CI.SUMMON_STAT_VARS} == \
        {CI.dynamic_member_name(b, 2) for b in bases_smn}


def test_les_deux_summons_HSE_sont_atteints_par_la_voie_DYNAMIQUE_seule():
    """Ce que la fiche appelait « constantes que l'overload n'interroge pas » : `unitId_3`(109) et
    `unitId_4`(123) sont les ORDINAUX 3 et 4 de la meme base `unitId`, et l'ability qui les porte
    ne detient AUCUNE variable `summon*` -- elle detient des `spawn*`."""
    for uid, ordinal in (("thousSmnBlueHorrorHSE", 3), ("thousSmnScreamerHSE", 4)):
        reg = CI.summon_spawn_regimes(uid)
        assert reg["verdict"] == "dynamic-only", reg
        assert reg["meta"] == []
        assert [d["ability"] for d in reg["dynamic"]] == ["EnvAllyAndEnemyNpcs:WarpSurge"]
        d = reg["dynamic"][0]
        assert d["ordinal"] == ordinal and d["constant"] == "unitId_%d" % ordinal
        assert d["summonVariables"] == {}, "une variable summon* est apparue -- relire l'ability"
        assert d["spawnVariables"], "l'ability ne porte plus de spawn* -- le verdict tombe"
    # CONTRE-BRAS : les ordinaux 1 et 2 de la MEME ability sont, eux, atteints par les constantes
    # FIXES -- et pourtant leur profil META est nul, pour la meme raison (aucune variable summon*).
    for uid in ("blackSmnBloodletterHSE", "thousSmnPinkHorrorHSE"):
        reg = CI.summon_spawn_regimes(uid)
        assert reg["meta"] and reg["meta"][0]["variables"] == {}, reg
        assert reg["verdict"] == "dynamic-only", reg


def test_le_patch_summon_spawn_integralement_nul_est_REFUSE():
    """Un patch a 8 zeros pose un porteur a 0 PV, et le RPC l'ecrit sans broncher : c'est un echec
    RENDU, donc lu comme une mesure. L'echappatoire existe et elle est NOMMEE."""
    smn = G._cfg()["units"]["summons"]
    nuls = []
    for uid in sorted(smn):
        try:
            st = CI.summon_stats(uid)
        except KeyError:
            continue
        if not any(st[f] for f in CI.COMBAT_STAT_FIELDS):
            nuls.append(uid)
    assert nuls, "aucun profil nul -- le refus ne garde plus rien, re-mesurer"
    for uid in nuls:
        with pytest.raises(ValueError, match="INTEGRALEMENT NUL"):
            CI.explicit_stats(uid)
        rep = CI.explicit_stats(uid, allow_zero_profile=True)
        assert rep["zeroProfile"] is True
        assert all(rep["fields"][f] == 0 for f in CI.COMBAT_STAT_FIELDS)
    # CONTRE-BRAS : un summon au profil NON nul passe, et ne se declare pas `zeroProfile`.
    ok = CI.explicit_stats(SMN_ID)
    assert ok["zeroProfile"] is False and ok["fields"]["Health"] > 0
    print("\n[419r1tr12r2r1] profils summon-spawn INTEGRALEMENT NULS refuses : %d %r"
          % (len(nuls), nuls))


def test_le_refus_d_ambiguite_ne_protegeait_PAS_du_profil_nul():
    """La cause pour laquelle le refus d'ambiguite laissait passer `genesSmnDecoy` : ses cinq
    abilities declarantes rendent des profils EGAUX -- egaux parce que tous NULS. C'est l'accord en
    regime degenere, qui ne prouve rien. Sans ce test, la reparation se lirait comme redondante."""
    cands = CI.summon_declaring_abilities("genesSmnDecoy")
    assert len(cands) >= 2, cands
    profils = {n: tuple(CI.summon_stats("genesSmnDecoy", n)[f] for f in CI.COMBAT_STAT_FIELDS)
               for n, _k, _p in cands}
    assert len(set(profils.values())) == 1, profils      # donc AUCUNE ambiguite detectee
    assert not any(any(v) for v in profils.values()), profils   # et tous NULS
    # Le desalignement qui l'explique, LU dans le gameconfig : la constante dit `_2`, l'ability ne
    # porte que les variables NUES (donc l'ordinal 1 de `WithStatsFromConfig`).
    sl = next(c for c in cands if c[0] == "SpiritualLeader")
    assert sl[1] == "unitId_2" and sl[2] is False
    variables = (G.ability("SpiritualLeader") or {}).get("variables") or {}
    assert "summonHp" in variables and "summonHp_2" not in variables
