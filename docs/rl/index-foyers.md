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
| lignes de tableau OUVERTES | 468 |
| dont ANNOTEES (`FOYER:` + `BLOCAGE:`) | 465 |
| dont NON ANNOTEES | 3 |
| foyers distincts (fichiers/repertoires) | 415 |

Non annotees restantes : #120bis-spawn, #390-r1, #BL-1020r

## Points de COLLISION -- un foyer, plusieurs residus

Ces residus **ne partent pas ensemble**.

| foyer | n | residus |
|---|---|---|
| `scripts/python/engine/runner/operations/triggers/dispatch/registry.py` | 13 | #1001-r1, #1002-r1, #1019-r2, #1020-r5, #1074, #419-r1-tr9-r4-r1-r2-r1c, #443-r2-b2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #521-r4, #911-r1, #963-r3, #999-r1, #BL-1029r |
| `scripts/python/engine/runner/snapshot.py` | 10 | #287-r14-r2, #287-r5-r2, #448-r3-r1-r1-r1, #545-r1, #889-r3, #889-r5-r3, #922-r1, #961-r3, #987-r1, #999-r3-r2 |
| `scripts/python/catalog_inject.py` | 9 | #254-bc, #254-bc-r1, #380-r1, #419-r1-tr12-r2-r1, #419-t6-r1, #433-r4-r3-r1-r3, #448-r3-r1-r1-r1, #889-r3, #914-r1 |
| `scripts/python/rl_duel.py` | 9 | #1044-r1, #237-r1, #419-r1-tr9-r5, #448-r3-r1-r1-r1, #449-r2-r4-r1, #589-r1-r1-r2-r1-r2, #593, #605-r1, #914-r1 |
| `frida/hooks/features/ai-step/rpc-snapshot.ts` | 8 | #1036-r8, #1039-r1, #287-r5-r2, #347-r3, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #487-r2, #545-r1, #969-r4 |
| `scripts/python/engine/runner/operations/triggers/loki/` | 8 | #1078-r2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #521-r4, #895-r4, #911-r1, #946-r3, #999-r1, #BL-1029r |
| `scripts/python/engine/entities/effects/factory.py` | 7 | #1078-r3, #922-r1, #924-r1, #952-r2, #961-r3, #965-r2, #999-r1 |
| `scripts/python/engine/runner/abilities/handler.py` | 7 | #1022-r2, #116-r, #217, #890-r3, #894-r2, #894-r3, #953-r4 |
| `scripts/python/probe_468_collision_numeros.py` | 7 | #468-r1, #468-r13, #468-r2, #468-r3, #468-r7, #468-r8, #486-r4 |
| `scripts/python/engine/entities/effects/loki/` | 6 | #1078-r3, #433-r4-r1-r1-r1, #521-r9, #890-r3, #894-r3, #895-r4 |
| `scripts/python/engine/runner/components.py` | 6 | #287-r5-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1, #508-r2, #590-r1, #929-r2 |
| `scripts/python/engine/runner/damage_model.py` | 6 | #1036-r7, #1042-r5, #1078-r3, #521-r9, #924-r2, #965-r2 |
| `scripts/python/engine/services/ability_range.py` | 6 | #419-r1-tr14-r5-r2-r1-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1, #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r2-r2-r1-r1-r1-r3, #447-r1-r1-r1 |
| `scripts/ratchets.ps1` | 6 | #430-r1, #430-r2, #434-r3, #457-r6, #469-r2, #486-r4 |
| `scripts/python/` | 5 | #1064-r1, #277-r1, #486-r3, #547-r4-r1, #915-r1 |
| `scripts/python/engine/ai/state_bridge.py` | 5 | #1015-r4, #1079-r1, #334-r3, #419-r1-tr9-r1, #977-r7 |
| `scripts/python/engine/entities/effects/base.py` | 5 | #1008-r2, #175-r3, #368-r2, #389-r3, #433-r3-r2-r1 |
| `scripts/python/engine/entities/effects/loki/hits.py` | 5 | #1015-r5, #419-r1-tr9-r4-r1-r2-r1a, #419-r1-tr9-r4-r1-r2-r2, #884-r2, #943-r7 |
| `scripts/python/engine/entities/selectors/geometry.py` | 5 | #1027-r1, #1032-r2, #1078-r1, #894-r2, #927-r3 |
| `scripts/python/engine/entities/selectors/tiles.py` | 5 | #1022-r2, #287-r11-r2-r1-r3, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r3, #550-r4, #895-r1 |
| `scripts/python/engine/runner/abilities/targeting.py` | 5 | #1022-r2, #287-r11, #547-r6, #590-r6, #946-r2 |
| `scripts/python/engine/runner/operations/damage.py` | 5 | #1025-r2, #508-r2, #521-r8, #951-r1, #955-r1 |
| `scripts/python/engine/runner/operations/damage_hits.py` | 5 | #419-r4, #433-r4-r1-r1-r1, #889-r2, #920-r3, #965-r2 |
| `scripts/python/engine/runner/operations/damage_ops/ability.py` | 5 | #488-r2, #489-r1, #512-r3, #605-r1, #953-r4 |
| `scripts/python/engine/runner/operations/spawn.py` | 5 | #589-r1-r1-r2-r1-r1, #908-r2, #922-r1, #929-r2, #952-r2 |
| `scripts/python/engine/runner/operations/triggers/dispatch/core.py` | 5 | #1045-r2, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1, #462-r4b-r1-r1-r1-r1-c-r3-r2, #462-r4b-r1-r1-r1-r1-c-r3-r3, #937-r1 |
| `scripts/python/engine/services/damage_prediction.py` | 5 | #1013-r1, #589-r1-r1-r2-r1-r3, #884-r1, #910-r1, #920-r3 |
| `scripts/python/probe_457_offline_tests_green.py` | 5 | #457-r6, #486-r21, #486-r25, #547-r3, #935-r2 |
| `scripts/python/probe_462_live_tests_status.py` | 5 | #462-r1, #462-r2, #462-r3, #462-r4, #465-r1 |
| `scripts/python/tests/engine/` | 5 | #277-r1, #449-r2-r4-r2, #462-r6-r2, #940-r3, #954-r1 |
| `scripts/python/tests/engine/runner/` | 5 | #1005-r2, #1015-r3, #1038-r2, #503-r2, #922-r2 |
| `scripts/python/verdict_cache.py` | 5 | #486-r16, #486-r17, #486-r8, #486-r9, #943-r2 |
| `frida/hooks/features/ai-step/` | 4 | #419-r1-tr11-r2, #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r3 |
| `scripts/python/engine/ai/context.py` | 4 | #1027-r5, #1079-r1, #419-r1-tr9-r1, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1 |
| `scripts/python/engine/entities/effects/__init__.py` | 4 | #1008-r2, #1019-r1, #943-r4, #943-r7 |
| `scripts/python/engine/entities/effects/aura_selectors.py` | 4 | #1074, #433-r3-r2-r1, #926-r1, #943-r4 |
| `scripts/python/engine/entities/effects/loki/extra_damage_aura.py` | 4 | #1036-r7, #1042-r5, #419-r1-tr9-r4-r1-r2-r1b, #433-r4-r1-r4-r2-r1-r1-r1-r1 |
| `scripts/python/engine/entities/formulas.py` | 4 | #1008-r1, #894-r2, #895-r1, #920-r3 |
| `scripts/python/engine/entities/selectors/units.py` | 4 | #1030-r6, #1032-r2, #550-r3, #951-r1 |
| `scripts/python/engine/playbook/noncomparable/_base.py` | 4 | #447-r1-r1-r3-r1, #590-r7, #969-r1, #971-r2 |
| `scripts/python/engine/playbook/prediction/normal_attack.py` | 4 | #1036-r7, #1078-r3, #419-r1-tr14-r2, #932-r2 |
| `scripts/python/engine/playbook/scene.py` | 4 | #1011-r2, #425-r1, #932-r2, #953-r5 |
| `scripts/python/engine/runner/abilities/**` | 4 | #20, #217, #585-r1, #585-r4 |
| `scripts/python/engine/runner/abilities/attack_type.py` | 4 | #1022-r2, #890-r3, #894-r2, #894-r3 |
| `scripts/python/engine/runner/abilities/behaviours/combat.py` | 4 | #1030-r4, #489-r1, #512-r3, #889-r2 |
| `scripts/python/engine/runner/abilities/behaviours/context.py` | 4 | #1008-r1, #1027-r1, #287-r14-r2, #999-r3-r2 |
| `scripts/python/engine/runner/operations/movement.py` | 4 | #448-r1-r1-r3, #448-r1-r2-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5, #462-r4b-r1-r1-r1-r1-c-r3-r1-r6 |
| `scripts/python/engine/services/battle_query.py` | 4 | #287-r11-r2-r1-r3, #419-r1-tr14-r4-r3, #494-r2, #910-r1 |
| `scripts/python/engine/services/damage_modifiers.py` | 4 | #1011-r2, #1019-r1, #437-r1-r1-r2, #920-r3 |
| `scripts/python/engine/utilities/tile.py` | 4 | #175-r1, #271-r7, #425-r1, #922-r2 |
| `scripts/python/loop_status.py` | 4 | #467-r1, #467-r5, #467-r6-a, #526-r3 |
| `scripts/python/probe_273_gitignored_inputs.py` | 4 | #464-r1b, #464-r1c, #486-r17, #486-r9 |
| `frida/hooks/features/ui-nav.ts` | 3 | #595-r1, #595-r2, #596 |
| `scripts/python/engine/battle_query.py` | 3 | #433-r4-r1-r1-r2, #894-r2, #971-r1 |
| `scripts/python/engine/entities/abilities/active_ability.py` | 3 | #585-r1, #909-r1, #957-r4 |
| `scripts/python/engine/entities/triggers.py` | 3 | #1008-r3, #1009-r3, #927-r1 |
| `scripts/python/engine/entities/unit_context.py` | 3 | #1036-r3, #1036-r8, #987-r1 |
| `scripts/python/engine/playbook/` | 3 | #419-r1, #419-r2, #433-r4-r3-r2 |
| `scripts/python/engine/playbook/__init__.py` | 3 | #1026-r1, #485-r1-r2, #485-r1-r4 |
| `scripts/python/engine/playbook/non_owner.py` | 3 | #1036-r3, #433-r4-r3-r1-r1, #433-r4-r3-r1-r2 |
| `scripts/python/engine/playbook/non_owner_attack.py` | 3 | #1024-r7, #271-r7, #433-r4-r3-r1-r2 |
| `scripts/python/engine/playbook/noncomparable/master_of_the_tutelaries.py` | 3 | #202-r1, #971-r1, #971-r4 |
| `scripts/python/engine/runner/abilities/behaviours/effects.py` | 3 | #576-r2, #889-r4, #893-r2 |
| `scripts/python/engine/runner/abilities/loki/summon.py` | 3 | #1013-r3, #429-r1-r1-r1-r1, #590-r8 |
| `scripts/python/engine/runner/operations/turnflow.py` | 3 | #462-r4e-o-r2-r1-r1-r1-r1, #462-r4e-o-r2-r1-r1-r1-r2, #596-r1 |
| `scripts/python/engine/services/ability_caster_gates.py` | 3 | #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2, #433-r4-r2-r1-r3 |
| `scripts/python/fingerprint_functions.py` | 3 | #482-r1, #482-r2, #482-r4 |
| `scripts/python/probe_486r12_declencheurs.py` | 3 | #486-r16, #486-r37, #486-r38 |
| `data/seed-bc.json` | 2 | #254-bc, #392-r1 |
| `data/symbols/` | 2 | #590-r11, #909-r4 |
| `docs/**` | 2 | #283-r2, #330-r2 |
| `docs/rl/kit-coverage.md` | 2 | #909-r5, #951-r6 |
| `frida/hooks/features/observe.ts` | 2 | #462-r4e-o-r2-r1-r1-r1-r1, #595-r3 |
| `frida/hooks/features/ui-windows.ts` | 2 | #390-r6, #390-r7 |
| `frida/hooks/il2cpp/` | 2 | #259-b, #389-r3 |
| `scripts/hooks/loop-status.ps1` | 2 | #467-r3, #467-r5 |
| `scripts/python/audit_kit_coverage.py` | 2 | #909-r5, #951-r6 |
| `scripts/python/declencheur_cliquet.py` | 2 | #486-r16, #486-r25 |
| `scripts/python/engine/` | 2 | #419-r1-tr9-r4-r1-r3, #485-r1-r3 |
| `scripts/python/engine/ai/action_generators.py` | 2 | #334-r3, #447-r1-r1-r3-r1 |
| `scripts/python/engine/entities/effects/loki/damage_reduction.py` | 2 | #1042-r5, #965-r2 |
| `scripts/python/engine/entities/effects/loki/dark_angels_passives.py` | 2 | #946-r1, #946-r4 |
| `scripts/python/engine/entities/effects/loki/extra_damage.py` | 2 | #1005-r1, #999-r1 |
| `scripts/python/engine/entities/effects/loki/inescapable_death.py` | 2 | #924-r1, #924-r2 |
| `scripts/python/engine/entities/pathfinding/base_pathfinder.py` | 2 | #448-r1-r1-r1-r1-r2-r1, #448-r1-r1-r1-r1-r2-r2 |
| `scripts/python/engine/playbook/base.py` | 2 | #438-r1, #445-r1 |
| `scripts/python/engine/playbook/nonattack.py` | 2 | #27-r9, #969-r4 |
| `scripts/python/engine/playbook/noncomparable/` | 2 | #1033-r2, #909-r3 |
| `scripts/python/engine/playbook/noncomparable/__init__.py` | 2 | #1032-r1, #577-r2 |
| `scripts/python/engine/playbook/noncomparable/_targets.py` | 2 | #969-r4, #969-r5 |
| `scripts/python/engine/playbook/noncomparable/alpha_warrior.py` | 2 | #945-r1, #971-r1 |
| `scripts/python/engine/playbook/noncomparable/early_warning_override.py` | 2 | #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1, #433-r4-r2-r3 |
| `scripts/python/engine/playbook/noncomparable/solar_atomizer.py` | 2 | #1027-r3, #969-r5 |
| `scripts/python/engine/playbook/noncomparable/storm_speeder.py` | 2 | #967-r1, #967-r4 |
| `scripts/python/engine/playbook/noncomparable/war_howl.py` | 2 | #585-r2, #969-r1 |
| `scripts/python/engine/playbook/prediction/` | 2 | #909-r1, #910-r1 |
| `scripts/python/engine/playbook/prediction/_shared.py` | 2 | #1011-r2, #1042-r5 |
| `scripts/python/engine/playbook/prediction/abilities.py` | 2 | #1036-r7, #433-r4-r1-r4-r2-r1-r1-r1-r1 |
| `scripts/python/engine/playbook/should_execute_gates.py` | 2 | #419-r1-tr14-r5-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1 |
| `scripts/python/engine/runner/abilities/admec.py` | 2 | #894-r2, #894-r3 |
| `scripts/python/engine/runner/abilities/behaviours/ai_control.py` | 2 | #429-r1-r1-r1-r1, #590-r8 |
| `scripts/python/engine/runner/abilities/loki/__init__.py` | 2 | #485-r1-r2, #485-r1-r4 |
| `scripts/python/engine/runner/abilities/loki/attempted_possession.py` | 2 | #287-r11, #590-r6 |
| `scripts/python/engine/runner/abilities/loki/mv71.py` | 2 | #287-r11-r2-r1-r3, #433-r4-r1-r3 |
| `scripts/python/engine/runner/abilities/tau.py` | 2 | #895-r1, #895-r5 |
| `scripts/python/engine/runner/operations/additional_hits.py` | 2 | #1020-r6, #419-r1-tr9-r4-r3 |
| `scripts/python/engine/runner/operations/attack_prediction.py` | 2 | #449-r3, #494-r2 |
| `scripts/python/engine/runner/operations/behaviour.py` | 2 | #429-r1-r3-r1-r2-r1, #BF-chance |
| `scripts/python/engine/runner/operations/displace.py` | 2 | #550-r2, #550-r4 |
| `scripts/python/engine/runner/operations/effects.py` | 2 | #368-r2, #919-r1 |
| `scripts/python/engine/runner/operations/refresh_effects.py` | 2 | #419-r1-tr9-r4-r1-r2-r1b, #919-r1 |
| `scripts/python/engine/runner/operations/remove_effects.py` | 2 | #389-r4, #936-r1-r2 |
| `scripts/python/engine/runner/operations/triggers/dispatch/ability.py` | 2 | #521-r8, #929-r4 |
| `scripts/python/engine/runner/operations/triggers/dispatch/attack.py` | 2 | #1025-r2, #521-r8 |
| `scripts/python/engine/runner/operations/triggers/genestealer.py` | 2 | #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1 |
| `scripts/python/engine/runner/operations/triggers/loki/fury_of_the_ancients.py` | 2 | #1005-r3, #927-r1 |
| `scripts/python/engine/runner/operations/triggers/loki/haywire_mine.py` | 2 | #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5 |
| `scripts/python/engine/runner/operations/triggers/loki/savage_killer.py` | 2 | #929-r2, #929-r4 |
| `scripts/python/engine/services/custom_normal_attack.py` | 2 | #419-r1-tr12-r3, #419-r1-tr14-r5-r3 |
| `scripts/python/engine/services/damage_config.py` | 2 | #449-r2-r4-r1, #449-r2-r4-r3 |
| `scripts/python/engine/services/effect_bonus.py` | 2 | #1005-r1, #1033-r1 |
| `scripts/python/engine/services/targeting_query.py` | 2 | #433-r4-r2-r1-r2-r3, #444-r2 |
| `scripts/python/il2cpp_metadata.py` | 2 | #486-r10, #982-r6 |
| `scripts/python/migrate_485r1_barils_reexport.py` | 2 | #485-r1-r3, #923-r1 |
| `scripts/python/probe_1009_reliques_dark_angels.py` | 2 | #1009-r1, #1009-r2 |
| `scripts/python/probe_1021_face_decision_au_registre.py` | 2 | #1032-r1, #1033-r2 |
| `scripts/python/probe_1210_exemplar_of_the_montka.py` | 2 | #942-r1, #942-r2 |
| `scripts/python/probe_229_effect_triggers_active.py` | 2 | #1074, #426-r1 |
| `scripts/python/probe_433r4r1r4r2_neigh_channel_wired.py` | 2 | #433-r4-r1-r4-r2-r1-r1-r1-r1, #943-r7 |
| `scripts/python/probe_449r2_spread_inventory.py` | 2 | #449-r2-r1, #449-r2-r3 |
| `scripts/python/probe_486r15_declencheurs_tests.py` | 2 | #486-r20, #486-r21 |
| `scripts/python/probe_486r2_usage_des_probes.py` | 2 | #486-r3, #486-r6 |
| `scripts/python/tests/conftest.py` | 2 | #455-r2, #531-r1 |
| `scripts/python/tests/engine/conftest.py` | 2 | #419-r1-tr5-r8, #531-r1 |
| `scripts/python/tests/engine/runner/test_1009_reliques_dark_angels_live.py` | 2 | #1009-r1, #1009-r2 |
| `scripts/python/tests/engine/runner/test_585r1_selection_type_releve_offline.py` | 2 | #585-r1, #585-r4 |
| `scripts/python/tests/engine/runner/test_catalog_inject_offline.py` | 2 | #254-bc, #254-bc-r1 |
| `scripts/python/tests/test_431_build_pin_offline.py` | 2 | #468-r6, #941-r4 |

## Foyers ISOLES -- un seul residu

Candidats naturels a un dispatch parallele, sous reserve de croiser leurs autres foyers.

| foyer | residu | blocage |
|---|---|---|
| `docs/rl/backlog.md` | #468-r5 | `aucun` |
| `docs/rl/case-1046-horreurs-thousand-sons.md` | #1046-r1 | `aucun` |
| `docs/rl/dsl-effect-nodes.md` | #330-r1 | `aucun` |
| `docs/rl/playbook/prediction.md` | #330-r1 | `aucun` |
| `docs/rl/port-residuals-inventory.md` | #526-r3 | `aucun` |
| `docs/rl/runner-engine.md` | #330-r1 | `aucun` |
| `frida/hooks/` | #552-r2 | `capteur` |
| `frida/hooks/ai-toolkit/bucket-decode.ts` | #988-r1 | `aucun` |
| `frida/hooks/controller.ts` | #1064-r1 | `aucun` |
| `frida/hooks/features/ai-step/projection.ts` | #419-r1-tr10-r2 | `aucun` |
| `frida/hooks/features/ai-step/rpc-*.ts` | #595-r3 | `capteur` |
| `frida/hooks/features/ai-step/rpc-nc-predict.ts` | #449-r1 | `capteur` |
| `frida/hooks/features/ai-step/rpc-predict.ts` | #971-r3 | `capteur` |
| `frida/hooks/features/ai-step/rpc-targeting.ts` | #444-r1 | `capteur` |
| `frida/hooks/features/battle-events.ts` | #596-r1 | `aucun` |
| `frida/hooks/features/bucket-audit.ts` | #475-r3 | `capteur` |
| `frida/hooks/features/dsl-ctor-trace.ts` | #1009-r3 | `aucun` |
| `frida/hooks/features/introspect.ts` | #982-r6 | `capteur` |
| `frida/hooks/features/modifier-observe.ts` | #475-r2 | `capteur` |
| `frida/hooks/features/movement-trace.ts` | #547-r6 | `aucun` |
| `frida/hooks/features/retreat-capture.ts` | #390-r6 | `aucun` |
| `frida/hooks/features/sim-engine.ts` | #595-r3 | `capteur` |
| `frida/hooks/features/warmup-singletons.ts` | #596-r2 | `capteur` |
| `frida/hooks/game/apply-stack.ts` | #596-r1 | `aucun` |
| `frida/hooks/game/rarity.ts` | #1039-r1 | `aucun` |
| `frida/hooks/game/state.ts` | #596 | `capteur` |
| `frida/hooks/il2cpp/build-pin.ts` | #475-r2 | `capteur` |
| `frida/hooks/il2cpp/invoke.ts` | #595-r2 | `capteur` |
| `frida/hooks/probes/valid-targets-from.ts` | #1064-r1 | `aucun` |
| `frida/host/ai-trace-store.ts` | #273-r | `capteur` |
| `scripts/cliquets-cache/probe_477r24r1_slots_interface.tsv` | #943-r2 | `aucun` |
| `scripts/declencheurs-empreinte.tsv` | #486-r37 | `aucun` |
| `scripts/node/verify_portraits.mjs` | #273-r | `capteur` |
| `scripts/python/**` | #1031-r1 | `aucun` |
| `scripts/python/audit_combat_ability_coverage.py` | #1041-r1 | `aucun` |
| `scripts/python/audit_npc_registry.py` | #1021-r3 | `aucun` |
| `scripts/python/audit_passive_ability_coverage.py` | #1041-r2 | `aucun` |
| `scripts/python/build_fingerprint_archive.py` | #482-r5 | `aucun` |
| `scripts/python/engine/ai/tactic.py` | #334-r3 | `aucun` |
| `scripts/python/engine/entities/abilities/**` | #20 | `aucun` |
| `scripts/python/engine/entities/behaviours.py` | #894-r4 | `aucun` |
| `scripts/python/engine/entities/effect_targets.py` | #366-r1-effect-targets | `aucun` |
| `scripts/python/engine/entities/effects/loki/amulet_of_the_voidwyrm.py` | #585-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/counter_attack.py` | #946-r3 | `aucun` |
| `scripts/python/engine/entities/effects/loki/deathwing.py` | #932-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/first_among_traitors.py` | #926-r1 | `etage` |
| `scripts/python/engine/entities/effects/loki/helspear.py` | #1008-r2 | `etage` |
| `scripts/python/engine/entities/effects/loki/icon_of_obstinacy.py` | #943-r4 | `porteur` |
| `scripts/python/engine/entities/effects/loki/imperative.py` | #943-r7 | `seeding` |
| `scripts/python/engine/entities/effects/loki/instinctive_behaviour.py` | #1015-r2 | `aucun` |
| `scripts/python/engine/entities/effects/loki/revealed.py` | #1033-r1 | `etage` |
| `scripts/python/engine/entities/effects/loki/status.py` | #175-r3 | `etage` |
| `scripts/python/engine/entities/effects_state.py` | #936-r1-r2 | `aucun` |
| `scripts/python/engine/entities/pathfinding/fly_pathfinder.py` | #448-r1-r1-r1-r1-r2-r2 | `porteur` |
| `scripts/python/engine/entities/pathfinding/pathfinders.py` | #448-r1-r1-r1-r1-r2-r1 | `aucun` |
| `scripts/python/engine/entities/selectors/**` | #585-r1 | `aucun` |
| `scripts/python/engine/entities/stats.py` | #270-r1-r1-r2 | `aucun` |
| `scripts/python/engine/entities/traits/combat.py` | #943-r7 | `seeding` |
| `scripts/python/engine/entities/unit_flag.py` | #494-r2 | `aucun` |
| `scripts/python/engine/playbook/adjacency.py` | #948-r3 | `seeding` |
| `scripts/python/engine/playbook/adjacent_unit_preference.py` | #932-r1 | `aucun` |
| `scripts/python/engine/playbook/aggressive_onslaught.py` | #287-r11-r2-r1-r3 | `etage` |
| `scripts/python/engine/playbook/bespoke.py` | #957-r4 | `aucun` |
| `scripts/python/engine/playbook/common.py` | #419-r1-tr14-r5-r2-r1-r1-r2 | `porteur` |
| `scripts/python/engine/playbook/excruciating_frequencies.py` | #969-r5 | `porteur` |
| `scripts/python/engine/playbook/intoxicating_elixir.py` | #922-r2 | `capteur` |
| `scripts/python/engine/playbook/loki_custom.py` | #27-r9 | `etage` |
| `scripts/python/engine/playbook/noncomparable/adaptive_strategy.py` | #577-r2 | `etage` |
| `scripts/python/engine/playbook/noncomparable/attempted_possession.py` | #590-r7 | `seeding` |
| `scripts/python/engine/playbook/noncomparable/crusade_of_wrath.py` | #969-r1 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/exemplar_of_the_montka.py` | #942-r3 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/fear_of_the_unseen.py` | #957-r2 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/grot_tank.py` | #971-r4 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/heroic_fusillade.py` | #433-r4-r1-r4-r2-r2 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/ironkin_steeljack.py` | #971-r1 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/mind_control.py` | #552-r3 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/nova_shield.py` | #969-r5 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/poxwalkers.py` | #17 | `etage` |
| `scripts/python/engine/playbook/noncomparable/waaagh.py` | #971-r2 | `aucun` |
| `scripts/python/engine/playbook/obsessive_annunciation.py` | #954-r1 | `aucun` |
| `scripts/python/engine/playbook/prophetic_sentinel.py` | #915-r2 | `porteur` |
| `scripts/python/engine/playbook/psyker.py` | #433-r4-r1-r4-r2-r1-r1-r1-r1 | `seeding` |
| `scripts/python/engine/playbook/savior_protocols.py` | #456-r2-r1 | `aucun` |
| `scripts/python/engine/playbook/tile_targets.py` | #1027-r4 | `aucun` |
| `scripts/python/engine/predict.py` | #953-r5 | `aucun` |
| `scripts/python/engine/runner/abilities/` | #419-r1-tr12-r3 | `aucun` |
| `scripts/python/engine/runner/abilities/__init__.py` | #485-r1-r4 | `aucun` |
| `scripts/python/engine/runner/abilities/aeldari.py` | #940-r1 | `capteur` |
| `scripts/python/engine/runner/abilities/astramilitarum.py` | #1026-r1 | `etage` |
| `scripts/python/engine/runner/abilities/attack_query.py` | #1037-r1 | `etage` |
| `scripts/python/engine/runner/abilities/behaviours/` | #1078-r2 | `etage` |
| `scripts/python/engine/runner/abilities/behaviours/chain.py` | #894-r4 | `aucun` |
| `scripts/python/engine/runner/abilities/behaviours/grants.py` | #1022-r1 | `porteur` |
| `scripts/python/engine/runner/abilities/behaviours/stats.py` | #919-r1 | `etage` |
| `scripts/python/engine/runner/abilities/behaviours/summon.py` | #1013-r3 | `aucun` |
| `scripts/python/engine/runner/abilities/behaviours/turnflow.py` | #1020-r5 | `etage` |
| `scripts/python/engine/runner/abilities/darkangels.py` | #1022-r2 | `etage` |
| `scripts/python/engine/runner/abilities/deathguard.py` | #1030-r1 | `etage` |
| `scripts/python/engine/runner/abilities/loki/healing_balms.py` | #966-r2 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/instruments_of_vengeance.py` | #889-r7 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/mind_control.py` | #552-r2 | `capteur` |
| `scripts/python/engine/runner/abilities/loki/momentum.py` | #943-r7 | `seeding` |
| `scripts/python/engine/runner/abilities/loki/quickening.py` | #347-r1 | `capteur` |
| `scripts/python/engine/runner/abilities/loki/reveal.py` | #1033-r4 | `etage` |
| `scripts/python/engine/runner/abilities/loki/wall_of_mirrors.py` | #433-r4-r1-r2 | `porteur` |
| `scripts/python/engine/runner/abilities/necrons.py` | #116-r | `etage` |
| `scripts/python/engine/runner/abilities/tyranids.py` | #890-r3 | `aucun` |
| `scripts/python/engine/runner/messages.py` | #596-r1 | `aucun` |
| `scripts/python/engine/runner/operations/` | #547-r6 | `aucun` |
| `scripts/python/engine/runner/operations/change_unit_owner.py` | #590-r1 | `seeding` |
| `scripts/python/engine/runner/operations/damage_ops/` | #446-r3a | `porteur` |
| `scripts/python/engine/runner/operations/damage_ops/__init__.py` | #485-r1-r4 | `aucun` |
| `scripts/python/engine/runner/operations/damage_ops/normal.py` | #965-r2 | `etage` |
| `scripts/python/engine/runner/operations/damage_ops/normal_like.py` | #953-r4 | `porteur` |
| `scripts/python/engine/runner/operations/heal.py` | #1037-r1 | `etage` |
| `scripts/python/engine/runner/operations/left_over_damage.py` | #462-r4e-o-r1-r1-r1 | `porteur` |
| `scripts/python/engine/runner/operations/remove_unit.py` | #389-r4 | `aucun` |
| `scripts/python/engine/runner/operations/revive.py` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r6 | `aucun` |
| `scripts/python/engine/runner/operations/summon_ai.py` | #577-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/base.py` | #929-r4 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/dispatch/move_death.py` | #955-r1 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/loki/**` | #585-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/__init__.py` | #485-r1-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/act_of_faith.py` | #1001-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/chalice_of_baal.py` | #1005-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/deathwing.py` | #932-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/dw02_advanced_burst_cannon.py` | #1009-r3 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/electrochaff_backups.py` | #1025-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fabricator_claw_array.py` | #927-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fire.py` | #951-r4 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/floating_death.py` | #1065-r2 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/fuelled_by_fury.py` | #66-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/geminae_superia.py` | #1074 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/grim_retribution.py` | #946-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/helspear.py` | #1008-r3 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/icon_of_obstinacy.py` | #943-r7 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/loki/possession.py` | #955-r1 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/loki/synaptic_linchpin.py` | #937-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/pending_attack.py` | #889-r7 | `aucun` |
| `scripts/python/engine/services/movement_query.py` | #1048-r2 | `porteur` |
| `scripts/python/engine/services/static_battle_rules.py` | #419-r1-tr9-r4-r1-r2-r1a | `aucun` |
| `scripts/python/engine/utilities/` | #1013-r3 | `aucun` |
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
| `scripts/python/import_closure.py` | #486-r17 | `aucun` |
| `scripts/python/kit_item_voies.py` | #1041-r2 | `aucun` |
| `scripts/python/mcp_ghidra.py` | #594 | `aucun` |
| `scripts/python/migrate_270r4r2r2_hisser_differes.py` | #923-r1 | `aucun` |
| `scripts/python/probe_1015r1_beast_snagga.py` | #1015-r5 | `aucun` |
| `scripts/python/probe_1015r1_close_combat_weakness.py` | #1015-r3 | `aucun` |
| `scripts/python/probe_1022_aether_stride.py` | #1022-r3 | `aucun` |
| `scripts/python/probe_1025_electrochaff_port.py` | #1025-r3 | `aucun` |
| `scripts/python/probe_1025r1_more_gitz_bonus_live.py` | #1035-r4 | `aucun` |
| `scripts/python/probe_1033_reveal_live.py` | #1033-r4 | `etage` |
| `scripts/python/probe_1035r2_blighted_land_bonus_live.py` | #1035-r4 | `aucun` |
| `scripts/python/probe_1044_levier_traits.py` | #1044-r3 | `aucun` |
| `scripts/python/probe_116_necrons.py` | #419-r1-tr5-r8 | `capteur` |
| `scripts/python/probe_202r_decision_abraxas.py` | #202-r1 | `aucun` |
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
| `scripts/python/probe_419r6r1_face_decision.py` | #419-r6-r1-r1 | `aucun` |
| `scripts/python/probe_419r6r1r1_sort_utility_trace.py` | #419-r6-r1-r1 | `aucun` |
| `scripts/python/probe_429r1_bit_readers_scan.py` | #429-r1-r2 | `aucun` |
| `scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py` | #429-r1-r3-r1-r2-r1 | `aucun` |
| `scripts/python/probe_433_r4_r2_r1_r1_c_caster_gates.py` | #433-r4-r2-r1-r1-c-r2 | `aucun` |
| `scripts/python/probe_433_r4_r2_r4_r1_contre_epreuves.py` | #433-r4-r2-r4-r1-r1 | `aucun` |
| `scripts/python/probe_433r4r1r4r2_is_adjacent_substrat_live.py` | #433-r4-r1-r4-r2-r3 | `aucun` |
| `scripts/python/probe_433r4r1r4r2r4_aval_decision_live.py` | #433-r4-r1-r4-r2-r4-r1 | `aucun` |
| `scripts/python/probe_437r1_overwatch_offbyone.py` | #437-r1-r1-r3 | `aucun` |
| `scripts/python/probe_437r1r1r1_effect_face_table.py` | #437-r1-r1-r1-r1 | `aucun` |
| `scripts/python/probe_440_repo_root_scan_guard.py` | #468-r6 | `aucun` |
| `scripts/python/probe_447_r1_r1_zone_inclusion_decision.py` | #447-r6 | `aucun` |
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
| `scripts/python/probe_547_ledger_sans_verdict_non_vert.py` | #934-r3 | `aucun` |
| `scripts/python/probe_547r1_mesure_missing_non_verdict.py` | #547-r9 | `aucun` |
| `scripts/python/probe_585r1_mutants.py` | #585-r4 | `aucun` |
| `scripts/python/probe_589r1r1r2r1_amulet_crit_reduction_live.py` | #589-r1-r1-r2-r1-r2 | `aucun` |
| `scripts/python/probe_594_ctor_litteraux.py` | #594 | `aucun` |
| `scripts/python/probe_889_lions_wrath.py` | #889-r4 | `aucun` |
| `scripts/python/probe_902_reanimator.py` | #902-r2 | `seeding` |
| `scripts/python/probe_909_decision_actives_kit.py` | #909-r4 | `aucun` |
| `scripts/python/probe_915_prophetic_sentinel.py` | #915-r3 | `aucun` |
| `scripts/python/probe_916r1_effect_slots.py` | #982-r6 | `capteur` |
| `scripts/python/probe_928_legacy_of_combat.py` | #928-r1 | `aucun` |
| `scripts/python/probe_939_bio_minefield.py` | #939-r1 | `etage` |
| `scripts/python/probe_950_terrors_lament_tough_to_kill.py` | #1045-r1 | `aucun` |
| `scripts/python/probe_956_purete_de_passe.py` | #956-r1 | `aucun` |
| `scripts/python/probe_961_necron_passives.py` | #961-r3 | `aucun` |
| `scripts/python/probe_964r1_ecog_support.py` | #964-r2 | `aucun` |
| `scripts/python/probe_966r3_execution_du_cast.py` | #966-r6 | `seeding` |
| `scripts/python/probe_974_decision_gates_live.py` | #974-r2 | `aucun` |
| `scripts/python/probe_987_thunderous_assault_strategy2.py` | #977-r3 | `aucun` |
| `scripts/python/prototype_485r1_registre_explicite.py` | #485-r1-r2 | `aucun` |
| `scripts/python/rl_collect_batch.py` | #961-r2 | `aucun` |
| `scripts/python/rl_gen_enum_columns.py` | #270-b | `aucun` |
| `scripts/python/rl_gen_ref_tables.py` | #270-b | `aucun` |
| `scripts/python/targeting_reason.py` | #447-r2 | `aucun` |
| `scripts/python/tests/` | #486-r20 | `aucun` |
| `scripts/python/tests/engine/runner/*_live.py` | #933-r5 | `aucun` |
| `scripts/python/tests/engine/runner/_charge_regime.py` | #922-r1 | `aucun` |
| `scripts/python/tests/engine/runner/_combat_replay.py` | #949-r1 | `aucun` |
| `scripts/python/tests/engine/runner/conftest.py` | #531-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_1002_reliques_astra_offline.py` | #1002-r2 | `aucun` |
| `scripts/python/tests/engine/runner/test_1022_aether_stride_live.py` | #1022-r3 | `aucun` |
| `scripts/python/tests/engine/runner/test_1024r1_shield_of_faith_live.py` | #1024-r6 | `aucun` |
| `scripts/python/tests/engine/runner/test_1025_electrochaff_backups_live.py` | #1025-r3 | `aucun` |
| `scripts/python/tests/engine/runner/test_1065_floating_death_live.py` | #1065-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_1210_exemplar_of_the_montka_offline.py` | #942-r2 | `aucun` |
| `scripts/python/tests/engine/runner/test_889r6_instruments_of_vengeance_offline.py` | #889-r7 | `aucun` |
| `scripts/python/tests/engine/runner/test_894_arc_scourge_offline.py` | #894-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_928_legacy_of_combat_live.py` | #928-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_939_bio_minefield_offline.py` | #939-r1 | `etage` |
| `scripts/python/tests/engine/runner/test_946_unwavering_sentinel_live.py` | #946-r2 | `porteur` |
| `scripts/python/tests/engine/runner/test_950r2_prediction_aura_live.py` | #1045-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_foehammer_live.py` | #281-r4 | `aucun` |
| `scripts/python/tests/engine/runner/test_pick_randomly_one_rng_live.py` | #462-r4 | `aucun` |
| `scripts/python/tests/engine/test_270r4r2r2_differes_offline.py` | #484-r2 | `aucun` |
| `scripts/python/tests/engine/test_270r4r2r2r3_gardes_du_hissage_offline.py` | #486-r7 | `aucun` |
| `scripts/python/tests/engine/test_433r4r1r4r2r1r1_derivation_morte_offline.py` | #486-r7 | `aucun` |
| `scripts/python/tests/engine/test_447_r1_r1_zone_inclusion_decision_live.py` | #447-r6 | `aucun` |
| `scripts/python/tests/engine/test_933_premisse_regime_offline.py` | #933-r5 | `aucun` |
| `scripts/python/tests/engine/test_949r1_lecteurs_de_ledger_offline.py` | #949-r1 | `aucun` |
| `scripts/python/tests/engine/test_957_decision_faces_offline.py` | #957-r2 | `porteur` |
| `scripts/python/tests/engine/test_966r3_execution_du_cast_live.py` | #966-r6 | `seeding` |
| `scripts/python/tests/engine/test_974_custodes_emperors_children_decision_offline.py` | #974-r2 | `aucun` |
| `scripts/python/tests/test_457_r5_perimetre_offline.py` | #463-r2 | `aucun` |
| `scripts/python/tests/test_465_ledger_validite_offline.py` | #941-r4 | `aucun` |
| `scripts/python/tests/test_474_optional_locks_offline.py` | #941-r2 | `aucun` |
| `scripts/python/tests/test_547_ledger_sans_verdict_non_vert_offline.py` | #934-r3 | `aucun` |
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
| `capteur` | 32 | #1027-r5, #259-a, #259-b, #273-r, #287-r5-r2, #347-r1, #347-r3, #389-r3, #419-r1-tr11-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #419-r1-tr5-r8, #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r3, #444-r1, #449-r1, #462-r4e-o-r2-r1-r1-r1-r1, #462-r4e-o-r2-r1-r1-r1-r2, #475-r2, #475-r3, #487-r2, #545-r1, #552-r2, #595-r1, #595-r2, #595-r3, #596, #596-r2, #922-r2, #940-r1, #971-r3, #982-r6 |
| `seeding` | 28 | #1008-r1, #1011-r2, #1027-r1, #287-r11, #287-r14-r2, #392-r1, #419-r1-tr9-r1, #433-r4-r1-r4-r2-r1-r1-r1-r1, #433-r4-r2-r1-r2-r3, #447-r1-r1-r3-r1, #448-r3-r1-r1-r1, #449-r2-r4-r1, #482-r1, #590-r1, #590-r7, #889-r3, #889-r5-r3, #890-r4, #902-r2, #911-r1, #929-r2, #929-r4, #943-r7, #948-r3, #955-r1, #966-r6, #987-r1, #BF-chance |
| `etage` | 47 | #1008-r2, #1019-r1, #1020-r5, #1022-r2, #1026-r1, #1027-r3, #1030-r1, #1033-r1, #1033-r4, #1037-r1, #1065-r2, #1078-r2, #1079-r1, #116-r, #17, #175-r3, #27-r9, #271-r7, #287-r11-r2-r1-r3, #368-r2, #419-r1-tr12-r2-r1, #419-r4, #433-r3-r2-r1, #433-r4-r1-r1-r1, #433-r4-r1-r1-r2, #433-r4-r1-r3, #433-r4-r3-r1-r2, #443-r2-b2, #444-r2, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1, #508-r2, #577-r2, #590-r6, #590-r8, #889-r2, #894-r2, #895-r4, #919-r1, #926-r1, #939-r1, #946-r1, #946-r4, #951-r1, #965-r2, #967-r1, #977-r7 |
| `porteur` | 52 | #1022-r1, #1027-r6, #1030-r4, #1030-r6, #1042-r4, #1048-r2, #366-r1-chaos-friendly-fire, #419-r1-tr12-r2-r2, #419-r1-tr12-r4, #419-r1-tr14-r2, #419-r1-tr14-r4-r3, #419-r1-tr14-r5-r2-r1-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r4-r1, #419-r1-tr14-r5-r2-r1-r2-r1-r3, #419-r1-tr14-r5-r3, #419-r1-tr9-r4-r1-r2-r2, #419-t6-r1, #425-r1, #433-r4-r1-r2, #433-r4-r2-r1-r2-r2-r1-r1-r1-r3, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2, #437-r1-r1-r2, #445-r1, #446-r3a, #447-r1-r1-r1, #447-r3, #448-r1-r1-r1-r1-r2-r2, #448-r1-r2-r1, #449-r2-r4-r3, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4, #462-r4b-r1-r1-r1-r1-c-r3-r2, #462-r4e-o-r1-r1-r1, #465-r1, #503-r2, #521-r4, #550-r2, #884-r2, #895-r1, #915-r2, #942-r1, #943-r4, #945-r1, #945-r3, #946-r2, #952-r2, #953-r4, #957-r2, #967-r5, #969-r4, #969-r5 |
| `aucun` | 306 | #1001-r1, #1002-r1, #1002-r2, #1005-r1, #1005-r2, #1005-r3, #1008-r3, #1009-r1, #1009-r2, #1009-r3, #1013-r1, #1013-r3, #1015-r2, #1015-r3, #1015-r4, #1015-r5, #1019-r2, #1020-r6, #1021-r3, #1022-r3, #1024-r6, #1024-r7, #1025-r2, #1025-r3, #1027-r4, #1030-r3, #1031-r1, #1032-r1, #1032-r2, #1033-r2, #1035-r4, #1036-r3, #1036-r7, #1036-r8, #1037-r2, #1038-r2, #1039-r1, #1041-r1, #1041-r2, #1042-r2, #1042-r5, #1044-r1, #1044-r3, #1045-r1, #1045-r2, #1046-r1, #1064-r1, #1065-r1, #1074, #1078-r1, #1078-r3, #175-r1, #20, #202-r1, #217, #237-r1, #254-bc, #254-bc-r1, #270-a, #270-b, #270-r1-r1-r2, #271-r1, #271-r8, #277-r1, #281-r4, #283-r2, #330-r1, #330-r2, #334-r3, #350-r3a-r4-r1, #352-r1, #366-r1-effect-targets, #369, #380-r1, #389-r4, #389-r5, #390-r6, #390-r7, #390-r8, #419-r1, #419-r1-tr10-r2, #419-r1-tr12-r3, #419-r1-tr14-r5-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1, #419-r1-tr14-r5-r2-r1-r2-r1-r1-r1, #419-r1-tr14-r5-r2-r1-r2-r3, #419-r1-tr9-r4-r1-r2-r1a, #419-r1-tr9-r4-r1-r2-r1b, #419-r1-tr9-r4-r1-r2-r1c, #419-r1-tr9-r4-r1-r3, #419-r1-tr9-r4-r3, #419-r1-tr9-r5, #419-r2, #419-r6-r1-r1, #420-r4, #426-r1, #429-r1-r1-r1-r1, #429-r1-r2, #429-r1-r3-r1-r2-r1, #430-r1, #430-r2, #433-r3-r3-r2, #433-r4-r1-r4-r2-r2, #433-r4-r1-r4-r2-r3, #433-r4-r1-r4-r2-r4-r1, #433-r4-r2-r1-r1-c-r2, #433-r4-r2-r3, #433-r4-r2-r4-r1-r1, #433-r4-r3-r1-r1, #433-r4-r3-r1-r3, #433-r4-r3-r2, #434-r3, #437-r1-r1-r1-r1, #437-r1-r1-r3, #438-r1, #447-r2, #447-r6, #448-r1-r1-r1-r1-r2-r1, #448-r1-r1-r3, #448-r6, #449-r2-r1, #449-r2-r3, #449-r2-r4-r2, #449-r2-r4-r4-r1, #449-r3, #455-r1, #455-r2, #455-r4-r1, #456-r2-r1, #457-r6, #462-r1, #462-r2, #462-r3, #462-r4, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r3, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r5, #462-r4b-r1-r1-r1-r1-c-r3-r1-r6, #462-r4b-r1-r1-r1-r1-c-r3-r3, #462-r4c-r1-r1, #462-r4c-r1-r2, #462-r4c-r2, #462-r4c-r3, #462-r6-r1, #462-r6-r2, #463-r2, #464-r1b, #464-r1c, #467-r1, #467-r3, #467-r4-a, #467-r5, #467-r6-a, #468-r1, #468-r13, #468-r2, #468-r3, #468-r5, #468-r6, #468-r7, #468-r8, #469-r1, #469-r2, #469-r4, #471-r1, #471-r2, #475-r1, #482-r2, #482-r4, #482-r5, #482-r6, #484-r1, #484-r2, #485-r1-r1-r2, #485-r1-r2, #485-r1-r3, #485-r1-r4, #486-r10, #486-r16, #486-r17, #486-r20, #486-r21, #486-r25, #486-r26, #486-r3, #486-r37, #486-r38, #486-r4, #486-r6, #486-r7, #486-r8, #486-r9, #488-r2, #489-r1, #494-r2, #498-r5, #5, #510-r3, #511-r1, #512-r3, #519-r1, #521-r8, #521-r9, #523-r3, #526-r3, #531-r1, #547-r3, #547-r4-r1, #547-r6, #547-r9, #550-r3, #550-r4, #552-r3, #576-r2, #577-r1, #585-r1, #585-r2, #585-r4, #589-r1-r1-r2-r1-r1, #589-r1-r1-r2-r1-r2, #589-r1-r1-r2-r1-r3, #590-r11, #593, #594, #596-r1, #605-r1, #66-r2, #884-r1, #889-r4, #889-r7, #890-r3, #893-r2, #894-r1, #894-r3, #894-r4, #894-r5, #895-r5, #908-r1, #908-r2, #909-r1, #909-r3, #909-r4, #909-r5, #910-r1, #914-r1, #915-r1, #915-r3, #919-r2, #919-r3, #920-r3, #921-r1, #922-r1, #923-r1, #924-r1, #924-r2, #927-r1, #927-r3, #928-r1, #932-r1, #932-r2, #933-r5, #934-r2, #934-r3, #935-r2, #936-r1-r2, #937-r1, #940-r3, #941-r2, #941-r4, #942-r2, #942-r3, #943-r2, #943-r8, #945-r2, #946-r3, #949-r1, #951-r4, #951-r5, #951-r6, #953-r5, #954-r1, #956-r1, #957-r1, #957-r4, #961-r1, #961-r2, #961-r3, #963-r3, #964-r2, #966-r2, #967-r4, #969-r1, #971-r1, #971-r2, #971-r4, #974-r2, #977-r3, #979-r2, #983-r2, #988-r1, #999-r1, #999-r3-r2, #BL-1029r, #haze-ord, #o10-c |

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
| `a deriver par fichier` | 1 | #934-r2 |
| `aucun` | 14 | #1027-r6, #1037-r2, #1042-r2, #1042-r4, #390-r8, #448-r6, #890-r4, #919-r2, #919-r3, #921-r1, #943-r8, #945-r2, #957-r1, #983-r2 |
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
| `data/unspawnable_rank17.json` | #961-r2 |
| `engine/runner/operations/triggers/loki/final_vengeance.py` | #1002-r1 |
| `frida/hooks/features/ai-step/rpc-runner.ts` | #1044-r1 |
| `frida/hooks/features/rpc-snapshot.ts` | #1027-r5 |
| `scripts/python/engine/entities/effects/loki/lifewards.py` | #963-r3 |
| `scripts/python/engine/playbook/basilisk_barrage.py` | #1026-r1 |
| `scripts/python/engine/playbook/noncomparable/call_ripper_swarms.py` | #1032-r1 |
| `scripts/python/engine/playbook/noncomparable/nova_charge.py` | #1032-r1 |
| `scripts/python/engine/playbook/registry.py` | #585-r2 |
| `scripts/python/engine/runner/operations/triggers/loki/instruments_of_vengeance_attack.py` | #889-r7 |
| `scripts/python/engine/runner/operations/triggers/loki/lifewards.py` | #963-r3 |
| `scripts/python/engine/runner/operations/triggers/loki/rapid_fire.py` | #1020-r5 |
| `scripts/python/engine/runner/operations/triggers/loki/way_of_the_short_blade.py` | #1019-r2 |
| `scripts/python/probe_1038r2_contemptuous_confrontation_live.py` | #1038-r2 |
| `scripts/python/probe_273_gitignore_inputs.py` | #547-r6 |
| `scripts/python/probe_419r1tr14r5r2r1r1r1r3_gates.py` | #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1 |
| `scripts/python/probe_940r2_kiss_of_death_decision.py` | #940-r3 |
| `scripts/python/probe_945_adaptive_strategy.py` | #945-r3 |
| `scripts/python/probe_979_faces_decision_mow.py` | #979-r2 |
| `scripts/python/tests/engine/runner/test_1030_the_lantern_live.py` | #1030-r3 |

