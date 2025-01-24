import random
import itertools
import json

from dataclasses import dataclass
from functools import reduce

from abc import ABC, abstractmethod

@dataclass
class ItemType:
    code: str
    description: str

    def __str__(self):
        return "Item type (code " + self.code + ") - " + self.description
    
    def Description(self):
        return self.description


@dataclass
class Scenario:
    code: str
    description: str
    item_types: list[ItemType]
    available_quantities: list[int]
    
    def __post_init__(self):
        assert len(self.available_quantities) == len(self.item_types), "Quantities must match the number of items in the scenario"
        
    def codes(self):
        return [x.code for x in self.item_types]
    
    def simple_item_overview(self):
        return "Here is a list of [ITEM_CODE, AVAILABLE_QUANTITIES] for the scenario: " + json.dumps([[x.code, q] for x, q in zip(self.item_types, self.available_quantities)])

    def __len__(self):
        return len(self.item_types)

    def __str__(self):
        return (
            "Scenario "
            + self.code
            + "\n"
            + self.description
            + "\n\n"
            + "\n".join([str(item) + f" - x{Q} available" for item, Q in zip(self.item_types, self.available_quantities)])
        )
        
    def Description(self):
        return str(self)
    
    def to_json(self):
        return json.dumps({
            "code": self.code,
            "description": self.description,
            "item_types": [
                {"code": item.code, "description": item.description}
                for item in self.item_types
            ],
            "available_quantities": self.available_quantities
        })

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        item_types = [ItemType(**item) for item in data["item_types"]]
        return Scenario(
            code=data["code"],
            description=data["description"],
            item_types=item_types,
            available_quantities=data["available_quantities"]
        )

@dataclass
class Bundle:
    scenario: Scenario
    quantities: list[int]

    def __post_init__(self):
        assert len(self.quantities) == len(self.scenario.item_types), "Quantities must match the number of items in the scenario"
        if not all([q <= Q for q, Q in zip(self.quantities, self.scenario.available_quantities)]):
            print("Bundle quantity can not exceed scenario available quantity, coercing down")
            self.quantities = [min(q, q_) for q, q_ in zip(self.quantities, self.scenario.available_quantities)]
        assert all([q >= 0 for q, Q in zip(self.quantities, self.scenario.available_quantities)]), "Bundle quantiy can not be negative"
        
    def __str__(self):
        return ";".join([str(q) for q in self.quantities])
    
    def total_quantity(self) -> int:
        return sum(self.quantities)
    
    def get_item_type_quantity(self, item_type: ItemType) -> int:
        idx = self.scenario.codes().index(item_type.code)
        return self.quantities[idx]
    
    def set_item_type_quantity(self, item_type: ItemType, quantity: int):
        idx = self.scenario.codes().index(item_type.code)
        self.quantities[idx] = quantity
    
    def copy(self) -> 'Bundle':
        return Bundle(
            scenario=self.scenario,
            quantities=list(tuple(self.quantities))
        )

    def description(self) -> str:
        description = f"Items in bundle ({sum(self.quantities)} total)\n\n"
        has_item = False
        for item, quantity in zip(self.scenario.item_types, self.quantities):
            if quantity > 0:
                has_item = True
                description += f"Item {item.code}x{quantity} ([Item Code]x[Quantity])): {item.description}\n"
        if not has_item:
            description += " - No items in bundle.\n"
        return description
    
    def Description(self):
        return self.description()

    def to_code_description(self):
        description = f"Items in bundle ({sum(self.quantities)} total)"
        codes = []
        has_item = False
        for item, quantity in zip(self.scenario.item_types, self.quantities):
            if quantity > 0:
                has_item = True
                codes.append(f"{item.code}x{quantity}")
        if not has_item:
            description += " - No items in bundle."
        else:
            description += " - " + ", ".join(codes)
        return description
    
    def __eq__(self, other: 'Bundle') -> bool:
        return (self.scenario.code == other.scenario.code) and all([q1 == q2 for q1, q2 in zip(self.quantities, other.quantities)])

    def __contains__(self, other: 'Bundle') -> bool:
        return all(a >= b for a, b in zip(self.quantities, other.quantities))
    
    def __hash__(self) -> int:
        return hash((self.scenario.code, tuple(self.quantities)))
    
    def to_json(self):
        return json.dumps({
            "scenario": json.loads(self.scenario.to_json()),
            "quantities": self.quantities
        })

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        scenario = Scenario.from_json(json.dumps(data["scenario"]))
        return Bundle(scenario=scenario, quantities=data["quantities"])
    
    @staticmethod
    def from_types_quantities(scenario: Scenario, item_type_codes: list[str], item_quantities: list[int]):
        quantities = [0 for i in range(len(scenario))]
        
        for item_type_code, quantity in zip(
            item_type_codes, item_quantities
        ):
            if item_type_code in scenario.codes():
                idx = scenario.codes().index(item_type_code)
                quantities[idx] = quantity

        bundle = Bundle(scenario=scenario, quantities=quantities)
        
        return bundle

class Prices(ABC):
    
    @abstractmethod
    def __call__(self, bundle: Bundle):
        raise NotImplementedError
    
    @abstractmethod
    def Description(self):
        raise NotImplementedError
    
    
class DirectPrices(Prices):
    
    def __init__(self, bundle_price_dict: dict[Bundle, float]):
        self.bundle_price_dict = bundle_price_dict
        
    def __call__(self, bundle):
        possible_price_list = [0] + [price if ref_bundle in bundle else 0 for ref_bundle, price in self.bundle_price_dict.items()]
        return max(possible_price_list)
    
    def Description(self) -> str:
        """
        Generates a comprehensive description of the DirectPrices instance.

        Returns:
            str: A formatted string describing the direct pricing rules and the bundle-price listings.
        """
        if not self.bundle_price_dict:
            return (
                "Direct Prices Description:\n"
                "No bundle prices are specified. All bundles and individual items are free by default."
            )
        
        # Short description of how DirectPrices works
        short_description = (
            "DirectPrices assigns explicit prices to specific bundles. "
            "When evaluating a bundle's price, it checks all predefined bundles to find those "
            "contained within the given bundle. The price of the bundle is the highest price among "
            "these contained bundles. If no contained bundles are found, the price defaults to 0."
        )
        
        # Detailed listing of bundle-price pairs
        bundle_listings = "\n".join([
            f"  - Price: ${price:.2f}; Bundle: [{bundle.to_code_description()}]"
            for bundle, price in self.bundle_price_dict.items()
        ])
        
        detailed_description = (
            "Direct Prices Description:\n"
            f"{short_description}\n\n"
            "Defined Bundle Prices:\n"
            f"{bundle_listings}"
        )
        
        return detailed_description

    def to_json(self) -> str:
        """
        Serialize the DirectPrices instance to a JSON string.
        
        The bundle_price_dict is converted into a list of dictionaries, each containing
        the serialized bundle and its corresponding price.
        """
        serialized_data = {
            "bundle_price_list": [
                {
                    "bundle": json.loads(bundle.to_json()),  # Convert bundle to dict
                    "price": price
                }
                for bundle, price in self.bundle_price_dict.items()
            ]
        }
        return json.dumps(serialized_data, indent=4)
    
    @staticmethod
    def from_json(json_str: str) -> 'DirectPrices':
        """
        Deserialize a JSON string to a DirectPrices instance.
        
        Expects the JSON string to contain a list of bundle-price pairs.
        """
        data = json.loads(json_str)
        bundle_price_dict = {}
        
        for entry in data.get("bundle_price_list", []):
            bundle_data = entry["bundle"]
            bundle_json_str = json.dumps(bundle_data)
            bundle = Bundle.from_json(bundle_json_str)
            price = entry["price"]
            bundle_price_dict[bundle] = price
        
        return DirectPrices(bundle_price_dict)

def scenario_singleton_bundles(scenario: Scenario) -> list[Bundle]:
    return [Bundle(scenario, [1 if i == j else 0 for j in range(len(scenario.item_types))]) for i in range(len(scenario.item_types))]

def scenario_empty_bundle(scenario: Scenario) -> Bundle:
    return Bundle(scenario, [0 for _ in range(len(scenario.item_types))])

def scenario_all_bundles(scenario: Scenario):
    sorted_product = sorted(itertools.product([0, 1], repeat=len(scenario)), key=sum)
    return [Bundle(scenario, qs) for qs in list(sorted_product)[1:]]

def bundleAContainsB(bundleA, bundleB):
    return bundleB in bundleA

def scenario_bundle_sample(scenario: Scenario, k: int, seed: int = 42):
    
    max_k = reduce((lambda x, y: x * y), [q + 1 for q in scenario.available_quantities])
    
    assert k <= max_k, "Too many samples requested for given scenario, max is k = " + str(max_k)
    
    if seed is not None:
        random.seed(seed)

    bundles = []
    
    while len(bundles) < k:
        bundle_quantities = [random.randint(0, Q) for Q in scenario.available_quantities]
        bundle = Bundle(scenario, bundle_quantities)
        if all([bundle != bundle2 for bundle2 in bundles]):
            bundles.append(bundle)
            
    return bundles

TransportationScenario = Scenario(
    "TRANSPORTATION",
    "Three scooters and three bikes are up for auction",
    [
        ItemType(
            "ESCOOT1",
            """"Electric Scooter S2 Pro (2024): Powerful folding e-scooter for urban commuting. 350W brushless hub motor, top speed of 19 mph. Features include 8.5" solid tires, up to 25 miles range, and dual braking system. 36V/11.4Ah battery, aerospace-grade aluminum frame. Weighs 33 lbs, supports up to 260 lbs. Includes 3 LED lights, cruise control, and mobile app connectivity. Portable folding design for easy storage. UL 2272 certified for safety.""",
        ),
        ItemType(
            "ESCOOT2",
            """Electric Scooter Elettrica (2023): Sleek and stylish electric scooter. 4kW electric motor, 62 miles range in ECO mode. Features include color TFT display, LED lighting, and reverse gear. 12" wheels, metallic blue exterior, black eco-leather seat. Energy recovery system during deceleration. Two riding modes: ECO and Power. Bluetooth connectivity for smartphone integration. Silent operation for urban environments.""",
        ),
        ItemType(
            "VOLTRON",
            """Voltron SP03 Electric Scooter (2024): Versatile commuter e-scooter. 350W motor with 19 MPH top speed and 21 miles range. Features 8.5" maintenance-free solid tires with honeycomb design. Smart app control for riding modes, lighting, and cruise control. Portable folding design, lightweight for easy carrying. Supports up to 264 lbs. Dual braking system for safety. UL2272 certified with 12-month warranty on main parts.""",
        ),
        ItemType(
            "TROIK",
            """Troik Verve+ 2 (2023): Comfortable electric hybrid bike. Aluminum frame, Bosch Active Line motor, 400Wh integrated battery. Shimono Altus 9-speed drivetrain, hydraulic disc brakes. Features include suspension fork, upright geometry, and integrated lights. 700c wheels with puncture-resistant tires. Matte Nautical Navy color. Range: up to 65 miles. Weight: 22.5 kg (49.6 lbs). Sizes available: S, M, L, XL.""",
        ),
        ItemType(
            "TITAN",
            """Titan Escape 3 (2023): Cost-friendly fitness and commuter bike. ALUXX aluminum frame, Shimono Tourney 3x7-speed drivetrain, mechanical disc brakes. Features include upright geometry and 700x38c tires for stability. 700c aluminum wheels, Metallic Red color. Weight: 13.5 kg (29.8 lbs). Sizes available: XS, S, M, L, XL. Great value for daily rides.""",
        ),
        ItemType(
            "SCHWIN",
            """Schwin Suburban (2021): Comfortable and affordable city bike. Steel frame, Shimono Tourney 7-speed drivetrain, linear-pull brakes. Features include swept-back handlebars and wide comfort saddle. 26" wheels with 2.0" wide tires. Navy Blue color. Rear rack included. Weight: 15.9 kg (35 lbs). One size fits most (recommended for riders 5'4" to 6'2"). Cost-friendly option for leisurely rides.""",
        ),
    ],
    [
        1, 1, 1, 1, 1, 1
    ]
)

ElectronicsScenario = Scenario(
    "ELECTRONICS",
    "A local library is auctioning off donated electronics that are all like-new and in perfect working condition.",
    [
        ItemType("AIRPODS2", "Apple AirPods (2nd Generation) Wireless Ear Buds, Bluetooth Headphones with Lightning Charging Case Included, Over 24 Hours of Battery Life, Effortless Setup for iPhone."),
        ItemType("AIRPODSPROMAX", "Apple AirPods Max Wireless Over-Ear Headphones, Active Noise Cancelling, Transparency Mode, Personalized Spatial Audio, Dolby Atmos, Bluetooth Headphones for iPhone – Space Gray."),
        ItemType("IPAD9", "Apple iPad (9th Generation): with A13 Bionic chip, 10.2-inch Retina Display, 64GB, Wi-Fi, 12MP front/8MP Back Camera, Touch ID, All-Day Battery Life – Silver."),
        ItemType("IPAD12", "Apple iPad Air 11-inch (M2): Built for Apple Intelligence, Liquid Retina Display, 128GB, 12MP Front/Back Camera, Wi-Fi 6E, Touch ID, All-Day Battery Life — Purple."),
        ItemType("APPLEPENCIL2", "Apple Pencil (2nd Generation): Compatible with iPad only. Pixel-Perfect Precision and Industry-Leading Low Latency, Perfect for Note-Taking, Drawing, and Signing documents. Attaches, Charges, and Pairs magnetically."),
        ItemType("APPLEPENCILPRO", "Apple Pencil Pro: Advanced Tools, Pixel-Perfect Precision, Tilt and Pressure Sensitivity, and Industry-Leading Low Latency for Note-Taking, Drawing, and Art. Attaches, Charges, and Pairs Magnetically."),
    ],
    [
        1, 1, 1, 1, 1, 1
    ])

PreservesScenario = Scenario(
    "PRESERVES",
    "Variety of gourmet preserves available at a specialty food auction.",
    [
        ItemType("OSJ", "Organic Strawberry Jam: Sun-ripened organic strawberries bursting with flavor. Our jam is made from hand-picked berries grown in pesticide-free orchards. We use only organic cane sugar and a touch of lemon juice to enhance the natural sweetness. No artificial preservatives or colors. Perfect for spreading on toast or swirling into yogurt. 340g (12 oz) jar."),
        ItemType("WBP", "Wild Blueberry Preserves: Experience the intense flavor of wild Maine blueberries in every spoonful. Our preserves are packed with whole berries harvested from the rugged fields of New England. Cooked in small batches to preserve the fruit’s integrity. Contains wild blueberries, sugar, pectin, and lemon juice. Excellent on pancakes or as a cheesecake topping. 280g (10 oz) jar."),
        ItemType("ALC", "Apricot and Lavender Conserve: A sophisticated blend of succulent apricots and aromatic lavender from Provence. This artisanal conserve balances the fruit’s sweetness with delicate floral notes. Made with apricots, sugar, lavender flowers, and apple pectin. Pairs wonderfully with cheese or as a glaze for roasted meats. 225g (8 oz) jar."),
        ItemType("SFRS", "Sugar-Free Raspberry Spread: Indulge in the bright flavor of raspberries without the added sugar. Our spread is sweetened with natural stevia extract and contains 70% fruit. Made with raspberries, water, pectin, lemon juice, and stevia leaf extract. Only 10 calories per tablespoon. Ideal for those watching their sugar intake. 300g (10.5 oz) jar."),
        ItemType("SPC", "Spiced Plum Chutney: A savory-sweet condiment inspired by traditional Indian chutneys. Ripe plums are slow-cooked with vinegar, brown sugar, and a blend of warming spices including cinnamon, cloves, and ginger. Contains plums, brown sugar, apple cider vinegar, onions, raisins, and spices. Delicious with curries or as a glaze for grilled meats. 250g (8.8 oz) jar."),
        ItemType("TMPJ", "Tropical Mango and Passionfruit Jam: Bring the taste of the tropics to your breakfast table with our exotic jam. Juicy mangoes and tangy passionfruit create a vibrant, sunny spread. Made with mangoes, passionfruit pulp, sugar, and pectin. No artificial flavors or colors. Try it on scones or use as a cake filling for a tropical twist. 310g (11 oz) jar."),
    ],
    [
        1, 1, 1, 1, 1, 1
    ]
)

scenarios = [TransportationScenario, ElectronicsScenario, PreservesScenario]