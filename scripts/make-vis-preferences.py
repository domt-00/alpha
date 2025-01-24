import os
import pandas as pd
from datetime import datetime
import concurrent.futures
from alpha.auctions.ceca import CECA_XOR
from alpha.auctions.ceca_purellm_g import CECA_PureLLM_G_Proxy_Factory
from alpha.person import Seed
from alpha.persons.full_person import FullPerson
from alpha.persons.standard_person import StandardValuePipeline
from alpha.scenario import scenarios, scenario_all_bundles, Bundle
from alpha.util import setup_logging
from tqdm import tqdm
import logging
import argparse
from dotenv import load_dotenv
from alpha.seed_generation.v5 import SeedGenerationPipeline_v5
import numpy as np
from plotnine import *
from tqdm import tqdm
from itertools import product

# Logger setup
logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.ERROR)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

def make_bundles(scenario):
    bundles = []
    
    quantities = [0 for i in range(len(scenario))]
    for i in range(len(scenario)):
        quantities[i] = 1
        bundles.append(Bundle(scenario, [q for q in quantities]))
    for i in range(len(scenario)):
        quantities[len(scenario)-1-i] = 0
        bundles.append(Bundle(scenario, [q for q in quantities]))
        
    return bundles

# Define function to process each scenario and its bundles

def process_scenario(scenario):
    rows = []
    
    print("Creating seed")
    seed = SeedGenerationPipeline_v5().generate(scenario, 1)[0]
    print("Created seed")
    
    repeats = 10
    bundles = [(i, b) for i, b in enumerate(make_bundles(scenario))]  # Convert to list to determine length
    total_iterations = repeats * len(bundles)
    
    print(f"Processing {total_iterations} total iterations (Repeats: {repeats}, Bundles: {len(bundles)})")
    
    # Create a single tqdm progress bar
    with tqdm(total=total_iterations, desc="Processing", unit="iter") as pbar:
        for repeat, idx_bundle in product(range(repeats), bundles):
            bundle_idx, bundle = idx_bundle
            model = "gpt-4o-mini"
            value = StandardValuePipeline(model)(
                scenario=scenario, 
                seed=seed, 
                bundle=bundle, 
                logger=rootLogger, 
                use_cache=False
            )
            rows.append({
                "scenario": scenario.code,
                "seed": seed.code,
                "model": model,
                "bundle": ";".join([str(x) for x in bundle.quantities]),
                "bundle_idx": bundle_idx,
                "value": value
            })
            pbar.update(1)
    
    return rows

# Main function to parallelize the task
def main():
    
    parser = argparse.ArgumentParser(
        description="Visualize a snapshot of preferences for a person per scenario."
    )
    parser.add_argument("--env_path", type=str, default=".env",
                        help="Path to the .env file to load environment variables from.")
    parser.add_argument(
        "--outprefix", 
        default="tmp", 
        help="Path to output figure file (default: 'tmp.png')."
    )
    
    args = parser.parse_args()
    
    load_dotenv(dotenv_path=args.env_path)
    print(f"[INFO] Loaded environment variables from {args.env_path}")
    
    all_rows = []
    
    # Use ThreadPoolExecutor for parallelization
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = [executor.submit(process_scenario, scenario) for scenario in scenarios]
        
        # Use tqdm to track progress
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(scenarios)):
            try:
                all_rows.extend(future.result())
            except Exception as e:
                rootLogger.error(f"Error processing scenario: {e}")
    
    # Write all rows to CSV after processing all scenarios
    df = pd.DataFrame(all_rows)
    
    df.to_csv("tmp_variability.csv", index=False)
    
    # Add a color identifier for the specific bundles to color
    df['color'] = np.where(df['bundle_idx'] == 5, 'green', 
                           np.where(df['bundle_idx'] == df['bundle_idx'].max(), 'coral', 'black'))
    df["bundle_idx"] = 1 + df["bundle_idx"]

    # Convert the color column to a category type to ensure it works properly for coloring
    df['color'] = pd.Categorical(df['color'], categories=['black', 'green', 'coral'])

    # Create the plot
    plot = (
        ggplot(df, aes(x='factor(bundle_idx)', y='value', color='factor(color)'))
        + geom_boxplot()
        + facet_wrap('~scenario', ncol=1, scales='free_y')
        + scale_color_manual(values=['black', 'green', 'coral'])
        + labs(x='Bundle', y='Value ($)')
        + theme_minimal()
        + theme(axis_text_x=element_text(rotation=90, hjust=1), legend_position='none')
    )
    
    fig = plot.draw()  # Convert the ggplot (plotnine) object to a Matplotlib figure

    # Save the figure via Matplotlib
    fig.savefig(f"{args.outprefix}_fig5.png", dpi=300, bbox_inches='tight')
    
if __name__ == "__main__":
    main()
