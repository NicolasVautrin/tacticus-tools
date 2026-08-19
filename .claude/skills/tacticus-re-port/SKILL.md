---
name: tacticus-re-port
description: Protocole de rétro-ingénierie (ghidra) + portage FIDÈLE du moteur Tacticus, côté DÉCISION (prédiction/playbook/scoring IA) ET côté COMBAT (runner/opérations/ECS). Ordre non négociable — recon du kit complet, RE fidèle (le décompilé = vérité, jamais l'expérience live), mirror 1:1 des fonctions natives NOMMÉES (jamais inventer), décomposition par étage d'un écart de dégât (jamais fitter un scalaire), validation des DEUX faces (décider ≠ exécuter, le no-op combat est silencieux). Use when reverse-engineering a Tacticus game mechanic, porting one into engine/ (prediction, playbook, runner/combat), or when a damage/prediction value diverges offline vs live.
user-invocable: true
---

# Tacticus — RE + portage fidèle (DÉCISION + COMBAT)

Le but du portage `engine/` est un moteur **fidèle ET modifiable** : il RE-CALCULE chaque
mécanisme depuis ses entrées (jamais un cache d'outputs natifs), avec une **structure Python qui
colle à la structure du jeu**, pour qu'on puisse changer un paramètre/une règle **au bon endroit**,
comme dans le jeu, et le valider **méthode par méthode** contre le décompilé.

La fidélité a **DEUX faces distinctes** — les confondre est l'angle mort n°1 :
- **DÉCIDER** comme l'IA native : prédiction / scoring / playbook (« faut-il caster X ? quel dégât
  PRÉDIT ? quelle cible ? »). Registres : `engine/playbook` + `engine/services`.
- **EXÉCUTER** comme le moteur natif : le runner qui APPLIQUE l'action et mute l'état (ECS).
  Registres : `engine/runner` + `AbilityHandler.ABILITY_CLASSES` + `operations/*`.

**Ordre du protocole (chaque phase avant la suivante) : 0 RECON → 1 RE fidèle → 2 PORTAGE (mirror
la structure native, côté DÉCISION §2A et/ou COMBAT §2B) → 3 DÉCOMPOSITION si le dégât diverge →
4 VALIDER + TRACER.** L'infra (hash-discipline, résolution runtime, démarrage ghidra-mcp, amorce,
« Ne jamais ») reste dans `CLAUDE.md` — s'y référer avant de toucher ghidra ou une session live.

---

## 0. RECON D'ABORD — lire le KIT COMPLET de l'unité AVANT toute RE / probe / ghidra

**Le tout PREMIER geste face à un mécanisme lié à une unité** (divergence de dégât, effet non porté,
formule d'ability, scoring d'une attaque…) **= lire le KIT COMPLET de l'unité concernée** :
`gameconfig.py <unit>` (traits + actives + **passives** décodés, avec les nombres) **ET** le texte
de règles i2 — **AVANT** de poser un hook, lancer un probe live, décompiler dans ghidra, ou écrire
une ligne de port. La recon oriente TOUTE l'enquête : sans elle, on RE à l'aveugle le mauvais
mécanisme.

- **Comment** : `python gameconfig.py <unit>` (kit complet : traits + `[active]` + `[passive]`),
  puis `--ability <name>` / `--trait <name>` pour les tableaux par-niveau + flags
  (`variablesAffectedByRarityBonus`), et le **texte i2** (`--ability`/`--trait` le rend). Croiser
  avec `unit_map.py` si on cherche une unité qui porte un mécanisme donné. Ordre : **gameconfig →
  i2 → (seulement alors) ghidra/probe**.
- **Ce que SEUL le kit révèle** (invisible côté effets capturés / `decisionView`) :
  - **passif vs actif** : un **passif** est indexé par SON niveau/canal propre, PAS forcément
    l'`activeAbilityLevel` de l'ability active — et sa magnitude peut ne PAS être rarity-scalée.
    (Ex. **SmashaEad = PASSIF** « +437 Damage » ; le confondre avec l'active fausse level+multiplier.)
  - **conditionnels / triggers / snowball** : n'existent QUE dans le **texte i2**
    (« for every 2 hits… », « increased by 73 per hex traversed », « until start of next turn »).
  - **mécaniques de trait transitoires** (ex. GetStuckIn coups bonus, BeastSlayer) qui ne
    remontent JAMAIS comme un effet nommé (`decisionView.effects` est aveugle).
- **Pourquoi** : faute déjà commise (#75 : sauté sur `statModSources` + décompilé combat de SmashaEad
  **avant** de lire que c'est un **passif** — la lecture du kit a montré que 599/437/300 ne se
  réconcilient PAS par level/mult, ce que le décompilé seul ne disait pas ; #47 GetStuckIn +2 coups
  manqué en ne lisant que les effets capturés). Un mécanisme PAR-UNITÉ ne peut pas être RE
  correctement sans savoir QUEL trait / active / passif le porte. La recon coûte ~1 commande ; la
  sauter coûte des heures de RE mal ciblée. (Mémoires `feedback_recon_units_first` +
  `feedback_recon_full_kit_not_captured_effects`.)

---

## 1. RE = décompilé fidèle, JAMAIS l'expérience live

Pour comprendre un mécanisme (formule de dégât, prédiction, scoring IA…), la méthode attendue est la
**rétro-ingénierie fidèle via ghidra** (le décompilé = vérité), **pas** l'expérimentation live
(« je fais varier un input et j'observe la sortie pour deviner la formule »).

- **Le live sert UNIQUEMENT de confirmation** d'un mécanisme déjà compris depuis le code natif,
  jamais de source pour deviner/fitter une formule.
- **Chercher d'abord les fonctions NOMMÉES décomposées** (`mcp__ghidra__search_symbols_by_name` sur
  le namespace, ex. `DamageCalculations$$`, `DamagePrediction$$`) **avant** de grinder une fonction
  inline géante (`PredictAttackRaw` ≈ l'inline optimisé de ~80 méthodes propres). Porter depuis les
  feuilles propres (1:1 méthode→fonction), pas depuis l'inline.
- **Les traces/hooks live = un OUTIL DE CIBLAGE de la RE, JAMAIS un outil de découverte de formule.**
  Le SEUL usage légitime d'un hook live dans une enquête RE : poser **UN** hook + `Thread.backtrace`,
  lire la **chaîne d'appels** (frames `il2cpp+0xRVA` → soustraire `0x180000000` → adresses de
  fonctions), en déduire **quelle(s) fonction(s) NOMMÉE(S)** est en jeu, puis **aller LIRE ces
  fonctions dans ghidra** (`decompile_function`). Le backtrace répond à **« QUELLE fonction dois-je
  RE ? »**, jamais à « quelle est la formule / la valeur ? » — ça, c'est le décompilé qui le donne.
  - **Anti-pattern PROSCRIT** (déjà commis, ~10 reinjects gaspillés en une session) : empiler hook
    après hook (capturer la sortie de la feuille A, puis B, puis les 29 feuilles, puis le bonus…)
    pour **re-découvrir en tâtonnant** ce que la fonction nommée du décompilé donne en 30 s de
    lecture. Dès qu'un backtrace (ou un simple `search_symbols_by_name` sur la classe de service)
    pointe une fonction nommée pertinente (`CalculateElevationBonusModifier`,
    `CalculateDefenderModifiersForPrediction`, …), **STOP les hooks → lire le décompilé**. Réflexe de
    départ : `search_symbols_by_name` sur la classe de service (`DamageCalculations$$`, …) et LIRE,
    **avant** de poser le 1ᵉʳ hook.
  - Corollaire : ne pas confirmer live une valeur (« le +50 vient-il d'ici ? ») qu'on peut LIRE dans
    le code. Le live ne confirme QUE ce que le décompilé ne peut pas trancher statiquement (ex.
    valeur runtime d'un état, ordre d'énumération non-RE, generic-sharing ambigu).
- **Ne JAMAIS asserter un mécanisme sans l'avoir lu dans le décompilé** : un pattern qualitatif
  observé (« la largeur dépend de la cible ») ≠ formule vérifiée. Marquer toute déduction non encore
  lue dans le code comme **hypothèse**, et la confirmer dans ghidra avant de l'affirmer ou d'agir
  dessus.
- **Pourquoi** : les expériences live coûtent du temps, sont bruitées (positions/effets/RNG cachés),
  et mènent à des fits faux (cf. hypothèses crit puis perçage-seul réfutées). Le décompilé donne le
  mécanisme exact, déterministe et modifiable. (Mémoire `feedback_re_ghidra_not_experiment`.)

### 1.1 Confirmer live = ADAPTER LES TEAMS à l'objectif

Quand le live sert à **confirmer** un mécanisme (jamais à le deviner), **toujours crafter les rosters
+ tailles + positions pour que la condition à observer SOIT remplie et STABLE assez longtemps**. Ne
pas lancer une bataille générique/aléatoire puis se battre contre ses dynamiques émergentes.

- **Garder vivante l'unité observée** : team adverse faible/peu nombreuse, ou la driver en lieu sûr
  (une unité en sécurité survit indéfiniment — prendre autant de tours que nécessaire).
- **Éliminer le bruit** : 1 mécanisme à la fois (ex. si on étudie MES summons, pas de summoners
  ennemis qui polluent l'observation).
- **Garantir l'occasion d'agir** : un ennemi vivant à portée/atteignable pour voir l'attaque/le move.
- **DRIVER les positions, ne pas blâmer la géométrie** : si le setup ne remplit pas la condition
  (ex. attaquant hors portée de sa cible), **bouger l'unité** (`applyAction` move) jusqu'à la
  condition — ne pas conclure « bloqué par la géométrie de spawn ».
- **Pourquoi** : faute déjà commise (scarabs focus/tués en 1 round avant d'avoir pu agir → impossible
  de valider « les summons agissent-ils par tour ? » ; la cause était le setup, pas le mécanisme).
  (Mémoires `feedback_adapt_teams_to_validation_objective`, `feedback_drive_positions_dont_blame_geometry`.)

### 1.2 Méthodes natives DIFFICILES — procédure d'escalade (fonction géante, aliasing, gshared)

Quand la lecture statique d'une fonction devient un marécage — décompilé de dizaines de milliers
de caractères, register-aliasing, indirections gshared (`DAT_18xxxxxxx`, dispatch d'interface,
rgctx) — on n'ABANDONNE PAS et on ne DEVINE PAS : on suit l'escalade ci-dessous. « Trop gros »
n'est JAMAIS une raison d'arrêter une RE ; le coût-token d'une lecture ciblée est négligeable
devant un port faux + sa re-dérivation. **Fil rouge : gap prédiction #152** — mécanisme générique
`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` → 1ʳᵉ op `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` (si `Current != Initial`, itère `get_Modifications` et NÈGUE chaque montant per-source),
symétrique de l'attaquant `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` (~55K chars). Deux
échecs de méthode y ont été commis (abandon sur la taille ; gate deviné) — cette procédure les
interdit. L'inconnue finale (« quelle entité / quel stat derrière l'interface ? ») a été résolue en
STATIQUE PUR par l'étape C.3, sans hook.

#### A. Décompilé surdimensionné (> ~25K tokens) = un FICHIER à parser, pas un mur

1. **Comportement de l'outil** : au-delà de ~25K tokens, `mcp__ghidra__decompile_function` REFUSE
   l'inline et SAUVE la réponse JSON complète dans un fichier — le chemin est dans le message
   d'erreur (`...\tool-results\mcp-ghidra-decompile_function-<ts>.txt`). Ce n'est PAS un échec :
   le décompilé complet est là, structuré (`{result: [{name, code, signature, ...}]}`).
2. **Exploitation = parsing ciblé, jamais lecture linéaire** (le fichier est UNE ligne JSON géante :
   ni `Read` brut, ni « je lis tout ») :
   ```
   python -c "
   import json
   d = json.load(open(r'<chemin tool-results>.txt', encoding='utf-8'))
   code = d['result'][0]['code']; lines = code.split(chr(10))
   print('TOTAL', len(lines), '|', d['result'][0]['signature'])
   for i, l in enumerate(lines):
       if '<PrimitiveSuspecte>' in l or 'DAT_<token>' in l:
           print('%5d: %s' % (i, l.rstrip()))
   "
   ```
   puis extraire des FENÊTRES de contexte (`for i in range(a,b): print(lines[i])`) autour des hits.
   Sorties console : ASCII only (cf. CLAUDE.md).
3. **Vécu #152** : IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction = 55K chars, 1395 lignes → l'enquête complète a tenu en ~15 lignes
   greppées + 2 fenêtres (~120 lignes lues au total). L'abandon initial (« 55K c'est trop ») avait
   bloqué la RE pour rien.

#### B. Naviguer une fonction géante : call-sites + JUMEAU symétrique

1. **Points d'ancrage** (on ne lit JAMAIS une géante du début à la fin) :
   - les **call-sites des primitives NOMMÉES** suspectes (le grep §A) ;
   - les **flags littéraux** aux call-sites (`..., 1, ...` vs `..., 0, ...` — ex. `negatesDamage`) ;
   - les **tokens `DAT_18xxxxxxx`** (metadata il2cpp lazy-init — cf. C.2) ;
   - les **boucles de copie inline** (`do{...}while(lVar!=0)` memcpy unrollé) : elles donnent la
     TAILLE de la struct copiée et sa destination locale (`param_4` → `&local_298`) — c'est la BASE
     pour traduire toute variable aliasée en offset de champ (`local_288` = `local_298+0x10`).
2. **Technique du jumeau** : quand une fonction a un SYMÉTRIQUE (attaquant/défenseur,
   gagnant/perdant, surcharges à Slot voisins dans dump.cs), **diff des DEUX call-sites de la même
   primitive** — ça isole le mécanisme sans lire les deux fonctions en entier.
3. **Vécu #152** (diff obtenu en ~15 lignes greppées de chaque côté) :

   | | Attaquant `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` (l.611) | Défenseur `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` |
   |---|---|---|
   | Entité fetchée | `plStack_290` = struct+0x8 = **`entities.Caster`** | `local_288` = struct+0x10 = **`entities.Target`** |
   | StatComponent | couple `DAT_18325bda0/DAT_18328b048` = case **0** de `GetStatComponent` = **Attack** | couple `DAT_1831fb970/DAT_1831b6fc8` = case **3** = **Defense** |
   | `negatesDamage` | `0` → montants tels quels | `1` → montants **NÉGUÉS** |

   La structure asymétrique add/negate est PROUVÉE sans avoir lu 2×1400 lignes.

#### C. Échelle d'escalade pour un primitif NON RÉSOLU

Cibles typiques : slot d'interface virtuel, token `DAT_` (classe il2cpp ou MethodInfo), offset de
champ d'une struct par valeur. Dans l'ordre, chaque étape est bon marché :

1. **Le jumeau / les variantes** (cf. §B.2) — surcharges, Slot voisins, la version courte d'une
   paire (le défenseur IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction se lit inline là où l'attaquant IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction déborde).
2. **Résoudre un token `DAT_`** : `mcp__ghidra__list_xrefs` sur le token → chercher une **PETITE
   fonction NOMMÉE** qui utilise le MÊME token dans un contexte discriminant, et la lire.
   Vécu #152 : xrefs de `DAT_1831b6fc8` → `UnitExtensions$$IdunBattle.Entities.UnitExtensions$$GetStatComponent` (petite,
   un `switch(statType)`) → le token n'apparaît QUE dans `case 3` ⇒ c'est le composant du
   StatType 3 ; l'enum `StatType` (dump.cs) donne `Defense = 3`. Patterns à connaître :
   - `FUN_1801f2030(&DAT_...)` en tête de fonction = **lazy-init metadata** — l'ORDRE du bloc ne
     dit RIEN, c'est l'USAGE du token dans le corps qui l'identifie ;
   - `*(DAT+0x20)` = classe déclarante d'un MethodInfo, `*(ushort*)(DAT+0x50)` = slot → la boucle
     qui compare `interfaceOffsets` puis indexe la vtable = **dispatch d'appel d'interface** ;
   - `*(int*)(KLASS+0xe4)==0 → il2cpp_runtime_class_init` = classe ; `*(KLASS+0xb8)` = static fields.
3. **Résoudre une signature / un offset de champ = le dump.cs Il2CppDumper du MÊME hash**
   (`data/dumps/<HASH>/dump.cs` — vérifier `HASH` == build du projet ghidra, cf. CLAUDE.md).
   Il donne (a) la **signature C# exacte** (nombre/type/rôle des params, méthode d'instance vs
   static, surcharges départagées par VA/Slot) et (b) le **layout complet des structs avec
   offsets**. Vécu #152 — c'est CETTE étape qui a tout tranché : signature
   `CalculateDefenderModifiersForPrediction(IMatchState, AbilityEntities, List<EffectWithTarget>)`
   ⇒ la struct copiée = `AbilityEntities` ; son layout ⇒ `+0x8 Caster`, `+0x10 Target` ⇒
   `local_288` = **la CIBLE** ; et `CalculateModifiersFromStatModifications(StatComponent stat,
   bool negatesDamage, IMatchState)` nomme le flag. Le hook de mesure prévu est devenu inutile.
4. **BORNE explicite, puis MESURER.** L'effort statique est BORNÉ : si après (1)-(3) — ordre de
   grandeur 3 à 5 lectures ciblées, PAS des heures — l'inconnue reste ouverte, on bascule sur la
   mesure (§D). **Critère net de bascule** : on MESURE quand l'inconnue restante est une
   **IDENTITÉ / VALEUR RUNTIME** (quelle entité concrète arrive ici ? quel contenu a ce dict ?
   quel état fait diverger deux cibles ?) derrière ≥ 2 indirections non résolues (interface +
   rgctx) dans une fonction aliasée. On ne mesure JAMAIS une **FORMULE / STRUCTURE** — ça, ça se
   LIT (§1) ; et on ne « finit » JAMAIS par un gate deviné (§E).

#### D. Le hook de MESURE (statique épuisé)

1. **Quoi capter** : les **ARGS + le RETOUR de la PRIMITIVE** (pas de la géante) — ex. #152 :
   l'entité propriétaire du StatComponent, le StatType, Current vs Initial, la liste de modifiers
   retournée par `CalculateModifiersFromStatModifications`.
2. **Sur un CONFRONT DISCRIMINANT** : le cas-qui-diffère VS le cas-qui-ne-diffère-pas (u82
   Terrifying vs u86), UN seul facteur variable (même attaquant, même tuile — cf. §1.1 crafter le
   setup). Le retour tranche le gate générique : la primitive fire-t-elle AUSSI pour u86 ? sur
   quel stat ? avec quels montants ? → l'identité runtime est lue, pas devinée.
3. **Sécurité (non négociable)** : JAMAIS de (re)inject/restart host pendant qu'un agent worktree
   tourne ; amorce `force:true` après CHAQUE reinject avant tout RPC/probe ; hook diagnostic
   **auto-armé** au register ; **résolution runtime par nom** (`findClassAnywhere`/`findMethod`),
   jamais de RVA hardcodée — si un point d'entrée n'est résolvable que par adresse (diagnostic),
   stocker la **VA ghidra complète** et calculer `va - 0x180000000` dans le code, et sanity-checker
   le batch contre un hook contrôle connu-qui-fire (cf. CLAUDE.md + mémoire
   `feedback_rva_transcription_from_va`).

#### E. ⛔ ANTI-PATTERN — le gate deviné après back-solve

> **Un back-solve numérique EXACT sur UN cas ne licencie PAS d'inventer le GATE.**
> « Signature numérique connue + gate non lu = HYPOTHÈSE, pas un port. » Options légitimes :
> (a) finir la lecture statique (échelle §C), (b) mesurer (§D), (c) déférer — `TaskCreate` +
> doc case-study — JAMAIS enshriner un gate deviné (string/effet hardcodé). Cf. §2.1 : tout gate
> doit se lire « le natif distingue ce cas ICI (classe/id/enum @VA), donc moi aussi ».
>
> Vécu #152 : le gate candidat « `if target has effect "Terrifying_ExtraDefense" → base=Initial` »
> a failli être hardcodé alors que le back-solve était exact. La lecture (C.2+C.3) a montré un
> mécanisme 100% générique — « la CIBLE a-t-elle un stat-mod de **Defense** actif
> (`Current != Initial`) ? » — où Terrifying n'est qu'UNE source possible parmi toutes. Le gate
> hardcodé aurait été faux sur toute autre source de mod de Defense, et invérifiable contre le
> natif. Un back-solve sur UN cas ne distingue pas deux mécanismes qui produisent le même chiffre
> sur CE cas (sous-détermination — même leçon que §3 pour les scalaires).

---

## 2. PORTAGE — mirror la STRUCTURE native, ne jamais inventer

Le port Python d'un mécanisme natif doit **coller le plus possible à la structure du code du jeu** :

- **1:1 classe native → module, méthode native → fonction homonyme**, avec la **VA citée** en
  commentaire (ex. `# IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`).
- **Validable méthode par méthode** contre le natif — pas de black-box ni de cache d'outputs.
- **Pourquoi** : c'est ce qui rend le moteur fidèle ET modifiable. Une structure qui diverge du natif
  devient impossible à valider finement et à faire évoluer.

### 2.0 RÈGLE IMPÉRATIVE — PARTIR de la fonction native NOMMÉE, NE JAMAIS inventer

**Avant d'écrire UNE ligne de port, ouvrir le décompilé et partir de la fonction/classe NATIVE
NOMMÉE.** L'ordre est non négociable : (1) `search_symbols_by_name` sur le mécanisme → (2) lire la
fonction native → (3) nommer la fonction/classe Python **d'après son homonyme natif + `# NomNatif
@VA` en commentaire** → (4) mirroir de la **chaîne d'appels** native. **INTERDIT d'inventer un nom
ou une structure quand une contrepartie native existe.**

- Si un helper offline préexistant a un **nom inventé** (ex. `predict_normal`/`predict_special`), NE
  PAS prolonger ce pli : le réaligner sur son homonyme natif quand on le touche (`MakeDamagePredictions`
  → `GenerateMultiHitAttackPredictions` → `CalculateDamagePredictionScenario` ; utilité
  `CalculateUtilityFromPredictions` = `Σ CalculateUtilityFromDamageEvent`).
- **Ne pas découper une fonction native en plusieurs fonctions Python** au nommage arbitraire (ex.
  inventer `predict_special_aoe` alors que le natif est UN seul `<Ability>Playbook.MakeDamagePredictions`
  qui produit la liste main + AoE). Une fonction native = une fonction Python homonyme.
- **Ne pas créer un NOUVEAU module `engine/` « pour du code partagé »** : RE d'abord l'organisation
  native (à quelle classe le mécanisme appartient) → le placer dans le port de CETTE classe (ex.
  `positional_mods`→`damage_modifiers`, `attack_hits`→`AttackHitsWithModifiersFormula` ;
  `DamageCalculations` est splitté par-concern, chaque header dit sa tranche). Une duplication/fork
  de service côté port = une divergence STRUCTURELLE du natif (le natif a 1 service, le port en a
  fait N) — à réconcilier, pas à contourner. (Mémoires `feedback_no_invented_modules_no_defensive_getattr`,
  `feedback_check_own_port_before_re`.)
- **Une mécanique/primitive rencontrée une 2ᵉ FOIS = SIGNAL de factoriser, PAS de la re-porter ad-hoc.**
  Le jeu factorise presque toujours via UN primitive nommé (souvent un sélecteur `DSLFactory`) — que le
  port a **souvent DÉJÀ** (`engine/dsl/selectors.py`, `nodes.py`) mais que les abilities court-circuitent
  avec un check inline. Au 2ᵉ site, S'ARRÊTER et router les deux par le primitive partagé + UNE table
  d'enum. Vécu (feedback user) : `UnitsWithoutTrait(0x1b=Steppable)` (natif `IdunBattleLogic.Entities.DSLFactory$$UnitsWithoutTrait`) porté 2× à la main (`ArcaneShield` triggers.py + `GetEmRuntz` spawn.py) via `"Steppable" in
  ctx.traits`, avec le mapping `UnitTrait` id→nom épars (`TRAIT_STEPPABLE`, `# 0x_ non mappé`, `0xd inconnu`,
  `0x1a=Imperial`) — au lieu d'UNE table `UnitTrait` (enum dump.cs) + un helper `has_trait`/`units_without_trait`.
  ⚠ piège : `UnitTrait` et `EffectType` sont deux enums DISTINCTS de même valeur (27 = Steppable vs Taunted)
  → nommer lève l'ambiguïté que l'int cache. (Mémoire `feedback_check_own_port_before_re`.)
- **DSL du jeu = arbre d'expression LAZY** (`DSLFactory`/`TargetsSelector` : `Sum`/`Min`/`If`/
  `SurroundingUnits`/… sont des NŒUDS, car leurs opérandes sont des sous-formules runtime type
  `TotalTimesAttacked`). On le mirroir par un **moteur de nœuds** (`engine/dsl/nodes.py`,
  `Node.evaluate(ctx)`), chaque ability = l'arbre EXACT du décompilé, vérifiable nœud-par-nœud.
  Nuance port **eager** : on résout les feuilles puis on combine → l'arithmétique triviale (`Sum`=`+`)
  NE doit PAS être un wrapper inutile ; le socle générique ne garde que le NON-trivial
  (géométrie/ciblage/état runtime). ⚠ **Ghidra MISLABEL les ctors de nœuds gshared** (le ctor de
  `IdunBattleLogic.Entities.DSLFactory$$Sum` s'affiche `HasUsedActiveAbilityThisTurnTrigger$$.ctor`) → sémantique
  lue via la STRUCTURE (pointeur de classe, args, arithmétique), JAMAIS via les noms.
- **Pas de `getattr(state, "x", default)` défensif** pour des attributs garantis (`__slots__` +
  `__init__`) — l'accès direct est correct et échoue plus fort en cas de bug.
- **Pourquoi (faute corrigée 3× en une session par l'utilisateur — « pourquoi tu inventes alors que
  la doctrine est claire ? »)** : inventer des noms/structures rend le port invérifiable contre le
  décompilé, non-évolutif, et fait perdre du temps en corrections. Le nom natif + la VA sont la
  preuve de fidélité. (Mémoire `feedback_mirror_named_game_functions`.)

### 2.1 RÈGLE — tout GATE par nom/id/effet doit être JUSTIFIÉ contre le natif

**Tout branchement conditionné par un nom (ability/effet/playbook/unité) ou un id — `if ability_name
== "X"`, `if id == N`, `X in {_SET}`, `"X" in name` — doit correspondre à une DISTINCTION RÉELLE du
natif (une classe / un id / un enum bespoke côté jeu), commentée avec sa preuve (VA / classe / enum).
JAMAIS un raccourci qui court-circuite un mécanisme GÉNÉRIQUE natif qu'on aurait loupé.**

- **Miroir du dispatch natif** : per-ability → 1 classe native ⇒ registre par **id** ; per-effet → 1
  classe native ⇒ **factory par nom** ; condition de trait/profil/faction ⇒ gate
  `HasTrait`/`DamageProfileIs`/`IsSameFaction` (par enum/trait, PAS par nom d'unité). Si le natif a
  UNE fonction générique (ex. `RepairPlaybook IdunBattle.AI.Playbook.Common.RepairPlaybook$$.ctor`, `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`), le port passe par CE générique — il ne hardcode pas les cas un par un.
- **INTERDIT le substring de nom** (`"Repair" in name`, `"Heal" in name`) comme DISCRIMINANT : il
  false-matche (ex. `NanoscarabRepairProtocols` capté par `"Repair"`, mauvais routage) — utiliser
  l'**id / enum exact**. (Le substring reste OK pour une NORMALISATION de clé documentée, ex.
  `Heal_<Passive>` → clé config gameconfig, ce n'est PAS un gate.)
- **Gate hardcodé INÉVITABLE** (distinction native NON dérivable offline — ex. héritage de
  `PredictAttack` via la vtable +0x27, cf. `_PREDICT_VIA_NORMAL_ATTACK={SpiritLeech}` #90) : (a)
  commenter la **raison + le mécanisme natif + VA** ; (b) le marquer **possiblement INCOMPLET** ; (c)
  créer une **tâche** pour énumérer l'ensemble complet par RE (ex. #92/#99). Ne jamais laisser un tel
  hardcode silencieux se faire passer pour générique/complet.
- **Pourquoi** : un gate par nom non justifié = l'anti-pattern « inventer au lieu de mirrorer »
  appliqué au CONTRÔLE DE FLUX — il fork le port loin de la structure native, casse la généralisation
  (un cas non listé est traité à tort), et devient invérifiable contre le décompilé. Chaque gate doit
  se lire comme « le natif distingue ce cas ICI (classe/id/enum @VA), donc moi aussi ».

### 2A. Côté DÉCISION (prédiction / playbook / scoring IA)

L'IA native = un **bucket utility-maximizer** : `PickNextUnit` → par-ability `<Ability>Playbook` →
`argmax` d'utilité parmi les actions LÉGALES. Le dégât PRÉDIT par-ability alimente le scoring
(`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` → `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` = `Σ
CalculateUtilityFromDamageEvent`). Registres du port : `engine/playbook` + `engine/services`.

**L'oracle du dégât per-ability = le playbook natif, PAS le preview.** Hiérarchie des mesures :

1. **`aiPlaybookPredict {runnerId, unitId, targetId, abilityType[, level, multiplier]}`** (RPC #102) =
   l'oracle DIRECT : invoque `<Ability>Playbook.MakeDamagePredictions` natif (ex. PlasmaCannonPlaybook
   `IdunBattle.AI.Playbook.Loki.PlasmaCannonPlaybook$$MakeDamagePredictions`, ALoki_NormalAttackPlaybook `IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions`) et rend la liste `ProbableDamageEvent`
   (target, healthDmg min/max, appliedHits, probability). C'est CE que l'IA score. Varier
   `{level, multiplier}` SÉPARE les hypothèses de niveau. Tuile COURANTE seulement (bouger l'unité
   pour une autre position).
2. **Tour de décision IA OBSERVÉ** (`modifierObserveInstall` → `Reset` → `aiPlayByUnit` →
   `modifierObserveStatus`) = la décomposition PAR ÉTAGE de ce dégât (cf. §3).
3. **⚠ `aiPredict` (= `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions`) N'EST PAS l'oracle
   playbook** : c'est le **PREVIEW decisionView**, Attack-based QUEL QUE SOIT l'abilityType (vérifié
   cache ET `fresh:true`). Une égalité `aiPredict(special)==aiPredict(normale)` ne prouve RIEN (faux
   verdict #96 : PlasmaCannon routé Attack-based à tort). Tuile invalide → fallback
   `GetPredictionForTargetsUnreachableFromSelectionTile` (valeur d'une AUTRE tuile). `aiPredict` reste
   l'oracle du **preview affiché** (`decisionView.attackPlans`/`exposureView` l'utilisent) et des
   requêtes par-tuile — jamais du dégât per-ability d'une spéciale. (Mémoire
   `aipredict_preview_not_playbook_oracle`.)

**Base per-ability = l'AbilityState PROPRE de l'ability, pas le canal global** (#100). Chaque entrée
`ActiveAbilityComponent` porte son couple `{Level, VariableMultiplierPercentage}` (`_abilityState
@0x4c`, `IdunBattle.Entities.Components.ActiveAbility$$get_AbilityState` : Override `@0x58` prime), capté par `combatSnapshot.abilityStates`.
C'est CE couple que `MakeDamagePredictions` reçoit (5ᵉ arg) et que `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` consomme (idx = `Level.ToZeroBasedIndex` clampé ; `Fix64.Round(v × mult/100)` par entrée
si var ∈ `variablesAffectedByRarityBonus`). Le canal global `unitConfig.activeAbilityLevel ×
abilityVariablesMultiplier` est un AUTRE couple (mesuré u80 PlasmaCannon : per-ability → 1396 vs
global → 1594, faux). Cas d'école : `docs/rl/playbook/prediction.md` « MAJ #100 + #102 ».

### 2B. Côté COMBAT (runner / opérations / ECS)

**Porter/valider le côté DÉCISION ne garantit EN RIEN que le mécanisme est reproduit côté EXÉCUTION.**
Deux chemins distincts, registres distincts (cf. l'intro). Confirmer l'un NE couvre PAS l'autre.

- **Le runner combat NO-OP SILENCIEUSEMENT toute ability non enregistrée** :
  `AbilityHandler.visit_ActiveAbilityMessage` fait `ported:False ; return` (0 dégât, 0 effet, AUCUNE
  erreur) pour tout `ActiveAbilityType` absent de `ABILITY_CLASSES` (~11 abilities enregistrées). La
  divergence d'état qui s'ensuit est INVISIBLE → attribuée à tort au bruit RNG ou à un autre
  mécanisme. **Faute déjà commise** : SpiritLeech (1104) lourdement travaillé côté DÉCISION
  (#84/#86/#90) mais JAMAIS exécuté en combat — no-op muet non détecté jusqu'à #93.
- **Archi runner** : pipeline `IdunBattle.Runner.IdunRunner$$Apply` (gate → pre → record → post) ; messages = visitor ;
  ~80 `Operations` = mutateurs ECS atomiques ; cascade LIFO inline + FIFO deferred. Map :
  `docs/rl/runner-engine.md`. Validation = **replay-diff vs live**.
- **Doctrine** :
  1. **Jamais conclure « X est porté/géré » sans préciser QUEL côté** (décision vs exécution) est
     couvert. Si un seul côté est fait, **TÂCHER l'autre** (port-gap → `TaskCreate`, cf. §4).
  2. **Rendre le no-op combat VISIBLE** (flag `AbilityHandler.unported` qui accumule les casts tombés
     sur no-op) et l'**ASSERTER** dans tout test d'exécution d'ability (`assert last["ported"] is
     True`) — un cast qui tombe sur no-op doit **ÉCHOUER LOUD**, pas passer en silence.
  3. Un replay-diff / self-play qui « colle » **sans forcer l'exécution** du mécanisme ne prouve RIEN
     sur l'exécution : la décision peut choisir X pendant que le runner l'ignore.
- **Pourquoi** : la fidélité « le moteur reproduit le jeu » a DEUX faces ; valider une seule en
  croyant couvrir les deux = un angle mort SILENCIEUX qui corrompt le dataset RL / le replay sans le
  moindre signal (pas d'erreur, pas de test rouge).

---

## 3. DIVERGENCE DE DÉGÂT off↔live = DÉCOMPOSITION PAR ÉTAGE, JAMAIS un fit de scalaire

**PREMIER RÉFLEXE, INCONDITIONNEL : dès qu'une valeur de dégât diverge offline↔live** (replay-diff,
prédiction↔oracle, `off ≠ live`, un ratio/écart « bizarre »), **le geste n°1 est l'OUTIL DE
DÉCOMPOSITION `scripts/python/tools/damage_decomp.py` — lire la valeur PAR ÉTAGE du pipeline des DEUX
côtés et localiser l'étage divergent. NE JAMAIS fitter un scalaire (×0.9 ? /2 ? mult 90 ?) sur le
dégât FINAL.**

- **Pourquoi** : un dégât final est **sous-déterminé** — `300 = 333×0.9 = 167×1.8 = 599/2` :
  impossible de distinguer multiplier / valeur / base / nb de coups depuis le seul endpoint. Le
  fit-de-scalaire mène à la mauvaise piste **de façon quasi garantie** (déjà : ~5 reinjects gaspillés
  sur #68 à « capter le mult 90 » alors que le mult=180 était confirmé live et que le vrai signal
  était l'additif RÉSOLU ; #49 élévation red-herring ; #96 « base = maxDmg seul » = mis-attribution,
  le 1396 se décompose des deux façons — vraie base = `avg(minDmg,maxDmg)` scalés, lu en varLevelDumps
  #100). **L'étage se LIT, il ne se devine pas.** Si tu es tenté d'écrire « le facteur est ~X donc le
  paramètre Y vaut Z » → **STOP, décompose d'abord.**
- **Pipeline natif (étages nommés)** : `base → GetBaseDamageWithFixedPiercedArmor (pierce/armure) →
  result_bout → CalculateBaseDamageWithAllModifiers (%-mult + ADDITIF via DamageModifiers.Add) →
  crit/block → Amount`. `modifier-observe` (DÉJÀ dans les hooks : RPC `modifierObserveInstall`/
  `modifierObserveStatus`/`modifierObserveReset`) capte la valeur LIVE par étage
  (base/pierceA/pierceB/penetration/result par bout + additif attaquant/défenseur + attribution
  par-source via `BaseEffect.DamageBonusForAttack`). `tools/damage_decomp` : `arm(rpc)` → rejouer
  l'attaque (seedée) → `read_live_decomp(rpc)` → `decomp_report(rr, live_ph, live_decomp)` imprime le
  tableau + l'ÉTAGE divergent. Démo/gabarit : `tests/engine/runner/test_damage_decomp_live.py`.
- **Le décompilé décide QUEL étage RE ; UNE lecture live confirme SA valeur runtime** (cf. §1). Le
  live NE sert JAMAIS à deviner une formule.
- **Un « facteur qui colle » sur UN cas = HYPOTHÈSE, pas un fait** : trouver un 2ᵉ cas qui SÉPARE les
  candidats avant de committer (ex. u90 PowerTrip ×180 sans /2 réfute un /2 universel en une ligne).
  Si une mesure DIRECTE contredit l'hypothèse (Level.mult=180 ≠ 90) → **RE-DÉRIVER**, pas patcher
  l'hypothèse.
- **Fenêtre de mesure PRÉDICTION fiable = le tour de décision IA OBSERVÉ** : `modifierObserveInstall`
  → `Reset` → `aiPlayByUnit` → `modifierObserveStatus`. Étages : `multDumps` (chaque multiplicateur
  composé ×1000 + topRva — LA décomposition du ×k), `predCalcDumps` (in→out per-bout,
  `DamagePrediction.CalculateBaseDamageWithAllModifiers`), `valueDumps` (bouts post-perçage, ring
  200), `varLevelDumps` (variables d'ability niveau×mult). Tuiles candidates SÉPARATRICES
  (not-moved+élévation vs moved+plate) pour isoler les gates. Complément direct : `aiPlaybookPredict`
  (§2A) donne l'oracle per-ability sans passer par l'interprétation de ratios.
- Détail : `docs/rl/case-68-orksnob-attacker-effects.md` + `docs/rl/playbook/prediction.md` « MAJ #96
  REVERTÉ + #98 RÉSOLU » / « MAJ #100 + #102 » + mémoire `feedback_damage_decomposition_measure_stage`.

---

## 4. VALIDER + TRACER

- **Tests CIBLÉS de la tranche touchée uniquement**, jamais toute la suite `tests/engine/` (chaque
  test live monte des batailles ; la suite entière ~10 min+ sature la session). Ex. slice DAMAGE →
  `test_damage_roll_live.py` + `test_runner_attack_live.py` + crit/block ; slice PRÉDICTION →
  `test_predict_live.py` + `test_playbook_live.py`. Inclure un test de garde par dépendance partagée
  impactée, pas plus. Suite complète : seulement sur demande explicite / avant un jalon.
- **Replay-diff vs live** = la validation d'EXÉCUTION (§2B). Un agreement qui « colle » sans forcer
  l'exécution ne prouve rien sur l'exécution.
- **Validator adversarial en worktree** (cf. `CLAUDE.md` § Agents) : commiter le checkpoint sur
  `master`, lancer le(s) validator(s) worktree (figés au commit de lancement), prendre leur VERDICT
  (jamais leur code), fix-forward. Ne jamais réinjecter Frida / restart host pendant qu'un agent
  worktree tourne.
- **Manques de portage = tâches (automatique)** : **tout manque de portage constaté ⇒ une tâche créée
  IMMÉDIATEMENT (`TaskCreate`)** — effet/trait/formule non porté, divergence runner↔live ou
  prédiction↔oracle, `off ≠ live` dans un replay-diff, un `# TODO`/no-op rencontré. Contenu : unité/
  effet + symptôme CHIFFRÉ (off vs live) + VA/fonction native si connue + pointeur doc case-study.
  S'applique aux découvertes FORTUITES (sans se laisser détourner de la tâche courante : créer ≠
  traiter). Le système de tâches est LE registre des gaps de fidélité (un gap laissé en remarque de
  conversation est perdu au `/compact`). **Persister durablement** : écrire le détail RE dans un doc
  repo (`docs/rl` case-study) au MOMENT de la trouvaille, PAS seulement dans la tâche/conversation
  (les deux sont lossy au `/compact`). Tâche = tracker actionnable ; doc = détail RE ; les deux, pas
  l'un OU l'autre. (Mémoires `feedback_port_gap_auto_task`, `feedback_persist_findings_durably`.)

---

## Inventaire des outils

| Phase | Outil | Rôle |
|---|---|---|
| 0 Recon | `gameconfig.py <unit> [--ability/--trait]` | kit complet (traits/actives/**passives**), tableaux par-niveau, flags rarity, texte i2 |
| 0 Recon | `unit_map.py` | trouver quelle unité porte un mécanisme donné |
| 1 RE | `mcp__ghidra__search_symbols_by_name` | trouver la/les fonction(s) NOMMÉE(S) (réflexe de départ, avant tout hook) |
| 1 RE | `mcp__ghidra__decompile_function` / `list_xrefs` | LIRE le décompilé = vérité ; suivre la chaîne d'appels |
| 1 RE | hook + `Thread.backtrace` | CIBLAGE seul : « quelle fonction RE ? » — jamais la formule/valeur |
| 2A Décision | `aiPlaybookPredict` (RPC) | oracle DIRECT du dégât per-ability du playbook (`MakeDamagePredictions`) |
| 2A Décision | `combatSnapshot.abilityStates` | capteur AbilityState per-ability {level, multiplier} (#100) |
| 2A Décision | `aiPredict` (RPC) | ⚠ PREVIEW Attack-based (piège) — oracle de l'affichage/par-tuile, PAS du per-ability |
| 3 Décompo | `tools/damage_decomp.py` + `modifierObserve*` | dégât PAR ÉTAGE des 2 côtés → localiser l'étage divergent |
| 3 Décompo | modifier-observe : `multDumps`/`predCalcDumps`/`valueDumps`/`varLevelDumps` | décomposition prédiction pendant le tour de décision observé (`aiPlayByUnit`) |
| 2B/4 Combat | `AbilityHandler.unported` + `assert ported` | rendre le no-op combat VISIBLE et LOUD |
| 4 Valider | pytest CIBLÉ (`test_predict_live`/`test_playbook_live`/`test_*_live`) | agreement live, slice touchée seulement |
| 4 Valider | replay-diff, `engine_validate.py` | validation d'EXÉCUTION vs live |
| — | `rl_duel build` | monter le runner isolé (voir `references/runner.md` : amorce, board, discipline) |

Catalogue RPC complet : `references/rpc-api.md`. Lancement runner : `references/runner.md`.

## Anti-patterns (déjà commis — checklist)

- ❌ Empiler des hooks pour re-découvrir en tâtonnant une formule LISIBLE dans le décompilé → STOP,
  `search_symbols_by_name` + lire.
- ❌ Abandonner une RE parce que le décompilé est « trop gros » (refus inline de l'outil) → parser
  le fichier tool-results sauvé, grep les call-sites + fenêtres (§1.2 A/B).
- ❌ Hardcoder un gate parce qu'un back-solve numérique colle sur UN cas → « signature numérique
  connue + gate non lu = HYPOTHÈSE » : lire (§1.2 C), mesurer (§1.2 D) ou déférer — jamais deviner.
- ❌ Fitter un scalaire (×0.9, /2, mult 90) sur le dégât FINAL → décomposer par étage (`damage_decomp`).
- ❌ Inventer un nom / une structure / un NOUVEAU module Python quand un natif existe → partir de la
  fonction native NOMMÉE + citer la VA.
- ❌ Gate par substring de nom (`"Repair" in name`) → id / enum exact, justifié contre le natif.
- ❌ Conclure « X est porté » sans dire décision vs exécution → préciser, et tâcher l'autre côté.
- ❌ `aiPredict(special)==aiPredict(normale)` comme preuve → c'est le preview Attack-based, pas
  l'oracle playbook (`aiPlaybookPredict`).
- ❌ Sauter la recon et RE le mauvais mécanisme (passif confondu avec l'active).
- ❌ Bataille générique pour confirmer un mécanisme → crafter les teams + driver les positions.
- ❌ Laisser un gap en remarque de conversation → `TaskCreate` immédiat + doc case-study.

## Pointeurs

- **Cas d'école prédiction** : `docs/rl/playbook/prediction.md` (MAJ #96 REVERTÉ + #98 RÉSOLU ; MAJ
  #100 + #102) · `docs/rl/case-68-orksnob-attacker-effects.md`.
- **Archi moteurs** : `docs/rl/runner-engine.md` (runner/combat) · `docs/rl/playbook-engine.md`
  (décision) · `docs/rl/dsl-cartography-phase1.md` + les TSV `docs/rl/dsl-usage/` (le graphe
  primitive ↔ ability, RE-DÉRIVABLE par `python scripts/python/dsl_xref_map.py report`).
- **Infra (reste dans `CLAUDE.md`)** : hash-discipline dump↔build, résolution runtime (pas de RVA
  hardcodée), démarrage ghidra-mcp, amorce après chaque (re)inject, « Ne jamais » (heap
  scans, broad-hooks…), ASCII-only en sortie console, agents worktree.
- **API/harnais** : `references/rpc-api.md`, `references/runner.md`, `references/hooks.md`.
- **Mémoires liées** : `feedback_recon_units_first`, `feedback_recon_full_kit_not_captured_effects`,
  `feedback_re_ghidra_not_experiment`, `feedback_mirror_named_game_functions`,
  `feedback_no_invented_modules_no_defensive_getattr`, `feedback_damage_decomposition_measure_stage`,
  `aipredict_preview_not_playbook_oracle`, `feedback_port_gap_auto_task`,
  `feedback_persist_findings_durably`, `feedback_adapt_teams_to_validation_objective`,
  `feedback_drive_positions_dont_blame_geometry`.
