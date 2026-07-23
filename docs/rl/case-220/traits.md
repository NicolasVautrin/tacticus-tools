> Tranche de la campagne de classification [case-220](../case-220-classification-campaign.md) — protocole, sommaire et ledger §T (prerequis transverses) dans le fichier maitre.

## §5 Traits communs §5.1 — ThrillSeekers, PrioritisedEfficiency, PutridExplosion, IndirectFire, BlessingsOfKhorne, MartialKatah, Vehicle

**Architecture de câblage relue** (prouvé) : `runner/operations/triggers/dispatch.py`
(`TRAIT_TRIGGERS`/`ABILITY_TRIGGERS`/`EFFECT_TRIGGERS`) pour les triggers ;
`entities/effects/factory.py` (`TRAIT_OWNER_EFFECTS`/`TRAIT_DERIVED_ABILITIES`/
`ABILITY_INIT_OWNER_EFFECTS`, `@18157e800`) pour les owner-effects ; `runner/snapshot.py:149`
seede `_seed_ability_owner_effects` sur les unités INITIALES (owner-effects de trait
always-active = captés live via `decisionView.effects`), `spawn.py` seede
`_seed_trait_owner_effects` sur les SUMMONS.

**Résultat : 4 traits sur 7 sont RIEN-À-FAIRE (fermés), 2 ports [opus], 1 [fable].**

```
[MartialKatah | custo* x4]  — CLOS, rien à faire
VAs : DmgBonus @180f58930 ; DmgReduction @180f58b30 ; trait 1055 -> effets 0x56b/0x56a
Déjà porté : MartialKatahDmgReduction (#105, -20% attaques normales reçues) + DmgBonus (+100% vs
   Summons, VALIDÉ bit-exact #57d), enregistrés factory + TRAIT_OWNER_EFFECTS. Prédiction ET runner OK.
```
```
[BlessingsOfKhorne | world* x11 | 1216]  — CLOS pour cette tâche
VAs : ModifiersEffect @180f34c50 / @180f34ae0 / N @180f34ea0 ; trait 1046
Déjà porté : ModifiersEffect + BeaconOfRage (#189) + OverwhelmingWrath (#190), VALIDÉS bit-exact
   (case-185, deux faces). N seedé par Scene._seed_battle_counters (decisionView defeatedByMelee).
⚠ N'est PAS un « enregistrement registre » : matérialisation par CAPTURE
   (AOwnerEffectSpecificTriggeredAbility) — l'ajouter à TRAIT_OWNER_EFFECTS serait FAUX.
Résiduel séparé (déjà documenté case-185) : runner full-sim ne track pas death-cause → N figé au seed.
```
```
[Vehicle | x8]  — CLOS (rattaché #131/B4)
VAs : NotBlockingMovementOfTraits @18155b370 ({Mounted, Vehicle 1029, Unstoppable 1042}) ;
      consommé par WalkPathfinder.GetTileBlockingReasons @180f2e9d0
Trait d'EXEMPTION pur. Déjà consommé comme target-trait (BeastSlayer extra_damage.py:448,
   damage_model.py:75). Exemption MOUVEMENT = même fondation déferrée/INVALIDABLE que Unstoppable
   (case-205 §3) : la porter maintenant = registered-but-dead → candidat de la tranche #131/B4.
```
```
[IndirectFire | x9]  — CLOS
VAs : trait 1005 ; CalculateTrenchReduction @181004830 ; obscuring @18109bad0 (mask 6)
Volet Trench DÉJÀ câblé (calculate_trench_reduction, damage_modifiers.py:289, gate
   attacker_has_indirect_fire — mirror @181004830). Volet « over obscuring » : le moteur est déjà
   OVER-PERMISSIF (obscuring non modélisé en légalité sauf Gauntlets ring-2) → rien à exempter
   pour un porteur. Le vrai gap = la restriction LoS pour les NON-porteurs (fondation séparée).
```
```
[PutridExplosion | deathPutrifier + npc x6 | 1074]  — PORT [opus], 1 tranche
VAs : CreateTrigger @1812248f0 (OnPreDeath2(1) & OwnerIsTarget) ; CreateBehaviour @181224710
Mécanique : à la mort du porteur → AttackWithAbilityDamage sur AdjacentUnits(owner) MOINS
   UnitsFromFaction("DeathGuard"), dégât = PercentageOf(maxHealth, 25%) profil Toxic.
Template : miroir structurel FinalJustice (@18121f180, TRAIT_TRIGGERS + fire_on_death=True),
   MAIS AoE ability-damage multi-cible au lieu d'attaque normale mono.
Prérequis : confirmer feuilles AttackWithAbilityDamage multi-cible + UnitsFromFaction (exclusion).
Risques : VALIDABLE (deathPutrifier lineup) ; exclusion faction + profil Toxic à vérifier.
```
```
[ThrillSeekers | emper* x5 | 1444]  — PORT [opus], 1-2 tranches
VAs : CreateTrigger @1811a8570 ; CreateBehaviour @1811a83b0 ; effet Thrilled 1434
Mécanique : trigger = (On(6) & IsFirstHitInSeries & OwnerIsCaster & Not(IsWounded(target)))
   OR (On(0xf) & OwnerIsTarget) = « attaque un ennemi PLEINE VIE » OU « subit du dégât ».
   Behaviour = AddStaticStatModifierEffect(owner, 1434, stat 9=CritChance, +15,
   TurnsFromRounds(1)) ; refresh ChangeEffectTurns si HasEffect, gate Not(HasFlag(owner,6)).
Prérequis : events 6/0xf à nommer (HYPOTHÈSE non lue au bit) ; vérifier l'impact +CritChance
   sur la prédiction ; rider overkill-sur-kill-au-crit (i2) = ajout pipeline kill.
Risques : si le crit n'est pas un axe de prédiction, gain oracle faible.
```
```
[PrioritisedEfficiency | votan* x7 | 1486]  — **[fable]**, le plus dur des 7
VAs : UpdateStanceAbility CreateTrigger @181114b80 (turn-start, effets 1479-1483) ;
      CounterAbility @1811143a0/@181114220 ; GetStanceDefiningUnit @181106dc0 ;
      GetSwitchStanceCounter @181106eb0 (GetPersistentData) ; effets @180f66060/@180f660b0/@180f661e0
Mécanique : MACHINE DE STANCE PARTAGÉE PAR ÉQUIPE. Compteur persistant sur la StanceDefiningUnit
   canonique, incrémenté à chaque active d'un ami porteur → parité = stance. Turn-start :
   applique à TOUS les porteurs. Offensive : +25% dégât + 1 Movement ; Défensive : -33% reçu.
Prérequis : substrat persistent-data (Add/GetPersistentData), StanceDefiningUnit, event 0xc
   (active-ability-used) dans le dispatch, +1 Movement dans la reachability. Proche du chantier
   DslContext live-state (#5).
Risques : team-shared state + timing turn-start = terrain à flip-flop.
```

**Synthèse** : fermer les 4 RIEN-À-FAIRE (retire ~32 porteurs de la liste §5.1) ; ports =
PutridExplosion (facile, validable) puis ThrillSeekers ; PrioritisedEfficiency = [fable] en dernier.
**Points validator** : PutridExplosion exclusion faction + substrat AoE ability-damage AVANT port ;
ThrillSeekers events 6/0xf hypothétiques ; ne PAS se faire happer par l'exemption mouvement/LoS
de Vehicle/IndirectFire (registered-but-dead).
