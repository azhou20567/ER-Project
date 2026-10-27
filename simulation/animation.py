"""
This module only deals with visualization (layout, colors, labels). It intentionally does not
change the simulation model or its outcomes.
"""

import salabim as sim
from config import ANIMATION_SPEED, ANIMATION_WIDTH, ANIMATION_HEIGHT
from simulation.esi import ESI_COLORS

def _animate_text(*args, **kwargs):
    try:
        return sim.AnimateText(*args, **kwargs)
    except TypeError:
        for key in ["textcolor", "fillcolor", "color", "bgcolor", "backgroundcolor"]:
            kwargs.pop(key, None)
        return sim.AnimateText(*args, **kwargs)


def setup_animation(env):
    """
    Configure Salabim's built-in animation window for this simulation.

    Each stage is one row: patients waiting on the left (outlined boxes), patients being
    served on the right (solid boxes). Stages inside the "ED beds" box are entered with the
    bed held, so that box shows why patients back up in "Waiting for ED bed".
    Test components are drawn as circles in the testing row while their patient stays
    visible in "Awaiting results".
    """
    # World coordinates match pixels: (0, 0) is bottom-left, (width, height) is top-right.
    width, height = ANIMATION_WIDTH, ANIMATION_HEIGHT
    env.animation_parameters(
        animate=True,
        width=width,
        height=height,
        x0=0,
        y0=0,
        x1=width,
        background_color="#000000",
        speed=ANIMATION_SPEED,
        title="ER Simulation",
        show_time=False,  # The clock label below replaces Salabim's built-in clock.
    )

    white = "#ffffff"
    grey = "#9e9e9e"
    red = "#ef5350"
    blue = "#4fc3f7"
    margin = 12

    # Simulation time zero is midnight, so show the time of day as well as minutes.
    def clock():
        t = env.now()
        minute_of_day = int(t % 1440)
        return f"Day {int(t // 1440) + 1}  {minute_of_day // 60:02d}:{minute_of_day % 60:02d}   (t = {t:.0f} min)"

    _animate_text(clock, x=width - margin, y=height - margin, fontsize=13, text_anchor="ne", textcolor=white)

    # Legend, below Salabim's menu buttons in the top-left corner.
    y_legend = height - 48
    _animate_text("ESI", x=margin, y=y_legend, fontsize=10, text_anchor="w", textcolor=white)
    for esi, color in ESI_COLORS.items():
        x = margin + 30 + (esi - 1) * 30
        sim.AnimateRectangle(
            spec=(x, y_legend - 8, x + 26, y_legend + 8),
            fillcolor=color,
            linecolor="black",
            text=str(esi),
            textcolor="black",
        )
    _animate_text(
        "outlined = waiting    solid = being served    circle = test",
        x=margin + 190,
        y=y_legend,
        fontsize=10,
        text_anchor="w",
        textcolor=white,
    )

    def busy(resource, label, note=""):
        """Label showing how much of a resource is in use; turns red when all of it is in use."""
        def text():
            return f"{label} {resource.claimed_quantity():g}/{resource.capacity():g} busy{note}"

        def color():
            return red if resource.available_quantity() <= 0 else grey

        return text, color

    def shared(resource_name, other_stages):
        return lambda: f"uses {resource_name}, shared w/ {other_stages}", lambda: grey

    rows = [
        # (stage, waiting queue, being-served queue, (resource label, label color))
        ("Triage", env.q_wait_triage, env.q_in_triage, busy(env.nurses, "nurses", " (also treat/discharge)")),
        ("ED bed", env.q_wait_bed, None, busy(env.beds, "beds")),
        ("Examination", env.q_wait_provider, env.q_in_treatment, busy(env.providers, "providers", " (also diagnosis)")),
        ("Testing", env.q_wait_testing, env.q_in_testing, busy(env.testing_equipment, "testing stations")),
        ("Awaiting results", None, env.q_awaiting_test, (lambda: "patient waits in bed for its test", lambda: grey)),
        ("Diagnosis", env.q_wait_diagnosis, env.q_in_diagnosis, shared("providers", "exam")),
        ("Treatment", env.q_wait_treatment, env.q_in_treatment_stage, shared("nurses", "triage")),
        ("Discharge", env.q_wait_discharge, env.q_in_discharge, shared("nurses", "triage")),
    ]
    first_bed_row = 2  # Rows from here on are inside the ED beds box.

    # Columns: stage label | waiting line | arrow | being served.
    box_width = 28  # Patient boxes are 26 px wide plus a gap; they are centered on their position.
    x_wait = 230
    x_arrow = 610
    x_serve = 650
    overflow_room = 60  # Space left at the end of each line for the "+N more" label.
    max_waiting = int((x_arrow - x_wait - overflow_room) / box_width)
    max_serving = int((width - margin - x_serve - overflow_room) / box_width)

    y_headers = height - 80
    _animate_text("WAITING", x=x_wait - 14, y=y_headers, fontsize=10, text_anchor="w", textcolor=grey)
    _animate_text("BEING SERVED", x=x_serve - 14, y=y_headers, fontsize=10, text_anchor="w", textcolor=grey)

    y_first = height - 112
    step = (y_first - 46) / (len(rows) - 1)

    def lane(queue, x, max_length, kind, y):
        queue.animate(x=x + 14, y=y, direction="e", max_length=max_length, title="", id=kind)
        # Count of patients that don't fit on screen.
        _animate_text(
            lambda: f"+{len(queue) - max_length} more" if len(queue) > max_length else "",
            x=x + max_length * box_width + 6,
            y=y,
            fontsize=10,
            text_anchor="w",
            textcolor=white,
        )

    for i, (stage, waiting, serving, (resource_text, resource_color)) in enumerate(rows):
        y = y_first - i * step
        x_label = margin + (12 if i >= first_bed_row else 0)
        _animate_text(stage, x=x_label, y=y + 7, fontsize=12, text_anchor="w", textcolor=white)
        _animate_text(resource_text, x=x_label, y=y - 9, fontsize=9, text_anchor="w", textcolor=resource_color)
        if waiting is not None:
            lane(waiting, x_wait, max_waiting, "waiting", y)
        if waiting is not None and serving is not None:
            _animate_text("→", x=x_arrow + 10, y=y, fontsize=16, text_anchor="c", textcolor=grey)
        if serving is not None:
            lane(serving, x_serve, max_serving, "serving", y)

    # Patients leave "Waiting for ED bed" into the box below once a bed frees up.
    _animate_text(
        "↓ into a free bed",
        x=x_serve - 14,
        y=y_first - step,
        fontsize=11,
        text_anchor="w",
        textcolor=grey,
    )

    # The ED beds box: everything inside it is done while holding a bed.
    def bed_color():
        return red if env.beds.available_quantity() <= 0 else blue

    box_top = y_first - (first_bed_row - 0.5) * step
    box_bottom = y_first - (len(rows) - 0.5) * step
    sim.AnimateRectangle(
        spec=(margin / 2, box_bottom, width - margin / 2, box_top),
        fillcolor="#0c1a24",
        linecolor=bed_color,
        linewidth=2,
        layer=10,  # Drawn behind the patients.
    )
    _animate_text(
        lambda: f"ED BEDS {env.beds.claimed_quantity():g}/{env.beds.capacity():g} occupied: every patient in this box holds a bed",
        x=width / 2,
        y=box_top - 12,
        fontsize=11,
        text_anchor="c",
        textcolor=bed_color,
    )
