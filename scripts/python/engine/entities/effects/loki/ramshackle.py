"""`Ramshackle_DmgReduction` (`EffectType` 0x442 = 1090) -- le passif du Grot Tank, residu #570-r1.

CE QUE SON ABSENCE COUTAIT, ET POURQUOI PERSONNE NE LE VOYAIT
==============================================================
#570 a porte l'ability `1057 GrotTank` (spawn, PV `summonHp + RoundsStarted x extraHp`, armes,
traits, playbook) et a NOMME ce trou : le summon `orksGrotTank` arrivait avec ses stats justes,
ses quatre traits et ses deux armes -- **et sans sa reduction de degat**. L'ecart est PERMISSIF
(le tank encaisse plus qu'il ne devrait, donc il meurt plus vite) et **silencieux** : aucune
erreur, aucun crash, et aucun test ne pouvait le voir, puisque « le tank meurt » est un resultat
plausible.

i2 : « Takes -`dmgReduction` damage from attacks with damage types that have `pierceRatio` %
pierce ratio or lower. »

L'ARTEFACT, LU EN ENTIER (build `rnca9r7q6c`)
=============================================
`data/symbols/<build>/frida/classes.tsv` donne le parent
`IdunBattle.Entities.Effects.DamageModifierAbilityEffect`, et `methods.tsv` ne connait a cette
classe que `.ctor` et `CreateDamageModifier` -- donc UN SEUL canal, aucune `CreateActiveCondition`,
aucun `GetCalculateLevel`.

`IdunBattle.Entities.Effects.Loki.Ramshackle_DmgReductionEffect$$CreateDamageModifier`, mirror
noeud par noeud :

    v            = DSLFormulas.ConfigVar( 0x12 = dmgReduction, GetAbilityState(effet),
                                          <config@effet+0x60> )
    pierceConst  = DSLFormulas.ConfigConst( 0x49 = pierceRatio, <config@effet+0x60> )
    attackPierce = DSLFormulas.AttackPiercingRatio()
    trigger      = DSLTriggers.get_OwnerIsTarget
                   op_BitwiseAnd
                   DSLTriggers.AmountIsEqualOrGreater( pierceConst, attackPierce )
    return         EffectBonus.ForAddition( trigger, DSLFormulas.Multiply(v, <DSLFormulas+0x38>) )

`<DSLFormulas+0x38>` = `Direct(-1)` (`DSLFormulas$$.ctor` ecrit `+0x18 <- Direct(0)`,
`+0x20 <- Direct(1)`, `+0x28 <- Direct(2)`, `+0x30 <- Direct(100)`, `+0x38 <- Direct(-1)`) =>
`-dmgReduction` PLAT. Jumeau exact de forme : `HolyDuel_DmgReductionEffect` et
`PsychicFortress_DmgReductionEffect` (meme parent, meme unique canal, meme
`Multiply(ConfigVar(0x12), MinusOne)`).

LE PLACEMENT -- **MESURE (#570-r5), PRE-PERCAGE**
=================================================
Le mirror place la reduction en PRE-percage (`for_subtraction` -> `flat_reductions` ->
`mods.additive`, consomme AVANT
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`,
famille `Nightshroud` #120 / `PsychicFortress`). Ce n'est plus un choix de famille : c'est ce que
le natif fait, mesure **par coup** contre le modele concurrent.

    (`probe_570r1_ramshackle.py`, board `MC1_67`/777, tank a 3193 d'armure, niveau 50 x 180 %
     => `R = dmgReduction[50] x 1,8 = 499`)

    profil            ancre `nu`      modele PRE      modele POST     NATIF (par coup)
    `Physical` (1 %)  [18]            [13]            [0]             [13]   -> PRE
    `Energy`  (30 %)  [750, 841]      [568, 534]      [251, 342]      [568, 534] -> PRE
    `Gauss`   (60 %)  --              --              --              6862 == 6862 (temoin NEG.)

L'ancre `nu` est le MEME coup rejoue avec ce canal RENDU MUET : sans elle, « port == natif » ne
dirait pas si le placement a ete confronte ou s'il est inobservable. Le modele POST est
`max(0, nu - R)`. Les deux modeles DIFFERENT sur ce regime, et c'est ce qui autorise a conclure.

⚠ **LE REGIME EST LOAD-BEARING, ET IL Y A UN REGIME DEGENERE JUSTE A COTE.**
`GetDamageWithPiercing` = `max(0, d - armure, d x percage/100)`. Des que la branche SOUSTRACTIVE
gagne (degat brut > armure), l'etage percage est l'IDENTITE sur l'axe additif : PRE et POST rendent
alors EXACTEMENT le meme nombre et l'accord ne prouve RIEN. La mesure ci-dessus tient parce que le
tank a 3193 d'armure pour des degats bruts inferieurs, donc la branche PERCAGE l'emporte. Garde
executable : `test_570r5_ordre_de_seeding_offline.py` etages 7 et 7b.

⚠ **ET LA « DIVERGENCE DE FAMILLE » ECRITE ICI AVANT #570-r5 N'EN ETAIT PLUS UNE.** Elle opposait
`HolyDuel` (`for_addition(False, -v)`, dit POST-percage) a `PsychicFortress` (`for_subtraction`,
PRE-percage). Depuis #462-r4b-r1, l'`Addition@+0x10` du DEFENSEUR est versee dans le MEME
accumulateur pre-percage que `flat_reductions`
(`AttackDamageOperation._apply_defender_flat_reductions`) : les deux ecritures rendent le meme
nombre, il n'y avait donc aucune fourche cote port. Ce que la mesure tranche est le placement
NATIF, contre un modele POST construit a la main. Garde : meme fichier, etage 8.

LES DEUX ETAGES DE SUBSTRAT, ET ILS SONT LEVES
===============================================
La cause n'etait PAS « `combatSnapshot` ne publie pas l'entite NPC fraichement spawnee » (elle la
publie : le probe la lit) :

  ETAGE 1 -- L'UNITE (#570-r3). `combatSnapshot.unitConfig` rend `{"error": "config null"}` pour
  toute unite INVOQUEE (elle n'a aucune `UnitConfiguration`), donc son `passive_ability_level`
  restait `0` / son multiplicateur `100`. Le canal qui porte l'information est `unitAbilityStates`,
  que `snapshot._load_passive_abilities` sait consommer -- mais que le HARNAIS des probes ne
  collectait pas. **LEVE** : le CTX du tank passe de `(0, 100)` a `(50, 180)`. S'y ajoute, cote
  spawn PORTE, le defaut de `build_summon_context` remis a `abilitiesLevel ?? abilityState.level`
  (LU dans `SpawnUnitOptions$$WithStatsFromConfig`).

  ETAGE 2 -- L'INSTANCE D'EFFET (#570-r5). Elle portait `ability_level = None` / `mult = 100` :
  `load_state` materialisait les effets AVANT de consommer le canal, donc a la naissance de l'effet
  le CTX de son owner portait encore `0`/`100`. Or le natif BAKE l'`AbilityStateReference` du
  poseur dans l'entite-effet (`AddEffectBehaviour$$DefaultEffectBuilder`) : l'etat doit EXISTER
  avant l'effet. **LEVE** -- la resolution du canal est hissee avant `_load_stats_and_effects` et
  comble `abstate_by_id` (`snapshot._ability_state_with_channel`, meme garde que le seed d'aval).
  MESURE : l'instance passe de `(None, 100)` a `(50, 180)`, soit `dmgReduction[1] = 5` ->
  `dmgReduction[50] x 180 % = 499`.

CE QUI EST CONFRONTE, ET CE QUI NE L'EST PAS :
  * le GATE, face NEGATIVE : `Gauss` (60 % > 30) rend **6862 == 6862** -- un port qui appliquerait
    la reduction partout echouerait ici ;
  * le CABLAGE : l'instance d'effet du port existe sur la cible et son canal repond (le probe
    l'imprime), donc « le port ne reduit rien » est elimine ;
  * la POSE au spawn : le tank du PORT porte 1090 (etage [2]) ;
  * la MAGNITUDE : **CONFRONTEE** par coup sur deux profils (13 et [568, 534]) ;
  * le PLACEMENT : **CONFRONTE**, PRE-percage.
  * NON couvert : un porteur de `Ramshackle` autre que `orksGrotTank` (il n'y en a pas), et le
    regime `damage_profile` INCONNU du gameconfig (tri-etat `None`, jamais rencontre live).

LE SENS DE LA COMPARAISON, ET IL EST LU
========================================
`IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` se termine
litteralement par `return (int)<slot +0x20> <= <slot +0x10|+0x18>` -- donc
`AmountIsEqualOrGreater(amount, minAmount)` = `amount >= minAmount`. Au call-site, `amount` est
`ConfigConst(pierceRatio)` et `minAmount` est `AttackPiercingRatio()` : le gate est
**`pierceRatio >= <percage de l'attaque>`**, c'est-a-dire « les profils a percage FAIBLE », ce que
l'i2 dit par « `pierceRatio` % pierce ratio **or lower** ». L'inverser rendrait l'effet actif
exactement sur les profils qu'il ne protege pas.

`IdunBattle.Entities.Formulas.AttackPiercingRatioFormula$$Calculate` : lit
`AbilityEntities+0xbc` (`Nullable<DamageProfileType>`), **rend 0 si le Nullable est VIDE**, sinon
resout le profil par `IBattleQuery.<slot 0xac>` et rend son champ `+0x14` = `PiercingRatio`. C'est
donc le percage NOMINAL DU PROFIL, jamais le percage effectif du coup (aucun `extraPierce` n'entre
ici).

⚠ **UN 0 NATIF FAIT PASSER LE GATE** (`30 >= 0`), et le port ne peut pas distinguer « l'attaque
n'a pas de profil » (le cas natif) de « l'appelant n'a pas threade le profil » (une limite du
port). Le port tranche donc en DEUX temps, et le dit :
  * `damage_profile` FALSY (`None` / `""`) -> mirror du Nullable VIDE -> percage **0**, gate PASSE ;
  * `damage_profile` renseigne mais INCONNU du gameconfig -> **non mesure** -> aucune contribution,
    jamais un 0 invente (un 0 ferait passer le gate a tort et sur-proteger la cible).

MAGNITUDE : `dmgReduction[ablvl]` (65 paliers, 5 -> 364), **DANS**
`variablesAffectedByRarityBonus` -> scale par le multiplicateur de rarete du porteur. Le porteur
est le SUMMON : `spawn_unit` lui pose l'effet a l'init (mirror de la boucle ABILITIES d'
`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute`) avec le niveau passif et le
multiplicateur du summon.

`0x445 = 1093` est le litteral du `.ctor`, relu A L'ASSEMBLEUR (`ba 45 04 00 00`) et non dans le
decompile : `TriggeredAbilityType 1093 = Ramshackle`. ⚠ **1093 est aussi `EffectType.HolyDuel_
DmgReduction`** -- deux enums, meme ordinal, deux choses differentes ; c'est exactement le piege
que le CLAUDE.md nomme, et la raison pour laquelle on ecrit le NOM.

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....services.effect_bonus import EffectBonus, for_subtraction

#: `TriggeredAbilityType 0x445 = 1093` -- le litteral du `.ctor`, relu a l'assembleur. C'est la
#: CONFIG que `GetAbilityState(effet)` resout, pas l'`EffectType` 1090.
_ABILITY_ID = "Ramshackle"
#: `AbilityVariableType 0x12 = 18` (`enums.tsv`, jamais recopie du decompile).
_VAR_DMG_REDUCTION = "dmgReduction"
#: `AbilityConstantType 0x49 = 73` -- la constante `pierceRatio` du kit (= 30 sur ce build).
_CONST_PIERCE_RATIO = "pierceRatio"


def _attack_piercing_ratio(damage_profile: "str | None") -> "int | None":
    """`IdunBattle.Entities.Formulas.AttackPiercingRatioFormula$$Calculate`.

    Tri-etat, et les trois branches sont celles du natif ou de son absence :
      * profil FALSY  -> le `Nullable<DamageProfileType>` natif est VIDE, le natif rend **0** ;
      * profil connu  -> `PiercingRatio` du profil (champ `+0x14` de la config resolue) ;
      * profil INCONNU du gameconfig -> `None` = non mesure (cf. l'en-tete : un 0 invente ferait
        passer le gate a tort)."""
    if not damage_profile:
        return 0                                   # Nullable VIDE -> le natif rend 0
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur d'effets.
    import gameconfig as GC
    prof = GC.damage_profile(damage_profile)
    if not prof:
        return None
    r = prof.get("PiercingRatio")
    return None if r is None else int(r)


class RamshackleDmgReductionEffect(BaseEffect):
    """`Ramshackle_DmgReduction` (0x442 = 1090) -- owner-effect PERMANENT du passif `Ramshackle`,
    pose a l'init du porteur par `RamshackleAbility` (parent `IdunBattle.Entities.Abilities.
    AOwnerEffectTriggeredAbility`, `classes.tsv`), dont `$$GetEffectType` a pour corps entier
    `return 0x442`.

    Le porteur unique du kit est le summon `orksGrotTank` (`visualId` `orksNpc3GrotTank`,
    `passiveAbilities: ["Ramshackle"]` DES DEUX COTES de la paire summon/npc)."""

    # Parent `DamageModifierAbilityEffect`, unique slot `CreateDamageModifier` -> la contribution
    # sort par le forwarder ATTAQUANT, comme `HolyDuel` / `Markerlight` / `MartialKatah_DmgReduction`,
    # MALGRE le trigger `OwnerIsTarget` (#437-r1-r1-r1).
    DEFENSE_MALUS_NATIVE_FACE = "attacker"

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None
                                               ) -> EffectBonus | None:
        """MIRROR de `...Ramshackle_DmgReductionEffect$$CreateDamageModifier`.

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `AttackPiercingRatio()` -- tri-etat, `None` = non mesure ;
          2. `ConfigConst(0x49)`     -- `pierceRatio`, relu du gameconfig (jamais 30 en dur) ;
          3. `AmountIsEqualOrGreater(pierceRatio, attackPierce)` = `pierceRatio >= attackPierce` ;
          4. `ConfigVar(0x12)`       -- `dmgReduction[niveau]`, scale par la rarete ;
          5. `Multiply(v, Direct(-1))` puis `ForAddition` -- additif NEGATIF cote defenseur.

        Le noeud `get_OwnerIsTarget` n'a pas de test explicite : ce canal EST celui du defenseur
        (l'effet vit sur la cible), meme convention que toutes les autres classes de ce canal."""
        attack_pierce = _attack_piercing_ratio(damage_profile)          # 1
        if attack_pierce is None:
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        pierce_const = ability_var(_ABILITY_ID, _CONST_PIERCE_RATIO,    # 2  ConfigConst(0x49)
                                   is_constant=True)
        if pierce_const is None:
            return None
        if int(pierce_const) < int(attack_pierce):                      # 3  AmountIsEqualOrGreater
            return None
        v = ability_var(_ABILITY_ID, _VAR_DMG_REDUCTION, lvl,           # 4  ConfigVar(0x12)
                        multiplier_pct=self.ability_variables_multiplier)
        if not v:
            return None
        # `Multiply(v, <DSLFormulas+0x38> = Direct(-1))` sous `ForAddition` -> place en PRE-percage
        # (`for_subtraction` -> `flat_reductions`, famille Nightshroud #120), comme
        # `PsychicFortress`. ⚠ MESURE (#570-r5), par coup, contre le modele POST-percage construit
        # depuis une ancre `nu` -- cf. l'en-tete, section « LE PLACEMENT », et le regime DEGENERE
        # qu'elle nomme (cible a faible armure).
        return for_subtraction(False, abs(int(v)))                      # 5
