# #10036 -- POURQUOI les caches de cliquets churnent sur `master`

Six caches versionnes sont reecrits par n'importe quelle passe et rendent `rc=6`, sur des modules
qu'aucune branche ne touche. Un cliquet qui rougit en permanence n'est plus lu : il ne garde rien.
La question n'etait pas de les regenerer (geste de l'orchestrateur au merge) mais de trouver
**pourquoi leur empreinte bouge sans que le code bouge**.

## Le verdict, en une ligne

**Le code BOUGE.** Aucun des six ne churne par entropie ni par non-determinisme : la cause est une
derive REELLE, amplifiee par des cles de ligne qui agregent un terme GLOBAL, et declenchee jusque
par une edition de COMMENTAIRE.

## Les trois pistes, tranchees par la mesure

Protocole : le cache restaure depuis git, puis le cliquet joue dans **deux process FRAIS** sur le
**meme arbre**, empreintes comparees ; plus un 3e run sans restaurer (detection d'alternance).

| piste | verdict |
|---|---|
| entropie dans le hachage (ordre, chemin absolu, horodatage) | **ECARTEE** -- 5 caches, 3 runs chacun, `A == B == C` partout |
| entree non deterministe | **ECARTEE** -- meme mesure |
| derive REELLE non commitee | **CONFIRMEE** -- c'est la seule qui reste, et elle se reproduit a la demande |

⚠ Un seul `B != C` a ete observe, sur `probe_283 --step exec` : **faux**, la mesure tournait en
fond pendant que l'arbre etait edite (le probe balaye `scripts/python`, donc mes propres fichiers).
Re-mesure a arbre gele, 5 runs : identiques. C'est exactement le motif que le brief redoutait --
ne jamais conclure d'un seul re-jeu, et verifier que l'arbre n'a pas bouge SOUS la mesure.

## La cause : la GRANULARITE de la cle de ligne

Le meme probe le demontre seul, avec ses **deux** appels, dans le meme fichier de code et sur le
meme arbre. Seule la composition de la cle differe :

| appel de `probe_283_enum_ordinal_sweep` | cle de ligne | lignes communes | cles invalidees | valeurs changees |
|---|---|---|---|---|
| `sigs` (`--step exec`) | `sha_texte(<source du fichier>)` | 3307 | **81** | 32 |
| `hits` (`--step exec`) | `sha_texte(<sha du fichier> + "\|" + sha_sigs)` | 3300 | **3300 (100 %)** | **0** |
| `mirror` (`--step mirror`) | `sha_texte(<source du fichier>)` | 3311 | **81 (2,4 %)** | 0 |

`sha_sigs` est **GLOBAL** : le sha de toutes les signatures positionnelles derivees du balayage.
Une seule signature qui bouge invalide **toutes** les lignes `hits`, y compris celles dont la
valeur est litteralement `{"confrontes":[],"hits":[],"hors":[]}`.

**Preuve interne, sans rien supposer** -- pour `_analyze_errors.py`, un fichier qu'aucune branche
ne touche :

```
sigs   cle a4871a27 -> a4871a27   valeur identique   <- shas[rel] INCHANGE
hits   cle 610bc182 -> 7b4aa30c   valeur identique   <- seul sha_sigs a pu bouger
```

La cle `hits` compose `shas[rel]` et `sha_sigs` ; `sigs` prouve que `shas[rel]` n'a pas bouge ; donc
le terme global est le seul coupable. Et la premisse **ECRITE** au code (`probe_283`, en tete de la
passe 2) -- << un port ordinaire ne change AUCUNE signature -> `sha_sigs` est stable >> -- est
**refutee par le fichier lui-meme** : 32 valeurs `sigs` ont change sur la periode.

## Le declencheur dominant : une edition de COMMENTAIRE

`probe_485_imports_differes` cle ses lignes sur la **fermeture d'imports** de la cible. C'est une
granularite revendiquee fine, et elle est en pratique quasi globale, parce que les fermetures
d'`engine/**` sont enormes.

Contre-epreuve ISOLEE -- ajout d'**une seule ligne de commentaire** a `engine/dsl/base.py`, rien
d'autre, puis restauration :

```
cles communes                  : 77
CLES INVALIDEES a valeur egale : 75  (97,4 %)
valeurs reellement changees    : 0
```

C'est **exactement** l'ecart mesure contre `HEAD` (75/77, 0 valeur). Le commit `457e64de`
(<< #1032-r3 : les citations DSL migrees >>) a fait precisement cela sur des dizaines de fichiers
`engine/**` : il a remplace l'ancienne orthographe `DSLFactory$$Filter` (REPLI DELIBERE -- ecrite
ici pour dire CE QUI A CHANGE, ne pas la << corriger >>) par
`IdunBattleLogic.Entities.DSLSelectors$$Filter`, dans un **commentaire**. Nos migrations de
citations VA -> symbole sont donc un moteur de churn a plein regime.

## Cadence : la peremption est structurelle, pas accidentelle

- **368** commits touchent `scripts/python/engine/` en 7 jours (~53/jour).
- `probe_485` et `probe_270r4r2` regeneres a `9eefb900` : **51** commits plus tot, dont **18**
  touchent `engine/`.
- `probe_283` regenere a `944ff145` : **68** commits plus tot, dont **19** touchent `engine/`.
- `probe_326` regenere a `452f3e96` (2026-08-15) : **407** commits plus tot ; **un seul** touche son
  source, et il suffit -- son contexte EST le sha de ce source.

La regeneration a lieu au merge, par un acteur unique ; l'invalidation, elle, court a 53 commits par
jour. Un cache a cle agregee est donc perime **en permanence**, par construction.

## Etat par cache

| cache | regime | mesure |
|---|---|---|
| `probe_283_step_exec` | terme GLOBAL dans la cle (`sha_sigs`) | `hits` : **3300/3300** cles, **0** valeur |
| `probe_485_imports_differes` | cle = sha de la FERMETURE d'imports | **75/77 (97,4 %)**, **0** valeur |
| `probe_326_inventaire_natif` | CONTEXTE = sha de son propre source, change par un commentaire | 10 lignes ; **seule la ligne de contexte** differe |
| `probe_283_step_mirror` | cle = sha du fichier -- **regime SAIN** | **81/3311 (2,4 %)**, 19 neuves |
| `il2cpp_noms_declares` | contexte = sha de `il2cpp_metadata.py` ; regenere a `457e64de` | **aucun churn observe** |
| `probe_270r4r2_import_en_premier` | -- | **aucun churn** : `A == B == C == HEAD`. **Premisse REFUTEE.** |

## Deux angles morts trouves en chemin, non portes

1. **`il2cpp_noms_declares` est structurellement evictable.** `noms_declares` appelle
   `enregistrer()` a chaque invocation, et `enregistrer()` reecrit le fichier avec **exactement les
   entrees vues par CE process**. L'`appel` porte les ANCRES, qui dependent de l'appelant, et
   **deux modules** l'appellent (`probe_419r1tr9r4r1r3_symboles_cites_absents`,
   `probe_433r4r1r4r2_neigh_channel_wired`). Deux ancrages differents s'evinceraient a chaque
   passe -- le fichier n'en porte qu'**une** entree. Le remede est deja ECRIT dans le depot et
   applique ailleurs : `probe_175r2._cache` donne **un fichier par getter**, precisement pour ce
   motif. Non observe aujourd'hui (les deux appelants n'ont pas fait diverger le fichier), donc
   signale comme risque, pas comme defaut.
2. **`sys.platform` et `sys.version_info` entrent dans le CONTEXTE** de `probe_485` et de
   `probe_270r4r2`. Legitime au fond (leur resultat depend de l'interpreteur), mais un cache
   **VERSIONNE** cle ainsi est structurellement FROID pour quiconque n'a pas la meme plateforme et
   la meme version mineure -- meme famille que le piege `sha_fichiers` / CRLF ferme par #486-r11.

## Ce qui n'est PAS couvert

Le remede n'est pas porte : cette tranche etablit la CAUSE, pas la correction. Les deux voies
plausibles -- scinder la cle agregee (un cache par valeur du terme global, comme `probe_175r2` l'a
fait pour ses getters) ou desolidariser la cle du terme global quand la valeur n'en depend pas
reellement -- demandent une lecture de ce que `hits` consomme vraiment de `sigs`, et se jugent sur
le taux de hits, pas sur la taille du diff. Residu `#10036`.
