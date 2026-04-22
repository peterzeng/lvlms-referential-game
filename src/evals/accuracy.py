import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
import statsmodels.api as sm


def get_accuracy(df: pd.DataFrame, 
                 num_of_rounds=4, 
                 precision=1, 
                 include_cols=None):
    df = df.copy()
    col_mapper = {
        f'round{round_num}_matcher_sequence_accuracy': f'R{round_num}'
        for round_num in range(1, num_of_rounds + 1)
    }
    accuracy_cols = [f'round{round_num}_matcher_sequence_accuracy' 
                     for round_num in range(1, num_of_rounds + 1)]
    
    out_cols = accuracy_cols
    if include_cols:
        assert isinstance(include_cols, list), "include_cols should be a list"
        assert all(col in df.columns for col in include_cols), \
            "Some include_cols are not in the dataframe"
        
        out_cols = include_cols + accuracy_cols

    df = df[out_cols]
    df[accuracy_cols] = df[accuracy_cols].round(precision)
    df.rename(columns=col_mapper, inplace=True)
    df.dropna(inplace=True)

    if df.empty:
        return None
    return df
    

def get_accuracy_from_transcript_df(
    df: pd.DataFrame,
    num_of_rounds=4,
    precision=1,
) -> pd.DataFrame:
    out = []

    for pair_id in df['pair_id'].unique():
        df_pair = df[df['pair_id'] == pair_id]
        if df_pair.empty or len(df_pair) < num_of_rounds:
            continue
        
        row = {"condition": df_pair.iloc[0]['condition'], "pair_id": pair_id}
        
        for round_num in range(1, num_of_rounds + 1):
            df_round = df_pair[df_pair['round_ix'] == round_num]
            accuracy = df_round.iloc[0]['accuracy']
            row[f'R{round_num}'] = round(accuracy, precision)
        out.append(row)

    return pd.DataFrame(out)


def plot_ols_trend(
    df: pd.DataFrame,
    *,
    condition_col: str = "condition",
    pair_id_col: str = "pair_id",
    round_prefix: str = "R",
    metric_col="Accuracy",
    show_points: bool = True,
    show_trajectories: bool = True,
    annotate_slope: bool = False,          # NEW
    slope_fmt: str = "{:.2f}",              # NEW
    jitter: float = 0.08,
    point_size: float = 16,
    point_alpha: float = 0.55,
    traj_alpha: float = 0.12,
    traj_lw: float = 1.0,
    fit_lw: float = 2.5,
    band_alpha: float = 0.20,
    seed: int = 0,
    title: str | None = None,
    save_fp: str | None = None,
    dpi: int = 300,
):
    """
    Plot OLS trends of Accuracy over rounds per condition with optional
    jittered points, faint within-pair trajectories, and slope annotation.

    Expected df structure (wide):
      - condition_col (e.g., 'Condition')
      - pair_id_col (e.g., 'pair_id')
      - round columns: R1, R2, R3, R4, ...
    """

    def p_to_stars(p: float) -> str:
        if p < 0.001: return "***"
        if p < 0.01:  return "**"
        if p < 0.05:  return "*"
        return "n.s."

    # --- identify round columns ---
    round_cols = [c for c in df.columns if c.startswith(round_prefix)]
    if not round_cols:
        raise ValueError(f"No round columns found with prefix='{round_prefix}'.")

    def _round_num(col: str) -> int:
        return int(col[len(round_prefix):])

    round_cols = sorted(round_cols, key=_round_num)
    round_nums = [_round_num(c) for c in round_cols]

    # --- long format ---
    raw_long = df.melt(
        id_vars=[condition_col, pair_id_col],
        value_vars=round_cols,
        var_name="Round",
        value_name=metric_col,
    )
    raw_long["RoundNum"] = raw_long["Round"].str[len(round_prefix):].astype(int)
    raw_long[metric_col] = pd.to_numeric(raw_long[metric_col], errors="coerce")

    # --- plotting setup ---
    rng = np.random.default_rng(seed)
    fig, ax = plt.subplots(figsize=(9, 5))

    palette = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    conds = sorted(raw_long[condition_col].dropna().unique())
    color_map = {c: palette[i % len(palette)] for i, c in enumerate(conds)}

    x_grid = np.linspace(min(round_nums), max(round_nums), 200)

    for cond in conds:
        color = color_map[cond]
        dfc = raw_long[
            (raw_long[condition_col] == cond) & raw_long[metric_col].notna()
        ].copy()

        if dfc.empty:
            continue

        # ---- faint trajectories ----
        if show_trajectories:
            for _, gt in dfc.groupby(pair_id_col):
                gt = gt.sort_values("RoundNum")
                if len(gt) >= 2:
                    ax.plot(
                        gt["RoundNum"],
                        gt[metric_col],
                        color=color,
                        alpha=traj_alpha,
                        linewidth=traj_lw,
                        zorder=1,
                    )

        # ---- jittered points ----
        if show_points:
            xj = dfc["RoundNum"].to_numpy() + rng.uniform(-jitter, jitter, size=len(dfc))
            ax.scatter(
                xj,
                dfc[metric_col],
                s=point_size,
                alpha=point_alpha,
                color=color,
                edgecolors="none",
                zorder=2,
            )

        # ---- OLS fit ----
        X = sm.add_constant(dfc["RoundNum"].astype(float))
        y = dfc[metric_col].astype(float)
        model = sm.OLS(y, X).fit()

        slope = float(model.params["RoundNum"])
        pval = float(model.pvalues["RoundNum"])
        stars = p_to_stars(pval)

        Xg = sm.add_constant(pd.Series(x_grid, name="RoundNum"))
        pred = model.get_prediction(Xg).summary_frame(alpha=0.05)

        ax.plot(
            x_grid,
            pred["mean"],
            color=color,
            linewidth=fit_lw,
            label=f"{cond} (n={len(dfc)//4}, {stars})",
            zorder=4,
        )

        ax.fill_between(
            x_grid,
            pred["mean_ci_lower"],
            pred["mean_ci_upper"],
            color=color,
            alpha=band_alpha,
            linewidth=0,
            zorder=3,
        )

        # ---- slope annotation (optional) ----
        if annotate_slope:
            x_anno = x_grid[-1]
            y_anno = pred["mean"].iloc[-1]
            ax.text(
                x_anno + 0.05,
                y_anno,
                f"→ c = {slope_fmt.format(slope)}",
                color=color,
                fontsize=10,
                va="center",
                ha="left",
            )

    ax.set_xticks(round_nums)
    ax.set_xlabel("Round")

    if metric_col.lower() == "accuracy":
        ax.set_ylabel("Accuracy (%)")
        ax.set_ylim(0, 110)
        ax.set_yticks(np.arange(0, 110, 10))
        ax.set_title(
            title
            if title is not None
            else "OLS trend of Accuracy over rounds (mean fit ± 95% CI)"
        )
    else:
        ax.set_ylabel(metric_col)
        ax.set_title(
            title
            if title is not None
            else f"OLS trend of {metric_col} over rounds (mean fit ± 95% CI)"
        )
    ax.grid(True, alpha=0.3)
    ax.legend(title="Condition (# samples, slope sig.)", loc="center left", bbox_to_anchor=(1.15, 0.5))
    fig.tight_layout()

    if save_fp:
        save_path = Path(save_fp)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_fp, dpi=dpi, bbox_inches="tight")

    return fig, ax
