# #491 — `1069 SeekerMissileFrequencyLock` : l'audit disait DAMAGE, le natif ne frappe PAS

Build `rnca9r7q6c`. Porteur lineup : `tauMarksman` (Sho'syl), dans le pool rank 17.

## Le contre-résultat

L'audit `combat-ability-coverage` classe `1069` en `DAMAGE(HeavyRound)` — d'après le
profil d'attaque du kit (`1hmp20 / 1hR3p80`). **C'est faux au niveau de l'ability active.**

`IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour`
ne contient **aucun** nœud d'attaque : il pose trois effets et les compose.

(en cours de rédaction — RE non terminée)
