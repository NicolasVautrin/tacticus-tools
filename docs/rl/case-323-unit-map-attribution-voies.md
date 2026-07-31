# case-323 — `unit_map find --ability` était aveugle à 3 voies d'attribution sur 5

**Critère** : `unit_map find --ability` remonte-t-il TOUTES les voies par lesquelles une unité peut
porter une ability — et combien de verdicts « 0 porteur » déjà rendus sont FAUX ?

**Réponse, mesurée** : il en lisait **2 sur 5**. Les 3 manquantes (`relicAbilities`,
`mythicAbilities`, relique ÉQUIPABLE `items[*].abilityId` + `allowedUnits`) rendaient **42
abilities** invisibles, dont **34 ont un porteur héros/MoW dans le pool** et **3 sont portées
ÉQUIPÉES dès le seed BC courant**. Le re-balayage de `docs/rl/` trouve **7 verdicts « 0 porteur /
non pertinent » FAUX**, sur **5 abilities distinctes**, dans **6 fiches** — plus **2 chiffres** à
corriger. **9 verdicts de contrôle TIENNENT** sous l'index complet : le correctif ne retourne que
ce qui était réellement aveugle.

Re-dérivation : `python scripts/python/probe_323_ability_carrier_voies.py [--pool]`
(volets A–D 100 % offline ; le volet E interroge `rl_duel build --list-pool`, un RPC, pas un runner).
Garde : `scripts/python/tests/test_323_unit_map_voies_offline.py`.

---

## 1. Pourquoi ce cas n'est pas un cas d'outillage

`unit_map` est l'**outil de recensement**. C'est lui qu'on interroge pour répondre à
« qui porte cette ability ? », donc lui qui alimente la gate de confrontabilité du `CLAUDE.md` et,
en bout de chaîne, les verdicts *dead-code* / *non pertinent* qui **ferment un résidu**.

Un outil de recensement aveugle à une voie ne se trompe pas : il **atteste**. Son zéro se lit comme
une preuve, et rien en aval ne le contredit. C'est exactement la faute que le dépôt dénonce partout
— classer par un instrument aveugle à un canal — mais appliquée à l'instrument qui sert à classer.
Le précédent est nommé et mesuré : `docs/rl/case-317-repair-callers-inventory.md` §1, où #310 avait
classé l'`EffectType` 1456 `NetherRealmCasket_LivingMetalBonus` **DEAD, 0 porteur au gameconfig**,
sur la foi de `unit_map.py find --ability NetherRealmCasket` → « 0 unité ».

## 2. Les 5 voies COUVERTES, et les 4 qui ne le seront pas

Mesuré sur le gameconfig du build `rnca9r7q6c` (`probe_323` volet A) :

| voie | source gameconfig | unités | abilities |
|---|---|---:|---:|
| `active` | `units.<kind>.<id>.activeAbilities` | 516 | 175 |
| `passive` | `units.<kind>.<id>.passiveAbilities` | 591 | 211 |
| `relic` | `units.<kind>.<id>.relicAbilities` | 191 | 25 |
| `mythic` | `units.<kind>.<id>.mythicAbilities` | 22 | 11 |
| `item` | `items[*].abilityId` + `items[*].allowedUnits` | 65 | 32 |

`unit_map` ne lisait que les **deux premières**. Les trois autres sont désormais indexées,
et `find --ability` affiche par quelle voie chaque porteur l'obtient (`voie:item`, `voie:relic`…) —
la distinction est décisive : `voie:item` signifie « la fiche d'unité ne la mentionne nulle part,
elle arrive par un équipement ».

**NON couvertes — assumé, documenté, imprimé** (aucune n'est dérivable du gameconfig seul) :

| voie | pourquoi elle est hors de portée | où chercher à la place |
|---|---|---|
| `trait` | le mapping trait → ability vit dans le **natif** (`Mechanic` → `ActiveAbilityType` 28 `Repair` ; `LivingMetal` → `TriggeredAbilityType` 1010) ; aucune entrée `units.*Abilities` | `find --trait <T>` |
| `liveevent` | les `Enhancement*` d'un `liveEvents.idunLiveEventConfigs[].enhancements` : accordées hors bataille régulière | mirror offline seulement |
| `summon` | un summon porte SON kit ; il n'apparaît pas sur son summoner | chercher le summon, remonter au summoner |
| `tile` | les `PowerUp_*` sont posés par le BOARD | `board.py` / dump du board |

**Le dispositif qui empêche la rechute** : quand `find --ability` rend 0, il n'imprime plus un zéro
nu — il imprime les 4 voies non couvertes et la phrase
`CE ZERO NE PROUVE PAS QUE L'ABILITY EST MORTE`. Une couverture partielle **assumée** vaut mille
fois mieux qu'une couverture partielle silencieuse ; c'est cette ligne, pas l'index, qui aurait
sauvé #310.

## 3. Le gisement — 42 abilities invisibles

`probe_323` volet B : catalogue = 572 abilities ; visibles par l'ancienne lecture = 386 ;
**invisibles = 42** (31 par la voie relique, 11 par la voie mythique — `Maugetar` est la seule
relique déjà visible, un npc la porte en `activeAbilities`).

Ventilé contre le pool (volet E, rank 17, **105 unités spawnables**) :

* **34 / 42** ont un porteur `lineup` **DANS LE POOL** → un « 0 porteur » sur elles était un faux
  négatif à conséquence directe ;
* **3** sont **ÉQUIPÉES dès le seed BC** (`BC.Units[].TertiaryAbility`), donc confrontables
  aujourd'hui, sans injection : `NetherRealmCasket` (1462, `necroSpyder`), `KardiocoreGalvanus`
  (1457, `admecMarshall` + `admecRuststalker`), `SupaCyborkBody` (1475, `orksRuntherd`) — et les
  4 porteurs sont dans le pool ;
* **8** ont leur porteur hors pool (`tauFarsight`, `votanUthar`, `spaceWolfPriest`,
  `necroReanimator`, `adeptCelestine`, `thousDaemonPrince`, `darkaStormSpeeder`,
  `votanIronmaster`) → **injectables** (`case-92-catalog-injection.md` §6), pas « non
  confrontables ».

⚠ **Qualifier l'enum est obligatoire ici** — trois ids voisins, trois enums :
`TriggeredAbilityType` 1462 = `NetherRealmCasket` (c'est la valeur écrite dans
`BC.Units[].TertiaryAbility`) ; `EffectType` 1462 = `TheArdentBlade` ; et l'effet mort-à-tort de
#310 est l'`EffectType` **1456** `NetherRealmCasket_LivingMetalBonus`. De même
`TriggeredAbilityType` 1475 = `SupaCyborkBody` alors que l'`EffectType` 1475 = `FragLance`.

## 4. Le re-balayage — 7 verdicts FAUX

`probe_323` volet C : **327 fiches, 86 894 lignes, 139 lignes portant un verdict « zéro »**,
**17 signalements** (fenêtre de ±3 lignes autour du verdict). Adjugés un par un :

| fiche | verdict écrit | mesure #323 | statut |
|---|---|---|---|
| `case-310-living-metal-repair.md` §? (l. 111 et 218) | « `find --ability NetherRealmCasket` rend **0 unité** → l'effet 1456 est DEAD » | 18 porteurs ; 3 héros du pool ; `necroSpyder` l'a ÉQUIPÉE | **FAUX** |
| `case-313-enum-mirror-bijection.md` §7 (1557) | `PhasalSubjugator` : « aucune unité ; contenu non encore attribué » | `necroOverlord` (**pool**, `R_Booster_Crit_PhasalSubjugator`) + 5 npc `relicAbilities` | **FAUX** |
| `case-313-enum-mirror-bijection.md` §7 (1558) | `Helspear` : « aucune unité » | `blackHaarken` (**pool**, `R_Crit_Helspear`) + 5 npc | **FAUX** |
| `case-318-effect-utility-mirror-bijection.md` §6 (1583) | `Helspear` : « **aucune unité** — kit livré en avance » | idem | **FAUX** |
| `case-225-dynamic-trait-gates.md` §1 | `SupaCyborkBody` : « la seed BC courante n'en pose pas → **non confronté** » | `orksRuntherd` porte `TertiaryAbility = 1475 = SupaCyborkBody` **dans le seed**, et il est **dans le pool** | **FAUX** |
| `case-ischarging-hits-channel.md` §4 + §3 (1478) | `SabreOfSacrifice` : « **NON — npc + relique** » ; « `astraDreir` (le héros du pool) ne l'a **pas** » | `astraDreir` est le SEUL `allowedUnits` de `R_Crit_SabreOfSacrifice`, et il **est dans le pool** | **FAUX** |
| `port-residuals-inventory.md` N16 | « 2 NON PERTINENTS (… #15 `SabreOfSacrifice` npc+relique) » | idem — écho du précédent | **FAUX** |

**Chiffres à corriger** (pas des verdicts, mais des mesures fausses) :

* `port-residuals-inventory.md` **N317-c** annonce « **25** relic-abilities » → la mesure est
  **42** (25 `relicAbilities` − 1 déjà visible + 7 item-seules + 11 `mythicAbilities`) ;
* `backlog.md` (`NetherRealmCasketPlaybook`) écrit « tout porteur de la relique (**4 unités** au
  seed BC) » → **1 seule** unité porte 1462 au seed (`necroSpyder`) ; les 4 portent **une** relique,
  pas **cette** relique.

**Contrôles négatifs — 9 verdicts qui TIENNENT** sous l'index complet (0 porteur sur les 5 voies) :
`ObeisanceGenerators`, `MassHeal`, `SpikySting`, `LandMine`, `PriorityReclamation`, `ProperKilly`,
`ATemptingTrap`, `EnhancementRegeneration`, `EnhancementLifeSteal`. Sans ces contrôles, un
`carrier_voies` devenu permissif ferait passer toute la garde au vert en rendant l'outil inutile
dans l'autre sens — c'est ce que garde `test_control_une_ability_sans_aucun_porteur_reste_a_zero`.

### Ce que le re-balayage ne prouve PAS

Le volet C lit de la **prose**, pas une structure : il signale des CANDIDATS, l'adjudication est
manuelle (table ci-dessus). Deux angles morts assumés : un verdict qui ne nomme pas l'ability à
moins de 3 lignes n'est pas vu, et une fiche qui parle d'un **effet** (`…_ExtraDmg`) sans nommer
l'**ability** qui le pose ne l'est pas non plus. Le compte de 7 est donc un **plancher**.

## 5. La gate de confrontabilité du `CLAUDE.md` — le trou est ailleurs

`rl_duel build --list-pool` **n'est pas** aveugle aux reliques à la manière de `unit_map` : il
répond à une autre question (quels `unitId` normalisent au rank cible), et la mesure le confirme —
les **56** unités du seed éligibles à une relique sont **toutes** dans le pool, et les **4** qui en
portent une équipée aussi.

Son vrai angle mort est plus fin, et il est symétrique : **« dans le pool » ne dit pas « arrive en
bataille AVEC sa relique »**. 52 des 56 éligibles y arrivent sans. Une gate passée sur le seul pool
ne suffit donc pas à conclure qu'une ability de RELIQUE est exercée — il faut lire
`BC.Units[].TertiaryAbility`.

Ce que la mesure établit par ailleurs, et qui contredit « `rl_duel.py` ne monte aucun équipement,
l'item est hors du harnais » (`case-ischarging-hits-channel` §4) : le seed BC **porte déjà** 4
reliques équipées, et la normalisation les **préserve** —
`frida/hooks/features/normalize-bc/json-build.ts` ne touche à `TertiaryAbility` que pour lui poser
son `TertiaryAbilityLevel` au niveau cible. Une relique traverse donc `buildNormalizedBC` intacte.
⚠ Ce qui reste NON mesuré ici : que le rail COMBAT du **port** instancie la triggered-ability
correspondante — c'est le résidu N317-a, que cette fiche ne referme pas. **Fermé depuis par #357**
(`case-357-rail-relique-equipee.md`), et confronté live sur `DawnBlade`.

**Règle qui en sort** : pour une ability de relique, ventiler en TROIS états, jamais deux —
`équipée au seed` (confrontable tout de suite) / `porteur au pool, relique non équipée` (montage à
écrire : poser `TertiaryAbility`) / `porteur hors pool` (injection catalogue). « Non confrontable »
n'est aucun des trois.

> **Suite — le montage de l'état 2 EXISTE depuis #237** (`docs/rl/case-237-relique-forcee.md`) :
> `rl_duel build --equip-relic "<unitId>:<Ability>[:level]"`. « Poser `TertiaryAbility` » était
> **incomplet** : il faut TROIS écritures, et le champ seul ne produit rien — la config d'ability
> (**29 des 32** absentes du seed) et surtout **`TertiaryAbilityLevel >= 1`**
> (`Idun.Shared.Level$$ToZeroBasedIndex` lève sur `<= 0`, et `0` est ce que porte toute entrée sans
> relique). Le compte de l'état 3, re-dérivé : **9** porteurs hors catalogue.

## 6. Le correctif et sa garde

`scripts/python/unit_map.py` :

* `UNIT_ABILITY_FIELDS` / `VOIE_KEYS` / `VOIES_NON_COUVERTES` — les voies, nommées et énumérables ;
* `_relic_items()` — index `{unitId: [(abilityId, itemId)]}` de la relique ÉQUIPABLE ;
* `kit()` porte désormais `voies`, `relic_items`, `abilities_all` (`abilities` reste l'union
  active+passive, pour ne pas déplacer le sens des appelants existants) ;
* `carrier_voies(kit, needle)` — par QUELLES voies cette unité la porte ;
* `find --ability` interroge les 5 voies, affiche `voie:` par ligne, accepte `--ability-voie` pour
  isoler une voie, et **imprime le pied de page anti-faux-verdict** sur un zéro ;
* `voies [--ability X]` — la table de couverture, à l'écran.

**Effet de bord ASSUMÉ** (volet D) : la classification `mech` balaie maintenant toutes les voies —
une relique de crit (`R_Booster_Crit_*`) est un modificateur de dégât aussi réel qu'un passif.
`vanilla-target` passe de **269 à 232** : **37 unités** en sortent, dont `necroWarden`,
`necroDestroyer`, `genesPrimus`, `astarCyrus`… Elles n'ont **jamais** été des cibles vanille ;
elles le paraissaient parce que leur modificateur arrivait par une voie non lue.

Garde : `tests/test_323_unit_map_voies_offline.py`, 7 tests, cas NOMMÉ = **1462 / `necroSpyder`**.
Vue ROUGE avant vert sur **5 mutations** (`logs/mutate_323.py`, harnais jetable) : retirer `item` de
`VOIE_KEYS` (2 rouges), neutraliser `_relic_items()` (3 rouges), retirer `relic` puis `mythic` de
`UNIT_ABILITY_FIELDS` (1 rouge chacune), supprimer le pied de page (1 rouge). Message verbatim du
cas nommé :

```
AssertionError: REGRESSION #323 : `necroSpyder` ne porte plus `NetherRealmCasket` par AUCUNE voie.
C'est exactement l'etat qui a fait classer l'effet 1456 `NetherRealmCasket_LivingMetalBonus` en
DEAD (#310) : l'outil de recensement etait aveugle a la RELIQUE. La voie attendue est `item`
(items/R_Booster_Crit_NetherRealmCasket.allowedUnits contient necroSpyder).
```

## 7. Ce qui n'est PAS couvert

* **Aucune confrontation live d'une ability de relique** : la tâche est offline. Ce qui est prouvé,
  c'est que l'outil **voit** les porteurs et que le seed en **équipe** 3 abilities sur des unités du
  pool — pas qu'une relique produise son effet dans le rail COMBAT porté (N317-a). **La
  confrontation existe depuis #357** (`DawnBlade`, natif == port == `hpToHeal[niveau]`), sur UNE
  relique des 32.
* **Les 4 voies non couvertes restent non couvertes** : c'est un choix, pas un oubli. La voie
  `trait` en particulier demanderait le mapping natif trait → ability, qui n'est nulle part dans le
  gameconfig.
* **Le compte de 7 verdicts faux est un plancher** (§4, angles morts du scan de prose).
* **Les 8 abilities du gisement dont le porteur est hors pool** n'ont pas été injectées : leur
  confrontabilité par `catalog_inject` est affirmée par doctrine, pas mesurée ici.
