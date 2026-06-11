from app.pipeline.steps import default_steps
from app.pipeline.steps.executor import ExecutorStep
from app.pipeline.steps.income_tracker import IncomeTrackerStep
from app.pipeline.steps.notifier import NotifierStep


def test_default_steps_include_executor_and_income_tracker():
    steps = default_steps()
    names = [s.name for s in steps]
    assert "executor" in names
    assert "income_tracker" in names
    # executor comes after recommender
    assert names.index("executor") > names.index("recommender")
    # income_tracker comes after executor
    assert names.index("income_tracker") > names.index("executor")
    # last three steps are executor, income_tracker, notifier
    assert isinstance(steps[-3], ExecutorStep)
    assert isinstance(steps[-2], IncomeTrackerStep)
    assert isinstance(steps[-1], NotifierStep)
