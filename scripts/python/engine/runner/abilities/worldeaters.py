"""Abilities actives WorldEaters (porteurs `world*`). Module DEDIE (isolation de faction ; org native =
1 classe par ability). RE ghidra gqfc5mff6c (VAs citees). Case-220 §6.3 (docs/rl/case-220/world-eaters.md).

BloodyFury (1129, `worldTerminator` « Wrask ») -- #505, RE relue sur `rnca9r7q6c`. Detail en tete de
la section dediee, en bas de ce module.

JakhalStimms (1131, `worldJakhal` « Macer »). Namespace natif `Abilities.Active.Loki.JakhalStimmsAbility`.
`IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
    aoeSel = op_BitwiseAnd( AdjacentUnits(@0x168=caster, 1, 3),      # A : TOUTES unites adjacentes au caster
                            AdjacentFriends(@0x178=target, 1, 3) )   # B : friends-DE-LA-CIBLE (= ennemis caster) adj cible
    main   = GetAttackBehaviour(@0x178=target)                       # [MAIN] attaque sur la cible
    aoe    = GetAttackBehaviour(aoeSel)                              # [AOE]  attaque sur l'intersection
    selfLoss = ChangeStat(@0x160=caster, Position(Health=5, current), mode 3=Subtract,
                          PercentageOf(StatAmount(@0x160, Health, current), ConfigConst(hpPct=25)))
    ExecuteAtomic( op_BitwiseAnd(main, aoe), 0x2a )                 # attaques ATOMIQUES (tag 0x2a)
    Execute( selfLoss )                                             # PUIS self-loss (Execute SEPARE)

`IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$GetAttackBehaviour` = `AttackWithAttackDamage( actor@0x160, <sel>, MinMaxDamage(minDmg 0xc/
maxDmg 0xd), damageProfile = Nullable(GetDamageProfile), hits = GetHits )`. `GetHits` = `ArmoriumCherub
IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` (gshared dedup) = `GetNumberConstant(nrOfHits=0x2f)`. i2 : « Deals 4x [dmg]
Physical Damage to an adjacent enemy and all other enemies adjacent to both Macer and the target. Then Macer
loses 25% of his current Health. Using Jakhal Stimms does not end Macer's turn. » Attaque MELEE, profil
Physical (pierce 1). Config 1131 : nrOfHits=4, hpPct=25 (constantes) ; minDmg/maxDmg per-level (rarity).

- AoE (intersection) : natif `AdjacentUnits(caster) & AdjacentFriends(target)`. `AdjacentUnits(caster)` =
  TOUTES unites adjacentes au caster (les 2 equipes, self exclu via `op_Subtraction`) ; `AdjacentFriends(
  target)` = SUBJECT-RELATIF = amis DE LA CIBLE = ennemis-du-caster adjacents a la cible. Le runner
  `AdjacentFriends` filtre `team==CASTER` (PAS subject-relatif, cf. selectors.py) -> fold en
  `AdjacentEnemies(TargetTile())` (convention #122 Harvester : `AdjacentFriends(target)` natif =
  `AdjacentEnemies(TargetTile())` runner). Port = `And(AdjacentUnits(CasterTile()), AdjacentEnemies(
  TargetTile()))` = ennemis-du-caster adjacents a la fois au caster ET a la cible ; exclut le caster (self
  exclu de AdjacentUnits) et la cible (target exclue de AdjacentEnemies(TargetTile)) = « all OTHER enemies
  adjacent to both ». `_within` (via les deux selecteurs) exclut deja les cadavres (mirror natif `Units(
  tiles)` = DEBOUT = vivants).
- MAIN = `AttackWithAttackDamage(Target(), ...)` (@0x178). AOE = MEME attaque (memes bornes minDmg/maxDmg,
  memes hits, meme profil : une seule config de degat) sur `aoeSel` (`multi=True`, tri par id = ordre de
  lecture natif). `native_factory="attack"` : l'`ExecuteBehaviour`/`GetAttackBehaviour` appelle
  `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (XREF callees), PAS `AttackWithAbilityDamage` -> famille
  ATTACK (2 tirages/coup a cc=0). Multi-coups (hits=4) -> classification factory OBLIGATOIRE (tip#2) :
  "attack". Profil Physical (pierce 1). `hits=4` lu de la config (nrOfHits, chemin par defaut).
- `ExecuteAtomic(op_and(main, aoe), 0x2a)` -> `AtomicGroup(op_and(main, aoe))` (inline #201 ; tag 0x2a = id
  du groupe atomique, aucun EvaluateAbilities implicite). Ordre = main PUIS aoe (cibles aoe triees par id)
  -> meme `state.rng` -> bit-exact BY CONSTRUCTION vs une sequence directe.
- SELF-LOSS = `ChangeStat(Self, Health, Subtract, PercentageOf(current_hp, hpPct=25))` -> feuille
  `SubtractHealthPercent` (behaviours/stats.py) sur `Caster()`. Executee APRES l'`AtomicGroup` (Execute
  SEPARE du natif). Deterministe (aucun rng) : `hp = Max(hp - round_half_even(hp*25/100), 0)`. Ne decale pas
  l'ordre rng des attaques (executee apres). Le caster ne meurt PAS (pct<100). Les attaques ne touchent pas
  le caster -> il lit son HP INCHANGE (sauf overwatch, alors HP post-overwatch, fidele a l'ordre natif).
- FREE ACTION (« does not end Macer's turn ») : DEJA cable via `NO_END_TURN_ABILITY_TYPES` /
  `NO_ABILITY_USED_FLAG_ABILITY_TYPES` (base.py, 1131 present) -> le handler pose skip_end_turn/skip_used.
- Passif Skullsmasher (worldJakhal, 1217, +extraDmg x floor(PV%-manquant/10) + stun on-kill) = item SEPARE
  ([opus]+prerequis), NON porte -> le runner offline l'ignore. Consequence validation : mesurer JakhalStimms
  sur un Macer A PLEINE VIE (0% manquant -> extraDmg=0 -> Skullsmasher OFF, canal degat bit-exact propre) ;
  un Macer blesse verrait +extraDmg live (non un bug de ce port). Le stun requiert un kill melee ANTERIEUR
  (gate OFF au 1er cast). Trait BlessingsOfKhorne (extra dmg per kill) = idem passif separe non porte.

MurderousSwing (1137, `worldExecutions` « Tarvakh »). Namespace natif SANS `.Loki` :
`IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
    targets = AdjacentEnemies(@0x160 = caster)                       # ring 1, ennemis DU CASTER
    dmg     = If( AmountIsGreater(Count(targets), Direct(1)),        # STRICT ( > 1 ), cf. ci-dessous
                  MinMaxDamage,                                       # `$$GetMultipleUnitsDamage`
                  Sum(MinMaxDamage,                                   # `$$GetSingleUnitDamage`
                      Direct(GetVariableForLevel(config, 8 = extraDmg))) )
    Execute( AttackWithAttackDamage( @0x160 = caster, targets, dmg,
                                     GetDamageProfile(config) = Piercing,
                                     GetHits() = GetNumberConstant(0x2f = nrOfHits) = 1,
                                     AbilityOrEffect(this+0x10 = 1137) ) )

C'est le MEME noeud de degat que `$$GetCorrectDamage` (la face DECISION en porte deja la transcription,
`entities/abilities/active_ability.py::MurderousSwingAbility.get_correct_damage`) -- ici il est monte
INLINE dans l'`ExecuteBehaviour`, pas via un appel a `GetCorrectDamage`.

i2 : « Deals 1x [dmg] Piercing Damage to all adjacent enemies. If only one enemy is hit, deals
+[extraDmg] Damage. » Config 1137 : `damageProfile = Piercing`, `nrOfHits = 1` ; `minDmg`/`maxDmg`/
`extraDmg` per-niveau (les trois sont dans `variablesAffectedByRarityBonus`).

- **`AmountIsGreater` est STRICT** et le decompile le dit de facon PIEGEUSE : la factory
  `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreater` appelle un ctor que ghidra etiquette
  `IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$.ctor` -- **corps TRIVIAL
  DEDUPLIQUE** (les deux classes ont le meme ctor a 2 champs). La classe REELLE se lit sur le
  `ShouldTrigger` : `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger`
  rend `b < a` (STRICT), la ou `...AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` rend
  `b <= a`. Conclure sur le nom du ctor donnerait `Count >= 1` = TOUJOURS vrai, donc un extraDmg
  JAMAIS applique -- l'exact contraire de l'i2 et de la mesure #108.
- **le `Count` est REEVALUE PAR CIBLE** : le natif ne l'enveloppe d'AUCUN `Cache`, et
  `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` evalue le noeud de degat
  une fois par cible. Le set de cibles, lui, est materialise UNE fois par
  `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (puis `OrderBy`). Consequence LUE :
  si une cible MEURT, `AdjacentEnemies` ne la compte plus -> les cibles suivantes peuvent basculer
  du regime MULTI au regime SINGLE (+extraDmg) DANS LE MEME CAST. Le port mirror cet ordre exact
  (`entities.units` = vues LIVE-by-ref, cf. `entities_from_state`).
- la CIBLE DU MESSAGE n'a AUCUN role dans l'arbre : le set est `AdjacentEnemies(caster)`, self-centre.
  Elle ne sert qu'au GATE de ciblage (`RANGE_ADJACENT` + `TargetIsEnemy`).
- `native_factory="attack"` : l'`ExecuteBehaviour` appelle `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
  (famille ATTACK -> `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, 2 tirages/coup a cc=0),
  CLASSE PAR LE DECOMPILE.
- confonds du PORTEUR, hors perimetre de ce port : `RapidAssault` (effet 1229, +25% sans gate) est porte
  et s'applique des DEUX cotes ; `BlessingsOfKhorne` est indexe sur le nb de defaites en MELEE de la
  bataille (0 au 1er cast) ; `TrophyTaker` n'agit que sur la crit-chance (neutralisee au build par
  `--crit 0,0`).

KillMaimBurn (1132, `worldKharn` « Kharn the Betrayer »). Namespace natif
`Abilities.Active.Loki.KillMaimBurnAbility` (#504).
`IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :

    dmg1 = MinMaxDamage (state, 0)  = RandomAmount(GetVariableForLevel(0xc  minDmg  ), (0xd  maxDmg  ))
    dmg2 = MinMaxDamage2(state, 0)  = RandomAmount(GetVariableForLevel(0x36 minDmg_2), (0x37 maxDmg_2))
    dmg3 = MinMaxDamage3(state, 0)  = RandomAmount(GetVariableForLevel(0x38 minDmg_3), (0x39 maxDmg_3))
    p1/p2/p3 = GetDamageProfile()/GetDamageProfile2()/GetDamageProfile3()  # Piercing / Eviscerate / Plasma
    h1/h2/h3 = ConfigConst(0x2f nrOfHits) / ConfigConst(0x32 nrOfHits_2) / ConfigConst(0x66 nrOfHits_3)
    n        = GetNumberConstant(0x16 range)                                    # = 2

    t2 = GetNextTarget( previousTarget  = target@0x60,
                        validNextTargets = AdjacentEnemies(caster@0x48, 1, 3),
                        damage           = dmg2 )
    t3 = GetNextTarget( previousTarget   = t2,
                        validNextTargets = Unobscured(caster@0x48,
                                              SurroundingEnemies(caster@0x48, n, 1, 3)),
                        damage           = dmg2 )                       # <-- dmg2, PAS dmg3 (LU)

    b1 = Group( AttackWithAttackDamage(caster@0x48, target@0x60, dmg1, Direct(Nullable(p1)), h1,
                                       AbilityOrEffect(this+0x10), <options>, 2),
                target@0x60, 0x20 )
    b2 = Group( AttackWithAttackDamage(caster@0x48, t2, dmg2, Direct(Nullable(p2)), h2, ...), t2, 0x20 )
    b3 = Group( AttackWithAttackDamage(caster@0x48, t3, dmg3, Direct(Nullable(p3)), h3, ...), t3, 0x20 )
    ExecuteAtomic( op_BitwiseAnd(op_BitwiseAnd(b1, b2), b3), 0x2a )

`IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$GetNextTarget(previousTarget,
validNextTargets, damage)` (MIRROR du DECOMPILE) :

    pool   = FromTrigger( validNextTargets,
                          op_LogicalNot(IsObjectOrSteppable(It@0x68)), 0 )
             .Otherwise(validNextTargets)                          # repli si le filtre VIDE tout
    sorted = SortUnitsByDamageUtility( pool, caster@0x48, Direct(AbilityOrEffect(this+0x10)),
                                       UtilityDefinition(0x23 = UtilityType.Damage), damage,
                                       3, <hits = null> )
    return If( IsAlive(previousTarget), previousTarget, First(sorted, 1) )
           .Otherwise(previousTarget)

i2 CONCORDANT : « Deals 1x [dmg] Piercing Damage to an adjacent enemy. Then performs a second attack
targeting an adjacent enemy, dealing 6x [dmg_2] Eviscerating Damage. Then performs a third attack
targeting an enemy within range 2, dealing 1x [dmg_3] Plasma Damage. **All attacks prioritize the
same target until it is killed and then prioritise kills.** » -- la derniere phrase EST le
`If(IsAlive(prev), prev, First(SortUnitsByDamageUtility(...)))`.
Config 1132 : `nrOfHits=1`/`damageProfile=Piercing`, `nrOfHits_2=6`/`damageProfile_2=Eviscerate`,
`nrOfHits_3=1`/`damageProfile_3=Plasma`, `range=2` ; les SIX bornes sont dans
`variablesAffectedByRarityBonus`.

- **Les trois bandes sont LAZY, et c'est le coeur de l'ability** : `t2`/`t3` sont des SELECTEURS, donc
  evalues par `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` au moment de LEUR bande. Si la
  bande 1 tue la cible, `IsAlive(previousTarget)` est FAUX quand la bande 2 s'execute -> re-ciblage.
  `t3` re-evalue `t2` (il en est le `previousTarget`), donc la chaine se re-derive a chaque bande.
- **`damage` de la 2e ET de la 3e `GetNextTarget` est `dmg2`** (`MinMaxDamage2`), LU au decompile : le
  meme `pvVar5` est passe aux deux appels. Ne PAS "corriger" en `dmg3` pour la 3e bande.
- **`SortUnitsByDamageUtilitySelector$$Select` CONSOMME UN TIRAGE** : il appelle `damage.Calculate(
  entities)` UNE fois (hors de la boucle par cible), et `IdunBattle.Entities.Formulas.RandomAmount$$
  Calculate` finit par `query.NextInternal(min, max + 1)` sur le PRNG de bataille (`DSLFactory+0x18`).
  Le tri n'est donc PAS gratuit en rng -- mais il n'a lieu que dans la branche FAUSSE du `If`
  (cible precedente MORTE). `hits` du selecteur est `null` -> le champ reste a `1` et la prediction
  vaut `dmgMin == dmgMax == <le tirage>`, 1 coup.
- `native_factory="attack"` : `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` construit
  `AttackDamageBehaviour` + `AttackBehaviour` (famille ATTACK, 2 tirages/coup a cc=0) -- LU, pas deduit.
  Le `caster`/`target` que ce `DSLBehaviors` donne a l'`AttackDamageBehaviour` sont les selecteurs par
  DEFAUT (`caster@0x48`/`target@0x60`) ; les arguments de l'appelant vont a l'`AttackBehaviour`.
- `Group(..., 0x20)` = `GroupType.Ability_Attack` (LU dans `data/symbols/<build>/frida/enums.tsv`),
  pass-through d'etat ; `ExecuteAtomic(., 0x2a)` -> `AtomicGroup` (inline #201).
- FACE DECISION deja portee (#362, `engine/playbook/noncomparable/kill_maim_burn.py`) : le playbook ne
  lit QUE le 1er volet (`MinMaxDamage`/`GetDamageProfile`). Les suffixes `_2`/`_3` sont propres a la
  face COMBAT -- c'est-a-dire a CE port.
- Confonds du PORTEUR, hors perimetre : `TrophyTaker` (crit-chance, neutralise par `--crit 0,0`),
  `BlessingsOfKhorne` (indexe sur les defaites melee de la bataille, 0 au 1er cast), `RapidAssault`.

OverwhelmingWrath (1141, `worldEightbound` « Azkor »), #503 -- patron 2-PHASES « POSE D'EFFETS SEULE »
(le meme que `tau.py::HeavyRailRifle`) : le cast ne frappe PAS, il ARME. Trois poses, aucun degat,
aucun tirage RNG -- c'est le CONTRASTE exact des trois abilities ci-dessus, toutes famille ATTACK.
Detail complet dans `overwhelming_wrath_tree` / `OverwhelmingWrathAbility` en bas de module ;
RE : `docs/rl/case-503-overwhelming-wrath.md`.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const, TargetsSelector, _is_alive, _units_of
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.behaviours import op_add, op_and, AtomicGroup, Group
from ...entities.formulas import (Count, Difference, Get, If, Min, Multiply, RandomAmount, Sum,
                                  TotalTimesAttacked)
from ...entities.selectors.accessors import CasterTile, Owner, Target, TargetTile
from ...entities.selectors.geometry import Otherwise
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import (AdjacentEnemies, AdjacentUnits, And, Damageable,
                                         NormalUnits, Sub, SurroundingEnemies, Unobscured,
                                         non_steppable_or_object_units)
from ...entities.triggers import AmountIsGreater
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...dsl.effects import ExecutionContext
from ...streams.group_type import GroupType
from ..operations.damage_prediction_sort import SortTargetsByDamagePrediction
from .base import ActiveAbility, ability_attack_params
from .behaviours.combat import AttackWithAttackDamage, ChainLeftOverHitsAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddBondEffect, AddEffect
from .behaviours.stats import SubtractHealthPercent
from .targeting import RANGE_ADJACENT, RANGED_BOOL_FALSE, TargetingOptions
from .targeting_rule import TargetingRule as TR
from ..components import StatsComponent
from ..operations.damage_utility import first_by_damage_utility

if TYPE_CHECKING:
    from ..state import State


def jakhal_stimms_tree() -> AtomicGroup:
    """Arbre des ATTAQUES de `IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE ; cf.
    en-tete module). Le self-loss `ChangeStat` est un `Execute` SEPARE (hors atomic) -> execute par
    l'appelant apres cet AtomicGroup :
        AtomicGroup( op_and(
            AttackWithAttackDamage(Target(), "JakhalStimms", "Physical", melee, hits=4),                 # MAIN
            AttackWithAttackDamage( And(AdjacentUnits(CasterTile()), AdjacentEnemies(TargetTile())),      # AOE
                                    "JakhalStimms", "Physical", melee, multi=True, hits=4 ) ) )

    MAIN = attaque MELEE 4x Physical (pierce 1) sur la cible du message (`hits=4` de la config nrOfHits, chemin
    par defaut). AOE = MEME attaque (memes bornes/hits/profil) sur les ennemis du caster adjacents a la fois au
    caster ET a la cible (`And` = intersection ; caster/cible exclus). `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage,
    XREF ; 2 tirages/coup a cc=0). `multi=True` folde le selecteur multi-cible (tri par id = ordre natif).
    `ExecuteAtomic(., 0x2a)` -> `AtomicGroup`. Ordre main PUIS aoe -> meme `state.rng` -> bit-exact."""
    ability_type = int(ActiveAbilityType.JakhalStimms)              # AbilityOrEffect(this+0x10) threade after-hit
    main = AttackWithAttackDamage(Target(), "JakhalStimms", "Physical", is_melee=True,
                                  native_factory="attack", ability_type=ability_type)
    aoe_sel = And(AdjacentUnits(CasterTile()),                      # A : TOUTES unites adjacentes au caster
                  AdjacentEnemies(TargetTile()))                    # B : ennemis-du-caster adjacents a la cible
    aoe = AttackWithAttackDamage(aoe_sel, "JakhalStimms", "Physical", is_melee=True, multi=True,
                                 native_factory="attack", ability_type=ability_type)
    return AtomicGroup(op_and(main, aoe))


class JakhalStimmsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$ExecuteBehaviour` (id 1131, `worldJakhal` « Macer », WorldEaters) —
    MIRROR du DECOMPILE. Attaque MELEE 4x Physical (pierce 1) sur la cible + MEME attaque sur les ennemis
    adjacents a la fois au caster ET a la cible (AoE INTERSECTION `AdjacentUnits(caster) & AdjacentFriends(
    target)`) ; PUIS le caster perd 25% de son PV COURANT (`ChangeStat` Subtract, Execute separe). Free action
    (does not end turn, cable via base.py). Le behaviour = l'arbre DSL (`jakhal_stimms_tree`) : les feuilles
    `AttackWithAttackDamage` (mode bornes, hits=config nrOfHits) emettent la MEME Operation d'attaque d'ability
    que le pipeline combat porte -> bit-exact BY CONSTRUCTION vs une sequence directe sous meme rng.
    `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, XREF). Passif Skullsmasher + trait BlessingsOfKhorne (extra dmg)
    NON portes = items separes -> valider sur un Macer PLEINE VIE (gate OFF, canal bit-exact propre)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.JakhalStimms)   # 1131
    ABILITY_ID = "JakhalStimms"

    # GATE DE CIBLE (#115). Le masque est le champ `Rules` (`options+0x28`) des
    # `IdunBattle.Core.Services.TargetingOptions` que le ctor passe a
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` (lequel recopie la struct dans
    # `this+0x70..0xaf` et n'ECRASE que `+0x30`/`+0x38`, les deux regles-delegues : `Rules` arrive
    # INTACT jusqu'au filtre).
    #
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$.ctor` est de la forme
    # PRESET COPIE : il n'appelle AUCUN `TargetingOptions..ctor`, il recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` situe a l'offset +0x40 du bloc `<class>+0xb8` :
    #     opts <- <TargetingOptions statics>+0x40 .. +0x7f     (copie integrale, aucun flag ajoute)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit ce preset : `*(statics+0x68) = 0x4000`
    # (= `<preset>+0x28` = `Rules`) — valeur CONSTANTE lue dans ce cctor. Ce n'est PAS la surcharge
    # « preset + flags » (`TargetingOptions..ctor(&opts, &preset, <flags>)`, qui fait
    # `Rules <- preset.Rules | flags`) : ici il n'y a aucun flag a OR-er.
    #
    # NB le preset de JakhalStimms (+0x40) est DIFFERENT de celui des actives DarkAngels/Aeldari
    # (+0x140, `Rules = 0x4002`) : meme forme de ctor, masque distinct — d'ou la lecture ability par
    # ability plutot qu'une regle « toutes les offensives valent 0x4002 ».
    #
    # Decomposition (enum `IdunBattle.Core.Services.TargetingRule` VERBATIM,
    # `data/symbols/gqfc5mff6c/frida/enums.tsv`) :
    #     0x4000 TargetIsEnemy -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`) : refus sur
    #            soi-meme et sur un allie. SEUL bit du masque : pas de TargetMatchesDynamicRule ici
    #            (contraste avec le preset +0x140), et 1131 n'a effectivement aucun
    #            `GetDynamicInvalidTargetReason` natif.
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x40` -> `TargetingRange` statique
    # `+0x30` = `onlyAdjacent = True` + `overrideRange = 1` -> cible ADJACENTE obligatoire
    # (`forceMeleeTarget = False`). C'est le MEME preset que les 0x4000 votann -- mais surtout
    # PAS celui des 0x4002, dont le `TargetingRange` est `useRangeFromConfig` : les presets ne
    # se generalisent pas plus sur la portee que sur le masque.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        # 1) ExecuteAtomic(op_and(main, aoe), 0x2a) : attaques (main sur cible + aoe intersection).
        jakhal_stimms_tree().execute(entities, ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)   # MAIN = feuille Target()
        aoe = [{"target": p["target"], "attack": p["attack"]}
               for p in atks if p.get("target") != target_id]                            # cibles aoe != cible principale
        # 2) Execute(ChangeStat(Self, Health, Subtract, PercentageOf(current, hpPct))) : self-loss APRES l'atomic.
        SubtractHealthPercent(Caster(), "JakhalStimms", "hpPct").execute(entities, ectx)
        self_loss = next((p for n, p in ectx.emitted if n == "ChangeStat"), None)
        return {"ability": "JakhalStimms", "caster": caster_id, "target": target_id,
                "hits": 4, "main_attack": main, "aoe": aoe, "self_loss": self_loss, "dsl": True}


def murderous_swing_targets() -> AdjacentEnemies:
    """`AdjacentEnemies(@0x160 = caster)` -- le set de cibles de
    `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$ExecuteBehaviour`, et AUSSI la
    source du `Count` du noeud de degat (le natif reutilise LE MEME noeud pour les deux).

    Overload natif `IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(df, ref, ...)` =
    `Enemies(ref, Units(AdjacentTiles(ref)) - ref)` : ennemis-du-caster sur son ring 1, caster exclu.
    Cote port c'est `AdjacentEnemies(CasterTile())` (radius 1 par defaut), qui filtre `team != caster`
    et dont `_within` exclut deja les cadavres (mirror `Units(tiles)` = DEBOUT)."""
    return AdjacentEnemies(CasterTile())


def murderous_swing_extra_damage_node(targets: AdjacentEnemies, extra: int) -> If:
    """DELTA du noeud de degat de `MurderousSwingAbility$$ExecuteBehaviour`, mirror 1:1 :

        If( AmountIsGreater(Count(targets), Direct(1)),  Direct(0),        # GetMultipleUnitsDamage
                                                         Direct(extra) )   # GetSingleUnitDamage

    Le natif ecrit `If(cond, MinMaxDamage, Sum(MinMaxDamage, Direct(extraDmg)))` : les DEUX branches
    partagent `MinMaxDamage`, que la feuille du port recoit deja resolu en `(bmin, bmax)` via
    `ability_attack_params` -> le noeud monte ici est le TERME AJOUTE, exactement comme le `flat_node`
    de Foehammer (`Sum(MinMax, Multiply(...))`). `SumAmount$$CalculateMin`/`$$CalculateMax` etant
    compositionnels, ce terme s'ajoute aux DEUX bornes.

    `AmountIsGreater` est STRICT (`AmountIsGreaterAbilityTrigger$$ShouldTrigger` = `b < a`) : plus d'UN
    ennemi adjacent -> pas d'extraDmg ; un seul -> +extraDmg."""
    return If(AmountIsGreater(Count(targets), Get(1)), Get(0), Get(int(extra)))


def murderous_swing_tree(targets: AdjacentEnemies, damage_override) -> AttackWithAttackDamage:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$ExecuteBehaviour`
    (MIRROR du DECOMPILE ; cf. en-tete module). UN SEUL `Execute`, UNE SEULE feuille :

        AttackWithAttackDamage( actor = @0x160 caster, targets = AdjacentEnemies(caster),
                                degat = If(Count(targets) > 1, MinMaxDamage,
                                           Sum(MinMaxDamage, Direct(extraDmg))),
                                profil = GetDamageProfile = Piercing,
                                coups  = GetHits() = GetNumberConstant(nrOfHits) = 1 )

    `multi=True` folde `AttackBehaviour$$Execute` : le selecteur est resolu UNE fois, `OrderBy` (tri par
    id = ordre de lecture natif), puis une attaque par cible. `native_factory="attack"` (la factory
    appelee par l'`ExecuteBehaviour`, lue au decompile). Les coups viennent de la config (`nrOfHits`,
    chemin par defaut) : `GetHits` est le corps gshared que ghidra etiquette
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` (= `GetNumberConstant(0x2f)`)."""
    return AttackWithAttackDamage(targets, "MurderousSwing", "Piercing", is_melee=True, multi=True,
                                  damage_override=damage_override, native_factory="attack",
                                  ability_type=int(ActiveAbilityType.MurderousSwing))


class MurderousSwingAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$ExecuteBehaviour` (id 1137,
    `worldExecutions` « Tarvakh », WorldEaters) -- MIRROR du DECOMPILE, cf. `murderous_swing_tree()`.

    FACE COMBAT du gisement `[-D]` : la face DECISION etait portee depuis #108
    (`_SPECIAL_ABILITY_CLASSES["MurderousSwing"]` -> l'IA PREDIT le splash self-centre et CHOISIT
    l'ability) pendant que l'execution etait un NO-OP silencieux. ROUGE mesure AVANT ce port
    (`probe_murderous_swing_1137.py`, k=1) : `ported=False`,
    `flags={ability_used_flag: True, turn_finished: True}` -- le cast est ACCEPTE et consomme le tour --
    et cible 500000 -> 500000, caster 9537 -> 9537, alors que le MEME cast LIVE mutait
    (`mutated=True`, 84 evenements, 3953 de degat).

    Turn-flags = defauts base (1137 ABSENT des overrides `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MurderousSwing)   # 1137
    ABILITY_ID = "MurderousSwing"

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$.ctor`
    # est de la forme PRESET COPIE : il ne construit AUCUN `TargetingOptions` (aucun litteral visible),
    # il recopie les 0x40 octets du champ STATIQUE de `TargetingOptions` a l'offset +0x40 du bloc
    # `<class>+0xb8`, puis `AActiveAbility..ctor(this, &opts, 0, 0)`.
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit ce preset (RELU pour CETTE ability, pas
    # herite d'un lot) :
    #     +0x40 isSelfCasting   = 0
    #     +0x48 range          <- `TargetingRange` statics +0x30 = RANGE_ADJACENT
    #     +0x60 forceMeleeTarget = 1 = `RangedBool.False`
    #     +0x68 Rules            = 0x4000  (= <preset>+0x28)
    #     +0x70/+0x78            = 0 (les deux regles-delegues, ECRASEES par `AActiveAbility..ctor`)
    # MEME preset que JakhalStimms (1131) ci-dessus -- ce qui ne se DEDUIT pas : les presets ne se
    # generalisent ni par faction ni par profil, ils se relisent ability par ability.
    #     0x4000 TargetIsEnemy -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`) : refus sur
    #            soi-meme et sur un allie. SEUL bit : pas de `TargetMatchesDynamicRule`, et 1137 n'a
    #            effectivement aucun `MurderousSwingAbility$$GetDynamicInvalidTargetReason`.
    # PORTEE : `RANGE_ADJACENT` (`onlyAdjacent = True` + `overrideRange = 1`) = cible ADJACENTE
    # obligatoire. `force_melee_target = RANGED_BOOL_FALSE` -> aucun `Min(1, range)`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        ce = state.get_entity(caster_id)
        sc = ce.get_component(StatsComponent) if ce is not None else None
        ctx = sc.ctx if sc is not None else None
        level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
        # `Direct(GetVariableForLevel(config, 8 = extraDmg))` -- variable PER-NIVEAU, dans
        # `variablesAffectedByRarityBonus` (le multiplier s'applique, comme cote natif).
        extra = int(ability_var("MurderousSwing", "extraDmg", level, multiplier_pct=mult) or 0)
        targets = murderous_swing_targets()
        delta_node = murderous_swing_extra_damage_node(targets, extra)
        seen: list[int] = []

        def damage_override(_st, _caster, _target, bmin, bmax):
            # `AttackDamageBehaviour$$ExecuteTarget` evalue le noeud de degat PAR CIBLE -> on
            # REEVALUE ici (aucun `Cache` natif), sur l'`entities` LIVE : un mort dans le ring 1
            # fait retomber le `Count` et peut basculer les cibles suivantes en regime SINGLE.
            d = int(delta_node.evaluate(entities))
            seen.append(d)
            return bmin + d, bmax + d

        murderous_swing_tree(targets, damage_override).execute(entities, ectx)
        hits = [{"target": p.get("target"), "attack": p.get("attack")}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": "MurderousSwing", "caster": caster_id, "target": target_id,
                "extra_damage": extra, "per_target_delta": seen, "hits": hits, "dsl": True}


KILL_MAIM_BURN_ID = "KillMaimBurn"
# `GroupType.Ability_Attack` = 0x20 -- le 3e argument des trois `DSLBehaviors.Group` de
# `KillMaimBurnAbility$$ExecuteBehaviour`, DECLARE `groupType : IdunBattle.Streams.GroupType` dans
# `frida/methods.tsv` et LU dans `data/symbols/<build>/frida/enums.tsv`.
KILL_MAIM_BURN_GROUP = GroupType.Ability_Attack


def _kill_maim_burn_const(key: AbilityConstantType) -> int:
    """`AbilityConfiguration$$GetNumberConstant(config, <key>)` = `KillMaimBurn.constants[<nom>]`.

    Lecture gameconfig DIRECTE, par le NOM du membre d'enum (jamais son ordinal) : le noeud
    `ConfigConst` du port lit `ctx.config`, un `AbilityConfiguration` que le contexte d'un cast de
    runner ne porte pas -- meme voie que `triggers/loki/serene_unifier.py::_ability_const`."""
    import gameconfig as GC                 # DIFFERE, et GRATUIT au sens du cliquet d'import isole :
    #   `gameconfig` n'est PAS un module `engine.*` (c'est un script racine de `scripts/python`), donc
    #   il n'entre dans aucun cycle du paquet ; le hisser ferait payer le chargement du gameconfig a
    #   tout import de `abilities/worldeaters.py`, y compris aux consommateurs qui n'en ont pas besoin.
    consts = (GC.ability(KILL_MAIM_BURN_ID) or {}).get("constants") or {}
    return int(consts.get(getattr(key, "name", str(key))) or 0)


class KillMaimBurnNextTarget(TargetsSelector):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$GetNextTarget(
    previousTarget, validNextTargets, damage)` -- MIRROR 1:1 du decompile (cf. l'en-tete du module) :

        pool   = FromTrigger(validNextTargets, NOT IsObjectOrSteppable(It@0x68), 0)
                 .Otherwise(validNextTargets)
        sorted = SortUnitsByDamageUtility(pool, caster@0x48, Direct(AbilityOrEffect(1132)),
                                          UtilityDefinition(0x23 = UtilityType.Damage), damage, 3, null)
        return If(IsAlive(previousTarget), previousTarget, First(sorted, 1)).Otherwise(previousTarget)

    Les DEUX etages structurels (`pool` et le `.Otherwise` final) sont des noeuds DSL montes tels
    quels ; seul l'etage `SortUnitsByDamageUtility + First` est COLLAPSE en imperatif
    (`operations/damage_utility.first_by_damage_utility`), doctrine slice-18/19 deja appliquee a
    FinalJustice / AncestralFortune / Doombolt -- le selecteur AI-target n'a pas d'equivalent noeud.

    ⚠ **UN TIRAGE PRNG dans la branche FAUSSE.** `SortUnitsByDamageUtilitySelector$$Select` appelle
    `damage.Calculate(entities)` UNE fois (avant la boucle par cible) ; `damage` est ici
    `MinMaxDamage2` = `RandomAmount(minDmg_2, maxDmg_2)`, dont le `Calculate` finit par
    `query.NextInternal(min, max + 1)` sur le PRNG de BATAILLE. Le port consomme donc le meme tirage,
    au meme endroit, et SEULEMENT quand la cible precedente est morte (le `If` court-circuite).
    `hits` du selecteur natif est `null` -> la prediction de tri vaut `dmgMin == dmgMax == <tirage>`
    pour 1 coup, ce que reproduit `first_by_damage_utility(state, pool, roll, roll)`.

    Le noeud est evalue PARESSEUSEMENT (une fois par bande, par `AttackBehaviour$$Execute`), et
    `previous` peut etre un AUTRE `KillMaimBurnNextTarget` (la 3e bande prend la 2e en
    `previousTarget`) : la chaine se re-derive donc integralement a chaque bande, comme le natif."""
    __slots__ = ("previous", "pool", "state", "dmg_min", "dmg_max", "picked", "rolls")

    def __init__(self, previous: TargetsSelector, valid: TargetsSelector, state,
                 dmg_min: int, dmg_max: int):
        self.previous = previous
        # `FromTrigger(valid, NOT IsObjectOrSteppable(It), 0).Otherwise(valid)` -- le repli natif n'a de
        # sens que parce que `validNextTargets` peut etre INTEGRALEMENT compose d'Object/Steppable
        # (cf. case-462-r4b-...-r1-mot-object-or-steppable).
        self.pool = Otherwise(non_steppable_or_object_units(valid), valid)
        self.state, self.dmg_min, self.dmg_max = state, int(dmg_min), int(dmg_max)
        self.picked, self.rolls = [], []          # diagnostic (jamais lu par l'arbre)

    def select(self, ctx):
        # `IfSelector.Select` = `cond = trigger.ShouldTrigger(entities)` PUIS
        # `(cond ? selectorTrue : selectorFalse).Select(entities)`. Ici `trigger` est
        # `IsAlive(previousTarget)` et `selectorTrue` EST `previousTarget` : le noeud
        # `previousTarget` est donc evalue DEUX FOIS sur la branche vraie -- une fois par le
        # trigger, une fois par la branche rendue. Ce n'est pas un detail de style : quand
        # `previousTarget` est lui-meme un `GetNextTarget` (la bande 3 prend la bande 2), CHAQUE
        # evaluation peut consommer un tirage de tri. #504 l'a mesure au tirage pres (24 tirages
        # natifs contre 20 pour un port qui n'evaluait qu'une fois).
        prev = _units_of(self.previous, ctx)               # `IsAlive(previousTarget)` -- le TRIGGER
        if any(_is_alive(u) for u in prev):
            res = _units_of(self.previous, ctx)            # branche VRAIE : `previousTarget` RE-EVALUE
            self.picked.append(("alive", [u.get("id") for u in res]))
        else:
            candidates = _units_of(self.pool, ctx)         # `targets.Select` du selecteur de tri
            # `damage.Calculate(entities)` -- `RandomAmount(minDmg_2, maxDmg_2)`, PRNG de bataille.
            roll = int(RandomAmount(Const(self.dmg_min), Const(self.dmg_max),
                                    rng=getattr(self.state, "rng", None)).calculate(ctx))
            self.rolls.append(roll)
            # `owner_id` = le `caster@0x48` que le natif passe en `+0x20` du selecteur de tri
            # (#494-r1) : sa POSITION entre dans la prediction PAR CIBLE, donc dans la cle.
            # #494-r1-r1 : la cle EST cette prediction (armure et defense comprises). Le noeud
            # `+0x28` du selecteur est `Direct(AbilityOrEffect(1132))` -> seule l'ABILITY descend
            # jusqu'a la prediction ; ni PROFIL ni PERCAGE, parce que le selecteur passe
            # `damageProfile: null` (percage 0, cf. l'en-tete de `damage_utility.py`). Ce qui
            # dispense, au passage, de trancher lequel des trois profils de 1132
            # (`Piercing`/`Eviscerate`/`Plasma`) le tri emploierait.
            _cast = getattr(ctx, "caster", None)
            _cid = (_cast or {}).get("id")
            best = first_by_damage_utility(self.state, [u.get("id") for u in candidates], roll, roll,
                                           owner_id=_cid, is_melee=True,
                                           ability_type=int(ActiveAbilityType.KillMaimBurn))
            res = [] if best is None else [u for u in candidates if u.get("id") == best]
            self.picked.append(("retarget", [u.get("id") for u in res]))
        if not res:                                        # `.Otherwise(previousTarget)`
            res = _units_of(self.previous, ctx)
            self.picked.append(("otherwise", [u.get("id") for u in res]))
        return res


def kill_maim_burn_selectors(state, caster_id: int) -> tuple:
    """Les deux `GetNextTarget` de `KillMaimBurnAbility$$ExecuteBehaviour`, montes dans l'ordre du
    decompile. Rendus a part pour que l'ability puisse LIRE leur diagnostic apres execution.

      * `t2` = `GetNextTarget(target@0x60, AdjacentEnemies(caster@0x48, 1, 3), dmg2)`
      * `t3` = `GetNextTarget(t2, Unobscured(caster@0x48, SurroundingEnemies(caster@0x48, range, 1, 3)),
                              dmg2)` -- le decompile passe `dmg2` (`pvVar5`) AUX DEUX appels.

    La surcharge 4-args de `SurroundingEnemies` (celle du decompile ici : `SurroundingEnemies(this,
    caster, <int range>, 1, 3)`) fait servir le MEME selecteur de centre ET de reference d'equipe --
    ce qui, le centre etant le caster, coincide avec le defaut `reference = ctx.caster` du port."""
    bmin2, bmax2, _pierce2, _hits2 = ability_attack_params(
        state, caster_id, KILL_MAIM_BURN_ID, "Eviscerate", ranged=False,
        min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2")
    t2 = KillMaimBurnNextTarget(Target(), AdjacentEnemies(CasterTile()), state, bmin2, bmax2)
    t3 = KillMaimBurnNextTarget(
        t2,
        Unobscured(SurroundingEnemies(CasterTile(),
                                      Const(_kill_maim_burn_const(AbilityConstantType.range)))),
        state, bmin2, bmax2)
    return t2, t3


def kill_maim_burn_tree(t2: TargetsSelector, t3: TargetsSelector) -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$ExecuteBehaviour`
    (id 1132, `worldKharn` « Kharn ») -- MIRROR 1:1 du decompile (cf. l'en-tete du module) :

        ExecuteAtomic( Group(b1, Target, 0x20) & Group(b2, t2, 0x20) & Group(b3, t3, 0x20), 0x2a )

    Trois plages, trois profils et trois comptes de coups DISTINCTS (`minDmg`/`maxDmg` + `Piercing` +
    `nrOfHits`(0x2f) ; `minDmg_2`/`maxDmg_2` + `Eviscerate` + `nrOfHits_2`(0x32) ; `minDmg_3`/
    `maxDmg_3` + `Plasma` + `nrOfHits_3`(0x66)). `is_melee=True` : `attackRangeType = Melee` est une
    propriete de l'ABILITY (une seule config), y compris pour la 3e bande qui porte a 2 hexes.
    `native_factory="attack"` (`DSLBehaviors$$AttackWithAttackDamage` -> `AttackDamageBehaviour` +
    `AttackBehaviour`, LU). `multi=True` sur les trois : le natif passe TOUJOURS par
    `AttackBehaviour$$Execute` (resolution de la LISTE puis `OrderBy`), meme pour un singleton."""
    aid = int(ActiveAbilityType.KillMaimBurn)                 # AbilityOrEffect(this+0x10)
    b1 = AttackWithAttackDamage(Target(), KILL_MAIM_BURN_ID, "Piercing", is_melee=True, multi=True,
                                native_factory="attack", ability_type=aid)
    b2 = AttackWithAttackDamage(t2, KILL_MAIM_BURN_ID, "Eviscerate", is_melee=True, multi=True,
                                min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2",
                                native_factory="attack", ability_type=aid)
    b3 = AttackWithAttackDamage(t3, KILL_MAIM_BURN_ID, "Plasma", is_melee=True, multi=True,
                                min_key="minDmg_3", max_key="maxDmg_3", hits_key="nrOfHits_3",
                                native_factory="attack", ability_type=aid)
    return AtomicGroup(op_and(op_and(Group(b1, int(KILL_MAIM_BURN_GROUP), Target()),
                                     Group(b2, int(KILL_MAIM_BURN_GROUP), t2)),
                              Group(b3, int(KILL_MAIM_BURN_GROUP), t3)))


class KillMaimBurnAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$ExecuteBehaviour` (id 1132,
    `worldKharn` « Kharn the Betrayer », WorldEaters -- HERO, present dans
    `rl_duel build --list-pool`) -- MIRROR du DECOMPILE, cf. `kill_maim_burn_tree()`.

    TROIS attaques enchainees sur la MEME cible tant qu'elle vit, re-ciblees par utilite de degat des
    qu'elle meurt (`GetNextTarget`) :
      1. cible du message                       -> `nrOfHits`   x `Piercing`   `minDmg`  /`maxDmg`
      2. `AdjacentEnemies(caster)` si (1) tue   -> `nrOfHits_2` x `Eviscerate` `minDmg_2`/`maxDmg_2`
      3. `Unobscured(SurroundingEnemies(caster, range=2))` si (2) tue
                                                -> `nrOfHits_3` x `Plasma`     `minDmg_3`/`maxDmg_3`

    FACE COMBAT du gisement `[-D]` : la face DECISION est portee depuis #362
    (`playbook/noncomparable/kill_maim_burn.py` : l'IA PREDIT et CHOISIT 1132) pendant que
    l'execution etait un NO-OP SILENCIEUX -- 1132 absente d'`ABILITY_CLASSES`, donc cast accepte,
    tour consomme, 0 degat, 0 effet, AUCUNE erreur (meme signature que MurderousSwing avant #149).

    Turn-flags = defauts base (1132 ABSENT de `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.KillMaimBurn)   # 1132
    ABILITY_ID = KILL_MAIM_BURN_ID

    # MASQUE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$.ctor` est de
    # la forme PRESET COPIE : il n'appelle AUCUN `TargetingOptions$$.ctor`, il recopie les 0x40 octets
    # du champ STATIQUE de `TargetingOptions` a l'offset +0x40 du bloc `<class>+0xb8`, puis
    # `AActiveAbility..ctor(this, &opts, 0)`. `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit
    # ce preset (RELU pour CETTE ability, pas herite d'un lot) :
    #     +0x40 isSelfCasting     = 0
    #     +0x48 range            <- `TargetingRange` statics +0x30 = RANGE_ADJACENT
    #     +0x60 forceMeleeTarget  = 1 = `RangedBool.False`   (⚠ enum natif INVERSE : True=0, False=1)
    #     +0x68 Rules             = 0x4000  (= <preset>+0x28)
    #     +0x70/+0x78             = 0 (les deux regles-delegues, ECRASEES par `AActiveAbility..ctor`)
    #     0x4000 TargetIsEnemy -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`). SEUL bit : pas de
    #            `TargetMatchesDynamicRule`, et 1132 n'a effectivement aucun
    #            `KillMaimBurnAbility$$GetDynamicInvalidTargetReason`.
    # MEME preset que JakhalStimms (1131) / MurderousSwing (1137) ci-dessus -- ce qui ne se DEDUIT pas.
    # PORTEE : `RANGE_ADJACENT` (`onlyAdjacent = True` + `overrideRange = 1`) = cible ADJACENTE
    # obligatoire. La `range=2` de la config ne borne QUE le pool de re-ciblage de la 3e bande
    # (`SurroundingEnemies`), PAS le gate de cible du cast.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        t2, t3 = kill_maim_burn_selectors(state, caster_id)   # noeuds NEUFS -> etat PAR-CAST
        ectx = ExecutionContext(state=state, rng=state.rng)
        kill_maim_burn_tree(t2, t3).execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": KILL_MAIM_BURN_ID, "caster": caster_id, "target": target_id,
                "attacks": atks,
                # ventilation LUE des deux `GetNextTarget` (branche prise + tirages de tri consommes)
                "next_target_2": {"picks": t2.picked, "rolls": t2.rolls},
                "next_target_3": {"picks": t3.picked, "rolls": t3.rolls},
                "dsl": True}


# =====================================================================================
# OverwhelmingWrath (1141, `worldEightbound` « Azkor ») -- #503
# =====================================================================================
#: `EffectType.Taunted_OnlySpecificTargets` -- l'effet COMPOSITE 27 (`TauntedEffect`, base
#: `ABondEffect`), le MEME que pose `GetEmRuntz` / `CrushingClaws`.
OW_TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)            # 0x1b = 27
#: `EffectType.OverwhelmingWrath_PendingAttack` -- l'ARMEMENT de la phase 2.
OW_PENDING_ATTACK = int(EffectType.OverwhelmingWrath_PendingAttack)  # 0x514 = 1300
#: Le NOM gameconfig de l'ACTIVE 1141 -- et c'est la config que lisent LES DEUX PHASES : la
#: TRIGGERED 1237 n'a AUCUNE entree gameconfig propre (mesure, cf. le bloc de la phase 2).
OW_ACTIVE_ID = ActiveAbilityType.OverwhelmingWrath.name              # "OverwhelmingWrath"
#: `EffectType.OverwhelmingWrath_RangeDmgReduction` -- le -dmgReductionPct% RANGED sur le caster.
OW_RANGE_DMG_REDUCTION = int(EffectType.OverwhelmingWrath_RangeDmgReduction)   # 0x515 = 1301


def overwhelming_wrath_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour`
    -- MIRROR 1:1 du DECOMPILE (build `rnca9r7q6c`) :

        e1 = AddEffect( 0x515 = 1301 OverwhelmingWrath_RangeDmgReduction, AbilityStateReference,
                        source = Caster@0x48, targets = Caster@0x48, TurnsFromRounds(1) )
        e2 = AddBondEffect( 0x1b = 27 Taunted_OnlySpecificTargets, AbilityStateReference,
                            source  = Caster@0x48,
                            targets = NormalUnits( AdjacentEnemies(Owner@0x30, unique: 1,
                                                                   selectionType: 3),
                                                   selectionType: 3 ),
                            bondedEntity = Caster@0x48, TurnsFromRounds(1) )
        e3 = AddBondEffect( 0x514 = 1300 OverwhelmingWrath_PendingAttack, AbilityStateReference,
                            source = Caster@0x48, targets = Caster@0x48,
                            bondedEntity = Caster@0x48, options = <Nullable ZERO> )
        AActiveAbility.Execute( op_Addition( op_Addition(e1, e2), e3 ) )

    AUCUNE attaque, aucun `ChangeStat`, aucun spawn -- et AUCUN `Group` (contraste avec
    `kill_maim_burn_tree` ci-dessus, dont les trois bandes en portent un) : le cast ARME (patron
    2-PHASES, cf. `tau.py::heavy_rail_rifle_tree`). Le `2x Eviscerate` du kit appartient a la
    TRIGGERED `IdunBattleLogic.Entities.Abilities.Triggered.Loki.OverwhelmingWrath_AttackAbility`
    (`TriggeredAbilityType` 0x4d5 = 1237), portee par l'effet 1300 -- HORS de ce port (residu
    #503-r1). C'est pourquoi la colonne `categorie` de l'audit (`DAMAGE(Eviscerate)`, derivee du
    KIT) ne decrit PAS ce behaviour.

    LES DEUX SLOTS DE ROLE, re-derives sur CE build et non hérités : `Selectors+0x48` est le CASTER
    et `Selectors+0x30` l'OWNER. Preuve independante -- `IdunBattleLogic.Entities.Abilities.Active.
    Loki.MomentShackleAbility$$ExecuteBehaviour` passe `+0x48` a `DSLBehaviors$$Heal` et a
    `DSLFormulas$$StatAmount` (que `case-231` avait lus `caster@0x160`), et `+0x30` aux deux
    `AddDynamicStatModifierEffect` + a l'`AddEffect(0x571)` (que `case-231` avait lus `owner@0x148`) ;
    et `IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$GetPossibleMovementTiles`
    passe `+0x48` au parametre NOMME `caster` de `DSLSelectors$$TilesUnitCanMoveToChargeTarget`.
    Sur une ACTIVE, `Owner` et `Caster` designent la MEME unite (le port ne materialise pas de
    selecteur `Owner` distinct : `Owner()` retombe sur le caster, convention actee case-224) -- l'ecart
    de slot est donc SANS effet ici, et il est ecrit pour rester grepable.

    `AdjacentEnemies(unit, unique, selectionType)` natif =
    `Enemies( of: unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType )` :
    la reference d'equipe est le 1er argument (`Owner`), PAS un caster implicite. Le selecteur porte
    filtre sur `ctx.caster.team` -- identique tant que le centre EST le caster, ce qui est le cas ici.

    DUREES : les deux premieres feuilles portent `TurnsFromRounds(1)` (litteral `1`, PAS un
    `GetNumberConstant(nrOfRounds)` -- 1141 n'a pas cette constante au gameconfig) -> le port passe
    `duration_rounds=1`, converti par `BattleQuery$$ConvertRoundsToTurns`. La TROISIEME recoit un
    `Nullable<AddEffectBehaviourOptions>` ZERO-initialise (`local_198..uStack_180 = 0`), donc AUCUN
    override -> `duration_rounds=None` = `DefaultAmountOfRounds` de l'effet (meme lecture que les deux
    poses de `heavy_rail_rifle_tree`).

    `scale_from_source=True` sur la feuille 1301 : sa magnitude est un `ConfigVar` --
    `IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$CreateDamageDefenseModifier`
    = `EffectBonus.ForPercentDecrease( get_OwnerIsTarget & IsRangedAttack,
    ConfigVar(0x46 = AbilityVariableType.dmgReductionPct, GetAbilityState(effet), config@+0x60) )`.
    Sans le bake de l'`AbilityStateReference` (3e argument natif), l'effet materialise lirait le
    niveau par defaut au lieu de celui du poseur. Les deux bonds n'en ont PAS besoin (27 et 1300 ne
    lisent aucun `ConfigVar` cote port : 27 est un composite a sous-effets, 1300 est un marqueur)."""
    dmg_reduction = AddEffect(
        OW_RANGE_DMG_REDUCTION, EffectType.OverwhelmingWrath_RangeDmgReduction.name,
        Caster(), duration_rounds=1, scale_from_source=True)
    taunt = AddBondEffect(
        OW_TAUNTED, EffectType.Taunted_OnlySpecificTargets.name,
        Caster(), NormalUnits(AdjacentEnemies(Owner())),
        duration_rounds=1, bonded_ref=Caster())
    pending = AddBondEffect(
        OW_PENDING_ATTACK, EffectType.OverwhelmingWrath_PendingAttack.name,
        Caster(), Caster(), duration_rounds=None, bonded_ref=Caster())
    return op_add(op_add(dmg_reduction, taunt), pending)


class OverwhelmingWrathAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour`
    (id 1141, `worldEightbound` « Azkor », WorldEaters). Arbre DSL `overwhelming_wrath_tree`.

    i2 (`Abilities/OverwhelmingWrath_CurrentLevelDescription`) : « Until the beginning of his next
    turn Azkor Taunts all adjacent enemies and takes -{dmgReductionPct}% Damage from ranged attacks.
    Deals {nrOfHits}x {minDmg}-{maxDmg} Eviscerating Damage to all adjacent enemies at the beginning
    of Azkor's next turn. » -> les DEUX premieres phrases sont l'ACTIVE (portee ici, trois poses
    d'effet) ; la TROISIEME est la phase 2, la triggered 1237 armee par l'effet 1300 (residu #503-r1).

    ROUGE MESURE AVANT CE PORT : 1141 etait ABSENTE d'`ABILITY_CLASSES` -> `AbilityHandler` acceptait
    le cast, posait les flags de tour, et n'executait RIEN. Zero effet, zero erreur.

    `ABILITY_ATTACK_TYPE` : `...OverwhelmingWrathAbility$$.ctor` termine par
    `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = `2` = `Others`. LITTERAL TRANSCRIT, pas
    deduit : l'ability est classee `DAMAGE(Eviscerate)` par le kit, et son ctor dit quand meme `2`.

    Turn-flags = defauts base (1141 ABSENT des overrides `NO_END_TURN_ABILITY_TYPES` /
    `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> le cast termine le tour et pose `ActiveAbilityUsed`.

    Diag : {posed: [{effect, target, bonded}], dsl: True}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.OverwhelmingWrath)   # 1141
    ABILITY_ID = "OverwhelmingWrath"

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **FLAGS DIRECTS** (la 1re des trois
    # surcharges) : `IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$.ctor`
    # recopie les 24 octets du champ STATIQUE `TargetingRange statics+0x30` dans un local, puis
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, range=<TargetingRange statics+0x30>,
    #                            forceMeleeTarget=1, rules=0x4000, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)
    # Le litteral EST le masque : ni preset a OR-er, ni copie de bloc `TargetingOptions` -- contraste
    # avec les TROIS autres abilities de ce module, toutes en PRESET COPIE.
    #     0x4000 (bit 14) TargetIsEnemy -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`).
    # `isSelfCasting = 1` avec `TargetIsEnemy` n'est PAS contradictoire : c'est le meme couple que
    # 1061 `UnbreakableDuty` / 1175 `BloodChalice` -- le flag dit que le cast peut partir sans cible
    # designee, le bit reste arme sur la cible quand il y en a une.
    # ⚠ MAIS `isSelfCasting = 1` ne veut PAS dire « castable a vide » : MESURE (contre-epreuve G1 de
    # `probe_503_generalisation.py`), sans aucun ennemi adjacent le natif REFUSE, sur
    # `0x800 AddCasterIfAtLeastOneTarget` -- le caster n'entre dans les cibles legales que s'il
    # existe au moins une AUTRE cible (branche `else` de
    # `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`). Le port rend `0` la :
    # ecart PERMISSIF ANTERIEUR (#447), deja nomme et mesure sur 1226 Chronometron dans la docstring
    # de `get_caster_not_added_reason` ; #503 le re-mesure sur un DEUXIEME porteur.
    # PORTEE : `TargetingRange statics+0x30` = `RANGE_ADJACENT` (`onlyAdjacent = RangedBool.True` +
    # `overrideRange = 1`). `forceMeleeTarget = 1` = `RangedBool.False` (aucun clamp melee).
    # ⚠ Ces quatre valeurs MIGRENT depuis `TARGETING_OPTIONS_UNPORTED[1141]` (contrat de DISJONCTION :
    # une ability a UNE source de masque, jamais deux) ; elles ont ete RE-LUES au decompile avant
    # migration et sont bit-identiques a celles qui vivaient la-bas.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=True,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        overwhelming_wrath_tree().execute(entities, ectx)
        posed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                  "bonded": p.get("bonded")}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddBondEffect")]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "posed": posed, "dsl": True}


# ---- PHASE 2 : `OverwhelmingWrath_Attack` (TriggeredAbilityType 0x4d5 = 1237), #503-r1 -----------
#
# DEPLACEE vers `runner/operations/triggers/loki/overwhelming_wrath_attack.py` par #503-r3 -- avec
# sa RE integrale (les cinq points de fidelite, le `RemoveEffect` qui appartient au `Triggered()`
# d'`APendingAttackEffect`, la struct d'options zeroee). Une ability TRIGGERED vit avec les
# triggers : c'est ce qui rend `TRIGGERED_ABILITY_BEHAVIOURS[1237]` peuple des que
# `dispatch/registry.py` est charge, sans dependre d'`abilities/handler.py`.
# ⚠ Ici l'arete `registry -> worldeaters` etait GRATUITE (mesure) -- un import pour effet de bord
# aurait suffi. On deplace quand meme : la phase 2 de `1069` exigeait le deplacement (arete
# PORTEUSE), et traiter les deux familles differemment aurait inscrit dans le port une asymetrie
# que rien dans le natif ne justifie. Ce module garde la PHASE 1, l'active `1141` ci-dessus.

# ================== BloodyFury (worldTerminator « Wrask », actif 1129) -- #505 ====================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$ExecuteBehaviour` (RE relue sur
# `rnca9r7q6c`), transcription de l'arbre, UN SEUL noeud terminal passe a `AActiveAbility$$Execute` :
#
#     dmg   = DSLFormulas$$Cache( AActiveAbility$$MinMaxDamage(this, abilityState) )
#     other = DSLSelectors$$Damageable(
#                 DSLSelectors$$AdjacentEnemies(unit = Owner@DSLSelectors+0x30, unique: 1,
#                                               unitSelectionType: 3)
#                 op_Subtraction Target@DSLSelectors+0x60 )              # == `$$GetOtherTargets`
#     chain = DSLSelectors$$SortTargetsByDamagePredictionSelector(
#                 attacker              = Owner@+0x30,
#                 units                 = other,
#                 ability               = DSLSelectors$$Direct(AbilityOrEffect(this+0x10)),
#                 damage                = dmg,
#                 hits                  = <DSLFormulas+0x20>,           # cf. ci-dessous : Direct(1)
#                 damageProfileType     = DSLSelectors$$Direct(Nullable(GetDamageProfile(config))),
#                 attackerSelectionType = 3)
#     DSLBehaviors$$ChainLeftOverHitsAttackDamage(
#                 caster                     = Owner@+0x30,
#                 firstTarget                = Target@+0x60,
#                 dmgAmount                  = dmg,
#                 damageProfileType          = Direct(Nullable(GetDamageProfile(config))),
#                 hits                       = <GetNumTotalHits(this)>,
#                 abilityType                = this+0x10,
#                 otherTargetSelector        = chain,
#                 extraHitsAfterTargetKilled = **null**)
#
# ⚠ LE `hits` DU SELECTEUR DE TRI EST **1**, PAS `nrOfHits`, ET CE N'EST PAS UN OUBLI DE LECTURE.
# Le natif passe `*(void **)(<DSLFormulas> + 0x20)`, un CHAMP de l'instance `DSLFormulas`, pas un
# `Direct(GetNumberConstant(...))` construit sur place. `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
# ecrit cinq formules-constantes memoisees, LUES : `+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`,
# `+0x30 = 100`, `+0x38 = -1` (meme classe et meme ctor `(valeur, 0)` que
# `IdunBattleLogic.Entities.DSLFormulas$$Direct`). Donc `hits = Direct(1)`. C'est un ECART LU avec
# `1048 FragstormGrenadeLauncher`, qui monte la MEME feuille et passe, lui,
# `Direct(GetNumberConstant(0x2f = nrOfHits))` : le tri par priorite de kill de BloodyFury predit le
# report sur UN coup, pas sur la volee entiere. Recopier le voisin aurait change l'ordre du report.
#
# TROIS AUTRES ECARTS LUS avec 1048 (aucun n'est copie) :
#   * pas de `SortByFormula` par PV en amont du selecteur de prediction (1048 en a un) ;
#   * le pool est `AdjacentEnemies` (ring 1) et non `SurroundingEnemies(range)` ;
#   * le `hits` de la CHAINE est une FORMULE (`GetNumTotalHits`), pas la constante `nrOfHits`.
# ET UN POINT COMMUN LU : `extraHitsAfterTargetKilled` est **null** des deux cotes (1006
# `MultiThreatEliminator` y met `Get(GetNumberConstant(0x2b = extraHit))`) -- donc AUCUN coup bonus
# par ennemi tue pour 1129. Le `extraHit` de sa config sert au SNOWBALL, pas au report.
# ⚠ `DSLFormulas$$Get(amount:System.Int32)` EST `DSLFormulas$$Direct(amount:System.Int32)` : meme
# `Il2CppClass*`, meme allocateur, meme ctor, meme argument (#512-r5, mesure sur `t6dpr4k06g` par
# `probe_512r5_get_vs_direct.py`). Les `Get(...)` ecrits plus bas dans ce fichier sont donc le MEME
# noeud-constante que les `Direct(...)` du decompile cite -- ce n'est pas une equivalence de
# commodite. ⚠ La resolution passe par la SIGNATURE : `$$Get` porte trois surcharges homonymes, et
# celles sur `System.String` / `IdunBattle.Utils.Hex.Edge` allouent, elles, d'AUTRES classes.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$GetNumTotalHits` (MIRROR) :
#     Sum( Direct(GetNumberConstant(0x2f = nrOfHits)), GetNumExtraHits(this) )
# `...BloodyFuryAbility$$GetNumExtraHits` (MIRROR) :
#     Min( Multiply( Direct(GetNumberConstant(0x2b = extraHit)),
#                    DSLFormulas$$TotalTimesAttacked(Owner@DSLSelectors+0x30) ),
#          Subtract( Direct(GetNumberConstant(0x48 = maxNrOfHits)),
#                    Direct(GetNumberConstant(0x2f = nrOfHits)) ) )
# -> coups = nrOfHits + min(extraHit x <attaques recues DANS LA BATAILLE>, maxNrOfHits - nrOfHits),
# donc borne par `maxNrOfHits`. Config 1129 : nrOfHits=1, extraHit=1, maxNrOfHits=8, damageProfile
# `Chain`, `attackRangeType = Melee`.
# i2 mot a mot : « Deals {nrOfHits}x {minDmg}-{maxDmg} Chain Damage to an adjacent enemy. This attack
# scores +{extraHit} hit for each time Wrask was attacked in this battle, to a maximum of
# {maxNrOfHits} hits total. Any leftover hits are allocated to remaining adjacent enemies,
# prioritising kills. »
#
# ⚠ « DANS LA BATAILLE » N'EST PAS UNE PARAPHRASE DE L'i2, C'EST L'OFFSET.
# `IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate` rend `*(uint *)(comp + 0x34)` ;
# `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackReceived` incremente +0x34
# ET +0x38 ; et `$$ResetAttacksReceivedThisTurn` n'efface QUE `+0x38` (`*(ulong*)(this+0x38) = 0`).
# Aucun des deux `$$ResetThisTurn` ni des trois `Reset*ThisTurn` n'ecrit +0x34. Le compteur PER-TOUR
# deja porte (`UnitComponent.times_attacked_this_turn`, gate du HP-floor) est donc `+0x38`, PAS ce
# compteur-ci : le total de bataille est un champ NEUF (`UnitComponent.total_times_attacked`),
# incremente au MEME site (`operations/minimal_health.py::record_attacked`).
#
# MECANIQUES DU KIT `worldTerminator` QUI NE PASSENT PAS PAR CETTE ABILITY (mesure, pas supposition) :
# `unit_map.py kit worldTerminator` attribue `dmg_bonus` et `dmg_reduction` a des TRAITS
# (`BlessingsOfKhorne`, `TerminatorArmour`) et `shield` a la PASSIVE `WrathfulDevotion` -- aucune des
# trois n'est lue par `BloodyFuryAbility` (ni son `.ctor`, ni `$$ExecuteBehaviour`, ni les deux
# `GetNum*Hits`, tous relus integralement). Le `shield` du kit est donc HORS de ce port ; il vit
# dans le pipeline de degat partage, du cote de la CIBLE.

BLOODY_FURY_ID = "BloodyFury"
BLOODY_FURY_PROFILE = "Chain"      # `AbilityConfiguration$$GetDamageProfile` (constants.damageProfile)


def bloody_fury_other_targets() -> Damageable:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$GetOtherTargets` -- MIRROR 1:1 :

        Damageable( AdjacentEnemies(unit = Owner@DSLSelectors+0x30, unique: 1, unitSelectionType: 3)
                    op_Subtraction Target@DSLSelectors+0x60 )

    La surcharge appelee est celle a **4 arguments** (`AdjacentEnemies(unit, unique, selectionType)`,
    tranchee sur les DEUX candidats du dump -- l'autre prend `(unit, unitTile, unique)`), dont le corps
    est `Enemies(unit, Units(AdjacentTiles(unit), unique, sel) op_Subtraction unit, sel)` : le MEME
    selecteur sert de centre ET de reference d'equipe. Cote port, `AdjacentEnemies(Owner())` filtre
    `team != ctx.caster.team` -- observationnellement egal ici (Owner == Caster pour une active), et
    c'est le slot `+0x30` qui est CITE, jamais `Caster@+0x48` que le natif n'utilise pas.

    ⚠ Le meme ensemble est relu, INLINE, par `$$ExecuteBehaviour` (le natif ne rappelle pas
    `$$GetOtherTargets`, il recopie l'expression) -> un seul foyer cote port."""
    return Damageable(Sub(AdjacentEnemies(Owner()), Target()))


def bloody_fury_hits_formula(nr_of_hits: int, extra_hit: int, max_nr_of_hits: int) -> Sum:
    """`...BloodyFuryAbility$$GetNumTotalHits` + `$$GetNumExtraHits` -- MIRROR 1:1 de l'arbre :

        Sum( Direct(nrOfHits),
             Min( Multiply(Direct(extraHit), TotalTimesAttacked(Owner@+0x30)),
                  Subtract(Direct(maxNrOfHits), Direct(nrOfHits)) ) )

    Les trois constantes sont resolues a la CONSTRUCTION (le natif fait
    `Direct(GetNumberConstant(...))`, donc un noeud a valeur figee) ; le seul terme runtime est
    `TotalTimesAttacked`, evalue par la feuille de chaine AVANT sa boucle -- comme le natif, qui fait
    `hits = (+0x98).Calculate(entities)` une fois, hors boucle.

    `DSLFormulas$$Subtract(a, b)` = `a - b` -> `Difference(a, b)` cote port. L'ordre des operandes est
    LU : `Subtract(this_00, pvVar4 = Direct(maxNrOfHits), pvVar3 = Direct(nrOfHits))`, donc bien
    `maxNrOfHits - nrOfHits` (l'inverse rendrait un `Min` negatif et TUERAIT le snowball)."""
    return Sum(Get(int(nr_of_hits)),
               Min(Multiply(Get(int(extra_hit)), TotalTimesAttacked(Owner())),
                   Difference(Get(int(max_nr_of_hits)), Get(int(nr_of_hits)))))


def bloody_fury_tree(state, hits_node, base_min: int, base_max: int,
                     pierce: int) -> ChainLeftOverHitsAttackDamage:
    """Arbre de `...BloodyFuryAbility$$ExecuteBehaviour` -- MIRROR 1:1 (cf. l'en-tete de section).

    `attackRangeType = Melee` (gameconfig) -> `is_melee=True`. Famille de factory = **ATTACK** : le
    nom natif est `...AttackDamage` et le `.ctor` alloue `ChainLeftOverHitsAttackDamageBehaviour`,
    qui construit le mold `AttackDamageBehaviour` par iteration -> `native_factory="attack"` (le
    defaut de la feuille).

    `extra_hits = 0` encode le `extraHitsAfterTargetKilled = **null**` du call-site natif :
    `$$GetLeftOverHits` fait `if (list.Count > 0 && (+0x90) != null) count += (+0x90).Calculate(...)`,
    donc un noeud nul et un noeud valant 0 rendent le MEME compte (meme encodage que 1048).

    RESIDU NOMME : le `DSLFormulas$$Cache` qui enveloppe `MinMaxDamage` n'est pas materialise -- la
    feuille partagee re-derive `(bmin, bmax)` par `ability_attack_params` et laisse
    `AttackDamageOperation.execute_ability_attack` rouler par coup, exactement comme 1006 et 1048.
    `Cache` ne change AUCUNE valeur (il memoise l'evaluation pour la duree du cast)."""
    chain = SortTargetsByDamagePrediction(
        state=state, attacker=Owner(), targets=bloody_fury_other_targets(),
        ability_type=int(ActiveAbilityType.BloodyFury),
        damage_min=base_min, damage_max=base_max,
        hits=1,                                   # `<DSLFormulas+0x20>` = `Direct(1)`, LU au ctor
        damage_profile=BLOODY_FURY_PROFILE, pierce=pierce, is_melee=True)
    return ChainLeftOverHitsAttackDamage(
        Owner(), Target(), chain, BLOODY_FURY_ID, BLOODY_FURY_PROFILE, hits_node, 0,
        is_melee=True)


class BloodyFuryAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BloodyFuryAbility$$ExecuteBehaviour`
    (id 1129, `worldTerminator` « Wrask », WorldEaters) -- face EXECUTION.

    `nrOfHits` coups `Chain` MELEE sur un ennemi ADJACENT, plus UN coup par attaque deja recue par
    Wrask DEPUIS LE DEBUT DE LA BATAILLE (plafond `maxNrOfHits` = 8 coups au total) ; les coups qui
    tombent sur le CADAVRE sont REPORTES sur les autres ennemis adjacents au CASTER, tries par
    priorite de kill. Le report lui-meme vit dans la feuille partagee
    `ChainLeftOverHitsAttackDamage` (`behaviours/combat.py`, mirror de
    `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` et de son
    `$$GetLeftOverHits`) ; ici, seulement la CONSTRUCTION de l'arbre.

    ⚠ Sans `extraHits`, un maillon ne peut REPORTER que si la cible meurt AVANT le dernier coup :
    `GetLeftOverHits` rend `max(0, H - k - 1) + 0`. Avec `nrOfHits = 1` et un Wrask jamais attaque,
    l'attaque fait UN coup et ne peut donc RIEN reporter -- le regime interessant demande un
    snowball non nul.

    Face DECISION deja portee : le playbook `BloodyFuryPlaybook`
    (`playbook/noncomparable/bloody_fury.py`, `1 + adj x 10`) et la formule de coups de
    `entities/abilities/active_ability.py::BloodyFuryAbility`. Ce port-ci est la face EXECUTION, qui
    etait un NO-OP SILENCIEUX (absente d'`ABILITY_CLASSES` : le cast etait choisi par la decision et
    l'execution l'ignorait -- 0 degat, 0 effet, aucune erreur).

    Renvoie {ability, caster, target, hits, chain, dsl}. Termine le tour (1129 hors des frozensets
    de `base.py`)."""

    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BloodyFury)   # 1129
    ABILITY_ID = BLOODY_FURY_ID

    # GATE DE CIBLE (#115) -- forme de ctor = **PRESET STATIQUE, SURCHARGE COPIE PURE** (la 3e des
    # six formes). `...BloodyFuryAbility$$.ctor` recopie les 0x40 octets du PRESET STATIQUE
    # `IdunBattle.Core.Services.TargetingOptions` statics `+0x40`, puis appelle
    # `TargetingOptions$$.ctor(&opts, &preset)` a **DEUX** arguments, puis
    # `AActiveAbility$$.ctor(this, &opts, 0)`.
    # ⚠ LE DECOMPILE RESSEMBLE A UN PRESET+FLAGS DONT LE LITTERAL AURAIT DISPARU : ce sont les XREFS
    # ENTRANTES qui tranchent. `BloodyFuryAbility$$.ctor` figure dans les appelants de la surcharge
    # a 2 arguments (avec Drachnyen/Doombolt/MurderousSwing/DakkaDakkaDakka/HeroicFusillade/
    # VigilanceEternal) et dans AUCUN des appelants de la surcharge PRESET+FLAGS. Le corps de cette
    # surcharge, RELU, est une copie verbatim des 8 qwords (`+0x00/+0x08/+0x10/+0x18/+0x1c/+0x20/
    # +0x28/+0x30/+0x38`) : elle n'ajoute AUCUN flag. Meme piege que `1029 Drachnyen` (#336).
    # Champs du preset, LUS dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     +0x40 (`isSelfCasting`)     = 0
    #     +0x48..+0x5f (`range`)      = recopie de `<TargetingRange statics>+0x30` = RANGE_ADJACENT
    #     +0x60 (`forceMeleeTarget`)  = 1 = `RangedBool.False`
    #     +0x68 (`rules`)             = 0x4000 = `TargetIsEnemy`, et RIEN d'autre
    # MASQUE EFFECTIF = `0x4000`. Concordant avec la mesure independante de
    # `docs/rl/case-302-4/tile-target-population.tsv` (ligne 1129, `state=measured`, `form=preset`,
    # `rules=0x4000`), et avec la valeur qui vivait dans `TARGETING_OPTIONS_UNPORTED` -- d'ou elle
    # MIGRE ici dans le meme commit (contrat de DISJONCTION).
    #     0x4000  TargetIsEnemy -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`) : refus sur
    #             soi-meme et sur un allie. SEUL bit du masque -- en particulier PAS de
    #             `TargetMatchesDynamicRule`, et 1129 n'a effectivement aucun
    #             `BloodyFuryAbility$$GetDynamicInvalidTargetReason` (absent du dump, et absent de
    #             `DYNAMIC_TARGET_RULE_UNPORTED` -- VERIFIE, pas suppose).
    # PORTEE : `RANGE_ADJACENT` (`onlyAdjacent = True` + `overrideRange = 1`) -> cible ADJACENTE
    # obligatoire, et la constante de config `range` n'est PAS consultee (1129 n'en a d'ailleurs
    # aucune). Coherent avec `attackRangeType = Melee` et l'i2 (« an adjacent enemy »).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = `0`
    # (`DirectTargetAttack`), LU au ctor (`AActiveAbility___ctor(this, &local_48, (void *)0x0)`) ->
    # transcrit dans la table `ABILITY_ATTACK_TYPE` (`abilities/attack_type.py`), qui est le registre
    # de cette donnee (pas un attribut de classe).

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(hits_node, base_min, base_max, pierce)`.

        Les trois constantes de l'arbre de coups viennent de `GetNumberConstant` (constantes de
        config, pas de variables per-niveau) ; les bornes et le percage du profil viennent du foyer
        partage `ability_attack_params` (mirror `AActiveAbility$$MinMaxDamage` / `GetDamageProfile`).
        Le `hits` que rend `ability_attack_params` (= `nrOfHits`) est IGNORE ici : le natif n'appelle
        pas `GetHits`, il monte `GetNumTotalHits`."""
        nr_of_hits = int(ability_var(self.ABILITY_ID, "nrOfHits", is_constant=True) or 1)
        extra_hit = int(ability_var(self.ABILITY_ID, "extraHit", is_constant=True) or 0)
        max_hits = int(ability_var(self.ABILITY_ID, "maxNrOfHits", is_constant=True) or nr_of_hits)
        base_min, base_max, pierce, _cfg_hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, BLOODY_FURY_PROFILE, ranged=False)
        return (bloody_fury_hits_formula(nr_of_hits, extra_hit, max_hits),
                int(base_min), int(base_max), int(pierce))

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        hits_node, base_min, base_max, pierce = self._params(state, caster_id)
        # DIAGNOSTIC : le compte de coups tel que la feuille l'evaluera -- lu AVANT l'execution,
        # comme le natif (`hits = (+0x98).Calculate(entities)` hors boucle). L'evaluer apres
        # rapporterait une valeur qui n'a pas servi si le compteur bougeait pendant le cast.
        hits = int(hits_node.evaluate(entities))
        ectx = ExecutionContext(state=state, rng=state.rng)
        bloody_fury_tree(state, hits_node, base_min, base_max, pierce).execute(entities, ectx)
        chain = next((p["chain"] for n, p in ectx.emitted if n == "ChainLeftOverHits"), [])
        return {"ability": BLOODY_FURY_ID, "caster": caster_id, "target": target_id,
                "hits": hits, "chain": chain, "dsl": True}


# Les trois constantes de config LUES au decompile de `$$GetNumTotalHits`/`$$GetNumExtraHits`,
# nommees (regle « un entier qui DESIGNE passe par un ENUM ») : `GetNumberConstant(0x2f)`,
# `GetNumberConstant(0x2b)` et `GetNumberConstant(0x48)`.
assert (int(AbilityConstantType.nrOfHits) == 0x2F
        and int(AbilityConstantType.extraHit) == 0x2B
        and int(AbilityConstantType.maxNrOfHits) == 0x48)
