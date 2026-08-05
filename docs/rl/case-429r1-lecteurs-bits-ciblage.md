# #429-r1 — Les deux bits « sans lecteur » lisaient ailleurs, et l'un d'eux gardait une porte ouverte

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`.

`#429` avait laissé deux membres de `TargetingRule` en `READER_UNKNOWN` — `AbilityIsNotDisabledByConfigModification`
(bit 34) et `AllowDeadTarget` (bit 38) — après relecture des **huit** lecteurs de ciblage. Les deux
sont localisés. **Aucun des deux ne vit dans une cascade de ciblage**, et c'est la raison de fond
pour laquelle huit relectures exhaustives ne pouvaient pas les trouver : le périmètre était le bon
pour la question posée, et faux pour ces deux-là.

## 1. L'outil qui ne pouvait pas conclure, re-mesuré

`mcp__ghidra__search_code` en mode littéral rend **`literal_total: 0`** pour le motif
`>> 0x26 & 0xffffffffffffff01`, qui apparaît **verbatim** dans le décompilé de
`IdunBattle.Entities.Abilities.AActiveAbility$$CanContinueOnDeadTarget` — obtenu par
`mcp__ghidra__decompile_function`, sur le même binaire, dans la même session. Un outil qui ne
retrouve pas ce qu'il vient lui-même de rendre ne fonde **aucune** conclusion négative. La mesure de
`#429` (« `literal_total: 1` pour un motif présent deux fois ») était déjà juste ; celle-ci est plus
tranchante parce qu'elle est **reproductible en deux appels**.

Ce qui l'a remplacé : **un scan d'instructions**, `scripts/python/probe_429r1_bit_readers_scan.py`.
Il lit les sections de code du `GameAssembly.dll` du build qui fait foi (via le foyer `build_pin`,
qui refuse si installé ≠ versionné) et décode les quatre formes par lesquelles un test de bit ≥ 32
s'écrit en x86-64 — `shr r64,N`, `shl r64,63-N`, `bt r64,N`, `movabs r64,1<<N`. Un `test r/m64, imm32`
ne peut pas porter un tel bit : l'immédiat est signe-étendu sur 32 bits.

**Contre-épreuve intégrée** (`--check`) : le scan du bit 38 doit retrouver
`AActiveAbility$$CanContinueOnDeadTarget`, établi par décompilation indépendante. Sans elle, un
silence du scanner sur le bit 34 ne vaudrait rien — exactement le reproche fait à `search_code`.

Résultat, filtré sur `IdunBattle*` (le reste est du BCL : SHA-384/512, `System.Uri`, `Hash128`) :

| bit | sites bruts | sites `IdunBattle*` | ce que c'est |
|---|---|---|---|
| 34 | 29 | **1** | `AnnihilatorBeamAbility$$GetDynamicInvalidTargetReason+0x1c`, `movabs 1<<34` — un **producteur** |
| 38 | 27 | **2** | `AActiveAbility$$CanContinueOnDeadTarget+0x1f` (`shr r64,38`) — le **lecteur** ; `GreatFrostAxeAbility$$GetTargetingOptionsForContinue+0x6a` (`movabs 1<<38`) — l'**unique** porteur |

## 2. Bit 34 — un CODE DE RAISON, jamais un bit testé

```
AnnihilatorBeamAbility$$GetDynamicInvalidTargetReason(caster, casterTiles, target, targetTiles):
    if (AbilityConfiguration.GetNumberConstant(config, 0x11) > 0) return None;
    return AbilityIsNotDisabledByConfigModification;          // 0x400000000
```

La constante `0x11` est **exactement** celle que
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsDisabled` teste
en premier (`disabled = valeur < 1`). Le nom du bit se lit alors littéralement : *l'ability n'est pas
désactivée par une modification de configuration*. Le contexte produit existe côté i2 —
`UI/GuildBossSupportingBattle_Modification_Ability_AnnihilatorBeam_nrOfTargets_detailed` :
« *{ABILITY_NAME} targets {TARGET_AMOUNT} fewer hexes* ». Le terme d'infobulle
`IdunLocalization.Tooltips$$BattleHUD_Tooltip_AbilityDisabledByConfigModification_Description` est ce
qui **présente** ce code ; il ne le produit pas.

Le code remonte par le point d'extension `TargetMatchesDynamicRule` (bit 1), dont le natif rend le
verdict de la déléguée **tel quel**. Donc : catégorie **`REASON`**, `reader` = la déléguée. Rien à
porter — `AnnihilatorBeam` (1071) n'est pas au registre, et le bit n'arme aucune règle.

> ⚠ Le terme i2 n'a **aucun appelant CODE** (2 xrefs, toutes deux `DATA`). Ce n'est pas ce qui a
> tranché : les termes `Tooltips$$*` sont posés par des composants `Localize` côté scènes, hors DLL.
> Ce qui tranche est le producteur, lu au décompilé.

## 3. Bit 38 — lu, et il gardait une porte que le port laissait ouverte

```
AActiveAbility$$CanContinueOnDeadTarget(this):                 // slot 17 de IActiveAbility
    SetConfigValuesInTargetingOptions(ref _targetingOptionsForContinue);   // ne touche que Range
    return (_targetingOptionsForContinue.Rules >> 0x26) & 1;
```

**Le masque lu n'est pas le masque principal.** `AActiveAbility` en porte deux : `_targetingOptions`
(+0x70) et `_targetingOptionsForContinue` (+0xb0, donc `Rules` à +0xd8), ce second posé par le `.ctor` :

```
n = this.GetTargetingOptionsForContinue();                     // virtuel, vtable +0x458
_targetingOptionsForContinue = n.HasValue ? n.Value : targetingOptions;
```

C'est la clé du résidu : **aucun `TARGETING_OPTIONS` du registre ne pouvait porter ce bit**, et
compter ses porteurs sur le masque principal rendait un *zéro de méthode* — la faute même que #429
avait diagnostiquée pour d'autres règles, reproduite ici sur un autre axe.

**Inventaire des surcharges, par deux sources indépendantes** — la question que
`abilities/targeting.py` déclarait ouverte (« l'inventaire des overrides n'a pas été relevé ») :

* dump Il2CppDumper (toutes les méthodes de toutes les classes, **sans déduplication de corps**) :
  `CanContinueOnDeadTarget` n'a qu'**une** implémentation, `AActiveAbility` — **aucun override** ;
* dump Frida du build courant : `GetTargetingOptionsForContinue` a **3** entrées — la base,
  `EntropyCannonsAbility`, `GreatFrostAxeAbility` — et le scan d'instructions montre que seule la
  dernière arme le bit 38 (`TargetingOptions..ctor(&opts, &<statics+0x40>, 0x4000000000)`, l'overload
  « preset + flags additionnels », qui est un `Rules |= additionalRules` sur une copie du template).

La base, elle, dérive du masque principal en forçant `ForceMeleeTarget = RangedBool.False` et en
ajoutant `AllowIgnoreForcedAttackTarget` (1 << 40) — **jamais** `AllowDeadTarget`.

⇒ **`GreatFrostAxe` (1089) est la seule ability de tout le binaire dont `CanContinueOnDeadTarget()`
rende `true`.**

### Le consommateur, et ce qu'il gardait

```
ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility(abilityType, target):
    if (!EntityExtensions.IsUnit(target))       return false;
    if (UnitExtensions.IsAlive(target, state))  return false;
    return !ability.CanContinueOnDeadTarget();          // slot 0x11, resultat ^ 1
```

C'est le **premier** gate d'`ActiveAbilityOperation$$ExecuteInternal`, avant `IsInvalidTarget`. Le
port ne l'avait pas, et deux docstrings l'actaient ainsi en nommant le blocage : le bit « n'a été
RE-lu pour AUCUNE ability », donc un défaut « refuse » risquait de casser les résurrections.

**Les deux moitiés de ce blocage sont levées par la mesure** : le bit EST lu (§ ci-dessus), et le
défaut « refuse » n'est pas une devinette — c'est ce que le natif fait pour 103 abilities sur 104.

## 4. Le trou, chiffré

Un gate absent ne prouve pas un trou : le gate **suivant** aurait pu refuser les mêmes casts, auquel
cas le porter serait du code mort. `probe_429r1_dead_target_gate.py --volet trou` tranche, sur un
**état réel** où l'on marque une cible morte :

* `is_invalid_target` **seul** ACCEPTAIT **43 / 104** abilities du registre ;
* le gate #429-r1 en refuse **42**, et laisse passer **exactement 1089 `GreatFrostAxe`**.

Le gate n'est donc ni redondant ni inerte.

## 5. La confrontation live, et sa morsure

`tests/engine/runner/test_429r1_dead_target_gate_live.py` (5 tests, ~8 s). Montage **écrit**
(positions forcées, board `MC1_67`) : `spaceWulfen` (2,2), `ultraInceptorSgt` (1,3),
`tyranWingedPrime` (2,3) à 1 PV, **plus un second ennemi loin**. `spaceWulfen` tue, puis
`ultraInceptorSgt` caste `DeathFromAbove` (1003) sur le **cadavre**, depuis une tuile adjacente.

| | tirages RNG | verdict |
|---|---|---|
| NATIF | **0** | action **non consommée** (`hasAction` reste vrai) = refus en tête d'opération |
| PORT pré-fix | **6** | `is_invalid_target` rendait **0** — un summon spawné, **5702 dégâts sur un cadavre** |
| PORT post-fix | **0** | `dead_target_not_allowed` — accord avec le natif |

La contre-épreuve est **intégrée** : le même cast est rejoué avec le gate débranché, et le test
exige que les tirages soient alors `> 0`. Un vert du test principal ne prouverait rien sans elle.

**Deux ennemis, et ce n'est pas cosmétique.** Premier jet avec un seul : le tuer TERMINE la bataille,
`decisionView`/`observeBattle` cessent de publier les unités, le cadavre devient invisible et toutes
les sondes rendent `None` — un montage qui ne mesure plus rien, et dont le silence ressemble à un
résultat. Le test garde ce préalable explicitement (`test_le_montage_pose_bien_un_cadavre_visible_et_positionne`).

### Généralisation, et la ligne qui reste rouge

* **Seed** : `31337` sur le même board → chiffres identiques (natif 0 / port pré-fix 6 / post-fix 0).
* **Rôles inversés + porteur du bit** : `ultraInceptorSgt` tue, `spaceWulfen` caste `GreatFrostAxe`
  (1089) sur le cadavre → le gate rend bien **faux** (le porteur du bit 38 n'est PAS refusé). Sans
  cette ligne, un gate qui refuserait *tout* passerait les quatre autres tests.
* **Board** : `C1_74` — montage **NON INSTALLÉ** (la cible survit à 1 PV), et le scénario le dit
  (`why` non vide → `pytest.fail`, jamais un vert). `C3_01` refuse le placement `(6,6)`. Un seul
  board est donc confronté ; c'est un non-couvert, pas un accord.
* ⚠ **Une divergence RÉSIDUELLE, mesurée sur ce même cas 1089** (résidu `#429-r1-r3`) : le natif
  refuse quand même (0 tirage, action non consommée) alors que le port **exécute** (la glace se
  pose). Le refus natif vient donc du gate **suivant**, où une règle que le port ne porte pas encore
  refuse un cadavre — vraisemblablement la PORTÉE (le natif retire l'unité morte du board ; le port
  lui garde son `PositionComponent`). **Ce n'est pas une régression de cette tranche** :
  `port_sans_gate_last` est *identique* à `port_last` pour 1089, la divergence lui préexiste. Bilan :
  **43 divergences avant, 1 après**.

**Ce que le live ne peut PAS discriminer, et il faut le dire** : `IsDeadUnitAndNotAllowedByAbility`
et `IsInvalidTarget` sortent tous deux avant `On(0x2a)`, avant tout dégât et avant les flags de tour.
Leur observable depuis le runner est **identique**. Le live établit « le natif no-oppe » ; que ce soit
*ce* gate-là est établi au décompilé, et c'est le §4 qui montre que le port en avait besoin.

## 6. Ce qui change dans l'inventaire

`READER_UNKNOWN` passe de **2** entrées à **0**. La catégorie **reste** : c'est la case honnête du
prochain membre non localisé, pas une case à vider par principe.

* bit 34 → **`REASON`**, reader = `AnnihilatorBeamAbility$$GetDynamicInvalidTargetReason`.
* bit 38 → **`GATE_OPERATION`**, kind NEUF : « règle de refus lue **hors ciblage**, par un gate
  d'OPÉRATION ». Deux traits la séparent des `GATE_*` : le natif **abandonne l'opération** au lieu de
  rendre un `IBrokenTargetingRule`, et son masque n'est pas forcément celui de l'ability — d'où
  `armed_by = "TargetingOptionsForContinue (+0xb0), PAS le masque principal (+0x70)"`.

Ce kind ouvre **structurellement** la dérogation `ported_by` (le champ #447), au lieu d'allonger une
allowlist nominative : une règle dont le natif ne rend jamais le code ne peut, par construction, pas
être « portée » au sens `int(TR.<X>)` rendu. La garde reste mordante —
`test_contre_epreuve_ported_by_hors_allowlist` pose `ported_by` sur `TargetIsEnemy` (un vrai code de
refus) et exige le rouge.

## 7. Trouvé en chemin

**Le dépôt se contredisait déjà.** `engine/runner/operations/active_ability.py` écrivait, avant cette
tranche : « `AActiveAbility$$CanContinueOnDeadTarget` = **bit 38 de options+0x28** » — donc le lecteur
du bit 38 était **nommé au bon endroit** pendant que `targeting_rule_inventory.py` le classait
`READER_UNKNOWN` en affirmant que le slot 0x11 « lit l'entrée de base d'ability — **PAS ce bit** ».
Deux modules du même dépôt, deux affirmations opposées, aucune garde entre les deux. La localisation
manquait d'un seul cran d'indirection, pas d'une découverte.

**Un `int(TR.<X>)` dans un `return` n'est pas toujours un code de refus.** Le critère de dérivation
de `probe_429_targeting_rule_inventory.rules_returned_by_port` lit tout `int(TR.<X>)` sous un `return`
comme un refus rendu. Écrire `return replace(base, rules=... | int(TR.AllowIgnoreForcedAttackTarget))`
— une **construction de masque** — faisait donc rougir la garde des PERMISSIONS. Le `int(...)` est
sorti du `return`, avec le commentaire qui dit pourquoi. Le critère reste imparfait sur ce point ; il
est nommé au lieu d'être contourné en silence.

**`--hp-target` ne suffit pas à un montage « cadavre »** : il faut au moins deux adversaires, sinon la
victoire coupe les vues (cf. §5).

## 8. Résidus nommés

* ~~**`#429-r1-r1` — l'attaque NORMALE sur cadavre n'est pas gatée côté port.**~~ **LIVRÉ le
  2026-08-05** — `docs/rl/case-429r1r1-attaque-normale-cadavre.md`. La question préalable posée ici
  a **déplacé l'étage** : le port n'a pas « deux portes » mais **onze**, et
  `DamageHandler.visit_AttackUnitMessage` n'en est qu'une — `engine/**` ne construit **aucun**
  `AttackUnitMessage`, les attaques déclenchées appellent `AttackDamageOperation.execute`
  directement. Le foyer est donc l'OPÉRATION. Mesuré : natif 0 tirage / port pré-fix **6 tirages,
  6049 dégâts sur un cadavre, action consommée** / post-fix 0.
* **`#429-r1-r3` — la dernière divergence du gate cible-morte : `GreatFrostAxe` (1089).** Le porteur
  du bit 38 échappe correctement au gate #429-r1, puis le natif le refuse par le gate SUIVANT que le
  port ne reproduit pas : `is_invalid_target` rend `0` sur un cadavre positionné. Piste première : la
  PORTÉE — `TargetingQuery$$GetTiles(target)` est vide côté natif pour une unité morte (retirée du
  board), alors que le port garde le `PositionComponent` du cadavre (`get_tiles` rend `[]`, mais le
  volet portée de `targeting.py` ne passe pas par lui). Fermer cette ligne rend le port exact sur
  **104/104**. Mesure : `probe_429r1_dead_target_gate.scenario_live(..., ability=1089,
  killer="ultraInceptorSgt", caster="spaceWulfen")`.
* **`#429-r1-r2` — quatre formes d'instruction hors de portée du scanner**, à dire chaque fois qu'on
  l'invoque : constante lue depuis `.rdata` (`and rax, qword ptr [rip+X]`), `bt` à opérande mémoire,
  test compilé en deux moitiés 32 bits (`test dword ptr [x+4], imm32` — le bit 34 y est le bit 2 du
  dword haut), et masque passé par une **variable** (le bit testé n'est alors pas un immédiat). Le
  scan ÉLARGIT la couverture, il ne la CLÔT pas. Sa contre-épreuve dit sur quelle forme il a mordu,
  pas sur celles qu'il ignore.

## 9. Re-dériver

```
python scripts/python/probe_429r1_bit_readers_scan.py                 # bits 34 et 38
python scripts/python/probe_429r1_bit_readers_scan.py --check         # contre-epreuve seule
python scripts/python/probe_429r1_bit_readers_scan.py --all-bits      # carte des 64 bits
python scripts/python/probe_429r1_dead_target_gate.py --volet bit
python scripts/python/probe_429r1_dead_target_gate.py --volet trou --state-file <ABSOLU>
python -m pytest tests/engine/runner/test_429r1_dead_target_gate_live.py -q
python -m pytest tests/engine/runner/test_targeting_rule_inventory.py -q
```

⚠ Les chiffres de cette fiche se **re-dérivent**. `43 / 104` bouge à chaque ability portée.
