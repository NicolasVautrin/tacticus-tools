"""Package `loki` — effets du namespace natif `IdunBattle.Entities.Effects.Loki` (+ `Effects.Idun`,
`Effects.Triggered.Loki`), **regroupés par FAMILLE DE HOOK de pipeline** (une classe va dans le fichier de
son hook primaire ; ses hooks secondaires voyagent avec elle). Découpé depuis l'ancien monolithe `loki.py`
(1447 l, 44 classes). Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra).

Ce `__init__` re-exporte la SURFACE PUBLIQUE COMPLETE (les 44 effets + `LIGHT_COVER_TILE_ID`) → tous les
imports externes (`from .loki import X` dans `factory.py`/`effects/__init__.py`, `from ...entities.effects.loki
import LIGHT_COVER_TILE_ID` dans `operations/damage.py`) restent INCHANGES.

- `extra_damage.py`      — bonus de dégât ATTAQUANT, volet DIRECT (l'effet buffe l'attaque de son porteur).
- `extra_damage_aura.py` — même famille, volet AURA (effet sur le SOURCE + `CreateTargetSelector` natif →
                           hooks `create_aura_*`, réévalués PAR CANDIDAT).
- `damage_reduction.py` — malus de dégât DÉFENSEUR (`create_effect_damage_malus_for_defense` + auras réduc).
- `hits.py`             — coups / blocs / pénétration-armure (hits/block/armor-pen).
- `status.py`           — stat-mods, composites (Stunned/Taunted), HP-floor, modificateurs multi-axes.
- `imperative.py`       — DoctrinaImperatives (Tan Gi'da) : Protector (+FixedArmor) / Conqueror (+dmg gate).
- `votann.py`           — Leagues of Votann (#113) : les 3 `DynamicStatModifierEffect` GÉNÉRIQUES du lot
                          (armure −, crit +, block +) + le canal PERÇAGE `GravitonRifle_ExtraPierce`.
- `darkangels.py`       — Dark Angels (case-117 phase 2) : canal PERÇAGE `Hailstrike_ExtraPierce` (1509,
                          porteur != source -> scaling resolu contre la SOURCE).
- `dark_angels_passives.py` — passifs `LionHelm` (1163, darkaAzrael : aura +dmg overwatch + aura
                          stat-mod block) et `FearedInterrogator` (1235, darkaAsmodai : marqueur de
                          cible + bonus degat/coups).
- `visions_of_heresy.py` — canal PERCAGE par STAT (`EXTRA_PIERCE_MELEE` 21 / `EXTRA_PIERCE_RANGED` 22)
                          conditionne aux PV : `VisionsOfHeresy_ExtraPierce{Melee,Ranged}` (1345/1346,
                          `bloodDeathCompany`). UNE classe native, deux `EffectType` (case-366-r1).
- `war_howl.py`         — buff d'ACTIVE a duree 1 tour de `spaceBlackmane` : `WarHowl_ExtraDamage_
                          Unstoppable` (1222), +extraDmg ET +extraCritChance sur la NORMALE MELEE
                          du porteur, + trait `Unstoppable` (case-366-r1).
- `inescapable_accuracy.py` — passif d'`eldarMauganRa` : `InescapableAccuracy_extraCritChance`
                          (1115), `InescapableAccuracy_extraCritDmg` (1116) et
                          `InescapableAccuracy_overrideHits` (1117) sur les attaques A DISTANCE
                          tant que le porteur n'a pas bouge (case-366-r1). TROIS canaux DIFFERENTS
                          (RollCritical / CalculateCriticalDamage / GetAttackHits), gate PARTAGE.
- `until_of_end_turn.py` — `UntilOfEndTurnEffect` : LE marqueur a duree du natif (aucune contribution ;
                          sa seule semantique est `CreateRemoveEffectTrigger` = `On(TurnEnd)`).
- `structural_analyser.py` — volet PORTEUR du passif de `tauDarkstrider` :
                          `StructuralAnalyser_Visual` (1174), cible Owner, ZERO contribution,
                          ACTIF tant qu'un allie est adjacent (toute faction) ou T'au a <= 2 hexes
                          (case-366-r1). SOEUR de `1156` (non porte), pas sa fille.
- `martial_superiority.py` — `MartialSuperiority_Visual` (1255, `templChampion`) : marqueur « riposte
                          armee », dont la SEULE semantique est `CreateActiveCondition =
                          NOT IsTurnOf(Owner)`. AUCUN consommateur logique de l'id (mesure
                          exhaustive) -> contribution de FIDELITE seule (case-366-r1).
- `crit_aura.py`        — auras stat-mod dont le `StatType` ecrit chez la cible est le CRIT
                          (`PathOfCommand_ExtraCrit` 1107, eldarAutarch). Meme interface
                          `aura_stat_modification_*` que le volet block de LionHelm."""
from __future__ import annotations


__all__ = []
