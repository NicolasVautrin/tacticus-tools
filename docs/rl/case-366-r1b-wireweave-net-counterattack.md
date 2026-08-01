# case-366-r1b — `1111 WireweaveNet_CounterAttack` : une riposte PRE-HIT, armée par le TOUR

**Question, binaire.** Le port fait-il partir la contre-attaque de Calandis exactement quand le
natif la fait partir, pour exactement le même montant — et se tait-il exactement quand le natif se
tait ?

**Réponse : OUI, confronté LIVE et bit-exact des deux côtés, après DEUX corrections que seule
l'adversarialité a trouvées** — un foyer PARTAGÉ qui écrasait le flag `IsActive` (§7bis), et une
entrée de seed que j'avais posée par analogie et qui cassait la garde du voisin (§7ter). Porteur
`eldarRanger` (Calandis), HERO **au pool** ; voie directe, ni greffe npc, ni injection catalogue,
ni relique.

i2 : « The first time Calandis is targeted by a normal melee attack during the enemy's turn, the
attacker immediately takes 2x 873-1310 Piercing Damage. If the attacker is eliminated, their melee
attack is not executed. »

## 1. Le canal, établi à SA PROPRE SOURCE — un EFFET, pas une triggered-ability

L'hypothèse « même canal que le voisin `1110` » est **fausse** : `1110` est une lecture par coup
côté défense (`EffectBonus.ForSubtraction`), `1111` n'a **aucun canal de bonus**. Sa chaîne, lue
dans `data/symbols/<build>/frida/classes.tsv` :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.WireweaveNetAbility
        : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility : BaseTriggeredAbility
    IdunBattle.Entities.Effects.Loki.WireweaveNet_CounterAttackEffect
        : IdunBattle.Entities.Effects.CounterAttackEffect
        : IdunBattle.Entities.Effects.PlayerTurnEffect : BaseEffect

Le comportement vit donc dans **trois `Triggered()` portés par l'entité-EFFET**, pas dans un
`CreateTrigger` d'ability. `1111` est aussi un cas d'école de **qualification d'enum** : le même
nombre est l'`EffectType` rendu par `WireweaveNetAbility$$GetEffectType` (`return 0x457`) **et** le
`TriggeredAbilityType` que le `.ctor` de l'effet bake — deux enums, une valeur.

## 2. Le `.ctor` : trois littéraux, tous lus à l'ASSEMBLEUR

`WireweaveNet_CounterAttackEffect$$.ctor` (le décompilateur masque l'immédiat) :

    mov edx, 0x457                              ; 1111
    call AbilityOrEffect$$op_Implicit           ; surcharge tranchée par SON CORPS
    mov edx, 1 ; mov r8d, 2
    call CounterAttackEffect$$.ctor             ; (turnsEnabled, activationFrequency, sourceAbility)

* La surcharge d'`op_Implicit` visée par le `call` appelle **`set_TriggeredAbility`** ; les trois
  homonymes écrivent `set_ActiveAbility` / `set_Effect` / un 4e champ. C'est la lecture qui qualifie
  le `0x457` en `TriggeredAbilityType` — jamais le nom de la fonction.
* `PlayerTurnEffect$$.ctor` écrit `+0x484 = turnsEnabled`, `+0x480 = activationFrequency`, et passe
  `hasAutomaticActivation = (activationFrequency == 0)` à `BaseEffect$$.ctor` ⇒ **FALSE** : l'effet
  ne s'arme PAS tout seul à la pose.

| littéral | consommateur | conséquence |
|---|---|---|
| `turnsEnabled = 1` | `PlayerTurnEffect$$IsEnabledTurnType` branche `else` | `NOT <DSLTriggers+0x28>` = **`NOT IsTurnOf(Owner)`** ⇒ fenêtre = tour ENNEMI |
| `activationFrequency = 2` | `$$CreateHandleTriggerAbilitiesInternal`, branche `== 2` | `On(0x12) & IsTurnOf(Owner) -> Deactivate` + `On(0x17) & IsTurnOf(Owner) -> Activate` |
| `hasAutomaticActivation = False` | `BaseEffect$$.ctor` | c'est le `If(NOT IsTurnOf(Owner), ActivateEffect)` de la pose qui arme, pas la pose elle-même |

(`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` : identification établie par `case-366-r1` §2 ;
`<DSLTriggers+0x70>` et `+0x40` = deux instances d'un trigger sans champ, `size 16` ⇒ `YesTrigger`,
et `+0x48 = NOT` de la même classe.)

## 3. La POSE

    AOwnerEffectTriggeredAbility$$CreateTrigger = OnOwnerSpecificAbilityInit(this.Id@+0x10)
    WireweaveNetAbility$$CreateBehaviour        =
          AddEffect(0x457, <AbilityStateReference>, source=Owner@<Sel+0x30>,
                    targets=Owner@<Sel+0x30>, <durée ZÉROÉE>)
        + If( NOT <DSLTriggers+0x28>, ActivateEffect(Owner, 0x457) )

Le second terme est littéralement le corps de `WireweaveNetAbility$$ActivateEffectIfOwnerTurn`,
inliné. L'effet est donc un **owner-effect permanent posé à l'init**, et il est **INACTIF pendant le
tour de son porteur** — donc **absent du canal `decisionView` par DÉFAUT** (actifs seuls).

**Il n'est pourtant PAS inscrit à `factory.ABILITY_INIT_OWNER_EFFECTS`, et c'est une décision
mesurée** (§7ter). Raison courte : sur le canal COMBAT, « la riposte peut partir » ⟺ « l'instance
est ARMÉE » ⟺ « le canal par défaut la publie ». L'instance INACTIVE, contrairement à celles
d'`AnvilShield`/`HammerOfWrath` (dont un gate `HasEffect` doit la voir), ne sert à rien.

## 4. La RIPOSTE

    CounterAttackEffect$$CreateTargetTrigger =
          GetCounterAttackTrigger()               # vtable +0x778 -> On(0x2a = PreUnitAbility, true)
        & <DSLTriggers+0x20>                      # conjoint SINGLETON non qualifié (§6)
        & GetCounterAttackCondition()             # vtable +0x788
        & AreEnemies(Caster@<Sel+0x48>, Owner@<Sel+0x30>, 0)
        & IsAlive(Caster@<Sel+0x48>)

    WireweaveNet_CounterAttackEffect$$GetCounterAttackCondition =
          get_OwnerOrOwnerTileIsTarget & IsMeleeAttack & IsNormalAttack

    CounterAttackEffect$$CreateTargetTriggerBehaviour =
          GetCounterAttackBehaviour(effect) & DeactivateEffect(effect)     # gate vtable +0x738

`0x2a = 42 = PreUnitAbility` — **vérifié contre `frida/enums.tsv`**, pas déduit (`43 = UnitHealed` :
le commentaire `# On(0x2b = 43, 1)` de `martial_superiority.py` est une coquille, son code utilise
bien l'enum). La riposte part donc **AVANT** l'attaque entrante, et le « If the attacker is
eliminated, their melee attack is not executed » d'i2 est rendu par le **gate ACTEUR-MORT
post-`On(PreUnitAbility)`** d'`ActiveAbilityOperation$$ExecuteInternal`, déjà porté par #133 sur les
deux voies.

**`IsNormalAttack`, PAS `IsDirectTargetAttack`** — c'est le point qui sépare cette riposte de celle
de `MartialSuperiority`, dont le gate (`AbilityHasAttackType(DirectTargetAttack) | IsNormalAttack`)
est **strictement plus large**. Une ACTIVE de mêlée réveille Jaeger, pas Calandis. Recopier le
voisin aurait donné un port permissif.

**Le `& DeactivateEffect(effect)` porte le « the FIRST time »**, et son gate (`vtable +0x738`) est un
stub **`return 1`** : le PREMIER membre du groupe `CounterAttackEffect` dans la table
`methodPointers` (corps `mov eax,1 ; ret`, partagé — l'unique propriétaire nommé est
`UnityEngine.U2D.IK.Solver2D$$DoValidate`). Le 3e `Triggered()` de `PlayerTurnEffect`
(`On(0x2e = UnitResurrected) & OwnerIsTarget -> Activate`) est, lui, gaté par un stub `return 0`
⇒ **non bâti** (et sans observable : il ne concerne que la résurrection du porteur).

## 5. Le DÉGÂT

    GetCounterAttackBehaviour = AttackDamage(effect, GetDamageProfile(cfg), GetNumberConstant(cfg, 0x2f))
    CounterAttackEffect$$AttackDamage = AttackWithAttackDamage(
        caster  = Owner@<Sel+0x30>,            targets = GetCounterAttackTargets() = <Sel+0x48> (Caster),
        amount  = GetDamage() = GetMinMaxDamage(0),
        profile, hits,                          source = this.SourceAbility (= TriggeredAbility 1111))

gameconfig `WireweaveNet` : `attackRangeType = Melee`, `constants = {damageProfile: "Piercing",
nrOfHits: "2"}`, `variables = {minDmg, maxDmg}` (65 paliers) avec
`variablesAffectedByRarityBonus = ["minDmg","maxDmg"]`. Niveau 50 : **665-997** avant multiplicateur
de rareté ; niveau 65 : 873-1310 (= les chiffres i2). `WireweaveNet` est le **PASSIF** d'`eldarRanger`
(`unit_map kit`) ⇒ `level_slot="passive"` — pas le piège de `#366-r1`, où la magnitude était indexée
par le niveau de l'ACTIVE.

## 6. La face DÉCISION — et un conjoint natif DÉGÉNÉRÉ

`IdunBattle.AI.Utilities.WireweaveNet_FirstAttack` (`UtilityType` **55** sur ce build ; 54 sur
`gqfc5mff6c`, d'où l'écriture `key-0x36` des docs) est un terme de
`ComparablePlaybook<T>$$CalculateActionUtility`, par (tuile caster, cible).
`<EvaluateAttackInSteps>d__1$$MoveNext` :

    tile = case.CasterPosition.MainTile ; if (tile == null) yield break
    if (IsAdjacentTo(case.CasterPosition.MainTile, case.CasterPosition.MainTile))
        if (GetOwnedEffects(case.Target, state, (EffectType?)0x457).Any(e => e.IsActive))
            yield return GetUtilityValue("WIREWEAVENET_AdjacentActiveEffect")

**Les DEUX opérandes d'`IsAdjacentTo` sortent du MÊME champ** : à l'assembleur, les trois appels à
`UnitPosition$$get_MainTile` sont précédés du MÊME `add rcx, 0x18` sur l'objet `UtilityAttackCase`
(aucun `mov rcx,[...+0x20]`). Et `MovementUtil$$AreTilesAdjacent` court-circuite explicitement
`tile1 == tile2 -> true` (avec `|Δélévation| = 0 < 2`). ⇒ **le conjoint est VRAI dès que
`CasterPosition.MainTile` existe : ce n'est PAS un gate d'adjacence porteur/cible.** La lecture
« cible adjacente ET cible possédant l'effet 1111 » de `docs/rl/playbook/architecture.md` (faite sur
`gqfc5mff6c`) sur-lisait ce conjoint ; elle est corrigée là-bas. Conséquence pratique : le malus
s'applique **aussi** à une attaque à distance contre une Calandis armée — le nom de la clé BC dit
l'inverse, mais le nom n'est pas le code.

Poids : `BC.Utilities.Default.WireweaveNet_FirstAttack.WIREWEAVENET_AdjacentActiveEffect` = **-30**.
Le prédicat `Any` est `e => e.GetComponent<EffectComponent>().IsActive` (lambda `b__1_0`, corps
`return *(byte*)(comp + 0x5c)`) ⇒ côté port on lit `Scene.effects(uid)`
(= `EffectsState.active_effects`, qui conjugue présence ET flag), **surtout pas** `has_effect`.

## 7. Ce qui est VALIDÉ, et par quoi

**Harnais déterministe OFFLINE** — `probe_366_r1b_wireweave_gates.py`, **10 étapes, toutes vertes** :

| étape | ce qui est exercé | mesure |
|---|---|---|
| [0] | registre (3 `Triggered()`, classe, seed) | `EFFECT_TRIGGERS[1111]` = 3 classes |
| [1] | cas POSITIF | riposte **1542** sur l'attaquant, `per_hit=[703, 839]`, **2** coups |
| [2] | `& DeactivateEffect` | 2e attaque du MÊME tour → **0** |
| [3] | fenêtre `NOT IsTurnOf(Owner)` | tour du porteur → **0** |
| [4] | `IsMeleeAttack` (POSITIONNEL) | attaquant à 2 hexes → **0** |
| [5] | `IsNormalAttack` | ACTIVE `1131` DirectTargetAttack → **0** |
| [6] | `AreEnemies` | attaquant ALLIÉ → **0** |
| [7] | `get_OwnerOrOwnerTileIsTarget` | attaque visant un autre allié → instance de Calandis INTACTE |
| [8] | machine à états | `On(0x12)` → reste OFF ; `On(0x17)` du porteur → ON ; tour ennemi suivant → riposte **1633** ; `On(0x17)` de l'ENNEMI → reste OFF |
| [9] | face DÉCISION | `-30` ssi filet armé ; `0` sans filet ; `0` si `MainTile == null` |
| [10] | prédicat `Any(e => e.IsActive)` | filet CONSOMMÉ (présent mais éteint) → prédicat `False`, terme `0` (case-415-r1) |

**Cliquets** : `probe_181` (98/98, 0 manquante), `probe_120 --step 0` (98 abilities, 0 littéral
manquant, et ses 5 étapes du vecteur `On(PreUnitAbility)` restent vertes AVEC les nouveaux triggers
inscrits), `probe_273 --only-scan`, `probe_365`. **Non-régression offline** : 51 tests
(`test_effect_trigger_channels`, les deux `test_overwatch_*` — même famille `PlayerTurnEffect`,
même machine à états —, `test_ability_registry_ratchet`, `test_366_effects_registry_partition`,
`test_366r1_carrier_active_level`) + 48 tests playbook/prédiction offline.

**Confrontation LIVE** — `probe_366_r1b_wireweave_net.py`, board `MC1_67`, seed 777, crit/block
neutralisés, `passiveAbilityLevel = 50`, `multiplier = 180` ⇒ bornes RAW **1197-1795** :

| montage | live | port (même capture, même flux MT) | verdict |
|---|---|---|---|
| **`pos`** (orksNob, dist 1, tour ennemi) — riposte sur l'attaquant | `[1272, 1599]` | idem | **MATCH** |
| — attaque entrante sur Calandis | `[2691, 3446, 3065, 3443]` | idem | **MATCH** |
| — PV finaux (Calandis / attaquant) | `987354` / `987938` | `987354` / `987938` | **bit-exact** |
| — CONTRE-ÉPREUVE offline (1111 retiré) | — | Calandis `990858`, attaquant **intact** | le régime MORD |
| — CONTREFACTUEL de tour (`current_player` = Calandis) | — | identique à la contre-épreuve | la fenêtre FERME |
| **`--neg-ranged`** (necroWarden, dist 2), filet ARMÉ | riposte `[]` | riposte `[]` | **MATCH** |
| **`--two-attackers`** — riposte au 1ᵉʳ | `[2343, 2294]` | idem | **MATCH** |
| — riposte au 2ᵉ, MÊME tour ennemi | `[]` (il frappe pourtant : `[1520]` sur Calandis) | `[]` | **MATCH** |

Les deux coups de riposte tombent dans **[1197, 1795]** — c'est la **garde d'ATTRIBUTION**, et elle
est indispensable : Calandis porte AUSSI le trait `Overwatch`, dont l'auto-attaque frappe le MÊME
adversaire sur un AUTRE vecteur (le voisin a mesuré **4197** de dégât d'overwatch sur un autre
board). « Dégât > 0 sur l'attaquant » serait donc VERT pour n'importe quel canal. On exige
cumulativement : la classe d'effet portée, **exactement 2** coups, chacun sous
`maxDmg[passif] × multiplicateur`, la contre-épreuve et le contrefactuel de tour.

**⚠ Un CONFONDANT, trouvé par le bras négatif.** Le flag `IsActive` lu APRÈS le coup tombe à `false`
**aussi dans le cas `--neg-ranged`, où AUCUNE riposte n'a eu lieu** : en 1v1 l'attaque clôt le tour
ennemi, et `On(0x12) & IsTurnOf(Owner) -> DeactivateEffect` le fait tomber tout seul. Le flag seul ne
prouve donc RIEN sur le `& DeactivateEffect` du behaviour. D'où le montage `--two-attackers`, où le
second frappe dans le MÊME tour (`turn_rolled` faux) : c'est le seul qui isole la lecture.

**Gardes** — `tests/engine/runner/test_wireweave_net_counter_live.py`, **6 tests, tous verts** :
positif bit-exact des deux côtés, attribution, armement pendant le tour ennemi, once-per-turn (avec
le rejeu OFFLINE du 2ᵉ coup, cf. §7bis), négatif ranged, fenêtre isolée offline.

**MUTATIONS ADVERSARIALES — 11 mutations, 11 ROUGES** (`probe_366_r1b_wireweave_gates.py` comme
détecteur, sauf M11 qui vise le foyer partagé) :

| mutation | ce qui rougit |
|---|---|
| M1 trigger de riposte retiré du registre | `[0]` l'ArraySet natif porte 3 `Triggered()` |
| M2 repli `NOT IsTurnOf(Owner)` neutralisé | `[3]` la fenêtre ne ferme pas |
| M3 `IsNormalAttack` → `IsDirectTargetAttack` (l'erreur du voisin) | `[5]` une ACTIVE de mêlée réveille la riposte |
| M4 `& DeactivateEffect(effect)` retiré | `[1]` l'instance reste armée |
| M6 `_flag_is_set` toujours vrai | `[2]` la riposte repart le même tour |
| M7 `IsMeleeAttack` neutralisé | `[4]` riposte à distance |
| M8 `AreEnemies` neutralisé | `[6]` riposte contre un allié |
| M9 `On(TurnEnd) -> Activate` retiré | `[0]` registre incomplet |
| M10 malus DÉCISION rendu sans filet armé | `[9]` |
| **M11 le correctif de `refresh_stat_modifier_effects` annulé** | **`[2b]` `active après = True`, riposte fantôme de 1508 au 2ᵉ coup** |
| **M12 discriminant re-confondu avec `active_condition_ported`** | **3 tests de `test_refresh_active_flag_discriminant_offline`**, dont le régime « seedé inactif qui se rallume » |
| **M13 correctif annulé (variante offline)** | `test_unported_condition_is_never_relit_by_the_refresh` **+** l'étape `[2b]` |
| (M5 — retirer l'entrée de seed — est devenue SANS OBJET : le probe porte désormais le cliquet INVERSE, cf. §7ter) | |

**Cliquets** : `probe_181` (98/98, 0 manquante), `probe_120 --step 0` (98 abilities, 0 littéral
manquant ; ses 5 étapes du vecteur `On(PreUnitAbility)` restent vertes AVEC les nouveaux triggers),
`probe_273 --only-scan`, `probe_365`. **Non-régression** : **126** tests offline + **20** tests live
voisins (`test_fire_and_reposition_reduce_dmg_live` 8/8, `test_martial_superiority_live` 4/4,
`test_anvil_shield_stun_live` + `test_visions_of_heresy_pierce_live` 8/8).

## 7bis. Le foyer PARTAGÉ qui écrasait `IsActive` — trouvé par le rejeu du 2ᵉ coup

La garde live `once_per_enemy_turn` telle qu'écrite d'abord ne lisait que le NATIF (flag + absence de
seconde riposte côté jeu). **Mutation M4 appliquée : les 6 tests restaient VERTS.** Un test qui ne
rougit sous aucune mutation de son propre sujet ne garde rien. En liant le port à la mesure — REJOUER
le 2ᵉ coup OFFLINE sur le même flux MT et comparer les PV — la garde a immédiatement trouvé une
**riposte fantôme du port : 2ᵉ attaquant à 997150 offline contre 999999 live**.

Étage : l'étage 1 (1ᵉʳ coup) était bit-exact, donc la divergence naissait ENTRE les deux coups.
`refresh_stat_modifier_effects` (`runner/operations/refresh_effects.py`), traversé par le pipeline
d'attaque complet, faisait pour CHAQUE effet non consommé :

    active = bool(e.is_active(ustate))     # `is_active()` de base = True
    e.active = active                      # <- ECRASE le flag que DeactivateEffect vient de poser

Le natif ne fait pas ça. `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`, branche
`refreshType == Normal`, lu verbatim :

    if (effectComponent.<+0x5e>)                    return false;
    if (!effect.ShouldRefreshForTrigger(trigger))   return effectComponent.<+0x5c>;   // LE FLAG COURANT
    return effect.ShouldBeActive(entities);                                           // CreateActiveCondition

⇒ le natif a **DEUX régimes** : ré-évaluer, ou **renvoyer le flag courant**. Le port n'a ni
`RefreshEffectTrigger` ni `ShouldRefreshForTrigger` : il ne peut pas mirrorer le CHOIX du régime. Il
décide donc sur ce qu'il **peut lire** — la classe porte-t-elle vraiment sa `CreateActiveCondition` ?

| la classe SURCHARGE `is_active` | le port a | ce qu'il fait |
|---|---|---|
| OUI — **13** classes sur 145 | une LECTURE du natif | ré-évalue et **écrit** le flag (= comportement d'avant ce cas) |
| NON — les 132 autres | rien : `BaseEffect.is_active` rend `True` **inconditionnellement**, une valeur PAR DÉFAUT | **conserve** le flag et conjugue |

Les deux branches sont ancrées sur une mesure LIVE : `test_contagions_lifecycle_live` (aura qui
grandit → il FAUT ré-évaluer) et `test_wireweave_net_counter_is_once_per_enemy_turn` (la riposte 1111
ne doit PAS se ré-armer → il FAUT conserver).

**⚠ LE PREMIER DISCRIMINANT ÉTAIT FAUX, et il a fallu qu'un tiers rougisse pour le voir.** J'avais
pris `BaseEffect.active_condition_ported`. Ce drapeau répond à une **autre question** — « le flag
CAPTÉ au seed est-il PÉRIMÉ parce que la condition porte sur l'état SIMULÉ ? » (case-322) — et n'est
posé que par **UNE** classe, là où **13** portent réellement `is_active`. Résultat : les 12 autres
étaient **VERROUILLÉES**. Une instance arrivée INACTIVE du seed (le canal `includeInactive` de
`snapshot.decision_view_seed_body` publie bien `active: false`) dont la condition portée devient
vraie en cours de sim ne pouvait plus **jamais** se rallumer. Mesure, sur
`test_contagions_lifecycle_live` : l'aura `ContagionsOfNurgle` grandit, `1072` devient éligible —
live `actif=[1072] armure=1387`, port `actif=[] armure=2312`. **Mon rayon d'explosion initial était
mal mesuré** : j'avais joué 126 tests offline + 20 live voisins, aucun ne couvrait ce régime.

**Deux gardes, complémentaires, et chacune vérifiée ROUGE sous mutation :**

* **étape `[2b]` du probe offline** — rejoue les deux coups par le **pipeline complet**
  (`AttackUnitMessage`), pas par le seul vecteur `On(0x2a)` : c'est l'écart entre les deux qui
  cachait le bug d'origine. Rougit sous M13 (correctif annulé).
* **`tests/engine/runner/test_refresh_active_flag_discriminant_offline.py`** (5 tests) — les
  **quatre régimes** (condition portée qui s'allume / qui s'éteint ; condition non portée qui ne se
  rallume pas / qu'on n'éteint pas) **plus un cliquet du discriminant** qui compare les deux
  ensembles. Rougit sous M12 (re-confusion avec `active_condition_ported`) sur **3 tests**, dont
  précisément `test_ported_condition_relights_a_seeded_inactive_instance`. Ce régime n'était retenu
  par **rien** avant Contagions — et Contagions l'a attrapé par hasard ; il est désormais gardé
  offline, en 0,8 s.

## 7ter. Le seed d'owner-effect : posé par analogie, RETIRÉ sur mesure

`ABILITY_INIT_OWNER_EFFECTS["WireweaveNet"]` avait été inscrit par analogie avec `AnvilShield` /
`HammerOfWrath` / `ModifiedExoarmour` / `VisionsOfHeresy` — même profil natif (owner-effect à l'init,
inactif donc invisible du canal par défaut). **Les deux gardes MÊLÉE du voisin sont passées au ROUGE :
`live [23633]` contre `port [21840]`.** Attribution faite par mutation (entrée retirée → les deux
redeviennent vertes), pas par raisonnement.

Cause : `spawn._seed_ability_owner_effects` lit les passives du **KIT gameconfig**
(`GC.unit(vid).passiveAbilities`), pas de la MESURE. Le montage anti-bruit de case-366-r1
(`--unit-stat "eldarRanger:PassiveAbilities=[]"`) retire le passif du BC — le port matérialisait
quand même 1111 et faisait partir une riposte FANTÔME, décalant le flux MT. C'est le **piège #312 /
#264**, celui-là même que le pendant DÉCISION (`scene._seed_condition_gated_owner_effects`) évite
avec son `seed_witness_effect`.

Le substrat mesuré existe (`UnitContext.passive_abilities`, tri-état, canal `unitAbilityStates`)
mais il est seedé par `_load_passive_abilities` **APRÈS** la boucle d'owner-effects de
`_load_stats_and_effects` : à l'instant du seed il vaut toujours `None`. Le corriger demanderait de
déplacer cette boucle dans `load_state` — un changement structurel partagé que ce cas ne peut pas
valider largement. **Décision : ne pas inscrire l'entrée**, parce qu'elle est *inutile* ici (armé ⟺
publié) autant que nuisible. Le probe porte le **cliquet INVERSE** (étape `[0]` : l'entrée ne doit
pas revenir), avec la raison en clair à l'emplacement où on l'attendrait dans `factory.py`.

## 8. Ce qui n'est PAS couvert

* **`<DSLTriggers+0x20>`** — conjoint SINGLETON de `CreateTargetTrigger` : classe instanciée
  UNIQUEMENT par `DSLTriggers$$InitializeShared` (2 xrefs, toutes deux là), qui ne reçoit que
  `factory@+0x10` (le service DSL) — aucun sélecteur d'owner/cible, donc condition GLOBALE. Même
  traitement que `ctx@0x90` de `MartialSuperiority` et `ctx@0x98` des `Triggered()` d'overwatch
  (case-127 §8.3) : **non qualifié, non porté**.
* **Le slot `Caster`** — le natif lit la cible de la riposte dans `<DSLSelectors+0x48>` (`Caster`),
  pas `Actor`. Sur le vecteur `On(PreUnitAbility)` publié par `ActiveAbilityOperation` les deux
  désignent l'attaquant, et c'est `TriggerEvent.actor_id` qui le porte côté port. Le port n'a pas de
  canal caster-de-l'événement distinct d'`actor`.
* **`source = AbilityOrEffect{TriggeredAbility = 1111}`** non threadé sur l'attaque de riposte (le
  canal `ability_type` du port est keyé sur l'espace `ActiveAbilityType`) — même choix que
  `MartialSuperiority` / `MartialApotheosis`.
* **`get_OwnerOrOwnerTileIsTarget`, 2e branche** (cible = la TUILE du porteur) : structurellement
  couverte par la 1re, aucun vecteur porté ne cible la tuile d'une unité occupée.
* **Quatre SŒURS de la même base `CounterAttackEffect` non portées** :
  `GrimRetribution_CounterAttack` (1213), `SmashaSquigJaws_CounterAttack` (1104),
  `UnwaveringSentinel_CounterAttack` (1439), `WarConstruct_CounterAttack` (1286). Leur i2 montre que
  la base sert des sémantiques différentes (« the first enemy » pour GrimRetribution, « **each**
  enemy » pour WarConstruct, qui override `CreateActiveCondition`) : **chacune demande sa propre
  lecture**, ce cas ne les préjuge pas.
* **`ActivationFrequency == 1`** (la branche symétrique de `CreateHandleTriggerAbilitiesInternal`,
  qui utilise `IsEnabledTurnType` au lieu d'`IsTurnOf`) n'est exercée par aucun effet porté.
* **La face DÉCISION est confrontée LIVE depuis `case-415-r1`** : deux cibles au `pairUtility` natif
  EXACTEMENT égal (même `utilRaw` Fix64), une seule portant un filet armé, caster ÉPINGLÉ
  (`--unit-stat Movement=0`) — le natif retient la cible SANS filet, et retombe sur la porteuse dès
  que le filet disparaît. Le port rend les deux. Le seul régime qui reste NON CONFRONTÉ sur cette
  face est « filet PRÉSENT mais DÉSARMÉ » : `aiDryRunAllUnits` n'évalue que les unités du joueur
  COURANT (mesuré), donc jamais un attaquant pendant le tour de Calandis — la seule fenêtre où le
  canal `decisionView` par défaut cesse de publier l'instance. Il est gardé OFFLINE par l'étape
  `[10]` du probe (le prédicat `Any(e => e.IsActive)` contre la seule PRÉSENCE), que l'étape `[9]`
  ne couvrait pas — elle reçoit le booléen tout fait.
* **Le régime « capture pendant le tour de Calandis, puis franchissement de la frontière de tour »**
  — sans instance à armer, la riposte ne partirait pas. Résidu assumé, cf. §7ter (rouvrir demande
  d'abord de faire lire au seed d'owner-effects le substrat MESURÉ).
* **`--lethal` et `--neg-owner-turn` du probe live** n'ont pas été joués : le premier demande de
  caler les PV de l'attaquant entre le tir d'Overwatch de l'approche et la magnitude de la riposte,
  le second est déjà couvert — plus proprement — par le contrefactuel OFFLINE (le live REFUSE
  l'action d'une unité hors-tour, cf. #133).
* **`spawn._seed_ability_owner_effects` lit le KIT gameconfig pour TOUTES ses entrées** (pas
  seulement la mienne) : le piège #312 reste ouvert pour les 15 autres, il n'a simplement pas
  d'observable connu chez elles. Résidu NOMMÉ, hors périmètre de ce cas.
* **`ShouldRefreshForTrigger` n'est PAS porté** — le port ne mirrore donc pas le CHOIX natif entre
  « ré-évaluer » et « conserver », il choisit celui qu'il sait lire (§7bis). Le natif lu :
  `BaseEffect$$ShouldRefreshForTrigger` rend TRUE pour les triggers `0/1/2` et pour tout effet dont
  le set de triggers (vtable `+0x5c8`) est vide ; porter ce choix demanderait l'enum
  `RefreshEffectTrigger` **et** les points d'émission de refresh, qui n'existent pas côté port
  (`refresh_stat_modifier_effects` est appelé par le pipeline, sans notion de trigger). Résidu NOMMÉ.

## 9. Artefacts

| quoi | où |
|---|---|
| classe d'effet | `scripts/python/engine/entities/effects/loki/counter_attack.py` |
| triggers (riposte + armement) | `scripts/python/engine/runner/operations/triggers/loki/wireweave_net.py` |
| registres | `scripts/python/engine/entities/effects/factory.py` (`EFFECT_CLASSES` ; et le commentaire qui documente l'entrée `ABILITY_INIT_OWNER_EFFECTS` VOLONTAIREMENT absente), `.../triggers/dispatch/registry.py` (`EFFECT_TRIGGERS[1111]`) |
| correctif du foyer PARTAGÉ | `scripts/python/engine/runner/operations/refresh_effects.py` (§7bis) — helper `_active_condition_is_ported` |
| garde du foyer PARTAGÉ | `scripts/python/tests/engine/runner/test_refresh_active_flag_discriminant_offline.py` (4 régimes + cliquet du discriminant) |
| face DÉCISION | `scripts/python/engine/utilities/wireweave_net.py` + `engine/playbook/base.py` (`calculate_action_utility`) |
| harnais offline | `scripts/python/probe_366_r1b_wireweave_gates.py` |
| montage live | `scripts/python/probe_366_r1b_wireweave_net.py` |
| gardes live | `scripts/python/tests/engine/runner/test_wireweave_net_counter_live.py` |
