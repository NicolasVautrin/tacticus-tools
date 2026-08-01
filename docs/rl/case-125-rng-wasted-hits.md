# case-125 — coups GASPILLES sur un cadavre : flux `state.rng` (OK) et REPORT de coups (FAUX)

> Build `gqfc5mff6c`. Probe : `scripts/python/probe_125_leftover_hits.py --mode sweep`.
> Gardes : `tests/engine/runner/test_chain_leftover_hits_live.py` (live, 2 seeds) +
> `tests/engine/runner/test_necrons_lot1_live.py::test_multi_threat_chain_only_on_kill_live`.
> Residu d'origine : [case-116](case-116-necrons-lot1.md) §3 « #116-d », requalifie par
> [case-122](case-122-hits-malus-ability-vector.md) §6.

## 1. La question, et la reponse

**Question (binaire).** Quand une attaque multi-coups TUE sa cible avant d'avoir epuise ses coups, le
natif consomme-t-il du `state.rng` pour les coups restants ? Et le port fait-il pareil ?

**Reponse : OUI le natif consomme, OUI le port fait pareil — il n'y a AUCUN desalignement de flux de
ce fait.** Les deux constats qui se contredisaient etaient tous les deux mal attribues :

| affirmation | verdict |
|---|---|
| #116 : « le natif ROULE bien ses 6 coups apres la mort, il cesse seulement de les APPLIQUER » | **VRAIE** (decompile) |
| #116 : « le report vaut CONSTANT `1 + extraHit` des que la cible meurt » | **FAUSSE** (4 regimes) |
| #122 : « le port cesse de rouler des la mort -> `state.rng` desaligne » | **FAUSSE** (le port roule tous ses coups) |
| #122 : « le regime 8000 est bit-exact, le regime 2500 diverge » | **VRAIE** — mais la cause est le REPORT |

La cause reelle du desalignement mesure par #122 est le **nombre de coups accorde au maillon SUIVANT**
(`GetLeftOverHits`) : un maillon qui recoit 2 coups au lieu de 4 consomme 4 tirages de moins, et c'est
le maillon d'apres qui tire faux. Le seuil « ecart a 4 coups gaspilles, pas a 1 » n'est pas un seuil de
flux : c'est le point ou la formule de report fausse commence a differer de la vraie (cf. §4).

## 2. Le decompile : ou le natif s'arrete, et ou il ne s'arrete pas

### 2.1 La boucle de coups n'a AUCUNE sortie sur la mort

`IdunBattle.Operations.AttackDamageOperation$$Execute` :

```
hits   = IdunBattle.Operations.AttackDamageOperation$$GetAttackHits(...)
group  = IdunBattle.Operations.ADamageOperation$$SetupHitGroup(...)
IdunBattle.Operations.AttackDamageOperation$$ExecuteHits(op, attackData, currentAttack, group, hits)
```

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` est un `while (i < hits)` **plat** : le
compteur est incremente dans TOUTES les branches du corps, il n'y a ni `break` ni test de mort de la
cible. Les seuls sauts hors de la boucle sont des null-checks qui LEVENT.

Et dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, les tirages d'un coup sont consommes
**avant** la sous-operation `0x42` :

1. `IdunBattle.Core.HitDamage$$GetDamage` (1 tirage si `Min != Max`) ;
2. slot 0xa -> `IdunBattle.Core.Services.DamagePrediction$$RollCritical` (0 tirage a `cc = 0`) ;
3. slot 4 -> `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` (0 tirage) ;
4. slot 8 -> `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` (1 tirage, sans gate) ;
5. sous-op `0x42` = `IdunBattle.Operations.ApplyDamageOperation$$Execute` — **le seul etage qui
   court-circuite sur un cadavre**, et il est EN AVAL des tirages.

Le port fait exactement pareil : `engine/runner/operations/damage_hits.py::_run_hits` boucle
`for i in range(hits)` sans aucun gate de mort. **Aucune divergence de flux.**

⚠ **RECTIFICATION (2026-08-01, `case-366-r1-crit-multihit.md`)** : la branche de fin de boucle
d'`ExecuteHits` que ce cas lisait comme « le coup a ete DISCARD » teste en fait
`OperationResult+0x21` = **le coup a CRITE** (le voisin `+0x22` est `didBlock`, etabli par le nom
du parametre d'`ADamageOperation$$EvaluateAfterHitTriggers`). `hitGroup+0x4c` compte donc les
CRITS, pas les discards. Sans consequence sur les conclusions de ce cas — la boucle reste sans
gate de mort, et `_run_hits` roule bien tous ses coups.

Seule sortie anticipee d'`ExecuteHit` : le coup a ete **DISCARD** (`IdunBattle.Core.AttackHit` champ
`+0x8`, pose par `IdunBattle.Operations.DiscardHitOperation$$Execute` via
`Core.Services.OperationProcessor$$DiscardHit`, lui-meme atteint par le behaviour
`IdunBattle.Entities.Behaviours.DiscardHitBehaviour$$Execute` de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility_DiscardHits`). C'est un
mecanisme d'ANNULATION de coup (Harlequins), pas le chemin cadavre.

### 2.2 Ce qui s'arrete vraiment : `ApplyDamageOperation`, sur `UnitFlag.Overkilled`

`IdunBattle.Operations.ApplyDamageOperation$$Execute`, dans l'ordre :

```
if UnitExtensions.HasFlag(target, UnitFlag.Fled = 9)          -> log + return
if UnitExtensions.HasFlag(target, 8) && !UnitExtensions.IsDead(target)  -> log d'incoherence
if UnitExtensions.HasFlag(target, UnitFlag.Overkilled = 8):
    IdunBattle.Operations.ApplyDamageOperation$$RecordHitStatistics(...)
    IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit(..., flag = 1)   # site (a)
    return                                    # <- AUCUN event de degat n'est emis
...
bVar16 = IdunBattle.Entities.Components.HealthComponent$$IsDead(healthComp)      # AVANT application
...
if Damage.GetTotal(requested) > 0:
    <sous-op 0x3a = l'event de degat>
    if HealthComponent$$IsDead(healthComp):                                      # site (b)
        AddLeftoverHit(..., flag = bVar16)
...
if <ce coup est un overkill (octet +0x13 de l'AttackData)> and
   IdunBattle.Entities.UnitExtensions$$CanBeOverkilled(target):
    IdunBattle.Entities.Components.UnitFlagsComponent$$Add(target, 8)            # pose Overkilled
...
if <PV reellement retires> > 0 and IsDead(apres):                                # site (c)
    AddLeftoverHit(Damage(requested - applied), flag = bVar16)
```

**`8` = `UnitFlag.Overkilled`, PAS « Dead »** (`UnitFlag.Dead` = 6, `Fled` = 9 — enum
`IdunBattle.Entities.Enum.UnitFlag` du dump). [case-116](case-116-necrons-lot1.md) §3 l'appelait « le
flag de mort » : c'est cette lecture qui rendait le comportement des events incomprehensible.

**Consequence directement observable** : tant que la cible n'est pas `Overkilled`, un coup tombe sur
son cadavre traverse tout le chemin et emet un event `Amount = 0` ; des qu'elle l'est, plus AUCUN event.
Le nombre d'events est donc l'index du coup d'overkill, **pas** le nombre de coups. Mesure (seed 4242,
u79, 6 coups) :

| PV cible | events LIVE du 1er maillon | coup fatal `k` | coup d'overkill `o` |
|---|---|---|---|
| 10000 | `[1700, 1839, 1840, 1903, 1837, 881]` (6) | 6 | jamais (`2 x PV` > total) |
| 4000 | `[1700, 1839, 461, 0, 0]` (5) | 3 | 5 |
| 3000 | `[1700, 1300, 0, 0]` (4) | 2 | 4 |
| 2500 | `[1700, 800, 0]` (3) | 2 | 3 |

`o` = premier coup dont le CUMUL de degat demande atteint `2 x PV_depart` (seuil
`overkillDmgPctOfHealth = 100`) — verifie sur les 4 regimes. **Compter les events sous-estime les
coups** : c'est le piege qui a produit les deux lectures contradictoires.

## 3. La vraie cause : `GetLeftOverHits`

`IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` :

```
list  = target.GetComponent<...>.LeftOverDamages (+0x90)
count = # entrees dont le FLAG (IdunBattle.Core.LeftOverDamage$$.ctor param_4 -> champ +0x7c) est VRAI
        ET dont l'AbilityOrEffect (+0x18) == la notre (+0x70)
if list.Count > 0 and <noeud extraHits> != null : count += extraHits.Calculate(entities)
return count
```

Le port rendait **`1 + extraHit` des que l'attaque tue** — un scalaire calibre par #116 sur un SEUL
regime (PV 8000). C'est faux des que le coup fatal arrive tot.

## 4. La loi, mesuree

`probe_125_leftover_hits.py --mode sweep` FORCE le report maillon par maillon (`_left_over_hits`
remplace par une suite imposee) et confronte chaque tuple au per-coup LIVE du maillon dont la cible
**SURVIT** — le seul dont le per-coup live n'est ni clampe par les PV ni tronque par la suppression
d'event. Seed 4242, board `MC1_67`, `necroDestroyer` (1006, 6 coups) vs
`eldarRanger,astraBullgryn,tauMarksman`, `--crit 0,0`, `--hp-player 60000` :

| PV cibles | `k` | `o` | report LIVE mesure | `1 + extraHit` (avant) | `max(0, H-k-1) + extraHit` |
|---|---|---|---|---|---|
| 2500 | 2 | 3 | **4** (`{4,1}` / `{4,2}`) | 2 | **4** |
| 3000 | 2 | 4 | **4** (`{4,1}` / `{4,2}`) | 2 | **4** |
| 4000 | 3 | 5 | `{1,2,3}` (LightCover ecrase) | 2 | 3 |
| 10000 | 6 | — | **>= 1** (le 2e maillon EST frappe) | 2 | **1** |

Deux regimes decisifs :

- **2500 vs 3000** ont le MEME `k` et un `o` DIFFERENT et rendent le MEME report : le report depend de
  **`k`**, pas de l'index d'overkill. Cela refute le modele « une entree par coup post-overkill »
  (`H - o + 1`, qui aurait donne 4 puis 3).
- **10000** : `k = H`, AUCUN coup gaspille, et pourtant le 2e maillon est frappe -> c'est ce regime qui
  pin le terme `+ extraHits` (`extraHit = 1` en gameconfig pour 1006) et refute `H - k` seul.

**Loi portee** (H = coups APPLIQUES du maillon, k = index 1-based du coup qui met la cible a 0 PV) :

```
cible SURVIVANTE       -> 0                               (aucune entree, pas meme le + extraHits)
tuee au coup k         -> max(0, H - k - 1) + extraHits
deja morte a l'entree  -> H + extraHits                   (modelise, non confronte : le selecteur de
                                                           cible suivante filtre les vivants)
```

Pourquoi #116 mesurait juste et concluait faux : son unique regime (PV 8000) donne `k = 5`, `H = 6`,
donc `max(0, 6-5-1) + 1 = 1` **et** `1 + extraHit = 2` — et le maillon suivant portait `LightCover`
(-2 coups, plancher 1), qui **ecrase 1 et 2 sur la meme valeur appliquee**. Deux formules
indiscernables sur ce regime ; elles divergent des `k <= 3`.

### Ecart lecture / mesure, assume et nomme

Les trois call-sites lus predisent `H - k` entrees de flag vrai (un coup sur cadavre a `IsDead` avant
= vrai, et `IdunBattle.Entities.Components.HealthComponent$$IsDead` est bien
`CurrentValue < 1 && CurrentMaximumValue > 0`, sans differe). La mesure en donne **une de moins**.
Exactement UN coup-sur-cadavre ne laisse pas d'entree comptee ; la mesure ne dit pas LEQUEL (le
premier coup sur le cadavre et le coup d'overkill coincident sur les 4 regimes, et les regimes qui les
separeraient — `o <= k`, ou `o` jamais atteint — ne sont pas observables a travers cette chaine : ils
exigent un report >= 4 ET un maillon suivant survivant, deux conditions incompatibles ici). Ce n'est
pas un scalaire fitte : la loi est entiere, a un seul terme libre, confrontee sur 4 regimes dont deux
qui separent `k` de `o`.

## 5. Le fix

`engine/runner/abilities/behaviours/combat.py::ChainLeftOverHitsAttackDamage._left_over_hits` — la loi
ci-dessus remplace le `1 + extraHit` en dur. Les deux autres branches (survivante -> 0, deja morte ->
`H + extraHit`) sont inchangees.

Additif : le maillon emis (`ChainLeftOverHits`) expose desormais `per_hit_health` et `hp_before`, les
DEUX entrees de la loi (un consommateur qui lit `per_hit` sommerait PV + bouclier + armure-pool).

**Rien d'autre n'est touche** : `_run_hits` (partage par TOUS les vecteurs de degat) n'est pas modifie —
le decompile confirme que sa boucle sans gate de mort est deja le mirror exact.

## 6. Validation

- **Probe, 4 regimes x 1 seed (avant/apres)** : le port passe de `report = 2` a `report = 4`
  (PV 2500/3000) et sa chaine devient le tuple compatible avec le LIVE. Maillon discriminant
  (`tauMarksman`, survivant) : **avant** `[2613]` vs live `[2423]` -> **apres** `[2423]` = live.
- **Generalisation, seeds frais** (memes regime et board, rolls entierement differents) :
  seed 31337 -> live `[2558]`, port `[2558]` ; seed 777 -> live `[2930]`, port `[2930]`. Bit-exact.
  Avant le fix, le port aurait tire `[2942]` / `[2556]`.
- **Garde live nouvelle** : `tests/engine/runner/test_chain_leftover_hits_live.py` (seeds 4242 et 777),
  geometrie de chaine DRIVEE (les 3 ennemis sont deplaces en ligne, chacun adjacent au precedent et
  dans le disque rayon 2 du caster) ; le test contient son CONTRE-CAS (l'ancienne formule doit
  contredire le live sur le maillon discriminant, sinon il declare la mesure non discriminante).
- **Garde offline durcie** : `test_multi_threat_chain_only_on_kill_live` n'assert plus `1 + extraHit`
  mais la LOI recalculee depuis `per_hit_health`, sur DEUX regimes de `k` differents, avec l'assertion
  « un report constant ne peut pas passer ».
- **Non-regression rejouee (13 passed, 0 fail)** : `test_necrons_lot1_live` (3),
  `test_ability_hits_attack_nature_live` (2), `test_damage_roll_live` + `test_ability_hits_channel_live`
  (5), `test_runner_attack_live` + `test_damage_ability_live` (3).

## 7. Ce qui n'est PAS couvert

- **Jets de block/esquive d'un coup gaspille** : sur un cadavre DEJA `Overkilled`,
  `ApplyDamageOperation$$Execute` retourne AVANT les jets qu'il porte, alors que le port les joue
  encore (`calculate_damage_operation` dans `_run_hits`). NO-OP tant que la cible n'a aucune source de
  block (tous les cas mesures ici) ; sinon 1 tirage d'ecart par coup gaspille. **Residu nomme.**
- **Clamp PV per-coup** : le port applique le degat du maillon en UN bloc, donc son `per_hit` du
  maillon fatal n'est pas clampe (`[2987, 2613]` la ou le live montre `[2500, 0]`). Sans effet sur
  l'etat final (PV 0 des deux cotes) ni sur le flux `state.rng` — inchange par ce port.
- **`UnitFlag.Overkilled` n'est pas modelise** dans le port : il ne change ni le report (les deux
  chemins posent une entree de flag vrai) ni les tirages, mais il gouverne l'emission des events —
  donc toute future confrontation qui COMPTE des events doit en tenir compte.
- **Persistance de `LeftOverDamages`** : la liste vit sur le composant de la CIBLE et n'est pas videe
  entre attaques ; le port la recalcule a partir de la seule attaque courante. Identique tant qu'une
  cible n'est frappee qu'une fois par la meme ability (le cas de la chaine).
- **Branche « cible deja morte a l'entree »** : modelisee (`H + extraHit`), non confrontee — le
  selecteur de cible suivante filtre les vivants (deja note en case-116 §5).
