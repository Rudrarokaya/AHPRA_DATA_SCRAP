"""
AHPRA Health Professions, States, and Divisions Data
"""

# All 16 registered health professions
PROFESSIONS = [
    "Aboriginal and Torres Strait Islander Health Practitioner",
    "Chinese Medicine Practitioner",
    "Chiropractor",
    "Dental Practitioner",
    "Medical Practitioner",
    "Medical Radiation Practitioner",
    "Midwife",
    "Nurse",
    "Occupational Therapist",
    "Optometrist",
    "Osteopath",
    "Paramedic",
    "Pharmacist",
    "Physiotherapist",
    "Podiatrist",
    "Psychologist",
]

# Australian states and territories
STATES = [
    "Australian Capital Territory",
    "New South Wales",
    "Northern Territory",
    "Queensland",
    "South Australia",
    "Tasmania",
    "Victoria",
    "Western Australia",
]

# State abbreviations mapping
STATE_ABBREVIATIONS = {
    "Australian Capital Territory": "ACT",
    "New South Wales": "NSW",
    "Northern Territory": "NT",
    "Queensland": "QLD",
    "South Australia": "SA",
    "Tasmania": "TAS",
    "Victoria": "VIC",
    "Western Australia": "WA",
}

# Divisions for professions that have them
DIVISIONS = {
    "Chinese Medicine Practitioner": [
        "Acupuncturist",
        "Chinese herbal medicine practitioner",
        "Chinese herbal dispenser",
    ],
    "Dental Practitioner": [
        "Dentist",
        "Dental therapist",
        "Dental hygienist",
        "Dental prosthetist",
        "Oral health therapist",
    ],
    "Medical Radiation Practitioner": [
        "Diagnostic radiographer",
        "Nuclear medicine technologist",
        "Radiation therapist",
    ],
    "Nurse": [
        "Registered nurse",
        "Enrolled nurse",
    ],
}

# Alphabet for prefix search
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Common name prefixes that may need deeper recursion
# (these are known to have many practitioners)
HIGH_VOLUME_PREFIXES = [
    "SM",  # Smith
    "JO",  # Jones, Johnson
    "WI",  # Williams, Wilson
    "BR",  # Brown
    "TA",  # Taylor
    "AN",  # Anderson
    "TH",  # Thomas
    "JA",  # Jackson, James
    "WH",  # White
    "HA",  # Harris
    "MA",  # Martin, Martinez
    "TH",  # Thompson
    "GA",  # Garcia
    "CL",  # Clark
    "RO",  # Robinson, Rodriguez
    "LE",  # Lee, Lewis
    "WA",  # Walker, Wang
    "NG",  # Nguyen
    "CH",  # Chen, Chang
    "KI",  # King, Kim
]

# Major suburbs/localities by state (sourced from ABS data)
# Used for multi-dimensional discovery to increase coverage
MAJOR_SUBURBS = {
    "New South Wales": [
        "Sydney", "Parramatta", "Newcastle", "Wollongong", "Central Coast",
        "Penrith", "Liverpool", "Blacktown", "Campbelltown", "Bankstown",
        "Hornsby", "Chatswood", "North Sydney", "Bondi", "Manly",
        "Sutherland", "Hurstville", "Kogarah", "Randwick", "Burwood",
        "Strathfield", "Auburn", "Ryde", "Epping", "Macquarie Park",
        "Gosford", "Wyong", "Maitland", "Cessnock", "Lake Macquarie",
        "Port Macquarie", "Tamworth", "Orange", "Dubbo", "Wagga Wagga",
        "Albury", "Coffs Harbour", "Lismore", "Tweed Heads", "Broken Hill",
    ],
    "Victoria": [
        "Melbourne", "Geelong", "Ballarat", "Bendigo", "Shepparton",
        "Mildura", "Warrnambool", "Traralgon", "Wodonga", "Wangaratta",
        "Frankston", "Dandenong", "Box Hill", "Ringwood", "Footscray",
        "St Kilda", "South Yarra", "Richmond", "Carlton", "Brunswick",
        "Preston", "Heidelberg", "Moorabbin", "Caulfield", "Brighton",
        "Glen Waverley", "Doncaster", "Camberwell", "Hawthorn", "Kew",
        "Sunshine", "Werribee", "Melton", "Pakenham", "Cranbourne",
        "Mornington", "Rosebud", "Sale", "Bairnsdale", "Horsham",
    ],
    "Queensland": [
        "Brisbane", "Gold Coast", "Sunshine Coast", "Townsville", "Cairns",
        "Toowoomba", "Mackay", "Rockhampton", "Bundaberg", "Hervey Bay",
        "Gladstone", "Mount Isa", "Ipswich", "Logan", "Redcliffe",
        "Caboolture", "Caloundra", "Maroochydore", "Noosa", "Nambour",
        "Southport", "Surfers Paradise", "Robina", "Nerang", "Burleigh Heads",
        "Chermside", "Indooroopilly", "Toowong", "Woolloongabba", "Fortitude Valley",
        "Springwood", "Browns Plains", "Beenleigh", "Cleveland", "Redland Bay",
        "Bowen", "Emerald", "Longreach", "Roma", "Charleville",
    ],
    "Western Australia": [
        "Perth", "Fremantle", "Mandurah", "Rockingham", "Bunbury",
        "Geraldton", "Kalgoorlie", "Albany", "Broome", "Karratha",
        "Port Hedland", "Busselton", "Joondalup", "Wanneroo", "Stirling",
        "Morley", "Midland", "Armadale", "Gosnells", "Canning",
        "Subiaco", "Claremont", "Nedlands", "South Perth", "Victoria Park",
        "Scarborough", "Hillarys", "Duncraig", "Karrinyup", "Innaloo",
        "Thornlie", "Cannington", "Belmont", "Bayswater", "Bassendean",
        "Esperance", "Carnarvon", "Newman", "Tom Price", "Exmouth",
    ],
    "South Australia": [
        "Adelaide", "Mount Gambier", "Whyalla", "Murray Bridge", "Port Augusta",
        "Port Lincoln", "Port Pirie", "Victor Harbor", "Gawler", "Mount Barker",
        "Salisbury", "Elizabeth", "Modbury", "Marion", "Noarlunga",
        "Glenelg", "Brighton", "Henley Beach", "Semaphore", "Port Adelaide",
        "Norwood", "Burnside", "Unley", "Mitcham", "Blackwood",
        "Prospect", "Walkerville", "Campbelltown", "Paradise", "Magill",
        "Tea Tree Gully", "Golden Grove", "Mawson Lakes", "Salisbury", "Playford",
        "Clare", "Tanunda", "Nuriootpa", "Renmark", "Berri",
    ],
    "Tasmania": [
        "Hobart", "Launceston", "Devonport", "Burnie", "Kingston",
        "Glenorchy", "Clarence", "Moonah", "New Town", "Sandy Bay",
        "Rosny", "Bellerive", "Lindisfarne", "Howrah", "Sorell",
        "Mowbray", "Newnham", "Invermay", "Prospect", "Ravenswood",
        "Ulverstone", "Wynyard", "Smithton", "George Town", "Scottsdale",
        "Queenstown", "New Norfolk", "Bridgewater", "Brighton", "Richmond",
    ],
    "Australian Capital Territory": [
        "Canberra", "Belconnen", "Woden", "Tuggeranong", "Gungahlin",
        "Civic", "Braddon", "Dickson", "Fyshwick", "Kingston",
        "Manuka", "Barton", "Deakin", "Curtin", "Weston",
        "Bruce", "Mitchell", "Phillip", "Mawson", "Kambah",
        "Queanbeyan",  # Often grouped with ACT for health services
    ],
    "Northern Territory": [
        "Darwin", "Alice Springs", "Palmerston", "Katherine", "Nhulunbuy",
        "Tennant Creek", "Jabiru", "Casuarina", "Stuart Park", "Fannie Bay",
        "Parap", "Nightcliff", "Rapid Creek", "Millner", "Coconut Grove",
        "Howard Springs", "Humpty Doo", "Litchfield", "Batchelor", "Pine Creek",
    ],
}
