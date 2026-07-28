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
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...entities.behaviours import op_and, AtomicGroup
from ...entities.formulas import Count, Get, If
from ...entities.selectors import (Target, CasterTile, TargetTile, AdjacentUnits, AdjacentEnemies,
                                   And, Caster)
from ...entities.triggers import AmountIsGreater
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ...dsl.effects import ExecutionContext
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage, SubtractHealthPercent
from .targeting import RANGE_ADJACENT, RANGED_BOOL_FALSE, TargetingOptions
from .targeting_rule import TargetingRule as TR

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
        from ..components import StatsComponent
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
