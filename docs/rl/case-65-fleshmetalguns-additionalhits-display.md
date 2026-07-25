# Case #65 — FleshmetalGuns (Volk) + sémantique DISPLAY du canal #179 (EffectAdditionalHits)

**Statut : RÉSOLU** (2026-07-22). Port des 3 effets cycliques de FleshmetalGuns **et** découverte
d'une sémantique générale du canal #179 côté PRÉDICTION qui invalidait la forme `predefined [min,max]`
utilisée jusqu'ici (indétectable avant, cf. §3).

## 1. Le port (blackObliterator / Volk, passif 0x429=1065)

- Cycle natif (`FleshMetalGunsAbility.CreateBehaviour @18121f6e0`) : au début du tour de Volk,
  `RemoveEffect(0x42b, 0x4bc, 0x4c5)` puis `If(UnitTurnsStarted % 3 == 1/2/0 → AddEffect(
  FocusedMalice 0x42b=1067 / RuinousSalvo 0x4bc=1212 / WarpHail 0x4c5=1221))`. ~~Le cycle est
  **natif** (l'état runner porte l'effet courant) — offline, seules les 3 classes d'effet sont
  portées~~ → **MAJ #222** : la ROTATION est désormais PORTÉE offline
  (`runner/operations/triggers/loki/fleshmetal_guns.py`, `ABILITY_TRIGGERS["FleshmetalGuns"]`) —
  trigger `On(0x16=TurnStart_Actions) & IsTurnOf(Self)` (`CreateTrigger @180e17450`, corps dédupliqué
  identifié par la table de pointeurs de méthodes). Parité tranchée et confirmée LIVE :
  `%3==1` Melta, `%3==2` Flame, `%3==0` HeavyRound. cf. `case-222-maillons-de-pose.md` §2.
- `BaseFleshmetalGunsEffect.CreateAdditionalHits @180f48260` : trigger `OwnerIsCaster &
  IsRangedAttack` ; nœud roll = `RandomAmount(ConfigVar(keyMin), ConfigVar(keyMax))`
  (`GetMinMaxDamage(effect, 0, …)`), nœud display = **`Average` des mêmes ConfigVars**
  (`GetMinMaxDamage(effect, 1, …) @180f11cc0`) ; count = `GetNumberConstant(keyCount)` ;
  profil = virtuel 0x728. Clés par variante (suffixe `""`/`_2`/`_3`) : base = minDmg/maxDmg/
  nrOfHits/Melta ; RuinousSalvo (`GetDamageProfileType @180f49fa0` → GetDamageProfile2) =
  jeu `_2`/Flame ; WarpHail (`@180f49ff0` → GetDamageProfile3) = jeu `_3`/HeavyRound.
  Le volet « Despoiled Ground » de WarpHail = `FleshMetalGuns_TileEffectAbility @18121fb40`
  (effet de tuile, hors #179, non porté).

## 2. LE FINDING GÉNÉRAL — display #179 = amount(MIDPOINT) + spread pipeline, PAS [min,max]

La prédiction native n'affiche **pas** les bornes du RandomAmount. Chaîne mesurée (ground truth
AllMods `CalculateBaseDamageWithAllModifiers @18102d3f0`, probe_65_allmods, round WarpHail) :

1. vars **int-résolues** par `GetVariableForLevel` (varTrace 56/57 : minDmg_3/maxDmg_3 = 698/1096
   = [388,609] × mult 1.8) ;
2. amount = **midpoint Fix64** `(v_min + v_max)/2` (nœud Average) — possiblement x.5 ;
3. bornes display = amount ± `CalculateDamageSpread @1810028e0` (±20 %, Round AwayFromZero) ;
4. bornes **TRONQUÉES en int** (op_Explicit — le param de `CalculateBaseDamageWithAllModifiers`
   est un `int baseDamage`) → inputs AllMods observés 718/1076 (WarpHail, avg 897) ;
5. per-coup : même pipeline armure/mods que l'arme (outs ×0.55 pierce HeavyRound = [395,592]).

Oracle reconstruit EXACT : r2 WarpHail (3184,4772) = arme 6×[399,598] + 2×[395,592] ; r3 Melta
(3890,**5830**) exige la **troncature** de l'étape 4 (avg 1246.5 → bornes 997.5/1495.5 → 997/1495
→ per-coup 748/1121 ; un round donnerait 5832).

## 3. Pourquoi la forme `predefined [min,max]` semblait valider partout

Les paires de vars du jeu sont presque toutes des paires **±20 % exactes autour de leur moyenne** :
SquigHound [1330,1994] (avg 1662), CordClaw [886,1330] (avg 1108), FleshmetalGuns Melta [554,831]
(avg 692.5), Flame [443,665] (avg 554) — pour elles, `predefined [min,max]` et `amount(midpoint)`
+ spread coïncident au round près (validations passées « exactes » non mensongères, juste
sous-déterminées). **La paire WarpHail [388,609] est asymétrique (±22.2 %)** → premier
discriminant : miss systématique ±22 (2 coups × ±11) du run 1 de probe_65_fleshmetal.

Conséquence pour les ports futurs : pour un `EffectAdditionalHits` à paire (minVar, maxVar), la
face PRÉDICTION doit émettre `amount = (v_min + v_max)/2` (canal `additional_hit_groups` forme
`amount`) — **jamais** `predefined [min,max]` (piège si la paire est asymétrique). La face COMBAT
(roll réel) reste `RandomAmount(min,max)` — bornes différentes du display, incohérence native à
mirrorer telle quelle (aucun consommateur combat du canal à ce jour). SquigHound/CordClaw laissés
en predefined (numériquement identiques, validés) — à basculer si un consommateur combat naît.

Fix offline associé (fidélité) : `get_base_damage_fix64` tronque désormais ses bornes en int
(mirror op_Explicit, no-op pour toute base entière) ; le canal amount ne tronque plus le midpoint
x.5 (`prediction.py` / `damage_prediction.py`).

## 4. Validation (session 71, MC1_67, Volk solo vs bloodSanguinary hp-player 30000)

- probe_65_fleshmetal seed 65002/65003 : **30/30 rows agreement 100 % (exacts, TOL 3 non
  consommée)** — cycle observé FocusedMalice→RuinousSalvo→WarpHail→FocusedMalice ; ranged avec
  groupes (12+ rows/branche), melee sans (gate IsRangedAttack, rows (1160,1740) exactes) ; 2 tuiles
  adjacentes à melee bloquée (élévation) où natif ET offline choisissent l'arme ranged = OK aussi.
- Counterfactuel groupes-OFF : 23/23 rows appliquées divergent (load-bearing), 0 row non-appliquée
  déstabilisée.
- Contamination écartée : LetTheGalaxyBurn contribution 0 tant que la cible n'est pas sur un
  hex-effect (prouvé #62 : delta Volk = exactement 2 coups Melta) ; FrenziedFiring jamais casté ;
  HeavyWeapon déjà géré (#66 45/45).
- Régression stages 12345 + 2468 : voir commit (baselines conservées).
