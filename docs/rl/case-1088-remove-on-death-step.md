# #1088 — `IEffect` slot 4 `get_RemoveOnDeathStep` : une hypothèse nommée qui était fausse, et le dériveur qui ne pouvait plus la lire

Build `t6dpr4k06g` (2026-08-15). Tranche du foyer `scripts/python/engine/entities/effects/base.py`.

## 1. Le fait

`IdunBattle.Entities.Effects.BaseEffect$$get_RemoveOnDeathStep` rend **`1` = `AfterUnitRemove`**
(corps `b8 01 00 00 00 c3`, 66 contrôles d'alignement locaux). Le port posait `0` = `PreUnitRemove`,
en **hypothèse nommée** (#389-r2), faute de pouvoir lire un getter constant dédupliqué par IL2CPP.

Quatre classes surchargent, sur 465 (`data/symbols/<build>/metadata/remove_on_death_step.tsv`,
**0 indéterminée**) :

| classe native | valeur | mirror Python |
|---|---|---|
| `IdunBattle.Entities.Effects.TauntedEffect` | `2` `AfterDeathTrigger` | `TauntedEffect` |
| `IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect` | `2` | **aucun** |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeed_ExtraExplodeEffect` | `2` | **aucun** |
| `IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect` | `0` `PreUnitRemove` | `AttemptedPossessionPossessedEffect` |

Ce n'était donc **pas** un cas particulier de `Taunted` : les 461 classes qui héritent étaient
toutes décrites au mauvais step.

## 2. Pourquoi l'écart n'était PAS inerte

La fiche d'origine écrivait « conséquence NULLE sur l'observable (les trois steps tournent) ».
`IdunBattle.Operations.KillUnitOperation$$Execute` place ses deux events **entre** le step 1 et le
step 2 :

```
RemoveEffects(step 0) -> RemoveEffects(step 1) -> On(UnitDeath) -> On(UnitDefeated) -> RemoveEffects(step 2)
```

Un effet à `AfterDeathTrigger` est donc **encore porté** quand ces events partent. Le port, qui
retirait tout au step 0, rendait structurellement impossible tout trigger lisant un effet du
mourant — cause racine de la face SUCCESS inerte de `#911-r1`, dont la mesure live exigeait
`HasEffect(Target, 27 Taunted_OnlySpecificTargets)` vrai à `On(UnitDefeated)`.

Les deux sources se rejoignent sans s'être vues : la mesure live disait « step ni 0 ni 1 », la
dérivation binaire rend `2`.

## 3. Le filtre a une clause que les résumés perdaient

`IdunBattle.Operations.RemoveEffectsOperation$$Execute`, relu verbatim :

```
if (options.step.HasValue && effect.<IEffect slot 4> != options.step.Value)  -> NE PAS retirer
if (options.keepOnRevive     && effect.<IEffect slot 2 = get_KeepOnRevive>)  -> NE PAS retirer
```

Le filtre par step est **gardé par `HasValue`** : un appel sans step retire **tout**, quel que soit
le slot 4. « Compare le slot 4 à `options.step` » ne le montre pas.

## 4. Ce qui empêchait de lire — et qui n'était pas ce qu'on croyait

`probe_175r2_can_be_immune_to.py` sait résoudre exactement cette forme de question. Il **crashait**
sur le nouveau build (`FileNotFoundError` nu) : son calage du bloc `methodPointers` ancrait sur
`ghidra/functions.tsv`, table extraite seulement après des heures d'analyse, absente au lendemain
d'un changement de build.

L'ancre n'a jamais eu besoin de ghidra — elle ne sert qu'à **situer** le bloc, donc n'importe quel
couple (symbole, VA) suffit. `frida/methods.tsv` le porte, **et elle est estampillée** par le
sha256 du binaire dont elle sort. Elle passe en première, ghidra en repli.

**Confrontation non dégénérée** : les deux ancres rendent le même ensemble de **13** classes à
`get_CanBeImmuneTo` effectif vrai (ghidra sur `rnca9r7q6c`, frida sur `t6dpr4k06g`), et 13 n'est pas
zéro. Le calage vote **1193/1384** sur une seule base, 2ᵉ tête à 22 voix. `probe_982r4`
(`get_KeepOnChangeOwner`, second getter) rend lui aussi le même résultat qu'avant.

Deux crans ajoutés, chacun fermant un faux vert : la clé du cache hache **la source d'ancre
réellement utilisée** (sinon la bascule `methods.tsv` → `functions.tsv`, le jour où l'extraction se
termine, servirait un verdict dérivé avec l'autre source) ; et le **décodeur** entre dans la clé
d'appel.

⚠ **La largeur est le piège du décodeur entier** : `32 c0` est `xor al,al` (8 bits, ce qu'un
compilateur émet pour un `bool`), `33 c0`/`31 c0` sont `xor eax,eax` (32 bits). Et un `c3` **nu** ne
définit pas `eax` : il est nommé illisible, jamais rabattu sur `0` — ce qui aurait fabriqué un
`PreUnitRemove` par défaut, c'est-à-dire exactement l'erreur qu'on corrigeait.

## 5. Le déplacement de feuille

Le foyer doit **nommer** la valeur (règle « un entier qui désigne passe par un enum »), or charger
`engine/runner/operations/remove_effects.py` tire **177** modules `engine.*`, `entities/effects/base`
compris : l'importer de là aurait fermé un cycle.

La doctrine ordonne **(1) déplacer** avant **(3) différer**. `KillUnitStep` vit désormais dans
`engine/entities/kill_unit_step.py`, feuille qui n'importe **rien** de `engine.*` (2 modules
chargés). Les 5 importeurs sont repointés ; **aucun ré-export** laissé derrière (un baril neuf irait
contre #485-r1-r1). Registre `probe_313` mis à jour dans le même commit — 38 mirrors en bijection.

## 6. Ce que la validation a trouvé — deux faux verts, dont un à moi

**Le test existant était aveugle.** En remettant l'ancien défaut faux,
`test_389r2_kill_unit_remove_effects_offline.py` reste **intégralement vert** (10 passed) : il pose
ses steps explicitement sur des stubs. Le défaut faux vivait depuis #389-r2 sans que rien ne
rougisse.

**La première version de la garde neuve l'était aussi.** Son helper **ré-implémentait** le prédicat
(`int(getattr(eff, "remove_on_kill_step", <défaut>))`) pour s'épargner le montage d'un `State`
complet. Il rendait les bons chiffres, et la mutation du code de **production** le laissait vert.
Trouvée par mutation, pas par relecture. Il appelle désormais le vrai `remove_effects_operation` ;
le seul régime inatteignable autrement — un objet-effet **étranger** à la hiérarchie, donc sans
l'attribut — substitue l'étage **aval** (`remove_effect_instance`) et laisse intacte la clause
mesurée.

Mutation adversariale finale, **5/5 mordent** : défaut → `PreUnitRemove` (4 rouges) ; `Taunted` →
`AfterUnitRemove` (4) ; défaut de secours → `0` (1) ; `Possessed` → hérité (2) ; suppression de la
garde `step is not None` (1). Arbre non muté : 7 passed.

## 7. Le second site, invisible depuis le foyer

`remove_effects_operation` portait `getattr(eff, "remove_on_kill_step", 0)` — **le même faux
défaut**, recopié là où aucune surcharge de classe ne le corrige. Corriger le foyer seul l'aurait
laissé mordre sur tout effet hydraté par un chemin ne passant pas par `BaseEffect`.

Et `AttemptedPossessionPossessedEffect` vaut `PreUnitRemove`, c'est-à-dire **exactement l'ancien
défaut faux** : sans ligne explicite, la correction du défaut l'aurait décalée d'un step en silence.

## 8. Ce qui n'est PAS couvert

- **Aucune confrontation live** de la face SUCCESS de `#911-r1`. L'étage est levé ; le montage
  (`probe_911r1_daemonic_patrons_finale_live.py` + un bras où la cible tauntée MEURT) reste à jouer.
- **Deux classes natives surchargent sans mirror Python** : `ArmourOfShriekingSoulsEffect` (1423) et
  `RammingSpeed_ExtraExplodeEffect` (1098), toutes deux à `AfterDeathTrigger`. Leur existence est
  figée par l'étage 3 du test, pour qu'un port futur ne les redécouvre pas et que leur disparition
  se voie.
- **La 2ᵉ source runtime (vtable) n'a pas pu confronter les surcharges** : 5 classes sur 7 sont non
  initialisées dans la session courante. Le probe sort **rouge** en le disant, au lieu d'appeler
  « accord » ce qui est compatible avec un lecteur constant — sa garde de non-dégénérescence exige
  au moins deux valeurs distinctes. Pour la fermer : poser un taunt en bataille, puis rejouer
  `probe_1088_remove_on_death_step.py --runtime`.
