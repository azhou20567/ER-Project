NUM_TRIAGE_NURSES = 2
NUM_PROVIDERS = 3
NUM_BEDS = 10

# These are in minutes and can be adjusted at any time if no dataset is provided.
MEAN_ARRIVAL_TIME = 9
MEAN_TRIAGE_TIME = 5
MEAN_SERVICE_TIME = 25
# Mean post-provider additional-care duration; bed occupancy also includes provider waiting and care.
MEAN_BED_TIME = 60

# Most patients are ESI 3/4, barely any are ESI 1.
ESI_WEIGHTS_SYNTHETIC = [3, 12, 40, 35, 10]  # ESI 1..5
SIMULATION_TIME = 5000

DATASET_PATH = "nhamcs/nhamcs2022.parquet"

# Turn this to True for animation, otherwise keep it False.
ANIMATE = True

# Makes animation speed up.
ANIMATION_SPEED = 5