# #486-r23 -- le VERT offline se VERSIONNE, et le `0,21 %` qui l'avait de-oblige mesurait son EFFICACITE

## 1. Le biais du survivant applique a un garde-fou

Le 2026-08-05, `d82ec527` retire la banque de cliquets de `CLAUDE.md` (-153 lignes) et du skill
d'orchestration (-60). L'argument est une mesure : sur les 67 runs de `logs/ratchets-bg`,
**2 437 lignes de cliquet lues, 5 non nulles -- 0,21 %**, dont deux faux rouges documentes.
Conclusion ecrite alors : « ce sont des prises de FONDATION, pas de GARDE ».

**Cette conclusion est refutee par le resultat.** De-oblige le 05, la suite offline portait
**14-15 echecs** le 07 -- **7 confirmes sur 5 fichiers en 101 s**. Onze fichiers rouges en 48 h.

Le vice a un nom : **biais du survivant applique a un garde-fou**. `0,21 %` de lignes non nulles
ne mesure pas l'inutilite du cliquet, ca mesure son **EFFICACITE** -- un garde qui tient une
propriete ne se voit jamais rougir, precisement parce qu'il empeche la derive qu'il garderait.
L'argument aurait ete **identique, au chiffre pres, pour n'importe quel garde qui fonctionne** :
c'est ce qui le disqualifie comme critere. Un taux de declenchement bas est compatible avec les
deux hypotheses opposees (« inutile » / « efficace ») ; il ne les separe pas, donc il ne conclut
rien.

**Ce qui SEPARE les deux hypotheses est une contre-epreuve, pas un ratio** : retirer le garde et
mesurer la derive. Elle a eu lieu par accident, et elle a tranche en 48 h.

⚠ Ne jamais re-de-obliger un garde sur son taux de declenchement. Le critere valable est le
**COUT**, confronte au **cout de la derive qu'il empeche** -- et c'est cette confrontation-la que
la presente tranche instruit, chiffres a l'appui.

⚠ Corollaire, et c'est ce qui distingue `probe_457` des 45 autres cliquets : **la refutation ne
vaut que pour lui**. Il pese 67 % de la banque et c'est LUI qui a laisse passer les 14 rouges,
parce qu'il n'est pas un cliquet de gisement mais un **lanceur de suite de tests**. Les 32
cliquets de gisement n'ont pas tire une seule fois en 67 runs, et rien ici ne dit ce que vaut
leur de-obligation. **Aucun d'eux n'est retabli par cette tranche.**

## 2. Ce que coute l'etape de PR -- en SECONDES, jamais en pourcentage de fichiers

Le pourcentage de fichiers selectionnes est un indicateur **trompeur** : le cout n'est pas
proportionnel au compte.

Mesure du 2026-08-07 sur `c46bb3cd`, `probe_457 --since HEAD~1`, MONO-SHARD, worktree d'agent :

| grandeur | valeur |
| --- | --- |
| diff | **1 chemin** (`docs/rl/backlog.md`) -- la PR la plus petite possible |
| fichiers retenus | 10 / 236 |
| tests joues | 248 |
| **mur total** | **550,8 s** |
| dont pytest | 476,4 s |
| dont selection (graphe d'imports) | **~40 s** |

Une **PR purement documentaire** paie donc **550,8 s** en mono-shard. La borne basse par les
poids (`logs/ratchets/457-durations.json`, 230,9 s en serie) **sous-estime d'un facteur 2,4** :
les poids chronometrent l'EXECUTION des tests, pas l'import ni la collecte.

Distribution de la selection sur les 20 derniers commits de `master` (empreinte de `c46bb3cd`) :
**min 5, mediane 25, max 236 fichiers**, et **5 commits sur 20 rejouent TOUT**. Quatre de ces
cinq TOUT-rejeux ont la meme cause, auto-infligee : `scripts/ratchets-457-footprints.json` est
une **lecture GLOBALE** de l'empreinte, donc **toute PR qui met a jour l'empreinte declenche un
rejeu complet** -- c'est-a-dire exactement ce que prescrit la consigne « si tu ajoutes un test
offline, mesure son empreinte et commite le JSON ».

## 3. La cause du PLANCHER : pourquoi un diff `docs/` tire dix fichiers

Ventilation des 10 fichiers retenus par le diff `docs/rl/backlog.md` seul (motif exact, pas
l'agregat) :

| fichier | cause | motif |
| --- | --- | --- |
| `test_366_r1_grapnel_launcher_cast_offline.py` | **graphe/incertain** | import non resolu |
| `test_381r1_movable_tiles_pool_offline.py` | **graphe/incertain** | import non resolu |
| `test_270r1r1r3_role_enum_offline.py` | **graphe/incertain** | import non resolu |
| `test_270r4_role_enum_offline.py` | **graphe/incertain** | import non resolu |
| `test_477r24_phase_attribution_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_477r24r1_slots_interface_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_477r25_slots_autres_interfaces_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_337_dsl_triggers_attestation_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_480r8_rpc_joignable_offline.py` | hors .py | empreinte lit `docs/rl` |
| `test_468_collision_numeros_offline.py` | declare | `DECLENCHEUR` couvre `docs/rl/backlog.md` |

**Aucun des dix n'est une declaration trop large.** Le soupcon porte sur
`test_366_r1_grapnel_launcher_cast` et `test_381r1_movable_tiles_pool` -- ils ne dependent PAS de
`backlog.md`, et la mesure le confirme : ils sont retenus par une voie qui **ne regarde pas le
diff du tout**.

**DEUX causes structurelles, et une seule legitime :**

1. **`incertains` du graphe d'imports -- retenu INDEPENDAMMENT du diff.**
   `impacted_files` fait `if abs_rel in touches or abs_rel in incertains`. Or `incertains` est
   construit par `_calculer_import_graph` sur trois criteres qui ne dependent que du FICHIER :
   import relatif (`n.level`), appel dynamique (`import_module`/`__import__`/`load_module`/
   `exec_module`), ou source illisible. **Un fichier `incertain` est donc rejoue a CHAQUE PR,
   quel que soit le diff** -- y compris un diff vide de tout `.py`. C'est un plancher constant,
   invisible, que le rapport de causes agrege sous le mot « graphe ».

2. **La granularite REPERTOIRE des dependances hors-`.py`.** L'empreinte stocke des
   REPERTOIRES (`par_test[rel]["dirs"]`), pas des fichiers. Un test qui lit UNE case-doc de
   `docs/rl` est enregistre comme dependant de **tout `docs/rl`** (~800 fichiers). Comme presque
   toute PR de ce depot touche `docs/rl` (backlog + case-doc), **ces tests rejouent sur presque
   toute PR**. C'est cette voie qui apporte les fichiers LOURDS (`test_477r24r1` 40,9 s,
   `test_480r8` 38,3 s, `test_477r25` 31,8 s).

Legitime, en revanche : `test_468_collision_numeros_offline` **declare** `docs/rl/backlog.md`
parce que c'est l'allocateur de numeros et qu'il lit le backlog par construction. Il est aussi le
plus lourd (**82,5 s**), donc il fixe a lui seul le plancher du mur shardé.

## 4. Ce que la suite instruit

Le reste de cette case-doc (ledger versionne du vert offline, regle de composition, concurrence,
economie mesuree) est redige au fil de la tranche.

**AUCUNE obligation n'est cablee par cette tranche** -- ni dans `CLAUDE.md`, ni dans le skill
d'orchestration, ni sous forme de hook ou de cliquet. La mise en service attend que le mecanisme
existe et que son cout soit connu.
