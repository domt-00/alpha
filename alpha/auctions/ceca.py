"""
Runs competitive equilibrium CA auction given bidders
"""

from ortools.linear_solver import pywraplp
from tqdm import tqdm
import concurrent
import random
import string

from alpha.proxy import Proxy, ProxyFactory
from alpha.xor import XORBid
from alpha.auction import Auction, Allocation
from alpha.agent import Agent, MessageDecorator
from alpha.person import Person
from alpha.scenario import Scenario, DirectPrices, Bundle, scenario_empty_bundle

def process_agent(data):
    i, agent, prices, bundle = data
    try:
        r, valuation = agent.Message("ceca_xor_step", {
            "prices": prices,
            "bundle": bundle
        })
        return (i, r, valuation, agent)
    except Exception as e:
        return (i, True, None, agent)  # Treat errors as agreement


class CECA_XOR_Elicitation_Proxy(Proxy):
    
    def __init__(self, person: Person):
        self.person = person
        self.manifest_valuation = XORBid()
    
    def RealPerson(self) -> Person:
        return self.person
    
    def Support(self):
        return ["ceca_xor_step"]
    
    @MessageDecorator(cache = True)
    def Message(self, message_type: str, params: any, logger = None):
        if message_type == "ceca_xor_step":
            prices = params["prices"]
            bundle = params["bundle"]
            
             
            demanded_bundle: Bundle = self.person.Message(
                "demand",
                {
                    "prices": prices,
                    "bundle": bundle
                }
            )
            
            if bundle == demanded_bundle:
                return 1, self.manifest_valuation
            else:
                demanded_bundle_value = self.person.Message(
                    "value",
                    {
                        "bundle": demanded_bundle
                    }
                )
                
                bundle_ = demanded_bundle.copy()
                
                for item_type in demanded_bundle.scenario.item_types:
                    if bundle_.get_item_type_quantity(item_type) > 1:
                        bundle__ = bundle_.copy()
                        
                        bundle__.set_item_type_quantity(item_type, 0)
                        
                        if demanded_bundle_value >= self.person.Message(
                            "value",
                            {
                                "bundle": bundle__
                            }):
                            logger.info("Removing item ", item_type)
                            bundle_ == bundle__
                        else:
                            logger.info("Keeping item ", item_type)
                        
                
                self.manifest_valuation.add_atomic_bid(
                    bundle_,
                    demanded_bundle_value
                )
                
                logger.info("Mainfest valuation return " + str(self.manifest_valuation))
                
                return 0, self.manifest_valuation
    

class CECA_XOR_Elicitation_Proxy_Factory(ProxyFactory):
    
    def __call__(self, person: Person) -> Proxy:
        return CECA_XOR_Elicitation_Proxy(person)

    
class CECA_XOR(Auction):

    def __init__(self, max_iterations: int = None):
        self.log_rows = []
        self.max_iterations = max_iterations

    def __call__(
        self,
        scenario: Scenario = None,
        agents: list[Agent] = None,
        persons: list[Person] = None
    ) -> Allocation:
        assert scenario is not None, "scenario must not be None"
        
        for agent in agents:
            assert "ceca_xor_step" in agent.Support(), "Agent must support ceca_xor_step"
        
        run_code = "".join([random.choice(string.ascii_uppercase) for i in range(3)])
            
        iteration = 0
        allocation = None
        last_valuations = [XORBid() for agent in agents]
        
        with tqdm(desc='CECA Iterations', unit='it', unit_scale=False, dynamic_ncols=True, 
              bar_format='{desc}: {n_fmt} it. | {rate_fmt} it/s') as pbar:
            while True:
                iteration += 1
                
                # Get allocation at last valuation
                allocation = allocate(scenario, last_valuations)
                
                pbar.set_description(f"ICA Iterations: {iteration}; Payment: {sum([x[1] for x in allocation])}")
                pbar.update(1)
                
                reached_CE = True
                num_yes = 0
                
                # Prepare data for parallel execution, checking if each agent is satisfied
                agent_data = []
                for i, agent, agent_allocation, last_valuation in zip(
                    range(len(agents)),
                    agents,
                    allocation,
                    last_valuations
                ):
                    bundle, payment = agent_allocation
                    value = last_valuation.evaluate(bundle)
                    pii = value - payment
                    prices = DirectPrices({
                        bundle: max(0, value - pii)
                        for bundle, value in last_valuation.atomic_bids
                    })
                    agent_data.append((i, agent, prices, bundle))
                
                # Execute in parallel
                with concurrent.futures.ProcessPoolExecutor() as executor:
                    results = list(executor.map(process_agent, agent_data))
                
                # Process results
                for i, r, valuation, agent in results:
                    agents[i] = agent
                    if not r:
                        reached_CE = False
                        last_valuations[i] = valuation.copy()
                    else:
                        num_yes += 1
                
                allocation = allocate(scenario, last_valuations)
                
                # need to add log row
                values = []
                if persons is None:
                    for r in agent_data:
                        value = r[1].RealPerson().Message(
                            "value",
                            {
                                "bundle": r[3]
                            }
                        )
                        values.append(value)
                else:
                    for person, agent_allocation in zip(persons, allocation):
                        bundle, payment = agent_allocation
                        value = person.Message(
                            "value",
                            {
                                "bundle": bundle
                            }
                        )
                        values.append(value)
                
                self.log_rows.append({
                    "auction_run": run_code,
                    "scenario": scenario.code,
                    "human_interactions": [agent.NumberOfHumanInteractions() for agent in agents],
                    "avg_human_interactions": sum([agent.NumberOfHumanInteractions() for agent in agents])/len(agents),
                    "auction_values": values,
                    "total_auction_value": sum(values),
                    "quantities": [
                        bundle.quantities for bundle, payment in allocation
                    ]
                })
                
                if reached_CE:
                    break
                if self.max_iterations is not None and iteration >= self.max_iterations:
                    print(f"Max ICA iterations ({self.max_iterations}) reached — stopping early.")
                    break
                
        print("="*50)
        print("="*50)
        print("="*50)
        print("Auction concluded")
        
        return allocation



def allocate(scenario: Scenario, bids: list[XORBid]) -> Allocation:
    
    # Step 1: Optimize for maximum revenue
    solver = pywraplp.Solver.CreateSolver('SCIP')
    
    if not solver:
        return None
    
    # Create variables
    x = {}
    for i, bid in enumerate(bids):
        for j, (bundle, value) in enumerate(bid.atomic_bids):
            x[i, j] = solver.IntVar(0, 1, f'x_{i}_{j}')
    
    # Objective function
    objective = solver.Objective()
    for i, bid in enumerate(bids):
        for j, (bundle, value) in enumerate(bid.atomic_bids):
            objective.SetCoefficient(x[i, j], value)
    objective.SetMaximization()
    
    # Constraints
    # 1. Each bidder wins at most one bundle (XOR constraint)
    for i in range(len(bids)):
        solver.Add(solver.Sum([x[i, j] for j in range(len(bids[i].atomic_bids))]) <= 1)
    
    # 2. Each item is allocated at most once
    for k in range(len(scenario)):
        solver.Add(solver.Sum([
            bundle.get_item_type_quantity(scenario.item_types[k]) * x[i, j]
            for i, bid in enumerate(bids)
            for j, (bundle, value) in enumerate(bid.atomic_bids)
        ]) <= 1)
    
    # Solve
    status = solver.Solve()
    
    if status == pywraplp.Solver.OPTIMAL:
        max_revenue = objective.Value()
        
        solver = pywraplp.Solver.CreateSolver('SCIP')
        
        # Recreate variables
        x = {}
        for i, bid in enumerate(bids):
            for j, (bundle, value) in enumerate(bid.atomic_bids):
                x[i, j] = solver.IntVar(0, 1, f'x_{i}_{j}')
        
        # Add all previous constraints
        for i in range(len(bids)):
            solver.Add(solver.Sum([x[i, j] for j in range(len(bids[i].atomic_bids))]) <= 1)
        
        for k in range(len(scenario)):
            solver.Add(solver.Sum([
                bundle.get_item_type_quantity(scenario.item_types[k]) * x[i, j]
                for i, bid in enumerate(bids)
                for j, (bundle, value) in enumerate(bid.atomic_bids)
            ]) <= 1)
        
        # Add constraint to maintain maximum revenue
        solver.Add(solver.Sum([
            value * x[i, j]
            for i, bid in enumerate(bids)
            for j, (bundle, value) in enumerate(bid.atomic_bids)
        ]) == max_revenue)
        
        # Step 3: Optimize for number of bidders with allocated bundles
        objective = solver.Objective()
        for i, bid in enumerate(bids):
            for j, (bundle, value) in enumerate(bid.atomic_bids):
                objective.SetCoefficient(x[i, j], 1)
        objective.SetMaximization()
        
        # Solve
        status = solver.Solve()
        
        if status == pywraplp.Solver.OPTIMAL:
            allocation = [
                (scenario_empty_bundle(scenario), 0)
                for j in range(len(bids))
            ]
            for i, bid in enumerate(bids):
                for j, (bundle, value) in enumerate(bid.atomic_bids):
                    if x[i, j].solution_value() > 0.5:
                        allocation[i] = (bundle, value)
                        
            return allocation
    else:
        
        return [ ... ]
    