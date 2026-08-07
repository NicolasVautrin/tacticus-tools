"""GARDES #433-r4-r2-r1 + -r2 -- le CONTENU des deux branches d'`EarlyWarningOverridePlaybook`.

Les deux residus sont fermes ENSEMBLE, et ces gardes disent pourquoi : `threshold` (branche B) et
l'ancienne approximation de la branche A (`portee d'arme max`) sont NUMERIQUEMENT egales sur toute
unite a une seule arme a distance. Fermer `-r2` seul aurait rendu les deux branches du PORT
identiques -- un port qui donne la bonne reponse pour la mauvaise raison, qu'aucun test d'utilite
n'aurait rattrape. La garde `test_the_two_branches_are_not_the_same_quantity` verrouille cela.

Ce que chaque garde protege :
  * la CASCADE de `IdunBattle.Core.Services.TargetingQuery$$GetRange` (override du ctor > config >
    arme) et son ORDRE -- un clamp applique trop tot serait ecrase ;
  * les regimes ou le port ne sait pas decider et rend `None`, l'ability ne versant alors RIEN
    (borne INFERIEURE assumee) : `CustomRange(GetRange)`, et `UseWholeBoard` **quand son gate de
    ciblage dynamique n'est pas derivable**. ⚠ `UseWholeBoard` ne suffit PLUS a lui seul depuis
    `#433-r4-r2-r1-r1` : le regime se scinde selon `GetDynamicInvalidTargetReason` (gardes dans
    `test_433_r4_r2_r1_r1_dynamic_target_gate_offline.py`) ;
  * le court-circuit MULTI-TUILES de `IdunBattle.Core.Services.BattleQuery$$IsTileInRangeOfAnyAbility` ;
  * `IdunShared.Battle.WeaponProfile$$get_IsMelee` : une arme de portee 1 est MELEE, donc HORS du
    set de `FindRangedWeapon` -- c'est ce qui fait retomber le `threshold` sur son `?? 1` ;
  * la NON-DUPLICATION du substrat : une ability presente dans les DEUX sources (registre du runner
    et `TARGETING_OPTIONS_UNPORTED`) aurait deux verites possibles ;
  * la PRESENCE du masque `rules` pour les abilities actives du pool hors registre
    (`#433-r4-r2-r1-r2-r2-r1-r1`) -- sans lui les etages walkability et ligne de vue sont desarmes,
    et le bit 43 `AllowUnwalkableTargetTile` qu'aucune ne porte.

Les valeurs de reach citees ici sont celles MESUREES live (`probe_433_r4_r2_r1_ability_range.py
--step kit`, sweep de 40 positions par kit) -- cf. `docs/rl/case-433-r4-r2-r1-r2-portees.md`.
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.playbook.noncomparable.early_warning_override import _ranged_weapon_threshold
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import (RANGE_ADJACENT, RANGE_ADJACENT_IF_MELEE_CASTER,
                                               RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD,
                                               RANGED_BOOL_FALSE,
                                               RANGED_BOOL_IF_NOT_RANGED_CASTER, RANGED_BOOL_TRUE,
                                               TARGETING_OPTIONS_UNPORTED, TargetingRange)
from engine.services import ability_range as ar

RANGED = "tauMarksman"          # arme Range=3 + SeekerMissileFrequencyLock (constants.range = 5)
MELEE = "custoBladeChampion"    # arme de melee seule + MartialInspiration (RANGE_ADJACENT)
CHARGE = "astraDreir"           # arme de melee seule + LeadingTheCharge (RANGE_WHOLE_BOARD)


# --------------------------------------------------------------- 1. la cascade `GetRange`

def test_the_five_static_targeting_ranges_are_the_runner_foyer():
    """Aucun fork : la table locale REUTILISE les cinq statiques deja RE-lus cote runner. Si l'un
    d'eux changeait de contenu, les portees derivees ici suivraient -- c'est le but."""
    assert RANGE_ADJACENT_IF_MELEE_CASTER.only_adjacent == RANGED_BOOL_IF_NOT_RANGED_CASTER
    assert RANGE_FROM_CONFIG.use_range_from_config is True
    assert (RANGE_ADJACENT.only_adjacent, RANGE_ADJACENT.override_range) == (RANGED_BOOL_TRUE, 1)
    assert RANGE_WHOLE_BOARD.use_whole_board is True
    assert RANGE_SELF.override_range == 0
    for r in (RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD, RANGE_SELF):
        assert r.only_adjacent == RANGED_BOOL_FALSE


def test_config_range_only_when_use_range_from_config():
    """`AActiveAbility$$SetConfigValuesInTargetingOptions` ne recopie `constants.range` que si
    `UseRangeFromConfig` -- sans le flag, la config est MUETTE et la portee retombe sur l'arme.

    C'est LE discriminant mesure entre `tauMarksman` (Seeker, `RANGE_FROM_CONFIG`, reach 5) et
    `astraDreir` (`LeadingTheCharge`, `RANGE_WHOLE_BOARD`, `constants.range = 4` IGNORE, reach 1)."""
    assert ar.ability_range_value(1069, RANGED) == 5        # SeekerMissileFrequencyLock
    assert ar.ability_range_value(1204, CHARGE) is None     # LeadingTheCharge (whole board)


def test_override_range_wins_over_config():
    """L'ORDRE natif : `SetConfigValues...` ne pose la config que si `OverrideRange` est encore
    vide, donc un override du ctor GAGNE. On le prouve sur un `TargetingRange` synthetique qui
    porte les DEUX (aucune ability du lot ne le fait -- la garde protege l'ordre, pas un cas)."""
    both = TargetingRange(use_range_from_config=True, override_range=2)
    import dataclasses
    # ⚠ LE COBAYE SE DERIVE, IL NE SE FIGE PAS. Il etait ecrit en dur (`1069
    # SeekerMissileFrequencyLock`) : le jour ou cette ability a ete PORTEE (#491), elle a quitte
    # `TARGETING_OPTIONS_UNPORTED` -- disjointe d'`ABILITY_CLASSES` -- et ce test est tombe en
    # `KeyError` sur `master`, pour une cause qui n'a RIEN a voir avec ce qu'il garde (l'ORDRE
    # override-avant-config). Un cobaye fige dans une table qui RETRECIT a chaque port est une
    # peremption programmee ; on prend donc la premiere entree VIVANTE qui porte les deux
    # ingredients du montage. (Repare depuis #488, qui a fait sortir 1087 de la meme table.)
    # MEMBRE et non ordinal nu (#270-r1 volet 2) : toute ECRITURE sur cette table porte un membre --
    # les cles de la table EN SONT deja, donc iterer dessus le garantit.
    cle = next((k for k, o in TARGETING_OPTIONS_UNPORTED.items()
                if o.range is not None and getattr(o.range, "use_range_from_config", False)
                and isinstance(ar._config_range(int(k)), int) and ar._config_range(int(k)) > 0),
               None)
    assert cle is not None, (
        "plus AUCUNE entree de `TARGETING_OPTIONS_UNPORTED` ne porte `use_range_from_config` avec "
        "un `constants.range` lisible : ce test a perdu son substrat, pas sa raison d'etre")
    aid = int(cle)
    assert ar._config_range(aid) > 0, "montage : l'ability doit bien porter un constants.range"
    prev = TARGETING_OPTIONS_UNPORTED[cle]
    try:
        TARGETING_OPTIONS_UNPORTED[cle] = dataclasses.replace(prev, range=both)
        ar._REACH_CACHE.clear()
        assert ar.ability_range_value(aid, RANGED) == 2
    finally:
        TARGETING_OPTIONS_UNPORTED[cle] = prev
        ar._REACH_CACHE.clear()


def test_only_adjacent_collapses_the_range_to_one():
    """`RangedBoolExtensions$$IsTrue` : `True` -> adjacence ; `IfNotRangedCaster` -> adjacence pour
    un caster SANS arme a distance, portee d'arme sinon."""
    assert ar.ability_range_value(1191, MELEE) == 1          # MartialInspiration, only_adjacent=True
    assert ar._ranged_bool_is_true(RANGED_BOOL_IF_NOT_RANGED_CASTER, MELEE) is True
    assert ar._ranged_bool_is_true(RANGED_BOOL_IF_NOT_RANGED_CASTER, RANGED) is False


def test_undecidable_ranges_return_none_and_never_widen():
    """`UseWholeBoard` et `CustomRange(GetRange)` -> `None` = « le port ne sait pas ». L'ability ne
    verse RIEN a la zone : BORNE INFERIEURE assumee, jamais un elargissement a l'aveugle."""
    assert ar.ability_range_value(1204, CHARGE) is None      # LeadingTheCharge  (whole board)
    assert ar.ability_range_value(1038, "deathPutrifier") is None   # FoulInfusion (delegue)
    assert ar.unit_threat_reach(CHARGE) == 1, "l'ability whole-board ne doit rien ajouter a l'arme"


# --------------------------------------------------------------- 2. la zone, et le consommateur

@pytest.mark.parametrize("visual,expected", [(RANGED, 5), (MELEE, 1), (CHARGE, 1)])
def test_unit_threat_reach_matches_the_live_partition(visual, expected):
    """Les trois kits dont la partition native a ete mesuree tuile par tuile (40 positions,
    `d = 2..10`) : le port doit rendre EXACTEMENT la meme frontiere."""
    assert ar.unit_threat_reach(visual) == expected


def test_multi_tile_unit_short_circuits_to_true():
    """1re ligne du natif : `if (GetFeetCount(unit) > 1) return true;` -- avant toute lecture de
    portee. Le port l'expose ; cote DECISION aucun canal ne publie le compte de pieds, donc
    l'appelant passe 1 et le residu est NOMME."""
    far = (0, 0), (9, 9)
    assert ar.is_tile_in_range_of_any_ability(far[0], far[1], MELEE, feet_count=1) is False
    assert ar.is_tile_in_range_of_any_ability(far[0], far[1], MELEE, feet_count=3) is True


def test_missing_main_tile_is_out_of_range():
    """`GetMainTile == null` -> l'`OrderedSet` d'entree est VIDE -> `GetAllTilesInAbilityRange` rend
    un ensemble vide -> `Contains` est faux."""
    assert ar.is_tile_in_range_of_any_ability(None, (1, 1), RANGED) is False
    assert ar.is_tile_in_range_of_any_ability((1, 1), None, RANGED) is False


@pytest.mark.parametrize("d,expected", [(1, True), (5, True), (6, False), (9, False)])
def test_the_zone_is_a_disc_of_radius_reach(d, expected):
    """La frontiere mesuree sur `tauMarksman` : en portee jusqu'a `d <= 5` INCLUS, hors au-dela."""
    assert ar.is_tile_in_range_of_any_ability((0, 0), (d, 0), RANGED) is expected


# --------------------------------------------------------------- 3. la branche B, et le partage

def test_ranged_weapon_threshold_mirrors_find_ranged_weapon():
    """`threshold(E) = FindRangedWeapon(E).Range ?? 1`. `get_IsMelee` = `!Range.HasValue ||
    Range < 2` -> une unite sans arme de portee >= 2 retombe sur le `?? 1`."""
    assert _ranged_weapon_threshold(RANGED) == 3
    assert _ranged_weapon_threshold(MELEE) == 1
    assert _ranged_weapon_threshold(CHARGE) == 1
    assert _ranged_weapon_threshold("unite-qui-n-existe-pas") == 1


def test_the_two_branches_are_not_the_same_quantity():
    """LA garde de ce cas. Si le port derivait les deux branches de la MEME quantite, le partage
    A/B cesserait d'etre observable -- et un test d'utilite ne le verrait pas, puisque les deux
    branches rendraient la meme chose. Sur `tauMarksman` : zone d'ability 5, arme a distance 3."""
    assert ar.unit_threat_reach(RANGED) != _ranged_weapon_threshold(RANGED)
    assert (ar.unit_threat_reach(RANGED), _ranged_weapon_threshold(RANGED)) == (5, 3)


# --------------------------------------------------------------- 4. hygiene du substrat

def test_no_ability_has_two_contradictory_sources():
    """Une ability presente a la fois dans `ABILITY_CLASSES` (avec un `TargetingRange`) et dans
    `TARGETING_OPTIONS_UNPORTED` aurait DEUX verites ; `targeting_range_of` en choisirait une en
    silence. Depuis `#433-r4-r2-r1-r2-r2-r1-r1` la table locale de ce module n'existe plus (elle
    forkait le masque de sa propre portee) : la disjonction se garde a la SOURCE."""
    dupes = []
    for aid in TARGETING_OPTIONS_UNPORTED:
        cls = ABILITY_CLASSES.get(aid)
        opts = getattr(cls, "TARGETING_OPTIONS", None) if cls is not None else None
        if opts is not None:
            dupes.append(aid)
    assert dupes == [], "abilities a deux sources d'options : %r" % (dupes,)


#: Les abilities ACTIVES du pool spawnable hors `ABILITY_CLASSES` (#433-r4-r2-r1-r2-r2-r1-r1).
#: DERIVEE, pas choisie : `rl_duel build --list-pool` (rank courant, 97 unites regulieres) croise
#: avec `gameconfig.activeAbilities`, moins le registre COMBAT. La liste est FIGEE ici parce que
#: `--list-pool` exige la session host (normalisation live) et qu'un test offline ne peut pas la
#: rejouer ; le test qui suit, lui, DERIVE son perimetre du seed BC versionne.
#: ⚠ ELLE RETRECIT A CHAQUE PORT, et c'est voulu : `test_the_pool_abilities_carry_a_read_mask`
#: exige aussi qu'AUCUNE entree ne soit dans `ABILITY_CLASSES` (assertion `intrus`), parce que le
#: masque aurait alors DEUX sources. Une ability qui entre au registre doit donc SORTIR d'ici dans
#: le meme commit -- c'est le pendant, cote perimetre, du contrat de disjonction que garde
#: `tests/engine/runner/test_targeting_options_sources.py`.
#: Sorties : 1087 `ExemplarOfTheKauyon` (#488), 1048 `FragstormGrenadeLauncher` (#489),
#: 1069 `SeekerMissileFrequencyLock` (#491), 1088 `HellfyreMissileRack` (#487),
#: 1027 `PsychicMaelstrom` (#490), 1068 `SilentDeath` (#497),
#: 1152 `UnstoppableMomentumReworked` (#498), 1019 `StormOfWrath` (#499),
#: 1038 `FoulInfusion` (#500), 1165 `MightFromBelow` (#501),
#: 1064 `Loki_SwoopingHawk` (#502), 1141 `OverwhelmingWrath` (#503), 1132 `KillMaimBurn` (#504),
#: 1129 `BloodyFury` (#505), 1204 `LeadingTheCharge` (#508),
#: 1191 `MartialInspiration` (#509), 1177 `LightOfSanguinius` (#510),
#: 1197 `ExcruciatingFrequencies` (#512), 1195 `TalonsOfTheEmperor` (#521) -- toutes pour la MEME
#: raison : leur face COMBAT est portee, donc leur masque a MIGRE sur la classe. Les TREIZE
#: dernieres sont sorties EN PARALLELE, sur des branches aveugles l'une a l'autre : la liste se
#: relit apres resolution, elle ne se rature pas d'un seul cote.
#: ⚠ #503, #504, #505, #508, #509, #510, #512 et #521 se sont croisees sur CETTE liste : chacune n'y
#: retirait QUE son id (1141 / 1132 / 1129 / 1204 / 1191 / 1177 / 1197 / 1195), et un
#: `--ours`/`--theirs` en aurait donc RESSUSCITE un -- le test serait reste VERT de chaque cote pris
#: isolement. La resolution est l'UNION des retraits, verifiee ensuite PAR LE CODE (`intrus` == []
#: contre `ABILITY_CLASSES`).
POOL_ABILITIES_WITHOUT_COMBAT_CLASS = [
    1005, 1039, 1049, 1050, 1057, 1061, 1063,
    1101, 1106, 1121, 1164, 1175, 1183,
]


def test_the_pool_abilities_carry_a_read_mask():
    """`#433-r4-r2-r1-r2-r2-r1-r1` : les abilities ACTIVES du pool spawnable hors registre portent
    desormais leur masque `rules`, pas seulement leur portee. Sans lui, `tile_removed_by_walkability`
    et `target_is_obscured` sont DESARMES (convention permissive) et leur terme attribue des tuiles
    que le natif retire."""
    manquants = [a for a in POOL_ABILITIES_WITHOUT_COMBAT_CLASS
                 if TARGETING_OPTIONS_UNPORTED.get(a) is None]
    assert manquants == [], "masque non lu : %r" % (manquants,)
    intrus = [a for a in POOL_ABILITIES_WITHOUT_COMBAT_CLASS if a in ABILITY_CLASSES]
    assert intrus == [], "entrees a DEUX sources : %r" % (intrus,)
    sans_portee = [a for a in POOL_ABILITIES_WITHOUT_COMBAT_CLASS
                   if ar.targeting_range_of(a) is None]
    assert sans_portee == [], "portee perdue a la migration : %r" % (sans_portee,)


def test_a_read_range_is_never_a_range_without_its_mask():
    """LA garde du de-fork. Le module portait `TARGETING_RANGE_BY_ABILITY` -- le volet PORTEE SEUL --
    pendant que le masque restait non lu : deux sources pour une MEME struct native de 0x40 octets,
    et c'est ce qui laissait la walkability et la ligne de vue desarmees. Rouvrir une table de portee
    separee ferait rougir ce test.

    Le perimetre se DERIVE du seed BC VERSIONNE (`data/seed-bc.json`) -- un SUR-ENSEMBLE du pool
    spawnable (168 `VisualId` contre 97 unites), donc une exigence plus stricte que le lot traite."""
    import json
    from pathlib import Path
    import gameconfig as GC
    seed = Path(__file__).resolve().parents[4] / "data" / "seed-bc.json"
    bc = json.loads(seed.read_text(encoding="utf-8"))
    actives = set()
    for vid in {u.get("VisualId") for u in (bc.get("Units") or []) if u.get("VisualId")}:
        for name in ((GC.unit(vid) or {}).get("activeAbilities") or []):
            try:
                actives.add(int(ActiveAbilityType[name]))
            except KeyError:
                continue
    assert len(actives) > 100, "montage : le seed BC doit exposer un kit substantiel"
    orphelines = [a for a in sorted(actives)
                  if ar.targeting_range_of(a) is not None and ar._options_of(a) is None]
    assert orphelines == [], "portee lue sans masque (fork rouvert) : %r" % (orphelines,)


def test_the_six_friendly_only_abilities_contribute_no_tile():
    """Le court-circuit `TargetIsFriendly && !TargetIsEnemy` de
    `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetTiles` -- le TROISIEME etage que la
    lecture des 32 masques debloque. `target_tiles_zone_is_empty` ne lisait QUE `ABILITY_CLASSES`,
    donc rendait `False` pour toutes les 32 : leur zone etait versee a
    `AttackQuery$$GetAllTilesInAbilityRange` alors que le natif n'en verse AUCUNE tuile."""
    # ⚠ LA LISTE SUIT `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`, elle ne la fige pas : 1038
    # `FoulInfusion` en est SORTIE avec son port (#500), donc n'apparait plus ici. Son masque
    # `TargetIsFriendly && !TargetIsEnemy` est INCHANGE -- c'est le PERIMETRE balaye qui a change,
    # et `test_the_pool_abilities_carry_a_read_mask` garde la disjonction qui l'exige.
    attendues = [1005, 1039, 1049, 1061, 1175]
    vides = [a for a in POOL_ABILITIES_WITHOUT_COMBAT_CLASS if ar.target_tiles_zone_is_empty(a)]
    assert vides == attendues, "court-circuit : %r" % (vides,)
    for aid in attendues:
        assert ar.ability_range_value(aid, MELEE) is None
    # 1038 hors perimetre depuis #500, mais les DEUX proprietes tiennent toujours sur elle : le
    # court-circuit friendly-only, et la portee non derivable du `CustomRange(GetRange)`.
    assert ar.target_tiles_zone_is_empty(1038) is True
    assert ar.ability_range_value(1038, MELEE) is None


def test_bit_43_is_carried_by_none_of_the_pool_abilities():
    """Le bit 43 `AllowUnwalkableTargetTile` DESARME le `RemoveAll` de
    `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`. Aucune des 32 ne le porte -- donc le
    terme de walkability MORD pour toutes. Un futur masque qui le porterait doit faire ROUGIR ce
    test, pas passer inapercu."""
    porteurs = [aid for aid, o in TARGETING_OPTIONS_UNPORTED.items() if o.rules & (1 << 43)]
    assert porteurs == [], "bit 43 inattendu : %r" % (porteurs,)


def test_registry_ranges_are_reachable_through_the_same_accessor():
    """`targeting_range_of` doit lire le registre du runner AUSSI -- sinon les 102 abilities deja
    RE-lues seraient ignorees et la zone retomberait partout sur la portee d'arme."""
    from_registry = [aid for aid in ABILITY_CLASSES if ar.targeting_range_of(aid) is not None]
    assert len(from_registry) >= 100, "seulement %d portees lues au registre" % len(from_registry)
