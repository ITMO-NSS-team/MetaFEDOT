"""This script vary hyperparameters of a pipeline operations, train and evaluate the pipeline.
To use this script you need to have a file with selected pipelines for each dataset to train the pipelines onto.
This script saves it state to file defined in `processed_models_file` argument of `main` function.
"""

import logging
import pickle
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import List, Tuple
import logging
import numpy as np
import optuna
import pandas as pd
from fedot.core.data.data import DataTypesEnum, InputData
from fedot.core.optimisers.objective import PipelineObjectiveEvaluate
from fedot.core.optimisers.objective.metrics_objective import MetricsObjective
from fedot.core.pipelines.pipeline import Pipeline
from fedot.core.pipelines.tuning.tuner_builder import TunerBuilder as TunerBuilder_
from fedot.core.repository.quality_metrics_repository import ClassificationMetricsEnum
from fedot.core.repository.tasks import Task, TaskTypesEnum
from golem.core.tuning.optuna_tuner import OptunaTuner as OptunaTuner_
from tqdm import tqdm

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)


class CustomDataProducer:
    def __init__(self, trains: List[InputData], tests: List[InputData]):
        self.trains = trains
        self.tests = tests

    def __call__(self):
        return list(zip(self.trains, self.tests))


class TunerBuilder(TunerBuilder_):
    """Overrides data produces."""

    def build(self, trains: List[np.ndarray], tests: List[np.ndarray]):
        objective = MetricsObjective(self.metric)
        data_producer = CustomDataProducer(trains, tests)  # Overriden
        objective_evaluate = PipelineObjectiveEvaluate(
            objective,
            data_producer,
            validation_blocks=self.validation_blocks,
            time_constraint=self.eval_time_constraint,
            eval_n_jobs=self.n_jobs,
        )  # because tuners are not parallelized
        tuner = self.tuner_class(
            objective_evaluate=objective_evaluate,
            adapter=self.adapter,
            iterations=self.iterations,
            early_stopping_rounds=self.early_stopping_rounds,
            timeout=self.timeout,
            search_space=self.search_space,
            n_jobs=self.n_jobs,
            **self.additional_params,
        )
        return tuner


class OptunaTuner(OptunaTuner_):
    """Overrides `tune` method to accept `direction` argument and to return optuna `study` object."""

    def tune(self, graph, direction: str, show_progress: bool = True):
        graph = self.adapter.adapt(graph)
        predefined_objective = partial(self.objective, graph=graph)
        is_multi_objective = self.objectives_number > 1

        self.init_check(graph)

        study = optuna.create_study(directions=[direction] * self.objectives_number)

        init_parameters, has_parameters_to_optimize = self._get_initial_point(graph)
        if not has_parameters_to_optimize:
            self._stop_tuning_with_message(f"Graph {graph.graph_description} has no parameters to optimize")
            tuned_graphs = self.init_graph
        else:
            # Enqueue initial point to try
            if init_parameters:
                study.enqueue_trial(init_parameters)

            study.optimize(
                predefined_objective,
                n_trials=self.iterations,
                n_jobs=self.n_jobs,
                timeout=self.timeout.seconds,
                callbacks=[self.early_stopping_callback],
                show_progress_bar=show_progress,
            )

            if not is_multi_objective:
                best_parameters = study.best_trials[0].params
                tuned_graphs = self.set_arg_graph(graph, best_parameters)
                self.was_tuned = True
            else:
                tuned_graphs = []
                for best_trial in study.best_trials:
                    best_parameters = best_trial.params
                    tuned_graph = self.set_arg_graph(deepcopy(graph), best_parameters)
                    tuned_graphs.append(tuned_graph)
                    self.was_tuned = True
        final_graphs = self.final_check(tuned_graphs, is_multi_objective)
        final_graphs = self.adapter.restore(final_graphs)
        return final_graphs, study


def get_train_test_data(
    train_x: np.ndarray,
    test_x: np.ndarray,
    train_y: np.ndarray,
    test_y: np.ndarray,
    task: Task,
) -> Tuple[List[InputData], List[InputData]]:
    trains = [
        InputData(
            idx=np.arange(0, len(train_x)),
            task=task,
            data_type=DataTypesEnum.table,
            features=train_x,
            target=train_y,
        ),
    ]
    tests = [
        InputData(
            idx=np.arange(0, len(test_x)),
            task=task,
            data_type=DataTypesEnum.table,
            features=test_x,
            target=test_y,
        ),
    ]
    return trains, tests


def tune_hyperparameters(
    pipeline: Pipeline,
    trains: List[InputData],
    tests: List[InputData],
    metric: str,
    study_file: str,
    iterations: int = 50,
) -> None:
    if metric == "roc_auc":
        metric = ClassificationMetricsEnum.ROCAUC
        direction = "minimize"
    elif metric == "logloss":
        metric = ClassificationMetricsEnum.logloss
        direction = "maximize"
    else:
        raise ValueError(f"Uknown metric {metric}")

    tuner = OptunaTuner

    # It is safer to use a single job, though it is slower.
    n_jobs = 1

    task = Task(TaskTypesEnum.classification)

    pipeline_tuner = (
        TunerBuilder(task)
        .with_tuner(tuner)
        .with_metric(metric)
        .with_iterations(iterations)
        .with_n_jobs(n_jobs)
        .build(trains, tests)
    )

    _, study = pipeline_tuner.tune(pipeline, direction)
    with open(study_file, "wb") as f:
        pickle.dump(study, f)


def main(
    knowledge_base_file: str,
    selected_graphs_file: str,
    folds_directory: str,
    save_directory: str,
    processed_models_file: str,
    iterations: int = 50,
):
    df = pd.read_csv(knowledge_base_file)
    # Since knowledgebase is made on Windows.
    model_filenames = df["model_path"].apply(lambda x: x.split("\\")[-1])

    try:
        with open(processed_models_file, "rb") as f:
            processed_models = pickle.load(f)
    except FileNotFoundError:
        processed_models = []

    with open(selected_graphs_file, "rb") as f:
        selected_graphs = pickle.load(f)

    folds_directory = Path(folds_directory)

    save_directory = Path(save_directory)
    if not save_directory.exists():
        save_directory.mkdir(parents=True, exist_ok=True)

    task = Task(TaskTypesEnum.classification)

    skipped_model_filenames = []

    for dataset_id, model_files in tqdm(selected_graphs.items()):
        for model_file in model_files:
            # Fix since file was made on MacOS
            model_file = model_file.replace("/Users/", "/home/")
            model_filename = Path(model_file).name

            key_to_check = f"{dataset_id}/{model_filename.split('.json')[0]}"
            if key_to_check in processed_models:
                continue

            indices = model_filenames == model_filename  # Preliminary check shows that the names are unique.
            record = df[indices]
            if len(record) != 1:
                print(f"Found {len(record)} records for {model_filename}")
                skipped_model_filenames.append(model_filename)
                continue

            record = record.iloc[0]

            dataset_id = record.dataset_id
            dataset_name = record.dataset_name
            fold_id = record.fold_id
            fitness_metric = record.fitness_metric

            study_directory = save_directory.joinpath(dataset_id)
            if not study_directory.exists():
                study_directory.mkdir(parents=True, exist_ok=True)

            study_file = study_directory.joinpath(model_filename.replace(".json", ".pickle"))
            # Skip already processed model.
            if study_file.exists():
                continue

            train_x_filename = f"train_{dataset_name}_fold{fold_id}.npy"
            test_x_filename = f"test_{dataset_name}_fold{fold_id}.npy"
            train_y_filename = f"trainy_{dataset_name}_fold{fold_id}.npy"
            test_y_filename = f"testy_{dataset_name}_fold{fold_id}.npy"

            train_x = np.load(folds_directory.joinpath(train_x_filename))
            test_x = np.load(folds_directory.joinpath(test_x_filename))
            train_y = np.load(folds_directory.joinpath(train_y_filename))
            test_y = np.load(folds_directory.joinpath(test_y_filename))

            trains, tests = get_train_test_data(train_x, test_x, train_y, test_y, task)

            pipeline = Pipeline().load(model_file)

            tune_hyperparameters(pipeline, trains, tests, fitness_metric, study_file, iterations)
            processed_models.append(key_to_check)
            with open(processed_models_file, "wb") as f:
                pickle.dump(processed_models, f)



if __name__ == "__main__":
    # DEFINE YOUR PATHS HERE
    main(
        knowledge_base_file="/home/cherniak/itmo_job/GAMLET/data/knowledge_base_1_v2/knowledge_base.csv",
        selected_graphs_file="/home/cherniak/itmo_job/GAMLET/surrogate_hyperparams/collect_dataset/sorted_selected_graphs.pickle",
        folds_directory="/home/cherniak/itmo_job/datasets_folds",
        save_directory="/home/cherniak/itmo_job/graphs_with_hyperparameters",
        processed_models_file="/home/cherniak/itmo_job/GAMLET/surrogate_hyperparams/collect_dataset/processed_models.pickle",
        iterations=50,
    )

