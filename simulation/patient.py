import random
import salabim as sim
import config as cfg


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
        """Determine service time after triage, preserving an explicit duration."""
        if self.service_time is None:
            if self._esi_provided:
                # Preserve the existing fallback for an explicitly supplied ESI.
                self.service_time = cfg.MEAN_SERVICE_TIME
            else:
                # NHAMCS has no direct provider service time; use the synthetic distribution.
                self.service_time = random.expovariate(1.0 / cfg.MEAN_SERVICE_TIME)

    def animation_objects(self, *args, **kwargs):
        # Salabim passes `screen_coordinates` from AnimateQueue.
        screen_coordinates = kwargs.get("screen_coordinates", True)

        def fill(_t=None):
            if getattr(self, "esi", None) is None:
                return "#d0d0d0"
            return {
                1: "#e53935",  # red
                2: "#fb8c00",  # orange
                3: "#fdd835",  # yellow/gold
                4: "#81d4fa",  # light blue
                5: "#a5d6a7",  # light green
            }.get(self.esi, "#d0d0d0")

        def label(_t=None):
            if getattr(self, "esi", None) is None:
                return "?"
            return str(self.esi)

        rect_kwargs = dict(
            spec=(-13, -8, 13, 8),
            fillcolor=fill,
            linecolor="black",
            linewidth=1,
            text=label,
            textcolor="black",
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
        if getattr(cfg, "ANIMATE", False):
            yield self.hold(getattr(cfg, "ANIMATION_STAGE_PAUSE", 0))
        yield self.request(self.triage)
        self._safe_move(self.env.q_in_triage)
        if getattr(cfg, "ANIMATE", False):
            yield self.hold(getattr(cfg, "ANIMATION_STAGE_PAUSE", 0))
        yield self.hold(random.expovariate(1.0 / cfg.MEAN_TRIAGE_TIME))
        self.release(self.triage)
        # After triage completes, assign service time.
        self._assign_service_time()
 
        # BED / TREATMENT SPACE
        # Retain the bed through provider waiting, provider care, and additional care.
        self._safe_move(self.env.q_wait_bed)
        if getattr(cfg, "ANIMATE", False):
            yield self.hold(getattr(cfg, "ANIMATION_STAGE_PAUSE", 0))
        yield self.request(self.beds, request_priority=self.esi)

        # PROVIDER
        # Lower priority value = served first, so ESI 1 (most critical) wins.
        self._safe_move(self.env.q_wait_provider)
        if getattr(cfg, "ANIMATE", False):
            yield self.hold(getattr(cfg, "ANIMATION_STAGE_PAUSE", 0))
        yield self.request(self.providers, request_priority=self.esi)
        self._safe_move(self.env.q_in_treatment)
        if getattr(cfg, "ANIMATE", False):
            yield self.hold(getattr(cfg, "ANIMATION_STAGE_PAUSE", 0))
        wait_time = self.env.now() - arrival_time
        self.metrics.record_wait_time(self.esi, wait_time)
 
        yield self.hold(self.service_time)
        self.release(self.providers)
 
        # ADDITIONAL CARE (bed remains held after provider release)
        self._safe_move(self.env.q_in_bed)
        if getattr(cfg, "ANIMATE", False):
            yield self.hold(getattr(cfg, "ANIMATION_STAGE_PAUSE", 0))
        yield self.hold(random.expovariate(1.0 / cfg.MEAN_BED_TIME))
        self.release(self.beds)

        # Leave the last queue so the box disappears properly
        self._safe_move(None)
        length_of_visit = self.env.now() - arrival_time
        self.metrics.record_length_of_visit(self.esi, length_of_visit)
