# #62c : GetStuckIn bonus-hits en COMBAT (runner) — PORTE + VALIDE

Build `gqfc5mff6c`. RE complete 2026-07-08 ; **PORTE 2026-07-09** (commit `3997793`) ; **re-valide
adversarialement 2026-07-24** (tache #67, cf. MAJ en bas). Le COMBAT (runner) ajoute les coups bonus
GetStuckIn a l'EXECUTION via le behaviour chance-gate porte (`_run_hits(bonus_hit_chance=...)` +
`getstuckin_combat_chance`), PAS dans la formule de nb de coups (la prediction, elle, les fold de facon
DETERMINISTE cf. `attack_hits_formula.py` + #47). GREP avant de re-RE : **c'est FAIT**, ce fichier = la
spec + le journal de validation.

## Mecanique native (LUE)

- **Trigger** `GetStuckInAbility.CreateTrigger @180f83350` :
  `On(8) & CurrentHitIndex.IsOdd & OwnerIsCaster & !(MinDistance(caster,target) > 2)`.
  => fire une fois PAR COUP d'index IMPAIR, sur l'attaque du caster lui-meme, cible a distance <= 2.
- **Behaviour** `AddBonusHitsToCurrentHitGroupBehaviour.Execute @180f93410` : evalue le nb de coups
  bonus (noeuds DSL `FUN_180025220` idx7, `FUN_1800250d0` idx1) et l'INJECTE dans le hit-group courant
  pendant l'execution (List.Add d'un ValueTuple {position, count}).
- **Chance (gate `Maybe`)** `GetBonusHitChance @180f83460` :
  `If(orks_adjacents >= 2 OU amis_adjacents >= 4, chance_2 = 100, chance = 30)` (gameconfig GetStuckIn).
  Adjacence = `AdjacentUnits(target)` -> Orks(faction 5) / Friends-of-caster.
- Effet net : +1 coup par coup d'index impair QUAND le roll passe => ~ +floor(hits/2) si chance=100.

## Cote PREDICTION (deja fait, NE PAS retoucher)

`attack_hits_with_modifiers(include_bonus_hit_behaviours=True)` fold GetStuckIn de facon DETERMINISTE
(chance ne pilote que le roll d'exec, pas la prediction IA) : `+floor(hits/2)` compte SSI chance==100.
Valide seed777 step-13 + validateur. `GetStuckInTrait.as_attacker_bonus_hits` (traits/combat.py).

## Cote COMBAT (a porter — le trou #62c)

- Point d'entree : `AttackDamageOperation` (engine/runner/operations/damage.py). Le runner boucle
  `hits` fois ; ordre RNG PAR COUP = crit-roll (NextBool si cc>=1, PAIR) -> spread (IMPAIR) -> block.
  Aujourd'hui `include_bonus_hit_behaviours=False` => GetStuckIn OMIS (fidele : la formule native ne
  l'inclut pas non plus ; c'est un behaviour SEPARE).
- Port fidele : pendant l'execution, pour chaque coup d'INDEX IMPAIR, si `OwnerIsCaster` &
  `MinDistance(caster,target) <= 2` & carrier a le trait GetStuckIn : roll `Maybe(GetBonusHitChance)`
  (30 ou 100 selon adjacence orks>=2/amis>=4) ; succes => +1 coup bonus insere dans la sequence.

## Execution native (RE `ExecuteHits @180e607b0` + voisins)

- `AttackDamageOperation.ExecuteHits @180e607b0` = boucle principale : `for hitIndex in range(numHits)`
  { `ExecuteHit @180e5eff0` (crit/spread/block/degat DEDANS) -> `UpdateHitGroupAfterHit` ->
  `UpdateCurrentAttackAfterHit` -> `List.Add` (record du coup) -> accumule les totaux dans le
  hit-group (+0x40/+0x44/+0x48) -> `RegisterBlocks` -> check `Any(param_2[8], func-sur-hitIndex)`
  qui pose le flag hit-group `+0x3c` }. `numHits` est FIXE a l'entree de la boucle.
- Les coups BONUS ne grossissent PAS `numHits` de cette boucle : ils passent par le chemin SEPARE
  `AttackDamageOperation.ExecuteAdditionalHitsWithoutDamageProfileType @180e5e7c0`, declenche par la
  cascade du trigger `On(8)` (PAS inline dans la boucle). Le behaviour `AddBonusHitsToCurrentHitGroup
  Behaviour @180f93410` insere le coup bonus ; son roll `Maybe(GetBonusHitChance)` s'evalue quand la
  cascade traite l'event 8 APRES le coup courant.
- Le `param_2[8]` + `Enumerable.Any(...)` en fin d'iteration = liste de conditions/bonus pendants
  evaluee par index de coup (a relier au coup impair). Detail exact du couplage a confirmer.

## POSITION RNG : RESOLUE (RE re-expert + confirmation live, 2026-07-09)

**Le `Maybe(chance)` n'est PAS dans la condition du trigger** (hypothese de depart REFUTEE). Lu :
- `GetStuckInAbility.CreateTrigger @180f83350` = `On(8,1) & AmountIsOdd(CurrentHitIndex) & OwnerIsCaster
  & !(MinDistance(caster,target) > 2)` — AUCUN noeud Maybe/chance dedans.
- `GetStuckInAbility.CreateBehaviour @180f83280` = `Maybe(AddBonusHitsToCurrentHitGroup(pos,count),
  GetBonusHitChance())` — le ROLL est DANS LE BEHAVIOUR. `MaybeBehaviour.Execute @180fc9dc0` evalue le
  noeud chance (sans RNG) puis `FUN_180003b40(5, IRandom, chance)` = **NextBool(chance) = 1 tirage genrand** ;
  si succes -> `AddBonusHitsToCurrentHitGroupBehaviour.Execute @180f93410` (insere `{position,count}` dans
  `hitGroup+0xf0`, AUCUN RNG).

**Position** : le behaviour Maybe s'execute dans `EvaluateAfterHitTriggers @180e25fc0`, DERNIERE instruction
de `ExecuteHit @180e5eff0` -> **APRES crit+spread+block du coup courant, AVANT le coup suivant**. Indexation
**0-based** : sur 3 coups {0,1,2}, seul l'index 1 est IMPAIR -> **1 roll Maybe / attaque 3-coups**.

**Interleaving = DEFERE (FIFO), prouve live** : la boucle de base finit d'abord (le behaviour depose juste
`{position,count}`), PUIS `AttackDamageOperation.ExecuteAdditionalHitsWithoutDamageProfileType @180e5e7c0`
(gate `attack.count==1 && !additionalHitsFlag`, xref unique depuis `Execute @180e60c70`) rappelle
`ExecuteHits` pour chaque coup bonus. Le coup bonus repasse le chemin COMPLET (crit/spread/block + son
propre EvaluateAfterHitTriggers) avec le MEME profil reduit (pierce/armure) que les coups de base ; s'il
tombe sur un index impair il RE-roll un Maybe (2e GSI group observe live sur idx3) mais ses pending ne sont
PAS re-executes (garde anti-recursion). **count = 1 coup bonus / succes** (noeud idx1 `GetAdditionalHitsData`).

**Chance** `GetBonusHitChance @180f83460` = `If(orks_adj(target)>=2 OU amis_adj(caster)>=4, ConfigConst(0x33),
ConfigConst(0x2a))` ; 1v1 sans orks/amis adjacents -> **30** (le caster ork adjacent a la cible compte pour 1,
<2). Branche 100 non confirmee live (lecture seule).

**Trace de reference (test bit-exact)** : `rl_duel build --seed 4242 --p-units orksNob --a-units bloodIntercessor
--rank 17 --hp-target 100000`, endturn+aiturn (sort u78 du deep-strike), move orksNob->(0,0) adjacent, attaque
normale (Loki_NormalAttack id **69**). MT19937 seed 4242 (mti=624). Resultat : **8 tirages genrand, 3 coups**
Amounts=`2287,2594,2467`, DidCrit=0/DidBlock=0, **1 GSI group (Maybe ECHOUE, index 1)**, HP 100000->92652
(delta -7348). Decomposition des 8 tirages (l'agent en a laisse 4 "non attribues" -> en fait deja modeles par
le port) = **3 crit-rolls (orksNob a cc>=1, tous echouent -> DidCrit=0 mais tirage consomme) + 3 spreads +
1 block-roll (BeastSlayer chance10 hit0 puis EXCLU coups 2-3 par le gating #72) + 1 Maybe (index 1)**. A CONFIRMER
par le replay-diff (le port aligne les tirages automatiquement s'il est bit-exact ; pas d'attribution manuelle).

## Recette de port (verdict re-expert)

Dans `AttackDamageOperation._run_hits` (damage.py) : boucle de base `for hit_index in range(num_hits)` (num_hits
FIXE). Apres crit+spread+block de CHAQUE coup, si `hit_index % 2 == 1` (0-based) ET owner==caster ET
`hex_dist(caster,target) <= 2` ET carrier a GetStuckIn : `chance = GetBonusHitChance` (100 si orks_adj(cible)>=2
ou amis_adj(caster)>=4, sinon 30) ; **tirer 1 `next_bool(chance)`** (meme ordre que les autres Maybe) ; si succes
-> enregistrer `pending_bonus{count=1}` (NE PAS executer tout de suite). Apres la boucle de base (si non deja
en train d'executer des coups bonus) : executer chaque pending en repassant le meme corps de coup (crit/spread/
block + re-roll Maybe si son index est impair, MAIS sans re-executer ses propres pending = pas de recursion) ;
le coup bonus prend l'index suivant (num_hits, num_hits+1, ...). Profil du coup bonus = identique aux base.

## Points faibles a valider (garde adversariale)

1. **Attribution des tirages** : le port doit aligner les 8 tirages du replay-diff seed4242 (si desync -> la
   position du Maybe ou le compte crit/block est faux). Le replay-diff est LA garde (pas d'attribution manuelle).
2. **Anti-recursion** du coup bonus (garde native `attack.count==1 && !additionalHitsFlag`) : verifier que le
   port ne boucle pas ; le coup bonus RE-roll un Maybe (tirage consomme) mais n'execute pas ses pending.
3. **count>1** : lu =1, non teste pour count>1.
4. **Branche chance=100** (orks_adj>=2 / amis>=4) : non confirmee live -> a valider sur un setup adjacence.

## Cas de validation (live, replay-diff)

- **orksNob 1v1, chance=30** : natif = 3 coups (validateur cluster, BITE 2) — le fold en dur donnait 4
  (sur-comptage) => le port combat doit reproduire 3 (roll 30% echoue le plus souvent) ET bit-exact
  le degat total.
- **chance=100** (orks_adj>=2 ou amis_adj>=4) : +floor(hits/2) coups deterministes.
- Confirmer via `test_runner_attack_live` / replay-diff : degat total combat == live, sequence RNG alignee.

## Etat

**PORTE + VALIDE (2026-07-09).** Port : `AttackDamageOperation._run_hits(bonus_hit_chance=...)` (damage.py :
roll `next_bool(chance)` sur coup d'index IMPAIR apres crit+spread+block + coups bonus DEFERES FIFO ; gate
`bonus_hit_chance is None` => strict no-op, 0 regression) + helper `getstuckin_combat_chance` (damage_model.py :
GetStuckIn present + cheby<=2 + chance 30/amis_adj>=4->100 ; branche orks-faction non portee offline = gap
documente). VALIDE live `tests/engine/runner/test_getstuckin_combat_live.py` : chance=30 + hit-count/RNG-aligned
(ecart off-live CONSTANT a travers la frontiere Maybe => tirage bien positionne, pas de desync). No-reg
damage_roll+block 4/4. NB : le bit-exact ABSOLU (off_ph==live_ph) est xfail #68 (additif SmashaEad +299/coup
sur-applique par le port en combat, ORTHOGONAL a GetStuckIn -- cf. case-68).

## MAJ 2026-07-24 (tache #67) : re-validation adversariale + nettoyage docstrings stale

Contexte : la tache #67 partait d'un ETAT ACTUEL STALE (« le combat OMET le coup bonus, TODO #62c ») —
FAUX pour la base 148dde1 : le port existe depuis `3997793` (ancetre de HEAD, aucun revert). Les 3 blocs
« TODO #62c / combat OMET » (`attack_hits_formula.py`, `traits/combat.py`, `damage_ops.py`) etaient des
commentaires jamais mis a jour apres le port. Cette MAJ RE-CONFIRME la fidelite par RE + live, corrige les
docstrings, et ajoute une garde de non-regression pour l'execution DEFEREE.

### RE re-confirmee (decompile = verite)
- `CurrentHitIndex` = **compteur PERSISTANT `attack+0x30`** (RE `ExecuteHit @180e5eff0` : `param_3 = *(attack+
  0x30)` lu au DEBUT de chaque iteration d'`ExecuteHits`, passe a `EvaluateAfterHitTriggers` comme index ;
  `UpdateCurrentAttackAfterHit @180e26be0` l'incremente APRES chaque coup). Init 0 => base 0,1,2,... (0-based
  confirme empiriquement : au coup index-1 uniquement pour orksNob 3-coups). Les coups bonus CONTINUENT le
  compteur (3,4,... apres 3 coups de base).
- Coups bonus DEFERES via `Execute @180e60c70` : la boucle base peuple `hitGroup+0x58` (`UpdateHitGroupAfterHit
  @180e26c80` : `AddRange(hitGroup+0x58, unit+0xf0)` puis VIDE `unit+0xf0`) ; PUIS une boucle `foreach` sur une
  **COPIE snapshot** de `hitGroup+0x58` re-`ExecuteHits` par entree => les succes Maybe des coups bonus (ajoutes
  a l'original, pas a la copie) ne CASCADENT PAS. Un coup bonus d'index impair RE-roll un Maybe (tirage
  consomme) mais son succes est ignore : mirror EXACT du port (`_run_hits` boucle bonus, retour ignore).
- Roll = `MaybeBehaviour.Execute @180fc9dc0` -> `IPseudoRNG.NextBool(chance)` (slot 5) avec `chance` = formule
  `GetBonusHitChance` evaluee ; NextBool TIRE toujours (meme a 100, v in [1,99]) == port `next_bool`.

### Live (probe 1v1 propre, aucun confound — replay-diff bit-exact)
Sur `bloodIntercessor` (non-Big/Vehicle => BeastSlayer_ExtraDmg=0), chance=30 en 1v1, MEME seed offline/live :
- **orksNob (base 3, 1 roll Maybe idx1)** : 8 cas COUP BONUS (4 coups) + 11 cas no-bonus (3 coups), **tous
  bit-exact** (per_hit ET PV). Ex. seed 4301 `off=live=[1685,1321,1459,1420]`, hp 9035->3150. Le 4e coup (val
  1420 a l'index persistant 3) prouve que la conso RNG de la boucle base (3 spreads + 1 Maybe idx1) est EXACTE.
- **orksBigMek (base 4, DEUX rolls Maybe idx1 ET idx3)** : 6 cas BONUS+1 (5 coups) + **2 cas BONUS+2 (6 coups,
  FIFO deferee a 2 entrees, ex. seed 4410 `[550,529,550,118,476,590]`)** + no-bonus, **tous bit-exact**. Valide
  le 2e roll Maybe (idx3) a la bonne position ET la FIFO deferee multi-entrees.

### Points « a valider » de la spec — leves
1. Attribution des tirages : replay-diff bit-exact sur 16 cas bonus + N no-bonus (2 porteurs) => aligne.
2. Anti-recursion : confirmee par RE (snapshot copy) + aucun cas divergent.
3. `count>1` : orksBigMek produit 2 coups bonus (2 entrees FIFO) bit-exact => leve.
4. Branche chance=100 / cas 2-bonus « discriminant » du re-roll bonus : le re-roll d'un coup bonus d'index
   impair est TERMINAL (aucun tirage apres) => **inobservable** pour tout porteur (max base = orksBigMek 4 ;
   il faudrait base>=5 pour un index bonus impair NON terminal, inexistant chez les orks). Resolu par RE
   (snapshot copy => pas de cascade), non-discriminable en live — pas un residu, une propriete structurelle.

### Corrections livrees
- Docstrings stale « TODO #62c / combat OMET » -> reformulees (formule exclut GetStuckIn car l'EXECUTION
  l'ajoute ; bit-exact live) dans `attack_hits_formula.py`, `traits/combat.py`, `damage_ops.py`.
- `test_getstuckin_combat_absolute_bit_exact` (bit-exact ABSOLU) est **VERT** depuis #75/#68 (additif SmashaEad
  pre-percage, commit `c147513`) — l'ancien xfail #68 est LEVE.
- Nouveau `tests/engine/runner/test_getstuckin_bonus_deferred_live.py` : garde l'EXECUTION DEFEREE (orksBigMek,
  exige >=1 coup bonus materialise bit-exact) — le test soeur ne couvrait que le cas no-bonus 3-coups.

### Gap NON ferme (hors #62c, documente)
`getstuckin_combat_chance` ne calcule pas `orks_adj(cible)` faction-Orks (le runner ne porte pas la faction :
`build_hits_board` a retire `visual_id` car il ne distingue pas 2 instances miroir). Seul `amis_adj(caster)>=4`
est evalue -> en presence de 2+ orks adjacents a la cible SANS 4 amis adjacents au caster, le port renvoie 30 la
ou le natif renverrait 100 (sous-compte le coup bonus). Orthogonal a la POSITION/EXECUTION RNG (#62c core) ;
n'affecte que la PROBABILITE du roll, pas sa conso (1 tirage quel que soit chance). Fermeture = porter la faction
dans le runner (chantier separe).
