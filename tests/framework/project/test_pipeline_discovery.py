import sys
import textwrap
import warnings
from pathlib import Path

import pytest

from kedro.framework.project import configure_project, find_pipelines


@pytest.fixture
def mock_package_name_with_pipelines(tmp_path, request):
    package_name = "test_package"
    pipelines_dir = tmp_path / package_name / "pipelines"
    pipelines_dir.mkdir(parents=True)
    (pipelines_dir / "__init__.py").touch()
    for pipeline_name in request.param:
        pipeline_dir = pipelines_dir / pipeline_name
        pipeline_dir.mkdir()
        (pipeline_dir / "__init__.py").write_text(
            textwrap.dedent(
                f"""
                from kedro.pipeline import Pipeline, node, pipeline


                def create_pipeline(**kwargs) -> Pipeline:
                    return pipeline([node(lambda: 1, None, "{pipeline_name}")])
                """
            )
        )
    sys.path.insert(0, str(tmp_path))
    yield package_name
    sys.path.pop(0)

    # Make sure that the `importlib_resources.files` in `find_pipelines`
    # will point to the correct `test_package.pipelines` not from cache.
    del sys.modules[f"{package_name}.pipelines"]


@pytest.fixture
def pipeline_names(request):
    return request.param


@pytest.mark.parametrize(
    "mock_package_name_with_pipelines,pipeline_names",
    [(x, x) for x in [set(), {"my_pipeline"}]],
    indirect=True,
)
def test_find_pipelines(
    mock_package_name_with_pipelines,
    pipeline_names,
):
    configure_project(mock_package_name_with_pipelines)
    pipelines = find_pipelines()
    assert set(pipelines) == pipeline_names | {"__default__"}
    assert sum(pipelines.values()).outputs() == pipeline_names


@pytest.mark.parametrize(
    "mock_package_name_with_pipelines,pipeline_names",
    [(x, x) for x in [set(), {"good_pipeline"}]],
    indirect=True,
)
def test_find_pipelines_skips_modules_without_create_pipelines_function(
    mock_package_name_with_pipelines,
    pipeline_names,
):
    # Create a module without `create_pipelines` in the `pipelines` dir.
    pipelines_dir = Path(sys.path[0]) / mock_package_name_with_pipelines / "pipelines"
    pipeline_dir = pipelines_dir / "bad_touch"
    pipeline_dir.mkdir()
    (pipeline_dir / "__init__.py").touch()

    configure_project(mock_package_name_with_pipelines)
    with pytest.warns(
        UserWarning, match="module does not expose a 'create_pipeline' function"
    ):
        pipelines = find_pipelines()
    assert set(pipelines) == pipeline_names | {"__default__"}
    assert sum(pipelines.values()).outputs() == pipeline_names


@pytest.mark.parametrize(
    "mock_package_name_with_pipelines,pipeline_names",
    [(x, x) for x in [set(), {"my_pipeline"}]],
    indirect=True,
)
def test_find_pipelines_skips_modules_with_unexpected_return_value_type(
    mock_package_name_with_pipelines,
    pipeline_names,
):
    # Define `create_pipelines` so that it does not return a `Pipeline`.
    pipelines_dir = Path(sys.path[0]) / mock_package_name_with_pipelines / "pipelines"
    pipeline_dir = pipelines_dir / "not_my_pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from typing import Dict

            from kedro.pipeline import Pipeline, node, pipeline


            def create_pipeline(**kwargs) -> Dict[str, Pipeline]:
                return {
                    "pipe1": pipeline([node(lambda: 1, None, "pipe1")]),
                    "pipe2": pipeline([node(lambda: 2, None, "pipe2")]),
                }
            """
        )
    )

    configure_project(mock_package_name_with_pipelines)
    with pytest.warns(
        UserWarning,
        match=(
            r"Expected the 'create_pipeline' function in the '\S+' "
            r"module to return a 'Pipeline' object, got 'dict' instead."
        ),
    ):
        pipelines = find_pipelines()
    assert set(pipelines) == pipeline_names | {"__default__"}
    assert sum(pipelines.values()).outputs() == pipeline_names


@pytest.mark.parametrize(
    "mock_package_name_with_pipelines,pipeline_names",
    [(x, x) for x in [set(), {"my_pipeline"}]],
    indirect=True,
)
def test_find_pipelines_skips_regular_files_within_the_pipelines_folder(
    mock_package_name_with_pipelines,
    pipeline_names,
):
    # Create a regular file (not a subdirectory) in the `pipelines` dir.
    pipelines_dir = Path(sys.path[0]) / mock_package_name_with_pipelines / "pipelines"
    (pipelines_dir / "not_my_pipeline.py").touch()

    configure_project(mock_package_name_with_pipelines)
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=UserWarning)
        pipelines = find_pipelines()
    assert set(pipelines) == pipeline_names | {"__default__"}
    assert sum(pipelines.values()).outputs() == pipeline_names


@pytest.mark.parametrize(
    "mock_package_name_with_pipelines,pipeline_names",
    [(x, x) for x in [set(), {"my_pipeline"}]],
    indirect=True,
)
def test_find_pipelines_skips_modules_that_cause_exceptions_upon_import(
    mock_package_name_with_pipelines,
    pipeline_names,
):
    # Create a module that will result in errors when we try to load it.
    pipelines_dir = Path(sys.path[0]) / mock_package_name_with_pipelines / "pipelines"
    pipeline_dir = pipelines_dir / "boulevard_of_broken_pipelines"
    pipeline_dir.mkdir()
    (pipeline_dir / "__init__.py").write_text("I walk a lonely road...")

    configure_project(mock_package_name_with_pipelines)
    with pytest.warns(
        UserWarning,
        match=r"An error occurred while importing the '\S+' module.",
    ):
        pipelines = find_pipelines()
    assert set(pipelines) == pipeline_names | {"__default__"}
    assert sum(pipelines.values()).outputs() == pipeline_names
