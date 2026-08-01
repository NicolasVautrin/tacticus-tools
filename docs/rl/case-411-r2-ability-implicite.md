# #411-r2 — le « x8,06 » n'etait pas une divergence de port : les deux cotes ne jouaient pas la meme ability

**Verdict : (b) ARTEFACT DE MONTAGE.** Le port n'a aucun defaut d'echelle. Le bras temoin
faisait resoudre au port l'attaque NORMALE pendant que le natif executait l'ACTIVE du caster.

## 1. Le symptome, et pourquoi il resistait

`probe_411r1_transfer_port.py` (PR #455) relevait dans son **bras temoin** — celui ou aucun
chemin #411 n'est actif — port **426** contre natif **3433**, soit **x8,06**, avec des ratios
par ailleurs coherents. Deux lectures tenaient et rien ne les separait : (a) un facteur perdu
dans la chaine de degat du port, (b) un bras temoin qui n'atteint pas le regime suppose.

## 2. Le discriminant : un TROISIEME temoin natif

La question binaire, posee avant toute methode :

> Sur le MEME etat pre-attaque, le nombre que le PORT calcule et le nombre que le NATIF
> applique sont-ils deux mesures de LA MEME attaque ?

Elle se tranche avec un troisieme nombre, natif, independant du tirage **et** de l'execution :
la prediction `IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions` (RPC
`aiPredict`, `fresh: true`), prise sur le meme etat. Trois nombres — `P` la prediction native,
`G` le total du port, `N` le delta de PV natif — et une table sans recouvrement : `N` dedans et
`G` dehors = bug de port ; `G` dedans et `N` dehors = montage. Aucun facteur n'est ajuste : on
demande a un temoin natif lequel des deux cotes il valide.
Probe : `scripts/python/probe_411r2_scale_discriminant.py`.

**Rendu** (`MC1_67`/31337, `necroDestroyer` -> `astraBullgryn`, rank 17, `--crit 0,0`) :

| regime | pred natif | port G | natif N | verdict rendu |
|---|---|---|---|---|
| `--block-target 0,0` | `[2610..3912]` | **3433** (dedans) | **6597** (dehors) | (b) montage |
| `--block-target 100,500` | `[2610..3912]` | **426** (dehors) | **3433** (dedans) | (a) port |

Le meme montage rend **deux verdicts opposes** selon le block : c'est la signature d'un ecart
qui n'est pas un facteur. Le block soustrait `~6 x 500 = 3000` **des deux cotes**
(`ApplyBlockDamage` = `Math.Max(0, damage - blockDamage)`, lu au decompile), donc `3433 - 3007
= 426` cote port et `~6433 - 3000 = 3433` cote natif : **le x8,06 est une difference constante
appliquee a deux bases differentes**, pas un facteur x8. Le seul ecart reel est le x1,92 sur
le degat brut.

## 3. Decomposition par etage

`scripts/python/probe_411r2_stage_sweep.py` fait varier UNE entree a la fois et lit la pente
des deux cotes. Aucun scalaire n'est fitte.

**Armure de la cible** (PV forces a 60 000 : a armure basse le natif TUE, et `hp0 - hp1` vaut
alors les PV — une mesure PLAFONNEE qui se lit comme une mesure) :

| `FixedArmor` cible | natif N | port G | ratio |
|---|---|---|---|
| 3513 | 6597 | 3433 | 1,922 |
| 200 | 9797 | 3960 | 2,474 |
| 0 | 10997 | 5160 | 2,131 |

Le ratio **persiste** a armure nulle : l'armure est hors de cause. En reconstruisant depuis
les trois points, les deux cotes appliquent la **meme** regle — `max(0,6 R, R - armure)`,
`0,6` etant le `PiercingDamageRatio` de l'arme — et seul `R` differe : `R_natif = 1832,7`
contre `R_port ~= 860`. L'etage est donc la **base de degat**.

**Base de degat de l'attaquant** (`--unit-stat necroDestroyer:Damage=9|18|36`) :

| `Damage` | `GetStat(ATTACK)` natif | port G | natif N |
|---|---|---|---|
| 9 | 9 | 57 | **10997** |
| 18 | 18 | 111 | **10997** |
| 36 | 36 | 204 | **10997** |

Le port suit la stat ; **le natif ne bouge pas d'un point**. Une execution de degat
insensible a `GetStat(ATTACK)` n'est pas une attaque normale : c'est la signature d'une
ability CONFIG-based. Le « facteur 2 » du premier regime etait donc **fortuit** — le rapport
entre deux quantites qui n'ont rien a voir.

Controles qui ferment les autres portes :
* `appliedHits = 6` cote natif (`aiPlaybookPredict` -> `MakeDamagePredictions`), jamais 12 ;
* bras **sans attaque** : **aucun** delta de PV ; avec attaque : **seule** la cible en perd ;
* `IdunBattle.Entities.Components.MultiValueStatComponent$$GetAllValues` ajoute bien l'entree
  PAR DEFAUT `{entityId 0, GetStatPart(comp, Current)}` avant `AddRange(dict.Values)` — donc
  `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` voit le block scalaire,
  et le port a **raison** de bloquer. Le block n'etait pas le sujet.

## 4. La cause

`decisionView.attackPlans` porte **une entree par ability castable** sur la cible (`_decision`
appelle `decisionView` avec `allAbilities=True`). Pour ce couple, les evals sont :

```
[{"abilityId": 69,   "ability": "Loki_NormalAttack",       "kind": "normal"},
 {"abilityId": 1006, "ability": "MultiThreatEliminator",   "kind": "active"}]
```

L'auto-resolution de `rl_duel.cmd_act` bouclait **sans `break`** : elle retenait donc la
**DERNIERE**, c'est-a-dire l'**ACTIVE**, en silence. Les probes qui croyaient confronter
l'attaque normale faisaient jouer `1006 MultiThreatEliminator` au natif pendant que leur port
resolvait `AttackDamageOperation.execute`. Tout le tableau du §3 s'explique : le degat
config-based de `1006` ignore `ATTACK` mais subit l'armure de la cible.

Le meme piege etait **deja connu et pare ailleurs** : `_normal_ability_map` (TF18) existe
precisement pour ne pas « se fier au defaut (qui peut resoudre vers un ACTIF) » — mais elle ne
servait qu'a `play`/`_apply_spec`, **pas** a `act`.

## 5. Le fix

`rl_duel.cmd_act` **LEVE** desormais (rc 2) quand plusieurs `abilityId` sont candidats,
en listant les candidats et en pointant l'attaque normale. Un seul candidat -> comportement
inchange. On ne durcit pas les appelants, on durcit le choke point : rendre un resultat sur une
ability arbitraire est exactement ce qui **se lit comme une mesure**.

Les quatre probes qui s'y fiaient nomment l'ability via un `_normal_ability_id` local (mirror
de `_normal_ability_map`), qui **leve** si le kind `normal` manque :
`probe_411_transfer_hit_guaranteed_block.py`, `probe_366r1_harlequins_panoply.py`,
`probe_406_harlequins_panoply_move.py`, `probe_411r2_scale_discriminant.py`.

**Apres fix, sur le regime exact du brief :**

| regime | port G | natif N | ratio |
|---|---|---|---|
| `--block-target 0,0` | 3433 | **3266** | **0,951** |
| `--block-target 100,500` | 426 | **349** | **0,819** |

Les deux tombent dans la fenetre native (`[2610..3912]` sans block ; `BlockScenarios[0]` =
`[0..912]` avec block, `count = 1`). **Le x8,06 s'effondre.** L'ecart residuel est le tirage :
port et natif ne partagent pas l'etat du PRNG — l'en-tete de `probe_411r1_transfer_port.py` le
dit lui-meme, et sous block la soustraction de 500 amplifie mecaniquement la variance relative
(chaque coup ne vaut plus que 14..150).

## 6. Consequence sur les chiffres publies de #411

La mesure qui a fonde la RE #411 portait sur l'ACTIVE. Le temoin **6597/0** et la greffe
**3153/3488** cites en backlog sont les chiffres de `1006 MultiThreatEliminator`, pas des
« 6 coups de melee ». **Le verdict qualitatif tient** — rejoue apres fix : temoin **3266/0**,
greffe **1644/1632**, `transfert observe = OUI`, les coups d'index impair quittent toujours la
cible. Seuls les scalaires changent. Idem pour les deux probes Harlequins, dont les verdicts
(`DISCARD CONFIRME`, `ACCORD PORT/NATIF sur la TUILE`) sont preserves — et dont le ratio 0,142
~= 1/6 devient enfin coherent avec le « ~1/N pour une arme a N coups » que le probe annonce.

## 7. NON couvert

* **`probe_411r1_transfer_port.py` n'est pas corrige ici** : il vit dans la PR #455, non
  mergee au moment de ce travail. Il porte le meme appel implicite et **doit** recevoir
  `--ability` explicite ; sinon `rl_duel` le fera desormais echouer en rc 2 (bruyamment, ce qui
  est l'effet recherche). Ses verdicts structurels (ventilation per-coup, ledger de tirages de
  block) sont a rejouer apres fix.
* **Les autres commandes de `rl_duel`** ne sont pas balayees : seul `cmd_act` est durci.
  `_plan_ab_map` conserve son ecrasement « dernier gagne » pour `play`/`_apply_spec` — la
  parade y est `_normal_ability_map`, mais je n'ai pas mesure si tous les chemins l'utilisent.
* **La regle de tri des evals** n'est pas etablie : je constate l'ordre `[normal, active]` sur
  ce montage, je ne l'ai pas lu au natif et je ne m'y fie pas — d'ou le refus plutot qu'un
  « prendre le premier ».
* **Le regime crit** n'est pas confronte (`--crit 0,0` partout).
