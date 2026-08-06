# #287-r11-r1-r1 — le slot n'était pas « non résolu », il était MAL LU (décalage de UN)

Quatre sites du port déclaraient un slot d'`IBattleQuery` « non résolu », et deux d'entre eux
laissaient `CasterHas2TurnsLeft` (bit 52) NON PORTÉE. Le résidu supposait que la table de
métadonnée trancherait. Elle tranche — mais **pas sur le slot que le port citait**.

## 1. Le fait, et ce qui l'établit

| site | le port écrivait | le décompilé écrit | la table publie |
|---|---|---|---|
| `targeting.py` (bit 52) | `IBattleQuery 0x1a`, « non résolu » | `<slot 0x1b>(this.<+0x18>, caster, 2)` | `27 HasMinimumRemainingTurns 2` |
| `astramilitarum.py` (1142) | idem, redit | idem | idem |
| `targeting.py` (préfixe `CasterHasNotMoved`) | `IBattleQuery 0x34`, « non résolu » | `<slot 0x35>(this.<+0x18>, caster)` | `53 IsTurnOfUnit 1` |
| `triggers/loki/hateful_assault.py` | `DSLSelectors+0x78`, nom non résolu | `AreEqual(+0x78, +0x30)` | — (slot partagé, pas d'interface) |

**Les deux premiers sites portaient un décalage de UN.** Ce n'est pas la table qui se trompait,
c'est le port — et le brief de la tranche pointait exactement le bon endroit en refusant de croire
la table sur parole : la contradiction annoncée (« la table publie 1 paramètre, le port en lit 2 »)
se dissout dès qu'on lit le bon slot, `0x1b`, dont l'arité est **2**.

**Trois sources indépendantes** le disent, et aucune n'est la table :

* le **call-site**, `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, appelle le
  helper d'invocation d'interface avec **cinq** arguments — `(0x1b, <klass IBattleQuery>, this.<+0x18>, caster, 2)` ;
* la lambda du décorateur `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass68_0$$u003CHasMinimumRemainingTurnsu003Eb__0`
  relaie le **même couple (slot, klass)** et son NOM donne la méthode ;
* symétriquement, `...u003Cu003Ec__DisplayClass66_0$$u003CShouldPlayerSkipTurnu003Eb__0` relaie
  `0x1a` et `...u003Cu003Ec__DisplayClass86_0$$u003CIsTurnOfUnitu003Eb__0` relaie `0x35`.

⚠ **La voie « proxy » que le résidu accusait FONCTIONNAIT.** Elle rend un nom pour `0x1a`, pour
`0x1b` ET pour `0x35`. Ce qui a échoué n'est pas l'outil de résolution : c'est qu'on lui a donné un
mauvais numéro, puis qu'on a lu son silence sur ce mauvais numéro comme « non résoluble ».

⚠ **Le discriminant qui aurait suffi était l'ARITÉ, et le port l'avait sous les yeux.** Le call-site
passe deux arguments ; `ShouldPlayerSkipTurn` en publie un. Cette incohérence était visible sans
aucun outil — et `targeting_rule_inventory.py`, dans le MÊME dépôt, écrivait déjà `slot 0x1b`.
La faute n'est donc pas un manque d'information mais une **concordance interne non confrontée**.

## 2. `HasMinimumRemainingTurns`, verbatim

    limit = <GetMaxRounds() INLINE>                       // victoryConfig.<+0x18>.TryGetValue(1)
    if (!limit.HasValue)                return true;
    matchTurn = StateExtensions.GetMatchTurn(state);
    first     = StateExtensions.GetPlayer(state, GetPlayerTurnOrder()[0]);
    return turns <= limit.Value - matchTurn.GetAmountOfTurnsEndedByPlayer(first.Id);

Trois lectures qui ne se devinent pas :

* **le paramètre `unit` n'est PAS lu.** Le corps ne le référence nulle part, et le joueur dont on
  compte les tours est `GetPlayerTurnOrder()[0]`, pas le propriétaire du caster. Le gate est GLOBAL
  au match. Un port qui aurait filtré par joueur serait faux dès trois camps ;
* **le retour est un `Nullable<int>`, pas un entier.** Rabattre l'absence sur `0` inverse le
  verdict (`2 <= 0 - ended` est FAUX) et ferait refuser TOUS les casts des trois porteurs ;
* `this+0xb0` est le paramètre **`victoryConfig`** de `IdunBattle.Core.Services.BattleQuery$$Initialize`
  (14ᵉ, NOMMÉ dans la métadonnée) et son dictionnaire `+0x18` est **`BC.Victory.VictoryConditions`** —
  lu par `IdunBattle.Core.Services.BattleQuery$$GetMaxRounds` à la clé `1`, que `enums.tsv` nomme
  `idun.Shared.Battle.VictoryConditionType.MainPlayerRoundLimitation`.

⇒ **le plafond de rounds a un substrat côté port**, ce que trois sites affirmaient l'inverse
(`tau.py`, `loki_custom.py`, `ability_caster_gates.py`). Le mirror est
`engine.services.victory_config`, avec le défaut DÉRIVÉ de `data/seed-bc.json` — même patron que
`engine.services.damage_config`, et pour la même raison : la valeur ne s'écrit pas, elle se lit.

## 3. Ce que le port LÈVE, et pourquoi ce n'est pas un renoncement

Le second bras a besoin de `TurnComponent.<Dictionary @+0x40>`
(`IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEndedByPlayer`), que le port n'a
pas. Deux candidats existent et **aucun n'est celui-là** :

* `State.turn_counts` mirroir `TurnComponent+0x38`, les tours **DÉMARRÉS** ;
* `decisionView.turnsEnded` publie `GetAmountOfTurnsEnded(matchTurn, 0)` = `Sum(dict.Values)`, la
  **SOMME sur tous les joueurs**, pas la ventilation.

`has_minimum_remaining_turns` **LÈVE** donc au second bras, en nommant le champ manquant. Un `True`
silencieux y serait un port permissif muet — le vice exact que `get_surrounding_tiles` refuse pour
`only_empty_or_steppable`. RÉSIDU `#287-r11-r1-r1-r1`.

⚠ **Le premier bras, lui, est une MESURE, pas une convention.** `limit` vide ⇒ `true`, et le natif
ne lit rien d'autre. C'est le régime de TOUS les runners `rl_duel build` : la seed versionnée ne
porte pas `MainPlayerRoundLimitation`. Le port y répond donc pour la même raison que le jeu.

## 4. Confrontation LIVE — quatre bras, et le quatrième n'est pas décoratif

`probe_287r11r1r1_caster_has_2_turns_left.py`. Porteur `astraOrdnanceBattery` (**MACHINE OF WAR**,
pool MoW du seed), ability `1142`, board `C1_02`, `MachineOfWarAmmo = 9`.

| bras | `MainPlayerRoundLimitation` | natif `casterReason` | port (encadré) | levée |
|---|---|---|---|---|
| `temoin` | ABSENT | `0x0` | `0x0` | non |
| `plafond1` | `1` | **`0x10000000000000` `CasterHas2TurnsLeft`** | `0x10000000000000` | oui |
| `plafond20` | `20` | `0x0` | `0x0` | oui |

**Ventilation par verdict natif : `{0x0: 2, 0x10000000000000: 1}`** — non dégénérée.

⚠ **LE PORT EST CONFRONTÉ PAR ENCADREMENT, JAMAIS PAR AJUSTEMENT.** `ended` n'est pas mesurable
côté port ; le verdict est donc évalué pour TOUTE valeur de `ended` dans `[0, n_endturns+1]`, et
l'accord n'est retenu que s'il est **CONSTANT** sur l'intervalle. Les deux plafonds sont choisis
pour cela : `2 <= 1 - ended` est faux pour tout `ended >= 0`, `2 <= 20 - ended` vrai pour tout
`ended <= 18`. Fitter un `ended` sur la réponse native aurait été l'anti-pattern « ajuster un
scalaire ».

⚠ **ET C'EST PRÉCISÉMENT CE QUI REND LES TROIS PREMIERS BRAS INSUFFISANTS.** Un modèle
`turns <= limit` — sans le terme `- ended` — donne EXACTEMENT les trois mêmes verdicts. Le 4ᵉ bras
existe pour le séparer : `limit = 3`, un `casterReason` après CHAQUE `endturn`.

| pas | 0 | 1 | 2 | 3 | 4 … 8 |
|---|---|---|---|---|---|
| `casterReason` | `0x1` (ÉCARTÉ) | `0x0` | `0x0` | **`0x10000000000000`** | `0x10000000000000` |

Bascule au pas 3, **monotone**. Sans `- ended`, `2 <= 3` resterait vrai à tous les pas. Le rang
donne au passage une mesure indirecte du compteur natif : au premier refus,
`GetAmountOfTurnsEndedByPlayer(turnOrder[0]) = limit - turns + 1 = 2` pour 3 `endturn` émis —
cohérent avec l'alternance stricte mesurée par `#462-r4e-o-r2-r1-r1-r1`.

⚠ **Le pas 0 est ÉCARTÉ pour une raison NOMMÉE, pas pour faire passer le critère** :
`IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason` rend `broken(ValidRequest)` AVANT la
cascade tant que `ActiveAbility.CanCurrentlyBeUsed` est faux (`initialCooldownTurns` de 1142 = 1).
La règle n'y a pas été évaluée — ce pas ne dit rien d'elle. Le probe les COMPTE et les affiche, et
**refuse de conclure** si TOUS les bras sont court-circuités.

⚠ **Le montage a un piège de MUNITIONS.** 1142 porte `munitionsCost = 1` et le seed BC capture
`MachineOfWarAmmo = 0` : sans le patch, `casterReason` reste `0x1` pour toujours et l'accord
apparent serait un court-circuit déguisé. Même levier que `probe_253`.

## 5. `DSLSelectors+0x78` — l'ordre des arguments ne tranche PAS

Le 4ᵉ site. `#287-r11-r1` concluait `+0x78 = TargetTile` depuis
`get_OwnerIsTargetTile = AreEqual(DSLSelectors+0x78, AbilityEntities+0x30)`. **La conclusion est
juste, l'argument ne l'était pas** : le second opérande est `DSLSelectors+0x30` (pas
`AbilityEntities`), et surtout l'ORDRE ne prouve rien — `AreEqual` est SYMÉTRIQUE, donc rien
n'oblige le compilateur à préserver l'ordre du nom.

Ce qui tranche est un **système d'équations** entre les sept getters nommés de `DSLTriggers` dont le
corps entier est un `AreEqual` :

    get_OwnerIsActor      = AreEqual(+0x30, +0x40)   get_CasterIsCasterTile = AreEqual(+0x48, +0x50)
    get_OwnerIsCaster     = AreEqual(+0x30, +0x48)   get_CasterIsTarget     = AreEqual(+0x48, +0x60)
    get_OwnerIsCasterTile = AreEqual(+0x30, +0x50)   get_OwnerTileIsTarget  = AreEqual(MainTileOfUnits(+0x30), +0x60)
    get_OwnerIsTargetTile = AreEqual(+0x78, +0x30)

Les six premières se recoupent et fixent `+0x30 = Owner`, `+0x40 = Actor`, `+0x48 = Caster`,
`+0x50 = CasterTile`, `+0x60 = Target` — `get_OwnerTileIsTarget` étant le témoin décisif, puisqu'il
prend `MainTileOfUnits(+0x30)`, donc `+0x30` est une ENTITÉ. La septième met alors en présence
`{Owner, TargetTile}` avec `+0x30` déjà pris : il reste `+0x78 = TargetTile`. **L'ordre y est
INVERSÉ par rapport au nom**, ce que six équations sur sept contredisent — lire l'ordre aurait donné
l'exact contraire.

## 6. La garde

`tests/engine/test_287r11r1r1_caster_has_2_turns_left_offline.py`, **18 tests / quatre étages** :
le SLOT et son ARITÉ lus dans la table ; `GetMaxRounds` (`Nullable`, clé nommée, défaut dérivé,
tri-état du `State`) ; les deux bras dont la LEVÉE ; le câblage des deux faces et sa BORNE (une
ability sans le bit ne lève jamais) ; et le mutant `turns <= limit`, qui **assertionne son propre
non-vide**.

Vue rouge sur l'arbre témoin (`git archive` d'`origin/master`, arbre COMPLET) : **14 failed /
4 passed** ; **18 passed** après.

⚠ **Les 4 verts du témoin sont exactement l'étage qui aurait empêché la faute — et il n'existait
pas.** Trois d'entre eux lisent `interface_slots.tsv`, donc ils étaient verts AVANT la tranche : la
table disait la vérité depuis toujours, personne ne la confrontait au port. Le quatrième est un
acquis antérieur (les trois masques portaient déjà le bit). Ce n'est pas une faiblesse de la garde,
c'est le diagnostic : la donnée était là, le CRAN de lecture manquait.

⚠ **Les trois imports NEUFS sont faits DANS leurs tests**, et c'est la seule raison : en tête, ils
font échouer la **COLLECTE** sur le témoin, donc un rouge d'UNE ligne au lieu d'une ventilation par
bras. Mesuré — le premier jet a rendu exactement ce rouge d'une ligne.

## 7. Chiffres, re-dérivés des deux côtés

| | avant | après |
|---|---|---|
| règles GATE **PORTÉES** (`probe_429`) | 26 | **27** |
| règles GATE non portées | 20 | **19** |
| `CasterHas2TurnsLeft` | non portée, 3 abilities armées | **PORTÉE** |
| mirrors sous garde `probe_313` | 33 | **34** |

Cliquets re-joués APRÈS rebase : `probe_313` 34 mirrors en bijection, 0 dette ; `probe_181`
104/104, 0 manquante ; `probe_120` étape 0 « littéral de ctor manquant : aucun » ; `probe_273
--only-scan` OK ; `probe_287r5` OK (4 dettes, inchangé — cette tranche porte le volet CASTER, pas
le volet CIBLE qu'il recense) ; `probe_365` OK ; `probe_477r35` 0 module non importable seul ;
`probe_485` VERT. Cette tranche n'ajoute **aucune** entrée à `ABILITY_CLASSES` (1142/1160/1188 y
étaient déjà avec leur masque et leur `AbilityAttackType`).

## 8. Ce qui n'est PAS couvert

* **Le second bras n'est pas porté** — `TurnComponent+0x40`. Résidu `#287-r11-r1-r1-r1` ; point
  d'ancrage à publier : ce dictionnaire, VENTILÉ PAR JOUEUR (la somme ne suffit pas).
* **Le préfixe `IsTurnOfUnit` de `CasterHasNotMoved` n'est PAS porté côté RUNNER**, alors qu'il
  l'est côté DÉCISION. L'écart est **RESTRICTIF** — le port refuse là où le natif accepte — et il
  est INERTE sur le chemin `ExecuteInternal` (le caster y est le joueur courant), mais pas chez les
  deux autres appelants (`turnflow`, `handler`). Résidu `#287-r11-r1-r1-r2`. Il n'était nommé nulle
  part : la note disait « ne peut que DÉSARMER », ce qui décrit un écart sans le déclarer.
* **Les deux autres porteurs du bit** (1160 `tauBroadside`, 1188 `adeptExorcist`) ne sont pas
  confrontés live : le bit est GLOBAL au match, donc leur régime est identique à celui de 1142 —
  mais c'est un raisonnement, pas une mesure.
* **Aucun régime à plafond de rounds n'existe hors de ce probe** : `data/seed-bc.json` ne porte pas
  `MainPlayerRoundLimitation`, et le montage l'INJECTE. Un runner d'arène ordinaire n'exerce donc
  que le premier bras.
* **Trois rouges PRÉ-EXISTANTS** rencontrés et **reproduits à l'identique sur `origin/master`** :
  `test_447_r1_r1_zone_inclusion_decision_live.py` (3 tests). Hors de cette tranche.
* **Deux cliquets rouges sur `origin/master`**, non causés par cette tranche :
  `probe_468_collision_numeros.py` (cohabitation `#419-r6-r2`, PR #745 — reproduit à l'identique sur
  le témoin) et `probe_477r25_slots_autres_interfaces.py` (3 citations, dont les **trois lignes
  sont VERBATIM identiques à `origin/master`** et n'apparaissent pas dans le diff de la tranche —
  `astramilitarum.py` « slot 171 », `genestealer.py` « slot 103 », `targeting.py` « vslot 24 »).
  Les citations de slot AJOUTÉES ici (`0x1a`, `0x1b`, `0x35`) passent : `probe_477r24r1` est VERT,
  0 nom faux et 0 contradiction d'arité.
* Le rouge de `test_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason_offline.py` (21 tests) était celui
  de la BASE du worktree, réparé par `#484` sur `master` — **le rebase l'a dissous**, et c'est la
  démonstration de pourquoi il est obligatoire : sans lui, la tranche aurait rendu 21 rouges qui ne
  lui appartenaient pas.

## 9. Résidus

* **`#287-r11-r1-r1-r1`** — `TurnComponent.<Dictionary @+0x40>` ventilé par joueur, le second bras
  de `HasMinimumRemainingTurns`. Aujourd'hui : LEVÉE explicite.
* **`#287-r11-r1-r1-r2`** — le préfixe `BattleQuery$$IsTurnOfUnit` (slot `0x35`) de la clause 1 de
  `TargetingQuery$$GetInvalidCasterReason`, côté RUNNER. Écart RESTRICTIF nommé.
