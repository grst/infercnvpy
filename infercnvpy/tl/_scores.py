"""Scores to summarize and assess copy number variation"""
from typing import Any, Mapping, Optional
import numpy as np
from numba import njit
from .._util import _choose_mtx_rep
import scipy.sparse as sp
from anndata import AnnData
import warnings


def cnv_score(
    adata: AnnData,
    groupby: str = "cnv_leiden",
    *,
    use_rep: str = "cnv",
    key_added: str = "cnv_score",
    inplace: bool = True,
    obs_key=None,
) -> Optional[Mapping[Any, np.number]]:
    """Assign each cnv cluster a CNV score.

    Clusters with a high score are likely affected by copy number abberations.
    Based on this score, cells can be divided into tumor/normal cells.

    Ths score is currently simply defined as the mean of result of
    :func:`infercnvpy.tl.infercnv` for each cluster.

    Parameters
    ----------
    adata
        annotated data matrix
    groupby
        Key under which the clustering is stored in adata.obs. Usually
        the result of :func:`infercnvpy.tl.leiden`, but could also be
        other grouping information, e.g. sample or patient information.
    use_rep
        Key under which the result of :func:`infercnvpy.tl.infercnv` is stored
        in adata.
    key_added
        Key under which the score will be stored in `adata.obs`.
    inplace
        If True, store the result in adata, otherwise return it.
    obs_key
        Deprecated alias for `groupby`.

    Returns
    -------
    Depending on the value of `inplace`, either returns `None` or
    dictionary with the score per group.
    """
    if obs_key is not None:
        warnings.warn(
            "The obs_key argument has been renamed to `groupby` for consistency with "
            "other functions and will be removed in the future. ",
            category=FutureWarning,
        )
        groupby = obs_key

    if groupby not in adata.obs.columns and groupby == "cnv_leiden":
        raise ValueError(
            "`cnv_leiden` not found in `adata.obs`. Did you run `tl.leiden`?"
        )
    cluster_score = {
        cluster: np.mean(
            np.abs(adata.obsm[f"X_{use_rep}"][adata.obs[groupby] == cluster, :])
        )
        for cluster in adata.obs[groupby].unique()
    }

    if inplace:
        score_array = np.array([cluster_score[c] for c in adata.obs[groupby]])
        adata.obs[key_added] = score_array
    else:
        return cluster_score


def ithgex(
    adata: AnnData,
    groupby: str,
    *,
    use_raw: Optional[bool] = None,
    layer: Optional[str] = None,
    inplace: bool = True,
    key_added: str = "ithgex",
) -> Optional[Mapping[str, float]]:
    """Compute the ITHGEX diversity score based on gene expression cite:`Wu2021`.

    A high score indicates a high diversity of gene expression profiles of cells
    within a group.

    The score is defined as follows:

        Intratumoral heterogeneity scores based on CNAs and gene expressions
        The calculations of intratumoral heterogeneity scores were inspired by a
        previous study and modified as follows. First, to calculate ITHCNA, we used
        the relative expression value matrix generated by inferCNV and calculated the
        pairwise cell–cell distances using Pearson's correlation coefficients for each
        patient. ITHCNA was defined as interquartile range (IQR) of the distribution for
        all malignant cell pairs' Pearson's correlation coefficients. **Similarly, we also
        used gene expression profiles of cancer cells of each patient to construct the
        distribution of the intratumoral distances. ITHGEX was assigned as the IQR of the
        distribution.**

        (from :cite:`Wu2021`)


    Parameters
    ----------
    adata
        annotated data matrix
    groupby
        calculate diversity for each group defined in this category.
    use_raw
        Use gene expression from `adata.raw`. Defaut: Use `.raw` if available,
        `.X` otherwise.
    layer
        Use gene expression from `adata.layers[layer]`
    inplace
        If True, store the result in adata, otherwise return it.
    key_added
        Key under which the score will be stored in `adata.obs`.

    Returns
    -------
    Depending of the value of `inplace` either returns a dictionary
    with one value per group or `None`.
    """
    groups = adata.obs[groupby].unique()
    ithgex = {}
    for group in groups:
        tmp_adata = adata[adata.obs[groupby] == group, :]
        X = _choose_mtx_rep(tmp_adata, use_raw, layer)
        if sp.issparse(X):
            X = X.todense()
        if X.shape[0] <= 1:
            continue
        pcorr = np.corrcoef(X, rowvar=True)
        assert pcorr.shape == (
            tmp_adata.shape[0],
            tmp_adata.shape[0],
        ), f"pcorr is a cell x cell matrix {tmp_adata.shape[0]} {pcorr.shape}"
        q75, q25 = np.percentile(pcorr, [75, 25])
        ithgex[group] = q75 - q25

    if inplace:
        ithgex_obs = np.empty(adata.shape[0])
        for group in groups:
            ithgex_obs[adata.obs[groupby] == group] = ithgex[group]
        adata.obs[key_added] = ithgex_obs
    else:
        return ithgex


def ithcna(
    adata: AnnData,
    groupby: str,
    *,
    use_rep: str = "X_cnv",
    key_added: str = "ithgex",
    inplace: bool = True,
) -> Optional[Mapping[str, float]]:
    """Compute the ITHCNA diversity score based on copy number variation :cite:`Wu2021`.

    A high score indicates a high diversity of CNV profiles of cells
    within a group.

    The score is defined as follows:

        Intratumoral heterogeneity scores based on CNAs and gene expressions
        The calculations of intratumoral heterogeneity scores were inspired by a
        previous study and modified as follows. First, to calculate ITHCNA, we used
        the relative expression value matrix generated by inferCNV and calculated the
        pairwise cell–cell distances using Pearson's correlation coefficients for each
        patient. ITHCNA was defined as interquartile range (IQR) of the distribution for
        all malignant cell pairs' Pearson's correlation coefficients.

        (from :cite:`Wu2021`)

    Parameters
    ----------
    adata
        annotated data matrix
    groupby
        calculate diversity for each group defined in this category.
    use_rep
        Key under which the result of :func:`infercnvpy.tl.infercnv` is stored
        in adata.
    key_added
        Key under which the score will be stored in `adata.obs`.
    inplace
        If True, store the result in adata, otherwise return it.

    Returns
    -------
    Depending of the value of `inplace` either returns a dictionary
    with one value per group or `None`.
    """
    groups = adata.obs[groupby].unique()
    ithcna = {}
    for group in groups:
        tmp_adata = adata[adata.obs[groupby] == group, :]
        X = tmp_adata.obsm[use_rep]
        if sp.issparse(X):
            X = X.todense()
        if X.shape[0] <= 1:
            continue
        pcorr = np.corrcoef(X, rowvar=True)
        assert pcorr.shape == (
            tmp_adata.shape[0],
            tmp_adata.shape[0],
        ), "pcorr is a cell x cell matrix"
        q75, q25 = np.percentile(pcorr, [75, 25])
        ithcna[group] = q75 - q25

    if inplace:
        ithcna_obs = np.empty(adata.shape[0])
        for group in groups:
            ithcna_obs[adata.obs[groupby] == group] = ithcna[group]
        adata.obs[key_added] = ithcna_obs
    else:
        return ithcna
