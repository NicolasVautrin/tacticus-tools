# Case #165 — Profil de PREDICTION = `param_8` du `<Ability>Playbook`, PAS `ability.damageProfile` (audit + validation)

**Statut** : audit RE COMPLET (~60 playbooks) + validation live SELECTIVE. 2 overrides retenus (validés live) + 1
(CrushingClaws, case-164). Le reste = candidats NON retenus (gap plus profond). Generalise l'insight #164.

## L'insight (confirmé #164)

La prediction d'une special vient de `<Ability>Playbook.MakeDamagePredictions` -> `ComparablePlaybook.
GenerateMultiHitAttackPredictions @181409da0`. Signature (audit) :
`(this, p2, p3, target, base, damageFormula, hits, param_8:Nullable<DamageProfile>, &out, 0, typeinfo)`.
Le **`param_8`** (juste avant `&out`) = le profil de degat de la PREDICTION, choisi par le playbook :
- `0` litteral = Nullable vide = profil `None` (enum -1) -> **pierce 0 / armure PLEINE**.
- `Nullable(idx)` = profil explicite (ex. HarvesterOfSouls -> `0x13=19=HeavyRound`, pierce 55).

Le port (`generate_multi_hit_attack_prediction`) derive par defaut `ab.get_damage_profile()` (= damageProfile
config de l'ability, sinon l'arme ranged-first). Divergence quand le playbook passe `null` ou un literal != profil
de l'ability. Sans override, le port applique le PiercingRatio du profil derive (souvent > 0) -> sur-prediction
sur cible blindee la ou le natif applique l'armure pleine.

## Audit param_8 (~60 `<Ability>Playbook`, decompile gqfc5mff6c)

- **~38 NON divergents** : passent `Nullable(ability.GetDamageProfile())` -> le port fait pareil. (Dont SpiritLeech
  = `Nullable(GetFirstAttackDamageProfile @1811ed330)` = wrapper trivial de GetDamageProfile ; ReapingScythe idem.)
- **7 n-a** : pas de `GenerateMultiHitAttackPredictions` (Loki_NormalBossAttack, AncientFury, ExplosivePresents,
  FragstormGrenadeLauncher, MortisRound, MartialInspiration, StormOfFlensingBlades ; TalonsOfTheEmperor = HYPOTHESE,
  MoveNext non lu).
- **12 candidats divergents** : 11 `null` + 1 mismatch (Executioner -> Nullable(0xd=13=Psychic)).

## Validation LIVE (sweep vs ultraTitus, armure 2312) — LE FILTRE DECISIF

L'override pierce ne corrige QUE les abilities dont le pierce est le SEUL gap. La confrontation live a REVELE que
la majorite des candidats ont un gap PLUS PROFOND (hits/base) que l'override ne touche pas :

| ability (id) | carrier | live vs eng (avant fix) | verdict | retenu ? |
|---|---|---|---|---|
| CrushingClaws (1105) | tyranTyrantGuard | [2,2] vs [2236,3352] | pierce SEUL gap | OUI (case-164, bit-exact) |
| **HeraldOfTheApocalypse (1020)** | blackHaarken | Piercing 80 sur-pred | pierce SEUL gap | **OUI (VALIDE OK)** |
| **SanctorumMissile (1062)** | adeptMorvenn | Blast 15 sur-pred | pierce SEUL gap | **OUI (VALIDE OK)** |
| Executioner (1066) | eldarFarseer | [9537,9537] vs [1515,2273] hits 7/1 | gap HITS+base dominant | NON [#166] |
| MultiThreatEliminator (1006) | necroDestroyer | [6,6] vs [0,0] hits 6/1 | gap HITS -> ENG_ZERO | NON [#167] |
| FragBomb (1017) | astraBullgryn | [6,6] vs [0,0] hits 6/6 | base moteur=0 -> ENG_ZERO | NON [#168] |
| SorcerousFacade (1100), DaemonicOrdnance (1148), HadesAutocannons (1147), HarbingerOfDestruction (1008), HellfireShells (1080), PsychicMaelstrom (1027) | thousTzaangor/blackForgefiend/necroPlasmancer/astraPrimarisPsy/(NPC) | non confronte | carrier non buildable / non-firing / build KO | NON [#169] |

## Fix retenu (validé live)

`_PLAYBOOK_PROFILE_OVERRIDE = {1020: "None", 1062: "None"}` (+ CrushingClaws 1105 dans `_crushing_claws_inputs`).
Chaque entree = mirror du `param_8=null` natif (profil None, pierce 0). Les candidats NON retenus restent
documentes en commentaire dans le code + ici, avec leur tache dediee.

## Lecon (importante pour les generalisations futures)

Un audit RE structurel (param_8=null) donne une LISTE DE CANDIDATS, PAS un fix bulk. **Chaque candidat doit etre
confronte LIVE sur cible blindee AVANT d'etre retenu** : les abilities a playbook bespoke cumulent souvent
plusieurs gaps de port (base, hits, pierce) et l'override pierce n'en corrige qu'un. Bulk-appliquer les 11 aurait
shippe des "fix" non valides (dont 3+ prouves faux : hits/base dominants). Le pierce override ne vaut que quand le
reste (base+hits) matche deja l'oracle (cas CrushingClaws / Herald / Sanctorum).

NB decouvert au passage (HORS #165) : `RighteousRepugnance_NormalAttack` (adeptMorvenn) sur-predit aussi
(hits 5 vs 2 cote moteur) — gap d'attaque NORMALE distinct, a tracer separement si adeptMorvenn est joue.
