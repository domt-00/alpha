import os
import pandas as pd
from datetime import datetime
import concurrent.futures
from alpha.auctions.ceca import CECA_XOR
from alpha.auctions.ceca_purellm_g import CECA_PureLLM_G_Proxy_Factory
from alpha.person import Seed
from alpha.persons.full_person import FullPerson
from alpha.persons.standard_person import StandardValuePipeline, StandardValuePipeline2
from alpha.scenario import scenarios, scenario_all_bundles
from alpha.util import setup_logging
from tqdm import tqdm
import logging
from alpha.seed_generation.v5 import SeedGenerationPipeline_v5
from plotnine import *
import argparse
from dotenv import load_dotenv
import random
from itertools import product


# Logger setup
logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.ERROR)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

# Define function to process each scenario and its bundles
def process_scenario(scenario):
    rows = []
    
    print("Creating seed")
    seed = SeedGenerationPipeline_v5().generate(scenario, 1)[0]
    print("Created seed")
    
    all_bundles = scenario_all_bundles(scenario)
    all_models = ["openai/gpt-4o-mini", "google/gemini-flash-1.5", "meta-llama/llama-3.1-70b-instruct", "anthropic/claude-3.5-haiku"]
    total_iterations = len(all_bundles) * len(all_models)
    
    with tqdm(total=total_iterations, desc="Processing", unit="iter") as pbar:
        for bundle, model in product(all_bundles, all_models):
            rows.append({
                "scenario": scenario.code,
                "seed": seed.code,
                "model": model,
                "bundle": ";".join([str(x) for x in bundle.quantities]),
                "value": StandardValuePipeline2(model)(scenario=scenario, seed=seed, bundle=bundle, logger=rootLogger)
            })
            
            pbar.update(1)
    
    # Return the rows instead of writing them directly to file, to aggregate later
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
    df.to_csv("tmp-gptv3-all.csv", index=False)

    # Convert 'bundle' to string if it isn't already
    # (Useful to avoid pivot issues if bundle is a numeric column)
    df['bundle'] = df['bundle'].astype(str)

    # 2. Filter for the models of interest
    models_of_interest = [
        "openai/gpt-4o-mini",
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.1-70b-instruct",
        "anthropic/claude-3.5-haiku"
    ]
    filtered_df = df[df["model"].isin(models_of_interest)]
    
    mm = {
        "openai/gpt-4o-mini" : "GPT-4o-mini",
        "google/gemini-flash-1.5": "Gemini-flash-1.5",
        "meta-llama/llama-3.1-70b-instruct": "Llama-3.1-70b-instruct",
        "anthropic/claude-3.5-haiku": "Claude-3.5-haiku"
    }
    
    
    filtered_df["model"] = [mm[x] for x in filtered_df['model']]


    # 3. Pivot to wide format so each model is a column
    wide_df = filtered_df.pivot_table(
        index=["bundle", "scenario"],
        columns="model",
        values="value"
    ).reset_index()

    # 4. Melt so openai/gpt-4o-mini is in one column (x-axis) 
    #    and all the other LLM values become the y-axis
    other_llms = [ "Gemini-flash-1.5", "Llama-3.1-70b-instruct", "Claude-3.5-haiku"]
    melted_df = wide_df.melt(
        id_vars=["bundle", "scenario", "GPT-4o-mini"],
        value_vars=other_llms,
        var_name="other_model",
        value_name="other_value"
    )
    

    # 5. Build the plot
    p = (
        ggplot(melted_df, aes(
            x="GPT-4o-mini",
            y="other_value",
            color="other_model",
            shape="other_model"
        ))
        + geom_point(size=3, alpha=0.7)
        + geom_abline(slope=1, intercept=0, color="red", linetype="dashed", size=0.5)
        + facet_wrap("~scenario", scales="free")
        + labs(
            x="GPT-4o Mini Value ($)",
            y="Other LLM Value ($)"
        )
        + coord_fixed(ratio=1)  # Ensures the same scaling for x and y
        + theme_minimal()
        + theme(
            axis_text_x=element_text(rotation=90, hjust=1),
            axis_title=element_text(size=12),
            strip_text=element_text(size=12),
            figure_size=(6, 6),  # Adjust as needed
            legend_position='bottom',       # Move legend to the bottom
            legend_direction='horizontal',  # Arrange legend items horizontally
            legend_title=element_blank(),  # Optional: Adjust legend title size
            legend_text=element_text(size=10)
        )
    )
    
    fig = p.draw()  # Convert the ggplot (plotnine) object to a Matplotlib figure

    # Save the figure via Matplotlib
    fig.savefig(f"{args.outprefix}_fig6.png", dpi=300, bbox_inches='tight')

if __name__ == "__main__":
    main()
