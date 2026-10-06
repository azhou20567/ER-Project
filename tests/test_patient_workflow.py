import unittest
from unittest.mock import patch

import salabim as sim

import config as cfg
import simulation.environment as environment
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
        self.animation_queues = [
            self.env.q_wait_triage,
            self.env.q_in_triage,
            self.env.q_wait_bed,
            self.env.q_wait_provider,
            self.env.q_in_treatment,
            self.env.q_in_bed,
        ]

    def sample_duration(self, rate):
        self.samples.append((self.env.now(), rate))
        durations = {
            1.0 / cfg.MEAN_TRIAGE_TIME: 1.0,
            1.0 / cfg.MEAN_SERVICE_TIME: 3.0,
            1.0 / cfg.MEAN_BED_TIME: 4.0,
        }
        return durations[rate]

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

    def assert_departed(self, *patients):
        for patient in patients:
            self.assertIsNone(patient._anim_queue)
            self.assertEqual(patient.queues(), set())
        for resource in (self.triage, self.providers, self.beds):
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

        # Provider care ends at 14; additional care occupies the bed until 18.
        self.env.run(till=14.5)
        self.assert_claims(patient, bed=True)
        self.assertIn(patient, self.env.q_in_bed)
        self.assertEqual(self.providers.claimed_quantity(), 0)
        self.assertEqual(self.metrics.lengths_of_visit[3], [])
        self.env.run(till=17.9)
        self.assert_claims(patient, bed=True)
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
        self.assertEqual(
            self.samples,
            [(0.0, 1.0 / cfg.MEAN_TRIAGE_TIME), (1.0, 1.0 / cfg.MEAN_SERVICE_TIME)],
        )
        self.env.run(till=13.9)
        self.assertEqual(len(self.samples), 2)
        self.env.run(till=14.1)
        self.assert_claims(patient, bed=True)
        self.assertEqual(self.samples[-1], (14.0, 1.0 / cfg.MEAN_BED_TIME))

        self.env.run(till=18.1)
        self.assertEqual(self.metrics.wait_times[2], [11.0])
        self.assertEqual(self.metrics.lengths_of_visit[2], [18.0])
        self.assert_departed(patient)


if __name__ == "__main__":
    unittest.main()
