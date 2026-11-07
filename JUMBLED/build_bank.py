"""Build word_bank.json from keyword rules matched against the real MATATAG topics.

Keys come from matatag_spec.json, so every topic in the game setup lines up with
a topic in the quiz specification form. Run this after editing the rules:

    python build_bank.py

A topic that matches no rule keeps no entry and falls back to that subject's
general pool inside the game, so add a rule when a topic needs its own words.
"""
import json
import os
import re
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(os.path.dirname(BASE), "matatag_spec.json")
OUT = os.path.join(BASE, "word_bank.json")

MIN_WORDS = 4      # fewer than this and the rule is too thin to be worth it
MAX_WORDS = 8      # one topic should not drown out the rest of the subject
WORD_OK = re.compile(r"^[A-Z]{3,14}$")

SCIENCE = [
    (["atom", "ion", "molecule"],
     ["ATOM", "ELECTRON", "PROTON", "NEUTRON", "ION", "MOLECULE", "CHARGE", "NUCLEUS"]),
    (["periodic", "elements, compounds"],
     ["ELEMENT", "GROUP", "PERIOD", "METAL", "SYMBOL", "COMPOUND", "MIXTURE", "TRIAD"]),
    (["bonding", "ionic", "covalent"],
     ["BOND", "IONIC", "COVALENT", "SHARED", "VALENCE", "SALT", "METAL", "ELECTRON"]),
    (["isotope", "atomic mass", "percentage composition", "mole", "molar"],
     ["ISOTOPE", "MASS", "GRAM", "CARBON", "FORMULA", "RATIO", "MOLE", "AVOGADRO"]),
    (["reaction", "balancing", "equations", "catalyst", "chemical change", "changes"],
     ["REACTANT", "PRODUCT", "CHEMICAL", "BURN", "RUST", "ACID", "BASE", "ENERGY"]),
    (["solutions", "concentration", "saturation"],
     ["SOLUTE", "SOLVENT", "DISSOLVE", "MIXTURE", "SUGAR", "SALT", "DILUTE", "STRONG"]),
    (["separation", "substances and mixtures"],
     ["FILTER", "DISTILL", "EVAPORATE", "MAGNET", "SETTLE", "SCREEN", "PURE", "SIEVE"]),
    (["particulate", "kinetic"],
     ["PARTICLE", "GAS", "LIQUID", "SOLID", "SPACE", "MOTION", "VIBRATE", "HEAT"]),
    (["scientific method", "laboratory safety"],
     ["HYPOTHESIS", "OBSERVE", "EXPERIMENT", "THEORY", "DATA", "CONCLUDE", "GOGGLE", "GLOVE"]),
    (["measurement", "si units"],
     ["METER", "LITER", "GRAM", "SECOND", "KELVIN", "MOLE", "RULER", "VOLUME"]),
    (["cell", "biological organization", "mitosis"],
     ["CELL", "NUCLEUS", "MEMBRANE", "TISSUE", "ORGANELLE", "ORGANISM", "DIVIDE", "GROWTH"]),
    (["reproduction", "heredity", "genetics", "dna", "genes", "chromosome", "inheritance"],
     ["GENE", "TRAIT", "DOMINANT", "RECESSIVE", "ALLELE", "SEXUAL", "ASEXUAL", "PARENT"]),
    (["biotechnology"],
     ["CLONE", "CULTURE", "GENOME", "VIRUS", "INSULIN", "YEAST", "TISSUE", "ENZYME"]),
    (["virus", "bacteria", "fungi", "protist", "disease"],
     ["VIRUS", "BACTERIA", "FUNGUS", "GERM", "IMMUNE", "VACCINE", "HYGIENE", "HOST"]),
    (["ecosystem", "energy flow", "material cycles"],
     ["ECOLOGY", "PRODUCER", "CONSUMER", "PREDATOR", "PREY", "HABITAT", "NUTRIENT", "DECAY"]),
    (["biomolecules", "carbohydrate", "protein", "lipid", "nucleic"],
     ["SUGAR", "STARCH", "PROTEIN", "LIPID", "FAT", "OIL", "AMINO", "NUCLEIC"]),
    (["digestive"],
     ["STOMACH", "INTESTINE", "ENZYME", "LIVER", "ABSORB", "CHEW", "BILE", "MOUTH"]),
    (["circulatory", "blood", "cardiovascular"],
     ["HEART", "ARTERY", "VEIN", "PLASMA", "PULSE", "BLOOD", "VALVE", "OXYGEN"]),
    (["respiratory"],
     ["LUNGS", "DIAPHRAGM", "TRACHEA", "INHALE", "EXHALE", "OXYGEN", "AIRWAY", "GASP"]),
    (["force", "newton", "momentum", "impulse"],
     ["FORCE", "MASS", "PUSH", "PULL", "GRAVITY", "INERTIA", "FRICTION", "MOMENTUM"]),
    (["speed", "velocity", "distance-time", "displacement", "motion: distance"],
     ["SPEED", "VELOCITY", "DISTANCE", "METER", "SECOND", "GRAPH", "CLOCK", "STRAIGHT"]),
    (["energy transformation", "conservation of energy", "kinetic and potential",
      "work and power", "work, power"],
     ["ENERGY", "WORK", "POWER", "KINETIC", "POTENTIAL", "WATT", "JOULE", "LIGHT"]),
    (["heat transfer", "conduction", "convection", "radiation"],
     ["CONDUCT", "CONVECT", "RADIATE", "TEMPERATURE", "WARM", "FLAME", "SOLID", "METAL"]),
    (["electric charge", "current", "voltage", "resistance", "ohm", "circuit"],
     ["CURRENT", "VOLTAGE", "RESISTOR", "CIRCUIT", "OHM", "WIRE", "BATTERY", "SERIES"]),
    (["electromagnetism", "motors and generators"],
     ["MAGNET", "COIL", "FIELD", "POLE", "ATTRACT", "MOTOR", "GENERATOR", "INDUCE"]),
    (["earthquake", "epicenter"],
     ["FAULT", "EPICENTER", "MAGNITUDE", "SEISMIC", "PLATE", "TREMOR", "SHOCK", "ROCK"]),
    (["volcano", "eruption", "interior of the earth"],
     ["LAVA", "MAGMA", "CRATER", "ASH", "ERUPT", "CORE", "MANTLE", "CRUST"]),
    (["tide"],
     ["TIDE", "MOON", "OCEAN", "GRAVITY", "SUN", "WATER", "PULL", "RISE"]),
    (["typhoon", "weather"],
     ["TYPHOON", "STORM", "CLOUD", "RAIN", "WIND", "GAUGE", "HUMID", "WARNING"]),
    (["season", "rotation and revolution"],
     ["SEASON", "TILT", "ORBIT", "EQUINOX", "SUMMER", "WINTER", "SOLAR", "YEAR"]),
    (["eclipse", "phases of the moon"],
     ["ECLIPSE", "SHADOW", "CRESCENT", "GIBBOUS", "PHASE", "ALIGN", "LUNAR", "CYCLE"]),
    (["natural disasters"],
     ["HAZARD", "EVACUATE", "SUPPLY", "DRILL", "RESCUE", "WARNING", "KIT", "PLAN"]),
    (["climate"],
     ["CLIMATE", "GREENHOUSE", "CARBON", "EMISSION", "WARM", "ICE", "TEMPERATURE", "RISING"]),
    (["evolution", "biodiversity"],
     ["EVOLVE", "SPECIES", "FOSSIL", "ADAPT", "SELECT", "VARIETY", "ANCIENT", "TRAIT"]),
    (["biotech", "genetic", "biological"],
     ["GENE", "CROP", "TISSUE", "CLONE", "YEAST", "BREED", "GRAFT", "MICROBE"]),
    (["prevention of cardio"],
     ["EXERCISE", "SMOKE", "SALT", "FAT", "HEART", "DIET", "CHECK", "REST"]),
]

MATH = [
    (["integer", "number line", "absolute value", "real number", "properties of real"],
     ["INTEGER", "NEGATIVE", "POSITIVE", "ABSOLUTE", "NUMBER", "ORIGIN", "ZERO", "DISTANCE"]),
    (["fraction", "decimal", "rational number", "radical"],
     ["FRACTION", "DECIMAL", "RATIONAL", "NUMERATOR", "DENOMINATOR", "WHOLE", "ROOT", "SQUARE"]),
    (["polynomial", "factoring", "binomial", "monomial", "special products", "trinomial"],
     ["POLYNOMIAL", "FACTOR", "TERM", "BINOMIAL", "TRINOMIAL", "MONOMIAL", "SQUARE", "PRODUCT"]),
    (["linear equation", "linear inequalit", "slope", "intercept", "graphs of"],
     ["SLOPE", "INTERCEPT", "GRAPH", "LINEAR", "EQUATION", "INEQUALITY", "VARIABLE", "RISE"]),
    (["quadratic", "discriminant", "nature of roots", "completing the square"],
     ["ROOTS", "DISCRIMINANT", "PARABOLA", "VERTEX", "FORMULA", "CURVE", "SOLVE", "REAL"]),
    (["sequence", "series"],
     ["SEQUENCE", "SERIES", "PATTERN", "TERM", "RATIO", "COMMON", "SUM", "NEXT"]),
    (["sets", "union", "intersection", "complement", "venn", "subsets"],
     ["SET", "UNION", "INTERSECT", "COMPLEMENT", "MEMBER", "EMPTY", "VENN", "LIST"]),
    (["probability", "permutation", "combination"],
     ["PROBABLE", "EVENT", "OUTCOME", "SAMPLE", "CHANCE", "FAVORABLE", "ARRANGE", "CHOOSE"]),
    (["circle", "chord", "arc", "tangent", "inscribed"],
     ["CIRCLE", "CHORD", "ARC", "TANGENT", "RADIUS", "DIAMETER", "CENTER", "INSCRIBE"]),
    (["triangle", "pythagorean", "trigonometry", "sine", "cosine", "elevation", "depression"],
     ["TRIANGLE", "HYPOTENUSE", "ANGLE", "SINE", "COSINE", "TANGENT", "THEOREM", "LEG"]),
    (["quadrilateral", "parallelogram", "trapezoid", "kite"],
     ["QUADRILATERAL", "PARALLEL", "TRAPEZOID", "KITE", "SIDE", "VERTEX", "DIAGONAL", "BASE"]),
    (["similarity", "proportion"],
     ["RATIO", "PROPORTION", "SIMILAR", "CONGRUENT", "SCALE", "MATCH", "SHADOW", "DOUBLED"]),
    (["percent", "discount", "interest", "tax", "sales"],
     ["PERCENT", "DISCOUNT", "INTEREST", "PRINCIPAL", "RATE", "TAX", "CHANGE", "TOTAL"]),
    (["measures of position", "quartile", "decile", "percentile"],
     ["QUARTILE", "DECILE", "MEDIAN", "RANGE", "ORDER", "MEAN", "DATA", "POSITION"]),
    (["systems of linear", "substitution", "elimination", "graphing"],
     ["SYSTEM", "SUBSTITUTE", "ELIMINATE", "PAIR", "SOLUTION", "REPLACE", "CHECK", "LINE"]),
    (["perimeter", "area"],
     ["PERIMETER", "AREA", "UNITS", "SQUARE", "MEASURE", "LENGTH", "WIDTH", "COVER"]),
    (["word problems", "applications"],
     ["PROBLEM", "UNKNOWN", "SENTENCE", "QUANTITY", "MODEL", "REASON", "DOUBLE", "ANSWER"]),
    (["logical reasoning", "if-then"],
     ["LOGIC", "PREMISE", "CONVERSE", "STATEMENT", "PROOF", "TRUTH", "FALSE", "REASON"]),
    (["algebraic", "expression"],
     ["EXPRESSION", "VALUE", "SUBSTITUTE", "SIMPLIFY", "COEFFICIENT", "POWER", "TERM", "BRACKET"]),
    (["infinite geometric"],
     ["INFINITE", "LIMIT", "CONVERGE", "SUM", "RATIO", "ENDLESS", "SMALL", "SERIES"]),
    (["variation", "direct, inverse", "joint"],
     ["VARIATION", "DIRECT", "INVERSE", "JOINT", "COMBINED", "CONSTANT", "EQUATION", "RATIO"]),
]

ENGLISH = [
    (["voice", "passive"],
     ["VOICE", "ACTIVE", "PASSIVE", "SUBJECT", "VERB", "ACTION", "RECEIVER", "AGENT"]),
    (["theme", "tone"],
     ["THEME", "TONE", "MOOD", "MESSAGE", "AUTHOR", "ATTITUDE", "CENTRAL", "STYLE"]),
    (["poetry", "poets", "poetic", "free verse"],
     ["POEM", "VERSE", "STANZA", "RHYME", "METER", "POET", "LYRIC", "ODE"]),
    (["short story", "narrative", "story elements", "fiction"],
     ["FICTION", "PLOT", "CHARACTER", "SETTING", "CONFLICT", "NARRATOR", "CLIMAX", "ENDING"]),
    (["argument", "claim", "fallac", "evidence", "debate", "persuasive", "editorial"],
     ["CLAIM", "EVIDENCE", "REASON", "FALLACY", "DEBATE", "ARGUE", "PERSUADE", "COUNTER"]),
    (["bias", "propaganda", "media and information"],
     ["BIAS", "SLANT", "FACT", "OPINION", "SOURCE", "LOADED", "BANDWAGON", "LITERACY"]),
    (["bibliography", "citation", "citing", "plagiarism", "gathering"],
     ["CITATION", "SOURCE", "CREDIT", "REFERENCE", "AUTHOR", "TITLE", "PAGE", "LIST"]),
    (["cause and effect", "comparison", "contrast", "text structure", "informational"],
     ["CAUSE", "EFFECT", "COMPARE", "CONTRAST", "SIGNAL", "STRUCTURE", "OUTLINE", "BOTH"]),
    (["cohesive", "discourse"],
     ["CONNECTOR", "TRANSITION", "HOWEVER", "THEREFORE", "MARKER", "PHRASE", "DEVICE", "LINK"]),
    (["conditional"],
     ["CONDITION", "CLAUSE", "RESULT", "WOULD", "COULD", "MIGHT", "REAL", "LIKELY"]),
    (["obligation", "prohibition", "modal", "modality", "hedging"],
     ["OBLIGATION", "PROHIBIT", "PERMIT", "SHOULD", "MUST", "MAY", "MODAL", "SOFTEN"]),
    (["figurative", "simile", "metaphor", "personification"],
     ["SIMILE", "METAPHOR", "PERSONIFY", "IMAGE", "LIKENESS", "ABSTRACT", "COMPARE", "FIGURE"]),
    (["drama", "dramatic", "theater", "theatrical", "shakespeare", "one-act", "stage", "kabuki",
      "peking", "wayang", "conventions"],
     ["DRAMA", "STAGE", "ACTOR", "SCENE", "PROPS", "COSTUME", "TRAGEDY", "COMEDY"]),
    (["sound devices", "alliteration", "onomatopoeia"],
     ["ALLITERATION", "ONOMATOPOEIA", "RHYME", "SOUND", "REPEAT", "STRESS", "ASSONANCE", "ECHO"]),
    (["foreshadowing", "irony", "symbolism", "literary devices"],
     ["FORESHADOW", "IRONY", "SYMBOL", "TWIST", "HINT", "MEANING", "DEVICE", "CLUE"]),
    (["listening", "note-taking", "summarizing", "outlining"],
     ["LISTEN", "NOTE", "SUMMARY", "MAIN", "DETAIL", "RECORD", "POINT", "SHORT"]),
    (["research", "report", "paper"],
     ["RESEARCH", "TOPIC", "REPORT", "METHOD", "FINDING", "ABSTRACT", "PAPER", "SURVEY"]),
    (["tense", "verb", "participle", "gerund", "infinitive", "agreement", "pronoun", "verbals"],
     ["TENSE", "VERB", "PARTICIPLE", "GERUND", "INFINITIVE", "PAST", "PRESENT", "FUTURE"]),
    (["technical", "documentation", "scientific writing"],
     ["MANUAL", "PROCEDURE", "PRECISE", "TECHNICAL", "DOCUMENT", "PLAIN", "FORM", "PLAN"]),
    (["myth", "legend", "folktale", "epic", "heroic", "beowulf", "literature", "folktales"],
     ["MYTH", "LEGEND", "FOLKTALE", "EPIC", "HERO", "MORAL", "ANCIENT", "QUEST"]),
    (["context clues", "vocabulary"],
     ["CLUE", "MEANING", "WORD", "SENTENCE", "PREFIX", "SUFFIX", "ROOT", "GUESS"]),
    (["solidarity"],
     ["UNITY", "TOGETHER", "SOLID", "GROUP", "SUPPORT", "SHARED", "BOND", "TRUST"]),
    (["revising", "editing"],
     ["REVISE", "EDIT", "DRAFT", "CUT", "SMOOTH", "CHECK", "MARK", "CLEAR"]),
    (["multimodal", "presentation"],
     ["SLIDE", "VISUAL", "SPEAKER", "POSTURE", "CHART", "VOICE", "GESTURE", "PROPS"]),
    (["characterization", "dialogue", "delivery"],
     ["CHARACTER", "DIALOGUE", "VOICE", "GESTURE", "MANNER", "LINES", "STAGE", "TRUST"]),
    (["environmental literature", "nature"],
     ["NATURE", "FOREST", "CLIMATE", "GUARD", "LIFE", "EARTH", "GREEN", "RESPECT"]),
    (["direct and indirect", "speech"],
     ["SPEECH", "QUOTE", "REPORT", "PRONOUN", "TENSE", "PERSON", "VERB", "COMMAND"]),
    (["problem-solution", "problem and solution", "expository", "classification"],
     ["PROBLEM", "SOLUTION", "SOLVE", "ADVICE", "CAUSE", "STEPS", "ANSWER", "GROUP"]),
]

FILIPINO = [
    (["noli", "filibusterismo"],
     ["TAUHAN", "PANGYAYARI", "BUOD", "SIMBOLO", "MENSAHE", "KARAPATAN", "PERA", "PARAAN"]),
    (["dula", "pelikula", "zarzuela", "moro-moro", "pangradyo", "telebisyon"],
     ["DULA", "EKSENA", "GALAW", "DIALOGO", "TAGPUAN", "TAUHAN", "ENTABLADO", "SARIWANG"]),
    (["epiko", "biag", "ibalon", "handiong", "hinilawod", "maragtas", "darangen"],
     ["EPIKO", "BAYANI", "AWIT", "LABAN", "MARAGTAS", "LAMANG", "DAGAT", "SAKNA"]),
    (["alamat", "pambayan"],
     ["ALAMAT", "MITO", "LEYENDA", "HALIMAW", "BATAS", "GINTO", "BUNDOK", "DAIGDIG"]),
    (["sanaysay", "pagsulat"],
     ["SANAYSAY", "IDEYA", "PANANAW", "EBIDENSYA", "LAKIP", "WAKAS", "SULAT", "PANGUNGUSAP"]),
    (["pangungusap", "pang-abay", "pang-ukol", "gamit ng wika"],
     ["PANGUNGUSAP", "PANDIWANG", "PANGNGALAN", "TAYUTAY", "UKOL", "ABAY", "BANGGIT", "WASTO"]),
    (["bantas", "baybay"],
     ["BANTAS", "PUNTOS", "GUWIT", "KOMMA", "TULDOK", "BAYBAY", "WASTO", "MALAKI"]),
    (["korido", "pasyon", "senakulo", "tulang", "awit"],
     ["KORIDO", "PASYON", "SENAKULO", "AWIT", "SUKAT", "TUGMA", "TULA", "DAGDAG"]),
    (["etnograpiya", "kultura", "pamilya", "ninuno", "komunidad"],
     ["ETNOGRAPIA", "KULTURA", "NINUNO", "PAMILYA", "TRIBU", "PINAGMULAN", "ANGKAN", "LIPUNAN"]),
    (["pananaliksik", "sanggunian", "pagbanggit", "panukalang", "panukala"],
     ["PANANALIKSIK", "SANGGUNIAN", "SURIIN", "LAYUNIN", "DATOS", "RESULTA", "TALAAN", "SIPI"]),
    (["talumpati", "deklamasyon"],
     ["TALUMPATI", "PANITIKAN", "TINGGAL", "HINIG", "SALITA", "TULA", "DALITA", "TAYUTAY"]),
    (["nobela", "maikling kuwento", "kuwento"],
     ["NOBELA", "KUWENTO", "TAUHAN", "BANABA", "KABAHAN", "TAGPUAN", "PANAHON", "DALOY"]),
    (["malikhaing", "tula", "laihang", "pariralang"],
     ["MALIKHAIN", "TULA", "LAIHA", "TALUDTOD", "SUKAT", "TUGMA", "LARAWAN", "PANDAMA"]),
    (["opinyon", "katwiran", "paniniwala"],
     ["KATWIRAN", "PANINIWALA", "KATOTOHANAN", "BIAS", "EBIDENSYA", "KONTENIDO", "DAHILAN",
      "SALIK"]),
    (["pagtatanghal", "iskrip", "ensayong"],
     ["TANGHAL", "ISKRIP", "ENSAYO", "GALAW", "KASUYAN", "MUSIKA", "SAYAW", "ILAW"]),
    (["paglalarawan", "tagpuan", "karanasan"],
     ["TAGPUAN", "PANAHON", "LARAWAN", "PANDAMA", "DALOY", "KARANASAN", "SALAYSAY", "TINGIN"]),
    (["pagsusuri", "pag-unawa", "akda", "piling akda", "paghahambing"],
     ["SUSIIN", "AKDA", "LAIHA", "PAKSA", "SALIN", "RESULTA", "KATOTOHANAN", "PANANAW"]),
    (["pagpapahalaga", "papayag", "damdamin", "kaisipan"],
     ["DAMDAM", "KAISIPAN", "SALITA", "TINGGAL", "HINING", "LOOB", "PUSO", "ISIP"]),
    (["pakikinig", "pagsasalita", "panonood"],
     ["PAKIKINIG", "TINGIN", "DENOTASYON", "KONOTASYON", "INTONASYON", "BISA", "SALITA", "SUNOD"]),
]

MAPEH = [
    (["art movements", "baroque", "renaissance", "medieval", "neoclassical", "romantic art",
      "modern art", "impressionism", "abstract"],
     ["ARTIST", "CANVAS", "SCULPTURE", "MUSEUM", "PAINT", "SHADING", "BRONZE", "STYLE"]),
    (["arts and crafts", "textiles", "pottery", "woodcarving", "batik", "designs in"],
     ["LOOM", "CLAY", "CARVE", "THREAD", "DYE", "WEAVE", "KILN", "PATTERN"]),
    (["photography", "digital art", "media-based", "technology-based", "film", "animation"],
     ["LENS", "CAMERA", "PIXEL", "FILM", "FRAME", "EDIT", "SOUND", "SCREEN"]),
    (["architecture", "sculpture and architecture"],
     ["PILLAR", "ARCH", "DOME", "STEEL", "BRICK", "FACADE", "DESIGN", "SPAN"]),
    (["rondalla", "kundiman", "harana", "vocal", "brass band", "instrumental music"],
     ["KUNDIMAN", "HARANA", "RONDALLA", "BANDURIA", "CHOIR", "VOICE", "GUITAR", "PLUCK"]),
    (["gong", "instrument", "ensemble", "percussion"],
     ["GONG", "FLUTE", "DRUM", "STRINGS", "BRASS", "BEAT", "HOLLOW", "WOOD"]),
    (["music of", "opera", "ballet", "musical theater", "popular music", "OPM", "sacred music"],
     ["OPERA", "BALLET", "MELODY", "HARMONY", "TEMPO", "STAGE", "DANCE", "SONG"]),
    (["classical period", "romantic period", "20th century music", "jazz", "mozart", "bach",
      "beethoven", "chopin", "vivaldi", "handel"],
     ["COMPOSER", "SYMPHONY", "PIANO", "VIOLIN", "NOTES", "ORCHESTRA", "CONDUCT", "WALTZ"]),
    (["fitness", "exercise", "yoga", "zumba", "aerobics", "conditioning"],
     ["FITNESS", "STRETCH", "ENDURANCE", "FLEXIBLE", "POSTURE", "STAMINA", "PULSE", "REPEAT"]),
    (["athletics", "running", "jumping", "throwing", "javelin"],
     ["SPRINT", "RELAY", "JAVELIN", "TRACK", "START", "RACE", "VAULT", "THROW"]),
    (["basketball", "volleyball", "badminton", "football", "table tennis", "team sports",
      "dual sports", "officiating"],
     ["COURT", "NET", "REFEREE", "DRIBBLE", "SERVE", "SPIKE", "TEAM", "FOUL"]),
    (["folk dance", "tinikling", "itik", "rhythmic", "dances of asia"],
     ["DANCE", "BAMBOO", "RHYTHM", "POLE", "CLAP", "STEP", "COSTUME", "MUSIC"]),
    (["laro ng lahi", "indigenous games", "recreation", "outdoor", "camping", "hiking",
      "orienteeing", "orienteering", "healthy lifestyle"],
     ["SIPBA", "SIEVE", "FIELD", "TRAIL", "MAP", "COMPASS", "TENT", "GAME"]),
    (["first aid", "injury", "safety"],
     ["BANDAGE", "SPLINT", "RESCUE", "CLEAN", "GAUZE", "COTTON", "ALERT", "READY"]),
    (["nutrition", "diet", "food groups", "macronutrients", "malnutrition"],
     ["PROTEIN", "VITAMIN", "MINERAL", "CALORIE", "FIBER", "MEAT", "SUGAR", "WATER"]),
    (["hygiene", "personal health"],
     ["SOAP", "BRUSH", "TOWEL", "SHOWER", "NAILS", "CLEAN", "REST", "WASTE"]),
    (["drugs", "substance", "alcohol", "tobacco", "gateway"],
     ["TOBACCO", "ALCOHOL", "ADDICT", "RELAPSE", "REFUSE", "PRESSURE", "HARM", "LEGAL"]),
    (["communicable", "diseases", "disorders", "prevention and control"],
     ["GERM", "VACCINE", "FEVER", "SPREAD", "MOSQUITO", "HYGIENE", "DOSE", "CATCH"]),
    (["stress", "mental health", "holistic", "decision", "refusal"],
     ["STRESS", "CALM", "BREATH", "FEELING", "CHOICE", "SUPPORT", "BALANCE", "GOAL"]),
    (["environmental", "waste", "pollution", "community health"],
     ["GARBAGE", "RECYCLE", "POLLUTE", "SMOKE", "SEWAGE", "CLEAN", "DISEASE", "WATER"]),
    (["consumer health", "quackery", "fraud", "health services", "health plans", "career"],
     ["LABEL", "PRICE", "CLAIM", "SERVICE", "INSURANCE", "LICENSE", "PROOF", "JOB"]),
    (["arts of", "asian arts", "east asian", "southeast asian", "african", "latin american"],
     ["MASK", "SHRINE", "LACQUER", "SILK", "PAPER", "CLAY", "RITUAL", "CRAFT"]),
    (["festival", "celebration", "contemporary", "regions"],
     ["FESTIVAL", "PARADE", "COSTUME", "RITUAL", "REGION", "GALLERY", "MODERN", "PUBLIC"]),
]

SOCSCI = [
    (["scarcity", "needs", "wants", "pangangailangan"],
     ["KAKULANGAN", "KAILANGAN", "GUSTO", "PAGPILI", "HALAGA", "HIRAP", "YAMAN", "KAGUSTUHAN"]),
    (["supply", "demand", "presyo", "ekilibriyo", "price"],
     ["SUPPLY", "DEMAND", "PRESYO", "EKILIBRIYO", "TAAS", "BABA", "BALANSE", "BILI"]),
    (["inflation", "unemployment", "salapi", "bangko", "gastos"],
     ["INFLASION", "SALAPI", "BANGKO", "TRABAHO", "PERA", "IPON", "UTANG", "GASTOS"]),
    (["produksyon", "factor market", "salik ng produksyon", "lupa, paggawa", "kabisera"],
     ["LUPA", "PAGGAWA", "KABISERA", "NEGOSYANTE", "KITA", "HUSAY", "TUBO", "TRABAHO"]),
    (["kompetisyon", "monopolyo", " uri ng ekonomiya", "pamilihan"],
     ["MONOPOLYO", "KOMPETENSYA", "TINDAHAN", "PALENGKE", "SISTEMA", "PILI", "SALAPI", "BAYAD"]),
    (["gdp", "gnp", "pambansang ekonomiya", "paghahanda sa kaunlaran"],
     ["KABUUAN", "PERSENTAHE", "TUBO", "GASTOS", "YAMAN", "LUPA", "TRABAHO", "SALAPI"]),
    (["heograpiya", "anyong lupa", "anyong tubig", "lokasyon", "katangian", "yamang likas",
      "klima", "vegetation", "rehiyon", "timog at kanlurang asya"],
     ["KONTINENTE", "BUNDOK", "ILOG", "DAGAT", "LAWA", "BAYBAYIN", "KLIMA", "HANGIN"]),
    (["kasaysayan", "pinagmulan", "primarya", "sanggunian", "likas na katangian"],
     ["SANGGUNIAN", "EBIDENSYA", "BATAYAN", "TAON", "LAYUNIN", "PINAGMULAN", "TALAAN", "SULAT"]),
    (["kolonyalismo", "imperyalismo", "pananakop", "amerika sa pilipinas", "espanya", "reaksyon"],
     ["KOLONIA", "KASTILA", "AMERIKANO", "SAKOP", "BAYANI", "HARI", "BATAS", "SUNOD"]),
    (["rebolusyon", "mga pangyayari"],
     ["REBOLUSYON", "LABAN", "BAYANI", "LIHAM", "KALAYAAN", "SAMAHAN", "BATAS", "TINGGAL"]),
    (["karapatang pantao", "mamamayan", "karapatan at tungkulin", "pananagutan ng mamamayan"],
     ["KARAPATAN", "KATUNGKULIN", "MAMAMAYAN", "BATAS", "TINGGAL", "PILI", "TINIG", "BAYAN"]),
    (["pamahalaan", "batas at", "patakaran", "politika"],
     ["PAMAHALAAN", "BATAS", "TUNGKULIN", "PATAKARAN", "OPISINA", "PISO", "TINIG", "PILI"]),
    (["united nations", "asean", "internasyonal", "ugnayan", "globalisasyon", "bansang asyano",
      "panyapaten"],
     ["KATIPUNAN", "KASANGGUNIAN", "BANSA", "KASUNDUAN", "PANDAIGDIG", "SANDIGAN", "USISA",
      "PILIPINAS"]),
    (["pamanang pook", "heritage"],
     ["PAMANA", "BAHAY", "LUMANG", "TANAW", "MARKA", "TURISMO", "MATANDA", "BANTAYOG"]),
    (["lipunan", "istruktura sosyal"],
     ["LIPUNAN", "KLASE", "PAMILYA", "GRUPO", "NOON", "UGALI", "PINAGMULAN", "KARAPATAN"]),
    (["isyung pangkapaligiran", "isyung pangkabuhayan", "isyung pang-ekonomiya",
      "kontemporaryong isyu", "isyu"],
     ["ISYU", "SULIRAN", "KALIKASAN", "KABUHAYAN", "BAGYO", "GUTO", "UBUSAN", "TIBAY"]),
    (["kabihasnan", "sibilisasyon", "hapon", "koreano", "tsino", "indus", "silangang asya",
      "gitnang silangan"],
     ["KABIHASNAN", "LUNSOD", "SULAT", "MURAL", "BATAYAN", "SANGAY", "ILOG", "BUNDOK"]),
    (["opportunity cost", "production possibilities", "pag-iipon", "pamumuhunan", "badyet",
      "personal finance", "pagpapahalaga sa mga pamanang"],
     ["IPON", "GASTOS", "PAMUMUHUNAN", "BADYET", "HALAGA", "PAGPILI", "SAGUTAN",
      "PERA"]),
    (["komunidad", "pamayanan", "ang aking komunidad"],
     ["KOMUNIDAD", "PAMAYANAN", "BARANGAY", "KALYE", "PALENGKE", "SIMBAAN", "ESKWEELA", "TULAY"]),
    (["diwa ng kalayaan", "kamalay-kabansa", "nasyonalismo"],
     ["KALAYAAN", "BANSA", "BAYANI", "WATAWAT", "PUSO", "ISIP", "TINIG", "BATAS"]),
    (["west philippine sea", "teritoryal", "karagatan"],
     ["KARAGATAN", "TERRITORYO", "ISLA", "BAYBAYIN", "DALUYAN", "SAGUTAN", "BANSA", "BATAS"]),
    (["konteksto ng mundo", "pandaigdig", "globalisasyon"],
     ["PANDAIGDIG", "BANSA", "KONTINENTE", "PALITAN", "TRAPO", "KULTURA", "KASUNDUAN", "MUNDO"]),
]

TLE = [
    (["farm tools", "crop", "propagation", "agriculture"],
     ["SPADE", "SICKLE", "HOE", "SEED", "SOIL", "HARVEST", "PLOW", "WATER"]),
    (["bread", "pastry", "baking"],
     ["OVEN", "FLOUR", "YEAST", "SUGAR", "DOUGH", "KNEAD", "BREAD", "PASTRY"]),
    (["cookery", "kitchen", "sanitation", "appetizer", "salad", "sandwich", "dessert", "garnish",
      "mise"],
     ["KNIFE", "STOVE", "PANS", "RECIPE", "PLATE", "SPOON", "CLEAN", "CHEF"]),
    (["costing", "portion"],
     ["RECIPE", "COST", "PRICE", "SERVE", "MEASURE", "PROFIT", "BUDGET", "YIELD"]),
    (["electrical", "wiring", "circuits"],
     ["WIRE", "PLIERS", "SWITCH", "OUTLET", "FUSE", "CIRCUIT", "TAPE", "VOLTAGE"]),
    (["entrepreneurship", "business", "marketing", "bookkeeping", "accounting", "financial"],
     ["PRODUKTO", "PRESYO", "LAKI", "TINDAN", "LISTAHAN", "TALAAN", "KITA", "GASTOS"]),
    (["home economics", "caregiving", "household", "housekeeping"],
     ["BABY", "BROOM", "CLEAN", "PLAN", "LAUNDRY", "MOP", "LINEN", "SAFE"]),
    (["ict", "computer", "network", "cable", "topology", "hardware", "software", "troubleshoot",
      "servicing", "assembling"],
     ["MONITOR", "ROUTER", "CABLE", "DRIVER", "PIXEL", "MODEM", "SERVER", "BOOT"]),
    (["carpentry", "industrial arts", "mensuration"],
     ["SAW", "DRILL", "GAUGE", "LAYOUT", "HAMMER", "NAIL", "RULER", "ANGLE"]),
    (["occupational health", "workplace", "resume", "interview", "work readiness", "ethics"],
     ["RESUME", "EMPLOYER", "APPLY", "UNIFORM", "SAFETY", "POLITE", "PUNCTUAL", "TRAINING"]),
    (["safety"],
     ["HELMET", "GLOVE", "GOGGLE", "WARN", "BOOTS", "LADDER", "CAREFUL", "FIRST"]),
]

POOLS = {
    "Science": ["MATTER", "ENERGY", "FORCE", "CELL", "ROCK", "WATER", "AIR", "HEAT", "LIGHT",
                "GRAVITY", "ORBIT", "SPECIES", "GENE", "ACID", "SALT", "OXIDE", "PLANT", "ANIMAL",
                "CLIMATE", "VOLCANO", "EARTH", "MOON", "SPACE", "SPEED", "MASS", "VOLUME",
                "DENSITY", "PRESSURE", "MAGNET", "CIRCUIT"],
    "Mathematics": ["ANGLE", "ARC", "AREA", "AXIS", "BASE", "CHORD", "CONE", "CUBE", "DECIMAL",
                    "EDGE", "EXPONENT", "FACTOR", "FORMULA", "FUNCTION", "GRAPH", "INTEGER",
                    "LINE", "MATRIX", "MEDIAN", "METER", "NULL", "PLANE", "POWER", "PRIME",
                    "RADIUS", "RATIO", "ROOT", "SERIES", "SLOPE", "VERTEX"],
    "English": ["ADJECTIVE", "ADVERB", "ALLITERATION", "CLAUSE", "CONFLICT", "CONTEXT", "DIALOGUE",
                "EVIDENCE", "FIGURATIVE", "GENRE", "IMAGERY", "IRONY", "METAPHOR", "MOOD",
                "NARRATOR", "ONOMATOPOEIA", "OUTLINE", "PLOT", "POINT", "PURPOSE", "RHYME",
                "SIMILE", "STANZA", "STRUCTURE", "SUBJECT", "SUMMARY", "SYMBOL", "TENSE", "THEME",
                "TONE"],
    "Filipino": ["PANITIKAN", "KARUNUGAN", "SALIWIKAIN", "BUGTONG", "TAYUTAY", "PANDIWANG",
                 "PANGNGALAN", "KABUUAN", "SUSIIN", "LAIHA", "TUGMA", "SUKAT", "ALAMAT", "EPIKO",
                 "BAYANI", "TAGPUAN", "TAUHAN", "AKDA", "SALIN", "KARANASAN", "WASTO", "BAYBAY",
                 "BANGGIT", "SIPI", "SALAYSAY", "DAMDAM", "ISIP", "TINGGAL", "BATAYAN", "SANGAY"],
    "MAPEH": ["RHYTHM", "MELODY", "HARMONY", "TEMPO", "COSTUME", "STAGE", "DANCE", "SCULPTURE",
              "PERSPECTIVE", "MOOD", "COLOR", "SKETCH", "ENSEMBLE", "FITNESS", "ENDURANCE",
              "FLEXIBILITY", "COOPERATION", "STRATEGY", "REFEREE", "SAFETY", "HYGIENE", "NUTRIENT",
              "VACCINE", "POSTURE", "BALANCE", "AGILITY", "WELLNESS", "ART", "MUSIC", "CANVAS"],
    "SocSci": ["KALIKASAN", "KABUHAYAN", "PAMAHALAAN", "KASAYSAYAN", "KULTURA", "LIPUNAN",
               "PULITIKA", "EKONOMIYA", "HEOGRAPIYA", "KARAPATAN", "KALAYAAN", "BAYANIHAN",
               "SANDIGAN", "KATUTUBO", "KATOTOHANAN", "PANANAGUTAN", "KALAGAYAN", "LUPAIN",
               "SAGUTAN", "KAUGALIAN", "KALUSUGAN", "KALIHAN", "SULIRAN", "PAMANA",
               "BANSA", "BATAS", "TINIG", "IPON", "YAMAN"],
    "TLE": ["TOOL", "SAFETY", "REPAIR", "MEASURE", "RECIPE", "PLAN", "COST", "PROFIT", "SERVICE",
            "PRODUCT", "CUSTOMER", "EQUIPMENT", "MAINTENANCE", "WIRING", "CIRCUIT", "HARVEST",
            "SEEDLING", "SANITATION", "CLEANLINESS", "TEAMWORK", "PUNCTUAL", "RESPECT", "APRON",
            "OVEN", "MIXER", "DRILL", "CABLE", "ROUTER", "SERVE", "VALUE"],
}

SUBJECT_RULES = {"Science": SCIENCE, "Mathematics": MATH, "English": ENGLISH,
                 "Filipino": FILIPINO, "MAPEH": MAPEH, "SocSci": SOCSCI, "TLE": TLE}

# Offered by the quiz form but absent from matatag_spec.json, so the game needs
# their names from here or they would only ever get the general pool.
EXTRA_TOPICS = {"Science": ["Biotechnology", "Climate"]}


def build():
    with open(SPEC, encoding="utf-8") as f:
        spec = json.load(f)

    names = {}
    for subjects in spec.values():
        for subject, quarters in subjects.items():
            for topics in quarters.values():
                names.setdefault(subject, set()).update(topics)

    for subject, extra in EXTRA_TOPICS.items():
        names.setdefault(subject, set()).update(extra)

    bank, missing = {}, []
    for subject, topic_names in names.items():
        rules = SUBJECT_RULES.get(subject, [])
        topics = {}
        for name in sorted(topic_names):
            low = name.lower()
            picked = []
            for keywords, words in rules:
                if any(key in low for key in keywords):
                    picked += words
            unique, seen = [], set()
            for w in picked:
                if w not in seen and WORD_OK.match(w):
                    seen.add(w)
                    unique.append(w)
            if len(unique) >= MIN_WORDS:
                topics[name] = unique[:MAX_WORDS]
            else:
                missing.append((subject, name, len(unique)))
        pool = [w for w in POOLS.get(subject, []) if WORD_OK.match(w)]
        bank[subject] = {"general": pool, "topics": topics}

    all_names = {n for s in names.values() for n in s}
    print("topics with their own words: %d of %d unique names"
          % (sum(len(b["topics"]) for b in bank.values()), len(all_names)))
    print("falling back to the subject pool:", dict(Counter(s for s, n, c in missing)))
    for subject, name, count in missing[:12]:
        print("   ", subject, "|", name, "|", count, "matched")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
