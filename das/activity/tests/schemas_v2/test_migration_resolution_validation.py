from activity.schemas.migration.choice_processor import (
    ChoiceProcessor,
    HardcodedChoice,
    HardcodedChoiceResolution,
    ResolutionStrategy,
)
from activity.schemas.migration.logger import LogContext, MigrationLogger
from activity.schemas.migration.service import (
    MigrationRequest,
    MigrationResult,
    MigrationService,
)

_test_context = LogContext(migration_request_id="MR-test", tenant_name="test", dry_run=True)
_test_logger = MigrationLogger(context=_test_context)


class TestHardcodedChoiceResolutionContract:
    def test_from_dict_normalizes_property_path_to_list(self):
        resolution = HardcodedChoiceResolution.from_dict(
            {
                "property_path": ("details", "severity"),
                "strategy": "USE_EXISTING",
                "choice_field_name": "severity",
            }
        )

        assert resolution.property_path == ["details", "severity"]

    def test_generated_resolution_options_include_property_path(self):
        processor = ChoiceProcessor()
        processor.existing_choices = {}
        processor.proposed_choices = {}
        hardcoded_choice = HardcodedChoice(
            property_path=["details", "severity"],
            choices=[{"value": "minor", "display": "Minor"}],
        )
        migration_result = MigrationResult(event_type_value="fire_rep", log=_test_logger.for_event_type("fire_rep"))

        resolution_options = processor.get_resolution_options(migration_result, hardcoded_choice)

        assert resolution_options
        assert all(option.property_path == ["details", "severity"] for option in resolution_options)


class TestResolutionSelectionValidation:
    def test_matches_selection_against_generated_options(self):
        processor = ChoiceProcessor()
        hardcoded_choice = HardcodedChoice(
            property_path=["severity"],
            resolution_options=[
                HardcodedChoiceResolution(
                    property_path=["severity"],
                    strategy=ResolutionStrategy.USE_EXISTING,
                    choice_field_name="severity",
                )
            ],
        )
        selection = HardcodedChoiceResolution(
            property_path=["severity"],
            strategy=ResolutionStrategy.USE_EXISTING,
            choice_field_name="severity",
        )

        matched_option = processor.find_matching_resolution_option(hardcoded_choice, selection)

        assert matched_option is not None
        assert matched_option.choice_field_name == "severity"

    def test_auto_resolves_first_option_when_no_selection_provided(self):
        service = MigrationService(request=None, logger=_test_logger)
        processor = ChoiceProcessor()
        hardcoded_choice = HardcodedChoice(
            property_path=["severity"],
            resolution_options=[
                HardcodedChoiceResolution(
                    property_path=["severity"],
                    strategy=ResolutionStrategy.USE_EXISTING,
                    choice_field_name="severity",
                ),
                HardcodedChoiceResolution(
                    property_path=["severity"],
                    strategy=ResolutionStrategy.CREATE_NEW,
                    choice_field_name="new_severity",
                ),
            ],
        )
        result = MigrationResult(
            event_type_value="fire_rep",
            log=_test_logger.for_event_type("fire_rep"),
            migration_request=MigrationRequest(event_type_value="fire_rep"),
            hardcoded_choices=[hardcoded_choice],
        )

        service.resolve_and_validate_migration_requests([result], processor)

        assert result.success is True
        assert result.resolved_hardcoded_choices[0].resolution.strategy == ResolutionStrategy.USE_EXISTING

    def test_accepts_matching_selected_resolution(self):
        service = MigrationService(request=None, logger=_test_logger)
        processor = ChoiceProcessor()
        selection = HardcodedChoiceResolution(
            property_path=["severity"],
            strategy=ResolutionStrategy.USE_EXISTING,
            choice_field_name="existing_severity",
        )
        hardcoded_choice = HardcodedChoice(
            property_path=["severity"],
            resolution_options=[
                HardcodedChoiceResolution(
                    property_path=["severity"],
                    strategy=ResolutionStrategy.USE_EXISTING,
                    choice_field_name="existing_severity",
                ),
                HardcodedChoiceResolution(
                    property_path=["severity"],
                    strategy=ResolutionStrategy.CREATE_NEW,
                    choice_field_name="severity",
                ),
            ],
        )
        result = MigrationResult(
            event_type_value="fire_rep",
            log=_test_logger.for_event_type("fire_rep"),
            migration_request=MigrationRequest(
                event_type_value="fire_rep",
                hardcoded_choices_resolutions=[selection],
            ),
            hardcoded_choices=[hardcoded_choice],
        )

        service.resolve_and_validate_migration_requests([result], processor)

        assert result.success is True

    def test_rejects_unknown_selected_resolution_property_path(self):
        service = MigrationService(request=None, logger=_test_logger)
        processor = ChoiceProcessor()
        result = MigrationResult(
            event_type_value="fire_rep",
            log=_test_logger.for_event_type("fire_rep"),
            migration_request=MigrationRequest(
                event_type_value="fire_rep",
                hardcoded_choices_resolutions=[
                    HardcodedChoiceResolution(
                        property_path=["unknown_field"],
                        strategy=ResolutionStrategy.USE_EXISTING,
                        choice_field_name="severity",
                    )
                ],
            ),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["severity"],
                            strategy=ResolutionStrategy.USE_EXISTING,
                            choice_field_name="severity",
                        )
                    ],
                )
            ],
        )

        service.resolve_and_validate_migration_requests([result], processor)

        assert result.success is False
        assert "Unknown hardcoded choice resolution property path" in result.errors[0]

    def test_rejects_use_proposed_from_later_request(self):
        service = MigrationService(request=None, logger=_test_logger)
        processor = ChoiceProcessor()
        consumer = MigrationResult(
            event_type_value="consumer",
            log=_test_logger.for_event_type("consumer"),
            migration_request=MigrationRequest(
                event_type_value="consumer",
                hardcoded_choices_resolutions=[
                    HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.USE_PROPOSED,
                        choice_field_name="shared_severity",
                    )
                ],
            ),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["severity"],
                            strategy=ResolutionStrategy.USE_PROPOSED,
                            choice_field_name="shared_severity",
                        )
                    ],
                )
            ],
        )
        producer = MigrationResult(
            event_type_value="producer",
            log=_test_logger.for_event_type("producer"),
            migration_request=MigrationRequest(
                event_type_value="producer",
                hardcoded_choices_resolutions=[
                    HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="shared_severity",
                    )
                ],
            ),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["severity"],
                            strategy=ResolutionStrategy.CREATE_NEW,
                            choice_field_name="shared_severity",
                        )
                    ],
                )
            ],
        )

        service.resolve_and_validate_migration_requests([consumer, producer], processor)

        assert consumer.success is False
        assert any("created by a later migration request" in error for error in consumer.errors)
        assert producer.success is True

    def test_rejects_duplicate_custom_create_new_choice_field_names(self):
        service = MigrationService(request=None, logger=_test_logger)
        processor = ChoiceProcessor()
        first_result = MigrationResult(
            event_type_value="first",
            log=_test_logger.for_event_type("first"),
            migration_request=MigrationRequest(
                event_type_value="first",
                hardcoded_choices_resolutions=[
                    HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="shared_severity",
                    )
                ],
            ),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["severity"],
                            strategy=ResolutionStrategy.CREATE_NEW,
                            choice_field_name="severity",
                        )
                    ],
                )
            ],
        )
        second_result = MigrationResult(
            event_type_value="second",
            log=_test_logger.for_event_type("second"),
            migration_request=MigrationRequest(
                event_type_value="second",
                hardcoded_choices_resolutions=[
                    HardcodedChoiceResolution(
                        property_path=["impact"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="shared_severity",
                    )
                ],
            ),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["impact"],
                    choices=[{"value": "high", "display": "High"}],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["impact"],
                            strategy=ResolutionStrategy.CREATE_NEW,
                            choice_field_name="impact",
                        )
                    ],
                )
            ],
        )

        service.resolve_and_validate_migration_requests([first_result, second_result], processor)

        assert first_result.success is True
        assert second_result.success is False
        assert any("already planned for creation in this batch" in error for error in second_result.errors)

    def test_rejects_custom_create_new_name_collision_with_existing_field(self):
        service = MigrationService(request=None, logger=_test_logger)
        service.existing_choices = {"shared_severity": ["low"]}
        processor = ChoiceProcessor()
        result = MigrationResult(
            event_type_value="first",
            log=_test_logger.for_event_type("first"),
            migration_request=MigrationRequest(
                event_type_value="first",
                hardcoded_choices_resolutions=[
                    HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="shared_severity",
                    )
                ],
            ),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["severity"],
                            strategy=ResolutionStrategy.CREATE_NEW,
                            choice_field_name="severity",
                        )
                    ],
                )
            ],
        )

        service.resolve_and_validate_migration_requests([result], processor)

        assert result.success is False
        assert any("already exists and cannot be created again" in error for error in result.errors)

    def test_allows_same_result_create_new_and_use_proposed_dependency(self):
        service = MigrationService(request=None, logger=_test_logger)
        processor = ChoiceProcessor()
        result = MigrationResult(
            event_type_value="fire_rep",
            log=_test_logger.for_event_type("fire_rep"),
            migration_request=MigrationRequest(
                event_type_value="fire_rep",
                hardcoded_choices_resolutions=[
                    HardcodedChoiceResolution(
                        property_path=["severity"],
                        strategy=ResolutionStrategy.CREATE_NEW,
                        choice_field_name="shared_severity",
                    ),
                    HardcodedChoiceResolution(
                        property_path=["impact"],
                        strategy=ResolutionStrategy.USE_PROPOSED,
                        choice_field_name="shared_severity",
                    ),
                ],
            ),
            hardcoded_choices=[
                HardcodedChoice(
                    property_path=["severity"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["severity"],
                            strategy=ResolutionStrategy.CREATE_NEW,
                            choice_field_name="severity",
                        )
                    ],
                ),
                HardcodedChoice(
                    property_path=["impact"],
                    choices=[{"value": "low", "display": "Low"}],
                    resolution_options=[
                        HardcodedChoiceResolution(
                            property_path=["impact"],
                            strategy=ResolutionStrategy.USE_PROPOSED,
                            choice_field_name="shared_severity",
                        )
                    ],
                ),
            ],
        )

        service.resolve_and_validate_migration_requests([result], processor)

        assert result.success is True
        assert service.can_persist_result(result, set()) is True
