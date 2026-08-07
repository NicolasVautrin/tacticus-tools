# #287-r11 — trois règles dynamiques dont l'étage était DÉJÀ porté, et les trois lectures qui font la différence

Dettes réelles **10 → 7**, re-dérivé des deux côtés par `probe_287r5_etages_bloquants.py` (le
recensement est la vérité courante, pas cette page — le re-jouer).

| id | ability | porteur | canal | étage demandé | état de l'étage |
|---|---|---|---|---|---|
| 1200 | `SquigLaunchas` | `orksRukkatrukk` (MACHINE OF WAR) | surcharge | `AmountIsEqualOrGreater` × 2 | **déjà porté** (`orks.py`) |
| 1168 | `EntropyCannons` | `deathCrawler` (MACHINE OF WAR) | surcharge | `IsInTeamAura` + `HasNegativeModifier` | **déjà porté** (case-224) |
| 1179 | `CultDemagogue` | `genesPrimus` (pool) | surcharge | `GetFreeSurroundingTiles` + `GetAllAliveUnits` | **déjà porté** (`get_movable_tiles_for`) |

Les trois fois, **seul le call-site manquait** — c'est la troisième tranche de suite dans ce cas
(cf. `case-287r8` §3). « Prendre l'étage AVANT l'ability, et VÉRIFIER D'ABORD S'IL EXISTE » n'est pas
un conseil : c'est ce qui a fait tenir trois ids dans le budget d'un.

## 1. Les trois corps, verbatim

`SquigLaunchasAbility$$GetDynamicInvalidTargetReason` :

    if (!EntityExtensions.IsUnit(target)) return 0;
    entities = new AbilityEntities(caster, caster, target, caster, ...);   # owner = caster
    a = HasMinimumAdjacentOrks(         Direct(GetNumberConstant(0x78 nrOfUnits)) )
    b = HasMinimumAdjacentFriendlyUnits(Direct(GetNumberConstant(0x79 nrOfUnits_2)) )
    return (b || a) ? 0 : 2;

`EntropyCannonsAbility$$GetDynamicInvalidTargetReason` :

    if (!EntityExtensions.IsUnit(target)) return 0;
    entities = new AbilityEntities(caster, caster, target, null, ...);     # owner = NUL
    aura = IsInTeamContagionsOfNurgleAura(sel+0x60 Target, sel+0x48 Caster).ShouldTrigger(entities, 0x20)
    neg  = HasNegativeModifier(sel+0x60 Target, 0x10 FixedArmor).ShouldTrigger(entities, 0x20)
    comp = target.GetComponent<FixedArmorComponent>();
    return (aura || (comp.<+0x48> > 0 && neg)) ? 0 : 2;

`CultDemagogueAbility$$GetDynamicInvalidTargetReason` :

    range     = GetNumberConstant(0x44 range_2);            # = 2
    name      = GetStringConstant(0x0 unitId);              # = "genesSmnDecoy"
    freeTiles = battleQuery.GetFreeSurroundingTiles(GetMainTile(caster, state), range, 0, 1);   # slot 104
    allAlive  = battleQuery.GetAllAliveUnits(Nullable<int>(GetCurrentOwnerEntityId(caster)));   # slot 137
    battleQuery.GetSurroundingEnemies(target, allAlive, range, 0);        # slot 120 -- RESULTAT JETE
    if (freeTiles.Count() != 0) return 0;
    return allAlive.Where(u => GetUnitId(u) == name).Any() ? 0 : 2;

`2` = `TargetingRule.TargetMatchesDynamicRule`, `0x42f` = `EffectType.ContagionsOfNurgle_ArmorReduction1`,
`0x10` = `StatType.FixedArmor`.

## 2. `1179` — l'ambiguïté de `case-287r8` §11 est tranchée PAR L'ASSEMBLEUR

Le décompilé n'assigne pas le retour du slot 120, et le `Where` qui suit reçoit un `uVar7` qu'on
pouvait lire de deux façons. Les octets tranchent, et dans les deux sens :

    41 ff d2                 call r10                   ; slot 120 GetSurroundingEnemies
    48 8b 0d 03 bc 04 02     mov  rcx, [rip+...]        ; RAX ECRASE -- aucun `mov <reg>, rax`
    e8 16 c5 f0 fe           call ...
    ...
    48 8b cd                 mov  rcx, rbp              ; 1er argument d'Enumerable.Where
                                                        ; rbp == le 3e argument passe au slot 120
                                                        ; (`mov r8, rbp`), c'est-a-dire allAlive

**L'appel est MORT** — et sans effet de bord : `GetSurroundingEnemies` construit un `OrderedSet`
NEUF (via `GetSurroundingUnits`) et n'applique son `FilterInPlace` qu'à celui-là, jamais à `from`.
Deux des trois primitives que `case-287r8` §11 listait disparaissent avec lui.

⇒ **La règle ne lit PAS la cible.** Ses deux termes ne dépendent que du caster, donc son verdict est
le même pour toutes les cibles d'un état. Conséquence de mesure : sa bascule ne peut PAS s'exercer
cible par cible — il faut **deux montages**, et le critère de non-dégénérescence du probe est
agrégé par id, pas par montage.

### Le terme `onlyMovable` DOMINE les deux termes de disque

`GetFreeSurroundingTiles(center, d, includeCenter, onlyMovable)` =
`GetSurroundingTiles(center, d, onlyEmptyOrSteppable: 1, onlyWalkable: 1, onlyMovable, includeCenter)`
puis `FilterInPlace(IsFreeTile)`. Le filtre `onlyMovable` de `TileQuery.<IterateSurroundingTiles>d__6`
(champ `+0x30`) prend l'unité **sur la tuile centre** — ici le caster — et exige
`GetMovableTilesFor(unit, ignoreUnitFlags: 1, {overrideRange = d}).Contains(tile)`.

Or toute tuile atteignable en `d` pas est à distance hex `<= d` : `movable(d) ⊆ disque(d)`, donc
l'intersection **vaut** `movable(d)`. Et `IsFreeTile` (même corps que `TileExtensions$$CanAddUnit`,
établi en `case-287r8` §2) est plus strict que `onlyEmptyOrSteppable` comme que `onlyWalkable`. Les
trois termes de disque sont **dominés** ; ce qui reste est le `stop_set` de
`services/movement_query.get_movable_tiles_for`. Raisonnement de DOMINATION, pas approximation.

## 3. `1168` — `+0x48` est `Initial`, PAS la valeur courante

Le composant est identifié par la **paire de globales du call-site**, croisée avec
`UnitExtensions$$GetStatComponent` dont le `case 0x10` (= `StatType.FixedArmor`) appelle le MÊME
`GetComponent` générique avec le MÊME `FixedArmorComponent.ComponentId`. Ce n'est donc pas un
composant tiers : c'est le `StatComponent` de `FixedArmor`.

Et son `+0x48` est lu deux fois au décompilé :
`StatComponent$$GetStatPart` `case 3: return *(uint*)(this+0x48)` (= `StatPart.Initial`), et
`StatComponent$$get_CurrentValue` = `*(this+0x48) + *(this+0x10)` clampé.

⇒ **une cible dont le FixedArmor a été réduit à zéro reste VALIDE** — c'est l'armure de BASE qui
doit être non nulle. Lire la valeur courante fabriquerait un SUR-refus exactement dans le régime que
l'ability vise. Recoupement indépendant : `plagueburst_is_valid_adjacent_enemy_trigger` (1169, même
MoW) porte déjà `StatPart.INITIAL` sur le même couple de termes.

## 4. `1200` — le piège est le SEUIL, pas le prédicat

Les deux prédicats servent **déjà** `FulfillsSummonCriteria` dans l'`ExecuteBehaviour`. Seules les
constantes changent : ciblage `nrOfUnits` = 1 Ork / `nrOfUnits_2` = 2 amis (`0x78`/`0x79`), summon
`nrOfUnits_3` = 2 / `nrOfUnits_4` = 4 (`0x81`/`0x82`). Réutiliser le critère de summon au site de
ciblage aurait produit un **SUR-refus** — l'inverse exact de la dégradation que la tranche corrige.

Même famille de piège sur `1179` : `GetNumberConstant(0x44)` est **`range_2`**, et le gameconfig de
1179 porte **les deux** (`range = 2` ET `range_2 = 2`). Lire la mauvaise clé rendrait aujourd'hui la
même valeur et divergerait au premier rééquilibrage — une confusion silencieuse en valeur, ce que
la règle « un entier qui désigne passe par un enum » vise précisément.

## 5. Deux verrous de MONTAGE, mesurés

- **Sans munitions, les deux montages MoW ne mesurent RIEN.** Les deux abilities portent
  `munitionsCost = 1`, le seed BC partagé part à `MachineOfWarAmmo = 0`, et
  `AttackQuery$$GetInvalidTargetReason` court-circuite sur `ActiveAbility$$get_CanCurrentlyBeUsed`
  en rendant le littéral `1` (`ValidRequest`) AVANT la cascade. Premier jet du probe :
  `casterReason = 1`, « munitions épuisées », **après quatre tours de déblocage** — aucun nombre de
  tours ne lève ce court-circuit-là. Parade : `seed_bc_with_ammo` (repris de `probe_250`).
- **Un `--a-place` dont l'unité n'arrive pas en bataille ne fait REFUSER aucun placement.** La 4ᵉ
  cible du montage 1200 a disparu ; le probe imprime désormais le **substrat effectivement monté**.
  Résidu `#287-r13`.
  ⚠ **La CAUSE écrite ici était FAUSSE, et #287-r13 l'a réfutée par mesure.** « Un `necroWarden` en
  quatrième exemplaire ne monte pas » : `BC.Units` n'en porte qu'**un seul** template, et le même
  montage avec la 4ᵉ tuile en `(3,6)` au lieu de `(0,6)` monte les **quatre**
  (`placements verifies OK (8)`, rc 0). La cause était la **tuile** `(0,6)` — et `rl_duel build` la
  nommait déjà (`[error] placement NON HONORE par le natif: necroWarden (team2) demande @(0,6) mais
  present @[(2,3),(1,1),(4,6)]`, rc 3). Ce qui est réellement silencieux est le cas **voisin** : une
  unité du roster confiée au placement **natif** (sans `--a-place`) qui n'arrive pas — mesuré,
  `[build] placements verifies OK (4)` puis **rc 0** avec 3 unités sur 4. C'est ce cas-là que
  `_verify_roster` couvre. Détail : `docs/rl/case-287r10-consommateurs-verifies.md` §6.

## 6. Confrontation LIVE, avec attribution

`probe_287r11_regles_triggers_live.py` — géométrie **PLACÉE** (`--place`/`--a-place`, jamais subie),
attribution par désarmement **sur les SUR-refus seuls**, SOUS-refus compté à part (il survit au
témoin par construction — leçon de `case-287r8` §5).

| montage | id | cibles | verdicts natifs | refus reproduits à l'identique | sur-refus imputables | SOUS-refus | témoin désarmé |
|---|---|---|---|---|---|---|---|
| `1200` | 1200 | 3 | `{0x0: 2, 0x2: 1}` | **1** | **0** | **0** | 0 |
| `1168` | 1168 | 4 | `{0x0: 1, 0x2: 3}` | **3** | **0** | **0** | 0 |
| `1179-libre` | 1179 | 2 | `{0x0: 2}` | 0 | **0** | **0** | 0 |
| `1179-encercle` | 1179 | 3 | `{0x2: 3}` | **3** | **0** | **0** | 0 |

Board `C1_02` (5×7), seed 4242, `--no-ai`. Non-dégénérescence vérifiée **par id** : les deux
verdicts natifs sont exercés pour les trois. Le rayon de l'aura Contagion vaut **1** au premier tour
du porteur (seule la cible à `d = 1` passe) — cohérent avec case-224.

## 7. La garde

`tests/engine/test_287r11_regles_triggers_offline.py`, **six étages** : recensement ; les QUATRE
bras de 1200 (dont « 0 allié adjacent », qu'aucun montage live n'a pu produire) ; les seuils
ciblage/summon ; le terme `StatPart.Initial` de 1168 sous **mutant explicite** ; la bascule de 1179
et le fait qu'elle ne lit pas la cible ; les mutants en DELTA.

Vue rouge sur l'arbre témoin (`git archive` de `965f2b00`) : **8 failed / 2 passed** ; **10 passed**
après. Les DEUX verts sont nommés et c'est ce qui rend le rouge lisible :

- le bit au masque est un **acquis antérieur** (les trois ids posaient déjà `TargetMatchesDynamicRule`) ;
- le test des **seuils** garde une LECTURE, pas un delta — et c'est **structurel** : la faute qu'il
  vise est un SUR-refus, or le témoin est PERMISSIF, donc aucun substrat ne peut distinguer
  « accepte parce qu'il lit le bon seuil » de « accepte parce qu'il ne lit rien ». Il garde donc les
  deux canaux qui peuvent glisser indépendamment : l'**ordinal écrit au site** et la **séparation
  effective** des deux jeux de seuils sur un substrat.

## 8. Chiffres, re-dérivés des deux côtés

| | avant #287-r11 | après |
|---|---|---|
| règle ÉVALUABLE par le port (surcharge/table) | 28 | **31** |
| aucune règle (le `0` permissif) | 37 | **34** |
| dont **dette réelle** (surcharge native lisible) | **10** | **7** |
| dont `0` coïncidant avec le corps de base | 27 | 27 |

`probe_181` reste à **104/104**, `ABILITY_ATTACK_TYPE` à **0 manquante** (les trois ids étaient déjà
au registre : cette tranche n'ajoute aucune entrée, elle en surcharge trois).

## 9. Ce qui n'est PAS couvert

- **La branche AURA de 1168 n'est confrontée que dans un sens en live** : le montage produit une
  cible sous aura (acceptée) et trois hors aura (refusées), mais aucune cible **hors aura ET à
  armure négativement modifiée** — le seul régime où les deux branches se séparent. Couvert
  **offline** (étage 4 de la garde), pas live.
- **Le bras « 0 allié adjacent » de 1200 n'est pas exercé en live** : le montage `C1_02` ne rend que
  **3** cibles adverses, et les trois régimes utiles (1 Ork / 2 amis / 1 ami) les consomment.
  Couvert offline.
- **Le second terme de 1179 (`decoy vivant`) n'est pas exercé en live** : faire apparaître un
  `genesSmnDecoy` demande de caster l'ability, ce que la mesure de ciblage ne fait pas. Couvert
  offline (substrat avec decoy posé).
- Le volet **caster** (`options+0x30`, `CasterMatchesDynamicRule`) : inchangé, aucune règle portée.
- Les **7 dettes restantes** sont recensées par `probe_287r5_etages_bloquants.py` — deux d'entre
  elles (`1180 HeroicFusillade`, `1179`-comme-`1016 SendInTheNextWave`) demandent le même étage de
  mouvement que celui que cette tranche vient d'employer, donc leur coût a baissé.

## 10. Résidu `#287-r13` — TRAITÉ, et son énoncé était en partie FAUX

**Ce que cette section affirmait** : « un `--place`/`--a-place` dont l'unité n'arrive pas en bataille
est SILENCIEUX ». **Réfuté par mesure** (#287-r13) : `_verify_placements` couvre déjà ce cas et rend
`rc 3` en nommant l'unité, la tuile demandée et les positions obtenues.

**Ce qui était réellement silencieux** — et que `rl_duel._verify_roster` couvre désormais : une unité
du roster **confiée au placement natif** (donc jamais citée par `--place`/`--a-place`) qui n'arrive
pas. Mesuré : `--a-units necroWarden x4` avec trois `--a-place` monte **3 unités sur 4**, imprime
`[build] placements verifies OK (4)` et rend **rc 0**, en affichant un roster adverse à quatre
entrées. Détail et rayon de souffle : `docs/rl/case-287r10-consommateurs-verifies.md` §6.
