import math
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
import statsmodels.api as sm
from typing import Mapping, Optional


def plot_metrics_grid(
    df: pd.DataFrame,
    metrics: list[str],
    *,
    nrows: int = 2,
    condition_col: str = "condition",
    x_col: str = "round_ix",
    show_points: bool = True,
    jitter_x: float = 0.08,
    point_size: float = 10,
    markersize: float = 20,
    point_alpha: float = 0.35,
    show_ci: bool = True,
    ci_alpha: float = 0.18,
    show_significance: bool = True,
    seed: int = 0,
    sharex: bool = True,
    sharey: bool = False,
    title: str | None = None,
    save_fp: str | None = None,
    dpi: int = 300,
    condition_color_map: Optional[Mapping[str, str]] = None,
    marker_map: Optional[Mapping[str, str]] = None,
    figsize: tuple[float, float] = (4.8, 3.8),
    legend_loc: str = "upper left",
    legend_alpha: float = 0.85,
    legend_pad_frac: float = 0.12,
    robust_se: bool = False,
    global_legend: bool = False,
    global_legend_loc: str = "upper center",
    global_legend_ncol: int | None = None,
    global_legend_framealpha: float = 0.95,
    global_legend_bbox_to_anchor: tuple[float, float] | None = None,
    global_legend_title: str | None = None,
    global_legend_fontsize: float = 9.0,
    global_legend_title_fontsize: float = 9.0,
    global_legend_top_pad: float = 0.10,
    global_legend_bottom_pad: float = 0.10,
    metrics_ymax_dict: Optional[Mapping[str, float]] = None,
):

    def stars(p: float) -> str:
        if p < 0.001:
            return "***"
        if p < 0.01:
            return "**"
        if p < 0.05:
            return "*"
        return "n.s."

    if nrows < 1:
        raise ValueError("nrows must be >= 1")
    if not metrics:
        raise ValueError("metrics must be a non-empty list of column names")
    if condition_col not in df.columns or x_col not in df.columns:
        raise ValueError(f"df must contain '{condition_col}' and '{x_col}' columns")

    missing = [m for m in metrics if m not in df.columns]
    if missing:
        raise ValueError(f"These metrics are not in df columns: {missing}")

    rng = np.random.default_rng(seed)

    data = df.copy()
    data = data.dropna(subset=[condition_col, x_col])
    data[x_col] = pd.to_numeric(data[x_col], errors="coerce")
    data = data.dropna(subset=[x_col])

    conds = list(pd.unique(data[condition_col]))

    # --- color mapping
    palette = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    if condition_color_map is None:
        color_map = {c: palette[i % len(palette)] for i, c in enumerate(conds)}
    else:
        color_map = dict(condition_color_map)
        for i, c in enumerate(conds):
            if c not in color_map:
                color_map[c] = palette[i % len(palette)]

    # --- marker mapping
    default_markers = ["o", "s", "X", "^", "D", "v", "P", "*"]

    if marker_map is None:
        marker_map_local = {
            c: default_markers[i % len(default_markers)] for i, c in enumerate(conds)
        }
    else:
        marker_map_local = dict(marker_map)
        for i, c in enumerate(conds):
            if c not in marker_map_local:
                marker_map_local[c] = default_markers[i % len(default_markers)]

    m = len(metrics)
    ncols = math.ceil(m / nrows)
    total_axes = nrows * ncols

    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(figsize[0] * ncols, figsize[1] * nrows),
        sharex=sharex,
        sharey=sharey,
    )

    axes = np.array(axes).reshape(-1)

    z = 1.959963984540054
    global_handles = {}

    for idx, metric in enumerate(metrics):
        ax = axes[idx]

        dmetric = data.copy()
        dmetric[metric] = pd.to_numeric(dmetric[metric], errors="coerce")

        valid_rounds = (
            dmetric.groupby(x_col)[metric]
            .apply(lambda s: s.notna().any())
        )
        valid_rounds = valid_rounds[valid_rounds].index

        dmetric = dmetric[dmetric[x_col].isin(valid_rounds)].copy()
        dmetric_nonan = dmetric.dropna(subset=[metric]).copy()

        g = (
            dmetric_nonan.groupby([condition_col, x_col])[metric]
            .agg(mean="mean", sd="std", n="count")
            .reset_index()
        )

        g["sd"] = g["sd"].fillna(0.0)
        g["se"] = g["sd"] / np.sqrt(np.maximum(g["n"], 1))
        g["ci_lo"] = g["mean"] - z * g["se"]
        g["ci_hi"] = g["mean"] + z * g["se"]

        for cond in conds:
            gg = g[g[condition_col] == cond].copy()
            if gg.empty:
                continue

            color = color_map[cond]
            marker = marker_map_local[cond]

            gg = gg.sort_values(x_col)

            if show_points:
                raw = dmetric_nonan[dmetric_nonan[condition_col] == cond]
                if not raw.empty:
                    xj = raw[x_col].to_numpy(dtype=float) + rng.uniform(
                        -jitter_x, jitter_x, size=len(raw)
                    )

                    ax.scatter(
                        xj,
                        raw[metric].to_numpy(dtype=float),
                        s=point_size,
                        markersize=markersize,
                        alpha=point_alpha,
                        color=color,
                        marker=marker,
                        edgecolors="none",
                        zorder=1,
                    )

            leg_label = str(cond)

            if show_significance:
                raw = dmetric_nonan[dmetric_nonan[condition_col] == cond].copy()

                if len(raw) >= 2 and raw[x_col].nunique() >= 2:
                    X = sm.add_constant(raw[x_col].astype(float))
                    y = raw[metric].astype(float)

                    fit = (
                        sm.OLS(y, X).fit(cov_type="HC3")
                        if robust_se
                        else sm.OLS(y, X).fit()
                    )

                    slope = float(fit.params[x_col])
                    pval = float(fit.pvalues[x_col])

                    leg_label = f"{cond} (c={slope:.2f}, {stars(pval)})"

            (line,) = ax.plot(
                gg[x_col].to_numpy(dtype=float),
                gg["mean"].to_numpy(dtype=float),
                marker=marker,
                markersize=markersize,
                linewidth=2.0,
                color=color,
                label=leg_label,
                zorder=3,
            )

            if global_legend and (leg_label not in global_handles):
                global_handles[leg_label] = line

            if show_ci:
                ax.fill_between(
                    gg[x_col].to_numpy(dtype=float),
                    gg["ci_lo"].to_numpy(dtype=float),
                    gg["ci_hi"].to_numpy(dtype=float),
                    color=color,
                    alpha=ci_alpha,
                    linewidth=0,
                    zorder=2,
                )

        ax.set_title(metric, fontsize=18)
        ax.set_xlabel("Round", fontsize=18)
        ax.grid(True, alpha=0.25)
        ax.tick_params(axis="x", labelsize=18)
        ax.tick_params(axis="y", labelsize=18)

        if (idx % ncols) == 0:
            ax.set_ylabel("Value", fontsize=18)

        if metrics_ymax_dict is not None and metric in metrics_ymax_dict:
            ymax_target = metrics_ymax_dict.get(metric, None)

            if ymax_target is not None:
                ymin, _ymax = ax.get_ylim()
                ax.set_ylim(ymin, float(ymax_target))

        ymin, ymax = ax.get_ylim()
        span = max(ymax - ymin, 1e-9)
        ax.set_ylim(ymin, ymax + legend_pad_frac * span)

        if not global_legend:
            ax.legend(
                loc=legend_loc,
                fontsize=10.25,
                handlelength=1,
                frameon=True,
                framealpha=legend_alpha,
            )

        if "lexical" not in metric:
            unique_rounds = np.sort(pd.unique(data[x_col].dropna()))

            if (
                len(unique_rounds) <= 12
                and np.all(np.isclose(unique_rounds, np.round(unique_rounds)))
            ):
                for ax2 in axes[:m]:
                    ax2.set_xticks(unique_rounds)

        else:
            ax.set_xticks(valid_rounds)

    for j in range(m, total_axes):
        axes[j].axis("off")

    if title is not None:
        fig.suptitle(title, y=1.02)

    if global_legend:

        if global_legend_ncol is None:
            global_legend_ncol = min(len(global_handles), max(1, len(global_handles)))

        if global_legend_bbox_to_anchor is None:
            if "upper" in global_legend_loc:
                global_legend_bbox_to_anchor = (0.5, 1.01)
            elif "lower" in global_legend_loc:
                global_legend_bbox_to_anchor = (0.5, -0.01)
            else:
                global_legend_bbox_to_anchor = (1.01, 0.5)

        fig.legend(
            handles=list(global_handles.values()),
            labels=list(global_handles.keys()),
            loc=global_legend_loc,
            bbox_to_anchor=global_legend_bbox_to_anchor,
            ncol=global_legend_ncol,
            frameon=True,
            framealpha=global_legend_framealpha,
            fontsize=global_legend_fontsize,
        )

        if "upper" in global_legend_loc:
            fig.tight_layout(rect=(0, 0, 1, 1 - global_legend_top_pad))

        elif "lower" in global_legend_loc:
            fig.tight_layout(rect=(0, global_legend_bottom_pad, 1, 1))

        else:
            fig.tight_layout()

    else:
        fig.tight_layout()

    if save_fp:
        save_fp = Path(save_fp)
        save_fp.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_fp, dpi=dpi, bbox_inches="tight")

    return fig, axes.reshape(nrows, ncols)