"""
This module only deals with visualization (layout, colors, labels). It intentionally does not
change the simulation model or its outcomes.
"""

import math
import salabim as sim
from config import ANIMATION_SPEED, ANIMATION_WIDTH, ANIMATION_HEIGHT

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

    This animates which Patient components enter/leave as they progress:
    - q_wait_triage, q_in_triage
    - q_wait_bed
    - q_wait_provider, q_in_treatment (examination)
    - q_wait_testing, q_in_testing (Test components, not patients)
    - q_wait_diagnosis, q_in_diagnosis
    - q_wait_treatment, q_in_treatment_stage
    - q_wait_discharge, q_in_discharge
    Every stage after the ED bed is entered with the bed held.
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
        show_time=False,  # The "Sim time" label below replaces Salabim's built-in clock.
    )

    white = "#ffffff"
    margin = 12
    _animate_text(
        lambda: f"Sim time: {env.now():.1f} min",
        x=width - margin,
        y=height - margin,
        fontsize=12,
        text_anchor="ne",
        textcolor=white,
    )

    _animate_text(
        "Stages after the ED bed hold a bed; grey circles are tests",
        x=width - margin,
        y=height - 30,
        fontsize=10,
        text_anchor="ne",
        textcolor=white,
    )

    sections = [
        ("Waiting for triage", env.q_wait_triage),
        ("In triage", env.q_in_triage),
        ("Waiting for ED bed", env.q_wait_bed),
        ("Waiting for examination", env.q_wait_provider),
        ("Examination", env.q_in_treatment),
        ("Tests waiting for equipment", env.q_wait_testing),
        ("Tests running", env.q_in_testing),
        ("Waiting for diagnosis", env.q_wait_diagnosis),
        ("Diagnosis", env.q_in_diagnosis),
        ("Waiting for treatment", env.q_wait_treatment),
        ("Treatment", env.q_in_treatment_stage),
        ("Waiting for discharge", env.q_wait_discharge),
        ("Discharge / transfer", env.q_in_discharge),
    ]

    # Layout: columns of stages filling the window, reading top to bottom.
    rows_per_column = 7
    num_columns = math.ceil(len(sections) / rows_per_column)
    column_width = (width - 2 * margin) / num_columns
    header_height = 56
    step = (height - header_height - margin) / rows_per_column
    title_gap = 18
    half_box_width = 14  # Patient boxes are centered on their position and 26 px wide.

    for i, (title, queue) in enumerate(sections):
        x0 = margin + (i // rows_per_column) * column_width
        y_title = height - header_height - (i % rows_per_column) * step
        y_queue = y_title - title_gap

        # Show live counts so we can verify patients are entering later queues.
        _animate_text(
            lambda qq=queue, t=title: f"{t} ({len(qq)})",
            x=x0,
            y=y_title,
            fontsize=10,
            text_anchor="w",
            textcolor=white,
        )
        queue.animate(x=x0 + half_box_width, y=y_queue, direction="e", title="")
