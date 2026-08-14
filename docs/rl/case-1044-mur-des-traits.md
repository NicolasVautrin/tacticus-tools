# #1044 — le mur des TRAITS : un seul trait résistait, et il n'était pas où on le cherchait

`--unit-stat "<vis>:Traits=[…]"` **MORD**. La prémisse inverse (`#1042-r3` : « NE MORD PAS »)
est **fausse** : re-mesurée le 2026-08-14, elle confondait « le levier n'atteint pas
`BaseUnitComponent` » avec « **un** des traits est réécrit par un second étage natif ».
Sur les **105** membres de l'enum, **104** obéissent ; **`UnitTrait.Hero` seul** résiste — et sa
source est nommée. Le montage sort donc du régime dégénéré sans aucun capteur neuf, sans fenêtre
de reinject et sans une ligne de `frida/hooks/`.

---

## 1. Deux étages natifs, et c'est le SECOND qui faisait mur

| symbole | rôle |
|---|---|
| `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` | énumère `UnitConfiguration.Traits (+0xd0)` et remplit `BaseUnitComponent.<permanents @+0x40>` |
| `IdunBattle.Entities.Factories.MachineFactory$$Build` | appelle **le même** foyer — les Machines of War passent par là aussi |
| `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` (2 args) | passe **APRÈS** et **FORCE** le triplet `{Hero, NPC, Summon}` |
| `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` (3 args) | choisit le `UnitOverrideType` — c'est **lui** qui décide qu'une unité est un héros |
| `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` | la LECTURE effective (veto compris) |

Le premier étage est bien alimenté par `BC.Units[].Traits` : c'est pourquoi le levier mord.
Le second, lu au décompilé, est une table close — `IdunBattle.Operations.UnitOverrideType`,
**type déclaré** lu dans `data/symbols/<build>/frida/methods.tsv` :

```
UnitOverrideType.Hero   (0) -> +Hero(0x10)  -NPC(0x7e6)  -Summon(0x2)
UnitOverrideType.NPC    (1) -> -Hero        +NPC         -Summon
UnitOverrideType.Summon (2) -> -Hero        -NPC         +Summon
```

Et la surcharge à 3 args choisit ainsi :

* si `options.<Nullable<UnitOverrideType>>` porte une valeur → **elle** décide ;
* sinon `heroDeDroit = !hasParent && !Contains(NPC) && !Contains(Summon)`, calculé **sur les
  traits que l'étage 1 vient de poser** ; si vrai → `UnitOverrideType.Hero` ;
* sinon → **retour sec**, aucun des trois n'est touché.

**C'est la sortie, et elle est dans la troisième branche** : une unité dont `BC.Units[].Traits`
porte **déjà** `NPC` (ou `Summon`) n'est plus « héros de droit », la fonction retourne sans rien
écrire, et `Hero` reste **absent**. Il n'existe pas de quatrième voie côté BC : les trois valeurs
de l'enum posent chacune un des trois traits, donc « ni Hero, ni NPC, ni Summon » ne s'obtient
qu'en **court-circuitant** ce foyer.

⚠ **`IdunBattle.Entities.UnitExtensions$$GetTraits` ne rend QUE `+0x40`** — il est aveugle aux
deux autres collections. La lecture qui fait foi est
`BaseUnitComponent$$HasTrait(t) == !retirés(+0x50).Contains(t) && (permanents(+0x40).Contains(t)
|| temporaires(+0x48).Contains(t))`. Le canal publié (`combatSnapshot.units[].traits`, #233)
n'utilise pas le getter : il invoque `IdunBattle.Entities.UnitExtensions$$HasTrait` valeur par
valeur. C'est la bonne mesure, et c'est pourquoi cette tranche n'a demandé **aucun** capteur.

---

## 2. Le régime DÉGÉNÉRÉ, et sa sortie — mesurés dans le même build

Toute unité `lineup` du pool arrive `Hero`, donc `UnitsWithTrait(·, UnitTrait.Hero)` est
uniformément **vrai** : un port sans ce gate y est d'accord avec le natif partout. Exactement la
forme du mur de la rareté (`case-1039`), avec une issue plus courte.

`probe_1044_levier_traits.py`, board `MC1_67`, seed 777, cinq p-units placées + cinq cibles :

| bras | `adeptCanoness` | `adeptRetributor` | `astraBullgryn` | `adeptHospitaller` / `astraCreed` |
|---|---|---|---|---|
| demande `levier-nu` | `[]` | `[Psyker]` | *(témoin)* | *(témoins)* |
| **mesure** | `[Hero]` | `[Hero, Psyker]` | `[BigTarget, Hero, Imperial]` | seed intact |
| demande `hero-separant` | `[NPC]` | `[Psyker, NPC]` | `[Psyker]` | *(témoins)* |
| **mesure** | `[NPC]` | `[NPC, Psyker]` | `[Hero, Psyker]` | seed intact |

Trois lectures, et la troisième est celle qui vaut :

1. **le levier mord** — `Imperial`, `ActOfFaith`, `HeavyWeapon`, `BigTarget` sortent ; `Psyker`,
   absent du seed de ces unités, entre. 9 retraits et 4 ajouts effectifs sur le second bras ;
2. **`Hero` résiste au levier nu**, et il résiste **sur une unité qui ne le demande pas** — donc
   il n'est pas « un patch non appliqué », il est **réécrit** ;
3. **`astraBullgryn` est le CONTRÔLE, dans le même build** : muté sans trait porteur, il reçoit
   `Hero` alors que `BC.Units[].Traits` ne le porte pas, pendant que ses voisins mutés **avec**
   porteur ne le reçoivent pas. Sans ce troisième point, l'absence de `Hero` chez les porteurs
   pourrait venir du montage entier.

Le régime est **SÉPARANT** : 10 paires sur 10 d'unités du même camp portent des jeux différents,
et deux unités sont sans `Hero` quand trois l'ont.

**Il ne dépend ni du board ni du seed** — re-joué à l'identique sur `C3_46` / seed `31337` :
mêmes cinq jeux de traits, mêmes 10/10, même unique résistant. Le premier board d'essai (`C3_01`)
a en revanche **refusé le montage** : la géométrie de `P_POS`/`A_UNITS` est dimensionnée pour un
7×9 jouable sur ces dix tuiles. **376 des boards dumpés** les portent — le montage n'est donc pas
attaché à `MC1_67`, mais il ne s'applique pas non plus à n'importe lequel, et le probe le **dit**
au lieu de conclure.

---

## 3. Le COÛT du levier — mesuré, et il départage les deux traits porteurs

`Summon` marche par la même branche native. Il coûte **beaucoup** plus cher :

| | `--place` tenu | dans `decisionView.toActivate` | `combatSnapshot.units[].ctrl` |
|---|---|---|---|
| porteur `NPC` | **oui** (5/5) | **oui** (5/5) | **oui** (5/5) |
| porteur `Summon` | **non**, `rl_duel build` refuse | **non** | – |

Le refus est reproductible et il se lit sur une seule ligne :

```
[error] placement NON HONORE par le natif: adeptRetributor (team1) demande @(2,1) mais present @[(3, 4)]
```

et, sur le même build, `À ACTIVER : [77, 81, 83, 85]` — `u79`, la p-unit `Summon`, en est absente.

Le refus d'activation d'une p-unit `Summon` est le comportement natif documenté par `#291` (le
jeu termine le tour de toute unité `Summon`/`Object`), pas un trou de harnais. `NPC` est donc le
porteur par défaut, et `Summon` reste nommé sans être utilisé.

⚠ **Ce que le levier ne peut PAS produire** : un jeu de traits **sans aucun** des trois. Toute
unité arrive avec exactement un membre de `{Hero, NPC, Summon}` — soit forcé, soit celui qu'on a
écrit. Un montage qui exigerait « aucun » est hors de portée de cette voie, et il faudrait alors
poser `AddUnitOptions.<Nullable<UnitOverrideType>>` côté message natif.

---

## 4. Ce que ça débloque, confronté

`#1042-r3` est **fermé par la mesure**, pas par argument. Même probe, même board, même seed, seul
le bras change :

| bras de `probe_1042_wisdom_of_the_ancients_live.py` | `targetIds` de l'effet 1445 | P1 | P2 | P3 |
|---|---|---|---|---|
| `mow` (témoin non nul) | `[85, 87, 89]` | oui | oui | oui |
| `mow --traits "adeptCanoness=Imperial,ActOfFaith,NPC"` | **`[87]`** | **non** | oui | **non** |

C'est la signature qu'exige le décompilé du nœud, et elle n'est produite par rien d'autre :

```
F = Filter( B, AmountIsGreaterThanZero(
                   UnitsWithTrait( ValidCharacter( AdjacentFriends(ActiveTarget, unique, 3) ),
                                   UnitTrait.Hero = 0x10, 3 ) ) )
```

Retirer `Hero` au **milieu** de la chaîne `P1–P2–P3` éteint ses **deux voisins** (leur unique
voisin ami n'est plus un Héros) et laisse le milieu **visé** (ses deux voisins le sont restés).
L'étage 1bis du probe confirme la morsure par membre d'enum : `[26, 1007, 2022]` =
`Imperial, ActOfFaith, NPC`, **pas** `Hero`.

---

## 5. Les gardes, et ce qu'elles ont vu ROUGE

* `scripts/python/probe_1044_levier_traits.py` — le **MONTAGE NOMMÉ** : deux régimes
  (`hero-separant`, `levier-nu`), `sans_hero(traits, porteur)`, un étage 0 offline
  (bijection du mirror + les trois membres forcés portent bien ces noms-là) et un étage COÛT.
  Il **refuse** (`rc 2`) plutôt que de conclure : canal `null`, montage incomplet, build refusé.
* `scripts/python/tests/engine/conftest.py::traits_forces_case` — la porte pytest.
* `scripts/python/tests/engine/test_1044_levier_traits_live.py` — 7 assertions.

Vues **ROUGES par mutation du montage**, avant de rendre :

```
AssertionError: adeptCanoness porte toujours `Hero` malgre le trait porteur (demande=[] mesure=['Hero'])
AssertionError: adeptCanoness : `Hero` absent de la mesure -- le forcage d'AddUnitTypeTraits aurait disparu, la prose du probe et la fixture seraient a relire (mesure=[])
AssertionError: astraBullgryn : le forcage n'a pas eu lieu, la contre-epreuve ne discrimine plus (mesure=['Psyker'])
```

La première mutation retire le trait porteur du cas ; la seconde remplace la mesure du canal par
la **demande** — c'est-à-dire exactement le vice qu'on refuse : croire ce qu'on a écrit plutôt
que lire ce que le jeu porte.

---

## 6. Ce qui N'EST PAS couvert

* **Le veto `+0x50`** n'a pas d'écrivain identifié (résidu ouvert de `#233`) :
  `RemoveTraitOperation$$RemoveTrait` retire de `+0x40`/`+0x48`, il ne remplit pas `+0x50`.
  Rien ici ne l'exerce.
* **`AddUnitOptions.<Nullable<UnitOverrideType>>`** — la voie qui permettrait de forcer
  `NPC`/`Summon` **sans** écrire le trait, ou de poser `Hero` sur une unité qui ne le serait pas.
  Elle passe par le message natif, pas par la BC ; non explorée (`#1044-r1`).
* **Les Machines of War** : `MachineFactory$$Build` appelle le même `InitBaseComponent`, mais
  aucun bras ne l'a mesuré — une MoW n'est pas dans `P_POS` du montage (`#1044-r3`).
* **Le substrat de repli du port** (`unit_trait_names`, kit gameconfig) ignore ce forçage : il
  rend les traits du gameconfig, sans `+Hero` ni `-NPC`. Il n'est consulté que lorsque
  `ctx.traits_measured` est faux, donc hors mesure ; l'écart n'est pas chiffré ici (`#1044-r2`).
