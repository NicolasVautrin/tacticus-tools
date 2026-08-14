"""#270-r1 volet 2 -- GARDE : les 109 cles des DIX dicts que le build n'attribue PAS a un enum
unique sont des MEMBRES, et la conversion n'a rien deplace.

CE QUI DISTINGUE CE VOLET DU PREMIER, ET POURQUOI LA GARDE N'EST PAS LA MEME.

Le volet 1 (`test_270r1_dict_keys_enum_offline`) portait sur des dicts que le BUILD tranchait
seul : toutes leurs cles n'appartenaient qu'a UN enum. Ici le build ne tranche pas -- 44 cles
resolvent a la fois dans `ActiveAbilityType` et `TriggeredAbilityType`, 22 + 25 + 7 dans
`ActiveAbilityType` et `EffectType`, et les 18 cles de TRIANGLE (0..5) resolvent dans **454**
enums. L'attribution a donc ete LUE site par site, et c'est ce qui peut se perdre :

  * pour les 110 ids d'ability, le discriminant est le **NOM** (#270-c) -- sur le gameconfig,
    l'intersection nom-a-nom `passiveAbilities`/`activeAbilities` est VIDE, alors que
    `TriggeredAbilityType` partage **458** ordinaux avec `EffectType` (454 nomment autre chose) et
    **233** avec `ActiveAbilityType` (231). Un ordinal qui « resout » ne prouve donc rien ; c'est
    le nom cite au site (`GetEmRuntzAbility`, `BreathOfSilencePlaybook`, ...) qui l'atteste ;
  * pour les 18 cles de TRIANGLE, le discriminant est le **TYPE DECLARE** du parametre :
    `IdunBattle.Core.Services.BattleQuery$$GetTilesInTriangleShape(startTile, direction)` prend un
    `IdunBattleLogic.Utils.Hex.Corner`. Ce n'est pas un scalaire, et ce n'est pas devinable du nom
    court -- CINQ autres enums du build s'appellent `Corner` (Unity/SimpleUI), tous a 3 ou 4
    valeurs.

QUATRE ETAGES.

  * ETAGE 1 -- CLIQUET : chaque cle est une instance de l'enum LU. Ne se perime jamais ; rougit
    si une entree revient avec un ordinal nu, c.-a-d. si le gisement se rouvre.
  * ETAGE 2 -- ANTI-DEPLACEMENT : les 109 couples (ordinal, valeur) mesures AVANT conversion sont
    toujours la, meme valeur, meme ordre relatif. Sur-ensemble ORDONNE, pas egalite : une entree
    AJOUTEE passe sans re-figer les couples. ⚠ Le couple est cherche dans sa SOURCE EFFECTIVE et
    non dans le dict (`_resolveur_targeting`, #547-r4) : porter la face COMBAT d'une ability fait
    MIGRER son masque sur la classe, ce qui n'est pas une perte -- et l'ancienne forme, qui exigeait
    le dict, obligeait chaque port a RAYER son couple du snapshot (19 fois, puis 3 rouges sur
    `master` le 2026-08-08). Le couple reste desormais verrouille APRES migration.
  * ETAGE 3 -- ACCESSEURS PUBLICS : les tables traversees par le chemin REEL des appelants, avec
    l'ordinal ET avec le membre. Il existe parce qu'une cle jamais jouee n'est vue par personne.
  * ETAGE 4 -- REINSERTION : `pop` + reinsertion REMPLACE la cle, contrairement a une affectation
    sur cle existante qui la CONSERVE. Cinq sites du depot (un test live, quatre probes) font
    exactement ce `pop`/reinsertion sur ces tables : si leur constante est un ordinal nu, le dict
    ressort du fichier avec une cle non typee et l'etage 1 rougit SELON L'ORDRE DES TESTS. La
    propriete CPython qui separe les deux formes est attestee ici, pas supposee.

100 % OFFLINE : aucun runner, aucune session Frida, aucune lecture de gameconfig.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine import battle_query as BQ  # noqa: E402
from engine.entities.abilities import active_ability as AA  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.selectors import geometry as GEO  # noqa: E402
from engine.hex_corner import Corner  # noqa: E402
from engine.playbook.noncomparable import _base as NCB  # noqa: E402
from engine.playbook.prediction import abilities as PA  # noqa: E402
from engine.runner.abilities import targeting as T  # noqa: E402
from engine.services import ability_caster_gates as ACG  # noqa: E402

# --- SNAPSHOT mesure AVANT la conversion (128 couples). GENERE depuis les dicts eux-memes.
# Les valeurs non scalaires (fonctions, `TargetingOptions`) sont normalisees par
# `_valeur_comparable` : on fige la valeur EFFECTIVE, pas l'identite de l'objet.

# ⚠ PORTER UNE ABILITY NE RETIRE PLUS RIEN D'ICI (#547-r4). Les couples ci-dessous portent des
# notes « RETIREE (#N) » : elles sont HISTORIQUES et decrivent le regime d'avant, ou chaque port
# devait rayer son couple a la main -- 19 ratures, 8 croisements de branches, puis 3 rouges sur
# `master`. Depuis, le couple d'une ability portee est retrouve par `_resolveur_targeting` sur sa
# classe : NE RIEN RAYER, c'est precisement ce qui le laisserait sans garde.
SNAP_TARGETING_UNPORTED = (
    # ⚠ 1216 -- SEULE VALEUR DU SNAPSHOT QUI AIT CHANGE, et c'est une CORRECTION, pas une derive.
    # Le couple mesure etait `(32788, True, None, 1)` : le `range = None` venait d'un bloc de preset
    # NON LU. `#923` (merge `46ba95e8`) l'a RE-LU et RESOLU -> `RANGE_SELF`, et c'est bien ce fichier
    # qui l'a vu (l'etage 2 confronte la valeur EFFECTIVE, migration comprise) -- mais la tranche a
    # oublie de reporter la mesure ici, d'ou `master` ROUGE.
    # RE-VERIFIE INDEPENDAMMENT (#943, decompile `rnca9r7q6c`) avant de toucher au snapshot :
    #   * `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit le preset `<statics>+0x280` en
    #     copiant `<TargetingRange statics>+0x60..0x77` dans `<preset>+0x288..0x29f`, avec
    #     `<preset>+0x280 = 1` (isSelfCasting), `+0x2a0 = 1` (forceMeleeTarget = RangedBool.False) et
    #     `+0x2a8 = 0x8004` (rules) ;
    #   * `IdunBattle.Core.Services.TargetingRange$$.cctor` pose `<statics>+0x60 = 1`
    #     (onlyAdjacent = RangedBool.False), `+0x68 = Nullable(0)` (overrideRange) et `+0x70 = null`
    #     (overrideRangeFunc) -- c'est-a-dire exactement `RANGE_SELF`.
    # Le tuple ci-dessous est donc la valeur NATIVE, et l'ancien `None` etait un aveu de non-lecture
    # qui laissait `get_range` rendre `None`, donc AUCUN gate de portee (degradation PERMISSIVE).
    (1216, (32788, True, (1, False, False, 0, False), 1)),
    (1217, (16384, False, (0, False, False, 1, False), 1)),
    (1093, (16386, False, (1, True, False, None, False), 1)),
    # ⚠ 1215 -- DEUXIEME valeur du snapshot qui change, et c'est la MEME correction que 1216
    # ci-dessus, un cran plus tard (#943-r1). `#943` avait RE-LU le preset et ECRIT la lecture dans
    # ce fichier meme (le bloc de 1216), mais avait laisse `1215` a `None` -- deliberement, pour ne
    # pas resserrer un gate dans une tranche 100 % offline. Or les deux abilities recopient le MEME
    # preset `<TargetingOptions statics>+0x280` : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # InstrumentsOfVengeanceAbility$$.ctor` est une STATIC-COPY de ce preset (aucun appel de
    # `TargetingOptions$$.ctor`), exactement comme celui de 1216 modulo `additionalRules = 0x10`.
    # Deux STATIC-COPY du meme preset ne peuvent pas avoir deux portees : la portee de 1215 EST
    # `RANGE_SELF`, et le `None` etait un aveu de non-lecture (`get_range() -> None` = AUCUN gate,
    # degradation PERMISSIVE).
    (1215, (32772, True, (1, False, False, 0, False), 1)),
    (1005, (1026, True, (0, False, False, 1, False), 1)),
    # 1019 StormOfWrath RETIREE (#499) : sa face COMBAT est portee (`ChainAbilityDamage`), donc son
    # masque a MIGRE sur `StormOfWrathAbility.TARGETING_OPTIONS` -- meme mouvement que
    # 1027/1038/1048/1068/1069/1087/1088/1152. Le ctor a ete RELU a cette occasion et la valeur qui
    # etait figee ici est CONFIRMEE champ pour champ : `rules = 0x4000 = 16384` (TargetIsEnemy seul),
    # `selfCast = False`, `range` = `TargetingRange statics+0x00` = ADJACENT_IF_MELEE_CASTER,
    # `forceMeleeTarget = 1` (RangedBool.False). C'est la SOURCE qui bouge, jamais la valeur.
    (1039, (34056, True, (0, False, False, 1, False), 1)),
    (1049, (1024, True, (1, True, False, None, False), 1)),
    (1057, (4160, False, (0, False, False, 1, False), 1)),
    (1061, (33792, True, (1, True, False, None, False), 1)),
    # HUIT entrees RETIREES du snapshot AU TOTAL, parce que leur face COMBAT est PORTEE et que
    # leur masque a MIGRE sur la classe -- les deux tables `*_UNPORTED` sont disjointes
    # d'`ABILITY_CLASSES`. La VALEUR est inchangee ; seule la SOURCE a bouge, et c'est
    # `test_targeting_options_sources.py` qui garde la disjonction. RETIREES ICI :
    # 1087 `ExemplarOfTheKauyon` (#488), 1048 `FragstormGrenadeLauncher` (#489),
    # 1069 `SeekerMissileFrequencyLock` (#491), 1088 `HellfyreMissileRack` (#487) -- les trois
    # dernieres laissaient `master` ROUGE sur ce fichier, trouvees au rebase de #488 -- et
    # 1038 `FoulInfusion` (#500). Les trois autres (1027, 1068, 1152) portent leur propre note
    # plus bas. Le compte se RE-DERIVE de la table, jamais d'une soustraction : #498 et #500 ont
    # retire chacune une entree EN PARALLELE, sur deux branches.
    (1121, (524352, False, (0, False, False, 1, False), 0)),
    # 1141 OverwhelmingWrath RETIREE (#503) : meme mouvement -- sa face COMBAT est portee
    # (`worldeaters.OverwhelmingWrathAbility.TARGETING_OPTIONS`), donc son masque a MIGRE.
    # 1152 UnstoppableMomentumReworked RETIREE (#498) : sa face COMBAT est portee, donc son masque
    # a MIGRE sur `UnstoppableMomentumReworkedAbility.TARGETING_OPTIONS` -- meme mouvement que
    # 1027/1048/1068/1069/1087/1088. Le ctor a ete RELU a cette occasion et la valeur figee ici est
    # CONFIRMEE champ pour champ : `rules = 0x10120040 = 269615168`, `selfCast = False`,
    # `range` = `TargetingRange statics+0x30` = ADJACENT, `forceMeleeTarget = 1` (RangedBool.False).
    (1164, (16386, False, (1, True, False, None, False), 1)),
    (1175, (3074, True, (0, False, False, 1, False), 1)),
    # 1197 ExcruciatingFrequencies RETIREE (#512) : sa face COMBAT est portee, donc son masque a
    # MIGRE sur `emperorschildren.ExcruciatingFrequenciesAbility.TARGETING_OPTIONS` -- meme
    # mouvement que 1019/1027/1038/1048/1064/1068/1069/1087/1088/1129/1132/1141/1152/1165/1204. Le
    # ctor a ete RELU a cette occasion et la valeur qui etait figee ici est CONFIRMEE champ pour
    # champ : `rules = 0x20000000042 = 2199023255618` (`TargetMatchesDynamicRule | TargetIsTile |
    # AllowUntargetableTarget` -- le bit 41 est AU-DELA DE 32), `selfCast = False`, `range` =
    # `TargetingRange statics+0x30` = ADJACENT, `forceMeleeTarget = 1` (RangedBool.False). C'est la
    # SOURCE qui bouge, jamais la valeur.
    (1050, (8589950976, False, (0, False, False, 1, False), 1)),
    (1101, (8589950978, False, (1, True, False, None, False), 1)),
    (1106, (32788, True, (1, False, False, 0, False), 1)),
    (1183, (8589950976, False, (0, False, False, 1, False), 1)),
    # 1129 BloodyFury RETIREE (#505) : sa face COMBAT est portee
    # (`ChainLeftOverHitsAttackDamage` melee profil `Chain` + snowball de coups), donc son masque a
    # MIGRE sur `BloodyFuryAbility.TARGETING_OPTIONS` -- meme mouvement que
    # 1019/1027/1038/1048/1068/1069/1087/1088/1152. Le ctor a ete RELU a cette occasion et la valeur
    # qui etait figee ici est CONFIRMEE champ pour champ : `rules = 0x4000 = 16384` (TargetIsEnemy
    # seul), `selfCast = False`, `range` = `TargetingRange statics+0x30` = ADJACENT,
    # `forceMeleeTarget = 1` (RangedBool.False). C'est la SOURCE qui bouge, jamais la valeur. Elle
    # etait la SEULE de la surcharge « PRESET SEUL » (copie pure a 2 arguments).
    # 1027 PsychicMaelstrom RETIREE (#490) : sa face COMBAT est portee, donc son masque a MIGRE
    # sur `PsychicMaelstromAbility.TARGETING_OPTIONS` -- meme mouvement que 1048/1069/1087/1088.
    # Ce snapshot fige l'ordinal ECRIT AU SITE, et le site a change ; rien n'est perdu, les sites
    # qui portent desormais 1027 l'ecrivent par le MEMBRE et `probe_313` garde la bijection.
    (1063, (16386, False, (3, False, False, None, False), 2)),
    # 1064 Loki_SwoopingHawk RETIREE (#502) : sa face COMBAT est portee, donc son masque a MIGRE
    # sur `SwoopingHawkAbility.TARGETING_OPTIONS` -- meme mouvement que 1027/1048/1068/1069/1087/
    # 1088. Le masque lui-meme n'a PAS bouge (0x4000 TargetIsEnemy, RANGE_ADJACENT, RangedBool
    # .False) ; c'est sa SOURCE qui change, et le contrat de disjonction impose le retrait d'ici.
    # 1068 SilentDeath RETIREE (#497) : sa face COMBAT est portee, donc son masque a MIGRE sur
    # `SilentDeathAbility.TARGETING_OPTIONS` -- meme mouvement que 1027/1048/1069/1087/1088. Le
    # ctor a ete RELU a cette occasion et la valeur figee ici est CONFIRMEE champ pour champ
    # (`16384` = `TargetIsEnemy` seul, `RANGE_ADJACENT`, `forceMeleeTarget = 1`).
    # 1132 KillMaimBurn RETIREE (#504) : sa face COMBAT est portee, donc son masque a MIGRE sur
    # `KillMaimBurnAbility.TARGETING_OPTIONS` -- meme mouvement que 1027/1038/1048/1068/1069/1087/
    # 1088/1152. Le ctor a ete RELU a cette occasion et la valeur qui etait figee ici est CONFIRMEE
    # champ pour champ (`16384` = `TargetIsEnemy` seul, `RANGE_ADJACENT`, `forceMeleeTarget = 1`).
    # 1165 MightFromBelow : SORTIE (#501) -- face COMBAT portee, masque migre sur
    # `abilities/loki/might_from_below.py::MightFromBelowAbility.TARGETING_OPTIONS` (valeur
    # inchangee : rules 0x4000, RANGE_ADJACENT, forceMeleeTarget 1). Meme mouvement que 1027/1087.
    # 1177 LightOfSanguinius RETIREE (#510) : sa face COMBAT est portee, donc son masque a MIGRE sur
    # `bloodangels.LightOfSanguiniusAbility.TARGETING_OPTIONS` -- meme mouvement que 1027/1038/1048/
    # 1064/1068/1069/1087/1088/1132/1141/1152/1165. Le `.cctor` a ete RELU a cette occasion et la
    # valeur qui etait figee ici est CONFIRMEE champ pour champ : `rules = 0x102004032 = 4328538162`
    # (`<TargetingOptions statics>+0x268`), `selfCast = False`, `range` = `TargetingRange` statics+0x48
    # = RANGE_WHOLE_BOARD, `forceMeleeTarget = 1` (RangedBool.False). C'est la SOURCE qui bouge.
    # ⚠ Son JUMEAU 1204 `LeadingTheCharge` (MEME preset, MEME masque) est sorti d'ici en #508, une
    # tranche PARALLELE -- ce qui les separait etait leur `GetDynamicInvalidTargetReason`, et les
    # deux faces COMBAT sont desormais portees, chacune par sa tranche.
    # 1191 MartialInspiration RETIREE (#509) : sa face COMBAT est portee, donc son masque a MIGRE
    # sur `custodes.py::MartialInspirationAbility.TARGETING_OPTIONS` -- meme mouvement que
    # 1019/1027/1038/1048/1064/1068/1069/1087/1088/1132/1141/1152/1165. Le ctor a ete RELU a cette
    # occasion (forme STATIC-COPY, preset `<TargetingOptions statics>+0x40`) et la valeur qui etait
    # figee ici est CONFIRMEE champ pour champ : `16384` = `TargetIsEnemy` SEUL, `selfCast = False`,
    # `RANGE_ADJACENT`, `forceMeleeTarget = 1` (`RangedBool.False`). C'est la SOURCE qui bouge.
    # ⚠⚠ #509 et #510 se sont croisees ICI : chacune ne retirait QUE son couple. Un `--ours`/
    # `--theirs` aurait RESSUSCITE celui de l'autre, en laissant chaque cote VERT pris isolement.
    # La resolution est l'UNION des retraits, et les tailles ci-dessous sont RE-DERIVEES du code.
    # 1195 TalonsOfTheEmperor RETIREE (#521) : sa face COMBAT est portee, donc son masque a MIGRE
    # sur `custodes.py::TalonsOfTheEmperorAbility.TARGETING_OPTIONS` -- meme mouvement que
    # 1019/1027/1038/1048/1064/1068/1069/1087/1088/1132/1141/1152/1165/1191. Le ctor a ete RELU a
    # cette occasion (forme STATIC-COPY, preset `<TargetingOptions statics>+0x40` -- le MEME que
    # 1191 ci-dessus) et la valeur qui etait figee ici est CONFIRMEE champ pour champ :
    # `16384 = 0x4000` = `TargetIsEnemy` SEUL (lu a `<preset>+0x28`), `selfCast = False`,
    # `RANGE_ADJACENT`, `forceMeleeTarget = 1` (`RangedBool.False`). C'est la SOURCE qui bouge,
    # jamais la valeur -- la comparaison a ete refaite par `_valeur_comparable` sur la classe
    # portee, tuple pour tuple.
    # ⚠ Le preset est PARTAGE avec 1191, le litteral d'`AbilityAttackType` ne l'est PAS : `2`
    # (`Others`) pour 1195 contre `0` pour 1191, transcrit du 3e argument d'`AActiveAbility..ctor`.
    # 1204 LeadingTheCharge : SORTIE (#508) -- face COMBAT portee, masque migre sur
    # `abilities/loki/leading_the_charge.py::LeadingTheChargeAbility.TARGETING_OPTIONS`. La VALEUR
    # est CONFIRMEE champ pour champ contre le preset `TargetingOptions statics+0x240` relu au
    # `.cctor` : `rules = 0x102004032 = 4328538162`, `selfCast = False`, `range` = WHOLE_BOARD,
    # `forceMeleeTarget = 1` (RangedBool.False) -- exactement ce qui etait fige ici, et le MEME
    # preset que 1177 juste au-dessus. Seule la SOURCE a bouge.
    (1010, (16400, False, (0, False, False, 1, False), 1)),
    (1144, (1073758240, False, (1, False, True, None, False), 1)),
    (1185, (8589950978, False, (1, True, False, None, False), 0)),
    (1015, (32788, True, (1, False, False, 0, False), 1)),
    (1044, (16386, False, (1, True, False, None, False), 0)),
    (1080, (16386, False, (1, True, False, None, False), 0)),
    (1053, (16384, False, (0, False, False, 1, False), 1)),
    (1108, (16384, False, (0, False, False, 1, False), 1)),
)

SNAP_CASTER_GATE = (
    (1045, 'spawn_tile'),
    (1008, 'not_derivable'),
    (1015, 'not_derivable'),
    (1023, 'not_derivable'),
    (1040, 'not_derivable'),
    (1102, 'not_derivable'),
    (1207, 'not_derivable'),
    (1077, 'not_read'),
    (1106, 'not_read'),
    (1184, 'not_read'),
    (1215, 'not_read'),
    (1216, 'not_read'),
)

SNAP_NATIVE_PRIORITY = (
    (1070, 1000),
    (1085, 1000),
    (1109, 1000),
    (1127, 1000),
    (1155, 1000),
    (1173, 1000),
    (1192, 1000),
    (1200, 1000),
    (1213, 1000),
    (1032, 100),
    (1125, 100),
    (1174, 100),
    (1187, 100),
    (1159, -100),
    (1201, -100),
    (1209, -100),
    (1072, -1000),
    (1084, -1000),
    (1111, -1000),
    (1172, -1000),
    (1194, -1000),
    (1223, -1000),
)

SNAP_INPUT_OVERRIDES = (
    (1191, '_martial_inspiration_inputs'),
    (1105, '_crushing_claws_inputs'),
    (1080, '_hellfire_shells_inputs'),
    (1089, '_great_frost_axe_inputs'),
    (1036, '_frenzied_firing_inputs'),
    (1230, '_savage_echoes_inputs'),
    (1051, '_stikkbomb_inputs'),
    (1098, '_plasma_grenade_inputs'),
    (1048, '_fragstorm_grenade_launcher_inputs'),
    (1222, '_mass_driver_accelerator_inputs'),
    (1059, '_ramming_speed_inputs'),
    (1035, '_plague_wind_inputs'),
    (1093, '_plague_wind_inputs'),
)

SNAP_PROFILE_OVERRIDE = (
    (1020, 'None'),
    (1062, 'None'),
    (1017, 'None'),
    (1006, 'None'),
    (1066, 'Psychic'),
    (1008, 'None'),
    (1100, 'None'),
    (1148, 'None'),
    (1147, 'None'),
)

SNAP_EXTRA_EVENTS = (
    (1059, '_ramming_speed_self_events'),
    (1035, '_plague_wind_wave_events'),
    (1093, '_plague_wind_wave_events'),
)

SNAP_NOT_MINMAX_AVERAGE = (
    (1080, ('HellfireShellsPlaybook$$MakeDamagePredictions', 'Direct(minDmg) SEUL', True)),
    (1089, ('GreatFrostAxePlaybook$$MakeDamagePredictions', 'Get(minDmg) SEUL', True)),
    (1051, ('StikkbombPlaybook$$MakeDamagePredictions', 'Get(minDmg) SEUL', True)),
    (1191, ('MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext', 'round(minDmg * buff), hits = 1', True)),
    (1098, ('PlasmaGrenadePlaybook$$MakeDamagePredictions', 'Get(minDmg) SEUL', True)),
    (1048, ('FragstormGrenadeLauncherPlaybook$$MakeDamagePredictions', 'nrOfHits x maxDmg (var 0xd) en UN coup -- hits=1 pose par la surcharge appelee', True)),
    (1059, ('RammingSpeedPlaybook$$MakeDamagePredictions', 'Get(minDmg) SEUL + hits const 0x2f ; batch SELF (hits 0x32) ; batch EXPLOSION conditionnel', True)),
)

SNAP_TRIANGLE_EVEN = (
    (0, ((-1, 1), (0, 1))),
    (1, ((0, 1), (1, 1))),
    (2, ((-1, 1), (-1, 0))),
    (3, ((1, 1), (1, 0))),
    (4, ((-1, 0), (0, -1))),
    (5, ((0, -1), (1, 0))),
)

SNAP_TRIANGLE_ODD = (
    (0, ((-1, 0), (0, 1))),
    (1, ((1, 0), (0, 1))),
    (2, ((-1, 0), (-1, -1))),
    (3, ((1, -1), (1, 0))),
    (4, ((-1, -1), (0, -1))),
    (5, ((1, -1), (0, -1))),
)

SNAP_TRIANGLE_DIRS = (
    (0, (5, 0)),
    (1, (0, 1)),
    (2, (5, 4)),
    (3, (1, 2)),
    (4, (4, 3)),
    (5, (3, 2)),
)

def _resolveur_targeting(ordinal):
    """La valeur EFFECTIVE du masque, quelle que soit sa SOURCE (#547-r4).

    `TARGETING_OPTIONS_UNPORTED` est DISJOINTE d'`ABILITY_CLASSES` : porter la face COMBAT d'une
    ability y RETIRE son entree et pose le meme masque sur la classe. Le couple mesure n'est donc
    pas perdu -- il a CHANGE DE SOURCE, et `targeting_options_for` (le resolveur qu'interrogent
    reellement les appelants, deja utilise par l'etage 3 ci-dessous) continue de le rendre.

    Interroger le dict BRUT faisait rougir les etages 2/cardinalite/lookup a chaque port REUSSI :
    dix-neuf tranches ont raye leur couple du snapshot a la main, et les trois du 2026-08-08
    (1121 `ItItches` #550, 1050 `HolyDuel` #549, 1164 `MindControl` #552) ont laisse `master`
    ROUGE. Passer par le resolveur ELARGIT la garde au lieu de la reduire : le couple reste
    verrouille APRES la migration, alors que l'ancienne forme le laissait sortir du snapshot --
    une valeur alteree en migrant n'aurait plus ete confrontee a rien.
    """
    return T.targeting_options_for(ordinal)


#: (dict vivant, snapshot, enum attendu, nom lisible[, resolveur]) -- le perimetre EXACT du volet 2.
#: Le 5e element est OPTIONNEL : seule `TARGETING_OPTIONS_UNPORTED` a une SECONDE source. Pour les
#: neuf autres tables le dict EST la source unique, et un ordinal disparu y reste une PERTE.
CIBLES = (
    (T.TARGETING_OPTIONS_UNPORTED, SNAP_TARGETING_UNPORTED, ActiveAbilityType,
     "runner/abilities/targeting.TARGETING_OPTIONS_UNPORTED", _resolveur_targeting),
    (ACG.DYNAMIC_CASTER_GATE_BY_ABILITY, SNAP_CASTER_GATE, ActiveAbilityType,
     "services/ability_caster_gates.DYNAMIC_CASTER_GATE_BY_ABILITY"),
    (NCB.NATIVE_PRIORITY, SNAP_NATIVE_PRIORITY, ActiveAbilityType,
     "playbook/noncomparable/_base.NATIVE_PRIORITY"),
    (PA._MAKE_DMG_INPUT_OVERRIDES, SNAP_INPUT_OVERRIDES, ActiveAbilityType,
     "playbook/prediction/abilities._MAKE_DMG_INPUT_OVERRIDES"),
    (PA._PLAYBOOK_PROFILE_OVERRIDE, SNAP_PROFILE_OVERRIDE, ActiveAbilityType,
     "playbook/prediction/abilities._PLAYBOOK_PROFILE_OVERRIDE"),
    (PA._MAKE_DMG_EXTRA_EVENTS, SNAP_EXTRA_EVENTS, ActiveAbilityType,
     "playbook/prediction/abilities._MAKE_DMG_EXTRA_EVENTS"),
    (AA._PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE, SNAP_NOT_MINMAX_AVERAGE, ActiveAbilityType,
     "entities/abilities/active_ability._PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE"),
    (BQ._TRIANGLE_EVEN_COL, SNAP_TRIANGLE_EVEN, Corner,
     "battle_query._TRIANGLE_EVEN_COL"),
    (BQ._TRIANGLE_ODD_COL, SNAP_TRIANGLE_ODD, Corner,
     "battle_query._TRIANGLE_ODD_COL"),
    (GEO._TRIANGLE_SHAPE_DIRECTIONS, SNAP_TRIANGLE_DIRS, Corner,
     "entities/selectors/geometry._TRIANGLE_SHAPE_DIRECTIONS"),
)


def _cibles():
    """`CIBLES` avec son 5e element NORMALISE (`None` = le dict est la source unique)."""
    for c in CIBLES:
        yield c[0], c[1], c[2], c[3], (c[4] if len(c) > 4 else None)


def _valeur_effective(vivant, resolveur, ordinal):
    """La valeur du couple, prise dans le dict et -- a defaut SEULEMENT -- chez le resolveur.

    Rend `None` quand le couple n'est retrouvable NULLE PART : c'est ca, une vraie perte.
    """
    if ordinal in vivant:
        return _valeur_comparable(vivant[ordinal])
    if resolveur is None:
        return None
    v = resolveur(ordinal)
    return None if v is None else _valeur_comparable(v)


def _valeur_comparable(v):
    """Normalise une valeur pour la confronter au snapshot.

    Une FONCTION est reduite a son `__name__` : son identite ne survit pas a un import, mais
    l'appariement handler <-> ability est exactement ce qu'il faut figer. Les `TargetingOptions`
    sont aplaties en tuple de leurs champs SCALAIRES, comme au volet 1.
    """
    if isinstance(v, T.TargetingOptions):
        r = v.range
        # `range=None` est DELIBERE sur plusieurs entrees (bloc de preset non resolu -> aucun gate
        # de portee invente) : le figer tel quel, ne pas fabriquer un range par defaut.
        porte = (None if r is None
                 else (int(r.only_adjacent), bool(r.use_range_from_config),
                       bool(r.use_whole_board), r.override_range, bool(r.override_range_func)))
        return (int(v.rules), bool(v.self_cast), porte, int(v.force_melee_target))
    if callable(v):
        return v.__name__
    if isinstance(v, tuple):
        return tuple(_valeur_comparable(x) if isinstance(x, tuple) else x for x in v)
    if isinstance(v, str):
        return v
    return int(v)


def test_cles_sont_des_membres_d_enum():
    """ETAGE 1 -- CLIQUET : aucune cle ordinale nue ne subsiste, et aucune ne peut revenir.

    ROUGE si une entree est ajoutee plus tard avec un ordinal (`1234: ...` au lieu de
    `ActiveAbilityType.X: ...`) -- ce serait la reouverture du gisement.
    """
    fautives = {}
    for vivant, _snap, enum_attendu, nom, _res in _cibles():
        hors = [k for k in vivant if not isinstance(k, enum_attendu)]
        if hors:
            fautives[nom] = [(repr(k), type(k).__name__) for k in hors]
    assert fautives == {}, (
        "ces cles ne sont pas des membres de leur enum -- un ordinal nu devient FAUX au "
        "changement de build, en silence (regle CLAUDE.md) : %r" % fautives)


def test_snapshot_ordinal_valeur_et_ordre():
    """ETAGE 2 -- ANTI-DEPLACEMENT : chaque couple mesure avant la conversion est toujours la.

    C'est ce test qui attrape « le bon nom en face de la mauvaise valeur » -- le seul mode
    d'echec propre a une conversion de masse : il ne casse aucun import et ne leve rien.

    ⚠ LE COUPLE EST CHERCHE DANS SA SOURCE EFFECTIVE, PAS DANS LE DICT (#547-r4) -- cf.
    `_resolveur_targeting`. `ordinaux_disparus` ne nomme donc plus qu'une VRAIE perte : introuvable
    des deux cotes. L'ORDRE, lui, ne se verifie que sur les couples restes dans le dict : une
    migration retire une cle, elle ne permute rien, donc l'exigence devient « SOUS-SUITE ordonnee
    du snapshot » -- une permutation reelle rougit toujours.
    """
    ecarts = {}
    for vivant, snap, _enum, nom, res in _cibles():
        attendu = dict(snap)
        effectif = {o: _valeur_effective(vivant, res, o) for o in attendu}
        manquants = {o: v for o, v in attendu.items() if effectif[o] is None}
        revalorises = {o: (v, effectif[o]) for o, v in attendu.items()
                       if effectif[o] is not None and effectif[o] != v}
        connus = [int(k) for k in vivant if int(k) in attendu]
        ordre_ok = connus == [o for o, _ in snap if o in connus]
        if manquants or revalorises or not ordre_ok:
            ecarts[nom] = {"ordinaux_disparus": manquants, "valeur_changee": revalorises,
                           "ordre_preserve": ordre_ok}
    assert ecarts == {}, (
        "la conversion en membres d'enum n'est PAS value-preserving : %r" % ecarts)


def test_cardinalites_du_volet():
    """Le compte du volet 2 : 25 + 12 + 22 + 13 + 9 + 3 + 7 + 6 + 6 + 6 = 109 couples MESURES.

    ⚠ CE COMPTE NE BOUGE PLUS QUAND UNE ABILITY EST PORTEE (#547-r4), et c'est le changement de
    forme du cas. Il a d'abord ete rature a la main a CHAQUE port -- 44 -> 25 en dix-neuf tranches :
    1087 (#488), 1048 (#489), 1069 (#491), 1088 (#487), 1027 (#490), 1068 (#497), 1152 (#498),
    1019 (#499), 1038 (#500), 1165 (#501), 1064 (#502), 1141 (#503), 1132 (#504), 1129 (#505),
    1204 (#508), 1191 (#509), 1177 (#510), 1197 (#512), 1195 (#521) -- huit de ces tranches se sont
    croisees ici, chacune annoncant le chiffre de son SEUL retrait, et un `--ours`/`--theirs` aurait
    RESSUSCITE l'entree de l'autre en laissant chaque cote VERT pris isolement. Puis les trois du
    2026-08-08 (1121 #550, 1050 #549, 1164 #552) ont laisse `master` ROUGE, faute d'une 20e rature.
    Depuis, le snapshot n'est plus AMPUTE par un port : `_resolveur_targeting` retrouve le couple
    sur la classe portee, donc les 109 couples restent verrouilles A VIE -- y compris apres
    migration, ce que l'ancienne forme ne faisait pas (un couple raye n'etait plus confronte a
    rien). Le SEUL geste qui doit encore toucher ces chiffres est un AJOUT de couple mesure.

    ⚠ **LE PLANCHER PAR TABLE EST TOMBE LE 2026-08-14, ET C'ETAIT LE PROGRES (#996-r1-r3).**
    Cette boucle exigeait `assert dans_le_dict` par table -- « il reste des couples du snapshot
    DANS la table ». `TARGETING_OPTIONS_UNPORTED` est passee a **0 entree**
    (`len(TARGETING_OPTIONS_UNPORTED) == 0`) par deux migrations LEGITIMES et independantes :
    `1215 InstrumentsOfVengeance` (#889-r6) puis `1015 PrecisionShot` (#996-r1-r3). Ses **25**
    couples ne sont PAS perdus -- ils sont tous retrouves par `_resolveur_targeting`, ce que les
    deux crans suivants verifient deja, et ce que l'etage 2 confronte en VALEUR.

    C'est la TROISIEME incarnation du meme vice ce jour-la (apres `test_519_comptes_derives` et
    `test_996_no_op_silencieuses`) : garder une PROPRIETE DU CORPUS (« cette table est encore
    peuplee ») la ou l'invariant a garder est celui de la DERIVATION (« chaque couple mesure reste
    retrouvable, et on sait OU »). Un plancher par table lit le drainage comme une panne --
    exactement ce que `probe_1021` decrit en majuscules et ce qui a fait rougir CINQ cliquets le
    2026-08-13.

    ⚠ **ET LE PLANCHER NE SE REMPLACE PAR RIEN : les trois crans qui restent PORTENT DEJA tout
    l'invariant.** Deux assertions de remplacement ont ete ecrites, puis RETIREES apres mesure --
    `total_confronte == 109` et `total_dans_les_dicts > 0`. Les deux sont **DOMINEES** : aucune ne
    peut rougir la premiere, donc aucune n'ajoute de pouvoir de detection.

    MESURE (rejeu de la ventilation sur les vraies `CIBLES`, puis sur des cibles mutees ; quelle
    assertion tombe la PREMIERE ?) :

        REEL                       tombees=[]                                      confronte=109
        couple PERDU des 2 cotes   tombees=['introuvables == [] (TARGETING_...)']   confronte=0
        snapshot AMPUTE            tombees=['sum(tailles) == 109', ...]             confronte=108
        UNE table videe            tombees=[]                                       confronte=109
        les DIX tables videes      tombees=['res is not None or not ailleurs (...)'] dans_dicts=0

    `total_confronte` vaut `sum(len(snap)) - sum(len(introuvables))` : le premier terme est
    verrouille a 109 trois lignes plus haut, le second est asserte NUL a chaque tour. Il ne peut
    donc valoir autre chose que 109 sans qu'une assertion anterieure soit deja tombee. Et
    `total_dans_les_dicts > 0` est inatteignable pour la RAISON MEME qui le justifiait : les neuf
    tables sans resolveur qui se videraient declenchent `res is not None or not ailleurs` avant.

    ⚠ **C'EST LE MEME VICE QUE LE PLANCHER, SOUS L'AUTRE FACE.** Un plancher de population rougit
    quand il ne faut pas ; une assertion dominee ne rougit jamais. Remplacer l'un par l'autre
    n'aurait pas repare le volet -- ca l'aurait vide en le faisant paraitre plus riche. Une
    troisieme redaction ecrivait `len(dans_le_dict) + len(ailleurs) == len(snap)`, tautologique
    par construction (`o in vivant` et `o not in vivant` PARTITIONNENT toujours). Le bon geste
    etait de RETIRER le plancher, pas de lui trouver un remplacant.
    """
    tailles = [len(s) for _v, s, _e, _n, _r in _cibles()]
    assert tailles == [25, 12, 22, 13, 9, 3, 7, 6, 6, 6], (
        "le snapshot du volet 2 a change de forme : %r" % tailles)
    assert sum(tailles) == 109
    # Le dict PEUT retrecir jusqu'a se VIDER (migration), et c'est LEGITIME : ce qui ne doit jamais
    # arriver, c'est qu'un couple cesse d'etre confronte. Ces deux crans le disent entierement --
    # une table qui perd sans seconde source, et un couple introuvable des DEUX cotes. Ne RIEN
    # ajouter ici : toute garde de plus serait dominee par eux (mesure en docstring).
    for vivant, snap, _enum, nom, res in _cibles():
        ailleurs = [o for o, _ in snap if o not in vivant]
        assert res is not None or not ailleurs, (
            "%s a PERDU des entrees et n'a pas de seconde source : %r" % (nom, ailleurs))
        introuvables = [o for o in ailleurs if res(o) is None]
        assert introuvables == [], (
            "%s : couples introuvables des DEUX cotes : %r" % (nom, introuvables))


def test_lookup_par_int_brut():
    """La propriete qui rend la conversion transparente pour les appelants.

    Tous les consommateurs interrogent ces tables avec un `int` brut (`.get(int(ability_id))`,
    `table[int(direction)]`). `IntEnum` herite `__hash__` d'`int` (MRO : `IntEnum` -> `int` ->
    `ReprEnum` -> `Enum`), donc la cle `ActiveAbilityType.MartialExemplar` et l'entier `1216`
    designent la MEME entree. On l'atteste sur les 109 couples plutot que de le supposer.

    ⚠ Un couple MIGRE (face COMBAT portee) n'est plus dans le dict : la propriete se verifie alors
    par le RESOLVEUR, interroge lui aussi avec l'`int` brut (#547-r4). Ce qui est atteste reste le
    meme : le lookup par entier rend la valeur mesuree.
    """
    for vivant, snap, _enum, nom, res in _cibles():
        for ordinal, valeur in snap:
            assert ordinal in vivant or (res is not None and res(ordinal) is not None), (
                "%s : `%d in dict` est faux apres conversion, et aucune autre source ne le rend"
                % (nom, ordinal))
            assert _valeur_effective(vivant, res, ordinal) == valeur, (
                "%s : le lookup par int brut %d ne rend pas la valeur attendue" % (nom, ordinal))


def test_reinsertion_pop_remplace_la_cle_affectation_non():
    """ETAGE 4 -- la propriete CPython dont depend la SURVIE de l'etage 1 aux autres tests.

    Cinq sites du depot retirent temporairement une entree de ces tables puis la restaurent :
    `tests/engine/test_savage_echoes_prediction_live`, `probe_216_savage_prediction`,
    `probe_351_facade_event_count`, `probe_352_grenade_prediction_base`,
    `probe_27_r5_r1_plague_wind_prediction`. Deux formes de restauration coexistent dans le
    depot, et elles ne sont PAS equivalentes :

      * affectation sur une cle DEJA presente   -> CPython CONSERVE la cle d'origine
        (`test_433_r4_r2_r1_r2_ability_range_offline` fait cela sur `TARGETING_OPTIONS_UNPORTED`
        et est donc sans danger, y compris avec un ordinal nu) ;
      * `pop` puis reinsertion                  -> la cle est REMPLACEE par ce qu'on passe.

    D'ou la regle : tout site en `pop`/reinsertion sur ces tables doit porter un MEMBRE. Ce test
    fige la propriete ; si elle tombait (version de Python, passage a un `Enum` nu), l'etage 1
    deviendrait dependant de l'ordre des tests, ce qui est exactement le genre d'echec
    intermittent qu'on ne diagnostique jamais.
    """
    d = {ActiveAbilityType.SavageEchoes: "x"}
    d[1230] = "y"                                        # affectation sur cle existante
    assert list(d) == [ActiveAbilityType.SavageEchoes], (
        "CPython ne conserve plus la cle sur une affectation : %r" % [type(k) for k in d])
    sauve = d.pop(1230)
    d[1230] = sauve                                      # pop + reinsertion
    assert type(list(d)[0]) is int and not isinstance(list(d)[0], ActiveAbilityType), (
        "le `pop` + reinsertion ne remplace plus la cle -- la regle de l'etage 4 est a relire")


#: Les dix tables du volet, par leur NOM tel qu'il est ecrit aux sites de mutation.
_TABLES_DU_VOLET = ("TARGETING_OPTIONS_UNPORTED", "DYNAMIC_CASTER_GATE_BY_ABILITY",
                    "NATIVE_PRIORITY", "_MAKE_DMG_INPUT_OVERRIDES", "_PLAYBOOK_PROFILE_OVERRIDE",
                    "_MAKE_DMG_EXTRA_EVENTS", "_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE",
                    "_TRIANGLE_EVEN_COL", "_TRIANGLE_ODD_COL", "_TRIANGLE_SHAPE_DIRECTIONS")

#: Un id SYNTHETIQUE deliberement hors de tout enum, insere puis retire par un probe pour
#: fabriquer un masque de test (`probe_419...tiles_in_range_order._SYNTH_ID`). Il n'a pas de
#: membre par CONSTRUCTION -- l'exclure ici est un fait LU, pas une echappatoire de confort.
_SYNTHETIQUES = {"_SYNTH_ID"}


def _index_est_un_membre(noeud, litteraux_module: dict) -> bool:
    """L'expression d'index designe-t-elle un MEMBRE d'enum (directement ou par une constante) ?

    Accepte `Enum.Membre`, `Enum(...)`, et un `Name` dont l'affectation module-level vaut l'un
    des deux. Refuse un litteral entier et `int(<Enum>.<Membre>)` -- `int()` DEGRADE le membre en
    ordinal nu, et c'est precisement ce qui casse la restauration.
    """
    import ast as _ast
    if isinstance(noeud, _ast.Constant) and isinstance(noeud.value, int):
        return False
    if isinstance(noeud, _ast.Attribute):
        return True
    if isinstance(noeud, _ast.Call):
        f = noeud.func
        return not (isinstance(f, _ast.Name) and f.id == "int")
    if isinstance(noeud, _ast.Name):
        if noeud.id in _SYNTHETIQUES:
            return True
        val = litteraux_module.get(noeud.id)
        return True if val is None else _index_est_un_membre(val, {})
    return True


def test_etage5_les_sites_de_REINSERTION_portent_un_membre():
    """ETAGE 5 -- BALAYAGE STATIQUE : aucun site du depot ne REINSERE une cle en ordinal nu.

    POURQUOI IL EXISTE, et il a ete ecrit APRES avoir constate que l'etage 4 ne suffisait pas.
    Mutation essayee : rendre a `probe_216_savage_prediction` sa constante `ABILITY = 1230`.
    Les quatre premiers etages sont restes VERTS -- ils lisent les dicts APRES import, et un
    probe qui n'est pas joue dans la passe ne les touche jamais. C'est mot pour mot le mode de
    defaillance de #455-r3 : le runtime ne voit que ce qu'une passe JOUE.

    Le balayage, lui, porte sur le TEXTE de tout Python suivi. Il rougit sur
    `<TABLE>[<litteral entier>] = ...`, sur `<TABLE>[<var valant un litteral entier>] = ...` et
    sur `<TABLE>.pop(<idem>)` / `.setdefault(<idem>)`.

    NE COUVRE PAS -- dit plutot que maquille : `update(<dict construit ailleurs>)`, dont les cles
    ne sont pas lisibles au site (`probe_27_r5_r1` en a un ; ses deux constantes sont des membres,
    verifie a la main). Le suivre demanderait de remonter la construction du dict.
    """
    import ast
    import subprocess

    r = subprocess.run(["git", "ls-files", "scripts/python"],
                       cwd=str(PYDIR.parents[1]), capture_output=True, text=True)
    assert r.returncode == 0, "git ls-files a echoue : le balayage ne mesurerait RIEN"
    fichiers = [f for f in r.stdout.split() if f.endswith(".py")]
    assert len(fichiers) > 300, "perimetre suspect (%d fichiers) -- un zero rassurant" % len(fichiers)

    fautifs = []
    for rel in fichiers:
        p = PYDIR.parents[1] / rel
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not any(t in src for t in _TABLES_DU_VOLET):
            continue
        try:
            arbre = ast.parse(src, filename=rel)
        except SyntaxError:
            continue
        litteraux = {}
        for n in arbre.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                    and isinstance(n.targets[0], ast.Name):
                litteraux[n.targets[0].id] = n.value

        def _nom_table(noeud):
            if isinstance(noeud, ast.Name) and noeud.id in _TABLES_DU_VOLET:
                return noeud.id
            if isinstance(noeud, ast.Attribute) and noeud.attr in _TABLES_DU_VOLET:
                return noeud.attr
            return None

        for n in ast.walk(arbre):
            # <TABLE>[idx] = ...  -- REINSERTION (ou creation) d'une cle
            if isinstance(n, ast.Assign):
                for cible in n.targets:
                    if isinstance(cible, ast.Subscript):
                        t = _nom_table(cible.value)
                        if t and not _index_est_un_membre(cible.slice, litteraux):
                            fautifs.append((rel, n.lineno, t, ast.dump(cible.slice)[:60]))
            # <TABLE>.pop(idx) / .setdefault(idx, ...)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr in ("pop", "setdefault") and n.args:
                t = _nom_table(n.func.value)
                if t and not _index_est_un_membre(n.args[0], litteraux):
                    fautifs.append((rel, n.lineno, t, ast.dump(n.args[0])[:60]))

    assert fautifs == [], (
        "ces sites REINSERENT ou retirent une cle par un ordinal NU -- apres restauration la "
        "table porterait une cle non typee, et le cliquet (etage 1) rougirait selon l'ORDRE des "
        "tests : %r" % fautifs)


def test_generalisation_les_accesseurs_publics():
    """ETAGE 3 -- la conversion traversee par le chemin REEL des appelants.

    POURQUOI CET ETAGE EXISTE. Les tests de comportement qui consomment ces dix tables n'en
    exercent qu'une poignee. Un deplacement qui ne frapperait qu'une cle jamais jouee ne serait
    vu par personne. Ici on balaye par les ACCESSEURS PUBLICS, donc a travers le `.get(int(...))`
    que font reellement les consommateurs, avec l'ORDINAL NU et avec le MEMBRE.

    Et les appels DISCRIMINENT : on exige que les reponses ne soient pas toutes identiques, sans
    quoi l'egalite int/membre tiendrait meme sur une table entierement melangee.
    """
    from engine.services import ability_range as AR

    # 44 -- `targeting.targeting_options_for` (le resolveur qui consulte cette 2e source de masque)
    masques = {}
    for ordinal, attendu in SNAP_TARGETING_UNPORTED:
        membre = ActiveAbilityType(ordinal)
        par_int, par_membre = T.targeting_options_for(ordinal), T.targeting_options_for(membre)
        assert par_int is not None, "%d : le resolveur ne trouve plus le masque" % ordinal
        assert _valeur_comparable(par_int) == _valeur_comparable(par_membre) == attendu, (
            "%d : `targeting_options_for` differe selon la forme de la cle" % ordinal)
        masques[ordinal] = _valeur_comparable(par_int)
    assert len(set(masques.values())) > 1, "les 44 masques sont identiques -- rien n'est mesure"

    # 12 -- `ability_caster_gates.dynamic_caster_gate_of`
    regimes = {}
    for ordinal, attendu in SNAP_CASTER_GATE:
        membre = ActiveAbilityType(ordinal)
        assert ACG.dynamic_caster_gate_of(ordinal) == attendu
        assert ACG.dynamic_caster_gate_of(membre) == attendu
        regimes[ordinal] = attendu
    assert len(set(regimes.values())) > 1, "les 12 regimes sont identiques -- rien n'est mesure"
    # une ability HORS table doit rendre `none` : sans ce controle un accesseur constant passerait
    assert ACG.dynamic_caster_gate_of(ActiveAbilityType.PlagueWind) == ACG.CASTER_GATE_NONE

    # 22 -- `noncomparable.native_priority`
    tiers = set()
    for ordinal, attendu in SNAP_NATIVE_PRIORITY:
        membre = ActiveAbilityType(ordinal)
        assert NCB.native_priority(ordinal) == attendu
        assert NCB.native_priority(membre) == attendu
        tiers.add(attendu)
    assert tiers == {1000, 100, -100, -1000}, "les quatre tiers natifs ne sont plus tous couverts"
    assert NCB.native_priority(ActiveAbilityType.PlagueWind) == 0, (
        "une ability hors table doit valoir `AbilityPriority.Normal`")

    # 18 -- `battle_query.get_tiles_in_triangle_shape`, le SEUL consommateur des tables de
    #      TRIANGLE. On l'interroge sur une colonne PAIRE et une colonne IMPAIRE (les deux
    #      branches de parite) avec l'ordinal ET le membre.
    formes = {}
    for col in (2, 3):
        for ordinal, _ in SNAP_TRIANGLE_EVEN:
            membre = Corner(ordinal)
            par_int = BQ.get_tiles_in_triangle_shape((col, 5), ordinal)
            par_membre = BQ.get_tiles_in_triangle_shape((col, 5), membre)
            assert par_int == par_membre, (
                "col=%d corner=%d : le triangle differe selon la forme de la cle" % (col, ordinal))
            assert len(par_int) == 3, "col=%d corner=%d : %r n'est pas un triangle" % (
                col, ordinal, par_int)
            formes[(col, ordinal)] = tuple(par_int)
    assert len(set(formes.values())) == 12, (
        "les 6 coins x 2 parites doivent donner 12 triangles DISTINCTS : %r" % len(set(formes)))
    # hors domaine : le natif garde `if (5 < direction)` -> le centre SEUL
    assert BQ.get_tiles_in_triangle_shape((2, 5), 6) == [(2, 5)]

    # 6 -- `geometry._TRIANGLE_SHAPE_DIRECTIONS` alimente le selecteur DSL `TilesInTriangleShape` ;
    #     il est confronte a `battle_query` par le meme couple de directions, coin par coin.
    for ordinal, couple in SNAP_TRIANGLE_DIRS:
        assert GEO._TRIANGLE_SHAPE_DIRECTIONS[ordinal] == couple
        assert GEO._TRIANGLE_SHAPE_DIRECTIONS[Corner(ordinal)] == couple

    # 25 + 7 -- les quatre registres de prediction : consultes par `.get(int(...))` dans
    #           `make_damage_predictions`. On atteste l'equivalence des deux formes d'acces sur
    #           chaque cle, faute d'accesseur public dedie (ce sont des registres prives).
    for table, snap in ((PA._MAKE_DMG_INPUT_OVERRIDES, SNAP_INPUT_OVERRIDES),
                        (PA._PLAYBOOK_PROFILE_OVERRIDE, SNAP_PROFILE_OVERRIDE),
                        (PA._MAKE_DMG_EXTRA_EVENTS, SNAP_EXTRA_EVENTS),
                        (AA._PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE, SNAP_NOT_MINMAX_AVERAGE)):
        for ordinal, attendu in snap:
            membre = ActiveAbilityType(ordinal)
            assert _valeur_comparable(table.get(ordinal)) == attendu
            assert _valeur_comparable(table.get(membre)) == attendu

    # `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` est DISJOINTE des deux registres de moyenne
    # (garde #350) : la conversion ne doit pas l'avoir rendue intersectante.
    assert not (set(map(int, AA._PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE))
                & set(map(int, AA._PREDICTION_MINMAX_RANDOM_READ))), (
        "la table #350 n'est plus disjointe de `_PREDICTION_MINMAX_RANDOM_READ`")

    # `ability_range` consulte `TARGETING_OPTIONS_UNPORTED` pour la portee : les deux formes de la
    # cle doivent rendre la meme zone.
    for ordinal, _ in SNAP_TARGETING_UNPORTED:
        membre = ActiveAbilityType(ordinal)
        assert AR.tiles_in_range_reach(ordinal, None) == AR.tiles_in_range_reach(membre, None)
