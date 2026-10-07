import salabim as sim
from config import NUM_TRIAGE_NURSES, NUM_PROVIDERS, NUM_BEDS, NUM_TESTING_STATIONS

def create_environment():
    env = sim.Environment(trace = False) # just creating a new simulated environment, trace -> False to avoid printing every event to console

    # Queues used for animation/visualization. Patients will enter/leave these during their journey.
    env.q_wait_triage = sim.Queue("q_wait_triage")
    env.q_in_triage = sim.Queue("q_in_triage")
    env.q_wait_provider = sim.Queue("q_wait_provider")
    env.q_in_treatment = sim.Queue("q_in_treatment")
    env.q_wait_bed = sim.Queue("q_wait_bed")
    env.q_in_bed = sim.Queue("q_in_bed")
    env.q_wait_testing = sim.Queue("q_wait_testing")
    env.q_in_testing = sim.Queue("q_in_testing")
    env.q_wait_diagnosis = sim.Queue("q_wait_diagnosis")
    env.q_in_diagnosis = sim.Queue("q_in_diagnosis")
    env.q_wait_treatment = sim.Queue("q_wait_treatment")
    env.q_in_treatment_stage = sim.Queue("q_in_treatment_stage")
    env.q_wait_discharge = sim.Queue("q_wait_discharge")
    env.q_in_discharge = sim.Queue("q_in_discharge")

    # Nurse pool shared by triage, treatment, and discharge (returned as `triage` for existing callers).
    triage = sim.Resource("nurses", capacity = NUM_TRIAGE_NURSES)
    providers = sim.Resource("providers", capacity = NUM_PROVIDERS) # creating resource for providers, capacity based on config.py
    beds = sim.Resource("beds", capacity = NUM_BEDS) # creating resource for beds, capacity based on config.py
    # Used by Test components; attached to env so the return signature stays unchanged.
    env.testing_equipment = sim.Resource("testing_equipment", capacity = NUM_TESTING_STATIONS)

    return env, triage, providers, beds # returning the environment and resources to be used in the simulation
