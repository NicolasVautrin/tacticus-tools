> Debloqueur transverse case-220 (levier #1, ~9 items) — RE des artefacts natifs (2026-07-23).
> Ledger : [case-220-classification-campaign.md](../case-220-classification-campaign.md) §T ligne "Feuilles stat-mod".
> Sommaire : [port-roadmap.md](../port-roadmap.md) §4.1. Faces consommatrices : black-templars.md,
> astra-militarum.md, emperors-children.md, world-eaters.md.

# Feuille DSL `AddStaticStatModifierEffect` (self / ToOwner / sur SELECTEUR)

## Etat
- **Feuille DSL = GAP** : `runner/abilities/behaviours/stats.py` porte `Heal`/`ChangeStat`/`SetHealth`
  mais PAS encore la feuille de pose de stat-mod permanent/duree (docstring stats.py:5 : "c'est ICI
  qu'atterrira la feuille").
- **Mecanique de pose EAGER = DEJA portee** : le runner applique un StatModification via
  `AddEffectOperation._apply_stat_mods -> apply_change_stat` (source-keye), cf. `BlackRageExtraMoveEffect`
  (EffectType 1342, `entities/effects/loki/status.py:407`) pose par BlackRage
  `AddStaticStatModifierEffect(caster, 1342, stat=MOVEMENT(1), amount=ConfigConst(extraMovement))`.
  => le port de la feuille REUTILISE ce chemin ; il n'y a PAS de nouvelle Operation a ecrire.

## Artefacts natifs (VAs, build gqfc5mff6c)
Factory `DSLFactory` (`IdunBattleLogic.Entities`) — 3 familles, wrappers Nullable inclus :
- `AddStaticStatModifierEffect` @180de7c60  (CORE plain : owner=0,0 -> cibles = selecteur `param_2`)
- `AddStaticStatModifierEffect` @180de79a0 / @180de7b20  (wrappers `Nullable<amount>` : `Nullable.get_Value`
  + node d'amount ; le label decompile `IceTileEffect.<FreezeCoroutine>` est un MISLABEL gshared, ignorer)
- `AddStaticStatModifierEffectToOwner` @180de7750 (CORE) / @180de7860  (injecte `*(builder+0x148)` =
  self/owner cache DEUX fois dans le ctor -> lie l'owner du modifier au CASTER, au lieu de 0,0)
- `AddOrUpdateStaticStatModifierEffect` @180de71d0  (variante : maj si un modifier meme cle existe deja)

Feuille (le vrai noeud a porter) `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour` :
- `..ctor` @180fb7850  (args mappes depuis le factory : ownerSel?, ownerSrc?, targetSel `param_2`,
  statType `param_3`, mode/flag `param_4`, amountNode `param_5`, duration `param_6`, bool `param_7`)
- `.Execute` @180fb6c10  <-- A DECOMPILER EN PREMIER au port (ordre exact des args + semantique mode/duree)
- `.StatModifierBuilder` @180fb7680  (construit le StatModification injecte a l'effet)
- `.CheckParametersAndLogErrors` @180fb6a40 ; lambda display-class `<Execute>b__0` @180fd9180

Effet pose `IdunBattle.Entities.Effects.StaticStatModifierEffect` :
- `..ctor` @180f474c0  (copie un bloc StatModification 7-champs `param_2[0..6]` puis delegue a
  `ADynamicStatModifierEffect..ctor` -> variante "static" = montant FIXE, ne recompute pas)
- `.GetStatModificationAmount` @180f47430  (renvoie le montant fixe)

## Modes (tranches au decompile factory)
1. **self / sur SELECTEUR** (`@180de7c60`) : cibles = le TargetsSelector `param_2` (peut etre Self, ou
   un selecteur AoE type Friends r2). owner du modifier = null (0,0).
2. **ToOwner** (`@180de7750`) : owner du modifier force au caster (`builder+0x148` x2). Usage : buffs
   dont l'expiration/retrait suit le CASTER (ex. aura BlackTemplars +1091 melee vs Psyker, LeadingTheCharge).
3. **AddOrUpdate** (`@180de71d0`) : semantique idempotente (refresh d'un modifier existant meme cle) —
   a confirmer sur `.Execute` (probable coalescing par (source, stat) au lieu d'empiler).

## Items consommateurs (9, cf. §T)
BlackTemplars (levier #1) : CrusadeOfWrath (1086/1087 sur selecteur r2), UnbreakableDuty (1083 permanent
On(28)), DestroyTheWitch (1088/1089 ToOwner aura), ChampionOfTheFeast (1097 ToOwner + count) ; +
DoomSiren, ExcruciatingFrequencies, RefusalToBeOutdone, LeadingTheCharge, TrophyTaker.

## Prochaine action (port [opus], prochaine vague)
1. Decompiler `AddStatModifierEffectBehaviour.Execute @180fb6c10` + `.ctor @180fb7850` + `.StatModifierBuilder
   @180fb7680` -> fixer l'ordre des args et la semantique mode(param_4)/duration(param_6)/flag(param_7).
2. Ajouter la feuille `AddStatModifierEffect` dans `runner/abilities/behaviours/stats.py` (3 modes :
   selecteur / self / ToOwner), reutilisant `AddEffectOperation._apply_stat_mods` + `apply_change_stat`
   (source-keye) — modele `BlackRageExtraMoveEffect` (status.py:407, deja pose eager).
3. Cabler + valider sur 1 porteur spawnable (ex. CrusadeOfWrath BlackTemplars : buff selecteur r2 mesurable
   au ChangeStat live) ; AddOrUpdate = confirmer coalescing.
