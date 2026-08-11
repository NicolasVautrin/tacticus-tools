# #914 — Les trois rouges de `master` : deux montages qui ne mordaient plus, et un compte à rebours déguisé en seuil

Mesures du 2026-08-11, `4c8f81d8` puis `84f76b55` :

| fichier | avant | après |
|---|---|---|
| `test_hailstrike_phase2_live.py` + `test_576_blood_chalice_live.py` | 2 failed, 13 passed | **15 passed** |
| `test_path_of_command_crit_aura_live.py` (#912) | 1 failed, 4 passed | **5 passed** |

**Aucun code de moteur n'a changé.** Les trois rouges accusaient le port ; aucun des trois ne venait
de lui. C'est le point commun — et **deux d'entre eux ont la MÊME cause racine** : la bascule
**#419-r5/#419-r6**, qui équipe les items Best-In-Slot **par défaut** et a ouvert le canal crit
(`could_crit` **0/106 → 98/106**). Deux montages écrits avant elle reposaient sur « le crit est
impossible » / « la normalisation met la crit à 0 » — des propriétés du **HARNAIS**, devenues fausses
sans qu'une ligne de test ni de port ne bouge.

---

## 1. `test_hailstrike_pierce_envelope_live` — le montant live comparé HORS de son régime

Symptôme : `degat live 2856 hors des bornes du port AVEC le bonus [1800, 2701] -- la magnitude du
percage portee est fausse`.

### 1.1 Décomposition par étage (`probe_914_hailstrike_enveloppe.py`)

Le probe monte le régime de la fixture `hailstrike_armor` et imprime, tir par tir, l'entrée et la
sortie de chaque étage. Les **six premiers tirs** de la série sont sans appel :

| tir | port `total` | live `Amount` | `DidCrit` | `WasOverkill` | dans `[1800, 2701]` |
|---|---|---|---|---|---|
| 0..4 | 2617 / 2246 / 2484 / 2445 / 2448 | idem | 0 | 0 | oui |
| 5 | 5009 | **2856** | **1** | **1** | non |

Étages, identiques sur les six tirs : `pierce_sans_bonus 65` (profil `Plasma`) + `effect_bonus 15`
(`extraPierceRatio[L50]`) = `pierce 80`, `attack_stat 2813`, `armor_fixed 4821`,
`clean_min/clean_max = [1800, 2701]`. **Rien ne diverge.** Le tir 5 n'appartient tout simplement pas
à l'ensemble que ces bornes décrivent, et deux raisons indépendantes l'en sortent :

* `clean_min`/`clean_max` sont la plage **NON-CRIT** (`hit_nc.min/max × hits`,
  `engine/runner/operations/damage_ops/normal.py`) — le natif dit `Attack_DidCrit: 1` ;
* `Amount` est le dégât **APPLIQUÉ** — sur `Attack_WasOverkill: 1` c'est **les PV restants**, pas le
  dégât calculé (`UnitStats_RemainingHealth: 0`). Le port, lui, rend son 5009 calculé.

### 1.2 Les deux dérives de MONTAGE, et pourquoi elles étaient invisibles

**(i) Le patch de PV était INOPÉRANT.** `_build` (et `probe_123.ensure_seed_bc`) écrivait
`Health = 900000` dans le **seed BC**. `buildNormalizedBC` **RECALCULE** `Health` au rank cible :
mesuré, la cible arrivait à **~9539 PV**, et le probe l'annonçait pourtant
(`[bc] astraBullgryn : PV portes a 900000`) — un montage qui ment dans son propre `print`. La cible
mourait donc au 4ᵉ tir de la série. Le seul levier qui mord est celui appliqué au BC **déjà
normalisé** : `--unit-stat "astraBullgryn:Health=…,RemainingHealth=…"` (c'est aussi pourquoi
`--hp-target`, lui, fonctionne — il patche au même endroit).

**(ii) Le crit est devenu POSSIBLE sous les pieds du test.** Quand #123 a écrit cette enveloppe,
`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` (`GetStat(9) > 0 && GetStat(10) > 0`) était
**FAUX pour toute unité** : les quatre stats crit/block ne vivent que dans les items, et aucun
n'était équipé. **#419-r6** a fait de l'équipement BiS le **DÉFAUT** (`could_crit 0/106 → 98/106`).
L'enveloppe non-crit encadrait tous les tirs *par construction* ; elle a cessé de le faire sans
qu'une seule ligne du test ni du port ne bouge.

### 1.3 Réparation

Le montage **ÉTABLIT** le régime, le test **EXIGE** que le natif le confirme :

* PV par `--unit-stat` (BC normalisé) — mesuré `hp_cible = 900000`, la cible survit aux 6 tirs ;
* `--crit 0,0` et `--block-target 0,0` — les deux canaux **orthogonaux** au perçage, et eux seuls.
  Ce n'est **pas** `--no-bis-items`, qui déshabillerait le héros entier (« un héros rank 17 sans
  aucun item n'existe pas dans le jeu ») ;
* étage (0) neuf dans le test : les quatre drapeaux `Attack_DidCrit` / `DidBlock` / `DidEvade` /
  `WasOverkill` doivent être nuls, **avant** toute comparaison de magnitude. Si ce rouge-là
  apparaît, c'est le **levier** qui ne mord plus — pas le port. Le message le dit.

Aucune borne n'a été relâchée.

**Le régime restauré rend la série de #123 à l'unité près** : `1921, 2422, 2700, 2015, 2445, 2153`
(cf. `case-117` §5bis), et le port les reproduit **bit-exact 6/6** — la bit-exactitude sous armure,
résidu §5ter fermé par #131, est donc re-confirmée. Discrimination intacte : sans le bonus, les
bornes tombent à `[1462, 2194]` et trois tirs live en sortent.

### 1.4 Contre-épreuve : ce rouge est INDÉPENDANT de `#910`

Le probe re-joué avec `engine/runner/abilities/base.py` et `entities/effects/factory.py` **restaurés
à `f3c2812f`** (le commit qui précède `4c8f81d8`) rend des étages **strictement identiques** —
`65 / 15 / 80`, `attack_stat 2813`, `armor 4821`, `[1800, 2701]` — et les mêmes totaux au PV près.
La réparation du canal perçage de #910 (`entity_trait_names`, `tertiary_ability_state_of`) ne touche
ni `target_traits` ni l'état d'ability de `Hailstrike_ExtraPierce`, dont le seul gate est
`get_OwnerIsCaster & (IsRangedAttack | IsOverwatchAttack)`. **Les bornes sont les mêmes avant et
après** : issue « le rouge est bien indépendant ».

---

## 2. `test_576::test_le_cablage_du_registre_est_complet` — `assert 7 > 10`

`assert len(TARGETING_OPTIONS_UNPORTED) > 10` et `assert len(DYNAMIC_TARGET_RULE_UNPORTED) >= 1`
gardaient « le retrait des deux tables est CIBLÉ, pas un effacement ».

Ce n'est **pas** un chiffre périmé : la propriété était fausse dès l'écriture. Ces tables **FONDENT
par construction** — toute face COMBAT portée en retire sa ligne, le contrat de disjonction l'exige,
et **quinze** entrées sont sorties depuis #487. Un seuil posé dessus est un **compte à rebours** : il
passe de vrai à faux sans qu'aucune propriété gardée n'ait changé. Le descendre le ferait retomber ;
le re-dériver *dans un test* le périmerait au même rythme — un compte écrit à la main dans cette
table précise a déjà été faux **quatre fois en un jour** (#519).

Remplacé par deux invariants, tous deux locaux à ce que #576 a fait :

* `targeting_options_for(1175) is opts` — la source **EFFECTIVE** du masque est la CLASSE. Le
  résolveur consulte la classe puis la table : cette identité dit ce qu'un compte ne disait pas, que
  le masque relu est bien celui qui **sert** ;
* `"get_dynamic_invalid_target_reason" in vars(cls)` — la règle dynamique est **surchargée**, pas
  héritée. `hasattr` restait vrai même si la surcharge disparaissait (la base porte un défaut
  permissif qui rend `0`) : c'est ce qui **autorise** la sortie de `DYNAMIC_TARGET_RULE_UNPORTED`.

L'anti-effacement, lui, existe déjà **dérivé du code** au lieu d'être écrit :
`probe_519_comptes_de_table.py` recompte la table par ses marqueurs `@FORME`, et
`tests/engine/test_519_comptes_derives_offline.py` exige que le bloc généré soit à jour **et** que la
dérivation « mesure quelque chose » (`total > 0`, bloc et hors-bloc non vides). La disjonction est
tenue globalement par `test_targeting_options_sources.py`.

---

## 3. `test_path_of_command_crit_aura_live::test_crit_gate_bites_and_is_not_distance` (#912)

Symptôme : `allie a portee SANS chance de crit qui recoit du crit (live 20, port 55) -> le noeud
UnitsWithStatBiggerThan ne mord pas`, `assert (20 == 0)`.

### 3.1 Le chiffre, lu avant d'accuser

`live 20` est un **DELTA** (`statDelta.critChance`) ; `port 55` est une valeur **ABSOLUE**
(`sc.ctx.stat(CRIT_CHANCE)`). L'assertion opposait deux grandeurs différentes — d'où la lecture
« un troisième chiffre, les deux côtés divergent entre eux » consignée au backlog, qui est fausse :
`35 (base) + 20 (bonus) = 55` est un **accord parfait** entre le natif et le port.

### 3.2 La prémisse, mesurée (`probe_912_crit_zero_porteur.py`)

Le montage prend `eldarFarseer` pour l'allié « sans crit », sur la prémisse écrite « la normalisation
la met à 0 ». Trois bras sur le montage EXACT du test :

| bras | régime | `eldarFarseer.critChance` de base | prémisse |
|---|---|---|---|
| A | courant (BiS équipés, défaut) | **35** | **FAUSSE** |
| B | `TACTICUS_BIS_ITEMS=0` (témoin d'avant #419-r5) | 0 | tenue |
| C | courant + `--unit-stat eldarFarseer:CritChance=0` | **0** (et `critDamage` intact à 1561) | tenue |

Le gate natif **mord parfaitement** : il sélectionne un allié qui a *réellement* de la chance de
crit. Le test avait cessé de lui présenter le porteur qu'il croyait.

### 3.3 Réparation

* **Bras C** au montage : le porteur « sans crit » se **construit** (`--unit-stat …:CritChance=0`),
  il ne se suppose plus. Pas `TACTICUS_BIS_ITEMS=0`, qui déshabillerait le roster entier.
* **La prémisse devient une assertion** : `pre[flat]["cc"] == 0`, lue **avant** l'atterrissage
  (l'Autarch est encore en teleport-in, passives déférées). Contre-épreuve exécutée — levier retiré,
  le test rougit sur *cette* assertion et son message nomme le levier, au lieu d'accuser le nœud.
* **Les grandeurs sont appariées** : delta live ↔ part **attribuée** à l'entité-effet (`_attr`),
  absolu ↔ absolu. La même faute frappait une **seconde** assertion — `off[carrier]["cc"] == 0` sur
  le PORTEUR, qui a lui aussi 35 de crit de base : elle accusait `SurroundingFriends` de self-buff
  pour une stat que l'aura n'a jamais touchée (delta live et part attribuée sont bien nuls).

Aucune assertion n'a été relâchée ; le fichier passe de 4 à **5** tests verts et gagne un cran.

---

## 4. Portée, et ce qui n'est PAS couvert

**Le gisement « enveloppe non-crit assertée » est-il plus large ?** Balayé : non. Les autres
consommateurs de `clean_min`/`clean_max` **écartent** déjà les coups sales
(`_pierce_floor_regime.py`, `test_heavy_grav_cannon_live`, `test_flail_swing_live`,
`test_wireweave_net_counter_live`, `test_runner_attack_live` …) ; `test_hailstrike_phase2_live` était
le seul à en faire une **assertion**, parce qu'il a été écrit avant que le crit soit possible.
⚠ `test_runner_attack_live` reste le seul à dériver « coup propre » de l'appartenance à la plage
plutôt que des tags natifs — c'est un **filtre**, donc sans danger de faux rouge, mais c'est le
raisonnement inverse (on déduit le régime du résultat).

**Le montage inopérant** a été corrigé dans ses **deux** foyers jumeaux (`probe_123`, `probe_131` —
qui partagent jusqu'au fichier de cache du seed BC). Ce qui reste ouvert : **rien ne signale** qu'un
champ de `BC.Units[]` recalculé par `buildNormalizedBC` a été patché en amont. `rl_duel` sait déjà
émettre ce genre d'avertissement (`--unit-stat … Shield=…` → `[warn]`) ; ici il n'y a personne pour
le dire, et le silence a coûté un rouge. → résidu **`#914-r1`**.

**Non mesuré** : le régime OVERWATCH du bonus (déjà `NON CONFRONTÉ` depuis #123), et la face
DÉCISION du canal perçage (résidu `#910-r1`, foyer partagé — non touché ici).

### 4.1 Le motif, et pourquoi il va récidiver

Deux des trois rouges viennent d'une **bascule de harnais** qui a invalidé une prémisse **écrite en
commentaire** — « le crit est structurellement impossible », « la normalisation met la crit à 0 ».
Ces deux phrases étaient **vraies** le jour où elles ont été écrites. Rien ne les a confrontées au
harnais depuis, parce qu'une prémisse en commentaire n'est **pas exécutable** : la seule chose qui
l'a signalée, c'est un test qui rougit des mois plus tard **en accusant le port**.

Les deux réparations posent le même cran, et c'est le seul qui tienne : **la prémisse devient une
assertion mesurée sur l'état live**, avec un message qui désigne le **levier de montage**, pas la
mécanique. Le reste du dépôt applique déjà ce réflexe pour les coups sales (`dirty = DidCrit or
DidBlock or DidEvade`, cinq fichiers) ; il ne l'appliquait nulle part aux **stats de base**.

⚠ Le gisement n'est pas refermé : toute prémisse de la forme « la normalisation met X à 0 » écrite
avant #419-r5 est suspecte. Recensement et cliquet → résidu **`#914-r2`**.
