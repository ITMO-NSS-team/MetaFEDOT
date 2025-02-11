"""The module contains custom method to train `lib.lightning_modules.GraphTransformer`."""

import json
import os
from pathlib import Path
import pickle
import random
import warnings
from collections import defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
from torch.utils.data import RandomSampler

from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger
from torch_geometric.loader import DataLoader

from gamlet.data_preparation.surrogate_dataset import GraphDataset, PairDataset, SingleDataset
from gamlet.surrogate import surrogate_model


def get_files(path, index_col=0):
    """Loading preprocessed data and creating Dataset objects for model training
    Parameters:
    -----------
    Returns:
         datasets: table of dataset metafeatures
         task_pipe_comb: table of pipeline-dataset correspondance and metric values
         pipelines: list of pipeline objects
         splits: train-test splits
    """
    with open(os.path.join(path, "pipelines.pickle"), "rb") as input_file:
        pipelines = pickle.load(input_file)
    datasets = pd.read_csv(os.path.join(path, "datasets.csv"), index_col=index_col).fillna(0)
    task_pipe_comb = pd.read_csv(os.path.join(path, "task_pipe_comb.csv"))
    task_pipe_comb = task_pipe_comb[task_pipe_comb.y < 10]
    spl_file = Path(path, "split.json")
    splits = None
    if spl_file.is_file():
        with open(spl_file) as f:
            splits = json.load(f)
    return datasets, task_pipe_comb, pipelines, splits


def create_torch_dsets(datasets, task_pipe_comb, pipelines, task_sets, splits=None, is_pair=False):
    """Loading preprocessed data and creating Dataset objects for model training
    Parameters:
    -----------
    is_pair: create dataset with or without pipeline pairs.
    """

    train_task_set, val_task_set, test_task_set = task_sets
    if is_pair:
        train_dataset = PairDataset(
            task_pipe_comb[task_pipe_comb.task_id.isin(train_task_set)].reset_index(drop=True),
            GraphDataset(pipelines),
            datasets,
        )
    else:
        train_dataset = SingleDataset(
            task_pipe_comb[task_pipe_comb.task_id.isin(train_task_set)].reset_index(drop=True),
            GraphDataset(pipelines),
            datasets,
        )

    val_dataset = SingleDataset(
        task_pipe_comb[task_pipe_comb.task_id.isin(val_task_set)].reset_index(drop=True),
        GraphDataset(pipelines),
        datasets,
    )
    test_dataset = SingleDataset(
        task_pipe_comb[task_pipe_comb.task_id.isin(test_task_set)].reset_index(drop=True),
        GraphDataset(pipelines),
        datasets,
    )

    # Infer parameters
    meta_data = dict()
    if isinstance(pipelines[0].in_size, int):
        meta_data["in_size"] = pipelines[0].in_size
    else:
        meta_data["in_size"] = len(pipelines[0].in_size)
    meta_data["dim_dataset"] = datasets.shape[1]
    return train_dataset, val_dataset, test_dataset, meta_data


def train_val_test_split(
    splits: Dict[str, List[int]], tasks_in_file, is_folded=False
) -> Tuple[List[int], List[int], List[int]]:
    VAL_R = 0.15
    TEST_R = 0.15
    try:
        train_task_set = set(splits["train"])
    except KeyError:
        warnings.warn("The key `train` is not found in the json file.")
        train_task_set = set()
    try:
        val_task_set = set(splits["val"])
    except KeyError:
        warnings.warn("The key `val` is not found in the json file.")
        val_task_set = set()
    try:
        test_task_set = set(splits["test"])
    except KeyError:
        warnings.warn("The key `test` is not found in the json file.")
        test_task_set = set()

    if splits is not None:
        train_task_set = train_task_set & tasks_in_file
        val_task_set = val_task_set & tasks_in_file
        test_task_set = test_task_set & tasks_in_file
    else:
        train_task_set, val_task_set, test_task_set = random_train_val_test_split(
            list(tasks_in_file),
            (VAL_R, TEST_R),
        )

    if "val" not in splits:  # if validation is missing, sample it from train
        if is_folded:
            dataset_types = defaultdict(list)
            for t in train_task_set:
                dataset_types[t.split("_")[0]].append(t)
            types_list = sorted(list(dataset_types.keys()))
            train_task_types, val_task_types = random_train_val_test_split(types_list, (VAL_R,))
            train_task_set = set([item for d_type in train_task_types for item in dataset_types[d_type]])
            val_task_set = set([item for d_type in val_task_types for item in dataset_types[d_type]])
        else:
            train_task_set, val_task_set = random_train_val_test_split(list(train_task_set), (VAL_R,))

    return train_task_set, val_task_set, test_task_set


def random_train_val_test_split(tasks: List[int], splits: List[float]) -> Tuple[List[int], List[int], List[int]]:
    """Split tasks list into train/valid/test sets randomly"""
    random.seed(10)
    random.shuffle(tasks)
    ind_splits = [len(tasks)]
    split_ratio = 0
    for split in reversed(splits):
        split_ratio += split
        ind_splits.append(int((1 - split_ratio) * len(tasks)))

    task_sets = []
    ind_prev = 0
    for ind in reversed(ind_splits):
        task_sets.append(set(tasks[ind_prev:ind]))
        ind_prev = ind
    return task_sets


def _create_data_loaders(train_dataset, val_dataset, test_dataset, config):
    train_loader, val_loader, test_loader = None, None, None
    sampler = RandomSampler(train_dataset, replacement=True, num_samples=config["batch_size"] * 50)

    if train_dataset is not None:
        train_loader = DataLoader(
            train_dataset,
            sampler=sampler,
            batch_size=config["batch_size"],
            num_workers=config["num_dataloader_workers"],
        )
    if val_dataset is not None:
        val_loader = DataLoader(
            val_dataset,
            batch_size=config["batch_size"],
            num_workers=config["num_dataloader_workers"],
        )
    if test_dataset is not None:
        test_loader = DataLoader(
            test_dataset,
            batch_size=config["batch_size"],
            num_workers=config["num_dataloader_workers"],
        )
    return train_loader, val_loader, test_loader


def _parse_dataset_config(config):
    dataset_configs = {}
    dataset_configs["is_pair"] = False

    if config["model"]["name"] == "RankingPipelineDatasetSurrogateModel":
        dataset_configs["is_pair"] = True

    if config["model"]["model_parameters"]["dataset_encoder_type"] == "l":
        dataset_configs["index_col"] = [0, 1]
    else:
        dataset_configs["index_col"] = 0
    return dataset_configs


def _create_model(config, meta_data):
    model_class = getattr(surrogate_model, config["model"]["name"])
    config["model"]["model_parameters"]["in_size"] = meta_data["in_size"]
    config["model"]["model_parameters"]["dim_dataset"] = meta_data["dim_dataset"]

    dim_feedforward = 2 * config["model"]["model_parameters"]["d_model"]
    config["model"]["model_parameters"]["dim_feedforward"] = dim_feedforward
    model = model_class(config["model"]["model_parameters"])
    return model


def train_surrogate_model(config: Dict[str, Any]) -> List[Dict[str, float]]:
    """Create surrogate model and do training according to config parameters."""
    train_loader, val_loader, test_loader, config, meta_data = setup_loaders(config)
    do_training(train_loader, val_loader, test_loader, config, meta_data)


def setup_loaders(config: Dict[str, Any]):
    dataset_configs = _parse_dataset_config(config)

    datasets, task_pipe_comb, pipelines, splits = get_files(
        config["dataset_params"]["root_path"], index_col=dataset_configs["index_col"]
    )

    tasks_in_file = set(datasets.index.get_level_values(0))
    task_sets = train_val_test_split(splits, tasks_in_file, is_folded=config["dataset_params"]["is_folded"])
    train_dataset, val_dataset, test_dataset, meta_data = create_torch_dsets(
        datasets, task_pipe_comb, pipelines, task_sets, splits=splits, is_pair=dataset_configs["is_pair"]
    )
    assert len(train_dataset) != 0
    assert len(val_dataset) != 0
    assert len(test_dataset) != 0
    train_loader, val_loader, test_loader = _create_data_loaders(train_dataset, val_dataset, test_dataset, config)
    return train_loader, val_loader, test_loader, config, meta_data


def do_training(train_loader, val_loader, test_loader, config, meta_data):
    # creating surrogate model
    model = _create_model(config, meta_data)

    # setting up training params
    if config["tensorboard_logger"] is not None:
        logger = TensorBoardLogger(**config["tensorboard_logger"])
    else:
        logger = None

    model_checkpoint_callback = ModelCheckpoint(**config["model_checkpoint_callback"])

    if config["early_stopping_callback"] is not None:
        early_stopping_callback = EarlyStopping(**config["early_stopping_callback"])
    else:
        early_stopping_callback = None

    trainer = Trainer(
        **config["trainer"],
        logger=logger,
        callbacks=[c for c in [model_checkpoint_callback, early_stopping_callback] if c is not None],
        gradient_clip_val=0.5,
    )
    trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=val_loader)

    model_class = getattr(surrogate_model, config["model"]["name"])
    model = model_class.load_from_checkpoint(model_checkpoint_callback.best_model_path)
    model.eval()
    test_results = trainer.test(model, dataloaders=test_loader)
    return test_results


def test_ranking(config: Dict[str, Any]) -> List[Dict[str, float]]:  # Evalutate surrogate
    """Test surrogate model"""
    dataset_configs = _parse_dataset_config(config)

    datasets, task_pipe_comb, pipelines, splits = get_files(
        config["dataset_params"]["root_path"], index_col=dataset_configs["index_col"]
    )
    task_set_train = set(splits["train"])
    pipe_list_train = task_pipe_comb[task_pipe_comb.task_id.isin(task_set_train)].pipeline_id.unique()
    splits["train"] = []
    splits["val"] = []
    tasks_in_file = set(datasets.index.get_level_values(0))
    task_sets = train_val_test_split(splits, tasks_in_file)

    d_cand = pd.DataFrame()
    d_cand["pipeline_id"] = np.concatenate([pipe_list_train for d in splits["test"]])
    d_cand["task_id"] = np.concatenate([np.full((len(pipe_list_train), 1), d) for d in splits["test"]])
    d_cand["y"] = 0

    _, _, test_dataset, _ = create_torch_dsets(
        datasets, d_cand, pipelines, task_sets, splits=splits
    )
    _, _, test_loader = _create_data_loaders(None, None, test_dataset, config)

    model_class = getattr(surrogate_model, config["model"]["name"])
    chpoint_dir = config["model_data"]["save_dir"] + "checkpoints/"
    model = model_class.load_from_checkpoint(
        checkpoint_path=chpoint_dir + os.listdir(chpoint_dir)[0],
        hparams_file=config["model_data"]["save_dir"] + "hparams.yaml",
    )
    model.eval()

    task_ids, pipe_ids, y_preds, y_trues = [], [], [], []
    with torch.no_grad():
        for batch in test_loader:
            model.test_step(batch)
            res = model.test_step_outputs.pop()
            task_ids.append(res["task_id"])
            pipe_ids.append(res["pipe_id"])
            y_preds.append(res["y_pred"])
            y_trues.append(res["y_true"])

    df = pd.DataFrame(
        {
            "task_id": np.concatenate(task_ids),
            "pipe_id": np.concatenate(pipe_ids),
            "y_pred": np.concatenate(y_preds),
            "y_true": np.concatenate(y_trues),
        }
    )

    with open(config["dataset_params"]["root_path"] + "/pipelines_fedot.pickle", "rb") as input_file:
        pipelines_fedot = pickle.load(input_file)

    res = df.loc[df.groupby(["task_id"])["y_pred"].idxmax()]
    res["model_str"] = [str(pipelines_fedot[i]) for i in res.pipe_id.values]
    res = res[["task_id", "y_true", "pipe_id", "model_str"]]
    res["y_true"] = -res["y_true"]
    res.columns = ["dataset", "fitness", "pipe_id", "model_str"]

    res.to_csv("./experiments/surrogate_test_set_prediction.csv", index=False)
    pipelines_top = {i: pipelines_fedot[i] for i in res.pipe_id}
    with open("./experiments/top_pipelines.pickle", "wb") as file:
        pickle.dump(pipelines_top, file)
