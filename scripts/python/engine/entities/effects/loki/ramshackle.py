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

LE PLACEMENT -- PRESUME PAR LA FAMILLE, **PAS ENCORE TRANCHE PAR LA MESURE**
=============================================================================
Les deux jumeaux ci-dessus DIVERGENT sur ce point (`HolyDuel` -> `for_addition(-v)` = POST-percage ;
`PsychicFortress` -> `for_subtraction(v)` = PRE-percage, place que sa propre docstring qualifie
deja de « presumee par la famille Nightshroud »). Ce module suit `PsychicFortress`
(`for_subtraction` -> `flat_reductions`, mirror `Nightshroud` #120), et c'est un CHOIX DE FAMILLE,
pas une mesure.

POURQUOI LA MESURE NE TRANCHE PAS ENCORE, et ou elle s'arrete exactement
(`probe_570r1_ramshackle.py`, board `MC1_67`, tank a 3193 d'armure) :

    profil `Physical` (1 %)  : port 18   natif 13    -> ecart 5    <- REGIME DEGENERE
    profil `Energy`   (30 %) : port 1589 natif 1102  -> ecart 487
    profil `Gauss`    (60 %) : port 6862 natif 6862  -> **OK**, temoin NEGATIF bit-exact

Le premier ecart (5) est compatible avec les DEUX hypotheses -- `499` dilue a 1 % vaut 4,99, et une
reduction de `5` posee en post-percage vaut 5. C'est un regime ou l'accord ne prouve rien, et c'est
ce qui a d'abord fait ecrire ici une conclusion que la 2e ligne a refutee.

Le VRAI blocage est en amont : le port lit `dmgReduction[**1**] = 5` au lieu du palier reel, parce
que l'entite NPC fraichement spawnee arrive cote port avec `passive_ability_level = 0` et
`ability_variables_multiplier = 100` (MESURE). C'est le MEME trou de substrat que #570 avait deja
nomme pour son etage E3 (« `combatSnapshot` ne publie pas l'entite NPC fraichement spawnee »).
Tant que ce niveau est faux, AUCUNE comparaison de magnitude n'est concluante -- et forcer un
placement sur un ecart mesure avec la mauvaise magnitude serait exactement le fit que la doctrine
interdit. Residu ouvert, `BLOCAGE: seeding`.

CE QUI EST CONFRONTE, ET CE QUI NE L'EST PAS :
  * le GATE, face NEGATIVE : `Gauss` (60 % > 30) rend **6862 == 6862** -- un port qui appliquerait
    la reduction partout echouerait ici ;
  * le CABLAGE : l'instance d'effet du port existe sur la cible et son canal repond (le probe
    l'imprime), donc « le port ne reduit rien » est elimine ;
  * la POSE au spawn : le tank du PORT porte 1090 (etage [2]) ;
  * la MAGNITUDE et le PLACEMENT : **NON CONFRONTES**, cause ci-dessus.

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
        # `PsychicFortress`. ⚠ PRESUME PAR LA FAMILLE, PAS MESURE -- cf. l'en-tete, section
        # « LE PLACEMENT » : la mesure ne peut pas trancher tant que le niveau seede est faux.
        return for_subtraction(False, abs(int(v)))                      # 5
