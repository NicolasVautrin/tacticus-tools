# #437-r1-r1-r3 — pourquoi le `x1.25` n'entre pas dans la prediction native

**EN COURS DE REDACTION — le critere ci-dessous est pose AVANT toute mesure.**

## 1. Le critere, enonce AVANT de mesurer

Residu herite : sur ce que la fiche `#437-r1-r1` decrit comme « les memes entrees d'etage »
(base 3614/5422, percage 30, armure 0), deux vecteurs natifs rendent des bornes differentes —
combat `(1130, 1695)`, `aiPredict` `(904, 1356)` = `Round(P x 0.25)`, face attaquant absente.

**Question binaire** : dans l'etat exact ou `--predict-2faces` lit `(904, 1356)`, la face
ATTAQUANT `HeavyWeapon_ExtraDmg` est-elle NON NEUTRE ?

* **Lecture MONTAGE** — elle est NEUTRE dans cet etat (une condition du trigger DSL de
  `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` est fausse).
  Alors le COMBAT sur CE MEME etat rend aussi `(904, 1356)` : **il n'y a aucune divergence de
  modele**, et le residu se ferme.
* **Lecture REELLE** — elle est NON NEUTRE (le combat sur ce meme etat rendrait `(1130, 1695)`) et
  seule la voie PREDICTION l'ignore. Il faut alors remonter au decompile : quel appelant construit
  quels `Nullable<DamageModifiers>`.

**Ce qui separe les deux** : une garde par PRESENCE de l'effet ne vaut rien (mesure #437-r1-r1 §5).
Ce qui vaut est la valeur du bonus CONSTRUIT, et l'etat des trois entrees du trigger natif.

**Ce qui me ferait conclure l'inverse** : si le port lui-meme (`stage_inputs`) rend `pct_att` NON
VIDE dans cet etat ET que le capteur `effect-bonus-trace` ne voit aucun `Add` de face `attacker`
pendant l'appel `aiPredict`, alors la face est bien vivante et la prediction l'ignore — lecture
REELLE. Inversement `pct_att` VIDE cote port = les deux modeles sont d'accord et c'est le montage.
