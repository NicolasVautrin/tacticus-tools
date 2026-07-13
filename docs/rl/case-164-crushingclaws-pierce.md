# Case #164 — CrushingClaws prediction : le playbook passe `param_8=null` (profil None) -> pierce 0, PAS le PiercingRatio de l'ability

**Statut** : RE fait (decompile `gqfc5mff6c`) + FIX applique + VALIDE LIVE (2 niveaux d'armure, bit-exact). #164 CLOS.

## TL;DR

`predict_sweep` flaggait CrushingClaws (TyrantGuard 1105) en MAJOR : oracle `[2,2]` vs moteur `[2236,3352]`.
Le `[2,2]` (min==max, chaque coup = 1) N'EST PAS un cap d'overkill (l'attaque NORMALE de la meme unite, meme
cible, meme profil Piercing, predit `[3086,4632]` correctement). C'est **pierce 0** : le natif applique
l'armure PLEINE a CrushingClaws.

**Cause structurelle** : la prediction d'une special vient de `<Ability>Playbook.MakeDamagePredictions` qui
appelle `ComparablePlaybook.GenerateMultiHitAttackPredictions @181409da0` avec un **profil de degat EXPLICITE
en `param_8` (`Nullable<DamageProfile>`)** — PAS le `damageProfile` de l'ability.
- `CrushingClawsPlaybook.MakeDamagePredictions @1811274b0` passe **`param_8 = null`** (0) pour la cible
  principale ET chaque splash -> profil `None` (enum -1) -> **pierce 0** -> armure pleine.
- `HarvesterOfSoulsPlaybook @1811428b0` passe `Nullable(0x13=19=HeavyRound)` -> pierce 55 (le port le
  retrouvait via `ab.get_damage_profile()`, d'ou sa justesse "generique" — coincidence, pas structure).

Le port sourcait le profil de prediction depuis `ab.get_damage_profile()` (= "Piercing" -> PiercingRatio 80),
divergence STRUCTURELLE du natif (qui le prend en param_8). D'ou la sur-prediction (peu d'armure soustraite).

## RE (VAs, build gqfc5mff6c)

- `CrushingClawsPlaybook.MakeDamagePredictions @1811274b0` :
  - base = `ArcScourgeAbility.GetDamage @1811b3800` = `AActiveAbility.MinMaxDamageAverage @180fb2cc0` =
    `DSLFactory.Half(Sum(Direct(minDmg[lvl,mult]), Direct(maxDmg[lvl,mult])))` = **avg(minDmg,maxDmg)** (POINT,
    pas une plage -> explique min==max cote oracle). (minDmg id 0xc, maxDmg id 0xd.)
  - hits main = `ArmoriumCherubAbility.GetHits @180fb16c0` = `GetNumberConstant(0x2f=nrOfHits)` = 2.
  - hits splash = `BringerOfDespairAbility.GetHitsToBonusTarget @180fb1690` = `GetNumberConstant(0x32=nrOfHits_2)` = 1.
  - main : `GenerateMultiHit(..., target, base, hits=2, param_8=0, ...)` -- **param_8 = 0 (null)**.
  - splash : boucle `GetEntitiesFromSelector(GetAdjacentDamageTargetsUnits)` -> `GenerateMultiHit(..., s, base,
    hits=1, param_8=0, ...)` -- **param_8 = 0 (null)** aussi.
- `GenerateMultiHitAttackPredictions @181409da0` : invoque le service `DamagePrediction.PredictAttack`
  (slot interface 0x27) avec `(base_wrappe, param_8=profil-nullable, hits)`. `param_8` = le profil de degat de
  la PREDICTION. Null -> profil `None` -> pierce 0.
- `HarvesterOfSoulsPlaybook @1811428b0` : `local_res8[0]=0x13 ; Nullable__ctor(&local_368, 0x13)` puis
  `GenerateMultiHit(..., param_8=Nullable(0x13), ...)`. 0x13=19 = **HeavyRound** (`_PROFILE_BY_INDEX[19]`).
- Profils (gameconfig) : Piercing={PiercingRatio:80}, Physical={PiercingRatio:1}, HeavyRound={PiercingRatio:55},
  enum -1 = "None". Les DEUX volets de CrushingClaws (Piercing main + Physical splash) collapsent identiquement
  -> le natif n'utilise NI l'un NI l'autre profil : param_8=null (pierce 0), profil-independant. Preuve directe.

## Experience decisive (base=0 vs pierce=0)

`[2,2]` seul ne distingue pas "base ~0" de "pierce 0 + armure pleine" (les deux -> plancher 1/coup). Discriminant
= CrushingClaws vs cible FAIBLE armure. base avg live = **1746** ((minDmg 1496 + maxDmg 1996)/2, lvl 50 x mult 180).

| cible          | armure | oracle main (2 coups) | oracle splash (1 coup) | formule pierce 0 (base+/-20% - armure) |
|----------------|--------|-----------------------|------------------------|-----------------------------------------|
| ultraTitus     | 2312   | [2,2]                 | [1,1]                  | [1397-2312, 2095-2312] < 0 -> plancher 1 |
| worldJakhal    | 1003   | [788,2184]            | [394,1092]             | [1397-1003, 2095-1003] = [394,1092] EXACT |

base pas 0 (le degat SCALE avec l'armure) ; pierce 0 EXACT aux deux niveaux (splash = base+/-20% - armure, coup unique).

## Fix (offline, aucun reinject/capture)

`engine/playbook/prediction.py` : handler `_crushing_claws_inputs` (HOMONYME du playbook natif) enregistre pour
l'ability 1105 dans `_MAKE_DMG_INPUT_OVERRIDES`, rend `{"profile_override": "None"}`. Le profil "None" ->
`GC.damage_profile("None")=None` -> pierce 0 (`dp={}`), `profile_idx=-1`. Mirror du `param_8=null` natif (main +
splash, car `make_damage_predictions._event` applique l'override aux DEUX). base/hits inchanges (1746 / 2 / 1).

## Validation live (predict_sweep + probe)

- Sweep `--p-units eldarMauganRa,tyranTyrantGuard --a-units ultraTitus,ultraTitus --board MC1_67` : **OK=8/8**
  (CrushingClaws OK=2 [etait MAJOR=2] ; HarvesterOfSouls OK=2 + NormalAttack OK=4 = **0 regression**).
- Probe vs worldJakhal (armure 1003) : moteur main `[788,2184]` == oracle `[788,2184]` **bit-exact** (arme-general,
  pas juste le plancher). Splash oracle `[394,1092]` == formule pierce 0.

## Portee & suivi (generalisation)

Insight STRUCTUREL : **le profil de prediction d'une special = le `param_8` que passe SON `<Ability>Playbook`,
PAS `ability.damageProfile`.** Le port le derive de l'ability (juste pour le playbook generique + la plupart des
bespoke, ou param_8 == profil de l'ability), mais un playbook bespoke peut passer un profil DIFFERENT (HeavyRound
explicite) ou NULL (CrushingClaws). -> AUDIT a faire : enumerer tous les `<Ability>Playbook.MakeDamagePredictions`
bespoke et confronter leur `param_8` a `ab.get_damage_profile()` du port (tache de generalisation #165).
