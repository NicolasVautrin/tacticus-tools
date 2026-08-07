"""#512 -- CLIQUET du port de `1197 ExcruciatingFrequencies` (`emperNoiseMarine` « Shiron »).

Ce que ce fichier garde, et que le probe live (`probe_512_excruciating_frequencies.py`) ne garde
pas : le probe MESURE (il a besoin d'une session Frida chaude) ; ce test GARDE, hors ligne, les six
proprietes dont la perte serait SILENCIEUSE.

  [1] CONTRAT DE DISJONCTION -- 1197 est dans `ABILITY_CLASSES` et porte son masque, donc elle doit
      avoir DISPARU des tables « non portee » (`TARGETING_OPTIONS_UNPORTED`,
      `DYNAMIC_TARGET_RULE_UNPORTED`, `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`). La faute inverse ne
      casse rien a l'execution : elle donne DEUX sources au masque, et `probe_181` reste VERT
      (il verifie qu'un masque EXISTE, jamais qu'il n'est declare QU'UNE FOIS).

  [2] ORDINAUX MESURES AU SITE -- `probe_313` compare le MIRROR au build et redevient vert des
      qu'on regenere le mirror apres un renumerotage, alors que la valeur ECRITE au site, elle, a
      change. On fige donc ici les entiers LUS au decompile : `rules = 0x20000000042` (dont le bit
      **41**, au-dela de 32), `TemporaryStatModifier = 0x56c`, `StatType.CritChance = 0x9`,
      `AbilityConstantType.nrOfTiles = 0x17`, `AbilityVariableType.extraCritChance = 0x41`,
      `AbilityAttackType = 2 = Others`.

  [3] LA QUALIFICATION DES DEUX ENUMS DE CONFIG -- et c'est le piege silencieux du cas : `0x17` et
      `0x41` sont TOUS LES DEUX des ordinaux valides dans `AbilityConstantType` **et** dans
      `AbilityVariableType`, et ils y nomment autre chose. Confondre les deux aurait lu deux
      mauvaises cles du gameconfig SANS lever la moindre erreur. Le discriminant est l'ACCESSEUR
      appele au site (`GetNumberConstant` / `GetVariableForLevel`), jamais l'ordinal.

  [4] LA STRUCTURE DE L'ARBRE -- `(AddStaticStatModifierEffect & AttackWithAttackDamage)
      & RemoveEffect`, dans CET ordre (le buff pose AVANT l'attaque, retire APRES), et **AUCUN
      `AtomicGroup`** : la callee native est `AActiveAbility$$Execute` (2 arguments), pas
      `$$ExecuteAtomic` (3 arguments) -- CONTRASTE avec `DoomSiren` (1199) dans le meme module et
      avec `LeadingTheCharge` (1204).

  [5] LE COMPTE PORTE SUR *TOUTES* LES UNITES DE LA LIGNE, L'ATTAQUE SUR LES SEULS ENNEMIS. Deux
      selecteurs DISTINCTS batis sur le meme `GetAffectedTiles`. La faute (reutiliser le selecteur
      d'ennemis pour le `Count`) est INVISIBLE de tout regime sans allie sur la ligne -- d'ou le
      substrat mixte ci-dessous, et d'ou le couple R1/R2 du probe live. MESURE (#512, board
      `MC1_67`) : le natif publie `UnitStats_CritChance_Modification_Change=90` avec l'allie sur la
      ligne, `60` sans -- memes ennemis, memes tuiles, meme seed.

  [6] LA BORNE `nrOfTiles` -- le rayon fait exactement `constants.nrOfTiles` tuiles. Sans elle il
      irait jusqu'au bord du plateau, et une unite au-dela compterait ET serait frappee.

RESIDU `#512-r1` (mesure, pas suppose) : en regime NOMINAL le port SOUS-TIRE, parce que
`SuppressiveFireAddEffectAbility` n'ecoute que `On(NormalAttack = 38)` et ne pose donc pas `Pinned`
sur les cibles d'une attaque d'ABILITY -- si bien que `TerrifyingCrescendo` ne monte pas. Le MEME
montage prive du passif du caster rend le degat **bit-exact** (9575 / 7101 des deux cotes, 6
tirages). L'ecart n'est PAS dans ce mirror ; il est dans le vecteur de dispatch d'un trait partage
par 49 porteurs.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre DECLARE LARGE, et c'est mesure : charger une ability tire le registre, le vocabulaire
#: DSL, les Operations, l'IA, le pathfinding et les utilites, plus la cascade des `conftest.py`. Une
#: liste feuille a feuille rougirait au premier import ajoute. `**/` exige un SEGMENT, d'ou les deux
#: globs ET les conftest ecrits un par un.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
        # 4e face du contrat de disjonction : ce fichier PORTE
        # `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`, dont on garde que 1197 est sortie. C'est une
        # dependance REELLE (import), pas un voisinage -- elle doit donc declencher.
        "scripts/python/tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1197 et TOUT ce que sa fermeture d'imports traverse : registre "
              "d'abilities, tables de ciblage, vocabulaire DSL (selecteurs de geometrie, formules), "
              "Operations d'effet et de degat. `build: True` parce que les ordinaux figes ici "
              "(masque 64 bits, EffectType, StatType, AbilityConstantType, AbilityVariableType, "
              "AbilityAttackType) sont LUS dans le binaire du build -- un changement de build peut "
              "les renumeroter, et c'est precisement ce que ce fichier doit faire rougir.",
}

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import gameconfig as GC                                                    # noqa: E402
import hexgeo                                                              # noqa: E402
import engine.battle_query as bq                                           # noqa: E402
from engine.entities.ability_constant_type import AbilityConstantType      # noqa: E402
from engine.entities.ability_variable_type import AbilityVariableType      # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.behaviours import Seq                                 # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.selectors.geometry import (Cache, SortReverse,        # noqa: E402
                                                TilesBehindInLine)
from engine.entities.selectors.units import Enemies, Units                 # noqa: E402
from engine.entities.stats import StatType                                 # noqa: E402
from engine.runner.abilities.attack_type import (ABILITY_ATTACK_TYPE,      # noqa: E402
                                                 AbilityAttackType)
from engine.runner.abilities.base import ActiveAbility                     # noqa: E402
from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage   # noqa: E402
from engine.runner.abilities.behaviours.context import entities_with_tile_target  # noqa: E402
from engine.runner.abilities.behaviours.effects import (                   # noqa: E402
    AddStaticStatModifierEffect, RemoveEffect)
from engine.runner.abilities.emperorschildren import (                     # noqa: E402
    EF_CRIT_CHANCE, EF_TEMPORARY_STAT_MODIFIER, EXCRUCIATING_FREQUENCIES_ID,
    ExcruciatingFrequenciesAbility, excruciating_frequencies_extra_crit_chance,
    excruciating_frequencies_nr_of_tiles, excruciating_frequencies_tree)
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,   # noqa: E402
                                               TARGETING_OPTIONS_UNPORTED,
                                               excruciating_frequencies_affected_tiles)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

ABILITY = int(ActiveAbilityType.ExcruciatingFrequencies)   # 1197

#: Masque LU au ctor (forme FLAGS DIRECTS, surcharge a 7 arguments) :
#: `TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x20000000042, 0, 0)`.
RULES_MESUREES = 0x20000000042


# ---------------------------------------------------------------- [1] disjonction

def test_1197_est_au_registre_et_a_UNE_seule_source_de_masque():
    """Le CONTRAT : une ability a UNE source de masque, jamais deux."""
    assert ABILITY in ABILITY_CLASSES, "1197 absente d'ABILITY_CLASSES -- le no-op n'est pas leve"
    assert ABILITY not in TARGETING_OPTIONS_UNPORTED, "deux sources de masque pour 1197"
    assert ABILITY not in DYNAMIC_TARGET_RULE_UNPORTED, (
        "1197 encore dans DYNAMIC_TARGET_RULE_UNPORTED alors que la classe SURCHARGE "
        "get_dynamic_invalid_target_reason")
    assert not (set(ABILITY_CLASSES) & set(TARGETING_OPTIONS_UNPORTED)), (
        "la disjonction globale est rompue")


def test_1197_est_sortie_du_perimetre_des_abilities_du_pool_hors_registre():
    """La 4e face du contrat : `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` est le PERIMETRE des actives du
    pool spawnable HORS registre. Y laisser 1197 ferait rougir son propre test (`intrus`), mais dans
    l'autre sens : c'est ici qu'on garde que le retrait a bien eu lieu."""
    from tests.engine.test_433_r4_r2_r1_r2_ability_range_offline import (
        POOL_ABILITIES_WITHOUT_COMBAT_CLASS)
    assert ABILITY not in POOL_ABILITIES_WITHOUT_COMBAT_CLASS


def test_la_classe_surcharge_bien_la_regle_dynamique_ET_delegue_au_foyer():
    """`TargetMatchesDynamicRule` est POSE dans le masque : sans surcharge, la base rend 0 et le gate
    serait DESARME (degradation permissive). Et la surcharge doit DELEGUER : deux mirrors du meme
    `GetDynamicInvalidTargetReason` divergeraient sans que rien ne le voie."""
    assert (ExcruciatingFrequenciesAbility.get_dynamic_invalid_target_reason
            is not ActiveAbility.get_dynamic_invalid_target_reason)
    src = ExcruciatingFrequenciesAbility.get_dynamic_invalid_target_reason.__code__.co_names
    assert "_dynamic_rule_excruciating_frequencies" in src, (
        "la surcharge ne DELEGUE plus au foyer de `targeting.py` : le corps serait duplique")


# ---------------------------------------------------------------- [2] ordinaux mesures au site

def test_ordinaux_lus_au_decompile():
    """Ce que `probe_313` ne peut PAS garder : la valeur ECRITE AU SITE au moment de la lecture."""
    opts = ExcruciatingFrequenciesAbility.TARGETING_OPTIONS
    assert int(opts.rules) == RULES_MESUREES, (
        "masque de 1197 : le ctor passe 0x20000000042 en FLAGS DIRECTS")
    assert opts.self_cast is False
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsTile
                                  | TR.AllowUntargetableTarget)
    assert EF_TEMPORARY_STAT_MODIFIER == 0x56c == int(EffectType.TemporaryStatModifier)
    assert EF_CRIT_CHANCE == 0x9 == int(StatType.CRIT_CHANCE)
    assert int(AbilityConstantType.nrOfTiles) == 0x17
    assert int(AbilityVariableType.extraCritChance) == 0x41
    assert ABILITY_ATTACK_TYPE.get(ABILITY) == AbilityAttackType.Others == 2, (
        "3e argument d'`AActiveAbility$$.ctor` = 2 = Others -- TRANSCRIT, pas deduit du "
        "comportement (1197 EST une attaque, et porterait DirectTargetAttack a l'oeil)")


def test_le_bit_41_du_masque_survit_a_une_lecture_64_bits():
    """`AllowUntargetableTarget` est le bit **41** : un masque lu ou stocke en 32 bits le perdrait
    en SILENCE, et la cible-tuile (qui n'est jamais « targetable ») serait refusee."""
    opts = ExcruciatingFrequenciesAbility.TARGETING_OPTIONS
    assert int(TR.AllowUntargetableTarget) == 1 << 41
    assert int(opts.rules) & (1 << 41)
    assert int(opts.rules) & 0xFFFFFFFF != int(opts.rules), (
        "le masque tiendrait sur 32 bits : ce test a perdu son objet")


# ---------------------------------------------------------------- [3] qualification des enums

def test_les_deux_index_de_config_sont_AMBIGUS_et_l_accesseur_tranche():
    """LE piege silencieux du cas. `0x17` et `0x41` existent dans les DEUX enums de config et y
    nomment autre chose ; le port lirait alors deux mauvaises cles du gameconfig SANS erreur.
    Le discriminant est l'ACCESSEUR appele au site, jamais l'ordinal :
    `GetNumberConstant(0x17)` -> `AbilityConstantType`, `GetVariableForLevel(0x41)` ->
    `AbilityVariableType` (types DECLARES, lus dans `frida/methods.tsv`)."""
    assert AbilityConstantType(0x17).name == "nrOfTiles"
    assert AbilityVariableType(0x17).name == "extraChance", (
        "l'ordinal 0x17 ne nomme plus autre chose dans l'autre enum -- ce test a perdu son objet")
    assert AbilityVariableType(0x41).name == "extraCritChance"
    assert AbilityConstantType(0x41).name == "armorReduction", (
        "l'ordinal 0x41 ne nomme plus autre chose dans l'autre enum -- ce test a perdu son objet")


def test_les_cles_de_config_sont_celles_du_gameconfig():
    """`nrOfTiles` est une CONSTANTE, `extraCritChance` une VARIABLE PAR NIVEAU : deux tables
    differentes du gameconfig, et le natif les lit par deux accesseurs differents."""
    cfg = GC.ability(EXCRUCIATING_FREQUENCIES_ID) or {}
    consts = cfg.get("constants") or {}
    variables = cfg.get("variables") or {}
    assert int(consts.get(AbilityConstantType.nrOfTiles.name)) == 3
    assert int(consts.get("nrOfHits")) == 1
    assert consts.get("damageProfile") == "Blast"
    assert AbilityVariableType.extraCritChance.name in variables
    assert AbilityConstantType.nrOfTiles.name not in variables, (
        "`nrOfTiles` est passe en VARIABLE : le port lit la mauvaise table")


def test_extraCritChance_est_lue_PAR_NIVEAU_et_HORS_rarity_bonus():
    """MESURE (#512, live, `--list-pool` rank 17) : le runner normalise a l'ability niveau **50**
    avec un `AbilityVariablesMultiplier` de **160 %**, et le natif publie
    `CritChance_Modification_Change = 90` pour 3 unites -> **30 par unite**, PAS 20 (niveau 1) ni 48
    (30 x 160 %). Les deux lectures fautives sont donc gardees ici :
      * ignorer le NIVEAU rendrait 20 ;
      * appliquer le MULTIPLICATEUR rendrait 48 -- or `extraCritChance` n'est pas dans
        `variablesAffectedByRarityBonus`, et c'est la CONFIG qui en decide, pas le site d'appel."""
    from engine.entities.effects.magnitude import ability_var
    cle = AbilityVariableType.extraCritChance.name
    assert int(ability_var(EXCRUCIATING_FREQUENCIES_ID, cle, 1) or 0) == 20
    assert int(ability_var(EXCRUCIATING_FREQUENCIES_ID, cle, 50) or 0) == 30
    assert int(ability_var(EXCRUCIATING_FREQUENCIES_ID, cle, 50, multiplier_pct=160) or 0) == 30, (
        "le multiplicateur de rarete MORD sur extraCritChance : il ne devrait pas")
    rarity = (GC.ability(EXCRUCIATING_FREQUENCIES_ID) or {}).get(
        "variablesAffectedByRarityBonus") or []
    assert cle not in rarity and "minDmg" in rarity


# ---------------------------------------------------------------- [4] structure de l'arbre

def test_l_arbre_est_stat_PUIS_attaque_PUIS_retrait_et_SANS_AtomicGroup():
    """`Execute( (AddStaticStatModifierEffect & AttackWithAttackDamage) & RemoveEffect )`.

    L'ORDRE est la mecanique : le buff pose AVANT l'attaque en fait beneficier les tirages de crit
    du cast, et le retrait APRES l'empeche de survivre. L'absence d'`AtomicGroup` est LUE : la
    callee native est `AActiveAbility$$Execute(behaviour, entities)` (2 arguments), pas
    `$$ExecuteAtomic(behaviour, entities, groupType)` (3)."""
    from engine.entities.behaviours import AtomicGroup
    arbre = excruciating_frequencies_tree(3, 30)
    assert isinstance(arbre, Seq)
    assert isinstance(arbre.left, Seq) and isinstance(arbre.right, RemoveEffect)
    stat, attaque = arbre.left.left, arbre.left.right
    assert isinstance(stat, AddStaticStatModifierEffect)
    assert isinstance(attaque, AttackWithAttackDamage)
    assert not isinstance(arbre, AtomicGroup), "1197 n'a AUCUN ExecuteAtomic (contraste DoomSiren)"
    assert stat.effect_type == EF_TEMPORARY_STAT_MODIFIER and stat.stat_type == EF_CRIT_CHANCE
    # `turns = DSLFormulas+0x20 = Direct(1)` -- deja en TOURS, surtout pas `TurnsFromRounds`.
    assert stat.duration_turns == 1 and stat.duration_rounds is None
    assert arbre.right.effect_type == EF_TEMPORARY_STAT_MODIFIER
    assert attaque.profile == "Blast" and attaque.is_melee is False and attaque.multi is True
    assert attaque.native_factory == "attack", (
        "famille ATTACK (`DSLBehaviors$$AttackWithAttackDamage`) : crit/block actifs")


def test_les_DEUX_selecteurs_sont_bien_DEUX_arbres_distincts():
    """Le `Count` lit `Cache(Units(GetAffectedTiles))`, l'attaque `Cache(Enemies(Units(...)))`.
    Les CONFONDRE est la faute centrale du cas, et elle est invisible sans allie sur la ligne."""
    arbre = excruciating_frequencies_tree(3, 30)
    compte = arbre.left.left.amount           # Multiply(Count(<tous>), Const(extraCritChance))
    tous = compte.a.selector
    ennemis = arbre.left.right.target_sel
    assert isinstance(tous, Cache) and isinstance(ennemis, Cache)
    assert isinstance(tous.source, Units), "le Count doit porter sur TOUTES les unites de la ligne"
    assert isinstance(ennemis.source, Enemies), "l'attaque doit porter sur les seuls ENNEMIS"
    assert isinstance(ennemis.source.inner, Units)
    for sel in (tous.source.tiles, ennemis.source.inner.tiles):
        assert isinstance(sel, SortReverse) and isinstance(sel.source, TilesBehindInLine)
        assert sel.source.check_walkable is True and sel.source.update_reference is True


def test_le_foyer_de_la_geometrie_est_PARTAGE_avec_la_regle_dynamique():
    """`GetAffectedTiles` a UN seul mirror : la face DECISION (le gate dynamique de `targeting.py`)
    et la face COMBAT le construisent par la MEME fonction. Deux geometries divergeraient."""
    sel = excruciating_frequencies_affected_tiles(3)
    assert isinstance(sel, SortReverse) and isinstance(sel.source, TilesBehindInLine)
    assert sel.source.max_count.evaluate(None) == 3


# ---------------------------------------------------------------- [5] et [6] : substrat mixte

COLS = ROWS = 8
POS_CASTER = (3, 1)
POS_AIM = (3, 2)


def _tid(col, row):
    return col * 100 + row + 1


def _board():
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _ligne(n):
    """La ligne DERIVEE par le foyer partage -- jamais posee a l'oeil : sur un board hex la ligne
    CUBE n'est PAS la ligne « row constante », et un montage suppose rendrait des bras VIDES."""
    ex = (lambda p: 0 <= p[0] < COLS and 0 <= p[1] < ROWS)
    return bq.get_tiles_behind(POS_CASTER, POS_AIM, max_count=n, check_walkable=True,
                               update_reference=True, walkable_at=lambda p: True,
                               elevation_at=lambda p: 0, tile_exists=ex)


def _substrat(unites):
    """`State` runner minimal : `unites` = (id, visualId, team, (col,row))."""
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": p[0], "row": p[1]}, "effects": []}
        for (uid, vid, team, p) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _p) in unites]}
    return load_state(dv, ob, snap, board=_board())


U_CASTER, U_E1, U_ALLIE, U_E2, U_HORS = 9001, 9002, 9003, 9004, 9005


def _mixte(avec_allie: bool = True, avec_hors_ligne: bool = False):
    """Ennemi / ALLIE / ennemi sur les trois tuiles du rayon (+ eventuellement un ennemi sur la
    4e, hors borne). C'est le SEUL regime ou la faute « compter les ennemis » est visible."""
    L = _ligne(4)
    unites = [(U_CASTER, "emperNoiseMarine", 1, POS_CASTER),
              (U_E1, "necroWarden", 2, L[0]),
              (U_E2, "orksNob", 2, L[2])]
    if avec_allie:
        unites.append((U_ALLIE, "ultraTitus", 1, L[1]))
    if avec_hors_ligne:
        unites.append((U_HORS, "tauMarksman", 2, L[3]))
    return _substrat(unites), L


def test_le_substrat_a_la_geometrie_voulue():
    """Un substrat dont la ligne n'est pas celle qu'on croit rend tous les bras VRAIS PAR VACUITE."""
    L = _ligne(4)
    assert len(L) == 4 and len(set(L)) == 4
    assert L[0] == POS_AIM, "la 1re tuile de la marche DOIT etre la tuile visee"


def test_le_COMPTE_porte_sur_TOUTES_les_unites_et_l_ATTAQUE_sur_les_ENNEMIS():
    """LE point du cas. Meme ennemis, memes tuiles : la SEULE difference est l'allie sur la ligne.
    MESURE live (#512, board `MC1_67`) : le natif publie `CritChance_Modification_Change = 90` avec
    l'allie, `60` sans."""
    st, L = _mixte(avec_allie=True)
    out = ABILITY_CLASSES[ABILITY]().execute_behaviour(st, U_CASTER, _tid(*POS_AIM))
    assert out is not None and out["dsl"] is True
    assert sorted(out["units_on_line"]) == sorted([U_E1, U_ALLIE, U_E2])
    assert out["extra_crit_chance"] == 20, "niveau 1 (substrat sans StatsComponent scale)"
    assert out["crit_chance"] == 3 * 20, "le Count doit voir les TROIS unites, allie compris"
    assert sorted(a["target"] for a in out["attacks"]) == [U_E1, U_E2], (
        "l'ALLIE de la ligne ne doit recevoir AUCUN coup")

    st2, _ = _mixte(avec_allie=False)
    out2 = ABILITY_CLASSES[ABILITY]().execute_behaviour(st2, U_CASTER, _tid(*POS_AIM))
    assert out2["crit_chance"] == 2 * 20, "sans l'allie le compte tombe a 2 -- c'est le DISCRIMINANT"
    assert sorted(a["target"] for a in out2["attacks"]) == [U_E1, U_E2], (
        "les CIBLES ne bougent pas : seul le COMPTE change entre les deux regimes")


def test_la_borne_nrOfTiles_exclut_la_4e_tuile_du_compte_ET_des_cibles():
    """`nrOfTiles = 3` : une unite sur la 4e tuile ne compte pas et n'est pas frappee. Sans la
    borne le rayon irait jusqu'au bord du plateau."""
    assert excruciating_frequencies_nr_of_tiles() == 3
    st, L = _mixte(avec_allie=True, avec_hors_ligne=True)
    out = ABILITY_CLASSES[ABILITY]().execute_behaviour(st, U_CASTER, _tid(*POS_AIM))
    assert len(out["tiles"]) == 3
    assert U_HORS not in (out["units_on_line"] or [])
    assert U_HORS not in [a["target"] for a in out["attacks"]]
    assert out["crit_chance"] == 3 * 20, "la 4e unite ne doit PAS entrer dans le Count"


def test_la_crit_chance_est_VUE_par_l_attaque_puis_RENDUE_apres_le_cast():
    """Le buff est pose AVANT l'attaque et retire APRES : si l'ordre etait inverse, le cast
    n'aurait AUCUN effet observable -- ni sur le tirage de crit, ni sur l'etat final. On mesure donc
    la stat AU MOMENT du coup (et pas seulement le montant emis)."""
    import engine.runner.abilities.behaviours.combat as C   # forme B : la seule qui MORDE
    from engine.runner.components import StatsComponent
    st, _ = _mixte(avec_allie=True)
    ctx = st.get_entity(U_CASTER).get_component(StatsComponent).ctx
    assert ctx.stat(int(StatType.CRIT_CHANCE)) == 0
    vues = []
    orig = C.AttackDamageOperation.execute_ability_attack

    def _spy(state, *a, **k):
        vues.append(ctx.stat(int(StatType.CRIT_CHANCE)))
        return orig(state, *a, **k)
    C.AttackDamageOperation.execute_ability_attack = staticmethod(_spy)
    try:
        ABILITY_CLASSES[ABILITY]().execute_behaviour(st, U_CASTER, _tid(*POS_AIM))
    finally:
        C.AttackDamageOperation.execute_ability_attack = orig
    assert vues == [60, 60], "les DEUX coups doivent voir le buff (pose AVANT, retire APRES)"
    assert ctx.stat(int(StatType.CRIT_CHANCE)) == 0, "le buff SURVIT au cast : le RemoveEffect rate"


def test_la_cible_TUILE_est_materialisee_par_le_helper_partage():
    """`entities_from_state` rend `target = None` pour une entite-TUILE : sans materialisation,
    `SelectTile(TargetTile())` resout VIDE et le rayon n'a plus de direction -> no-op silencieux."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    st, _ = _mixte(avec_allie=True)
    tuile = _tid(*POS_AIM)
    assert entities_from_state(st, U_CASTER, tuile).target is None, (
        "le foyer materialise desormais la cible-tuile : le helper a perdu son objet")
    ents = entities_with_tile_target(st, U_CASTER, tuile)
    assert ents.target is not None and ents.target["id"] == tuile
    assert ents.target["pos"] == {"col": POS_AIM[0], "row": POS_AIM[1]}
    assert len(excruciating_frequencies_affected_tiles(3).evaluate(ents)) == 3


def test_une_cible_qui_n_est_ni_unite_ni_tuile_ne_fabrique_RIEN():
    """Degradation NOMMEE : substrat non mesure -> pas de cast, jamais une tuile inventee."""
    st, _ = _mixte(avec_allie=True)
    assert ABILITY_CLASSES[ABILITY]().execute_behaviour(st, U_CASTER, None) is None
    assert ABILITY_CLASSES[ABILITY]().execute_behaviour(st, U_CASTER, 999999) is None
