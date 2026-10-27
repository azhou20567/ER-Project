import random
import unittest
from unittest.mock import patch

import salabim as sim

import config as cfg
import simulation.environment as environment
from simulation.arrival_generator import ArrivalGenerator
from simulation.esi import ESI
from simulation.patient import Patient


class ResourceHolder(sim.Component):
    def setup(self, held_resource, hold_duration):
        self.held_resource = held_resource
        self.hold_duration = hold_duration

    def process(self):
        yield self.request(self.held_resource)
        yield self.hold(self.hold_duration)
        self.release(self.held_resource)


class PatientWorkflowTests(unittest.TestCase):
    def setUp(self):
        previous_yieldless = sim.yieldless()
        sim.yieldless(False)
        self.addCleanup(sim.yieldless, previous_yieldless)
        animate = patch.object(cfg, "ANIMATE", False)
        animate.start()
        self.addCleanup(animate.stop)

        with patch.multiple(
            environment, NUM_TRIAGE_NURSES=1, NUM_PROVIDERS=1, NUM_BEDS=1
        ):
            self.env, self.triage, self.providers, self.beds = environment.create_environment()
        self.metrics = ESI()
        self.samples = []
        sampling = patch(
            "simulation.patient.random.expovariate", side_effect=self.sample_duration
        )
        sampling.start()
        self.addCleanup(sampling.stop)
        # Stage durations come from Patient._sample(stage, esi); give each stage a fixed length.
        stage_sampling = patch.object(Patient, "_sample", side_effect=self.sample_stage)
        stage_sampling.start()
        self.addCleanup(stage_sampling.stop)
        # By default no patient needs treatment (0.99 is above every ESI's probability).
        self.treatment_roll = 0.99
        treatment = patch(
            "simulation.patient.random.random", side_effect=lambda: self.treatment_roll
        )
        treatment.start()
        self.addCleanup(treatment.stop)
        self.animation_queues = [
            self.env.q_wait_triage,
            self.env.q_in_triage,
            self.env.q_wait_bed,
            self.env.q_wait_provider,
            self.env.q_in_treatment,
            self.env.q_wait_testing,
            self.env.q_in_testing,
            self.env.q_awaiting_test,
            self.env.q_wait_diagnosis,
            self.env.q_in_diagnosis,
            self.env.q_wait_treatment,
            self.env.q_in_treatment_stage,
            self.env.q_wait_discharge,
            self.env.q_in_discharge,
        ]

    def sample_duration(self, rate):
        # Only triage still samples expovariate directly.
        self.samples.append((self.env.now(), "triage"))
        durations = {
            1.0 / cfg.MEAN_TRIAGE_TIME: 1.0,
        }
        return durations[rate]

    def sample_stage(self, stage, esi):
        self.samples.append((self.env.now(), stage))
        # Testing + diagnosis + discharge = 4, the old "additional care" length.
        durations = {"exam": 3.0, "test": 2.0, "diagnosis": 1.0, "treatment": 2.0, "discharge": 1.0}
        return durations[stage]

    def patient(self, esi=3, service_time=3.0, **kwargs):
        return Patient(
            triage=self.triage,
            providers=self.providers,
            beds=self.beds,
            metrics=self.metrics,
            esi=esi,
            service_time=service_time,
            env=self.env,
            **kwargs,
        )

    def block(self, resource, duration):
        return ResourceHolder(
            held_resource=resource, hold_duration=duration, env=self.env
        )

    def assert_claims(self, patient, *, triage=False, provider=False, bed=False):
        self.assertEqual(patient in self.triage.claimers(), triage)
        self.assertEqual(patient in self.providers.claimers(), provider)
        self.assertEqual(patient in self.beds.claimers(), bed)
        # Testing equipment is only ever claimed by the linked Test, never the patient.
        self.assertNotIn(patient, self.env.testing_equipment.claimers())

    def assert_departed(self, *patients):
        for patient in patients:
            self.assertIsNone(patient._anim_queue)
            self.assertEqual(patient.queues(), set())
        for resource in (self.triage, self.providers, self.beds, self.env.testing_equipment):
            self.assertEqual(resource.claimed_quantity(), 0)
            self.assertEqual(len(resource.requesters()), 0)
            self.assertEqual(len(resource.claimers()), 0)
        for queue in self.animation_queues:
            self.assertEqual(len(queue), 0)

    def test_bed_retention_release_and_metric_timing(self):
        self.block(self.beds, 5)
        self.block(self.providers, 11)
        patient = self.patient()

        # Triage ends at 1; the bed remains unavailable until 5.
        self.env.run(till=2)
        self.assert_claims(patient)
        self.assertIn(patient, self.beds.requesters())
        self.assertNotIn(patient, self.providers.requesters())
        self.assertIn(patient, self.env.q_wait_bed)
        self.assertEqual(self.metrics.wait_times[3], [])
        self.assertEqual(self.metrics.lengths_of_visit[3], [])

        # The patient holds the bed while the provider is busy until 11.
        self.env.run(till=5.5)
        self.assert_claims(patient, bed=True)
        self.assertIn(patient, self.providers.requesters())
        self.assertIn(patient, self.env.q_wait_provider)
        self.assertEqual(self.metrics.wait_times[3], [])

        self.env.run(till=11.5)
        self.assert_claims(patient, provider=True, bed=True)
        self.assertIn(patient, self.env.q_in_treatment)
        self.assertEqual(self.metrics.wait_times[3], [11.0])
        self.assertEqual(self.metrics.lengths_of_visit[3], [])

        # Exam ends at 14; testing 14-16, diagnosis 16-17, discharge 17-18, all with the bed held.
        self.env.run(till=14.5)
        self.assert_claims(patient, bed=True)
        self.assertEqual(len(self.env.q_in_testing), 1)
        self.assertEqual(self.providers.claimed_quantity(), 0)
        self.assertEqual(self.metrics.lengths_of_visit[3], [])
        self.env.run(till=16.5)
        self.assert_claims(patient, provider=True, bed=True)
        self.assertIn(patient, self.env.q_in_diagnosis)
        self.env.run(till=17.5)
        self.assert_claims(patient, triage=True, bed=True)
        self.assertIn(patient, self.env.q_in_discharge)
        self.env.run(till=17.9)
        self.assert_claims(patient, triage=True, bed=True)
        self.assertEqual(self.metrics.lengths_of_visit[3], [])

        self.env.run(till=18.1)
        self.assertEqual(self.metrics.wait_times[3], [11.0])
        self.assertEqual(self.metrics.lengths_of_visit[3], [18.0])
        self.assert_departed(patient)

    def test_later_higher_acuity_bed_request_wins(self):
        occupant = self.block(self.beds, 8)
        earlier = self.patient(esi=5, service_time=2)
        later = self.patient(esi=1, service_time=2, at=1)

        self.env.run(till=3)
        self.assertIn(earlier, self.beds.requesters())
        self.assertIn(later, self.beds.requesters())
        self.assertIn(occupant, self.beds.claimers())
        self.assert_claims(earlier)
        self.assert_claims(later)

        self.env.run(till=8.1)
        self.assert_claims(later, provider=True, bed=True)
        self.assert_claims(earlier)
        self.assertIn(earlier, self.beds.requesters())

        self.env.run(till=21)
        self.assertEqual(self.metrics.wait_times[1], [7.0])
        self.assertEqual(self.metrics.wait_times[5], [14.0])
        self.assert_departed(earlier, later)

    def test_equal_acuity_bed_requests_remain_fifo(self):
        self.block(self.beds, 8)
        earlier = self.patient(esi=2, service_time=2)
        later = self.patient(esi=2, service_time=2, at=1)

        self.env.run(till=3)
        self.assertIn(earlier, self.beds.requesters())
        self.assertIn(later, self.beds.requesters())
        self.env.run(till=8.1)
        self.assert_claims(earlier, provider=True, bed=True)
        self.assert_claims(later)
        self.env.run(till=14.1)
        self.assert_claims(later, provider=True, bed=True)

        self.env.run(till=21)
        self.assertEqual(self.metrics.wait_times[2], [8.0, 13.0])
        self.assert_departed(earlier, later)

    def test_provider_acuity_priority_is_preserved(self):
        self.beds.set_capacity(2)
        self.block(self.providers, 10)
        earlier = self.patient(esi=5, service_time=2)
        later = self.patient(esi=1, service_time=2, at=1)

        self.env.run(till=3)
        self.assert_claims(earlier, bed=True)
        self.assert_claims(later, bed=True)
        self.assertIn(earlier, self.providers.requesters())
        self.assertIn(later, self.providers.requesters())
        self.env.run(till=10.1)
        self.assert_claims(later, provider=True, bed=True)
        self.assert_claims(earlier, bed=True)
        self.env.run(till=12.1)
        self.assert_claims(earlier, provider=True, bed=True)
        self.assert_claims(later, bed=True)

        self.env.run(till=19)
        self.assertEqual(self.metrics.wait_times[1], [9.0])
        self.assertEqual(self.metrics.wait_times[5], [12.0])
        self.assert_departed(earlier, later)

    def test_existing_lower_acuity_bed_occupant_is_not_preempted(self):
        occupant = self.patient(esi=5, service_time=5)
        waiting = self.patient(esi=1, service_time=2, at=2)

        self.env.run(till=4)
        self.assert_claims(occupant, provider=True, bed=True)
        self.assert_claims(waiting)
        self.assertIn(waiting, self.beds.requesters())
        self.env.run(till=7)
        self.assert_claims(occupant, bed=True)
        self.assert_claims(waiting)
        self.env.run(till=10.1)
        self.assert_claims(waiting, provider=True, bed=True)

        self.env.run(till=17)
        self.assertEqual(self.metrics.wait_times[1], [8.0])
        self.assert_departed(occupant, waiting)

    def test_acuity_and_duration_sampling_stay_at_existing_logical_points(self):
        self.block(self.beds, 5)
        self.block(self.providers, 11)
        # These observed time distributions must not supply process durations.
        data = ([2], [1.0], {}, {2: [999.0]}, {2: [9999.0]})
        with patch("simulation.patient.random.choices", return_value=[2]) as acuity:
            patient = self.patient(esi=None, service_time=None, data=data)
            self.assertEqual(patient.esi, 2)
            acuity.assert_called_once_with([2], weights=[1.0], k=1)
        self.assertIsNone(patient.service_time)
        self.assertEqual(self.samples, [])

        self.env.run(till=0.5)
        self.assertIsNone(patient.service_time)
        self.env.run(till=2)
        self.assertEqual(patient.service_time, 3.0)
        self.assert_claims(patient)
        self.assertEqual(self.samples, [(0.0, "triage"), (1.0, "exam")])
        self.env.run(till=13.9)
        self.assertEqual(len(self.samples), 2)
        self.env.run(till=14.1)
        self.assert_claims(patient, bed=True)
        self.assertEqual(self.samples[-1], (14.0, "test"))

        self.env.run(till=18.1)
        self.assertEqual(
            self.samples,
            [(0.0, "triage"), (1.0, "exam"), (14.0, "test"), (16.0, "diagnosis"), (17.0, "discharge")],
        )
        self.assertEqual(self.metrics.wait_times[2], [11.0])
        self.assertEqual(self.metrics.lengths_of_visit[2], [18.0])
        self.assert_departed(patient)

    def test_linked_test_holds_equipment_while_patient_keeps_bed(self):
        patient = self.patient()

        # Triage 0-1, exam 1-4, then the Test runs 4-6.
        self.env.run(till=5)
        self.assert_claims(patient, bed=True)
        (test,) = self.env.testing_equipment.claimers()
        self.assertIs(test.patient, patient)
        self.assertIn(test, self.env.q_in_testing)
        # The patient stays visible in its bed while the test runs.
        self.assertIn(patient, self.env.q_awaiting_test)
        self.assertFalse(patient.testing_done())

        self.env.run(till=6.5)
        self.assertTrue(patient.testing_done())
        self.assertEqual(self.env.testing_equipment.claimed_quantity(), 0)
        self.assert_claims(patient, provider=True, bed=True)

        self.env.run(till=9)
        self.assertEqual(self.metrics.lengths_of_visit[3], [8.0])
        self.assert_departed(patient)

    def test_diagnosis_waits_for_testing_done(self):
        self.env.testing_equipment.set_capacity(1)
        self.block(self.env.testing_equipment, 10)
        patient = self.patient()

        # The exam ends at 4 but equipment is busy until 10; the provider is idle meanwhile.
        self.env.run(till=11)
        self.assert_claims(patient, bed=True)
        self.assertNotIn(patient, self.providers.requesters())
        self.assertEqual(self.providers.claimed_quantity(), 0)
        self.assertFalse(patient.testing_done())

        self.env.run(till=12.5)
        self.assert_claims(patient, provider=True, bed=True)
        self.assertEqual(self.metrics.stage_waits["testing"][3], [6.0])

        self.env.run(till=15)
        self.assertEqual(self.metrics.lengths_of_visit[3], [14.0])
        self.assert_departed(patient)

    def test_treatment_depends_on_esi_probability(self):
        # 0.5 is below ESI 2's treatment probability (0.8) and above ESI 4's (0.25).
        self.treatment_roll = 0.5
        self.beds.set_capacity(2)
        treated = self.patient(esi=2)
        untreated = self.patient(esi=4, at=20)

        # Treated: triage 0-1, exam 1-4, test 4-6, diagnosis 6-7, treatment 7-9, discharge 9-10.
        self.env.run(till=8)
        self.assert_claims(treated, triage=True, bed=True)
        self.assertIn(treated, self.env.q_in_treatment_stage)

        self.env.run(till=40)
        self.assertEqual(self.metrics.lengths_of_visit[2], [10.0])
        self.assertEqual(self.metrics.lengths_of_visit[4], [8.0])
        self.assertEqual(self.metrics.stage_waits["treatment"][2], [0.0])
        self.assertEqual(self.metrics.stage_waits["treatment"][4], [])
        self.assert_departed(treated, untreated)

    def test_treatment_skipped_when_not_needed(self):
        patient = self.patient(esi=1)

        self.env.run(till=10)
        self.assertNotIn("treatment", self.metrics.stage_waits)
        self.assertEqual(self.metrics.lengths_of_visit[1], [8.0])
        self.assert_departed(patient)

    def test_shared_nurse_serves_discharge_before_same_acuity_triage(self):
        # Patient in bed reaches discharge at 7; a new arrival asks for triage first, at 6.5.
        in_bed = self.patient()
        ResourceHolder(held_resource=self.triage, hold_duration=4, at=6, env=self.env)
        arriving = self.patient(at=6.5)

        self.env.run(till=9)
        self.assertIn(in_bed, self.triage.requesters())
        self.assertIn(arriving, self.triage.requesters())

        # The nurse frees up at 10 and goes to the discharge, despite the earlier triage request.
        self.env.run(till=10.1)
        self.assert_claims(in_bed, triage=True, bed=True)
        self.assertIn(arriving, self.triage.requesters())

        self.env.run(till=25)
        # Arriving: triage 11-12, bed at 12 (freed at 11), then exam/test/diagnosis/discharge until 19.
        self.assertEqual(self.metrics.lengths_of_visit[3], [11.0, 12.5])
        self.assert_departed(in_bed, arriving)


class AnimationNeutralityTests(unittest.TestCase):
    def setUp(self):
        previous_yieldless = sim.yieldless()
        sim.yieldless(False)
        self.addCleanup(sim.yieldless, previous_yieldless)

    def run_simulation(self, animate):
        # Same seed and synthetic arrivals; only the ANIMATE flag differs (no window is opened).
        with patch.object(cfg, "ANIMATE", animate):
            random.seed(1)
            sim.random_seed(1)
            env, triage, providers, beds = environment.create_environment()
            metrics = ESI()
            ArrivalGenerator(triage=triage, providers=providers, beds=beds, metrics=metrics, env=env)
            env.run(till=2000)
        return metrics

    def test_animate_flag_does_not_change_results(self):
        animated = self.run_simulation(animate=True)
        plain = self.run_simulation(animate=False)
        self.assertEqual(animated.wait_times, plain.wait_times)
        self.assertEqual(animated.lengths_of_visit, plain.lengths_of_visit)
        self.assertEqual(animated.stage_waits, plain.stage_waits)


if __name__ == "__main__":
    unittest.main()
