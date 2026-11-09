import pytest

from regression_lab.dataset import load_benchmark, load_fixture


@pytest.fixture
def benchmark():
    return load_benchmark()


@pytest.fixture
def baseline(benchmark):
    return load_fixture("baseline", benchmark[1])


@pytest.fixture
def candidate(benchmark):
    return load_fixture("candidate", benchmark[1])
