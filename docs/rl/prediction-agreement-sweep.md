# Balayage d'agrement PREDICTION : moteur <-> oracle live per-ability (`aiPlaybookPredict`)

Build `gqfc5mff6c`. Outil : `scripts/python/predict_sweep.py`. Objectif : produire une CARTE
priorisee des ecarts entre la prediction offline du moteur (`engine.playbook.prediction`) et
l'oracle natif DIRECT du playbook per-ability (RPC `aiPlaybookPredict` = `<Ability>Playbook.
MakeDamagePredictions`, #102). READ-ONLY : l'outil ne corrige rien, il mesure et bucketise.

GREP ce fichier avant de re-investiguer un ecart de prediction : les PIEGES d'alignement
ci-dessous ont deja coute plusieurs faux MAJOR.

## Pourquoi cet oracle (et pas `aiPredict`)

`aiPredict` = `DamagePredictionQuery.GetAllPredictions` = le PREVIEW decisionView, **Attack-based
quel que soit l'abilityType** -> il rend la valeur de l'attaque NORMALE meme pour un special
config-based (PlasmaCannon/SpiritLeech). Faux oracle pour les specials (piege #96).

`aiPlaybookPredict` (#102) invoque le VRAI `<Ability>Playbook.MakeDamagePredictions` natif ->
la liste de `ProbableDamageEvent` que l'IA score reellement. C'est l'homologue exact de la
fonction Python `prediction.make_damage_predictions` (et `make_normal_attack_predictions` pour
le playbook de l'attaque normale). Comparaison apples-to-apples : meme fonction native, meme struct.

Depuis #103, `decisionView.attackPlans[].evals[].ranked[].dmgMin/Max` (le DISPLAY) route AUSSI
par `MakeDamagePredictions` pour les actives -> le display sert de sanity-check tiers (`disp`).
Attention : si le decode `MakeDamagePredictions` echoue, le display RETOMBE sur GetAllPredictions
(preview Attack-based) -> `disp` peut alors diverger de l'oracle playbook (cf. ORACLE_FAIL).

## Ce que compare le harnais

Pour chaque triple **(attaquant, ability de DEGAT, cible)** que le natif a score
(`attackPlans.evals` avec `ranked[0].dmgMax != None`), a **position COURANTE** des deux cotes :

- MOTEUR : `make_normal_attack_predictions` (kind==normal) / `make_damage_predictions`
  (actives/granted) -> event de la cible principale -> `accurate_health_damage.min/max`.
- ORACLE : `aiPlaybookPredict(unitId, targetId, abilityType)` -> event cible principale ->
  `healthDmgMin/Max`.

`ability_name` = `gameconfig.ability_name(id)`. `kind` = `decisionView.units[].abilities[].kind`.

## PIEGES D'ALIGNEMENT (hard-won ; ne pas les reintroduire)

L'oracle `aiPlaybookPredict` predit depuis la **tuile COURANTE** avec l'**etat de tour REEL** de
l'unite (HasMoved, MP). Pour une comparaison SANS artefact, le moteur doit etre evalue dans le
MEME etat. Deux pieges rencontres et resolus :

1. **Positionnel (hors-portee)** — apres le drive au contact, une melee n'est pas encore adjacente ;
   depuis la tuile courante l'oracle rend `[0,0]` (ability non applicable ICI) alors que le moteur
   calcule quand meme -> faux MAJOR. FIX : (a) `classify` renvoie `OUT_OF_RANGE` quand l'oracle
   rend `[0,0]` (exclu des buckets de gap) ; (b) COMMIT-BEST-MOVE : on bouge chaque attaquant sur
   sa meilleure tuile d'attaque (max `dmgMax` de ses evals) pour qu'il predise du degat reel.

2. **`has_moved` (le plus vicieux)** — le moteur derive `has_moved` de `attack_pos != pos_courante`.
   Apres le commit-move, l'unite a **physiquement bouge** (HasMoved=True cote natif -> le natif EXCLUT
   les bonus NOT-MOVED, ex. **HeavyWeapon +25% ranged not-moved**), mais comme on predit depuis la
   tuile courante (`attack_pos == pos`), le moteur croit "not-moved" et APPLIQUE le bonus ->
   SUR-prediction uniforme (~x1.25 sur ranged). Symptome : `disp == live` (le display, evalue a la
   tuile de MOVE avec has_moved correct, matche l'oracle) mais `eng` haut, sur des abilities RANGED.
   FIX : **CYCLE-TOUR** apres le commit-move (`endturn` -> ennemi -> `endturn` -> moi) qui RESET
   HasMoved a False tout en gardant les positions avancees. Etat compare = "debut de tour, unite en
   portee, attaque SANS bouger" -> `_hm=False` cote moteur ET HasMoved=False cote natif = aligne
   (le bonus not-moved s'applique des DEUX cotes, correctement).

   VALIDATION du fix (seed 777) : PlasmaCannon (darkaTerminator) passe de 4 MAJOR (`eng x1.25`) a
   **5 OK** apres le cycle. Preuve que le +25% etait bien l'artefact has_moved, pas un gap de formule.

## Classification (`classify`)

| statut         | condition | interpretation |
|----------------|-----------|----------------|
| `OK`           | \|eng-live\| <= 3 (min ET max) | agrement (arrondi //100 vs Fix64) |
| `MINOR`        | ratio dans [0.90, 1.10] | ecart mineur (arrondi/borderline) |
| `MAJOR`        | hors [0.90, 1.10] | **ecart de formule reel** |
| `ENG_ZERO`     | eng=[0,0], live>0 | moteur ne predit AUCUN degat (trou de port) |
| `ENG_NONE`     | natif predit du degat, moteur ne produit aucun event | ability non reconnue degat par le moteur |
| `ORACLE_FAIL`  | RPC oracle echoue / decode -1, moteur produit une valeur | trou de DECODAGE `aiPlaybookPredict` (4e type de retour ?) OU non-degat |
| `OUT_OF_RANGE` | oracle=[0,0] | artefact positionnel (exclu des gaps) |
| `NON_DAMAGE`   | les DEUX cotes sans event | buff/self/ally-targeted mal ranke (hors scope degat) |

Buckets = `(ability, kind, retClass)`, tries par `#MAJOR/ENG_ZERO/ENG_NONE` desc.

## Usage

```
# une seed
python predict_sweep.py --seed 777 --max-turns 6 --json out.json
# carte multi-roster agregee (build/dispose isole par seed)
python predict_sweep.py --seeds 777,31337,42,7,2024,100,13,999 --json map.json
# roster crafte (garantit la couverture de porteurs de specials)
python predict_sweep.py --seed 777 --p-units tyranNeurothrope,custoBladeChampion,darkaTerminator,admecDominus,darkaAzrael
# runner existant (ne build/dispose rien)
python predict_sweep.py --runner 12
```

Pre-requis : session Frida chaude (amorce apres chaque reinject). Le harnais build+dispose son
propre runner (state-file dedie `logs/runners/_predict_sweep.json`, coexistence) -- ne touche pas au runner
utilisateur. Le drive/commit-move/cycle mutent le runner ISOLE uniquement.

## Carte des ecarts (run propre 2026-07-11, post-fix-cycle)

Run : `--seeds 777,31337,42,7,2024,100,13,999` (179 triples) + `--p-units tyranNeurothrope,
custoBladeChampion,darkaTerminator,admecDominus,darkaAzrael` (20 triples).

Bilan multi-seed : **OK=52, MINOR=14, MAJOR=11, ORACLE_FAIL=22, OUT_OF_RANGE=58, NON_DAMAGE=22**.
-> sur le mesurable (OK+MINOR+MAJOR = 77), **66/77 = 86% d'agrement** (OK+MINOR), le moteur est
largement fidele. Les 11 MAJOR + 22 ORACLE_FAIL se regroupent en 6 causes -> taches #105-#110.

| # | gap | signature | cause probable | statut |
|---|-----|-----------|----------------|--------|
| #105 | attaque normale vs **custoTrajann** | eng OVER x1.58 (3 cas) | trait DEFENSEUR **MartialKatah** (-X% des attaques normales) non porte cote defenseur | MAJOR |
| #106 | **MartialInspiration** (yield) | eng=[7404,11046] h3 vs live=[2244,3366] h1 (x3.3) | modele degat des abilities YIELD faux (hits + base) | MAJOR |
| #107 | **ultraApothecary** attaque normale | eng h1 vs live h2 (x0.5, 3 cas) | +1 coup HORS kit de base (effet/aura live) non capte | MAJOR |
| #108 | **MurderousSwing** (config special) | eng UNDER x1.60 uniforme (h1/1) | %-mod attaquant (RapidAssault/BlessingsOfKhorne) non applique au special | MAJOR |
| #109 | **GauntletsOfUltramar / HammerOfWrath** | eng predit du degat, natif=0 (disp=[0,0]) | actives NON-degat scorees a tort (gate makes_damage_predictions trop large) | ORACLE_FAIL(11) |
| #110 | **Doombolt / JakhalStimms** | MakeDamagePredictions null, GetAllPredictions>0 | specials ATTACK-BASED : oracle direct inmesurable (couverture) ; subsume #99 | ORACLE_FAIL(8) |

Autres : `bloodDeathCompany` (Blast ranged) sous/sur-predit par cible (famille #49, range-shape) ;
`bloodMephiston->ultraTitus` OVER x1.49 (1 cas, a re-confirmer) ; `ArmoriumCherub` 1 MAJOR vs
custoTrajann (meme MartialKatah defender #105). `VexillaMagnifica/HolyDuel/BlackRage/Waaagh/
SendInTheNextWave/FightingRetreat` = NON_DAMAGE (buffs, correctement ecartes). `PlasmaCannon/
Supercharge/MightFromBelow/BringerOfDespair/DakkaDakkaDakka` = OK/MINOR (specials config-based
fideles).

Note methodo : les MAJOR **moved-gated** (HeavyWeapon +25%, charge FeederTendrils +728) qui
polluaient le run PRE-cycle ont DISPARU apres le fix cycle-tour (FeederTendrils_NormalAttack passe
OK, PlasmaCannon OK) -> ce sont les 6 causes ci-dessus qui sont de VRAIS ecarts de formule/couverture.
