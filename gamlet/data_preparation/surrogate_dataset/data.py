import os
from random import sample

import torch
import torch_geometric.utils as utils
from torch.utils.data import Dataset
from torch_geometric.data import Data


def my_inc(self, key, value, *args, **kwargs):
    if key == "subgraph_edge_index":
        return self.num_subgraph_nodes
    if key == "subgraph_node_idx":
        return self.num_nodes
    if key == "subgraph_indicator":
        return self.num_nodes
    elif "index" in key:
        return self.num_nodes
    else:
        return 0


class GraphDataset(object):
    """Pipelines dataset for Structure-Aware Transformer.
    Computes rich feature representation of the grap including subraph features.
    """

    def __init__(
        self,
        dataset,
        degree=False,
        k_hop=2,
        se="gnn",
        use_subgraph_edge_attr=False,
        cache_path=None,
        return_complete_index=True,
    ):
        self.dataset = dataset

        self.n_features = dataset[0].x.shape[-1]
        self.degree = degree
        self.compute_degree()
        self.abs_pe_list = None
        self.return_complete_index = return_complete_index
        self.k_hop = k_hop
        self.se = se
        self.use_subgraph_edge_attr = use_subgraph_edge_attr
        self.cache_path = cache_path
        if self.se == "khopgnn":
            Data.__inc__ = my_inc
            self.extract_subgraphs()

    def compute_degree(self):
        if not self.degree:
            self.degree_list = None
            return
        self.degree_list = []
        for g in self.dataset:
            deg = 1.0 / torch.sqrt(1.0 + utils.degree(g.edge_index[0], g.num_nodes))
            self.degree_list.append(deg)

    def extract_subgraphs(self):
        print("Extracting {}-hop subgraphs...".format(self.k_hop))
        # indicate which node in a graph it is; for each graph, the
        # indices will range from (0, num_nodes). PyTorch will then
        # increment this according to the batch size
        self.subgraph_node_index = []

        # Each graph will become a block diagonal adjacency matrix of
        # all the k-hop subgraphs centered around each node. The edge
        # indices get augumented within a given graph to make this
        # happen (and later are augmented for proper batching)
        self.subgraph_edge_index = []

        # This identifies which indices correspond to which subgraph
        # (i.e. which node in a graph)
        self.subgraph_indicator_index = []

        # This gets the edge attributes for the new indices
        if self.use_subgraph_edge_attr:
            self.subgraph_edge_attr = []

        for i in range(len(self.dataset)):
            if self.cache_path is not None:
                filepath = "{}_{}.pt".format(self.cache_path, i)
                if os.path.exists(filepath):
                    continue
            graph = self.dataset[i]
            node_indices = []
            edge_indices = []
            edge_attributes = []
            indicators = []
            edge_index_start = 0

            for node_idx in range(graph.num_nodes):
                sub_nodes, sub_edge_index, _, edge_mask = utils.k_hop_subgraph(
                    node_idx, self.k_hop, graph.edge_index, relabel_nodes=True, num_nodes=graph.num_nodes
                )
                node_indices.append(sub_nodes)
                edge_indices.append(sub_edge_index + edge_index_start)
                indicators.append(torch.zeros(sub_nodes.shape[0]).fill_(node_idx))
                if self.use_subgraph_edge_attr and graph.edge_attr is not None:
                    edge_attributes.append(graph.edge_attr[edge_mask])  # CHECK THIS DIDN"T BREAK ANYTHING
                edge_index_start += len(sub_nodes)

            if self.cache_path is not None:
                if self.use_subgraph_edge_attr and graph.edge_attr is not None:
                    subgraph_edge_attr = torch.cat(edge_attributes)
                else:
                    subgraph_edge_attr = None
                torch.save(
                    {
                        "subgraph_node_index": torch.cat(node_indices),
                        "subgraph_edge_index": torch.cat(edge_indices, dim=1),
                        "subgraph_indicator_index": torch.cat(indicators).type(torch.LongTensor),
                        "subgraph_edge_attr": subgraph_edge_attr,
                    },
                    filepath,
                )
            else:
                self.subgraph_node_index.append(torch.cat(node_indices))
                self.subgraph_edge_index.append(torch.cat(edge_indices, dim=1))
                self.subgraph_indicator_index.append(torch.cat(indicators))
                if self.use_subgraph_edge_attr and graph.edge_attr is not None:
                    self.subgraph_edge_attr.append(torch.cat(edge_attributes))
        print("Done!")

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, index):
        if index > len(self.dataset):
            print(index)
        data = self.dataset[index]

        if self.n_features == 1:
            data.x = data.x.squeeze(-1)
        # Fix for FEDOT data. In OpenML data minimal number of nodes is 2 but in FEDOT is 1.
        if len(data.x.shape) == 0:
            data.x = data.x.unsqueeze(0)
        n = data.num_nodes
        s = torch.arange(n)
        if self.return_complete_index:
            data.complete_edge_index = torch.vstack((s.repeat_interleave(n), s.repeat(n)))
        data.degree = None
        if self.degree:
            data.degree = self.degree_list[index]
        data.abs_pe = None
        if self.abs_pe_list is not None and len(self.abs_pe_list) == len(self.dataset):
            data.abs_pe = self.abs_pe_list[index]

        # add subgraphs and relevant meta data
        if self.se == "khopgnn":
            if self.cache_path is not None:
                cache_file = torch.load("{}_{}.pt".format(self.cache_path, index))
                data.subgraph_edge_index = cache_file["subgraph_edge_index"]
                data.num_subgraph_nodes = len(cache_file["subgraph_node_index"])
                data.subgraph_node_idx = cache_file["subgraph_node_index"]
                data.subgraph_edge_attr = cache_file["subgraph_edge_attr"]
                data.subgraph_indicator = cache_file["subgraph_indicator_index"]
                return data
            data.subgraph_edge_index = self.subgraph_edge_index[index]
            data.num_subgraph_nodes = len(self.subgraph_node_index[index])
            data.subgraph_node_idx = self.subgraph_node_index[index]
            if self.use_subgraph_edge_attr and data.edge_attr is not None:
                data.subgraph_edge_attr = self.subgraph_edge_attr[index]
            data.subgraph_indicator = self.subgraph_indicator_index[index].type(torch.LongTensor)
        else:
            data.num_subgraph_nodes = None
            data.subgraph_node_idx = None
            data.subgraph_edge_index = None
            data.subgraph_indicator = None

        return data


class SingleDataset(Dataset):
    """Dataset for surrogate model. Stores dataset-pipeline experiments data."""

    def __init__(self, indxs, data_pipe, data_dset):
        self.data_pipe = data_pipe
        self.data_dset = data_dset

        self.indxs = indxs[indxs.y > -1000000]
        self.indxs = self.indxs.sort_values(by="y", ascending=False)

        cnts = self.indxs.groupby("task_id").size()
        cnts = cnts[cnts > 1]  # remove records with only 1 pipeline per dataset
        self.indxs = self.indxs[self.indxs.task_id.isin(set(cnts.index))]
        # self.weights = 1./cnts  # dataset weight

    def __len__(self):
        return len(self.indxs)

    def __getitem__(self, idx):
        """
        Args:
            idx: index of dataset-pipeline pair.
        Returns:
            task_id: index of dataset.
            pipe_id: index of pipeline.
            x_pipeline: Data object of pipeline.
            x_dataset: vector of dataset meta-features.
            y: value of quality metric.
        """
        task_id = self.indxs["task_id"].iloc[idx]
        pipe_id = torch.tensor(self.indxs["pipeline_id"].iloc[idx])

        y = torch.tensor(self.indxs["y"].iloc[idx], dtype=torch.float32)
        gr_data = self.data_pipe.__getitem__(pipe_id)

        dset_data = Data()
        dset_data.x = torch.tensor(self.data_dset.loc[task_id].values, dtype=torch.float32)
        if dset_data.x.dim() < 2:
            dset_data.x = dset_data.x.view(1, -1)

        # w = torch.tensor(self.weights[task_id], dtype=torch.float32)
        return task_id, pipe_id, gr_data, dset_data, y


class PairDataset(SingleDataset):
    """Dataset for surrogate model. Used to train on ranking objective.
    Returns pair of pipelines for chosen dataset.
    """

    def __init__(self, indxs, data_pipe, data_dset):
        super().__init__(indxs, data_pipe, data_dset)

        self.indxs["ind"] = list(range(len(self.indxs)))

        self.task_pipe_dict = self.indxs.groupby("task_id")["ind"].apply(list).to_dict()
        self.dateset_id_list = list(self.task_pipe_dict.keys())

    def __len__(self):
        return len(self.dateset_id_list)

    def __getitem__(self, itask):
        """
        Args:
            idx: index of data.
        Returns:
            x_dset: vector of dataset meta-features.
            x_pipe1: Data object of pipeline 1.
            x_pipe2: Data object of pipeline 2.
            y: 1.0 if y1 > y2 else 0.0 if y1 < y2 else 0.5.
        """
        task_id = self.dateset_id_list[itask]
        comb_ids = self.task_pipe_dict[task_id]
        idx1, idx2 = sample(comb_ids, 2)

        _, _, gr_data1, _, y1 = super().__getitem__(idx1)
        _, _, gr_data2, dset_data2, y2 = super().__getitem__(idx2)
        return gr_data1, gr_data2, dset_data2, (1.0 if y1 > y2 else 0.0 if y1 < y2 else 0.5)
