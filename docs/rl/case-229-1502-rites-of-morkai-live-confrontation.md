# 1502 `RitesOfMorkai` — confrontation LIVE du gate `IsActive` (résorption des deux résidus)

Suite directe de `case-229-1502-rites-of-morkai-active-gate.md` (PR #235, `a543a51`), dont **deux
résidus** sont traités ici :

1. « le **rayon de souffle** de 1502 n'est PAS mesuré » — la case §3 de
   `case-229-effect-triggers-active-inventory.md` était marquée NON MESURABLE ;
2. « **confrontabilité** : `spaceWolfPriest` est un HERO hors pool, donc l'effet 1502 n'est pas
   posable en runner » — **ce constat était FAUX**.

Le port lui-même n'est **pas modifié** : il est confirmé, et sa justification change de statut —
de « mirror d'un gate dont l'atteignabilité est supposée » à « mirror d'un gate dont on a MESURÉ
qu'aucun vecteur de jeu ne peut l'exercer ». C'est un **cliquet de fidélité**, pas une correction
de nombre — et c'est maintenant démontré, plus supposé.

## 1. Le déblocage : « hors pool » n'est pas « non confrontable »

Le pool runner dérive du seed BC, qui est la capture d'**UNE** bataille : son catalogue ne porte que
les unités possédées ce jour-là. Un héros hors pool **s'injecte**
(`catalog_inject.write_augmented_seed_bc`, mirror de
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration`), qui alimente les DEUX
catalogues `Units` **et** `Abilities` :

    units = ['spaceWolfPriest']   abils = ['RitesOfMorkai', 'HealingBalms']
    rl_duel build --list-pool --seed-bc <seed augmente>   ->  97 -> 98 unites regulieres

`spaceWolfPriest` n'est pas dans un `unspawnable_rank17` (fichier absent d'un worktree frais :
c'est un artefact généré, pas une liste de refus versionnée). Le seed augmenté est écrit **hors de
`data/`** (c'est une SORTIE).

Ce que la voie a permis, et qui était déclaré impossible par la fiche précédente :

| déclaré impossible (#235) | mesuré ici |
|---|---|
| « l'effet 1502 n'est PAS posable en runner » | Baldr déployé, `RitesOfMorkai` (1211) **casté**, 3 effets 1502 posés par la cascade native |
| « personne n'a mesuré que `readEffectsByUnit` publie une instance 1502, et personne ne le peut » | **3 instances publiées**, canal par défaut ET `includeInactive` |
| validation du gate par effet **injecté** dans `state.effects` | gate confronté sur des instances **posées par le cast natif** et capturées par `load_state` |
| « `resolveVtableSlot` LIVE rend des slots NULS (carriers hors pool) » (`revive_effect.py`) | la classe `RitesOfMorkaiEffect` est désormais **initialisée** par le cast : ses slots de vtable se lisent LIVE |

## 2. Montage

    seed BC     : data/seed-bc.json augmente de spaceWolfPriest -> logs/seed_bc_swp_probe.json
    board       : MC1_67 (pvp, 7x9)      seeds : 777 et 4242 (verdicts identiques)
    team 1      : spaceWolfPriest (u81, « Baldr ») + astraCreed (u83) + eldarFarseer (u85)
    team 2      : orksNob (u77, 3 hits) + orksWarboss (u79)
    calibrage   : --hp-player 3000  --dmg-target 1000   --no-ai
    3e montage  : board C3_01, seed 999, spaceWolfPriest+bloodIntercessor+ultraTitus
                  vs worldKharn+orksNob   (cf. §4.2 bis)

Alliés **non-mécaniques** obligatoires : `get_HealType` de RitesOfMorkai vaut 0 (Heal) et
`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` refuse les mécaniques — c'est le piège
qui avait fait échouer le contrôle positif de #235 avec `necroOverlord`.

Calibrage du coup fatal **non overkill** : `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`
rend `pct = (dmg - hpAvant)/hpAvant * 100` comparé à `overkillDmgPctOfHealth` (=100), donc il faut
`dmg < 2 * hpAvant` au coup létal. Mesuré : 3000 -> 2096 -> 962 -> 0 (les 3 hits du Nob, le 3e via
son trait `GetStuckIn`) — `pct` de l'ordre de 5 % au coup fatal, `Attack_DidCrit=0`.

Probe : `scripts/python/probe_1502_rites_of_morkai_live.py` (build + marche des adverses au contact
+ cast + les deux questions + suivi de fin de vie de l'instance).

## 3. Q1 — RAYON DE SOUFFLE : **OUI**, `readEffectsByUnit` publie 1502

Contrôle négatif avant le cast : **0** instance publiée. Après le cast de `RitesOfMorkai` par Baldr :

    [Q1] includeInactive=False -> instances 1502 = 3
           unit=81 name=RitesOfMorkai type=1502 active=True removed=False eid=106 rem=2
           unit=83 name=RitesOfMorkai type=1502 active=True removed=False eid=107 rem=2
           unit=85 name=RitesOfMorkai type=1502 active=True removed=False eid=108 rem=2
    [Q1] includeInactive=True  -> instances 1502 = 3   (identique)

La cascade native du cast montre la pose (`Effect_SourceActiveAbility=1211`,
`Effect_RemainingTurns=2`) sur les trois alliés non-mécaniques adjacents, plus
`RitesOfMorkai_ExtraDamage` (effectType **1529**) sur le seul Baldr.

Côté port, `load_state` matérialise les trois :

    unit=81 active=True rem=2 source=81 abil_lvl=50 mult=180
    unit=83 active=True rem=2 source=83 abil_lvl=50 mult=180
    unit=85 active=True rem=2 source=85 abil_lvl=50 mult=180

⇒ **La case « 1502 -> canal unité -> OUI » de `case-229` §3 est CONFIRMÉE par mesure**, et non plus
« non confrontée ». Contraste avec 1077 (bond `Haze`), que `case-231` avait RÉFUTÉ live : la nuance
structurelle avancée par #235 (1077 = entité de BOND via `AddBondEffect`, 1502 = effet d'unité
ordinaire posé par `AddEffectOperation` sur `EffectsOwnedComponent`) est la bonne.

## 4. Q2 — LE GATE DISCRIMINE, mais sur une entrée que le JEU ne produit pas

### 4.1 Face PORT, sur des instances posées NATIVEMENT (plus aucune injection)

Même état LIVE, seule l'instance 1502 change d'état ; victime u83, tueur u77 :

| état de l'instance | vivant après la mort | hp | trigger | `consumed` |
|---|---|---|---|---|
| `active=True` (tel que capté) | **oui** | 3000 (= hp_max) | 1 | `[True]` |
| `active=False` | **non** | 0 | 0 | `[False]` |
| `active=False` puis `True` | **oui** | 3000 | 1 | `[True]` |
| `active=True` + OVERKILL | **non** | 0 | 0 | `[False]` |

Identique sur les deux seeds. Le gate lit bien le FLAG (le reste de l'état est le même), et
l'overkill reste un discriminant indépendant.

### 4.2 Face NATIVE : le jeu revive, et le port rend le MÊME nombre

Séquence live, u77 attaque u83 (inspiré, 3000 PV) — cascade verbatim :

    UnitStats_RemainingHealth: 2096  ->  962  ->  0          (3 hits, DidCrit=0, NumberOfMembers=0)
    [Group#21 e=83 «RitesOfMorkai»] -> [Group#22 e=107 «RitesOfMorkai»]
        Effect_Id=107  (steps 17 puis 19)                    = le RemoveEffect du 2e volet
    [Group#21 e=83 «RitesOfMorkai»] -> [Group#44 e=83]
        UnitStats_Transformed=1  UnitStats_RemainingHealth=3000    = le REVIVE

Le port, sur le même état, rend `alive=True hp=3000 trigger=1 consumed=[True]` : **agrément exact**,
valeur comprise (`Min(GetReviveHP, StatAmount(target, Health, max))` sature au hp_max de 3000).

⚠ Le diff d'état avant/après ne voit **RIEN** (3000 -> 3000) : le revive est instantané dans la même
cascade. Seuls les ÉVÉNEMENTS en témoignent — c'est ce qui a d'abord fait échouer la garde, et c'est
maintenant le critère qu'elle applique (`_scan_death_and_revive`).

### 4.2 bis — Généralisation, et l'overkill mord pour de vrai

Troisième montage, choisi pour être disjoint du premier : board **C3_01**, seed **999**, alliés
`spaceWolfPriest,bloodIntercessor,ultraTitus`, adverses `worldKharn,orksNob`.

- **Q1 : 2 instances 1502** (Baldr + `bloodIntercessor`) et non 3 — sur ce board, `ultraTitus` ne
  spawne pas adjacent à Baldr, donc la pose en zone (`range = 1`) ne l'atteint pas. C'est un
  contrôle utile : le nombre publié suit la géométrie, il n'est pas constant.
- **Q2 côté port : matrice identique** `(True, False, True, False)`.
- **Face native : PAS de revive** — et c'est le comportement CORRECT. La cascade porte
  `Unit_IsDying: 1, Unit_WasOverkilled: 1` : `worldKharn` frappe assez fort pour franchir
  `overkillDmgPctOfHealth`, et `get_ReviveOnOverkill` = false (« unless Overkilled »). Le port,
  sur le même état avec `overkill=True`, refuse également. **Le 3e discriminant est donc confronté
  LIVE**, en accord, sans avoir été prémédité.

### 4.3 Face NÉGATIVE : aucun vecteur natif d'extinction — RE + mesure

**Mesure.** Suivi de l'instance survivante, tour après tour (seed 4242) :

    t+0 : 1502 = [(active=True, removed=False, remaining=1)]
    t+1 : 1502 = ABSENT

Jamais d'état `active=False`, alors que `includeInactive` le publierait. La fin de vie observée est
un **RETRAIT**, pas une extinction.

**RE — pourquoi c'est structurel, et pas un hasard de scénario.** Trois lectures, chacune faite ici :

1. `IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor` appelle
   `IdunBattle.Entities.Effects.ReviveEffect$$.ctor(this, 2, 0, AbilityOrEffect(0x4bb), 1)`, et ce
   ctor écrit `+0x484 = 2` (turnsEnabled), `+0x488 = 1` (removeEffect), **`+0x480 = 0`**
   (activationFrequency) — la branche **conditionnelle** de
   `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`.
2. Le virtuel `CreateActiveCondition` (slot vtable `+0x518`), **lu LIVE** sur
   `RitesOfMorkaiEffect` désormais initialisée, pointe sur le corps partagé (ICF, 115 propriétaires)
   dont le symbole est `IdunBattleLogic.Effects.TeleportMovingEffect$$CreateActiveCondition` :

       return this.<DSLFactory @+0x48>.@+0xf8;

   Or `IdunBattleLogic.Entities.DSLFactory$$.ctor` construit à `+0xf8` un trigger CONSTANT sans
   paramètre, et pose à `+0x100` le `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot` **de ce même
   type** : c'est la paire constante vrai/faux. Que `+0xf8` soit la branche VRAIE est tranché par la
   mesure — l'instance 1502 est publiée `active=True` tour après tour, ce qui serait impossible si
   sa condition d'activité était le constant faux. (`BaseEffect.CreateActiveCondition` est, lui,
   ABSTRAIT — slot nul + `MethodInfo` nul : c'est `ReviveEffect` qui remplit le slot.)

   ⇒ `IdunBattle.Entities.Effects.BaseEffect$$ShouldBeActive` évalue `ShouldTrigger(<constant vrai>)`
   et rend TOUJOURS vrai. `RefreshEffect` ne peut alors qu'écrire `+0x5c = 1` (réactivation
   inconditionnelle) ; il n'atteint jamais
   `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` (le seul écrivain de
   `+0x5c = 0` de ce rail). Le raisonnement ne dépend même pas de trancher
   `IdunBattle.Entities.Effects.BaseEffect$$NeedsRefreshing` (le gate d'entrée de `RefreshEffect`
   quand `activation == 0`) : s'il rend faux, l'effet n'est pas touché du tout ; s'il rend vrai,
   il est réactivé. Aucune branche n'éteint.
3. **Le résidu « écrivain non identifié de `EffectComponent+0x5e` » est FERMÉ** :
   c'est `IdunBattle.Operations.RemoveEffectOperation$$Execute`, et sa forme interdit précisément
   l'état recherché —

       comp = GetComponent<EffectComponent>(effectEntity);
       if (comp.@+0x5f != 0) return;        // deja Removed          -> idempotent
       if (comp.@+0x5e != 0) return;        // retrait DEJA en cours  -> idempotent
       ... evenement 0x40 (LoseEffect) ...
       comp.@+0x5e = 1;                     // marqueur « retrait en cours »
       if (comp.@+0x5c != 0) <dispatch 0x2d>(effectEntity);          // ReverseModification si ACTIF
       ... retrait de l'id des deux listes d'ActiveEffectIds, RemoveSubEffects, evenements ...
       comp.@+0x5c = 0;                     // IsActive  = 0
       comp.@+0x5f = 1;                     // Removed   = 1

   `+0x5c = 0` et `+0x5f = 1` sont écrits **dans la même opération, à quelques instructions
   d'écart**. Il n'existe donc **aucun état stable où une instance est `IsActive == 0` sans être
   `Removed == 1`** — et `readEffectsByUnit` filtre `removed` **inconditionnellement**, dans les
   deux modes. C'est exactement la signature mesurée : `active=True` puis ABSENT.

**Conséquence honnête pour le port.** Le gate posé par #235 est un **cliquet de FIDÉLITÉ** : il
refuse une entrée que seul le canal de SEED peut fabriquer (`decisionView { includeInactive: true }`
+ `EffectFactory.create` depuis #219), jamais le déroulement d'une bataille. Il ne corrige aucun
nombre observable en jeu, et il ne doit pas être présenté comme tel. Il reste juste : c'est le
mirror 1:1 de la lecture par-cible de
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`, et le port ne
choisit pas ses gates selon ce qu'il sait déjà atteindre.

## 5. Bénéfices collatéraux mesurés

- **La vtable de `RitesOfMorkaiEffect` est désormais lisible LIVE** (la classe est initialisée dès
  qu'un cast a eu lieu). Lecture directe des slots, qui **confirme** le mapping que #79/#89 avaient
  dû dériver de la table `methodPointers` du PE :

      +0x718 IgnoreArmor              +0x728 get_ActivateOnResurrect   +0x738 get_ReviveOnOverkill
      +0x748 get_HealType             +0x758 CreateTargetFilter        +0x768 GetReviveChance
      +0x778 GetReviveHP

  avec `get_ReviveOnOverkill` = `get_ActivateOnResurrect` = corps `32 c0 c3` (`xor al,al ; ret`)
  = **false**, et `get_HealType` = `IgnoreArmor` = corps `33 c0 c3` (`xor eax,eax ; ret`) = **0**.
  Les valeurs `revive_on_overkill = False` et `heal_type = 0` du port sont donc confirmées par une
  **seconde source indépendante**. Sur `ReviveEffect`, `CreateTargetFilter`/`GetReviveChance`/
  `GetReviveHP` sont bien les trois ABSTRAITS (stub + `MethodInfo` nul).
- **Piège de lecture écarté** : `IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal`
  (la base de `ReviveEffect`) lit les slots `+0x728/+0x738/+0x748` avec une TOUTE AUTRE sémantique
  (portée de bond / adjacence / rupture). Sur `ABondEffect` ces trois slots sont ABSTRAITS ; c'est
  `ReviveEffect` qui les remplit. Ses trois branches produisent des
  `IdunBattleLogic.Entities.DSLFactory$$RemoveEffect` — **jamais** un `DeactivateEffect` : elles
  vont donc dans le même sens que §4.3 (retrait, pas extinction). Pour 1502, `get_HealType` = 0 et
  `get_ReviveOnOverkill` = false ferment de toute façon deux des trois branches.

## 6. Ce qui n'est PAS couvert

- **La face négative n'a PAS d'équivalent natif** : on ne peut pas montrer « le jeu refuse de
  revive parce que l'effet est inerte », puisque cet état n'existe pas en bataille. La garde de
  test exerce donc le flag par le chemin de SEED — qui est celui du port.
- **1547 `ReanimationBeamReviveTrigger`**, **1186**, **1201** : hors périmètre (un item par tâche).
  Le porteur de 1547 (`necroReanimator`, MoW) est lui aussi « hors pool » — et la voie
  `catalog_inject` s'y appliquerait de la même façon, ce que la fiche #235 n'envisageait pas.
- **La généralisation de §4.3 aux autres effectTypes** n'est pas faite : le corps
  `CreateActiveCondition = dsl@+0xf8` est partagé par ~115 classes (compte ICF, pas un inventaire
  d'effets), mais chaque effectType doit être lu pour son propre `activationFrequency` avant d'en
  conclure quoi que ce soit.
- **`RitesOfMorkai_ExtraDamage` (1529)**, publié par le même cast, a lui un
  `IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$CreateActiveCondition` PROPRE
  (donc une vraie condition, donc un vecteur d'extinction plausible) — non instruit ici.
- **Les autres volets de l'ability** (pose en zone, attaque mêlée de suivi de
  `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour`) restent
  le résidu de `case-66-revive-in-place.md`. Ils sont maintenant **confrontables** — le cast natif
  tourne en runner.
