import random
import salabim as sim
import config as cfg
from simulation.test import Test
from simulation.esi import ESI_COLORS


class Patient(sim.Component):
    def setup(self, triage, providers, beds, metrics, esi=None, service_time=None, data=None):
        self.triage = triage
        self.providers = providers
        self.beds = beds
        self.metrics = metrics

        # If esi/service_time are provided explicitly, use them.
        # Otherwise, assign ESI now and determine service time after triage.
        self._esi_provided = esi is not None
        self.esi = esi
        self.service_time = service_time
        self.data = data
        self._assign_esi()

    def _safe_move(self, new_queue):
        # Safely transition this patient to a new animation queue.
        old_queue = self._anim_queue
        if new_queue is old_queue:
            return

        # Attempt to enter the new queue first.
        entered_new = False
        if new_queue is None:
            entered_new = True
        else:
            if new_queue in self._qmembers:
                entered_new = True
            else:
                try:
                    self.enter(new_queue)
                except Exception:
                    pass
                entered_new = new_queue in self._qmembers

        # Only once we've entered the new queue, leave the old one.
        if entered_new and old_queue is not None and old_queue in self._qmembers:
            try:
                self.leave(old_queue)
            except Exception:
                pass

        if entered_new:
            self._anim_queue = new_queue

    def _assign_esi(self):
        """Assign acuity at patient creation, preserving an explicit ESI."""
        if self.esi is None:
            if self.data is not None:
                esi_levels, esi_weights, _hourly_arrival_rates, _wait_times_by_esi, _lengths_of_visit_by_esi = self.data
                self.esi = random.choices(esi_levels, weights=esi_weights, k=1)[0]
            else:
                # Fallback
                self.esi = random.choices([1, 2, 3, 4, 5], weights=cfg.ESI_WEIGHTS_SYNTHETIC, k=1)[0]

    def _assign_service_time(self):
        """Determine examination time after triage, preserving an explicit duration."""
        if self.service_time is None:
            if self._esi_provided:
                # Preserve the existing fallback for an explicitly supplied ESI.
                self.service_time = cfg.MEAN_EXAM_TIME_BY_ESI[self.esi]
            else:
                # NHAMCS has no direct provider service time; use the synthetic distribution.
                self.service_time = self._sample("exam", self.esi)

    def _sample(self, stage, esi):
        """Sample a stage duration from that stage's per-ESI mean (config.py)."""
        means = {
            "exam": cfg.MEAN_EXAM_TIME_BY_ESI,
            "test": cfg.MEAN_TEST_TIME_BY_ESI,
            "diagnosis": cfg.MEAN_DIAGNOSIS_TIME_BY_ESI,
            "treatment": cfg.MEAN_TREATMENT_TIME_BY_ESI,
            "discharge": cfg.MEAN_DISCHARGE_TIME_BY_ESI,
        }
        return random.expovariate(1.0 / means[stage][esi])

    def _priority(self, stage):
        """Request priority for shared staff (lower value is served first)."""
        return self.esi * 10 + cfg.STAGE_PRIORITY_WEIGHT[stage]

    def animation_objects(self, *args, id=None, **kwargs):
        # Salabim passes `screen_coordinates` and the queue animation's `id` from AnimateQueue.
        screen_coordinates = kwargs.get("screen_coordinates", True)
        # Waiting patients are drawn as outlines; patients being served are solid.
        waiting = id == "waiting"

        def esi_color(_t=None):
            return ESI_COLORS.get(getattr(self, "esi", None), "#d0d0d0")

        def fill(_t=None):
            return "#000000" if waiting else esi_color()

        def label(_t=None):
            if getattr(self, "esi", None) is None:
                return "?"
            return str(self.esi)

        rect_kwargs = dict(
            spec=(-13, -8, 13, 8),
            fillcolor=fill,
            linecolor=esi_color if waiting else "black",
            linewidth=2 if waiting else 1,
            text=label,
            textcolor=esi_color if waiting else "black",
            # Let Salabim decide whether these are screen/world coordinates for this queue.
            screen_coordinates=screen_coordinates,
        )
        try:
            ao0 = sim.AnimateRectangle(**rect_kwargs)
        except TypeError:
            # Fallback for versions that don't accept screen_coordinates because Salabim is weird.
            rect_kwargs.pop("screen_coordinates", None)
            ao0 = sim.AnimateRectangle(**rect_kwargs)
        return (28, 18, ao0)

    def process(self):
        # Measure wait from the moment the patient enters the ER.
        arrival_time = self.env.now()
        self._anim_queue = None

        # TRIAGE
        self._safe_move(self.env.q_wait_triage)
        stage_start = self.env.now()
        yield self.request(self.triage, request_priority=self._priority("triage"))
        self.metrics.record_stage_wait("triage", self.esi, self.env.now() - stage_start)
        self._safe_move(self.env.q_in_triage)
        yield self.hold(random.expovariate(1.0 / cfg.MEAN_TRIAGE_TIME))
        self.release(self.triage)
        # After triage completes, assign service time.
        self._assign_service_time()
 
        # BED / TREATMENT SPACE
        # Retain the bed through examination, testing, diagnosis, treatment, and discharge.
        self._safe_move(self.env.q_wait_bed)
        stage_start = self.env.now()
        yield self.request(self.beds, request_priority=self.esi)
        self.metrics.record_stage_wait("bed", self.esi, self.env.now() - stage_start)

        # EXAMINATION (provider)
        # Lower priority value = served first, so ESI 1 (most critical) wins.
        self._safe_move(self.env.q_wait_provider)
        stage_start = self.env.now()
        yield self.request(self.providers, request_priority=self._priority("exam"))
        self.metrics.record_stage_wait("exam", self.esi, self.env.now() - stage_start)
        self._safe_move(self.env.q_in_treatment)
        wait_time = self.env.now() - arrival_time
        self.metrics.record_wait_time(self.esi, wait_time)

        yield self.hold(self.service_time)
        self.release(self.providers)

        # TESTING (bed stays held; the linked Test claims testing_equipment on its own)
        # The patient stays visible in its bed while its Test is shown in the testing lanes.
        self._safe_move(self.env.q_awaiting_test)
        self.testing_done = sim.State("testing_done", value=False)
        stage_start = self.env.now()
        test = Test(
            patient=self,
            testing_equipment=self.env.testing_equipment,
            duration=self._sample("test", self.esi),
        )
        yield self.wait(self.testing_done)
        # Time spent waiting for equipment = elapsed testing time minus the test itself.
        self.metrics.record_stage_wait("testing", self.esi, max(0.0, self.env.now() - stage_start - test.duration))

        # DIAGNOSIS (provider)
        self._safe_move(self.env.q_wait_diagnosis)
        stage_start = self.env.now()
        yield self.request(self.providers, request_priority=self._priority("diagnosis"))
        self.metrics.record_stage_wait("diagnosis", self.esi, self.env.now() - stage_start)
        self._safe_move(self.env.q_in_diagnosis)
        yield self.hold(self._sample("diagnosis", self.esi))
        self.release(self.providers)

        # TREATMENT (nurse, only for some patients; sicker patients need it more often)
        if random.random() < cfg.TREATMENT_PROBABILITY_BY_ESI[self.esi]:
            self._safe_move(self.env.q_wait_treatment)
            stage_start = self.env.now()
            yield self.request(self.triage, request_priority=self._priority("treatment"))
            self.metrics.record_stage_wait("treatment", self.esi, self.env.now() - stage_start)
            self._safe_move(self.env.q_in_treatment_stage)
            yield self.hold(self._sample("treatment", self.esi))
            self.release(self.triage)

        # DISCHARGE / TRANSFER (nurse), then the bed is finally released
        self._safe_move(self.env.q_wait_discharge)
        stage_start = self.env.now()
        yield self.request(self.triage, request_priority=self._priority("discharge"))
        self.metrics.record_stage_wait("discharge", self.esi, self.env.now() - stage_start)
        self._safe_move(self.env.q_in_discharge)
        yield self.hold(self._sample("discharge", self.esi))
        self.release(self.triage)
        self.release(self.beds)

        # Leave the last queue so the box disappears properly
        self._safe_move(None)
        length_of_visit = self.env.now() - arrival_time
        self.metrics.record_length_of_visit(self.esi, length_of_visit)
