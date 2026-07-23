> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

### §6.2 AstraMilitarum (11 items, après exclusions 1028/1016/1142/IndirectFire)

**Constat transverse (PROUVÉ)** : 2 passifs MISSING de `kit-coverage.md` sont DÉJÀ portés côté
effet/prédiction — **SpotterReworked** (extra_damage.py:847/862, factory.py:139/140, canal aura)
et **Nightshroud** (dégât −364, damage_reduction.py:184, factory.py:224). Ne pas re-porter.

```
[SpotterReworked | astraOrdnance passif]  — PRÉDICTION FAITE ; reste mini-pose runner-face [opus]
VAs : CreateBehaviour @1811a1920 (AddEffect 1039+1064 self) ; effets @180f6c930/@180f6c680/@180f6c860
      + @180f6c980/@180f6cb40 ; playbook @181189050
```
```
[Nightshroud | astraPrimarisPsy passif]  — dégât PORTÉ ; reste pose aura turn-start [opus]
VAs : CreateBehaviour @181223400 ; CreateTrigger @181223590 (On 0x12 & IsTurnOf) ; effet @180f5c190/@180f5bff0
Pose = AddEffect(1046 Infiltrate + 1047 DmgReduction −364, amis ring-1 non-0x3ec, TurnsFromRounds(1)).
Prérequis : trigger turn-start runner (template LivingMetal) ; Infiltrate 0x416 = tranche séparée basse prio.
```
```
[AvalancheOfMuscle | astraBullgryn passif]  — [opus] direct trivial
VAs : effet @180f32cd0/@180f32b20 ; GetExtraDamage @18121a080 ; playbook @181163e60
ForAddition(OwnerIsCaster & IsNormalAttack & IsCharging, ConfigVar 8) — JUMEAU bit-à-bit de
FeederTendrils (extra_damage.py:111). 1 tranche (classe + factory + enum).
Risques : piège multiplier per-ability vs global (#68/#75) ; gate charge (has_moved).
```
```
[ToughToKill | astraDreir passif]  — [opus]+prérequis
VAs : Heal @1811a8b60/@1811a8c60 (On 0x13 turn-start, Heal ForRegenerate var 0x20) ;
      crit @180e25180/@180e24f00/@180e25040
(a) regen turn-start = [opus] direct (ToughToKill EST la référence native de Heal/ForRegenerate).
(b) crit REÇU : ForSubtraction(OwnerIsTarget, −35% CritChance / −1091 CritDamage) → PRÉREQUIS =
canal crit DÉFENSEUR (l'existant base.py:213/220 est attaquant-only). 2 tranches.
```
```
[1017 FragBomb | astraBullgryn]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811e04c0 ; GetAdjacentTargets @1811e0890 ; playbook @18113cdf0
Arbre : main = Units(targetTile) 6 hits ; splash = AdjacentUnits(targetTile,0,3) − caster (FRIENDLY-FIRE,
comme Stikkbomb) 3 hits ; le tout via SortedAttackSeries + ExecuteAtomic(0x43).
Prérequis : feuille SortedAttackSeries (série triée main+splash) ; résolution nœud AttackDamage vs
AttackWithAttackDamage. Risques : ordre exact dans la série (conso state.rng) ; friendly-fire.
```
```
[1027 PsychicMaelstrom | astraPrimarisPsy]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811fcc20 ; GetRollChanceForHitNumber @1811fcff0 ; playbook @181153b50
Arbre : hits = 1 + Maybe(75) + Maybe(50) + Maybe(25) + Maybe(10) (cascade bernoulli) →
AttackWithAbilityDamage(target, MinMax, profil, hits) ; ExecuteAtomic(0x46).
Prérequis : formule hit-count cascade en AMOUNT (le Maybe porté est un gate de behaviour, pas un
contributeur de count) + espérance prédiction (GetRollChanceForHitNumber). Risques : RNG-exact (seed
contrôlé) ; résolution feuille direct vs crit (cf. BasiliskBarrage).
```
```
[1026 BasiliskBarrage | astraOrdnance]  — [opus]+prérequis
VAs : ExecuteBehaviour @1811b8620 ; GetNumShellsGuaranteed @1811b8bf0 / Miss @1811b8db0 / Total
      @1811b8eb0 ; LaunchShells @1811b8fd0 ; playbook @181120bf0 (@181120170)
Arbre : scatter 5 obus en 3 anneaux — ring0 = PickRandomly(tiles cible, guaranteed) ; ring1 =
PickRandomly(cible+dist 1, total−(guaranteed+miss)) ; ring2 = PickRandomly(dist 2, miss) ;
AttackWithAbilityDamage(all, 2 hits) AtomicGroup(0x54). Comptages round-dependants (+1 obus
guaranteed par round terminé).
Prérequis : sélecteur TilesAtDistance (natif @181069760 — présent battle_query.py:170, pas en
TargetsSelector) ; formules shell round-based (à décompiler au port) ; résolution feuille
direct-vs-crit (AttackWithAbilityDamage porté = direct-only, behaviours.py:550 ; le natif passe
MinMax+profile → probablement variant crit @180de9fb0).
Risques : RNG-exact du scatter (GAP type Fragstorm #215 : le natif tire des HEX).
```
```
[1143 ForwardSpotter | astraOrdnanceBattery]  — [opus] structure, VALIDATION BLOQUÉE harnais MoW
VAs : ExecuteBehaviour @1811dfa90 ; PickTiles @1811dfd90 ; playbook @18113c010
Summon LE plus simple (1 astraSmnGuardsman adjacent au FRIENDLY ciblé, on-appearance PerformAIAttack —
pattern EXACT ScarabSummon). Prérequis : TilesUnitCanAttackFrom + Otherwise (contournables par
get_spawn_tile_selector). ⚠ porteur = Machine of War hors-plateau → rejoint le groupe Malleus/
DutyEternal (veille) tant que le cast-par-MoW en runner n'est pas prouvé.
```
```
[SummaryExecution | astraYarrick passif]  — moitié [opus] / moitié [fable]
VAs : Ability @181225a30/@181225ae0 ; AddBase @181225c10 ; effets @180f6fac0/@180f6f910/@180f6f8a0
      + @180f6fd40/@180f6fb90
(a) [opus] : +291 aux amis Battle-Fatigue = AddDynamicStatModifierEffectToOwner (template
DoctrinaImperatives, loki/imperative.py) gate trait BF.
(b) [fable] : intercepte la FUITE (On 0x34 & TriggeringAbilityIs 1025 flee) → Kill(ForDirectKill)
l'unité fuyarde + buff +146 first-flee. Prérequis : feuille Kill/ForDirectKill, vecteur flee-event,
gate first-time. Substrat BattleFatigue/FleeOperation EXISTE (runner/operations/behaviour.py).
Risques : harnais pour déclencher une vraie fuite BF.
```
```
[SwornProtector | astraCreed passif]  — [fable]
VAs : CreateBehaviour @1812260e0 ; CreateTrigger @1812263c0 (On 0x2b=targeted-by-enemy, first-time,
      pas de Kell vivant, hex libre) ; GetSpawnTile @181226750 ; gates @181226660/@1812266c0 ;
      playbook @181189a10 ; utility @1810e0c60
Mécanique : 1re fois que Creed est CIBLÉ par une attaque ennemie → Spawn astraSmnKell adjacent
(marker 1230) + If(CanSwitchPosition, TriggerAbility(kell, 0x433)) — échange de position + Kell
prend les coups. Prérequis ABSENTS : vecteur on-targeted (0x2b), opération d'ÉCHANGE de position,
REDIRECTION de dégât, feuille TriggerAbility, CanSwitchPosition, MainTileOfUnits/
AbilityHasAttackType/HasTriggeredAbilityBeenTriggered.
```
```
[1204 LeadingTheCharge | astraDreir]  — [fable], le plus lourd de la faction
VAs : ExecuteBehaviour @1811ee0b0 ; GetExtraPierceRatio @1811eed00 ; GetMoveTile @1811ef080 ;
      GetSummonTiles @1811ef320 ; playbook @1811491f0 ; utility @1810efed0
Arbre (ExecuteAtomic ~10 sous-behaviours) : Infiltrate + charge MoveUnit + effet PierceRatio
dynamique (+var par ami NORMAL vaincu — Multiply(var 0x3f, Count(Filter(AllUnits, IsNormalUnit &
AreFriends & HasBeenDefeated)))) + attaque 3 hits + summon ≤4 astraSmnDeathRider (qui attaquent
immédiatement AVEC le bonus pierce) + garde re-attaque (TimesAttackMadeThisTurn/SetCache).
Prérequis : prédicats IsNormalUnit/HasBeenDefeated/HasAdjacentEnemies ; effet Infiltrate ; canal
stat PierceRatio (26) honoré par le pipeline de dégât ; garde re-attaque. 3 tranches.
```

**Synthèse Astra** : quasi-couverts = SpotterReworked, Nightshroud ; [opus] direct = AvalancheOfMuscle ;
[opus]+prérequis = ToughToKill, FragBomb, PsychicMaelstrom, BasiliskBarrage ; bloqué harnais MoW =
ForwardSpotter ; mixte = SummaryExecution ; **[fable]** = SwornProtector, LeadingTheCharge.
HYPOTHÈSES : nécessité réelle des poses runner-face ; mapping direct-vs-crit des 2 overloads
AttackWith*Damage (@180de9c90 vs @180de9fb0) ; formules shell non décompilées en détail.
