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

Livré : `frida/hooks/ai-toolkit/bucket-decode.ts` (décodeur récursif, offsets résolus au runtime
**par le type du champ**, aucun offset en dur) ; `frida/hooks/probes/playbook-utility-trace.ts`
(capteur armable par playbook) ; les deux lecteurs réparés (`rpc-predict.ts` = `ncEvaluate`,
`rpc-nc-predict.ts`), qui publient désormais `via` (`best` | `subBuckets`), `actionCount` et
`subCount` ; `scripts/python/probe_988_ancres_utilite_playbook.py`.

**NON couvert — et c'est le résidu `#988-r1`** : le capteur est **inerte tant qu'il n'est pas
injecté**, donc son coût réel (fires par tour d'IA) n'est **pas mesuré** — la borne écrite dans
son en-tête est *dérivée de la structure du générateur*, pas observée. Le témoin APRÈS n'est pas
non plus posé. Le probe discrimine seul le host patché (champ `via`) et vérifie que les utilités
rendues **concordent** avec `{10.0, 15.0}` — pas seulement qu'elles sont non vides.

Non couvert également : les 23 autres consommateurs Python d'`ncEvaluate` n'ont pas été rejoués
(ils lisent `util`, dont le contrat est inchangé — seules des positions autrefois `empty`
deviennent scorées, ce qui est précisément le correctif).
