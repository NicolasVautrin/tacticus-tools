# case-393 — une SUBSTITUTION à signature fixe dérive derrière le port, et le rouge tombe ailleurs

`test_additional_hits_rounding_live.py` est parti **rouge sur `master`** (3 échecs) après la PR
`1227 HarlequinsPanoply` :

    TypeError: additional_hits_variant.<locals>._exec() got an unexpected keyword argument
    'hit_interceptor'

**Défaut de HARNAIS, pas de port.** Plusieurs probes remplacent `execute_additional_hits` par une
implémentation de substitution **à signature fixe**, pour n'isoler qu'un étage à la fois. Le port,
lui, gagne des paramètres. Chaque ajout casse en silence toute substitution restée en arrière — et
le `TypeError` tombe à la **passe live suivante**, pas dans la PR qui a ajouté le paramètre.

## Les deux substitutions trouvées, et leur retard

| substitution | paramètres manquants | rouge visible ? |
|---|---|---|
| `probe_r6_round_materialize.additional_hits_variant` | `hit_interceptor` (#366-r1) | oui — 3 échecs live |
| `probe_r6b_additional_hits_order._extra_rolls_variant` | `attack_profile` (#227) **et** `hit_interceptor` | **non** — chemin `--extra-rolls`, exercé par aucun test |

La seconde était donc cassée depuis #227 sans que rien ne le dise : elle n'est atteinte que par
`probe_r6b --extra-rolls N`.

## Le paramètre est TRANSMIS, pas avalé

Un stub qui accepterait `hit_interceptor` puis le laisserait tomber rendrait le test vert **en
cessant d'exercer l'étage**. Concrètement, il désarmerait le discard `HarlequinsPanoply` et le
`RegisterBlockMade` per-coup dans les rejeux offline, mais **pas** dans le port livré : l'écart se
lirait comme une régression de matérialisation. La condition de validité de ces contrefactuels est
que **seules** `order` et `force_round` (resp. `k`) varient — tout le reste est threadé verbatim.

## Le cliquet

`scripts/python/tests/test_additional_hits_variant_signatures_offline.py` — offline, hermétique
(pas de session, `gameconfig` neutralisé), deux gardes :

1. **signature** — scan AST de tout `scripts/python/**` : toute fonction dont les six premiers
   paramètres sont ceux du canal (`state, attacker_id, target_id, tgt, thc, groups`) doit déclarer
   la **même liste** que `execute_additional_hits`, et n'a droit ni à `*args` ni à `**kwargs`.
   **Aucune liste à tenir à jour** : une troisième substitution écrite demain est enrôlée seule ;
2. **transmission** — une sentinelle passée en `hit_interceptor` doit ressortir **identique** dans
   les kwargs vus par `AttackDamageOperation._run_hits`.

Contre-épreuve (la garde mord) : rejouée sur l'arbre d'avant le correctif → **3 rouges** (signature
+ les deux transmissions), 1 vert (la prémisse « le scan trouve bien les substitutions »).
