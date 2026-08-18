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
| lignes de tableau OUVERTES | 413 |
| dont ANNOTEES (`FOYER:` + `BLOCAGE:`) | 411 |
| dont NON ANNOTEES | 2 |
| foyers distincts (fichiers/repertoires) | 490 |

Non annotees restantes : #120bis-spawn, #BL-1020r

## Points de COLLISION -- un foyer, plusieurs residus

Ces residus **ne partent pas ensemble**.

| foyer | n | residus |
|---|---|---|
| `scripts/ratchets.ps1` | 10 | #430-r1, #430-r2, #434-r3, #457-r6, #469-r2, #471-r1, #485-r1-r4, #485-r4, #547-r4-r1, #943-r9 |
| `scripts/python/engine/playbook/prediction/normal_attack.py` | 7 | #10019-r2, #1036-r7, #419-r1-tr14-r2, #446-r3a, #590-r11, #910-r1, #932-r2 |
| `scripts/python/engine/runner/damage_model.py` | 6 | #1020-r11, #1036-r7, #419-r1-tr9-r4-r1-r2-r1a-r1, #433-r4-r1-r4-r2-r1-r1-r1-r1-r1, #590-r11, #965-r2 |
| `scripts/python/engine/utilities/tile.py` | 6 | #1024-r7, #1036-r9, #175-r1, #271-r7, #271-r9, #425-r1 |
| `scripts/python/probe_462_live_tests_status.py` | 6 | #462-r1, #462-r2, #462-r3, #462-r4, #465-r1, #471-r1 |
| `scripts/python/` | 5 | #1064-r1, #419-r1-tr9-r4-r1-r3, #486-r3, #915-r1, #951-r8 |
| `scripts/python/engine/entities/effects/factory.py` | 5 | #10035-r3, #590-r11, #915-r1, #922-r1, #965-r2 |
| `scripts/python/engine/playbook/scene.py` | 5 | #1011-r2, #425-r1, #590-r11, #932-r2, #953-r5 |
| `scripts/python/engine/runner/components.py` | 5 | #448-r7, #482-r7, #590-r1, #590-r11, #929-r2 |
| `scripts/python/engine/runner/operations/damage_hits.py` | 5 | #1020-r11, #419-r4, #433-r4-r1-r1-r1, #920-r3, #965-r2 |
| `scripts/python/probe_457_offline_tests_green.py` | 5 | #457-r6, #486-r21, #486-r25, #547-r3, #935-r2 |
| `scripts/python/tests/engine/runner/` | 5 | #1005-r2, #1015-r3, #1038-r2, #503-r2, #922-r2 |
| `scripts/python/engine/ai/state_bridge.py` | 4 | #10031-r1, #952-r7, #977-r10, #977-r11 |
| `scripts/python/engine/entities/effects/loki/hits.py` | 4 | #10019-r1, #10019-r2, #1008-r5, #419-r1-tr9-r4-r1-r2-r2 |
| `scripts/python/engine/entities/selectors/units.py` | 4 | #1030-r8, #550-r3, #590-r11, #889-r11 |
| `scripts/python/engine/entities/triggers.py` | 4 | #1009-r3, #1032-r5, #419-r1-tr9-r4-r1-r3, #590-r11 |
| `scripts/python/engine/runner/abilities/**` | 4 | #20, #217, #585-r1, #585-r4 |
| `scripts/python/engine/runner/operations/spawn.py` | 4 | #1022-r4, #890-r5, #922-r1, #929-r2 |
| `scripts/python/engine/services/damage_prediction.py` | 4 | #1013-r1, #589-r1-r1-r2-r1-r3, #884-r1, #920-r3 |
| `scripts/python/loop_status.py` | 4 | #467-r1, #467-r5, #467-r6-a, #526-r3 |
| `scripts/python/probe_273_gitignored_inputs.py` | 4 | #464-r1b, #464-r1c, #471-r1, #486-r9 |
| `frida/hooks/features/ai-step/` | 3 | #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r3 |
| `frida/hooks/features/ai-step/rpc-snapshot.ts` | 3 | #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r1, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #487-r2 |
| `scripts/python/engine/ai/context.py` | 3 | #1027-r5, #425-r1, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1 |
| `scripts/python/engine/entities/formulas.py` | 3 | #1008-r1, #895-r1, #920-r3 |
| `scripts/python/engine/playbook/adjacent_unit_preference.py` | 3 | #433-r4-r3-r2, #922-r2, #932-r1 |
| `scripts/python/engine/playbook/prediction/_shared.py` | 3 | #1011-r2, #590-r14, #910-r1 |
| `scripts/python/engine/runner/abilities/handler.py` | 3 | #217, #419-r1-tr9-r4-r1-r3, #590-r11 |
| `scripts/python/engine/runner/operations/damage_ops/ability.py` | 3 | #419-r1-tr9-r4-r1-r2-r1a-r1, #488-r2, #512-r7 |
| `scripts/python/engine/runner/operations/remove_effects.py` | 3 | #389-r4, #547-r14, #936-r1-r2 |
| `scripts/python/engine/runner/operations/triggers/dispatch/registry.py` | 3 | #443-r2-b2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #521-r4 |
| `scripts/python/engine/runner/operations/triggers/loki/` | 3 | #521-r4, #895-r4, #946-r3 |
| `scripts/python/engine/runner/operations/turnflow.py` | 3 | #462-r4e-o-r2-r1-r1-r1-r1, #462-r4e-o-r2-r1-r1-r1-r2, #596-r1 |
| `scripts/python/engine/services/ability_caster_gates.py` | 3 | #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2, #433-r4-r2-r1-r3 |
| `scripts/python/engine/services/damage_modifiers.py` | 3 | #1011-r2, #437-r1-r1-r2, #920-r3 |
| `scripts/python/engine/utilities/unit_picker.py` | 3 | #10022-r2, #10022-r4, #10022-r5 |
| `scripts/python/fingerprint_functions.py` | 3 | #482-r1, #482-r2, #482-r4 |
| `scripts/python/probe_283_enum_ordinal_sweep.py` | 3 | #420-r7, #426-r1, #471-r1 |
| `scripts/python/probe_486r12_declencheurs.py` | 3 | #486-r16, #486-r37, #486-r38 |
| `scripts/python/tests/engine/test_270r4r2r2_differes_offline.py` | 3 | #484-r2, #485-r6, #934-r2 |
| `scripts/python/tests/test_431_build_pin_offline.py` | 3 | #468-r6, #934-r2, #941-r4 |
| `scripts/python/verdict_cache.py` | 3 | #486-r16, #486-r9, #943-r2 |
| `data/seed-bc.json` | 2 | #254-bc, #392-r1 |
| `data/symbols/` | 2 | #909-r4, #909-r6 |
| `data/symbols/t6dpr4k06g/metadata/*.tsv` | 2 | #590-r11, #915-r1 |
| `docs/**` | 2 | #283-r2, #330-r2 |
| `docs/rl/backlog.md` | 2 | #10030-r1, #468-r5 |
| `docs/rl/kit-coverage.md` | 2 | #909-r5, #951-r6 |
| `frida/hooks/features/ai-step/internals.ts` | 2 | #1020-r10, #419-r1-tr11-r2 |
| `frida/hooks/features/ai-step/rpc-predict.ts` | 2 | #419-r1-tr11-r2, #971-r3 |
| `frida/hooks/features/ai-step/rpc-targeting.ts` | 2 | #444-r1, #590-r13 |
| `frida/hooks/features/observe.ts` | 2 | #462-r4e-o-r2-r1-r1-r1-r1, #595-r3 |
| `frida/hooks/features/scorer-damage-trace.ts` | 2 | #10011-r3, #175-r5 |
| `frida/hooks/features/ui-windows.ts` | 2 | #390-r6, #390-r7 |
| `scripts/cliquets-cache/probe_477r24r1_slots_interface.tsv` | 2 | #943-r2, #943-r9 |
| `scripts/hooks/loop-status.ps1` | 2 | #467-r3, #467-r5 |
| `scripts/python/audit_kit_coverage.py` | 2 | #909-r5, #951-r6 |
| `scripts/python/catalog_inject.py` | 2 | #254-bc, #890-r5 |
| `scripts/python/declencheur_cliquet.py` | 2 | #486-r16, #486-r25 |
| `scripts/python/engine/` | 2 | #482-r7, #485-r1-r3 |
| `scripts/python/engine/ai/action_generators.py` | 2 | #271-r9, #334-r3 |
| `scripts/python/engine/entities/behaviours.py` | 2 | #10015-r1, #894-r4 |
| `scripts/python/engine/entities/effects/aura_selectors.py` | 2 | #433-r5, #926-r1 |
| `scripts/python/engine/entities/effects/base.py` | 2 | #1019-r4, #175-r4 |
| `scripts/python/engine/entities/effects/loki/` | 2 | #433-r4-r1-r1-r1, #895-r4 |
| `scripts/python/engine/entities/effects/loki/dark_angels_passives.py` | 2 | #946-r1, #946-r4 |
| `scripts/python/engine/entities/effects/loki/extra_damage.py` | 2 | #1005-r1, #419-r1-tr9-r4-r1-r3 |
| `scripts/python/engine/entities/effects/loki/intoxicating_elixir.py` | 2 | #922-r1, #922-r2 |
| `scripts/python/engine/entities/pathfinding/base_pathfinder.py` | 2 | #448-r1-r1-r1-r1-r2-r1, #448-r1-r1-r1-r1-r2-r2 |
| `scripts/python/engine/entities/stats.py` | 2 | #270-r1-r1-r2, #482-r7 |
| `scripts/python/engine/playbook/base.py` | 2 | #438-r1, #445-r1 |
| `scripts/python/engine/playbook/common.py` | 2 | #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r1, #419-r1-tr14-r5-r2-r1-r1-r2 |
| `scripts/python/engine/playbook/non_owner.py` | 2 | #1036-r9, #433-r4-r3-r1-r1 |
| `scripts/python/engine/playbook/non_owner_attack.py` | 2 | #1024-r7, #1036-r9 |
| `scripts/python/engine/playbook/noncomparable/__init__.py` | 2 | #1032-r1, #577-r2 |
| `scripts/python/engine/playbook/noncomparable/early_warning_override.py` | 2 | #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1, #433-r4-r2-r3 |
| `scripts/python/engine/playbook/noncomparable/master_of_the_tutelaries.py` | 2 | #202-r1, #971-r4 |
| `scripts/python/engine/playbook/noncomparable/solar_atomizer.py` | 2 | #1027-r3, #969-r5 |
| `scripts/python/engine/playbook/noncomparable/storm_speeder.py` | 2 | #10022-r4, #967-r1 |
| `scripts/python/engine/playbook/prediction/abilities.py` | 2 | #1036-r7, #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r2 |
| `scripts/python/engine/playbook/psyker.py` | 2 | #419-r1, #419-r2 |
| `scripts/python/engine/runner/abilities/__init__.py` | 2 | #485-r1-r4, #485-r3 |
| `scripts/python/engine/runner/abilities/behaviours/combat.py` | 2 | #419-r1-tr14-r4-r3, #489-r2 |
| `scripts/python/engine/runner/abilities/behaviours/context.py` | 2 | #1008-r1, #1030-r8 |
| `scripts/python/engine/runner/abilities/behaviours/stats.py` | 2 | #590-r11, #919-r1 |
| `scripts/python/engine/runner/abilities/deathguard.py` | 2 | #1030-r1, #1032-r5 |
| `scripts/python/engine/runner/abilities/loki/__init__.py` | 2 | #485-r1-r4, #485-r3 |
| `scripts/python/engine/runner/abilities/loki/mind_control.py` | 2 | #552-r2, #590-r11 |
| `scripts/python/engine/runner/abilities/tau.py` | 2 | #10034-r1, #895-r1 |
| `scripts/python/engine/runner/battle_query_state.py` | 2 | #10024-r2, #419-r1-tr14-r4-r3 |
| `scripts/python/engine/runner/operations/behaviour.py` | 2 | #429-r1-r3-r1-r2-r1, #BF-chance |
| `scripts/python/engine/runner/operations/displace.py` | 2 | #482-r7, #550-r2 |
| `scripts/python/engine/runner/operations/movement.py` | 2 | #10031-r1, #589-r2-r1-r1 |
| `scripts/python/engine/runner/operations/refresh_effects.py` | 2 | #577-r1, #919-r1 |
| `scripts/python/engine/runner/operations/triggers/dispatch/attack.py` | 2 | #10013, #512-r7 |
| `scripts/python/engine/runner/operations/triggers/loki/haywire_mine.py` | 2 | #10015, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4 |
| `scripts/python/engine/runner/operations/triggers/loki/savage_killer.py` | 2 | #929-r2, #929-r4 |
| `scripts/python/engine/runner/snapshot.py` | 2 | #487-r2, #922-r1 |
| `scripts/python/engine/services/battle_query.py` | 2 | #433-r4-r1-r4-r2-r1-r1-r1-r1-r1, #482-r7 |
| `scripts/python/engine/services/custom_normal_attack.py` | 2 | #419-r1-tr12-r3, #419-r1-tr14-r5-r3 |
| `scripts/python/engine/services/effect_bonus.py` | 2 | #1005-r1, #1033-r1 |
| `scripts/python/engine/services/targeting_query.py` | 2 | #433-r4-r2-r1-r2-r3, #444-r2 |
| `scripts/python/il2cpp_metadata.py` | 2 | #486-r10, #982-r6 |
| `scripts/python/migrate_485r1_barils_reexport.py` | 2 | #485-r1-r3, #923-r1 |
| `scripts/python/probe_1009_reliques_dark_angels.py` | 2 | #1009-r1, #1009-r2 |
| `scripts/python/probe_1021_face_decision_au_registre.py` | 2 | #1032-r1, #1033-r2 |
| `scripts/python/probe_1210_exemplar_of_the_montka.py` | 2 | #942-r1, #942-r2 |
| `scripts/python/probe_365_versioned_imports_gitignored.py` | 2 | #462-r4c-r3, #471-r1 |
| `scripts/python/probe_366_r1_bcpatch_port_blindspot.py` | 2 | #10027-r1, #484-r1 |
| `scripts/python/probe_419*.py` | 2 | #419-r1, #419-r2 |
| `scripts/python/probe_440_repo_root_scan_guard.py` | 2 | #468-r6, #471-r1 |
| `scripts/python/probe_449r2_spread_inventory.py` | 2 | #449-r2-r1, #449-r2-r3 |
| `scripts/python/probe_455_all_skipped_file.py` | 2 | #455-r1, #471-r1 |
| `scripts/python/probe_475_pinned_addresses.py` | 2 | #471-r1, #475-r1 |
| `scripts/python/probe_486r15_declencheurs_tests.py` | 2 | #486-r20, #486-r21 |
| `scripts/python/probe_486r2_usage_des_probes.py` | 2 | #486-r3, #486-r6 |
| `scripts/python/probe_547_ledger_sans_verdict_non_vert.py` | 2 | #431-r2, #934-r3 |
| `scripts/python/probe_908_nether_realm_casket_crit_live.py` | 2 | #10035-r1, #10035-r2 |
| `scripts/python/rl_duel.py` | 2 | #1044-r1, #593 |
| `scripts/python/tests/` | 2 | #10033-r1, #486-r20 |
| `scripts/python/tests/**` | 2 | #462-r6-r2, #486-r26 |
| `scripts/python/tests/conftest.py` | 2 | #455-r2, #531-r1 |
| `scripts/python/tests/engine/` | 2 | #419-r2, #954-r1 |
| `scripts/python/tests/engine/conftest.py` | 2 | #419-r1-tr5-r8, #531-r1 |
| `scripts/python/tests/engine/runner/test_1009_reliques_dark_angels_live.py` | 2 | #1009-r1, #1009-r2 |
| `scripts/python/tests/engine/test_270r4r2r2r3_gardes_du_hissage_offline.py` | 2 | #486-r7, #934-r2 |
| `scripts/python/tests/engine/test_949r1_lecteurs_de_ledger_offline.py` | 2 | #949-r1, #949-r3 |

## Foyers ISOLES -- un seul residu

Candidats naturels a un dispatch parallele, sous reserve de croiser leurs autres foyers.

| foyer | residu | blocage |
|---|---|---|
| `data/symbols/t6dpr4k06g/metadata/active_playbook_builders.tsv` | #951-r8 | `aucun` |
| `docs/rl/` | #482-r7 | `aucun` |
| `docs/rl/case-1046-horreurs-thousand-sons.md` | #1046-r1 | `aucun` |
| `docs/rl/case-302-4-population-cible-tuile.md` | #419-r1-tr14-r5-r2-r1-r2-r3 | `aucun` |
| `docs/rl/case-302-4/tile-target-population.json` | #419-r1-tr14-r5-r2-r1-r2-r3 | `aucun` |
| `docs/rl/case-302-4/tile-target-population.tsv` | #419-r1-tr14-r5-r2-r1-r2-r3 | `aucun` |
| `docs/rl/case-462-r4b-r1-r1-r1-r1-c-r3-r1-r4-post-unit-kill.md` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2 | `aucun` |
| `docs/rl/case-475-adresses-epinglees.md` | #475-r5 | `porteur` |
| `docs/rl/case-951-r7-reattestation-au-changement-de-build.md` | #482-r7 | `aucun` |
| `docs/rl/dsl-effect-nodes.md` | #330-r1 | `aucun` |
| `docs/rl/playbook/prediction.md` | #330-r1 | `aucun` |
| `docs/rl/port-residuals-inventory.md` | #526-r3 | `aucun` |
| `docs/rl/runner-engine.md` | #330-r1 | `aucun` |
| `frida/hooks/` | #552-r2 | `capteur` |
| `frida/hooks/ai-toolkit/bucket-decode.ts` | #988-r1 | `aucun` |
| `frida/hooks/controller.ts` | #1064-r1 | `aucun` |
| `frida/hooks/features/` | #10019-r1 | `capteur` |
| `frida/hooks/features/ai-step/playbook-predict.ts` | #419-r1-tr11-r2 | `capteur` |
| `frida/hooks/features/ai-step/projection.ts` | #419-r1-tr10-r2 | `aucun` |
| `frida/hooks/features/ai-step/rpc-*.ts` | #595-r3 | `capteur` |
| `frida/hooks/features/ai-step/rpc-nc-predict.ts` | #449-r1 | `capteur` |
| `frida/hooks/features/battle-events.ts` | #596-r1 | `aucun` |
| `frida/hooks/features/bucket-audit.ts` | #475-r3 | `capteur` |
| `frida/hooks/features/deployment-draft.ts` | #10020-r1 | `capteur` |
| `frida/hooks/features/dsl-ctor-trace.ts` | #1009-r3 | `aucun` |
| `frida/hooks/features/introspect.ts` | #982-r6 | `capteur` |
| `frida/hooks/features/movement-trace.ts` | #547-r6 | `aucun` |
| `frida/hooks/features/retreat-capture.ts` | #390-r6 | `aucun` |
| `frida/hooks/features/sim-engine.ts` | #595-r3 | `capteur` |
| `frida/hooks/features/warmup-singletons.ts` | #10021 | `capteur` |
| `frida/hooks/game/ai-control.ts` | #10022-r6 | `capteur` |
| `frida/hooks/game/apply-stack.ts` | #596-r1 | `aucun` |
| `frida/hooks/game/receive-damage-types.ts` | #487-r2 | `aucun` |
| `frida/hooks/game/recorder.ts` | #10022-r6 | `capteur` |
| `frida/hooks/game/weapons.ts` | #419-r1-tr14-r5-r2-r1-r2-r1-r2 | `aucun` |
| `frida/hooks/il2cpp/` | #259-b | `capteur` |
| `frida/hooks/il2cpp/invoke.ts` | #595-r2 | `capteur` |
| `frida/hooks/probes/valid-targets-from.ts` | #1064-r1 | `aucun` |
| `frida/host/ai-trace-store.ts` | #273-r | `capteur` |
| `scripts/cliquets-cache/probe_326_inventaire_natif.tsv` | #10028-r2 | `aucun` |
| `scripts/cliquets-cache/probe_477r25_slots_autres_interfaces.tsv` | #943-r9 | `aucun` |
| `scripts/declencheurs-empreinte.tsv` | #486-r37 | `aucun` |
| `scripts/node/verify_portraits.mjs` | #273-r | `capteur` |
| `scripts/python/**` | #1031-r1 | `aucun` |
| `scripts/python/audit_combat_ability_coverage.py` | #1041-r1 | `aucun` |
| `scripts/python/audit_npc_registry.py` | #1021-r3 | `aucun` |
| `scripts/python/audit_passive_ability_coverage.py` | #1041-r2 | `aucun` |
| `scripts/python/backlog_entries.py` | #10030-r1 | `aucun` |
| `scripts/python/build_fingerprint_archive.py` | #482-r5 | `aucun` |
| `scripts/python/counterproof.py` | #462-r6-r2 | `aucun` |
| `scripts/python/engine/**` | #485-r4 | `aucun` |
| `scripts/python/engine/ai/tactic.py` | #334-r3 | `aucun` |
| `scripts/python/engine/battle_query.py` | #433-r4-r1-r1-r2 | `aucun` |
| `scripts/python/engine/dsl/base.py` | #419-r1-tr14-r4-r3 | `etage` |
| `scripts/python/engine/entities/abilities/**` | #20 | `aucun` |
| `scripts/python/engine/entities/abilities/active_ability.py` | #585-r1 | `aucun` |
| `scripts/python/engine/entities/effect_targets.py` | #366-r1-effect-targets | `aucun` |
| `scripts/python/engine/entities/effect_type.py` | #946-r3 | `porteur` |
| `scripts/python/engine/entities/effects/__init__.py` | #1019-r4 | `aucun` |
| `scripts/python/engine/entities/effects/loki/amulet_of_the_voidwyrm.py` | #585-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/counter_attack.py` | #946-r3 | `porteur` |
| `scripts/python/engine/entities/effects/loki/daemonic_patrons.py` | #590-r11 | `aucun` |
| `scripts/python/engine/entities/effects/loki/damage_reduction.py` | #965-r2 | `etage` |
| `scripts/python/engine/entities/effects/loki/deathwing.py` | #932-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/extra_damage_aura.py` | #1036-r7 | `etage` |
| `scripts/python/engine/entities/effects/loki/first_among_traitors.py` | #926-r1 | `etage` |
| `scripts/python/engine/entities/effects/loki/kustom_force_field.py` | #590-r11 | `aucun` |
| `scripts/python/engine/entities/effects/loki/norn_crown.py` | #590-r11 | `aucun` |
| `scripts/python/engine/entities/effects/loki/relentless_march.py` | #577-r1 | `aucun` |
| `scripts/python/engine/entities/effects/loki/revealed.py` | #1033-r1 | `etage` |
| `scripts/python/engine/entities/effects/loki/shock_assault.py` | #590-r11 | `aucun` |
| `scripts/python/engine/entities/effects/loki/status.py` | #419-r1-tr9-r4-r1-r3 | `aucun` |
| `scripts/python/engine/entities/effects/loki/synaptic_insight.py` | #590-r11 | `aucun` |
| `scripts/python/engine/entities/effects/loki/way_of_the_short_blade.py` | #1008-r5 | `aucun` |
| `scripts/python/engine/entities/effects_state.py` | #936-r1-r2 | `aucun` |
| `scripts/python/engine/entities/pathfinding/fly_pathfinder.py` | #448-r1-r1-r1-r1-r2-r2 | `porteur` |
| `scripts/python/engine/entities/pathfinding/ignore_terrain_pathfinder.py` | #175-r1 | `aucun` |
| `scripts/python/engine/entities/pathfinding/pathfinders.py` | #448-r1-r1-r1-r1-r2-r1 | `aucun` |
| `scripts/python/engine/entities/selectors/` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1 | `etage` |
| `scripts/python/engine/entities/selectors/geometry.py` | #889-r11 | `aucun` |
| `scripts/python/engine/entities/selectors/tiles.py` | #895-r1 | `seeding` |
| `scripts/python/engine/entities/unit_selection_type.py` | #433-r5 | `porteur` |
| `scripts/python/engine/playbook/` | #419-r1 | `aucun` |
| `scripts/python/engine/playbook/adjacency.py` | #948-r3 | `seeding` |
| `scripts/python/engine/playbook/excruciating_frequencies.py` | #969-r5 | `porteur` |
| `scripts/python/engine/playbook/friends_in_range.py` | #433-r4-r3-r2 | `aucun` |
| `scripts/python/engine/playbook/intoxicating_elixir.py` | #922-r2 | `aucun` |
| `scripts/python/engine/playbook/light_im_up.py` | #10024-r2 | `porteur` |
| `scripts/python/engine/playbook/loki_custom.py` | #27-r9 | `etage` |
| `scripts/python/engine/playbook/non_owner_repair.py` | #271-r7 | `aucun` |
| `scripts/python/engine/playbook/nonattack.py` | #27-r9 | `etage` |
| `scripts/python/engine/playbook/noncomparable/` | #1033-r2 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/_targets.py` | #969-r5 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/adaptive_strategy.py` | #577-r2 | `etage` |
| `scripts/python/engine/playbook/noncomparable/alpha_warrior.py` | #945-r1 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/exemplar_of_the_montka.py` | #942-r3 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/fear_of_the_unseen.py` | #957-r2 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/grot_tank.py` | #971-r4 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/heroic_fusillade.py` | #433-r4-r1-r4-r2-r2 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/mind_control.py` | #552-r3 | `aucun` |
| `scripts/python/engine/playbook/noncomparable/nova_shield.py` | #969-r5 | `porteur` |
| `scripts/python/engine/playbook/noncomparable/poxwalkers.py` | #17 | `etage` |
| `scripts/python/engine/playbook/noncomparable/war_howl.py` | #585-r2 | `aucun` |
| `scripts/python/engine/playbook/obsessive_annunciation.py` | #954-r1 | `aucun` |
| `scripts/python/engine/playbook/prophetic_sentinel.py` | #915-r2 | `porteur` |
| `scripts/python/engine/playbook/savior_protocols.py` | #456-r2-r1 | `aucun` |
| `scripts/python/engine/playbook/should_evaluate_target.py` | #969-r4 | `porteur` |
| `scripts/python/engine/playbook/should_execute_gates.py` | #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r2 | `etage` |
| `scripts/python/engine/playbook/shrapnel.py` | #419-r1 | `aucun` |
| `scripts/python/engine/playbook/tile_targets.py` | #1027-r4 | `aucun` |
| `scripts/python/engine/predict.py` | #953-r5 | `aucun` |
| `scripts/python/engine/runner/abilities/` | #419-r1-tr12-r3 | `aucun` |
| `scripts/python/engine/runner/abilities/aeldari.py` | #940-r1 | `capteur` |
| `scripts/python/engine/runner/abilities/attack_query.py` | #1037-r1 | `etage` |
| `scripts/python/engine/runner/abilities/attack_type.py` | #419-r1-tr9-r4-r1-r3 | `aucun` |
| `scripts/python/engine/runner/abilities/behaviours/chain.py` | #894-r4 | `aucun` |
| `scripts/python/engine/runner/abilities/behaviours/grants.py` | #1022-r1 | `porteur` |
| `scripts/python/engine/runner/abilities/bloodangels.py` | #590-r11 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/attempted_possession.py` | #590-r11 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/healing_balms.py` | #966-r2 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/mv71.py` | #433-r4-r1-r3 | `etage` |
| `scripts/python/engine/runner/abilities/loki/quickening.py` | #347-r1 | `capteur` |
| `scripts/python/engine/runner/abilities/loki/reveal.py` | #1033-r4 | `etage` |
| `scripts/python/engine/runner/abilities/loki/splash.py` | #1032-r5 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/summon.py` | #1022-r4 | `aucun` |
| `scripts/python/engine/runner/abilities/loki/wall_of_mirrors.py` | #433-r4-r1-r2 | `porteur` |
| `scripts/python/engine/runner/abilities/necrons.py` | #590-r11 | `aucun` |
| `scripts/python/engine/runner/abilities/repair.py` | #334-r3 | `aucun` |
| `scripts/python/engine/runner/abilities/spacewolves.py` | #1032-r5 | `aucun` |
| `scripts/python/engine/runner/abilities/targeting.py` | #547-r6 | `aucun` |
| `scripts/python/engine/runner/abilities/thousandsons.py` | #1022-r4 | `aucun` |
| `scripts/python/engine/runner/abilities/ultramarines.py` | #1032-r5 | `aucun` |
| `scripts/python/engine/runner/abilities/worldeaters.py` | #590-r11 | `aucun` |
| `scripts/python/engine/runner/messages.py` | #596-r1 | `aucun` |
| `scripts/python/engine/runner/operations/additional_hits.py` | #419-r1-tr9-r4-r3 | `aucun` |
| `scripts/python/engine/runner/operations/attack_prediction.py` | #449-r3 | `aucun` |
| `scripts/python/engine/runner/operations/change_unit_owner.py` | #590-r1 | `seeding` |
| `scripts/python/engine/runner/operations/damage.py` | #10013 | `porteur` |
| `scripts/python/engine/runner/operations/damage_ops/__init__.py` | #485-r1-r4 | `aucun` |
| `scripts/python/engine/runner/operations/damage_ops/normal.py` | #965-r2 | `etage` |
| `scripts/python/engine/runner/operations/damage_ops/normal_like.py` | #512-r7 | `aucun` |
| `scripts/python/engine/runner/operations/effects.py` | #919-r1 | `etage` |
| `scripts/python/engine/runner/operations/heal.py` | #1037-r1 | `etage` |
| `scripts/python/engine/runner/operations/left_over_damage.py` | #462-r4e-o-r1-r1-r1 | `porteur` |
| `scripts/python/engine/runner/operations/remove_unit.py` | #389-r4 | `aucun` |
| `scripts/python/engine/runner/operations/remove_unit_from_tiles.py` | #448-r7 | `aucun` |
| `scripts/python/engine/runner/operations/revive.py` | #547-r14 | `aucun` |
| `scripts/python/engine/runner/operations/stat_ops.py` | #482-r7 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/base.py` | #929-r4 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/dispatch/ability.py` | #929-r4 | `seeding` |
| `scripts/python/engine/runner/operations/triggers/dispatch/core.py` | #10015-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/genestealer.py` | #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/**` | #585-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/__init__.py` | #485-r3 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/anvil_shield.py` | #419-r1-tr9-r4-r1-r3 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/chalice_of_baal.py` | #1005-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/daemonic_patrons.py` | #911-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/dawn_blade.py` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r6-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/deathwing.py` | #932-r1 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/dw02_advanced_burst_cannon.py` | #1009-r3 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fire.py` | #951-r4 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/floating_death.py` | #1065-r2 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/fuelled_by_fury.py` | #66-r2 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/fury_of_the_ancients.py` | #1005-r3 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/grim_retribution.py` | #946-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/instruments_of_vengeance_attack.py` | #889-r11 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/lakrimae.py` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1 | `etage` |
| `scripts/python/engine/runner/operations/triggers/loki/power_up.py` | #482-r7 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/primarch_first_legion.py` | #590-r11 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/sabre_of_sacrifice.py` | #590-r11 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/loki/the_ardent_blade.py` | #590-r11 | `aucun` |
| `scripts/python/engine/runner/operations/triggers/pending_attack.py` | #895-r4 | `etage` |
| `scripts/python/engine/runner/state.py` | #10015-r1 | `etage` |
| `scripts/python/engine/services/ability_range.py` | #433-r4-r2-r1-r1-b | `capteur` |
| `scripts/python/engine/services/damage_config.py` | #449-r2-r4-r3 | `porteur` |
| `scripts/python/engine/services/movement_query.py` | #1048-r2 | `porteur` |
| `scripts/python/engine/utilities/__init__.py` | #485-r3 | `aucun` |
| `scripts/python/engine/utilities/damage.py` | #449-r2-r4-r3 | `porteur` |
| `scripts/python/engine/utilities/decider.py` | #10022-r2 | `aucun` |
| `scripts/python/engine/utilities/move.py` | #10022-r8 | `capteur` |
| `scripts/python/gen_ai_targets.py` | #464-r1b | `aucun` |
| `scripts/python/gen_battlelogic_targets.py` | #464-r1b | `aucun` |
| `scripts/python/gen_campaign_builder_targets.py` | #464-r1b | `aucun` |
| `scripts/python/gen_full_game_targets.py` | #464-r1b | `aucun` |
| `scripts/python/host_inputs.py` | #273-r | `capteur` |
| `scripts/python/kit_item_voies.py` | #1041-r2 | `aucun` |
| `scripts/python/mcp_ghidra.py` | #594 | `aucun` |
| `scripts/python/migrate_270r4r2r2_hisser_differes.py` | #923-r1 | `aucun` |
| `scripts/python/nettoyer_livraison.py` | #479-r6 | `aucun` |
| `scripts/python/pe_symboles.py` | #10028-r3 | `aucun` |
| `scripts/python/probe_*.py` | #277-r1 | `aucun` |
| `scripts/python/probe_10015_allow_for_dead_owner.py` | #10015 | `aucun` |
| `scripts/python/probe_10018_effectsdatabase_registry.py` | #431-r2 | `aucun` |
| `scripts/python/probe_10018r1_solar_atomizer_phase2_live.py` | #894-r8 | `aucun` |
| `scripts/python/probe_10022r3_ordre_activation_live.py` | #10022-r8 | `capteur` |
| `scripts/python/probe_10033_recensement_live.py` | #10033-r1 | `aucun` |
| `scripts/python/probe_1015r1_close_combat_weakness.py` | #1015-r3 | `aucun` |
| `scripts/python/probe_1025_electrochaff_port.py` | #1025-r3 | `aucun` |
| `scripts/python/probe_1025r1_more_gitz_bonus_live.py` | #1035-r4 | `aucun` |
| `scripts/python/probe_1026r1_face_decision_port.py` | #1026-r3 | `aucun` |
| `scripts/python/probe_1033_reveal_live.py` | #1033-r4 | `etage` |
| `scripts/python/probe_1035r2_blighted_land_bonus_live.py` | #1035-r4 | `aucun` |
| `scripts/python/probe_1044_levier_traits.py` | #1044-r3 | `aucun` |
| `scripts/python/probe_116_necrons.py` | #419-r1-tr5-r8 | `capteur` |
| `scripts/python/probe_175r3_can_be_immune_to_ctor.py` | #175-r4 | `aucun` |
| `scripts/python/probe_202r_decision_abraxas.py` | #202-r1 | `aucun` |
| `scripts/python/probe_229_effect_triggers_active.py` | #426-r1 | `aucun` |
| `scripts/python/probe_230_load_state_turn_state.py` | #462-r4c-r2 | `aucun` |
| `scripts/python/probe_242_fabricator_claw_cap.py` | #462-r4c-r1-r1 | `aucun` |
| `scripts/python/probe_249_unported_rule_carriers.py` | #426-r1 | `aucun` |
| `scripts/python/probe_259_gshared_coverage.py` | #259-a | `capteur` |
| `scripts/python/probe_262_gshared_runtime.py` | #259-b | `capteur` |
| `scripts/python/probe_270r4r2r2_tri_differes.py` | #485-r6 | `aucun` |
| `scripts/python/probe_271_kustom_force_field_reworked.py` | #271-r1 | `aucun` |
| `scripts/python/probe_271r4_face_attack_live.py` | #271-r8 | `aucun` |
| `scripts/python/probe_281_pre_unit_ability_shortcut.py` | #281-r4 | `aucun` |
| `scripts/python/probe_302_4_tile_target_population.py` | #419-r1-tr14-r5-r2-r1-r2-r3 | `aucun` |
| `scripts/python/probe_313_enum_mirror_bijection.py` | #471-r1 | `aucun` |
| `scripts/python/probe_319_scan_fidelity.py` | #471-r1 | `aucun` |
| `scripts/python/probe_330r4_estampilles_des_generes.py` | #471-r1 | `aucun` |
| `scripts/python/probe_350r3a_r4_comparable_gate.py` | #350-r3a-r4-r1 | `aucun` |
| `scripts/python/probe_366r1_*.py` | #366-r1-chaos-friendly-fire | `porteur` |
| `scripts/python/probe_389r2_kill_unit_remove_effects.py` | #389-r5 | `aucun` |
| `scripts/python/probe_391_conftest_dir_identity.py` | #471-r1 | `aucun` |
| `scripts/python/probe_419r1tr10r2_multi_tuiles_canal.py` | #419-r1-tr10-r2 | `aucun` |
| `scripts/python/probe_419r1tr12r2_stats_npc_summon.py` | #419-r1-tr12-r2-r2 | `porteur` |
| `scripts/python/probe_419r1tr9_r4_r1_r2_r1_legendary_commander.py` | #419-r1-tr9-r4-r1-r2-r1b-r2 | `aucun` |
| `scripts/python/probe_419r1tr9r4r1r3_symboles_cites_absents.py` | #419-r1-tr9-r4-r1-r3 | `aucun` |
| `scripts/python/probe_419r6r1_face_decision.py` | #419-r6-r1-r1 | `aucun` |
| `scripts/python/probe_419r6r1r1_sort_utility_trace.py` | #419-r6-r1-r1 | `aucun` |
| `scripts/python/probe_429r1_bit_readers_scan.py` | #429-r1-r2 | `aucun` |
| `scripts/python/probe_429r1r1r1_ability_attack_dead_target.py` | #429-r1-r1-r1-r2 | `porteur` |
| `scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py` | #429-r1-r3-r1-r2-r1 | `aucun` |
| `scripts/python/probe_431_build_literals.py` | #471-r1 | `aucun` |
| `scripts/python/probe_433_r4_r2_r1_r1_c_caster_gates.py` | #433-r4-r2-r1-r1-c-r2 | `aucun` |
| `scripts/python/probe_433_r4_r2_r4_r1_contre_epreuves.py` | #433-r4-r2-r4-r1-r1 | `aucun` |
| `scripts/python/probe_433r4r1r4r2_is_adjacent_substrat_live.py` | #433-r4-r1-r4-r2-r3 | `aucun` |
| `scripts/python/probe_433r4r1r4r2r4_aval_decision_live.py` | #433-r4-r1-r4-r2-r4-r1 | `aucun` |
| `scripts/python/probe_437r1_overwatch_offbyone.py` | #437-r1-r1-r3 | `aucun` |
| `scripts/python/probe_437r1r1r1_effect_face_table.py` | #437-r1-r1-r1-r1 | `aucun` |
| `scripts/python/probe_439_cliquet_peut_rougir.py` | #471-r1 | `aucun` |
| `scripts/python/probe_446_r3_repugnance_followup.py` | #446-r3a | `porteur` |
| `scripts/python/probe_447_r1_r1_zone_inclusion_decision.py` | #447-r6 | `aucun` |
| `scripts/python/probe_448_r3_r1_r1_greffe_sans_canal.py` | #941-r2 | `aucun` |
| `scripts/python/probe_449r2r4r4_bc_damage_fields.py` | #449-r2-r4-r4-r1 | `aucun` |
| `scripts/python/probe_455r4_resilient_window.py` | #455-r4-r1 | `aucun` |
| `scripts/python/probe_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable.py` | #485-r1-r1-r2 | `aucun` |
| `scripts/python/probe_462_r4b_r1_r1_r1_r1_c_r3_r1_r4_post_unit_kill.py` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2 | `aucun` |
| `scripts/python/probe_462r5_dead_imports.py` | #471-r1 | `aucun` |
| `scripts/python/probe_464_sibling_script_cwd.py` | #471-r1 | `aucun` |
| `scripts/python/probe_467_loop_status_fidelity.py` | #471-r1 | `aucun` |
| `scripts/python/probe_467r4_contrat_host.py` | #467-r4-a | `aucun` |
| `scripts/python/probe_468_collision_numeros.py` | #468-r8 | `aucun` |
| `scripts/python/probe_471_tri_etat_cliquets.py` | #471-r1 | `aucun` |
| `scripts/python/probe_477r24_phase_attribution.py` | #10028-r1 | `aucun` |
| `scripts/python/probe_477r24r1_slots_interface.py` | #941-r2 | `aucun` |
| `scripts/python/probe_477r25_slots_autres_interfaces.py` | #433-r3-r3-r2 | `aucun` |
| `scripts/python/probe_480r11_worktree_orphelin.py` | #471-r1 | `aucun` |
| `scripts/python/probe_488r1_onmelta_vivant.py` | #488-r2 | `aucun` |
| `scripts/python/probe_489r2_leftover_law.py` | #489-r2 | `etage` |
| `scripts/python/probe_498_unstoppable_momentum.py` | #498-r5 | `aucun` |
| `scripts/python/probe_503_generalisation.py` | #503-r2 | `porteur` |
| `scripts/python/probe_510_light_of_sanguinius_live.py` | #510-r3 | `aucun` |
| `scripts/python/probe_511_strike_from_the_shadows.py` | #511-r1 | `aucun` |
| `scripts/python/probe_519_temoins_de_camp.py` | #519-r1 | `aucun` |
| `scripts/python/probe_523r1_heavy_warp_flamer_tracking.py` | #523-r3 | `aucun` |
| `scripts/python/probe_526r2_fraicheur_backlog.py` | #526-r3 | `aucun` |
| `scripts/python/probe_547r1_mesure_missing_non_verdict.py` | #547-r9 | `aucun` |
| `scripts/python/probe_585r1_mutants.py` | #585-r4 | `aucun` |
| `scripts/python/probe_589r2r1_beeline_sans_chemin.py` | #589-r2-r1-r1 | `aucun` |
| `scripts/python/probe_594_ctor_litteraux.py` | #594 | `aucun` |
| `scripts/python/probe_889r7_instruments_phase2.py` | #889-r12 | `aucun` |
| `scripts/python/probe_902_reanimator.py` | #902-r2 | `seeding` |
| `scripts/python/probe_909_decision_actives_kit.py` | #909-r4 | `aucun` |
| `scripts/python/probe_911r1_daemonic_patrons_finale_live.py` | #911-r2 | `aucun` |
| `scripts/python/probe_915_prophetic_sentinel.py` | #915-r3 | `aucun` |
| `scripts/python/probe_916r1_effect_slots.py` | #982-r6 | `capteur` |
| `scripts/python/probe_922_intoxicating_elixir_live.py` | #922-r2 | `aucun` |
| `scripts/python/probe_928_legacy_of_combat.py` | #928-r1 | `aucun` |
| `scripts/python/probe_933_premisses_regime.py` | #10027-r2 | `aucun` |
| `scripts/python/probe_937_synaptic_linchpin.py` | #937-r2 | `aucun` |
| `scripts/python/probe_939_bio_minefield.py` | #939-r1 | `etage` |
| `scripts/python/probe_949r1_lecteurs_de_ledger.py` | #949-r3 | `aucun` |
| `scripts/python/probe_950_terrors_lament_tough_to_kill.py` | #1045-r1 | `aucun` |
| `scripts/python/probe_956_purete_de_passe.py` | #956-r1 | `aucun` |
| `scripts/python/probe_964r1_ecog_support.py` | #964-r2 | `aucun` |
| `scripts/python/probe_966r3_execution_du_cast.py` | #966-r6 | `seeding` |
| `scripts/python/probe_969r1_prob_confrontee.py` | #969-r6 | `aucun` |
| `scripts/python/probe_974_decision_gates_live.py` | #974-r2 | `aucun` |
| `scripts/python/probe_987_thunderous_assault_strategy2.py` | #977-r3 | `aucun` |
| `scripts/python/probe_988_ancres_utilite_playbook.py` | #431-r2 | `aucun` |
| `scripts/python/regen_enum_mirrors.py` | #313-r2 | `aucun` |
| `scripts/python/rl_collect_batch.py` | #961-r2 | `aucun` |
| `scripts/python/rl_gen_enum_columns.py` | #270-b | `aucun` |
| `scripts/python/rl_gen_ref_tables.py` | #270-b | `aucun` |
| `scripts/python/symbols_sync.py` | #10003 | `aucun` |
| `scripts/python/targeting_reason.py` | #447-r2 | `aucun` |
| `scripts/python/tests/engine/**` | #277-r1 | `aucun` |
| `scripts/python/tests/engine/**/test_*.py` | #1027-r8 | `aucun` |
| `scripts/python/tests/engine/runner/**` | #449-r2-r4-r2 | `aucun` |
| `scripts/python/tests/engine/runner/*_live.py` | #933-r5 | `aucun` |
| `scripts/python/tests/engine/runner/_charge_regime.py` | #922-r1 | `aucun` |
| `scripts/python/tests/engine/runner/_combat_replay.py` | #949-r1 | `aucun` |
| `scripts/python/tests/engine/runner/conftest.py` | #531-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_10009_foyer_effects_factory_offline.py` | #922-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_1002_reliques_astra_offline.py` | #1002-r2 | `aucun` |
| `scripts/python/tests/engine/runner/test_1024r1_shield_of_faith_live.py` | #1024-r6 | `aucun` |
| `scripts/python/tests/engine/runner/test_1025_electrochaff_backups_live.py` | #1025-r3 | `aucun` |
| `scripts/python/tests/engine/runner/test_1065_floating_death_live.py` | #1065-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_1210_exemplar_of_the_montka_offline.py` | #942-r2 | `aucun` |
| `scripts/python/tests/engine/runner/test_429r1r1r1_ability_attack_dead_target_live.py` | #429-r1-r1-r1-r2 | `porteur` |
| `scripts/python/tests/engine/runner/test_448_r2b_stormboyz_teleporting_in_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/runner/test_448r1r1r3r1_movement_start_live.py` | #10033-r2 | `aucun` |
| `scripts/python/tests/engine/runner/test_585r1_selection_type_releve_offline.py` | #585-r4 | `aucun` |
| `scripts/python/tests/engine/runner/test_889r6_instruments_of_vengeance_offline.py` | #1032-r4 | `aucun` |
| `scripts/python/tests/engine/runner/test_894_arc_scourge_offline.py` | #894-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_928_legacy_of_combat_live.py` | #928-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_939_bio_minefield_offline.py` | #939-r1 | `etage` |
| `scripts/python/tests/engine/runner/test_950r2_prediction_aura_live.py` | #1045-r1 | `aucun` |
| `scripts/python/tests/engine/runner/test_catalog_inject_offline.py` | #254-bc | `aucun` |
| `scripts/python/tests/engine/runner/test_foehammer_live.py` | #281-r4 | `aucun` |
| `scripts/python/tests/engine/runner/test_pick_randomly_one_rng_live.py` | #462-r4 | `aucun` |
| `scripts/python/tests/engine/runner/test_statmod_captured_channel_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/test_270r4r2_cycles_imports_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/test_359r5_selector_only_event_order_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/test_419*_live.py` | #419-r1 | `aucun` |
| `scripts/python/tests/engine/test_419r1tr13_shrapnel_live.py` | #419-r1 | `aucun` |
| `scripts/python/tests/engine/test_433r4r1r4r1_unobscured_canal_offline.py` | #433-r4-r1-r1-r2 | `aucun` |
| `scripts/python/tests/engine/test_433r4r1r4r2r1r1_derivation_morte_offline.py` | #486-r7 | `aucun` |
| `scripts/python/tests/engine/test_446_r3_repugnance_followup_live.py` | #446-r3a | `porteur` |
| `scripts/python/tests/engine/test_447_r1_r1_zone_inclusion_decision_live.py` | #447-r6 | `aucun` |
| `scripts/python/tests/engine/test_477r25_slots_autres_interfaces_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/test_489r1_foyer_combat_offline.py` | #489-r3 | `aucun` |
| `scripts/python/tests/engine/test_498r4_face_decision_is_displaceable_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/test_566r1_sure_kill_gate_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/test_603_index_foyers_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/engine/test_922r2_intoxicating_elixir_ancre_offline.py` | #922-r2 | `aucun` |
| `scripts/python/tests/engine/test_927r3_cache_selector_modes_offline.py` | #1032-r4 | `aucun` |
| `scripts/python/tests/engine/test_932_deathwing_offline.py` | #380-r2 | `aucun` |
| `scripts/python/tests/engine/test_933_premisse_regime_offline.py` | #933-r5 | `aucun` |
| `scripts/python/tests/engine/test_957_decision_faces_offline.py` | #957-r2 | `porteur` |
| `scripts/python/tests/engine/test_963r4_areenemies_null_operand_offline.py` | #431-r2 | `aucun` |
| `scripts/python/tests/engine/test_966r3_execution_du_cast_live.py` | #966-r6 | `seeding` |
| `scripts/python/tests/engine/test_974_custodes_emperors_children_decision_offline.py` | #974-r2 | `aucun` |
| `scripts/python/tests/engine/test_nc_priority_tiers_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/test_366_r1_bcpatch_port_blindspot_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/test_457_r5_perimetre_offline.py` | #463-r2 | `aucun` |
| `scripts/python/tests/test_463r1_ecart_empreinte_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/test_464_sibling_script_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/test_465_ledger_validite_offline.py` | #941-r4 | `aucun` |
| `scripts/python/tests/test_474_optional_locks_offline.py` | #941-r2 | `aucun` |
| `scripts/python/tests/test_480r8_rpc_joignable_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/test_547_ledger_sans_verdict_non_vert_offline.py` | #934-r3 | `aucun` |
| `scripts/python/tests/test_951r2_voies_de_couverture_offline.py` | #951-r5 | `aucun` |
| `scripts/python/tests/test_956_purete_de_passe_offline.py` | #956-r1 | `aucun` |
| `scripts/python/tests/test_additional_hits_variant_signatures_offline.py` | #934-r2 | `aucun` |
| `scripts/python/tests/test_enum_ordinal_ratchet_offline.py` | #934-r2 | `aucun` |
| `scripts/ratchets-10031-liaisons-figees.json` | #10031-r1 | `aucun` |
| `scripts/ratchets-457-footprints.json` | #935-r2 | `aucun` |
| `scripts/ratchets-468-numeros-attestes.json` | #468-r5 | `aucun` |
| `scripts/ratchets-486r15-dette-declencheurs.txt` | #486-r26 | `aucun` |
| `scripts/ratchets-951r2-couverture-attestee.json` | #951-r5 | `aucun` |
| `scripts/sql/006_ref_tables.sql` | #270-b | `aucun` |

## Par BLOCAGE

Un residu `capteur` ne part pas tant qu'aucune fenetre de reinject n'est prevue.

| blocage | n | residus |
|---|---|---|
| `capteur` | 33 | #10011-r3, #10019-r1, #10020-r1, #10021, #10022-r6, #10022-r8, #1020-r10, #1027-r5, #1044-r1, #175-r5, #259-a, #259-b, #273-r, #347-r1, #419-r1-tr11-r2, #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r1, #419-r1-tr5-r8, #433-r4-r2-r1-r1-b, #433-r4-r2-r1-r1-c-r1, #433-r4-r2-r1-r3, #444-r1, #449-r1, #462-r4e-o-r2-r1-r1-r1-r1, #462-r4e-o-r2-r1-r1-r1-r2, #475-r3, #552-r2, #590-r13, #595-r2, #595-r3, #940-r1, #943-r7-r1, #971-r3, #982-r6 |
| `seeding` | 16 | #1008-r1, #1011-r2, #392-r1, #433-r4-r2-r1-r2-r3, #482-r1, #590-r1, #590-r14, #890-r4, #890-r5, #895-r1, #902-r2, #929-r2, #929-r4, #948-r3, #966-r6, #BF-chance |
| `etage` | 36 | #10015-r1, #10022-r5, #1024-r7, #1027-r3, #1030-r1, #1030-r8, #1033-r1, #1033-r4, #1036-r7, #1037-r1, #1065-r2, #17, #27-r9, #419-r1-tr14-r4-r3, #419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r2, #419-r1-tr9-r4-r1-r2-r1a-r1, #419-r4, #433-r4-r1-r1-r1, #433-r4-r1-r3, #433-r4-r3-r1-r1, #443-r2-b2, #444-r2, #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r1, #489-r2, #577-r2, #895-r4, #919-r1, #926-r1, #939-r1, #946-r1, #946-r4, #965-r2, #967-r1, #977-r10, #977-r11 |
| `porteur` | 42 | #10013, #10024-r2, #1022-r1, #1027-r6, #1042-r4, #1048-r2, #366-r1-chaos-friendly-fire, #419-r1-tr12-r2-r2, #419-r1-tr12-r4, #419-r1-tr14-r2, #419-r1-tr14-r5-r2-r1-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r1-r3, #419-r1-tr14-r5-r3, #419-r1-tr9-r4-r1-r2-r2, #429-r1-r1-r1-r2, #433-r4-r1-r2, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r1, #433-r4-r2-r1-r2-r2-r1-r1-r1-r4-r2, #433-r5, #437-r1-r1-r2, #445-r1, #446-r3a, #447-r3, #448-r1-r1-r1-r1-r2-r2, #449-r2-r4-r3, #462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r4, #462-r4e-o-r1-r1-r1, #465-r1, #475-r5, #503-r2, #521-r4, #550-r2, #909-r8, #915-r2, #942-r1, #945-r1, #945-r3, #946-r3, #957-r2, #967-r5, #969-r4, #969-r5 |
| `aucun` | 284 | #10003, #10015, #10019-r2, #1002-r2, #10022-r2, #10022-r4, #10027-r1, #10027-r2, #10028-r1, #10028-r2, #10028-r3, #10030-r1, #10031-r1, #10033-r1, #10033-r2, #10034-r1, #10035-r1, #10035-r2, #10035-r3, #1005-r1, #1005-r2, #1005-r3, #1008-r5, #1009-r1, #1009-r2, #1009-r3, #1013-r1, #1015-r3, #1019-r4, #1020-r11, #1021-r3, #1022-r4, #1024-r6, #1025-r3, #1026-r3, #1027-r4, #1027-r8, #1030-r3, #1031-r1, #1032-r1, #1032-r4, #1032-r5, #1033-r2, #1035-r4, #1036-r9, #1037-r2, #1038-r2, #1041-r1, #1041-r2, #1042-r2, #1044-r3, #1045-r1, #1046-r1, #1064-r1, #1065-r1, #175-r1, #175-r4, #20, #202-r1, #217, #254-bc, #270-a, #270-b, #270-r1-r1-r2, #271-r1, #271-r7, #271-r8, #271-r9, #277-r1, #281-r4, #283-r2, #313-r2, #330-r1, #330-r2, #334-r3, #350-r3a-r4-r1, #352-r1, #366-r1-effect-targets, #369, #380-r2, #389-r4, #389-r5, #390-r1, #390-r6, #390-r7, #390-r8, #419-r1, #419-r1-tr10-r2, #419-r1-tr12-r3, #419-r1-tr14-r5-r2-r1-r2-r1-r2, #419-r1-tr14-r5-r2-r1-r2-r3, #419-r1-tr9-r4-r1-r2-r1b-r2, #419-r1-tr9-r4-r1-r3, #419-r1-tr9-r4-r3, #419-r2, #419-r6-r1-r1, #420-r7, #425-r1, #426-r1, #429-r1-r2, #429-r1-r3-r1-r2-r1, #430-r1, #430-r2, #431-r2, #433-r3-r3-r2, #433-r4-r1-r1-r2, #433-r4-r1-r4-r2-r1-r1-r1-r1-r1, #433-r4-r1-r4-r2-r2, #433-r4-r1-r4-r2-r3, #433-r4-r1-r4-r2-r4-r1, #433-r4-r2-r1-r1-c-r2, #433-r4-r2-r3, #433-r4-r2-r4-r1-r1, #433-r4-r3-r2, #434-r3, #437-r1-r1-r1-r1, #437-r1-r1-r3, #438-r1, #447-r2, #447-r6, #448-r1-r1-r1-r1-r2-r1, #448-r6, #448-r7, #449-r2-r1, #449-r2-r3, #449-r2-r4-r2, #449-r2-r4-r4-r1, #449-r3, #455-r1, #455-r2, #455-r4-r1, #456-r2-r1, #457-r6, #462-r1, #462-r2, #462-r3, #462-r4, #462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r2, #462-r4b-r1-r1-r1-r1-c-r3-r1-r6-r2, #462-r4c-r1-r1, #462-r4c-r1-r2, #462-r4c-r2, #462-r4c-r3, #462-r6-r1, #462-r6-r2, #463-r2, #464-r1b, #464-r1c, #467-r1, #467-r3, #467-r4-a, #467-r5, #467-r6-a, #468-r5, #468-r6, #468-r8, #469-r1, #469-r2, #469-r4, #471-r1, #471-r2, #475-r1, #479-r6, #482-r2, #482-r4, #482-r5, #482-r6, #482-r7, #484-r1, #484-r2, #485-r1-r1-r2, #485-r1-r3, #485-r1-r4, #485-r3, #485-r4, #485-r6, #486-r10, #486-r16, #486-r20, #486-r21, #486-r25, #486-r26, #486-r3, #486-r37, #486-r38, #486-r6, #486-r7, #486-r9, #487-r2, #488-r2, #489-r3, #498-r5, #5, #510-r3, #511-r1, #512-r7, #519-r1, #523-r3, #526-r3, #531-r1, #547-r14, #547-r3, #547-r4-r1, #547-r6, #547-r9, #550-r3, #552-r3, #577-r1, #585-r1, #585-r2, #585-r4, #589-r1-r1-r2-r1-r3, #589-r2-r1-r1, #590-r11, #593, #594, #596-r1, #66-r2, #884-r1, #889-r11, #889-r12, #894-r1, #894-r4, #894-r5, #894-r8, #908-r1, #909-r1, #909-r3, #909-r4, #909-r5, #909-r6, #910-r1, #911-r2, #915-r1, #915-r3, #919-r2, #919-r3, #920-r3, #921-r1, #922-r1, #922-r2, #923-r1, #928-r1, #932-r1, #932-r2, #933-r5, #934-r2, #934-r3, #935-r2, #936-r1-r2, #937-r2, #941-r2, #941-r4, #942-r2, #942-r3, #943-r2, #943-r8, #943-r9, #945-r2, #949-r1, #949-r3, #951-r4, #951-r5, #951-r6, #951-r8, #952-r7, #953-r5, #954-r1, #956-r1, #957-r1, #957-r4, #961-r1, #961-r2, #964-r2, #966-r2, #969-r6, #971-r4, #974-r2, #977-r3, #979-r2, #983-r2, #988-r1, #haze-ord, #o10-c |

## Foyers qui ne designent AUCUN fichier

`aucun` = residu d'arbitrage ou de mesure, rien a editer.
`?` = la fiche dit elle-meme que le foyer depend d'une mesure NON FAITE : c'est un
resultat, pas un abandon. Ces residus se dispatchent SANS contrainte de disjonction
(`aucun`) ou APRES la mesure qui les determine (`?`).

| valeur | n | residus |
|---|---|---|
| `?` (declencheur non etabli, non reproduit sur le 2e couple) —` | 1 | #o10-c |
| `aucun` | 18 | #1027-r6, #1037-r2, #1042-r2, #1042-r4, #390-r8, #448-r6, #890-r4, #909-r1, #909-r8, #919-r2, #919-r3, #921-r1, #943-r7-r1, #943-r8, #945-r2, #957-r1, #957-r4, #983-r2 |
| `aucun (attribution ; outillage livre = probe_961r1_attribution.py + regime range2_flat)` | 1 | #961-r1 |
| `aucun (montage ; tests live a ecrire)` | 1 | #967-r5 |
| `aucun<br>` | 1 | #5 |
| `aucun` --` | 12 | #390-r1, #419-r1-tr12-r4, #419-r1-tr14-r5-r2-r1-r2-r1-r3, #447-r3, #462-r4c-r1-r2, #462-r6-r1, #469-r1, #469-r4, #471-r2, #482-r6, #894-r5, #908-r1 |
| `aucun` —` | 5 | #270-a, #352-r1, #369, #909-r3, #haze-ord |

## Foyers qui designent un fichier A CREER

Absents de l'arbre courant et **jamais** presents dans l'historique : ce sont des
fichiers que la tranche ECRIRA (mirror neuf, probe a monter). Ils comptent comme
foyer pour la disjonction. Un chemin absent qui, LUI, a existe serait un foyer
POURRI -- `test_603_index_foyers_offline.py` etage 3 le refuse.

| chemin | residus |
|---|---|
| `data/unspawnable_rank17.json` | #961-r2 |
| `effects/factory.py` | #922-r1 |
| `frida/classes.tsv` | #922-r1 |
| `frida/hooks/features/ai-step/rpc-runner.ts` | #1044-r1 |
| `frida/hooks/features/rpc-snapshot.ts` | #1027-r5 |
| `scripts/python/engine/playbook/noncomparable/call_ripper_swarms.py` | #1032-r1 |
| `scripts/python/engine/playbook/noncomparable/nova_charge.py` | #1032-r1 |
| `scripts/python/engine/playbook/owner_repair.py` | #271-r9 |
| `scripts/python/engine/playbook/registry.py` | #585-r2 |
| `scripts/python/engine/playbook/talon_of_horus.py` | #419-r2 |
| `scripts/python/engine/runner/operations/triggers/loki/haze_corruption.py` | #462-r4b-r1-r1-r1-r1-c-r3-r1-r6-r2 |
| `scripts/python/probe_1038r2_contemptuous_confrontation_live.py` | #1038-r2 |
| `scripts/python/probe_273_gitignore_inputs.py` | #547-r6 |
| `scripts/python/probe_547r4r1_*.py` | #547-r4-r1 |
| `scripts/python/probe_945_adaptive_strategy.py` | #945-r3 |
| `scripts/python/probe_979_faces_decision_mow.py` | #979-r2 |
| `scripts/python/tests/engine/runner/test_1030_the_lantern_live.py` | #1030-r3 |

