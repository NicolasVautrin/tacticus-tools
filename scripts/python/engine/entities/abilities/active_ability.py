"""Port FIDÈLE de `IdunBattle.Entities.Abilities.AActiveAbility` (+ NormalAttackAbility).

Mirror live : l'ability expose `GetDamage / GetHits / GetDamageProfile` que le scorer
(`Playbook.MakeDamagePredictions`) consomme avant d'appeler la prédiction. Les valeurs viennent
de la config (gameconfig = registre `BattleQuery@0x48`, RE IdunBattle.Core.Services.BattleQuery$$GetAbilityConfig) au niveau de l'unité,
SAUF l'attaque normale dont le dégât d'arme n'est PAS dans gameconfig (id générique 69) → fourni
par la capture `combatSnapshot.normalAttack` (= dégât de base d'arme résolu).

⚠ Modèle de dégât (mesuré) :
  • attaque NORMALE : `GetDamage` rend UNE base (pré-spread) ; le spread ±20% est appliqué par la
    prédiction (`CalculateDamageSpread`). base = avg(min,max) capté.
  • ability SPÉCIALE : gameconfig fournit `minDmg/maxDmg` par niveau EXPLICITES (pas de spread
    symétrique). Le `GetDamage` par-ability exact se porte incrémentalement ; défaut = min/max config.
"""
from __future__ import annotations

from fractions import Fraction

from ..unit_context import UnitContext
from ..stats import StatType
# Cles de `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` (#270-r1 volet 2) : des ids d'abilities ACTIVES.
# Depuis #270-r1-r1, c'est AUSSI le type des ELEMENTS des cinq registres de moyenne min/max.
from ..active_ability_type import ActiveAbilityType
# `_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY` porte les DEUX enums : sa cle est un
# `ActiveAbilityType`, sa valeur un `TriggeredAbilityType` -- c'est le sujet meme de la table.
from ..triggered_ability_type import TriggeredAbilityType
# `UnitsWithTrait(..., 2 = Summon)` du sélecteur de `HadesAutocannons` — l'id natif vient de l'enum,
# jamais d'un littéral (cf. `entities/traits/unit_trait.py`).
from ..traits.unit_trait import UnitTrait as _UnitTrait
# `HasEffect(Tiles(Subject), 5 = Fire)` du selecteur de `DaemonicOrdnance` — meme regle : l'id natif
# vient de l'enum, jamais d'un litteral (cf. `entities/effect_type.py`).
from ..effect_type import EffectType as _EffectType
from .ability_configuration import AbilityConfiguration
from ...services.damage_prediction import get_default_attack_hits
from ...services.min_max_damage import MinMaxDamage
from ...dsl import nodes as dsl   # facade DSLFactory (construction des noeuds)
# `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` et `$$CalculateAverage` — les DEUX moyennes que
# la prédiction d'ability emprunte selon le playbook (cf. `_PREDICTION_MINMAX_AVERAGE`).
from ...dsl.base import _round_fix64, calculate_average
# #158 : table `DamageProfileType index -> nom` DERIVEE de l'enum (source unique, ex-copie transcrite retiree).
from ..damage_profile_type import PROFILE_NAME_BY_INDEX as _PROFILE_BY_INDEX  # re-exporte (prediction.py l'importe d'ici)
# #270-r4 : direction de BattleQuery.GetTilesInTriangleShape (...Utils.Hex.Corner).
from ...hex_corner import Corner
from ...services.damage_prediction import get_attack_piercing_damage_ratio
from ..damage_trait import DamageTrait
from ..traits.unit_trait import UnitTrait
from ..unit_selection_type import UnitSelectionType as _UnitSelectionType
# `TacticalPrecisionAbility.get_aoe_targets` interroge `WillBeCharging` (`IBattleQuery` slot 0xcd).
# Import EN TETE, forme B (le module, pas le nom) : `engine.battle_query` est une FEUILLE (ses
# seuls imports sont `hexgeo` et `engine.hex_corner`), donc aucune arete de cycle a fermer --
# verifie en process frais, `import engine.battle_query` ne ramene pas ce module.
from ... import battle_query as _bq


# ─── #344 : la PRÉDICTION d'ability moyenne `minDmg/maxDmg` par DEUX chaînes natives distinctes ───
#
# Le 6ᵉ argument que `<X>Playbook$$MakeDamagePredictions` passe à
# `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` prend l'une de DEUX formes, portées
# chacune par UN corps DÉDUPLIQUÉ (donc UN SEUL nom ghidra pour tous ses propriétaires) :
#
#   (a) `<X>Ability$$GetDamageAmountMain` — corps partagé étiqueté
#       `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$GetDamageAmountMain`
#       -> `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage`
#       =  `Half(Sum(Direct(minDmg), Direct(maxDmg)), rule = 0)`
#       -> `IdunBattle.Entities.Formulas.DivideAmount$$Calculate`
#       -> `IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round` demi-vers-le-PAIR.
#
#   (b) `<X>Ability$$GetDamage` — corps partagé étiqueté
#       `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetDamage`
#       -> `AActiveAbility$$MinMaxDamage(state, isPrediction: FALSE)` = `RandomAmount(minDmg, maxDmg)`,
#       dont le playbook prend le slot 4 d'`IAmountFormula` =
#       `IdunBattle.DSL.AAmountFormula$$CalculateAverage` = `(min + max) / 2` ENTIER = TRONCATURE.
#
# Les deux ne divergent QUE lorsque `minDmg + maxDmg` vaut 3 mod 4, d'exactement 1 — invisible
# deux fois sur trois. Les DEUX faces sont MESURÉES LIVE (`probe_344_ability_damage_average.py`) :
# FlailSwing 1042 relève de (a) et le natif MONTE ; PlasmaCannon 1150 relève de (b) et le natif
# TRONQUE. Un port qui mettrait tout le monde d'un seul côté est faux dans l'autre moitié.
#
# ⚠ Le NOM du corps ne dit JAMAIS à quelle forme appartient une ability donnée (les deux corps sont
# dédupliqués) : la voie de lecture est les XREFS ENTRANTES de chaque corps, et — quand le playbook
# n'appelle aucune méthode d'ability — la lecture du call-site lui-même. #350 a bouclé l'inventaire :
# les ensembles ci-dessous sont EXHAUSTIFS pour le build `rnca9r7q6c`, parce que la moyenne min/max
# ne peut naître QUE de `AActiveAbility$$MinMaxDamage{,Average}` (dont les xrefs sont énumérées) ou
# d'un `DSLFormulas$$Half`/`$$Divide` INLINE dans le playbook (dont les xrefs le sont aussi : deux
# playbooks, `SorcerousFacade` et `IncendiaryShells`). Le DÉFAUT reste (b) — qui est aussi le
# comportement historique du port. ⚠ Une ability absente des DEUX registres n'est pas « (b) lue » :
# elle est NON LUE. Cf. docs/rl/case-344 et docs/rl/case-350.

# (a1) corps DÉDUPLIQUÉ `<X>Ability$$GetDamageAmountMain` -> `AActiveAbility$$MinMaxDamageAverage`.
#
# ⚠ #270-r1-r1 : les cinq registres ci-dessous portaient leurs 55 ids en ORDINAUX NUS, avec le nom
# en commentaire de fin de ligne. Le rôle « élément de conteneur » n'était visité par AUCUN des cinq
# rôles du recenseur, donc ce gisement se lisait `0`. Le discriminant est le NOM déjà cité au site :
# confronté à `data/symbols/<build>/frida/enums.tsv`, il matche 55/55 `ActiveAbilityType`, tandis que
# `TriggeredAbilityType` et `EffectType` nomment systématiquement autre chose au même ordinal
# (1173 = `MasterOfTheTutelaries_Summon` / `Markerlight_Visual`, par exemple). L'ordinal, lui, ne
# tranche rien. Il reste en commentaire de fin de ligne : il ne désigne plus, il documente.
_A_VIA_GET_DAMAGE_AMOUNT_MAIN = frozenset({
    ActiveAbilityType.ArcScourge,              # 1173  (`ArcScourgePlaybook$$EvaluateNonComparable`)
    ActiveAbilityType.ArmoriumCherub,          # 1014
    ActiveAbilityType.BasiliskBarrage,         # 1026  (`BasiliskBarragePlaybook$$GenerateAttackPredictionsForShells`)
    ActiveAbilityType.BrazierOfHolyFire,       # 1041
    ActiveAbilityType.BringerOfDespair,        # 1022
    ActiveAbilityType.CrushingClaws,           # 1105
    ActiveAbilityType.Executioner,             # 1066  (`ExecutionerPlaybook$$GeneratePredictions`)
    ActiveAbilityType.FlailSwing,              # 1042  -- MESURÉ LIVE (bras (a) du probe #344)
    ActiveAbilityType.FragBomb,                # 1017
    ActiveAbilityType.HarbingerOfDestruction,  # 1008
    ActiveAbilityType.HarvesterOfSouls,        # 1067
    ActiveAbilityType.MortisRound,             # 1004
    ActiveAbilityType.MultiThreatEliminator,   # 1006
    ActiveAbilityType.PlagueWind,              # 1035
    ActiveAbilityType.PsychicMaelstrom,        # 1027
    ActiveAbilityType.SanctorumMissile,        # 1062
    ActiveAbilityType.ScythingTalons,          # 1065
    ActiveAbilityType.StranglethornCannon,     # 1056
})

# (a2) corps DÉDUPLIQUÉ `<X>Ability$$GetDamage(state, isPrediction)` — étiqueté
# `IdunBattleLogic.Entities.Abilities.Active.Loki.StaffOfStarsAbility$$GetDamage` — qui FORWARDE
# `isPrediction` à `AActiveAbility$$MinMaxDamage`. Les ONZE call-sites de playbook posent tous
# `mov r8b, 1` (lu à l'octet) : `isPrediction = TRUE` -> branche `Half(Sum(Direct(mn), Direct(mx)), 0)`,
# donc EXACTEMENT la même arithmétique que (a1). Le nom du corps ne prédit rien : c'est le littéral
# du call-site qui tranche.
_A_VIA_STAFF_OF_STARS_GET_DAMAGE = frozenset({
    ActiveAbilityType.AncestralFortune,             # 1207  (`AncestralFortunePlaybook$$MakeDamagePredictions`)
    ActiveAbilityType.Fragstorm,                    # 1078
    ActiveAbilityType.HadesAutocannons,             # 1147
    ActiveAbilityType.KillMaimBurn,                 # 1132  (`KillMaimBurnPlaybook$$EvaluateNonComparable`)
    ActiveAbilityType.LeadingTheCharge,             # 1204
    ActiveAbilityType.LightOfSanguinius,            # 1177
    ActiveAbilityType.LivingBatteringRam,           # 1111  (`LivingBatteringRamPlaybook$$EvaluateNonComparable`)
    ActiveAbilityType.ScytheOfDust,                 # 1074
    ActiveAbilityType.SeekerMissileFrequencyLock,   # 1069
    ActiveAbilityType.StaffOfStars,                 # 1073  (DEUX call-sites : cible principale + volet secondaire)
})

# (a3) corps PROPRE de l'ability (non dédupliqué, donc nommé par ghidra), qui aboutit à la même
# moyenne demi-vers-le-pair. Pour les quatre premiers le call-site du playbook pose `isPrediction = 1`.
_A_VIA_OWN_ABILITY_BODY = frozenset({
    ActiveAbilityType.BladeOfMagnus,          # 1157  `BladeOfMagnusAbility$$GetDamage` = Sum(MinMaxDamage(true), If(HasEffect(5), Direct(extraDmg), 0))
    ActiveAbilityType.DaemonicOrdnance,       # 1148  `DaemonicOrdnanceAbility$$GetDamage` -> MinMaxDamage(true)  (4e arg `mov r9b, 1`)
    ActiveAbilityType.MortarionsPlagueWind,   # 1093  `MortarionsPlagueWindAbility$$GetDamage1` -> MinMaxDamageAverage
    ActiveAbilityType.MurderousSwing,         # 1137  `MurderousSwingAbility$$GetCorrectDamage` -> MinMaxDamageAverage sur les DEUX branches du If
    ActiveAbilityType.ReapingScythe,          # 1095  `ReapingScytheAbility$$GetDamage` : `isPrediction != 0` -> MinMaxDamageAverage
    ActiveAbilityType.SpiritLeech,            # 1104  `SpiritLeechAbility$$GetAttackDamage` -> MinMaxDamage(true) (les deux branches du ConditionalAmount)
})

# (a4) le playbook n'appelle AUCUNE méthode d'ability : il INLINE la moyenne. Même primitive finale
# (`DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)`), donc même arrondi.
_A_INLINE_IN_PLAYBOOK = frozenset({
    ActiveAbilityType.IncendiaryShells,   # 1044  `IncendiaryShellsAbility$$GetDamageRange(random = 0)` = Divide(Sum(Get(mn), Get(mx)), Get(2), 0)
    ActiveAbilityType.SorcerousFacade,    # 1100  `SorcerousFacadePlaybook$$MakeDamagePredictions` = Half(Sum(Get(mn), Get(mx)), 0)
})

_PREDICTION_MINMAX_AVERAGE = (_A_VIA_GET_DAMAGE_AMOUNT_MAIN | _A_VIA_STAFF_OF_STARS_GET_DAMAGE
                              | _A_VIA_OWN_ABILITY_BODY | _A_INLINE_IN_PLAYBOOK)

# Famille (b), LUE elle aussi (xrefs du corps `VigilanceEternalAbility$$GetDamage`) — elle coïncide
# avec le défaut, donc rien à brancher ; on la NOMME pour distinguer « lu et confirmé (b) » de
# « non lu, retombé sur le défaut ». Consommée par les gardes de #344.
_PREDICTION_MINMAX_RANDOM_READ = frozenset({
    ActiveAbilityType.BlightGrenades,           # 1176
    ActiveAbilityType.DakkaDakkaDakka,          # 1171
    ActiveAbilityType.DoomSiren,                # 1199
    ActiveAbilityType.EntropyCannons,           # 1168
    ActiveAbilityType.ExcruciatingFrequencies,  # 1197
    ActiveAbilityType.PlagueburstMortar,        # 1169
    ActiveAbilityType.ExplosivePresents,        # 1170
    ActiveAbilityType.FrenziedFiring,           # 1036  (DEUX call-sites : cible d'origine + volet AoE)
    ActiveAbilityType.HeavyWarpFlamer,          # 1227
    ActiveAbilityType.HeraldOfTheApocalypse,    # 1020
    ActiveAbilityType.LashOfTorment,            # 1196
    ActiveAbilityType.MassDriverAccelerator,    # 1222
    ActiveAbilityType.MightFromBelow,           # 1165
    ActiveAbilityType.PlasmaCannon,             # 1150  -- MESURÉ LIVE (bras (b) du probe #344)
    ActiveAbilityType.StrikeFromTheShadows,     # 1225
    ActiveAbilityType.Supercharge,              # 1103
    ActiveAbilityType.TacticalPrecision,        # 1154
    ActiveAbilityType.VigilanceEternal,         # 1202  (`VigilanceEternalPlaybook$$EvaluateNonComparable`)
    # #350 -- corps PROPRE de l'ability, `isPrediction` CODÉ EN DUR À FAUX (pas un paramètre) :
    ActiveAbilityType.SavageEchoes,             # 1230  `SavageEchoesAbility$$GetDamage` = Sum(MinMaxDamage(this, state, 0), Multiply(...))
})


# ─── #350 : les abilities dont la PRÉDICTION n'est NI (a) NI (b) — leur base n'est PAS une moyenne ───
#
# Résultat de lecture à part entière : on les NOMME au lieu de les forcer dans l'une des deux formes.
# Elles ne sont dans AUCUN des deux registres ci-dessus, donc `get_damage()` leur rend le défaut
# (troncature de la moyenne) — ce qui est faux sur un axe PLUS PROFOND que l'arrondi : ce n'est pas
# la bonne GRANDEUR. Certaines sont déjà corrigées en amont par un handler
# `playbook/prediction/abilities.py::_MAKE_DMG_INPUT_OVERRIDES` (colonne « corrigé »), les autres
# restent des résidus chiffrés. Aucun code ne branche sur cette table : elle est LUE par la garde
# offline de #350, qui vérifie sa disjonction d'avec les deux registres de moyenne.
_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE = {
    # ActiveAbilityType : (symbole natif porteur de la formule, ce que le natif prend réellement,
    #                      corrigé ?) — l'ordinal reste en fin de ligne, il ne désigne plus.
    ActiveAbilityType.HellfireShells:      # 1080
        ("HellfireShellsPlaybook$$MakeDamagePredictions", "Direct(minDmg) SEUL", True),
    ActiveAbilityType.GreatFrostAxe:       # 1089
        ("GreatFrostAxePlaybook$$MakeDamagePredictions", "Get(minDmg) SEUL", True),
    ActiveAbilityType.Stikkbomb:           # 1051
        ("StikkbombPlaybook$$MakeDamagePredictions", "Get(minDmg) SEUL", True),
    ActiveAbilityType.MartialInspiration:  # 1191
        ("MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext",
         "round(minDmg * buff), hits = 1", True),
    # #974 -- TROU de ce registre, trouve en portant la face DECISION. Le corps appelle
    # `GetVariableForLevel(cfg, 0xc, ...)` DIRECTEMENT : il n'y a AUCUN `MinMaxDamage` dedans, donc
    # la base n'est pas la moyenne. S'y ajoute un terme FLAT (`GetExtraDamage`) que le generique
    # ignorait -- les deux ecarts vont en sens OPPOSES, ce qui les rendait inseparables d'une
    # mesure scalaire. `nrOfHits`, lui, N'EST PAS surcharge (le natif rappelle `GetHits`).
    ActiveAbilityType.TalonsOfTheEmperor:  # 1195
        ("TalonsOfTheEmperorPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext",
         "Get(minDmg 0xc) SEUL + GetExtraDamage (flat) ; profil CONDITIONNEL "
         "(damageProfile_2 si MeetSecondDamageProfileRequirement) ; hits = nrOfHits", True),
    ActiveAbilityType.PlasmaGrenade:       # 1098
        ("PlasmaGrenadePlaybook$$MakeDamagePredictions", "Get(minDmg) SEUL", True),
    # #352 : la lecture « maxDmg SEUL » de #350 etait INCOMPLETE. Le playbook n'appelle pas
    # `GenerateMultiHitAttackPredictions` : il appelle la surcharge « amount » de
    # `IBattleQuery.GetAttackPrediction` avec `nrOfHits x maxDmg` en UN coup (la surcharge pose
    # `hits: 1` en dur). Ce n'est donc ni la bonne grandeur NI la bonne structure.
    ActiveAbilityType.FragstormGrenadeLauncher:  # 1048
        ("FragstormGrenadeLauncherPlaybook$$MakeDamagePredictions",
         "nrOfHits x maxDmg (var 0xd) en UN coup -- hits=1 pose par la surcharge appelee", True),
    # #353 — RECTIFICATION de la ligne posee par #350. Elle nommait `ExplodesAbility$$GetDamage`
    # (`PercentageOf(StatAmount(Health), ...)`) comme LA formule de 1059 : lecture PARTIELLE, prise
    # sur les xrefs de ce corps. `RammingSpeedPlaybook$$MakeDamagePredictions` emet QUATRE batchs,
    # et ce corps n'alimente que les deux derniers, sous condition :
    #   1. CIBLE   : `Get(minDmg 0xc)`, hits = `GetNumberConstant(0x2f)` LITTERAL, profil config ;
    #   2. CASTER  : memes base/profil, hits = `GetNumberConstant(0x32 = nrOfHits_2)` (recul du ram) ;
    #   3/4. si `selfPreds.Any(p => p.WillBeKill)` SEULEMENT : `ExplodesAbility$$GetDamage` evaluee,
    #        puis `GenerateAttackPredictions(..., Nullable(0xf = DirectDamage))` sur
    #        `Friends(AdjacentUnits(GetTileToMoveTo))` puis sur `Enemies(<idem>)`.
    # 1 et 2 sont PORTES (`_ramming_speed_inputs` / `_ramming_speed_self_events`). Pour 3/4,
    # `GetTileToMoveTo` exige `UtilityBucket[Tile 7, RammingSpeed_MostAdjacentEnemies 54]` : ce
    # bucket est PORTE depuis #353-r1a (`engine/utilities/ramming_speed.py` + `decider.py`, 54
    # inscrite a `UTILITY_BY_TYPE`, confrontee live 2/2). Ce qui RESTE ouvert pour 3/4 est le gate
    # `selfPreds.Any(p => p.WillBeKill)`, non observable : `get_WillBeKill` lit
    # `CannotBeGuaranteedKilled@+0x89` et `BlockScenarios[0]+0x0c`, ni l'un ni l'autre expose par
    # `aiPlaybookPredict` -- volet (b) de `#353-r1`, cf. `docs/rl/case-353-ramming-speed-prediction.md`.
    ActiveAbilityType.RammingSpeed:  # 1059
        ("RammingSpeedPlaybook$$MakeDamagePredictions",
         "Get(minDmg) SEUL + hits const 0x2f ; batch SELF (hits 0x32) ; batch EXPLOSION conditionnel",
         True),
}


# ─── #350-r3 : les playbooks dont la formule ne porte PAS sur leur propre `ActiveAbilityType` ──────
#
# Un `<X>Playbook` n'évalue pas toujours l'ability qui l'a fait charger : il peut aller CHERCHER une
# autre ability par `Playbook<T>$$GetAbility<T>(this, <id>, ...)`. Quand cet `<id>` est un
# `TriggeredAbilityType`, aucune inscription à `_PREDICTION_MINMAX_AVERAGE` / `_RANDOM_READ` n'a de
# sens : ces deux registres sont indexés par `ActiveAbilityType` et ne sont lus que par
# `AActiveAbility.get_damage`, chemin que l'objet évalué N'EMPRUNTE PAS (il descend de
# `BaseTriggeredAbility`, config à `+0x20`, pas `AActiveAbility`, config à `+0x60`).
#
# Table PUREMENT DOCUMENTAIRE — aucun code ne branche dessus ; la garde offline de #350 vérifie
# qu'elle est DISJOINTE des trois tables ci-dessus (une entrée qui y apparaîtrait aussi serait une
# qualification d'enum fausse, exactement l'erreur que cette table existe pour empêcher).
# ⚠ CE SITE EST LE CAS D'ÉCOLE des DEUX enums au même endroit (#270-r3 pour la clé, #270-r1-r1 pour
# la valeur) : la CLÉ est un `ActiveAbilityType` (1160 = `HeavyRailRifle`) et la VALEUR un
# `TriggeredAbilityType` (1260 = `HeavyRailRifle_Attack`, ordinal ABSENT d'`ActiveAbilityType`).
# C'est exactement ce que cette table existe pour dire, et l'ordinal ne le disait pas.
_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY = {
    # ActiveAbilityType : (playbook natif, TriggeredAbilityType RÉELLEMENT évalué, chaîne lue)
    ActiveAbilityType.HeavyRailRifle:  # 1160
        ("HeavyRailRiflePlaybook$$EvaluateNonComparable",
         TriggeredAbilityType.HeavyRailRifle_Attack,
                      # 1260 = 0x4ec — littéral passé à `Playbook<T>$$GetAbility<T>`, et valeur rendue
                      # par `HeavyRailRifle_PendingAttackEffect$$GetTriggeredAbilityType`
         "MassiveScythingTalonsAbility$$GetDamage -> BaseTriggeredAbility$$MinMaxDamage "
         "= RandomAmount(cfg@0x20[0xc], cfg@0x20[0xd]), pris au slot 4 d'IAmountFormula "
         "(= AAmountFormula$$CalculateAverage, TRONCATURE) -> forme (b)"),
}


class AActiveAbility:
    """Base ability active. `ability_type` = ActiveAbilityType ; `config` = AbilityConfiguration
    (None pour l'attaque normale générique) ; `caster` = UnitContext de l'attaquant ;
    `ability_state` = AbilityState PER-ABILITY {level, multiplier} (cf. propriété `level`)."""

    def __init__(self, ability_type: int, caster: UnitContext,
                 config: AbilityConfiguration | None = None,
                 ability_state: dict | None = None):
        self.ability_type = ability_type
        self.caster = caster
        self.config = config
        # AbilityState PER-ABILITY (#100) — mirror du natif : chaque AActiveAbility est construite
        # avec SON couple {Level, VariableMultiplierPercentage} (entrée ActiveAbilityComponent,
        # _abilityState @0x4c ; capteur combatSnapshot.abilityStates). C'est CE niveau qui indexe
        # TOUTES les variables config (IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel), PAS le canal global
        # unitConfig.activeAbilityLevel (mesuré u80 PlasmaCannon : natif maxDmg[65]x120 = 1396 vs
        # global 50x180 = 1594). None/{} => fallback global (runners sans capteur, offline).
        self.ability_state = ability_state or {}

    @property
    def level(self) -> int:
        """Niveau PER-ABILITY (AbilityState.Level) ; fallback = canal global activeAbilityLevel."""
        lv = self.ability_state.get("level")
        return int(lv) if lv else self.caster.active_ability_level

    @property
    def variable_multiplier(self) -> int | None:
        """VariableMultiplierPercentage PER-ABILITY (AbilityState @+4) ; None si non capté
        (l'appelant retombe alors sur le mult global de rareté `scene.mult`)."""
        m = self.ability_state.get("multiplier")
        return int(m) if m is not None else None

    @property
    def multiplier(self) -> int:
        """Multiplier EFFECTIF pour `GetVariableForLevel` : per-ability (capteur #100) sinon le
        canal global de rareté du porteur (`unitConfig.abilityVariablesMultiplier` — même valeur
        que `scene.mult`)."""
        m = self.ability_state.get("multiplier")
        if m is None:
            m = self.caster.ability_variables_multiplier or 100
        return int(m)

    # AActiveAbility.GetDamageProfile (IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile) : profil de dégât de l'ability.
    def get_damage_profile(self) -> str:
        if self.config is not None:
            prof = (self.config.constants or {}).get("damageProfile")
            if prof:
                return prof
        # Config sans damageProfile → le natif rend un Nullable VIDE (-1, IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile), résolu en
        # aval sur le profil de l'ARME du porteur, RANGED-first (cf. GetAmountOfHitsRangedFirstOrMelee).
        # GROUND TRUTH step-17 seed777 : HarvesterOfSouls (pas de damageProfile) → per-coup natif
        # 987/1481 = entrée × 0.55 = pierce 55 = HeavyRound (l'arme RANGED de Maugan), MÊME en
        # adjacent — l'ancien fallback Physical (pierce 0) soustrayait l'armure pleine (dmax 549).
        import gameconfig as _GC
        gu = _GC.unit(self.caster.visual_id or "") or {}
        weapons = gu.get("weapons") or []
        ranged = next((w for w in weapons if w.get("Range")), None)
        w = ranged or (weapons[0] if weapons else None)
        if w and w.get("DamageProfile"):
            return w["DamageProfile"]
        return _PROFILE_BY_INDEX.get(self.caster.damage_type, "Physical")

    # GetHits : nombre de coups (base config + ExtraHits / ExtraHitsMelee).
    def get_hits(self) -> int:
        base = self.config.get_variable_for_level(
            "nrOfHits", self.level, 1) if self.config else 1
        return get_default_attack_hits(base, self.caster.stat(StatType.EXTRA_HITS),
                                       self.caster.extra_hits_melee, self.caster.is_melee)

    # GetDamage : base de dégât (single, pré-spread) — défaut générique (special : min/max config).
    # Chaque var est scalée ×mult/100 + Fix64.Round DANS GetVariableForLevel
    # (`IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`, gate
    # variablesAffectedByRarityBonus). DÉCOMPOSÉ PAR ÉTAGE #100 (varLevelDumps, u80 PlasmaCannon
    # (50,180)) : minDmg 665→1197 + maxDmg 886→1595 → avg 1396 ; bouts prédiction [1117,1675] =
    # ±20% EXACT. ⚠ Le « base = maxDmg seul » (#96) est RÉFUTÉ par cette lecture — le 1396 se
    # décomposait AUSSI en maxDmg[65]×1.2 (sous-détermination), d'où le faux verdict.
    #
    # ⚠ L'ARRONDI DE LA MOYENNE N'EST PAS UNIQUE (#344) : il dépend de la forme que le
    # `<X>Playbook$$MakeDamagePredictions` passe en 6ᵉ argument de
    # `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` — cf. `_PREDICTION_MINMAX_AVERAGE`.
    def get_damage(self) -> int:
        if self.config is not None:
            lvl, mult = self.level, self.multiplier
            mn = self.config.get_variable_for_level("minDmg", lvl, 0, mult)
            mx = self.config.get_variable_for_level("maxDmg", lvl, 0, mult)
            if mn or mx:
                if int(self.ability_type) in _PREDICTION_MINMAX_AVERAGE:
                    # (a) `AActiveAbility$$MinMaxDamageAverage` = `Half(Sum(Direct(mn), Direct(mx)), 0)`
                    # -> `DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)`
                    # = `Fix64.Round` demi-vers-le-PAIR.
                    return _round_fix64(Fraction(mn + mx, 2), 0)
                # (b) `AActiveAbility$$MinMaxDamage(state, isPrediction: FALSE)` = `RandomAmount(mn, mx)`,
                # dont le playbook prend le slot 4 = `AAmountFormula$$CalculateAverage` = TRONCATURE.
                return calculate_average(mn, mx)
            return self.config.get_variable_for_level("dmg", lvl, 0, mult) \
                or self.config.get_variable_for_level("baseDmg", lvl, 0, mult)
        return 0

    def get_correct_damage(self, base: int, nr_enemies: int) -> int:
        """`<Ability>.GetCorrectDamage` — DÉFAUT = base seule (`GetMultipleUnitsDamage` générique : aucune
        clause conditionnelle sur le NB de cibles). Override par-ability pour les clauses gatées sur le
        nombre d'ennemis touchés (ex. MurderousSwing : +extraDmg si UN seul ennemi). `nr_enemies` = total
        des cibles AoE (principale + secondaires)."""
        return base

    def get_pierce(self) -> int:
        """pierceRatio (0..100). Défaut 100 = perçage neutre (pas de réduction armure) ; l'attaque
        normale surcharge avec le profil d'arme. (Abilities spéciales : profil config = TODO.)"""
        return 100

    def get_special_hits(self, is_melee: bool) -> int:
        """Nombre de coups pour la PRÉDICTION spéciale (`Playbook.MakeDamagePredictions` ->
        `ability.GetHits`). DÉFAUT générique = `GetDefaultAttackHits(nrOfHits + ExtraHits[+Melee])`
        (comportement historique de `generate_multi_hit_attack_prediction`, préservé pour les abilities non portées). Les
        abilities à formule de coups PROPRE (DSL : snowball/flag/…) surchargent — mirror des sous-classes
        `AActiveAbility` natives (ex. `BloodyFuryAbility.GetNumTotalHits`, `HarvesterOfSoulsAbility.GetHits`)."""
        base = self.config.get_variable_for_level(
            "nrOfHits", self.level, 1) if self.config else 1
        return get_default_attack_hits(base, self.caster.stat(StatType.EXTRA_HITS),
                                       self.caster.extra_hits_melee, is_melee)

    def get_aoe_targets(self, ctx: "dsl.DslContext") -> list:
        """Cibles AoE ADDITIONNELLES (hors cible principale) que l'ability touche aussi — base du Σ
        multi-cible (`CalculateUtilityFromPredictions` somme un `ProbableDamageEvent` par cible touchée,
        cf. §39). DÉFAUT = aucune (ability mono-cible). Les abilities AoE surchargent avec l'arbre DSL de
        leur `GetSurroundingUnits`/`GetOtherTargets`. `ctx.target` = cible principale (exclue du set)."""
        return []

    def get_prediction_set_repeat(self, n_targets: int) -> int:
        """Nombre de fois que `MakeDamagePredictions` RÉ-ÉMET la liste d'events de dégât (= la BOUCLE
        EXTERNE du playbook natif sur le set de cibles). DÉFAUT = 1 (émission LINÉAIRE : 1 event/cible).
        Override par-ability pour les playbooks à DOUBLE boucle sur le MÊME set : ex. MurderousSwing
        (`IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions` boucle sur `AdjacentEnemies(caster)`
        ET `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` re-boucle sur ce MÊME set) -> **count² events**,
        chaque cible apparaît `count` fois. Confirmé LIVE (#108 : K=1->1, K=2->4, K=3->9, perTarget=K).
        `n_targets` = taille du set AoE (= `1 + len(aoe)`, mirror du `Enumerable.Count(set)` natif)."""
        return 1

    def get_max_secondary_targets(self) -> int | None:
        """Plafond de cibles SECONDAIRES (`ability.GetMaxSecondaryTargets`, ex. PlasmaCannon
        `meta_pvp_screen_test.u003Cu003Ec$$u003CStartu003Eb__6_1 return 2`). Le playbook pondère alors le 2ᵉ batch par `min(1, max/n)`
        (`FromIntFraction(max, n)` dans `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions`). None = pas de plafond
        (batch AoE non pondéré : Harvester/BloodyFury)."""
        return None

    def get_health_to_lose(self, max_hp: int) -> int | None:
        """`<Ability>.GetHealthToLose` — COÛT en PV de l'ability (ex. DakkaDakkaDakka IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose =
        `PercentageOf(StatAmount(owner, 5=Health), ConfigConst(0x4f healthPct))`). Le playbook émet
        alors un `ProbableDamageEvent` SELF dont l'utilité est NÉGÉE (friendly-fire, DamageUtility
        IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext) — mesuré step-13 seed777 : −15.0 exact par candidat DakkaDakkaDakka
        (= (80+20)×healthPct/100 à PV pleins). DÉFAUT None = pas de coût en PV."""
        return None

    def get_damage_min_max_raw(self) -> MinMaxDamage:
        """min/max EXPLICITES de la config (special) — avant scenario. Pour les abilities dont
        gameconfig donne directement min/max (pas de spread symétrique)."""
        lvl = self.level
        if self.config is not None:
            return MinMaxDamage(min=self.config.get_variable_for_level("minDmg", lvl, 0),
                                max=self.config.get_variable_for_level("maxDmg", lvl, 0))
        return MinMaxDamage()


class NormalAttackAbility(AActiveAbility):
    """Attaque normale (id concret, ex. 69). Dégât d'arme NON dans gameconfig → capté
    (`UnitContext.normal_*`). `GetDamage` rend la base (avg) ; `GetHits` = hits captés ;
    profil = `unit.damageType`."""

    def get_damage(self) -> int:
        """Base PAR COUP = stat Attack (RE : `DSLFactory.NormalAttackDamage`=`StatAmountFormula(Attack)`).
        VALIDÉ live (8/11 exact) : la chaîne `base par-coup × hits-arme + pierce + armure` reproduit
        l'oracle pour les unités sans buff dégât (u88/u92/u96). `get_attack_prediction` applique le ×hits
        (la boucle proba somme un event par coup ; crit=0 → Σ = hits × per-coup)."""
        return self.caster.stat(StatType.ATTACK)          # stat(0)=Attack

    def get_hits(self) -> int:
        """hits de l'ARME (gameconfig) + ExtraHits — GetDefaultAttackHits. (≠ `normal_hits` capté
        parfois : u96 capté=2 mais arme Power=3.)"""
        return get_default_attack_hits(self.caster.normal_weapon_hits, self.caster.stat(StatType.EXTRA_HITS),
                                       self.caster.extra_hits_melee, not self.caster.normal_ranged)

    def get_pierce(self) -> int:
        """pierceRatio de l'attaque normale — GetAttackPiercingDamageRatio (IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio) : profil
        d'arme `PiercingRatio` (gameconfig) + bonus LasCannon (#71 : +50 si le profil porte
        DamageTrait.LasCannon(3) ET l'attaquant UnitTrait.HeavyWeapon(1001)|Emplacement(1016)) +
        ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}, clamp 0..100.
        ⚠ DEAD CODE actuel (aucun call-site : prédiction ET combat passent par
        `battle_query.select_weapon_pierce`, qui applique DÉJÀ le bonus #71). Rendu fidèle (plus de
        `profile_has_lascannon=False` codé en dur) pour ne pas ré-introduire le gap si un chemin le recâble."""
        import gameconfig as GC
        dir_pierce = (self.caster.extra_pierce_ranged if self.caster.normal_ranged
                      else self.caster.extra_pierce_melee)
        prof = GC.damage_profile(self.caster.normal_profile) or {}
        profile_has_lascannon = DamageTrait.LasCannon.name in (prof.get("Traits") or ())
        att_traits = self.caster.traits or ()
        attacker_hw_emp = (UnitTrait.HeavyWeapon.name in att_traits
                           or UnitTrait.Emplacement.name in att_traits)
        return get_attack_piercing_damage_ratio(
            self.caster.normal_profile_pierce, profile_has_lascannon=profile_has_lascannon,
            attacker_extra_pierce=self.caster.extra_pierce, attacker_extra_pierce_dir=dir_pierce,
            attacker_has_heavy_weapon_or_emplacement=attacker_hw_emp)

    def get_damage_min_max_raw(self) -> MinMaxDamage:
        """min/max captés directement (prédiction native vs allié-déploiement — référence de capture)."""
        return MinMaxDamage(min=self.caster.normal_min, max=self.caster.normal_max)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Sous-classes SPÉCIALES = mirror 1:1 des `AActiveAbility` natives. Chaque méthode de coups native BÂTIT
# un arbre DSL (`DSLFactory`) ; on le TRANSCRIT nœud-par-nœud (engine/dsl/nodes.py) et on l'évalue sur un
# `DslContext`. Constantes config (ids natifs) : nrOfHits(0x2f), extraHit(0x2b), maxNrOfHits(0x48).
# Registre → `active_ability_for` = miroir du dispatch natif `ActiveAbilityType → classe`.
# ─────────────────────────────────────────────────────────────────────────────────────────────


def _hits_ctx(ability) -> dsl.DslContext:
    """`DslContext` pour un arbre de coups (numérique) : config + niveau + compteur runtime + flags.
    Niveau = PER-ABILITY (`ability.level`, AbilityState #100), fallback global géré par la propriété."""
    return dsl.DslContext(
        config=ability.config,
        ability_level=ability.level,
        times_attacked=getattr(ability.caster, "times_attacked", 0) or 0,
    )


class HarvesterOfSoulsAbility(AActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits` — transcription EXACTE de l'arbre DSL natif :
    `If(HasFlag(@+0x160), ConfigConst(nrOfHits), Sum(ConfigConst(nrOfHits), ConfigConst(extraHit)))`.
    Le flag (@+0x160, gate non encore RE) est ABSENT dans le cas commun (branche `false` → nrOfHits+extraHit
    ; confirmé côté agrément : natif = kill sûr, l'attaque normale seule ne l'était pas). ⚠ Volet AoE
    (`GetSurroundingUnits`/`GetSurroundingDamageAmount`) = prédiction multi-cible séparée (task #39)."""

    _HITS = dsl.If(dsl.HasFlag("harvester_flag_0x160"),
                   dsl.ConfigConst("nrOfHits", 1),
                   dsl.Sum(dsl.ConfigConst("nrOfHits", 1), dsl.ConfigConst("extraHit", 0)))

    # IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetSurroundingUnits (RE COMPLETE 2026-07-02) — tree natif EXACT (chaine LUE) :
    #   A   = IdunBattleLogic.Entities.DSLSelectors$$SurroundingUnits(sel@0x160, ConfigConst(0x16)) -> IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles -> Units
    #   B   = Enemies(sel@0x160, AdjacentFriends(sel@0x178, 1))     IdunBattleLogic.Entities.DSLSelectors$$Enemies ; IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends
    #   AoE = op_BitwiseAnd(A, B)                                   IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd
    # Selecteurs resolus (IdunBattleLogic.Entities.DSLSelectors$$InitializeShared alloue +0x148..+0x198 via ctors gshared MISLABELES
    # `BoardGeometry..ctor` -> identite = pointeur de classe + usage, PAS le nom du ctor) :
    #   sel@0x160 = OWNER/caster : StatAmount(@0x160,Health=5)=maxHP caster (DakkaDakkaDakka.GetHealthToLose
    #               IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose) ; HasFlag(@0x160)=flag caster (IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits). Comme POSITION
    #               -> tuile COURANTE de l'owner : GetSurroundingUnits(param_1) ne recoit AUCUN casterPosition
    #               -> sel@0x160 resout la position LIVE (owner non deplace en prediction), != tuile d'attaque.
    #   sel@0x178 = TARGET (cible principale param_4 du playbook IdunBattle.AI.Playbook.Loki.HarvesterOfSoulsPlaybook$$MakeDamagePredictions).
    # ConfigConst 0x16 = AbilityConstantType.range=22 (dump.cs) = constante "range" gameconfig = 3 (Harvester) ;
    #   IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant LEVE une exception si la cle est ABSENTE (IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant
    #   TryGetValue->throw) -> "range" est TOUJOURS present (l'ancienne hypothese "0x16 absent -> defaut" etait
    #   FAUSSE). AdjacentFriends(target,1) = Friends(target, Units(AdjacentTiles(target)) - {target}) = allies
    #   de la CIBLE adjacents a elle = ennemis du caster ; Enemies(caster, .) les garde tous -> B = ring-1 HEX
    #   ennemis de la cible. A = unites <= range(3) hex de la tuile COURANTE du caster (centre exclu).
    # A & B PRUNE ASYMETRIQUEMENT : ground-truth seed777 step-17 (caster reel @(5,6), range 3) -> A = {168(d3),
    #   88(d2)} exclut 92/90(a d4) => main-92->{168} (90 d1-de-92 exclu), main-90->{168} (92 exclu),
    #   main-168->{88} (92/90 exclus) : les 4 sets natifs EXACTS. L'ancien ring-1-seul sur-incluait (90 dans
    #   AoE-92, 92/90 dans AoE-168) -> Harvester sur-value 168 vs la vraie cible 92. Surrounding dmg =
    #   minDmg_2/maxDmg_2 (== minDmg/maxDmg) -> reutilise generate_multi_hit_attack_prediction.
    _AOE = dsl.Damageable(dsl.And(
        dsl.SurroundingUnits(dsl.OwnerTile(), dsl.ConfigConst("range", 1)),
        dsl.AdjacentEnemies(dsl.TargetTile(), dsl.Const(1)),
    ))

    def get_special_hits(self, is_melee: bool) -> int:
        if self.config is None:
            return 1
        return self._HITS.evaluate(_hits_ctx(self))

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)


class BloodyFuryAbility(AActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$GetNumTotalHits` — transcription EXACTE de l'arbre DSL natif :
    `Sum(ConfigConst(nrOfHits), Min(Multiply(ConfigConst(extraHit), TotalTimesAttacked),
    Difference(ConfigConst(maxNrOfHits), ConfigConst(nrOfHits))))` = SNOWBALL sur le nb d'attaques du
    caster, plafonné à `maxNrOfHits`. `TotalTimesAttacked` (compteur runtime @+0x34) NON capté offline →
    `ctx.times_attacked` défaut 0 ⇒ coups = nrOfHits (base). Volet AoE (`GetOtherTargets`) = task #39."""

    _HITS = dsl.Sum(
        dsl.ConfigConst("nrOfHits", 1),
        dsl.Min(
            dsl.Multiply(dsl.ConfigConst("extraHit", 0), dsl.TotalTimesAttacked()),
            dsl.Difference(dsl.ConfigConst("maxNrOfHits", 1), dsl.ConfigConst("nrOfHits", 1)),
        ),
    )

    def get_special_hits(self, is_melee: bool) -> int:
        if self.config is None:
            return 1
        return self._HITS.evaluate(_hits_ctx(self))

    def get_aoe_targets(self, ctx):
        # Sub attend un ensemble d'unités ; la cible principale = ctx.target (via UnitSet).
        main = dsl.UnitSet([ctx.target] if ctx.target else [])
        tree = dsl.Damageable(dsl.Sub(dsl.AdjacentEnemies(dsl.CasterTile(), dsl.Const(1)), main))
        return tree.evaluate(ctx)


class PlasmaCannonAbility(AActiveAbility):
    """`PlasmaCannonAbility` (TypeDefIndex 9922) — « 3x dégâts Plasma à un ennemi à portée 3 et
    jusqu'à DEUX ennemis DERRIÈRE la cible ». Playbook `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions` : batch principal + batch SECONDAIRE (`IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$GetValidSecondaryTargetsSelector`
    = `IdunBattleLogic.Entities.DSLSelectors$$UnitsDirectlyBehind`), pondéré `min(1, GetMaxSecondaryTargets/n)`
    (`GetMaxSecondaryTargets meta_pvp_screen_test.u003Cu003Ec$$u003CStartu003Eb__6_1 = 2`)."""

    _SECONDARY = dsl.Damageable(dsl.UnitsDirectlyBehind())

    def get_aoe_targets(self, ctx):
        return self._SECONDARY.evaluate(ctx)

    def get_max_secondary_targets(self) -> int | None:
        return 2   # GetMaxSecondaryTargets meta_pvp_screen_test.u003Cu003Ec$$u003CStartu003Eb__6_1

    # Dégât : CONFIG-based via le générique `get_damage()` = MinMaxDamage avg (#96 REVERTÉ puis
    # affiné #100) — la « preuve Attack-based » aiPredict==normale était un artefact (GetAllPredictions
    # = preview) et le « base = maxDmg seul » intermédiaire est réfuté par varLevelDumps (min 1197 +
    # max 1595 → avg 1396). VALIDÉ BIT-EXACT vs l'oracle direct `aiPlaybookPredict(1150)` (#102) :
    # port [6282,9423]x3 == natif (u80 (50,180), bouts 1117/1675 ±20%, mods 1.875).


# Registre nom d'ability → sous-classe à formule de coups propre. À ÉTENDRE au fil du portage.
class DakkaDakkaDakkaAbility(AActiveAbility):
    """`DakkaDakkaDakkaAbility` (KillaKan Snappawrecka) — « 6x dmg Projectile à un ennemi à portée 3 ;
    +2 coups par réparation (cap 16) ; perd 15% de sa Health max ».
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetNumHits` = arbre DSL EXACT : `Min(Sum(Direct(nrOfHits 0x2f),
      Multiply(TimesRepaired, Direct(extraHits key 100))), ConfigConst(maxNrOfHits 0x48))`.
      `TimesRepaired` (compteur runtime) non capté offline → 0 ⇒ nrOfHits (=6).
    - damage : `GetDamageFormula` (playbook IdunBattle.AI.Playbook.Loki.DakkaDakkaDakkaPlaybook$$MakeDamagePredictions, helper partagé étiqueté BlightGrenades) =
      `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` = avg(minDmg', maxDmg') niveau+mult → la base
      générique `get_damage()` suffit (bornes VALIDÉES exactes step-13 seed777 : per-coup natif
      404/728/1028/1331 reproduit sur les 4 cibles, D=2244 vs natif 2244.5 → mêmes entiers).
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetHealthToLose` = `PercentageOf(StatAmount(owner, 5=Health), ConfigConst(0x4f
      healthPct=15))` → event SELF négatif (−15.0 exact mesuré par candidat, cf. base)."""

    _HITS = dsl.Min(
        dsl.Sum(dsl.ConfigConst("nrOfHits", 1),
                dsl.Multiply(dsl.TimesRepaired(), dsl.ConfigConst("extraHits", 0))),
        dsl.ConfigConst("maxNrOfHits", 99),
    )

    def get_special_hits(self, is_melee: bool) -> int:
        if self.config is None:
            return 1
        return self._HITS.evaluate(_hits_ctx(self))

    def get_health_to_lose(self, max_hp: int) -> int | None:
        """`DakkaDakkaDakkaAbility$$GetHealthToLose` (decompile `rnca9r7q6c`), MIRROR :

            amount     = DSLFormulas.StatAmount(owner@+0x48, 5 = Health, 2)
            percentage = DSLFormulas.ConfigConst(0x4f = AbilityConstantType.healthPct, this+0x60)
            return DSLFormulas.PercentageOf(amount, percentage, roundingRule: 0)

        ⚠ `roundingRule` VAUT **0**, ET C'EST LE 4e ARGUMENT DU CALL-SITE QUI LE DIT -- lu aux
        octets, pas deduit. `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` ventile `1` =
        `Fix64.Ceiling`, `2` = `Fix64.Floor`, **tout le reste** = `Fix64.Round`, dont le corps
        (`FixMath.NET.Fix64$$Round`, `midpointRounding == 0`) rend la partie entiere quand la
        fraction est `< 0.5`, `+1` quand elle est `> 0.5`, et **arrondit vers le PAIR** sur
        `0x80000000` exact (demi-vers-le-pair). Le port ecrivait `(max_hp * pct) // 100`, un FLOOR :
        faux d'exactement 1 sur toute fraction `>= 0.5`. Sur `healthPct = 15` (constante du
        gameconfig de `DakkaDakkaDakka`), la divergence tombe des que `3 * max_hp mod 20 >= 10` --
        `max_hp = 1237` -> natif 186, ancien port 185. C'est le residu #883-r1 : le foyer DSL
        `entities/formulas.py::PercentageOf` etait deja juste, ce site IMPERATIF le contournait.

        Les deux arrondis intermediaires de `PercentageOf$$CalculateInternal` (le motif
        `x / 100 * 100 -> Round -> / 100`, deux fois) sont NEUTRES pour des operandes entieres :
        `Fraction` les represente exactement, ce que la docstring de `formulas.PercentageOf` etablit
        deja. Seul l'arrondi FINAL, celui de `RoundFix64Result`, est observable.

        `get_variable_for_level` lit la VARIABLE puis, a defaut, la CONSTANTE : `healthPct` vit dans
        `constants` pour cette ability, et c'est cette retombee qui le rend -- le natif, lui, appelle
        `ConfigConst` d'emblee. Meme valeur, chemin different, verifie au gameconfig."""
        pct = self.config.get_variable_for_level("healthPct", self.level, 0) \
            if self.config else 0
        # `roundingRule = 0` -> `Fix64.Round` (demi-vers-le-PAIR), surtout PAS `// 100`.
        return _round_fix64(Fraction(int(max_hp) * int(pct), 100), 0) if pct else None


class MurderousSwingAbility(AActiveAbility):
    """`MurderousSwingAbility` (Tarvakh worldExecutions, id 1137). `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$GetCorrectDamage` =
    `If(AmountIsGreater(nrEnemies, Direct(1)), GetMultipleUnitsDamage=base, GetSingleUnitDamage=
    Sum(base, Direct(GetVariableForLevel(8=extraDmg))))` (`IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$GetSingleUnitDamage`/`IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$GetMultipleUnitsDamage`). Le `+extraDmg`
    (i2 « +1746 Damage si un seul ennemi ») est AJOUTÉ À LA BASE, AVANT le spread ±20% + les mods
    (`predict_attack_raw`/`GetBaseDamageFix64`) → il scale min ET max PROPORTIONNELLEMENT
    (`extraDmg / avg(minDmg,maxDmg) ≈ 0.60` à tous les niveaux → ratio ×1.60), ce N'EST donc NI un
    additif à delta constant NI un %-mod (diagnostic #108 : oracle/moteur = ×1.601 UNIFORME min&max,
    RapidAssault +25% déjà appliqué des deux côtés). `extraDmg` scalé `(level, mult)` comme minDmg/maxDmg.

    AoE mêlée SELF-centrée : `IdunBattle.AI.Playbook.MurderousSwingPlaybook$$MakeDamagePredictions` construit le set `AdjacentEnemies(caster)`
    (`nrEnemies = Count(set)` -> GetCorrectDamage) PUIS boucle DEUX fois dessus (externe = MakeDamage
    Predictions ; interne = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`) -> **count² events**, chaque
    ennemi adjacent apparaît `count` fois (CONFIRMÉ LIVE #108 : K=1->1, K=2->4, K=3->9).
    `get_prediction_set_repeat` = `count` -> réplique la liste d'events count fois (mirror de la
    boucle externe).

    #359-r5 — `get_aoe_targets` rend le set ENTIER, cible COMPRISE, et `make_damage_predictions` ne
    l'en retire plus : ce playbook n'émet **aucun** event pour `<Target>` séparément (relu au
    décompilé — son argument `target` n'est même jamais consommé), donc la cible n'a d'event que par
    la boucle du sélecteur, à sa place. 1137 est pour cela dans `_MAKE_DMG_SELECTOR_ONLY`, avec 1147
    et 1148. Conséquence sur `nrEnemies` : c'est `Enumerable.Count(entities)` = la taille du set —
    ce que le port calculait comme `1 + len(aoe)`, juste tant que la cible est DANS le set (le
    régime ordinaire d'une mêlée), faux d'exactement 1 sinon."""

    _AOE = dsl.Damageable(dsl.AdjacentEnemies(dsl.CasterTile(), dsl.Const(1)))

    def get_correct_damage(self, base: int, nr_enemies: int) -> int:
        if nr_enemies != 1 or self.config is None:   # >1 ennemi -> GetMultipleUnitsDamage = base seule
            return base
        extra = self.config.get_variable_for_level("extraDmg", self.level, 0, self.multiplier)
        return base + int(extra or 0)                # GetSingleUnitDamage = base + extraDmg (key 8)

    def get_aoe_targets(self, ctx):
        # mirror set natif `AdjacentEnemies(caster@0x160, 1, 3)`, rendu TEL QUEL (#359-r5) : c'est LA
        # boucle du playbook, `nrEnemies = Enumerable.Count(set)` en est la taille.
        return self._AOE.evaluate(ctx)

    def get_prediction_set_repeat(self, n_targets: int) -> int:
        return max(1, int(n_targets))                # boucle EXTERNE sur le set AoE -> count² (#108)


class ExecutionerAbility(AActiveAbility):
    """`ExecutionerAbility` (eldarFarseer « Eldryon », id 1066). `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` =
    `DSLFactory.RoundsStarted` (IdunBattleLogic.Entities.DSLFormulas$$RoundsStarted -> `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate`) =
    Σ `UnitComponent.turnsStarted@+0x58` sur les units-in-scope (= le CASTER) = nb de rounds STARTED
    (i2 : « takes 582-2183 Psychic Damage FOR EACH ROUND THAT HAS STARTED »). `ExecutionerPlaybook.
    IdunBattle.AI.Playbook.Loki.ExecutionerPlaybook$$GeneratePredictions` passe N=GetHits comme compte multi-coups à `GenerateMultiHit
    AttackPredictions` -> UN event agrégé par cible, appliedHits=N, dégât = N x base. CONFIRME LIVE
    (#122, probe_122_rounds.py) : aiPlaybookPredict appliedHits 3->8 (+1/round-cycle) ; le port rendait
    appliedHits=1 (config nrOfHits) -> sous-compte xN. Off-by-one : StartTurn incrémente AVANT que
    l'ability agisse -> round 1 = 1 coup (jamais 0). `turnsStarted` = stat 12 (`GetStat(unit,0xc)`,
    `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`, capté par combatSnapshot). Eldryon = unité lineup
    (jamais late-spawn) -> caster.turnsStarted == numéro de round (le verdict re-expert note un scope
    caster-only : lire le compteur du CASTER, PAS un round global — fidèle même pour un caster spawné
    tardivement). Single-target : AUCUN override d'events (le multi-hit loop rend 1 event/cible)."""

    def get_special_hits(self, is_melee: bool) -> int:
        n = self.caster.stat(StatType.TURNS_STARTED)
        return max(1, int(n or 0))     # rounds started (>=1 en bataille ; fallback 1 si non capté)


class MultiThreatEliminatorAbility(AActiveAbility):
    """`MultiThreatEliminatorAbility` (necroDestroyer « Destroyer », id 1006). La PRÉDICTION
    (`IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$MakeDamagePredictions`) passe un nombre de coups
    CONSTANT = **6**, lu du champ STATIQUE de la classe (`IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.cctor` : `**(class+0xb8) = 6`) —
    PAS de la config : l'ability n'a AUCUN `nrOfHits` (seulement `extraHit=1`, consommé par le COMBAT
    `IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$GetExtraHits` / `GetNextHitTargetSelector`, hors prédiction). base = `ArcScourgeAbility.
    IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$GetDamage` = `AActiveAbility.MinMaxDamageAverage` = avg(minDmg,maxDmg) (le générique
    `get_damage`). Le playbook passe `param_8 = null` (Nullable vide) → profil `None` (pierce 0, armure
    PLEINE) via `_PLAYBOOK_PROFILE_OVERRIDE[1006]`. VALIDÉ LIVE (u81→ultraTitus armure 2312) : 6 coups
    plancher 1 (base 1309 < armure) = oracle [6,6]. Le générique rendait 1 coup (config nrOfHits absent)."""

    def get_special_hits(self, is_melee: bool) -> int:
        return 6     # IdunBattleLogic.Entities.Abilities.Active.Loki.MultiThreatEliminatorAbility$$.cctor : champ statique hits = 6 (constante native)


class FrenziedFiringAbility(AActiveAbility):
    """`FrenziedFiringAbility` (blackObliterator « Volk », id 1036). Le playbook
    `IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions` emet **DEUX** batchs
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` :

      1. cible d'ORIGINE — `targets = Target@0x178`, `hits = Evaluate(GetHitsForOriginalTarget)`
         (base GEOMETRIQUE, arbre `get_hits_for_original_target` ci-dessous — case-61, LIVREE) ;
      2. **volet AoE** — `targets = IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets`,
         `hits = 1` **LITTERAL** (immediat du call-site, PAS une constante de config : `nrOfHits`
         (0x2f) vaut deja 1 pour cette ability, mais le natif n'appelle NI `GetNumberConstant` NI
         `GetHits` pour ce batch — recopier `nrOfHits` serait une coincidence, pas un mirror).
         Le resultat du batch 2 est concatene dans la liste du batch 1 (`List.Add` en boucle).

    Les DEUX batchs partagent la meme `GetDamageFormula` (helper etiquete
    `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$GetDamageFormula` =
    `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` avg = `get_damage()` generique) et le
    meme `Nullable(IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile)` (profil config, PAS
    null) -> aucun override base/profil, seul `hits` differe. `param_10` (poids Fix64) = 0 sur les deux
    -> `probability = Fix64.FromInt(1)`, donc AUCUNE ponderation `GetMaxSecondaryTargets` ici.

    `GetTargets` = `DSLFactory.AdjacentEnemies(caster@0x160, TargetTiles@0x190, 1)`, surcharge
    `IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies` a 4 args :
        `Enemies(caster@0x160, Units(AdjacentTiles(TargetTiles@0x190), 1, 3) - TargetTiles@0x190, 3)`
    = les unites d'equipe != celle du CASTER posees sur les tuiles adjacentes (ring-1 hex) a la tuile
    de la CIBLE. Le centre est deja exclu par `AdjacentTiles` (le `op_Subtraction` natif est defensif) ;
    la cible principale, elle, est retiree par `make_damage_predictions`.

    Le filtre VIVANT n'est PAS un noeud du tree : il est porte par `Units(...)`
    (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, occupation de tuile — un mort n'est
    plus sur le board) que `_within` mirrore deja (#57m ; `ctx.units` garde les cadavres). D'ou
    `AdjacentEnemies` NU, sans wrapper `Damageable`."""

    # IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets
    _AOE = dsl.AdjacentEnemies(dsl.TargetTile(), dsl.Const(1))

    #: `hits` LITTERAL du 2e `GenerateMultiHitAttackPredictions` (7e arg = immediat 1) ET du 2e
    #: `AttackWithAttackDamage` de `FrenziedFiringAbility$$ExecuteBehaviour` (`DSLFactory.Direct(1)`).
    AOE_HITS = 1

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)

    @staticmethod
    def get_hits_for_original_target(n_hits: int, max_hits: int):
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetHitsForOriginalTarget`
        — MIRROR 1:1 du DECOMPILE, en ARBRE DSL (source UNIQUE des deux faces : la PREDICTION
        (`_frenzied_firing_inputs`) et le COMBAT (`runner/abilities/blacklegion.py`) EVALUENT
        CET arbre, aucun recalcul impératif parallèle) :

            Min( Cache( Sum( Get(GetHits),                       # GetHits = GetNumberConstant(0x2f=nrOfHits)
                             Count( Filter( Walkable(AdjacentTiles(Target@0x178)),
                                            Not(HasUnit(Subject@0x180))
                                            | Not(AreEnemies(Units(Subject@0x180), Caster@0x160)) ) ) ) ),
                 ConfigConst(0x48 = maxNrOfHits) )

        = `nrOfHits` + le nombre de tuiles ADJACENTES A LA CIBLE marchables ET **pas tenues par un
        ennemi du caster** (tuile vide = comptée ; tuile tenue par un ALLIÉ du caster = comptée AUSSI ;
        seule la présence d'un ennemi l'exclut), plafonné à `maxNrOfHits`. Base GEOMETRIQUE : plus la
        cible est dégagée, plus Volk la crible.

        `Subject@0x180` = l'élément COURANT lié par le `Filter` (mirror du slot `ability+0x180` que
        `FromTriggerSelector` écrase à chaque item) — ici un id de TUILE, d'où les prédicats
        tile-domain `HasUnit`/`Units`.

        Le filtre VIVANT n'est pas un nœud : il vient de `Units(...)`
        (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, lecture par occupation de tuile —
        un mort n'est plus sur le board), que `_units_on`/`Units` mirrorent déjà (#57m).

        INSTANCE FRAICHE PAR APPEL (factory, pas attribut de classe) : le nœud `Cache` est STATEFUL
        (mémoïsation par instance, cf. `Cache`), et le natif reconstruit l'arbre à chaque cast —
        `FrenziedFiringAbility$$ExecuteBehaviour` appelle `GetHitsForOriginalTarget(this)` puis
        `SetCache(<ce nœud>)` AVANT chacune de ses deux attaques, ce qui FIGE la géométrie
        pré-attaque et la partage entre les deux volets.

        `n_hits` (`Get(GetHits)`) et `max_hits` (`ConfigConst(0x48)`) sont RESOLUS PAR L'APPELANT
        depuis SA source de config (le `DslContext` du RUNNER ne porte ni `config` ni `ability_level`,
        contrairement à celui de la prédiction) — même convention que `harvester_of_souls_tree`."""
        pred = dsl.TriggerOr(dsl.Not(dsl.HasUnit(dsl.Subject())),                    # !HasUnit(tile)
                             dsl.Not(dsl.AreEnemies(dsl.Units(dsl.Subject()),        # | !AreEnemies(
                                                    dsl.Caster())))                  #     Units(tile), caster)
        tiles = dsl.Filter(dsl.Walkable(dsl.AdjacentTiles(dsl.Target())), pred)
        return dsl.Min(dsl.Cache(dsl.Sum(dsl.Get(int(n_hits)), dsl.Count(tiles))),
                       dsl.Const(int(max_hits)))


class SavageEchoesAbility(AActiveAbility):
    """`SavageEchoesAbility` (bloodTerminator « Cezare », id 1230). Le playbook
    `IdunBattle.AI.Playbook.Loki.SavageEchoesPlaybook$$MakeDamagePredictions` n'est PAS generique : il
    passe en 6e arg de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    la formule `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage`
    (arbre ci-dessous), et NON la `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` generique.
    Les 3 AUTRES arguments sont, eux, generiques (lus au decompile du playbook) :
      * profil = `IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile` -> `Nullable` NON vide
        (= `damageProfile` config = Eviscerate) : AUCUN quirk `param_8 = null` facon #164/#165 ;
      * hits  = `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits`
        = `GetNumberConstant(0x2f = nrOfHits)` = le chemin generique `get_special_hits` ;
      * cibles = `IdunBattleLogic.Entities.DSLSelectors$$Entity(target)` -> MONO-CIBLE (aucun batch AoE).
    Seule la BASE diverge donc, et c'est `_savage_echoes_inputs` qui la fournit."""

    @staticmethod
    def get_damage_formula(min_max: int, extra_dmg: int):
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` — MIRROR 1:1
        du DECOMPILE, en ARBRE DSL (source UNIQUE des deux faces : la PREDICTION
        (`_savage_echoes_inputs`) et le COMBAT (`runner/abilities/bloodangels.py`) EVALUENT CET arbre,
        aucun recalcul imperatif parallele) :

            Sum( MinMaxDamage(minDmg 0xc, maxDmg 0xd),                   # base config
                 Multiply( Get(GetVariableForLevel(config, 8 = extraDmg)),
                           Count( CanAddUnit( AdjacentTiles(Owner@0x148) ) ) ) )

        = la base config PLUS `extraDmg x (nb de tuiles adjacentes au porteur ou une unite PEUT etre
        ajoutee)`. `CanAddUnit` = `IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` ->
        `IdunBattle.Entities.TileExtensions$$CanAddUnitFromAbility` = tuile MARCHABLE et LIBRE (aucun
        pied d'unite vivante). Plus Cezare est degage, plus il frappe fort.

        SUJET = `Owner` (slot factory `+0x148`, cf. la carte `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` :
        `0x148 Owner · 0x158 Actor · 0x160 Caster · 0x168 CasterTile · 0x178 Target`) — pour une ability
        ACTIVE l'Owner EST le caster, d'ou le noeud `Caster()` du port (le port n'expose pas de noeud
        `Owner` distinct ; meme convention que le mirror COMBAT deja livre).
        ⚠ C'est un selecteur d'ENTITE : le natif en prend la MainTile REELLE
        (`EntityExtensions$$GetTiles`), PAS la tuile candidate `casterPosition` du balayage IA — celle-ci
        vit dans les slots `CasterTile/CasterTiles@0x168/0x170`, que cet arbre n'utilise pas. Le compte
        est donc le MEME pour toutes les tuiles candidates d'un tour, et le port le mirrore en lisant la
        position du dict d'unite (`_entity_pos`), jamais `ctx.caster_pos`.

        `min_max` et `extra_dmg` sont RESOLUS PAR L'APPELANT depuis SA source (meme convention que
        `FrenziedFiringAbility.get_hits_for_original_target`) : la PREDICTION passe l'avg
        `MinMaxDamage(avgFlag)` = `get_damage()` generique — c'est le SEUL etage ou l'arbre est evalue,
        `GenerateMultiHitAttackPredictions` reduisant la formule a UN scalaire (`FUN_1800250d0` sur
        `param_6`) avant `PredictAttack` ; le COMBAT passe la borne min PUIS la borne max
        (`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage`, Calculate index 2/3), le
        terme `Multiply(...)` etant identique sur les deux bornes."""
        return dsl.Sum(dsl.Get(int(min_max)),
                       dsl.Multiply(dsl.Get(int(extra_dmg)),
                                    dsl.Count(dsl.CanAddUnit(dsl.AdjacentTiles(dsl.Caster())))))


class MassDriverAcceleratorAbility(AActiveAbility):
    """`MassDriverAcceleratorAbility` (votanChampion « Kimm », id 1222) — CHARGE a splash.
    `IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions` emet **DEUX**
    batchs `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
    concatenes dans une seule `List<ProbableDamageEvent>` :

      1. cible PRINCIPALE — `param_4 = target`, `param_5 = <selecteur Target>` (`DSLSelectors+0x60`),
         `param_6 = <GetDamage>`, `param_7 = AActiveAbility$$GetHits`,
         `param_8 = Nullable(AActiveAbility$$GetDamageProfile)` ;
      2. **volet SPLASH** — pour CHAQUE entite de
         `IdunBattleLogic.Entities.Abilities.Active.Loki.MassDriverAcceleratorAbility$$GetAdjacentAttackTargets` :
         `param_4 = <cette entite>`, `param_5 = IdunBattleLogic.Entities.DSLSelectors$$Entity(<cette
         entite>)`, `param_6 = <LA MEME valeur de degat>`, `param_7 = AActiveAbility$$GetHits2`,
         `param_8 = Nullable(AActiveAbility$$GetDamageProfile2)`.

    Le SET est `GetAdjacentAttackTargets` =
    `Enemies(DSLSelectors+0x48 = caster, AdjacentUnits(DSLSelectors+0x60 = target, unique: 1, sel: 3), 3)`
    -- les ENNEMIS DU CASTER poses sur les tuiles ADJACENTES A LA CIBLE (la cible elle-meme est deja
    retiree par `AdjacentUnits`). C'est le MEME artefact natif que la face COMBAT :
    `...MassDriverAcceleratorAbility$$ExecuteBehaviour` re-inline exactement
    `Enemies(caster@0x48, AdjacentUnits(target@0x60, 1, 3), 3)`, le passe a `DSLSelectors$$Cache` /
    `DSLBehaviors$$SetCache`, puis attaque `DSLSelectors$$Alive(<cache>)` avec son 2e
    `DSLBehaviors$$AttackWithAttackDamage`. Le filtre VIVANT n'est pas un noeud du set : il vient de
    `Units(...)` (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, occupation de tuile --
    un mort n'est plus sur le board), que `_within` mirrore deja (#57m). D'ou `AdjacentEnemies` NU.

    TROIS lectures que le decompile impose, et qu'on ne devine pas :

    1. **Le splash porte sur l'ENNEMI ADJACENT, pas sur la cible principale.** `param_5` est
       `DSLSelectors$$Entity(<entite iteree>)`, un selecteur MONO-ENTITE construit A CHAQUE tour de
       boucle -- alors que
       `IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$MakeDamagePredictions` et
       `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` repassent, EUX, le
       selecteur `Target` (d'ou leur quirk « n events identiques sur la cible principale », cf.
       `prediction.make_secondary_multihit_event`). Ici les events sont DISTINCTS : chacun est predit
       contre les PV / l'armure / les traits de SON ennemi. `GenerateMultiHitAttackPredictions` le
       confirme etage par etage : `param_4` ne sert qu'a peupler l'`AbilityEntities`
       (`Target` + `EntityExtensions$$GetTiles(param_4)`), et les cibles reellement predites sont
       celles que rend `SelectUniqueUnits(param_5, entities, 3)`.
    2. **Le degat du splash est celui du batch PRINCIPAL, pas `MinMaxDamage2`.** Le playbook evalue
       `<GetDamage>` = `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(abilityState,
       isPrediction: false)` UNE SEULE FOIS, dans une locale, et repasse CETTE locale en `param_6` aux
       deux batchs. La face COMBAT, elle, appelle bien `MinMaxDamage2` pour son 2e
       `AttackWithAttackDamage` -- c'est une DIVERGENCE natif/natif entre decision et execution.
       Sans consequence NUMERIQUE sur cette config (`minDmg_2`/`maxDmg_2` y sont egaux a
       `minDmg`/`maxDmg`), mais la garder explicite evite de re-deriver la base du splash depuis
       `minDmg_2` -- ce qui serait faux des qu'un build les desaccorderait.
    3. **Seuls les COUPS et le PROFIL different entre les deux batchs** : `GetHits2` =
       `GetNumberConstant(0x32 = nrOfHits_2)` et `GetDamageProfile2` = `GetEnumConstant(0x3f =
       damageProfile_2)`. Sur 1222 : `nrOfHits` = `nrOfHits_2` = 1, mais `damageProfile` =
       `DirectDamage` et `damageProfile_2` = **Physical** -- deux `PiercingRatio` distincts, donc
       deux degats predits distincts contre une meme armure. C'est ce profil qui rend le volet
       observable.

    `param_10` (fournisseur de poids Fix64) = **0** sur les DEUX batchs -> `Fix64.FromInt(1)`, donc
    AUCUNE ponderation `GetMaxSecondaryTargets` (`get_max_secondary_targets` reste None).
    Les entrees per-batch sont fournies par `engine.playbook.prediction.abilities.
    _mass_driver_accelerator_inputs` ; cette classe ne porte que le SET."""

    # `...MassDriverAcceleratorAbility$$GetAdjacentAttackTargets` (le referent d'equipe de `Enemies`
    # est le CASTER -- `DSLSelectors+0x48` --, ce que `AdjacentEnemies` mirrore par construction).
    _AOE = dsl.AdjacentEnemies(dsl.TargetTile(), dsl.Const(1))

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)


class FragBombAbility(AActiveAbility):
    """`FragBomb` (1017, `astraBullgryn` « Kut Skoden ») — le volet **SPLASH** de sa prédiction (#957).

    `IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$MakeDamagePredictions` émet **DEUX** batchs
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
    concaténés dans une seule `List<ProbableDamageEvent>` — MÊME forme que
    `MassDriverAcceleratorPlaybook` :

        damage = <X>Ability$$GetDamageAmountMain(abilityState)      # corps DEDUPLIQUE, etiquete
                                                                    # `StranglethornCannonAbility$$
                                                                    #  GetDamageAmountMain`
        hits   = AActiveAbility$$GetHits()                          # GetNumberConstant(0x2f = nrOfHits)
        list   = GenerateMultiHitAttackPredictions(caster, casterPosition, target,
                     <DSLSelectors+0x60 = Target>, damage, hits, param_8 = 0, null, 0)
        ae     = default(AbilityEntities); ae.<+0x08> = caster; ae.<+0x10> = target
        hits2  = AActiveAbility$$GetHits2()                         # GetNumberConstant(0x32 = nrOfHits_2)
        for e in <GetAdjacentTargets>.Select(ae):
            list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, e,
                               DSLSelectors$$Entity(e), damage, hits2, param_8 = 0, null, 0) )
        return list

    QUATRE lectures que le décompilé impose :

    1. **Le SET est `AdjacentUnits` NU — friendly-fire.**
       `...FragBombAbility$$GetAdjacentTargets` =
       `AdjacentUnits(<DSLSelectors+0x60> = Target, unique: 0, sel: 3) op_Subtraction
        <DSLSelectors+0x48> = Caster`.
       AUCUN wrapper `Enemies(...)` (contraste `MassDriverAccelerator`, qui en a un) : les ALLIÉS du
       caster adjacents à la tuile ciblée sont prédits eux aussi, et leur event est `friendly` —
       donc son utilité est NÉGÉE par `CalculateUtilityFromDamageEvent`. C'est le MÊME artefact que
       la face COMBAT (`runner/abilities/astramilitarum.frag_bomb_tree` :
       `Sub(Sub(Units(AdjacentTiles(Target())), Target()), Caster())`, mesuré live — l'allié
       `astraCreed` adjacent à la cible encaisse bien 3 coups).
       `AdjacentUnits` retire déjà le centre (la cible) par construction.
    2. **Le splash porte sur l'unité ADJACENTE**, pas sur la cible principale : `param_5` est
       `DSLSelectors$$Entity(<entité itérée>)`, reconstruit à chaque tour (contraste
       `Stikkbomb`/`PlasmaGrenade`, qui repassent le sélecteur `Target` — d'où leur quirk « n events
       identiques sur la cible principale », cf. `prediction.make_secondary_multihit_event`). Chaque
       event est donc prédit contre les PV / l'armure / les traits de SON unité.
    3. **Le dégât du splash est celui du batch PRINCIPAL** : `damage` est évalué UNE fois, hors
       boucle, et repassé en `param_6` aux deux batchs. La config 1017 n'a d'ailleurs AUCUNE variable
       `_2` (`minDmg_2`/`maxDmg_2` absents) — la plage est partagée, exactement comme côté COMBAT.
    4. **Seuls les COUPS changent entre les deux batchs**, et `param_8` (le `Nullable<DamageProfile>`)
       est **0 sur les DEUX** — d'où l'entrée `_PLAYBOOK_PROFILE_OVERRIDE[FragBomb] = "None"`, qui
       vaut donc pour le principal comme pour le splash (pierce 0, armure PLEINE). Contraste
       `MassDriverAccelerator`, dont le splash a son PROPRE profil (`GetDamageProfile2`).

    Les entrées per-batch sont fournies par `engine.playbook.prediction.abilities.
    _frag_bomb_inputs` ; cette classe ne porte que le SET."""

    # `...FragBombAbility$$GetAdjacentTargets` — `AdjacentUnits` NU (aucun filtre d'équipe) moins le
    # CASTER. `radius = 1` : le natif n'a qu'UNE surcharge d'`AdjacentUnits`
    # (`(this, origin, unique, selectionType)`), dont le corps est
    # `Units(AdjacentTiles(origin), …) op_Subtraction origin` — l'anneau 1 exact.
    _AOE = dsl.Sub(dsl.AdjacentUnits(dsl.TargetTile(), dsl.Const(1)), dsl.Caster())

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)


class HadesAutocannonsAbility(AActiveAbility):
    """`HadesAutocannons` (1147, MoW `blackForgefiend`) — le volet **AoE** de sa prédiction (#359).

    `IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$MakeDamagePredictions` ne prédit PAS « la
    cible » : il BOUCLE sur les entités que rend
    `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetEntitiesFromSelector(
    IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets, caster,
    casterPosition, target)` et, pour CHACUNE, `List.AddRange(GenerateMultiHitAttackPredictions(
    caster, casterPosition, <entite>, DSLSelectors$$Entity(<entite>), <damage>, <hits>, ...))` :

        damage = StaffOfStarsAbility$$GetDamage(state, isPrediction = 1)   # (a2), hors boucle
        hits   = AActiveAbility$$GetHits()                                 # hors boucle
        for e in GetEntitiesFromSelector(GetAllTargets(), ...):
            list.AddRange(GenerateMultiHitAttackPredictions(..., e, Entity(e), damage, hits,
                                                            0, Nullable<DamageProfile>(null), 0))

    Il n'y a donc **NI second batch NI sélecteur secondaire** : c'est LA boucle du sélecteur, dont le
    port n'avait aucun mirror -> `AActiveAbility.get_aoe_targets` rendait `[]` et le port émettait
    UN event là où le natif en émet un PAR summon retenu.

    Le sélecteur, VERBATIM (`...HadesAutocannonsAbility$$GetAllTargets`) :

        range = AbilityConfiguration$$GetNumberConstant(0x16 = range)
        ring  = DSLSelectors$$SurroundingUnits(Target, range, unique: 1, includeCenter: 1, sel: 3)
        f     = DSLSelectors$$Friends(of: Target, entities: ring, sel: 3)
        w     = DSLSelectors$$UnitsWithTrait(f, 2 = Summon, 3)
        desc  = DSLSelectors$$SortByRow(Tiles(w), 0, 0, false) ; asc = SortReverse(desc)
        return DSLSelectors$$If(AreEqual(CurrentPlayer, Player(1)), desc, asc)

    = les **SUMMONS du camp de la CIBLE**, dans le disque de rayon `range` centré sur ELLE, cible
    INCLUSE (`includeCenter = 1`). i2 : « a targeted enemy summon and all other enemy summons within
    2 hexes ». MÊME arbre que la face COMBAT (`runner/abilities/blacklegion.
    hades_autocannons_get_all_targets`) ; il est redit ici parce que `entities/` ne peut pas importer
    `runner/` (sens de dépendance), exactement comme `MassDriverAcceleratorAbility._AOE`.

    Le référent `DSLSelectors+0x60` est **Target** et non Caster — lu sur un second consommateur dont
    le nom natif le DIT : `...DaemonicOrdnanceAbility$$GetTargetAreaTiles` =
    `TilesOnSameElevation(+0x60, TilesInTriangleShape(+0x60, dir), 1)` (la zone-triangle est ancrée
    sur la cible, confronté live en #350-r3), et `MassDriverAcceleratorAbility` cite déjà la même
    carte (`+0x48 = caster`, `+0x60 = target`). Le contraste `+0x30 = Owner` est lisible sur
    `...HadesAutocannonsAbility$$ExecuteBehaviour`, qui attaque DEPUIS `DSLSelectors+0x30`.

    #359-r2 — LE TRI EST PORTÉ (il ne l'était pas), et la RE qui vivait ici portait DEUX erreurs :

      * `SortByRow(Tiles(w), 0, 0, false)` était nommé `asc`. **Faux** : le 5ᵉ argument de
        `IdunBattleLogic.Entities.DSLSelectors$$SortByRow` est `ascending` (ctor nommé
        `IdunBattle.Entities.Selectors.SortByRowSelector$$.ctor(this, tiles, state, pseudoRng,
        sameColumnIsRandom, additionalSortingFormula, ascending)`, champ `+0x38`), et
        `IdunBattle.Entities.Selectors.SortByRowSelector$$Select` prend `OrderByDescending` quand
        il vaut 0. Le call-site passe `false` ⇒ la branche « joueur courant = team 1 » est
        DÉCROISSANTE, et c'est `SortReverse` qui produit la croissante.
      * `Player(1)` n'est pas « le joueur nº 1 » : le paramètre de
        `IdunBattleLogic.Entities.DSLSelectors$$Player` est nommé `team` au décompilé et part dans
        `PlayersByTeamSelector$$.ctor(this, state, team)`. D'où `CurrentPlayerIsOfTeam(1)`.

    #359-r5 — L'ORDRE DES EVENTS EST FERMÉ, et ce n'était pas ce tri qui l'interdisait : c'était
    l'ÉTAGE AU-DESSUS. Le natif boucle sur le sélecteur TEL QUEL, cible incluse
    (`includeCenter: 1`), donc la cible principale occupe sa place TRIÉE : mesuré natif
    `[113, 110, 116]`, la cible `110` en 2ᵉ position. Le port extrayait la cible du set et l'émettait
    en TÊTE ; il ne le fait plus pour 1147 — l'ability est dans `_MAKE_DMG_SELECTOR_ONLY`
    (`playbook/prediction/abilities.py`), le registre des playbooks SANS batch `<Target>`. La
    correction est REGISTRÉE et non globale : sur les huit abilities du port qui surchargent
    `get_aoe_targets`, CINQ ont bien un batch `<Target>` explicite (Harvester, PlasmaCannon,
    FrenziedFiring, MassDriverAccelerator — plus FragBomb hors de ce lot), et l'appliquer à toutes
    les aurait cassées. Les trois concernées : 1147, 1148, 1137 MurderousSwing.

    Sans effet sur le SCORE tant que le consommateur SOMME (`CalculateUtilityFromPredictions`) :
    l'ensemble et les valeurs sont inchangés, seul l'ordre bouge. Ce que la correction ferme est la
    FIDÉLITÉ de la liste émise — et le seul lecteur de position du port (`main = events[0]` de
    `playbook/base.py`) ne descend, en aval, que dans `_spiritleech_lifesteal_util`, qui ne
    concerne aucune de ces trois abilities.

    ⚠ Le natif boucle sur des entités **TUILE** (`GetAllTargets` finit par `Tiles(...)`), là où la
    face COMBAT re-résout l'occupant (`DSLSelectors$$Units(GetAllTargets())`). Le substrat de
    prédiction du port porte des dicts d'UNITÉ : `Units(Tiles(w))` est l'identité sur l'ensemble
    (une tuile de summon a ce summon pour occupant), donc l'ENSEMBLE est le même ; seule l'identité
    publiée par le natif dans `ProbableDamageEvent.target` peut être celle de la TUILE."""

    # `...HadesAutocannonsAbility$$GetAllTargets`, TRI COMPRIS (#359-r2 ; cf. docstring).
    # `include_center=True` = `SurroundingUnits(..., includeCenter: 1, ...)` : la cible elle-même est
    # un des summons frappés, et depuis #359-r5 elle reste DANS la liste rendue — `make_damage_
    # predictions` ne l'en retire plus (1147 est dans `_MAKE_DMG_SELECTOR_ONLY`), donc l'ensemble ET
    # l'ordre émis sont exactement ceux du sélecteur.
    _SET = dsl.UnitsWithTrait(
        dsl.Friends(dsl.SurroundingUnits(dsl.TargetTile(), dsl.ConfigConst("range", 0),
                                         include_center=True),
                    reference=dsl.Target()),
        int(_UnitTrait.Summon))
    # `SortByRow(Tiles(w), 0, 0, false)` — `ascending = false` ⇒ row DÉCROISSANTE (cf. docstring).
    # Le port omet le `Tiles(...)` interposé : `SortByRow` classe par `_entity_pos`, mirror du
    # `EntityExtensions$$GetMainTileId` que la clé native applique, et qui rend la même tuile pour
    # une unité que pour une entité-tuile. Le garder changerait le DOMAINE du résultat (tuiles au
    # lieu d'unités) sans changer l'ordre — or le consommateur du port lit des unités.
    _DESC = dsl.SortByRow(_SET, ascending=False)
    # `DSLSelectors$$If(AreEqual(CurrentPlayer, Player(1)), desc, SortReverse(desc))`
    _AOE = dsl.SelectIf(dsl.CurrentPlayerIsOfTeam(1), _DESC, dsl.SortReverse(_DESC))

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)


class DaemonicOrdnanceAbility(AActiveAbility):
    """`DaemonicOrdnance` (1148, MoW `blackForgefiend`) — le pendant AoE de sa prédiction (#359-r1).

    `IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$MakeDamagePredictions` a la MÊME forme que
    celui de 1147 : il ne prédit PAS « la cible », il BOUCLE sur les entités que rend
    `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetEntitiesFromSelector(
    IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetAllDamageableTargets,
    caster, casterPosition, target)` :

        hits = AActiveAbility$$GetHits()                                    # hors boucle
        for e in GetEntitiesFromSelector(GetAllDamageableTargets(), ...):
            damage = DaemonicOrdnanceAbility$$GetDamage(Entity(e), state, isPrediction = 1)
            list.AddRange(GenerateMultiHitAttackPredictions(caster, casterPosition, e, Entity(e),
                                                            damage, hits, 0,
                                                            Nullable<DamageProfile>(null), 0))

    ⚠ `GetDamage` est évalué DANS la boucle (contraste avec 1147, où il est hoisté), mais son corps
    IGNORE l'argument `target` — `IdunBattleLogic.Entities.Abilities.Active.Loki.
    DaemonicOrdnanceAbility$$GetDamage` = `AActiveAbility$$MinMaxDamage(state, isPrediction)` seul.
    La base est donc la MÊME pour toutes les entités : rien à surcharger ici.

    Le sélecteur, VERBATIM (`...DaemonicOrdnanceAbility$$GetAllDamageableTargets`) :

        area = GetTargetAreaTiles()
        p    = DSLTriggers$$HasEffect( DSLSelectors$$Tiles(Subject@+0x68), 5 = Fire, 0, 6 )
        f    = DSLSelectors$$Filter(area, p)
        u    = DSLSelectors$$Units(f, unique: 1, sel: 3)
        return DSLSelectors$$Enemies(Caster@+0x48, u, 3)

    et sa zone (`...DaemonicOrdnanceAbility$$GetTargetAreaTiles`) :

        dir = DSLFormulas$$If( DSLTriggers$$IsPositionMachineForCurrentPlayer(2),
                               Direct(1), Direct(4) )
        return TilesOnSameElevation( Target@+0x60, TilesInTriangleShape(Target@+0x60, dir), 1 )

    = les **ENNEMIS du caster debout sur une tuile EN FEU** de la zone-triangle ancrée sur la CIBLE.
    MÊME arbre que la face COMBAT (`runner/abilities/blacklegion.
    daemonic_ordnance_all_damageable_targets`) ; il est redit ici parce que `entities/` ne peut pas
    importer `runner/` (sens de dépendance), exactement comme `HadesAutocannonsAbility._AOE`.

    `Tiles(Subject)` est COLLAPSÉ en `Subject()` : le sujet lié par le `Filter` est déjà une
    entité-TUILE (la source est un sélecteur de tuiles), et `UnitsMainTilesSelector` sur une
    `TileEntity` rend cette tuile — l'identité. Même collapse que la face COMBAT.

    ⚠ Ce que le SET ajoute au gate de cible principale de #350-r3 : ce dernier réduit l'appartenance
    de la CIBLE à « ennemi du caster ET sa tuile porte Fire » (exact, parce que la zone est ancrée
    SUR elle, donc la contient toujours, quel que soit `dir`). Mais l'ensemble, lui, contient aussi
    les DEUX voisines du triangle : une cible hors zone de feu avec un autre ennemi dedans donnait
    `∅` côté port et un event côté natif. MESURÉ (#359-r1, board `MC1_67`, cible sur tuile FROIDE,
    un ennemi brûlant dans son triangle) : natif **1** event — sur l'AUTRE ennemi —, port **0**.

    NON PORTÉ, et sans consommateur ici : le natif rend des entités TUILE (`Filter` tile-domain) et
    re-résout l'occupant par `Units`, ce que ce nœud fait aussi ; seule l'identité publiée dans
    `ProbableDamageEvent.target` pourrait être celle de la TUILE — le live mesure des ids d'UNITÉ."""

    # `...DaemonicOrdnanceAbility$$GetTargetAreaTiles` — `dir` par le prédicat de plateau, jamais une
    # constante : `ctx.current_player_machine_position` (canal `Scene.machine_of_war_position`,
    # cascade `BattleQuery$$GetPositionMachineForPlayer`). Non mesuré -> False -> `dir = 4`, la
    # branche `else` NATIVE ; c'est une dégradation NOMMÉE, pas un défaut inventé.
    _AREA = dsl.TilesOnSameElevation(
        dsl.Target(),
        dsl.TilesInTriangleShape(dsl.Target(),
                                 # #270-r4 : direction de GetTilesInTriangleShape est
                                 # DECLARE IdunBattleLogic.Utils.Hex.Corner.
                                 dsl.If(dsl.IsPositionMachineForCurrentPlayer(2),
                                        dsl.Const(int(Corner.NorthEast)),
                                        dsl.Const(int(Corner.SouthWest)))),
        1)
    _AOE = dsl.Enemies(dsl.Units(dsl.Filter(_AREA, dsl.HasEffect(dsl.Subject(),
                                                                 int(_EffectType.Fire)))))

    def get_aoe_targets(self, ctx):
        return self._AOE.evaluate(ctx)


class BrazierOfHolyFireAbility(AActiveAbility):
    """`BrazierOfHolyFire` (1041, `adeptCanoness`) — le nombre de coups de la PRÉDICTION est
    CONDITIONNEL au trait de la cible (#945).

    `IdunBattle.AI.Playbook.Loki.BrazierOfHolyFirePlaybook$$MakeDamagePredictions` n'appelle PAS
    `AActiveAbility$$GetHits` : il construit une FORMULE et l'évalue sur la cible —

        damage = <BrazierOfHolyFireAbility>$$GetDamageAmountMain(abilityState)   # corps dédupliqué
                                                                # `StranglethornCannonAbility$$...`
                                                                # -> `AActiveAbility$$MinMaxDamageAverage`
        sel    = DSLSelectors.Entity(target)
        hits   = BrazierOfHolyFireAbility.GetNumberOfHits(sel)
        n      = hits.Calculate(AbilityEntities(caster: caster, actor: caster, target: target,
                                                owner: caster, ...))            # IAmountFormula slot 1
        prof   = <BrazierOfHolyFireAbility>$$GetDamageProfileType()             # corps dédupliqué
                                                                # `BaseFleshmetalGunsEffect$$...`
        return GenerateMultiHitAttackPredictions(caster, casterPosition, target, Target@+0x60,
                                                 damage, n, prof, Nullable(null), 0)

    et `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetNumberOfHits` :

        nrOfHits   = AbilityConfiguration.GetNumberConstant(config, 0x2f)
        nrOfHits_2 = AbilityConfiguration.GetNumberConstant(config, 0x32)
        return DSLFormulas.ConditionalAmount(DSLTriggers.HasTrait(target, 0x3fb = UnitTrait.Daemon),
                                             nrOfHits_2, nrOfHits)

    `ConditionalAmount(cond, ifTrue, ifFalse)` — ordre LU (même forme que
    `...IncursionAbility$$GetNextSpawnTile`, `ConditionalAmount(<cond>, 1, 0)`). Config `rnca9r7q6c` :
    `nrOfHits = 2`, `nrOfHits_2 = 4` → **4 coups contre un Daemon, 2 sinon**.

    ⚠ DEUX écarts avec le chemin générique, et ils vont dans le même sens :
      * le générique (`AActiveAbility.get_special_hits`) lit `nrOfHits` puis passe par
        `GetDefaultAttackHits(base, ExtraHits, ExtraHitsMelee, is_melee)` — le playbook natif, lui,
        passe le résultat BRUT de la formule : **aucun `ExtraHits`** ne s'y ajoute ;
      * il ignorait la branche `Daemon` : contre un démon le port prédisait **la moitié** des coups.

    La base, elle, est déjà juste : 1041 figure dans `_A_VIA_GET_DAMAGE_AMOUNT_MAIN` (#344), donc
    `get_damage()` rend déjà la moyenne demi-vers-le-pair.

    Le trait est lu sur l'ENTITÉ cible (`_entity_traits`), jamais sur le kit par visualId — même
    substrat et même raison que `HellfireShells` (#267-r1)."""
    #: `GetNumberConstant(config, 0x2f)` / `(config, 0x32)` — les clés gameconfig homonymes.
    _CONST_HITS = "nrOfHits"          # AbilityConstantType 0x2f = 47
    _CONST_HITS_2 = "nrOfHits_2"      # AbilityConstantType 0x32 = 50
    #: `DSLTriggers.HasTrait(target, 0x3fb)` — nom LU dans `frida/enums.tsv` (`1019=Daemon`).
    _TRAIT = UnitTrait.Daemon.name    # 0x3fb = 1019

    def get_number_of_hits(self, target_traits) -> int:
        """`BrazierOfHolyFireAbility$$GetNumberOfHits(Entity(target)).Calculate(entities)`.

        `target_traits` = les traits de l'ENTITÉ cible. Constante absente de la config -> 0, ce que
        l'appelant traite comme « pas d'override » (le natif, lui, lèverait)."""
        c = (self.config.constants or {}) if self.config is not None else {}
        hits = int(c.get(self._CONST_HITS) or 0)
        if self._TRAIT in (target_traits or ()):
            hits = int(c.get(self._CONST_HITS_2) or 0) or hits
        return hits


class TacticalPrecisionAbility(AActiveAbility):
    """`TacticalPrecision` (1154, `ultraTitus` << Titus >>) — le volet SÉLECTEUR de sa prédiction (#976).

    `IdunBattle.AI.Playbook.Loki.TacticalPrecisionPlaybook$$MakeDamagePredictions` a **DEUX
    BRANCHES EXCLUSIVES**, et c'est la seule ability du port dont le sélecteur ET les trois entrées
    (base / hits / profil) basculent ensemble :

        mainTile = casterPosition.get_MainTile()
        if (battleQuery.<slot 0xcd>(caster, mainTile, target))        // WillBeCharging
            base   = VigilanceEternalAbility$$GetDamage(state)        // = MinMaxDamage(minDmg, maxDmg)
            hits   = AActiveAbility$$GetHits()                        // nrOfHits
            prof   = TacticalPrecisionAbility$$GetChargingAttackDamageProfile()
                     = AActiveAbility$$GetDamageProfile()             // damageProfile
            sel    = <DSLSelectors+0x60> = Target                     // MONO-CIBLE
        else
            base   = TacticalPrecisionAbility$$GetNonChargingAttackDamage(state)
                     = AActiveAbility$$MinMaxDamage2(state)           // minDmg_2 / maxDmg_2
            hits   = TacticalPrecisionAbility$$GetNonChargingAttackHits()
                     = AActiveAbility$$GetHits2() = GetNumberConstant(0x32 = nrOfHits_2)
            prof   = TacticalPrecisionAbility$$GetNonChargingAttackDamageProfile()
                     = AActiveAbility$$GetDamageProfile2()            // damageProfile_2
            sel    = TacticalPrecisionAbility$$GetNonChargingAttackTargets()
                     = DSLSelectors$$AdjacentEnemies(Caster@+0x48, unique: 1, selectionType: 3)
        return GenerateMultiHitAttackPredictions(caster, casterPosition, target, sel, base, hits,
                                                 Nullable(prof), <poids vide>, 0)

    C'est le MÊME découpage que la face COMBAT (`runner/abilities/ultramarines.py` : « If(IsCharging
    (caster, cible), 1x Bolter FORCE-CRIT sur la cible, 3x Chain sur TOUS les AdjacentEnemies
    (caster)) », branches EXCLUSIVES) — la face DÉCISION prédit donc exactement ce que la face
    COMBAT exécutera.

    ⚠ **`WillBeCharging` n'est PAS `IsCharging`**, et les confondre est le piège central de ce port.
    `IsCharging(caster, target)` lit `UnitComponent.ChargedUnitIds`, c'est-à-dire un pas DÉJÀ JOUÉ ;
    le playbook, lui, score une position CANDIDATE que le caster n'a pas prise — il ne peut donc
    interroger qu'un prédicat PROSPECTIF. Le slot `0xcd` est LU dans
    `data/symbols/<build>/metadata/interface_slots.tsv` (`IBattleQuery 205 WillBeCharging 3`), et
    son arité **3** est ce qui le distingue d'`IsCharging` (slot 0xcc-, arité 2) au call-site.
    Foyer : `battle_query.will_be_charging`, qui délègue à `newly_adjacent_ids` — le corps
    d'`IdunBattle.Operations.MoveUnitOperation$$UpdateCharging`, déjà partagé avec la face COMBAT.

    ⚠ Les DEUX branches sont `_MAKE_DMG_SELECTOR_ONLY` : le natif n'émet **aucun** event `<Target>`
    séparé — il passe UN sélecteur à `GenerateMultiHitAttackPredictions`, qui boucle dessus. En
    branche CHARGING ce sélecteur EST `Target`, donc la liste rendue ici vaut `[target]` et le
    résultat coïncide avec un batch principal ; en branche NON-CHARGING la cible demandée n'a
    d'event **que si** elle est adjacente au caster. Émettre un event `<Target>` en plus aurait
    doublé la cible dans la première branche et l'aurait inventée dans la seconde.

    La BRANCHE est mémorisée sur l'instance (`tp_will_be_charging`) et relue par
    `playbook.prediction.abilities._tactical_precision_inputs` : `make_damage_predictions` appelle
    `get_aoe_targets` AVANT le handler d'entrées, donc l'ordre garantit **un seul** calcul du
    prédicat sur **un seul** substrat. Le recalculer côté handler ferait deux lectures qui peuvent
    diverger — exactement ce que « décomposer par étage » interdit."""

    #: `DSLSelectors$$AdjacentEnemies(Caster, unique: 1, selectionType: 3)`. Le 3e argument du
    #: call-site est l'immédiat `1` (et non une entité) : c'est donc la surcharge **A**
    #: `(this, unit, unique, selectionType)`, celle qui propage le littéral aux deux étages — le
    #: discriminant est la cible du `call`, pas le pseudo-C (#585-r3). `3` est nommé.
    _AOE_NON_CHARGING = dsl.AdjacentEnemies(
        dsl.Caster(), selection_type=int(_UnitSelectionType.OnlyAliveAndTargetable))

    @staticmethod
    def _neigh_two_tiles(board, positions) -> dict | None:
        """`{pos: [voisins]}` restreint aux SEULES tuiles que `newly_adjacent_ids` interroge (la
        position courante et la position candidate) — le substrat NATIF d'adjacence.

        `Board.neighbours_connectivity` EST la liste stockée du `ConnectivityComponent`, celle
        qu'énumère `TileQuery.<IterateAdjacentTiles>d__8`. TRI-ÉTAT : board absent, sans
        connectivité, ou tuile inconnue -> `None`, ce qui fait retomber `is_adjacent` sur son repli
        GÉOMÉTRIQUE **nommé** (couronne hex, écart strictement permissif de 4 à 38 arêtes selon le
        board, cf. #433-r4-r1-r4-r2). Jamais `{}`, qui se lirait « aucune tuile n'a de voisin »."""
        if board is None:
            return None
        out = {}
        for p in positions:
            if p is None:
                continue
            tid = board.id_at(p[0], p[1])
            if tid is None:
                return None
            nb = board.neighbours_connectivity(tid)
            if nb is None:
                return None
            out[(p[0], p[1])] = [board.coord(n) for n in nb if board.coord(n) is not None]
        return out or None

    def get_aoe_targets(self, ctx):
        """Le sélecteur UNIQUE que le playbook passe à `GenerateMultiHitAttackPredictions`, branche
        comprise. Rend `[target]` en CHARGING (`DSLSelectors+0x60`), les `AdjacentEnemies(Caster)`
        sinon.

        Le prédicat est évalué sur la position CANDIDATE (`ctx.caster_pos`, le sweep de tuiles du
        générateur d'action) contre la position COURANTE du caster — c'est littéralement
        `WillBeCharging(caster, casterPosition.MainTile, target)`.

        Canal muet (pas de position de caster ou de cible publiée) -> branche NON-CHARGING. C'est
        la dégradation du natif lui-même : sans nouveau contact, `newly` est vide et le prédicat
        est FAUX ; on ne suppose jamais une charge."""
        caster = ctx.caster or {}
        target = ctx.target
        cp = (caster.get("pos") or {}) if isinstance(caster.get("pos"), dict) else {}
        cur = (cp.get("col"), cp.get("row")) if cp.get("col") is not None else None
        frm = getattr(ctx, "caster_pos", None) or cur
        tid = (target or {}).get("id")
        pos_by_id = {}
        for u in (ctx.units or []):
            if u.get("id") is None or u.get("id") == caster.get("id"):
                continue                       # le natif exclut l'unité qui bouge (paramètre `unit`)
            p = u.get("pos") or {}
            if p.get("col") is not None:
                pos_by_id[int(u["id"])] = (p["col"], p["row"])
        neigh = self._neigh_two_tiles(getattr(ctx, "board", None), (cur, frm))
        charging = _bq.will_be_charging(tid, cur, frm, pos_by_id,
                                        getattr(ctx, "elev_by_pos", None), neigh)
        self.tp_will_be_charging = bool(charging)
        if charging:
            return [target] if target is not None else []
        return self._AOE_NON_CHARGING.evaluate(ctx)


_SPECIAL_ABILITY_CLASSES: dict[str, type[AActiveAbility]] = {
    "DaemonicOrdnance": DaemonicOrdnanceAbility,
    "BrazierOfHolyFire": BrazierOfHolyFireAbility,   # #945 — hits conditionnels au trait Daemon
    "HadesAutocannons": HadesAutocannonsAbility,
    "HarvesterOfSouls": HarvesterOfSoulsAbility,
    "BloodyFury": BloodyFuryAbility,
    "PlasmaCannon": PlasmaCannonAbility,
    "DakkaDakkaDakka": DakkaDakkaDakkaAbility,
    "MurderousSwing": MurderousSwingAbility,
    "Executioner": ExecutionerAbility,
    "MultiThreatEliminator": MultiThreatEliminatorAbility,
    "FrenziedFiring": FrenziedFiringAbility,
    "SavageEchoes": SavageEchoesAbility,
    "MassDriverAccelerator": MassDriverAcceleratorAbility,
    "FragBomb": FragBombAbility,                     # #957 — volet SPLASH (`GetAdjacentTargets`)
    "TacticalPrecision": TacticalPrecisionAbility,   # #976 — sélecteur à DEUX branches (WillBeCharging)
}


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Comparable vs NonComparable — mirror du dispatch natif `<Ability>Playbook : ComparablePlaybook |
# NonComparablePlaybook`. Un playbook COMPARABLE possède `MakeDamagePredictions` et l'IA score l'ability
# par une PRÉDICTION DE DÉGÂT par cible (attaques : normal, PlasmaCannon, HarvesterOfSouls…). Un playbook
# NONComparable n'a PAS `MakeDamagePredictions` : `EvaluateNonComparable` produit une utilité HEURISTIQUE
# (compte d'ennemis touchés / stat de cible), et le natif N'ÉMET AUCUN ProbableDamageEvent (decisionView
# dMin/dMax = None). L'engine doit donc EXCLURE ces abilities du chemin de prédiction de dégât (il
# fabriquait un dégât depuis leur `minDmg/maxDmg` gameconfig → sur-évaluation, cf. RadBombardment step15).
# ⚠ Le DÉGÂT réel À L'EXÉCUTION de ces abilities reste correct (runner engine) ; ce flag ne concerne QUE
# l'utilité de DÉCISION de l'IA. Chaque entrée = base de playbook RE'd + VA.
# ─────────────────────────────────────────────────────────────────────────────────────────────
_NONCOMPARABLE_ABILITIES: "frozenset[str]" = frozenset({
    "RadBombardment",    # RadBombardmentPlaybook : NonComparablePlaybook IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook$$.ctor ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook$$EvaluateNonComparable = (#ennemis dans GetAffectedTiles),
                         # compte NU. ⚠ Le « x 2 » qui figurait ici jusqu'a #975 etait FAUX : le corps ne
                         # porte NI `op_Multiply` NI `op_Addition`, seulement `Fix64.op_Implicit(count)`.
                         # Le `2` reel est le `MIN_UTILITY` du `.cctor` (`Fix64.op_Implicit(2)`), donc un
                         # PLANCHER de proposition, pas un facteur. Face DECISION portee :
                         # `engine/playbook/noncomparable/rad_bombardment.py`.
    "BloodyFury",        # BloodyFuryPlaybook : NonComparablePlaybook IdunBattle.AI.Playbook.Loki.BloodyFuryPlaybook$$.ctor ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.BloodyFuryPlaybook$$EvaluateNonComparable = 1 + (#ennemis adjacents) x W (heuristique de compte AoE)
    "VexillaMagnifica",  # VexillaMagnificaPlaybook : IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$EvaluateNonComparable = allié GetStat(5),
                         # skip si HasEffect(0x48a) (buff d'allié, pas du dégât)
    "MindControl",       # MindControlPlaybook : la chaine de parents LUE dans `classes.tsv` est
                         # `MindControlPlaybook -> NonComparablePlaybook`1 -> Playbook`1 ->
                         # BasePlaybook` (le ctor gshared est mislabele `ComparablePlaybook<...>`
                         # par ghidra). IdunBattle.AI.Playbook.Loki.MindControlPlaybook$$EvaluateNonComparable = `Fix64(GetStat(cible, 5 = HEALTH))`,
                         # MIN_UTILITY = 1 (cctor) -- patron IDENTIQUE a VexillaMagnifica. AUCUN
                         # `Make*Predictions` : le gameconfig de 1164 n'a d'ailleurs ni `minDmg` ni
                         # `maxDmg` (seulement `dmgReduction` / `extraDmgPct`), donc le chemin de
                         # prediction de degat n'avait rien a fabriquer -- l'entree est ici pour
                         # que le DISPATCH soit juste, pas pour corriger un chiffre. (#552)
    "FightingRetreat",   # FightingRetreatPlaybook : NonComparablePlaybook ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.FightingRetreatPlaybook$$EvaluateNonComparable = |ennemis adj| + |alliés adj - self| (self-debuff d'ennemis,
                         # pas de dégât — inerte ici de toute façon : pas de minDmg/maxDmg)
    "RitesOfRestoration",  # RitesOfRestorationPlaybook : NonComparablePlaybook IdunBattle.AI.Playbook.Loki.RitesOfRestorationPlaybook$$EvaluateNonComparable (soin AoE +
                         # résurrection, id 1039) ; utilité = 1 + Count(healTargets), résurrection-gated.
                         # PAS de prédiction de dégât (porté dans engine.playbook.noncomparable).
    "GauntletsOfUltramar",  # GauntletsOfUltramarPlaybook : NonComparablePlaybook ; EvaluateNonComparable
                         # IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$EvaluateNonComparable = Min(base, #ennemis dans l'arc GetAllTargetsSelector→SelectUniqueUnits(3)),
                         # heuristique de COMPTE — AUCUN CalculateUtilityFromDamageEvent, AUCUN ProbableDamageEvent.
                         # (#109 : le port fabriquait un dégât depuis minDmg/maxDmg → faux positif vs oracle null.)
    "HammerOfWrath",     # HammerOfWrathPlaybook : NonComparablePlaybook ; IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable ;
                         # IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$ShouldEvaluate = !EnemyWillBeKilledWithNormalAttack. L'utilité de DÉCISION
                         # utilise le dégât EN INTERNE (Σ CalculateUtilityFromDamageEvent(GetMinDamage/Profile/Hits)
                         # cible+adjacents + HasTrait(0x3eb)→+100 + CanAddUnit→+5), MAIS le playbook reste
                         # NonComparable → N'ÉMET AUCUN ProbableDamageEvent (MakeDamagePredictions=null, oracle
                         # disp=[0,0]). Le port doit donc EXCLURE l'event de dégât affiché (#109). ⚠ Une utilité de
                         # décision fidèle (NC) reste à porter dans engine.playbook.noncomparable si besoin décision.
    # --- #44 (reframe #34) : les 5 playbooks NC du « lead 8 ». MESURE LIVE (probe #34, aiPlaybookPredict) :
    # MakeDamagePredictions / MakeHealPredictions / MakeEffectPredictions rendent TOUS `null` pour ces
    # abilities -> AUCUN ProbableDamageEvent affiché, exactement comme Gauntlets/Hammer (#109). Leur
    # utilité de DÉCISION vit dans engine.playbook.noncomparable (comptages, ou dégât INTERNE via
    # `generate_multi_hit_attack_prediction` appelé directement pour 1202 / l'attaque normale pour 1163).
    "Stormcaller",       # StormcallerPlaybook IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$EvaluateNonComparable ; utilité = #unités dans la zone de glace
    "ItItches",          # ItItchesPlaybook IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$EvaluateNonComparable ; utilité = #ennemis poussés
    "TheQuickening",     # TheQuickeningPlaybook IdunBattle.AI.Playbook.Loki.TheQuickeningPlaybook$$EvaluateNonComparable ; utilité = paliers +1 (cible = TUILE)
    "BlackRage",         # BlackRagePlaybook IdunBattle.AI.Playbook.Loki.BlackRagePlaybook$$EvaluateNonComparable ; utilité = dégât de l'attaque NORMALE (interne)
    "VigilanceEternal",  # VigilanceEternalPlaybook IdunBattle.AI.Playbook.Loki.VigilanceEternalPlaybook$$EvaluateNonComparable ; utilité = dégât de l'ability (interne)
    # --- #56 (tranche 3b) : 2 summons NonComparable (EvaluateNonComparable, PAS de Make*Predictions).
    "SendInTheNextWave",  # SendInTheNextWavePlaybook IdunBattle.AI.Playbook.Loki.SendInTheNextWavePlaybook$$EvaluateNonComparable ; util=Attack(cible), MIN=max Attack ennemis
    "Incursion",          # IncursionPlaybook IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$EvaluateNonComparable ; util=PV(cible), MIN=max PV, gate adj>=2 tuiles
    # --- #945 : les QUATRE playbooks `NonComparable` du lot Loki. Base LUE dans
    # `data/symbols/<build>/frida/classes.tsv` (`NonComparablePlaybook`1` pour les quatre), et
    # AUCUN `Make*Predictions` -- `frida/methods.tsv` ne leur declare que `..ctor` (+ `.cctor` pour
    # AlphaWarrior) et `EvaluateNonComparable`. Le natif n'emet donc AUCUN `ProbableDamageEvent`
    # pour elles, la ou le port fabriquait un degat depuis leur `minDmg`/`maxDmg` gameconfig.
    "AdaptiveStrategy",   # 1005 IdunBattle.AI.Playbook.Loki.AdaptiveStrategyPlaybook$$EvaluateNonComparable ; util = #allies non-heros adjacents a la cible
    "StormOfWrath",       # 1019 IdunBattle.AI.Playbook.Loki.StormOfWrathPlaybook$$EvaluateNonComparable ; util = |GetChainedUnits(cible, onlyFriends)|
    "CalibaniteGreatsword",  # 1189 IdunBattle.AI.Playbook.Loki.CalibaniteGreatswordPlaybook$$EvaluateNonComparable ; TOGGLE, util constante Fix64(int.MaxValue)
    "AlphaWarrior",       # 1112 IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$EvaluateNonComparable ; util booleenne (le gameconfig de 1112
                          # n'a d'ailleurs ni `minDmg` ni `maxDmg` : l'entree est ici pour que le
                          # DISPATCH soit juste, pas pour corriger un chiffre -- comme MindControl)
    # --- #957 : les TROIS playbooks `NonComparable` du lot. Base LUE dans `frida/classes.tsv`
    # (`NonComparablePlaybook`1` pour les trois) ; recensement des corps fait AU BLOC d'adresses de
    # `ghidra/functions.tsv` -- trois corps CONTIGUS chacune (`EvaluateNonComparable`, `.cctor`,
    # `.ctor`), AUCUN `Make*Predictions`. Le natif n'emet donc AUCUN `ProbableDamageEvent` pour
    # elles ; sans ces entrees le port en fabriquerait un depuis leur `minDmg`/`maxDmg` gameconfig.
    "ExemplarOfHate",     # 1140 IdunBattle.AI.Playbook.Loki.ExemplarOfHatePlaybook$$EvaluateNonComparable ; util = 1 + PV%/100 + 2*(non-Infiltrate) + 1*(Chaos)
    "FearOfTheUnseen",    # 1115 IdunBattle.AI.Playbook.Loki.FearOfTheUnseenPlaybook$$EvaluateNonComparable ; VETO, util constante Fix64(10) sur SOI
    # --- #976 : `TitanhammerSquadPlaybook` a pour base `NonComparablePlaybook`1` — LUE dans
    # `data/symbols/<build>/frida/classes.tsv`, PAS deduite du `.ctor` (qui NOMME
    # `ComparablePlaybook<...>$$.ctor`, corps trivial DEDUPLIQUE : le piege de #487-r1 / #945 /
    # #957, verifie 5/5 sur le lot). Le natif n'a AUCUN `Make*Predictions`, donc n'emet AUCUN
    # `ProbableDamageEvent` pour 1231.
    # ⚠ CE QUE CETTE ENTREE CORRIGE EST LE **DISPATCH**, PAS UN CHIFFRE -- mesure, pas supposition :
    # le gameconfig de 1231 n'a NI `minDmg` NI `maxDmg` (constants = `initialCooldownTurns`,
    # `range` ; variables = `blockDmg`, `hpToHeal`), donc `ab.get_damage()` rendait deja **0**. Meme
    # situation exactement que `MindControl` (1164) et `AlphaWarrior` (1112) ci-dessus, et
    # l'affirmation « le port fabriquait un degat » aurait ete FAUSSE ici. Ce que l'entree ferme,
    # c'est la route : sans elle, `makes_damage_predictions` rendait `True` et 1231 restait sur le
    # chemin COMPARABLE, donc sa face DECISION ne pouvait pas etre son `EvaluateNonComparable`.
    "TitanhammerSquad",   # 1231 IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$EvaluateNonComparable ;
                          # util = |ennemis DISTINCTS du caster adjacents a la couronne de la TUILE
                          # visee| (`GetAdjacentTiles` slot 0x4f o `GetAdjacentEnemies` slot 0x7f,
                          # dedoublonnes par un `PooledHashSet`) ; MIN_UTILITY = 1 (`.cctor`).
    "Foehammer",          # 1097 IdunBattle.AI.Playbook.Loki.FoehammerPlaybook$$EvaluateNonComparable ; util = |unites mortes du plateau| (CONSTANTE)
                          # ⚠ 1097 EST une attaque (son `ExecuteBehaviour` fait bien un
                          # `AttackWithAttackDamage`) : c'est le PLAYBOOK qui est NonComparable, donc
                          # la DECISION n'est PAS un score de degat -- exactement le cas de 1163
                          # `BlackRage` / 1202 `VigilanceEternal` ci-dessus.
    # --- #974 : meme forme, et le meme piege. `1198 EuphoricStrikes` PORTE une config de degat
    # (`minDmg`/`maxDmg`/`damageProfile: Power`/`nrOfHits: 1`), mais son playbook est
    # `NonComparablePlaybook`1` (base LUE dans `frida/classes.tsv`) et son
    # `EvaluateNonComparable` score par `GetStat(cible, 5 = Health)` -- il ne construit AUCUNE
    # prediction d'ability. Sans cette entree, le port fabriquerait un `ProbableDamageEvent`
    # depuis `minDmg`/`maxDmg` que le natif n'emet jamais.
    "EuphoricStrikes",    # 1198 IdunBattle.AI.Playbook.Loki.EuphoricStrikesPlaybook$$EvaluateNonComparable
                          # ; util = PV courants de la cible, VETO `WillNormalAttackKill`
    # --- #979 : base `NonComparablePlaybook`1` LUE dans `frida/classes.tsv` (le `.ctor` NOMME
    # `ComparablePlaybook<...>` -- corps trivial deduplique, meme piege verifie 5/5 par #976). Le
    # gameconfig de 1188 PORTE `minDmg`/`maxDmg`/`damageProfile: Blast`/`nrOfHits: 1` (c'est la
    # PHASE 2, le barrage differe), donc sans cette entree `makes_damage_predictions` rendait True
    # et le port FABRIQUAIT un `ProbableDamageEvent` que le natif n'emet jamais : son playbook n'a
    # AUCUN `Make*Predictions`, il COMPTE des occupants.
    "DevastatingRefrain",  # 1188 IdunBattle.AI.Playbook.Loki.DevastatingRefrainPlaybook$$EvaluateNonComparable
                           # ; util = 1 + #ennemis occupant la forme ancree sur la tuile visee
})


def makes_damage_predictions(ability_name: str | None) -> bool:
    """L'IA score-t-elle cette ability par une PRÉDICTION DE DÉGÂT par cible (playbook Comparable,
    `MakeDamagePredictions`) ou par une utilité HEURISTIQUE (playbook NonComparable) ? Mirror du dispatch
    natif `<Ability>Playbook : ComparablePlaybook | NonComparablePlaybook`. Défaut = True (Comparable = cas
    commun des attaques) ; False = NonComparable RE'd (cf. `_NONCOMPARABLE_ABILITIES`)."""
    return (ability_name or "") not in _NONCOMPARABLE_ABILITIES


def active_ability_for(ability_name: str | None, ability_type: int, caster: UnitContext,
                       config: AbilityConfiguration | None,
                       ability_state: dict | None = None) -> AActiveAbility:
    """Fabrique l'`AActiveAbility` de la bonne sous-classe (formule de coups PROPRE si portée, sinon
    base générique). Mirror du dispatch natif `ActiveAbilityType → classe d'ability`.
    `ability_state` = AbilityState PER-ABILITY {level, multiplier} (capteur #100) — comme le natif
    construit chaque ability avec SON niveau."""
    klass = _SPECIAL_ABILITY_CLASSES.get(ability_name or "", AActiveAbility)
    return klass(ability_type, caster, config, ability_state=ability_state)
