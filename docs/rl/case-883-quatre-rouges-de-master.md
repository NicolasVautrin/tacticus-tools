# #883 — Les quatre rouges de `master` : UN bug de port, UN cliquet qui accusait le port, DEUX montages

Quatre rouges signalés « préexistants » par trois PR successives, tous reproduits sur `master`
(`07aa9154`). Ils ne relevaient **pas** de la même cause, et trois des quatre n'accusaient pas le
port. Le seul vrai bug de port est aussi celui que personne ne pouvait voir : sa mesure de
validation historique était **incapable de le départager**.

Le fil commun des quatre : **un accord mesuré en régime dégénéré ne prouve rien**, et il coûte
plus cher qu'une absence de mesure — parce qu'il s'écrit ensuite dans le code comme une certitude.

---

## 1. `probe_437r1r1r1_effect_face_table` — le CLIQUET accusait le PORT (outil)

**Verdict : ACCUSE LE MONTAGE (l'outil). La face du port est JUSTE.**

Le cliquet rendait `DIVERGENCES : 1` —
`UnbreakableDuty_DamageReduction  port=defender  natif=attacker`.

Le natif dit **defender**, et le port a raison. Lu dans les tables et confirmé au binaire :
`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDuty_DamageReductionEffect` dérive
directement de `IdunBattle.Entities.Effects.BaseEffect` et n'implémente **que**
`$$CreateEffectDamageMalusForDefense` (slot 0x1a, builder DÉFENSEUR) — il n'a aucun
`CreateEffectDamageBonusForAttack`.

### La cause, et pourquoi elle était invisible

`resolve_native_class` remonte la MRO de la classe de port pour couvrir un cas légitime (une
sous-classe de port — `...DroneEffect(...Effect)` — mirroire la même classe native que son parent
et ne re-cite pas le symbole). Mais la remontée **ne s'arrêtait pas avant `BaseEffect`**, qui
n'est le mirror d'AUCUNE classe native : les symboles de sa docstring y sont des **exemples**. Elle
en cite **neuf**, et le départage `max(count, -index)` en élisait toujours le même —
`ConquerorImperativeEffect`, face `attacker`.

Mesure sur `rnca9r7q6c` : sur les **69** classes du port à face de dégât, **9** résolvaient par
remontée, dont **8 jusqu'à `BaseEffect`**. Sept d'entre elles étaient d'accord **par
coïncidence** (leur face de port est `attacker`, celle de `ConquerorImperativeEffect` aussi) ; la
huitième — `defender` — sortait en DIVERGENCE. Le cliquet mesurait donc 8 lignes contre la
mauvaise classe native, et son vert sur 7 d'entre elles ne prouvait rien.

S'y ajoutait un second défaut, **non mordant aujourd'hui mais réel** : le regex `_SYM` n'acceptait
que le préfixe `IdunBattle.Entities.Effects[.Loki]`. Compte dérivé de `methods.tsv` (déclarations
d'un des quatre slots) : `IdunBattle.Entities.Effects.Loki` 166, `IdunBattle.Entities.Effects` 5,
`IdunBattleLogic.Entities.Abilities.Triggered.Loki` 5,
`Idun.Source.IdunBattle.Logic.Entities.Effects.Loki` 1,
`IdunBattleLogic.Entities.Abilities.Active.Loki` 1 (celui d'`UnbreakableDuty`),
`IdunBattle.Entities.Effects.Idun` 1 — soit **8 déclarations sur 179 hors de portée**. Le préfixe
est désormais libre, et c'est `classes.tsv` qui tranche, comme le probe le prescrivait déjà.

### Le cran ajouté

Un appariement établi par un PARENT de MRO qui **contredit** celui du nom est désormais compté
(`APPARIEMENTS EN CONFLIT`, dans le `rc`). Contre-épreuve : en réintroduisant la remontée jusqu'à
`BaseEffect`, le cliquet rend `rc = 9` et **nomme les 8** — y compris les 7 qui étaient vertes.
Sans ce cran, une panne d'appariement se traduisait en fausse divergence de FACE, donc en
accusation du port.

---

## 2. `test_lord_of_tempests_snowball_second_attack` — LE bug de port

**Verdict : RÉEL, corrigé.**

`offline 10525` contre `live 10527`. La décomposition par étage localise l'écart **au coup près** :

| | coup 1 | coup 2 | coup 3 |
|---|---|---|---|
| crit | `True` | `True` | `False` |
| LIVE | 5198 | 4129 | 1200 |
| port | 5197 | 4128 | 1200 |

**+1 sur chacun des deux coups CRITIQUES, 0 sur le coup non critique.** Le `hp0 - hp2` du test
n'était pas le coupable : la somme des `Amount` live vaut aussi 10527.

### La chaîne, remontée étage par étage

`hit_nc = (1042, 1364)` ; `hit_cr = (3905, 5317)`. Le décalage `hit_cr - mm` vaut **+1081 sur les
deux bornes** ; `mm(3530) = (2824, 4236)` avec `3530 x 0.8` et `x 1.2` tous deux **entiers** — donc
aucun arrondi possible à cet étage. L'écart vient d'un terme du décalage, et il vaut 1.

Ce terme est `ice_crit_damage_addition`, mirror d'
`IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack` :
`PercentageOf(StatAmount(attaquant, 10 = CRIT_DAMAGE), EffectConfig(5))`, avec
`cd = 2727`, `pct = 25` ⇒ **681,75**. Le port écrivait `(cd * pct) // 100` = **681** ; le natif
rend **682**.

### La vérité native, LUE

`PercentageOf` porte un **4ᵉ argument, `roundingRule`**, et `IceEffect` lui passe `0`. Son
consommateur `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` :

```
rule == 1 -> Fix64.Ceiling
rule == 2 -> Fix64.Floor
sinon (0) -> Fix64.Round          <- celle d'IceEffect
```

Le port appliquait donc la règle **2** là où le natif écrit **0**. `IdunBattle.Entities.Formulas.
PercentageOf$$CalculateInternal` normalise le pourcentage puis arrondit le produit à 2 décimales
avant `RoundFix64Result` : sur des entrées entières `cd` et `pct`, `cd x pct / 100` a au plus
2 décimales, donc ces deux étages sont des no-op et la chaîne se réduit à l'arrondi final.

**Le fix ne fabrique rien** : le foyer DSL générique du port était **déjà** juste —
`entities/formulas.py::PercentageOf` fait `_round_fix64(Fraction(pct*base, 100), mode)` et sa
docstring dit littéralement « **PAS `pct*base//100`** ». `ice_crit_damage_addition` était un site
**impératif qui contournait ce foyer**. Il le consomme désormais.

### Pourquoi le floor a tenu si longtemps — l'accord en régime dégénéré

La mesure qui l'attestait (`probe_45f --case crit`) force `cd = 700`, et
`700 x 25 / 100 = 175,0` **n'a aucune partie fractionnaire** : floor et round y rendent le même
175, sur 4 coups sur 4. Le témoin ne pouvait pas départager les deux règles, et son accord s'est
écrit dans le code sous la forme « `-> Fix64 -> floor int (+175 mesure)` ».

L'écart n'est pas marginal : à `pct = 25`, **1 500 valeurs de `cd` sur 4 000 (37,5 %)** sont
discriminantes. Le témoin historique (700) tombait dans les 62,5 % qui ne le sont pas.

Contre-épreuve du fix : `682` rend exactement le live, avec **monotonie stricte** autour
(680 → `[5196, 4127, 1200]`, 681 → `[5197, …]`, 682 → `[5198, …]`, 683 → `[5199, …]`) — la valeur
est déterminée de façon unique, ce n'est pas un ajustement multi-paramètre.

### Le cliquet qui manquait

Le fix n'était gardé que par un test **live** dont le pouvoir discriminant dépend de la géométrie
du drive et de la stat de Njal : que `cd` tombe un jour sur une valeur non fractionnaire, et il
redeviendrait vert avec le floor restauré, sans plus rien garder — exactement le sort du témoin
précédent. `tests/engine/runner/test_883_ice_crit_rounding_offline.py` ferme cette porte : il
appelle **le site lui-même** sur un état minimal (aucun runner, aucun RPC), et **assertionne que
son propre couple est discriminant**. Vérifié : avec le `// 100` restauré, il rend `rc 1`.

---

## 3. `test_supercharge_pierce_effect_boosts_its_own_hits` — le MONTAGE

**Verdict : ACCUSE LE MONTAGE. Le port est juste.**

`avec={81: 5472, 77: 0, 83: 7815}` contre `sans={81: 3398, 77: 0, 83: 5305}`. Les deux cibles qui
encaissent montent bien — c'est précisément ce que le test veut prouver (l'`AddEffect` est le
PREMIER volet du `&`). L'échec vient de `u77`, à **0 des deux côtés**, sur lequel `0 > 0` est faux.

`u77` est `blackAbaddon` (traits `TerminatorArmour`, `Resilient`), **vivant**, hp 10038. Son coup
est réduit de **-75 %** par `TerminatorArmour_ReduceDmg` (roll 3744 → 936), puis passe sous
l'armure effective 2510 → **0**. Aucune quantité de perçage ne peut le remonter : le discriminant
du test est structurellement inopérant sur cette cible, dans les deux bras.

**Le régime a changé sous le test.** Il a été écrit le 2026-07-26 ; l'absorption `TerminatorArmour`
a été portée le 2026-08-01 (#432, `5e9765cd`). Le test n'a jamais cessé d'être juste sur ce qu'il
prouve — il a cessé d'être **posable** sur une de ses trois cibles.

La garde est **renforcée, pas relâchée** : le `>` strict est maintenu sur chaque cible
confrontable, et il faut qu'il en reste **au moins une** — sans quoi un montage entièrement
dégénéré passerait pour un succès. Les cibles écartées sont nommées dans le message d'échec.

---

## 4. `test_calibanite_toggle_live_both_directions` — le MONTAGE, encore

**Verdict : ACCUSE LE MONTAGE. Le port est juste.**

`live2 groups=[] post=[]` : au 2ᵉ cast, le porteur n'a plus **aucun** effet. Mesuré pas à pas —
u91 (Forcas, `darkaCompanion`) est **tuée pendant le tour de l'IA adverse** qui sépare les deux
casts : `alive: False`, `hp: 0`, effets purgés.

Le côté port était correct de bout en bout (`off2 = Strike, add=[1404, …], rm=[1405]`) ; le live ne
pouvait pas répondre. Et l'échec était **muet** : un cast sur une unité morte revient
`ok: True, mutated: False, events: []` — le no-op est **accepté**, donc `post2` sort vide et
l'assertion de posture échoue en accusant le port.

La cause est le contact. `probe_112_darkangels.build(near=True)` déplace le camp joueur au contact
— nécessaire pour le splash de Supercharge et la branche Chaos d'ExemplarOfHate, **inutile pour un
toggle de posture qui ne fait aucun dégât**, et qui en paie le prix fort puisque le contact rend le
porteur atteignable. Hors contact, même seed : Forcas survit intacte et le toggle répond dans les
deux sens (`post1 = [… 1405]`, `post2 = [… 1404]`).

Deux changements, et le second compte autant que le premier : le test prend une fixture
`da_fresh_far` (`near=False`), et la survie du porteur devient une **assertion** — c'est ce qui
distingue « le port se trompe » de « le montage ne pose plus la question ».

---

## Ce que cette tranche laisse ouvert

* **`#883-r1`** — les autres sites du port qui matérialisent un `PercentageOf` par floor.
  Balayage `engine/**` : **6** occurrences de `// 100`, dont 2 en prose, 2 explicitement `Ceiling`
  et documentées (cohérentes avec `roundingRule = 1`), et **1 site exécutable non confronté** :
  `entities/abilities/active_ability.py::get_health_to_lose`. Les trois règles existent réellement
  dans le binaire — chaque site exige de LIRE le `roundingRule` de son écrivain natif, et `2` est
  une réponse valable.
* **L'empreinte `probe_457` du test neuf n'est pas gravée.** `--measure-missing` **refuse** de
  s'exécuter (`rc 99`, garde-fou délibéré du dépôt contre le réflexe) ; le forcer aurait coûté un
  rejeu de plusieurs centaines de secondes hors périmètre. Conséquence exacte, à connaître au
  merge : `probe_486r15` classe ce fichier parmi ceux « confrontés à UNE SEULE source » (fermeture
  d'imports) — son verdict reste `PASS`, mais la seconde source ne sera confrontée qu'au moment où
  l'empreinte sera regravée.
* **La fidélité de `TerminatorArmour_ReduceDmg` n'est pas jugée ici.** Le A/B du §3 est neutre
  vis-à-vis d'elle : les deux bras appliquent la même absorption, donc l'écart mesuré ne peut rien
  en dire — dans un sens comme dans l'autre.
