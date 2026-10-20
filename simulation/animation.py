"""
This module only deals with visualization (layout, colors, labels). It intentionally does not
change the simulation model or its outcomes.
"""

import salabim as sim
from config import ANIMATION_SPEED

def _animate_text(*args, **kwargs):
    try:
        return sim.AnimateText(*args, **kwargs)
    except TypeError:
        for key in ["textcolor", "fillcolor", "color", "bgcolor", "backgroundcolor"]:
            kwargs.pop(key, None)
        return sim.AnimateText(*args, **kwargs)


def _try_animation_kwargs(env):
    """
    Start animation with best-effort kwargs so coordinates and background are stable.
    """
    try:
        env.animate(True, x0=0, x1=420, y0=0, y1=520, backgroundcolor="#000000")
        return
    except TypeError:
        pass

    try:
        env.animate(True, x0=0, x1=420, y0=0, y1=520)
        return
    except TypeError:
        pass

    env.animate(True)


def _try_set_animation_parameters(env):
    # Background
    for method_name, kwargs in [
        ("animation_parameters", {"backgroundcolor": "#000000"}),
        ("animation_parameters", {"background_color": "#000000"}),
        ("animation_parameters", {"bgcolor": "#000000"}),
    ]:
        method = getattr(env, method_name, None)
        if method is None:
            continue
        try:
            method(**kwargs)
            break
        except TypeError:
            continue

    # Speed
    for method_name, args, kwargs in [
        ("animation_speed", (ANIMATION_SPEED,), {}),
        ("speed", (ANIMATION_SPEED,), {}),
        ("animation_parameters", (), {"speed": ANIMATION_SPEED}),
    ]:
        method = getattr(env, method_name, None)
        if method is None:
            continue
        try:
            method(*args, **kwargs)
            break
        except TypeError:
            continue

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
    _try_animation_kwargs(env)
    _try_set_animation_parameters(env)

    white = "#ffffff"
    _animate_text(
        lambda: f"Sim time: {env.now():.1f} min",
        x=350,
        y=12,
        fontsize=12,
        xy_anchor="ne",
        textcolor=white,
    )

    _animate_text(
        "Stages after the ED bed hold a bed; grey circles are tests",
        x=350,
        y=30,
        fontsize=10,
        xy_anchor="ne",
        textcolor=white,
    )

    # Layout: two columns so all 13 stages are visible.
    column_width = 512
    rows_per_column = 7
    title_gap = 14
    step = 72
    y0 = 56

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

    for i, (title, queue) in enumerate(sections):
        x0 = 12 + (i // rows_per_column) * column_width
        y_title = y0 + (i % rows_per_column) * step
        y_queue = y_title + title_gap

        # Show live counts so we can verify patients are entering later queues.
        _animate_text(
            lambda qq=queue, t=title: f"{t} ({len(qq)})",
            x=x0,
            y=y_title,
            fontsize=10,
            xy_anchor="w",
            textcolor=white,
        )
        queue.animate(x=x0, y=y_queue, direction="e", title="")
