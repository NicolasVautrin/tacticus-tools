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
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...entities.behaviours import op_and, AtomicGroup
from ...entities.selectors import (Target, CasterTile, TargetTile, AdjacentUnits, AdjacentEnemies,
                                   And, Caster)
from ...entities.active_ability_type import ActiveAbilityType
from ...dsl.effects import ExecutionContext
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage, SubtractHealthPercent
from .targeting import TargetingOptions
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
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy)

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
