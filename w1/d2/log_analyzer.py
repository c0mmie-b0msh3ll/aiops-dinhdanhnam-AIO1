from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_bgl_line(line: str) -> dict:
    line = line.lstrip("\ufeff")
    parts = line.rstrip("\n").split(maxsplit=9)
    if len(parts) < 10:
        return {
            "timestamp": pd.NaT,
            "label": "unknown",
            "content": line.strip(),
            "dataset": "generic",
        }

    label, unix_ts, _date, _node_a, time_text, _node_b, _src, _component, _level, content = parts
    timestamp = pd.to_datetime(time_text, format="%Y-%m-%d-%H.%M.%S.%f", errors="coerce")
    if pd.isna(timestamp):
        timestamp = pd.to_datetime(float(unix_ts), unit="s", errors="coerce")

    return {
        "timestamp": timestamp,
        "label": label,
        "content": content,
        "dataset": "BGL",
    }


def parse_hdfs_line(line: str) -> dict:
    line = line.lstrip("\ufeff")
    pattern = re.compile(
        r"^(?P<date>\d{6})\s+(?P<time>\d{6})\s+(?P<pid>\d+)\s+"
        r"(?P<level>\S+)\s+(?P<component>[^:]+):\s+(?P<content>.*)$"
    )
    match = pattern.match(line.rstrip("\n"))
    if not match:
        return {
            "timestamp": pd.NaT,
            "label": "-",
            "content": line.strip(),
            "dataset": "generic",
        }

    timestamp = pd.to_datetime(
        "20" + match.group("date") + match.group("time"),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    return {
        "timestamp": timestamp,
        "label": "-",
        "content": match.group("content"),
        "dataset": "HDFS",
    }


def parse_docker_line(line: str) -> dict:
    line = line.lstrip("\ufeff")
    parts = line.rstrip("\n").split(maxsplit=1)
    timestamp = pd.to_datetime(parts[0], errors="coerce", utc=False)
    content = parts[1] if len(parts) > 1 else ""
    return {
        "timestamp": timestamp,
        "label": "-",
        "content": content.strip(),
        "dataset": "Docker",
    }


def parse_line(line: str) -> dict:
    line = line.lstrip("\ufeff")
    if re.match(r"^\d{4}-\d{2}-\d{2}T", line):
        return parse_docker_line(line)
    if re.match(r"^[A-Z-]+\s+\d{10}\s+\d{4}\.\d{2}\.\d{2}\s+", line):
        return parse_bgl_line(line)
    if re.match(r"^\d{6}\s+\d{6}\s+\d+\s+", line):
        return parse_hdfs_line(line)
    return {
        "timestamp": pd.NaT,
        "label": "-",
        "content": line.strip(),
        "dataset": "generic",
    }


def build_miner(sim_th: float = 0.5) -> TemplateMiner:
    config = TemplateMinerConfig()
    config.drain_sim_th = sim_th
    config.profiling_enabled = False
    return TemplateMiner(config=config)


def parse_logs(logfile: Path, sim_th: float = 0.5) -> tuple[pd.DataFrame, TemplateMiner]:
    lines = logfile.read_text(encoding="utf-8", errors="ignore").splitlines()
    miner = build_miner(sim_th=sim_th)
    rows = []
    for idx, line in enumerate(lines, start=1):
        parsed = parse_line(line)
        result = miner.add_log_message(parsed["content"])
        rows.append(
            {
                "line_id": idx,
                "timestamp": parsed["timestamp"],
                "label": parsed["label"],
                "is_anomaly_label": parsed["label"] != "-",
                "content": parsed["content"],
                "template_id": result["cluster_id"],
                "template": result["template_mined"],
                "dataset": parsed["dataset"],
            }
        )
    return pd.DataFrame(rows), miner


def template_spikes(df: pd.DataFrame, window: str = "1h", z_threshold: float = 3.0) -> pd.DataFrame:
    usable = df.dropna(subset=["timestamp"]).copy()
    if usable.empty:
        return pd.DataFrame(columns=["template_id", "window", "count", "mean", "std", "z_score"])

    usable["window"] = usable["timestamp"].dt.floor(window)
    counts = (
        usable.groupby(["template_id", "template", "window"])
        .size()
        .rename("count")
        .reset_index()
    )
    stats = counts.groupby("template_id")["count"].agg(["mean", "std"]).reset_index()
    counts = counts.merge(stats, on="template_id", how="left")
    counts["std"] = counts["std"].fillna(0)
    counts["z_score"] = (counts["count"] - counts["mean"]) / counts["std"].replace(0, 1e-9)
    return counts[counts["z_score"] >= z_threshold].sort_values("z_score", ascending=False)


def new_templates_last_hour(df: pd.DataFrame) -> pd.DataFrame:
    usable = df.dropna(subset=["timestamp"]).copy()
    if usable.empty:
        return pd.DataFrame(columns=df.columns)
    cutoff = usable["timestamp"].max() - pd.Timedelta(hours=1)
    first_seen = usable.groupby("template_id")["timestamp"].min()
    new_ids = first_seen[first_seen >= cutoff].index
    return usable[usable["template_id"].isin(new_ids)].drop_duplicates("template_id")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mini log analyzer using Drain3")
    parser.add_argument("logfile", type=Path, help="Path to a log file")
    parser.add_argument("--sim-th", type=float, default=0.5, help="Drain similarity threshold")
    args = parser.parse_args()

    df, _miner = parse_logs(args.logfile, sim_th=args.sim_th)
    total = len(df)
    template_counts = df.groupby(["template_id", "template"]).size().reset_index(name="count")
    template_counts["percent"] = template_counts["count"] / total * 100
    top5 = template_counts.sort_values("count", ascending=False).head(5)
    spikes = template_spikes(df, window="1h", z_threshold=3.0).head(10)
    new_templates = new_templates_last_hour(df)

    print(f"Log file: {args.logfile}")
    print(f"Total lines: {total}")
    print(f"Unique templates: {df['template_id'].nunique()}")
    print(f"Detected dataset format: {df['dataset'].mode().iat[0] if not df.empty else 'unknown'}")
    print()
    print("Top-5 templates:")
    for _, row in top5.iterrows():
        print(f"- T{int(row.template_id)} | {int(row['count'])} lines | {row.percent:.2f}% | {row.template}")

    print()
    print("Template spikes in the last-hour style check (z >= 3.0):")
    if spikes.empty:
        print("- No strong template-count spikes found.")
    else:
        for _, row in spikes.iterrows():
            print(
                f"- T{int(row.template_id)} | window={row.window} | "
                f"count={int(row['count'])} | z={row.z_score:.2f} | {row.template}"
            )

    print()
    print("New templates first seen in the final hour:")
    if new_templates.empty:
        print("- No new templates in the final hour.")
    else:
        for _, row in new_templates.head(10).iterrows():
            print(f"- T{int(row.template_id)} | first_seen={row.timestamp} | {row.template}")


if __name__ == "__main__":
    main()
