NUM_TRIAGE_NURSES = 2
NUM_PROVIDERS = 3
NUM_BEDS = 10

# These are in minutes and can be adjusted at any time if no dataset is provided.
MEAN_ARRIVAL_TIME = 9
MEAN_TRIAGE_TIME = 5

# Expanded flow (placeholder values, keyed by ESI 1..5; sicker patients take longer).
NUM_TESTING_STATIONS = 4
MEAN_EXAM_TIME_BY_ESI = {1: 40, 2: 35, 3: 25, 4: 20, 5: 15}
MEAN_TEST_TIME_BY_ESI = {1: 60, 2: 50, 3: 40, 4: 25, 5: 15}
MEAN_DIAGNOSIS_TIME_BY_ESI = {1: 20, 2: 18, 3: 15, 4: 10, 5: 8}
TREATMENT_PROBABILITY_BY_ESI = {1: 0.95, 2: 0.8, 3: 0.5, 4: 0.25, 5: 0.1}
MEAN_TREATMENT_TIME_BY_ESI = {1: 45, 2: 35, 3: 25, 4: 15, 5: 10}
MEAN_DISCHARGE_TIME_BY_ESI = {1: 20, 2: 15, 3: 12, 4: 10, 5: 8}

# Shared nurses/providers serve the lowest value first: ESI * 10 + stage weight.
# Later stages get a smaller weight so patients already holding a bed can finish and free it.
STAGE_PRIORITY_WEIGHT = {"triage": 2, "exam": 1, "diagnosis": 0, "treatment": 1, "discharge": 0}

# Most patients are ESI 3/4, barely any are ESI 1.
ESI_WEIGHTS_SYNTHETIC = [3, 12, 40, 35, 10]  # ESI 1..5
SIMULATION_TIME = 5000

DATASET_PATH = "nhamcs/nhamcs2022.parquet"

# Turn this to True for animation, otherwise keep it False.
ANIMATE = True

# Makes animation speed up.
ANIMATION_SPEED = 5