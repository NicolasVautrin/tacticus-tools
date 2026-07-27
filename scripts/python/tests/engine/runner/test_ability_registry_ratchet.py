"""#167 -- CLIQUET de non-regression du registre d'abilities (offline pur, aucune session).

CE QUE CE FICHIER GARDE
-----------------------
Entrer dans `ABILITY_CLASSES` engage DEUX donnees, et leur absence se degrade de la MEME facon :
en silence, dans le sens PERMISSIF.

  * `TARGETING_OPTIONS` -- `engine/runner/abilities/targeting.py`, `get_invalid_target_reason` /
    `get_invalid_caster_reason` commencent par `options = getattr(ability, "TARGETING_OPTIONS", None)`
    et rendent **0 immediatement** si c'est `None`. Aucun gate. Le moteur accepte alors des casts que
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE (ami/ennemi, cible ==
    caster, caster ayant deja bouge). Ni erreur ni crash -- donc invisible en self-play, et c'est
    exactement l'espace d'action qu'un entrainement irait exploiter.
  * `ABILITY_ATTACK_TYPE` -- `engine/runner/abilities/attack_type.py`, `ability_has_attack_type`
    rend `False` sur une cle absente : l'ability se degrade en `Others` et le gate
    `AbilityHasAttackType(0|1)` de SwornProtector reste MUET pour elle.

POURQUOI UN CLIQUET, ET PAS UN SIMPLE ASSERT DE COUVERTURE
----------------------------------------------------------
C'est le SEUL gisement que notre propre cadence de portage AGGRAVE : chaque nouveau port l'alimente.
Le compte de masques manquants est passe de 60 a 75 pendant la campagne, sans qu'aucun test ne
rougisse. Et l'absence de `ABILITY_ATTACK_TYPE` a ete creusee TROIS fois (1036 FrenziedFiring en
`d2be96e`, puis 1041 BrazierOfHolyFire et 1116 RadBombardment en `825f69f`) -- les deux dernieres
n'ont ete vues qu'au RE-JEU apres rebase d'un autre agent : le trou ne s'etait montre dans aucune
des deux PR qui l'avaient creuse.

Un assert de couverture pleine serait ROUGE des le premier jour sur `TARGETING_OPTIONS` (28/81) et
donc desarme dans la semaine. La forme qui tient est le CLIQUET : une liste d'exemption figee, qui
ne peut que RETRECIR.

  * une ability du registre SANS masque et ABSENTE de la liste -> ECHEC (regression neuve) ;
  * une ability de la liste qui a MAINTENANT son masque -> ECHEC, il faut la retirer de la liste
    (c'est ce sens-la qui fait le cliquet : sans lui, la liste se fossilise et ne redescend jamais) ;
  * une ability de la liste ABSENTE du registre -> ECHEC (entree perimee).

`ABILITY_ATTACK_TYPE`, lui, est deja a 81/81 : sa garde est donc SANS exemption. Elle existait, mais
enterree a l'etape 0 de `probe_120_pre_unit_ability_fork.py` -- un probe qui monte un etat de
bataille complet et casse pour dix raisons sans rapport, auquel cas la couverture n'est jamais
vue. Ici elle tient seule, en un import.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

from engine.runner.abilities import ABILITY_CLASSES
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
from engine.runner.abilities.targeting_rule import TargetingRule

# --- LISTE D'EXEMPTION -- NE PEUT QUE RETRECIR ----------------------------------------------------
# Etat au 2026-07-27 (`6110d37`) : 81 abilities au registre, 28 avec masque, ces 53 sans.
# Ne JAMAIS y ajouter une ligne pour faire passer un port neuf : le masque se lit au decompile, dans
# le litteral passe par `<X>Ability$$.ctor` a `IdunBattle.Core.Services.TargetingOptions$$.ctor`.
#
# DEUX PIEGES quand on en retire une (les deux ont deja produit un masque FAUX) :
#   * l'overload PRESET + flags (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`) -- le litteral
#     visible n'est PAS le masque effectif ;
#   * l'ability qui n'appelle AUCUN ctor et recopie les 0x40 octets d'un champ STATIQUE : le masque
#     effectif est la constante ecrite par `TargetingOptions$$.cctor` a `<preset>+0x28`. Les presets
#     ne sont pas interchangeables (`statics+0x168` = 0x4002, `statics+0x68` = 0x4000) : lire ability
#     par ability, jamais generaliser « toutes les offensives valent X ».
# Recopier un litteral sans verifier l'overload produit un masque FAUX -- PIRE que l'absence, qui au
# moins ne ment pas. Laisser l'entree dans cette liste est le bon choix tant que le doute existe.
SANS_TARGETING_OPTIONS: dict[int, str] = {
    1000: "GauntletsOfUltramarAbility",
    1002: "CombatRestorativesAbility",
    1003: "DeathFromAboveAbility",
    1004: "MortisRoundAbility",
    1007: "ScarabHiveAbility",
    1014: "ArmoriumCherubAbility",
    1016: "SendInTheNextWaveAbility",
    1018: "ValkyrieStrikeAbility",
    1021: "IncursionAbility",
    1022: "BringerOfDespairAbility",
    1025: "SkyStrikeAbility",
    1028: "SupremeCommanderAbility",
    1036: "FrenziedFiringAbilityCombat",   # preset statique NON lu (cf. attack_type.py, lot #61)
    1037: "RevitalizingMalignancyAbility",
    1040: "SpawnPoxwalkersAbility",
    1042: "FlailSwingAbility",
    1043: "ThunderousAssaultAbility",
    1045: "GetEmRuntzAbility",
    1047: "ScarabSummonAbility",
    1051: "StikkbombAbility",
    1062: "SanctorumMissileAbility",
    1065: "ScythingTalonsAbility",
    1076: "MV71SniperDroneSquadAttackAbility",
    1077: "EarlyWarningOverrideAbility",
    1078: "FragstormAbility",
    1081: "FightingRetreatAbility",
    1082: "InspiredToGreatnessAbility",
    1089: "GreatFrostAxeAbility",
    1096: "MasterOfTheTutelariesAbility",
    1098: "PlasmaGrenadeAbility",
    1104: "SpiritLeechAbility",
    1105: "CrushingClawsAbility",
    1112: "AlphaWarriorAbility",
    1113: "StormcallerAbility",
    1118: "DoctrinaImperativesAbility",
    1122: "CordClawAbility",
    1139: "SentinelDirectivesAbility",
    1142: "MalleusRocketLauncherAbility",
    1143: "ForwardSpotterAbility",
    1145: "SporeMineLauncherAbility",
    1147: "HadesAutocannonsAbility",
    1148: "DaemonicOrdnanceAbility",
    1151: "TheQuickeningAbility",          # overload PRESET + flags (cf. le piege ci-dessus)
    1159: "MacroPlasmaIncineratorAbility",
    1160: "HeavyRailRifleAbility",
    1161: "TwinSmartMissileSystemAbility",
    1163: "BlackRageAbility",
    1166: "AberrantHypermorphAbility",
    1168: "EntropyCannonsAbility",
    1169: "PlagueburstMortarAbility",
    1187: "ThriceBlessedConflagrationAbility",
    1188: "DevastatingRefrainAbility",
    1230: "SavageEchoesAbility",
}


def _nom(aid: int) -> str:
    cls = ABILITY_CLASSES.get(aid)
    return cls.__name__ if cls is not None else "<hors registre>"


def test_attack_type_couvre_tout_le_registre():
    """`ABILITY_ATTACK_TYPE` est a 81/81 : sa garde n'a PAS d'exemption, et ne doit jamais en avoir.

    Le litteral est le 3e argument de `AActiveAbility$$.ctor` -- une ligne a relire au decompile,
    pas un chantier. Rien ne justifie d'entrer au registre sans lui."""
    manquants = sorted(a for a in ABILITY_CLASSES if a not in ABILITY_ATTACK_TYPE)
    assert not manquants, (
        "abilities entrees au registre SANS leur litteral `AbilityAttackType` -> elles se degradent "
        "en Others et le gate SwornProtector reste muet pour elles. Relire le 3e argument de "
        "`<X>Ability$$.ctor` -> `AActiveAbility..ctor(this, &opts, <ICI>)` : %s"
        % [(a, _nom(a)) for a in manquants])


def test_targeting_options_ne_regresse_pas():
    """Une ability qui entre au registre pose son masque DANS LE MEME COMMIT.

    Sans masque, la cascade rend 0 sans rien gater -- le cast illegal passe, en silence."""
    nouveaux = sorted(a for a, cls in ABILITY_CLASSES.items()
                      if getattr(cls, "TARGETING_OPTIONS", None) is None
                      and a not in SANS_TARGETING_OPTIONS)
    assert not nouveaux, (
        "abilities entrees au registre SANS `TARGETING_OPTIONS` -> aucun gate de ciblage, le moteur "
        "accepte des casts que le natif REFUSE. Lire le masque dans "
        "`<X>Ability$$.ctor` -> `TargetingOptions$$.ctor` (attention a l'overload PRESET, cf. l'en-tete "
        "de ce fichier) : %s" % [(a, _nom(a)) for a in nouveaux])


def test_liste_d_exemption_ne_peut_que_retrecir():
    """LE cliquet. Sans ce sens-la, la liste se fossilise : on n'ajoute plus de dette, mais on ne
    rembourse jamais celle qui reste, et les 53 entrees survivent a la campagne."""
    resorbees = sorted(a for a in SANS_TARGETING_OPTIONS
                       if a in ABILITY_CLASSES
                       and getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None)
    assert not resorbees, (
        "ces abilities ont MAINTENANT leur masque : les retirer de SANS_TARGETING_OPTIONS (la liste "
        "ne peut que retrecir) -> %s" % [(a, _nom(a)) for a in resorbees])

    perimees = sorted(a for a in SANS_TARGETING_OPTIONS if a not in ABILITY_CLASSES)
    assert not perimees, (
        "entrees perimees dans SANS_TARGETING_OPTIONS -- ces abilities ne sont plus au registre : %s"
        % [(a, SANS_TARGETING_OPTIONS[a]) for a in perimees])


def test_targeting_range_accompagne_toujours_le_masque():
    """#241 -- pendant EXACT de la regle ci-dessus, sur l'axe PORTEE.

    `rules` et `range` sortent du MEME appel de ctor -- `TargetingOptions..ctor(isSelfCasting,
    range, forceMeleeTarget, rules, ...)`, ou de la MEME copie de preset statique. N'en poser qu'un
    n'est pas un choix, c'est un oubli : `TargetingOptions.range is None` = « `TargetingRange` non
    RE-lu » -> `get_range` rend None -> AUCUN gate de portee. Meme degradation permissive, meme
    invisibilite en self-play.

    Pas d'exemption ici, et il n'en faut pas : les 28 masques deja poses portent tous leur
    `TargetingRange`, et il se lit dans la MEME ligne de decompile que le masque."""
    manquants = sorted(a for a, cls in ABILITY_CLASSES.items()
                       if getattr(cls, "TARGETING_OPTIONS", None) is not None
                       and cls.TARGETING_OPTIONS.range is None)
    assert not manquants, (
        "abilities avec `TARGETING_OPTIONS` mais SANS `TargetingRange` -> le volet portee du filtre "
        "n'est pas arme, le moteur accepte des casts hors portee que le natif REFUSE. Lire le 2e "
        "argument de `<X>Ability$$.ctor` -> `TargetingOptions$$.ctor` (ou le `<preset>+0x08..0x1f` "
        "du preset statique recopie) : %s" % [(a, _nom(a)) for a in manquants])


def test_masques_poses_ne_portent_aucun_bit_inconnu():
    """Tout bit d'un masque pose doit se nommer dans `TargetingRule` (le mirror GENERE de
    `IdunBattle.Core.Services.TargetingRule` depuis `data/symbols/<build>/frida/enums.tsv`).

    Un bit hors enum = une transcription fautive du decompile, ou un enum qui a bouge au dernier
    build. Les deux se lisent ici, et nulle part ailleurs : la cascade, elle, ignore silencieusement
    ce qu'elle ne sait pas lire."""
    connus = 0
    for membre in TargetingRule:
        v = int(membre)
        if v > 0:
            connus |= v

    fautifs = []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None:
            continue
        reste = int(opts.rules) & ~connus
        if reste:
            fautifs.append((aid, cls.__name__, hex(reste)))
    assert not fautifs, (
        "masques portant un bit ABSENT de l'enum TargetingRule (transcription fautive, ou enum "
        "deplace au dernier build -- rejouer probe_targeting_rule_bits.py) : %s" % fautifs)
