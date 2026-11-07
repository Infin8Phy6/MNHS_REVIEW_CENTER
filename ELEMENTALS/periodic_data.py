"""Tile data for every element, used to seed the SQLite database.

Columns: z, symbol, name, mass (amu), group (0 for the f-block rows), period,
series ("" | "L" lanthanide | "A" actinide), family (drives the tile colour),
metal class, state at room temperature, common oxidation states, and the
Latin/Greek word the symbol comes from when it is not taken from the English name.
"""

ROWS = [
    (1, "H", "Hydrogen", 1.008, 1, 1, "", "nonmetal", "Nonmetal", "Gas", "+1, -1", ""),
    (2, "He", "Helium", 4.0026, 18, 1, "", "noble", "Nonmetal", "Gas", "0", "Greek helios, sun"),
    (3, "Li", "Lithium", 6.94, 1, 2, "", "alkali", "Metal", "Solid", "+1", "Greek lithos, stone"),
    (4, "Be", "Beryllium", 9.0122, 2, 2, "", "alkaline", "Metal", "Solid", "+2", ""),
    (5, "B", "Boron", 10.81, 13, 2, "", "metalloid", "Metalloid", "Solid", "+3", ""),
    (6, "C", "Carbon", 12.011, 14, 2, "", "nonmetal", "Nonmetal", "Solid", "-4, +2, +4", "Latin carbo, charcoal"),
    (7, "N", "Nitrogen", 14.007, 15, 2, "", "nonmetal", "Nonmetal", "Gas", "-3, +2, +3, +4, +5", "Greek nitron, soda"),
    (8, "O", "Oxygen", 15.999, 16, 2, "", "nonmetal", "Nonmetal", "Gas", "-2, -1", "Greek oxys, sharp"),
    (9, "F", "Fluorine", 18.998, 17, 2, "", "halogen", "Nonmetal", "Gas", "-1", "Latin fluere, to flow"),
    (10, "Ne", "Neon", 20.180, 18, 2, "", "noble", "Nonmetal", "Gas", "0", "Greek neos, new"),
    (11, "Na", "Sodium", 22.990, 1, 3, "", "alkali", "Metal", "Solid", "+1", "Latin natrium, natron"),
    (12, "Mg", "Magnesium", 24.305, 2, 3, "", "alkaline", "Metal", "Solid", "+2", ""),
    (13, "Al", "Aluminium", 26.982, 13, 3, "", "post", "Metal", "Solid", "+3", "Latin alumen, alum"),
    (14, "Si", "Silicon", 28.085, 14, 3, "", "metalloid", "Metalloid", "Solid", "-4, +4", "Latin silex, flint"),
    (15, "P", "Phosphorus", 30.974, 15, 3, "", "nonmetal", "Nonmetal", "Solid", "-3, +3, +5", "Greek phosphoros, light-bearer"),
    (16, "S", "Sulfur", 32.06, 16, 3, "", "nonmetal", "Nonmetal", "Solid", "-2, +4, +6", "Latin sulphur"),
    (17, "Cl", "Chlorine", 35.45, 17, 3, "", "halogen", "Nonmetal", "Gas", "-1, +1, +3, +5, +7", "Greek chloros, pale green"),
    (18, "Ar", "Argon", 39.948, 18, 3, "", "noble", "Nonmetal", "Gas", "0", "Greek argos, inactive"),
    (19, "K", "Potassium", 39.098, 1, 4, "", "alkali", "Metal", "Solid", "+1", "Latin kalium, potash"),
    (20, "Ca", "Calcium", 40.078, 2, 4, "", "alkaline", "Metal", "Solid", "+2", "Latin calx, lime"),
    (21, "Sc", "Scandium", 44.956, 3, 4, "", "transition", "Metal", "Solid", "+3", ""),
    (22, "Ti", "Titanium", 47.867, 4, 4, "", "transition", "Metal", "Solid", "+2, +3, +4", "Latin titanes, sons of Earth"),
    (23, "V", "Vanadium", 50.942, 5, 4, "", "transition", "Metal", "Solid", "+2, +3, +4, +5", "Old Norse Vanadis"),
    (24, "Cr", "Chromium", 51.996, 6, 4, "", "transition", "Metal", "Solid", "+2, +3, +6", "Greek chroma, colour"),
    (25, "Mn", "Manganese", 54.938, 7, 4, "", "transition", "Metal", "Solid", "+2, +3, +4, +6, +7", ""),
    (26, "Fe", "Iron", 55.845, 8, 4, "", "transition", "Metal", "Solid", "+2, +3", "Latin ferrum"),
    (27, "Co", "Cobalt", 58.933, 9, 4, "", "transition", "Metal", "Solid", "+2, +3", "German kobold, mine spirit"),
    (28, "Ni", "Nickel", 58.693, 10, 4, "", "transition", "Metal", "Solid", "+2", ""),
    (29, "Cu", "Copper", 63.546, 11, 4, "", "transition", "Metal", "Solid", "+1, +2", "Latin cuprum, from Cyprus"),
    (30, "Zn", "Zinc", 65.38, 12, 4, "", "transition", "Metal", "Solid", "+2", ""),
    (31, "Ga", "Gallium", 69.723, 13, 4, "", "post", "Metal", "Solid", "+3", "Latin Gallia, France"),
    (32, "Ge", "Germanium", 72.630, 14, 4, "", "metalloid", "Metalloid", "Solid", "+2, +4", "Latin Germania, Germany"),
    (33, "As", "Arsenic", 74.922, 15, 4, "", "metalloid", "Metalloid", "Solid", "-3, +3, +5", "Greek arsenikon"),
    (34, "Se", "Selenium", 78.971, 16, 4, "", "nonmetal", "Nonmetal", "Solid", "-2, +4, +6", "Greek selene, moon"),
    (35, "Br", "Bromine", 79.904, 17, 4, "", "halogen", "Nonmetal", "Liquid", "-1, +1, +3, +5", "Greek bromos, stink"),
    (36, "Kr", "Krypton", 83.798, 18, 4, "", "noble", "Nonmetal", "Gas", "0, +2", "Greek kryptos, hidden"),
    (37, "Rb", "Rubidium", 85.468, 1, 5, "", "alkali", "Metal", "Solid", "+1", "Latin rubidus, red"),
    (38, "Sr", "Strontium", 87.62, 2, 5, "", "alkaline", "Metal", "Solid", "+2", ""),
    (39, "Y", "Yttrium", 88.906, 3, 5, "", "transition", "Metal", "Solid", "+3", "Ytterby, a Swedish village"),
    (40, "Zr", "Zirconium", 91.224, 4, 5, "", "transition", "Metal", "Solid", "+4", "Persian zargun, gold-coloured"),
    (41, "Nb", "Niobium", 92.906, 5, 5, "", "transition", "Metal", "Solid", "+3, +5", "Greek Niobe, daughter of Tantalus"),
    (42, "Mo", "Molybdenum", 95.95, 6, 5, "", "transition", "Metal", "Solid", "+2, +4, +6", "Greek molybdos, lead"),
    (43, "Tc", "Technetium", 98.0, 7, 5, "", "transition", "Metal", "Solid", "+4, +7", "Greek technetos, artificial"),
    (44, "Ru", "Ruthenium", 101.07, 8, 5, "", "transition", "Metal", "Solid", "+2, +3, +4", "Latin Ruthenia, Russia"),
    (45, "Rh", "Rhodium", 102.91, 9, 5, "", "transition", "Metal", "Solid", "+1, +3", "Greek rhodon, rose"),
    (46, "Pd", "Palladium", 106.42, 10, 5, "", "transition", "Metal", "Solid", "+2, +4", "Greek Pallas, the asteroid"),
    (47, "Ag", "Silver", 107.87, 11, 5, "", "transition", "Metal", "Solid", "+1", "Latin argentum, white"),
    (48, "Cd", "Cadmium", 112.41, 12, 5, "", "transition", "Metal", "Solid", "+2", ""),
    (49, "In", "Indium", 114.82, 13, 5, "", "post", "Metal", "Solid", "+1, +3", "Latin indicum, indigo"),
    (50, "Sn", "Tin", 118.71, 14, 5, "", "post", "Metal", "Solid", "+2, +4", "Latin stannum"),
    (51, "Sb", "Antimony", 121.76, 15, 5, "", "metalloid", "Metalloid", "Solid", "-3, +3, +5", "Latin stibium"),
    (52, "Te", "Tellurium", 127.60, 16, 5, "", "metalloid", "Metalloid", "Solid", "-2, +4, +6", "Latin tellus, Earth"),
    (53, "I", "Iodine", 126.90, 17, 5, "", "halogen", "Nonmetal", "Solid", "-1, +1, +5, +7", "Greek ioeides, violet"),
    (54, "Xe", "Xenon", 131.29, 18, 5, "", "noble", "Nonmetal", "Gas", "0, +2, +4, +6", "Greek xenos, stranger"),
    (55, "Cs", "Caesium", 132.91, 1, 6, "", "alkali", "Metal", "Solid", "+1", "Latin caesius, sky blue"),
    (56, "Ba", "Barium", 137.33, 2, 6, "", "alkaline", "Metal", "Solid", "+2", "Greek barys, heavy"),
    (57, "La", "Lanthanum", 138.91, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Greek lanthanein, to lie hidden"),
    (58, "Ce", "Cerium", 140.12, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3, +4", "Ceres, the dwarf planet"),
    (59, "Pr", "Praseodymium", 140.91, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Greek prasios, green"),
    (60, "Nd", "Neodymium", 144.24, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Greek neos didymos, new twin"),
    (61, "Pm", "Promethium", 145.0, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Greek Prometheus, who brought fire"),
    (62, "Sm", "Samarium", 150.36, 0, 6, "L", "lanthanide", "Metal", "Solid", "+2, +3", ""),
    (63, "Eu", "Europium", 151.96, 0, 6, "L", "lanthanide", "Metal", "Solid", "+2, +3", "Europe"),
    (64, "Gd", "Gadolinium", 157.25, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", ""),
    (65, "Tb", "Terbium", 158.93, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Ytterby, a Swedish village"),
    (66, "Dy", "Dysprosium", 162.50, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Greek dysprositos, hard to get"),
    (67, "Ho", "Holmium", 164.93, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Latin Holmia, Stockholm"),
    (68, "Er", "Erbium", 167.26, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Ytterby, a Swedish village"),
    (69, "Tm", "Thulium", 168.93, 0, 6, "L", "lanthanide", "Metal", "Solid", "+2, +3", "Thule, the far north"),
    (70, "Yb", "Ytterbium", 173.05, 0, 6, "L", "lanthanide", "Metal", "Solid", "+2, +3", "Ytterby, a Swedish village"),
    (71, "Lu", "Lutetium", 174.97, 0, 6, "L", "lanthanide", "Metal", "Solid", "+3", "Latin Lutetia, Paris"),
    (72, "Hf", "Hafnium", 178.49, 4, 6, "", "transition", "Metal", "Solid", "+4", "Latin Hafnia, Copenhagen"),
    (73, "Ta", "Tantalum", 180.95, 5, 6, "", "transition", "Metal", "Solid", "+5", "Greek Tantalus"),
    (74, "W", "Tungsten", 183.84, 6, 6, "", "transition", "Metal", "Solid", "+4, +6", "Swedish wolfram, dense ore"),
    (75, "Re", "Rhenium", 186.21, 7, 6, "", "transition", "Metal", "Solid", "+4, +7", "Latin Rhenus, the Rhine"),
    (76, "Os", "Osmium", 190.23, 8, 6, "", "transition", "Metal", "Solid", "+4, +8", "Greek osme, smell"),
    (77, "Ir", "Iridium", 192.22, 9, 6, "", "transition", "Metal", "Solid", "+3, +4", "Greek iris, rainbow"),
    (78, "Pt", "Platinum", 195.08, 10, 6, "", "transition", "Metal", "Solid", "+2, +4", "Spanish platina, little silver"),
    (79, "Au", "Gold", 196.97, 11, 6, "", "transition", "Metal", "Solid", "+1, +3", "Latin aurum, shining dawn"),
    (80, "Hg", "Mercury", 200.59, 12, 6, "", "transition", "Metal", "Liquid", "+1, +2", "Latin hydrargyrum, wet silver"),
    (81, "Tl", "Thallium", 204.38, 13, 6, "", "post", "Metal", "Solid", "+1, +3", "Greek thallos, green shoot"),
    (82, "Pb", "Lead", 207.2, 14, 6, "", "post", "Metal", "Solid", "+2, +4", "Latin plumbum"),
    (83, "Bi", "Bismuth", 208.98, 15, 6, "", "post", "Metal", "Solid", "+3, +5", ""),
    (84, "Po", "Polonium", 209.0, 16, 6, "", "post", "Metal", "Solid", "+2, +4", "Latin Polonia, Poland"),
    (85, "At", "Astatine", 210.0, 17, 6, "", "halogen", "Metalloid", "Solid", "-1, +1", "Greek astatos, unstable"),
    (86, "Rn", "Radon", 222.0, 18, 6, "", "noble", "Nonmetal", "Gas", "0", "From radium, its parent"),
    (87, "Fr", "Francium", 223.0, 1, 7, "", "alkali", "Metal", "Solid", "+1", "France"),
    (88, "Ra", "Radium", 226.0, 2, 7, "", "alkaline", "Metal", "Solid", "+2", "Greek aktinos, ray"),
    (89, "Ac", "Actinium", 227.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3", "Greek aktis, beam"),
    (90, "Th", "Thorium", 232.04, 0, 7, "A", "actinide", "Metal", "Solid", "+4", "Norse Thor, god of thunder"),
    (91, "Pa", "Protactinium", 231.04, 0, 7, "A", "actinide", "Metal", "Solid", "+4, +5", "Greek protos, first"),
    (92, "U", "Uranium", 238.03, 0, 7, "A", "actinide", "Metal", "Solid", "+3, +4, +5, +6", "Greek Ouranos, the sky"),
    (93, "Np", "Neptunium", 237.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3, +4, +5, +6", "Neptune, the planet"),
    (94, "Pu", "Plutonium", 244.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3, +4, +5, +6", "Pluto, the dwarf planet"),
    (95, "Am", "Americium", 243.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3", "The Americas"),
    (96, "Cm", "Curium", 247.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3", "The Curies"),
    (97, "Bk", "Berkelium", 247.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3, +4", "Berkeley, California"),
    (98, "Cf", "Californium", 251.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3", "California"),
    (99, "Es", "Einsteinium", 252.0, 0, 7, "A", "actinide", "Metal", "Solid", "+3", "Albert Einstein"),
    (100, "Fm", "Fermium", 257.0, 0, 7, "A", "actinide", "Metal", "Unknown", "+3", "Enrico Fermi"),
    (101, "Md", "Mendelevium", 258.0, 0, 7, "A", "actinide", "Metal", "Unknown", "+2, +3", "Dmitri Mendeleev"),
    (102, "No", "Nobelium", 259.0, 0, 7, "A", "actinide", "Metal", "Unknown", "+2, +3", "Alfred Nobel"),
    (103, "Lr", "Lawrencium", 266.0, 0, 7, "A", "actinide", "Metal", "Unknown", "+3", "Ernest Lawrence"),
    (104, "Rf", "Rutherfordium", 267.0, 4, 7, "", "transition", "Metal", "Unknown", "+4", "Ernest Rutherford"),
    (105, "Db", "Dubnium", 268.0, 5, 7, "", "transition", "Metal", "Unknown", "+5", "Dubna, the Russian town"),
    (106, "Sg", "Seaborgium", 269.0, 6, 7, "", "transition", "Metal", "Unknown", "+6", "Glenn Seaborg"),
    (107, "Bh", "Bohrium", 270.0, 7, 7, "", "transition", "Metal", "Unknown", "+7", "Niels Bohr"),
    (108, "Hs", "Hassium", 277.0, 8, 7, "", "transition", "Metal", "Unknown", "+8", "Latin Hassia, Hesse"),
    (109, "Mt", "Meitnerium", 278.0, 9, 7, "", "transition", "Metal", "Unknown", "+3, +4", "Lise Meitner"),
    (110, "Ds", "Darmstadtium", 281.0, 10, 7, "", "transition", "Metal", "Unknown", "+2, +4", "Darmstadt, Germany"),
    (111, "Rg", "Roentgenium", 282.0, 11, 7, "", "transition", "Metal", "Unknown", "+1, +3", "Wilhelm Roentgen"),
    (112, "Cn", "Copernicium", 285.0, 12, 7, "", "transition", "Metal", "Unknown", "0", "Nicolaus Copernicus"),
    (113, "Nh", "Nihonium", 286.0, 13, 7, "", "post", "Unknown", "Unknown", "+1, +3", "Japanese Nihon, Japan"),
    (114, "Fl", "Flerovium", 289.0, 14, 7, "", "post", "Unknown", "Unknown", "+2, +4", "The Flerov laboratory"),
    (115, "Mc", "Moscovium", 290.0, 15, 7, "", "post", "Unknown", "Unknown", "+1, +3", "Moscow region"),
    (116, "Lv", "Livermorium", 293.0, 16, 7, "", "post", "Unknown", "Unknown", "+2, +4", "Livermore laboratory"),
    (117, "Ts", "Tennessine", 294.0, 17, 7, "", "halogen", "Unknown", "Unknown", "-1, +1", "Tennessee, USA"),
    (118, "Og", "Oganesson", 294.0, 18, 7, "", "noble", "Unknown", "Unknown", "0", "Yuri Oganessian"),
]

# A few standard atomic weights are printed on real tiles with a trailing zero
# that a number cannot keep.
MASS_DISPLAY = {10: "20.180", 11: "22.990", 32: "72.630", 52: "127.60", 53: "126.90"}

# Ground states that do not follow the plain Aufbau order; the values replace
# the generated counts for those orbitals and are checked to keep the total
# equal to the atomic number.
CONFIG_FIX = {
    24: {"4s": 1, "3d": 5},
    29: {"4s": 1, "3d": 10},
    41: {"5s": 1, "4d": 4},
    42: {"5s": 1, "4d": 5},
    44: {"5s": 1, "4d": 7},
    45: {"5s": 1, "4d": 8},
    46: {"5s": 0, "4d": 10},
    47: {"5s": 1, "4d": 10},
    57: {"4f": 0, "5d": 1},
    58: {"4f": 1, "5d": 1},
    64: {"4f": 7, "5d": 1},
    89: {"5f": 0, "6d": 1},
    90: {"5f": 0, "6d": 2},
    91: {"5f": 2, "6d": 1},
    92: {"5f": 3, "6d": 1},
    93: {"5f": 4, "6d": 1},
    94: {"5f": 6, "6d": 0},
    95: {"5f": 7, "6d": 0},
    96: {"5f": 7, "6d": 1},
    105: {"7s": 1, "6d": 4},
    106: {"7s": 1, "6d": 5},
}

FILL_ORDER = [
    "1s", "2s", "2p", "3s", "3p", "4s", "3d", "4p", "5s", "4d", "5p", "6s",
    "4f", "5d", "6p", "7s", "5f", "6d", "7p",
]
CAPACITY = {"s": 2, "p": 6, "d": 10, "f": 14}
SUPERSCRIPT = str.maketrans("0123456789", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")


def config_parts(z):
    """Ground state as (orbital, electrons) pairs in filling order."""
    out, left = [], z
    for orb in FILL_ORDER:
        take = min(left, CAPACITY[orb[1]])
        if take:
            out.append((orb, take))
        left -= take
        if not left:
            break
    fixes = CONFIG_FIX.get(z)
    if fixes:
        for i, (orb, _) in enumerate(out):
            if orb in fixes:
                out[i] = (orb, fixes[orb])
        out = [p for p in out if p[1]]
        have = {o for o, _ in out}
        for orb, take in fixes.items():
            if take and orb not in have:
                out.append((orb, take))
        out.sort(key=lambda p: FILL_ORDER.index(p[0]))
    if sum(c for _, c in out) != z:
        raise ValueError("electron count for Z=%d is %d" % (z, sum(c for _, c in out)))
    return out


def electron_config(z):
    """Plain form for the database and tests, e.g. '1s2 2s2 2p6 3s2 3p6 4s1 3d5'."""
    return " ".join("%s%d" % (o, c) for o, c in config_parts(z))


def config_pretty(z):
    """Tile form with superscript electron counts, e.g. 1s² 2s² 2p⁶."""
    return " ".join(o + str(c).translate(SUPERSCRIPT) for o, c in config_parts(z))


def ox_pretty(ox):
    """Oxidation states with a real minus sign, e.g. '+2, \u22123'."""
    return ", ".join(p.strip().replace("-", "\u2212") for p in ox.split(","))

