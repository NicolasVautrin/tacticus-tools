# Case-217 — Stormcaller (active 1113, Njal spaceStormcaller) : face COMBAT

**Statut : LIVRÉ + VALIDÉ LIVE (probe 2/2 bit-exact + agreement 31337 4×100 %).** Build `gqfc5mff6c`,
session 2026-07-23. Complément COMBAT de la face DECISION déjà portée (#34/#115 :
`StormcallerPlaybook.EvaluateNonComparable @181160ff0`, `playbook/noncomparable/stormcaller.py`).
Avant #217 : 1113 absent d'`ABILITY_CLASSES` → **NO-OP silencieux** à CHAQUE walk 31337 (step 11,
u89 ab=1113) → divergence d'état invisible (0 dégât, 0 glace, 0 stun).

## 1. Artefact natif (RE décompilé, VAs)

`StormcallerAbility.ExecuteBehaviour @18120cc20` = 3 behaviours chaînés (`AbilityBehaviour.
op_Addition`) puis `AActiveAbility.Execute` (PLAIN, pas atomic) :

1. **AddEffect(0x11=Ice, stateRef, source=Owner@0x148, AdjacentTiles(TargetTiles@0x190) +
   TargetTiles@0x190, Nullable ZÉROÉ)** → glace la tuile de la cible + son ring-1 (== `GetAddIceTiles
   @18120cf70`, l'accesseur public consommé par la face DECISION). Durée = défaut
   `DefaultAmountOfRounds(0x11)=2` (@181559ff0, comme case-35).
2. **AttackWithAbilityDamage(caster@0x160, Cache(UnitsOnTilesWithEffect(Enemies(Owner@0x148,
   @0x80, 3), 0x11)), MinMaxDamage, DamageProfileFromConfig=Psychic, ConfigConst(0x2f)=3,
   AbilityOrEffect(1113))** → 3× Psychic (pierce 100, NoBlocking) sur **CHAQUE ennemi debout sur une
   tuile GLACÉE** — évalué APRÈS la pose [1] → la zone fraîche compte ET toute glace antérieure
   (LordOfTempests, cast précédent). Overload @180de9dd0 → core @180de9e50 (xref call-site 18120cdfc)
   = **le même nœud que SpiritLeech @181209a9f** → pipeline `execute_ability_attack` (MinMax roll +
   crit + block), déjà bit-exact.
3. **AddEffect(0x48a=1162 Stunned, stateRef, source=Owner@0x148, UnitsWithTrait(<MÊME Cache>, 4=Flying,
   3), TurnsFromRounds(1))** → stun 1 round des FLYING parmi les cibles attaquées (cache partagé
   [2]<->[3], mirror `Cache @180deb0d0`).

`UnitsOnTilesWithEffect @180dffc50` = `FromTrigger(source, <prédicat effectType@+0x20 sur la tuile>)`
(ctor gshared mislabelé ghidra — structure lue). Ctor @18120cfc0 = sur-flag TargetingOptions
(0x2_00000000), décision-side only. Kit gameconfig `Stormcaller` : Psychic, range 3, nrOfHits 3,
minDmg/maxDmg[level] rarity-affected.

## 2. Port (mirror 1:1)

- **`engine/runner/abilities/loki/stormcaller.py`** (NOUVEAU) : `stormcaller_get_add_ice_tiles()`
  (mirror @18120cf70 = `Union(AdjacentTiles(Target()), Tiles(Target()))`), `stormcaller_tree()`
  (les 3 volets, `op_add`), `StormcallerAbility` — enregistré `ABILITY_CLASSES[1113]` (handler.py).
- **`entities/selectors.py` : `UnitsOnTilesWithEffect`** (NOUVEAU primitif DSL @180dffc50) — filtre
  unit-domain par « la tuile de l'unité porte l'effet X », via la nouvelle capacité de contexte
  **`DslContext.tile_has_effect`** (dsl/base.py) wirée par `entities_from_state` sur `state.effects`
  (même clé tile-id que la pose `AddEffectOperation`, case-35).
- **Gate snowball MESURÉ + fixé (#217/#35-résidu)** : `execute_ability_attack` threade désormais
  `is_normal_attack=False` côté ATTAQUANT (`attacker_modifiers`, damage_model.py) — symétrique du
  #112 défenseur. Effets impactés (tous IsNormalAttack-gatés au natif) : LordOfTempests_ExtraDamage
  (@180f569a0), FeederTendrils, CrushingStrike. Le vecteur `execute_normal_like` reste défaut True
  (smite Psyker = kind 1013 = attaque-normale).

## 3. Validation (`probe_217_stormcaller.py`, PASS 2/2 ; replay-diff pattern case-35)

- **A (seed 21701, cast d=3, baseline count=0)** : glace live == offline == zone 5/5 ((6,7)+ring
  on-board) ; dégâts BIT-EXACT sur LES DEUX ennemis en un cast (WingedPrime 1524, Warden 1668 —
  preuve multi-cible « tous les ennemis sur glace ») ; stun Flying live==offline==True (WingedPrime),
  jamais sur le contrôle (necroWarden).
- **B (seed 21702, DISCRIMINANT snowball)** : round 1 = normale d=2 (le passif case-35 glace la tuile
  de la victime + celle du splash smite — branche 2 observée live) ; round 2 = drive Njal ADJACENT à
  la glace (count_pre=1 → effet `LordOfTempests_ExtraDamage` IsActive → **hydraté offline**) ; cast
  1113 à d=1 → count=3 à l'attaque. **AVANT fix** : offline 5271/5270 vs live 1671/1670 = écart
  exactement extraDmg(400)×3 hexes×3 hits → le natif N'applique PAS le snowball aux attaques
  d'ability. **APRÈS fix** : bit-exact 1671/1670. Glace/stun OK.
- **Zéro-régression** : `engine_agreement_stages --build --seeds 31337` = **4 étages 100 %**
  (prediction 10/10, utilité 10/10, ability 13/13 — dont step 11 ab=1113 —, move 18/18, aval du cast
  EXACT jusqu'au step 19) ; `test_lord_of_tempests_ice_live` 2/2 (snowball attaque NORMALE intact) ;
  `test_effect_stun_live` 1/1 (ability melee) ; `test_damage_roll_live` 2/2 (foyer partagé).

## 4. Résidus (non bloquants)

- **Conséquences AVAL des tuiles Ice toujours GATE** (pré-existant, terrain-effects.md §2) : blocage
  mouvement (`NotBlockingMovementOfTraits(0x11)`, #131 déféré faute de board jouable) et crit-bonus
  (`IceEffect.CreateEffectDamageBonusForAttack @180f44940`, direction/sélecteur à trancher). La POSE
  est réelle (état `state.effects` par tile-id) → ces mécaniques se brancheront dessus sans retouche.
- **Stun sur cadavre** : si un Flying meurt sous les 3 hits, le natif applique-t-il le Stun à
  l'entité morte ? Non mesuré (probe HP 300k, personne ne meurt) ; le port poserait l'effet (no-op
  observable). Micro-résidu.
- **BigTarget multi-tuile** : `UnitsOnTilesWithEffect` teste la MainTile seule (même réduction que
  `Units`/`_within`) — une unité 2-tuiles dont SEULE la tuile secondaire est glacée divergerait.
  Non couvert (aucun BigTarget dans les scénarios).
- **Refresh de durée sur re-pose** : AddEffect sur tuile déjà glacée = no-op port (gate
  already-present) vs `UpdateExistingEffect` natif (refresh possible du remaining) — pré-existant
  case-35, non mesuré ici (les diffs de NOUVELLES tuiles matchent).
- **`is_normal_attack=False` non threadé** sur `final_justice.py` (Blast death-trigger) ni
  `execute_normal_like` — hors périmètre mesuré ; à trancher si un carrier IsNormalAttack-gaté
  croise ces vecteurs.

## VAs
`StormcallerAbility.{ExecuteBehaviour @18120cc20, GetAddIceTiles @18120cf70, .ctor @18120cfc0}` ·
`DSLFactory.UnitsOnTilesWithEffect @180dffc50` · `DSLFactory.AttackWithAbilityDamage @180de9dd0 →
core @180de9e50` (== SpiritLeech @181209a9f) · `DSLFactory.UnitsWithTrait @180e00b10`
(UnitsWithFlagSelector flag=1) · `DSLFactory.Cache @180deb0d0` · `LordOfTempests_ExtraDamageEffect.
{CreateEffectDamageBonusForAttack @180f569a0, GetHexesIncreasingDamage @180f56b40}` (gate mesuré) ·
`StaticBattleRules.Effect.DefaultAmountOfRounds @181559ff0` · contexte sélecteurs `0x148 Owner ·
0x160 Caster · 0x178 Target · 0x190 TargetTiles` (runner-engine.md §654).
