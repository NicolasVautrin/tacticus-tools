# case-366-r1 — `1014 CamoCloak_DmgReduction` : une reduction PLATE gatee par le COUVERT

**Question, binaire.** Le port retire-t-il du degat ranged recu par `ultraEliminatorSgt` exactement
ce que le natif retire, et se tait-il exactement quand le natif se tait ?

*(RE en cours — ce document est ecrit au fil de l'etablissement ; voir le commit final.)*

## 1. Ce que l'inventaire annoncait, et ce que le decompile dit

`docs/rl/case-366-gisement-96-effets.md` §3.3 : « `CreateDamageModifier` + `CreateActiveCondition` ».
Les deux methodes existent bien, mais la colonne ne dit ni le CANAL ni la CONDITION — les deux
sont etablies ici a leur source.
