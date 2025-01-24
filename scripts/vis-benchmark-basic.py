#!/usr/bin/env python3

import argparse
import os
import glob
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from plotnine import (
    ggplot, 
    aes, 
    geom_line, 
    theme_bw,
    labs, 
    scale_y_continuous,
    scale_x_continuous,
    theme,
    element_text,
    scale_linetype_manual
)

from alpha.persons.full_person import FullPerson
from alpha.scenario import scenarios
from alpha.auctions.ceca import allocate

def get_scenario_by_code(code):
    """Return the scenario object (from alpha.scenario) matching the given code."""
    for s in scenarios:
        if s.code == code:
            return s
    return None

def discover_scenarios_and_setups(benchmark):
    """
    Discover which scenarios (directories) and setup subdirectories exist under data/<benchmark>.

    Returns:
        A list of tuples: [(scenario_code, setup_subdir), ... ]
    """
    base_dir = os.path.join("data", benchmark)
    if not os.path.isdir(base_dir):
        print(f"[ERROR] Benchmark directory does not exist: {base_dir}")
        return []

    scenario_dirs = [
        d for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d))
    ]

    tasks = []
    for scenario_code in scenario_dirs:
        scenario_path = os.path.join(base_dir, scenario_code)
        setup_subdirs = [
            s for s in os.listdir(scenario_path)
            if os.path.isdir(os.path.join(scenario_path, s))
        ]
        # For each discovered setup subdirectory, add a task
        for setup_index in setup_subdirs:
            tasks.append((scenario_code, setup_index))

    return tasks

def calculate_normalization_factors(benchmark):
    
    normalization_factors = {scenario.code: 0 for scenario in scenarios}
    setups = discover_scenarios_and_setups(benchmark)
    
    for scenario_code, setup_index in setups:
        directory = os.path.join("data", benchmark, scenario_code, str(setup_index))
        
        scenario_obj = get_scenario_by_code(scenario_code)
        
        fullperson_files = [
            f for f in os.listdir(directory)
            if f.startswith("FullPerson") and f.endswith(".json")
        ]
        
        persons = []
        
        for fp_file in fullperson_files:
            full_fp_path = os.path.join(directory, fp_file)

            with open(full_fp_path, "r") as f:
                p = FullPerson.from_json(f.read())
                p.demand_mode = "RAND"
                persons.append(p)
        
        allocation = allocate(scenario_obj, [p.XOR_Valuation for p in persons])
        values = []
        for p, agent_allocation in zip(persons, allocation):
            bundle, payment = agent_allocation
            values.append(p.Message(
                    "value",
                    {
                        "bundle": bundle
                    }
                ))
            
        normalization_factors[scenario_code] += sum(values)
        
    return normalization_factors

def standardize_dataset(df, max_interactions=120):
    # Create a standardized DataFrame with avg_human_interactions = 0..(max_interactions-1)
    new_df = pd.DataFrame({"avg_human_interactions": range(max_interactions)})
    
    # Ensure the original DataFrame is sorted
    df_sorted = df.sort_values("avg_human_interactions")
    
    new_df["avg_human_interactions"] = new_df["avg_human_interactions"].astype(float)
    # Perform an asof merge to find the closest greater or equal avg_human_interactions
    standardized_df = pd.merge_asof(
        new_df,
        df_sorted,
        on="avg_human_interactions",
        direction="backward",
        allow_exact_matches=True
    ).ffill()
    
    return standardized_df

def process_dataset(dataset_path, max_interactions=120):
    """
    Reads a CSV file, truncates rows above `max_interactions`, then ensures
    each scenario's data is 'standardized' so all share the same X-axis length.
    """
    df_original = pd.read_csv(dataset_path)
    df = df_original[df_original["avg_human_interactions"] <= max_interactions]
    
    process_df = pd.DataFrame()
    for scenario in df["scenario"].unique():
        for it in df["setup_index"].unique():
            sub_df = df[(df["scenario"] == scenario) & (df["setup_index"] == it)]
            sub_df = standardize_dataset(sub_df, max_interactions=max_interactions)
            process_df = pd.concat([process_df, sub_df])
    
    # Assume 'Proxy' column is the same for the entire dataset
    if "Proxy" in df_original.columns and not df_original["Proxy"].empty:
        process_df["Proxy"] = df_original["Proxy"].iloc[0]
    else:
        process_df["Proxy"] = "Unknown Proxy"
    
    return process_df

def main():
    parser = argparse.ArgumentParser(
        description="Process CSV files from data/{benchmark}-logs/ and plot normalized auction values."
    )
    parser.add_argument("benchmark", help="Name of the benchmark (e.g., 'ELECTRONICS', 'PRESERVES').")
    parser.add_argument(
        "--outfile", 
        default="tmp.png", 
        help="Path to output figure file (default: 'tmp.png')."
    )
    args = parser.parse_args()

    # Construct the path to the directory containing the CSV files
    logs_dir = os.path.join("data", f"{args.benchmark}-logs")

    # Gather all CSV files in that directory
    csv_files = glob.glob(os.path.join(logs_dir, "*.csv"))
    if not csv_files:
        print(f"No CSV files found in '{logs_dir}'")
        return

    # Collect data from all CSV files into a single DataFrame
    big_df_list = []
    for csv_file in csv_files:
        processed = process_dataset(csv_file)
        big_df_list.append(processed)

    big_df = pd.concat(big_df_list, ignore_index=True)

    # Aggregate total_auction_value by (Proxy, scenario, avg_human_interactions)
    normalized_df = (
        big_df.groupby(["Proxy", "scenario", "avg_human_interactions"], as_index=False)
        .agg({"total_auction_value": "sum"})
    )

    # Example normalization factors by scenario (update as appropriate)
    normalization_factors = calculate_normalization_factors(args.benchmark)
    
    {
        "ELECTRONICS":     6427.2,
        "PRESERVES":       219.0,
        "TRANSPORTATION":  21907.0
    }

    # Compute normalized auction values
    def normalize(row):
        factor = normalization_factors.get(row["scenario"], 1)
        return row["total_auction_value"] / factor

    normalized_df["normalized_auction_value"] = normalized_df.apply(normalize, axis=1)

    # Average across all scenarios that appear for each (Proxy, avg_human_interactions)
    normalized_df = (
        normalized_df.groupby(["Proxy", "avg_human_interactions"], as_index=False)
        .agg({"normalized_auction_value": "mean"})
    )
    
    # Define specific linetypes for each Proxy (optional)
    linetype_mapping = {
        "Proxy-XOR": "dashdot",
        "Proxy-VD1": "dashed",
        "Proxy-VD2": "dotted",
        "Proxy-NVD": "solid",
        "Proxy-H": "solid"
    }
    for proxy in linetype_mapping.keys():
        if not proxy in normalized_df["Proxy"].to_list():
            print(f"Please be sure to run {proxy} against benchmark before visualizing")
            
        
    # Convert Proxy to string just in case
    normalized_df["Proxy"] = normalized_df["Proxy"].astype(str)
    
    normalized_df.to_csv("tmp-view.csv")

    # Create the plot (using plotnine)
    plot = (
        ggplot(normalized_df, aes(
            x='avg_human_interactions', 
            y='normalized_auction_value', 
            color='Proxy',
            linetype='Proxy'
        ))
        + geom_line(size=1)
        + theme_bw()
        + labs(
            x='Number of Interactions',
            y='Average Efficiency (%)',
            color='Proxy',
            linetype='Proxy'
        )
        + scale_y_continuous(limits=(0, 1))
        + scale_x_continuous(limits=(0, 25))
        + scale_linetype_manual(values=linetype_mapping)
        + theme(
            legend_position=(0.7, 0.1),
            legend_justification=(0, 0),
            text=element_text(size=12),
            legend_title=element_text(size=12),
            legend_text=element_text(size=10),
            figure_size=(6.4, 6.4)
        )
    )

    # Option 1: Use plotnine's built-in save
    # plot.save(args.outfile, dpi=300)
    # Option 2: Convert to Matplotlib, then use savefig
    fig = plot.draw()  # Convert the ggplot (plotnine) object to a Matplotlib figure

    # Save the figure via Matplotlib
    fig.savefig(args.outfile, dpi=300, bbox_inches='tight')
    print(f"Figure saved to {args.outfile}")

if __name__ == "__main__":
    main()
