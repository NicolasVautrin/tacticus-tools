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
  * la PRESENCE du masque `rules` pour les 32 abilities actives du pool
    (`#433-r4-r2-r1-r2-r2-r1-r1`) -- sans lui les etages walkability et ligne de vue sont desarmes,
    et le bit 43 `AllowUnwalkableTargetTile` qu'aucune ne porte. ⚠ Ces trois gardes balayaient
    « le pool MOINS le registre COMBAT », donc leur perimetre RETRECISSAIT a chaque port : elles ont
    laisse `master` ROUGE apres les trois ports du 2026-08-08, et perdaient au passage de vue les 22
    abilities deja portees. Depuis `#547-r4` la population balayee est STABLE et la partition entre
    les deux sources de masque se DERIVE.

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


#: Override synthetique du cobaye ci-dessous. Aucune ability ne porte les DEUX ingredients (c'est
#: ecrit dans la docstring d'origine) : la garde protege l'ORDRE, pas un cas reel.
_OVERRIDE_SYNTHETIQUE = 2


def _cobayes_de_l_ordre() -> list:
    """Abilities utilisables comme hote de la garde d'ordre : `[(id, constants.range)]`.

    SUBSTRAT = LE GAMECONFIG, et c'est tout le point. Une ability y porte son `constants.range`
    qu'elle soit portee ou non -- cette population ne bouge donc pas quand nous portons. Mesure du
    2026-08-13 : 260 membres, **72** avec un `constants.range` > 0, **28** apres le filtre
    discriminant ci-dessous.

    ⚠ FILTRE DISCRIMINANT, pas cosmetique : on ECARTE les abilities dont la portee de config vaut
    deja l'override synthetique. Sur celles-la les deux bras du test rendraient le MEME nombre, et
    la garde passerait au vert sans rien separer -- un accord en regime degenere.
    """
    out = []
    for m in ActiveAbilityType:                 # MEMBRE, jamais un ordinal nu (#270-r1 volet 2)
        v = ar._config_range(int(m))
        if isinstance(v, int) and v > 0 and v != _OVERRIDE_SYNTHETIQUE:
            out.append((int(m), v))
    return sorted(out)                          # trie : le cobaye ne depend pas d'un ordre d'iteration


def test_override_range_wins_over_config():
    """L'ORDRE natif : `SetConfigValues...` ne pose la config que si `OverrideRange` est encore
    vide, donc un override du ctor GAGNE.

    ⚠ TROISIEME PEREMPTION DU MEME COBAYE, ET LA DERNIERE -- parce que cette fois on change de
    SOURCE, pas de cobaye. Historique : ecrit en dur sur `1069 SeekerMissileFrequencyLock`, tombe en
    `KeyError` quand #491 l'a PORTEE ; re-derive sur la premiere entree vivante de
    `TARGETING_OPTIONS_UNPORTED`, re-tombe a #488 ; puis ROUGE sur `master` le 2026-08-13 quand cette
    table est descendue a **3 entrees dont 0** avec un `constants.range` lisible. Le defaut n'est
    aucune de ces trois fois le choix du cobaye : c'est d'aller le chercher dans une table qui
    RETRECIT A CHAQUE PORT, donc dont le vide est notre PROGRES. Relacher le filtre n'aurait rien
    sauve -- la table s'eteint.

    CE QUE LA GARDE EXERCE DESORMAIS : `_range_terms`, qui EST le site de l'ordre (`ov =
    rng.override_range` puis `if ov is None and rng.use_range_from_config`). Elle n'injecte plus rien
    dans aucun registre -- l'ancienne version mutait `TARGETING_OPTIONS_UNPORTED` sous un `try/
    finally` pour emprunter un hote. Un invariant se teste sur la fonction qui le porte, pas a
    travers la plomberie qui l'appelle.

    ET ELLE EST PLUS FORTE QU'AVANT : elle porte maintenant les DEUX bras. Sans le second, un
    `_range_terms` qui ignorerait purement la config resterait VERT.
    """
    cobayes = _cobayes_de_l_ordre()
    assert cobayes, (
        "aucune ability du gameconfig ne porte un `constants.range` > 0 different de %d : la garde "
        "d'ordre n'a plus d'hote. Contrairement aux trois peremptions precedentes, celle-ci NE PEUT "
        "PAS venir de nos ports -- ce serait un changement de BUILD ou une regression de "
        "`_config_range`." % _OVERRIDE_SYNTHETIQUE)
    aid, cfg = cobayes[0]

    # BRAS 1 -- l'override du ctor est pose : il GAGNE, la config n'est jamais consultee.
    both = TargetingRange(use_range_from_config=True, override_range=_OVERRIDE_SYNTHETIQUE)
    assert ar._range_terms(both, aid, RANGED)[0] == _OVERRIDE_SYNTHETIQUE, (
        "override du ctor + use_range_from_config : l'override doit gagner (ability %d)" % aid)

    # BRAS 2, LA CONTRE-EPREUVE -- sans override, c'est la config qui parle. `cfg != override` par
    # construction du filtre, donc les deux bras rendent des nombres DIFFERENTS : le bras 1 prouve
    # quelque chose.
    sans = TargetingRange(use_range_from_config=True)
    assert ar._range_terms(sans, aid, RANGED)[0] == cfg, (
        "sans override, `_range_terms` doit rendre le `constants.range` (%d) de l'ability %d"
        % (cfg, aid))


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


#: Les 32 abilities ACTIVES du pool spawnable (#433-r4-r2-r1-r2-r2-r1-r1).
#: DERIVEE, pas choisie : `rl_duel build --list-pool` (rank courant, 97 unites regulieres) croise
#: avec `gameconfig.activeAbilities`. La liste est FIGEE ici parce que `--list-pool` exige la
#: session host (normalisation live) et qu'un test offline ne peut pas la rejouer ; le test
#: `test_a_read_range_is_never_a_range_without_its_mask`, lui, DERIVE son perimetre du seed BC
#: versionne.
#:
#: ⚠ CETTE POPULATION NE BOUGE PAS QUAND ON PORTE -- et c'est ce qui la distingue de ce qu'elle a
#: remplace (#547-r4). Elle a d'abord ete ecrite comme « le pool MOINS le registre COMBAT », donc
#: elle RETRECISSAIT a chaque port : dix-neuf tranches (#487 a #521) ont du la raturer a la main,
#: huit s'y sont croisees, et les TROIS de la cadence du 2026-08-08 (1121 `ItItches` #550,
#: 1050 `HolyDuel` #549, 1164 `MindControl` #552) l'ont laissee ROUGE sur `master` -- un port qui
#: REUSSIT ne doit pas faire rougir un test. Ce qui bouge, c'est la PARTITION entre les deux
#: sources de masque ; elle se DERIVE ci-dessous, elle ne s'ecrit plus.
#: Mesure du 2026-08-08 : 32 = 22 au registre + 10 dans `TARGETING_OPTIONS_UNPORTED`, exactement
#: une source chacune, portee et masque lisibles pour les 32 (aucune anomalie).
POOL_ACTIVE_ABILITIES = [
    1005, 1019, 1027, 1038, 1039, 1048, 1049, 1050, 1057, 1061, 1063, 1064, 1068, 1069,
    1087, 1088, 1101, 1106, 1121, 1129, 1132, 1141, 1152, 1164, 1165, 1175, 1177, 1183,
    1191, 1195, 1197, 1204,
]

#: Le complement, DERIVE du registre -- plus jamais rature a la main. Quatre fichiers hors de ce
#: module l'interrogent en `not in` (`test_501_might_from_below_offline`,
#: `test_509_martial_inspiration_live`, `test_512_excruciating_frequencies_offline`,
#: `test_521_talons_of_the_emperor_live`) : la derivation les rend VRAIS par construction des que
#: l'ability entre au registre, au lieu d'exiger une edition dans la meme tranche.
POOL_ABILITIES_WITHOUT_COMBAT_CLASS = [a for a in POOL_ACTIVE_ABILITIES
                                       if a not in ABILITY_CLASSES]


def test_the_pool_abilities_carry_a_read_mask():
    """`#433-r4-r2-r1-r2-r2-r1-r1` : les abilities ACTIVES du pool portent leur masque `rules`, pas
    seulement leur portee. Sans lui, `tile_removed_by_walkability` et `target_is_obscured` sont
    DESARMES (convention permissive) et leur terme attribue des tuiles que le natif retire.

    ⚠ LA PROPRIETE EST « EXACTEMENT UNE SOURCE », PAS « TOUTES DANS `TARGETING_OPTIONS_UNPORTED` »
    (#547-r4). L'ancienne forme exigeait le masque dans la table des non-portees ET l'absence du
    registre : une ability PORTEE la faisait rougir, alors que son masque avait simplement MIGRE.
    La forme actuelle balaye les 32 et exige `registre XOR unported` -- elle attrape donc AUSSI ce
    que l'ancienne ne voyait pas : une entree qui aurait quitte `TARGETING_OPTIONS_UNPORTED` sans
    que sa classe porte de `TARGETING_OPTIONS` (masque PERDU, zero source), et la double source.
    """
    sans_source, deux_sources = [], []
    for a in POOL_ACTIVE_ABILITIES:
        cls = ABILITY_CLASSES.get(a)
        au_registre = getattr(cls, "TARGETING_OPTIONS", None) is not None if cls else False
        en_table = TARGETING_OPTIONS_UNPORTED.get(a) is not None
        if au_registre and en_table:
            deux_sources.append(a)
        elif not au_registre and not en_table:
            sans_source.append(a)
    assert sans_source == [], "masque PERDU (ni registre ni table) : %r" % (sans_source,)
    assert deux_sources == [], "entrees a DEUX sources : %r" % (deux_sources,)
    sans_portee = [a for a in POOL_ACTIVE_ABILITIES if ar.targeting_range_of(a) is None]
    assert sans_portee == [], "portee perdue a la migration : %r" % (sans_portee,)
    sans_masque = [a for a in POOL_ACTIVE_ABILITIES if ar._options_of(a) is None]
    assert sans_masque == [], "masque non lisible par l'accesseur : %r" % (sans_masque,)
    # La partition se DERIVE, mais elle ne doit pas devenir DEGENEREE : un jour ou les 32 seraient
    # portees, les trois tests ci-dessous ne mesureraient plus rien cote `UNPORTED` sans le dire.
    assert len(POOL_ABILITIES_WITHOUT_COMBAT_CLASS) + len(
        [a for a in POOL_ACTIVE_ABILITIES if a in ABILITY_CLASSES]) == 32


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
    # ⚠ LE PERIMETRE EST LA POPULATION STABLE, PLUS LE COMPLEMENT DU REGISTRE (#547-r4). Balaye sur
    # « le pool moins le registre », ce test perdait une porteuse a chaque port : 1038 `FoulInfusion`
    # etait deja sortie de son perimetre avec #500 et devait etre re-testee a la main juste dessous,
    # et le NOM du test (« six ») etait devenu faux -- il n'en balayait plus que cinq. Le masque
    # `TargetIsFriendly && !TargetIsEnemy` d'une ability PORTEE est inchange, et
    # `target_tiles_zone_is_empty` lit les DEUX sources : la propriete se garde donc sur les 32.
    # Les six sont RE-MESUREES sur la population, pas heritees : [1005, 1038, 1039, 1049, 1061, 1175].
    attendues = [1005, 1038, 1039, 1049, 1061, 1175]
    vides = [a for a in POOL_ACTIVE_ABILITIES if ar.target_tiles_zone_is_empty(a)]
    assert vides == attendues, "court-circuit : %r" % (vides,)
    for aid in attendues:
        assert ar.ability_range_value(aid, MELEE) is None


def test_bit_43_is_carried_by_none_of_the_pool_abilities():
    """Le bit 43 `AllowUnwalkableTargetTile` DESARME le `RemoveAll` de
    `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`. Aucune des 32 ne le porte -- donc le
    terme de walkability MORD pour toutes. Un futur masque qui le porterait doit faire ROUGIR ce
    test, pas passer inapercu.

    ⚠ Le balayage passe par `_options_of`, donc par les DEUX sources (#547-r4) : lu sur le seul
    `TARGETING_OPTIONS_UNPORTED`, il perdait de vue chaque ability portee -- 22 des 32 aujourd'hui,
    et sa docstring promettait deja « aucune des 32 ». Les entrees de la table HORS pool restent
    balayees, elles aussi."""
    porteurs = [aid for aid in POOL_ACTIVE_ABILITIES if ar._options_of(aid).rules & (1 << 43)]
    porteurs += [aid for aid, o in TARGETING_OPTIONS_UNPORTED.items()
                 if aid not in POOL_ACTIVE_ABILITIES and o.rules & (1 << 43)]
    assert porteurs == [], "bit 43 inattendu : %r" % (porteurs,)


def test_registry_ranges_are_reachable_through_the_same_accessor():
    """`targeting_range_of` doit lire le registre du runner AUSSI -- sinon les 102 abilities deja
    RE-lues seraient ignorees et la zone retomberait partout sur la portee d'arme."""
    from_registry = [aid for aid in ABILITY_CLASSES if ar.targeting_range_of(aid) is not None]
    assert len(from_registry) >= 100, "seulement %d portees lues au registre" % len(from_registry)
