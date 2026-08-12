# Index des FOYERS -- projection de `docs/rl/backlog.md` pour le DISPATCH

> **GENERE. Ne pas editer a la main.**
> `python scripts/python/probe_603_index_foyers.py --index`
>
> **Ce fichier ne PROPOSE rien** : il projette les champs `FOYER:`/`BLOCAGE:` que le
> backlog PORTE. La source de verite reste `backlog.md` ; cet index est une VUE, donc
> il ne peut pas se perimer autrement que lui. Un index ecrit a la main aurait peri
> exactement comme ce qu'il documente.
>
> **A quoi il sert** : grouper deux residus dans un meme agent exige des foyers
> DISJOINTS. La famille (`#419`, `#433`...) est le MAUVAIS axe -- le foyer la
> TRAVERSE. Ci-dessous, tout foyer partage par >= 2 residus est un point de
> COLLISION : ces residus-la ne partent pas ensemble.
>
> ⚠ **Le foyer est SUR-LISTE a dessein.** Un foyer surestime refuse un appariement
> qui aurait pu passer ; un foyer sous-estime envoie deux agents sur le meme
> fichier. L'asymetrie est totale : le doute se resout du cote LARGE.

## Couverture

| | nombre |
|---|---|
| lignes de tableau OUVERTES | 421 |
| dont ANNOTEES (`FOYER:` + `BLOCAGE:`) | 418 |
| dont NON ANNOTEES | 3 |
| foyers distincts (fichiers/repertoires) | 361 |

Non annotees restantes : #120bis-spawn, #390-r1, #BL-1020r

## Points de COLLISION -- un foyer, plusieurs residus

Ces residus **ne partent pas ensemble**.

| foyer | n | residus |
|---|---|---|
| `scripts/python/engine/runner/components.py` | 12 | #287-r5-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r2, #508-r2, #547-r10, #590-r1, #919-r1, #929-r2, #951-r1, #951-r3 |
| `scripts/python/engine/runner/abilities/targeting.py` | 11 | #287-r11, #419-r1-tr14-r5-r2-r1-r2-r2, #447-r1-r1-r2, #447-r4, #547-r6, #590-r6, #895-r2, #895-r3, #907-r1, #943-r1, #946-r2 |
| `scripts/python/engine/entities/effects/factory.py` | 10 | #888-r1, #889-r6, #902-r1, #922-r1, #924-r1, #927-r2, #952-r2, #961-r3, #965-r2, #966-r4 |
| `scripts/python/engine/runner/abilities/handler.py` | 10 | #116-r, #217, #888-r1, #889-r6, #890-r3, #894-r2, #894-r3, #907-r1, #931-r1, #953-r4 |
| `scripts/python/engine/runner/operations/triggers/dispatch/registry.py` | 10 | #419-r1-tr9-r4-r1-r2-r1c, #443-r2-b2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #521-r4, #911-r1, #919-r1, #963-r3, #964-r1, #966-r4, #BL-1029r |
| `scripts/python/catalog_inject.py` | 9 | #254-bc, #254-bc-r1, #380-r1, #419-r1-tr12-r2-r1, #419-t6-r1, #433-r4-r3-r1-r3, #448-r3-r1-r1-r1, #889-r3, #914-r1 |
| `scripts/python/engine/ai/context.py` | 9 | #175-r1, #419-r1-tr11-r1, #419-r1-tr9-r1, #425-r1, #433-r4-r2-r1-r1-a-r1, #433-r4-r2-r1-r1-c-r2, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1, #433-r4-r3-r3, #957-r1 |
| `scripts/python/engine/runner/snapshot.py` | 9 | #287-r14-r2, #287-r5-r2, #448-r3-r1-r1-r1, #545-r1, #889-r3, #889-r5-r3, #922-r1, #951-r3, #961-r3 |
| `scripts/python/engine/runner/operations/damage.py` | 8 | #508-r2, #521-r8, #889-r1, #920-r1, #951-r1, #954-r2, #955-r1, #963-r2 |
| `scripts/python/engine/playbook/` | 7 | #419-r1, #419-r2, #433-r4-r3-r2, #893-r1, #909-r2, #909-r4, #940-r2 |
| `scripts/python/engine/runner/operations/triggers/loki/` | 7 | #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #521-r4, #895-r4, #911-r1, #946-r3, #964-r1, #BL-1029r |
| `scripts/python/engine/services/ability_range.py` | 7 | #419-r1-tr14-r5-r2-r1-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1, #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r2-r2-r1-r1-r1-r3, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1, #447-r1-r1-r1 |
| `scripts/python/probe_468_collision_numeros.py` | 7 | #468-r1, #468-r13, #468-r2, #468-r3, #468-r7, #468-r8, #486-r4 |
| `scripts/python/rl_duel.py` | 7 | #419-r1-tr9-r5, #448-r3-r1-r1-r1, #449-r2-r4-r1, #589-r1-r1-r2-r1-r2, #593, #605-r1, #914-r1 |
| `scripts/python/engine/entities/effects/loki/` | 6 | #433-r4-r1-r1-r1, #521-r9, #890-r3, #894-r3, #895-r4, #902-r1 |
| `scripts/python/engine/runner/abilities/attack_type.py` | 6 | #888-r1, #890-r3, #894-r2, #894-r3, #907-r1, #931-r1 |
| `scripts/python/engine/runner/operations/damage_ops/ability.py` | 6 | #488-r2, #489-r1, #512-r3, #605-r1, #889-r1, #953-r4 |
| `scripts/ratchets.ps1` | 6 | #430-r1, #430-r2, #434-r3, #457-r6, #469-r2, #486-r4 |
| `frida/hooks/features/ai-step/` | 5 | #419-r1-tr11-r2, #433-r4-r2-r1-r1-a-r1, #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r3 |
| `frida/hooks/features/observe.ts` | 5 | #287-r5-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r1, #462-r4e-o-r2-r1-r1-r1-r1, #595-r3 |
| `scripts/python/engine/entities/effects/base.py` | 5 | #175-r3, #368-r2, #389-r3, #433-r3-r2-r1, #916-r1 |
| `scripts/python/engine/runner/abilities/behaviours/effects.py` | 5 | #448-r6, #576-r2, #889-r4, #890-r2, #893-r2 |
| `scripts/python/engine/runner/operations/spawn.py` | 5 | #589-r1-r1-r2-r1-r1, #908-r2, #922-r1, #929-r2, #952-r2 |
| `scripts/python/probe_457_offline_tests_green.py` | 5 | #457-r6, #486-r21, #486-r25, #547-r3, #935-r2 |
| `scripts/python/probe_462_live_tests_status.py` | 5 | #462-r1, #462-r2, #462-r3, #462-r4, #465-r1 |
| `scripts/python/verdict_cache.py` | 5 | #486-r16, #486-r17, #486-r8, #486-r9, #943-r2 |
| `scripts/python/` | 4 | #277-r1, #486-r3, #547-r4-r1, #915-r1 |
| `scripts/python/engine/entities/effects/loki/hits.py` | 4 | #419-r1-tr9-r4-r1-r2-r1a, #419-r1-tr9-r4-r1-r2-r2, #884-r2, #949 |
| `scripts/python/engine/entities/formulas.py` | 4 | #448-r6, #894-r2, #895-r1, #964-r1 |
| `scripts/python/engine/entities/selectors/tiles.py` | 4 | #287-r11-r2-r1-r3, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r3, #550-r4, #895-r1 |
| `scripts/python/engine/runner/abilities/**` | 4 | #20, #217, #585-r1, #585-r4 |
| `scripts/python/engine/runner/abilities/behaviours/ai_control.py` | 4 | #429-r1-r1-r1-r1, #590-r5, #590-r8, #907-r1 |
| `scripts/python/engine/runner/abilities/behaviours/combat.py` | 4 | #489-r1, #512-r3, #889-r2, #890-r1 |
| `scripts/python/engine/runner/damage_model.py` | 4 | #521-r9, #920-r1, #924-r2, #965-r2 |
| `scripts/python/engine/runner/operations/damage_hits.py` | 4 | #419-r4, #433-r4-r1-r1-r1, #889-r1, #889-r2 |
| `scripts/python/engine/runner/operations/damage_ops/normal.py` | 4 | #889-r1, #924-r2, #925-r1, #965-r2 |
| `scripts/python/engine/runner/operations/movement.py` | 4 | #448-r1-r1-r3, #448-r1-r2-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5, #462-r4b-r1-r1-r1-r1-c-r3-r1-r6 |
| `scripts/python/engine/runner/operations/triggers/dispatch/core.py` | 4 | #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1, #462-r4b-r1-r1-r1-r1-c-r3-r2, #462-r4b-r1-r1-r1-r1-c-r3-r3, #937-r1 |
| `scripts/python/engine/runner/operations/turnflow.py` | 4 | #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r2, #462-r4e-o-r2-r1-r1-r1-r1, #462-r4e-o-r2-r1-r1-r1-r2, #596-r1 |
| `scripts/python/engine/services/battle_query.py` | 4 | #287-r11-r2-r1-r3, #419-r1-tr14-r4-r3, #494-r2, #910-r1 |
| `scripts/python/engine/utilities/tile.py` | 4 | #175-r1, #271-r7, #921-r1, #922-r2 |
| `scripts/python/loop_status.py` | 4 | #467-r1, #467-r5, #467-r6-a, #526-r3 |
| `scripts/python/probe_273_gitignored_inputs.py` | 4 | #464-r1b, #464-r1c, #486-r17, #486-r9 |
| `scripts/python/tests/engine/` | 4 | #277-r1, #449-r2-r4-r2, #462-r6-r2, #954-r1 |
| `frida/hooks/features/ai-step/rpc-snapshot.ts` | 3 | #347-r3, #487-r2, #545-r1 |
| `frida/hooks/features/ui-nav.ts` | 3 | #595-r1, #595-r2, #596 |
| `scripts/python/engine/battle_query.py` | 3 | #433-r4-r1-r1-r2, #894-r2, #967-r2 |
| `scripts/python/engine/entities/abilities/active_ability.py` | 3 | #585-r1, #909-r1, #957-r4 |
| `scripts/python/engine/entities/effects/aura_selectors.py` | 3 | #433-r3-r2-r1, #926-r1, #943-r4 |
| `scripts/python/engine/entities/selectors/geometry.py` | 3 | #889-r6, #894-r2, #927-r3 |
| `scripts/python/engine/entities/selectors/units.py` | 3 | #550-r3, #951-r1, #964-r1 |
| `scripts/python/engine/playbook/base.py` | 3 | #438-r1, #445-r1, #909-r2 |
| `scripts/python/engine/playbook/noncomparable/storm_speeder.py` | 3 | #967-r1, #967-r3, #967-r4 |
| `scripts/python/engine/playbook/prediction/normal_attack.py` | 3 | #419-r1-tr14-r2, #932-r2, #948-r1 |
| `scripts/python/engine/playbook/scene.py` | 3 | #932-r2, #943-r8, #948-r1 |
| `scripts/python/engine/runner/abilities/loki/attempted_possession.py` | 3 | #287-r11, #590-r6, #590-r9 |
| `scripts/python/engine/runner/abilities/loki/summon.py` | 3 | #429-r1-r1-r1-r1, #590-r5, #590-r8 |
| `scripts/python/engine/runner/abilities/tau.py` | 3 | #895-r1, #895-r3, #895-r5 |
| `scripts/python/engine/runner/operations/triggers/dispatch/move_death.py` | 3 | #929-r1, #947-r1, #955-r1 |
| `scripts/python/engine/runner/operations/triggers/loki/savage_killer.py` | 3 | #929-r1, #929-r2, #929-r4 |
| `scripts/python/engine/services/ability_caster_gates.py` | 3 | #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2, #433-r4-r2-r1-r3 |
| `scripts/python/engine/services/damage_prediction.py` | 3 | #589-r1-r1-r2-r1-r3, #884-r1, #910-r1 |
| `scripts/python/fingerprint_functions.py` | 3 | #482-r1, #482-r2, #482-r4 |
| `scripts/python/probe_486r12_declencheurs.py` | 3 | #486-r16, #486-r37, #486-r38 |
| `scripts/python/tests/engine/runner/` | 3 | #503-r2, #914-r2, #922-r2 |
| `data/seed-bc.json` | 2 | #254-bc, #392-r1 |
| `docs/**` | 2 | #283-r2, #330-r2 |
| `docs/rl/dsl-effect-nodes.md` | 2 | #330-r1, #547-r10 |
| `docs/rl/kit-coverage.md` | 2 | #909-r5, #951-r6 |
| `frida/hooks/il2cpp/` | 2 | #259-b, #389-r3 |
| `scripts/hooks/loop-status.ps1` | 2 | #467-r3, #467-r5 |
| `scripts/python/audit_kit_coverage.py` | 2 | #909-r5, #951-r6 |
| `scripts/python/declencheur_cliquet.py` | 2 | #486-r16, #486-r25 |
| `scripts/python/engine/` | 2 | #419-r1-tr9-r4-r1-r3, #485-r1-r3 |
| `scripts/python/engine/ai/action_generators.py` | 2 | #334-r3, #447-r1-r1-r3-r1 |
| `scripts/python/engine/ai/state_bridge.py` | 2 | #334-r3, #931-r2 |
| `scripts/python/engine/entities/effects/loki/dark_angels_passives.py` | 2 | #946-r1, #946-r4 |
| `scripts/python/engine/entities/effects/loki/extra_damage_aura.py` | 2 | #419-r1-tr9-r4-r1-r2-r1b, #433-r4-r1-r4-r2-r1-r1-r1-r1 |
| `scripts/python/engine/entities/effects/loki/icon_of_obstinacy.py` | 2 | #919-r1, #943-r4 |
| `scripts/python/engine/entities/effects/loki/inescapable_death.py` | 2 | #924-r1, #924-r2 |
| `scripts/python/engine/entities/pathfinding/base_pathfinder.py` | 2 | #448-r1-r1-r1-r1-r2-r1, #448-r1-r1-r1-r1-r2-r2 |
| `scripts/python/engine/entities/triggers.py` | 2 | #927-r1, #963-r1 |
| `scripts/python/engine/playbook/__init__.py` | 2 | #485-r1-r2, #485-r1-r4 |
| `scripts/python/engine/playbook/adjacent_unit_preference.py` | 2 | #921-r1, #932-r1 |
| `scripts/python/engine/playbook/non_owner.py` | 2 | #433-r4-r3-r1-r1, #433-r4-r3-r1-r2 |
| `scripts/python/engine/playbook/non_owner_attack.py` | 2 | #271-r7, #433-r4-r3-r1-r2 |
| `scripts/python/engine/playbook/noncomparable/` | 2 | #906-r1, #909-r3 |
| `scripts/python/engine/playbook/noncomparable/_base.py` | 2 | #447-r1-r1-r3-r1, #590-r7 |
| `scripts/python/engine/playbook/prediction/` | 2 | #909-r1, #910-r1 |
| `scripts/python/engine/playbook/savior_protocols.py` | 2 | #433-r4-r3-r3, #456-r2-r1 |
| `scripts/python/engine/playbook/should_execute_gates.py` | 2 | #419-r1-tr14-r5-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1 |
| `scripts/python/engine/runner/abilities/admec.py` | 2 | #894-r2, #894-r3 |
| `scripts/python/engine/runner/abilities/loki/__init__.py` | 2 | #485-r1-r2, #485-r1-r4 |
| `scripts/python/engine/runner/abilities/loki/mv71.py` | 2 | #287-r11-r2-r1-r3, #433-r4-r1-r3 |
| `scripts/python/engine/runner/abilities/repair.py` | 2 | #931-r1, #964-r1 |
| `scripts/python/engine/runner/operations/additional_hits.py` | 2 | #419-r1-tr9-r4-r3, #949 |
| `scripts/python/engine/runner/operations/attack_prediction.py` | 2 | #449-r3, #494-r2 |
| `scripts/python/engine/runner/operations/behaviour.py` | 2 | #429-r1-r3-r1-r2-r1, #BF-chance |
| `scripts/python/engine/runner/operations/change_unit_owner.py` | 2 | #590-r1, #590-r2 |
| `scripts/python/engine/runner/operations/damage_ops/normal_like.py` | 2 | #889-r1, #953-r4 |
| `scripts/python/engine/runner/operations/displace.py` | 2 | #550-r2, #550-r4 |
| `scripts/python/engine/runner/operations/effects.py` | 2 | #368-r2, #916-r1 |
| `scripts/python/engine/runner/operations/remove_effects.py` | 2 | #389-r4, #936-r1-r2 |
| `scripts/python/engine/runner/operations/summon_ai.py` | 2 | #577-r1, #907-r1 |
| `scripts/python/engine/runner/operations/triggers/dispatch/` | 2 | #590-r3, #965-r1 |
| `scripts/python/engine/runner/operations/triggers/dispatch/ability.py` | 2 | #521-r8, #929-r4 |
| `scripts/python/engine/runner/operations/triggers/genestealer.py` | 2 | #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1 |
| `scripts/python/engine/runner/operations/triggers/loki/haywire_mine.py` | 2 | #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5 |
| `scripts/python/engine/services/custom_normal_attack.py` | 2 | #419-r1-tr12-r3, #419-r1-tr14-r5-r3 |
| `scripts/python/engine/services/damage_config.py` | 2 | #449-r2-r4-r1, #449-r2-r4-r3 |
| `scripts/python/engine/services/targeting_query.py` | 2 | #433-r4-r2-r1-r2-r3, #444-r2 |
| `scripts/python/migrate_485r1_barils_reexport.py` | 2 | #485-r1-r3, #923-r1 |
| `scripts/python/probe_1210_exemplar_of_the_montka.py` | 2 | #942-r1, #942-r2 |
| `scripts/python/probe_449r2_spread_inventory.py` | 2 | #449-r2-r1, #449-r2-r3 |
| `scripts/python/probe_486r15_declencheurs_tests.py` | 2 | #486-r20, #486-r21 |
| `scripts/python/probe_486r2_usage_des_probes.py` | 2 | #486-r3, #486-r6 |
| `scripts/python/probe_547_ledger_sans_verdict_non_vert.py` | 2 | #934, #962-r1 |
| `scripts/python/probe_950_terrors_lament_tough_to_kill.py` | 2 | #950-r1, #950-r2 |
| `scripts/python/tests/conftest.py` | 2 | #455-r2, #531-r1 |
| `scripts/python/tests/engine/conftest.py` | 2 | #419-r1-tr5-r8, #531-r1 |
| `scripts/python/tests/engine/runner/test_585r1_selection_type_releve_offline.py` | 2 | #585-r1, #585-r4 |
| `scripts/python/tests/engine/runner/test_catalog_inject_offline.py` | 2 | #254-bc, #254-bc-r1 |
| `scripts/python/tests/engine/test_270r1_volet2_dict_keys_enum_offline.py` | 2 | #934, #943-r1 |
| `scripts/python/tests/engine/test_433r4r1r4r2r1r1_derivation_morte_offline.py` | 2 | #486-r7, #941-r1 |
| `scripts/python/tests/engine/test_950_terrors_lament_tough_to_kill_live.py` | 2 | #950-r1, #950-r2 |
| `scripts/python/tests/test_431_build_pin_offline.py` | 2 | #468-r6, #941-r4 |

## Foyers ISOLES -- un seul residu

Candidats naturels a un dispatch parallele, sous reserve de croiser leurs autres foyers.

| foyer | residu | blocage |
|---|---|---|
| `docs/rl/backlog.md` | #468-r5 | `aucun` |
| `docs/rl/playbook/prediction.md` | #330-r1 | `aucun` |
| `docs/rl/port-residuals-inventory.md` | #526-r3 | `aucun` |
| `docs/rl/runner-engine.md` | #330-r1 | `aucun` |
| `frida/hooks/` | #552-r2 | `capteur` |
| `frida/hooks/**` | #951-r3 | `capteur` |
| `frida/hooks/features/ai-step/projection.ts` | #419-r1-tr10-r2 | `aucun` |
| `frida/hooks/features/ai-step/rpc-*.ts` | #595-r3 | `capteur` |
| `frida/hooks/features/ai-step/rpc-nc-predict.ts` | #449-r1 | `capteur` |
| `frida/hooks/features/ai-step/rpc-targeting.ts` | #444-r1 | `capteur` |
| `frida/hooks/features/ai-step/sort-utility-trace.ts` | #419-r6-r1-r1 | `capteur` |
| `frida/hooks/features/battle-events.ts` | #596-r1 | `aucun` |
| `frida/hooks/features/bucket-audit.ts` | #475-r3 | `capteur` |
| `frida/hooks/features/modifier-observe.ts` | #475-r2 | `capteur` |
| `frida/hooks/features/movement-trace.ts` | #547-r6 | `aucun` |
| `frida/hooks/features/sim-engine.ts` | #595-r3 | `capteur` |
| `frida/hooks/features/warmup-singletons.ts` | #596-r2 | `capteur` |
| `frida/hooks/game/apply-stack.ts` | #596-r1 | `aucun` |
| `frida/hooks/game/state.ts` | #596 | `capteur` |
| `frida/hooks/il2cpp/build-pin.ts` | #475-r2 | `capteur` |
| `frida/hooks/il2cpp/invoke.ts` | #595-r2 | `capteur` |
| `frida/hooks/probes/` | #966-r2 | `capteur` |
| `frida/host/ai-trace-store.ts` | #273-r | `capteur` |
| `scripts/cliquets-cache/probe_477r24r1_slots_interface.tsv` | #943-r2 | `aucun` |
| `scripts/declencheurs-empreinte.tsv` | #486-r37 | `aucun` |
| `scripts/node/verify_portraits.mjs` | #273-r | `capteur` |
| `scripts/python/build_fingerprint_archive.py` | #482-r5 | `aucun` |
| `scripts/python/engine/ai/tactic.py` | #334-r3 | `aucun` |
| `scripts/python/engine/entities/abilities/**` | #20 | `aucun` |
| `scripts/python/engine/entities/behaviours.py` | #894-r4 | `aucun` |
| `scripts/python/engine/entities/effect_targets.py` | #366-r1-effect-targets | `aucun` |
| `scripts/python/engine/entities/effects/__init__.py` | #943-r4 | `porteur` |
| `scripts/python/engine/entities/effects/loki/amulet_of_the_voidwyrm.py` | #585-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/counter_attack.py` | #946-r3 | `aucun` |
| `scripts/python/engine/entities/effects/loki/damage_reduction.py` | #965-r2 | `etage` |
| `scripts/python/engine/entities/effects/loki/deathwing.py` | #932-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/first_among_traitors.py` | #926-r1 | `etage` |
| `scripts/python/engine/entities/effects/loki/heal_blocking.py` | #927-r2 | `porteur` |
| `scripts/python/engine/entities/effects/loki/healing_balms.py` | #966-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/possession.py` | #590-r3 | `etage` |
| `scripts/python/engine/entities/effects/loki/status.py` | #175-r3 | `etage` |
| `scripts/python/engine/entities/effects/loki/votann.py` | #959-r1 | `capteur` |
| `scripts/python/engine/entities/effects_state.py` | #936-r1-r2 | `aucun` |
| `scripts/python/engine/entities/pathfinding/fly_pathfinder.py` | #448-r1-r1-r1-r1-r2-r2 | `porteur` |
| `scripts/python/engine/entities/pathfinding/pathfinders.py` | #448-r1-r1-r1-r1-r2-r1 | `aucun` |
| `scripts/python/engine/entities/selectors/**` | #585-r1 | `aucun` |
| `scripts/python/engine/entities/selectors/accessors.py` | #967-r2 | `aucun` |
| `scripts/python/engine/entities/stats.py` | #270-r1-r1-r2 | `aucun` |
| `scripts/python/engine/entities/unit_flag.py` | #494-r2 | `aucun` |
| `scripts/python/engine/playbook/aggressive_onslaught.py` | #287-r11-r2-r1-r3 | `etage` |
| `scripts/python/engine/playbook/bespoke.py` | #957-r4 | `aucun` |
| `scripts/python/engine/playbook/common.py` | #419-r1-tr14-r5-r2-r1-r1-r2 | `porteur` |
| `scripts/python/engine/playbook/excruciating_frequencies.py` | #957-r3 | `aucun` |
| `scripts/python/engine/playbook/friends_in_range.py` | #959-r1 | `capteur` |
| `scripts/python/engine/playbook/intoxicating_elixir.py` | #922-r2 | `capteur` |
| `scripts/python/engine/playbook/loki_custom.py` | #27-r9 | `etage` |
| `scripts/python/engine/playbook/nonattack.py` | #27-r9 | `etage` |
| `scripts/python/engine/playbook/noncomparable/__init__.py` | #577-r2 | `etage` |
| `scripts/python/engine/playbook/noncomparable/adaptive_strategy.py` | #577-r2 | `etage` |
| `scripts/python/engine/playbook/noncomparable/alpha_warrior.py` | #945-r1 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/attempted_possession.py` | #590-r7 | `seeding` |
| `scripts/python/engine/playbook/noncomparable/calibanite_greatsword.py` | #945-r2 | `seeding` |
| `scripts/python/engine/playbook/noncomparable/early_warning_override.py` | #433-r4-r2-r3 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/exemplar_of_the_montka.py` | #942-r3 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/fear_of_the_unseen.py` | #957-r2 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/foehammer.py` | #957-r1 | `seeding` |
| `scripts/python/engine/playbook/noncomparable/heroic_fusillade.py` | #433-r4-r1-r4-r2-r2 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/master_of_the_tutelaries.py` | #202-r1 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/mind_control.py` | #552-r3 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/poxwalkers.py` | #17 | `etage` |
| `scripts/python/engine/playbook/obsessive_annunciation.py` | #954-r1 | `aucun` |
| `scripts/python/engine/playbook/prediction/_shared.py` | #943-r8 | `seeding` |
| `scripts/python/engine/playbook/prediction/abilities.py` | #433-r4-r1-r4-r2-r1-r1-r1-r1 | `seeding` |
| `scripts/python/engine/playbook/prophetic_sentinel.py` | #915-r2 | `porteur` |
| `scripts/python/engine/playbook/psyker.py` | #433-r4-r1-r4-r2-r1-r1-r1-r1 | `seeding` |
| `scripts/python/engine/runner/abilities/` | #419-r1-tr12-r3 | `aucun` |
| `scripts/python/engine/runner/abilities/__init__.py` | #485-r1-r4 | `aucun` |
| `scripts/python/engine/runner/abilities/aeldari.py` | #940-r1 | `capteur` |
| `scripts/python/engine/runner/abilities/astartes.py` | #448-r6 | `seeding` |
| `scripts/python/engine/runner/abilities/base.py` | #905-r1 | `aucun` |
| `scripts/python/engine/runner/abilities/behaviours/chain.py` | #894-r4 | `aucun` |
| `scripts/python/engine/runner/abilities/behaviours/context.py` | #287-r14-r2 | `seeding` |
| `scripts/python/engine/runner/abilities/blacktemplars.py` | #907-r1 | `etage` |
| `scripts/python/engine/runner/abilities/darkangels.py` | #889-r6 | `etage` |
| `scripts/python/engine/runner/abilities/deathguard.py` | #888-r1 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/healing_balms.py` | #966-r2 | `capteur` |
| `scripts/python/engine/runner/abilities/loki/mind_control.py` | #552-r2 | `capteur` |
| `scripts/python/engine/runner/abilities/loki/momentum.py` | #943-r7 | `capteur` |
| `scripts/python/engine/runner/abilities/loki/quickening.py` | #347-r1 | `capteur` |
| `scripts/python/engine/runner/abilities/loki/wall_of_mirrors.py` | #433-r4-r1-r2 | `porteur` |
| `scripts/python/engine/runner/abilities/necrons.py` | #116-r | `etage` |
| `scripts/python/engine/runner/abilities/targeting_rule_inventory.py` | #447-r1-r1-r2 | `aucun` |
| `scripts/python/engine/runner/abilities/tyranids.py` | #890-r3 | `aucun` |
| `scripts/python/engine/runner/messages.py` | #596-r1 | `aucun` |
| `scripts/python/engine/runner/operations/` | #547-r6 | `aucun` |
| `scripts/python/engine/runner/operations/damage_ops/` | #446-r3a | `porteur` |
| `scripts/python/engine/runner/operations/damage_ops/__init__.py` | #485-r1-r4 | `aucun` |
| `scripts/python/engine/runner/operations/left_over_damage.py` | #462-r4e-o-r1-r1-r1 | `porteur` |
| `scripts/python/engine/runner/operations/refresh_effects.py` | #419-r1-tr9-r4-r1-r2-r1b | `aucun` |
| `scripts/python/engine/runner/operations/remove_unit.py` | #389-r4 | `aucun` |
| `scripts/python/engine/runner/operations/revive.py` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r6 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/base.py` | #929-r4 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/dispatch/attack.py` | #521-r8 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/**` | #585-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/__init__.py` | #485-r1-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/deathwing.py` | #932-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fabricator_claw_array.py` | #927-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fire.py` | #951-r4 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fuelled_by_fury.py` | #66-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fury_of_the_ancients.py` | #927-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/grim_retribution.py` | #946-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/head_claimer.py` | #947-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/let_the_galaxy_burn.py` | #925-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/possession.py` | #955-r1 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/loki/refusal_to_be_outdone.py` | #965-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/synaptic_linchpin.py` | #937-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/pending_attack.py` | #888-r1 | `aucun` |
| `scripts/python/engine/services/damage_combat.py` | #954-r2 | `aucun` |
| `scripts/python/engine/services/damage_modifiers.py` | #437-r1-r1-r2 | `porteur` |
| `scripts/python/engine/services/static_battle_rules.py` | #419-r1-tr9-r4-r1-r2-r1a | `aucun` |
| `scripts/python/engine/streams/inform_ops.py` | #890-r1 | `aucun` |
| `scripts/python/engine/utilities/__init__.py` | #485-r1-r2 | `aucun` |
| `scripts/python/engine/utilities/damage.py` | #449-r2-r4-r3 | `porteur` |
| `scripts/python/engine/utilities/repair.py` | #271-r7 | `etage` |
| `scripts/python/game_nav.py` | #595-r1 | `capteur` |
| `scripts/python/gamenav/` | #596 | `capteur` |
| `scripts/python/gamenav/carte.py` | #596-r2 | `capteur` |
| `scripts/python/gen_ai_targets.py` | #464-r1b | `aucun` |
| `scripts/python/gen_battlelogic_targets.py` | #464-r1b | `aucun` |
| `scripts/python/gen_campaign_builder_targets.py` | #464-r1b | `aucun` |
| `scripts/python/gen_full_game_targets.py` | #464-r1b | `aucun` |
| `scripts/python/host_inputs.py` | #273-r | `capteur` |
| `scripts/python/il2cpp_metadata.py` | #486-r10 | `aucun` |
| `scripts/python/import_closure.py` | #486-r17 | `aucun` |
| `scripts/python/mcp_ghidra.py` | #594 | `aucun` |
| `scripts/python/migrate_270r4r2r2_hisser_differes.py` | #923-r1 | `aucun` |
| `scripts/python/probe_*.py` | #949-r1 | `aucun` |
| `scripts/python/probe_116_necrons.py` | #419-r1-tr5-r8 | `capteur` |
| `scripts/python/probe_202r_decision_abraxas.py` | #202-r1 | `aucun` |
| `scripts/python/probe_229_effect_triggers_active.py` | #426-r1 | `aucun` |
| `scripts/python/probe_230_load_state_turn_state.py` | #462-r4c-r2 | `aucun` |
| `scripts/python/probe_242_fabricator_claw_cap.py` | #462-r4c-r1-r1 | `aucun` |
| `scripts/python/probe_249_unported_rule_carriers.py` | #426-r1 | `aucun` |
| `scripts/python/probe_259_gshared_coverage.py` | #259-a | `capteur` |
| `scripts/python/probe_262_gshared_runtime.py` | #259-b | `capteur` |
| `scripts/python/probe_271_kustom_force_field_reworked.py` | #271-r1 | `aucun` |
| `scripts/python/probe_271r4_face_attack_live.py` | #271-r8 | `aucun` |
| `scripts/python/probe_281_pre_unit_ability_shortcut.py` | #281-r4 | `aucun` |
| `scripts/python/probe_283_enum_ordinal_sweep.py` | #426-r1 | `aucun` |
| `scripts/python/probe_287r5_etages_bloquants.py` | #287-r11 | `seeding` |
| `scripts/python/probe_350r3a_r4_comparable_gate.py` | #350-r3a-r4-r1 | `aucun` |
| `scripts/python/probe_365_versioned_imports_gitignored.py` | #462-r4c-r3 | `aucun` |
| `scripts/python/probe_366_r1_bcpatch_port_blindspot.py` | #484-r1 | `aucun` |
| `scripts/python/probe_366r1_*.py` | #366-r1-chaos-friendly-fire | `porteur` |
| `scripts/python/probe_389r2_kill_unit_remove_effects.py` | #389-r5 | `aucun` |
| `scripts/python/probe_419r1tr10r2_multi_tuiles_canal.py` | #419-r1-tr10-r2 | `aucun` |
| `scripts/python/probe_419r1tr12r2_stats_npc_summon.py` | #419-r1-tr12-r2-r2 | `porteur` |
| `scripts/python/probe_419r6r1_face_decision.py` | #419-r6-r1-r1 | `capteur` |
| `scripts/python/probe_419r6r1r1_sort_utility_trace.py` | #419-r6-r1-r1 | `capteur` |
| `scripts/python/probe_429r1_bit_readers_scan.py` | #429-r1-r2 | `aucun` |
| `scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py` | #429-r1-r3-r1-r2-r1 | `aucun` |
| `scripts/python/probe_433_r4_r2_r4_r1_contre_epreuves.py` | #433-r4-r2-r4-r1-r1 | `aucun` |
| `scripts/python/probe_433r4r1r4r2_is_adjacent_substrat_live.py` | #433-r4-r1-r4-r2-r3 | `aucun` |
| `scripts/python/probe_433r4r1r4r2_neigh_channel_wired.py` | #433-r4-r1-r4-r2-r1-r1-r1-r1 | `seeding` |
| `scripts/python/probe_433r4r1r4r2r4_aval_decision_live.py` | #433-r4-r1-r4-r2-r4-r1 | `aucun` |
| `scripts/python/probe_437r1_overwatch_offbyone.py` | #437-r1-r1-r3 | `aucun` |
| `scripts/python/probe_437r1r1r1_effect_face_table.py` | #437-r1-r1-r1-r1 | `aucun` |
| `scripts/python/probe_440_repo_root_scan_guard.py` | #468-r6 | `aucun` |
| `scripts/python/probe_448_r3_r1_r1_greffe_sans_canal.py` | #941-r2 | `aucun` |
| `scripts/python/probe_449r2r4r4_bc_damage_fields.py` | #449-r2-r4-r4-r1 | `aucun` |
| `scripts/python/probe_455_all_skipped_file.py` | #455-r1 | `aucun` |
| `scripts/python/probe_455r4_resilient_window.py` | #455-r4-r1 | `aucun` |
| `scripts/python/probe_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable.py` | #485-r1-r1-r2 | `aucun` |
| `scripts/python/probe_467r4_contrat_host.py` | #467-r4-a | `aucun` |
| `scripts/python/probe_475_pinned_addresses.py` | #475-r1 | `aucun` |
| `scripts/python/probe_477r24r1_slots_interface.py` | #941-r2 | `aucun` |
| `scripts/python/probe_477r25_slots_autres_interfaces.py` | #433-r3-r3-r2 | `aucun` |
| `scripts/python/probe_485_imports_differes.py` | #486-r17 | `aucun` |
| `scripts/python/probe_487_hellfyre_missile_rack.py` | #487-r2 | `capteur` |
| `scripts/python/probe_488r1_onmelta_vivant.py` | #488-r2 | `aucun` |
| `scripts/python/probe_498_unstoppable_momentum.py` | #498-r5 | `aucun` |
| `scripts/python/probe_503_generalisation.py` | #503-r2 | `porteur` |
| `scripts/python/probe_510_light_of_sanguinius_live.py` | #510-r3 | `aucun` |
| `scripts/python/probe_511_strike_from_the_shadows.py` | #511-r1 | `aucun` |
| `scripts/python/probe_519_temoins_de_camp.py` | #519-r1 | `aucun` |
| `scripts/python/probe_523r1_heavy_warp_flamer_tracking.py` | #523-r3 | `aucun` |
| `scripts/python/probe_526r2_fraicheur_backlog.py` | #526-r3 | `aucun` |
| `scripts/python/probe_547r1_mesure_missing_non_verdict.py` | #547-r9 | `aucun` |
| `scripts/python/probe_585r1_mutants.py` | #585-r4 | `aucun` |
| `scripts/python/probe_589r1r1r2r1_amulet_crit_reduction_live.py` | #589-r1-r1-r2-r1-r2 | `aucun` |
| `scripts/python/probe_594_ctor_litteraux.py` | #594 | `aucun` |
| `scripts/python/probe_889_lions_wrath.py` | #889-r4 | `aucun` |
| `scripts/python/probe_902_reanimator.py` | #902-r2 | `seeding` |
| `scripts/python/probe_909_decision_actives_kit.py` | #909-r4 | `aucun` |
| `scripts/python/probe_915_prophetic_sentinel.py` | #915-r3 | `aucun` |
| `scripts/python/probe_928_legacy_of_combat.py` | #928-r1 | `aucun` |
| `scripts/python/probe_939_bio_minefield.py` | #939-r1 | `etage` |
| `scripts/python/probe_953_954_skullsmasher_obsessive_annunciation.py` | #953-r1 | `aucun` |
| `scripts/python/probe_956_purete_de_passe.py` | #956-r1 | `aucun` |
| `scripts/python/probe_966_healing_balms_short_blade.py` | #966-r3 | `aucun` |
| `scripts/python/prototype_485r1_registre_explicite.py` | #485-r1-r2 | `aucun` |
| `scripts/python/rl_collect_batch.py` | #961-r2 | `aucun` |
| `scripts/python/rl_gen_enum_columns.py` | #270-b | `aucun` |
| `scripts/python/rl_gen_ref_tables.py` | #270-b | `aucun` |
| `scripts/python/targeting_reason.py` | #447-r2 | `aucun` |
| `scripts/python/tests/` | #486-r20 | `aucun` |
| `scripts/python/tests/engine/**/*_live.py` | #949-r1 | `aucun` |
| `scripts/python/tests/engine/runner/conftest.py` | #531-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_1210_exemplar_of_the_montka_offline.py` | #942-r2 | `aucun` |
| `scripts/python/tests/engine/runner/test_287r14_get_actual_target_offline.py` | #934 | `aucun` |
| `scripts/python/tests/engine/runner/test_894_arc_scourge_offline.py` | #894-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_928_legacy_of_combat_live.py` | #928-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_939_bio_minefield_offline.py` | #939-r1 | `etage` |
| `scripts/python/tests/engine/runner/test_946_unwavering_sentinel_live.py` | #946-r2 | `porteur` |
| `scripts/python/tests/engine/runner/test_ability_registry_ratchet.py` | #941-r3 | `aucun` |
| `scripts/python/tests/engine/runner/test_foehammer_live.py` | #281-r4 | `aucun` |
| `scripts/python/tests/engine/runner/test_harlequins_panoply_live.py` | #933-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_heroic_fusillade_migration_live.py` | #933-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_pick_randomly_one_rng_live.py` | #462-r4 | `aucun` |
| `scripts/python/tests/engine/test_270r4r2r2_differes_offline.py` | #484-r2 | `aucun` |
| `scripts/python/tests/engine/test_270r4r2r2r3_gardes_du_hissage_offline.py` | #486-r7 | `aucun` |
| `scripts/python/tests/engine/test_287r4r1_dynamic_target_rules_offline.py` | #941-r1 | `aucun` |
| `scripts/python/tests/engine/test_477r24r1_slots_interface_offline.py` | #941-r1 | `aucun` |
| `scripts/python/tests/engine/test_953_954_skullsmasher_obsessive_annunciation_live.py` | #953-r1 | `aucun` |
| `scripts/python/tests/engine/test_953r2_preattack_place_live.py` | #962-r1 | `aucun` |
| `scripts/python/tests/engine/test_957_decision_faces_offline.py` | #957-r2 | `porteur` |
| `scripts/python/tests/test_457_r5_perimetre_offline.py` | #463-r2 | `aucun` |
| `scripts/python/tests/test_465_ledger_validite_offline.py` | #941-r4 | `aucun` |
| `scripts/python/tests/test_474_optional_locks_offline.py` | #941-r2 | `aucun` |
| `scripts/python/tests/test_951r2_voies_de_couverture_offline.py` | #951-r5 | `aucun` |
| `scripts/python/tests/test_956_purete_de_passe_offline.py` | #956-r1 | `aucun` |
| `scripts/ratchets-457-footprints.json` | #935-r2 | `aucun` |
| `scripts/ratchets-468-numeros-attestes.json` | #468-r5 | `aucun` |
| `scripts/ratchets-951r2-couverture-attestee.json` | #951-r5 | `aucun` |
| `scripts/sql/006_ref_tables.sql` | #270-b | `aucun` |

## Par BLOCAGE

Un residu `capteur` ne part pas tant qu'aucune fenetre de reinject n'est prevue.

| blocage | n | residus |
|---|---|---|
| `capteur` | 40 | #259-a, #259-b, #273-r, #287-r5-r2, #347-r1, #347-r3, #389-r3, #419-r1-tr11-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #419-r1-tr5-r8, #419-r6-r1-r1, #433-r4-r2-r1-r1-a-r1, #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r3, #444-r1, #449-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r1, #462-r4e-o-r2-r1-r1-r1-r1, #462-r4e-o-r2-r1-r1-r1-r2, #475-r2, #475-r3, #487-r2, #545-r1, #552-r2, #590-r2, #590-r5, #595-r1, #595-r2, #595-r3, #596, #596-r2, #916-r1, #922-r2, #940-r1, #943-r7, #951-r3, #959-r1, #961-r3, #966-r2 |
| `seeding` | 27 | #287-r11, #287-r14-r2, #392-r1, #419-r1-tr9-r1, #433-r4-r1-r4-r2-r1-r1-r1-r1, #433-r4-r2-r1-r2-r3, #447-r1-r1-r3-r1, #448-r3-r1-r1-r1, #448-r6, #449-r2-r4-r1, #482-r1, #590-r1, #590-r7, #889-r3, #889-r5-r3, #890-r4, #902-r2, #911-r1, #921-r1, #929-r2, #929-r4, #943-r8, #945-r2, #951-r1, #955-r1, #957-r1, #BF-chance |
| `etage` | 47 | #116-r, #17, #175-r1, #175-r3, #27-r9, #271-r7, #287-r11-r2-r1-r3, #368-r2, #419-r1-tr12-r2-r1, #419-r4, #433-r3-r2-r1, #433-r4-r1-r1-r1, #433-r4-r1-r1-r2, #433-r4-r1-r3, #433-r4-r3-r1-r2, #443-r2-b2, #444-r2, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1, #508-r2, #577-r2, #590-r3, #590-r6, #590-r8, #889-r2, #889-r6, #893-r1, #894-r2, #895-r4, #902-r1, #907-r1, #919-r1, #924-r1, #924-r2, #926-r1, #929-r1, #939-r1, #940-r2, #946-r1, #946-r4, #947-r1, #964-r1, #965-r1, #965-r2, #966-r4, #967-r1, #967-r3 |
| `porteur` | 46 | #366-r1-chaos-friendly-fire, #419-r1-tr12-r2-r2, #419-r1-tr12-r4, #419-r1-tr14-r2, #419-r1-tr14-r4-r3, #419-r1-tr14-r5-r2-r1-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1, #419-r1-tr14-r5-r2-r1-r2-r1-r3, #419-r1-tr14-r5-r3, #419-r1-tr9-r4-r1-r2-r2, #419-r2, #419-t6-r1, #425-r1, #433-r4-r1-r2, #433-r4-r2-r1-r2-r2-r1-r1-r1-r3, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2, #437-r1-r1-r2, #445-r1, #446-r3a, #447-r1-r1-r1, #447-r3, #448-r1-r1-r1-r1-r2-r2, #448-r1-r2-r1, #449-r2-r4-r3, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4, #462-r4b-r1-r1-r1-r1-c-r3-r2, #462-r4e-o-r1-r1-r1, #465-r1, #503-r2, #521-r4, #550-r2, #884-r2, #895-r1, #915-r2, #927-r2, #942-r1, #943-r4, #945-r1, #945-r3, #946-r2, #950-r1, #952-r2, #953-r4, #957-r2, #967-r5 |
| `aucun` | 258 | #20, #202-r1, #217, #254-bc, #254-bc-r1, #270-a, #270-b, #270-r1-r1-r2, #271-r1, #271-r8, #277-r1, #281-r4, #283-r2, #330-r1, #330-r2, #334-r3, #350-r3a-r4-r1, #352-r1, #366-r1-effect-targets, #369, #380-r1, #389-r4, #389-r5, #419-r1, #419-r1-tr10-r2, #419-r1-tr11-r1, #419-r1-tr12-r3, #419-r1-tr14-r5-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r2-r2, #419-r1-tr14-r5-r2-r1-r2-r3, #419-r1-tr9-r4-r1-r2-r1a, #419-r1-tr9-r4-r1-r2-r1b, #419-r1-tr9-r4-r1-r2-r1c, #419-r1-tr9-r4-r1-r3, #419-r1-tr9-r4-r3, #419-r1-tr9-r5, #420-r4, #426-r1, #429-r1-r1-r1-r1, #429-r1-r2, #429-r1-r3-r1-r2-r1, #430-r1, #430-r2, #433-r3-r3-r2, #433-r4-r1-r4-r2-r2, #433-r4-r1-r4-r2-r3, #433-r4-r1-r4-r2-r4-r1, #433-r4-r2-r1-r1-c-r2, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1, #433-r4-r2-r3, #433-r4-r2-r4-r1-r1, #433-r4-r3-r1-r1, #433-r4-r3-r1-r3, #433-r4-r3-r2, #433-r4-r3-r3, #434-r3, #437-r1-r1-r1-r1, #437-r1-r1-r3, #438-r1, #447-r1-r1-r2, #447-r2, #447-r4, #448-r1-r1-r1-r1-r2-r1, #448-r1-r1-r3, #449-r2-r1, #449-r2-r3, #449-r2-r4-r2, #449-r2-r4-r4-r1, #449-r3, #455-r1, #455-r2, #455-r4-r1, #456-r2-r1, #457-r6, #462-r1, #462-r2, #462-r3, #462-r4, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r3, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5, #462-r4b-r1-r1-r1-r1-c-r3-r1-r6, #462-r4b-r1-r1-r1-r1-c-r3-r3, #462-r4c-r1-r1, #462-r4c-r1-r2, #462-r4c-r2, #462-r4c-r3, #462-r6-r1, #462-r6-r2, #463-r2, #464-r1b, #464-r1c, #467-r1, #467-r3, #467-r4-a, #467-r5, #467-r6-a, #468-r1, #468-r13, #468-r2, #468-r3, #468-r5, #468-r6, #468-r7, #468-r8, #469-r1, #469-r2, #469-r4, #471-r1, #471-r2, #475-r1, #482-r2, #482-r4, #482-r5, #482-r6, #484-r1, #484-r2, #485-r1-r1-r2, #485-r1-r2, #485-r1-r3, #485-r1-r4, #486-r10, #486-r16, #486-r17, #486-r20, #486-r21, #486-r25, #486-r26, #486-r3, #486-r37, #486-r38, #486-r4, #486-r6, #486-r7, #486-r8, #486-r9, #488-r2, #489-r1, #494-r2, #498-r5, #5, #510-r3, #511-r1, #512-r3, #519-r1, #521-r8, #521-r9, #523-r3, #526-r3, #531-r1, #547-r10, #547-r3, #547-r4-r1, #547-r6, #547-r9, #550-r3, #550-r4, #552-r3, #576-r2, #577-r1, #585-r1, #585-r2, #585-r4, #589-r1-r1-r2-r1-r1, #589-r1-r1-r2-r1-r2, #589-r1-r1-r2-r1-r3, #590-r9, #593, #594, #596-r1, #605-r1, #66-r2, #884-r1, #888-r1, #889-r1, #889-r4, #890-r1, #890-r2, #890-r3, #893-r2, #894-r1, #894-r3, #894-r4, #894-r5, #895-r2, #895-r3, #895-r5, #905-r1, #906-r1, #908-r1, #908-r2, #909-r1, #909-r2, #909-r3, #909-r4, #909-r5, #910-r1, #914-r1, #914-r2, #915-r1, #915-r3, #919-r2, #919-r3, #920-r1, #922-r1, #923-r1, #925-r1, #927-r1, #927-r3, #928-r1, #931-r1, #931-r2, #932-r1, #932-r2, #933-r1, #934, #935-r2, #936-r1-r2, #937-r1, #941-r1, #941-r2, #941-r3, #941-r4, #942-r2, #942-r3, #943-r1, #943-r2, #946-r3, #948-r1, #949, #949-r1, #950-r2, #951-r4, #951-r5, #951-r6, #953-r1, #954-r1, #954-r2, #956-r1, #957-r3, #957-r4, #961-r1, #961-r2, #962-r1, #963-r1, #963-r2, #963-r3, #966-r1, #966-r3, #967-r2, #967-r4, #BL-1029r, #haze-ord, #o10-c |

## Foyers qui ne designent AUCUN fichier

`aucun` = residu d'arbitrage ou de mesure, rien a editer.
`?` = la fiche dit elle-meme que le foyer depend d'une mesure NON FAITE : c'est un
resultat, pas un abandon. Ces residus se dispatchent SANS contrainte de disjonction
(`aucun`) ou APRES la mesure qui les determine (`?`).

| valeur | n | residus |
|---|---|---|
| `?` (declencheur non etabli, non reproduit sur le 2e couple) —` | 1 | #o10-c |
| `?` (les 15 sites ne sont pas listes ici ; a re-deriver par `--step prose -v`) —` | 1 | #420-r4 |
| `?` --` | 2 | #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2, #471-r1 |
| `aucun` | 3 | #890-r4, #919-r2, #919-r3 |
| `aucun (attribution ; outillage livre = probe_961r1_attribution.py + regime range2_flat)` | 1 | #961-r1 |
| `aucun (montage ; tests live a ecrire)` | 1 | #967-r5 |
| `aucun<br>` | 1 | #5 |
| `aucun` --` | 11 | #419-r1-tr12-r4, #419-r1-tr14-r5-r2-r1-r2-r1-r3, #447-r3, #462-r4c-r1-r2, #462-r6-r1, #469-r1, #469-r4, #471-r2, #482-r6, #894-r5, #908-r1 |
| `aucun` —` | 4 | #270-a, #352-r1, #369, #haze-ord |
| `docs/` --` | 1 | #419-r1-tr14-r5-r2-r1-r2-r3 |
| `les fichiers de test touches, un par un --` | 1 | #486-r26 |

## Foyers qui designent un fichier A CREER

Absents de l'arbre courant et **jamais** presents dans l'historique : ce sont des
fichiers que la tranche ECRIRA (mirror neuf, probe a monter). Ils comptent comme
foyer pour la disjonction. Un chemin absent qui, LUI, a existe serait un foyer
POURRI -- `test_603_index_foyers_offline.py` etage 3 le refuse.

| chemin | residus |
|---|---|
| `**3/3` | #585-r1 |
| `4/4` | #585-r1 |
| `AURA/de` | #943-r7 |
| `data/unspawnable_rank17.json` | #961-r2 |
| `effects/__init__.py` | #943-r7 |
| `engine/playbook/sanguinary_priest.py` | #921-r1 |
| `engine/utilities/devout_push.py` | #907-r1 |
| `noncomparable/get_em_runtz.py` | #943-r7 |
| `prediction/abilities.py` | #943-r7 |
| `scripts/python/engine/entities/effects/loki/lifewards.py` | #963-r3 |
| `scripts/python/engine/entities/effects/loki/the_lantern.py` | #888-r1 |
| `scripts/python/engine/entities/effects/loki/way_of_the_short_blade.py` | #966-r4 |
| `scripts/python/engine/playbook/noncomparable/war_howl.py` | #585-r2 |
| `scripts/python/engine/playbook/registry.py` | #585-r2 |
| `scripts/python/engine/runner/operations/triggers/loki/lifewards.py` | #963-r3 |
| `scripts/python/engine/runner/operations/triggers/loki/the_lantern_attack.py` | #888-r1 |
| `scripts/python/engine/runner/operations/triggers/loki/way_of_the_short_blade.py` | #966-r4 |
| `scripts/python/probe_273_gitignore_inputs.py` | #547-r6 |
| `scripts/python/probe_419r1tr14r5r2r1r1r1r3_gates.py` | #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1 |
| `scripts/python/probe_945_adaptive_strategy.py` | #945-r3 |
| `scripts/python/tests/engine/test_966_healing_balms_combat_live.py` | #966-r3 |
| `traits/combat.py` | #943-r7 |
| `triggers/loki/icon_of_obstinacy.py` | #943-r7 |

