# #462-r4e — `test_damage_catalog_live.py` : l'échantillon n'avait jamais été confrontable

**Rouge de MONTAGE**, inventorié par #462 (`p=0 f=4`) :

```
build runner KO (rl_duel) [...] --p-units: hors pool / non spawnables au rank 17:
        ['adeptSmnGeminaeSuperia']
        pool = 97 units (voir `build --list-pool`)
```

`p=0` : **zéro assertion évaluée**. Le fichier ne rougissait pas parce qu'un dégât avait bougé —
il ne démarrait pas.

---

## 1. La cause, établie — et ce n'est pas une régression

`_catalog_units()` échantillonnait `unit_map.all_kits()`, qui balaie **`lineup` + `npc` +
`summons`**, trié alphabétiquement, `[:4]`. **Aucun filtre de spawnabilité, à aucun moment de
l'histoire du fichier** : `all_kits()` incluait déjà les trois `kind` au commit de création
(`2faf6cea`, 2026-06-29), et le fichier n'a jamais été retouché depuis.

Ventilation des **80** unités au profil vanilla melee-multihit (mesurée le 2026-08-03) :

| `kind` | compte | arrive par `--p-units` ? |
|---|---|---|
| `summons` | 14 | **non** |
| `npc` | 57 | **non** |
| `lineup` | 9 | 6 oui, 3 non |

Les 4 têtes alphabétiques du régime par défaut étaient `adeptSmnGeminaeSuperia` (**summon**) puis
`admecBossBelisarius` / `admecBossManipulus` / `admecBossManipulusCE` (**npc**) : **les 4
paramètres étaient non spawnables**, donc 4 builds refusés.

**Pourquoi le summon n'est pas au pool** — il est pourtant DANS `BC.Units` du seed (175 entrées,
les summons compris). Il échoue la normalisation : `buildNormalizedBC` ne retient que ce qui passe
`IStatsFormula.StatsUsingProgressionIndexFor` au rank cible, et un summon n'a **pas de stats de
progression propres** (`Damage` / `FixedArmor` / `Health` absents du gameconfig — il hérite de son
summoner). Ce n'est donc ni (b) « le seed BC a changé » ni une dérive d'`unit_map` : c'est (c), un
summon, et la voie qui l'amènerait en bataille n'est pas `--p-units`.

**Chronologie de l'invisibilité** : `build_runner` rendait un `pytest.skip` → **4 skips VERTS
silencieux du 2026-06-29 au 2026-07-25** ; le hook #77 (`_HARNESS_DOWN_MARKERS`, marqueur
`build runner KO`) les a convertis en **ÉCHEC** ; #462 les a inventoriés le 2026-08-03. Reproduit
tel quel après correction, par la dérogation `DAMAGE_CATALOG_UNITS=adeptSmnGeminaeSuperia`.

### `adeptSmnGeminaeSuperia` est-elle récupérable ? Non — pas par CE harnais

Un summon est confrontable en général (on le fait apparaître par son summoner, #291). Mais
`replay_normal_attack` **PILOTE** l'attaquant : `applyAction move` puis attaque normale, et
`_do_replay` compare le dégât per-hit. Or le natif TERMINE le tour de toute unité qui apparaît
pendant le tour de son propriétaire (`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` →
`FinishUnitTurn(spawned, isTerminated: true)`) : un summon **s'observe, il ne se commande pas**.
S'ajoute que ses stats en bataille dérivent du summoner, donc l'unité mesurée ne serait plus
« ce kit au rank cible ». Le canal qui couvrirait les 14 summons + 57 npc du profil existe et il
est **NOMMÉ** : un mode de couverture séparé, qui rejoue les events du cast du summoner comme le
fait `probe_291_summon_activation.py`. Ce n'est pas `replay_normal_attack`.

---

## 2. Ce que le catalogue mesurait, et ce que l'échantillon préserve

Le fichier mesure une chose : l'attaque normale d'un profil d'arme **vanilla melee-multihit** est-
elle reproduite bit-exact, `spread → perçage/armure → multi-coups`. L'échantillon n'a donc de
valeur que par les **profils d'arme** qu'il couvre — et le tri alphabétique n'en couvrait aucun
(ses 4 têtes partageaient 2 valeurs de coups, et surtout aucune n'arrivait en bataille).

Catalogue **confrontable** = 6 unités, et leurs profils :

| unité | coups | perçage |
|---|---|---|
| `admecManipulus` | 2 | 30 |
| `astraCreed` | 2 | 10 |
| `genesMagus` | 2 | **100** |
| `tauDarkstrider` | 3 | 1 |
| `astraBullgryn` | 4 | 1 |
| `tauAunShi` | **5** | 40 |

Échantillon par défaut (N=4) : **un représentant par valeur de coups**, du plus petit au plus
grand, tie-break sur le perçage le plus **élevé**, puis `id` — soit `genesMagus` (2/100),
`tauDarkstrider` (3/1), `astraBullgryn` (4/1), `tauAunShi` (5/40). Il couvre **toutes** les
valeurs de coups disponibles (2..5) et les deux extrêmes de perçage (1 et 100, seul régime où
l'armure de la cible est annulée). `DAMAGE_CATALOG_N=0` joue les 6 (**31,6 s** mesurées).

**Ce que le catalogue PERD** : les 14 summons et 57 npc du profil (voie séparée, ci-dessus), et
3 `lineup` — `eldarLhykhis` (5 coups / perçage 60) et `thousSekhetar` (2/40), **absents du seed
BC** donc récupérables par injection catalogue (`catalog_inject.write_augmented_seed_bc` +
`build --seed-bc`) ; `necroPlasmancer` (2/65), **seul refus légitime** (`unspawnable_rank17` /
`UNSPAWNABLE_FALLBACK` : il passe la normalisation puis lève au spawn).

---

## 3. La gate est DÉRIVÉE, donc elle est GARDÉE

Le pool spawnable est une donnée **live** (`rl_duel build --list-pool` → RPC
`buildNormalizedBC`), et `_catalog_units()` tourne à la **collecte** — avant la fixture
`live_session`, donc avant l'amorce. Un RPC IL2CPP avant amorce, c'est le crash `0x2c`. La gate
est donc dérivée des **entrées versionnées**, en trois conditions dont chacune ferme une classe
mesurée :

* `kind == "lineup"` — écarte les 57 npc et 14 summons ;
* présent dans `BC.Units` de `data/seed-bc.json` — le pool en est un sous-ensemble **strict**
  (mesuré : `pool live − BC.Units = ∅`, 97/97) ;
* hors `rl_collect_batch._load_unspawnable(RANK)` — `necroPlasmancer`.

Et `test_derivation_du_pool_fidele` **confronte cette dérivation au pool RÉEL à chaque passe** :
une dérivation trop permissive se rattraperait en `build runner KO` (le rouge d'origine, qui
ressemble trait pour trait à un rouge de port — #462-r6) ; trop stricte, elle laisserait tomber
des profils d'arme **en silence**. Un garde-fou dont le verdict dérive ne vaut rien.

Fidélité vérifiée sur **4 ranks** (1, 10, 17, 20) : pool 97, `reel` 6, `derive == reel` partout.

---

## 4. Contre-épreuves (chacune a fait ROUGIR)

| mutation | rouge obtenu |
|---|---|
| gate permissive (`kind in ("lineup","summons")`) | `derives et hors pool: ['adeptSmnGeminaeSuperia', ...]` |
| gate stricte (`tauAunShi` ajouté aux unspawnable) | `au pool et non derives (profils perdus en silence): ['tauAunShi']` |
| commande de pool cassée | `--list-pool n'a rendu AUCUNE unite [...] (rc=2)` — `pytest.fail`, jamais un skip |
| dérogation `DAMAGE_CATALOG_UNITS=adeptSmnGeminaeSuperia` | le symptôme #462 **à l'identique** |
| seed du replay forcé à 31337 | le diagnostic overkill du §5 apparaît dans le message |

---

## 5. ~~Résidu~~ `#462-r4e-o` — le régime OVERKILL, trouvé en généralisant

> **FERMÉ le 2026-08-04** — la borne est portée : `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`.
> RE, confrontation et résidu `#462-r4e-o-r1` : **`case-462-r4e-o-amount-borne-aux-pv.md`**.
> Ce qui suit est le constat d'origine, conservé pour la trace de la mesure.

Le replay tourne sur UN couple (board, seed). En balayant 3 boards × 3 seeds, `astraBullgryn` vs
`eldarFarseer` diverge **sur le seul coup létal** :

```
MC1_67/31337  live=[1975, 1573, 2339, 1643]   off=[1975, 1573, 2339, 2404]
MC1_67/4242   live=[2373, 2125, 1764, 1268]   off=[2373, 2125, 1764, 1878]
C3_01/777     live=[2764, 3787,  979,    0]   off=[2764, 3787, 2289, 2203]
```

`sum(live)` vaut **7530 dans les trois cas** = les PV de la cible, et `hp_after` vaut **0 des deux
côtés**. Ce n'est donc **pas un trou de calcul** : l'état est identique, le natif **borne
`Amount` aux PV restants** et le port rend le dégât **brut**. Écart de RAPPORT per-hit, non porté
— un consommateur de ces montants (trace RL, utilité) lirait 8291 là où le natif écrit 7530.

Hors périmètre de ce cas (rouge de montage). `_diag_overkill` le **nomme dans le message
d'échec** pour qu'il ne se lise pas comme un trou du moteur de dégât — sans quoi il aurait
exactement la forme que #462-r6 dénonce. **Montage pour le reprendre** : `DAMAGE_CATALOG_UNITS=
astraBullgryn`, seed du replay 31337 ou 4242, board MC1_67, cible `eldarFarseer`.

---

## 6. Relevé de validation (2026-08-03)

* fichier : **5 passed** (4 unités + le garde de fidélité), 37,2 s ; `DAMAGE_CATALOG_N=0` :
  **7 passed**, 25,2 s — le catalogue confrontable **entier** est vert ;
* généralisation board/seed : 3 boards (`MC1_67`, `C4_09`, `C3_01`) × 3 seeds sur les 6 —
  seul écart trouvé = le régime overkill du §5, **aucun** écart de calcul ;
* fidélité de la gate : 4 ranks, 0 divergence ;
* 5 contre-épreuves, toutes rouges (§4) ;
* banque de cliquets : **36 cliquets, 35 verts**, mur 282 s — seul `probe_462` rouge sur
  l'attestation périmée du fichier touché, régénérée (`--run --since origin/master`, mur 23,7 s,
  `VERDICT: PASS`).

### Re-jeu APRÈS rebase — et ce que le rebase a apporté

Le rebase sur `origin/master` a amené **#462-r4a** (`ecc892cc`, « la face DÉFENSEUR entre dans la
MÊME chaîne %-list que l'attaquant »), qui touche `engine/runner/operations/damage.py`,
`engine/services/damage_modifiers.py`, `engine/services/damage_prediction.py`,
`engine/services/effect_bonus.py` — **exactement le chemin que ce catalogue mesure**. Le re-jeu
n'était donc pas une formalité :

* **5 passed** (136,6 s) et `DAMAGE_CATALOG_N=0` → **7 passed** (129,7 s) — les 6 profils d'arme
  restent bit-exacts à travers le changement de chaîne ;
* banque **VERTE, 36/36**, mur 378,4 s (session chargée — les murs se re-dérivent, ils ne se
  citent pas) ;
* conflit sur `scripts/ratchets-462-live-attestations.json` (le point de conflit connu, #462-r2)
  résolu **par RÉGÉNÉRATION** : un côté repris, puis `--run --since origin/master` rejoué (mur
  99,7 s, `VERDICT: PASS`). Jamais une fusion à la main.

**Non couvert** : les summons/npc du profil (canal nommé au §1) ; les 2 `lineup` hors seed BC
(injection catalogue, §2) ; le régime overkill (§5) ; le fichier reste mesuré sur **un** couple
(board, seed) par défaut — la généralisation ci-dessus est un relevé, pas un garde.
