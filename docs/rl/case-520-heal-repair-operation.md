# #520 — HEAL/REPAIR : le « BLOQUE » de l'audit est PERIME, mais le SOIN n'a pas son pipeline

**Statut** : etage 1 tranche. Redaction en cours.

## Etage 1 — VERDICT SUR LA PREMISSE

`docs/rl/combat-ability-coverage.md` annonce (texte ecrit par `audit_combat_ability_coverage.py`) :

> 3. **HEAL** / lifesteal / **REPAIR** -> **BLOQUE** sur un `HealOperation`/`RepairOperation`
>    combat absent du runner (tache #94). A construire avant de porter cette categorie.

**FAUX sur les deux termes.** Les deux Operations sont portees, et depuis longtemps :

| Operation | module porte | gate | pipeline de montant |
|---|---|---|---|
| `IdunBattle.Operations.HealUnitOperation$$Execute` | `engine/runner/operations/heal.py` | **ABSENT** | **ABSENT** |
| `IdunBattle.Operations.RepairUnitOperation$$Execute` | `engine/runner/operations/repair.py` (#299) | `AttackQuery$$EntityCanBeRepaired` | `DamagePrediction$$PredictRepair` (4 etages) |

La categorie n'est donc PAS bloquee : la ligne de l'audit est une citation perimee, et elle est
corrigee **dans le generateur**, pas dans le fichier genere.

## Ce que l'etage 1 a trouve EN PLUS — l'asymetrie HEAL/REPAIR

`RepairUnitOperation` porte les trois etages propres a la reparation ; `HealUnitOperation`, lui,
est un `fill_up` NU + un gate `EffectType.Cursed`. Il lui manque, cote natif :

  * `AttackQuery.<slot 0x11>` = `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed` — le gate ;
  * `DamagePredictionQuery.<slot 1>` = `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` — le
    `HealModifier` de la cible, le cap de GROUPE (`scope == 1`) et le cap BOSS.

C'est le vrai bloqueur de la categorie, et il est INVISIBLE : les quatre abilities HEAL deja au
registre soignent, mais d'un montant qui ignore tout modificateur de soin.
