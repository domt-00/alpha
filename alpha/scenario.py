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

ElectronicsScenarioSpecs = Scenario(
    "ELECTRONICS-SPECS",
    "A local library is auctioning off donated electronics that are all like-new and in perfect working condition. Item descriptions are based on official Apple Support technical specification pages.",
    [
        ItemType("AIRPODS2", "Apple AirPods (2nd Generation): True wireless in-ear earbuds. H1 chip; Bluetooth; Lightning Charging Case (24+ hrs total battery, 5 hrs per charge). Double-tap gesture control. No active noise cancellation. Works with any Bluetooth device; seamless pairing with Apple devices (iOS 14.3+). Year introduced: 2019."),
        ItemType("AIRPODSPROMAX", "Apple AirPods Max: Premium over-ear wireless headphones. H1 chip per ear cup. Active Noise Cancellation (ANC), Transparency mode, Personalised Spatial Audio. Digital Crown volume/playback control. Up to 20 hrs battery (ANC on). USB-C charging. Works with any Bluetooth device. Year introduced: 2020."),
        ItemType("IPAD9", "Apple iPad (9th Generation): 10.2-inch Retina display (264 ppi), A13 Bionic chip, 64GB. Lightning connector. Touch ID. 8MP rear / 12MP front camera. Wi-Fi. All-day battery. STYLUS COMPATIBILITY: Supports Apple Pencil (1st generation) ONLY. NOT compatible with Apple Pencil (2nd generation) or Apple Pencil Pro. Year introduced: 2021."),
        ItemType("IPAD12", "Apple iPad Air 11-inch (M2): 10.86-inch Liquid Retina display (264 ppi), M2 chip, 128GB. USB-C connector. Touch ID (top button). 12MP front and rear cameras. Wi-Fi 6E. All-day battery. STYLUS COMPATIBILITY: Supports Apple Pencil Pro and Apple Pencil (USB-C) ONLY. NOT compatible with Apple Pencil (1st or 2nd generation). Year introduced: 2024."),
        ItemType("APPLEPENCIL2", "Apple Pencil (2nd Generation): Pixel-perfect, low-latency stylus. Magnetically attaches, charges, and pairs. Double-tap to switch tools. COMPATIBLE IPADS: iPad Pro 12.9-inch (3rd–6th gen), iPad Pro 11-inch (1st–4th gen), iPad Air (4th gen), iPad Air (5th gen), iPad mini (6th gen). NOT compatible with iPad (9th generation) or iPad Air 11-inch (M2). Year introduced: 2018."),
        ItemType("APPLEPENCILPRO", "Apple Pencil Pro: Advanced stylus with squeeze (tool palette), barrel roll, haptic feedback, Find My. Pixel-perfect precision, tilt/pressure sensitivity. Magnetically attaches, charges, pairs. COMPATIBLE IPADS: iPad Air 11-inch (M2/M3/M4), iPad Air 13-inch (M2/M3/M4), iPad Pro 11-inch (M4/M5), iPad Pro 13-inch (M4/M5), iPad mini (A17 Pro). NOT compatible with iPad (9th generation). Requires iPadOS 17.5+. Year introduced: 2024."),
    ],
    [
        1, 1, 1, 1, 1, 1
    ])

ElectronicsScenarioReviews = Scenario(
    "ELECTRONICS-REVIEWS",
    "A local library is auctioning off donated electronics that are all like-new and in perfect working condition. Item descriptions combine official Apple Support technical specifications with Amazon UK buyer review highlights.",
    [
        ItemType("AIRPODS2", "Apple AirPods (2nd Generation): True wireless in-ear earbuds. H1 chip; Bluetooth; Lightning Charging Case (24+ hrs total battery, 5 hrs per charge). Double-tap gesture control. No active noise cancellation. Works with any Bluetooth device. Year introduced: 2019. Amazon UK buyer ratings: 4.1/5. Buyers report: 'great quality, use them every day'; 'good value, connects quickly'; note that these are standard earbuds without ANC."),
        ItemType("AIRPODSPROMAX", "Apple AirPods Max: Premium over-ear wireless headphones. H1 chip per ear cup. Active Noise Cancellation (ANC), Transparency mode, Personalised Spatial Audio. Digital Crown controls. Up to 20 hrs battery (ANC on). USB-C charging. Year introduced: 2020. Amazon UK buyer ratings: 4.5/5 (1,523 ratings). Buyers report: 'superb noise cancellation — on low volume no other sound can break through'; 'fantastic headphones, quality finish'; 'comfortable, great for studying in busy places'; 'USB-C charging is convenient'; ideal for focus and commuting."),
        ItemType("IPAD9", "Apple iPad (9th Generation): 10.2-inch Retina display (264 ppi), A13 Bionic chip, 64GB. Lightning connector. Touch ID. 8MP rear / 12MP front camera. Wi-Fi. All-day battery. STYLUS COMPATIBILITY: Supports Apple Pencil (1st generation) ONLY. NOT compatible with Apple Pencil (2nd generation) or Apple Pencil Pro. Year introduced: 2021. Amazon UK buyer ratings: 4.5/5 (4,521 ratings). Buyers report: 'nice and light and clear'; 'fast, smooth performance'; 'excellent display for reading and streaming'; 'all-day battery life'; 'good value entry-level tablet'."),
        ItemType("IPAD12", "Apple iPad Air 11-inch (M2): 10.86-inch Liquid Retina display (264 ppi), M2 chip, 128GB. USB-C connector. Touch ID (top button). 12MP front and rear cameras. Wi-Fi 6E. All-day battery. STYLUS COMPATIBILITY: Supports Apple Pencil Pro and Apple Pencil (USB-C) ONLY. NOT compatible with Apple Pencil (1st or 2nd generation). Year introduced: 2024. Amazon UK buyer ratings: 4.7/5 (1,556 ratings). Buyers report: 'fantastic screen — vivid, bright, high definition'; 'seamless multitasking'; 'excellent for notes and annotation'; 'premium look and feel'; 'amazing alternative to the iPad Pro'."),
        ItemType("APPLEPENCIL2", "Apple Pencil (2nd Generation): Pixel-perfect, low-latency stylus. Magnetically attaches, charges, and pairs. Double-tap to switch tools. COMPATIBLE IPADS: iPad Pro 12.9-inch (3rd–6th gen), iPad Pro 11-inch (1st–4th gen), iPad Air (4th & 5th gen), iPad mini (6th gen). NOT compatible with iPad (9th generation) or iPad Air 11-inch (M2). Year introduced: 2018. Amazon UK buyer ratings: 4.1/5. Buyers report: 'connected right away, charges well, great pencil'; 'completely changes how you use iPad'. IMPORTANT: Verify your iPad model is on the compatibility list before purchasing — pairing failures reported on incompatible models."),
        ItemType("APPLEPENCILPRO", "Apple Pencil Pro: Advanced stylus with squeeze (tool palette), barrel roll, haptic feedback, Find My. Pixel-perfect precision, tilt/pressure sensitivity. Magnetically attaches, charges, pairs. COMPATIBLE IPADS: iPad Air 11-inch (M2/M3/M4), iPad Air 13-inch (M2/M3/M4), iPad Pro 11-inch (M4/M5), iPad Pro 13-inch (M4/M5), iPad mini (A17 Pro). NOT compatible with iPad (9th generation). Requires iPadOS 17.5+. Year introduced: 2024. Amazon UK buyer ratings: 4.6/5 (5,628 ratings). Buyers report: 'works so well and is so easy to use'; 'fast charging, lasts ages'; 'great addition to any iPad — intuitive for note-taking'; 'I use it with my Air M2 2024 and it works brilliantly'; 'completely changes how you use iPad'."),
    ],
    [
        1, 1, 1, 1, 1, 1
    ])

ElectronicsMiniBasic = Scenario(
    "ELECTRONICS-MINI",
    "A local library is auctioning off donated electronics that are all like-new and in perfect working condition.",
    [
        ItemType("IPAD9", "Apple iPad (9th Generation): with A13 Bionic chip, 10.2-inch Retina Display, 64GB, Wi-Fi, 12MP front/8MP Back Camera, Touch ID, All-Day Battery Life – Silver."),
        ItemType("IPAD12", "Apple iPad Air 11-inch (M2): Built for Apple Intelligence, Liquid Retina Display, 128GB, 12MP Front/Back Camera, Wi-Fi 6E, Touch ID, All-Day Battery Life — Purple."),
        ItemType("APPLEPENCILPRO", "Apple Pencil Pro: Advanced Tools, Pixel-Perfect Precision, Tilt and Pressure Sensitivity, and Industry-Leading Low Latency for Note-Taking, Drawing, and Art. Attaches, Charges, and Pairs Magnetically."),
    ],
    [1, 1, 1])

ElectronicsMiniSpecs = Scenario(
    "ELECTRONICS-MINI-SPECS",
    "A local library is auctioning off donated electronics that are all like-new and in perfect working condition. Item descriptions are based on official Apple Support technical specification pages.",
    [
        ItemType("IPAD9", "Apple iPad (9th Generation): 10.2-inch Retina display (264 ppi), A13 Bionic chip, 64GB. Lightning connector. Touch ID. 8MP rear / 12MP front camera. Wi-Fi 5, Bluetooth 4.2. All-day battery (10 hrs). STYLUS COMPATIBILITY: Supports Apple Pencil (1st generation) ONLY. NOT compatible with Apple Pencil Pro or Apple Pencil (2nd generation). Year introduced: 2021."),
        ItemType("IPAD12", "Apple iPad Air 11-inch (M2): 10.86-inch Liquid Retina display (264 ppi), M2 chip, 8GB RAM, 128GB. USB-C connector. Touch ID (top button). 12MP front and rear cameras. Wi-Fi 6E, Bluetooth 5.3. All-day battery. Apple Intelligence capable. STYLUS COMPATIBILITY: Supports Apple Pencil Pro and Apple Pencil (USB-C) ONLY. NOT compatible with Apple Pencil (1st or 2nd generation). Year introduced: 2024."),
        ItemType("APPLEPENCILPRO", "Apple Pencil Pro: Advanced stylus with squeeze (tool palette), barrel roll (gyroscope), haptic feedback, Find My. Pixel-perfect precision, tilt/pressure sensitivity. Magnetically attaches, charges, pairs. Requires iPadOS 17.5+. COMPATIBLE IPADS: iPad Air 11-inch (M2/M3/M4), iPad Air 13-inch (M2/M3/M4), iPad Pro 11-inch (M4/M5), iPad Pro 13-inch (M4/M5), iPad mini (A17 Pro). NOT compatible with iPad (9th generation). Year introduced: 2024."),
    ],
    [1, 1, 1])

ElectronicsMiniPDF = Scenario(
    "ELECTRONICS-MINI-PDF",
    "A local library is auctioning off donated electronics that are all like-new and in perfect working condition. Item descriptions are drawn from official Apple Support technical specification pages and verified Amazon UK customer reviews.",
    [
        ItemType("IPAD9", """Apple iPad (9th Generation) — Year introduced: 2021.
DISPLAY: 10.2-inch LED backlit IPS Retina Multi-Touch. 2160×1620 px at 264 ppi. True Tone. 500 nits. Oleophobic coating.
CHIP: A13 Bionic with Neural Engine.
STORAGE: 64 GB. CONNECTOR: Lightning. Headphone jack. Smart Connector.
BIOMETRICS: Touch ID (home button). CAMERAS: 8MP rear (ƒ/2.4, 5× zoom, panorama, HDR). 12MP front Ultra Wide (ƒ/2.4, Centre Stage).
WIRELESS: Wi-Fi 5 (802.11ac, up to 866 Mb/s). Bluetooth 4.2.
BATTERY: 32.4 Wh, up to 10 hours web browsing or video. SIZE: 250.6×174.1×7.5 mm, 487 g.
STYLUS COMPATIBILITY: Supports Apple Pencil (1st generation) ONLY. NOT compatible with Apple Pencil Pro or Apple Pencil (2nd generation). Apple Pencil Pro will NOT attach or pair with this iPad.
AMAZON UK RATINGS: 4.5/5. Buyers report: 'nice and light, clear display'; 'fast, smooth performance for everyday tasks'; 'excellent for reading, streaming, light note-taking'; 'great battery life'; 'best value entry-level iPad'."""),
        ItemType("IPAD12", """Apple iPad Air 11-inch (M2) — Year introduced: 2024.
DISPLAY: 10.86-inch Liquid Retina LED IPS Multi-Touch. 2360×1640 px at 264 ppi. Wide colour (P3). True Tone. Anti-reflective. Fully laminated. 500 nits.
CHIP: Apple M2 — 8-core CPU, 9-core GPU, 16-core Neural Engine, 8 GB RAM. Apple Intelligence capable.
STORAGE: 128 GB. CONNECTOR: USB-C. Magnetic side connector for Apple Pencil.
BIOMETRICS: Touch ID (top button). CAMERAS: 12MP Wide rear (ƒ/1.8, Focus Pixels, 4K video, Smart HDR 4). 12MP Landscape front Center Stage (ƒ/2.0).
WIRELESS: Wi-Fi 6E (802.11ax). Bluetooth 5.3.
BATTERY: All-day (~10 hours). SIZE: 247.6×178.5×6.1 mm, 462 g.
STYLUS COMPATIBILITY: Supports Apple Pencil Pro and Apple Pencil (USB-C) ONLY. NOT compatible with Apple Pencil (1st or 2nd generation). Apple Pencil Pro magnetically attaches and pairs with this iPad.
AMAZON UK RATINGS: 4.7/5 (1,556 ratings). Buyers report: 'fantastic screen — vivid, bright, high definition'; 'seamless multitasking'; 'excellent for notes and annotation with Apple Pencil Pro'; 'premium look and feel — amazing alternative to iPad Pro'."""),
        ItemType("APPLEPENCILPRO", """Apple Pencil Pro — Year introduced: 2024.
OVERVIEW: Most advanced Apple Pencil. Pixel-perfect precision, tilt and pressure sensitivity, industry-leading low latency.
ADVANCED FEATURES: Squeeze — opens tool palette to switch tools, line weights, colours. Barrel roll — gyroscope allows rotation for shaped pen/brush control. Haptic feedback — pulse confirms squeeze/double-tap. Double-tap — switch between tools. Find My — locatable in Find My app. Apple Pencil hover — previews touch point before contact.
ATTACHMENT: Magnetically attaches, pairs, and charges on the side of compatible iPad. CONNECTIVITY: Bluetooth. SYSTEM REQUIREMENT: iPadOS 17.5 or later.
DIMENSIONS: 166 mm length, 8.9 mm diameter, 19.15 g.
COMPATIBLE IPADS (FULL LIST): iPad Pro 13-inch (M4, M5); iPad Pro 11-inch (M4, M5); iPad Air 13-inch (M2, M3, M4); iPad Air 11-inch (M2, M3, M4); iPad mini (A17 Pro). ONLY compatible with these models.
NOT COMPATIBLE WITH: iPad (9th generation) or any older iPad. Will not attach or pair with iPad 9th gen.
AMAZON UK RATINGS: 4.6/5 (5,628 ratings). Buyers report: 'works so well and so easy to use'; 'fast charging, lasts ages'; 'intuitive for note-taking'; 'I use it with my Air M2 2024 and it works brilliantly'; 'completely changes how you use iPad'."""),
    ],
    [1, 1, 1])

ElectronicsScenarioPDFFull = Scenario(
    "ELECTRONICS-PDF",
    "A local library is auctioning off donated electronics that are all like-new and in perfect working condition. Item descriptions are drawn from official Apple Support technical specification pages and verified Amazon UK customer reviews.",
    [
        ItemType("AIRPODS2", """Apple AirPods (2nd Generation) — Year introduced: 2019.
HARDWARE: H1 headphone chip. Bluetooth 5.0. Dual beamforming microphones; dual optical sensors; motion-detecting and speech-detecting accelerometers.
CONTROLS: Double-tap to play/pause/skip/answer calls. Hey Siri supported.
BATTERY: Up to 5 hours listening per charge; 15 minutes in case = 3 hours listening. Over 24 hours total with Lightning Charging Case.
CHARGING: Lightning Charging Case (or optional Wireless Charging Case, Qi-compatible).
AUDIO: Standard in-ear earbuds. NO Active Noise Cancellation. NO Transparency mode.
COMPATIBILITY: Works with any Bluetooth device; seamless pairing with Apple devices running latest iOS/iPadOS/watchOS/macOS/tvOS.
DIMENSIONS: Each earbud 40.5×16.5×18 mm, 4 g. Case 53.5×44.3×21.3 mm, 38.2 g.
AMAZON UK RATINGS: 4.1/5. Buyers report: 'great quality, use them every day'; 'good value, connects quickly to iPhone instantly'; 'solid everyday earbuds — not premium but does the job well'. Note: no noise cancellation — if ANC is required, consider AirPods Max instead."""),

        ItemType("AIRPODSPROMAX", """Apple AirPods Max — Year introduced: 2020.
HARDWARE: Apple H1 headphone chip in each ear cup (two chips total). Apple-designed 40 mm dynamic driver. 9 microphones total: 8 for Active Noise Cancellation, 3 for voice pickup.
SENSORS: Optical sensor, position sensor, case-detect sensor, accelerometer, gyroscope (per ear cup).
AUDIO FEATURES: Pro-Level Active Noise Cancellation (ANC); Transparency mode; Personalised Spatial Audio with dynamic head tracking; Adaptive EQ.
CONTROLS: Digital Crown (volume, play/pause, call answer/end, skip tracks, Siri). Listening mode button (switches ANC / Transparency). Hey Siri supported.
BATTERY: Up to 20 hours listening with ANC or Transparency mode enabled. Up to 20 hours movie playback with Spatial Audio. 5 minutes charge = ~1.5 hours listening. Ultra-low-power state in Smart Case preserves charge.
CHARGING: USB-C (current model).
CONNECTIVITY: Bluetooth 5.0.
WEIGHT: 384.8 g (headphones); 134.5 g (Smart Case).
AMAZON UK RATINGS: 4.5/5 (1,523 ratings). Buyers report: 'superb noise cancellation — on low volume no other sound can break through'; 'fantastic headphones, quality finish'; 'comfortable, great for studying in busy places'; 'USB-C charging is convenient'; 'microphone quality is great'. Best for: focus work, commuting, study environments with background noise."""),

        ItemType("IPAD9", """Apple iPad (9th Generation) — Year introduced: 2021.
DISPLAY: 10.2-inch LED backlit IPS Retina Multi-Touch display. 2160×1620 pixels at 264 ppi. True Tone. 500 nits brightness. Oleophobic coating.
CHIP: A13 Bionic with Neural Engine.
STORAGE: 64 GB (also available in 256 GB).
CONNECTOR: Lightning. Also has headphone jack, Smart Connector.
BIOMETRICS: Touch ID (home button, front face).
CAMERAS: 8 MP Wide rear (ƒ/2.4, digital zoom 5×, panorama up to 43 MP, HDR). 12 MP Ultra Wide front (ƒ/2.4, Centre Stage, 1080p video).
WIRELESS: Wi-Fi 5 (802.11ac, 2×2 MIMO, up to 866 Mb/s). Bluetooth 4.2.
BATTERY: Built-in 32.4 Wh lithium-polymer. Up to 10 hours web browsing on Wi-Fi or video playback.
SIZE/WEIGHT: 250.6×174.1×7.5 mm, 487 g (Wi-Fi model).
STYLUS COMPATIBILITY: Supports Apple Pencil (1st generation) ONLY. NOT compatible with Apple Pencil (2nd generation) or Apple Pencil Pro. Apple Pencil 1st gen sold separately.
AMAZON UK RATINGS: 4.5/5. Buyers report: 'nice and light, clear display'; 'fast, smooth performance for everyday tasks'; 'excellent for reading, streaming, and light note-taking'; 'great battery life'; 'best value entry-level iPad'."""),

        ItemType("IPAD12", """Apple iPad Air 11-inch (M2) — Year introduced: 2024.
DISPLAY: 10.86-inch Liquid Retina LED backlit IPS Multi-Touch display. 2360×1640 pixels at 264 ppi. Wide colour (P3). True Tone. Anti-reflective coating. Fully laminated. 500 nits brightness.
CHIP: Apple M2 — 8-core CPU (4 performance + 4 efficiency), 9-core GPU, 16-core Neural Engine, 8 GB RAM. Hardware-accelerated H.264 and HEVC encode/decode.
APPLE INTELLIGENCE: Yes — built-in personal intelligence system.
STORAGE: 128 GB (also available in 256 GB, 512 GB, 1 TB).
CONNECTOR: USB-C. Magnetic connector for Apple Pencil on side.
BIOMETRICS: Touch ID (top button).
CAMERAS: 12 MP Wide rear (ƒ/1.8, autofocus with Focus Pixels, 4K video, Smart HDR 4). 12 MP Landscape front Center Stage camera (ƒ/2.0, 1080p video).
WIRELESS: Wi-Fi 6E (802.11ax). Bluetooth 5.3.
BATTERY: All-day battery life (approximately 10 hours web browsing).
SIZE/WEIGHT: 247.6×178.5×6.1 mm, 462 g (Wi-Fi model).
STYLUS COMPATIBILITY: Supports Apple Pencil Pro and Apple Pencil (USB-C) ONLY. NOT compatible with Apple Pencil (1st generation) or Apple Pencil (2nd generation).
AMAZON UK RATINGS: 4.7/5 (1,556 ratings). Buyers report: 'fantastic screen — vivid, bright, high definition'; 'seamless multitasking, apps switch almost instantly'; 'excellent for notes and annotation with Apple Pencil Pro'; 'premium look and feel — amazing alternative to iPad Pro'; 'voice input works brilliantly'."""),

        ItemType("APPLEPENCIL2", """Apple Pencil (2nd Generation) — Year introduced: 2018.
OVERVIEW: Pixel-perfect precision, industry-leading low latency stylus for drawing, sketching, colouring, note-taking, marking up PDFs.
FEATURES: Double-tap touch surface to switch tools without setting it down. Supports Apple Pencil hover (preview where pencil will touch down — only on iPad Pro 11" 4th gen and iPad Pro 12.9" 6th gen).
ATTACHMENT: Magnetically attaches, charges, and pairs to the side of compatible iPad.
CONNECTIVITY: Bluetooth.
DIMENSIONS: 166 mm length, 8.9 mm diameter, 18.2 g.
COMPATIBLE IPADS (FULL LIST from Apple Support): iPad Pro 12.9-inch (3rd, 4th, 5th, 6th generation); iPad Pro 11-inch (1st, 2nd, 3rd, 4th generation); iPad Air (4th generation); iPad Air (5th generation); iPad mini (6th generation).
NOT COMPATIBLE WITH: iPad (9th generation) — uses Lightning, not magnetic side connector. iPad Air 11-inch (M2/M3/M4) — requires Apple Pencil Pro or Apple Pencil (USB-C) instead.
AMAZON UK RATINGS: 4.1/5 (71 ratings). Buyers report: 'connected right away, charges well'; 'immaculate condition, great pencil'; 'completely changes how you use iPad'. WARNING: Several buyers report pairing failures on incompatible iPad models. Verify your iPad is in the compatibility list above before purchasing."""),

        ItemType("APPLEPENCILPRO", """Apple Pencil Pro — Year introduced: 2024.
OVERVIEW: Most advanced Apple Pencil. Pixel-perfect precision, tilt and pressure sensitivity, industry-leading low latency for note-taking, drawing, and art.
ADVANCED FEATURES: Squeeze gesture — squeeze Apple Pencil Pro to open a new tool palette (switch tools, line weights, colours instantly). Barrel roll — built-in gyroscope lets you rotate the pencil for precise control of shaped pen and brush tools. Haptic feedback — light pulse confirms squeeze or double-tap actions. Double-tap — quickly switch between tools. Find My — locate it in the Find My app if misplaced. Apple Pencil hover — preview exactly where pencil will touch down before contact.
ATTACHMENT: Magnetically attaches, pairs, and charges on the side of compatible iPad.
CONNECTIVITY: Bluetooth.
SYSTEM REQUIREMENT: iPadOS 17.5 or later.
DIMENSIONS: 166 mm length, 8.9 mm diameter, 19.15 g.
COMPATIBLE IPADS (FULL LIST from Apple Support): iPad Pro 13-inch (M4, M5); iPad Pro 11-inch (M4, M5); iPad Air 13-inch (M2, M3, M4); iPad Air 11-inch (M2, M3, M4); iPad mini (A17 Pro).
NOT COMPATIBLE WITH: iPad (9th generation). iPad Air (4th or 5th generation). Any older iPad Pro or iPad mini.
AMAZON UK RATINGS: 4.6/5 (5,628 ratings). Buyers report: 'works so well and is so easy to use with almost anything'; 'fast charging, lasts ages'; 'great addition to any iPad — intuitive for note-taking'; 'I use it with my Air M2 2024 and it works brilliantly'; 'completely changes how you use iPad'. Note: expensive but widely considered worth it for iPad Air M2 and iPad Pro M4/M5 users."""),
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

scenarios = [TransportationScenario, ElectronicsScenario, ElectronicsScenarioSpecs, ElectronicsScenarioReviews, ElectronicsScenarioPDFFull, ElectronicsMiniBasic, ElectronicsMiniSpecs, ElectronicsMiniPDF, PreservesScenario]