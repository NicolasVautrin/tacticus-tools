# #943-r6 — les trois derniers rouges offline : deux réparations, une tolérance MESURÉE

Suite de `case-943-quinze-rouges-offline.md`. Trois rouges restaient sur `master`, chacun avec
une cause déjà nommée. **Les trois sont verts.** Deux étaient des réparations ; le troisième
demandait une décision, et la mesure l'a tranchée dans l'autre sens que la supposition écrite.

Attribution faite d'abord, sur arbre témoin détaché (`87e733cc`) : les trois rouges y sont
reproduits à l'identique, aucun n'était résorbé entre-temps.

## 1. `ai_control.py:133` — un différé GRATUIT, hissé en FORME B

`PerformAIMovement.execute` différait `ComputerMovementActionOperation` alors que le préambule
du même fichier charge déjà `...operations.summon_ai` (ligne 30). Ni cycle possible, ni coût.

Hissé en **forme B** (`from ...operations import summon_ai` puis `summon_ai.X`), pas en forme A :
`migrate_485r1_barils_reexport.py morsure` mesure **0 patcheur** sur ce nom aujourd'hui, et c'est
précisément pourquoi la forme qui n'en interdit aucun est la bonne — une liaison A gèle le binding
et désarmerait tout `monkeypatch.setattr` futur.

⚠ **Le différé VOISIN, ligne 289, n'a PAS été touché** : `perform_ai_ability_unit_behaviour` est
en forme C et **patché** par `test_590r4_utility_entity_offline.py:97`. Le hisser désarmerait ce
patch. Les deux différés du même fichier n'ont donc pas le même statut, et le recenseur de morsure
est ce qui les sépare.

## 2. `WrathfulDevotionAbility` sur `On(59)` — le test avait tort, le port avait raison

`case-943` §7 accusait `WrathfulDevotionAbility` de consommer `On(59)` « **sans lire
`ev.triggering_ability`** ». **C'est faux, et vérifiable en une ligne** : `wrathful_devotion.py`
lit `getattr(ev, "triggering_ability", None)` et sa docstring cite déjà #306. L'accusation était
supposée depuis le nom du test tombé, pas lue.

Le vice réel était **dans le test**. `test_the_divergence_is_latent_and_says_why` promettait dans
sa docstring de rougir « quand on ajoute un consommateur *qui lit le mauvais canal* », mais
assertionnait `got == []` — une **interdiction de présence**. Le jour où un consommateur légitime
est arrivé, il ne savait que l'interdire.

Mesure directe, sur le vrai `matches` :

| forme du payload | `+0x60` | `+0x98` | `matches` |
|---|---|---|---|
| ce que `RemoveEffectOperation$$Execute` publie | `1035` | *vide* | **True** |
| miroir, jamais produit par le natif | *vide* | `1035` | **False** |
| un autre `EffectType` sur `+0x60` | `Pinned` | `1035` | **False** |

Le gate lit donc bien `CurrentAbilityIs` (`DSLSelectors+0x88` → `+0x60`), conformément à
`WrathfulDevotionAbility$$CreateTrigger` branche 2.

L'assertion est remplacée par une **mesure** (`EFC.verdict_canal_retrait`) : chaque consommateur
d'un vecteur de retrait est instancié, son `matches` exécuté, et le canal **réellement demandé**
relevé par un `TriggerEvent` traçant. Ce n'est pas un grep — il voit les `getattr` et les lectures
faites dans une classe de base. Deux fautes sont cotées : être vrai sur la forme miroir, et ne lire
QUE `+0x98`.

Trois gardes neufs, dont **deux contre-épreuves** : un témoin de non-vacuité (le verdict serait vert
à vide si le registre perdait son dernier consommateur de retrait), le pendant exact des deux tests
de consommateur de POSE sur la face RETRAIT, et une mutation qui recâble le gate sur
`triggering_effect` et **doit** faire rougir en nommant la classe.

## 3. `#943-r4` — la tolérance, et la mesure qui la fonde

L'auteur de #943 avait refusé la réparation locale pour deux raisons écrites. **Les deux ont été
mesurées, et elles ne se valent pas.**

**Raison 1 — « trois autres fonctions font la même géométrie et sont invisibles au critère » :
CONFIRMÉE, et très sous-estimée.** Le critère d'entrée des étapes 2 et 4 est un token de *prose*
(la docstring nomme un natif à liste stockée), pas une propriété du code. Balayage par le CONTENU
(`etape6`, ajoutée ici, même arbre, même passe) :

```
29  fonctions d'engine/ comparent une distance hex a 1
 2  vues par etape2 (declarantes, sans canal)   <- les 2 rouges
 2  touchent le canal (etape4)
25  MUETTES -- invisibles aux etapes 2 et 4 par construction
```

Les trois nommées par #943 sont **confirmées** et ne sont que 3 des 25. `imperative.py::
create_aura_attack_damage_bonus_for_ally` applique exactement le même `hexgeo.distance != 1` que
son jumeau `icon_of_obstinacy`, sans le mentionner — le premier est invisible, le second est rouge.
Réparer les 2 visibles laisserait **25** sites divergents : c'est le fork que les docstrings
annoncent, pas son évitement.

**Raison 2 — « l'élévation peut déplacer la ground truth live de #930 » : PARTIELLEMENT RÉFUTÉE.**
La ground truth citée (`statModSources`, `orksBigMek`, « le porteur se buffe lui-même ») porte sur
le terme `op_Addition(Owner, ...)`. Le porteur est ajouté par `out = [int(owner_id)]` **avant toute
boucle** — il ne traverse aucun test de distance. Aucun câblage de canal ne peut donc le déplacer.
Ce qui peut bouger, et qui reste à confronter live, est l'ensemble des **voisins** retenus ; l'écart
est strictement RESTRICTIF (`hexgeo` seul sur-atteint : 4 arêtes sur `C1_74`, 38 sur `C3_14`, 0 dans
l'autre sens).

### Ce qui est livré : une tolérance NOMMÉE, pas un silence

`GEOMETRIE_NUE_TOLEREE` liste les **deux** sites par `(chemin, nom de fonction)` — jamais par
ligne, qui bouge à chaque édition et ferait périmer la liste sans que rien n'ait changé au fond.
`etape2` reste la mesure **brute** ; `etape2_hors_tolerance` porte le verdict. Quatre gardes, dont
**deux contre-épreuves** :

* une entrée qui ne désigne plus aucun site réel est **PÉRIMÉE** et rougit — même mode de
  défaillance que la suspension de l'étape 5 ;
* la **justification se re-mesure** : si les 25 muets disparaissent, la tolérance n'a plus d'objet
  et tombe. Les trois foyers nommés par #943 sont vérifiés toujours présents ;
* un mirror déclaré **neuf** à géométrie nue rougit malgré la tolérance ;
* **vider la liste fait réapparaître exactement les deux sites** — c'est ce qui prouve que le vert
  vient de la tolérance et non d'une disparition silencieuse du gisement.

## 4. Ce qui n'est PAS couvert

* **`#943-r6-r1`** (résidu ouvert) — `etape1` du même probe est **ROUGE** sur `admec.py:917`
  (`are_entities_adjacent` : élévation fournie, voisinage omis) et **aucun test de la banque ne la
  joue** : le seul fichier qui importe le probe appelle `etape2/3/4/5`, jamais `etape1`. Les quatre
  étapes *neuves* ont un test de câblage dédié, l'ancienne n'en a pas. Non traité ici : la tranche
  était bornée aux rouges JOUÉS, et câbler `etape1` rendrait rouge une banque qu'elle devait rendre
  verte.
* **Deux rouges de `probe_486r15`**, hérités et **attribués sur arbre témoin** : ils préexistent à
  `87e733cc`. `test_940_kiss_of_death_offline.py` (périmètre trop étroit d'un chemin :
  `engine/runner/abilities/behaviours/__init__.py`) et `test_932_deathwing_offline.py`
  (`data/seed-bc.json`). Réparation mécanique — une ligne de périmètre chacune — mais hors des
  trois rouges de la tranche, et sur des fichiers de tranches récentes possiblement en vol.
* **`scripts/cliquets-cache/probe_270r4r2_import_en_premier.tsv`** régénéré par la passe et
  **non livré** : 411/395 lignes de diff dont la quasi-totalité vient de fichiers merges depuis la
  dernière régénération, pas de cette tranche. Même raison mesurée que `#943-r2` — le livrer
  garantirait un conflit avec toute PR en vol sur un TSV généré.
* **Aucune confrontation LIVE de la tranche elle-même** (les trois rouges sont offline). Un probe
  live existant a néanmoins été rejoué : `probe_936_wrathful_devotion.py` rend `VERDICT: OK`,
  boucliers et marqueurs visuels identiques live/port sur les deux faces.
