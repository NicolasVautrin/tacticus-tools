# #484 -- les rouges PERMANENTS de `master` : re-derivation, ventilation, cause unique

**Mesure re-derivee le 2026-08-06** sur `origin/master` = `959189f2`, worktree propre,
`probe_457_offline_tests_green.py` en 8 shards (`TACTICUS_ALLOW_RATCHETS=1`) :

| | |
| --- | --- |
| perimetre (`not name.endswith("_live.py")`) | **213** fichiers |
| shards rouges | **6 / 8** (`s1 s2 s3 s5 s6 s7`) |
| tests en echec | **42** |
| fichiers porteurs | **13** |

Le compte rapporte par l'agent de `#477-r33` etait **40**. L'ecart de **+2** n'est pas une
derive de mesure : ce sont deux gisements a SEUIL (`test_270r4r2r2::etage3`,
`test_270r4r2r2r3::etage6`) que des PR mergees entre-temps ont fait franchir. Les rouges se
comptent donc a la HAUSSE tant que personne ne les traite -- c'est le comportement attendu
d'un cliquet, et la raison pour laquelle un rouge permanent est pire qu'absent : il encaisse
la degradation sans que quiconque le lise.

## 1. LA CAUSE UNIQUE -- `492c722f`, et elle porte 25 des 42

> `refactor(#270-r4-r2-r2): hisser 624 imports differes d'engine/ au niveau module`
> (2026-08-05, 144 fichiers, 671 insertions / 707 suppressions)

Ce refactor est **value-preserving a l'execution** -- sa propre mesure le dit (0 divergence de
VALEUR sur 197 017 attributs) -- et c'est exactement ce qui l'a rendu invisible : il ne change
pas ce que le code CALCULE, il change **ou le nom est LIE**.

```python
# AVANT (differe, dans le corps de la fonction)
def invalid_caster_reason(...):
    from ..runner.abilities.targeting import targeting_options_for   # lu a CHAQUE appel
    opts = targeting_options_for(aid)

# APRES (hisse au niveau module)
from ..runner.abilities.targeting import targeting_options_for       # lu UNE fois, a l'import
```

Un `import` differe re-resout l'attribut **du module source** a chaque appel : un
`monkeypatch.setattr(<module source>, "<nom>", stub)` mord. Hisse, le nom est copie dans le
namespace du CONSOMMATEUR au moment de l'import -- le patch pose sur la source ne mord **plus
jamais**. Les tests concernes n'ont pas commence a mesurer FAUX : ils ont cesse de **mesurer**.

**Signature commune, et elle est reconnaissable** : ce ne sont pas des ecarts de valeur, ce
sont des messages d'auto-controle -- *« le montage ne teste rien »*, *« le mutant rend la MEME
valeur »*, *« observe 0 »*, `assert None == <attendu>`. Ces tests ont ete ecrits avec la garde
qui detecte leur propre inertie ; elle a fonctionne. Sans elle, les 25 seraient **VERTS et
vides**, ce qui est le vrai cout evite ici.

| test | site du patch | consommateur qui lie desormais au module | fails |
| --- | --- | --- | --- |
| `test_433_..._caster_reason_offline.py` | `TGT.targeting_options_for` | `engine/services/ability_caster_gates.py` | **21** |
| `test_344r2_sort_attackers_prediction_offline.py` | `engine.services.damage_prediction.get_attack_prediction` | `engine/runner/abilities/darkangels.py` | **2** |
| `test_383_ramming_speed_explosion_offline.py` | `PA.generate_multi_hit_attack_prediction` | `engine/playbook/prediction/ramming_speed.py` | **1** |
| `test_448_r1_r1_r1_r1_flying_tiles_moved_offline.py` | `_F.is_like_flying` | `engine/services/movement_query.py` | **1** |

Les quatre lignes hissees sont VISIBLES dans le diff de `492c722f` :
`ability_caster_gates.py` (`targeting_options_for`), `darkangels.py` (`get_attack_prediction`),
`ramming_speed.py` (`generate_multi_hit_attack_prediction`), `movement_query.py`
(`is_like_flying`).

### 1bis. Le degat NE SE LIT PAS au nombre de rouges

`test_383` le montre : **trois** tests partagent le meme montage `_capture`, **un seul**
rougit. Les deux autres passent parce qu'ils n'assertionnent que sur la valeur de retour
(`evs`), que le vrai service continue de produire -- ils sont devenus des tests du **code
reel** la ou ils devaient tester le **cablage**. Meme forme sur `test_344r2` : deux des trois
parametres de `test_each_test_is_read_on_its_own_prediction` attendent `weak-first`, qui est
aussi l'ordre des ids en cas d'egalite -- ils passent **par coincidence**. Le rouge sous-compte
donc le degat : **42 rouges** signalent un nombre inconnu et superieur de tests **devenus
vacueux**.

### 1ter. La reparation, et pourquoi elle ne touche AUCUN contrat

On deplace le site d'injection la ou le nom est **effectivement lu** -- le module
CONSOMMATEUR -- sans toucher une seule assertion, une seule valeur attendue, un seul
`parametrize`. Le contrat teste (l'ordre des onze clauses, l'appariement borne <-> prediction,
la branche volante) est inchange. C'est la seule reparation qui soit mecanique ici :
re-differer les imports rouvrirait le gisement que `492c722f` a ferme, et le cliquet
`test_270r4r2r2` l'interdit executablement.

## 2. Ventilation des 42 -- la somme vaut le total

(Section completee au fil du travail ; voir le rapport de la PR.)
