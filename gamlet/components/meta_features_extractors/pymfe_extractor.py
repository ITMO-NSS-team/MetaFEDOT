from __future__ import annotations

import logging
import warnings
from functools import partial
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from pymfe.mfe import MFE
from tqdm import tqdm

from gamlet.data_preparation.dataset import DatasetBase, TabularData
from gamlet.components.meta_features_extractors import MetaFeaturesExtractor, DatasetMetaFeatures
from gamlet.components.meta_features_extractors import DatasetMetaFeatures

logger = logging.getLogger(__file__)


class PymfeExtractor(MetaFeaturesExtractor):
    default_params = dict(groups='default')

    def __init__(self, **extractor_params):
        self.extractor_params = extractor_params if extractor_params is not None else self.default_params
        self._extractor = MFE(**extractor_params)

    def extract(self, data_sequence: Sequence[Union[DatasetBase, TabularData]],
                fill_input_nans: bool = False, fit_kwargs: Optional[Dict[str, Any]] = None,
                extract_kwargs: Optional[Dict[str, Any]] = None) -> DatasetMetaFeatures:
        accumulated_meta_features = []

        for i, dataset_data in enumerate(tqdm(data_sequence, desc='Extracting meta features of the datasets')):
            if isinstance(dataset_data, DatasetBase):
                dataset_data = dataset_data.get_data()
            try:
                meta_features = self._extract_single(dataset_data, fill_input_nans, fit_kwargs, extract_kwargs)
                accumulated_meta_features.append(meta_features)
            except Exception:
                logger.exception(f'Dataset {dataset_data.dataset}: error while meta-features extractin.')

        output = DatasetMetaFeatures(pd.concat(accumulated_meta_features), is_summarized=self.summarize_features,
                                     features=self.features)
        return output

    def _extract_single(self, dataset_data: TabularData, fill_input_nans: bool = False,
                        fit_kwargs: Optional[Dict[str, Any]] = None,
                        extract_kwargs: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        fit_kwargs = fit_kwargs or {'rescale': 'robust'}
        extract_kwargs = extract_kwargs or {}

        logger.debug(
            f'Extracting meta-features of dataset {dataset_data.dataset}.'
        )
        x, y = dataset_data.x, dataset_data.y
        cat_cols_indicator = dataset_data.categorical_indicator
        if fill_input_nans:
            x = self.fill_nans(x, cat_cols_indicator)
        if cat_cols_indicator is not None:
            cat_cols = [i for i, val in enumerate(cat_cols_indicator) if val]
        else:
            cat_cols = 'auto'
        fit_extractor = self._extractor.fit
        fit_extractor = partial(fit_extractor, x, y, cat_cols=cat_cols, **fit_kwargs)
        if 'transform_cat' in fit_kwargs:
            mfe = fit_extractor()
        else:
            try:
                mfe = fit_extractor(transform_cat='gray')
            except RecursionError:
                warnings.warn('PyMFE did not manage to do fit. Trying "one-hot" categorical encoder...')
                mfe = fit_extractor(transform_cat='one-hot')
        meta_features_extracted = mfe.extract(out_type=pd.DataFrame, **extract_kwargs)
        meta_features_extracted.index = [dataset_data.id]
        return meta_features_extracted

    @property
    def summarize_features(self) -> bool:
        return self.extractor_params.get('summary', True) is not None

    @property
    def features(self) -> Tuple[str, ...]:
        return self._extractor.features

    @staticmethod
    def fill_nans(x: np.ndarray, cat_cols_indicator: Sequence[bool]) -> np.ndarray:
        x_new = pd.DataFrame(x)
        for col in x_new.columns:
            is_all_nan = x_new[col].isna().values.all()
            is_categorical = cat_cols_indicator[col]
            if is_all_nan:
                fill_value = 0
            elif is_categorical:
                fill_value = x_new[col].mode(dropna=True).values[0]
            else:
                fill_value = x_new[col].median(skipna=True)
            x_new[col].fillna(fill_value, inplace=True)
        return x_new.to_numpy()
