"""Abilities actives WorldEaters (porteurs `world*`). Module DEDIE (isolation de faction ; org native =
1 classe par ability). RE ghidra gqfc5mff6c (VAs citees). Case-220 §6.3 (docs/rl/case-220/world-eaters.md).

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
  `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (XREF callees), PAS `AttackWithAbilityDamage` -> famille
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
  `IdunBattleLogic.Entities.DSLFactory$$AmountIsGreater` appelle un ctor que ghidra etiquette
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
- `native_factory="attack"` : l'`ExecuteBehaviour` appelle `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
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
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const, TargetsSelector, _is_alive, _units_of
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.behaviours import op_and, AtomicGroup, Group
from ...entities.formulas import Count, Get, If, RandomAmount
from ...entities.selectors.accessors import CasterTile, Target, TargetTile
from ...entities.selectors.geometry import Otherwise
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import (AdjacentEnemies, AdjacentUnits, And, SurroundingEnemies,
                                         Unobscured, non_steppable_or_object_units)
from ...entities.triggers import AmountIsGreater
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ...dsl.effects import ExecutionContext
from ...streams.group_type import GroupType
from .base import ActiveAbility, ability_attack_params
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
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
    caster ET a la cible (`And` = intersection ; caster/cible exclus). `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage,
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
    `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, XREF). Passif Skullsmasher + trait BlessingsOfKhorne (extra dmg)
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

    Overload natif `IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(df, ref, ...)` =
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
            best = first_by_damage_utility(self.state, [u.get("id") for u in candidates], roll, roll)
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
