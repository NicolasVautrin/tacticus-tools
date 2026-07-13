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

## #169 — resolution des 6 candidats NON confrontes (RE deep-read + live)

Les 6 candidats "non confrontes" du tableau ci-dessus ont ete tranches par un DEEP-READ RE (re-expert : chaque
`<Ability>Playbook.MakeDamagePredictions` + sa chaine, VAs citees) + confrontation live (sweep vs `ultraTitus`
armure 2312, board MC1_67). **Un seul est un override pierce valide ; les 5 autres NE le sont PAS.**

**Clarification de signature (corrige l'audit) :** `ComparablePlaybook.GenerateMultiHitAttackPredictions @181409da0`
= `(this, p2, p3, target, dslEntity, base, hits, param_8=DamageProfile(Nullable), param_9=&weight(Nullable<Fix64>),
0, typeinfo)`. Le `param_8` = PROFIL ; le `param_9` = POIDS Fix64 de la tranche. Le caveat d'arite de #169 sur
PsychicMaelstrom (« null sur l'appel #1 seulement ») confondait param_8 et param_9.

| ability (id) | carrier | param_8 | base (RE) | live | verdict #169 |
|---|---|---|---|---|---|
| **HarbingerOfDestruction (1008)** | necroPlasmancer | **null**@1811425bc | avg@18114252c (OK) ; hits=ArmoriumCherub.GetHits@18114255e (OK) | NON confrontable (carrier = `UNSPAWNABLE_FALLBACK` ; autres = NPC) | **RETENU `"None"`** sur PREUVE decompile (pierce-SEUL gap, structure IDENTIQUE aux 1020/1062 valides live ; deep-read RE exclut tout gap base/hits). Flag : non live-confronte. |
| PsychicMaelstrom (1027) | astraPrimarisPsy | **Nullable(BasiliskBarrage.GetDamageProfile)** EXPLICITE @181153c50 (PAS null) | avg@181153c1e | **OK bit-exact [2792,4188]** | PAS un candidat null (mis-audit) ; live OK -> **AUCUN override**. |
| SorcerousFacade (1100) | thousTzaangor | null@18115c1a0 | **Half(Sum(var0xc,var0xd)) DSL @18115bf7c != avg** | pas de fire (SelectFirst=0) | gap BASE -> **tache #171** (pas override). |
| DaemonicOrdnance (1148) | blackForgefiend (MoW) | null@181128fea | **DaemonicOrdnanceAbility.GetDamage getter dedie != avg** | build non-Running (MoW) | gap BASE -> **tache #172**. |
| HadesAutocannons (1147) | blackForgefiend (MoW) | null@181140d4a | **LightOfSanguiniusAbility.GetDamage getter dedie != avg** | build non-Running (MoW) | gap BASE -> **tache #172**. |
| HellfireShells (1080) | NPC/summon only | null | **Direct(var0xc) DSL != avg + hits trait-cond (HasTrait 0x3f9)** | non buildable (NPC) | gap BASE+HITS -> **tache #173** (basse prio). |

**Fix retenu #169 :** `_PLAYBOOK_PROFILE_OVERRIDE[1008] = "None"` (unique ajout ; garde predict_live 2/2 PASS).
Les 5 autres : documentes en commentaire dans `prediction.py` + taches dediees #171/#172/#173.

**Lecon #169 (renforce celle de #165) :** un audit param_8=null donne des candidats ; un DEEP-READ de la base/hits
(pas juste le param_8) + la confrontation live tranchent. Ici le deep-read RE a (a) INVALIDE 1 candidat (PsychicMaelstrom
= profil explicite, mis-audit d'arite), (b) revele que 4/6 ont une BASE non-avg (formules DSL Half(Sum), getters dedies,
Direct(var)) que l'override pierce ne touche pas, (c) confirme 1 seul pierce-SEUL (Harbinger). Quand la base est
prouvee=avg ET hits=config par lecture (pas suppose), l'override "None" est legitime meme sans live si le carrier est
structurellement non confrontable (`UNSPAWNABLE_FALLBACK`) — la regle "confronter live" garde contre les gaps base/hits
CACHES, ecartes ici par le deep-read.
