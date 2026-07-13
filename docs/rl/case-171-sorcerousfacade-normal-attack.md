# Case #171 — SorcerousFacade (1100, thousTzaangor) : la prediction ennemie = l'ATTAQUE NORMALE, pas le special config

**Statut** : RESOLU + VALIDE LIVE. Fix = `_PREDICT_VIA_NORMAL_ATTACK += {"SorcerousFacade"}`. SorcerousFacade
OK bit-exact [1623,3591] ; garde predict_live 2/2 PASS.

## Ground truth live (mesure 2x, board MC1_67, thousTzaangor/Yazaghor -> ultraTitus)

Side-by-side au MEME position/cible (probe direct aiPlaybookPredict + engine, hors filtre attackPlan) :

| ability | oracle (aiPlaybookPredict) | engine AVANT fix | engine APRES fix |
|---|---|---|---|
| SorcerousFacade (1100) | **[1623, 3591]** (playbook=SorcerousFacadePlaybook) | [1197,1795] (special generique) MAJOR | **[1623,3591] OK** |
| Loki_NormalAttack (69)  | [1623, 3591] (Loki_NormalAttackPlaybook) | [1623,3591] OK | [1623,3591] OK |

`SorcerousFacade oracle == attaque normale (oracle ET engine) == [1623,3591]`, EXACTEMENT. La prediction native
de degat de SorcerousFacade CONTRE L'ENNEMI = l'attaque normale du caster (texte de regles : « Yazaghor performs
a NORMAL ATTACK against the closest enemy, then switches positions »). Le +728-1455 Psychic est le BONUS de BUFF
sur les futures attaques normales, PAS ce degat predit.

## Mecanisme natif (RE reconcilie — 2 passes re-expert)

`SorcerousFacadePlaybook.MakeDamagePredictions @18115bb90` construit DEUX events, tous deux pour la cible ENNEMIE
`lVar19 = TargetsSelector.SelectFirst(GetTarget(ability)) @18115bcf0` (l'ennemi le plus proche) :

1. **EVENT #1 = ATTAQUE NORMALE du caster** — via l'interface `DAT_18327ff80` slot **0x21** sur `*(param_1+0x28)`
   (le battleQuery/DSL du playbook) @~18115bd60, puis `ProbableDamageEvent.ctor(&event, lVar19, &profile) ->
   ToList`. C'est le MEME appel d'interface (DAT_18327ff80 slot 0x21 = « profil d'attaque normale du caster vs
   target ») que `NormalAttackPlaybook.MakeDamagePredictions @18149eeb0`. -> [1623,3591]. **C'est l'event que
   l'oracle expose.**
2. **EVENT #2 = `GenerateMultiHitAttackPredictions(base=Half(Sum(GetVariableForLevel(cfg,0xc),0xd)) = avg config
   728-1455, hits=GetNumberConstant(cfg,0x2f), profile=null)` @181409da0** = [1197,1795], MEME cible ennemie,
   ajoute par `AddRange`. L'oracle (aiPlaybookPredict) ne remonte PAS cet event #2 (dedup aval par cible +
   regle : l'ennemi ne subit QUE l'attaque normale ; le config 728-1455 = buff futur).

Piege de la 1re passe RE : le `GenerateMultiHit(base=config)` (event #2) avait ete lu comme LA base, mais l'event
RETOURNE/expose pour l'ennemi = l'event #1 (attaque normale), construit AVANT et via un mecanisme distinct.
Ce N'EST PAS le cas #92 refute (heritage vtable `PredictAttack` Attack-based) : ici le playbook EMET
EXPLICITEMENT une prediction d'attaque normale (interface slot 0x21), ce n'est pas un heritage.

## Fix (applique + valide)

`engine/playbook/prediction.py` : `_PREDICT_VIA_NORMAL_ATTACK = frozenset({"SorcerousFacade"})` (etait VIDE
depuis #99). SorcerousFacade est son 1er membre LEGITIME : `make_damage_predictions._event` route via
`make_normal_attack_predictions` (mirror de l'event #1). Distinct des 5 specials de #99 (config-based via
`PredictAttack` -> stub abstrait) : SorcerousFacade emet une attaque normale explicite.

VALIDATION : SorcerousFacade eng [1623,3591] == oracle (probe171, 2x, side-by-side vs id 69). Garde predict_live
2/2 PASS (aucune regression). L'attaque normale (id 69) reste OK.

## Portee / non-porte

L'event #2 (config-special [1197,1795], meme cible) N'EST PAS porte : l'oracle ne l'expose pas et l'ennemi ne
le subit pas (regle). Si un jour un consommateur aval du natif s'avere sommer event#1+event#2 pour l'utilite AI,
re-ouvrir ; pour la FIDELITE PREDICTION (== aiPlaybookPredict, verite per-ability depuis #102), l'event ennemi =
l'attaque normale, point.

## Lecon

Une lecture statique "base = config vars" peut etre INTERNE-coherente mais concerner le MAUVAIS event d'une
fonction MULTI-EVENTS (ici event#2 secondaire vs event#1 principal = l'attaque normale). Le side-by-side live
avec l'attaque normale au meme position a LOCALISE l'event ennemi ([1623,3591]==normale), et la 2e passe RE a
identifie le mecanisme exact (interface slot 0x21 = NormalAttackPlaybook). Quand une ability "declenche une
attaque normale" (texte de regles), toujours confronter l'oracle a l'attaque normale AVANT de porter une base config.
