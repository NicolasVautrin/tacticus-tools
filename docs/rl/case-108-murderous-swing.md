# Case #108 — MurderousSwing (Tarvakh) : sous-prediction ×1.60 + reserve event-count 4=2x2

Statut : RE de la reserve AVANCEE (decompile gqfc5mff6c). Port PAS encore corrige (attend
confirmation live du count^2). Ability `MurderousSwing` (id 1137, porteur worldExecutions "Tarvakh"),
AoE melee autour du caster.

## Symptome (validator, commit c871bd2 REFUSE)

Contre-exemple : Tarvakh u82@(5,8) vs u78 astraBullgryn@(6,8) + u80 bloodIntercessor@(6,7) (2 ennemis
adjacents). Oracle (`aiPlaybookPredict`) = **4 events**, degat **base seule** [3190,4786]. Moteur = **1 event**,
degat **base+extraDmg** [5105,7658] (ratio ~1.60 = le +extraDmg applique a tort).

## RE confirmee (decompile, VA gqfc5mff6c)

### 1. GetCorrectDamage @1811c2c10 = base-only si count>1 (CONFIRME)
`MurderousSwingAbility.GetCorrectDamage` construit le noeud DSL :
`If(AmountIsGreater(nrEnemies, Direct(1)), GetMultipleUnitsDamage, GetSingleUnitDamage)` ou
- `GetMultipleUnitsDamage @1811c2da0` = MinMaxDamage(base) **seule** (branche count>1).
- `GetSingleUnitDamage @1811c2de0`  = `Sum(base, Direct(GetVariableForLevel(8=extraDmg)))` (branche count==1).

`nrEnemies` = `Enumerable.Count(lVar9)` ou `lVar9` = le set AoE = AdjacentEnemies du caster (voir 2).
=> >=2 ennemis -> base seule ; 1 ennemi -> base + extraDmg (var 8, scale level/mult). Le port a DEJA cette
logique (`get_correct_damage`, active_ability.py:365) MAIS `nr_enemies` vaut TOUJOURS 1 car
`MurderousSwingAbility` n'override PAS `get_aoe_targets` -> aoe=[] -> nr_enemies=1+0=1. C'est le bug ×1.60.

### 2. MakeDamagePredictions @181134600 = boucle sur le set AoE (CONFIRME)
```
lVar9 = <AdjacentEnemies(caster)>            # set AoE, field playbook @+0x28 ; count = Enumerable.Count(lVar9)
damageExpr = GetCorrectDamage(ability, input, Direct(count), 1)   # If(count>1, base, base+extra)
enum = GetEnumerator(lVar9)
for target in lVar9:                          # BOUCLE EXTERNE sur le set (count iterations)
    perTargetVal = target.<iface slot 0x183200900>()
    setNode = DSLFactory.Get(field@+0x18, lVar9)     # noeud Get sur lVar9
    hits    = GetHits(ability)
    profile = GetDamageProfile(ability)
    events  = ComparablePlaybook.GenerateMultiHitAttackPredictions(this, actor, ..., perTargetVal,
                                                                    setNode, damageExpr, hits, profile, ...)
    list.AddRange(events)                     # concatene
```

### 3. GenerateMultiHitAttackPredictions @181409da0 = 1 event par element de param_5 (CONFIRME)
Boucle interne : evalue `param_5` (= `setNode` = `Get(lVar9)`) en enumerable via FUN_180025220, puis
`for t in enumerable: ProbableDamageEvent.__ctor(...); list.Add(...)`. => emet **len(param_5) events**.

## Reserve (4=2x2) : count^2 CONFIRME LIVE (2026-07-12)

Probe `probe_ms108.py` (Tarvakh vs cluster melee, aiPlaybookPredict per K adjacents) :
- K=1 -> 1 event (perTarget {86:1})
- K=2 -> 4 events (perTarget {82:2, 80:2})   [= observation validator]
- K=3 -> 9 events (perTarget {82:3, 80:3, 86:3})
=> **nEvents == K^2**, chaque cible adjacente apparait EXACTEMENT K fois. Elimine lineaire (K) ET
2x-fixe (2K). Chaque event = base seule [3190,4786] (count>1). count^2 CONFIRME.

## (archive) HYPOTHESE count^2 (pre-confirmation)

Si `Get(lVar9)` re-evalue le SET COMPLET (len = count), alors :
externe (count) x interne (count) = **count^2 events**. 2 ennemis -> 2x2 = 4 = l'observation oracle.
1 ennemi -> 1x1 = 1 (concorde single-enemy valide). Chaque event = base seule (count>1).

INCERTITUDE RESTANTE : `DSLFactory.Get(field@+0x18, lVar9)` non decompile -> je n'ai PAS prouve que la
boucle interne parcourt le set ENTIER (vs un sous-ensemble par-target-externe qui donnerait un autre compte).
La convergence (decompile deux boucles imbriquees sur le meme lVar9 + oracle 2->4) rend count^2 TRES probable,
mais le clincher = un cas **3 ennemis** : count^2=9 vs count-lineaire=3 vs 2x-fixe=6. NE PAS asserter count^2
sans ce test.

## Plan de port (apres confirmation live)

1. `MurderousSwingAbility.get_aoe_targets(ctx)` = `Damageable(AdjacentEnemies(CasterTile(), Const(1)))`
   moins la cible principale (pattern Sub(main), cf. l'ability voisine active_ability.py:295-299) ->
   `nr_enemies = 1 + len(aoe)` reflete le vrai compte -> get_correct_damage bascule base-seule a >=2. (Repare
   deja le DEGAT : base seule, ratio 1.0.)
2. EVENT COUNT : si count^2 confirme, repliquer l'emission quadratique (boucle externe sur le set x
   generate_multi_hit_attack_prediction sur le set) pour matcher l'utilite oracle. Sinon adapter au facteur
   reel mesure. (Le port emet actuellement 1 event/cible = count -> il faut count^2.)
3. Re-valider single (ratio 1.0, 1 event) ET multi (base seule, count^2 events) vs aiPlaybookPredict.

## Port IMPLEMENTE + VALIDE (2026-07-12)

1. `MurderousSwingAbility.get_aoe_targets` = `Damageable(AdjacentEnemies(CasterTile, 1))` -> nr_enemies =
   1 + len(aoe) reflete le vrai compte -> get_correct_damage bascule base-seule a >=2.
2. `AActiveAbility.get_prediction_set_repeat(n_targets)` (defaut 1) ; MurderousSwing override = count
   (= 1+len(aoe)) ; `make_damage_predictions` replique la liste d'events de degat `rep` fois (mirror
   boucle externe natif) AVANT l'event SELF. rep=1 pour toutes les autres abilities -> lineaire INCHANGE.

VALIDE LIVE (probe_ms108_val.py, port make_damage_predictions vs oracle aiPlaybookPredict, MEME runner) :
- K=1 (1v1 Tarvakh vs custoTrajann) : port n=1 per={78:1} main=(5106,7658) == ORACLE (base+extraDmg, ratio 1.0).
- K=3 (vs 5 melee)                  : port n=9 per={82:3,80:3,86:3} main=(3190,4786) == ORACLE (base seule, count^2).
Port == oracle EXACT sur les 2 regimes (compte d'events + per-target + main dmg). Ferme #108.

## Fichiers
- `scripts/python/engine/entities/abilities/active_ability.py` (MurderousSwingAbility get_aoe_targets +
  get_prediction_set_repeat ; AActiveAbility.get_prediction_set_repeat defaut 1).
- `scripts/python/engine/playbook/prediction.py` (make_damage_predictions : replication count^2).
