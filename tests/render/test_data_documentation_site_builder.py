import pytest

import os
import json
import shutil

from great_expectations import DataContext
from great_expectations.data_context.store import ExpectationsStore, ValidationsStore
from great_expectations.data_context.types.resource_identifiers import ValidationResultIdentifier, \
    ExpectationSuiteIdentifier
from great_expectations.render.renderer.site_builder import SiteBuilder

from great_expectations.data_context.util import safe_mmkdir, file_relative_path, instantiate_class_from_config


def assert_how_to_buttons(context, index_page_locator_info: str, index_links_dict: dict, show_how_to_buttons=True):
    """Helper function to assert presence or non-presence of how-to buttons and related content in various
        Data Docs pages.
    """

    # these are simple checks for presence of certain page elements
    show_walkthrough_button = "Show Walkthrough"
    walkthrough_modal = "Great Expectations Walkthrough"
    cta_footer = "To continue exploring Great Expectations check out one of these tutorials..."
    how_to_edit_suite_button = "How to Edit This Suite"
    how_to_edit_suite_modal = "How to Edit This Expectation Suite"
    action_card = "Actions"

    how_to_page_elements_dict = {
        "index_pages": [show_walkthrough_button, walkthrough_modal, cta_footer],
        "expectation_suites": [
            how_to_edit_suite_button,
            how_to_edit_suite_modal,
            show_walkthrough_button,
            walkthrough_modal
        ],
        "validation_results": [
            how_to_edit_suite_button,
            how_to_edit_suite_modal,
            show_walkthrough_button,
            walkthrough_modal
        ],
        "profiling_results": [
            action_card,
            show_walkthrough_button,
            walkthrough_modal
        ]
    }

    data_docs_site_dir = os.path.join(
        context._context_root_directory,
        context._project_config.data_docs_sites["local_site"]["store_backend"]["base_directory"]
    )

    page_paths_dict = {
        "index_pages": [index_page_locator_info],
        "expectation_suites": [
            os.path.join(data_docs_site_dir, link_dict["filepath"])
            for link_dict in index_links_dict.get("expectations_links", [])
        ],
        "validation_results": [
            os.path.join(data_docs_site_dir, link_dict["filepath"])
            for link_dict in index_links_dict.get("validations_links", [])
        ],
        "profiling_results": [
            os.path.join(data_docs_site_dir, link_dict["filepath"])
            for link_dict in index_links_dict.get("profiling_links", [])
        ]
    }

    for page_type, page_paths in page_paths_dict.items():
        for page_path in page_paths:
            with open(page_path, 'r') as f:
                page = f.read()
                for how_to_element in how_to_page_elements_dict[page_type]:
                    if show_how_to_buttons:
                        assert how_to_element in page
                    else:
                        assert how_to_element not in page


@pytest.mark.rendered_output
def test_configuration_driven_site_builder(site_builder_data_context_with_html_store_titanic_random):
    context = site_builder_data_context_with_html_store_titanic_random

    context.add_validation_operator(
        "validate_and_store",
        {
            "class_name": "ActionListValidationOperator",
            "action_list": [{
                "name": "store_validation_result",
                "action": {
                    "class_name": "StoreValidationResultAction",
                    "target_store_name": "validations_store",
                }
            }, {
                "name": "extract_and_store_eval_parameters",
                "action": {
                    "class_name": "StoreEvaluationParametersAction",
                    "target_store_name": "evaluation_parameter_store",
                }
            }]
            }
    )

    # profiling the Titanic datasource will generate one expectation suite and one validation
    # that is a profiling result
    datasource_name = 'titanic'
    data_asset_name = "Titanic"
    profiler_name = 'BasicDatasetProfiler'
    generator_name = "subdir_reader"
    context.profile_datasource(datasource_name)

    # creating another validation result using the profiler's suite (no need to use a new expectation suite
    # for this test). having two validation results - one with run id "profiling" - allows us to test
    # the logic of run_id_filter that helps filtering validation results to be included in
    # the profiling and the validation sections.
    batch_kwargs = context.build_batch_kwargs(
        datasource=datasource_name,
        generator=generator_name,
        name=data_asset_name
    )

    expectation_suite_name = "{}.{}.{}.{}".format(
            datasource_name,
            generator_name,
            data_asset_name,
            profiler_name
        )

    batch = context.get_batch(
        batch_kwargs=batch_kwargs,
        expectation_suite_name=expectation_suite_name,
    )
    run_id = "test_run_id_12345"
    context.run_validation_operator(
        assets_to_validate=[batch],
        run_id=run_id,
        validation_operator_name="validate_and_store",
    )

    data_docs_config = context._project_config.data_docs_sites
    local_site_config = data_docs_config['local_site']
    # local_site_config.pop('module_name')  # This isn't necessary
    local_site_config.pop('class_name')

    validations_set = set(context.stores["validations_store"].list_keys())
    assert len(validations_set) == 4
    assert ValidationResultIdentifier(
        expectation_suite_identifier=ExpectationSuiteIdentifier(
            expectation_suite_name=expectation_suite_name
        ),
        run_id="test_run_id_12345",
        batch_identifier=batch.batch_id
    ) in validations_set
    assert ValidationResultIdentifier(
        expectation_suite_identifier=ExpectationSuiteIdentifier(
            expectation_suite_name=expectation_suite_name
        ),
        run_id="profiling",
        batch_identifier=batch.batch_id
    ) in validations_set
    assert ValidationResultIdentifier(
        expectation_suite_identifier=ExpectationSuiteIdentifier(
            expectation_suite_name=expectation_suite_name
        ),
        run_id="profiling",
        batch_identifier=batch.batch_id
    ) in validations_set
    assert ValidationResultIdentifier(
        expectation_suite_identifier=ExpectationSuiteIdentifier(
            expectation_suite_name=expectation_suite_name
        ),
        run_id="profiling",
        batch_identifier=batch.batch_id
    ) in validations_set

    site_builder = SiteBuilder(
            data_context=context,
            runtime_environment={
                "root_directory": context.root_directory
            },
            **local_site_config
        )
    res = site_builder.build()

    index_page_locator_info = res[0]
    index_links_dict = res[1]

    # assert that how-to buttons and related elements are rendered (default behavior)
    assert_how_to_buttons(context, index_page_locator_info, index_links_dict)
    print(json.dumps(index_page_locator_info, indent=2))
    assert index_page_locator_info == context.root_directory + '/uncommitted/data_docs/local_site/index.html'

    print(json.dumps(index_links_dict, indent=2))

    assert "site_name" in index_links_dict

    assert "expectations_links" in index_links_dict
    assert len(index_links_dict["expectations_links"]) == 3

    assert "validations_links" in index_links_dict
    assert len(index_links_dict["validations_links"]) == 1, \
    """
    The only rendered validation should be the one not generated by the profiler
    """

    assert "profiling_links" in index_links_dict
    assert len(index_links_dict["profiling_links"]) == 3

    # save documentation locally
    safe_mmkdir("./tests/render/output")
    safe_mmkdir("./tests/render/output/documentation")

    if os.path.isdir("./tests/render/output/documentation"):
        shutil.rmtree("./tests/render/output/documentation")
    shutil.copytree(
        os.path.join(
            site_builder_data_context_with_html_store_titanic_random.root_directory,
            "uncommitted/data_docs/"
        ),
        "./tests/render/output/documentation"
    )

    # let's create another validation result and run the site builder to add it
    # to the data docs
    # the operator does not have an StoreValidationResultAction action configured, so the site
    # will not be updated without our call to site builder

    expectation_suite_path_component = expectation_suite_name.replace('.', '/')
    validation_result_page_path = os.path.join(
        site_builder.site_index_builder.target_store.store_backends[ValidationResultIdentifier].full_base_directory,
        "validations",
        expectation_suite_path_component,
        run_id,
        batch.batch_id + ".html")

    ts_last_mod_0 = os.path.getmtime(validation_result_page_path)

    run_id = "test_run_id_12346"
    operator_result = context.run_validation_operator(
        assets_to_validate=[batch],
        run_id=run_id,
        validation_operator_name="validate_and_store",
    )

    validation_result_id = ValidationResultIdentifier(
        expectation_suite_identifier=[key for key in operator_result["details"].keys()][0],
        run_id=run_id,
        batch_identifier=batch.batch_id)
    res = site_builder.build(resource_identifiers=[validation_result_id])

    index_links_dict = res[1]

    # verify that an additional validation result HTML file was generated
    assert len(index_links_dict["validations_links"]) == 2

    site_builder.site_index_builder.target_store.store_backends[ValidationResultIdentifier].full_base_directory

    # verify that the validation result HTML file rendered in the previous run was NOT updated
    ts_last_mod_1 = os.path.getmtime(validation_result_page_path)

    assert ts_last_mod_0 == ts_last_mod_1

    # verify that the new method of the site builder that returns the URL of the HTML file that renders
    # a resource

    new_validation_result_page_path = os.path.join(
        site_builder.site_index_builder.target_store.store_backends[ValidationResultIdentifier].full_base_directory,
        "validations",
        expectation_suite_path_component,
        run_id,
        batch.batch_id + ".html")

    html_url = site_builder.get_resource_url(resource_identifier=validation_result_id)
    assert "file://" + new_validation_result_page_path == html_url

    html_url = site_builder.get_resource_url()
    assert "file://" + os.path.join(site_builder.site_index_builder.target_store.store_backends[\
                                        ValidationResultIdentifier].full_base_directory,
                                        "index.html") == html_url


@pytest.mark.rendered_output
def test_configuration_driven_site_builder_without_how_to_buttons(site_builder_data_context_with_html_store_titanic_random):
    context = site_builder_data_context_with_html_store_titanic_random

    context.add_validation_operator(
        "validate_and_store",
        {
            "class_name": "ActionListValidationOperator",
            "action_list": [{
                "name": "store_validation_result",
                "action": {
                    "class_name": "StoreValidationResultAction",
                    "target_store_name": "validations_store",
                }
            }, {
                "name": "extract_and_store_eval_parameters",
                "action": {
                    "class_name": "StoreEvaluationParametersAction",
                    "target_store_name": "evaluation_parameter_store",
                }
            }]
            }
    )

    # profiling the Titanic datasource will generate one expectation suite and one validation
    # that is a profiling result
    datasource_name = 'titanic'
    data_asset_name = "Titanic"
    profiler_name = 'BasicDatasetProfiler'
    generator_name = "subdir_reader"
    context.profile_datasource(datasource_name)

    # creating another validation result using the profiler's suite (no need to use a new expectation suite
    # for this test). having two validation results - one with run id "profiling" - allows us to test
    # the logic of run_id_filter that helps filtering validation results to be included in
    # the profiling and the validation sections.
    batch_kwargs = context.build_batch_kwargs(
        datasource=datasource_name,
        generator=generator_name,
        name=data_asset_name
    )

    expectation_suite_name = "{}.{}.{}.{}".format(
            datasource_name,
            generator_name,
            data_asset_name,
            profiler_name
        )

    batch = context.get_batch(
        batch_kwargs=batch_kwargs,
        expectation_suite_name=expectation_suite_name,
    )
    run_id = "test_run_id_12345"
    context.run_validation_operator(
        assets_to_validate=[batch],
        run_id=run_id,
        validation_operator_name="validate_and_store",
    )

    data_docs_config = context._project_config.data_docs_sites
    local_site_config = data_docs_config['local_site']
    local_site_config.pop('class_name')
    # set this flag to false in config to hide how-to buttons and related elements
    local_site_config["show_how_to_buttons"] = False

    site_builder = SiteBuilder(
            data_context=context,
            runtime_environment={
                "root_directory": context.root_directory
            },
            **local_site_config
        )
    res = site_builder.build()

    index_page_locator_info = res[0]
    index_links_dict = res[1]

    assert_how_to_buttons(context, index_page_locator_info, index_links_dict, show_how_to_buttons=False)


def test_site_builder_with_custom_site_section_builders_config(tmp_path_factory):
    """Test that site builder can handle partially specified custom site_section_builders config"""
    base_dir = str(tmp_path_factory.mktemp("project_dir"))
    project_dir = os.path.join(base_dir, "project_path")
    os.mkdir(project_dir)

    # fixture config swaps site section builder source stores and specifies custom run_id_filters
    shutil.copy(file_relative_path(__file__, "../test_fixtures/great_expectations_custom_local_site_config.yml"),
                str(os.path.join(project_dir, "great_expectations.yml")))
    context = DataContext(context_root_dir=project_dir)
    local_site_config = context._project_config.data_docs_sites.get("local_site")

    module_name = 'great_expectations.render.renderer.site_builder'
    site_builder = instantiate_class_from_config(
        config=local_site_config,
        runtime_environment={
            "data_context": context,
            "root_directory": context.root_directory,
            "site_name": 'local_site'
        },
        config_defaults={
            "module_name": module_name
        }
    )
    site_section_builders = site_builder.site_section_builders

    expectations_site_section_builder = site_section_builders["expectations"]
    assert isinstance(
        expectations_site_section_builder.source_store,
        ValidationsStore
    )

    validations_site_section_builder = site_section_builders["validations"]
    assert isinstance(
        validations_site_section_builder.source_store,
        ExpectationsStore
    )
    assert validations_site_section_builder.run_id_filter == {"ne": "custom_validations_filter"}

    profiling_site_section_builder = site_section_builders["profiling"]
    assert isinstance(
        validations_site_section_builder.source_store,
        ExpectationsStore
    )
    assert profiling_site_section_builder.run_id_filter == {"eq": "custom_profiling_filter"}