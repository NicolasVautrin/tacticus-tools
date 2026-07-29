# #229 — Inventaire : quels effet-triggers lisent `e.active` ?

Question posee : pour CHAQUE effectType enregistre dans `EFFECT_TRIGGERS`
(`engine/runner/operations/triggers/dispatch/registry.py`), le port lit-il le flag
`EffectComponent.IsActive @+0x5c` (`BaseEffect.active`) — donc se comporte-t-il correctement
face a une instance seedee INERTE, ce que produirait un `decisionView { includeInactive: true }`
pose en DEFAUT au seed ?

Verdict etabli par LECTURE (decompile + port), jamais par absence de symptome. Re-derivable :
`python scripts/python/probe_229_effect_triggers_active.py` (100 % offline, aucun runner).

## 0. Compte reel du registre — 15 effectTypes / 28 classes (pas ~60)

Mesure du 2026-07-29, re-derivee du code : `EFFECT_TRIGGERS` porte **15 cles** pour **28 classes**
(la valeur est une LISTE : l'`ArraySet` natif rend N triggers par effet). Le chiffre « ~60 » de la
fiche d'entree ne correspond a rien dans ce registre ; l'ordre de grandeur ~60 est celui des
effectTypes *portes* toutes familles confondues, pas des effets *a triggers*.

## 1. Le critere natif : DEUX rails d'evaluation, UN SEUL a gate `IsActive`

`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger` appelle DEUX evaluateurs
sur le meme effet, et ils ne se ressemblent pas :

| evaluateur natif | source des triggers | gate `IsActive @+0x5c` |
|---|---|---|
| `...$$EvaluateEffectTriggerTargets` | `<Effect>$$CreateTargetTrigger` (slot 0x26 de la def) | **OUI, deux fois** |
| `...$$EvaluateEffectTriggerEffectAbilities` | `<Effect>$$CreateHandleTriggerAbilitiesInternal` (slot 0x12) | **AUCUN** |

- `EvaluateEffectTriggerTargets` : `if (*(char *)(effectComponent + 0x5c) != 0) { ... }` a
  l'entree, puis — dans la boucle PAR CIBLE — re-lit le flag sur l'`EffectComponent` recharge
  depuis l'entite (`if (*(char *)(lVar20 + 0x5c) != '\0')`) avant d'appeler `ShouldTrigger`
  (slot 0x13) puis `Execute` (slot 0x14). Une desactivation SURVENUE EN COURS DE DRAIN stoppe
  donc les cibles suivantes.
- `EvaluateEffectTriggerEffectAbilities` : le decompile n'accede **jamais** a `+0x5c`. C'est
  necessaire — c'est ce rail qui porte l'`ActivateEffect` capable de RE-ALLUMER un effet eteint
  (sans quoi un overwatch consomme ne reviendrait jamais).
- `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` greffe, quand
  `<Effect>$$CreateRemoveEffectTrigger` est non nul, un `Triggered(removeTrigger,
  RemoveEffect(this))` dans le **MEME `ArraySet`** : les remove-triggers greffes sont donc du
  rail `EffectAbilities` — eux non plus ne doivent PAS gater.

**Regle** : un trigger doit lire `e.active` si et seulement s'il vient de `CreateTargetTrigger`.
Le gater sur le rail `ArraySet` serait une INFIDELITE, pas une precaution.

Troisieme rail, distinct des deux : `<Effect>$$ApplyInternal` / `$$RevertInternal`
(`AddTriggeredAbility` / `RemoveTriggeredAbility`) — la triggered-ability n'existe que tant que
l'effet est APPLIQUE. Or `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ecrit
`+0x5c = 0` **puis** appelle `UpdateEffectTargets` avec une liste de cibles VIDE, ce qui envoie
toutes les cibles courantes dans `GetTargetsToRemove` -> `RemoveTargetsFromEffect`. Un effet
desactive est donc revoque de ses cibles : ce rail doit lire le flag lui aussi.
(RESIDU NOMME : le call site exact de `IdunBattle.Entities.Effects.BaseEffect$$Revert` est un
delegate non resolu — `RemoveTargetsFromEffect` empile des callbacks ; seules des xrefs DATA
existent.)

### N'importe quel effet peut devenir INERTE — c'est generique, pas une specialite

`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` (lu) :

    if (effect.Removed@+0x5f)                 return;
    if (ShouldBeRemoved(effect))              -> DeactivateEffect + retrait
    else if (!ShouldBeActive(...))            -> DeactivateEffect          // +0x5c = 0
    else                                      -> +0x5c = 1 ; UpdateEffectTargets ; UpdateLevel

Le pilotage du flag n'est donc PAS reserve aux effets a `CreateActiveCondition` custom ni aux
`ActivateEffect`/`DeactivateEffect` explicites : **tout** effet repasse par ce cycle. Corollaire
doctrinal : on ne peut pas ecarter un effectType du rayon de souffle au motif qu'« on ne l'a
jamais vu inactif » — l'absence d'observation ne prouve rien. (Aucun `<Effect>$$CreateActive
Condition` propre n'apparait pour les cinq effets en ecart, mais cette absence ne prouve rien non
plus : les corps triviaux sont dedupliques par IL2CPP.)

## 2. Inventaire — verdict par effectType

Colonne « rail » = origine native (symbole cite dans le probe). Colonne « lit » = mesure AST du
`matches` (le gate) et des helpers qu'il appelle — les ecritures de `execute_behaviour`
(`ActivateEffect`/`DeactivateEffect`) ne comptent pas, ce ne sont pas des gates.

| effectType | classe portee | rail | porteur | lit `e.active` | verdict |
|---|---|---|---|---|---|
| 5 Fire | `FireTileDoT` | ENV_ABILITY | tuile | no | CONFORME (hors rail effet-trigger) |
| 1009 Overwatch_AutoAttack | `OverwatchAutoAttack` | TARGETS | unite | **direct** | CONFORME |
| 1009 | `RangedAutoAttackActivateOnTurnStart` | ARRAYSET | unite | no | CONFORME (ne DOIT pas) |
| 1009 | `RangedAutoAttackDeactivateOnTurnStart` | ARRAYSET | unite | no | CONFORME (ne DOIT pas) |
| 1009 | `RangedAutoAttackDeactivateOnAttack` | ARRAYSET | unite | no | CONFORME (ne DOIT pas) |
| 1077 HazeOfCorruption_DamageTransfer | `HazeOfCorruptionDamageTransferTrigger` | TARGETS | unite | **direct** | CONFORME depuis #231 |
| 1145 EarlyWarningOverride_ReactivateOverwatch | `EarlyWarningOverrideReactivateOverwatch` | ARRAYSET | unite | no | CONFORME |
| 1145 | `EarlyWarningOverrideHitReductionPurge` | ARRAYSET | unite | via `active_effects` | CONFORME (noeud d'arbre `HasEffect(onlyActive=1)`) |
| 1180 InspiredToGreatness_OverrideLevel | `InspiredToGreatnessOverrideLevelRemove` | ARRAYSET (greffe) | unite | no | CONFORME |
| 1186 TimeFlux_Revive (ghost) | `GhostEffectRevive` | TARGETS | **tuile** | no | **ECART** (hors canal, cf. §3) |
| 1186 | `GhostRemoveOnSourceMoves` | ARRAYSET | tuile | no | CONFORME |
| 1186 | `GhostRemoveOnUnitAdded` | ARRAYSET | tuile | no | CONFORME |
| 1186 | `GhostRemoveOnUnitEnters` | ARRAYSET | tuile | no | CONFORME |
| 1186 | `GhostRemoveOnSourceDeathInactive` | ARRAYSET | tuile | **direct** | CONFORME (noeud `NOT IsEffectActive`) |
| 1186 | `GhostRemoveOnSourceRemoved` | ARRAYSET | tuile | no | CONFORME |
| 1197 MasterOfTheTutelaries | `MasterOfTheTutelariesSummonAbility` | APPLY_REVERT | unite | **direct** | CONFORME depuis #231 |
| 1201 AnvilShield_FrozenAttackerAdvantage | `AnvilShieldFrozenAdvantageExpire` | TARGETS | unite | **direct** | CONFORME depuis #231 |
| 1244 Contaminated | `ContaminatedTileEffect` | ARRAYSET | tuile | no | CONFORME |
| 1324 FuelledByFury_CanRevive | `FuelledByFuryCanReviveActivateOnAbilityInit` | ARRAYSET | unite | no | CONFORME (ne DOIT pas) |
| 1324 | `FuelledByFuryCanReviveActivateOnTurnStart` | ARRAYSET | unite | no | CONFORME (ne DOIT pas) |
| 1324 | `FuelledByFuryCanReviveDeactivateOnRevive` | ARRAYSET | unite | no | CONFORME (ne DOIT pas) |
| 1451 PhoenixGem_CanRevive | `PhoenixGemReviveAbility` | ARRAYSET | unite | no | CONFORME |
| 1451 | `PhoenixGemRemoveMarkerOnRevive` | ARRAYSET | unite | no | CONFORME |
| 1451 | `PhoenixGemRemoveMarkerOnResurrect` | ARRAYSET | unite | no | CONFORME |
| 1476 DespoiledGround | `DespoiledGroundTileDoT` | ENV_ABILITY | tuile | no | CONFORME (hors rail effet-trigger) |
| 1502 RitesOfMorkai | `RitesOfMorkaiReviveTrigger` | TARGETS | unite | **direct** | CONFORME depuis 2026-07-29 |
| 1547 ReanimationBeam_Revive | `ReanimationBeamReviveTrigger` | TARGETS | **machine** (MESURE, cf. §3) | **direct** | CONFORME depuis `case-1547` |
| 1550 Chronometron_ExtraDamage | `ChronometronExtraDamageRemove` | ARRAYSET (greffe) | unite | no | CONFORME |

**27 classes conformes / 1 en ecart** (22/6 a l'ecriture de cette fiche ; #231 a resorbe 1077,
1197 et 1201, la tache 1502 a resorbe `RitesOfMorkaiReviveTrigger`, `case-1547` a resorbe 1547).
⚠ Ce compte se PERIME a chaque resorption : le re-deriver par le probe, jamais citer cette ligne.
Precision sur la fiche d'entree : le flag n'etait lu que par **1009** cote `EFFECT_TRIGGERS`
(1077, 1197, 1201, 1502 puis 1547 l'ont rejoint). Pour **1324**, ce sont ses trois triggers qui l'ECRIVENT ;
le LECTEUR (`HasEffect(self, 0x52c, onlyActive=1, 6)`) est `FuelledByFuryReviveAbility`, qui vit
dans `ABILITY_TRIGGERS`, pas ici.

### Notes de qualification

- **5 Fire / 1476 DespoiledGround = ENV_ABILITY** : ce ne sont PAS des effet-triggers natifs. Le
  natif est une ability d'environnement (`EnvFireTileAbility$$CreateTrigger` =
  `On(0x14) & Count(EntitiesWithAnyEffect(5)) > 0`) ; l'inscription dans `EFFECT_TRIGGERS` est un
  VEHICULE de collecte par tuile portant l'effet. Leur gate natif est le selecteur
  (`IdunBattle.Entities.Selectors.EntitiesWithAnyEffectSelector$$Select` ->
  `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`), pas `EvaluateEffectTrigger*`. RESIDU
  NOMME : l'argument `onlyActive` que le selecteur passe a `HasOneOfEffects` n'est pas resolu
  (l'appel decompile a plus d'arguments que la signature reconstruite).
- **1197 MasterOfTheTutelaries** : l'ecart est double. La docstring du port affirme deja
  « instancie UNIQUEMENT tant que l'effet 1197 est ACTIF sur le porteur » et son `matches`
  commente « HasEffect(owner, 1197) : implicite par la collecte EFFECT_TRIGGERS (l'effet est
  actif) ». C'est vrai **par accident du canal de capture** (le canal par defaut ne publie que les
  actifs), pas par le code : `collect_effect_triggers` ne filtre que `e.consumed`. Basculer
  `includeInactive` en defaut rendrait cette docstring FAUSSE et le Screamer serait invoque par un
  effet eteint. **CLOS depuis `case-231-master-tutelaries-active-gate.md`** — et le remede n'y est
  PAS celui du rail TARGETS : l'arbre passe `onlyActive = 0`, l'activite mord par
  `DeactivateEffect -> UpdateEffectTargets(cibles vides) -> Revert -> RemoveTriggeredAbility`.
- **1186 GhostEffectRevive** : l'ecart est structurellement lisible. Le natif oppose deux
  triggers sur la mort du poseur — la resurrection (rail TARGETS, donc gatee par `IsActive`) et le
  retrait n°4 `GhostRemoveOnSourceDeathInactive` (`NOT IsEffectActive`). Ghost INACTIF + poseur qui
  meurt : le natif fait le RETRAIT et rien d'autre ; le port ferait **les deux** (le retrait matche,
  et la resurrection n'a aucun gate). Les deux branches sont exclusives cote natif, complementaires
  cote port.
- **1502 / 1547 (base `ReviveEffect`)** : `_ReviveEffectCore.matches` porte le once-per-turn par
  `ouc.revive_used_this_turn` (proxy PAR UNITE) la ou le natif l'exprime par le flag de
  l'INSTANCE (`DeactivateEffect` du `CreateTargetTriggerBehaviour`). Les deux consommateurs
  inscrits ici sont `removeEffect = TRUE` (one-shot par retrait), donc le proxy suffit sur le
  chemin nominal — mais un revive seede INERTE resterait armee cote port.
  **1547 est CLOS depuis `case-1547-reanimation-beam-active-gate.md`** : le gate y est pose sur
  LA CLASSE `ReanimationBeamReviveTrigger` (et non sur la base `ReviveEffectTrigger`, que 1502
  partage) — 1502 reste donc en ecart, avec sa fiche propre. Le jour ou 1502 sera clos, remonter
  le gate dans `ReviveEffectTrigger.matches` est une refactorisation mecanique.
- **1201 AnvilShield_FrozenAttackerAdvantage** — RESORBE par #231
  (`case-231-effect-1201-active-gate.md`). `matches` etait `AreEqual(target, EffectSource)` seul :
  une instance inerte faisait executer la consommation (`RemoveEffect`) a `UnitPostAbility` alors
  que le natif n'evalue meme pas le trigger. Le gate `_frozen_advantage_flag_is_set` le precede
  desormais, sur le modele de `_ranged_auto_attack_flag_is_set` (1009).

## 3. Rayon de souffle REEL d'un `includeInactive` global au seed

`includeInactive` n'est pas un interrupteur unique : c'est une option de DEUX capteurs distincts,
et le RPC de seed n'en cable qu'un.

- `decisionView` (`frida/hooks/features/ai-step/rpc-decision.ts`) fait
  `readEffectsByUnit(statePtr, { includeInactive })` — **unites et machines uniquement**
  (`EntityType.Unit` / `EntityType.Machine`).
- Les effets de TUILE arrivent par un autre chemin : `tileMeta` (`rpc-board.ts`) appelle
  `readEffectsByTile(statePtr)` **sans options** — les inactifs y sont donc TOUJOURS droppes,
  quelle que soit la decision prise sur `decisionView`.

Ventilation des 6 ecarts :

| ecart | canal de seed | dans le rayon de souffle ? |
|---|---|---|
| 1077 HazeOfCorruption_DamageTransfer | unite | **non** — RÉFUTÉ par mesure live, cf. ci-dessous |
| 1197 MasterOfTheTutelaries | unite | **non** — REFUTE a son tour par mesure (`case-231-master-tutelaries` §4) : 1197 n'est publie ni au canal par defaut ni sous `includeInactive` |
| 1201 AnvilShield_FrozenAttackerAdvantage | unite | **OUI** (non re-mesure ; l'ecart est CLOS par #231) |
| 1502 RitesOfMorkai | unite | **NON MESURABLE** — porteur hors pool, aucune bataille runner ne pose l'effet |
| 1547 ReanimationBeam_Revive | **MACHINE** (`mows[]`, PAS `units[]`) | **OUI — MESURE** (`case-mow-ammo-gauge` §7) : 1547 pose nativement, publie **1 au canal par defaut ET 1 sous `includeInactive`**, sous `mows[].effects` ; `units[]` seul rend 0/0. Le motif « no-ope faute de MUNITION » etait FAUX (`case-mow-ammo-gauge.md` §6). |
| 1186 GhostEffect (`GhostEffectRevive`) | tuile (`tileMeta`) | non — ecart reel, mais inatteignable par cette bascule |

> ⚠ **La colonne ci-dessus est une DEDUCTION (« porteur unite => canal unite »), et #231 en a
> refute la premiere ligne par MESURE.** `probe_231_haze_transfer_active_gate.py` monte un bond
> 1077 reellement pose (temoin natif `BondEffect_BondedId`) et lit les DEUX canaux sur le meme
> etat : **0 entree 1077 au canal par defaut, 0 aussi sous `includeInactive`** — alors que le
> meme appel rend 4 entrees `active: false` pour d'autres effets, donc le canal fonctionne. Le
> bond est HORS de ce que publie `readEffectsByUnit` : la bascule ne peut pas le seeder inerte.
> **1197 est tombe de la meme facon** (mesure independante, `case-231-master-tutelaries` §4).
> **1547 a ete MESURE le 2026-07-29** (`case-mow-ammo-gauge.md` §7) et il est le premier a TENIR :
> l'effet est publie 1/1 aux deux canaux. Mais la colonne « canal de seed » etait FAUSSE pour lui —
> son porteur est la MACHINE, donc l'entree sort sous **`mows[].effects`**, pas sous `units[]`.
> Compter les entrees `units[]` seules y rend 0/0 et fait conclure a tort « non publie ».
> `rpc-decision.ts` remplit les DEUX depuis la meme `readEffectsByUnit(statePtr, { includeInactive })`
> (cle = `casterId` pour une machine) : **toujours agreger `units[] + mows[]`** avant de conclure.
> Sur SIX lignes annoncees « OUI », TROIS ont ete confrontees et une seule a tenu. Traiter les
> restantes comme des hypotheses, et confronter avant de conclure (detail :
> `case-231-haze-transfer-active-gate.md` §3.1).
>
> ⚠ **Ne jamais conclure « non mesurable » d'une absence dans `--list-pool`** : la pool derive du
> seed BC (capture d'UNE bataille) et `catalog_inject.py` l'augmente. Cf. `ca6f5dc`.

## 4. Recommandation

**PLUS AUCUN effectType du canal UNITE ne l'empeche** — les cinq ont ete resorbes le 2026-07-29
(1077, 1197 et 1201 par #231 ; 1502 cf. §4bis ; 1547 par `case-1547`). Les lignes de rayon de
souffle de 1077 et 1197 ont ete REFUTEES par mesure (§3) ; celle de 1502 reste NON MESURABLE faute
de porteur spawnable ; **celle de 1547 est CONFIRMEE par mesure** (`case-mow-ammo-gauge.md` §7 —
1/1 aux deux canaux, sous `mows[].effects`), son gate `IsActive` etant deja pose dans le port. Il
reste UN ecart, mais il est HORS de cette bascule :

    1186  GhostEffect (porteur TUILE)       -> GhostEffectRevive

`tileMeta` appelle `readEffectsByTile` **sans options** : les inactifs de tuile sont toujours
droppes, donc un `includeInactive` pose sur `decisionView` ne peut pas seeder 1186 inerte. Le
gate manquant y reste une INFIDELITE a corriger, pas un obstacle a la bascule.

⚠ Avant de conclure « la bascule est sure », re-deriver ce paragraphe par
`python scripts/python/probe_229_effect_triggers_active.py` : il ne couvre QUE `EFFECT_TRIGGERS`,
et §5 nomme les gisements NON balayes (`has_effect`, face DECISION).

⚠ Les COMPTES de cette fiche (« 6 en ecart », « Cinq effectTypes ») sont ceux de l'inventaire
initial et se PERIMENT au fil des resorptions : les re-deriver par
`python scripts/python/probe_229_effect_triggers_active.py`, jamais citer ces lignes.

Chacun est un trigger a gate natif (`CreateTargetTrigger`, ou `ApplyInternal`/`RevertInternal`
pour 1197) dont le `matches` ne consulte pas le flag : seedes INERTES, ils firent alors que le
natif ne les evalue meme pas. La degradation est PERMISSIVE (report de degat, invocation,
consommation d'effet, revive) — ni erreur ni crash, donc invisible en self-play.

Deux voies de resorption. **#231 a TRANCHE pour la voie 1** (1077), et l'a doublee d'une garde qui
verrouille le refus de la voie 2 (`test_le_gate_ne_vaut_que_pour_le_rail_targets`) ; `case-1547`
l'a suivie a l'identique pour 1547 :

1. **Par-classe** (fidele au natif) : poser le gate dans le `matches` des restants, sur le modele
   deja porte de `_ranged_auto_attack_flag_is_set` (1009). C'est un mirror 1:1 du
   `if (+0x5c)` de `EvaluateEffectTriggerTargets`, une ligne par classe.
2. **Par le collecteur** (plus large, mais faux tel quel) : filtrer `e.active` dans
   `collect_effect_triggers`. **A NE PAS FAIRE sans separer les rails** : cela eteindrait aussi
   les 17 triggers du rail `ArraySet`, dont les `ActivateEffect` qui RALLUMENT l'effet — un
   overwatch consomme ne reviendrait plus jamais. Il faudrait d'abord porter le rail sur les
   classes (attribut `TARGET_TRIGGER = True/False`) et ne filtrer que le rail TARGETS.

La voie 1 est la plus sure ; la voie 2 n'a d'interet que si l'on veut un cliquet structurel, et
exige alors l'attribut de rail que ce probe materialise deja en table.

## 4bis. Resorption (un effectType par tache, voie 1)

- **1077 `HazeOfCorruption_DamageTransfer` : CLOS (#231)** — `case-231-haze-transfer-active-gate.md`.
- **1197 `MasterOfTheTutelaries` : CLOS (#231)** — `case-231-master-tutelaries-active-gate.md`. ⚠ PAS
  le meme remede : rail APPLY_REVERT, dont l'arbre passe `onlyActive = 0` ; l'activite mord par
  `DeactivateEffect -> UpdateEffectTargets(cibles vides) -> Revert -> RemoveTriggeredAbility`.
- **1201 `AnvilShield_FrozenAttackerAdvantage` : CLOS (#231)** — `case-231-effect-1201-active-gate.md`.
- **1502 `RitesOfMorkai` -> `RitesOfMorkaiReviveTrigger` : CLOS le 2026-07-29** —
  `case-229-1502-rites-of-morkai-active-gate.md`. Le gate est pose dans le `matches` de la classe
  1502 SEULE ; son jumeau 1547 (meme base `ReviveEffect`, meme rail) est INTACT et reste en ecart —
  le cliquet le montre (1547 toujours `no`). Complement de RE apporte par cette tache, qui comble
  deux trous du §5 ci-dessous :
  - les DEUX lectures de `+0x5c` sont **desambiguisees**. Liaison des parametres depuis le call
    site de `EvaluateEffectTrigger` : `param_3` = **entite-effet**, `param_4` = **EffectComponent**.
    La 1re lecture (`if (comp.IsActive) { if (comp.Targets.Count == 0) return; }`) est un
    FAST-PATH — un effet INACTIF la TRAVERSE. **Le gate est la 2e** : dans la boucle par cible, sur
    le composant RE-FETCH depuis l'entite-effet (`GetComponent(param_3)`), juste avant
    `ShouldTrigger` (slot 0x13) puis `Execute` (slot 0x14). Les deux portent sur l'effet SOURCE,
    jamais sur la cible.
  - `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` est **decompile** :
    `activation == 1 -> true` ; `== 2 -> false` ; `!= 0 -> ArgumentOutOfRange` ; sinon
    `if (comp@+0x5e != 0) return false` puis `if (!effect.<virtuel 0xc>(evt)) return comp.IsActive`
    (inchange) sinon `return effect.<virtuel 0xb>(entities)`. `RitesOfMorkaiEffect` passe
    `activationFrequency = 0` (`ReviveEffect..ctor`, champ `+0x480`) = la branche CONDITIONNELLE.
- **Reste** : 1186 (canal tuile). 1547 a ete MESURE le 2026-07-29 et son canal RECTIFIE : c'est
  **`mows[]`** (porteur = MACHINE), pas `units[]` — cf. `case-mow-ammo-gauge.md` §7.

## 5. Ce qui n'est PAS couvert par cette fiche

- **Les autres consommateurs de `by_unit`.** L'inventaire ne porte que sur `EFFECT_TRIGGERS`.
  `EffectsState.has_effect` ignore `e.active` par construction — or le natif distingue
  `HasEffect(..., onlyActive=0/1)`. Tout gate de presence porte par `has_effect` deviendrait
  permissif sur un seed inerte. Ce gisement n'est ni compte ni qualifie ici.
- **La face DECISION** (prediction, playbook, stat-mods, auras) : non balayee.
- ~~**Le detail de `ShouldBeActive`**~~ — DECOMPILE par #231 (`case-231-effect-1201-active-gate.md`
  §2.3) : `kind == 1 -> true`, `kind == 2 -> false`, sinon `comp+0x5e != 0 -> false`, puis
  `!HasActiveCondition(trigger) -> comp.IsActive@+0x5c`, sinon `CreateActiveCondition().ShouldTrigger`.
  Lecture INDEPENDANTE et concordante par la tache 1502 (cf. §4bis) ; le 1er argument de la branche
  conditionnelle (`kind`) est le champ `activationFrequency` du ctor d'effet — `RitesOfMorkaiEffect`
  passe **0** (`ReviveEffect..ctor`, champ `+0x480`), soit la branche CONDITIONNELLE.
  RESIDUS restants : l'ECRIVAIN de `EffectComponent+0x5e` n'est pas identifie (absent de
  `$$GetPropertiesString` et de `$$.ctor`), et la semantique de `kind` (`0/1/2`) vient des retours
  litteraux du decompile, pas d'un dump d'enum.
- **`onlyActive` du selecteur `EntitiesWithAnyEffect`** (gate reel de 5 / 1476) : non resolu.
- **Aucune mesure LIVE** : cette fiche est un inventaire par lecture. Aucune bataille n'a ete
  montee pour observer un effet inerte de ces cinq types (et l'absence d'un tel effet en
  observation ne prouverait rien, cf. §1).
