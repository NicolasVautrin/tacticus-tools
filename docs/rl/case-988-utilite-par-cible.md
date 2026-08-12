# #988 — L'utilité d'IA à sa SOURCE, et le bucket qui se déclarait vide

## 1. Ce qui manquait, et où il manquait vraiment

L'oracle des faces DÉCISION voit **l'action retenue**, jamais **le classement qui l'a produite**.
Un port peut donc rendre la bonne décision pour de mauvaises utilités sans que rien ne le dise.

La tranche visait `<X>Playbook$$GetTargetUtility`. **La table dit autre chose.** Comptes re-dérivés
de `data/symbols/<build>/frida/methods.tsv` (corps PROPRES, donc adressables) :

| méthode | corps propres | retour | porte une cible ? |
|---|---|---|---|
| `EvaluateNonComparable` | **133** | `Bucket<UnitAction>` | non (rend le bucket) |
| `CalculateCustomUtility` | **26** | `Fix64` | **oui** (`target:IdunBattle.Core.IEntity`) |
| `GetTargetUtility` | **2** | `Fix64` | oui |
| `CalculateCasterPositionUtility` | **2** | `Fix64` | non |

L'exemple le plus cité est le plus pauvre. Le gisement d'utilité **par cible** est
`CalculateCustomUtility` — **26** corps contre 2. Suivre le nom donné en exemple plutôt que la
table aurait couvert 2 abilities au lieu de 26.

⚠ `CalculateActionUtility` (l'utilité totale par candidat, face Comparable) a **0** corps propre :
elle n'existe que gshared, et elle est déjà ancrée ailleurs via le parent inflaté.

## 2. Le chemin chaud : la contrainte porte sur la BASE, pas sur les overrides

Un hook permanent sur un getter chaud a déjà produit 27 000 appels/s et tué le process. Mais ce
régime concerne la **base générique**. Les overrides concrets ont chacun **leur propre RVA**, dans
les deux tables — ce ne sont pas des corps gshared.

**Mesuré** (étage 1 de `probe_988_ancres_utilite_playbook.py`) : `interfaceSlotProbe` calibre la
vtable de 9 playbooks concrets et confronte l'adresse d'entrée lue au dump Ghidra —
**9 adressables, 0 divergence**. Le risque n°1 de la tranche (le hook qui se déclare `enabled` et
fire zéro fois) est **levé, sans fenêtre de reinject**.

`GetTargetUtility` sort en `NON VIRTUELLE (hors vtable)` : elle n'apparaît dans aucune vtable, ce
qui **ne prouve rien** sur son atteignabilité — le hook s'y attache par `findMethod`, pas par un
slot. Le probe le dit au lieu de compter un échec.

**L'émission conditionnelle s'exprime par l'ADRESSE, jamais par un `if`** : un test dans `onEnter`
n'évite rien, la traversée native → JS a déjà eu lieu. L'armement prend donc une liste de
playbooks et n'ancre que les leurs.

## 3. Le bucket qui se déclarait vide — lu au décompilé, puis réfuté en live

Tous les lecteurs de bucket du dépôt lisaient le seul champ `best`. Or :

```
// IdunBattle.AI.BucketSystem.Bucket<T>$$AddActionToBucket(this, key, action, mi)
sub = null;
this-><subBuckets>.TryGetValue(key, out sub);          // SortedList<int, Bucket<T>>
if (sub == null) { sub = new Bucket<T>(); this-><subBuckets>.Add(key, sub); }
sub.AddAction(action);              // ECRIT `sub.best`, JAMAIS `this.best`
```

`IdunBattle.AI.Playbook.NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies` n'appelle
**que** `AddActionToBucket`. Le `best` de la racine reste donc nul **par construction**, et un
lecteur qui s'y arrête rend « vide » sur un bucket plein.

**Ce n'est pas propre à un montage** : `IdunBattle.AI.Playbook.Loki.ThunderousAssaultPlaybook$$EvaluateNonComparable`
construit deux stratégies et appelle directement `GenerateBucketWithMultipleStrategies`. Pour ce
playbook, « empty » était la réponse **quelle que soit** la situation de jeu.

`Bucket<T>$$ChooseAction` / `$$ChooseActionFromBuckets` / `$$IsValidAction` ne lisent que des
champs — aucun service, aucun état de match. Le mirror est donc **exact et en lecture pure** :
aucune invocation, donc aucun risque de gel ni d'écriture.

**Réfutation live** (étage 2, montage #977 à positions forcées) : `ncEvaluate` rend **23/23
« empty »** pendant que deux canaux indépendants montrent le contraire — `bucket-audit` voit
**4 pushes dont 2 vers un sous-bucket**, d'utilités **15.0** et **10.0**, et `aiDryRunAllUnits`
propose bien l'ability.

## 3bis. Le piège du gshared transposé aux CHAMPS — trouvé par le garde, pas par relecture

À la première fenêtre de reinject, le correctif a rendu `positions=23 scorees=23 empty=0` : le
faux « empty » disparaissait. **Et c'était un faux positif.** Le garde de concordance du probe a
mordu : l'utilité rendue valait `559.7506`, alors que `bucket-audit` avait vu pousser `15.0` et
`10.0`, et `via` valait `best` partout — impossible sur un playbook à stratégies multiples.

Cause, mesurée : `findClassAnywhere("IdunBattle.AI.BucketSystem", "Bucket\`1")` rend la
**définition générique**, et sur elle `il2cpp_field_get_offset` rend **`0x0` pour tous les champs**
— les offsets d'un générique dépendent de `T`, donc IL2CPP ne les calcule que par instanciation.
Les **noms**, eux, se résolvaient parfaitement (`HighestUtilityAction`, `Buckets`, `MinUtility`),
ce qui rendait le diagnostic *rassurant*. Le décodeur lisait donc `bucket+0x0` — le **pointeur de
classe** : jamais nul, d'où un `best` faussement non nul et une utilité lue dans l'en-tête d'objet.

C'est **le piège du gshared transposé de l'axe des MÉTHODES à celui des CHAMPS** : même signature
(tout se déclare résolu), même issue (une valeur fausse sans la moindre erreur).

Correctif : le layout se résout sur la classe **de l'objet décodé** (`ptr.readPointer()`), avec
cache par classe — le module ne résout plus **aucune** classe par nom. Garde-fou : un offset
d'instance **nul** est refusé explicitement, `+0x0` n'étant jamais un champ.

**Ce qui l'a trouvé** : ni une relecture, ni un test d'existence — le contrôle de **concordance**
avec une valeur connue par un canal indépendant. Un test « le bucket n'est plus vide » aurait été
**vert**.

**Le garde qui manquait, et qui est vérifié.** `probe_988` étage 0 lit les offsets que le décodeur
*injecté* a résolus et les confronte à ceux **lus au décompilé** (`best@0x20`, `subBuckets@0x28`,
`minUtility@0x10` — `EvaluateInternal`, `AddActionToBucket`, `IsValidAction`). Un offset d'instance
**nul** est un rouge : `+0x0` est l'en-tête d'objet, jamais un champ.

Ce garde est **prouvé mordant, sans attendre de réinjection** : joué contre le bundle porteur de la
version fautive, il rend `ROUGE — offsets NULS sur best, subBuckets, minUtility` face aux
`0x20/0x28/0x10` attendus. Il est en lecture pure et s'exécute **avant** tout montage de runner.
Corollaire : la réparation n'exige plus de fenêtre *dédiée* — le prochain reinject, quel qu'il
soit, sera tranché automatiquement par cet étage.

## 4. Deux pièges de méthode rencontrés, et ce qu'ils coûtaient

**Un canal muet ne prouve ni la vacuité, ni sa propre mort.** Sur un premier montage (deux unités
lâchées au spawn), `bucket-audit` rendait 0 fire sur **tous** ses compteurs — la signature exacte
du piège du gshared. La conclusion « ce capteur est inerte » a été écrite, puis **réfutée** par le
second montage, où il fire normalement. Le zéro venait du **montage**, pas du hook. Le probe
sépare désormais les deux (`auditAlive`) au lieu de conclure.

**Un montage qui ne déclenche pas le régime n'est pas un verdict.** Le premier montage ne faisait
pas retenir l'ability par le natif ; « non proposée » s'y serait lu à tort comme « bucket vide ».
Ce sont les **positions forcées** (`--place` / `--a-place`) qui ouvrent le régime.

## 5. Ce qui est livré, et ce qui ne l'est pas

Livré : `frida/hooks/ai-toolkit/bucket-decode.ts` (décodeur récursif ; le layout se résout sur la
**classe inflatée de l'objet décodé**, jamais par nom de classe, jamais en dur) ;
`frida/hooks/probes/playbook-utility-trace.ts` (capteur armable par playbook) ; les deux lecteurs
réparés (`rpc-predict.ts` = `ncEvaluate`, `rpc-nc-predict.ts`), qui publient désormais `via`
(`best` | `subBuckets`), `actionCount` et `subCount` ;
`scripts/python/probe_988_ancres_utilite_playbook.py` et `probe_988r1_cout_capteur.py`.

### Le coût, MESURÉ (session 71, montage 8 unités, médiane sur 3 répétitions)

| régime | tour d'IA | surcoût | fires/tour | dropped |
|---|---|---|---|---|
| désarmé | 0,275 s | — | — | — |
| armé 1 playbook | 0,276 s | +0,001 s (+0,4 %) | **4** | 0 |
| armé TOUS (163 ancres) | 0,348 s | +0,073 s (+26,5 %) | **21** | 0 |

**Aucun des deux axes ne mord.** Latence : ~3 ordres de grandeur sous le régime de crash documenté
(27 000 appels/s → frame > 960 ms). Volume : `dropped = 0`, l'anneau n'est jamais approché. Le
filtrage par adresse reste donc un choix de **propreté de la mesure**, pas de survie — mais il
coûte 0,4 % au lieu de 26,5 %, donc on le garde.

La borne *dérivée* qu'annonçait l'en-tête (« dizaines à quelques centaines d'appels par tour »)
était **surestimée d'un ordre de grandeur** ; elle a été remplacée par le chiffre observé.

**NON couvert — résidu `#988-r1`** : le décodeur corrigé (résolution sur classe inflatée) n'a
**pas** tourné en live, le bundle injecté portant la version aux offsets nuls. Ce qui est
**acquis** : le garde qui tranche cette question est écrit et **vérifié mordant** (étage 0
ci-dessus). Aucune fenêtre dédiée n'est donc requise — au prochain reinject, `probe_988` doit rendre
l'étage 0 vert (`0x20/0x28/0x10`) puis l'étage 2 `ok: true` avec des utilités concordant avec
`{10.0, 15.0}`. Tant qu'il rougit, le décodeur injecté est faux, et c'est dit en 3 secondes.
Portée du coût : les **26** corps `CalculateCustomUtility` n'ont **pas** été exercés par ce montage
(`byMethod` ne montre que `EvaluateNonComparable` et `CalculateCasterPositionUtility`) — leur coût
reste non mesuré, et leur boucle est (position × cible), pas (unité × ability).

Non couvert également : les 23 autres consommateurs Python d'`ncEvaluate` n'ont pas été rejoués
(ils lisent `util`, dont le contrat est inchangé — seules des positions autrefois `empty`
deviennent scorées, ce qui est précisément le correctif).
