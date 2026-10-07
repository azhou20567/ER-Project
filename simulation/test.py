import salabim as sim


class Test(sim.Component):
    """A diagnostic test linked to a Patient; holds testing equipment while the patient keeps its bed."""

    def setup(self, patient, testing_equipment, duration):
        self.patient = patient
        self.testing_equipment = testing_equipment
        self.duration = duration

    def animation_objects(self, *args, **kwargs):
        # Small grey circle so tests look different from patient rectangles.
        circle_kwargs = dict(
            radius=7,
            fillcolor="#b0bec5",
            linecolor="black",
            linewidth=1,
            text=str(self.patient.esi),
            textcolor="black",
            screen_coordinates=kwargs.get("screen_coordinates", True),
        )
        try:
            ao0 = sim.AnimateCircle(**circle_kwargs)
        except TypeError:
            circle_kwargs.pop("screen_coordinates", None)
            ao0 = sim.AnimateCircle(**circle_kwargs)
        return (18, 18, ao0)

    def process(self):
        self.enter(self.env.q_wait_testing)
        yield self.request(self.testing_equipment)
        self.leave(self.env.q_wait_testing)
        self.enter(self.env.q_in_testing)
        yield self.hold(self.duration)
        self.release(self.testing_equipment)
        self.leave(self.env.q_in_testing)
        # Signal the owning patient, which is waiting on this state.
        self.patient.testing_done.set(True)
