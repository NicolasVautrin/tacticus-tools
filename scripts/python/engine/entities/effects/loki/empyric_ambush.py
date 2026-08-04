"""`EmpyricAmbush` (0x62a = **1578**) — la marque que `eldarLhykhis` pose sur sa cible, et qui
donne +crit aux HEROS allies qui la frappent. #589-r1-r1.

## IDENTITE — la config lue est l'ability ACTIVE 1232, relue BYTE A BYTE

`IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$.ctor` :

    mov edx, 0x4d0                                        ; 1232
    call IdunBattle.Core.AbilityOrEffect$$op_Implicit      ; surcharge ACTIVE -- tranchee par son
                                                          ;  ADRESSE : c'est celle dont le corps
                                                          ;  appelle `AbilityOrEffect$$
                                                          ;  set_ActiveAbility` (les surcharges
                                                          ;  portent toutes le meme nom)
    call IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect,
                                                      hasAutomaticActivation: 1)

`0x4d0 = 1232` est `ActiveAbilityType.EmpyricAmbush` (`enums.tsv`) ; l'EffectType, lui, vaut
**1578**. Les deux ne se confondent pas ici -- contrairement a `InescapableAccuracy`, ou l'id de
l'effet et celui de la triggered coincidaient. => la config est `abilities.EmpyricAmbush`, et les
variables sont indexees par le niveau de l'ability **ACTIVE** de la SOURCE (Lhykhis).

## POSE — sur la CIBLE, par la source, pour UN tour

`IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$ExecuteBehaviour` (mirror du
decompile, dans l'ordre) :

    FlyUnit( Caster@DSLSelectors+0x48,
             First(SortTilesByUtility(Randomize(CanAddUnit(AdjacentTiles(Target@+0x60))
                                                - <DSLSelectors+0x50>), Caster, 7, 0), 1, 0) )
  & If( <DSLTriggers+0x20>,
        AttackWithAttackDamage(Caster, Target, MinMaxDamage, GetDamageProfile, Get(GetHits), ...)
      & AddEffect( 0x62a = 1578 EmpyricAmbush, <abilityStateReference>,
                   source  = Owner@DSLSelectors+0x30,
                   targets = Target@DSLSelectors+0x60,
                   turns   = <DSLFormulas+0x20> = Direct(1) ) )

La surcharge d'`AddEffect` est celle a CINQ arguments `(effectType, abilityState, source, targets,
turns)` -- c'est ce qui met `source = Lhykhis` et `targets = l'ennemi frappe`. `<DSLFormulas+0x20>`
est `Direct(1)`, relu dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (qui pre-alloue `+0x18 =
Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`).
=> **l'effet dure UN tour**, ce n'est pas un permanent.

⚠ `EmpyricAmbushAbility` (1232) n'est PAS portee : ce module porte l'EFFET et son gate, pas la
pose. Cf. la section « ce qui n'est pas couvert » de `docs/rl/case-589-r1-r1-empyric-ambush.md`.

## LES DEUX CANAUX — meme trigger, deux variables

`IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$CreateCritChanceBonus` et
`$$CreateCritDamageBonus` ont le MEME corps a la variable pres :

    EffectBonus.ForAddition( get_OwnerIsTarget & IsValidAttackForBuff(),
                             ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )
    EffectBonus.ForAddition( get_OwnerIsTarget & IsValidAttackForBuff(),
                             ConfigVar(0x42 = extraCritDmg,    GetAbilityState(effect), config@+0x60) )

`0x41`/`0x42` = `AbilityVariableType` `65 = extraCritChance` / `66 = extraCritDmg` (`enums.tsv`).
Meme couple de canaux que `InescapableAccuracy` 1115/1116 : le premier decide SI le coup crite
(`DamagePrediction$$RollCritical` = `clamp(GetStat(9) + somme, 0, 100)`), le second de COMBIEN
(`DamagePrediction$$CalculateCriticalDamage` = `max(0, GetStat(10) + somme)`).

⚠ `variablesAffectedByRarityBonus` de `EmpyricAmbush` vaut `["minDmg", "maxDmg", "extraCritDmg"]` :
`extraCritChance` n'est **PAS** scalee par la rarete, `extraCritDmg` l'EST. Meme asymetrie que
1115/1116, et `ability_var` l'applique config-driven.

## `get_OwnerIsTarget` — le PORTEUR est le DEFENSEUR, et le canal l'y met

`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@DSLSelectors+0x30,
Target@DSLSelectors+0x60)` -- meme classe de trigger (`<DAT_1833a6968>`) que `get_OwnerIsActor`,
qui NOMME les slots (case-303/case-328).

Ce noeud n'est pas decoratif : les deux canaux crit natifs construisent leur `AbilityEntities` en
`(attacker, attacker, defender)` PUIS, dans la boucle sur les effets du board, **ECRASENT
`AbilityEntities+0x18` (`Owner`) par le porteur de l'effet courant** -- relu dans
`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` et
`$$GetCritDamageBonusFromEffects` (`Owner <- resolution d'entite depuis l'id enumere`, exactement
la boucle `effets x cibles` que `case-366-r1-blockhits-purgeresponse` a relue sur
`DamagePrediction$$GetAttackHits`). `get_OwnerIsTarget` demande donc : « le porteur de CET effet
est-il le defenseur du coup ? » -- vrai pour la marque, fausse pour tout autre porteur.

C'est ce meme fait qui a impose l'ELARGISSEMENT du balayage des deux canaux crit a
`board_effect_carriers` : un effet porte par la CIBLE etait auparavant hors de l'univers balaye
(cf. `entities/effects/__init__.py`).

## `IsValidAttackForBuff` — SEPT noeuds, et le sujet n'est PAS le porteur

`IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$IsValidAttackForBuff`, mirror de l'ordre du
decompile (les `op_BitwiseAnd`/`op_BitwiseOr`/`op_LogicalNot` sont ceux d'`AbilityTrigger`) :

    AreEnemies( Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60, 0 = ByCurrentTeam )
  & (   HasFaction( Caster, 8 = Aeldari, 3 )
      | AmountIsEqualOrGreater( TilesMovedThisTurn(Caster),
                                Direct(GetNumberConstant(0x51 = movement)) ) )
  & (   AreFriends( Caster, EffectSource(<DSLSelectors+0x38>), 0, anyEntity: false )
      & op_LogicalNot( AreEqual( Caster, EffectSource ) )
      & HasTrait( Caster, 0x10 = Hero ) )

Le SUJET de tous ces noeuds est `<DSLSelectors+0x48>` = **le CASTER de l'attaque en cours**, pas
l'`Owner` du porteur -- c'est le piege de cette famille (`case-589-r1` §4.4 : trois autres
call-sites de `TilesMovedThisTurn` ont pour sujet `<+0x30>` = Owner ; ne pas generaliser d'un
selecteur a l'autre). L'identification des slots est etablie de longue date et par plusieurs voies
independantes (`case-27` §« +0x30 = Owner, +0x48 = Caster, +0x60 = Target », `case-303`,
`case-328`, `case-334`), et `get_OwnerIsTarget` la recoupe ici meme (`AreEqual(+0x30, +0x60)`).

Resolutions (`enums.tsv`, jamais recopiees du decompile) : `UnitFaction 8 = Aeldari` ;
`UnitTrait 0x10 = 16 = Hero` ; `UnitTeamSelectionType 0 = ByCurrentTeam` ;
`AbilityConstantType 0x51 = 81 = movement`, dont la valeur est RELUE du gameconfig
(`abilities.EmpyricAmbush.constants["movement"]` = **4**), jamais codee en dur.

`AreEnemies` est un `op_LogicalNot(AreFriendsAbilityTrigger(...))` cote natif
(`IdunBattleLogic.Entities.DSLTriggers$$AreEnemies`), pas une classe propre.

## LE SEUIL — 4, au-DESSUS de la borne saturante de #589

C'est le seul des six consommateurs de `DSLFormulas$$TilesMovedThisTurn` dont le seuil puisse
basculer quand la beeline passe de la GEOMETRIE au `ConnectivityComponent` : `GetConnectedPathTo`
ne recoud que `if (GetDistance > 1)`, donc `min(n_G, n_C) >= 2` et tout seuil `<= 2` est deja
franchi AVANT le rebranchement (`case-589-r1` §2). `movement = 4` y echappe -- mesure : 22 couples
de `C1_74` basculent en regime `Fly`, 24 en `TeleportStrike`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect, tiles_moved_this_turn
from ..magnitude import ability_var

_ABILITY_ID = "EmpyricAmbush"      # ActiveAbilityType 0x4d0 = 1232 (active, eldarLhykhis)
_AELDARI = "Aeldari"               # UnitFaction 8
_HERO = "Hero"                     # UnitTrait 0x10 = 16


class EmpyricAmbushEffect(BaseEffect):
    """`EmpyricAmbush` (0x62a = 1578) — marque posee par `eldarLhykhis` sur la cible de son ability
    active, pour UN tour : les HEROS allies de Lhykhis (elle exclue) qui frappent l'unite marquee
    gagnent +`extraCritChance` de chance de crit et +`extraCritDmg` de degat de crit, a condition
    d'etre Aeldari OU d'avoir parcouru au moins `movement` (= 4) tuiles ce tour."""

    def is_valid_attack_for_buff(self, att_ctx: "Mapping | None" = None) -> bool:
        """MIRROR de `IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$IsValidAttackForBuff`,
        noeud par noeud, dans l'ordre du decompile :

            AreEnemies(Caster, Target, 0 = ByCurrentTeam)
          & ( HasFaction(Caster, 8 = Aeldari, 3)
              | AmountIsEqualOrGreater(TilesMovedThisTurn(Caster),
                                       Direct(GetNumberConstant(0x51 = movement))) )
          & ( AreFriends(Caster, EffectSource) & NOT AreEqual(Caster, EffectSource)
              & HasTrait(Caster, 0x10 = Hero) )

        Le SUJET de chaque noeud est `<DSLSelectors+0x48>` = le CASTER de l'attaque, donc les cles
        lues sont celles de l'ATTAQUANT -- jamais celles du porteur. Chaque cle est UN noeud natif,
        et une cle ABSENTE fait TAIRE son noeud (« present != applique ») :

          * `att_team` / `tgt_team`      -> `AreEnemies(Caster, Target)`. Non PROUVES ennemis =>
            ferme (le natif ne peut pas rendre vrai sans les deux equipes) ;
          * `att_faction`                -> `HasFaction(Caster, Aeldari)`. Le 3e argument natif
            (`selectionType = 3`, ecrit a `HasFactionTrigger+0x20`) regit l'agregation sur les
            unites RENDUES par le selecteur ; `Caster` en rend exactement UNE, donc il ne discrimine
            rien ici -- non porte, et c'est dit plutot que suppose ;
          * `tiles_moved_this_turn`      -> `TilesMovedThisTurn(Caster)`, lu par le foyer UNIQUE
            `effects.base.tiles_moved_this_turn` (tri-etat : `None` = non mesure, JAMAIS 0) ;
          * `att_traits`                 -> `HasTrait(Caster, Hero)` ;
          * `att_id` + `self.source`     -> `NOT AreEqual(Caster, EffectSource)` ;
          * `team_by_id` + `self.source` -> `AreFriends(Caster, EffectSource)`.

        `EffectSource(<DSLSelectors+0x38>)` = `IdunBattleLogic.Entities.DSLSelectors$$EffectSource`
        applique au slot `Effect` : la SOURCE de l'effet, c'est-a-dire `BaseEffect.source`
        (`EffectComponent` SourceUnit @+0x10), pas son porteur."""
        c = att_ctx or {}
        att_id, src = c.get("att_id"), self.source

        # --- AreEnemies(Caster@+0x48, Target@+0x60, 0 = ByCurrentTeam) -------------------------
        att_team, tgt_team = c.get("att_team"), c.get("tgt_team")
        if att_team is None or tgt_team is None or att_team == tgt_team:
            return False

        # --- AreFriends(Caster, EffectSource, 0, anyEntity: false) -----------------------------
        team_by_id = c.get("team_by_id") or {}
        src_team = team_by_id.get(src) if src is not None else None
        if src_team is None or src_team != att_team:
            return False

        # --- op_LogicalNot(AreEqual(Caster, EffectSource)) -------------------------------------
        if att_id is None or src is None or att_id == src:
            return False

        # --- HasTrait(Caster, 0x10 = Hero) -----------------------------------------------------
        att_traits = c.get("att_traits")
        if att_traits is None or _HERO not in att_traits:
            return False

        # --- HasFaction(Caster, 8 = Aeldari, 3)  |  TilesMovedThisTurn(Caster) >= movement ------
        if c.get("att_faction") == _AELDARI:
            return True
        n = tiles_moved_this_turn(c)                      # tri-etat : None = non mesure
        if n is None:
            return False
        k = ability_var(_ABILITY_ID, "movement", is_constant=True)   # GetNumberConstant(0x51)
        if k is None:
            return False
        return int(n) >= int(k)                           # AmountIsEqualOrGreater

    def _owner_is_target(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@+0x30,
        Target@+0x60)` -- « le PORTEUR de cet effet est-il le defenseur du coup ? ».

        `owner_id` est pose PAR PORTEUR par l'agregateur (`crit_*_bonus_from_effects`), mirror de
        l'ecriture `AbilityEntities+0x18 (Owner) <- le porteur de l'effet` que les deux canaux
        natifs font a chaque iteration. Identite NON PROUVEE (l'une des deux cles absente) => le
        noeud est FAUX, jamais permissif."""
        c = att_ctx or {}
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        return oid is not None and tid is not None and oid == tid

    def _bonus(self, var: str, att_ctx: "Mapping | None") -> "int | None":
        """Corps commun de `CreateCritChanceBonus` / `CreateCritDamageBonus` : les deux natifs sont
        le MEME code a l'`AbilityVariableType` pres (`0x41` vs `0x42`), donc un seul corps ici.

        `GetAbilityState(effect)` indexe la config de l'ability **ACTIVE** 1232 : le niveau est
        `active_ability_level`, repli `ability_level` puis stack `level` (l'effet est pose par une
        ACTIVE, cf. la surcharge d'`op_Implicit` relue en tete de module)."""
        if not self._owner_is_target(att_ctx):            # get_OwnerIsTarget
            return None
        if not self.is_valid_attack_for_buff(att_ctx):    # IsValidAttackForBuff()
            return None
        lvl = self.active_ability_level
        if lvl is None:
            lvl = self.ability_level if self.ability_level is not None else self.level
        n = ability_var(_ABILITY_ID, var, lvl, multiplier_pct=self.ability_variables_multiplier)
        return int(n) if n else None

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$CreateCritChanceBonus` :

            EffectBonus.ForAddition( get_OwnerIsTarget & IsValidAttackForBuff(),
                                     ConfigVar(0x41 = extraCritChance, GetAbilityState(effect),
                                               config@+0x60) )

        Le retour est un ENTIER (pas un `EffectBonus`) : le canal natif somme des scalaires
        (`GetCritChanceBonusFromEffects` accumule `addition - subtraction`), et son consommateur est
        `clamp(GetStat(9) + somme, 0, 100)` dans `DamagePrediction$$RollCritical`.

        `extraCritChance` n'est PAS dans `variablesAffectedByRarityBonus` -> aucun scaling de
        rarete ; `ability_var` applique cette regle config-driven."""
        return self._bonus("extraCritChance", att_ctx)    # ConfigVar 0x41

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattle.Entities.Effects.Loki.EmpyricAmbushEffect$$CreateCritDamageBonus` :

            EffectBonus.ForAddition( get_OwnerIsTarget & IsValidAttackForBuff(),
                                     ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect),
                                               config@+0x60) )

        Meme corps que son frere a la variable pres -- RELU au decompile, pas deduit. Le canal est
        l'AUTRE : `GetCritDamageBonusFromEffects` -> `max(0, GetStat(10) + somme)` dans
        `DamagePrediction$$CalculateCriticalDamage`. 1578 decide donc a la fois SI le coup crite et
        de COMBIEN, la ou 1115/1116 se partagent les deux roles.

        ⚠ `extraCritDmg` EST dans `variablesAffectedByRarityBonus` (contrairement a
        `extraCritChance`) : `ability_var` applique le multiplicateur de rarete."""
        return self._bonus("extraCritDmg", att_ctx)       # ConfigVar 0x42
